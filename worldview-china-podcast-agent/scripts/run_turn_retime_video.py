#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


VISUAL_SYNC_MODE = "turn_retimed_basic_v1"
DEFAULT_FRAME_INTERVAL_SEC = 0.5
DEFAULT_MOTION_SCALE_WIDTH = 160
DEFAULT_LOW_MOTION_THRESHOLD = 0.035
DEFAULT_SCENE_THRESHOLD = 0.30
DEFAULT_SCENE_PROTECT_SEC = 0.5
DEFAULT_TURN_EDGE_PROTECT_SEC = 0.8
DEFAULT_MIN_TRIM_SEC = 0.8
DEFAULT_MIN_KEPT_SEGMENT_SEC = 1.2
DEFAULT_MAX_CUTS_PER_MINUTE = 10.0


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _run_no_check(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


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


def _parse_time(value: Any) -> float:
	if isinstance(value, (int, float)):
		return float(value)
	text = str(value).strip()
	if not text:
		raise ValueError("empty timestamp")
	parts = text.split(":")
	if len(parts) == 1:
		return float(parts[0])
	if len(parts) == 2:
		return int(parts[0]) * 60 + float(parts[1])
	if len(parts) == 3:
		return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
	raise ValueError(f"unsupported timestamp: {value!r}")


def _round_range(start: float, end: float) -> dict[str, float]:
	return {"start_sec": round(start, 3), "end_sec": round(end, 3), "duration_sec": round(max(0.0, end - start), 3)}


def _merge_ranges(ranges: list[tuple[float, float]], gap: float = 0.05) -> list[tuple[float, float]]:
	cleaned = sorted((float(start), float(end)) for start, end in ranges if end > start)
	if not cleaned:
		return []
	merged = [cleaned[0]]
	for start, end in cleaned[1:]:
		last_start, last_end = merged[-1]
		if start <= last_end + gap:
			merged[-1] = (last_start, max(last_end, end))
		else:
			merged.append((start, end))
	return merged


def _intersect_range(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float] | None:
	start = max(left[0], right[0])
	end = min(left[1], right[1])
	if end <= start:
		return None
	return start, end


def _subtract_ranges(base_ranges: list[tuple[float, float]], cut_ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
	result = _merge_ranges(base_ranges)
	for cut_start, cut_end in _merge_ranges(cut_ranges):
		next_ranges: list[tuple[float, float]] = []
		for start, end in result:
			if cut_end <= start or cut_start >= end:
				next_ranges.append((start, end))
				continue
			if cut_start > start:
				next_ranges.append((start, min(cut_start, end)))
			if cut_end < end:
				next_ranges.append((max(cut_end, start), end))
		result = next_ranges
	return _merge_ranges(result)


def _range_duration(ranges: list[tuple[float, float]]) -> float:
	return sum(max(0.0, end - start) for start, end in ranges)


def _range_overlaps_any(candidate: tuple[float, float], ranges: list[tuple[float, float]]) -> bool:
	return any(_intersect_range(candidate, item) is not None for item in ranges)


def _path_for_concat(path: Path) -> str:
	return str(path.resolve()).replace("'", "'\\''")


def _measure_frame_motion(frame_paths: list[Path]) -> list[dict[str, float]]:
	from PIL import Image, ImageChops, ImageStat

	windows: list[dict[str, float]] = []
	previous = None
	for index, frame_path in enumerate(frame_paths):
		current = Image.open(frame_path).convert("L")
		if previous is None:
			motion = 0.0
		else:
			diff = ImageChops.difference(previous, current)
			motion = float(ImageStat.Stat(diff).mean[0]) / 255.0
		windows.append({"frame_index": float(index), "motion_score": round(motion, 6)})
		previous = current
	return windows


def _detect_scene_cuts(source_video: Path, scene_threshold: float, max_duration_sec: float | None) -> list[float]:
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"info",
		"-i",
		str(source_video),
	]
	if max_duration_sec is not None:
		cmd.extend(["-t", f"{max_duration_sec:.3f}"])
	cmd.extend([
		"-vf",
		f"select='gt(scene,{scene_threshold})',showinfo",
		"-an",
		"-f",
		"null",
		"-",
	])
	completed = _run_no_check(cmd)
	text = "\n".join([completed.stdout, completed.stderr])
	cuts = []
	for match in re.finditer(r"pts_time:(?P<time>\d+(?:\.\d+)?)", text):
		cuts.append(float(match.group("time")))
	return sorted(set(round(value, 3) for value in cuts))


def analyze_visual_activity(
	source_video: Path,
	output_path: Path,
	work_dir: Path,
	frame_interval_sec: float = DEFAULT_FRAME_INTERVAL_SEC,
	motion_scale_width: int = DEFAULT_MOTION_SCALE_WIDTH,
	low_motion_threshold: float = DEFAULT_LOW_MOTION_THRESHOLD,
	scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
	scene_protect_sec: float = DEFAULT_SCENE_PROTECT_SEC,
	max_duration_sec: float | None = None,
	force: bool = False,
) -> dict[str, Any]:
	assert source_video.exists(), f"Missing source video: {source_video}"
	if output_path.exists() and not force:
		return _read_json(output_path)
	duration = _duration(source_video)
	analysis_duration = min(duration, max_duration_sec) if max_duration_sec is not None else duration
	frames_dir = work_dir / "visual_activity_frames"
	if frames_dir.exists():
		shutil.rmtree(frames_dir)
	frames_dir.mkdir(parents=True, exist_ok=True)
	filter_expr = f"fps={1 / frame_interval_sec:.6f},scale={motion_scale_width}:-1"
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(source_video),
		"-t",
		f"{analysis_duration:.3f}",
		"-vf",
		filter_expr,
		"-q:v",
		"5",
		str(frames_dir / "frame_%06d.jpg"),
	]
	_run(cmd)
	frame_paths = sorted(frames_dir.glob("frame_*.jpg"))
	motion_measurements = _measure_frame_motion(frame_paths)
	windows = []
	for item in motion_measurements:
		frame_index = int(item["frame_index"])
		start = max(0.0, (frame_index - 1) * frame_interval_sec)
		end = min(analysis_duration, frame_index * frame_interval_sec)
		if frame_index == 0:
			end = min(analysis_duration, frame_interval_sec)
		windows.append({
			"start_sec": round(start, 3),
			"end_sec": round(max(start, end), 3),
			"motion_score": item["motion_score"],
			"low_motion": item["motion_score"] <= low_motion_threshold,
		})
	low_motion_ranges = _merge_ranges([
		(float(window["start_sec"]), float(window["end_sec"]))
		for window in windows
		if window["low_motion"] and float(window["end_sec"]) > float(window["start_sec"])
	], gap=frame_interval_sec + 0.01)
	scene_cuts = _detect_scene_cuts(source_video, scene_threshold, analysis_duration)
	protected_ranges = _merge_ranges([
		(max(0.0, cut - scene_protect_sec), min(analysis_duration, cut + scene_protect_sec))
		for cut in scene_cuts
	])
	activity = {
		"schema_version": "worldview-china-visual-activity.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"source_video": str(source_video),
		"source_video_sha256": _sha256(source_video),
		"source_duration_sec": round(duration, 3),
		"analysis_duration_sec": round(analysis_duration, 3),
		"frame_interval_sec": frame_interval_sec,
		"motion_scale_width": motion_scale_width,
		"low_motion_threshold": low_motion_threshold,
		"scene_threshold": scene_threshold,
		"scene_protect_sec": scene_protect_sec,
		"window_count": len(windows),
		"scene_cuts_sec": scene_cuts,
		"windows": windows,
		"low_motion_ranges": [_round_range(start, end) for start, end in low_motion_ranges],
		"protected_ranges": [
			{**_round_range(start, end), "reason": "scene_cut"}
			for start, end in protected_ranges
		],
	}
	_write_json(output_path, activity)
	return activity


