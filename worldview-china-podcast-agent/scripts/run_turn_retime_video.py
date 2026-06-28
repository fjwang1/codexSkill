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
DEFAULT_MIN_EXTEND_SEC = 0.05
DEFAULT_MAX_TURN_EXTENSION_SEC = 12.0
DEFAULT_MAX_TURN_EXTENSION_RATIO = 0.30
DEFAULT_MAX_TURN_BOUNDARY_DRIFT_SEC = 0.75
DEFAULT_MIN_KEPT_SEGMENT_SEC = 1.2
DEFAULT_MAX_CUTS_PER_MINUTE = 10.0
DEFAULT_RENDERED_DURATION_TOLERANCE_SEC = 0.75
DEFAULT_STATIC_CHECK_MAX_SAMPLES = 24
DEFAULT_STATIC_CHECK_MIN_SEGMENT_SEC = 6.0
DEFAULT_STATIC_CHECK_GAP_SEC = 5.0
DEFAULT_STATIC_CHECK_RENDERED_MAD_THRESHOLD = 0.25
DEFAULT_STATIC_CHECK_SOURCE_MAD_THRESHOLD = 2.0
REUSABLE_SOURCE_AUDIO_EVENT_TYPES = {"music", "applause", "intro", "outro", "sound", "sfx", "laughter"}


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


