#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "worldview-china-podcast-cold-open-detection.v1"

START_CUE_PATTERNS = [
	re.compile(r"\bbefore we (start|begin)\b", re.I),
	re.compile(r"\b(start|begin) (today'?s|the) (podcast|conversation|episode)\b", re.I),
	re.compile(r"\bwelcome (to|back)\b", re.I),
	re.compile(r"\blet'?s (start|begin|get started)\b", re.I),
	re.compile(r"\btoday'?s (podcast|episode|conversation)\b", re.I),
]

CTA_PATTERNS = [
	re.compile(r"\bsubscribe\b", re.I),
	re.compile(r"\bfollow us\b", re.I),
	re.compile(r"\bspotify\b", re.I),
	re.compile(r"\bthis channel\b", re.I),
]

VISUAL_COLD_OPEN_PATTERNS = [
	re.compile(r"\bconversation starts in\b", re.I),
	re.compile(r"\bpodcast starts in\b", re.I),
	re.compile(r"\bepisode starts in\b", re.I),
	re.compile(r"\bstarts in\b", re.I),
	re.compile(r"\bcoming up\b", re.I),
	re.compile(r"\bin this episode\b", re.I),
	re.compile(r"\bfirst revolution\b", re.I),
	re.compile(r"\bno\.?\s*2\b", re.I),
	re.compile(r"\bnumber\s+two\b", re.I),
]

FRAGMENT_START_PATTERNS = [
	re.compile(r"^\s*(and|but|or|so|because|therefore|however|then)\b", re.I),
	re.compile(r"^\s*(number\s+two|no\.?\s*2|the\s+third|third\s+is|second\s+is)\b", re.I),
	re.compile(r"^\s*(right|yeah|yes|okay|ok)[,.\s]+", re.I),
]


@dataclass
class Segment:
	index: int
	start: float
	end: float
	text: str
	raw: dict[str, Any]


def _default_run_paths(run_dir: Path) -> tuple[Path, Path, Path]:
	video = run_dir / "02-source-capture" / "youtube-media" / "source.mp4"
	transcript = run_dir / "02-source-capture" / "source_transcript.en.json"
	out = run_dir / "02-source-cold-open-detection"
	return video, transcript, out


def _load_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


def _load_segments(path: Path) -> tuple[list[Segment], Any]:
	data = _load_json(path)
	if isinstance(data, dict) and isinstance(data.get("transcript"), dict):
		raw_segments = data["transcript"].get("segments", [])
	elif isinstance(data, dict):
		raw_segments = data.get("segments", [])
	elif isinstance(data, list):
		raw_segments = data
	else:
		raw_segments = []
	segments: list[Segment] = []
	for pos, raw in enumerate(raw_segments):
		if not isinstance(raw, dict):
			continue
		start = raw.get("start", raw.get("source_start_sec", raw.get("start_sec")))
		end = raw.get("end", raw.get("source_end_sec", raw.get("end_sec")))
		text = raw.get("text", raw.get("source_text", ""))
		try:
			start_f = float(start)
			end_f = float(end)
		except (TypeError, ValueError):
			continue
		if not str(text).strip():
			continue
		index = int(raw.get("index", raw.get("segment_index", pos + 1)))
		segments.append(Segment(index=index, start=start_f, end=end_f, text=str(text), raw=raw))
	return segments, data


def _clean_text(text: str) -> str:
	text = text.lower()
	text = re.sub(r"[^a-z0-9\s]+", " ", text)
	text = re.sub(r"\s+", " ", text).strip()
	return text


def _contains_any(patterns: list[re.Pattern[str]], text: str) -> bool:
	return any(pattern.search(text) for pattern in patterns)


def _find_text_boundary(segments: list[Segment], max_scan_sec: float) -> dict[str, Any]:
	for seg in segments:
		if seg.start > max_scan_sec:
			break
		text = seg.text
		if _contains_any(START_CUE_PATTERNS, text):
			return {
				"found": True,
				"boundary_sec": seg.start,
				"segment_index": seg.index,
				"segment_start_sec": seg.start,
				"segment_end_sec": seg.end,
				"text": text,
				"reason": "start_cue_segment",
			}
	return {"found": False}


