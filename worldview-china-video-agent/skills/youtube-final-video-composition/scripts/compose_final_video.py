#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


SRT_TIME_RE = re.compile(
	r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)
DISPLAY_PUNCTUATION = set("，。！？；：、,.!?;:…“”‘’\"'`（）()《》〈〉【】[]{}")


@dataclass(frozen=True)
class Cue:
	index: int
	start: float
	end: float
	text: str


def main() -> int:
	args = parse_args()
	output_dir = args.output_dir.resolve()
	paths = make_paths(output_dir)
	for path in paths.values():
		if path.suffix:
			path.parent.mkdir(parents=True, exist_ok=True)
		else:
			path.mkdir(parents=True, exist_ok=True)

	require_file(args.source_video)
	require_file(args.voiceover_audio)
	require_file(args.subtitle_srt)
	if args.tts_manifest:
		require_file(args.tts_manifest)
	if args.segment_aligned_manifest:
		require_file(args.segment_aligned_manifest)
	require_tool("ffmpeg")
	require_tool("ffprobe")

	cues = parse_srt(args.subtitle_srt)
	if not cues:
		raise RuntimeError("SRT has no cues.")
	playback_speed = args.playback_speed
	if playback_speed <= 0:
		raise RuntimeError(f"Playback speed must be positive, got {playback_speed}.")
	input_srt_sha256 = hash_file(args.subtitle_srt)
	input_cue_sha256 = hash_cues(cues)
	tts_manifest = read_json(args.tts_manifest) if args.tts_manifest else None
	segment_aligned_manifest = read_json(args.segment_aligned_manifest) if args.segment_aligned_manifest else None
	voice_clone = build_voice_clone_evidence(tts_manifest=tts_manifest, segment_aligned_manifest=segment_aligned_manifest)

	source_probe = ffprobe(args.source_video)
	audio_probe = ffprobe(args.voiceover_audio)
	source_duration = get_duration(source_probe)
	audio_duration = get_duration(audio_probe)
	duration = min(source_duration, audio_duration)
	if duration <= 0:
		raise RuntimeError("Could not determine positive render duration.")
	delivery_duration = duration / playback_speed
	delivery_cues = scale_cues(cues, playback_speed)
	validate_subtitle_cues(
		delivery_cues,
		duration=delivery_duration,
		max_cue_duration=args.max_subtitle_cue_duration,
		max_visible_chars=args.max_subtitle_visible_chars,
	)

	delivery_audio_path = paths["audio"] / "final_voiceover.zh-CN.m4a"
	create_delivery_audio(args.voiceover_audio, delivery_audio_path, playback_speed)
	delivery_audio_probe = ffprobe(delivery_audio_path)
	delivery_audio_duration = get_duration(delivery_audio_probe)
	subtitle_srt_out = paths["subtitles"] / "zh-CN.voiceover.srt"
	subtitle_vtt_out = paths["subtitles"] / "zh-CN.voiceover.vtt"
	write_srt(subtitle_srt_out, delivery_cues)
	output_srt_sha256 = hash_file(subtitle_srt_out)
	output_cue_sha256 = hash_cues(delivery_cues)
	write_vtt(subtitle_vtt_out, delivery_cues)
	vtt_generated_from_srt = True

	width, height = output_size(args.output_height)
	render_subtitle_overlay(
		cues=delivery_cues,
		source_srt_sha256=output_srt_sha256,
		source_cue_sha256=output_cue_sha256,
		duration=delivery_duration,
		output_dir=paths["work"] / "subtitle_overlay",
		width=width,
		height=height,
		fps=args.fps,
	)
	overlay_video = paths["work"] / "subtitle_overlay" / "subtitle_overlay.mov"
	overlay_manifest = paths["work"] / "subtitle_overlay" / "overlay_manifest.json"
	overlay_payload = read_json(overlay_manifest)
	if overlay_payload.get("source_srt_sha256") != output_srt_sha256:
		raise RuntimeError("Subtitle overlay was not generated from the final copied SRT.")
	if overlay_payload.get("source_cue_sha256") != output_cue_sha256:
		raise RuntimeError("Subtitle overlay was not generated from the final SRT cues.")
	if overlay_payload.get("cue_count") != len(delivery_cues):
		raise RuntimeError("Subtitle overlay cue count does not match final SRT cue count.")
	compose_video(
		source_video=args.source_video,
		overlay_video=overlay_video,
		voiceover_audio=delivery_audio_path,
		final_video=paths["composited"] / "final.zh-voiceover.subtitled.mp4",
		duration=delivery_duration,
		output_height=args.output_height,
		video_bitrate=args.video_bitrate,
		playback_speed=playback_speed,
	)
	final_video_path = paths["composited"] / "final.zh-voiceover.subtitled.mp4"
	wait_for_stable_size(final_video_path)
	cover_path = create_cover(
		source_video=args.source_video,
		source_thumbnail=args.source_thumbnail,
		cover_title=args.cover_title,
		output_path=paths["cover"] / "cover.zh-CN.jpg",
		frame_time=args.cover_frame_time,
		width=width,
		height=height,
	)
	check_clips = make_check_clips(
		final_video=final_video_path,
		output_dir=paths["qa"] / "check-clips",
		duration=delivery_duration,
		check_points=args.check_point,
	)
	keyframes = make_keyframes(
		final_video=final_video_path,
		output_dir=paths["qa"] / "keyframes",
		duration=delivery_duration,
		check_points=args.check_point,
	)

	final_probe = ffprobe(final_video_path)
	final_video_sha256 = hash_file(final_video_path)
	manifest = {
		"schema_version": "youtube-final-video-composition.v1",
		"video_id": args.video_id,
		"source_url": args.source_url,
		"title": args.title,
		"render_profile": args.render_profile,
		"paths": {
			"source_video": str(args.source_video),
			"source_voiceover_audio": str(args.voiceover_audio),
			"voiceover_audio": str(delivery_audio_path),
			"tts_manifest": str(args.tts_manifest) if args.tts_manifest else None,
			"segment_aligned_manifest": str(args.segment_aligned_manifest) if args.segment_aligned_manifest else None,
			"subtitle_srt": str(subtitle_srt_out),
			"subtitle_vtt": str(subtitle_vtt_out),
			"final_video": str(final_video_path),
			"cover": str(cover_path),
			"qa_report": str(paths["qa"] / "final-render-qa-report.md"),
			"check_clips": [str(path) for path in check_clips],
			"keyframes": [str(path) for path in keyframes],
		},
		"playback": {
			"speed": playback_speed,
			"mode": "final_delivery_speedup",
			"subtitle_timeline": "scaled_to_delivery_timeline",
		},
		"duration": {
			"source_sec": source_duration,
			"voiceover_sec": audio_duration,
			"source_delivery_sec": source_duration / playback_speed,
			"voiceover_delivery_sec": delivery_audio_duration,
			"render_input_sec": duration,
			"render_sec": delivery_duration,
			"final_sec": get_duration(final_probe),
			"final_vs_voiceover_delta_sec": round(abs(get_duration(final_probe) - delivery_audio_duration), 3),
			"source_vs_voiceover_delta_sec": round(abs((source_duration / playback_speed) - delivery_audio_duration), 3),
		},
		"subtitle": {
			"cue_count": len(delivery_cues),
			"overlay_video": str(overlay_video),
			"vtt_generated_from_srt": vtt_generated_from_srt,
			"burned_subtitle_evidence": [str(path) for path in keyframes],
			"version_consistency": {
				"input_srt_sha256": input_srt_sha256,
				"input_cue_sha256": input_cue_sha256,
				"input_timeline": "original_audio_timeline",
				"final_srt_sha256": output_srt_sha256,
				"final_cue_sha256": output_cue_sha256,
				"final_timeline": "delivery_timeline",
				"overlay_source_srt_sha256": overlay_payload.get("source_srt_sha256"),
				"overlay_source_cue_sha256": overlay_payload.get("source_cue_sha256"),
				"overlay_cue_count": overlay_payload.get("cue_count"),
				"overlay_frame_count": overlay_payload.get("frame_count"),
				"overlay_generated_from_final_srt": True,
			},
		},
		"voice_clone": voice_clone,
		"probe": {
			"source": summarize_probe(source_probe),
			"source_voiceover_audio": summarize_probe(audio_probe),
			"audio": summarize_probe(delivery_audio_probe),
			"final": summarize_probe(final_probe),
		},
		"final_video_sha256": final_video_sha256,
	}
	write_json(paths["root"] / "render_manifest.json", manifest)
	write_qa_report(paths["qa"] / "final-render-qa-report.md", manifest)
	print(json.dumps({"ok": True, "manifest": str(paths["root"] / "render_manifest.json")}, ensure_ascii=False, indent=2))
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Compose final Chinese voiceover video with burned subtitles and cover.")
	parser.add_argument("--video-id", required=True)
	parser.add_argument("--title", required=True)
	parser.add_argument("--source-url", required=True)
	parser.add_argument("--source-video", required=True, type=Path)
	parser.add_argument("--voiceover-audio", required=True, type=Path)
	parser.add_argument("--tts-manifest", type=Path)
	parser.add_argument("--segment-aligned-manifest", type=Path)
	parser.add_argument("--subtitle-srt", required=True, type=Path)
	parser.add_argument("--subtitle-vtt", type=Path)
	parser.add_argument("--source-thumbnail", type=Path)
	parser.add_argument("--cover-title", required=True)
	parser.add_argument("--cover-frame-time", type=float)
	parser.add_argument("--output-dir", required=True, type=Path)
	parser.add_argument("--render-profile", default="1080p_high_quality")
	parser.add_argument("--output-height", type=int, default=1080)
	parser.add_argument("--video-bitrate", default="10000k")
	parser.add_argument("--fps", type=float, default=24.0)
	parser.add_argument("--playback-speed", type=float, default=1.15)
	parser.add_argument("--check-point", action="append", type=float, default=[])
	parser.add_argument("--max-subtitle-cue-duration", type=float, default=8.0)
	parser.add_argument("--max-subtitle-visible-chars", type=int, default=48)
	return parser.parse_args()


