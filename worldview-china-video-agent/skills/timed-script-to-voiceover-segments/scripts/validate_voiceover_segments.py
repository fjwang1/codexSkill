#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


TIME_RE = re.compile(r"^(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})(?:\.(?P<ms>\d{1,3}))?$")
PUNCTUATION_RE = re.compile(r"[\s，。！？、；：“”‘’（）《》—…,.!?;:\"'()\[\]{}-]")
MAX_SEGMENT_SECONDS = 30.0
MAX_SENTENCE_SECONDS = 30.0
CHARS_PER_SECOND = 4.2


def parse_time(value: str) -> float:
	match = TIME_RE.match(value)
	if match is None:
		raise ValueError(f"invalid time: {value!r}")
	hours = int(match.group("h"))
	minutes = int(match.group("m"))
	seconds = int(match.group("s"))
	milliseconds = match.group("ms") or "0"
	return hours * 3600 + minutes * 60 + seconds + int(milliseconds.ljust(3, "0")) / 1000


def require_string(obj: dict[str, Any], key: str, index: int) -> str:
	value = obj.get(key)
	if not isinstance(value, str) or not value.strip():
		raise ValueError(f"segments[{index}].{key} must be a non-empty string")
	return value


def count_speech_chars(text: str) -> int:
	return len(PUNCTUATION_RE.sub("", text))


def main() -> int:
	if len(sys.argv) != 2:
		print("usage: validate_voiceover_segments.py path/to/voiceover-segments.json", file=sys.stderr)
		return 2

	path = Path(sys.argv[1]).expanduser()
	data = json.loads(path.read_text(encoding="utf-8"))
	if not isinstance(data, dict):
		raise ValueError("top-level JSON must be an object")
	if data.get("schema_version") != "voiceover-segments.v1":
		raise ValueError('schema_version must be "voiceover-segments.v1"')

	segments = data.get("segments")
	if not isinstance(segments, list) or not segments:
		raise ValueError("segments must be a non-empty list")

	previous_end = -1.0
	warnings: list[str] = []

	for index, segment in enumerate(segments):
		if not isinstance(segment, dict):
			raise ValueError(f"segments[{index}] must be an object")

		segment_id = require_string(segment, "segment_id", index)
		start_text = require_string(segment, "start", index)
		end_text = require_string(segment, "end", index)
		voice_text = require_string(segment, "voice_text", index)

		start = parse_time(start_text)
		end = parse_time(end_text)
		if start < previous_end:
			raise ValueError(f"{segment_id} overlaps previous segment")
		if end <= start:
			raise ValueError(f"{segment_id} must have end > start")
		if end - start > MAX_SEGMENT_SECONDS + 0.75:
			raise ValueError(f"{segment_id} is longer than {MAX_SEGMENT_SECONDS:.0f}s and must be split")

		target_duration = segment.get("target_duration_sec")
		if not isinstance(target_duration, int | float):
			raise ValueError(f"{segment_id}.target_duration_sec must be numeric")
		if abs(float(target_duration) - (end - start)) > 0.75:
			warnings.append(f"{segment_id}: target_duration_sec differs from start/end by >0.75s")
		if float(target_duration) > MAX_SEGMENT_SECONDS + 0.75:
			raise ValueError(f"{segment_id}.target_duration_sec is longer than {MAX_SEGMENT_SECONDS:.0f}s")

		lines = [line.strip() for line in voice_text.splitlines() if line.strip()]
		if not lines:
			raise ValueError(f"{segment_id}.voice_text must contain at least one spoken line")
		max_sentence_estimate = 0.0
		for line_index, line in enumerate(lines, start=1):
			line_estimate = count_speech_chars(line) / CHARS_PER_SECOND
			max_sentence_estimate = max(max_sentence_estimate, line_estimate)
			if line_estimate > MAX_SENTENCE_SECONDS:
				raise ValueError(
					f"{segment_id}.voice_text line {line_index} is longer than {MAX_SENTENCE_SECONDS:.0f}s and must be split"
				)
			if line.endswith("、"):
				warnings.append(f"{segment_id}: voice_text line {line_index} ends with an enumeration comma and should be re-split")
			if re.search(r"\\n", line):
				warnings.append(f"{segment_id}: voice_text line {line_index} contains a literal \\\\n")

		line_count = segment.get("line_count")
		if isinstance(line_count, int) and line_count != len(lines):
			warnings.append(f"{segment_id}: line_count={line_count} but voice_text has {len(lines)} non-empty lines")

		recorded_max_sentence = segment.get("max_sentence_estimated_sec")
		if isinstance(recorded_max_sentence, int | float) and abs(float(recorded_max_sentence) - max_sentence_estimate) > 0.75:
			warnings.append(f"{segment_id}: max_sentence_estimated_sec differs from voice_text line estimate by >0.75s")

		if len(lines) == 1 and count_speech_chars(voice_text) / CHARS_PER_SECOND > 15:
			warnings.append(f"{segment_id}: long voice_text has no internal line break")

		estimated_speech = segment.get("estimated_speech_sec")
		if isinstance(estimated_speech, int | float) and estimated_speech > (end - start) * 1.05:
			fit = segment.get("timing_fit")
			if fit not in {"too_long", "needs_split", "needs_review"}:
				warnings.append(f"{segment_id}: estimated speech is long but timing_fit={fit!r}")

		if re.search(r"[A-Za-z]{30,}", voice_text):
			warnings.append(f"{segment_id}: possible long foreign-language residue")

		previous_end = end

	print(f"OK: {len(segments)} segments, last_end={previous_end:.3f}s")
	for warning in warnings:
		print(f"WARNING: {warning}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