def _find_opening_duplicate_matches(
	segments: list[Segment],
	candidate_end_sec: float | None,
	max_opening_sec: float,
	min_later_sec: float,
) -> list[dict[str, Any]]:
	opening_end = candidate_end_sec if candidate_end_sec is not None else max_opening_sec
	early = [s for s in segments if s.start < opening_end and len(_clean_text(s.text)) >= 80]
	later = [s for s in segments if s.start >= min_later_sec and len(_clean_text(s.text)) >= 80]
	matches: list[dict[str, Any]] = []
	for left in early:
		left_clean = _clean_text(left.text)
		best: tuple[float, Segment | None] = (0.0, None)
		for right in later:
			right_clean = _clean_text(right.text)
			ratio = SequenceMatcher(None, left_clean[:600], right_clean[:900]).ratio()
			if ratio > best[0]:
				best = (ratio, right)
		if best[1] is not None and best[0] >= 0.42:
			matches.append({
				"opening_segment_index": left.index,
				"opening_start_sec": left.start,
				"later_segment_index": best[1].index,
				"later_start_sec": best[1].start,
				"similarity": round(best[0], 3),
				"opening_excerpt": left.text[:180],
				"later_excerpt": best[1].text[:180],
			})
	return matches


def _load_visual_review(path: Path | None) -> dict[str, Any] | None:
	if not path:
		return None
	data = _load_json(path)
	if not isinstance(data, dict):
		raise ValueError(f"visual review must be a JSON object: {path}")
	return data


def _score_visual_review(data: dict[str, Any] | None) -> dict[str, Any]:
	if data is None:
		return {"present": False, "score": 0, "observations": [], "boundary_sec": None}
	observations = data.get("observations", [])
	if not isinstance(observations, list):
		observations = []
	matched: list[dict[str, Any]] = []
	for obs in observations:
		if not isinstance(obs, dict):
			continue
		text = str(obs.get("text", ""))
		if _contains_any(VISUAL_COLD_OPEN_PATTERNS, text):
			matched.append(obs)
	conf = str(data.get("confidence", "")).lower()
	cold_open_present = bool(data.get("cold_open_present"))
	boundary = data.get("cold_open_end_sec")
	try:
		boundary_f = float(boundary) if boundary is not None else None
	except (TypeError, ValueError):
		boundary_f = None
	score = len(matched)
	if cold_open_present:
		score += 2
	if conf in {"high", "very_high", "certain"}:
		score += 2
	if boundary_f is not None:
		score += 1
	return {
		"present": cold_open_present or bool(matched),
		"score": score,
		"matched_observations": matched,
		"observation_count": len(observations),
		"boundary_sec": boundary_f,
		"confidence_label": conf or None,
	}


def _extract_frames(video: Path, output_dir: Path, max_scan_sec: float, step_sec: float, extra_times: list[float]) -> list[dict[str, Any]]:
	frames_dir = output_dir / "frames"
	frames_dir.mkdir(parents=True, exist_ok=True)
	times = set()
	t = 0.0
	while t <= max_scan_sec:
		times.add(round(t, 2))
		t += step_sec
	for item in extra_times:
		if 0 <= item <= max_scan_sec + 10:
			times.add(round(item, 2))
	frames = []
	for sec in sorted(times):
		safe_time = f"{sec:08.2f}".replace(".", "_")
		name = f"frame_{safe_time}.jpg"
		out = frames_dir / name
		cmd = [
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-ss",
			f"{sec:.3f}",
			"-i",
			str(video),
			"-frames:v",
			"1",
			"-q:v",
			"2",
			str(out),
		]
		try:
			subprocess.run(cmd, check=True)
			frames.append({"time_sec": sec, "path": str(out)})
		except (OSError, subprocess.CalledProcessError) as exc:
			frames.append({"time_sec": sec, "path": str(out), "error": str(exc)})
	return frames


def _boundary_aligns_with_segment_start(segments: list[Segment], boundary: float, tolerance: float) -> dict[str, Any]:
	for seg in segments:
		if abs(seg.start - boundary) <= tolerance:
			return {
				"aligned": True,
				"segment_index": seg.index,
				"segment_start_sec": seg.start,
				"first_text_after_cut": seg.text,
			}
		if seg.start < boundary < seg.end:
			return {
				"aligned": False,
				"overlaps_segment": True,
				"segment_index": seg.index,
				"segment_start_sec": seg.start,
				"segment_end_sec": seg.end,
				"text": seg.text,
			}
	return {"aligned": False, "overlaps_segment": False}


def _fragment_risk(text: str) -> bool:
	return any(pattern.search(text) for pattern in FRAGMENT_START_PATTERNS)


