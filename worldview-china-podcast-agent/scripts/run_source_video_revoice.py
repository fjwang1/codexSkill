#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


WIDTH = 3840
HEIGHT = 2160
FPS = 30
SUBTITLE_OVERLAY_W = 3480
SUBTITLE_OVERLAY_H = 300
SUBTITLE_OVERLAY_X = 180
SUBTITLE_OVERLAY_Y = 1648
SUBTITLE_TOP_Y = 1808
SUBTITLE_TOP_MAX_Y = 1878
SUBTITLE_BOTTOM_Y = 1948
SUBTITLE_FONT_SIZE_PX = 96
LETTER_SPACING_PX = 6
SUBTITLE_FAUX_ITALIC_SHEAR = 0.10
SUBTITLE_SHADOW_BLUR_PX = 2
SUBTITLE_SHADOW_OFFSET = (6, 8)
SUBTITLE_SHADOW_ALPHA = 96
SUBTITLE_OUTLINE_WIDTH_PX = 3
SUBTITLE_OUTLINE_FILL = (30, 30, 30, 145)
SUBTITLE_OUTLINE_COLOR = "rgba(30,30,30,0.57)"
SUBTITLE_GLYPH_EDGE_PAD_PX = 72
SUBTITLE_SHEAR_EDGE_PAD_PX = 24
SUBTITLE_FONT_PATH = Path("/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf")
SUBTITLE_FONT_FAMILY = "NotoSansCJKsc-Bold"
SUBTITLE_FONT_FULL_NAME = "Noto Sans CJK SC Bold"
SUBTITLE_FONT_LICENSE_NOTE = "SIL Open Font License 1.1"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _duration(path: Path) -> float:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		str(path),
	])
	return float(result.stdout.strip())


def _probe(path: Path) -> dict[str, Any]:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_streams",
		"-show_format",
		"-of",
		"json",
		str(path),
	])
	return json.loads(result.stdout)


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _copy_if_exists(src: Path, dst: Path) -> str | None:
	if not src.exists():
		return None
	dst.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(src, dst)
	return str(dst)


def _encoder_exists(name: str) -> bool:
	result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	return name in result.stdout


def _filter_quote(path: Path) -> str:
	text = path.resolve().as_posix()
	text = text.replace("\\", "\\\\").replace("'", "\\'")
	return f"'{text}'"


def _subtitle_filter(subtitles_ass: Path) -> str:
	fonts_dir = Path("/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts")
	assert subtitles_ass.exists(), f"Missing subtitles ASS: {subtitles_ass}"
	assert fonts_dir.exists(), f"Missing subtitle fonts dir: {fonts_dir}"
	return (
		f"subtitles=filename={_filter_quote(subtitles_ass)}:"
		f"fontsdir={_filter_quote(fonts_dir)}:"
		"original_size=3840x2160"
	)


def _video_encoder_args(video_encoder: str, video_bitrate: str) -> tuple[str, list[str]]:
	if video_encoder == "h264_videotoolbox":
		if _encoder_exists("h264_videotoolbox"):
			return video_encoder, [
				"-c:v",
				"h264_videotoolbox",
				"-b:v",
				video_bitrate,
				"-pix_fmt",
				"yuv420p",
				"-tag:v",
				"avc1",
			]
		video_encoder = "libx264"
	if video_encoder == "libx264":
		return video_encoder, [
			"-c:v",
			"libx264",
			"-preset",
			"veryfast",
			"-crf",
			"18",
			"-pix_fmt",
			"yuv420p",
			"-tag:v",
			"avc1",
		]
	raise AssertionError(f"Unsupported video encoder: {video_encoder}")


def _first_stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any]:
	for stream in probe.get("streams") or []:
		if stream.get("codec_type") == codec_type:
			return stream
	raise AssertionError(f"Missing {codec_type} stream")


def _ffconcat_path(path: Path) -> str:
	return str(path).replace("'", "'\\''")


def _font(size: int) -> Any:
	from PIL import ImageFont

	assert SUBTITLE_FONT_PATH.exists(), f"Missing subtitle font: {SUBTITLE_FONT_PATH}"
	return ImageFont.truetype(str(SUBTITLE_FONT_PATH), size)