def _coerce_turn_id(item: dict[str, Any], index: int) -> str:
	value = item.get("turn_id")
	if value:
		return str(value)
	turn_index = item.get("turn_index", item.get("segment_index", index))
	return f"turn_{int(turn_index):04d}"


def _coerce_turn_index(item: dict[str, Any], index: int) -> int:
	value = item.get("turn_index", item.get("segment_index", index))
	return int(value)


def _load_source_turns(path: Path, source_time_offset_sec: float = 0.0) -> list[dict[str, Any]]:
	data = _read_json(path)
	if isinstance(data, dict):
		raw = data.get("turns") or data.get("segments") or data.get("timeline") or data.get("speaker_segments") or []
	elif isinstance(data, list):
		raw = data
	else:
		raw = []
	turns = []
	for index, item in enumerate(raw, start=1):
		if not isinstance(item, dict):
			continue
		start_value = item.get("source_start", item.get("start", item.get("start_sec")))
		end_value = item.get("source_end", item.get("end", item.get("end_sec")))
		if start_value is None or end_value is None:
			continue
		start = _parse_time(start_value) - source_time_offset_sec
		end = _parse_time(end_value) - source_time_offset_sec
		if end <= start:
			continue
		speaker = str(item.get("speaker") or item.get("speaker_id") or "").strip()
		if speaker in {"0", "1"}:
			speaker = f"Speaker {speaker}"
		turn = {
			"turn_id": _coerce_turn_id(item, index),
			"turn_index": _coerce_turn_index(item, index),
			"speaker": speaker,
			"source_start_sec": max(0.0, start),
			"source_end_sec": max(0.0, end),
			"source_text": str(item.get("source_text") or item.get("text") or item.get("zh_text") or ""),
			"trim_candidates": item.get("trim_candidates") or [],
			"silence_ranges": item.get("silence_ranges") or [],
			"filler_ranges": item.get("filler_ranges") or item.get("low_value_ranges") or [],
		}
		turns.append(turn)
	return turns


