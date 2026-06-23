#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import wave
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH = 3840
HEIGHT = 2160
FPS = 30
VISUAL_TRANSITION_EFFECT = "wipe_with_shadow"
VISUAL_TRANSITION_DURATION_SEC = 0.8
VISUAL_TRANSITION_MIN_DURATION_SEC = 0.2
VISUAL_TRANSITION_MAX_ADJACENT_RATIO = 0.4
VISUAL_TRANSITION_FEATHER_RATIO = 0.035
VISUAL_TRANSITION_SHADOW_RADIUS_RATIO = 0.045
VISUAL_TRANSITION_SHADOW_OPACITY = 0.30
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


@dataclass(frozen=True)
class VisualSegment:
	index: int
	start_sec: float
	end_sec: float
	image: Path
	title: str


@dataclass(frozen=True)
class VisualUnit:
	kind: str
	index: int
	start_sec: float
	end_sec: float
	duration_sec: float
	clip: Path
	image: Path | None = None
	from_image: Path | None = None
	to_image: Path | None = None
	from_segment_index: int | None = None
	to_segment_index: int | None = None


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_title(project_dir: Path) -> str:
	title_path = project_dir / "video_title.txt"
	assert title_path.exists(), f"Missing {title_path}"
	return title_path.read_text(encoding="utf-8").strip().splitlines()[0].strip()


def _publish_time(seconds: float) -> str:
	total = max(0, int(round(seconds)))
	hours = total // 3600
	minutes = (total % 3600) // 60
	secs = total % 60
	if hours:
		return f"{hours:02d}:{minutes:02d}:{secs:02d}"
	return f"{minutes:02d}:{secs:02d}"


def _write_publish_info(project_dir: Path, title: str, segments: list[VisualSegment]) -> Path:
	lines = [title]
	for segment in segments:
		chapter_title = segment.title.strip() or f"第 {segment.index} 章"
		lines.append(f"{_publish_time(segment.start_sec)}-{_publish_time(segment.end_sec)}：{chapter_title}")
	path = project_dir / "publish_info.txt"
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")
	return path


def _write_bilibili_upload_metadata(project_dir: Path, title: str, segments: list[VisualSegment], publish_info_path: Path) -> Path:
	path = project_dir / "bilibili_upload_metadata.json"
	metadata_script = Path(__file__).resolve().parents[2] / "article-bilibili-publish-metadata" / "scripts" / "generate_bilibili_publish_metadata.py"
	assert metadata_script.exists(), f"Missing metadata generator: {metadata_script}"
	_run([
		sys.executable,
		str(metadata_script),
		"--project-dir",
		str(project_dir),
		"--title",
		title,
		"--publish-info",
		str(publish_info_path),
		"--output",
		str(path),
		"--report",
		str(project_dir / "planning" / "bilibili_tag_report.json"),
	])
	return path


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


def _extract_audio_for_check(video: Path, output: Path) -> None:
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(video),
		"-vn",
		"-ac",
		"1",
		"-ar",
		"24000",
		"-c:a",
		"pcm_s16le",
		str(output),
	])


def _read_wav_samples(path: Path) -> tuple[int, list[float]]:
	with wave.open(str(path), "rb") as handle:
		assert handle.getsampwidth() == 2, f"Expected 16-bit wav for audio check: {path}"
		assert handle.getnchannels() == 1, f"Expected mono wav for audio check: {path}"
		rate = handle.getframerate()
		raw = handle.readframes(handle.getnframes())
	samples = [int.from_bytes(raw[index:index + 2], "little", signed=True) / 32768 for index in range(0, len(raw), 2)]
	return rate, samples


