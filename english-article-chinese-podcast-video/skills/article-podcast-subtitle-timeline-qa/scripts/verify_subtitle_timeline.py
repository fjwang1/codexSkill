#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SRT_MANIFEST_TOLERANCE_SEC = 0.04
VIDEO_DURATION_TOLERANCE_SEC = 0.75
CHUNK_START_OK_EARLY_SEC = -0.25
CHUNK_START_OK_LATE_SEC = 0.08
CHUNK_START_NEEDS_FIX_EARLY_SEC = -0.45
CHUNK_START_NEEDS_FIX_LATE_SEC = 0.18
CHUNK_END_OK_EARLY_SEC = -0.10
CHUNK_END_OK_LATE_SEC = 0.45
CHUNK_END_NEEDS_FIX_EARLY_SEC = -0.25
CHUNK_END_NEEDS_FIX_LATE_SEC = 0.75
CUE_MID_NEEDS_FIX_SEC = 0.80
CUE_MID_FAIL_SEC = 1.20


@dataclass(frozen=True)
class SrtCue:
	index: int
	start_sec: float
	end_sec: float
	text: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	h = hashlib.sha256()
	with path.open("rb") as f:
		for block in iter(lambda: f.read(1024 * 1024), b""):
			h.update(block)
	return h.hexdigest()


def _ffprobe(path: Path) -> dict[str, Any]:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration:stream=index,codec_type,codec_name,width,height",
		"-of",
		"json",
		str(path),
	])
	return json.loads(result.stdout)


def _duration(path: Path) -> float:
	info = _ffprobe(path)
	return float(info.get("format", {}).get("duration") or 0.0)


def _status(results: list[dict[str, Any]]) -> str:
	if any(item["status"] == "FAIL" for item in results):
		return "FAIL"
	if any(item["status"] == "NEEDS_FIX" for item in results):
		return "NEEDS_FIX"
	if any(item["status"] == "WARN" for item in results):
		return "PASS_WITH_WARNINGS"
	return "PASS"


def _check_delta(delta: float, ok_min: float, ok_max: float, fix_min: float, fix_max: float) -> str:
	if ok_min <= delta <= ok_max:
		return "PASS"
	if fix_min <= delta <= fix_max:
		return "WARN"
	return "NEEDS_FIX"


def _parse_timecode(value: str) -> float:
	match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", value.strip())
	if not match:
		raise ValueError(f"Invalid SRT timecode: {value}")
	hour, minute, second, ms = (int(part) for part in match.groups())
	return hour * 3600 + minute * 60 + second + ms / 1000


def _parse_srt(path: Path) -> list[SrtCue]:
	text = path.read_text(encoding="utf-8", errors="replace").strip()
	if not text:
		return []
	cues: list[SrtCue] = []
	for block in re.split(r"\n\s*\n", text):
		lines = [line.strip() for line in block.splitlines() if line.strip()]
		if len(lines) < 3:
			continue
		try:
			index = int(lines[0])
		except ValueError:
			continue
		if "-->" not in lines[1]:
			continue
		start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
		visible = " ".join(lines[2:]).strip()
		cues.append(SrtCue(index=index, start_sec=_parse_timecode(start_raw), end_sec=_parse_timecode(end_raw), text=visible))
	return cues


def _load_pcm16(path: Path) -> tuple[list[float], int]:
	with wave.open(str(path), "rb") as wav:
		channels = wav.getnchannels()
		sample_width = wav.getsampwidth()
		sample_rate = wav.getframerate()
		frames = wav.readframes(wav.getnframes())
	if sample_width != 2:
		raise ValueError(f"Only 16-bit PCM wav is supported for energy QA: {path}")
	values = array("h")
	values.frombytes(frames)
	if channels > 1:
		mono: list[float] = []
		for i in range(0, len(values), channels):
			mono.append(sum(values[i:i + channels]) / channels)
		return mono, sample_rate
	return [float(value) for value in values], sample_rate


def _percentile(values: list[float], percentile: float) -> float:
	if not values:
		return 0.0
	ordered = sorted(values)
	index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
	return ordered[index]


def _detect_speech_bounds(path: Path, frame_ms: float = 20.0) -> dict[str, float | int]:
	samples, sample_rate = _load_pcm16(path)
	if not samples:
		return {"onset_sec": 0.0, "offset_sec": 0.0, "duration_sec": 0.0, "threshold": 0.0, "max_rms": 0.0}
	frame_size = max(1, int(sample_rate * frame_ms / 1000))
	rms_values: list[float] = []
	for start in range(0, len(samples), frame_size):
		frame = samples[start:start + frame_size]
		if not frame:
			continue
		rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame))
		rms_values.append(rms)
	duration = len(samples) / sample_rate
	if not rms_values:
		return {"onset_sec": 0.0, "offset_sec": duration, "duration_sec": duration, "threshold": 0.0, "max_rms": 0.0}
	max_rms = max(rms_values)
	noise_floor = _percentile(rms_values, 0.10)
	threshold = max(120.0, noise_floor * 2.8, max_rms * 0.035)
	mask = [value >= threshold for value in rms_values]
	min_run = 3
	first = 0
	for idx in range(0, len(mask)):
		if sum(mask[idx:idx + min_run]) >= 2:
			first = idx
			break
	else:
		first = 0
	last = len(mask) - 1
	for idx in range(len(mask) - 1, -1, -1):
		window_start = max(0, idx - min_run + 1)
		if sum(mask[window_start:idx + 1]) >= 2:
			last = idx
			break
	onset = max(0.0, first * frame_ms / 1000 - 0.03)
	offset = min(duration, (last + 1) * frame_ms / 1000 + 0.03)
	return {
		"onset_sec": round(onset, 3),
		"offset_sec": round(offset, 3),
		"duration_sec": round(duration, 3),
		"threshold": round(threshold, 2),
		"max_rms": round(max_rms, 2),
	}


