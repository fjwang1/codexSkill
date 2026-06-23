#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


DISPLAY_PUNCTUATION = "，。！？；：、,.!?;:…“”‘’\"'`（）()《》〈〉【】[]{}"
DISPLAY_PUNCTUATION_TABLE = str.maketrans("", "", DISPLAY_PUNCTUATION)


def main() -> int:
	args = parse_args()
	payload = json.loads(args.segments.read_text(encoding="utf-8"))
	segments = payload.get("segments")
	if not isinstance(segments, list) or not segments:
		raise RuntimeError("segments JSON must contain a non-empty segments list.")
	validate_segments_schema(segments)

	args.output_dir.mkdir(parents=True, exist_ok=True)
	cues = build_cues(segments, args.max_chars_per_cue, args.min_cue_duration)
	report = validate_cues(
		segments=segments,
		cues=cues,
		max_segment_start_delay=args.max_segment_start_delay,
		max_in_segment_gap=args.max_in_segment_gap,
		max_cue_duration=args.max_cue_duration,
		anchor_early_tolerance=args.anchor_early_tolerance,
		anchor_late_tolerance=args.anchor_late_tolerance,
	)

	srt_path = args.output_dir / "zh-CN.voiceover.srt"
	vtt_path = args.output_dir / "zh-CN.voiceover.vtt"
	report_path = args.output_dir / "subtitle-timeline-report.json"
	srt_path.write_text(format_srt(cues), encoding="utf-8")
	vtt_path.write_text(format_vtt(cues), encoding="utf-8")
	report.update({
		"srt_path": str(srt_path),
		"vtt_path": str(vtt_path),
		"cue_count": len(cues),
	})
	report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

	blocking = []
	for key in [
		"segment_start_delay_violations",
		"in_segment_gap_violations",
		"cue_duration_violations",
	]:
		blocking.extend(report[key])
	blocking.extend(report["unambiguous_anchor_early_violations"])
	blocking.extend(report["unambiguous_anchor_late_violations"])
	if blocking:
		raise RuntimeError("subtitle timeline validation failed: " + json.dumps(blocking[:20], ensure_ascii=False))

	print(json.dumps({
		"ok": True,
		"srt_path": str(srt_path),
		"vtt_path": str(vtt_path),
		"report_path": str(report_path),
		"cue_count": len(cues),
		"anchor_ambiguity_count": len(report["anchor_ambiguities"]),
	}, ensure_ascii=False, indent=2))
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate continuous Chinese voiceover subtitles from voiceover-segments.json.")
	parser.add_argument("--segments", required=True, type=Path)
	parser.add_argument("--output-dir", required=True, type=Path)
	parser.add_argument("--max-chars-per-cue", type=int, default=24)
	parser.add_argument("--min-cue-duration", type=float, default=0.75)
	parser.add_argument("--max-cue-duration", type=float, default=8.0)
	parser.add_argument("--max-segment-start-delay", type=float, default=0.8)
	parser.add_argument("--max-in-segment-gap", type=float, default=1.2)
	parser.add_argument("--anchor-early-tolerance", type=float, default=0.8)
	parser.add_argument("--anchor-late-tolerance", type=float, default=0.8)
	return parser.parse_args()


def validate_segments_schema(segments: list[dict[str, Any]]) -> None:
	seen: set[str] = set()
	violations: list[dict[str, Any]] = []
	for index, segment in enumerate(segments):
		if not isinstance(segment, dict):
			violations.append({"index": index, "reason": "segment_not_object"})
			continue
		segment_id = segment.get("segment_id")
		if not isinstance(segment_id, str) or not segment_id.strip():
			violations.append({"index": index, "reason": "missing_or_empty_segment_id", "value": segment_id})
			continue
		if segment_id in seen:
			violations.append({"index": index, "reason": "duplicate_segment_id", "segment_id": segment_id})
		seen.add(segment_id)
	if violations:
		raise RuntimeError("segments schema validation failed: " + json.dumps(violations[:30], ensure_ascii=False))


