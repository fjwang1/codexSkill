#!/usr/bin/env python3
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any


EPSILON = 1e-12
SCHEMA_VERSION = "article-podcast-audio-artifact-qa.v1"


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _rel(path: Path, root: Path) -> str:
	try:
		return str(path.relative_to(root))
	except ValueError:
		return str(path)


def _read_wav_pcm16_mono(path: Path) -> tuple[int, list[int]]:
	with wave.open(str(path), "rb") as wav:
		channels = wav.getnchannels()
		sample_rate = wav.getframerate()
		sample_width = wav.getsampwidth()
		frame_count = wav.getnframes()
		raw = wav.readframes(frame_count)
	if sample_width != 2:
		raise ValueError(f"Only 16-bit PCM WAV is supported, got sample_width={sample_width}")
	samples = array.array("h")
	samples.frombytes(raw)
	if sys.byteorder != "little":
		samples.byteswap()
	if channels == 1:
		return sample_rate, list(samples)
	if channels < 1:
		raise ValueError(f"Invalid channel count: {channels}")
	mixed: list[int] = []
	for index in range(0, len(samples), channels):
		frame = samples[index:index + channels]
		if len(frame) == channels:
			mixed.append(round(sum(frame) / channels))
	return sample_rate, mixed


def _frame_features(
	samples: list[int],
	sample_rate: int,
	start_sec: float,
	end_sec: float,
	frame_ms: float,
	hop_ms: float,
) -> list[dict[str, float]]:
	start = max(0, int(start_sec * sample_rate))
	end = min(len(samples), int(end_sec * sample_rate))
	frame_size = max(8, int(sample_rate * frame_ms / 1000.0))
	hop_size = max(1, int(sample_rate * hop_ms / 1000.0))
	features: list[dict[str, float]] = []
	if end - start < frame_size:
		return features
	for position in range(start, end - frame_size + 1, hop_size):
		chunk = samples[position:position + frame_size]
		sum_sq = 0.0
		diff_sq = 0.0
		crossings = 0
		peak = 0
		previous = chunk[0]
		previous_positive = previous >= 0
		for offset, value in enumerate(chunk):
			abs_value = abs(value)
			if abs_value > peak:
				peak = abs_value
			sum_sq += float(value) * float(value)
			positive = value >= 0
			if offset and positive != previous_positive:
				crossings += 1
			if offset:
				diff = value - previous
				diff_sq += float(diff) * float(diff)
			previous = value
			previous_positive = positive
		rms_int = math.sqrt(sum_sq / len(chunk) + EPSILON)
		rms = rms_int / 32768.0
		db = 20.0 * math.log10(rms + EPSILON)
		diff_rms = math.sqrt(diff_sq / max(1, len(chunk) - 1) + EPSILON) / 32768.0
		high_frequency_proxy = diff_rms / (rms + EPSILON)
		zcr = crossings / max(1, len(chunk) - 1)
		crest = (peak / 32768.0) / (rms + EPSILON)
		features.append({
			"center_sec": round((position + frame_size / 2.0) / sample_rate, 4),
			"db": round(db, 3),
			"zcr": round(zcr, 4),
			"high_frequency_proxy": round(high_frequency_proxy, 4),
			"crest_factor": round(crest, 3),
		})
	return features


def _asr_words(asr: dict[str, Any]) -> list[dict[str, Any]]:
	words: list[dict[str, Any]] = []
	for segment_index, segment in enumerate(asr.get("segments") or [], start=1):
		segment_text = str(segment.get("text") or "").strip()
		segment_start = _to_float(segment.get("start"), 0.0)
		segment_end = _to_float(segment.get("end"), segment_start)
		raw_words = segment.get("words") or []
		if not raw_words:
			if segment_text:
				words.append({
					"text": segment_text,
					"start_sec": segment_start,
					"end_sec": segment_end,
					"probability": None,
					"segment_index": segment_index,
				})
			continue
		for word in raw_words:
			text = str(word.get("word") or "").strip()
			if not text:
				continue
			words.append({
				"text": text,
				"start_sec": _to_float(word.get("start"), segment_start),
				"end_sec": _to_float(word.get("end"), segment_end),
				"probability": _optional_float(word.get("probability")),
				"segment_index": segment_index,
			})
	return words