def _measure_spaced(draw: Any, text: str, font: Any, spacing: int, stroke: int) -> tuple[int, int]:
	width = 0
	height = 0
	for index, char in enumerate(text):
		box = draw.textbbox((0, 0), char, font=font, stroke_width=stroke)
		width += box[2] - box[0]
		height = max(height, box[3] - box[1])
		if index < len(text) - 1:
			width += spacing
	return width + round(abs(SUBTITLE_FAUX_ITALIC_SHEAR) * height) + SUBTITLE_GLYPH_EDGE_PAD_PX * 2, height


def _draw_spaced_text(canvas: Any, text: str, font: Any, box: tuple[int, int, int, int], spacing: int) -> dict[str, float | int | str]:
	from PIL import Image, ImageDraw, ImageFilter

	stroke = SUBTITLE_OUTLINE_WIDTH_PX
	x0, y0, x1, y1 = box
	measure_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
	width, height = _measure_spaced(measure_draw, text, font, spacing, stroke)
	available_width = x1 - x0
	assert width <= available_width, (
		f"Subtitle cue is too wide at fixed {SUBTITLE_FONT_SIZE_PX}px font; "
		f"split it during subtitle generation instead of shrinking: width={width}, available={available_width}, text={text!r}"
	)
	layer_pad = SUBTITLE_GLYPH_EDGE_PAD_PX
	layer = Image.new("RGBA", (width + layer_pad * 2, height + layer_pad * 2 + SUBTITLE_SHADOW_OFFSET[1]), (0, 0, 0, 0))
	shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
	layer_draw = ImageDraw.Draw(layer)
	shadow_draw = ImageDraw.Draw(shadow)
	x = layer_pad
	y = layer_pad
	for char in text:
		shadow_draw.text((x + SUBTITLE_SHADOW_OFFSET[0], y + SUBTITLE_SHADOW_OFFSET[1]), char, font=font, fill=(0, 0, 0, SUBTITLE_SHADOW_ALPHA))
		layer_draw.text((x, y), char, font=font, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=SUBTITLE_OUTLINE_FILL)
		char_box = layer_draw.textbbox((0, 0), char, font=font, stroke_width=stroke)
		x += char_box[2] - char_box[0] + spacing
	shadow = shadow.filter(ImageFilter.GaussianBlur(SUBTITLE_SHADOW_BLUR_PX))
	shadow.alpha_composite(layer)
	content = shadow.crop(shadow.getbbox() or (0, 0, shadow.width, shadow.height))
	shear = SUBTITLE_FAUX_ITALIC_SHEAR
	if abs(shear) > 0.0001:
		shear_extra = round(abs(shear) * content.height)
		shear_shift = (shear_extra if shear > 0 else 0) + SUBTITLE_SHEAR_EDGE_PAD_PX
		content = content.transform(
			(content.width + shear_extra + SUBTITLE_SHEAR_EDGE_PAD_PX * 2, content.height),
			Image.Transform.AFFINE,
			(1, shear, -shear_shift, 0, 1, 0),
			Image.Resampling.BICUBIC,
		)
	content_bbox = content.getbbox() or (0, 0, content.width, content.height)
	content_bbox = (
		max(0, content_bbox[0] - SUBTITLE_SHEAR_EDGE_PAD_PX),
		max(0, content_bbox[1] - SUBTITLE_SHEAR_EDGE_PAD_PX),
		min(content.width, content_bbox[2] + SUBTITLE_SHEAR_EDGE_PAD_PX),
		min(content.height, content_bbox[3] + SUBTITLE_SHEAR_EDGE_PAD_PX),
	)
	content = content.crop(content_bbox)
	paste_x = x0 + (x1 - x0 - content.width) // 2
	paste_y = y0 + (y1 - y0 - content.height) // 2
	canvas.alpha_composite(content, (paste_x, paste_y))
	return {
		"top_y": SUBTITLE_OVERLAY_Y + paste_y,
		"bottom_y": SUBTITLE_OVERLAY_Y + paste_y + content.height,
		"font_family": SUBTITLE_FONT_FAMILY,
		"font_full_name": SUBTITLE_FONT_FULL_NAME,
		"font_file": str(SUBTITLE_FONT_PATH),
		"font_size_px": getattr(font, "size", SUBTITLE_FONT_SIZE_PX),
		"line_count": 1,
		"letter_spacing_px": spacing,
		"text_width_px": content.width,
		"available_width_px": available_width,
		"outline": "subtle_translucent_outline",
		"outline_width_px": SUBTITLE_OUTLINE_WIDTH_PX,
		"outline_color": SUBTITLE_OUTLINE_COLOR,
		"shadow": "soft_drop_shadow",
		"shadow_blur_px": SUBTITLE_SHADOW_BLUR_PX,
		"faux_italic_shear": SUBTITLE_FAUX_ITALIC_SHEAR,
		"glyph_edge_pad_px": SUBTITLE_GLYPH_EDGE_PAD_PX,
		"shear_edge_pad_px": SUBTITLE_SHEAR_EDGE_PAD_PX,
		"shear_transform": "forward_x_plus_shear_y_with_positive_padding",
		"overflow_policy": "split_overlong_cues_no_font_shrink",
	}