def build_cues(segments: list[dict[str, Any]], max_chars_per_cue: int, min_cue_duration: float) -> list[dict[str, Any]]:
	cues: list[dict[str, Any]] = []
	for segment in segments:
		cues.extend(build_segment_cues(segment, max_chars_per_cue, min_cue_duration))
	return normalize_cues(cues)


def build_segment_cues(segment: dict[str, Any], max_chars_per_cue: int, min_cue_duration: float) -> list[dict[str, Any]]:
	start = parse_time(segment["start"])
	end = parse_time(segment["end"])
	text = clean_text(str(segment.get("voice_text") or ""))
	if not text:
		return []
	duration = max(0.001, end - start)
	constraints = drop_segment_start_constraints(locate_unique_anchor_constraints(segment, text), segment_start=start)
	chunks = split_text_with_constraints(text, constraints, max_chars_per_cue)
	max_cues = max(1, int(duration / max(0.25, min_cue_duration)))
	chunks = merge_constrained_chunks_to_max_cues(chunks, max_cues)
	return allocate_constrained_chunks(segment_id=str(segment["segment_id"]), chunks=chunks, start=start, end=end)


def split_text(text: str, max_chars_per_cue: int) -> list[str]:
	text = clean_text(text)
	if not text:
		return []
	parts = [part.strip() for part in re.split(r"(?<=[。！？；])|(?<=，)", text) if part.strip()]
	chunks: list[str] = []
	for part in parts:
		if visible_len(part) <= max_chars_per_cue:
			chunks.append(part)
			continue
		chunks.extend(split_long_text(part, max_chars_per_cue))
	return [chunk for chunk in chunks if chunk]


def split_long_text(text: str, max_chars_per_cue: int) -> list[str]:
	chunks: list[str] = []
	current = ""
	for char in text:
		current += char
		if visible_len(current) >= max_chars_per_cue:
			chunks.append(current.strip())
			current = ""
	if current.strip():
		chunks.append(current.strip())
	return chunks


def merge_to_max_cues(chunks: list[str], max_cues: int) -> list[str]:
	if len(chunks) <= max_cues:
		return chunks
	merged = chunks[:]
	while len(merged) > max_cues:
		best_index = min(range(len(merged) - 1), key=lambda index: visible_len(merged[index]) + visible_len(merged[index + 1]))
		merged[best_index:best_index + 2] = [merged[best_index] + merged[best_index + 1]]
	return merged


def split_text_with_constraints(
	text: str,
	constraints: list[dict[str, Any]],
	max_chars_per_cue: int,
) -> list[dict[str, Any]]:
	if not constraints:
		return [{"text": chunk, "min_start": None, "anchor_term": None} for chunk in split_text(text, max_chars_per_cue)]
	constraints_by_index = {int(item["index"]): item for item in constraints}
	split_indices = sorted({0, len(text), *(int(item["index"]) for item in constraints)})
	chunks: list[dict[str, Any]] = []
	for left, right in zip(split_indices, split_indices[1:]):
		piece = text[left:right].strip()
		if not piece:
			continue
		constraint = constraints_by_index.get(left)
		piece_chunks = split_text(piece, max_chars_per_cue)
		for index, chunk in enumerate(piece_chunks):
			chunks.append({
				"text": chunk,
				"min_start": float(constraint["min_start"]) if constraint and index == 0 else None,
				"anchor_term": str(constraint["term"]) if constraint and index == 0 else None,
			})
	return chunks


def merge_constrained_chunks_to_max_cues(chunks: list[dict[str, Any]], max_cues: int) -> list[dict[str, Any]]:
	if len(chunks) <= max_cues:
		return chunks
	merged = [chunk.copy() for chunk in chunks]
	while len(merged) > max_cues:
		candidates = [
			index
			for index in range(len(merged) - 1)
			if merged[index + 1].get("min_start") is None
		]
		if not candidates:
			break
		best_index = min(
			candidates,
			key=lambda index: visible_len(str(merged[index]["text"])) + visible_len(str(merged[index + 1]["text"])),
		)
		merged[best_index]["text"] = str(merged[best_index]["text"]) + str(merged[best_index + 1]["text"])
		del merged[best_index + 1]
	return merged