def _audio_similarity(source_wav: Path, extracted_wav: Path) -> dict[str, Any]:
	source_rate, source_samples = _read_wav_samples(source_wav)
	extracted_rate, extracted_samples = _read_wav_samples(extracted_wav)
	count = min(len(source_samples), len(extracted_samples))
	assert count > 0, "No comparable audio samples"
	left = source_samples[:count]
	right = extracted_samples[:count]
	left_mean = sum(left) / count
	right_mean = sum(right) / count
	left_var = sum((value - left_mean) ** 2 for value in left)
	right_var = sum((value - right_mean) ** 2 for value in right)
	covariance = sum((left[index] - left_mean) * (right[index] - right_mean) for index in range(count))
	correlation = covariance / (math.sqrt(left_var * right_var) + 1e-12)
	rms_source = math.sqrt(sum(value * value for value in left) / count)
	rms_diff = math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(count)) / count)
	return {
		"source_sample_rate": source_rate,
		"extracted_sample_rate": extracted_rate,
		"compared_duration_sec": round(count / source_rate, 3),
		"sample_correlation": round(correlation, 6),
		"rms_diff": round(rms_diff, 8),
		"rms_source": round(rms_source, 8),
		"rms_diff_over_source": round(rms_diff / (rms_source + 1e-12), 6),
		"status": "PASS" if correlation >= 0.995 and rms_diff / (rms_source + 1e-12) <= 0.05 else "NEEDS_REVIEW",
	}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
	assert SUBTITLE_FONT_PATH.exists(), f"Missing subtitle font: {SUBTITLE_FONT_PATH}"
	return ImageFont.truetype(str(SUBTITLE_FONT_PATH), size)


def _measure_spaced(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, spacing: int, stroke: int) -> tuple[int, int]:
	width = 0
	height = 0
	for index, char in enumerate(text):
		box = draw.textbbox((0, 0), char, font=font, stroke_width=stroke)
		width += box[2] - box[0]
		height = max(height, box[3] - box[1])
		if index < len(text) - 1:
			width += spacing
	return width + round(abs(SUBTITLE_FAUX_ITALIC_SHEAR) * height) + SUBTITLE_GLYPH_EDGE_PAD_PX * 2, height


def _draw_spaced_text(canvas: Image.Image, text: str, font: ImageFont.ImageFont, box: tuple[int, int, int, int], spacing: int) -> dict[str, float | int | str]:
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


def _ffconcat_path(path: Path) -> str:
	return str(path).replace("'", "'\\''")


def _visual_path(value: str, plan_dir: Path) -> Path:
	path = Path(value).expanduser()
	if not path.is_absolute():
		path = plan_dir / path
	return path.resolve()


def _load_visual_segments(project_dir: Path, audio_duration: float) -> list[VisualSegment]:
	plan_path = project_dir / "chapter_visuals" / "chapter_plan.json"
	assert plan_path.exists(), f"Missing {plan_path}"
	plan = _read_json(plan_path)
	chapters = list(plan.get("chapters") or [])
	assert chapters, "chapter_plan needs at least one chapter"
	segments: list[VisualSegment] = []
	for raw in chapters:
		image_value = raw.get("image") or raw.get("image_path") or raw.get("visual_path")
		assert image_value, f"Chapter missing image: {raw}"
		image = _visual_path(str(image_value), plan_path.parent)
		assert image.exists(), f"Missing chapter image: {image}"
		start = float(raw["start_sec"])
		end = float(raw["end_sec"])
		segments.append(VisualSegment(int(raw.get("chapter_index") or len(segments) + 1), start, min(audio_duration, end), image, str(raw.get("chapter_title") or "")))
	segments = sorted(segments, key=lambda item: item.start_sec)
	segments[0] = VisualSegment(segments[0].index, 0.0, segments[0].end_sec, segments[0].image, segments[0].title)
	segments[-1] = VisualSegment(segments[-1].index, segments[-1].start_sec, audio_duration, segments[-1].image, segments[-1].title)
	for index, segment in enumerate(segments):
		assert segment.end_sec > segment.start_sec, f"Chapter visual segment {segment.index} has non-positive duration"
		if index + 1 < len(segments):
			gap = segments[index + 1].start_sec - segment.end_sec
			assert abs(gap) <= 0.01, (
				f"Chapter visual timeline must be continuous for ffconcat: "
				f"segment {segment.index} ends at {segment.end_sec:.3f}, "
				f"next starts at {segments[index + 1].start_sec:.3f}"
			)
	return segments