def _render_subtitle_images(overlay_dir: Path, cues: list[dict[str, Any]]) -> tuple[Path, list[dict[str, Any]]]:
	from PIL import Image

	overlay_dir.mkdir(parents=True, exist_ok=True)
	blank = overlay_dir / "blank.png"
	Image.new("RGBA", (SUBTITLE_OVERLAY_W, SUBTITLE_OVERLAY_H), (0, 0, 0, 0)).save(blank)
	layouts: list[dict[str, Any]] = []
	font = _font(SUBTITLE_FONT_SIZE_PX)
	for cue in cues:
		img = Image.new("RGBA", (SUBTITLE_OVERLAY_W, SUBTITLE_OVERLAY_H), (0, 0, 0, 0))
		text = re.sub(r"\s+", " ", str(cue.get("display_text") or cue.get("text") or "")).strip()
		layout = _draw_spaced_text(
			img,
			text,
			font,
			(
				80,
				SUBTITLE_TOP_Y - SUBTITLE_OVERLAY_Y,
				SUBTITLE_OVERLAY_W - 80,
				min(SUBTITLE_OVERLAY_H, SUBTITLE_BOTTOM_Y - SUBTITLE_OVERLAY_Y),
			),
			LETTER_SPACING_PX,
		)
		index = int(cue.get("index") or cue.get("cue_index"))
		path = overlay_dir / f"cue_{index:04d}.png"
		img.save(path)
		layouts.append({"cue_index": index, "path": str(path), "layout": layout})
	return blank, layouts


def _render_subtitle_overlay_video(work_dir: Path, subtitle_manifest: Path, target_duration: float) -> tuple[Path, list[dict[str, Any]]]:
	manifest = _read_json(subtitle_manifest)
	cues = list(manifest.get("cues") or [])
	assert cues, f"Subtitle manifest has no cues: {subtitle_manifest}"
	overlay_dir = work_dir / "subtitle-overlays"
	blank, layouts = _render_subtitle_images(overlay_dir, cues)
	layout_by_cue = {int(item["cue_index"]): Path(item["path"]) for item in layouts}
	concat_path = work_dir / "subtitle_overlay_concat.ffconcat"
	boundaries = {0.0, target_duration}
	for cue in cues:
		start = max(0.0, min(target_duration, float(cue["start_sec"])))
		end = max(0.0, min(target_duration, float(cue["end_sec"])))
		if end > start:
			boundaries.add(start)
			boundaries.add(end)
	points = sorted(boundaries)
	with concat_path.open("w", encoding="utf-8") as handle:
		handle.write("ffconcat version 1.0\n")
		last_path = blank
		for start, end in zip(points, points[1:]):
			duration = end - start
			if duration <= 0.01:
				continue
			active = [
				cue
				for cue in cues
				if float(cue["start_sec"]) <= start + 0.001 and float(cue["end_sec"]) > start + 0.001
			]
			if active:
				cue = max(active, key=lambda item: (float(item["start_sec"]), int(item.get("index") or item.get("cue_index") or 0)))
				path = layout_by_cue[int(cue.get("index") or cue.get("cue_index"))]
			else:
				path = blank
			handle.write(f"file '{_ffconcat_path(path)}'\n")
			handle.write(f"duration {duration:.3f}\n")
			last_path = path
		handle.write(f"file '{_ffconcat_path(last_path)}'\n")
	overlay_video = work_dir / "subtitle_overlay.mov"
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"concat",
		"-safe",
		"0",
		"-i",
		str(concat_path),
		"-vf",
		f"fps={FPS},format=argb",
		"-c:v",
		"qtrle",
		"-pix_fmt",
		"argb",
		"-t",
		f"{target_duration:.3f}",
		str(overlay_video),
	])
	return overlay_video, layouts