def _to_float(value: Any, default: float) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _optional_float(value: Any) -> float | None:
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _overlapping_words(words: list[dict[str, Any]], start_sec: float, end_sec: float) -> list[dict[str, Any]]:
	return [
		word for word in words
		if float(word["end_sec"]) > start_sec and float(word["start_sec"]) < end_sec
	]


def _group_frames(frames: list[dict[str, float]], merge_gap_sec: float, frame_ms: float) -> list[list[dict[str, float]]]:
	if not frames:
		return []
	groups: list[list[dict[str, float]]] = [[frames[0]]]
	for frame in frames[1:]:
		previous = groups[-1][-1]
		if float(frame["center_sec"]) - float(previous["center_sec"]) <= merge_gap_sec:
			groups[-1].append(frame)
		else:
			groups.append([frame])
	min_duration = frame_ms / 1000.0
	return [group for group in groups if (float(group[-1]["center_sec"]) - float(group[0]["center_sec"]) + min_duration) >= min_duration]


def _risk_level(max_db: float, max_zcr: float, max_high_proxy: float, duration_sec: float) -> str:
	if max_db >= -36.0 and (max_zcr >= 0.18 or max_high_proxy >= 0.45) and duration_sec >= 0.08:
		return "high"
	if max_db >= -40.0 and (max_zcr >= 0.14 or max_high_proxy >= 0.35):
		return "medium"
	return "low"


def _extract_clip(ffmpeg: str, audio_path: Path, output_path: Path, start_sec: float, end_sec: float) -> bool:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	command = [
		ffmpeg,
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-ss",
		f"{max(0.0, start_sec):.3f}",
		"-to",
		f"{max(start_sec + 0.01, end_sec):.3f}",
		"-i",
		str(audio_path),
		str(output_path),
	]
	return subprocess.run(command, check=False).returncode == 0


def _extract_spectrogram(ffmpeg: str, audio_path: Path, output_path: Path, start_sec: float, end_sec: float) -> bool:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	command = [
		ffmpeg,
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-ss",
		f"{max(0.0, start_sec):.3f}",
		"-to",
		f"{max(start_sec + 0.01, end_sec):.3f}",
		"-i",
		str(audio_path),
		"-lavfi",
		"showspectrumpic=s=1600x500:legend=1:scale=log",
		"-frames:v",
		"1",
		str(output_path),
	]
	return subprocess.run(command, check=False).returncode == 0


def _candidate_dict(
	candidate_id: str,
	boundary_index: int,
	turn: dict[str, Any],
	next_turn: dict[str, Any],
	gap_start: float,
	gap_end: float,
	group: list[dict[str, float]],
	frame_ms: float,
	asr_words: list[dict[str, Any]],
) -> dict[str, Any]:
	half_frame = frame_ms / 2000.0
	start_sec = max(gap_start, float(group[0]["center_sec"]) - half_frame)
	end_sec = min(gap_end, float(group[-1]["center_sec"]) + half_frame)
	max_db = max(float(frame["db"]) for frame in group)
	max_zcr = max(float(frame["zcr"]) for frame in group)
	max_high_proxy = max(float(frame["high_frequency_proxy"]) for frame in group)
	max_crest = max(float(frame["crest_factor"]) for frame in group)
	duration_sec = max(0.0, end_sec - start_sec)
	overlap_in_candidate = _overlapping_words(asr_words, start_sec, end_sec)
	overlap_in_gap = _overlapping_words(asr_words, gap_start, gap_end)
	return {
		"candidate_id": candidate_id,
		"boundary_index": boundary_index,
		"previous_turn_index": turn.get("turn_index"),
		"next_turn_index": next_turn.get("turn_index"),
		"previous_speaker": turn.get("speaker"),
		"next_speaker": next_turn.get("speaker"),
		"previous_text_tail": str(turn.get("text") or "")[-40:],
		"next_text_head": str(next_turn.get("text") or "")[:40],
		"gap_start_sec": round(gap_start, 3),
		"gap_end_sec": round(gap_end, 3),
		"gap_duration_sec": round(max(0.0, gap_end - gap_start), 3),
		"candidate_start_sec": round(start_sec, 3),
		"candidate_end_sec": round(end_sec, 3),
		"candidate_duration_sec": round(duration_sec, 3),
		"max_db": round(max_db, 2),
		"max_zcr": round(max_zcr, 3),
		"max_high_frequency_proxy": round(max_high_proxy, 3),
		"max_crest_factor": round(max_crest, 2),
		"risk_level": _risk_level(max_db, max_zcr, max_high_proxy, duration_sec),
		"machine_preclassification": "suspected_non_speech_artifact" if not overlap_in_candidate else "asr_detected_speech_or_text",
		"asr_overlap_candidate_text": "".join(str(word["text"]) for word in overlap_in_candidate),
		"asr_overlap_gap_text": "".join(str(word["text"]) for word in overlap_in_gap),
		"asr_overlap_candidate_word_count": len(overlap_in_candidate),
		"asr_overlap_gap_word_count": len(overlap_in_gap),
		"asr_silence_agrees": len(overlap_in_candidate) == 0,
		"review_hint": "如果候选片段在两个 turn 之间、ASR 无文字但声学特征明显，应优先判为 VibeVoice 非语音伪声。若只是自然气口/尾音/转场呼吸，可判 false_positive 或 acceptable_tail。",
	}


