#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


DEFAULT_FONT = Path("/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf")
DEFAULT_FONTS_DIR = Path("/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


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


def _ffprobe(path: Path) -> dict[str, Any]:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration:stream=index,codec_type,codec_name,width,height",
		"-of",
		"json",
		str(path),
	])
	return json.loads(result.stdout)


def _font(size: int) -> ImageFont.FreeTypeFont:
	assert DEFAULT_FONT.exists(), f"Missing font: {DEFAULT_FONT}"
	return ImageFont.truetype(str(DEFAULT_FONT), size)


def _cover_crop(image: Image.Image, width: int, height: int) -> Image.Image:
	source = image.convert("RGB")
	ratio = width / height
	source_ratio = source.width / source.height
	if source_ratio > ratio:
		new_height = height
		new_width = round(height * source_ratio)
	else:
		new_width = width
		new_height = round(width / source_ratio)
	resized = source.resize((new_width, new_height), Image.Resampling.LANCZOS)
	left = max(0, (new_width - width) // 2)
	top = max(0, (new_height - height) // 2)
	return resized.crop((left, top, left + width, top + height))


def _draw_rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int, int]) -> None:
	draw.rounded_rectangle(box, radius=radius, fill=fill)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
	if not text:
		return []
	lines: list[str] = []
	current = ""
	for char in text:
		next_value = current + char
		if draw.textbbox((0, 0), next_value, font=font)[2] <= max_width or not current:
			current = next_value
		else:
			lines.append(current)
			current = char
	if current:
		lines.append(current)
	return lines[:2]


def _render_overlay_image(source: Path, target: Path, shot: dict[str, Any], width: int, height: int) -> None:
	base = _cover_crop(Image.open(source), width, height).convert("RGBA")
	layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
	draw = ImageDraw.Draw(layer)
	overlay = shot.get("overlay_text") or {}
	title = str(overlay.get("title") or "").strip()
	items = [str(item).strip() for item in overlay.get("items") or [] if str(item).strip()]
	if title:
		title_font = _font(round(width * 0.026))
		item_font = _font(round(width * 0.016))
		x = round(width * 0.055)
		y = round(height * 0.08)
		max_w = round(width * 0.52)
		title_lines = _wrap_text(draw, title, title_font, max_w)
		line_h = round(width * 0.037)
		item_h = round(width * 0.028)
		box_h = 42 + len(title_lines) * line_h + (len(items) * item_h if items else 0)
		box_w = max_w + 80
		_draw_rounded(draw, (x - 32, y - 28, x + box_w, y + box_h), 18, (0, 0, 0, 126))
		draw.rectangle((x - 32, y - 28, x - 18, y + box_h), fill=(47, 196, 214, 220))
		for line in title_lines:
			draw.text((x, y), line, font=title_font, fill=(255, 255, 255, 238))
			y += line_h
		if items:
			y += 8
			for item in items[:6]:
				draw.text((x, y), f"- {item}", font=item_font, fill=(230, 236, 232, 224))
				y += item_h
	target.parent.mkdir(parents=True, exist_ok=True)
	Image.alpha_composite(base, layer).convert("RGB").save(target, quality=96)


def _srt_time(seconds: float) -> str:
	ms = round(max(0.0, seconds) * 1000)
	hours = ms // 3_600_000
	ms %= 3_600_000
	minutes = ms // 60_000
	ms %= 60_000
	secs = ms // 1000
	ms %= 1000
	return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
	cs = round(max(0.0, seconds) * 100)
	hours = cs // 360_000
	cs %= 360_000
	minutes = cs // 6_000
	cs %= 6_000
	secs = cs // 100
	cs %= 100
	return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _clean_subtitle(text: str) -> str:
	clean = re.sub(r"\s+", " ", text).strip()
	clean = re.sub(r"[。．.]$", "", clean)
	return clean


