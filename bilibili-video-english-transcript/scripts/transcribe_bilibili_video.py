#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import mlx_whisper


DEFAULT_OUTPUT_ROOT = Path("/Users/wangfangjia/code/bilibili-mcp/outputs/bilibili_english_transcripts")
DEFAULT_MODEL = "mlx-community/whisper-tiny"


def _log(message: str) -> None:
	print(f"[bilibili-transcript] {message}", flush=True)


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
	_log(" ".join(cmd))
	subprocess.run(cmd, cwd=cwd, check=True)


def _run_capture_json(cmd: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
	_log(" ".join(cmd))
	result = subprocess.run(cmd, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE)
	return json.loads(result.stdout)


def _require_command(name: str) -> None:
	if shutil.which(name) is None:
		raise SystemExit(f"Required command not found: {name}")


def _extract_bvid(value: str) -> str:
	match = re.search(r"(BV[0-9A-Za-z]+)", value)
	if not match:
		raise SystemExit(f"Could not find a Bilibili BV id in: {value}")
	return match.group(1)


def _parse_timestamp(value: str | None) -> float:
	if not value:
		return 0.0
	if re.fullmatch(r"\d+(\.\d+)?", value):
		return float(value)
	parts = value.split(":")
	if len(parts) not in (2, 3):
		raise SystemExit(f"Invalid timestamp: {value}")
	parts_float = [float(part) for part in parts]
	if len(parts_float) == 2:
		minutes, seconds = parts_float
		return minutes * 60 + seconds
	hours, minutes, seconds = parts_float
	return hours * 3600 + minutes * 60 + seconds


def _format_srt_time(seconds: float) -> str:
	milliseconds = max(0, int(round(seconds * 1000)))
	hours = milliseconds // 3_600_000
	minutes = (milliseconds % 3_600_000) // 60_000
	secs = (milliseconds % 60_000) // 1000
	ms = milliseconds % 1000
	return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _segments_to_srt(segments: list[dict[str, Any]], *, offset_seconds: float) -> str:
	blocks: list[str] = []
	for index, segment in enumerate(segments, start=1):
		start = _format_srt_time(float(segment["start"]) + offset_seconds)
		end = _format_srt_time(float(segment["end"]) + offset_seconds)
		text = str(segment.get("text", "")).strip()
		blocks.append(f"{index}\n{start} --> {end}\n{text}")
	return "\n\n".join(blocks).strip() + "\n"


def _write_text(path: Path, text: str) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(text, encoding="utf-8")


def _build_yt_dlp_base(cookies_from_browser: str | None, cookies_file: str | None) -> list[str]:
	cmd = ["yt-dlp"]
	if cookies_from_browser:
		cmd.extend(["--cookies-from-browser", cookies_from_browser])
	if cookies_file:
		cmd.extend(["--cookies", cookies_file])
	return cmd


def _download_metadata(url: str, run_dir: Path, cookies_from_browser: str | None, cookies_file: str | None) -> dict[str, Any]:
	cmd = _build_yt_dlp_base(cookies_from_browser, cookies_file)
	cmd.extend(["--dump-single-json", "--no-playlist", url])
	metadata = _run_capture_json(cmd)
	(run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
	return metadata


def _download_video(url: str, media_dir: Path, cookies_from_browser: str | None, cookies_file: str | None) -> Path:
	cmd = _build_yt_dlp_base(cookies_from_browser, cookies_file)
	cmd.extend(
		[
			"-f",
			"bv*+ba/bestvideo+bestaudio/best",
			"--merge-output-format",
			"mp4",
			"--no-playlist",
			"-o",
			str(media_dir / "%(id)s.full.%(ext)s"),
			url,
		]
	)
	_run(cmd)
	videos = sorted(media_dir.glob("*.full.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
	if not videos:
		raise SystemExit(f"Video download completed but no merged mp4 found in {media_dir}")
	return videos[0]


def _extract_audio(video_path: Path, audio_path: Path, clip_start: str | None, clip_duration: str | None) -> float:
	cmd = ["ffmpeg", "-y"]
	offset = _parse_timestamp(clip_start)
	if clip_start:
		cmd.extend(["-ss", clip_start])
	cmd.extend(["-i", str(video_path)])
	if clip_duration:
		cmd.extend(["-t", clip_duration])
	cmd.extend(["-vn", "-ac", "1", "-ar", "16000", str(audio_path)])
	_run(cmd)
	return offset


def _transcribe(audio_path: Path, model: str, language: str, initial_prompt: str | None) -> dict[str, Any]:
	options: dict[str, Any] = {
		"path_or_hf_repo": model,
		"language": language,
		"task": "transcribe",
		"word_timestamps": False,
		"verbose": True,
	}
	if initial_prompt:
		options["initial_prompt"] = initial_prompt
	return mlx_whisper.transcribe(str(audio_path), **options)


def _write_report(
	run_dir: Path,
	metadata: dict[str, Any],
	url: str,
	bvid: str,
	model: str,
	video_path: Path,
	audio_path: Path,
	transcript_txt: Path,
	transcript_srt: Path,
	transcript_json: Path,
	result: dict[str, Any],
) -> None:
	title = metadata.get("title") or bvid
	duration = metadata.get("duration")
	text = str(result.get("text", "")).strip()
	preview = text[:1200].replace("\n", " ")
	report = f"""# Bilibili English Transcript

Title: {title}

BVID: {bvid}

URL: {url}

Duration: {duration}

Whisper model: {model}

Video: {video_path}

Audio: {audio_path}

Transcript TXT: {transcript_txt}

Transcript SRT: {transcript_srt}

Transcript JSON: {transcript_json}

## Preview

{preview}
"""
	_write_text(run_dir / "report.md", report)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Download a Bilibili video and generate an English Whisper transcript.")
	parser.add_argument("url", help="Bilibili URL or BV id")
	parser.add_argument("--out-root", default=str(DEFAULT_OUTPUT_ROOT), help="Root directory for transcript runs")
	parser.add_argument("--run-dir", default="", help="Exact output directory. Overrides --out-root")
	parser.add_argument("--model", default=os.environ.get("WHISPER_MODEL", DEFAULT_MODEL), help="MLX Whisper model repo")
	parser.add_argument("--language", default="en", help="ASR language code")
	parser.add_argument("--cookies-from-browser", default="chrome", help="Browser profile for yt-dlp cookies; use empty string to disable")
	parser.add_argument("--cookies-file", default="", help="Explicit cookies.txt file for yt-dlp")
	parser.add_argument("--source-video", default="", help="Use an existing complete video file instead of downloading it again")
	parser.add_argument("--clip-start", default="", help="Optional start timestamp for a test clip, e.g. 00:01:20")
	parser.add_argument("--clip-duration", default="", help="Optional clip duration for a test clip, e.g. 30")
	parser.add_argument("--initial-prompt", default="Bloomberg, Businessweek, Lulu Yilun Chen, China, capital controls, capital flight, wealthy Chinese families, underground banking, smurfing, cryptocurrency.", help="Optional Whisper prompt")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	_require_command("yt-dlp")
	_require_command("ffmpeg")

	url = args.url if args.url.startswith(("http://", "https://")) else f"https://www.bilibili.com/video/{args.url}/"
	bvid = _extract_bvid(url)
	timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	run_dir = Path(args.run_dir).expanduser() if args.run_dir else Path(args.out_root).expanduser() / f"{bvid}_{timestamp}"
	media_dir = run_dir / "media"
	audio_dir = run_dir / "audio"
	transcript_dir = run_dir / "transcripts"
	for path in (media_dir, audio_dir, transcript_dir):
		path.mkdir(parents=True, exist_ok=True)

	cookies_from_browser = args.cookies_from_browser or None
	cookies_file = args.cookies_file or None

	_log(f"Output directory: {run_dir}")
	metadata = _download_metadata(url, run_dir, cookies_from_browser, cookies_file)
	if args.source_video:
		source_video = Path(args.source_video).expanduser()
		if not source_video.exists():
			raise SystemExit(f"Source video does not exist: {source_video}")
		video_path = media_dir / source_video.name
		if source_video.resolve() != video_path.resolve():
			shutil.copy2(source_video, video_path)
		_log(f"Using existing source video: {video_path}")
	else:
		video_path = _download_video(url, media_dir, cookies_from_browser, cookies_file)
	audio_path = audio_dir / f"{bvid}.16k.wav"
	offset = _extract_audio(video_path, audio_path, args.clip_start or None, args.clip_duration or None)
	result = _transcribe(audio_path, args.model, args.language, args.initial_prompt or None)

	transcript_json = transcript_dir / f"{bvid}.whisper.json"
	transcript_txt = transcript_dir / f"{bvid}.english.txt"
	transcript_srt = transcript_dir / f"{bvid}.english.srt"
	transcript_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	_write_text(transcript_txt, str(result.get("text", "")).strip() + "\n")
	_write_text(transcript_srt, _segments_to_srt(result.get("segments", []), offset_seconds=offset))
	_write_report(run_dir, metadata, url, bvid, args.model, video_path, audio_path, transcript_txt, transcript_srt, transcript_json, result)

	_log(f"Transcript TXT: {transcript_txt}")
	_log(f"Transcript SRT: {transcript_srt}")
	_log(f"Report: {run_dir / 'report.md'}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
