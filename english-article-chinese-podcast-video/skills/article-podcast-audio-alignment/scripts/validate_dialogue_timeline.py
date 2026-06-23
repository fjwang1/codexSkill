#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


PUNCT_RE = re.compile(r"[\s,，。.!！?？;；:：、'\"“”‘’（）()《》<>\\[\\]{}—…·-]+")


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


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


def _content_len(text: Any) -> int:
	return len(PUNCT_RE.sub("", str(text or "")))


def _check_monotonic(items: list[dict[str, Any]], label: str, duration: float) -> list[str]:
	failures: list[str] = []
	previous_start = -0.001
	previous_end = -0.001
	for index, item in enumerate(items, start=1):
		try:
			start = float(item["start_sec"])
			end = float(item["end_sec"])
		except (KeyError, TypeError, ValueError):
			failures.append(f"{label} {index} has invalid start/end")
			continue
		if start < -0.001 or end > duration + 0.25:
			failures.append(f"{label} {index} outside audio duration: {start:.3f}-{end:.3f}, duration={duration:.3f}")
		if start >= end:
			failures.append(f"{label} {index} start >= end: {start:.3f}-{end:.3f}")
		if start < previous_start - 0.05:
			failures.append(f"{label} {index} start is not monotonic: {start:.3f} < {previous_start:.3f}")
		if end < previous_end - 0.25:
			failures.append(f"{label} {index} end moved backwards: {end:.3f} < {previous_end:.3f}")
		previous_start = max(previous_start, start)
		previous_end = max(previous_end, end)
	return failures


def _alignment_ratio(item: dict[str, Any]) -> float | None:
	try:
		return float(item["asr_matched_char_ratio"])
	except (KeyError, TypeError, ValueError):
		return None