def _ffmpeg_filter_path(path: Path) -> str:
	return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _select_evenly_spaced(items: list[dict[str, Any]], max_count: int) -> list[dict[str, Any]]:
	if max_count <= 0 or not items:
		return []
	if len(items) <= max_count:
		return list(items)
	if max_count == 1:
		return [items[len(items) // 2]]
	selected: list[dict[str, Any]] = []
	seen: set[int] = set()
	for index in range(max_count):
		source_index = round(index * (len(items) - 1) / (max_count - 1))
		if source_index in seen:
			continue
		seen.add(source_index)
		selected.append(items[source_index])
	return selected


def _raw_upper_frame_bytes(path: Path, time_sec: float, width: int = 320, height: int = 180) -> bytes:
	result = subprocess.run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-ss",
		f"{max(0.0, time_sec):.3f}",
		"-i",
		str(path),
		"-frames:v",
		"1",
		"-vf",
		f"crop=iw:ih*0.70:0:0,scale={width}:{height}",
		"-pix_fmt",
		"rgb24",
		"-f",
		"rawvideo",
		"-",
	], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	return result.stdout


def _mean_abs_frame_delta(left: bytes, right: bytes) -> float:
	assert len(left) == len(right), "frame byte lengths differ"
	if not left:
		return 0.0
	return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def detect_static_video_range_mismatches(
	plan: dict[str, Any],
	rendered_video: Path,
	max_samples: int = DEFAULT_STATIC_CHECK_MAX_SAMPLES,
	min_segment_sec: float = DEFAULT_STATIC_CHECK_MIN_SEGMENT_SEC,
	gap_sec: float = DEFAULT_STATIC_CHECK_GAP_SEC,
	rendered_static_mad_threshold: float = DEFAULT_STATIC_CHECK_RENDERED_MAD_THRESHOLD,
	source_motion_mad_threshold: float = DEFAULT_STATIC_CHECK_SOURCE_MAD_THRESHOLD,
) -> dict[str, Any]:
	source_video = Path(str(plan["source_video"]))
	assert source_video.exists(), f"Missing source video: {source_video}"
	assert rendered_video.exists(), f"Missing rendered video: {rendered_video}"
	eligible = [
		segment
		for segment in plan.get("edit_segments") or []
		if segment.get("source_mode") == "video_range" and float(segment.get("duration_sec") or 0.0) >= min_segment_sec
	]
	checks: list[dict[str, Any]] = []
	failures: list[dict[str, Any]] = []
	for segment in _select_evenly_spaced(eligible, max_samples):
		duration = float(segment.get("duration_sec") or 0.0)
		local_start = min(1.0, max(0.1, duration * 0.15))
		local_gap = min(gap_sec, max(0.0, duration - local_start - 0.2))
		if local_gap < 2.0:
			continue
		target_a = float(segment["target_start_sec"]) + local_start
		target_b = target_a + local_gap
		source_a = float(segment["source_start_sec"]) + local_start
		source_b = source_a + local_gap
		rendered_delta = _mean_abs_frame_delta(
			_raw_upper_frame_bytes(rendered_video, target_a),
			_raw_upper_frame_bytes(rendered_video, target_b),
		)
		source_delta = _mean_abs_frame_delta(
			_raw_upper_frame_bytes(source_video, source_a),
			_raw_upper_frame_bytes(source_video, source_b),
		)
		item = {
			"segment_index": int(segment.get("segment_index") or 0),
			"turn_index": segment.get("turn_index"),
			"target_start_sec": round(target_a, 3),
			"target_end_sec": round(target_b, 3),
			"source_start_sec": round(source_a, 3),
			"source_end_sec": round(source_b, 3),
			"rendered_mad": round(rendered_delta, 6),
			"source_mad": round(source_delta, 6),
		}
		checks.append(item)
		if rendered_delta <= rendered_static_mad_threshold and source_delta >= source_motion_mad_threshold:
			failures.append({
				**item,
				"reason": "rendered_video_range_static_while_mapped_source_moves",
			})
	return {
		"schema_version": "worldview-china-static-video-range-check.v1",
		"status": "PASS" if not failures else "FAIL",
		"sample_count": len(checks),
		"failure_count": len(failures),
		"thresholds": {
			"min_segment_sec": min_segment_sec,
			"gap_sec": gap_sec,
			"rendered_static_mad_threshold": rendered_static_mad_threshold,
			"source_motion_mad_threshold": source_motion_mad_threshold,
		},
		"checks": checks,
		"failures": failures,
	}


def _filter_complex_line_for_segment(segment: dict[str, Any], label: str) -> str:
	source_mode = str(segment.get("source_mode") or "video_range")
	start = float(segment["source_start_sec"])
	end = float(segment["source_end_sec"])
	duration = float(segment.get("duration_sec") or max(0.0, end - start))
	if source_mode == "freeze_tail":
		frame_end = max(start + 0.05, start + min(0.2, duration))
		return (
			f"[0:v]trim=start={start:.6f}:end={frame_end:.6f},setpts=PTS-STARTPTS,"
			f"loop=loop=-1:size=1:start=0,trim=duration={duration:.6f},"
			f"setpts=PTS-STARTPTS,fps=30,format=yuv420p[{label}]"
		)
	return (
		f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,"
		f"fps=30,format=yuv420p[{label}]"
	)


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


def _non_dialogue_event_type(text: str) -> str | None:
	value = re.sub(r"\s+", " ", str(text or "")).strip().lower()
	if not value:
		return None
	match = re.fullmatch(r"\[(music|applause|silence|intro|outro|sound|sfx|laughter|noise|preroll)\]", value)
	if not match:
		return None
	label = match.group(1)
	if label == "noise":
		return "background_audio_unknown"
	return label


def _is_non_dialogue_text(text: str) -> bool:
	return _non_dialogue_event_type(text) is not None


def _normalize_source_turn_ranges(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
	ordered = sorted(turns, key=lambda item: (float(item["source_start_sec"]), float(item["source_end_sec"])))
	if not ordered:
		return []
	normalized: list[dict[str, Any]] = []
	first_start = float(ordered[0]["source_start_sec"])
	if first_start > 0.1:
		normalized.append({
			"turn_id": "source_preroll_0000",
			"turn_index": 0,
			"speaker": None,
			"source_start_sec": 0.0,
			"source_end_sec": first_start,
			"source_text": "[preroll]",
			"trim_candidates": [],
			"silence_ranges": [],
			"filler_ranges": [],
			"non_dialogue": True,
			"source_audio_event_type": "preroll",
			"reuse_source_audio": False,
			"synthetic": True,
		})
	for raw_turn in ordered:
		turn = dict(raw_turn)
		if normalized:
			previous = normalized[-1]
			previous_end = float(previous["source_end_sec"])
			start = float(turn["source_start_sec"])
			has_seen_dialogue = any(not item.get("non_dialogue") for item in normalized)
			if start > previous_end + 0.1 and not has_seen_dialogue:
				normalized.append({
					"turn_id": f"source_initial_gap_before_{turn['turn_id']}",
					"turn_index": int(turn["turn_index"]) - 1,
					"speaker": None,
					"source_start_sec": previous_end,
					"source_end_sec": start,
					"source_text": "[silence]",
					"trim_candidates": [],
					"silence_ranges": [],
					"filler_ranges": [],
					"non_dialogue": True,
					"source_audio_event_type": "silence",
					"reuse_source_audio": False,
					"synthetic": True,
				})
			elif start < previous_end:
				if previous.get("speaker") != turn.get("speaker"):
					previous["source_end_sec"] = max(float(previous["source_start_sec"]), start)
				else:
					turn["source_start_sec"] = previous_end
		if float(turn["source_end_sec"]) > float(turn["source_start_sec"]):
			normalized.append(turn)
	return normalized


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
		start_value = item.get("source_start", item.get("source_start_sec", item.get("start", item.get("start_sec"))))
		end_value = item.get("source_end", item.get("source_end_sec", item.get("end", item.get("end_sec"))))
		if start_value is None or end_value is None:
			continue
		start = _parse_time(start_value) - source_time_offset_sec
		end = _parse_time(end_value) - source_time_offset_sec
		if end <= start:
			continue
		speaker = str(item.get("speaker") or item.get("speaker_id") or "").strip()
		if speaker in {"0", "1"}:
			speaker = f"Speaker {speaker}"
		source_text = str(item.get("source_text") or item.get("text") or item.get("zh_text") or "")
		event_type = str(item.get("source_audio_event_type") or item.get("event_type") or "").strip() or _non_dialogue_event_type(source_text)
		reuse_source_audio_value = item.get("reuse_source_audio")
		if reuse_source_audio_value is None:
			reuse_source_audio = bool(event_type in REUSABLE_SOURCE_AUDIO_EVENT_TYPES)
		else:
			reuse_source_audio = bool(reuse_source_audio_value)
		turn = {
			"turn_id": _coerce_turn_id(item, index),
			"turn_index": _coerce_turn_index(item, index),
			"speaker": speaker,
			"source_start_sec": max(0.0, start),
			"source_end_sec": max(0.0, end),
			"source_text": source_text,
			"trim_candidates": item.get("trim_candidates") or [],
			"silence_ranges": item.get("silence_ranges") or [],
			"filler_ranges": item.get("filler_ranges") or item.get("low_value_ranges") or [],
		}
		if item.get("audio_turn_ids"):
			turn["audio_turn_ids"] = list(item.get("audio_turn_ids") or [])
		elif item.get("target_audio_turn_ids"):
			turn["audio_turn_ids"] = list(item.get("target_audio_turn_ids") or [])
		if item.get("audio_turn_id"):
			turn["audio_turn_id"] = str(item.get("audio_turn_id"))
		elif item.get("target_audio_turn_id"):
			turn["audio_turn_id"] = str(item.get("target_audio_turn_id"))
		turn["non_dialogue"] = bool(item.get("non_dialogue")) or event_type is not None
		turn["source_audio_event_type"] = event_type
		turn["reuse_source_audio"] = reuse_source_audio
		turns.append(turn)
	return _normalize_source_turn_ranges(turns)


def _load_audio_turns(path: Path) -> dict[str, dict[str, Any]]:
	data = _read_json(path)
	raw = data.get("turns") if isinstance(data, dict) else data if isinstance(data, list) else []
	by_id: dict[str, dict[str, Any]] = {}
	by_index: dict[str, dict[str, Any]] = {}
	ordered_turns: list[dict[str, Any]] = []
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
		ordered_turns.append(audio_turn)
	ordered_turns.sort(key=lambda item: (float(item["audio_start_sec"]), float(item["audio_end_sec"])))
	for index, audio_turn in enumerate(ordered_turns):
		if index + 1 < len(ordered_turns):
			next_start = float(ordered_turns[index + 1]["audio_start_sec"])
			visual_end = max(float(audio_turn["audio_start_sec"]) + 0.05, next_start)
		else:
			manifest_duration = float(data.get("duration_sec") or audio_turn["audio_end_sec"]) if isinstance(data, dict) else float(audio_turn["audio_end_sec"])
			visual_end = max(float(audio_turn["audio_end_sec"]), manifest_duration)
		audio_turn["visual_audio_end_sec"] = visual_end
		audio_turn["following_silence_held_by_current_speaker_sec"] = round(visual_end - float(audio_turn["audio_end_sec"]), 3)
		by_id[audio_turn["turn_id"]] = audio_turn
		by_index[str(audio_turn["turn_index"])] = audio_turn
	return {**{f"index:{key}": value for key, value in by_index.items()}, **by_id}


def _load_audio_turn_groups(path: Path) -> list[dict[str, Any]]:
	data = _read_json(path)
	raw = data.get("turns") if isinstance(data, dict) else data if isinstance(data, list) else []
	turns: list[dict[str, Any]] = []
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
		turns.append({
			"turn_id": _coerce_turn_id(item, index),
			"turn_index": _coerce_turn_index(item, index),
			"speaker": str(item.get("speaker") or "").strip(),
			"audio_start_sec": start,
			"audio_end_sec": end,
			"alignment_confidence": item.get("alignment_confidence") or item.get("match_confidence"),
		})
	turns.sort(key=lambda item: (float(item["audio_start_sec"]), float(item["audio_end_sec"])))
	groups: list[dict[str, Any]] = []
	for turn in turns:
		if groups and groups[-1].get("speaker") == turn.get("speaker"):
			group = groups[-1]
			group["audio_end_sec"] = max(float(group["audio_end_sec"]), float(turn["audio_end_sec"]))
			group["turn_ids"].append(turn["turn_id"])
			group["turn_indices"].append(turn["turn_index"])
			continue
		groups.append({
			"turn_id": f"audio_group_{len(groups) + 1:04d}",
			"turn_index": len(groups) + 1,
			"speaker": turn.get("speaker"),
			"audio_start_sec": float(turn["audio_start_sec"]),
			"audio_end_sec": float(turn["audio_end_sec"]),
			"alignment_confidence": turn.get("alignment_confidence"),
			"turn_ids": [turn["turn_id"]],
			"turn_indices": [turn["turn_index"]],
		})
	for index, group in enumerate(groups[:-1]):
		next_start = float(groups[index + 1]["audio_start_sec"])
		if next_start > float(group["audio_end_sec"]):
			group["visual_audio_end_sec"] = next_start
			group["following_silence_held_by_current_speaker_sec"] = round(next_start - float(group["audio_end_sec"]), 3)
		else:
			group["visual_audio_end_sec"] = max(float(group["audio_start_sec"]) + 0.05, next_start)
			group["following_silence_held_by_current_speaker_sec"] = 0.0
	if groups:
		groups[-1]["visual_audio_end_sec"] = groups[-1]["audio_end_sec"]
		groups[-1]["following_silence_held_by_current_speaker_sec"] = 0.0
	return groups


def _audio_turn_binding_keys(source_turn: dict[str, Any]) -> list[str]:
	raw_keys = source_turn.get("audio_turn_ids") or source_turn.get("target_audio_turn_ids") or []
	if isinstance(raw_keys, str):
		keys = [raw_keys]
	elif isinstance(raw_keys, list):
		keys = [str(item) for item in raw_keys if item is not None]
	else:
		keys = []
	single = source_turn.get("audio_turn_id") or source_turn.get("target_audio_turn_id")
	if single is not None:
		keys.append(str(single))
	cleaned: list[str] = []
	seen: set[str] = set()
	for key in keys:
		key = key.strip()
		if not key or key in seen:
			continue
		seen.add(key)
		cleaned.append(key)
	return cleaned


def _combine_bound_audio_turns(audio_turns: dict[str, dict[str, Any]], keys: list[str]) -> dict[str, Any] | None:
	selected: list[dict[str, Any]] = []
	for key in keys:
		candidate = audio_turns.get(key)
		if candidate is None and key.isdigit():
			candidate = audio_turns.get(f"index:{key}")
		if candidate is not None:
			selected.append(candidate)
	if not selected:
		return None
	selected.sort(key=lambda item: (float(item["audio_start_sec"]), float(item["audio_end_sec"])))
	speakers = [str(item.get("speaker") or "").strip() for item in selected if str(item.get("speaker") or "").strip()]
	speaker = speakers[0] if speakers and all(value == speakers[0] for value in speakers) else ""
	return {
		"turn_id": selected[0]["turn_id"] if len(selected) == 1 else f"bound_audio_{selected[0]['turn_id']}_{selected[-1]['turn_id']}",
		"turn_index": selected[0]["turn_index"],
		"speaker": speaker,
		"audio_start_sec": min(float(item["audio_start_sec"]) for item in selected),
		"audio_end_sec": max(float(item["audio_end_sec"]) for item in selected),
		"visual_audio_end_sec": float(selected[-1].get("visual_audio_end_sec") or selected[-1]["audio_end_sec"]),
		"alignment_confidence": selected[0].get("alignment_confidence"),
		"turn_ids": [item["turn_id"] for item in selected],
		"turn_indices": [item["turn_index"] for item in selected],
		"following_silence_held_by_current_speaker_sec": round(float(selected[-1].get("following_silence_held_by_current_speaker_sec") or 0.0), 3),
	}


def _select_source_turn_map(run_dir: Path, explicit_path: Path | None) -> Path:
	if explicit_path is not None:
		return explicit_path.resolve()
	candidates = [
		run_dir / "04-source-dialogue-turn-map/source_dialogue_turn_map.active.json",
	]
	for path in candidates:
		if path.exists():
			return path.resolve()
	return (run_dir / "04-source-dialogue-turn-map/source_dialogue_turn_map.active.json").resolve()


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
	min_extend_sec: float,
	max_turn_extension_sec: float,
	max_turn_extension_ratio: float,
	min_kept_segment_sec: float,
) -> dict[str, Any]:
	turn_start = float(turn["source_start_sec"])
	turn_end = float(turn["source_end_sec"])
	source_duration = turn_end - turn_start
	source_speaker = str(turn.get("speaker") or "").strip()
	non_dialogue = bool(turn.get("non_dialogue"))
	if audio_turn is None:
		target_duration = source_duration
		audio_start = None
		audio_end = None
		audio_speaker = None
	else:
		audio_start = float(audio_turn["audio_start_sec"])
		audio_end = float(audio_turn.get("visual_audio_end_sec", audio_turn["audio_end_sec"]))
		target_duration = max(0.0, audio_end - audio_start)
		audio_speaker = str(audio_turn.get("speaker") or "").strip()
	speaker_match = bool(non_dialogue or (audio_turn is not None and (not source_speaker or not audio_speaker or source_speaker == audio_speaker)))
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
	extension_needed = max(0.0, target_duration - kept_duration)
	extension_limit = max(max_turn_extension_sec, target_duration * max_turn_extension_ratio)
	extension_segments: list[dict[str, Any]] = []
	if audio_turn is not None and extension_needed >= min_extend_sec:
		hold_frame = max(turn_start, turn_end - min(0.05, max(0.001, source_duration / 2.0)))
		extension_segments.append({
			"start_sec": round(hold_frame, 3),
			"end_sec": round(hold_frame, 3),
			"duration_sec": round(extension_needed, 3),
			"reason": "extend_short_source_turn_to_audio_boundary",
			"source_mode": "freeze_tail",
		})
	output_duration = kept_duration + _range_duration([
		(0.0, float(item["duration_sec"]))
		for item in extension_segments
	])
	duration_delta = output_duration - target_duration
	protected_violations = [
		_round_range(max(cut[0], protected[0]), min(cut[1], protected[1]))
		for cut in cuts
		for protected in protected_ranges
		if _intersect_range(cut, protected) is not None
	]
	if (audio_turn is None and not non_dialogue) or not speaker_match:
		confidence = "low"
	elif abs(duration_delta) <= 0.5 and not protected_violations:
		confidence = "high" if _range_duration(cuts) == 0 and not extension_segments else "medium"
	else:
		confidence = "low"
	return {
		"turn_id": turn["turn_id"],
		"turn_index": turn["turn_index"],
		"speaker": turn.get("speaker"),
		"audio_speaker": audio_speaker,
		"speaker_match": speaker_match,
		"audio_turn_missing": audio_turn is None and not non_dialogue,
		"non_dialogue": non_dialogue,
		"source_audio_event_type": turn.get("source_audio_event_type"),
		"reuse_source_audio": bool(turn.get("reuse_source_audio")),
		"synthetic": bool(turn.get("synthetic")),
		"source_start_sec": round(turn_start, 3),
		"source_end_sec": round(turn_end, 3),
		"target_audio_start_sec": round(audio_start, 3) if audio_start is not None else None,
		"target_audio_end_sec": round(audio_end, 3) if audio_end is not None else None,
		"audio_turn_ids": list(audio_turn.get("turn_ids") or [audio_turn["turn_id"]]) if audio_turn is not None else [],
		"audio_turn_indices": list(audio_turn.get("turn_indices") or [audio_turn["turn_index"]]) if audio_turn is not None else [],
		"following_silence_held_by_current_speaker_sec": round(float(audio_turn.get("following_silence_held_by_current_speaker_sec") or 0.0), 3) if audio_turn is not None else 0.0,
		"source_duration_sec": round(source_duration, 3),
		"target_duration_sec": round(target_duration, 3),
		"trim_needed_sec": round(trim_needed, 3),
		"trimmed_duration_sec": round(_range_duration(cuts), 3),
		"kept_duration_sec": round(kept_duration, 3),
		"extended_duration_sec": round(_range_duration([(0.0, float(item["duration_sec"])) for item in extension_segments]), 3),
		"extension_policy_limit_sec": round(extension_limit, 3),
		"output_duration_sec": round(output_duration, 3),
		"duration_delta_vs_target_sec": round(duration_delta, 3),
		"kept_source_ranges": [_round_range(start, end) for start, end in kept],
		"trimmed_source_ranges": cut_reasons,
		"extension_segments": extension_segments,
		"extension_exceeds_policy": bool(extension_needed > extension_limit),
		"protected_range_violations": protected_violations,
		"confidence": confidence,
	}


def _rebalance_turn_plans_to_target(
	turn_plans: list[dict[str, Any]],
	tolerance_sec: float = 0.75,
	min_kept_segment_sec: float = DEFAULT_MIN_KEPT_SEGMENT_SEC,
) -> list[dict[str, Any]]:
	target_duration = sum(float(turn["target_duration_sec"]) for turn in turn_plans)
	current_duration = sum(float(turn.get("output_duration_sec", turn["kept_duration_sec"])) for turn in turn_plans)
	surplus = current_duration - target_duration
	if surplus > tolerance_sec:
		trim_needed = surplus
		overlong_turn_refs = [
			(
				float(turn.get("duration_delta_vs_target_sec") or 0.0),
				index,
			)
			for index, turn in enumerate(turn_plans)
			if float(turn.get("duration_delta_vs_target_sec") or 0.0) > 0.0 and not turn.get("extension_segments")
		]
		for turn_delta, turn_index in sorted(overlong_turn_refs, reverse=True):
			if trim_needed <= 0.001:
				break
			turn = turn_plans[turn_index]
			kept = [
				(float(item["start_sec"]), float(item["end_sec"]))
				for item in turn.get("kept_source_ranges") or []
			]
			if not kept:
				continue
			trim_budget = min(trim_needed, turn_delta)
			new_kept = list(kept)
			cuts = [
				(float(item["start_sec"]), float(item["end_sec"]))
				for item in turn.get("trimmed_source_ranges") or []
			]
			trimmed_here = 0.0
			for kept_index in range(len(new_kept) - 1, -1, -1):
				start, end = new_kept[kept_index]
				available = max(0.0, (end - start) - min_kept_segment_sec)
				if available <= 0:
					continue
				take = min(available, trim_budget - trimmed_here)
				if take <= 0:
					continue
				cut = (end - take, end)
				new_kept[kept_index] = (start, end - take)
				cuts.append(cut)
				trimmed_here += take
				if trimmed_here >= trim_budget - 0.001:
					break
			if trimmed_here <= 0:
				continue
			new_kept = [(start, end) for start, end in new_kept if end - start > 0.001]
			kept_duration = _range_duration(new_kept)
			cut_ranges = _merge_ranges(cuts)
			turn["kept_source_ranges"] = [_round_range(start, end) for start, end in new_kept]
			turn["trimmed_source_ranges"] = [
				{
					**_round_range(start, end),
					"reason": "global_surplus_tail_rebalance",
					"score": 0.0,
				}
				for start, end in cut_ranges
			]
			turn["trimmed_duration_sec"] = round(_range_duration(cut_ranges), 3)
			turn["kept_duration_sec"] = round(kept_duration, 3)
			turn["output_duration_sec"] = round(kept_duration, 3)
			turn["duration_delta_vs_target_sec"] = round(kept_duration - float(turn["target_duration_sec"]), 3)
			if turn.get("confidence") == "high":
				turn["confidence"] = "medium"
			turn["global_rebalance_trimmed_sec"] = round(float(turn.get("global_rebalance_trimmed_sec") or 0.0) + trimmed_here, 3)
			trim_needed -= trimmed_here
		return turn_plans
	restore_needed = target_duration - current_duration
	if restore_needed <= tolerance_sec:
		return turn_plans
	if any(turn.get("extension_segments") for turn in turn_plans):
		return turn_plans

	cut_refs: list[tuple[float, float, int, int]] = []
	for turn_index, turn in enumerate(turn_plans):
		for cut_index, cut in enumerate(turn.get("trimmed_source_ranges") or []):
			duration = float(cut["duration_sec"])
			if duration <= 0:
				continue
			score = float(cut.get("score") or 0.0)
			cut_refs.append((score, -duration, turn_index, cut_index))

	for _score, _negative_duration, turn_index, cut_index in sorted(cut_refs):
		if restore_needed <= tolerance_sec:
			break
		turn = turn_plans[turn_index]
		cuts = [dict(cut) for cut in (turn.get("trimmed_source_ranges") or [])]
		if cut_index >= len(cuts):
			continue
		cut = cuts[cut_index]
		cut_start = float(cut["start_sec"])
		cut_end = float(cut["end_sec"])
		cut_duration = max(0.0, cut_end - cut_start)
		if cut_duration <= 0:
			continue
		restore = min(cut_duration, restore_needed)
		if cut_duration - restore <= 0.05:
			cuts.pop(cut_index)
			restore = cut_duration
		else:
			cut_start += restore
			cut["start_sec"] = round(cut_start, 3)
			cut["duration_sec"] = round(cut_end - cut_start, 3)
			cut["global_rebalance_restored_sec"] = round(restore, 3)
			cuts[cut_index] = cut
		turn_start = float(turn["source_start_sec"])
		turn_end = float(turn["source_end_sec"])
		cut_ranges = [(float(item["start_sec"]), float(item["end_sec"])) for item in cuts]
		kept = _kept_segments_after_cuts((turn_start, turn_end), cut_ranges)
		kept_duration = _range_duration(kept)
		turn["trimmed_source_ranges"] = [
			{**item, **_round_range(float(item["start_sec"]), float(item["end_sec"]))}
			for item in cuts
		]
		turn["kept_source_ranges"] = [_round_range(start, end) for start, end in kept]
		turn["trimmed_duration_sec"] = round(_range_duration(cut_ranges), 3)
		turn["kept_duration_sec"] = round(kept_duration, 3)
		turn["output_duration_sec"] = round(kept_duration, 3)
		turn["duration_delta_vs_target_sec"] = round(kept_duration - float(turn["target_duration_sec"]), 3)
		if turn.get("confidence") != "low":
			turn["confidence"] = "medium"
		turn["global_rebalance_restored_sec"] = round(float(turn.get("global_rebalance_restored_sec") or 0.0) + restore, 3)
		restore_needed -= restore

	return turn_plans


def build_retime_plan(
	source_video: Path,
	source_turn_map: Path,
	turn_audio_timeline: Path,
	visual_activity_path: Path,
	output_path: Path,
	source_time_offset_sec: float = 0.0,
	turn_edge_protect_sec: float = DEFAULT_TURN_EDGE_PROTECT_SEC,
	min_trim_sec: float = DEFAULT_MIN_TRIM_SEC,
	min_extend_sec: float = DEFAULT_MIN_EXTEND_SEC,
	max_turn_extension_sec: float = DEFAULT_MAX_TURN_EXTENSION_SEC,
	max_turn_extension_ratio: float = DEFAULT_MAX_TURN_EXTENSION_RATIO,
	max_turn_boundary_drift_sec: float = DEFAULT_MAX_TURN_BOUNDARY_DRIFT_SEC,
	min_kept_segment_sec: float = DEFAULT_MIN_KEPT_SEGMENT_SEC,
	max_cuts_per_minute: float = DEFAULT_MAX_CUTS_PER_MINUTE,
) -> dict[str, Any]:
	source_turns = _load_source_turns(source_turn_map, source_time_offset_sec=source_time_offset_sec)
	audio_turns = _load_audio_turns(turn_audio_timeline)
	audio_groups = _load_audio_turn_groups(turn_audio_timeline)
	visual_activity = _read_json(visual_activity_path)
	protected_ranges = _ranges_from_dicts(visual_activity.get("protected_ranges") or [])
	turn_plans = []
	audio_group_cursor = 0
	for source_turn in source_turns:
		audio_turn = None
		if not source_turn.get("non_dialogue"):
			binding_keys = _audio_turn_binding_keys(source_turn)
			if binding_keys:
				audio_turn = _combine_bound_audio_turns(audio_turns, binding_keys)
			if audio_turn is None:
				source_speaker = str(source_turn.get("speaker") or "").strip()
				for group_index in range(audio_group_cursor, len(audio_groups)):
					candidate = audio_groups[group_index]
					if not source_speaker or not candidate.get("speaker") or candidate.get("speaker") == source_speaker:
						audio_turn = candidate
						audio_group_cursor = group_index + 1
						break
			if audio_turn is None:
				audio_turn = audio_turns.get(str(source_turn["turn_id"])) or audio_turns.get(f"index:{source_turn['turn_index']}")
		turn_plans.append(
			_plan_turn(
				source_turn,
				audio_turn,
				visual_activity,
				protected_ranges,
				turn_edge_protect_sec,
				min_trim_sec,
				min_extend_sec,
				max_turn_extension_sec,
				max_turn_extension_ratio,
				min_kept_segment_sec,
			)
		)
	turn_plans = _rebalance_turn_plans_to_target(turn_plans, min_kept_segment_sec=min_kept_segment_sec)
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
				"source_mode": "video_range",
				"non_dialogue": bool(turn.get("non_dialogue")),
				"source_audio_event_type": turn.get("source_audio_event_type"),
				"reuse_source_audio": bool(turn.get("reuse_source_audio")),
			})
			cursor += duration
		for extension in turn.get("extension_segments") or []:
			duration = float(extension["duration_sec"])
			edit_segments.append({
				"segment_index": len(edit_segments) + 1,
				"turn_id": turn["turn_id"],
				"turn_index": turn["turn_index"],
				"speaker": turn.get("speaker"),
				"source_start_sec": extension["start_sec"],
				"source_end_sec": extension["end_sec"],
				"target_start_sec": round(cursor, 3),
				"target_end_sec": round(cursor + duration, 3),
				"duration_sec": duration,
				"source_mode": extension.get("source_mode") or "freeze_tail",
				"non_dialogue": bool(turn.get("non_dialogue")),
				"source_audio_event_type": turn.get("source_audio_event_type"),
				"reuse_source_audio": False,
				"reason": extension.get("reason"),
			})
			cursor += duration
	trimmed_ranges = [
		(float(item["start_sec"]), float(item["end_sec"]))
		for turn in turn_plans
		for item in turn["trimmed_source_ranges"]
	]
	extended_duration = sum(float(turn.get("extended_duration_sec") or 0.0) for turn in turn_plans)
	protected_violations = [
		item
		for turn in turn_plans
		for item in turn["protected_range_violations"]
	]
	target_duration = sum(float(turn["target_duration_sec"]) for turn in turn_plans)
	min_kept = min((
		float(segment["duration_sec"])
		for segment in edit_segments
		if segment.get("source_mode") == "video_range"
	), default=0.0)
	final_duration = cursor
	cuts_per_minute = len(trimmed_ranges) / max(0.001, final_duration / 60.0)
	turn_boundary_drift_violations = [
		{
			"turn_id": turn["turn_id"],
			"turn_index": turn["turn_index"],
			"speaker": turn.get("speaker"),
			"duration_delta_vs_target_sec": turn.get("duration_delta_vs_target_sec"),
		}
		for turn in turn_plans
		if abs(float(turn.get("duration_delta_vs_target_sec") or 0.0)) > max_turn_boundary_drift_sec
	]
	audio_turn_missing = [
		{"turn_id": turn["turn_id"], "turn_index": turn["turn_index"], "speaker": turn.get("speaker")}
		for turn in turn_plans
		if turn.get("audio_turn_missing")
	]
	speaker_mismatches = [
		{
			"turn_id": turn["turn_id"],
			"turn_index": turn["turn_index"],
			"source_speaker": turn.get("speaker"),
			"audio_speaker": turn.get("audio_speaker"),
		}
		for turn in turn_plans
		if not turn.get("speaker_match")
	]
	extension_policy_violations = [
		{
			"turn_id": turn["turn_id"],
			"turn_index": turn["turn_index"],
			"speaker": turn.get("speaker"),
			"extended_duration_sec": turn.get("extended_duration_sec"),
		}
		for turn in turn_plans
		if turn.get("extension_exceeds_policy")
	]
	audio_start_offset_sec = 0.0
	for turn in turn_plans:
		if not turn.get("non_dialogue"):
			break
		audio_start_offset_sec += float(turn.get("output_duration_sec") or turn.get("kept_duration_sec") or 0.0)
	status = "pass"
	warnings = []
	if protected_violations:
		status = "fail"
	if abs(final_duration - target_duration) > max_turn_boundary_drift_sec:
		status = "fail"
		warnings.append("retimed video duration is not within boundary drift tolerance of target audio timeline")
	if turn_boundary_drift_violations:
		status = "fail"
		warnings.append("one or more turn boundaries drift beyond tolerance")
	if audio_turn_missing:
		status = "fail"
		warnings.append("one or more dialogue source turns did not match an audio turn")
	if speaker_mismatches:
		status = "fail"
		warnings.append("one or more source turns matched a different audio speaker")
	if extension_policy_violations:
		status = "fail"
		warnings.append("one or more short source turns require excessive freeze extension")
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
			"min_extend_sec": min_extend_sec,
			"max_turn_extension_sec": max_turn_extension_sec,
			"max_turn_extension_ratio": max_turn_extension_ratio,
			"max_turn_boundary_drift_sec": max_turn_boundary_drift_sec,
			"min_kept_segment_sec": min_kept_segment_sec,
			"max_cuts_per_minute": max_cuts_per_minute,
			"audio_turn_grouping": "consecutive_same_speaker_audio_turns_are_grouped_for_one_source_turn",
			"switch_alignment": "hold_current_speaker_visual_until_next_audio_speaker_starts",
			"short_source_turn_policy": "freeze_tail_until_target_audio_turn_boundary",
			"opening_non_dialogue_policy": "preserve_initial_preroll_and_explicit_music_or_silence_before_first_dialogue",
			"strategy": "trim long source turns and extend short source turns so every turn boundary matches the Chinese audio timeline",
		},
		"summary": {
			"turn_count": len(turn_plans),
			"edit_segment_count": len(edit_segments),
			"trimmed_range_count": len(trimmed_ranges),
			"target_duration_sec": round(target_duration, 3),
			"estimated_video_duration_sec": round(final_duration, 3),
			"duration_delta_vs_target_sec": round(final_duration - target_duration, 3),
			"trimmed_duration_sec": round(_range_duration(trimmed_ranges), 3),
			"extended_duration_sec": round(extended_duration, 3),
			"audio_start_offset_sec": round(audio_start_offset_sec, 3),
			"min_kept_segment_duration_sec": round(min_kept, 3),
			"cuts_per_minute": round(cuts_per_minute, 3),
			"protected_range_violation_count": len(protected_violations),
			"turn_boundary_drift_violation_count": len(turn_boundary_drift_violations),
			"audio_turn_missing_count": len(audio_turn_missing),
			"speaker_mismatch_count": len(speaker_mismatches),
			"extension_policy_violation_count": len(extension_policy_violations),
		},
		"turns": turn_plans,
		"edit_segments": edit_segments,
		"protected_range_violations": protected_violations,
		"turn_boundary_drift_violations": turn_boundary_drift_violations,
		"audio_turn_missing": audio_turn_missing,
		"speaker_mismatches": speaker_mismatches,
		"extension_policy_violations": extension_policy_violations,
	}
	_write_json(output_path, plan)
	return plan