def make_paths(output_dir: Path) -> dict[str, Path]:
	return {
		"root": output_dir,
		"audio": output_dir / "audio",
		"subtitles": output_dir / "subtitles",
		"composited": output_dir / "composited",
		"cover": output_dir / "cover",
		"qa": output_dir / "qa",
		"work": output_dir / "work",
	}


def require_file(path: Path) -> None:
	if not path.exists():
		raise FileNotFoundError(path)


def require_tool(name: str) -> None:
	if shutil.which(name) is None:
		raise RuntimeError(f"Missing required tool: {name}")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	result = subprocess.run(cmd, text=True, capture_output=True)
	if result.returncode != 0:
		raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
	return result


def ffprobe(path: Path) -> dict[str, Any]:
	result = run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,avg_frame_rate,bit_rate,duration",
		"-of",
		"json",
		str(path),
	])
	payload = json.loads(result.stdout)
	if not isinstance(payload, dict):
		raise RuntimeError(f"ffprobe returned non-object JSON for {path}")
	return payload


def get_duration(probe: dict[str, Any]) -> float:
	format_data = probe.get("format") if isinstance(probe.get("format"), dict) else {}
	try:
		return float(format_data.get("duration") or 0.0)
	except (TypeError, ValueError):
		return 0.0


def summarize_probe(probe: dict[str, Any]) -> dict[str, Any]:
	streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
	format_data = probe.get("format") if isinstance(probe.get("format"), dict) else {}
	return {
		"duration": format_data.get("duration"),
		"size": format_data.get("size"),
		"bit_rate": format_data.get("bit_rate"),
		"streams": streams,
	}


