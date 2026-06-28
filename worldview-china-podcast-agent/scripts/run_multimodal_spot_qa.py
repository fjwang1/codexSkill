#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_MIN_SAMPLES = 20
DEFAULT_MAX_SAMPLES = 24
SAMPLE_CONTEXT_BEFORE_SEC = 4.0
SAMPLE_CONTEXT_AFTER_SEC = 6.0
SAMPLE_FRAME_END_MARGIN_SEC = 0.75
REQUIRED_CRITERIA = [
	"visual_audio_semantic_alignment",
	"subtitle_audio_timing",
	"subtitle_text_segmentation",
	"voice_identity_consistency",
	"speaker_switch_coherence",
	"video_motion_integrity",
]
PASS_VALUES = {"PASS", "WARN", "NA"}
FAIL_VALUES = {"FAIL", "UNKNOWN", ""}
ANCHOR_RE = re.compile(r"[A-Za-z]|\d|[一二三四五六七八九十百千万亿]+|[·：:《》]")


def _read_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _duration(path: Path) -> float:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		str(path),
	])
	return float(result.stdout.strip())


def _text_for_cue(cue: dict[str, Any]) -> str:
	return str(cue.get("display_text") or cue.get("text") or "").strip()


def _cue_start(cue: dict[str, Any]) -> float:
	return float(cue.get("start_sec") or cue.get("start") or 0.0)


def _cue_end(cue: dict[str, Any]) -> float:
	return float(cue.get("end_sec") or cue.get("end") or _cue_start(cue))


def _sample_time_for_cue(cue: dict[str, Any], subtitle_time_offset_sec: float, final_duration_sec: float) -> float:
	start = _cue_start(cue) + subtitle_time_offset_sec
	end = _cue_end(cue) + subtitle_time_offset_sec
	if end > start:
		value = start + min(0.6, max(0.1, (end - start) * 0.35))
	else:
		value = start
	return min(max(0.0, value), max(0.0, final_duration_sec - SAMPLE_FRAME_END_MARGIN_SEC))


def _nearest_turn(turns: list[dict[str, Any]], audio_time_sec: float) -> dict[str, Any] | None:
	for turn in turns:
		start = float(turn.get("start_sec") or turn.get("audio_start") or 0.0)
		end = float(turn.get("end_sec") or turn.get("audio_end") or start)
		if start <= audio_time_sec <= end:
			return turn
	if not turns:
		return None
	return min(turns, key=lambda item: abs(float(item.get("start_sec") or 0.0) - audio_time_sec))


def _turn_for_cue(cue: dict[str, Any], turns: list[dict[str, Any]], audio_time_sec: float) -> dict[str, Any] | None:
	source_turn_id = str(cue.get("source_turn_id") or cue.get("turn_id") or "").strip()
	if source_turn_id:
		for turn in turns:
			if str(turn.get("turn_id") or "").strip() == source_turn_id:
				return turn
	source_turn_index = cue.get("source_turn_index", cue.get("turn_index"))
	if source_turn_index is not None:
		try:
			source_turn_index_int = int(source_turn_index)
		except (TypeError, ValueError):
			source_turn_index_int = None
		if source_turn_index_int is not None:
			for turn in turns:
				try:
					turn_index = int(turn.get("turn_index"))
				except (TypeError, ValueError):
					continue
				if turn_index == source_turn_index_int:
					return turn
	return _nearest_turn(turns, audio_time_sec)


def _reason_for_cue(cue: dict[str, Any], previous_speaker: str | None, turn: dict[str, Any] | None) -> str:
	text = _text_for_cue(cue)
	if previous_speaker is not None and turn is not None and str(turn.get("speaker") or "") != previous_speaker:
		return "speaker_switch"
	if ANCHOR_RE.search(text):
		return "semantic_anchor"
	return "timeline_coverage"


def _dedupe_candidates(candidates: list[dict[str, Any]], min_gap_sec: float = 18.0) -> list[dict[str, Any]]:
	selected: list[dict[str, Any]] = []
	for candidate in sorted(candidates, key=lambda item: (item["priority"], item["sample_time_sec"])):
		if any(abs(candidate["sample_time_sec"] - existing["sample_time_sec"]) < min_gap_sec for existing in selected):
			continue
		selected.append(candidate)
	return sorted(selected, key=lambda item: item["sample_time_sec"])