def _decide(
	segments: list[Segment],
	text_boundary: dict[str, Any],
	visual: dict[str, Any],
	duplicate_matches: list[dict[str, Any]],
	min_cut_sec: float,
	max_cut_sec: float,
	boundary_tolerance_sec: float,
) -> dict[str, Any]:
	text_boundary_sec = text_boundary.get("boundary_sec") if text_boundary.get("found") else None
	visual_boundary_sec = visual.get("boundary_sec")
	candidate: float | None = None
	candidate_source = None
	if visual_boundary_sec is not None and text_boundary_sec is not None and abs(visual_boundary_sec - text_boundary_sec) <= 20:
		candidate = float(text_boundary_sec)
		candidate_source = "visual_and_text_agree"
	elif visual_boundary_sec is not None and visual.get("score", 0) >= 5:
		candidate = float(visual_boundary_sec)
		candidate_source = "high_confidence_visual_review"
	elif text_boundary_sec is not None:
		candidate = float(text_boundary_sec)
		candidate_source = "text_only_boundary"

	if candidate is None:
		return {
			"status": "NO_CONFIDENT_CUT",
			"recommended_action": "do_not_cut",
			"confidence": 0.0,
			"reason": "no_boundary_candidate",
		}

	alignment = _boundary_aligns_with_segment_start(segments, candidate, boundary_tolerance_sec)
	first_text = str(alignment.get("first_text_after_cut", ""))
	if not (min_cut_sec <= candidate <= max_cut_sec):
		return {
			"status": "NO_CONFIDENT_CUT",
			"recommended_action": "do_not_cut",
			"confidence": 0.0,
			"reason": "candidate_outside_allowed_opening_range",
			"candidate_end_sec": candidate,
			"allowed_range_sec": [min_cut_sec, max_cut_sec],
		}
	if alignment.get("overlaps_segment"):
		return {
			"status": "NO_CONFIDENT_CUT",
			"recommended_action": "do_not_cut",
			"confidence": 0.0,
			"reason": "candidate_splits_transcript_segment",
			"candidate_end_sec": candidate,
			"boundary_alignment": alignment,
		}

	visual_strong = bool(visual.get("present")) and int(visual.get("score", 0)) >= 4
	text_strong = bool(text_boundary.get("found"))
	dup_strong = len(duplicate_matches) >= 1
	not_fragment = bool(first_text) and not _fragment_risk(first_text)
	score = 0.0
	if visual_strong:
		score += 0.45
	if text_strong:
		score += 0.25
	if dup_strong:
		score += 0.15
	if alignment.get("aligned"):
		score += 0.10
	if not_fragment:
		score += 0.05
	score = min(score, 0.99)

	if visual_strong and text_strong and alignment.get("aligned") and not_fragment:
		status = "CUT_CONFIRMED"
		action = "cut"
		reason = "visual_text_boundary_and_opening_validation_pass"
	elif text_strong and dup_strong:
		status = "NEEDS_VISUAL_REVIEW"
		action = "visual_review"
		reason = "text_and_duplicate_signals_need_visual_confirmation"
	else:
		status = "NO_CONFIDENT_CUT"
		action = "do_not_cut"
		reason = "insufficient_visual_confirmation"

	return {
		"status": status,
		"recommended_action": action,
		"confidence": round(score, 3),
		"reason": reason,
		"candidate_source": candidate_source,
		"cut": {
			"start_sec": 0.0,
			"end_sec": round(candidate, 3),
			"duration_sec": round(candidate, 3),
		} if status == "CUT_CONFIRMED" else None,
		"candidate_end_sec": round(candidate, 3),
		"boundary_alignment": alignment,
	}