def _cue_source_times(cue: dict[str, Any], speed: float) -> tuple[float, float]:
	return float(cue["start_sec"]) * speed, float(cue["end_sec"]) * speed


def _normalize_rel(path_value: str) -> str:
	return path_value.replace("\\", "/").lstrip("./")


def _alignment_key(item: dict[str, Any], fallback_index: int) -> str:
	if item.get("cue_index") is not None:
		return f"cue:{item['cue_index']}"
	if item.get("turn_id"):
		return f"turn_id:{item['turn_id']}"
	if item.get("turn_index") is not None:
		return f"turn:{item['turn_index']}"
	if item.get("wav"):
		return f"wav:{_normalize_rel(str(item['wav']))}"
	return f"item:{fallback_index}"


def _prepare_alignment_items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for index, raw in enumerate(raw_items, start=1):
		item = dict(raw)
		item["_qa_index"] = index
		item["_qa_key"] = _alignment_key(item, index)
		items.append(item)
	return items


def _find_alignment_item_for_cue(cue: dict[str, Any], items: list[dict[str, Any]], speed: float) -> dict[str, Any] | None:
	source_cue_index = cue.get("source_cue_index")
	if source_cue_index is not None:
		for item in items:
			if str(item.get("cue_index")) == str(source_cue_index):
				return item
	source_turn_id = cue.get("source_turn_id")
	if source_turn_id:
		for item in items:
			if str(item.get("turn_id") or "") == str(source_turn_id):
				return item
		match = re.search(r"(\d+)", str(source_turn_id))
		if match:
			source_turn_index = int(match.group(1))
			candidates = [item for item in items if int(item.get("turn_index") or -1) == source_turn_index]
			if len(candidates) == 1:
				return candidates[0]
	source_turn_index = cue.get("source_turn_index") or cue.get("turn_index")
	if source_turn_index is not None:
		candidates = [item for item in items if str(item.get("turn_index")) == str(source_turn_index)]
		if len(candidates) == 1:
			return candidates[0]
	start, end = _cue_source_times(cue, speed)
	mid = (start + end) / 2
	for item in items:
		if float(item["start_sec"]) - 0.2 <= mid <= float(item["end_sec"]) + 0.2:
			return item
	return None


def _char_len(text: str) -> int:
	return max(1, len(re.sub(r"\s+", "", text)))


def _build_report(project_dir: Path, data: dict[str, Any]) -> str:
	summary = data["summary"]
	aggregate = data.get("aggregate_offsets", {})
	lines = [
		"# 字幕时间线逐句 QA 报告",
		"",
		f"状态：{summary['status']}",
		"",
		"## 总览",
		"",
		f"- 项目：`{project_dir}`",
		f"- 对齐模式：{summary['alignment_mode']}",
		f"- 播放速度：{summary['playback_speed_factor']}x",
		f"- 音频时长：{summary['audio_duration_sec']:.3f}s",
		f"- 视频时长：{summary.get('video_duration_sec', 0):.3f}s",
		f"- 字幕 cue 数：{summary['cue_count']}",
		f"- 对齐项数：{summary['alignment_item_count']}",
		f"- 对齐项问题数：{summary['alignment_issue_count']}",
		f"- cue 问题数：{summary['cue_issue_count']}",
		f"- cue start median：{aggregate.get('cue_start_delta_median_sec', 0):+.3f}s",
		f"- cue end median：{aggregate.get('cue_end_delta_median_sec', 0):+.3f}s",
		"",
		"## Gate 检查",
		"",
	]
	for item in data["timeline_checks"]:
		lines.append(f"- {item['status']}: {item['message']}")
	lines.extend(["", "## ASR 对齐项边界问题", ""])
	alignment_issues = [item for item in data["alignment_checks"] if item["status"] != "PASS"]
	if not alignment_issues:
		lines.append("- PASS: ASR 对齐项边界未发现明显早/晚问题")
	else:
		for item in alignment_issues[:40]:
			if "start_delta_sec" in item and "end_delta_sec" in item:
				lines.append(
					f"- {item['status']}: {item['alignment_key']} turn {item.get('turn_index')} {item.get('speaker') or item.get('role')} "
					f"start_delta={item['start_delta_sec']:+.3f}s end_delta={item['end_delta_sec']:+.3f}s "
					f"`{item.get('text_preview', '')}`"
				)
			else:
				lines.append(
					f"- {item['status']}: {item.get('alignment_key')} turn {item.get('turn_index')} {item.get('speaker') or item.get('role')} "
					f"{item.get('message', 'alignment issue')} `{item.get('text_preview', '')}`"
				)
		if len(alignment_issues) > 40:
			lines.append(f"- ... 还有 {len(alignment_issues) - 40} 个对齐项问题，见 JSON")
	lines.extend(["", "## 字幕 Cue 偏移问题", ""])
	cue_issues = [item for item in data["cue_checks"] if item["status"] in {"NEEDS_FIX", "FAIL"}]
	if not cue_issues:
		lines.append("- PASS: 字幕 cue 相对 ASR 时间轴未超过阈值")
	else:
		for item in cue_issues[:60]:
			if "start_delta_sec" in item and "end_delta_sec" in item:
				lines.append(
					f"- {item['status']}: cue {item['cue_index']} {item.get('alignment_key')} "
					f"start_delta={item['start_delta_sec']:+.3f}s end_delta={item['end_delta_sec']:+.3f}s `{item.get('text', '')}`"
				)
			else:
				lines.append(f"- {item['status']}: cue {item.get('cue_index')} {item.get('message', 'cue issue')} `{item.get('text', '')}`")
		if len(cue_issues) > 60:
			lines.append(f"- ... 还有 {len(cue_issues) - 60} 个 cue 问题，见 JSON")
	lines.extend([
		"",
		"## 解释",
		"",
		"- `start_delta_sec > 0` 表示字幕晚于检测到的语音开头；`< 0` 表示字幕提前。",
		"- `end_delta_sec < 0` 表示字幕早于检测到的语音结尾消失；`> 0` 表示字幕滞留。",
		"- 本报告以 `audio/dialogue_timeline.json` 的 ASR/forced-alignment 时间为基准；如果基准本身错误，应回到音频对齐 gate。",
	])
	return "\n".join(lines) + "\n"