def _load_audio_turns(path: Path) -> dict[str, dict[str, Any]]:
	data = _read_json(path)
	raw = data.get("turns") if isinstance(data, dict) else data if isinstance(data, list) else []
	by_id: dict[str, dict[str, Any]] = {}
	by_index: dict[str, dict[str, Any]] = {}
	for index, item in enumerate(raw or [], start=1):
		if not isinstance(item, dict):
			continue
		start_value = item.get("audio_start", item.get("start_sec", item.get("start")))
		end_value = item.get("audio_end", item.get("end_sec", item.get("end")))
		if start_value is None or end_value is None:
			continue
		start = _parse_time(start_value)
		end = _parse_time(end_value)
		if end <= start:
			continue
		turn_index = _coerce_turn_index(item, index)
		turn_id = _coerce_turn_id(item, index)
		audio_turn = {
			"turn_id": turn_id,
			"turn_index": turn_index,
			"speaker": item.get("speaker"),
			"audio_start_sec": start,
			"audio_end_sec": end,
			"alignment_confidence": item.get("alignment_confidence") or item.get("match_confidence"),
		}
		by_id[turn_id] = audio_turn
		by_index[str(turn_index)] = audio_turn
	return {**{f"index:{key}": value for key, value in by_index.items()}, **by_id}


def _coerce_range_list(raw: Any, parent_start: float, parent_end: float) -> list[tuple[float, float]]:
	ranges = []
	if not isinstance(raw, list):
		return ranges
	for item in raw:
		if isinstance(item, dict):
			start_value = item.get("start", item.get("start_sec", item.get("source_start")))
			end_value = item.get("end", item.get("end_sec", item.get("source_end")))
		elif isinstance(item, (list, tuple)) and len(item) >= 2:
			start_value, end_value = item[0], item[1]
		else:
			continue
		if start_value is None or end_value is None:
			continue
		start = _parse_time(start_value)
		end = _parse_time(end_value)
		if start < 0:
			start = parent_start + start
		if end <= start:
			continue
		intersection = _intersect_range((start, end), (parent_start, parent_end))
		if intersection is not None:
			ranges.append(intersection)
	return _merge_ranges(ranges)