def _write_subtitles(timeline: Path, video_dir: Path, width: int, height: int) -> dict[str, str]:
	data = _read_json(timeline)
	cues = data.get("cues") or []
	assert cues, f"No cues in {timeline}"
	srt_lines: list[str] = []
	ass_events: list[str] = []
	for index, cue in enumerate(cues, start=1):
		start = float(cue["start_sec"])
		end = float(cue["end_sec"])
		if end <= start:
			continue
		text = _clean_subtitle(str(cue.get("text", "")))
		if not text:
			continue
		srt_lines.extend([str(index), f"{_srt_time(start)} --> {_srt_time(end)}", text, ""])
		ass_text = text.replace("\\", "\\\\").replace("{", "（").replace("}", "）")
		ass_events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{ass_text}")
	srt = video_dir / "final_subtitles.srt"
	ass = video_dir / "final_subtitles.ass"
	srt.write_text("\n".join(srt_lines), encoding="utf-8")
	font_size = round(width * 0.025)
	margin_v = round(height * 0.072)
	ass.write_text("\n".join([
		"[Script Info]",
		"ScriptType: v4.00+",
		f"PlayResX: {width}",
		f"PlayResY: {height}",
		"ScaledBorderAndShadow: yes",
		"",
		"[V4+ Styles]",
		"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
		f"Style: Default,Noto Sans CJK SC,{font_size},&H00FFFFFF,&H000000FF,&H7A1C1C1C,&H00000000,-1,0,0,0,100,100,2,0,1,3,1,2,180,180,{margin_v},1",
		"",
		"[Events]",
		"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
		*ass_events,
		"",
	]), encoding="utf-8")
	return {"srt": str(srt), "ass": str(ass)}


def _encoder_args() -> list[str]:
	result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if "h264_videotoolbox" in result.stdout:
		return ["-c:v", "h264_videotoolbox", "-b:v", "18000k", "-allow_sw", "1"]
	return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def _render_clip(image: Path, clip: Path, duration: float, width: int, height: int, fps: int, motion: str) -> None:
	clip.parent.mkdir(parents=True, exist_ok=True)
	if clip.exists():
		try:
			if abs(_duration(clip) - duration) <= 0.05:
				return
		except Exception:
			pass
	frames = max(1, math.ceil(duration * fps))
	if motion == "none":
		vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p"
	else:
		vf = (
			f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
			f"zoompan=z='min(1.045,1+0.045*on/{frames})':"
			f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps},"
			f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,format=yuv420p"
		)
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-loop",
		"1",
		"-i",
		str(image),
		"-t",
		f"{duration:.3f}",
		"-vf",
		vf,
		"-an",
		"-r",
		str(fps),
		*_encoder_args(),
		str(clip),
	]
	_run(cmd)


def _concat_clips(clips: list[Path], concat_file: Path, out: Path) -> None:
	concat_file.parent.mkdir(parents=True, exist_ok=True)
	concat_file.write_text("".join(f"file '{clip.resolve()}'\n" for clip in clips), encoding="utf-8")
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
		str(concat_file),
		"-c",
		"copy",
		str(out),
	])


def _ffmpeg_filter_names() -> set[str]:
	result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	names: set[str] = set()
	for line in result.stdout.splitlines():
		parts = line.split()
		if len(parts) >= 2:
			names.add(parts[1])
	return names


def _render_subtitle_pngs(timeline: Path, overlay_dir: Path, width: int, height: int) -> list[dict[str, Any]]:
	data = _read_json(timeline)
	cues = data.get("cues") or []
	assert cues, f"No cues in {timeline}"
	overlay_dir.mkdir(parents=True, exist_ok=True)
	font = _font(round(width * 0.029))
	measure = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
	max_width = round(width * 0.86)
	bottom_margin = round(height * 0.087)
	line_gap = round(width * 0.008)
	records: list[dict[str, Any]] = []
	for index, cue in enumerate(cues, start=1):
		start = float(cue["start_sec"])
		end = float(cue["end_sec"])
		if end <= start:
			continue
		text = _clean_subtitle(str(cue.get("text", "")))
		if not text:
			continue
		lines = _wrap_text(measure, text, font, max_width)
		if not lines:
			continue
		boxes = [measure.textbbox((0, 0), line, font=font, stroke_width=2) for line in lines]
		line_heights = [box[3] - box[1] for box in boxes]
		total_height = sum(line_heights) + line_gap * (len(lines) - 1)
		y = height - bottom_margin - total_height
		canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
		draw = ImageDraw.Draw(canvas)
		for line, box, line_height in zip(lines, boxes, line_heights):
			text_width = box[2] - box[0]
			x = round((width - text_width) / 2)
			draw.text((x + 3, y + 4), line, font=font, fill=(0, 0, 0, 128), stroke_width=2, stroke_fill=(0, 0, 0, 100))
			draw.text((x, y), line, font=font, fill=(255, 255, 255, 245), stroke_width=2, stroke_fill=(24, 24, 24, 190))
			y += line_height + line_gap
		path = overlay_dir / f"subtitle_{index:04d}.png"
		canvas.save(path)
		records.append({"start_sec": start, "end_sec": end, "text": text, "overlay_png": str(path), "sha256": _sha256(path)})
	return records