def _extract_review_video_segment(source: Path, output: Path, start_sec: float, duration_sec: float) -> Path:
	output.parent.mkdir(parents=True, exist_ok=True)
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-ss",
		f"{start_sec:.3f}",
		"-i",
		str(source),
		"-t",
		f"{duration_sec:.3f}",
		"-map",
		"0:v:0",
		"-an",
		"-c:v",
		"libx264",
		"-preset",
		"veryfast",
		"-crf",
		"18",
		"-pix_fmt",
		"yuv420p",
		"-movflags",
		"+faststart",
		str(output),
	])
	return output


def _compose_video_copy(video_input: Path, audio_input: Path, output: Path, target_duration: float, allow_trim_audio: bool) -> None:
	audio_duration = _duration(audio_input)
	if audio_duration > target_duration + 0.3 and not allow_trim_audio:
		raise AssertionError(
			f"Chinese audio is longer than target video: audio={audio_duration:.3f}s video={target_duration:.3f}s. "
			"Fix upstream audio duration or pass --allow-trim-audio only for review samples."
		)
	output.parent.mkdir(parents=True, exist_ok=True)
	tmp = output.with_suffix(output.suffix + ".tmp.mp4")
	if tmp.exists():
		tmp.unlink()
	af = "apad"
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(video_input),
		"-i",
		str(audio_input),
		"-map",
		"0:v:0",
		"-map",
		"1:a:0",
		"-c:v",
		"copy",
		"-c:a",
		"aac",
		"-b:a",
		"192k",
		"-af",
		af,
		"-t",
		f"{target_duration:.3f}",
		"-movflags",
		"+faststart",
		str(tmp),
	])
	probe = _probe(tmp)
	_first_stream(probe, "video")
	_first_stream(probe, "audio")
	size_1 = tmp.stat().st_size
	time.sleep(0.5)
	size_2 = tmp.stat().st_size
	assert size_1 == size_2 and size_2 > 0, f"Temporary final video size is unstable: {size_1} -> {size_2}"
	if output.exists():
		output.unlink()
	tmp.replace(output)


