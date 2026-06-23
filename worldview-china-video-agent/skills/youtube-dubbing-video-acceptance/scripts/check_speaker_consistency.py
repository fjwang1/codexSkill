#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav


def main() -> int:
	args = parse_args()
	require_file(args.voiceover_audio)
	require_file(args.segments)
	segments_payload = json.loads(args.segments.read_text(encoding="utf-8"))
	segments = segments_payload.get("segments")
	if not isinstance(segments, list) or not segments:
		raise RuntimeError("segments JSON must contain non-empty segments list.")
	selected = select_segments(segments, args.sample_count, args.min_segment_sec)
	if len(selected) < min(args.sample_count, len(segments)):
		raise RuntimeError("Could not select enough usable speech segments.")

	with tempfile.TemporaryDirectory() as temp_dir:
		temp_root = Path(temp_dir)
		clip_paths = [
			extract_clip(args.voiceover_audio, temp_root, index, segment)
			for index, segment in enumerate(selected)
		]
		encoder = VoiceEncoder()
		embeddings = [encoder.embed_utterance(preprocess_wav(path)) for path in clip_paths]

	matrix = similarity_matrix(embeddings)
	pairwise = [
		{
			"a": selected[i]["segment_id"],
			"b": selected[j]["segment_id"],
			"cosine": round(float(matrix[i, j]), 4),
		}
		for i in range(len(selected))
		for j in range(i + 1, len(selected))
	]
	min_similarity = min((item["cosine"] for item in pairwise), default=1.0)
	decision = "PASS" if min_similarity >= args.min_similarity else "WARN"
	if min_similarity < args.fail_similarity:
		decision = "FAIL"
	result = {
		"schema_version": "speaker-consistency.v1",
		"decision": decision,
		"voiceover_audio_path": str(args.voiceover_audio.resolve()),
		"segments_path": str(args.segments.resolve()),
		"sample_count": len(selected),
		"min_similarity": min_similarity,
		"pass_threshold": args.min_similarity,
		"fail_threshold": args.fail_similarity,
		"selected_segments": [
			{
				"segment_id": segment["segment_id"],
				"start": segment["start"],
				"end": segment["end"],
				"start_sec": parse_hhmmss(str(segment["start"])),
				"end_sec": parse_hhmmss(str(segment["end"])),
			}
			for segment in selected
		],
		"pairwise": pairwise,
	}
	args.output_json.parent.mkdir(parents=True, exist_ok=True)
	args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Check whether sampled voiceover segments sound like one speaker.")
	parser.add_argument("--voiceover-audio", required=True, type=Path)
	parser.add_argument("--segments", required=True, type=Path)
	parser.add_argument("--output-json", required=True, type=Path)
	parser.add_argument("--sample-count", type=int, default=3)
	parser.add_argument("--min-segment-sec", type=float, default=3.0)
	parser.add_argument("--max-clip-sec", type=float, default=8.0)
	parser.add_argument("--min-similarity", type=float, default=0.70)
	parser.add_argument("--fail-similarity", type=float, default=0.55)
	return parser.parse_args()


def select_segments(segments: list[dict[str, Any]], sample_count: int, min_segment_sec: float) -> list[dict[str, Any]]:
	candidates = [
		segment for segment in segments
		if parse_hhmmss(str(segment["end"])) - parse_hhmmss(str(segment["start"])) >= min_segment_sec
	]
	if not candidates:
		candidates = segments
	if sample_count >= len(candidates):
		return candidates
	positions = [0, len(candidates) // 2, len(candidates) - 1]
	selected: list[dict[str, Any]] = []
	for position in positions:
		segment = candidates[position]
		if segment not in selected:
			selected.append(segment)
	while len(selected) < sample_count:
		position = round((len(candidates) - 1) * len(selected) / max(sample_count - 1, 1))
		segment = candidates[position]
		if segment not in selected:
			selected.append(segment)
		else:
			break
	return selected[:sample_count]


def extract_clip(audio_path: Path, temp_root: Path, index: int, segment: dict[str, Any]) -> Path:
	start = parse_hhmmss(str(segment["start"]))
	end = parse_hhmmss(str(segment["end"]))
	duration = max(1.0, min(end - start, 8.0))
	output = temp_root / f"speaker_sample_{index:02d}_{segment['segment_id']}.wav"
	run([
		"ffmpeg",
		"-y",
		"-v",
		"error",
		"-ss",
		f"{start:.3f}",
		"-t",
		f"{duration:.3f}",
		"-i",
		str(audio_path),
		"-ar",
		"16000",
		"-ac",
		"1",
		str(output),
	])
	return output


def similarity_matrix(embeddings: list[np.ndarray]) -> np.ndarray:
	stack = np.vstack(embeddings)
	norms = np.linalg.norm(stack, axis=1, keepdims=True)
	return (stack @ stack.T) / np.maximum(norms @ norms.T, 1e-9)


def parse_hhmmss(value: str) -> float:
	hours, minutes, seconds = value.split(":")
	return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def require_file(path: Path) -> None:
	if not path.exists() or not path.is_file():
		raise FileNotFoundError(path)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	result = subprocess.run(cmd, text=True, capture_output=True)
	if result.returncode != 0:
		raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
	return result


if __name__ == "__main__":
	raise SystemExit(main())