def _compose_final_with_png_subtitles(visual_base: Path, audio: Path, overlays: list[dict[str, Any]], out: Path) -> None:
	filter_script = out.parent / "subtitle_overlay_filter_complex.txt"
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(visual_base),
		"-i",
		str(audio),
	]
	for record in overlays:
		cmd.extend(["-loop", "1", "-i", str(record["overlay_png"])])
	prev = "0:v"
	lines: list[str] = []
	for index, record in enumerate(overlays, start=1):
		input_index = index + 1
		out_label = f"v{index}"
		lines.append(
			f"[{prev}][{input_index}:v]overlay=0:0:enable='between(t,{record['start_sec']:.3f},{record['end_sec']:.3f})'[{out_label}]"
		)
		prev = out_label
	filter_script.write_text(";\n".join(lines) + "\n", encoding="utf-8")
	cmd.extend([
		"-filter_complex_script",
		str(filter_script),
		"-map",
		f"[{prev}]",
		"-map",
		"1:a:0",
		"-c:v",
		"libx264",
		"-preset",
		"ultrafast",
		"-crf",
		"20",
		"-c:a",
		"aac",
		"-b:a",
		"192k",
		"-pix_fmt",
		"yuv420p",
		"-shortest",
		str(out),
	])
	_run(cmd)


def _compose_video_audio_only(visual_base: Path, audio: Path, out: Path) -> None:
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(visual_base),
		"-i",
		str(audio),
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
		"-shortest",
		str(out),
	])


def _mux_soft_subtitles(video: Path, srt: Path, out: Path) -> Path:
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(video),
		"-i",
		str(srt),
		"-map",
		"0:v",
		"-map",
		"0:a",
		"-map",
		"1:0",
		"-c:v",
		"copy",
		"-c:a",
		"copy",
		"-c:s",
		"mov_text",
		"-metadata:s:s:0",
		"language=chi",
		str(out),
	])
	return out


def _compose_final(visual_base: Path, audio: Path, ass: Path | None, out: Path, dialogue_timeline: Path, width: int, height: int, video_dir: Path) -> dict[str, Any]:
	out.parent.mkdir(parents=True, exist_ok=True)
	if ass is None:
		_compose_video_audio_only(visual_base, audio, out)
		return {"method": "no_burned_subtitles", "subtitle_overlay_pngs": []}
	filters = _ffmpeg_filter_names()
	if ass and "subtitles" in filters:
		filter_value = f"subtitles=filename='{ass}':fontsdir='{DEFAULT_FONTS_DIR}'"
		cmd = [
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-i",
			str(visual_base),
			"-i",
			str(audio),
			"-vf",
			filter_value,
			"-map",
			"0:v:0",
			"-map",
			"1:a:0",
			"-c:v",
			"libx264",
			"-preset",
			"veryfast",
			"-crf",
			"18",
			"-c:a",
			"aac",
			"-b:a",
			"192k",
			"-pix_fmt",
			"yuv420p",
			"-shortest",
			str(out),
		]
		_run(cmd)
		return {"method": "ffmpeg_subtitles_filter", "subtitle_overlay_pngs": []}
	_compose_video_audio_only(visual_base, audio, out)
	return {
		"method": "no_burned_subtitles_missing_ffmpeg_subtitles_filter",
		"subtitle_overlay_pngs": [],
		"note": "Local ffmpeg lacks the subtitles filter; use the generated SRT/ASS sidecars or the soft-subtitle MP4.",
	}


def _selected_map(selected_manifest: Path) -> dict[str, Path]:
	data = _read_json(selected_manifest)
	assert data.get("status") == "PASS", f"selected_visuals status is not PASS: {data.get('status')}"
	return {item["beat"]: Path(item["selected_image"]) for item in data["selections"] if item.get("status") == "selected"}