def _compose_video_burned_subtitles(
	video_input: Path,
	audio_input: Path,
	subtitle_manifest: Path,
	work_dir: Path,
	output: Path,
	target_duration: float,
	allow_trim_audio: bool,
	video_encoder: str,
	video_bitrate: str,
) -> dict[str, Any]:
	audio_duration = _duration(audio_input)
	if audio_duration > target_duration + 0.3 and not allow_trim_audio:
		raise AssertionError(
			f"Chinese audio is longer than target video: audio={audio_duration:.3f}s video={target_duration:.3f}s. "
			"Fix upstream audio duration or pass --allow-trim-audio only for review samples."
		)
	output.parent.mkdir(parents=True, exist_ok=True)
	tmp = output.with_suffix(output.suffix + ".tmp.mp4")
	if tmp.exists():
		tmp.unlink()
	resolved_encoder, encoder_args = _video_encoder_args(video_encoder, video_bitrate)
	overlay_video, layouts = _render_subtitle_overlay_video(work_dir, subtitle_manifest, target_duration)
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(video_input),
		"-i",
		str(audio_input),
		"-i",
		str(overlay_video),
		"-filter_complex",
		f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}[base];"
		f"[base][2:v]overlay={SUBTITLE_OVERLAY_X}:{SUBTITLE_OVERLAY_Y}:format=auto:shortest=1,format=yuv420p[vout]",
		"-map",
		"[vout]",
		"-map",
		"1:a:0",
		*encoder_args,
		"-c:a",
		"aac",
		"-b:a",
		"192k",
		"-af",
		"apad",
		"-t",
		f"{target_duration:.3f}",
		"-movflags",
		"+faststart",
		str(tmp),
	])
	probe = _probe(tmp)
	_first_stream(probe, "video")
	_first_stream(probe, "audio")
	size_1 = tmp.stat().st_size
	time.sleep(0.5)
	size_2 = tmp.stat().st_size
	assert size_1 == size_2 and size_2 > 0, f"Temporary burned-subtitle video size is unstable: {size_1} -> {size_2}"
	if output.exists():
		output.unlink()
	tmp.replace(output)
	return {
		"method": "pillow_overlay_video_ffmpeg_overlay",
		"subtitle_manifest": str(subtitle_manifest),
		"overlay_video": str(overlay_video),
		"cue_count": len(layouts),
		"subtitle_layout_rule": {
			"subtitle_overlay_x": SUBTITLE_OVERLAY_X,
			"subtitle_overlay_y": SUBTITLE_OVERLAY_Y,
			"subtitle_overlay_width": SUBTITLE_OVERLAY_W,
			"subtitle_overlay_height": SUBTITLE_OVERLAY_H,
			"subtitle_block_top_min_y": SUBTITLE_TOP_Y,
			"subtitle_block_top_max_y": SUBTITLE_TOP_MAX_Y,
			"subtitle_block_bottom_max_y": SUBTITLE_BOTTOM_Y,
			"font_family": SUBTITLE_FONT_FAMILY,
			"font_full_name": SUBTITLE_FONT_FULL_NAME,
			"font_file": str(SUBTITLE_FONT_PATH),
			"font_license_note": SUBTITLE_FONT_LICENSE_NOTE,
			"font_size_px": SUBTITLE_FONT_SIZE_PX,
			"letter_spacing_px": LETTER_SPACING_PX,
			"outline": "subtle_translucent_outline",
			"outline_width_px": SUBTITLE_OUTLINE_WIDTH_PX,
			"outline_color": SUBTITLE_OUTLINE_COLOR,
			"shadow": "soft_drop_shadow",
			"shadow_blur_px": SUBTITLE_SHADOW_BLUR_PX,
			"faux_italic_shear": SUBTITLE_FAUX_ITALIC_SHEAR,
			"glyph_edge_pad_px": SUBTITLE_GLYPH_EDGE_PAD_PX,
			"shear_edge_pad_px": SUBTITLE_SHEAR_EDGE_PAD_PX,
			"shear_transform": "forward_x_plus_shear_y_with_positive_padding",
			"overlap_policy": "latest_started_cue_visible",
		},
		"subtitle_layouts": layouts,
		"video_encoder": resolved_encoder,
		"video_bitrate": video_bitrate if resolved_encoder == "h264_videotoolbox" else None,
		"subtitle_style_reference": "article-podcast-subtitle-alignment",
	}


def _extract_screenshots(video: Path, screenshots_dir: Path, duration: float) -> dict[str, str]:
	screenshots_dir.mkdir(parents=True, exist_ok=True)
	points = {
		"opening": min(max(3.0, duration * 0.05), max(0.0, duration - 1.0)),
		"middle": max(0.0, duration / 2.0),
		"end": max(0.0, duration - min(5.0, duration * 0.05)),
	}
	paths: dict[str, str] = {}
	for name, seconds in points.items():
		path = screenshots_dir / f"{name}.png"
		_run([
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-ss",
			f"{seconds:.3f}",
			"-i",
			str(video),
			"-frames:v",
			"1",
			str(path),
		])
		paths[name] = str(path)
	return paths