def _detect_candidates(
	samples: list[int],
	sample_rate: int,
	turns: list[dict[str, Any]],
	asr_words: list[dict[str, Any]],
	args: argparse.Namespace,
) -> list[dict[str, Any]]:
	candidates: list[dict[str, Any]] = []
	for boundary_index, (turn, next_turn) in enumerate(zip(turns, turns[1:]), start=1):
		turn_end = _to_float(turn.get("end_sec"), 0.0)
		next_start = _to_float(next_turn.get("start_sec"), turn_end)
		gap_duration = next_start - turn_end
		if gap_duration < args.min_gap_sec:
			continue
		gap_start = turn_end + args.edge_guard_sec
		gap_end = next_start - args.edge_guard_sec
		if gap_end <= gap_start:
			continue
		frames = _frame_features(samples, sample_rate, gap_start, gap_end, args.frame_ms, args.hop_ms)
		flagged = [
			frame for frame in frames
			if float(frame["db"]) >= args.min_candidate_db
			and (
				float(frame["zcr"]) >= args.min_zcr
				or float(frame["high_frequency_proxy"]) >= args.min_high_frequency_proxy
				or float(frame["crest_factor"]) >= args.min_crest_factor
			)
		]
		for group_index, group in enumerate(_group_frames(flagged, args.merge_gap_sec, args.frame_ms), start=1):
			candidate_id = f"boundary_{boundary_index:04d}_candidate_{group_index:02d}"
			candidates.append(_candidate_dict(
				candidate_id,
				boundary_index,
				turn,
				next_turn,
				gap_start,
				gap_end,
				group,
				args.frame_ms,
				asr_words,
			))
	candidates.sort(key=lambda item: (
		{"high": 0, "medium": 1, "low": 2}.get(str(item["risk_level"]), 3),
		float(item["candidate_start_sec"]),
	))
	return candidates[:args.max_candidates]


def _export_candidate_media(project_dir: Path, audio_path: Path, duration_sec: float, candidates: list[dict[str, Any]], args: argparse.Namespace) -> None:
	if args.no_export_clips:
		return
	ffmpeg = shutil.which("ffmpeg")
	if not ffmpeg:
		for candidate in candidates:
			candidate["clip"] = None
			candidate["spectrogram"] = None
			candidate["media_export_error"] = "ffmpeg not found"
		return
	output_dir = project_dir / "audio" / "artifact_candidates"
	output_dir.mkdir(parents=True, exist_ok=True)
	for candidate in candidates:
		start_sec = max(0.0, float(candidate["candidate_start_sec"]) - args.clip_context_sec)
		end_sec = min(duration_sec, float(candidate["candidate_end_sec"]) + args.clip_context_sec)
		base_name = str(candidate["candidate_id"])
		clip_path = output_dir / f"{base_name}.wav"
		spectrogram_path = output_dir / f"{base_name}_spectrogram.png"
		if _extract_clip(ffmpeg, audio_path, clip_path, start_sec, end_sec):
			candidate["clip"] = _rel(clip_path, project_dir)
		else:
			candidate["clip"] = None
			candidate["media_export_error"] = "clip export failed"
		if _extract_spectrogram(ffmpeg, audio_path, spectrogram_path, start_sec, end_sec):
			candidate["spectrogram"] = _rel(spectrogram_path, project_dir)
		else:
			candidate["spectrogram"] = None
			candidate["media_export_error"] = "spectrogram export failed"


