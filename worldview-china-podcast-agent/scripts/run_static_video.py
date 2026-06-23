#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH = 3840
HEIGHT = 2160
FONT_PATH = Path("/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf")


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _duration(path: Path) -> float:
	result = subprocess.run(
		["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return float(result.stdout.strip())


def _probe(path: Path) -> dict[str, Any]:
	result = subprocess.run(
		["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return json.loads(result.stdout)


def _draw_cover(run_dir: Path, output: Path) -> None:
	metadata = _read_json(run_dir / "02-source-capture" / "source_metadata.json")
	thumb = run_dir / "02-source-capture" / "thumbnail.jpg"
	title = str(metadata.get("title") or "Worldview China Podcast")
	channel = str(metadata.get("channel") or "")
	image = Image.open(thumb).convert("RGB")
	image.thumbnail((WIDTH, HEIGHT))
	bg = image.resize((WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(26))
	overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 112))
	bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
	draw = ImageDraw.Draw(bg)
	title_font = ImageFont.truetype(str(FONT_PATH), 136)
	sub_font = ImageFont.truetype(str(FONT_PATH), 58)
	badge_font = ImageFont.truetype(str(FONT_PATH), 52)
	margin = 210
	draw.rounded_rectangle((margin, 250, WIDTH - margin, 470), radius=24, fill=(210, 77, 43, 230))
	draw.text((margin + 52, 305), "世界眼中的中国 · 中文播客翻译", font=badge_font, fill=(255, 255, 255, 255))
	wrapped = _wrap_text(draw, title, title_font, WIDTH - margin * 2, max_lines=3)
	y = 720
	for line in wrapped:
		draw.text((margin, y), line, font=title_font, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 170))
		y += 165
	draw.text((margin, 1510), channel.strip(), font=sub_font, fill=(235, 235, 235, 255))
	draw.text((margin, 1600), "忠实翻译原播客内容 · VibeVoice 中文双人播客", font=sub_font, fill=(235, 235, 235, 235))
	output.parent.mkdir(parents=True, exist_ok=True)
	bg.convert("RGB").save(output, quality=95)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
	words = text.split()
	lines: list[str] = []
	current = ""
	for word in words:
		candidate = f"{current} {word}".strip()
		if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
			current = candidate
			continue
		if current:
			lines.append(current)
		current = word
	if current:
		lines.append(current)
	if len(lines) > max_lines:
		lines = lines[:max_lines]
		lines[-1] = lines[-1].rstrip(" .") + "..."
	return lines


def _ffmpeg_filter_exists(name: str) -> bool:
	result = subprocess.run(
		["ffmpeg", "-hide_banner", "-filters"],
		check=False,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return result.returncode == 0 and any(f" {name} " in line for line in result.stdout.splitlines())


def _safe_concat_path(path: Path) -> str:
	return str(path).replace("'", "'\\''")


def _draw_subtitle_frame(base: Image.Image, text: str, output: Path) -> None:
	output.parent.mkdir(parents=True, exist_ok=True)
	if not text:
		base.save(output, quality=95)
		return
	frame = base.copy()
	draw = ImageDraw.Draw(frame)
	font = ImageFont.truetype(str(FONT_PATH), 96)
	box = draw.textbbox((0, 0), text, font=font, stroke_width=3)
	text_width = box[2] - box[0]
	text_height = box[3] - box[1]
	x = max(80, (WIDTH - text_width) // 2)
	y = min(1830, max(1760, HEIGHT - 260 - text_height))
	shadow_offset = 4
	draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=(0, 0, 0, 128), stroke_width=3, stroke_fill=(0, 0, 0, 96))
	draw.text((x, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(30, 30, 30, 160))
	frame.save(output, quality=95)


def _subtitle_intervals(cues: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
	points = {0.0, round(duration, 3)}
	for cue in cues:
		start = max(0.0, min(duration, float(cue["start_sec"])))
		end = max(0.0, min(duration, float(cue["end_sec"])))
		if end <= start:
			continue
		points.add(round(start, 3))
		points.add(round(end, 3))
	times = sorted(points)
	intervals: list[dict[str, Any]] = []
	for start, end in zip(times, times[1:]):
		if end - start < 0.03:
			continue
		mid = (start + end) / 2.0
		active = [
			cue for cue in cues
			if float(cue["start_sec"]) <= mid < float(cue["end_sec"])
		]
		active.sort(key=lambda cue: (float(cue["start_sec"]), int(cue.get("index") or 0)))
		text = str((active[-1] if active else {}).get("display_text") or "")
		intervals.append({"start_sec": start, "end_sec": end, "duration_sec": round(end - start, 3), "text": text})
	return intervals


def _render_with_pillow_frames(cover: Path, audio: Path, subtitle_manifest: Path, final_video: Path) -> dict[str, Any]:
	manifest = _read_json(subtitle_manifest)
	duration = _duration(audio)
	cues = list(manifest.get("cues") or [])
	assert cues, f"Subtitle manifest has no cues: {subtitle_manifest}"
	frames_dir = final_video.parent / "subtitle_frames"
	frames_dir.mkdir(parents=True, exist_ok=True)
	base = Image.open(cover).convert("RGB")
	intervals = _subtitle_intervals(cues, duration)
	assert intervals, "No subtitle intervals generated"
	frame_cache: dict[str, Path] = {}
	concat_lines: list[str] = []
	last_frame: Path | None = None
	for index, interval in enumerate(intervals, start=1):
		text = str(interval["text"])
		key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16] if text else "blank"
		frame_path = frame_cache.get(key)
		if frame_path is None:
			frame_path = frames_dir / f"frame_{len(frame_cache) + 1:04d}_{key}.jpg"
			_draw_subtitle_frame(base, text, frame_path)
			frame_cache[key] = frame_path
		concat_lines.append(f"file '{_safe_concat_path(frame_path)}'")
		concat_lines.append(f"duration {float(interval['duration_sec']):.3f}")
		last_frame = frame_path
	assert last_frame is not None
	concat_lines.append(f"file '{_safe_concat_path(last_frame)}'")
	concat_path = final_video.parent / "subtitle_frame_concat.txt"
	concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
	subprocess.run(
		[
			"ffmpeg",
			"-y",
			"-f",
			"concat",
			"-safe",
			"0",
			"-i",
			str(concat_path),
			"-i",
			str(audio),
			"-map",
			"0:v:0",
			"-map",
			"1:a:0",
			"-c:v",
			"libx264",
			"-pix_fmt",
			"yuv420p",
			"-preset",
			"veryfast",
			"-crf",
			"18",
			"-r",
			"30",
			"-c:a",
			"aac",
			"-b:a",
			"192k",
			"-shortest",
			"-movflags",
			"+faststart",
			str(final_video),
		],
		check=True,
	)
	return {
		"method": "pillow_frame_concat_fallback",
		"interval_count": len(intervals),
		"unique_frame_count": len(frame_cache),
		"concat": str(concat_path),
		"frames_dir": str(frames_dir),
	}


def run_static_video(run_dir: Path, force: bool) -> dict[str, Any]:
	output_dir = run_dir / "08-static-video"
	video_root = run_dir / "video"
	output_dir.mkdir(parents=True, exist_ok=True)
	video_root.mkdir(parents=True, exist_ok=True)
	cover = output_dir / "cover.png"
	audio = run_dir / "audio" / "final_podcast.wav"
	ass = run_dir / "video" / "final_subtitles.ass"
	assert audio.exists(), f"Missing final audio: {audio}"
	assert ass.exists(), f"Missing final subtitles ASS: {ass}"
	if force or not cover.exists():
		_draw_cover(run_dir, cover)
	final_video = output_dir / "final_video.mp4"
	subtitle_render: dict[str, Any]
	if force or not final_video.exists():
		if _ffmpeg_filter_exists("subtitles"):
			subprocess.run(
				[
					"ffmpeg",
					"-y",
					"-loop",
					"1",
					"-framerate",
					"30",
					"-i",
					str(cover),
					"-i",
					str(audio),
					"-vf",
					f"scale={WIDTH}:{HEIGHT},subtitles=filename='{ass}'",
					"-c:v",
					"libx264",
					"-pix_fmt",
					"yuv420p",
					"-preset",
					"medium",
					"-crf",
					"18",
					"-c:a",
					"aac",
					"-b:a",
					"192k",
					"-shortest",
					"-movflags",
					"+faststart",
					str(final_video),
				],
				check=True,
			)
			subtitle_render = {"method": "ffmpeg_subtitles_filter"}
		else:
			subtitle_render = _render_with_pillow_frames(cover, audio, run_dir / "video" / "subtitle_manifest.json", final_video)
	else:
		subtitle_render = {"method": "existing_file_reused"}
	shutil.copy2(final_video, video_root / "final_video.mp4")
	shutil.copy2(cover, video_root / "cover.png")
	screenshots_dir = output_dir / "screenshots"
	screenshots_dir.mkdir(parents=True, exist_ok=True)
	duration = _duration(final_video)
	points = {
		"opening": 15,
		"middle": max(15, duration / 2),
		"end": max(15, duration - 15),
	}
	screenshots: dict[str, str] = {}
	for name, second in points.items():
		path = screenshots_dir / f"{name}.png"
		subprocess.run(["ffmpeg", "-y", "-ss", f"{second:.3f}", "-i", str(final_video), "-frames:v", "1", str(path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		screenshots[name] = str(path)
	manifest = {
		"schema_version": "worldview-china-static-video-render.v1",
		"status": "pass",
		"visual_mode": "single_static_cover_v1",
		"cover": str(cover),
		"audio": str(audio),
		"subtitles_ass": str(ass),
		"subtitle_render": subtitle_render,
		"final_video": str(final_video),
		"root_final_video": str(video_root / "final_video.mp4"),
		"duration_sec": round(duration, 3),
		"probe": _probe(final_video),
		"screenshots": screenshots,
	}
	_write_json(output_dir / "render_manifest.json", manifest)
	_write_json(video_root / "render_manifest.json", manifest)
	(output_dir / "render_report.md").write_text(
		"\n".join([
			"# Static Video Render Report",
			"",
			"- status: PASS",
			"- visual_mode: single_static_cover_v1",
			f"- final_video: {final_video}",
			f"- duration_sec: {duration:.3f}",
			"- subtitles: burned ASS",
			f"- subtitle_render_method: {subtitle_render['method']}",
		]) + "\n",
		encoding="utf-8",
	)
	shutil.copy2(output_dir / "render_report.md", video_root / "render_report.md")
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["08-static-video"] = {
		"status": "pass",
		"final_video": str(final_video),
		"root_final_video": str(video_root / "final_video.mp4"),
		"render_manifest": str(output_dir / "render_manifest.json"),
		"duration_sec": round(duration, 3),
	}
	_write_json(run_manifest_path, run_manifest)
	return run_manifest["nodes"]["08-static-video"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Render static podcast video with burned Chinese subtitles.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--force", action="store_true")
	args = parser.parse_args()
	result = run_static_video(args.run_dir.expanduser().resolve(), args.force)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