def _fit_image_to_frame(path: Path) -> Image.Image:
	image = Image.open(path).convert("RGB")
	if image.size == (WIDTH, HEIGHT):
		return image
	scale = min(WIDTH / image.width, HEIGHT / image.height)
	resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
	canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
	canvas.paste(resized, ((WIDTH - resized.width) // 2, (HEIGHT - resized.height) // 2))
	return canvas


def _ease_in_out_sine(value: float) -> float:
	return 0.5 - 0.5 * math.cos(math.pi * value)


def _smoothstep(value: float) -> float:
	value = max(0.0, min(1.0, value))
	return value * value * (3.0 - 2.0 * value)


def _horizontal_wipe_mask(width: int, height: int, boundary_x: float, feather_px: float) -> Image.Image:
	feather_px = max(1.0, feather_px)
	row = bytearray(width)
	for x in range(width):
		alpha = _smoothstep((boundary_x - x + feather_px) / (2.0 * feather_px))
		row[x] = round(255 * alpha)
	return Image.frombytes("L", (width, 1), bytes(row)).resize((width, height))


def _vertical_shadow_mask(width: int, height: int, center_x: float, radius_px: float, opacity: float) -> Image.Image:
	radius_px = max(1.0, radius_px)
	row = bytearray(width)
	for x in range(width):
		distance = abs(x - center_x)
		alpha = max(0.0, 1.0 - distance / radius_px) * opacity
		row[x] = round(255 * alpha)
	return Image.frombytes("L", (width, 1), bytes(row)).resize((width, height))


def _write_rgb_video_from_frames(output: Path, fps: int, frames: list[Image.Image]) -> None:
	assert frames, f"No frames to write for {output}"
	output.parent.mkdir(parents=True, exist_ok=True)
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"rawvideo",
		"-pix_fmt",
		"rgb24",
		"-s",
		f"{WIDTH}x{HEIGHT}",
		"-r",
		str(fps),
		"-i",
		"-",
		"-c:v",
		"libx264",
		"-preset",
		"veryfast",
		"-pix_fmt",
		"yuv420p",
		"-movflags",
		"+faststart",
		str(output),
	]
	process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
	assert process.stdin is not None, "ffmpeg stdin was not opened"
	for frame in frames:
		assert frame.size == (WIDTH, HEIGHT), f"Transition frame has wrong size: {frame.size}"
		process.stdin.write(frame.convert("RGB").tobytes())
	process.stdin.close()
	return_code = process.wait()
	assert return_code == 0, f"ffmpeg failed while writing {output}: exit {return_code}"


def _render_wipe_with_shadow_transition(from_image: Path, to_image: Path, output: Path, duration_sec: float, fps: int) -> dict[str, Any]:
	frame_count = max(2, round(duration_sec * fps))
	actual_duration = frame_count / fps
	from_frame = _fit_image_to_frame(from_image)
	to_frame = _fit_image_to_frame(to_image)
	black = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
	feather = WIDTH * VISUAL_TRANSITION_FEATHER_RATIO
	shadow_radius = WIDTH * VISUAL_TRANSITION_SHADOW_RADIUS_RATIO
	frames: list[Image.Image] = []
	for frame_index in range(frame_count):
		linear_progress = (frame_index + 1) / (frame_count + 1)
		progress = _ease_in_out_sine(linear_progress)
		boundary_x = progress * WIDTH
		wipe_mask = _horizontal_wipe_mask(WIDTH, HEIGHT, boundary_x, feather)
		frame = Image.composite(to_frame, from_frame, wipe_mask)
		shadow_mask = _vertical_shadow_mask(WIDTH, HEIGHT, boundary_x, shadow_radius, VISUAL_TRANSITION_SHADOW_OPACITY)
		frame = Image.composite(black, frame, shadow_mask)
		frames.append(frame)
	_write_rgb_video_from_frames(output, fps, frames)
	return {
		"effect": VISUAL_TRANSITION_EFFECT,
		"frame_count": frame_count,
		"duration_sec": round(actual_duration, 3),
		"feather_ratio": VISUAL_TRANSITION_FEATHER_RATIO,
		"shadow_radius_ratio": VISUAL_TRANSITION_SHADOW_RADIUS_RATIO,
		"shadow_opacity": VISUAL_TRANSITION_SHADOW_OPACITY,
		"easing": "ease_in_out_sine",
	}


def _render_static_visual_clip(image: Path, output: Path, duration_sec: float, fps: int) -> None:
	assert duration_sec > 0, f"Static visual clip duration must be positive for {image}"
	output.parent.mkdir(parents=True, exist_ok=True)
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-loop",
		"1",
		"-framerate",
		str(fps),
		"-t",
		f"{duration_sec:.6f}",
		"-i",
		str(image),
		"-vf",
		f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p",
		"-an",
		"-c:v",
		"libx264",
		"-preset",
		"veryfast",
		"-tune",
		"stillimage",
		"-pix_fmt",
		"yuv420p",
		"-movflags",
		"+faststart",
		str(output),
	])


