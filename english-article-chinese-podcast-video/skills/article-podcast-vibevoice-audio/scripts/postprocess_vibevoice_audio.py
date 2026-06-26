#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _duration(path: Path) -> float:
	result = subprocess.run(
		[
			"ffprobe",
			"-v",
			"error",
			"-show_entries",
			"format=duration",
			"-of",
			"default=noprint_wrappers=1:nokey=1",
			str(path),
		],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return float(result.stdout.strip())


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _find_raw_wav(project_dir: Path) -> Path:
	raw_dir = project_dir / "audio" / "vibevoice_raw"
	candidates = sorted(raw_dir.glob("*.wav"), key=lambda path: path.stat().st_mtime, reverse=True)
	assert candidates, f"No VibeVoice wav found in {raw_dir}"
	return candidates[0]


def _volumedetect(path: Path) -> dict[str, float]:
	completed = subprocess.run(
		["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	text = completed.stdout + "\n" + completed.stderr
	values: dict[str, float] = {}
	for key in ("mean_volume", "max_volume"):
		match = re.search(rf"{key}:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
		if match:
			values[key] = float(match.group(1))
	assert "mean_volume" in values and "max_volume" in values, f"Could not parse volumedetect output for {path}"
	return values


def postprocess(
	project_dir: Path,
	raw_wav: Path | None,
	output: Path,
	silence_threshold: str,
	max_silence_sec: float,
	min_source_mean_volume: float,
	min_source_max_volume: float,
	allow_low_level_source: bool,
) -> dict[str, Any]:
	source = raw_wav.expanduser().resolve() if raw_wav else _find_raw_wav(project_dir)
	assert source.exists(), f"Missing raw wav: {source}"
	source_loudness = _volumedetect(source)
	if not allow_low_level_source:
		assert source_loudness["mean_volume"] >= min_source_mean_volume, (
			f"VibeVoice source mean_volume is suspiciously low: {source_loudness['mean_volume']:.1f} dB "
			f"< {min_source_mean_volume:.1f} dB. Rerun VibeVoice with the stable profile instead of rescuing it with loudnorm."
		)
		assert source_loudness["max_volume"] >= min_source_max_volume, (
			f"VibeVoice source max_volume is suspiciously low: {source_loudness['max_volume']:.1f} dB "
			f"< {min_source_max_volume:.1f} dB. Rerun VibeVoice with the stable profile instead of rescuing it with loudnorm."
		)
	output.parent.mkdir(parents=True, exist_ok=True)
	audio_filter = (
		f"silenceremove=start_periods=1:start_duration=0.2:start_threshold={silence_threshold}:"
		f"stop_periods=-1:stop_duration={max_silence_sec}:stop_threshold={silence_threshold},"
		"loudnorm=I=-18:TP=-1.5:LRA=11"
	)
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(source),
		"-af",
		audio_filter,
		"-ac",
		"1",
		"-ar",
		"24000",
		"-c:a",
		"pcm_s16le",
		str(output),
	])
	manifest_path = project_dir / "audio" / "audio_manifest.json"
	if manifest_path.exists():
		manifest = _read_json(manifest_path)
		manifest.update({
			"final_audio": "audio/final_podcast.wav" if output == project_dir / "audio" / "final_podcast.wav" else str(output),
			"final_audio_sha256": _sha256(output),
			"duration_sec": round(_duration(output), 3),
			"postprocess": {
				"source_wav": str(source),
				"source_sha256": _sha256(source),
				"source_loudness": source_loudness,
				"method": "silenceremove_plus_loudnorm",
				"silence_threshold": silence_threshold,
				"max_silence_sec": max_silence_sec,
				"loudnorm_i": -18,
				"loudnorm_tp": -1.5,
				"loudnorm_lra": 11,
			},
		})
		_write_json(manifest_path, manifest)
	return {
		"raw_wav": str(source),
		"final_audio": str(output),
		"duration_sec": round(_duration(output), 3),
		"sha256": _sha256(output),
		"source_loudness": source_loudness,
	}


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Postprocess VibeVoice raw wav into final_podcast.wav.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--raw-wav", type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--silence-threshold", default="-50dB")
	parser.add_argument("--max-silence-sec", type=float, default=0.8)
	parser.add_argument("--min-source-mean-volume", type=float, default=-30.0)
	parser.add_argument("--min-source-max-volume", type=float, default=-10.0)
	parser.add_argument("--allow-low-level-source", action="store_true")
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	output = (args.output or project_dir / "audio" / "final_podcast.wav").expanduser().resolve()
	result = postprocess(
		project_dir,
		args.raw_wav,
		output,
		args.silence_threshold,
		args.max_silence_sec,
		args.min_source_mean_volume,
		args.min_source_max_volume,
		args.allow_low_level_source,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