def _ranges_from_dicts(raw: Any) -> list[tuple[float, float]]:
	if not isinstance(raw, list):
		return []
	ranges = []
	for item in raw:
		if not isinstance(item, dict):
			continue
		start = float(item.get("start_sec") or item.get("start") or 0.0)
		end = float(item.get("end_sec") or item.get("end") or start)
		if end > start:
			ranges.append((start, end))
	return _merge_ranges(ranges)


def _candidate_ranges_for_turn(
	turn: dict[str, Any],
	visual_activity: dict[str, Any],
	protected_ranges: list[tuple[float, float]],
	turn_edge_protect_sec: float,
) -> list[dict[str, Any]]:
	turn_start = float(turn["source_start_sec"])
	turn_end = float(turn["source_end_sec"])
	allowed = _subtract_ranges(
		[(turn_start + turn_edge_protect_sec, turn_end - turn_edge_protect_sec)],
		protected_ranges,
	)
	candidates: list[dict[str, Any]] = []

	def add_ranges(raw_ranges: list[tuple[float, float]], kind: str, base_score: float) -> None:
		for raw_start, raw_end in raw_ranges:
			for start, end in allowed:
				intersection = _intersect_range((raw_start, raw_end), (start, end))
				if intersection is None:
					continue
				candidates.append({
					"start": intersection[0],
					"end": intersection[1],
					"kind": kind,
					"score": base_score,
				})

	low_motion_ranges = _ranges_from_dicts(visual_activity.get("low_motion_ranges") or [])
	turn_low_motion = []
	for item in low_motion_ranges:
		intersection = _intersect_range(item, (turn_start, turn_end))
		if intersection is not None:
			turn_low_motion.append(intersection)
	silence_ranges = _coerce_range_list(turn.get("silence_ranges"), turn_start, turn_end)
	filler_ranges = _coerce_range_list(turn.get("filler_ranges"), turn_start, turn_end)
	explicit_ranges = _coerce_range_list(turn.get("trim_candidates"), turn_start, turn_end)
	add_ranges(silence_ranges, "source_silence", 90.0)
	add_ranges(filler_ranges, "source_filler", 65.0)
	add_ranges(explicit_ranges, "explicit_trim_candidate", 70.0)
	add_ranges(turn_low_motion, "low_motion", 35.0)
	for candidate in candidates:
		if candidate["kind"] != "low_motion" and _range_overlaps_any((candidate["start"], candidate["end"]), turn_low_motion):
			candidate["score"] += 8.0
		midpoint = (candidate["start"] + candidate["end"]) / 2.0
		relative = (midpoint - turn_start) / max(0.001, turn_end - turn_start)
		if 0.25 <= relative <= 0.75:
			candidate["score"] += 5.0
		if relative < 0.15 or relative > 0.85:
			candidate["score"] -= 8.0
	return sorted(candidates, key=lambda item: (float(item["score"]), item["end"] - item["start"]), reverse=True)


def _candidate_to_cut(candidate: dict[str, Any], remaining: float, min_trim_sec: float) -> tuple[float, float] | None:
	start = float(candidate["start"])
	end = float(candidate["end"])
	duration = end - start
	if duration < min_trim_sec:
		return None
	if duration <= remaining + 0.05:
		return start, end
	take = max(min_trim_sec, remaining)
	center = (start + end) / 2.0
	cut_start = max(start, center - take / 2.0)
	cut_end = min(end, cut_start + take)
	cut_start = max(start, cut_end - take)
	return cut_start, cut_end