def _check_completion(
	turns: list[dict[str, Any]],
	cues: list[dict[str, Any]],
	*,
	min_turn_matched_char_ratio: float,
	max_trailing_low_confidence_turns: int,
	min_turn_sec_per_char: float,
	min_cue_sec_per_char: float,
) -> list[str]:
	failures: list[str] = []
	trailing_low_turns = 0
	for turn in reversed(turns):
		ratio = _alignment_ratio(turn)
		confidence = str(turn.get("alignment_confidence") or "").lower()
		text_len = _content_len(turn.get("tts_text") or turn.get("text"))
		is_low = confidence == "low" or (ratio is not None and ratio < min_turn_matched_char_ratio)
		if text_len >= 20 and is_low:
			trailing_low_turns += 1
			continue
		break
	if trailing_low_turns > max_trailing_low_confidence_turns:
		failures.append(
			f"trailing low-confidence turn run too long: {trailing_low_turns} > {max_trailing_low_confidence_turns}"
		)

	for turn in turns:
		text_len = _content_len(turn.get("tts_text") or turn.get("text"))
		if text_len < 20:
			continue
		ratio = _alignment_ratio(turn)
		if ratio is not None and ratio < min_turn_matched_char_ratio:
			failures.append(
				f"turn {turn.get('turn_index')} matched char ratio too low: {ratio:.3f} < {min_turn_matched_char_ratio:.3f}"
			)
		try:
			duration = float(turn["end_sec"]) - float(turn["start_sec"])
		except (KeyError, TypeError, ValueError):
			continue
		min_duration = max(0.5, min(5.0, text_len * min_turn_sec_per_char))
		if duration < min_duration:
			failures.append(
				f"turn {turn.get('turn_index')} duration too short for text: {duration:.3f}s < {min_duration:.3f}s, chars={text_len}"
			)

	for cue in cues:
		text_len = _content_len(cue.get("text"))
		if text_len < 12:
			continue
		try:
			duration = float(cue["end_sec"]) - float(cue["start_sec"])
		except (KeyError, TypeError, ValueError):
			continue
		min_duration = max(0.25, min(1.2, text_len * min_cue_sec_per_char))
		if duration < min_duration:
			failures.append(
				f"cue {cue.get('cue_index')} duration too short for text: {duration:.3f}s < {min_duration:.3f}s, chars={text_len}"
			)
	return failures


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Validate article podcast dialogue_timeline.json.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--min-matched-script-ratio", type=float, default=0.90)
	parser.add_argument("--min-asr-word-probability", type=float, default=0.75)
	parser.add_argument("--max-low-asr-word-ratio", type=float, default=0.25)
	parser.add_argument("--min-turn-matched-char-ratio", type=float, default=0.0)
	parser.add_argument("--max-trailing-low-confidence-turns", type=int, default=1)
	parser.add_argument("--min-turn-sec-per-char", type=float, default=0.055)
	parser.add_argument("--min-cue-sec-per-char", type=float, default=0.045)
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	audio_path = project_dir / "audio" / "final_podcast.wav"
	manifest_path = project_dir / "audio" / "audio_manifest.json"
	timeline_path = project_dir / "audio" / "dialogue_timeline.json"
	assert audio_path.exists(), f"Missing {audio_path}"
	assert manifest_path.exists(), f"Missing {manifest_path}"
	assert timeline_path.exists(), f"Missing {timeline_path}"

	manifest = _read_json(manifest_path)
	timeline = _read_json(timeline_path)
	duration = _duration(audio_path)
	turns = list(timeline.get("turns") or [])
	cues = list(timeline.get("cues") or [])
	failures: list[str] = []

	if timeline.get("audio_sha256") != _sha256(audio_path):
		failures.append("audio_sha256 does not match audio/final_podcast.wav")
	if timeline.get("audio_manifest_sha256") != _sha256(manifest_path):
		failures.append("audio_manifest_sha256 does not match audio/audio_manifest.json")
	if abs(float(timeline.get("duration_sec") or 0) - duration) > 0.5:
		failures.append(f"duration_sec mismatch: timeline={timeline.get('duration_sec')} audio={duration:.3f}")
	if len(turns) != int(manifest.get("turn_count") or 0):
		failures.append(f"turn count mismatch: timeline={len(turns)} manifest={manifest.get('turn_count')}")
	if not cues:
		failures.append("timeline has no cues")
	try:
		matched_ratio = float(timeline.get("asr_summary", {}).get("matched_script_ratio"))
	except (TypeError, ValueError):
		matched_ratio = -1.0
	if matched_ratio < args.min_matched_script_ratio:
		failures.append(f"ASR/script matched_script_ratio too low: {matched_ratio:.3f} < {args.min_matched_script_ratio:.3f}")
	try:
		avg_word_probability = float(timeline.get("asr_summary", {}).get("avg_word_probability"))
	except (TypeError, ValueError):
		avg_word_probability = -1.0
	if avg_word_probability < args.min_asr_word_probability:
		failures.append(
			f"ASR avg_word_probability too low: {avg_word_probability:.3f} < {args.min_asr_word_probability:.3f}"
		)
	try:
		low_word_ratio = float(timeline.get("asr_summary", {}).get("low_word_probability_ratio"))
	except (TypeError, ValueError):
		low_word_ratio = 1.0
	if low_word_ratio > args.max_low_asr_word_ratio:
		failures.append(
			f"ASR low_word_probability_ratio too high: {low_word_ratio:.3f} > {args.max_low_asr_word_ratio:.3f}"
		)
	failures.extend(_check_monotonic(turns, "turn", duration))
	failures.extend(_check_monotonic(cues, "cue", duration))
	failures.extend(
		_check_completion(
			turns,
			cues,
			min_turn_matched_char_ratio=args.min_turn_matched_char_ratio,
			max_trailing_low_confidence_turns=args.max_trailing_low_confidence_turns,
			min_turn_sec_per_char=args.min_turn_sec_per_char,
			min_cue_sec_per_char=args.min_cue_sec_per_char,
		)
	)
	turn_indexes = {int(turn["turn_index"]) for turn in turns if "turn_index" in turn}
	for cue in cues:
		try:
			turn_index = int(cue["turn_index"])
		except (KeyError, TypeError, ValueError):
			failures.append(f"cue missing turn_index: {cue}")
			continue
		if turn_index not in turn_indexes:
			failures.append(f"cue maps to missing turn_index={turn_index}")

	result = {
		"ok": not failures,
		"failures": failures,
		"turn_count": len(turns),
		"cue_count": len(cues),
		"duration_sec": round(duration, 3),
		"matched_script_ratio": round(matched_ratio, 3),
		"avg_word_probability": round(avg_word_probability, 3),
		"low_word_probability_ratio": round(low_word_ratio, 3),
	}
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if not failures else 2


if __name__ == "__main__":
	raise SystemExit(main())
