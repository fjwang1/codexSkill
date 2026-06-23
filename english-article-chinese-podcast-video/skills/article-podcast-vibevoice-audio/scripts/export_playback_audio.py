#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _ffprobe(path: Path) -> dict[str, Any]:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration,size:stream=index,codec_type,codec_name,sample_rate,channels",
		"-of",
		"json",
		str(path),
	])
	return json.loads(result.stdout)


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_audio(project_dir: Path, mp3_bitrate: str, m4a_bitrate: str) -> dict[str, Any]:
	audio_dir = project_dir / "audio"
	source = audio_dir / "final_podcast.wav"
	assert source.exists(), f"Missing source WAV: {source}"
	mp3 = audio_dir / "final_podcast_preview.mp3"
	m4a = audio_dir / "final_podcast_playback.m4a"
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(source),
		"-c:a",
		"libmp3lame",
		"-b:a",
		mp3_bitrate,
		str(mp3),
	])
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(source),
		"-c:a",
		"aac",
		"-b:a",
		m4a_bitrate,
		str(m4a),
	])
	manifest = {
		"schema_version": "article-podcast-playback-audio.v1",
		"source_wav": "audio/final_podcast.wav",
		"source_wav_sha256": _sha256(source),
		"human_audition_default": "audio/final_podcast_preview.mp3",
		"playback_m4a": "audio/final_podcast_playback.m4a",
		"note": "WAV is the internal alignment/master format. Use MP3/M4A for human audition and playback compatibility.",
		"outputs": {
			"mp3": {
				"path": str(mp3),
				"sha256": _sha256(mp3),
				"bitrate": mp3_bitrate,
				"ffprobe": _ffprobe(mp3),
			},
			"m4a": {
				"path": str(m4a),
				"sha256": _sha256(m4a),
				"bitrate": m4a_bitrate,
				"ffprobe": _ffprobe(m4a),
			},
		},
	}
	_write_json(audio_dir / "playback_audio_manifest.json", manifest)
	return manifest


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Export MP3/M4A playback copies from internal final_podcast.wav.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--mp3-bitrate", default="192k")
	parser.add_argument("--m4a-bitrate", default="192k")
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	manifest = export_audio(args.project_dir.expanduser().resolve(), args.mp3_bitrate, args.m4a_bitrate)
	print(json.dumps({
		"mp3": manifest["outputs"]["mp3"]["path"],
		"m4a": manifest["outputs"]["m4a"]["path"],
		"manifest": str(args.project_dir.expanduser().resolve() / "audio" / "playback_audio_manifest.json"),
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
