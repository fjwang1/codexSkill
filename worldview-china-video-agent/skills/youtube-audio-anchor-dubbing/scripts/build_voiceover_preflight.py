from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any


PRODUCTION_PHRASES = (
	"没有新的有效口播信息",
	"可配音信息",
	"自然停顿",
	"过渡停顿",
	"保留为",
	"无需口播",
	"让画面",
)

INCOMPLETE_TRAILING_CHARS = "，、：；,"
INCOMPLETE_TRAILING_PHRASES = (
	"根据",
	"按照",
	"虽然",
	"尽管",
	"直到",
	"期间",
	"如果",
	"因为",
	"但是",
	"但",
	"而",
	"他的梦想",
	"她的梦想",
	"他们的梦想",
)

PUNCTUATION_RE = re.compile(r"[\s,，。.!！?？;；:：、\"'“”‘’()（）\[\]【】《》<>-]+")
LATIN_MULTIWORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.+/-]*(?:\s+[A-Za-z][A-Za-z0-9&.+/-]*)+")
CJK_RE = re.compile(r"[\u3400-\u9fff]")


def main() -> None:
	args = _parse_args()
	segments_path = args.segments.expanduser().resolve()
	output_dir = args.output_dir.expanduser().resolve()
	_require_file(segments_path)
	payload = json.loads(segments_path.read_text(encoding="utf-8"))
	segments = payload.get("segments")
	if not isinstance(segments, list) or not segments:
		raise ValueError("voiceover file must contain a non-empty segments list.")
	output_dir.mkdir(parents=True, exist_ok=True)

	sha256 = _sha256_file(segments_path)
	source_coverage = _build_source_coverage_report(
		payload=payload,
		segments=segments,
		source_transcript_json=args.source_transcript_json,
		min_gap_sec=args.source_coverage_min_gap_sec,
		coverage_slack_sec=args.source_coverage_slack_sec,
		caption_merge_gap_sec=args.caption_merge_gap_sec,
	)
	common = _build_common_preflight(
		payload=payload,
		segments=segments,
		segments_path=segments_path,
		sha256=sha256,
		source_coverage=source_coverage,
	)
	for name in ("voiceover-segments-preflight", "content-window-preflight", "anchor-text-position-preflight", "source-coverage-preflight"):
		report = dict(common)
		report["preflight_name"] = name
		(output_dir / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build deterministic 04 voiceover preflight reports for the current segments JSON.")
	parser.add_argument("--segments", type=Path, required=True)
	parser.add_argument("--output-dir", type=Path, required=True)
	parser.add_argument("--source-transcript-json", type=Path)
	parser.add_argument("--source-coverage-min-gap-sec", type=float, default=2.0)
	parser.add_argument("--source-coverage-slack-sec", type=float, default=0.8)
	parser.add_argument("--caption-merge-gap-sec", type=float, default=1.0)
	return parser.parse_args()


def _build_common_preflight(
	*,
	payload: dict[str, Any],
	segments: list[dict[str, Any]],
	segments_path: Path,
	sha256: str,
	source_coverage: dict[str, Any],
) -> dict[str, Any]:
	missing_anchor_checks: list[dict[str, Any]] = []
	invalid_anchor_checks: list[dict[str, Any]] = []
	blocking_untranslated_source_text: list[dict[str, Any]] = []
	blocking_low_information_or_asr_noise: list[dict[str, Any]] = []
	duplicate_materialized_source_anchor_ids: list[dict[str, Any]] = []
	timeline_overlaps: list[dict[str, Any]] = []
	early_risk_terms: list[dict[str, Any]] = []
	duplicate_segment_ids: list[dict[str, Any]] = []
	anchor_owner: dict[str, str] = {}
	seen_ids: set[str] = set()
	previous: dict[str, Any] | None = None

	for segment in segments:
		segment_id = str(segment.get("segment_id") or "")
		if not segment_id or segment_id in seen_ids:
			duplicate_segment_ids.append({"segment_id": segment_id, "reason": "empty_or_duplicate_segment_id"})
		seen_ids.add(segment_id)
		start_sec = _segment_start_sec(segment)
		end_sec = _segment_end_sec(segment)
		if previous is not None and start_sec < _segment_end_sec(previous) - 0.05:
			timeline_overlaps.append(
				{
					"previous_segment_id": previous.get("segment_id"),
					"segment_id": segment_id,
					"previous_end_sec": round(_segment_end_sec(previous), 3),
					"start_sec": round(start_sec, 3),
				}
			)
		previous = segment
		voice_text = str(segment.get("voice_text") or "").strip()
		anchor_checks = segment.get("anchor_checks")
		if str(segment.get("sync_priority") or "") == "must_align" and not anchor_checks:
			missing_anchor_checks.append({"segment_id": segment_id, "reason": "must_align_without_anchor_checks"})
		if anchor_checks is not None and not isinstance(anchor_checks, list):
			invalid_anchor_checks.append({"segment_id": segment_id, "reason": "anchor_checks_not_list"})
			anchor_checks = []
		for check in anchor_checks or []:
			if not isinstance(check, dict):
				invalid_anchor_checks.append({"segment_id": segment_id, "reason": "anchor_check_not_object"})
				continue
			_check_anchor_fields(segment_id, check, invalid_anchor_checks)
			source_anchor_id = check.get("source_anchor_id")
			if source_anchor_id:
				source_anchor_id = str(source_anchor_id)
				owner = anchor_owner.get(source_anchor_id)
				if owner and str(segment.get("sync_priority") or "") == "must_align":
					duplicate_materialized_source_anchor_ids.append(
						{"source_anchor_id": source_anchor_id, "first_segment_id": owner, "duplicate_segment_id": segment_id}
					)
				else:
					anchor_owner[source_anchor_id] = segment_id
			_check_early_target_terms(segment, check, early_risk_terms)
		_untranslated_scan(segment, voice_text, blocking_untranslated_source_text)
		_low_information_scan(segment, voice_text, blocking_low_information_or_asr_noise)

	blocking_unlisted_high_risk_terms: list[dict[str, Any]] = []
	over_window_content_risks: list[dict[str, Any]] = []
	decision = "PASS"
	for values in (
		missing_anchor_checks,
		invalid_anchor_checks,
		blocking_unlisted_high_risk_terms,
		blocking_untranslated_source_text,
		blocking_low_information_or_asr_noise,
		over_window_content_risks,
		duplicate_materialized_source_anchor_ids,
		timeline_overlaps,
		early_risk_terms,
		duplicate_segment_ids,
		source_coverage.get("source_coverage_gaps") or [],
	):
		if values:
			decision = "FAIL"
			break
	return {
		"schema_version": "voiceover-preflight.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"decision": decision,
		"attempt": payload.get("attempt"),
		"voiceover_segments_path": str(segments_path),
		"voiceover_segments_sha256": sha256,
		"segment_count": len(segments),
		"must_align_count": sum(1 for segment in segments if str(segment.get("sync_priority") or "") == "must_align"),
		"non_voice_ranges_count": len(payload.get("non_voice_ranges") or []),
		"duplicate_segment_ids": duplicate_segment_ids,
		"missing_anchor_checks": missing_anchor_checks,
		"invalid_anchor_checks": invalid_anchor_checks,
		"blocking_unlisted_high_risk_terms": blocking_unlisted_high_risk_terms,
		"blocking_untranslated_source_text": blocking_untranslated_source_text,
		"blocking_low_information_or_asr_noise": blocking_low_information_or_asr_noise,
		"over_window_content_risks": over_window_content_risks,
		"duplicate_materialized_source_anchor_ids": duplicate_materialized_source_anchor_ids,
		"timeline_overlaps": timeline_overlaps,
		"early_risk_terms": early_risk_terms,
		"source_coverage": source_coverage,
	}


def _build_source_coverage_report(
	*,
	payload: dict[str, Any],
	segments: list[dict[str, Any]],
	source_transcript_json: Path | None,
	min_gap_sec: float,
	coverage_slack_sec: float,
	caption_merge_gap_sec: float,
) -> dict[str, Any]:
	if source_transcript_json is None:
		return {
			"decision": "SKIPPED",
			"reason": "source_transcript_json_not_provided",
			"source_coverage_gaps": [],
			"caption_window_count": 0,
		}
	source_path = source_transcript_json.expanduser().resolve()
	_require_file(source_path)
	source_payload = json.loads(source_path.read_text(encoding="utf-8"))
	caption_intervals = _caption_intervals_from_payload(source_payload)
	caption_windows = _merge_caption_intervals(caption_intervals, caption_merge_gap_sec)
	coverage_intervals = _coverage_intervals_from_payload(payload, segments, coverage_slack_sec)
	gaps: list[dict[str, Any]] = []
	for window in caption_windows:
		uncovered_ranges = _subtract_intervals(window["start_sec"], window["end_sec"], coverage_intervals)
		for start_sec, end_sec in uncovered_ranges:
			duration_sec = end_sec - start_sec
			if duration_sec < min_gap_sec:
				continue
			gaps.append(
				{
					"start_sec": round(start_sec, 3),
					"end_sec": round(end_sec, 3),
					"duration_sec": round(duration_sec, 3),
					"caption_window_start_sec": round(window["start_sec"], 3),
					"caption_window_end_sec": round(window["end_sec"], 3),
					"text_excerpt": _caption_excerpt(caption_intervals, start_sec, end_sec),
					"reason": "source_caption_window_not_covered_by_voiceover_or_non_voice_range",
				}
			)
	return {
		"decision": "FAIL" if gaps else "PASS",
		"source_transcript_json": str(source_path),
		"source_transcript_sha256": _sha256_file(source_path),
		"caption_window_count": len(caption_windows),
		"coverage_interval_count": len(coverage_intervals),
		"min_gap_sec": min_gap_sec,
		"coverage_slack_sec": coverage_slack_sec,
		"caption_merge_gap_sec": caption_merge_gap_sec,
		"source_coverage_gaps": gaps,
	}


def _caption_intervals_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
	transcript = payload.get("transcript")
	if not isinstance(transcript, dict):
		raise ValueError("source transcript JSON must contain transcript object.")
	segments = transcript.get("segments")
	if not isinstance(segments, list):
		raise ValueError("source transcript JSON must contain transcript.segments list.")
	intervals: list[dict[str, Any]] = []
	for item in segments:
		if not isinstance(item, dict):
			continue
		text = str(item.get("text") or "").strip()
		if not _has_caption_content(text):
			continue
		start = item.get("start")
		duration = item.get("duration")
		if not isinstance(start, int | float) or not isinstance(duration, int | float):
			continue
		end = float(start) + float(duration)
		if end <= float(start):
			continue
		intervals.append({"start_sec": float(start), "end_sec": end, "text": text})
	intervals.sort(key=lambda item: (item["start_sec"], item["end_sec"]))
	return intervals


def _has_caption_content(text: str) -> bool:
	plain = re.sub(r">>|\s+", " ", text).strip()
	if not plain:
		return False
	return bool(re.search(r"[A-Za-z0-9\u3400-\u9fff]", plain))


def _merge_caption_intervals(intervals: list[dict[str, Any]], merge_gap_sec: float) -> list[dict[str, Any]]:
	windows: list[dict[str, Any]] = []
	for interval in intervals:
		if not windows or interval["start_sec"] > windows[-1]["end_sec"] + merge_gap_sec:
			windows.append({"start_sec": interval["start_sec"], "end_sec": interval["end_sec"]})
		else:
			windows[-1]["end_sec"] = max(windows[-1]["end_sec"], interval["end_sec"])
	return windows


def _coverage_intervals_from_payload(payload: dict[str, Any], segments: list[dict[str, Any]], slack_sec: float) -> list[tuple[float, float]]:
	intervals: list[tuple[float, float]] = []
	for segment in segments:
		intervals.append((_segment_start_sec(segment) - slack_sec, _segment_end_sec(segment) + slack_sec))
	for item in payload.get("non_voice_ranges") or []:
		if not isinstance(item, dict):
			continue
		start = item.get("start_sec")
		end = item.get("end_sec")
		if not isinstance(start, int | float):
			start = _parse_hhmmss(str(item.get("start")))
		if not isinstance(end, int | float):
			end = _parse_hhmmss(str(item.get("end")))
		intervals.append((float(start) - slack_sec, float(end) + slack_sec))
	intervals.sort()
	merged: list[tuple[float, float]] = []
	for start, end in intervals:
		if end <= start:
			continue
		if not merged or start > merged[-1][1]:
			merged.append((start, end))
		else:
			merged[-1] = (merged[-1][0], max(merged[-1][1], end))
	return merged


def _subtract_intervals(start_sec: float, end_sec: float, coverage_intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
	uncovered: list[tuple[float, float]] = []
	cursor = start_sec
	for cover_start, cover_end in coverage_intervals:
		if cover_end <= cursor:
			continue
		if cover_start >= end_sec:
			break
		if cover_start > cursor:
			uncovered.append((cursor, min(cover_start, end_sec)))
		cursor = max(cursor, cover_end)
		if cursor >= end_sec:
			break
	if cursor < end_sec:
		uncovered.append((cursor, end_sec))
	return uncovered


def _caption_excerpt(intervals: list[dict[str, Any]], start_sec: float, end_sec: float) -> str:
	texts = [
		str(interval["text"]).strip()
		for interval in intervals
		if interval["end_sec"] > start_sec and interval["start_sec"] < end_sec
	]
	excerpt = " ".join(texts)
	excerpt = re.sub(r"\s+", " ", excerpt).strip()
	if len(excerpt) > 280:
		return excerpt[:277].rstrip() + "..."
	return excerpt


def _check_anchor_fields(segment_id: str, check: dict[str, Any], invalid_anchor_checks: list[dict[str, Any]]) -> None:
	required = ("source_anchor_start_sec", "effective_not_before_sec", "target_terms")
	missing = [key for key in required if key not in check]
	if missing:
		invalid_anchor_checks.append({"segment_id": segment_id, "reason": "missing_anchor_check_fields", "missing": missing})
	target_terms = check.get("target_terms")
	if "target_terms" in check and (not isinstance(target_terms, list) or not target_terms):
		invalid_anchor_checks.append({"segment_id": segment_id, "reason": "target_terms_empty_or_not_list"})


def _check_early_target_terms(segment: dict[str, Any], check: dict[str, Any], early_risk_terms: list[dict[str, Any]]) -> None:
	voice_text = str(segment.get("voice_text") or "")
	start_sec = _segment_start_sec(segment)
	end_sec = _segment_end_sec(segment)
	target_terms = check.get("target_terms")
	effective_not_before = check.get("effective_not_before_sec")
	if not isinstance(target_terms, list) or not isinstance(effective_not_before, int | float):
		return
	plain = PUNCTUATION_RE.sub("", voice_text)
	if not plain:
		return
	for term in target_terms:
		term_text = PUNCTUATION_RE.sub("", str(term))
		if not term_text:
			continue
		index = plain.find(term_text)
		if index < 0:
			continue
		estimated_sec = start_sec + (end_sec - start_sec) * (index / max(len(plain), 1))
		if estimated_sec < float(effective_not_before) - 0.8:
			early_risk_terms.append(
				{
					"segment_id": segment.get("segment_id"),
					"term": str(term),
					"estimated_sec": round(estimated_sec, 3),
					"effective_not_before_sec": round(float(effective_not_before), 3),
				}
			)


def _untranslated_scan(segment: dict[str, Any], voice_text: str, output: list[dict[str, Any]]) -> None:
	for match in LATIN_MULTIWORD_RE.finditer(voice_text):
		output.append(
			{
				"segment_id": segment.get("segment_id"),
				"matched_text": match.group(0),
				"reason": "continuous_latin_phrase_requires_allowlist_or_translation",
			}
		)


def _low_information_scan(segment: dict[str, Any], voice_text: str, output: list[dict[str, Any]]) -> None:
	segment_id = segment.get("segment_id")
	source_text = str(segment.get("source_text") or "")
	duration_sec = _segment_end_sec(segment) - _segment_start_sec(segment)
	anchor_checks = segment.get("anchor_checks")
	has_anchor = isinstance(anchor_checks, list) and bool(anchor_checks)
	stripped = PUNCTUATION_RE.sub("", voice_text)
	cjk_count = len(CJK_RE.findall(stripped))
	for phrase in PRODUCTION_PHRASES:
		if phrase in voice_text:
			output.append({"segment_id": segment_id, "reason": "production_or_pause_instruction_in_voice_text", "matched_text": phrase})
	if _looks_incomplete_viewer_utterance(voice_text):
		output.append(
			{
				"segment_id": segment_id,
				"reason": "incomplete_viewer_utterance",
				"duration_sec": round(duration_sec, 3),
				"voice_text": voice_text,
				"source_text": source_text,
			}
		)
	if has_anchor:
		return
	source_tokens = _source_tokens(source_text)
	if duration_sec <= 2.0 and cjk_count <= 5:
		output.append(
			{
				"segment_id": segment_id,
				"reason": "short_micro_segment_without_anchor_or_complete_proposition",
				"duration_sec": round(duration_sec, 3),
				"voice_text": voice_text,
				"source_text": source_text,
			}
		)
	elif source_tokens and len(source_tokens) <= 3 and cjk_count <= 8 and not _source_has_content_noun(source_tokens):
		output.append(
			{
				"segment_id": segment_id,
				"reason": "source_asr_fragment_without_text_authority",
				"duration_sec": round(duration_sec, 3),
				"voice_text": voice_text,
				"source_text": source_text,
			}
		)


def _looks_incomplete_viewer_utterance(voice_text: str) -> bool:
	text = voice_text.strip()
	if not text:
		return True
	if text[-1] in INCOMPLETE_TRAILING_CHARS:
		return True
	plain = PUNCTUATION_RE.sub("", text)
	if not plain:
		return True
	return plain in INCOMPLETE_TRAILING_PHRASES


def _source_tokens(source_text: str) -> list[str]:
	return re.findall(r"[A-Za-z0-9']+", source_text.lower())


def _source_has_content_noun(tokens: list[str]) -> bool:
	stop = {
		"a",
		"an",
		"and",
		"are",
		"be",
		"but",
		"for",
		"i",
		"in",
		"is",
		"it",
		"it's",
		"of",
		"oh",
		"or",
		"so",
		"the",
		"to",
		"we",
		"you",
	}
	return any(token not in stop for token in tokens)


def _segment_start_sec(segment: dict[str, Any]) -> float:
	value = segment.get("start_sec")
	if isinstance(value, int | float):
		return float(value)
	return _parse_hhmmss(str(segment["start"]))


def _segment_end_sec(segment: dict[str, Any]) -> float:
	value = segment.get("end_sec")
	if isinstance(value, int | float):
		return float(value)
	return _parse_hhmmss(str(segment["end"]))


def _parse_hhmmss(value: str) -> float:
	parts = value.split(":")
	if len(parts) != 3:
		raise ValueError(f"Expected HH:MM:SS, got {value!r}.")
	hours, minutes, seconds = parts
	return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _sha256_file(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _require_file(path: Path) -> None:
	if not path.exists() or not path.is_file():
		raise FileNotFoundError(path)


if __name__ == "__main__":
	main()