def _kept_segments_after_cuts(turn_range: tuple[float, float], cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
	return _subtract_ranges([turn_range], cuts)


def _all_kept_segments_valid(kept: list[tuple[float, float]], min_kept_segment_sec: float) -> bool:
	return all(end - start >= min_kept_segment_sec - 0.001 for start, end in kept)


def _fallback_candidates(
	turn: dict[str, Any],
	protected_ranges: list[tuple[float, float]],
	turn_edge_protect_sec: float,
) -> list[dict[str, Any]]:
	turn_start = float(turn["source_start_sec"])
	turn_end = float(turn["source_end_sec"])
	allowed = _subtract_ranges(
		[(turn_start + turn_edge_protect_sec, turn_end - turn_edge_protect_sec)],
		protected_ranges,
	)
	candidates = []
	for start, end in allowed:
		if end <= start:
			continue
		candidates.append({"start": start, "end": end, "kind": "fallback_middle", "score": 10.0})
	return sorted(candidates, key=lambda item: item["end"] - item["start"], reverse=True)


def _plan_turn(
	turn: dict[str, Any],
	audio_turn: dict[str, Any] | None,
	visual_activity: dict[str, Any],
	protected_ranges: list[tuple[float, float]],
	turn_edge_protect_sec: float,
	min_trim_sec: float,
	min_kept_segment_sec: float,
) -> dict[str, Any]:
	turn_start = float(turn["source_start_sec"])
	turn_end = float(turn["source_end_sec"])
	source_duration = turn_end - turn_start
	if audio_turn is None:
		target_duration = source_duration
		audio_start = None
		audio_end = None
	else:
		audio_start = float(audio_turn["audio_start_sec"])
		audio_end = float(audio_turn["audio_end_sec"])
		target_duration = max(0.0, audio_end - audio_start)
	trim_needed = max(0.0, source_duration - target_duration)
	cuts: list[tuple[float, float]] = []
	cut_reasons: list[dict[str, Any]] = []
	if trim_needed >= min_trim_sec:
		candidates = _candidate_ranges_for_turn(turn, visual_activity, protected_ranges, turn_edge_protect_sec)
		for pass_candidates in (candidates, _fallback_candidates(turn, protected_ranges, turn_edge_protect_sec)):
			for candidate in pass_candidates:
				remaining = trim_needed - _range_duration(cuts)
				if remaining < min_trim_sec:
					break
				available_candidate_ranges = _subtract_ranges(
					[(float(candidate["start"]), float(candidate["end"]))],
					cuts,
				)
				for available_start, available_end in sorted(available_candidate_ranges, key=lambda item: item[1] - item[0], reverse=True):
					remaining = trim_needed - _range_duration(cuts)
					if remaining < min_trim_sec:
						break
					cut = _candidate_to_cut(
						{**candidate, "start": available_start, "end": available_end},
						remaining,
						min_trim_sec,
					)
					if cut is None:
						continue
					new_cuts = _merge_ranges([*cuts, cut])
					kept = _kept_segments_after_cuts((turn_start, turn_end), new_cuts)
					if not _all_kept_segments_valid(kept, min_kept_segment_sec):
						continue
					cuts = new_cuts
					cut_reasons.append({
						**_round_range(cut[0], cut[1]),
						"reason": candidate["kind"],
						"score": round(float(candidate["score"]), 3),
					})
					if trim_needed - _range_duration(cuts) < min_trim_sec:
						break
				if trim_needed - _range_duration(cuts) < min_trim_sec:
					break
	kept = _kept_segments_after_cuts((turn_start, turn_end), cuts)
	kept_duration = _range_duration(kept)
	duration_delta = kept_duration - target_duration
	protected_violations = [
		_round_range(max(cut[0], protected[0]), min(cut[1], protected[1]))
		for cut in cuts
		for protected in protected_ranges
		if _intersect_range(cut, protected) is not None
	]
	if audio_turn is None:
		confidence = "low"
	elif abs(duration_delta) <= 0.5 and not protected_violations:
		confidence = "high" if _range_duration(cuts) == 0 else "medium"
	else:
		confidence = "low"
	return {
		"turn_id": turn["turn_id"],
		"turn_index": turn["turn_index"],
		"speaker": turn.get("speaker"),
		"source_start_sec": round(turn_start, 3),
		"source_end_sec": round(turn_end, 3),
		"target_audio_start_sec": round(audio_start, 3) if audio_start is not None else None,
		"target_audio_end_sec": round(audio_end, 3) if audio_end is not None else None,
		"source_duration_sec": round(source_duration, 3),
		"target_duration_sec": round(target_duration, 3),
		"trim_needed_sec": round(trim_needed, 3),
		"trimmed_duration_sec": round(_range_duration(cuts), 3),
		"kept_duration_sec": round(kept_duration, 3),
		"duration_delta_vs_target_sec": round(duration_delta, 3),
		"kept_source_ranges": [_round_range(start, end) for start, end in kept],
		"trimmed_source_ranges": cut_reasons,
		"protected_range_violations": protected_violations,
		"confidence": confidence,
	}


def build_retime_plan(
	source_video: Path,
	source_turn_map: Path,
	turn_audio_timeline: Path,
	visual_activity_path: Path,
	output_path: Path,
	source_time_offset_sec: float = 0.0,
	turn_edge_protect_sec: float = DEFAULT_TURN_EDGE_PROTECT_SEC,
	min_trim_sec: float = DEFAULT_MIN_TRIM_SEC,
	min_kept_segment_sec: float = DEFAULT_MIN_KEPT_SEGMENT_SEC,
	max_cuts_per_minute: float = DEFAULT_MAX_CUTS_PER_MINUTE,
) -> dict[str, Any]:
	source_turns = _load_source_turns(source_turn_map, source_time_offset_sec=source_time_offset_sec)
	audio_turns = _load_audio_turns(turn_audio_timeline)
	visual_activity = _read_json(visual_activity_path)
	protected_ranges = _ranges_from_dicts(visual_activity.get("protected_ranges") or [])
	turn_plans = []
	for source_turn in source_turns:
		audio_turn = audio_turns.get(str(source_turn["turn_id"])) or audio_turns.get(f"index:{source_turn['turn_index']}")
		turn_plans.append(
			_plan_turn(
				source_turn,
				audio_turn,
				visual_activity,
				protected_ranges,
				turn_edge_protect_sec,
				min_trim_sec,
				min_kept_segment_sec,
			)
		)
	edit_segments = []
	cursor = 0.0
	for turn in turn_plans:
		for source_range in turn["kept_source_ranges"]:
			duration = float(source_range["duration_sec"])
			edit_segments.append({
				"segment_index": len(edit_segments) + 1,
				"turn_id": turn["turn_id"],
				"turn_index": turn["turn_index"],
				"speaker": turn.get("speaker"),
				"source_start_sec": source_range["start_sec"],
				"source_end_sec": source_range["end_sec"],
				"target_start_sec": round(cursor, 3),
				"target_end_sec": round(cursor + duration, 3),
				"duration_sec": duration,
			})
			cursor += duration
	trimmed_ranges = [
		(float(item["start_sec"]), float(item["end_sec"]))
		for turn in turn_plans
		for item in turn["trimmed_source_ranges"]
	]
	protected_violations = [
		item
		for turn in turn_plans
		for item in turn["protected_range_violations"]
	]
	target_duration = sum(float(turn["target_duration_sec"]) for turn in turn_plans)
	min_kept = min((float(segment["duration_sec"]) for segment in edit_segments), default=0.0)
	final_duration = cursor
	cuts_per_minute = len(trimmed_ranges) / max(0.001, final_duration / 60.0)
	status = "pass"
	warnings = []
	if protected_violations:
		status = "fail"
	if min_kept and min_kept < min_kept_segment_sec - 0.001:
		status = "fail"
	if abs(final_duration - target_duration) > 0.75:
		warnings.append("retimed video duration is not within 0.75s of target audio timeline")
	if cuts_per_minute > max_cuts_per_minute:
		warnings.append("cut density exceeds recommended maximum")
	plan = {
		"schema_version": "worldview-china-turn-retime-edit-plan.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"visual_sync_mode": VISUAL_SYNC_MODE,
		"status": status,
		"warnings": warnings,
		"source_video": str(source_video),
		"source_video_sha256": _sha256(source_video),
		"source_turn_map": str(source_turn_map),
		"source_turn_map_sha256": _sha256(source_turn_map),
		"turn_audio_timeline": str(turn_audio_timeline),
		"turn_audio_timeline_sha256": _sha256(turn_audio_timeline),
		"visual_activity": str(visual_activity_path),
		"visual_activity_sha256": _sha256(visual_activity_path),
		"source_time_offset_sec": round(source_time_offset_sec, 3),
		"policy": {
			"turn_edge_protect_sec": turn_edge_protect_sec,
			"min_trim_sec": min_trim_sec,
			"min_kept_segment_sec": min_kept_segment_sec,
			"max_cuts_per_minute": max_cuts_per_minute,
			"strategy": "trim source silence/filler/low-motion middle ranges before fallback middle trims",
		},
		"summary": {
			"turn_count": len(turn_plans),
			"edit_segment_count": len(edit_segments),
			"trimmed_range_count": len(trimmed_ranges),
			"target_duration_sec": round(target_duration, 3),
			"estimated_video_duration_sec": round(final_duration, 3),
			"duration_delta_vs_target_sec": round(final_duration - target_duration, 3),
			"trimmed_duration_sec": round(_range_duration(trimmed_ranges), 3),
			"min_kept_segment_duration_sec": round(min_kept, 3),
			"cuts_per_minute": round(cuts_per_minute, 3),
			"protected_range_violation_count": len(protected_violations),
		},
		"turns": turn_plans,
		"edit_segments": edit_segments,
		"protected_range_violations": protected_violations,
	}
	_write_json(output_path, plan)
	return plan


def render_retimed_video(plan_path: Path, output_video: Path, video_encoder: str = "libx264") -> dict[str, Any]:
	plan = _read_json(plan_path)
	source_video = Path(str(plan["source_video"]))
	assert source_video.exists(), f"Missing source video: {source_video}"
	output_video.parent.mkdir(parents=True, exist_ok=True)
	concat_path = output_video.with_suffix(".ffconcat")
	with concat_path.open("w", encoding="utf-8") as handle:
		handle.write("ffconcat version 1.0\n")
		for segment in plan.get("edit_segments") or []:
			start = float(segment["source_start_sec"])
			end = float(segment["source_end_sec"])
			if end <= start:
				continue
			handle.write(f"file '{_path_for_concat(source_video)}'\n")
			handle.write(f"inpoint {start:.3f}\n")
			handle.write(f"outpoint {end:.3f}\n")
	tmp = output_video.with_suffix(output_video.suffix + ".tmp.mp4")
	if tmp.exists():
		tmp.unlink()
	if video_encoder == "h264_videotoolbox":
		encoder_args = ["-c:v", "h264_videotoolbox", "-b:v", "12000k", "-pix_fmt", "yuv420p", "-tag:v", "avc1"]
	else:
		encoder_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-tag:v", "avc1"]
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"concat",
		"-safe",
		"0",
		"-i",
		str(concat_path),
		"-map",
		"0:v:0",
		"-an",
		*encoder_args,
		"-movflags",
		"+faststart",
		str(tmp),
	])
	if output_video.exists():
		output_video.unlink()
	tmp.replace(output_video)
	duration = _duration(output_video)
	return {
		"schema_version": "worldview-china-turn-retime-render.v1",
		"retime_edit_plan": str(plan_path),
		"concat_file": str(concat_path),
		"retimed_video": str(output_video),
		"retimed_video_sha256": _sha256(output_video),
		"duration_sec": round(duration, 3),
		"edit_segment_count": len(plan.get("edit_segments") or []),
	}


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Build a basic turn-level source-video retime plan for Worldview China podcast renders.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--source-video", type=Path)
	parser.add_argument("--source-turn-map", type=Path)
	parser.add_argument("--turn-audio-timeline", type=Path)
	parser.add_argument("--visual-activity", type=Path)
	parser.add_argument("--output-plan", type=Path)
	parser.add_argument("--output-retimed-video", type=Path)
	parser.add_argument("--source-time-offset-sec", type=float, default=0.0)
	parser.add_argument("--frame-interval-sec", type=float, default=DEFAULT_FRAME_INTERVAL_SEC)
	parser.add_argument("--motion-scale-width", type=int, default=DEFAULT_MOTION_SCALE_WIDTH)
	parser.add_argument("--low-motion-threshold", type=float, default=DEFAULT_LOW_MOTION_THRESHOLD)
	parser.add_argument("--scene-threshold", type=float, default=DEFAULT_SCENE_THRESHOLD)
	parser.add_argument("--scene-protect-sec", type=float, default=DEFAULT_SCENE_PROTECT_SEC)
	parser.add_argument("--turn-edge-protect-sec", type=float, default=DEFAULT_TURN_EDGE_PROTECT_SEC)
	parser.add_argument("--min-trim-sec", type=float, default=DEFAULT_MIN_TRIM_SEC)
	parser.add_argument("--min-kept-segment-sec", type=float, default=DEFAULT_MIN_KEPT_SEGMENT_SEC)
	parser.add_argument("--max-cuts-per-minute", type=float, default=DEFAULT_MAX_CUTS_PER_MINUTE)
	parser.add_argument("--max-duration-sec", type=float)
	parser.add_argument("--render", action="store_true")
	parser.add_argument("--video-encoder", choices=("libx264", "h264_videotoolbox"), default="libx264")
	parser.add_argument("--force", action="store_true")
	return parser