def parse_srt(path: Path) -> list[Cue]:
	blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
	cues: list[Cue] = []
	for block in blocks:
		lines = [line.strip() for line in block.splitlines() if line.strip()]
		if len(lines) < 2:
			continue
		match_line_index = next((index for index, line in enumerate(lines) if SRT_TIME_RE.search(line)), None)
		if match_line_index is None:
			continue
		match = SRT_TIME_RE.search(lines[match_line_index])
		assert match is not None
		text = "\n".join(lines[match_line_index + 1:]).strip()
		if not text:
			continue
		cues.append(Cue(index=len(cues) + 1, start=parse_srt_time(match.group("start")), end=parse_srt_time(match.group("end")), text=text))
	return cues


def parse_srt_time(value: str) -> float:
	hours, minutes, rest = value.split(":")
	seconds, millis = rest.split(",")
	return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def scale_cues(cues: list[Cue], playback_speed: float) -> list[Cue]:
	return [
		Cue(index=cue.index, start=cue.start / playback_speed, end=cue.end / playback_speed, text=cue.text)
		for cue in cues
	]


def validate_subtitle_cues(cues: list[Cue], *, duration: float, max_cue_duration: float, max_visible_chars: int) -> None:
	violations: list[dict[str, Any]] = []
	previous_end = 0.0
	for cue in cues:
		cue_duration = cue.end - cue.start
		visible_chars = visible_len(cue.text)
		punctuation = sorted(set(cue.text) & DISPLAY_PUNCTUATION)
		if cue.start < previous_end - 0.03:
			violations.append({
				"cue": cue.index,
				"reason": "overlap",
				"start": round(cue.start, 3),
				"previous_end": round(previous_end, 3),
			})
		if cue.end > duration + 0.1:
			violations.append({
				"cue": cue.index,
				"reason": "beyond_render_duration",
				"end": round(cue.end, 3),
				"duration": round(duration, 3),
			})
		if cue_duration > max_cue_duration:
			violations.append({
				"cue": cue.index,
				"reason": "cue_duration_too_long",
				"duration": round(cue_duration, 3),
				"max": max_cue_duration,
			})
		if visible_chars > max_visible_chars:
			violations.append({
				"cue": cue.index,
				"reason": "cue_text_too_long",
				"visible_chars": visible_chars,
				"max": max_visible_chars,
			})
		if punctuation:
			violations.append({
				"cue": cue.index,
				"reason": "display_punctuation_present",
				"punctuation": punctuation,
			})
		previous_end = max(previous_end, cue.end)
	if violations:
		raise RuntimeError("Subtitle cue validation failed before final composition: " + json.dumps(violations[:30], ensure_ascii=False))