def _safe_transition_duration(prev_segment: VisualSegment, next_segment: VisualSegment, fps: int) -> float:
	prev_duration = prev_segment.end_sec - prev_segment.start_sec
	next_duration = next_segment.end_sec - next_segment.start_sec
	duration = min(
		VISUAL_TRANSITION_DURATION_SEC,
		prev_duration * VISUAL_TRANSITION_MAX_ADJACENT_RATIO,
		next_duration * VISUAL_TRANSITION_MAX_ADJACENT_RATIO,
	)
	frame_count = round(duration * fps)
	if frame_count / fps < VISUAL_TRANSITION_MIN_DURATION_SEC:
		return 0.0
	return frame_count / fps


def _planned_visual_units(segments: list[VisualSegment], video_dir: Path, fps: int) -> list[VisualUnit]:
	clip_dir = video_dir / "visual-clips"
	transition_durations = [
		_safe_transition_duration(segments[index], segments[index + 1], fps)
		for index in range(len(segments) - 1)
	]
	units: list[VisualUnit] = []
	unit_index = 1
	for index, segment in enumerate(segments):
		start = segment.start_sec + (transition_durations[index - 1] / 2 if index > 0 else 0.0)
		end = segment.end_sec - (transition_durations[index] / 2 if index < len(transition_durations) else 0.0)
		duration = end - start
		if duration > 0.01:
			clip = clip_dir / f"visual_{unit_index:04d}_hold_chapter_{segment.index:02d}.mp4"
			units.append(VisualUnit("hold", unit_index, start, end, duration, clip, image=segment.image, from_segment_index=segment.index))
			unit_index += 1
		if index < len(transition_durations) and transition_durations[index] > 0:
			next_segment = segments[index + 1]
			duration = transition_durations[index]
			start = segment.end_sec - duration / 2
			end = segment.end_sec + duration / 2
			clip = clip_dir / f"visual_{unit_index:04d}_transition_{segment.index:02d}_to_{next_segment.index:02d}_{VISUAL_TRANSITION_EFFECT}.mp4"
			units.append(
				VisualUnit(
					"transition",
					unit_index,
					start,
					end,
					duration,
					clip,
					from_image=segment.image,
					to_image=next_segment.image,
					from_segment_index=segment.index,
					to_segment_index=next_segment.index,
				)
			)
			unit_index += 1
	return units


def _render_visual_units(units: list[VisualUnit], fps: int) -> list[dict[str, Any]]:
	rendered: list[dict[str, Any]] = []
	for unit in units:
		if unit.kind == "hold":
			assert unit.image is not None, f"Hold visual unit missing image: {unit}"
			_render_static_visual_clip(unit.image, unit.clip, unit.duration_sec, fps)
			rendered.append({
				"kind": unit.kind,
				"index": unit.index,
				"start_sec": round(unit.start_sec, 3),
				"end_sec": round(unit.end_sec, 3),
				"duration_sec": round(unit.duration_sec, 3),
				"clip": str(unit.clip),
				"clip_sha256": _sha256(unit.clip),
				"image": str(unit.image),
				"image_sha256": _sha256(unit.image),
				"segment_index": unit.from_segment_index,
			})
			continue
		assert unit.from_image is not None and unit.to_image is not None, f"Transition visual unit missing images: {unit}"
		transition_meta = _render_wipe_with_shadow_transition(unit.from_image, unit.to_image, unit.clip, unit.duration_sec, fps)
		rendered.append({
			"kind": unit.kind,
			"index": unit.index,
			"start_sec": round(unit.start_sec, 3),
			"end_sec": round(unit.end_sec, 3),
			"duration_sec": round(unit.duration_sec, 3),
			"clip": str(unit.clip),
			"clip_sha256": _sha256(unit.clip),
			"from_segment_index": unit.from_segment_index,
			"to_segment_index": unit.to_segment_index,
			"from_image": str(unit.from_image),
			"to_image": str(unit.to_image),
			"from_image_sha256": _sha256(unit.from_image),
			"to_image_sha256": _sha256(unit.to_image),
			**transition_meta,
		})
	return rendered


def _write_visual_concat(units: list[VisualUnit], video_dir: Path) -> Path:
	concat_path = video_dir / "visual_concat.ffconcat"
	with concat_path.open("w", encoding="utf-8") as handle:
		handle.write("ffconcat version 1.0\n")
		for unit in units:
			clip = getattr(unit, "clip", None) or getattr(unit, "image", None)
			assert clip is not None, f"Visual concat unit has neither clip nor image: {unit}"
			handle.write(f"file '{_ffconcat_path(clip)}'\n")
	return concat_path