def _verify_legacy_chunk_manifest(project_dir: Path, asr_json: Path | None = None) -> dict[str, Any]:
	video_dir = project_dir / "video"
	audio_path = project_dir / "audio" / "final_podcast.wav"
	tts_path = project_dir / "audio" / "tts_manifest.json"
	subtitle_manifest_path = video_dir / "subtitle_manifest.json"
	srt_path = video_dir / "final_subtitles.srt"
	video_path = video_dir / "final_video.mp4"
	if not audio_path.exists():
		raise FileNotFoundError(audio_path)
	if not tts_path.exists():
		raise FileNotFoundError(tts_path)
	if not subtitle_manifest_path.exists():
		raise FileNotFoundError(subtitle_manifest_path)
	if not srt_path.exists():
		raise FileNotFoundError(srt_path)

	tts_manifest = _read_json(tts_path)
	subtitle_manifest = _read_json(subtitle_manifest_path)
	chunks = list(tts_manifest.get("chunks") or [])
	cues = list(subtitle_manifest.get("cues") or [])
	speed = float(subtitle_manifest.get("playback_speed_factor") or 1.0)
	alignment_mode = "energy_plus_manifest_estimate"
	if asr_json:
		alignment_mode = "energy_plus_manifest_estimate_with_external_asr_json_present"
	srt_cues = _parse_srt(srt_path)
	audio_duration = _duration(audio_path)
	video_duration = _duration(video_path) if video_path.exists() else 0.0

	timeline_checks: list[dict[str, Any]] = []
	if len(srt_cues) == len(cues):
		timeline_checks.append({"status": "PASS", "message": f"SRT cue count matches subtitle_manifest: {len(cues)}"})
	else:
		timeline_checks.append({"status": "FAIL", "message": f"SRT cue count {len(srt_cues)} != subtitle_manifest cue count {len(cues)}"})
	max_srt_delta = 0.0
	for srt_cue, cue in zip(srt_cues, cues):
		max_srt_delta = max(max_srt_delta, abs(srt_cue.start_sec - float(cue["start_sec"])), abs(srt_cue.end_sec - float(cue["end_sec"])))
	if max_srt_delta <= SRT_MANIFEST_TOLERANCE_SEC:
		timeline_checks.append({"status": "PASS", "message": f"SRT cue times match subtitle_manifest within {max_srt_delta:.3f}s"})
	else:
		timeline_checks.append({"status": "FAIL", "message": f"SRT cue times differ from subtitle_manifest by up to {max_srt_delta:.3f}s"})
	if video_path.exists():
		expected_video_duration = audio_duration / speed if speed else audio_duration
		duration_delta = video_duration - expected_video_duration
		if abs(duration_delta) <= VIDEO_DURATION_TOLERANCE_SEC:
			timeline_checks.append({"status": "PASS", "message": f"Video duration matches audio/speed: delta={duration_delta:+.3f}s"})
		else:
			timeline_checks.append({"status": "FAIL", "message": f"Video duration mismatch: video={video_duration:.3f}s expected={expected_video_duration:.3f}s delta={duration_delta:+.3f}s"})
	if cues:
		last_cue_end = float(cues[-1]["end_sec"])
		if video_duration and abs(video_duration - last_cue_end) <= 1.5:
			timeline_checks.append({"status": "PASS", "message": f"Last subtitle cue reaches video end: last={last_cue_end:.3f}s video={video_duration:.3f}s"})
		elif video_duration:
			timeline_checks.append({"status": "NEEDS_FIX", "message": f"Last subtitle cue does not reach video end: last={last_cue_end:.3f}s video={video_duration:.3f}s"})

	bounds_by_wav: dict[str, dict[str, float | int]] = {}
	for chunk in chunks:
		wav_value = str(chunk.get("wav") or "")
		if not wav_value:
			continue
		wav_path = project_dir / wav_value
		if not wav_path.exists():
			continue
		bounds_by_wav[_normalize_rel(wav_value)] = _detect_speech_bounds(wav_path)

	cues_by_chunk: dict[str, list[dict[str, Any]]] = {}
	for cue in cues:
		chunk = _find_chunk_for_cue(cue, chunks, speed)
		if not chunk:
			continue
		key = _normalize_rel(str(chunk["wav"]))
		cues_by_chunk.setdefault(key, []).append(cue)

	chunk_checks: list[dict[str, Any]] = []
	for chunk_index, chunk in enumerate(chunks, start=1):
		key = _normalize_rel(str(chunk.get("wav") or ""))
		chunk_cues = sorted(cues_by_chunk.get(key, []), key=lambda item: float(item["start_sec"]))
		if not chunk_cues:
			chunk_checks.append({
				"status": "FAIL",
				"chunk_index": chunk_index,
				"turn_index": chunk.get("turn_index"),
				"role": chunk.get("role"),
				"message": "No subtitle cues mapped to chunk",
				"text_preview": str(chunk.get("text") or "")[:60],
			})
			continue
		bounds = bounds_by_wav.get(key)
		if not bounds:
			chunk_checks.append({
				"status": "FAIL",
				"chunk_index": chunk_index,
				"turn_index": chunk.get("turn_index"),
				"role": chunk.get("role"),
				"message": "Missing wav bounds",
				"text_preview": str(chunk.get("text") or "")[:60],
			})
			continue
		chunk_start = float(chunk["start_sec"])
		speech_onset = chunk_start + float(bounds["onset_sec"])
		speech_offset = chunk_start + float(bounds["offset_sec"])
		first_cue_start = min(_cue_source_times(cue, speed)[0] for cue in chunk_cues)
		last_cue_end = max(_cue_source_times(cue, speed)[1] for cue in chunk_cues)
		start_delta = first_cue_start - speech_onset
		end_delta = last_cue_end - speech_offset
		start_status = _check_delta(start_delta, CHUNK_START_OK_EARLY_SEC, CHUNK_START_OK_LATE_SEC, CHUNK_START_NEEDS_FIX_EARLY_SEC, CHUNK_START_NEEDS_FIX_LATE_SEC)
		end_status = _check_delta(end_delta, CHUNK_END_OK_EARLY_SEC, CHUNK_END_OK_LATE_SEC, CHUNK_END_NEEDS_FIX_EARLY_SEC, CHUNK_END_NEEDS_FIX_LATE_SEC)
		status = "PASS"
		if "NEEDS_FIX" in {start_status, end_status}:
			status = "NEEDS_FIX"
		elif "WARN" in {start_status, end_status}:
			status = "WARN"
		chunk_checks.append({
			"status": status,
			"chunk_index": chunk_index,
			"turn_index": chunk.get("turn_index"),
			"chunk_index_in_turn": chunk.get("chunk_index"),
			"role": chunk.get("role"),
			"wav": key,
			"speech_onset_1x_sec": round(speech_onset, 3),
			"speech_offset_1x_sec": round(speech_offset, 3),
			"first_cue_start_1x_sec": round(first_cue_start, 3),
			"last_cue_end_1x_sec": round(last_cue_end, 3),
			"start_delta_sec": round(start_delta, 3),
			"end_delta_sec": round(end_delta, 3),
			"start_status": start_status,
			"end_status": end_status,
			"cue_count": len(chunk_cues),
			"text_preview": str(chunk.get("text") or "")[:80],
		})

	cue_checks: list[dict[str, Any]] = []
	for chunk_index, chunk in enumerate(chunks, start=1):
		key = _normalize_rel(str(chunk.get("wav") or ""))
		chunk_cues = sorted(cues_by_chunk.get(key, []), key=lambda item: float(item["start_sec"]))
		if not chunk_cues:
			continue
		bounds = bounds_by_wav.get(key)
		if not bounds:
			continue
		chunk_start = float(chunk["start_sec"])
		speech_onset = chunk_start + float(bounds["onset_sec"])
		speech_offset = chunk_start + float(bounds["offset_sec"])
		speech_duration = max(0.1, speech_offset - speech_onset)
		total_chars = sum(_char_len(str(cue.get("display_text") or cue.get("text") or "")) for cue in chunk_cues)
		cursor_chars = 0
		for cue in chunk_cues:
			text = str(cue.get("display_text") or cue.get("text") or "")
			chars = _char_len(text)
			expected_start = speech_onset + speech_duration * (cursor_chars / max(1, total_chars))
			expected_end = speech_onset + speech_duration * ((cursor_chars + chars) / max(1, total_chars))
			expected_mid = (expected_start + expected_end) / 2
			actual_start, actual_end = _cue_source_times(cue, speed)
			actual_mid = (actual_start + actual_end) / 2
			delta = actual_mid - expected_mid
			status = "PASS"
			if abs(delta) > CUE_MID_FAIL_SEC:
				status = "FAIL"
			elif abs(delta) > CUE_MID_NEEDS_FIX_SEC:
				status = "NEEDS_FIX"
			elif abs(delta) > 0.50:
				status = "WARN"
			cue_checks.append({
				"status": status,
				"cue_index": cue.get("index"),
				"chunk_index": chunk_index,
				"turn_index": chunk.get("turn_index"),
				"role": cue.get("role") or chunk.get("role"),
				"text": text,
				"actual_start_1x_sec": round(actual_start, 3),
				"actual_end_1x_sec": round(actual_end, 3),
				"expected_mid_1x_sec": round(expected_mid, 3),
				"actual_mid_1x_sec": round(actual_mid, 3),
				"estimated_mid_delta_sec": round(delta, 3),
			})
			cursor_chars += chars

	all_results = [*timeline_checks, *chunk_checks, *cue_checks]
	status = _status(all_results)
	chunk_issue_count = sum(1 for item in chunk_checks if item["status"] != "PASS")
	cue_issue_count = sum(1 for item in cue_checks if item["status"] in {"NEEDS_FIX", "FAIL"})
	chunk_start_deltas = [float(item["start_delta_sec"]) for item in chunk_checks if "start_delta_sec" in item]
	chunk_end_deltas = [float(item["end_delta_sec"]) for item in chunk_checks if "end_delta_sec" in item]
	cue_mid_deltas = [float(item["estimated_mid_delta_sec"]) for item in cue_checks if "estimated_mid_delta_sec" in item]
	def median(values: list[float]) -> float:
		return round(statistics.median(values), 3) if values else 0.0
	def p90_abs(values: list[float]) -> float:
		return round(_percentile([abs(value) for value in values], 0.90), 3) if values else 0.0
	data: dict[str, Any] = {
		"schema_version": "article-podcast-subtitle-timeline-qa.v1",
		"summary": {
			"status": status,
			"alignment_mode": alignment_mode,
			"playback_speed_factor": speed,
			"audio_duration_sec": round(audio_duration, 3),
			"video_duration_sec": round(video_duration, 3),
			"cue_count": len(cues),
			"srt_cue_count": len(srt_cues),
			"chunk_count": len(chunks),
			"chunk_issue_count": chunk_issue_count,
			"cue_issue_count": cue_issue_count,
			"residual_risk": "Cue-level checks use text-proportional estimates unless ASR/forced alignment is supplied.",
		},
		"inputs": {
			"project_dir": str(project_dir),
			"audio": "audio/final_podcast.wav",
			"tts_manifest": "audio/tts_manifest.json",
			"subtitle_manifest": "video/subtitle_manifest.json",
			"srt": "video/final_subtitles.srt",
			"video": "video/final_video.mp4" if video_path.exists() else None,
			"asr_json": str(asr_json) if asr_json else None,
		},
		"hashes": {
			"audio_sha256": _sha256(audio_path),
			"tts_manifest_sha256": _sha256(tts_path),
			"subtitle_manifest_sha256": _sha256(subtitle_manifest_path),
			"srt_sha256": _sha256(srt_path),
			"video_sha256": _sha256(video_path) if video_path.exists() else None,
		},
		"thresholds": {
			"srt_manifest_tolerance_sec": SRT_MANIFEST_TOLERANCE_SEC,
			"video_duration_tolerance_sec": VIDEO_DURATION_TOLERANCE_SEC,
			"chunk_start_ok_sec": [CHUNK_START_OK_EARLY_SEC, CHUNK_START_OK_LATE_SEC],
			"chunk_start_needs_fix_sec": [CHUNK_START_NEEDS_FIX_EARLY_SEC, CHUNK_START_NEEDS_FIX_LATE_SEC],
			"chunk_end_ok_sec": [CHUNK_END_OK_EARLY_SEC, CHUNK_END_OK_LATE_SEC],
			"chunk_end_needs_fix_sec": [CHUNK_END_NEEDS_FIX_EARLY_SEC, CHUNK_END_NEEDS_FIX_LATE_SEC],
			"cue_mid_needs_fix_sec": CUE_MID_NEEDS_FIX_SEC,
			"cue_mid_fail_sec": CUE_MID_FAIL_SEC,
		},
		"aggregate_offsets": {
			"chunk_start_delta_median_sec": median(chunk_start_deltas),
			"chunk_start_delta_p90_abs_sec": p90_abs(chunk_start_deltas),
			"chunk_end_delta_median_sec": median(chunk_end_deltas),
			"chunk_end_delta_p90_abs_sec": p90_abs(chunk_end_deltas),
			"cue_mid_delta_median_sec": median(cue_mid_deltas),
			"cue_mid_delta_p90_abs_sec": p90_abs(cue_mid_deltas),
			"interpretation": "Negative start/mid deltas usually mean subtitles are early; positive start/mid deltas usually mean subtitles are late.",
		},
		"timeline_checks": timeline_checks,
		"chunk_checks": chunk_checks,
		"cue_checks": cue_checks,
	}
	return data