def visible_len(text: str) -> int:
	return len(re.sub(r"\s+", "", text))


def format_duration(value: float) -> str:
	return f"{max(0.001, value):.3f}"


def format_vtt_time(value: float) -> str:
	total_millis = max(0, int(round(value * 1000)))
	hours, remainder = divmod(total_millis, 3_600_000)
	minutes, remainder = divmod(remainder, 60_000)
	seconds, millis = divmod(remainder, 1000)
	return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def format_srt_time(value: float) -> str:
	return format_vtt_time(value).replace(".", ",")


def output_size(output_height: int) -> tuple[int, int]:
	return (int(round(output_height * 16 / 9)), output_height)


def render_subtitle_overlay(
	cues: list[Cue],
	source_srt_sha256: str,
	source_cue_sha256: str,
	duration: float,
	output_dir: Path,
	width: int,
	height: int,
	fps: float,
) -> None:
	try:
		from PIL import Image, ImageDraw, ImageFont
	except ImportError as exc:
		raise RuntimeError("Pillow is required. Run with: uvx --from pillow python compose_final_video.py ...") from exc

	if output_dir.exists():
		shutil.rmtree(output_dir)
	frames_dir = output_dir / "frames"
	frames_dir.mkdir(parents=True, exist_ok=True)
	blank_path = frames_dir / "blank.png"
	Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(blank_path)
	font_path, font_index = select_font()
	font = ImageFont.truetype(font_path, max(42, int(height * 0.052)), index=font_index)
	entries: list[tuple[Path, float]] = []
	cursor = 0.0
	for cue in cues:
		start = max(0.0, min(duration, cue.start))
		end = max(start, min(duration, cue.end))
		if start > cursor + 0.03:
			entries.append((blank_path, start - cursor))
		if end > start + 0.03:
			frame_path = frames_dir / f"cue_{cue.index:05d}.png"
			render_subtitle_frame(frame_path, cue.text, width, height, font)
			entries.append((frame_path, end - start))
		cursor = max(cursor, end)
	if duration > cursor + 0.03:
		entries.append((blank_path, duration - cursor))
	if not entries:
		entries.append((blank_path, duration))

	concat_path = output_dir / "overlay.ffconcat"
	with concat_path.open("w", encoding="utf-8") as file:
		file.write("ffconcat version 1.0\n")
		for frame_path, entry_duration in entries:
			file.write(f"file '{frame_path}'\n")
			file.write(f"duration {format_duration(entry_duration)}\n")
		file.write(f"file '{entries[-1][0]}'\n")

	run([
		"ffmpeg",
		"-y",
		"-v",
		"error",
		"-f",
		"concat",
		"-safe",
		"0",
		"-i",
		str(concat_path),
		"-r",
		str(fps),
		"-pix_fmt",
		"argb",
		"-c:v",
		"qtrle",
		str(output_dir / "subtitle_overlay.mov"),
	])
	write_json(
		output_dir / "overlay_manifest.json",
		{
			"cue_count": len(cues),
			"frame_count": len(entries),
			"source_srt_sha256": source_srt_sha256,
			"source_cue_sha256": source_cue_sha256,
			"duration_sec": duration,
			"fps": fps,
			"overlay_video": str(output_dir / "subtitle_overlay.mov"),
		},
	)