def _render_visual_base(project_dir: Path, segments: list[VisualSegment], audio_duration: float, fps: int) -> tuple[Path, Path, list[dict[str, Any]], dict[str, Any]]:
	video_dir = project_dir / "video"
	units = _planned_visual_units(segments, video_dir, fps)
	assert units, "No visual units were planned"
	rendered_units = _render_visual_units(units, fps)
	concat_path = _write_visual_concat(units, video_dir)
	visual_base = video_dir / "visual_base_1x.mp4"
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
		f"fps={fps},format=yuv420p",
		"-an",
		"-c:v",
		"libx264",
		"-preset",
		"veryfast",
		"-pix_fmt",
		"yuv420p",
		"-t",
		f"{audio_duration:.3f}",
		"-movflags",
		"+faststart",
		str(visual_base),
	])
	transition_units = [unit for unit in rendered_units if unit["kind"] == "transition"]
	transition_summary = {
		"enabled": bool(transition_units),
		"effect": VISUAL_TRANSITION_EFFECT,
		"renderer": "python_pillow_fixed_compositor",
		"placement": "centered_on_chapter_boundary",
		"default_duration_sec": VISUAL_TRANSITION_DURATION_SEC,
		"min_duration_sec": VISUAL_TRANSITION_MIN_DURATION_SEC,
		"max_adjacent_segment_ratio": VISUAL_TRANSITION_MAX_ADJACENT_RATIO,
		"transition_count": len(transition_units),
		"transition_durations_sec": [unit["duration_sec"] for unit in transition_units],
		"visual_base": str(visual_base),
		"visual_base_sha256": _sha256(visual_base),
		"visual_base_duration_sec": round(_duration(visual_base), 3),
	}
	return visual_base, concat_path, rendered_units, transition_summary


def _render_subtitle_images(project_dir: Path, cues: list[dict[str, Any]]) -> tuple[Path, list[dict[str, Any]]]:
	overlay_dir = project_dir / "video" / "subtitle-overlays"
	overlay_dir.mkdir(parents=True, exist_ok=True)
	blank = overlay_dir / "blank.png"
	Image.new("RGBA", (SUBTITLE_OVERLAY_W, SUBTITLE_OVERLAY_H), (0, 0, 0, 0)).save(blank)
	layouts: list[dict[str, Any]] = []
	for cue in cues:
		img = Image.new("RGBA", (SUBTITLE_OVERLAY_W, SUBTITLE_OVERLAY_H), (0, 0, 0, 0))
		text = re.sub(r"\s+", " ", str(cue.get("display_text") or cue.get("text") or "")).strip()
		layout = _draw_spaced_text(
			img,
			text,
			_font(SUBTITLE_FONT_SIZE_PX),
			(
				80,
				SUBTITLE_TOP_Y - SUBTITLE_OVERLAY_Y,
				SUBTITLE_OVERLAY_W - 80,
				min(SUBTITLE_OVERLAY_H, SUBTITLE_BOTTOM_Y - SUBTITLE_OVERLAY_Y),
			),
			LETTER_SPACING_PX,
		)
		path = overlay_dir / f"cue_{int(cue['index']):04d}.png"
		img.save(path)
		layouts.append({"cue_index": int(cue["index"]), "path": str(path), "layout": layout})
	return blank, layouts


def _render_overlay_video(video_dir: Path, cues: list[dict[str, Any]], blank: Path, layouts: list[dict[str, Any]], audio_duration: float, fps: int) -> Path:
	concat_path = video_dir / "subtitle_overlay_concat.ffconcat"
	layout_by_cue = {int(item["cue_index"]): Path(item["path"]) for item in layouts}
	boundaries = {0.0, audio_duration}
	for cue in cues:
		start = max(0.0, min(audio_duration, float(cue["start_sec"])))
		end = max(0.0, min(audio_duration, float(cue["end_sec"])))
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
				cue = max(active, key=lambda item: (float(item["start_sec"]), int(item["index"])))
				path = layout_by_cue[int(cue["index"])]
			else:
				path = blank
			handle.write(f"file '{_ffconcat_path(path)}'\n")
			handle.write(f"duration {duration:.3f}\n")
			last_path = path
		handle.write(f"file '{_ffconcat_path(last_path)}'\n")
	overlay_video = video_dir / "subtitle_overlay.mov"
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
		f"fps={fps},format=argb",
		"-c:v",
		"qtrle",
		"-pix_fmt",
		"argb",
		"-t",
		f"{audio_duration:.3f}",
		str(overlay_video),
	])
	return overlay_video