def run_revoice(
	run_dir: Path,
	source_video: Path | None,
	audio: Path | None,
	force: bool,
	source_start_sec: float | None,
	match_audio_duration: bool,
	allow_trim_audio: bool,
	burn_subtitles: bool,
	subtitle_manifest: Path | None,
	subtitles_ass: Path | None,
	video_encoder: str,
	video_bitrate: str,
	update_root: bool,
) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	source = (source_video or run_dir / "02-source-capture/youtube-media/source.mp4").resolve()
	audio_path = (audio or run_dir / "audio/final_podcast.wav").resolve()
	assert source.exists(), f"Missing source video: {source}"
	assert audio_path.exists(), f"Missing Chinese audio: {audio_path}"
	output_dir = run_dir / "08-source-video-revoice"
	work_dir = output_dir / "work"
	video_root = run_dir / "video"
	output_dir.mkdir(parents=True, exist_ok=True)
	work_dir.mkdir(parents=True, exist_ok=True)
	video_root.mkdir(parents=True, exist_ok=True)

	source_duration = _duration(source)
	audio_duration = _duration(audio_path)
	trim_to_audio_duration = source_start_sec is None and match_audio_duration
	review_sample = source_start_sec is not None
	if match_audio_duration:
		target_duration = audio_duration
	else:
		target_duration = source_duration
	if source_start_sec is not None:
		video_input = _extract_review_video_segment(
			source,
			work_dir / "source_review_segment.mp4",
			source_start_sec,
			target_duration,
		)
		video_copy_policy = "source_segment_reencoded_review_sample"
	else:
		video_input = source
		video_copy_policy = "source_video_stream_copy_trimmed_to_audio_duration" if trim_to_audio_duration else "source_video_stream_copy"

	final_video = output_dir / "final_video.mp4"
	burned_subtitle_render: dict[str, Any] | None = None
	if force or not final_video.exists():
		if burn_subtitles:
			subtitle_manifest_path = (subtitle_manifest or run_dir / "video/subtitle_manifest.json").resolve()
			burned_subtitle_render = _compose_video_burned_subtitles(
				video_input,
				audio_path,
				subtitle_manifest_path,
				work_dir,
				final_video,
				target_duration,
				allow_trim_audio or review_sample,
				video_encoder,
				video_bitrate,
			)
			video_copy_policy = "source_video_reencoded_with_burned_ass_subtitles"
		else:
			_compose_video_copy(video_input, audio_path, final_video, target_duration, allow_trim_audio or review_sample)

	final_duration = _duration(final_video)
	source_probe = _probe(source)
	final_probe = _probe(final_video)
	source_video_stream = _first_stream(source_probe, "video")
	final_video_stream = _first_stream(final_probe, "video")
	final_audio_stream = _first_stream(final_probe, "audio")
	srt_copy = _copy_if_exists(run_dir / "video/final_subtitles.srt", output_dir / "subtitles/final_subtitles.srt")
	ass_source = (subtitles_ass or run_dir / "video/final_subtitles.ass").resolve()
	ass_copy = _copy_if_exists(ass_source, output_dir / "subtitles/final_subtitles.ass")
	audio_copy = _copy_if_exists(audio_path, output_dir / "audio/final_podcast.wav")
	screenshots = _extract_screenshots(final_video, output_dir / "screenshots", final_duration)
	if update_root:
		shutil.copy2(final_video, video_root / "final_video.mp4")
	visual_mode = (
		"source_video_revoice_burned_subtitles_trim_to_audio_duration"
		if burn_subtitles and trim_to_audio_duration
		else "source_video_revoice_burned_subtitles"
		if burn_subtitles
		else "source_video_revoice_trim_to_audio_duration"
		if trim_to_audio_duration
		else "source_video_revoice_strict"
		if not review_sample
		else "source_video_revoice_review_sample"
	)
	manifest = {
		"schema_version": "worldview-china-podcast-source-video-revoice.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"visual_mode": visual_mode,
		"review_sample": review_sample,
		"playback_speed": 1.0,
		"subtitle_mode": "burned_ass" if burn_subtitles else "sidecar_not_burned",
		"burned_subtitle_render": burned_subtitle_render,
		"source_video": str(source),
		"source_video_sha256": _sha256(source),
		"source_duration_sec": round(source_duration, 3),
		"source_start_sec": source_start_sec,
		"video_input": str(video_input),
		"video_copy_policy": video_copy_policy,
		"audio": str(audio_path),
		"audio_sha256": _sha256(audio_path),
		"audio_duration_sec": round(audio_duration, 3),
		"target_duration_sec": round(target_duration, 3),
		"final_video": str(final_video),
		"final_video_sha256": _sha256(final_video),
		"final_duration_sec": round(final_duration, 3),
		"duration_delta_audio_vs_final_sec": round(audio_duration - final_duration, 3),
		"source_video_stream": source_video_stream,
		"final_video_stream": final_video_stream,
		"final_audio_stream": final_audio_stream,
		"sidecar_subtitles": {
			"srt": srt_copy,
			"ass": ass_copy,
		},
		"copied_audio": audio_copy,
		"screenshots": screenshots,
		"outputs": {
			"final_video": str(final_video),
			"root_final_video": str(video_root / "final_video.mp4") if update_root else None,
			"render_manifest": str(output_dir / "render_manifest.json"),
			"render_report": str(output_dir / "render_report.md"),
		},
	}
	_write_json(output_dir / "render_manifest.json", manifest)
	if update_root:
		shutil.copy2(output_dir / "render_manifest.json", video_root / "render_manifest.json")
	report = [
		"# Source Video Revoice Render Report",
		"",
		f"- visual_mode: {manifest['visual_mode']}",
		f"- review_sample: {str(review_sample).lower()}",
		f"- source_video: `{source}`",
		f"- source_duration_sec: {source_duration:.3f}",
		f"- source_start_sec: {source_start_sec if source_start_sec is not None else 'full_source'}",
		f"- chinese_audio: `{audio_path}`",
		f"- audio_duration_sec: {audio_duration:.3f}",
		f"- target_duration_sec: {target_duration:.3f}",
		f"- final_video: `{final_video}`",
		f"- final_duration_sec: {final_duration:.3f}",
		f"- video_copy_policy: {video_copy_policy}",
		f"- subtitle_mode: {manifest['subtitle_mode']}",
		f"- burned_subtitle_render: {burned_subtitle_render['method'] if burned_subtitle_render else 'none'}",
		"- note: strict final delivery keeps source video frames unchanged and replaces only the audio track; burned-subtitle delivery is a separate visual derivative because subtitle overlay requires video re-encoding.",
	]
	(output_dir / "render_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
	if update_root:
		shutil.copy2(output_dir / "render_report.md", video_root / "render_report.md")
	return manifest


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Compose a Worldview China podcast video by preserving source video visuals and replacing the audio track.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--source-video", type=Path)
	parser.add_argument("--audio", type=Path)
	parser.add_argument("--source-start-sec", type=float)
	parser.add_argument("--match-audio-duration", action="store_true", help="Review-sample mode: cut source visuals to the Chinese audio duration.")
	parser.add_argument("--allow-trim-audio", action="store_true", help="Allow cutting Chinese audio to target video duration; use only for review samples.")
	parser.add_argument("--burn-subtitles", action="store_true", help="Burn subtitles into the source-video render using video/subtitle_manifest.json timings and article-video subtitle style. This re-encodes the video.")
	parser.add_argument("--subtitle-manifest", type=Path, help="Subtitle manifest to burn. Defaults to <run_dir>/video/subtitle_manifest.json.")
	parser.add_argument("--subtitles-ass", type=Path, help="Sidecar ASS subtitle path to copy. Defaults to <run_dir>/video/final_subtitles.ass.")
	parser.add_argument("--video-encoder", choices=["h264_videotoolbox", "libx264"], default="h264_videotoolbox")
	parser.add_argument("--video-bitrate", default="18000k", help="Bitrate used by h264_videotoolbox burned-subtitle renders.")
	parser.add_argument("--no-update-root", action="store_true")
	parser.add_argument("--force", action="store_true")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	manifest = run_revoice(
		run_dir=args.run_dir,
		source_video=args.source_video,
		audio=args.audio,
		force=args.force,
		source_start_sec=args.source_start_sec,
		match_audio_duration=args.match_audio_duration,
		allow_trim_audio=args.allow_trim_audio,
		burn_subtitles=args.burn_subtitles,
		subtitle_manifest=args.subtitle_manifest,
		subtitles_ass=args.subtitles_ass,
		video_encoder=args.video_encoder,
		video_bitrate=args.video_bitrate,
		update_root=not args.no_update_root,
	)
	print(json.dumps({
		"final_video": manifest["final_video"],
		"visual_mode": manifest["visual_mode"],
		"subtitle_mode": manifest["subtitle_mode"],
		"duration_sec": manifest["final_duration_sec"],
		"render_manifest": manifest["outputs"]["render_manifest"],
	}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