def select_font() -> tuple[str, int]:
	for path, index in [
		("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
		("/System/Library/Fonts/PingFang.ttc", 0),
		("/System/Library/Fonts/STHeiti Medium.ttc", 1),
	]:
		if Path(path).exists():
			return path, index
	raise RuntimeError("No Chinese-capable font found.")


def render_subtitle_frame(path: Path, text: str, width: int, height: int, font: Any) -> None:
	from PIL import Image, ImageDraw

	image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
	draw = ImageDraw.Draw(image)
	lines = wrap_text(draw, text.replace("\\N", "\n"), font, int(width * 0.82))
	lines = lines[:2] if len(lines) > 2 else lines
	stroke_width = max(4, int(height * 0.0045))
	line_heights = [draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)[3] for line in lines]
	text_height = sum(line_heights) + max(0, len(lines) - 1) * int(height * 0.014)
	y = height - text_height - int(height * 0.045)
	for line, line_height in zip(lines, line_heights, strict=False):
		bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
		x = (width - (bbox[2] - bbox[0])) // 2
		draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 175), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 175))
		draw.text((x, y), line, font=font, fill=(250, 253, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 245))
		y += line_height + int(height * 0.014)
	image.save(path)


def wrap_text(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
	raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
	result: list[str] = []
	for raw_line in raw_lines:
		current = ""
		for char in raw_line:
			test = current + char
			if draw.textbbox((0, 0), test, font=font, stroke_width=2)[2] <= max_width or not current:
				current = test
			else:
				result.append(current)
				current = char
		if current:
			result.append(current)
	return result or [text]


def compose_video(
	source_video: Path,
	overlay_video: Path,
	voiceover_audio: Path,
	final_video: Path,
	duration: float,
	output_height: int,
	video_bitrate: str,
	playback_speed: float,
) -> None:
	filter_complex = (
		f"[0:v]scale=-2:{output_height}:flags=lanczos,setpts=PTS/{playback_speed:.6f}[base];"
		f"[base][1:v]overlay=0:0:format=auto[outv];"
		f"[2:a]asetpts=PTS-STARTPTS[outa]"
	)
	final_video.parent.mkdir(parents=True, exist_ok=True)
	tmp_video = final_video.with_name(f"{final_video.name}.tmp.mp4")
	if tmp_video.exists():
		tmp_video.unlink()
	run([
		"ffmpeg",
		"-y",
		"-stats",
		"-v",
		"warning",
		"-i",
		str(source_video),
		"-i",
		str(overlay_video),
		"-i",
		str(voiceover_audio),
		"-filter_complex",
		filter_complex,
		"-map",
		"[outv]",
		"-map",
		"[outa]",
		"-t",
		f"{duration:.3f}",
		"-c:v",
		"h264_videotoolbox",
		"-b:v",
		video_bitrate,
		"-allow_sw",
		"1",
		"-c:a",
		"aac",
		"-ar",
		"48000",
		"-ac",
		"2",
		"-b:a",
		"192k",
		"-movflags",
		"+faststart",
		str(tmp_video),
	])
	probe = ffprobe(tmp_video)
	streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
	if not any(isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams):
		raise RuntimeError("Composed temp file has no video stream.")
	if not any(isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams):
		raise RuntimeError("Composed temp file has no audio stream.")
	if get_duration(probe) <= 0:
		raise RuntimeError("Composed temp file has no positive duration.")
	tmp_video.replace(final_video)


def create_delivery_audio(source_audio: Path, destination: Path, playback_speed: float) -> None:
	destination.parent.mkdir(parents=True, exist_ok=True)
	tmp_audio = destination.with_name(f"{destination.name}.tmp.m4a")
	if tmp_audio.exists():
		tmp_audio.unlink()
	run([
		"ffmpeg",
		"-y",
		"-v",
		"error",
		"-i",
		str(source_audio),
		"-af",
		f"{atempo_filter(playback_speed)},asetpts=PTS-STARTPTS",
		"-c:a",
		"aac",
		"-ar",
		"48000",
		"-ac",
		"2",
		"-b:a",
		"192k",
		str(tmp_audio),
	])
	probe = ffprobe(tmp_audio)
	if get_duration(probe) <= 0:
		raise RuntimeError("Delivery voiceover audio has no positive duration.")
	tmp_audio.replace(destination)


def atempo_filter(playback_speed: float) -> str:
	if 0.5 <= playback_speed <= 2.0:
		return f"atempo={playback_speed:.6f}"
	factors: list[float] = []
	remaining = playback_speed
	while remaining > 2.0:
		factors.append(2.0)
		remaining /= 2.0
	while remaining < 0.5:
		factors.append(0.5)
		remaining /= 0.5
	factors.append(remaining)
	return ",".join(f"atempo={factor:.6f}" for factor in factors)


def create_cover(source_video: Path, source_thumbnail: Path | None, cover_title: str, output_path: Path, frame_time: float | None, width: int, height: int) -> Path:
	try:
		from PIL import Image, ImageDraw, ImageFont
	except ImportError as exc:
		raise RuntimeError("Pillow is required. Run with: uvx --from pillow python compose_final_video.py ...") from exc

	work_frame = output_path.parent / "cover.base.jpg"
	time_value = frame_time if frame_time is not None else 8.0
	try:
		run(["ffmpeg", "-y", "-v", "error", "-ss", f"{time_value:.3f}", "-i", str(source_video), "-frames:v", "1", str(work_frame)])
		base = Image.open(work_frame).convert("RGB")
	except Exception:
		if source_thumbnail and source_thumbnail.exists():
			base = Image.open(source_thumbnail).convert("RGB")
		else:
			raise
	base = base.resize((width, height), Image.Resampling.LANCZOS)
	overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
	draw = ImageDraw.Draw(overlay)
	for y in range(int(height * 0.56), height):
		alpha = int(40 + 120 * ((y - height * 0.56) / (height * 0.44)))
		draw.line([(0, y), (width, y)], fill=(0, 0, 0, min(alpha, 165)))
	font = fit_font(cover_title, width - int(width * 0.1), int(height * 0.078))
	x = int(width * 0.045)
	y = int(height * 0.74)
	draw.text((x + 4, y + 5), cover_title, font=font, fill=(0, 0, 0, 190), stroke_width=2, stroke_fill=(0, 0, 0, 190))
	draw.text((x, y), cover_title, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(30, 30, 30, 235))
	image = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
	image.save(output_path, quality=95, optimize=True)
	return output_path


def fit_font(text: str, max_width: int, preferred_size: int) -> Any:
	from PIL import Image, ImageDraw, ImageFont

	font_path, font_index = select_font()
	size = preferred_size
	draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
	while size >= 36:
		font = ImageFont.truetype(font_path, size, index=font_index)
		if draw.textbbox((0, 0), text, font=font, stroke_width=2)[2] <= max_width:
			return font
		size -= 2
	return ImageFont.truetype(font_path, size, index=font_index)


def make_check_clips(final_video: Path, output_dir: Path, duration: float, check_points: list[float]) -> list[Path]:
	output_dir.mkdir(parents=True, exist_ok=True)
	points = [0.0, max(0.0, duration / 2 - 15), max(0.0, duration - 45)]
	points.extend(max(0.0, point - 10) for point in check_points)
	result: list[Path] = []
	seen: set[int] = set()
	for point in points:
		start = min(max(0.0, point), max(0.0, duration - 10))
		key = int(start)
		if key in seen:
			continue
		seen.add(key)
		length = min(30.0, duration - start)
		out = output_dir / f"check.{key:04d}-{int(key + length):04d}.mp4"
		run([
			"ffmpeg",
			"-y",
			"-v",
			"error",
			"-ss",
			f"{start:.3f}",
			"-t",
			f"{length:.3f}",
			"-i",
			str(final_video),
			"-c:v",
			"libx264",
			"-preset",
			"veryfast",
			"-crf",
			"20",
			"-c:a",
			"aac",
			"-b:a",
			"192k",
			str(out),
		])
		result.append(out)
	return result


def make_keyframes(final_video: Path, output_dir: Path, duration: float, check_points: list[float]) -> list[Path]:
	output_dir.mkdir(parents=True, exist_ok=True)
	points = [min(5.0, duration / 3), duration / 2]
	points.extend(check_points)
	result: list[Path] = []
	for index, point in enumerate(points, start=1):
		time_value = min(max(0.0, point), max(0.0, duration - 0.1))
		out = output_dir / f"frame_{index:02d}_{time_value:.1f}.jpg"
		run(["ffmpeg", "-y", "-v", "error", "-ss", f"{time_value:.3f}", "-i", str(final_video), "-frames:v", "1", str(out)])
		result.append(out)
	return result


def copy_asset(source: Path, destination: Path) -> None:
	destination.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(source, destination)


def hash_file(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as file:
		for chunk in iter(lambda: file.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def hash_cues(cues: list[Cue]) -> str:
	payload = json.dumps(
		[{"index": cue.index, "start": round(cue.start, 3), "end": round(cue.end, 3), "text": cue.text} for cue in cues],
		ensure_ascii=False,
		separators=(",", ":"),
	)
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_voice_clone_evidence(*, tts_manifest: dict[str, Any] | None, segment_aligned_manifest: dict[str, Any] | None) -> dict[str, Any]:
	source = tts_manifest or {}
	if not source and segment_aligned_manifest:
		voice_clone = segment_aligned_manifest.get("voice_clone")
		source = voice_clone if isinstance(voice_clone, dict) else {}
	mode = source.get("mode")
	ref_audio_sha256 = source.get("ref_audio_sha256")
	ref_text_sha256 = source.get("ref_text_sha256")
	if mode != "voice_clone_only":
		raise RuntimeError(f"Voice clone evidence must use mode voice_clone_only, got {mode!r}.")
	if not isinstance(ref_audio_sha256, str) or len(ref_audio_sha256) != 64:
		raise RuntimeError("Voice clone evidence must contain 64-char ref_audio_sha256.")
	if not isinstance(ref_text_sha256, str) or len(ref_text_sha256) != 64:
		raise RuntimeError("Voice clone evidence must contain 64-char ref_text_sha256.")
	return {
		"mode": mode,
		"model_dir": source.get("model_dir"),
		"ref_audio_path": source.get("ref_audio_path"),
		"ref_audio_sha256": ref_audio_sha256,
		"ref_text_path": source.get("ref_text_path"),
		"ref_text_sha256": ref_text_sha256,
		"reference_source": source.get("reference_source"),
		"lang_code": source.get("lang_code"),
		"segment_count": source.get("segment_count"),
	}


def read_json(path: Path) -> dict[str, Any]:
	payload = json.loads(path.read_text(encoding="utf-8"))
	if not isinstance(payload, dict):
		raise RuntimeError(f"Expected JSON object: {path}")
	return payload


def wait_for_stable_size(path: Path) -> None:
	first = path.stat().st_size
	second = path.stat().st_size
	if first <= 0 or second <= 0:
		raise RuntimeError(f"Final video has invalid size: {path}")
	if first != second:
		raise RuntimeError(f"Final video size is not stable: {first} != {second}")


def write_vtt(path: Path, cues: list[Cue]) -> None:
	lines = ["WEBVTT", ""]
	for cue in cues:
		lines.extend([
			f"{format_vtt_time(cue.start)} --> {format_vtt_time(cue.end)}",
			cue.text,
			"",
		])
	path.write_text("\n".join(lines), encoding="utf-8")


def write_srt(path: Path, cues: list[Cue]) -> None:
	lines: list[str] = []
	for index, cue in enumerate(cues, start=1):
		lines.extend([
			str(index),
			f"{format_srt_time(cue.start)} --> {format_srt_time(cue.end)}",
			cue.text,
			"",
		])
	path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
	path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def stream_summary(probe: dict[str, Any], codec_type: str) -> str:
	streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
	format_data = probe.get("format") if isinstance(probe.get("format"), dict) else {}
	stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == codec_type), None)
	if not stream:
		return "missing"
	if codec_type == "video":
		size = f"{stream.get('width', '?')}x{stream.get('height', '?')}"
		bitrate = stream.get("bit_rate") or format_data.get("bit_rate")
		return f"{stream.get('codec_name', '?')} {size}, bitrate={bitrate or 'unknown'}"
	bitrate = stream.get("bit_rate") or format_data.get("bit_rate")
	return f"{stream.get('codec_name', '?')}, bitrate={bitrate or 'unknown'}"


def write_qa_report(path: Path, manifest: dict[str, Any]) -> None:
	lines = [
		"# Final Render QA Report",
		"",
		f"- Video ID: `{manifest['video_id']}`",
		f"- Title: `{manifest['title']}`",
		f"- Final video: `{manifest['paths']['final_video']}`",
		f"- Cover: `{manifest['paths']['cover']}`",
		f"- Voiceover: `{manifest['paths']['voiceover_audio']}`",
		f"- SRT: `{manifest['paths']['subtitle_srt']}`",
		f"- VTT: `{manifest['paths']['subtitle_vtt']}`",
		f"- Render duration: `{manifest['duration']['render_sec']:.3f}s`",
		f"- Final duration: `{manifest['duration']['final_sec']:.3f}s`",
		f"- Playback speed: `{manifest['playback']['speed']:.2f}x`",
		f"- Final vs voiceover delta: `{manifest['duration']['final_vs_voiceover_delta_sec']:.3f}s`",
		f"- Source vs voiceover delta: `{manifest['duration']['source_vs_voiceover_delta_sec']:.3f}s`",
		f"- Subtitle cue count: `{manifest['subtitle']['cue_count']}`",
		f"- Final video sha256: `{manifest['final_video_sha256']}`",
		f"- VTT generated from SRT: `{manifest['subtitle']['vtt_generated_from_srt']}`",
		f"- Voice clone mode: `{manifest['voice_clone']['mode']}`",
		f"- Voice ref audio sha256: `{manifest['voice_clone']['ref_audio_sha256']}`",
		f"- Voice ref text sha256: `{manifest['voice_clone']['ref_text_sha256']}`",
		"",
		"## Probe Summary",
		"",
		f"- Source video: `{stream_summary(manifest['probe']['source'], 'video')}`",
		f"- Voiceover audio: `{stream_summary(manifest['probe']['audio'], 'audio')}`",
		f"- Final video: `{stream_summary(manifest['probe']['final'], 'video')}`",
		f"- Final audio: `{stream_summary(manifest['probe']['final'], 'audio')}`",
		"",
		"## Subtitle Evidence",
		"",
		"- Subtitles are burned through a generated transparent overlay video.",
		f"- Overlay video: `{manifest['subtitle']['overlay_video']}`",
		"- Keyframes below are the visual evidence for subtitle readability.",
		"",
		"## Check Clips",
		"",
	]
	lines.extend(f"- `{path}`" for path in manifest["paths"]["check_clips"])
	lines.extend(["", "## Keyframes", ""])
	lines.extend(f"- `{path}`" for path in manifest["paths"]["keyframes"])
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except Exception as exc:
		print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
		raise