def _write_report(result: dict[str, Any], path: Path) -> None:
	lines = [
		"# Cold Open Detection Report",
		"",
		f"- status: {result['status']}",
		f"- recommended_action: {result['recommended_action']}",
		f"- confidence: {result['confidence']}",
		f"- reason: {result.get('reason')}",
	]
	cut = result.get("cut")
	if cut:
		lines.append(f"- cut: {cut['start_sec']:.3f}-{cut['end_sec']:.3f}s")
	candidate = result.get("candidate_end_sec")
	if candidate is not None and not cut:
		lines.append(f"- candidate_end_sec: {candidate}")
	lines.extend(["", "## Evidence", ""])
	lines.append(f"- text_boundary: {json.dumps(result.get('evidence', {}).get('text_boundary'), ensure_ascii=False)}")
	lines.append(f"- visual: {json.dumps(result.get('evidence', {}).get('visual'), ensure_ascii=False)}")
	lines.append(f"- duplicate_match_count: {len(result.get('evidence', {}).get('duplicate_matches', []))}")
	lines.append("")
	lines.append("## Rule")
	lines.append("")
	lines.append("Do not cut unless status is CUT_CONFIRMED. NEEDS_VISUAL_REVIEW requires direct frame inspection or OCR evidence before rerunning detection.")
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
	parser = argparse.ArgumentParser(description="Conservatively detect podcast cold-open teaser ranges.")
	parser.add_argument("--run-dir", type=Path)
	parser.add_argument("--source-video", type=Path)
	parser.add_argument("--transcript-json", type=Path)
	parser.add_argument("--output-dir", type=Path)
	parser.add_argument("--visual-review-json", type=Path)
	parser.add_argument("--max-scan-sec", type=float, default=300.0)
	parser.add_argument("--min-cut-sec", type=float, default=15.0)
	parser.add_argument("--max-cut-sec", type=float, default=300.0)
	parser.add_argument("--boundary-tolerance-sec", type=float, default=0.35)
	parser.add_argument("--extract-frames", action="store_true")
	parser.add_argument("--frame-step-sec", type=float, default=10.0)
	args = parser.parse_args()

	if args.run_dir:
		default_video, default_transcript, default_out = _default_run_paths(args.run_dir)
		source_video = args.source_video or default_video
		transcript_json = args.transcript_json or default_transcript
		output_dir = args.output_dir or default_out
	else:
		if not args.source_video or not args.transcript_json:
			parser.error("either --run-dir or both --source-video and --transcript-json are required")
		source_video = args.source_video
		transcript_json = args.transcript_json
		output_dir = args.output_dir or Path.cwd() / "cold-open-detection"

	output_dir.mkdir(parents=True, exist_ok=True)
	segments, _ = _load_segments(transcript_json)
	if not segments:
		raise SystemExit(f"no transcript segments found: {transcript_json}")

	text_boundary = _find_text_boundary(segments, args.max_scan_sec)
	visual_review = _load_visual_review(args.visual_review_json)
	visual = _score_visual_review(visual_review)
	boundary_for_dupes = visual.get("boundary_sec") or (text_boundary.get("boundary_sec") if text_boundary.get("found") else None)
	duplicate_matches = _find_opening_duplicate_matches(
		segments,
		float(boundary_for_dupes) if boundary_for_dupes is not None and math.isfinite(float(boundary_for_dupes)) else None,
		args.max_scan_sec,
		min_later_sec=max(args.max_scan_sec, 300.0),
	)
	decision = _decide(
		segments,
		text_boundary,
		visual,
		duplicate_matches,
		args.min_cut_sec,
		args.max_cut_sec,
		args.boundary_tolerance_sec,
	)
	frames: list[dict[str, Any]] = []
	if args.extract_frames:
		extra_times = []
		if decision.get("candidate_end_sec") is not None:
			c = float(decision["candidate_end_sec"])
			extra_times.extend([max(0.0, c - 20), max(0.0, c - 10), c, c + 1, c + 5])
		for obs in visual.get("matched_observations", []):
			try:
				extra_times.append(float(obs.get("time_sec")))
			except (TypeError, ValueError):
				pass
		frames = _extract_frames(source_video, output_dir, args.max_scan_sec, args.frame_step_sec, extra_times)

	result = {
		"schema_version": SCHEMA_VERSION,
		"status": decision["status"],
		"recommended_action": decision["recommended_action"],
		"confidence": decision["confidence"],
		"reason": decision.get("reason"),
		"source_video": str(source_video),
		"transcript_json": str(transcript_json),
		"cut": decision.get("cut"),
		"candidate_end_sec": decision.get("candidate_end_sec"),
		"candidate_source": decision.get("candidate_source"),
		"boundary_alignment": decision.get("boundary_alignment"),
		"evidence": {
			"text_boundary": text_boundary,
			"visual": visual,
			"duplicate_matches": duplicate_matches,
			"frames": frames,
		},
		"policy": {
			"cut_requires_status": "CUT_CONFIRMED",
			"transcript_only_cut_allowed": False,
			"partial_teaser_cut_allowed": False,
		},
	}
	result_path = output_dir / "cold_open_detection_result.json"
	report_path = output_dir / "cold_open_detection_report.md"
	result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	_write_report(result, report_path)
	print(json.dumps({"status": result["status"], "result": str(result_path), "report": str(report_path)}, ensure_ascii=False))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