def verify(project_dir: Path, asr_json: Path | None = None) -> dict[str, Any]:
	video_dir = project_dir / "video"
	audio_path = project_dir / "audio" / "final_podcast.wav"
	timeline_path = project_dir / "audio" / "dialogue_timeline.json"
	subtitle_manifest_path = video_dir / "subtitle_manifest.json"
	srt_path = video_dir / "final_subtitles.srt"
	video_path = video_dir / "final_video.mp4"
	if not audio_path.exists():
		raise FileNotFoundError(audio_path)
	if not timeline_path.exists():
		raise FileNotFoundError(timeline_path)
	if not subtitle_manifest_path.exists():
		raise FileNotFoundError(subtitle_manifest_path)
	if not srt_path.exists():
		raise FileNotFoundError(srt_path)

	dialogue_timeline = _read_json(timeline_path)
	subtitle_manifest = _read_json(subtitle_manifest_path)
	raw_alignment_items = list(dialogue_timeline.get("cues") or dialogue_timeline.get("turns") or [])
	alignment_items = _prepare_alignment_items(raw_alignment_items)
	cues = list(subtitle_manifest.get("cues") or [])
	speed = float(subtitle_manifest.get("playback_speed_factor") or 1.0)
	alignment_mode = str(dialogue_timeline.get("alignment_method") or "dialogue_timeline_asr")
	if asr_json:
		alignment_mode = f"{alignment_mode}_with_external_asr_json_present"
	srt_cues = _parse_srt(srt_path)
	audio_duration = _duration(audio_path)
	video_duration = _duration(video_path) if video_path.exists() else 0.0
	timeline_hash = _sha256(timeline_path)

	timeline_checks: list[dict[str, Any]] = []
	if str(dialogue_timeline.get("audio_sha256") or "") == _sha256(audio_path):
		timeline_checks.append({"status": "PASS", "message": "dialogue_timeline audio_sha256 matches final_podcast.wav"})
	else:
		timeline_checks.append({"status": "FAIL", "message": "dialogue_timeline audio_sha256 does not match final_podcast.wav"})
	recorded_timeline_hash = subtitle_manifest.get("dialogue_timeline_sha256")
	if recorded_timeline_hash == timeline_hash:
		timeline_checks.append({"status": "PASS", "message": "subtitle_manifest dialogue_timeline_sha256 matches audio/dialogue_timeline.json"})
	elif recorded_timeline_hash:
		timeline_checks.append({"status": "FAIL", "message": "subtitle_manifest dialogue_timeline_sha256 does not match audio/dialogue_timeline.json"})
	else:
		timeline_checks.append({"status": "NEEDS_FIX", "message": "subtitle_manifest missing dialogue_timeline_sha256"})
	if abs(float(dialogue_timeline.get("duration_sec") or 0.0) - audio_duration) <= 0.5:
		timeline_checks.append({"status": "PASS", "message": "dialogue_timeline duration matches final audio"})
	else:
		timeline_checks.append({"status": "FAIL", "message": f"dialogue_timeline duration mismatch: timeline={dialogue_timeline.get('duration_sec')} audio={audio_duration:.3f}"})
	if not alignment_items:
		timeline_checks.append({"status": "FAIL", "message": "dialogue_timeline has no cues or turns"})

	if len(srt_cues) == len(cues):
		timeline_checks.append({"status": "PASS", "message": f"SRT cue count matches subtitle_manifest: {len(cues)}"})
	else:
		timeline_checks.append({"status": "FAIL", "message": f"SRT cue count {len(srt_cues)} != subtitle_manifest cue count {len(cues)}"})
	max_srt_delta = 0.0
	for srt_cue, cue in zip(srt_cues, cues):
		max_srt_delta = max(max_srt_delta, abs(srt_cue.start_sec - float(cue["start_sec"])), abs(srt_cue.end_sec - float(cue["end_sec"])))
	if max_srt_delta <= SRT_MANIFEST_TOLERANCE_SEC:
		timeline_checks.append({"status": "PASS", "message": f"SRT cue times match subtitle_manifest within {max_srt_delta:.3f}s"})
	else:
		timeline_checks.append({"status": "FAIL", "message": f"SRT cue times differ from subtitle_manifest by up to {max_srt_delta:.3f}s"})
	if video_path.exists():
		expected_video_duration = audio_duration / speed if speed else audio_duration
		duration_delta = video_duration - expected_video_duration
		if abs(duration_delta) <= VIDEO_DURATION_TOLERANCE_SEC:
			timeline_checks.append({"status": "PASS", "message": f"Video duration matches audio/speed: delta={duration_delta:+.3f}s"})
		else:
			timeline_checks.append({"status": "FAIL", "message": f"Video duration mismatch: video={video_duration:.3f}s expected={expected_video_duration:.3f}s delta={duration_delta:+.3f}s"})
	if cues:
		last_cue_end = float(cues[-1]["end_sec"])
		expected_end = video_duration or audio_duration
		if abs(expected_end - last_cue_end) <= 1.5:
			timeline_checks.append({"status": "PASS", "message": f"Last subtitle cue reaches end: last={last_cue_end:.3f}s expected={expected_end:.3f}s"})
		else:
			timeline_checks.append({"status": "NEEDS_FIX", "message": f"Last subtitle cue does not reach end: last={last_cue_end:.3f}s expected={expected_end:.3f}s"})

	cues_by_alignment: dict[str, list[dict[str, Any]]] = {}
	for cue in cues:
		item = _find_alignment_item_for_cue(cue, alignment_items, speed)
		if not item:
			continue
		cues_by_alignment.setdefault(str(item["_qa_key"]), []).append(cue)

	alignment_checks: list[dict[str, Any]] = []
	alignment_status_by_key: dict[str, str] = {}
	for item_index, item in enumerate(alignment_items, start=1):
		key = str(item["_qa_key"])
		item_cues = sorted(cues_by_alignment.get(key, []), key=lambda value: float(value["start_sec"]))
		if not item_cues:
			alignment_checks.append({
				"status": "FAIL",
				"alignment_index": item_index,
				"alignment_key": key,
				"turn_index": item.get("turn_index"),
				"speaker": item.get("speaker"),
				"message": "No subtitle cues mapped to ASR alignment item",
				"text_preview": str(item.get("text") or "")[:60],
			})
			continue
		asr_start = float(item["start_sec"])
		asr_end = float(item["end_sec"])
		first_cue_start = min(_cue_source_times(cue, speed)[0] for cue in item_cues)
		last_cue_end = max(_cue_source_times(cue, speed)[1] for cue in item_cues)
		start_delta = first_cue_start - asr_start
		end_delta = last_cue_end - asr_end
		start_status = _check_delta(start_delta, CHUNK_START_OK_EARLY_SEC, CHUNK_START_OK_LATE_SEC, CHUNK_START_NEEDS_FIX_EARLY_SEC, CHUNK_START_NEEDS_FIX_LATE_SEC)
		end_status = _check_delta(end_delta, CHUNK_END_OK_EARLY_SEC, CHUNK_END_OK_LATE_SEC, CHUNK_END_NEEDS_FIX_EARLY_SEC, CHUNK_END_NEEDS_FIX_LATE_SEC)
		status = "PASS"
		if "NEEDS_FIX" in {start_status, end_status}:
			status = "NEEDS_FIX"
		elif "WARN" in {start_status, end_status}:
			status = "WARN"
		alignment_status_by_key[key] = status
		alignment_checks.append({
			"status": status,
			"alignment_index": item_index,
			"alignment_key": key,
			"turn_index": item.get("turn_index"),
			"speaker": item.get("speaker"),
			"asr_start_1x_sec": round(asr_start, 3),
			"asr_end_1x_sec": round(asr_end, 3),
			"first_cue_start_1x_sec": round(first_cue_start, 3),
			"last_cue_end_1x_sec": round(last_cue_end, 3),
			"start_delta_sec": round(start_delta, 3),
			"end_delta_sec": round(end_delta, 3),
			"start_status": start_status,
			"end_status": end_status,
			"cue_count": len(item_cues),
			"text_preview": str(item.get("text") or "")[:80],
		})

	cue_checks: list[dict[str, Any]] = []
	for cue in cues:
		item = _find_alignment_item_for_cue(cue, alignment_items, speed)
		text = str(cue.get("display_text") or cue.get("text") or "")
		if not item:
			cue_checks.append({
				"status": "FAIL",
				"cue_index": cue.get("index"),
				"text": text,
				"message": "No matching ASR alignment item",
			})
			continue
		actual_start, actual_end = _cue_source_times(cue, speed)
		asr_start = float(item["start_sec"])
		asr_end = float(item["end_sec"])
		alignment_key = str(item["_qa_key"])
		group_size = len(cues_by_alignment.get(alignment_key, []))
		start_delta = actual_start - asr_start
		end_delta = actual_end - asr_end
		start_status = _check_delta(start_delta, CHUNK_START_OK_EARLY_SEC, CHUNK_START_OK_LATE_SEC, CHUNK_START_NEEDS_FIX_EARLY_SEC, CHUNK_START_NEEDS_FIX_LATE_SEC)
		end_status = _check_delta(end_delta, CHUNK_END_OK_EARLY_SEC, CHUNK_END_OK_LATE_SEC, CHUNK_END_NEEDS_FIX_EARLY_SEC, CHUNK_END_NEEDS_FIX_LATE_SEC)
		if group_size > 1:
			# A long ASR cue may be split into multiple single-line display cues.
			# Judge timing at the group level above; an individual later split is
			# expected to start well after the source ASR cue begins.
			status = alignment_status_by_key.get(alignment_key, "PASS")
			check_mode = "split_cue_group"
		else:
			status = "PASS"
			if "NEEDS_FIX" in {start_status, end_status}:
				status = "NEEDS_FIX"
			elif "WARN" in {start_status, end_status}:
				status = "WARN"
			check_mode = "single_cue"
		cue_checks.append({
			"status": status,
			"cue_index": cue.get("index"),
			"alignment_key": alignment_key,
			"check_mode": check_mode,
			"group_cue_count": group_size,
			"turn_index": item.get("turn_index"),
			"speaker": cue.get("speaker") or item.get("speaker"),
			"text": text,
			"subtitle_start_1x_sec": round(actual_start, 3),
			"subtitle_end_1x_sec": round(actual_end, 3),
			"asr_start_1x_sec": round(asr_start, 3),
			"asr_end_1x_sec": round(asr_end, 3),
			"start_delta_sec": round(start_delta, 3),
			"end_delta_sec": round(end_delta, 3),
			"start_status": start_status,
			"end_status": end_status,
		})

	all_results = [*timeline_checks, *alignment_checks, *cue_checks]
	status = _status(all_results)
	alignment_issue_count = sum(1 for item in alignment_checks if item["status"] != "PASS")
	cue_issue_count = sum(1 for item in cue_checks if item["status"] in {"NEEDS_FIX", "FAIL"})
	cue_start_deltas = [float(item["start_delta_sec"]) for item in cue_checks if "start_delta_sec" in item]
	cue_end_deltas = [float(item["end_delta_sec"]) for item in cue_checks if "end_delta_sec" in item]
	def median(values: list[float]) -> float:
		return round(statistics.median(values), 3) if values else 0.0
	def p90_abs(values: list[float]) -> float:
		return round(_percentile([abs(value) for value in values], 0.90), 3) if values else 0.0

	return {
		"schema_version": "article-podcast-subtitle-timeline-qa.v2",
		"summary": {
			"status": status,
			"alignment_mode": alignment_mode,
			"playback_speed_factor": speed,
			"audio_duration_sec": round(audio_duration, 3),
			"video_duration_sec": round(video_duration, 3),
			"cue_count": len(cues),
			"srt_cue_count": len(srt_cues),
			"alignment_item_count": len(alignment_items),
			"alignment_issue_count": alignment_issue_count,
			"cue_issue_count": cue_issue_count,
			"residual_risk": "Checks assume audio/dialogue_timeline.json is a valid ASR/forced-alignment baseline.",
		},
		"inputs": {
			"project_dir": str(project_dir),
			"audio": "audio/final_podcast.wav",
			"dialogue_timeline": "audio/dialogue_timeline.json",
			"subtitle_manifest": "video/subtitle_manifest.json",
			"srt": "video/final_subtitles.srt",
			"video": "video/final_video.mp4" if video_path.exists() else None,
			"asr_json": str(asr_json) if asr_json else None,
		},
		"hashes": {
			"audio_sha256": _sha256(audio_path),
			"dialogue_timeline_sha256": timeline_hash,
			"subtitle_manifest_sha256": _sha256(subtitle_manifest_path),
			"srt_sha256": _sha256(srt_path),
			"video_sha256": _sha256(video_path) if video_path.exists() else None,
		},
		"thresholds": {
			"srt_manifest_tolerance_sec": SRT_MANIFEST_TOLERANCE_SEC,
			"video_duration_tolerance_sec": VIDEO_DURATION_TOLERANCE_SEC,
			"cue_start_ok_sec": [CHUNK_START_OK_EARLY_SEC, CHUNK_START_OK_LATE_SEC],
			"cue_start_needs_fix_sec": [CHUNK_START_NEEDS_FIX_EARLY_SEC, CHUNK_START_NEEDS_FIX_LATE_SEC],
			"cue_end_ok_sec": [CHUNK_END_OK_EARLY_SEC, CHUNK_END_OK_LATE_SEC],
			"cue_end_needs_fix_sec": [CHUNK_END_NEEDS_FIX_EARLY_SEC, CHUNK_END_NEEDS_FIX_LATE_SEC],
		},
		"aggregate_offsets": {
			"cue_start_delta_median_sec": median(cue_start_deltas),
			"cue_start_delta_p90_abs_sec": p90_abs(cue_start_deltas),
			"cue_end_delta_median_sec": median(cue_end_deltas),
			"cue_end_delta_p90_abs_sec": p90_abs(cue_end_deltas),
			"interpretation": "Negative deltas usually mean subtitles are early; positive deltas usually mean subtitles are late.",
		},
		"timeline_checks": timeline_checks,
		"alignment_checks": alignment_checks,
		"cue_checks": cue_checks,
	}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Verify podcast subtitle/audio/video timeline alignment.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--asr-json", type=Path)
	parser.add_argument("--fail-on-needs-fix", action="store_true")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	data = verify(project_dir, args.asr_json.expanduser().resolve() if args.asr_json else None)
	video_dir = project_dir / "video"
	json_path = video_dir / "subtitle_timeline_qa.json"
	report_path = video_dir / "subtitle_timeline_qa_report.md"
	_write_json(json_path, data)
	report_path.write_text(_build_report(project_dir, data), encoding="utf-8")
	print(json.dumps({"status": data["summary"]["status"], "json": str(json_path), "report": str(report_path)}, ensure_ascii=False, indent=2))
	if data["summary"]["status"] == "FAIL":
		return 2
	if args.fail_on_needs_fix and data["summary"]["status"] in {"NEEDS_FIX", "PASS_WITH_WARNINGS"}:
		return 2
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