def main() -> None:
	args = _build_parser().parse_args()
	run_dir = args.run_dir.resolve()
	output_dir = run_dir / "08-source-video-revoice"
	work_dir = output_dir / "work"
	source_video = (args.source_video or run_dir / "02-source-capture/youtube-media/source.mp4").resolve()
	source_turn_map = (args.source_turn_map or run_dir / "02b-source-voice-prompts/source_speaker_timeline.normalized.json").resolve()
	turn_audio_timeline = (args.turn_audio_timeline or run_dir / "audio/dialogue_timeline.json").resolve()
	visual_activity = (args.visual_activity or output_dir / "visual_activity.json").resolve()
	output_plan = (args.output_plan or output_dir / "retime_edit_plan.json").resolve()
	analyze_visual_activity(
		source_video,
		visual_activity,
		work_dir,
		frame_interval_sec=args.frame_interval_sec,
		motion_scale_width=args.motion_scale_width,
		low_motion_threshold=args.low_motion_threshold,
		scene_threshold=args.scene_threshold,
		scene_protect_sec=args.scene_protect_sec,
		max_duration_sec=args.max_duration_sec,
		force=args.force,
	)
	plan = build_retime_plan(
		source_video,
		source_turn_map,
		turn_audio_timeline,
		visual_activity,
		output_plan,
		source_time_offset_sec=args.source_time_offset_sec,
		turn_edge_protect_sec=args.turn_edge_protect_sec,
		min_trim_sec=args.min_trim_sec,
		min_kept_segment_sec=args.min_kept_segment_sec,
		max_cuts_per_minute=args.max_cuts_per_minute,
	)
	result: dict[str, Any] = {
		"visual_activity": str(visual_activity),
		"retime_edit_plan": str(output_plan),
		"status": plan["status"],
		"summary": plan["summary"],
	}
	if args.render:
		retimed_video = (args.output_retimed_video or output_dir / "work/source_retimed_basic.mp4").resolve()
		result["render"] = render_retimed_video(output_plan, retimed_video, video_encoder=args.video_encoder)
	print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