def allocate_constrained_chunks(segment_id: str, chunks: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
	if not chunks:
		return []
	cues: list[dict[str, Any]] = []
	index = 0
	cursor_time = start
	while index < len(chunks):
		min_start = chunks[index].get("min_start")
		if min_start is not None and float(min_start) > cursor_time:
			if cues:
				cues[-1]["end"] = float(min_start)
			cursor_time = float(min_start)
		next_anchor_index = next(
			(
				candidate
				for candidate in range(index + 1, len(chunks))
				if chunks[candidate].get("min_start") is not None
			),
			None,
		)
		window_end = end if next_anchor_index is None else max(cursor_time, min(end, float(chunks[next_anchor_index]["min_start"])))
		group_end = len(chunks) if next_anchor_index is None else next_anchor_index
		cues.extend(allocate_chunk_group(segment_id=segment_id, chunks=chunks[index:group_end], start=cursor_time, end=window_end))
		cursor_time = window_end
		index = group_end
	return cues


def allocate_chunk_group(segment_id: str, chunks: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
	if not chunks:
		return []
	duration = max(0.25 * len(chunks), end - start)
	weights = [max(1, visible_len(str(chunk["text"]))) for chunk in chunks]
	total = sum(weights)
	cues: list[dict[str, Any]] = []
	cursor = start
	for index, chunk in enumerate(chunks):
		if index == len(chunks) - 1:
			chunk_end = end
		else:
			chunk_end = start + duration * sum(weights[: index + 1]) / total
		chunk_end = max(cursor + 0.25, min(end, chunk_end))
		cues.append({
			"segment_id": segment_id,
			"start": cursor,
			"end": chunk_end,
			"text": str(chunk["text"]),
		})
		cursor = chunk_end
	return cues


def locate_unique_anchor_constraints(segment: dict[str, Any], text: str) -> list[dict[str, Any]]:
	constraints: list[dict[str, Any]] = []
	sync_priority = str(segment.get("sync_priority") or "normal")
	for check in segment.get("anchor_checks") or []:
		for term in [str(item) for item in check.get("target_terms") or []]:
			if not term or not is_specific_anchor_term(term, force_specific=sync_priority == "must_align"):
				continue
			positions = [match.start() for match in re.finditer(re.escape(term), text)]
			if len(positions) != 1:
				continue
			constraints.append({
				"term": term,
				"index": positions[0],
				"end_index": positions[0] + len(term),
				"min_start": float(check.get("forbidden_before_sec") or check.get("effective_not_before_sec") or check.get("source_anchor_start_sec") or 0.0),
			})
	return prefer_longest_non_overlapping_constraints(collapse_same_anchor_time_constraints(constraints))


def collapse_same_anchor_time_constraints(constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Keep one subtitle scheduling constraint per anchor time.

	A single hard anchor often lists several target terms that share the same source
	time window, for example "second episode", "Chinese Dream" and "24 hours".
	Scheduling every term independently forces 0.25s micro-cues. The audio/segment
	manifest still carries every target term; subtitle layout only needs one cue
	start constraint for that shared anchor time.
	"""
	by_time: dict[float, dict[str, Any]] = {}
	for item in constraints:
		key = round(float(item["min_start"]), 3)
		existing = by_time.get(key)
		if existing is None:
			by_time[key] = item
			continue
		item_index = int(item["index"])
		existing_index = int(existing["index"])
		item_len = int(item["end_index"]) - item_index
		existing_len = int(existing["end_index"]) - existing_index
		if item_index < existing_index or (item_index == existing_index and item_len > existing_len):
			by_time[key] = item
	return sorted(by_time.values(), key=lambda item: (float(item["min_start"]), int(item["index"])))


def drop_segment_start_constraints(
	constraints: list[dict[str, Any]],
	*,
	segment_start: float,
) -> list[dict[str, Any]]:
	"""Do not force subtitle splits when the whole segment already starts at the anchor.

	The anchor timing contract is still enforced by the voiceover segment start/end and
	anchor checks. For subtitle layout, a start-aligned anchor can be displayed in the
	first normal cue. Keeping a term-level split at the same start time creates 0.25s
	prefix cues such as "在" or "但", which are technically timed but poor subtitles.
	"""
	return [item for item in constraints if float(item["min_start"]) > segment_start + 0.05]


def prefer_longest_non_overlapping_constraints(constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
	if not constraints:
		return []
	items = sorted(constraints, key=lambda item: (int(item["index"]), -(int(item["end_index"]) - int(item["index"])), float(item["min_start"])))
	filtered: list[dict[str, Any]] = []
	for item in items:
		item_start = int(item["index"])
		item_end = int(item["end_index"])
		overlap_index = None
		for index, existing in enumerate(filtered):
			existing_start = int(existing["index"])
			existing_end = int(existing["end_index"])
			if item_start < existing_end and item_end > existing_start:
				overlap_index = index
				break
		if overlap_index is None:
			filtered.append(item)
			continue
		existing = filtered[overlap_index]
		item_len = item_end - item_start
		existing_len = int(existing["end_index"]) - int(existing["index"])
		if item_len > existing_len or (item_len == existing_len and float(item["min_start"]) < float(existing["min_start"])):
			filtered[overlap_index] = item
	return sorted(filtered, key=lambda item: int(item["index"]))


def allocate_chunks(segment_id: str, chunks: list[str], start: float, end: float) -> list[dict[str, Any]]:
	if not chunks:
		return []
	duration = max(0.001, end - start)
	weights = [max(1, visible_len(chunk)) for chunk in chunks]
	total = sum(weights)
	cues: list[dict[str, Any]] = []
	cursor = start
	for index, chunk in enumerate(chunks):
		if index == len(chunks) - 1:
			chunk_end = end
		else:
			chunk_end = start + duration * sum(weights[: index + 1]) / total
		chunk_end = max(cursor + 0.25, min(end, chunk_end))
		cues.append({
			"segment_id": segment_id,
			"start": cursor,
			"end": chunk_end,
			"text": chunk,
		})
		cursor = chunk_end
	return cues


def normalize_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
	normalized: list[dict[str, Any]] = []
	previous_end = 0.0
	for cue in cues:
		start = max(previous_end, float(cue["start"]))
		end = max(start + 0.25, float(cue["end"]))
		text = wrap_subtitle_text(str(cue["text"]))
		if not text:
			continue
		normalized.append({
			"segment_id": cue["segment_id"],
			"start": round(start, 3),
			"end": round(end, 3),
			"text": text,
		})
		previous_end = end
	return merge_tiny_cues(normalized)


def merge_tiny_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
	result: list[dict[str, Any]] = []
	index = 0
	while index < len(cues):
		cue = cues[index].copy()
		duration = float(cue["end"]) - float(cue["start"])
		text = str(cue["text"]).replace("\n", "")
		is_tiny = duration < 0.5 or visible_len(text) <= 1
		if is_tiny and index + 1 < len(cues) and cues[index + 1]["segment_id"] == cue["segment_id"]:
			next_cue = cues[index + 1].copy()
			next_cue["start"] = cue["start"]
			next_cue["text"] = strip_display_punctuation(str(cue["text"]).replace("\n", "") + str(next_cue["text"]).replace("\n", ""))
			result.append(next_cue)
			index += 2
			continue
		if is_tiny and result and result[-1]["segment_id"] == cue["segment_id"]:
			result[-1]["end"] = cue["end"]
			result[-1]["text"] = strip_display_punctuation(str(result[-1]["text"]).replace("\n", "") + str(cue["text"]).replace("\n", ""))
			index += 1
			continue
		result.append(cue)
		index += 1
	return result


def validate_cues(
	*,
	segments: list[dict[str, Any]],
	cues: list[dict[str, Any]],
	max_segment_start_delay: float,
	max_in_segment_gap: float,
	max_cue_duration: float,
	anchor_early_tolerance: float,
	anchor_late_tolerance: float,
) -> dict[str, Any]:
	cues_by_segment: dict[str, list[dict[str, Any]]] = {}
	for cue in cues:
		cues_by_segment.setdefault(str(cue["segment_id"]), []).append(cue)

	start_delay_violations: list[dict[str, Any]] = []
	gap_violations: list[dict[str, Any]] = []
	duration_violations: list[dict[str, Any]] = []
	anchor_violations: list[dict[str, Any]] = []
	anchor_late_violations: list[dict[str, Any]] = []
	anchor_ambiguities: list[dict[str, Any]] = []

	for segment in segments:
		segment_id = str(segment["segment_id"])
		text = clean_text(str(segment.get("voice_text") or ""))
		if not text:
			continue
		start = parse_time(segment["start"])
		end = parse_time(segment["end"])
		segment_cues = cues_by_segment.get(segment_id, [])
		if not segment_cues:
			start_delay_violations.append({"segment_id": segment_id, "reason": "no cues"})
			continue
		first_delay = float(segment_cues[0]["start"]) - start
		if first_delay > max_segment_start_delay:
			start_delay_violations.append({
				"segment_id": segment_id,
				"segment_start_sec": round(start, 3),
				"first_cue_start_sec": round(float(segment_cues[0]["start"]), 3),
				"delay_sec": round(first_delay, 3),
			})
		for previous, current in zip(segment_cues, segment_cues[1:]):
			gap = float(current["start"]) - float(previous["end"])
			if gap > max_in_segment_gap:
				gap_violations.append({
					"segment_id": segment_id,
					"gap_start_sec": round(float(previous["end"]), 3),
					"gap_end_sec": round(float(current["start"]), 3),
					"gap_sec": round(gap, 3),
				})
		last_gap = end - float(segment_cues[-1]["end"])
		if last_gap > max_in_segment_gap:
			gap_violations.append({
				"segment_id": segment_id,
				"gap_start_sec": round(float(segment_cues[-1]["end"]), 3),
				"gap_end_sec": round(end, 3),
				"gap_sec": round(last_gap, 3),
			})
		for cue in segment_cues:
			duration = float(cue["end"]) - float(cue["start"])
			if duration > max_cue_duration:
				duration_violations.append({
					"segment_id": segment_id,
					"cue_start_sec": cue["start"],
					"cue_end_sec": cue["end"],
					"duration_sec": round(duration, 3),
				})
		check_anchor_cues(
			segment=segment,
			segment_cues=segment_cues,
			anchor_early_tolerance=anchor_early_tolerance,
			anchor_late_tolerance=anchor_late_tolerance,
			anchor_violations=anchor_violations,
			anchor_late_violations=anchor_late_violations,
			anchor_ambiguities=anchor_ambiguities,
		)

	return {
		"decision": "PASS" if not start_delay_violations and not gap_violations and not duration_violations and not anchor_violations and not anchor_late_violations else "FAIL",
		"segment_start_delay_violations": start_delay_violations,
		"in_segment_gap_violations": gap_violations,
		"cue_duration_violations": duration_violations,
		"unambiguous_anchor_early_violations": anchor_violations,
		"unambiguous_anchor_late_violations": anchor_late_violations,
		"anchor_ambiguities": anchor_ambiguities,
	}


def check_anchor_cues(
	*,
	segment: dict[str, Any],
	segment_cues: list[dict[str, Any]],
	anchor_early_tolerance: float,
	anchor_late_tolerance: float,
	anchor_violations: list[dict[str, Any]],
	anchor_late_violations: list[dict[str, Any]],
	anchor_ambiguities: list[dict[str, Any]],
) -> None:
	text = clean_text(str(segment.get("voice_text") or ""))
	for check in segment.get("anchor_checks") or []:
		for term in [str(item) for item in check.get("target_terms") or []]:
			if not term or term not in text:
				continue
			positions = [match.start() for match in re.finditer(re.escape(term), text)]
			if len(positions) != 1:
				anchor_ambiguities.append({
					"segment_id": str(segment["segment_id"]),
					"term": term,
					"occurrence_count": len(positions),
					"reason": "ambiguous target term; do not schedule subtitles by blind term search",
				})
	for constraint in locate_unique_anchor_constraints(segment, text):
		term = str(constraint["term"])
		cue = next((item for item in segment_cues if term in str(item["text"]).replace("\n", "")), None)
		if cue is None:
			continue
		forbidden = float(constraint["min_start"])
		if float(cue["start"]) < forbidden - anchor_early_tolerance:
			anchor_violations.append({
				"segment_id": str(segment["segment_id"]),
				"term": term,
				"cue_start_sec": round(float(cue["start"]), 3),
				"forbidden_before_sec": round(forbidden, 3),
				"early_by_sec": round(forbidden - float(cue["start"]), 3),
			})
		if float(cue["start"]) > forbidden + anchor_late_tolerance:
			anchor_late_violations.append({
				"segment_id": str(segment["segment_id"]),
				"term": term,
				"cue_start_sec": round(float(cue["start"]), 3),
				"expected_anchor_sec": round(forbidden, 3),
				"late_by_sec": round(float(cue["start"]) - forbidden, 3),
			})


def is_specific_anchor_term(term: str, *, force_specific: bool = False) -> bool:
	compact = re.sub(r"\s+", "", term)
	if not compact:
		return False
	if force_specific:
		return True
	generic_terms = {
		"中国",
		"美国",
		"德国",
		"日本",
		"电动车",
		"燃油车",
		"汽车",
		"车企",
		"电池",
		"充电",
	}
	if compact in generic_terms:
		return False
	if re.search(r"[A-Za-z0-9%]", compact):
		return True
	if re.search(r"百分|美元|亿元|亿美元|万|亿|年|英寸|公里|厘米|合资|贷款|关税|补贴", compact):
		return True
	return len(compact) >= 3


def clean_text(text: str) -> str:
	return re.sub(r"\s+", " ", text).strip()


def visible_len(text: str) -> int:
	return len(re.sub(r"\s+", "", text))


def wrap_subtitle_text(text: str) -> str:
	text = clean_text(text)
	if visible_len(text) <= 22:
		return strip_display_punctuation(text)
	lines: list[str] = []
	current = ""
	for char in text:
		current += char
		if visible_len(current) >= 18 and char in "，。；、 ":
			lines.append(current.strip())
			current = ""
	if current.strip():
		lines.append(current.strip())
	lines = [strip_display_punctuation(line) for line in lines if strip_display_punctuation(line)]
	if len(lines) <= 2:
		return "\n".join(lines)
	return "".join(lines[:-1]) + "\n" + lines[-1]


def strip_display_punctuation(text: str) -> str:
	"""Remove punctuation from on-screen subtitles while preserving TTS text upstream."""
	return clean_text(text.translate(DISPLAY_PUNCTUATION_TABLE))


def parse_time(value: str | int | float) -> float:
	if isinstance(value, int | float):
		return float(value)
	parts = str(value).split(":")
	if len(parts) == 3:
		return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
	if len(parts) == 2:
		return int(parts[0]) * 60 + float(parts[1])
	return float(value)


def format_srt_time(value: float) -> str:
	total_millis = max(0, int(round(value * 1000)))
	hours, remainder = divmod(total_millis, 3_600_000)
	minutes, remainder = divmod(remainder, 60_000)
	seconds, millis = divmod(remainder, 1000)
	return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def format_vtt_time(value: float) -> str:
	return format_srt_time(value).replace(",", ".")


def format_srt(cues: list[dict[str, Any]]) -> str:
	lines: list[str] = []
	for index, cue in enumerate(cues, start=1):
		lines.extend([
			str(index),
			f"{format_srt_time(float(cue['start']))} --> {format_srt_time(float(cue['end']))}",
			str(cue["text"]),
			"",
		])
	return "\n".join(lines)


def format_vtt(cues: list[dict[str, Any]]) -> str:
	lines = ["WEBVTT", ""]
	for cue in cues:
		lines.extend([
			f"{format_vtt_time(float(cue['start']))} --> {format_vtt_time(float(cue['end']))}",
			str(cue["text"]),
			"",
		])
	return "\n".join(lines)


if __name__ == "__main__":
	raise SystemExit(main())