def _report_lines(result: dict[str, Any]) -> list[str]:
	summary = result["summary"]
	lines = [
		"# 音频边界伪声 QA",
		"",
		f"状态：{result['status']}",
		"",
		"## 摘要",
		"",
		f"- turn 边界数：{summary['boundary_count']}",
		f"- 可扫描空档数：{summary['scanned_gap_count']}",
		f"- 候选数：{summary['candidate_count']}",
		f"- 高风险候选数：{summary['high_risk_count']}",
		"",
		"## 判定规则",
		"",
		"- 脚本只在两个 turn 之间理论上应接近安静的空档里找异常。",
		"- 如果空档中出现可听能量，并且过零率、短时差分高频代理或 crest factor 偏高，会列为候选。",
		"- ASR 没有识别出对应文字但声学特征异常时，优先交给 AI 判断是否为 VibeVoice 非语音伪声。",
		"",
	]
	candidates = result.get("candidates") or []
	if not candidates:
		lines.extend(["## 候选", "", "未发现需要 AI 复核的 turn 边界伪声候选。"])
		return lines
	lines.extend([
		"## 候选",
		"",
		"| id | 风险 | 时间 | dB | zcr | 高频代理 | ASR gap 文本 | clip |",
		"| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
	])
	for candidate in candidates:
		clip = candidate.get("clip") or ""
		lines.append(
			"| {id} | {risk} | {start:.3f}-{end:.3f}s | {db:.1f} | {zcr:.3f} | {hp:.3f} | {asr} | {clip} |".format(
				id=candidate["candidate_id"],
				risk=candidate["risk_level"],
				start=float(candidate["candidate_start_sec"]),
				end=float(candidate["candidate_end_sec"]),
				db=float(candidate["max_db"]),
				zcr=float(candidate["max_zcr"]),
				hp=float(candidate["max_high_frequency_proxy"]),
				asr=str(candidate.get("asr_overlap_gap_text") or "无"),
				clip=f"`{clip}`" if clip else "",
			)
		)
	lines.extend([
		"",
		"## AI 复核要求",
		"",
		"当状态为 `NEEDS_AI_REVIEW` 时，必须由 Codex 读取本报告、候选 clip/spectrogram、ASR overlap 和相邻 turn 文本，写出：",
		"",
		"```json",
		"{",
		'  "schema_version": "article-podcast-audio-artifact-ai-review.v1",',
		'  "status": "PASS | PASS_WITH_WARNINGS | FAIL",',
		'  "reviewer": "codex",',
		'  "decisions": [',
		'    {"candidate_id": "boundary_0001_candidate_01", "decision": "artifact | acceptable_tail | false_positive", "rationale": "..."}',
		"  ]",
		"}",
		"```",
	])
	return lines


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Detect possible VibeVoice non-speech artifacts around dialogue turn boundaries.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--audio", type=Path)
	parser.add_argument("--timeline", type=Path)
	parser.add_argument("--asr-json", type=Path)
	parser.add_argument("--output-json", type=Path)
	parser.add_argument("--output-report", type=Path)
	parser.add_argument("--min-gap-sec", type=float, default=0.35)
	parser.add_argument("--edge-guard-sec", type=float, default=0.12)
	parser.add_argument("--frame-ms", type=float, default=50.0)
	parser.add_argument("--hop-ms", type=float, default=10.0)
	parser.add_argument("--merge-gap-sec", type=float, default=0.08)
	parser.add_argument("--min-candidate-db", type=float, default=-40.0)
	parser.add_argument("--min-zcr", type=float, default=0.18)
	parser.add_argument("--min-high-frequency-proxy", type=float, default=0.45)
	parser.add_argument("--min-crest-factor", type=float, default=7.0)
	parser.add_argument("--max-candidates", type=int, default=16)
	parser.add_argument("--clip-context-sec", type=float, default=0.35)
	parser.add_argument("--no-export-clips", action="store_true")
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	audio_path = (args.audio or project_dir / "audio" / "final_podcast.wav").expanduser().resolve()
	timeline_path = (args.timeline or project_dir / "audio" / "dialogue_timeline.json").expanduser().resolve()
	asr_path = (args.asr_json or project_dir / "audio" / "asr_alignment.json").expanduser().resolve()
	output_json = (args.output_json or project_dir / "audio" / "audio_artifact_qa.json").expanduser().resolve()
	output_report = (args.output_report or project_dir / "audio" / "audio_artifact_qa_report.md").expanduser().resolve()
	assert project_dir.exists(), f"Missing project dir: {project_dir}"
	assert audio_path.exists(), f"Missing audio: {audio_path}"
	assert timeline_path.exists(), f"Missing timeline: {timeline_path}"

	sample_rate, samples = _read_wav_pcm16_mono(audio_path)
	duration_sec = len(samples) / sample_rate
	timeline = _read_json(timeline_path)
	turns = list(timeline.get("turns") or [])
	assert len(turns) >= 2, "dialogue_timeline.json must contain at least two turns"
	asr = _read_json(asr_path) if asr_path.exists() else {"segments": []}
	words = _asr_words(asr)
	scanned_gap_count = 0
	for turn, next_turn in zip(turns, turns[1:]):
		if _to_float(next_turn.get("start_sec"), 0.0) - _to_float(turn.get("end_sec"), 0.0) >= args.min_gap_sec:
			scanned_gap_count += 1
	candidates = _detect_candidates(samples, sample_rate, turns, words, args)
	_export_candidate_media(project_dir, audio_path, duration_sec, candidates, args)
	high_risk_count = sum(1 for candidate in candidates if candidate.get("risk_level") == "high")
	status = "PASS" if not candidates else "NEEDS_AI_REVIEW"
	result = {
		"schema_version": SCHEMA_VERSION,
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"status": status,
		"project_dir": str(project_dir),
		"audio": _rel(audio_path, project_dir),
		"timeline": _rel(timeline_path, project_dir),
		"asr_alignment": _rel(asr_path, project_dir) if asr_path.exists() else None,
		"audio_sha256": _sha256(audio_path),
		"timeline_sha256": _sha256(timeline_path),
		"asr_alignment_sha256": _sha256(asr_path) if asr_path.exists() else None,
		"duration_sec": round(duration_sec, 3),
		"thresholds": {
			"min_gap_sec": args.min_gap_sec,
			"edge_guard_sec": args.edge_guard_sec,
			"frame_ms": args.frame_ms,
			"hop_ms": args.hop_ms,
			"min_candidate_db": args.min_candidate_db,
			"min_zcr": args.min_zcr,
			"min_high_frequency_proxy": args.min_high_frequency_proxy,
			"min_crest_factor": args.min_crest_factor,
		},
		"summary": {
			"boundary_count": max(0, len(turns) - 1),
			"scanned_gap_count": scanned_gap_count,
			"candidate_count": len(candidates),
			"high_risk_count": high_risk_count,
		},
		"candidates": candidates,
		"ai_review_contract": {
			"required_when_status": "NEEDS_AI_REVIEW",
			"review_file": "audio/audio_artifact_ai_review.json",
			"decision_values": ["artifact", "acceptable_tail", "false_positive"],
			"pass_status_values": ["PASS", "PASS_WITH_WARNINGS"],
			"fail_status_values": ["FAIL"],
		},
	}
	output_json.parent.mkdir(parents=True, exist_ok=True)
	_write_json(output_json, result)
	output_report.write_text("\n".join(_report_lines(result)) + "\n", encoding="utf-8")
	print(json.dumps({
		"status": status,
		"candidate_count": len(candidates),
		"high_risk_count": high_risk_count,
		"json": str(output_json),
		"report": str(output_report),
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