def assemble(project_dir: Path, manifest_path: Path, selected_manifest: Path, audio: Path, dialogue_timeline: Path, out: Path, width: int, height: int, fps: int, motion: str, subtitles: bool) -> dict[str, Any]:
	manifest = _read_json(manifest_path)
	image_map = _selected_map(selected_manifest)
	ai_dir = project_dir / "ai_video_visuals"
	video_dir = project_dir / "video"
	overlay_dir = ai_dir / "overlays"
	clips_dir = video_dir / "ai-visual-clips"
	video_dir.mkdir(parents=True, exist_ok=True)
	rendered_segments: list[dict[str, Any]] = []
	clips: list[Path] = []
	for shot in manifest["shots"]:
		beat = shot["beat"]
		source_image = image_map[beat]
		assert source_image.exists(), f"Missing selected image for {beat}: {source_image}"
		overlay_image = overlay_dir / f"shot_{beat}_overlay.png"
		_render_overlay_image(source_image, overlay_image, shot, width, height)
		clip = clips_dir / f"shot_{beat}.mp4"
		duration = float(shot["visual_end_sec"]) - float(shot["visual_start_sec"])
		_render_clip(overlay_image, clip, duration, width, height, fps, motion)
		clips.append(clip)
		rendered_segments.append({
			"beat": beat,
			"visual_start_sec": shot["visual_start_sec"],
			"visual_end_sec": shot["visual_end_sec"],
			"duration_sec": round(duration, 3),
			"source_image": str(source_image),
			"source_image_sha256": _sha256(source_image),
			"overlay_image": str(overlay_image),
			"overlay_image_sha256": _sha256(overlay_image),
			"clip": str(clip),
			"clip_sha256": _sha256(clip),
		})
	concat_file = video_dir / "ai_visual_concat.ffconcat"
	visual_base = video_dir / "ai_visual_base.mp4"
	_concat_clips(clips, concat_file, visual_base)
	subtitle_paths: dict[str, str] | None = None
	ass_path: Path | None = None
	if subtitles:
		subtitle_paths = _write_subtitles(dialogue_timeline, video_dir, width, height)
		ass_path = Path(subtitle_paths["ass"])
	subtitle_render = _compose_final(visual_base, audio, ass_path, out, dialogue_timeline, width, height, video_dir)
	soft_subtitle_video: str | None = None
	srt_for_soft_subtitles = Path(subtitle_paths["srt"]) if subtitle_paths else video_dir / "final_subtitles.srt"
	if srt_for_soft_subtitles.exists() and subtitle_render["method"].startswith("no_burned_subtitles"):
		soft_subtitle_video = str(_mux_soft_subtitles(out, srt_for_soft_subtitles, out.with_name(f"{out.stem}_soft_subtitles{out.suffix}")))
	audio_duration = _duration(audio)
	video_duration = _duration(out)
	status = "PASS" if abs(audio_duration - video_duration) <= 0.5 else "NEEDS_REVIEW"
	result = {
		"schema_version": "article_ai_video_visuals.render.v1",
		"status": status,
		"project_dir": str(project_dir),
		"manifest": str(manifest_path),
		"selected_manifest": str(selected_manifest),
		"audio": str(audio),
		"audio_sha256": _sha256(audio),
		"dialogue_timeline": str(dialogue_timeline),
		"dialogue_timeline_sha256": _sha256(dialogue_timeline),
		"width": width,
		"height": height,
		"fps": fps,
		"motion": motion,
		"visual_base": str(visual_base),
		"visual_base_sha256": _sha256(visual_base),
		"final_video": str(out),
		"final_video_sha256": _sha256(out),
		"audio_duration_sec": round(audio_duration, 3),
		"final_video_duration_sec": round(video_duration, 3),
		"subtitle_paths": subtitle_paths,
		"subtitle_render": subtitle_render,
		"soft_subtitle_video": soft_subtitle_video,
		"segments": rendered_segments,
		"ffprobe": _ffprobe(out),
	}
	_write_json(ai_dir / "visual_render_manifest.json", result)
	return result


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--manifest", required=True, type=Path)
	parser.add_argument("--selected-manifest", required=True, type=Path)
	parser.add_argument("--audio", required=True, type=Path)
	parser.add_argument("--dialogue-timeline", required=True, type=Path)
	parser.add_argument("--out", required=True, type=Path)
	parser.add_argument("--width", type=int, default=3840)
	parser.add_argument("--height", type=int, default=2160)
	parser.add_argument("--fps", type=int, default=30)
	parser.add_argument("--motion", choices=["none", "slow_zoom"], default="slow_zoom")
	parser.add_argument("--no-subtitles", action="store_true")
	args = parser.parse_args()
	result = assemble(
		project_dir=args.project_dir,
		manifest_path=args.manifest,
		selected_manifest=args.selected_manifest,
		audio=args.audio,
		dialogue_timeline=args.dialogue_timeline,
		out=args.out,
		width=args.width,
		height=args.height,
		fps=args.fps,
		motion=args.motion,
		subtitles=not args.no_subtitles,
	)
	print(json.dumps({"status": result["status"], "final_video": result["final_video"], "duration": result["final_video_duration_sec"]}, ensure_ascii=False, indent=2))
	if result["status"] != "PASS":
		raise SystemExit(2)


if __name__ == "__main__":
	main()