def render_retimed_video(plan_path: Path, output_video: Path, video_encoder: str = "libx264") -> dict[str, Any]:
	plan = _read_json(plan_path)
	source_video = Path(str(plan["source_video"]))
	assert source_video.exists(), f"Missing source video: {source_video}"
	output_video.parent.mkdir(parents=True, exist_ok=True)
	filter_script = output_video.with_suffix(".filter_complex.txt")
	edit_segments = [
		segment
		for segment in plan.get("edit_segments") or []
		if float(segment.get("duration_sec") or 0.0) > 0.0
	]
	assert edit_segments, "retime edit plan has no renderable edit segments"
	filter_labels: list[str] = []
	filter_lines: list[str] = []
	freeze_segment_count = 0
	for index, segment in enumerate(edit_segments):
		label = f"v{index}"
		filter_labels.append(f"[{label}]")
		if str(segment.get("source_mode") or "video_range") == "freeze_tail":
			freeze_segment_count += 1
		filter_lines.append(_filter_complex_line_for_segment(segment, label))
	filter_lines.append(f"{''.join(filter_labels)}concat=n={len(filter_labels)}:v=1:a=0,format=yuv420p[vout]")
	filter_script.write_text(";\n".join(filter_lines) + "\n", encoding="utf-8")
	plan_target_duration = float((plan.get("summary") or {}).get("target_duration_sec") or 0.0)
	if output_video.exists() and plan_target_duration:
		existing_duration = _duration(output_video)
		existing_delta = existing_duration - plan_target_duration
		if abs(existing_delta) <= DEFAULT_RENDERED_DURATION_TOLERANCE_SEC:
			static_check = detect_static_video_range_mismatches(plan, output_video)
			if static_check["status"] != "PASS":
				raise AssertionError(
					"Existing retimed video contains static video_range spans while mapped source ranges move: "
					f"{static_check['failure_count']} failures"
				)
			return {
				"schema_version": "worldview-china-turn-retime-render.v1",
				"retime_edit_plan": str(plan_path),
				"filter_complex_script": str(filter_script),
				"render_strategy": "existing_valid_retimed_video_reused",
				"retimed_video": str(output_video),
				"retimed_video_sha256": _sha256(output_video),
				"duration_sec": round(existing_duration, 3),
				"target_duration_sec": round(plan_target_duration, 3),
				"duration_delta_vs_plan_sec": round(existing_delta, 3),
				"duration_tolerance_sec": DEFAULT_RENDERED_DURATION_TOLERANCE_SEC,
				"edit_segment_count": len(plan.get("edit_segments") or []),
				"freeze_segment_count": freeze_segment_count,
				"static_video_range_check": static_check,
			}
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
		"-i",
		str(source_video),
		"-filter_complex_script",
		str(filter_script),
		"-map",
		"[vout]",
		"-an",
		"-r",
		"30",
		"-fps_mode",
		"cfr",
		*encoder_args,
		"-movflags",
		"+faststart",
		str(tmp),
	])
	if output_video.exists():
		output_video.unlink()
	tmp.replace(output_video)
	duration = _duration(output_video)
	duration_delta = duration - plan_target_duration
	if plan_target_duration and duration_delta > DEFAULT_RENDERED_DURATION_TOLERANCE_SEC:
		trimmed = output_video.with_suffix(output_video.suffix + ".duration_trimmed.mp4")
		if trimmed.exists():
			trimmed.unlink()
		_run([
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-i",
			str(output_video),
			"-t",
			f"{plan_target_duration:.3f}",
			"-map",
			"0:v:0",
			"-an",
			"-c:v",
			"copy",
			"-movflags",
			"+faststart",
			str(trimmed),
		])
		trimmed.replace(output_video)
		duration = _duration(output_video)
		duration_delta = duration - plan_target_duration
	if plan_target_duration and abs(duration_delta) > DEFAULT_RENDERED_DURATION_TOLERANCE_SEC:
		raise AssertionError(
			"Rendered retimed video duration does not match retime plan target: "
			f"rendered={duration:.3f}s target={plan_target_duration:.3f}s delta={duration_delta:.3f}s"
		)
	static_check = detect_static_video_range_mismatches(plan, output_video)
	if static_check["status"] != "PASS":
		raise AssertionError(
			"Rendered retimed video contains static video_range spans while mapped source ranges move: "
			f"{static_check['failure_count']} failures"
		)
	return {
		"schema_version": "worldview-china-turn-retime-render.v1",
		"retime_edit_plan": str(plan_path),
		"filter_complex_script": str(filter_script),
		"render_strategy": "filter_complex_trim_setpts_concat",
		"retimed_video": str(output_video),
		"retimed_video_sha256": _sha256(output_video),
		"duration_sec": round(duration, 3),
		"target_duration_sec": round(plan_target_duration, 3),
		"duration_delta_vs_plan_sec": round(duration_delta, 3),
		"duration_tolerance_sec": DEFAULT_RENDERED_DURATION_TOLERANCE_SEC,
		"edit_segment_count": len(plan.get("edit_segments") or []),
		"freeze_segment_count": freeze_segment_count,
		"static_video_range_check": static_check,
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
	parser.add_argument("--min-extend-sec", type=float, default=DEFAULT_MIN_EXTEND_SEC)
	parser.add_argument("--max-turn-extension-sec", type=float, default=DEFAULT_MAX_TURN_EXTENSION_SEC)
	parser.add_argument("--max-turn-extension-ratio", type=float, default=DEFAULT_MAX_TURN_EXTENSION_RATIO)
	parser.add_argument("--max-turn-boundary-drift-sec", type=float, default=DEFAULT_MAX_TURN_BOUNDARY_DRIFT_SEC)
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
	source_turn_map = _select_source_turn_map(run_dir, args.source_turn_map)
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
		min_extend_sec=args.min_extend_sec,
		max_turn_extension_sec=args.max_turn_extension_sec,
		max_turn_extension_ratio=args.max_turn_extension_ratio,
		max_turn_boundary_drift_sec=args.max_turn_boundary_drift_sec,
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