def _append_sample_candidate(
	selected: list[dict[str, Any]],
	candidate: dict[str, Any] | None,
	max_samples: int,
	min_gap_sec: float,
) -> bool:
	if candidate is None:
		return False
	if any(item.get("cue_index") == candidate.get("cue_index") for item in selected):
		return False
	if any(abs(float(candidate["sample_time_sec"]) - float(item["sample_time_sec"])) < min_gap_sec for item in selected):
		return False
	if len(selected) >= max_samples:
		return False
	selected.append(dict(candidate))
	return True


def _nearest_candidate(
	candidates: list[dict[str, Any]],
	target_sec: float,
	selected: list[dict[str, Any]],
) -> dict[str, Any] | None:
	selected_cues = {item.get("cue_index") for item in selected}
	available = [
		item
		for item in candidates
		if item.get("cue_index") not in selected_cues
	]
	if not available:
		return None
	return min(
		available,
		key=lambda item: (
			abs(float(item["sample_time_sec"]) - target_sec),
			int(item.get("priority") or 0),
		),
	)


def _select_global_samples(candidates: list[dict[str, Any]], final_duration: float, min_samples: int, max_samples: int) -> list[dict[str, Any]]:
	assert max_samples >= min_samples >= 1, "sample count bounds are invalid"
	selected: list[dict[str, Any]] = []
	dynamic_gap_sec = min(8.0, max(1.0, final_duration / max(1, max_samples) * 0.5))
	semantic_gap_sec = min(18.0, max(1.0, final_duration / max(1, max_samples) * 0.9))
	opening = min(candidates, key=lambda item: float(item["sample_time_sec"])) if candidates else None
	ending = max(candidates, key=lambda item: float(item["sample_time_sec"])) if candidates else None
	_append_sample_candidate(selected, opening, max_samples, min_gap_sec=0.0)
	_append_sample_candidate(selected, ending, max_samples, min_gap_sec=0.0)
	coverage_count = max_samples
	if coverage_count > 1:
		for index in range(coverage_count):
			target = index * max(0.0, final_duration - SAMPLE_FRAME_END_MARGIN_SEC) / (coverage_count - 1)
			_append_sample_candidate(
				selected,
				_nearest_candidate(candidates, target, selected),
				max_samples,
				min_gap_sec=dynamic_gap_sec,
			)
	for reason, limit in (("speaker_switch", max_samples // 3), ("semantic_anchor", max_samples), ("timeline_coverage", max_samples)):
		added = 0
		for candidate in sorted(
			(item for item in candidates if item.get("reason") == reason),
			key=lambda item: (float(item["sample_time_sec"]), int(item.get("priority") or 0)),
		):
			if len(selected) >= max_samples:
				break
			if reason == "speaker_switch" and added >= limit:
				break
			if _append_sample_candidate(selected, candidate, max_samples, min_gap_sec=semantic_gap_sec):
				added += 1
		if len(selected) >= min_samples:
			break
	while len(selected) < min_samples and len(selected) < max_samples:
		target = len(selected) * max(0.0, final_duration - SAMPLE_FRAME_END_MARGIN_SEC) / max(1, min_samples - 1)
		candidate = _nearest_candidate(candidates, target, selected)
		if not _append_sample_candidate(selected, candidate, max_samples, min_gap_sec=0.0):
			break
	return sorted(selected, key=lambda item: float(item["sample_time_sec"]))


def _load_retime_module() -> Any:
	path = Path(__file__).with_name("run_turn_retime_video.py")
	spec = importlib.util.spec_from_file_location("worldview_turn_retime_video_for_spot_qa", path)
	assert spec is not None
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	spec.loader.exec_module(module)
	return module


def _run_motion_integrity_gate(run_dir: Path) -> dict[str, Any]:
	final_video = run_dir / "video/final_video.mp4"
	render_manifest_path = run_dir / "video/render_manifest.json"
	if not final_video.exists() or not render_manifest_path.exists():
		return {
			"status": "SKIPPED",
			"reason": "final_video_or_render_manifest_missing",
			"failures": [],
		}
	render_manifest = _read_json(render_manifest_path)
	turn_retime = render_manifest.get("turn_retime") if isinstance(render_manifest.get("turn_retime"), dict) else {}
	retime_plan_value = turn_retime.get("retime_edit_plan")
	if not retime_plan_value:
		return {
			"status": "SKIPPED",
			"reason": "no_turn_retime_plan",
			"failures": [],
		}
	retime_plan_path = Path(str(retime_plan_value))
	if not retime_plan_path.is_absolute():
		retime_plan_path = run_dir / retime_plan_path
	if not retime_plan_path.exists():
		return {
			"status": "FAIL",
			"reason": "retime_plan_missing",
			"retime_edit_plan": str(retime_plan_path),
			"failures": [{"reason": "retime_plan_missing", "retime_edit_plan": str(retime_plan_path)}],
		}
	retime = _load_retime_module()
	plan = _read_json(retime_plan_path)
	check = retime.detect_static_video_range_mismatches(plan, final_video)
	return {
		**check,
		"retime_edit_plan": str(retime_plan_path),
		"final_video": str(final_video),
	}


def _build_sample_plan(run_dir: Path, min_samples: int, max_samples: int) -> dict[str, Any]:
	final_video = run_dir / "video/final_video.mp4"
	final_audio = run_dir / "audio/final_podcast.wav"
	render_manifest_path = run_dir / "video/render_manifest.json"
	subtitle_manifest_path = run_dir / "video/subtitle_manifest.json"
	dialogue_timeline_path = run_dir / "audio/dialogue_timeline.json"
	voice_consistency_path = run_dir / "06d-voice-consistency-qa/voice-consistency-qa-result.json"
	render_manifest = _read_json(render_manifest_path)
	subtitle_manifest = _read_json(subtitle_manifest_path)
	dialogue_timeline = _read_json(dialogue_timeline_path)
	final_duration = _duration(final_video)
	subtitle_time_offset_sec = float(render_manifest.get("subtitle_time_offset_sec") or 0.0)
	cues = list(subtitle_manifest.get("cues") or [])
	turns = list(dialogue_timeline.get("turns") or [])
	candidates: list[dict[str, Any]] = []
	last_speaker: str | None = None
	for index, cue in enumerate(cues):
		cue_audio_time = _cue_start(cue)
		turn = _turn_for_cue(cue, turns, cue_audio_time)
		speaker = str(cue.get("speaker") or turn.get("speaker") if turn else cue.get("speaker") or "")
		reason = _reason_for_cue(cue, last_speaker, turn)
		priority = {"speaker_switch": 0, "semantic_anchor": 1, "timeline_coverage": 3}[reason]
		if index == 0:
			reason = "opening"
			priority = -2
		if index == len(cues) - 1:
			reason = "ending"
			priority = -1
		sample_time_sec = _sample_time_for_cue(cue, subtitle_time_offset_sec, final_duration)
		candidates.append({
			"sample_id": f"sample_{len(candidates) + 1:03d}",
			"priority": priority,
			"reason": reason,
			"sample_time_sec": round(sample_time_sec, 3),
			"audio_time_sec": round(max(0.0, sample_time_sec - subtitle_time_offset_sec), 3),
			"cue_index": cue.get("index", cue.get("cue_index")),
			"cue_text": _text_for_cue(cue),
			"cue_start_sec": round(_cue_start(cue), 3),
			"cue_end_sec": round(_cue_end(cue), 3),
			"turn_index": turn.get("turn_index") if turn else None,
			"speaker": speaker or None,
			"turn_text": str(turn.get("text") or "") if turn else "",
			"cue_source_turn_index": cue.get("source_turn_index"),
			"cue_source_turn_id": cue.get("source_turn_id"),
			"context": {
				"previous_cue_text": _text_for_cue(cues[index - 1]) if index > 0 else "",
				"next_cue_text": _text_for_cue(cues[index + 1]) if index + 1 < len(cues) else "",
			},
		})
		if speaker:
			last_speaker = speaker
	selected = _select_global_samples(candidates, final_duration, min_samples, max_samples)
	for index, sample in enumerate(selected, start=1):
		sample["sample_id"] = f"sample_{index:03d}"
		sample["audio_context_start_sec"] = round(max(0.0, sample["sample_time_sec"] - SAMPLE_CONTEXT_BEFORE_SEC), 3)
		sample["audio_context_end_sec"] = round(min(final_duration, sample["sample_time_sec"] + SAMPLE_CONTEXT_AFTER_SEC), 3)
	input_files = {
		"final_video": final_video,
		"final_audio": final_audio,
		"render_manifest": render_manifest_path,
		"subtitle_manifest": subtitle_manifest_path,
		"dialogue_timeline": dialogue_timeline_path,
		"voice_consistency": voice_consistency_path,
	}
	return {
		"schema_version": "worldview-china-multimodal-spot-qa-package.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"run_dir": str(run_dir),
		"policy": {
			"min_samples": min_samples,
			"max_samples": max_samples,
			"required_criteria": REQUIRED_CRITERIA,
			"sample_strategy": "opening_ending_global_quantiles_speaker_switches_semantic_anchors",
		},
		"input_files": {key: str(path) for key, path in input_files.items() if path.exists()},
		"input_file_hashes": {str(path.resolve()): _sha256(path) for path in input_files.values() if path.exists()},
		"subtitle_time_offset_sec": subtitle_time_offset_sec,
		"final_duration_sec": round(final_duration, 3),
		"samples": selected,
	}


def _extract_sample_media(final_video: Path, output_dir: Path, samples: list[dict[str, Any]]) -> None:
	for sample in samples:
		sample_dir = output_dir / "samples" / sample["sample_id"]
		sample_dir.mkdir(parents=True, exist_ok=True)
		frame_path = sample_dir / "frame.jpg"
		audio_path = sample_dir / "context_audio.wav"
		_run([
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-ss",
			f"{float(sample['sample_time_sec']):.3f}",
			"-i",
			str(final_video),
			"-frames:v",
			"1",
			str(frame_path),
		])
		_run([
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-ss",
			f"{float(sample['audio_context_start_sec']):.3f}",
			"-i",
			str(final_video),
			"-t",
			f"{float(sample['audio_context_end_sec']) - float(sample['audio_context_start_sec']):.3f}",
			"-vn",
			"-ac",
			"1",
			"-ar",
			"24000",
			"-c:a",
			"pcm_s16le",
			str(audio_path),
		])
		sample["frame"] = str(frame_path)
		sample["context_audio"] = str(audio_path)


def _write_review_package(output_dir: Path, package: dict[str, Any]) -> None:
	lines = [
		"# Multimodal Spot QA Review Package",
		"",
		"Review every sample. Mark each required criterion as PASS, WARN, FAIL, or NA.",
		"Any FAIL or missing required criterion blocks final QA.",
		"`video_motion_integrity` is also checked by an automatic frame-motion gate; reviewers should still mark it FAIL if a sample visibly repeats a stale frame.",
		"",
		"Required criteria:",
		*(f"- {criterion}" for criterion in REQUIRED_CRITERIA),
		"",
	]
	for sample in package["samples"]:
		lines.extend([
			f"## {sample['sample_id']} {sample['sample_time_sec']:.3f}s",
			f"- reason: {sample['reason']}",
			f"- speaker: {sample.get('speaker')}",
			f"- cue: {sample.get('cue_text')}",
			f"- turn: {sample.get('turn_text')}",
			f"- frame: `{sample.get('frame', '')}`",
			f"- context_audio: `{sample.get('context_audio', '')}`",
			"",
		])
	(output_dir / "multimodal-spot-qa-review-package.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _validate_review(package: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
	samples = package["samples"]
	reviews = review.get("sample_reviews") or []
	review_by_id = {str(item.get("sample_id")): item for item in reviews if isinstance(item, dict)}
	failures: list[str] = []
	warnings: list[str] = []
	for sample in samples:
		sample_id = sample["sample_id"]
		item = review_by_id.get(sample_id)
		if not item:
			failures.append(f"missing review for {sample_id}")
			continue
		criteria = item.get("criteria") if isinstance(item.get("criteria"), dict) else {}
		for criterion in REQUIRED_CRITERIA:
			value = str(criteria.get(criterion) or "").upper()
			if value in FAIL_VALUES:
				failures.append(f"{sample_id} criterion {criterion} is {value or 'missing'}")
			elif value not in PASS_VALUES:
				failures.append(f"{sample_id} criterion {criterion} has unsupported value {value}")
			elif value == "WARN":
				warnings.append(f"{sample_id} criterion {criterion} is WARN")
	if review.get("read_entire_package") is not True:
		failures.append("review did not confirm read_entire_package=true")
	status = "PASS" if not failures and str(review.get("status") or "PASS").upper() == "PASS" else "FAIL"
	if str(review.get("status") or "PASS").upper() != "PASS":
		failures.append(f"review status is {review.get('status')}")
	return {
		"status": status,
		"failures": failures,
		"warnings": warnings,
		"summary": {
			"sample_count": len(samples),
			"reviewed_sample_count": len(review_by_id),
			"fail_count": len(failures),
			"warn_count": len(warnings),
		},
		"review": review,
	}


def run_multimodal_spot_qa(
	run_dir: Path,
	min_samples: int = DEFAULT_MIN_SAMPLES,
	max_samples: int = DEFAULT_MAX_SAMPLES,
	review_json: Path | None = None,
	extract_media: bool = True,
	force: bool = False,
) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	output_dir = run_dir / "09a-multimodal-spot-qa"
	result_path = output_dir / "multimodal-spot-qa-result.json"
	if result_path.exists() and not force and review_json is None:
		return _read_json(result_path)
	output_dir.mkdir(parents=True, exist_ok=True)
	package = _build_sample_plan(run_dir, min_samples, max_samples)
	if extract_media:
		_extract_sample_media(run_dir / "video/final_video.mp4", output_dir, package["samples"])
	_write_json(output_dir / "multimodal-spot-qa-package.json", package)
	_write_review_package(output_dir, package)
	motion_integrity = _run_motion_integrity_gate(run_dir)
	automatic_failures = [
		f"video motion integrity failed: {item.get('reason')} target={item.get('target_start_sec')}-{item.get('target_end_sec')} source_mad={item.get('source_mad')} rendered_mad={item.get('rendered_mad')}"
		for item in motion_integrity.get("failures") or []
	]
	if review_json is None:
		result = {
			"schema_version": "worldview-china-multimodal-spot-qa-result.v1",
			"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
			"status": "FAIL" if automatic_failures else "NEEDS_REVIEW",
			"package": str(output_dir / "multimodal-spot-qa-package.json"),
			"review_package": str(output_dir / "multimodal-spot-qa-review-package.md"),
			"required_criteria": REQUIRED_CRITERIA,
			"summary": {
				"sample_count": len(package["samples"]),
				"reviewed_sample_count": 0,
				"fail_count": len(automatic_failures),
				"warn_count": 0,
				"automatic_motion_integrity_status": motion_integrity.get("status"),
			},
			"failures": automatic_failures,
			"automatic_checks": {
				"video_motion_integrity": motion_integrity,
			},
			"input_file_hashes": package["input_file_hashes"],
		}
	else:
		review = _read_json(review_json)
		validation = _validate_review(package, review)
		combined_failures = [*automatic_failures, *validation["failures"]]
		status = "PASS" if not combined_failures and validation["status"] == "PASS" else "FAIL"
		result = {
			"schema_version": "worldview-china-multimodal-spot-qa-result.v1",
			"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
			"status": status,
			"package": str(output_dir / "multimodal-spot-qa-package.json"),
			"review_package": str(output_dir / "multimodal-spot-qa-review-package.md"),
			"review_json": str(review_json),
			"required_criteria": REQUIRED_CRITERIA,
			"summary": {
				**validation["summary"],
				"fail_count": len(combined_failures),
				"automatic_motion_integrity_status": motion_integrity.get("status"),
			},
			"failures": combined_failures,
			"warnings": validation["warnings"],
			"automatic_checks": {
				"video_motion_integrity": motion_integrity,
			},
			"input_file_hashes": package["input_file_hashes"],
			"review": validation["review"],
		}
	_write_json(result_path, result)
	report_lines = [
		"# Multimodal Spot QA Report",
		"",
		f"- status: {result['status']}",
		f"- sample_count: {result['summary']['sample_count']}",
		f"- reviewed_sample_count: {result['summary']['reviewed_sample_count']}",
		f"- fail_count: {result['summary']['fail_count']}",
		f"- warn_count: {result['summary']['warn_count']}",
		f"- package: `{result['package']}`",
		f"- review_package: `{result['review_package']}`",
	]
	if result.get("failures"):
		report_lines.extend(["", "## Failures", *(f"- {item}" for item in result["failures"])])
	if result.get("warnings"):
		report_lines.extend(["", "## Warnings", *(f"- {item}" for item in result["warnings"])])
	(output_dir / "multimodal-spot-qa-report.md").write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")
	return result


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build and validate unified multimodal spot QA for Worldview China podcast videos.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
	parser.add_argument("--max-samples", type=int, default=DEFAULT_MAX_SAMPLES)
	parser.add_argument("--review-json", type=Path, help="Completed review JSON covering every sample and required criterion.")
	parser.add_argument("--no-extract-media", dest="extract_media", action="store_false")
	parser.add_argument("--force", action="store_true")
	parser.set_defaults(extract_media=True)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	result = run_multimodal_spot_qa(
		args.run_dir,
		min_samples=args.min_samples,
		max_samples=args.max_samples,
		review_json=args.review_json,
		extract_media=args.extract_media,
		force=args.force,
	)
	print(json.dumps({
		"status": result["status"],
		"result": str(Path(args.run_dir) / "09a-multimodal-spot-qa/multimodal-spot-qa-result.json"),
		"sample_count": result["summary"]["sample_count"],
	}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