def _render_video(project_dir: Path, visual_base: Path, overlay_video: Path, audio_path: Path, audio_duration: float, fps: int) -> tuple[Path, Path]:
	video_dir = project_dir / "video"
	final_1x = video_dir / "final_video_1x.mp4"
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(visual_base),
		"-i",
		str(audio_path),
		"-i",
		str(overlay_video),
		"-filter_complex",
		f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[base];[base][2:v]overlay={SUBTITLE_OVERLAY_X}:{SUBTITLE_OVERLAY_Y}:format=auto:shortest=1,format=yuv420p[vout]",
		"-map",
		"[vout]",
		"-map",
		"1:a",
		"-c:v",
		"libx264",
		"-preset",
		"veryfast",
		"-pix_fmt",
		"yuv420p",
		"-c:a",
		"aac",
		"-b:a",
		"192k",
		"-t",
		f"{audio_duration:.3f}",
		"-movflags",
		"+faststart",
		str(final_1x),
	])
	final = video_dir / "final_video.mp4"
	shutil.copy2(final_1x, final)
	return final_1x, final


def render(project_dir: Path, fps: int) -> dict[str, Any]:
	video_dir = project_dir / "video"
	video_dir.mkdir(parents=True, exist_ok=True)
	audio_path = project_dir / "audio" / "final_podcast.wav"
	subtitle_manifest_path = video_dir / "subtitle_manifest.json"
	timeline_path = project_dir / "audio" / "dialogue_timeline.json"
	audio_manifest_path = project_dir / "audio" / "audio_manifest.json"
	cover_path = project_dir / "cover" / "cover_4k.png"
	assert audio_path.exists(), f"Missing {audio_path}"
	assert subtitle_manifest_path.exists(), f"Missing {subtitle_manifest_path}"
	assert timeline_path.exists(), f"Missing {timeline_path}"
	title = _read_title(project_dir)
	subtitle_manifest = _read_json(subtitle_manifest_path)
	cues = list(subtitle_manifest.get("cues") or [])
	assert cues, "subtitle_manifest has no cues"
	audio_duration = _duration(audio_path)
	segments = _load_visual_segments(project_dir, audio_duration)
	publish_info_path = _write_publish_info(project_dir, title, segments)
	bilibili_metadata_path = _write_bilibili_upload_metadata(project_dir, title, segments, publish_info_path)
	visual_base, visual_concat, visual_units, visual_transition = _render_visual_base(project_dir, segments, audio_duration, fps)
	blank, layouts = _render_subtitle_images(project_dir, cues)
	overlay_video = _render_overlay_video(video_dir, cues, blank, layouts, audio_duration, fps)
	final_1x, final = _render_video(project_dir, visual_base, overlay_video, audio_path, audio_duration, fps)
	extracted_audio = video_dir / "final_video_audio_check.wav"
	_extract_audio_for_check(final, extracted_audio)
	audio_video_check = _audio_similarity(audio_path, extracted_audio)
	if (video_dir / "final_subtitles.srt").exists():
		shutil.copy2(video_dir / "final_subtitles.srt", video_dir / "final_subtitles_1x.srt")
	if (video_dir / "final_subtitles.ass").exists():
		shutil.copy2(video_dir / "final_subtitles.ass", video_dir / "final_subtitles_1x.ass")
	video_duration = _duration(final)
	layout_by_cue = {int(item["cue_index"]): item["layout"] for item in layouts}
	render_segments = []
	for cue in cues:
		render_segments.append({
			"index": int(cue["index"]),
			"start_sec": float(cue["start_sec"]),
			"end_sec": float(cue["end_sec"]),
			"subtitle_text": str(cue.get("display_text") or cue.get("text") or ""),
			"subtitle_layout": layout_by_cue[int(cue["index"])],
		})
	manifest = {
		"schema_version": "article-podcast-vibevoice-static-video.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"playback_speed_factor": 1.0,
		"pre_speed_video": "video/final_video_1x.mp4",
		"pre_speed_duration_sec": round(video_duration, 3),
		"final_video": "video/final_video.mp4",
		"final_duration_sec": round(video_duration, 3),
		"script_hash": _sha256(project_dir / "podcast_script.md") if (project_dir / "podcast_script.md").exists() else None,
		"audio_hash": _sha256(audio_path),
		"audio_manifest_hash": _sha256(audio_manifest_path) if audio_manifest_path.exists() else None,
		"dialogue_timeline_hash": _sha256(timeline_path),
		"cover_hash": _sha256(cover_path) if cover_path.exists() else None,
		"subtitle_hash": _sha256(video_dir / "final_subtitles.srt") if (video_dir / "final_subtitles.srt").exists() else None,
		"subtitle_manifest_hash": _sha256(subtitle_manifest_path),
		"publish_info_hash": _sha256(publish_info_path),
		"bilibili_upload_metadata_hash": _sha256(bilibili_metadata_path),
		"visual_base_hash": _sha256(visual_base),
		"visual_transition": visual_transition,
		"audio_video_check": {
			"extracted_audio": str(extracted_audio),
			"extracted_audio_sha256": _sha256(extracted_audio),
			**audio_video_check,
		},
		"subtitle_layout_rule": {
			"subtitle_overlay_y": SUBTITLE_OVERLAY_Y,
			"subtitle_overlay_height": SUBTITLE_OVERLAY_H,
			"subtitle_block_top_min_y": SUBTITLE_TOP_Y,
			"subtitle_block_top_max_y": SUBTITLE_TOP_MAX_Y,
			"subtitle_block_bottom_max_y": SUBTITLE_BOTTOM_Y,
			"font_family": SUBTITLE_FONT_FAMILY,
			"font_full_name": SUBTITLE_FONT_FULL_NAME,
			"font_file": str(SUBTITLE_FONT_PATH),
			"font_license_note": SUBTITLE_FONT_LICENSE_NOTE,
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
		"visual_segments": [
			{
				"index": segment.index,
				"start_sec": round(segment.start_sec, 3),
				"end_sec": round(segment.end_sec, 3),
				"image": str(segment.image),
				"image_sha256": _sha256(segment.image),
				"title": segment.title,
			}
			for segment in segments
		],
		"chapter_visual_hashes": {
			str(segment.index): _sha256(segment.image)
			for segment in segments
		},
		"visual_timeline_units": visual_units,
		"segments": render_segments,
		"outputs": {
			"visual_base": str(visual_base),
			"visual_concat": str(visual_concat),
			"final_video_1x": str(final_1x),
			"final_video": str(final),
			"subtitle_overlay": str(overlay_video),
			"publish_info": str(publish_info_path),
			"bilibili_upload_metadata": str(bilibili_metadata_path),
		},
		"ffprobe": _ffprobe(final),
	}
	_write_json(video_dir / "render_manifest.json", manifest)
	report = [
		"# 静态播客视频渲染报告",
		"",
		f"- project: `{project_dir}`",
		f"- final_video: `{final}`",
		f"- duration_sec: {video_duration:.3f}",
		f"- visual_segments: {len(segments)}",
		f"- visual_transition: {VISUAL_TRANSITION_EFFECT} count={visual_transition['transition_count']}",
		f"- visual_base: `{visual_base}`",
		f"- publish_info: `{publish_info_path}`",
		f"- bilibili_upload_metadata: `{bilibili_metadata_path}`",
		f"- subtitle_cues: {len(cues)}",
		"- playback_speed_factor: 1.0",
		f"- audio_video_check: {audio_video_check['status']} correlation={audio_video_check['sample_correlation']} rms_diff_over_source={audio_video_check['rms_diff_over_source']}",
		f"- subtitle_overlay: Pillow rendered transparent text overlays with {SUBTITLE_FONT_FULL_NAME}, white text with subtle translucent outline and soft drop shadow, no background box",
		f"- subtitle_font_file: `{SUBTITLE_FONT_PATH}`",
	]
	(video_dir / "render_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
	return {
		"final_video": str(final),
		"duration_sec": round(video_duration, 3),
		"render_manifest": str(video_dir / "render_manifest.json"),
		"publish_info": str(publish_info_path),
		"bilibili_upload_metadata": str(bilibili_metadata_path),
		"visual_base": str(visual_base),
	}


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Render a VibeVoice long-form article podcast video from existing audio/subtitles/chapter visuals.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--fps", type=int, default=FPS)
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	result = render(args.project_dir.expanduser().resolve(), args.fps)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
