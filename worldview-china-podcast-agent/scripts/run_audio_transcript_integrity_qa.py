#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "worldview-china-podcast-audio-transcript-integrity.v1"
TRADITIONAL_TO_SIMPLIFIED = str.maketrans({
	"蘭": "兰",
	"產": "产",
	"業": "业",
	"規": "规",
	"模": "模",
	"礎": "础",
	"於": "于",
	"國": "国",
	"錄": "录",
	"訪": "访",
	"問": "问",
	"與": "与",
	"眾": "众",
	"準": "准",
	"備": "备",
	"來": "来",
	"這": "这",
	"對": "对",
	"說": "说",
	"識": "识",
	"別": "别",
	"帶": "带",
	"當": "当",
	"個": "个",
	"麼": "么",
	"裡": "里",
	"歷": "历",
	"學": "学",
	"灣": "湾",
	"東": "东",
	"會": "会",
	"為": "为",
	"應": "应",
	"實": "实",
	"關": "关",
	"戰": "战",
	"稅": "税",
	"還": "还",
	"經": "经",
	"濟": "济",
	"體": "体",
	"現": "现",
	"錢": "钱",
	"開": "开",
	"發": "发",
	"過": "过",
	"師": "师",
	"漢": "汉",
	"語": "语",
	"書": "书",
	"數": "数",
	"詞": "词",
	"種": "种",
	"常": "常",
	"歲": "岁",
	"長": "长",
	"聽": "听",
	"見": "见",
	"點": "点",
	"後": "后",
	"們": "们",
	"時": "时",
	"間": "间",
	"裔": "裔",
	"觀": "观",
	"顧": "顾",
	"額": "额",
	"記": "记",
	"錄": "录",
	"題": "题",
	"種": "种",
	"層": "层",
	"別": "别",
	"讓": "让",
	"認": "认",
	"為": "为",
	"從": "从",
	"廣": "广",
	"場": "场",
	"戰": "战",
	"將": "将",
	"來": "来",
	"義": "义",
	"資": "资",
})


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _duration(path: Path) -> float:
	result = subprocess.run(
		["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return float(result.stdout.strip())


def _norm(text: str) -> str:
	text = text.translate(TRADITIONAL_TO_SIMPLIFIED).lower()
	text = text.replace("provisioncaptop", "provisioncapital")
	text = text.replace("captop", "capital")
	return "".join(char for char in text if char.isalnum())


def _script_chars(turns: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
	items: list[dict[str, Any]] = []
	chars: list[str] = []
	for turn in turns:
		turn_index = int(turn["turn_index"])
		display_text = str(turn.get("text") or "")
		alignment_text = str(turn.get("tts_text") or display_text)
		for raw_char in alignment_text:
			normalized = _norm(raw_char)
			if not normalized:
				continue
			for char in normalized:
				items.append({
					"char": char,
					"turn_index": turn_index,
					"speaker": turn.get("speaker"),
					"chunk_id": turn.get("chunk_id"),
					"text": display_text,
					"tts_text": alignment_text,
				})
				chars.append(char)
	return "".join(chars), items


def _asr_chars(asr: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
	items: list[dict[str, Any]] = []
	chars: list[str] = []
	raw_text_parts: list[str] = []
	for segment_index, segment in enumerate(asr.get("segments") or [], start=1):
		raw_segment_text = str(segment.get("text") or "").strip()
		if raw_segment_text:
			raw_text_parts.append(raw_segment_text)
		words = segment.get("words") or []
		if not words:
			text = _norm(raw_segment_text)
			start = float(segment.get("start") or 0.0)
			end = float(segment.get("end") or start)
			step = (end - start) / max(1, len(text))
			words = [{"word": ch, "start": start + idx * step, "end": start + (idx + 1) * step} for idx, ch in enumerate(text)]
		for word in words:
			text = _norm(str(word.get("word") or ""))
			if not text:
				continue
			start = float(word.get("start") or 0.0)
			end = float(word.get("end") or start)
			step = (end - start) / max(1, len(text))
			for idx, char in enumerate(text):
				items.append({
					"char": char,
					"start_sec": start + idx * step,
					"end_sec": start + (idx + 1) * step,
					"segment_index": segment_index,
					"word_probability": word.get("probability"),
				})
				chars.append(char)
	return "".join(chars), items, "\n".join(raw_text_parts).strip()


def _map_script_to_asr(script_text: str, asr_text: str) -> tuple[dict[int, int], list[tuple[str, int, int, int, int]]]:
	mapping: dict[int, int] = {}
	matcher = SequenceMatcher(a=script_text, b=asr_text, autojunk=False)
	opcodes = list(matcher.get_opcodes())
	for tag, i1, i2, j1, j2 in opcodes:
		if tag == "equal":
			for offset in range(i2 - i1):
				mapping[i1 + offset] = j1 + offset
		elif tag == "replace" and i2 > i1 and j2 > j1:
			s_len = i2 - i1
			a_len = j2 - j1
			if min(s_len, a_len) / max(s_len, a_len) >= 0.45:
				for offset in range(s_len):
					mapping[i1 + offset] = min(j2 - 1, j1 + round(offset * max(0, a_len - 1) / max(1, s_len - 1)))
	return mapping, opcodes


def _turn_ranges(script_items: list[dict[str, Any]]) -> dict[int, tuple[int, int]]:
	ranges: dict[int, list[int]] = {}
	for idx, item in enumerate(script_items):
		ranges.setdefault(int(item["turn_index"]), []).append(idx)
	return {turn_index: (min(indexes), max(indexes) + 1) for turn_index, indexes in ranges.items()}


def _turn_lookup(turns: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
	return {int(turn["turn_index"]): turn for turn in turns}


def _snippet_from_items(items: list[dict[str, Any]], start: int, end: int, max_chars: int = 120) -> str:
	seen: list[str] = []
	last_text = None
	for item in items[start:end]:
		text = str(item.get("text") or item.get("tts_text") or "")
		if text and text != last_text:
			seen.append(text)
			last_text = text
	text = " / ".join(seen)
	text = re.sub(r"\s+", " ", text).strip()
	return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _turn_metric(
	turn: dict[str, Any],
	start: int,
	end: int,
	script_to_asr: dict[int, int],
	asr_items: list[dict[str, Any]],
	timeline_turns: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
	turn_index = int(turn["turn_index"])
	char_count = max(0, end - start)
	mapped_indexes = [idx for idx in range(start, end) if idx in script_to_asr]
	ratio = len(mapped_indexes) / max(1, char_count)
	asr_indexes = [script_to_asr[idx] for idx in mapped_indexes if 0 <= script_to_asr[idx] < len(asr_items)]
	asr_start = min((float(asr_items[idx]["start_sec"]) for idx in asr_indexes), default=None)
	asr_end = max((float(asr_items[idx]["end_sec"]) for idx in asr_indexes), default=None)
	timeline_turn = (timeline_turns or {}).get(turn_index, {})
	return {
		"turn_index": turn_index,
		"speaker": turn.get("speaker"),
		"chunk_id": turn.get("chunk_id"),
		"normalized_char_count": char_count,
		"matched_char_count": len(mapped_indexes),
		"matched_char_ratio": round(ratio, 3),
		"asr_start_sec": round(asr_start, 3) if asr_start is not None else None,
		"asr_end_sec": round(asr_end, 3) if asr_end is not None else None,
		"timeline_start_sec": timeline_turn.get("start_sec"),
		"timeline_end_sec": timeline_turn.get("end_sec"),
		"text_head": str(turn.get("text") or "")[:80],
		"text_tail": str(turn.get("text") or "")[-80:],
	}


def _low_coverage_failures(
	turn_metrics: list[dict[str, Any]],
	min_long_turn_ratio: float,
	min_medium_turn_ratio: float,
	min_short_turn_ratio: float,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
	failures: list[str] = []
	warnings: list[dict[str, Any]] = []
	suspects: list[dict[str, Any]] = []
	for metric in turn_metrics:
		char_count = int(metric["normalized_char_count"])
		ratio = float(metric["matched_char_ratio"])
		if char_count >= 80 and ratio < min_long_turn_ratio:
			failures.append(
				f"turn {metric['turn_index']} matched_char_ratio too low: {ratio:.3f} < {min_long_turn_ratio:.3f}, chars={char_count}"
			)
			suspects.append(metric)
		elif char_count >= 30 and ratio < min_medium_turn_ratio:
			failures.append(
				f"medium turn {metric['turn_index']} matched_char_ratio too low: {ratio:.3f} < {min_medium_turn_ratio:.3f}, chars={char_count}"
			)
			suspects.append(metric)
		elif char_count >= 12 and ratio < min_short_turn_ratio:
			failures.append(
				f"short turn {metric['turn_index']} matched_char_ratio too low: {ratio:.3f} < {min_short_turn_ratio:.3f}, chars={char_count}"
			)
			suspects.append(metric)
		elif char_count >= 30 and ratio < 0.90:
			warnings.append(metric)
	return failures, warnings, suspects


def _unmatched_script_runs(
	opcodes: list[tuple[str, int, int, int, int]],
	script_items: list[dict[str, Any]],
	min_chars: int,
) -> list[dict[str, Any]]:
	runs: list[dict[str, Any]] = []
	for tag, i1, i2, j1, j2 in opcodes:
		if tag == "equal":
			continue
		script_len = i2 - i1
		asr_len = j2 - j1
		if script_len < min_chars:
			continue
		if tag == "replace" and asr_len >= script_len * 0.75:
			continue
		turn_indexes = sorted({int(item["turn_index"]) for item in script_items[i1:i2]})
		chunk_ids = sorted({str(item.get("chunk_id")) for item in script_items[i1:i2] if item.get("chunk_id")})
		runs.append({
			"opcode": tag,
			"script_start_char": i1,
			"script_end_char": i2,
			"script_char_count": script_len,
			"asr_char_count": asr_len,
			"turn_indexes": turn_indexes,
			"chunk_ids": chunk_ids,
			"script_snippet": _snippet_from_items(script_items, i1, i2),
			"repair_hint": "rerun_or_patch_listed_chunk_turns",
		})
	return runs


def _unmatched_asr_runs(opcodes: list[tuple[str, int, int, int, int]], asr_text: str, min_chars: int) -> list[dict[str, Any]]:
	runs: list[dict[str, Any]] = []
	for tag, i1, i2, j1, j2 in opcodes:
		if tag == "equal":
			continue
		script_len = i2 - i1
		asr_len = j2 - j1
		if asr_len < min_chars:
			continue
		if tag == "replace" and script_len >= asr_len * 0.75:
			continue
		runs.append({
			"opcode": tag,
			"asr_start_char": j1,
			"asr_end_char": j2,
			"asr_char_count": asr_len,
			"script_char_count": script_len,
			"asr_snippet": asr_text[j1:j2][:120] + ("..." if asr_len > 120 else ""),
			"risk": "extra_or_repeated_audio_not_in_script",
		})
	return runs


def _repetition_flags(asr_text: str) -> list[dict[str, Any]]:
	flags: list[dict[str, Any]] = []
	for unit_len in range(6, 21):
		index = 0
		while index + unit_len * 3 <= len(asr_text):
			unit = asr_text[index:index + unit_len]
			if len(set(unit)) <= 2:
				index += 1
				continue
			repeat_count = 1
			cursor = index + unit_len
			while asr_text[cursor:cursor + unit_len] == unit:
				repeat_count += 1
				cursor += unit_len
			if repeat_count >= 3:
				flags.append({
					"start_char": index,
					"unit_char_count": unit_len,
					"repeat_count": repeat_count,
					"text": unit,
					"risk": "possible_vibevoice_phrase_loop",
				})
				index = cursor
				continue
			index += 1
	if not flags:
		return []
	deduped: list[dict[str, Any]] = []
	seen: set[tuple[int, str]] = set()
	for flag in flags:
		key = (int(flag["start_char"]), str(flag["text"]))
		if key in seen:
			continue
		seen.add(key)
		deduped.append(flag)
	return deduped[:20]


def run_integrity_qa(
	run_dir: Path,
	min_global_matched_ratio: float,
	min_long_turn_ratio: float,
	min_medium_turn_ratio: float,
	min_short_turn_ratio: float,
	max_unmatched_script_run_chars: int,
	max_unmatched_asr_run_chars: int,
) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	audio_path = run_dir / "audio/final_podcast.wav"
	manifest_path = run_dir / "audio/audio_manifest.json"
	asr_path = run_dir / "audio/asr_alignment.json"
	timeline_path = run_dir / "audio/dialogue_timeline.json"
	for path in (audio_path, manifest_path, asr_path):
		assert path.exists(), f"Missing required input: {path}"
	manifest = _read_json(manifest_path)
	asr = _read_json(asr_path)
	turns = list(manifest.get("turns") or [])
	assert turns, "audio_manifest has no turns"
	timeline = _read_json(timeline_path) if timeline_path.exists() else {}
	script_text, script_items = _script_chars(turns)
	asr_text, asr_items, raw_asr_transcript = _asr_chars(asr)
	assert script_text, "normalized script text is empty"
	assert asr_text, "normalized ASR text is empty"
	script_to_asr, opcodes = _map_script_to_asr(script_text, asr_text)
	timeline_turns = _turn_lookup(list(timeline.get("turns") or []))
	ranges = _turn_ranges(script_items)
	turn_lookup = _turn_lookup(turns)
	turn_metrics = [
		_turn_metric(turn_lookup[turn_index], start, end, script_to_asr, asr_items, timeline_turns)
		for turn_index, (start, end) in sorted(ranges.items())
	]
	failures: list[str] = []
	warnings: list[str] = []
	global_ratio = len(script_to_asr) / max(1, len(script_text))
	if global_ratio < min_global_matched_ratio:
		failures.append(f"global matched_script_ratio too low: {global_ratio:.3f} < {min_global_matched_ratio:.3f}")
	low_failures, low_warnings, suspect_turns = _low_coverage_failures(
		turn_metrics,
		min_long_turn_ratio,
		min_medium_turn_ratio,
		min_short_turn_ratio,
	)
	failures.extend(low_failures)
	for metric in low_warnings:
		warnings.append(
			f"turn {metric['turn_index']} matched_char_ratio is below review threshold: {metric['matched_char_ratio']:.3f}"
		)
	unmatched_script_runs = _unmatched_script_runs(opcodes, script_items, min_chars=max_unmatched_script_run_chars)
	for run in unmatched_script_runs:
		failures.append(
			f"unmatched script run too long: {run['script_char_count']} chars, turns={run['turn_indexes']}, chunks={run['chunk_ids']}"
		)
	unmatched_asr_runs = _unmatched_asr_runs(opcodes, asr_text, min_chars=max_unmatched_asr_run_chars)
	for run in unmatched_asr_runs:
		warnings.append(f"long ASR-only run: {run['asr_char_count']} chars; possible repetition or hallucinated audio")
	repetition_flags = _repetition_flags(asr_text)
	for flag in repetition_flags:
		failures.append(
			f"possible repeated phrase loop in ASR transcript: `{flag['text']}` repeated {flag['repeat_count']} times"
		)
	chunk_targets = sorted({
		str(value)
		for item in [*suspect_turns, *unmatched_script_runs]
		for value in ([item.get("chunk_id")] if item.get("chunk_id") else item.get("chunk_ids", []))
		if value
	})
	result = {
		"schema_version": SCHEMA_VERSION,
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"status": "PASS" if not failures else "FAIL",
		"run_dir": str(run_dir),
		"inputs": {
			"audio": str(audio_path),
			"audio_sha256": _sha256(audio_path),
			"audio_duration_sec": round(_duration(audio_path), 3),
			"audio_manifest": str(manifest_path),
			"audio_manifest_sha256": _sha256(manifest_path),
			"asr_alignment": str(asr_path),
			"asr_alignment_sha256": _sha256(asr_path),
			"dialogue_timeline": str(timeline_path) if timeline_path.exists() else None,
			"dialogue_timeline_sha256": _sha256(timeline_path) if timeline_path.exists() else None,
		},
		"thresholds": {
			"min_global_matched_ratio": min_global_matched_ratio,
			"min_long_turn_ratio": min_long_turn_ratio,
			"min_medium_turn_ratio": min_medium_turn_ratio,
			"min_short_turn_ratio": min_short_turn_ratio,
			"max_unmatched_script_run_chars": max_unmatched_script_run_chars,
			"max_unmatched_asr_run_chars": max_unmatched_asr_run_chars,
		},
		"summary": {
			"script_text_chars": len(script_text),
			"asr_text_chars": len(asr_text),
			"matched_script_chars": len(script_to_asr),
			"matched_script_ratio": round(global_ratio, 3),
			"turn_count": len(turn_metrics),
			"suspect_turn_count": len(suspect_turns),
			"warning_turn_count": len(low_warnings),
			"unmatched_script_run_count": len(unmatched_script_runs),
			"unmatched_asr_run_count": len(unmatched_asr_runs),
			"repetition_flag_count": len(repetition_flags),
			"repair_target_chunks": chunk_targets,
		},
		"failures": failures,
		"warnings": warnings,
		"suspect_turns": suspect_turns,
		"warning_turns": low_warnings,
		"unmatched_script_runs": unmatched_script_runs,
		"unmatched_asr_runs": unmatched_asr_runs,
		"repetition_flags": repetition_flags,
		"repair_targets": [
			{
				"chunk_id": chunk_id,
				"action": "rerun_or_patch_chunk_then_rerun_06_audio_integrity_qa",
			}
			for chunk_id in chunk_targets
		],
	}
	output_dir = run_dir / "06b-audio-transcript-integrity"
	_write_json(output_dir / "audio-transcript-integrity-result.json", result)
	(output_dir / "final-audio-asr-transcript.txt").write_text(raw_asr_transcript + "\n", encoding="utf-8")
	report_lines = [
		"# Audio Transcript Integrity QA",
		"",
		f"- status: {result['status']}",
		f"- matched_script_ratio: {result['summary']['matched_script_ratio']}",
		f"- suspect_turn_count: {result['summary']['suspect_turn_count']}",
		f"- unmatched_script_run_count: {result['summary']['unmatched_script_run_count']}",
		f"- repetition_flag_count: {result['summary']['repetition_flag_count']}",
		f"- repair_target_chunks: {', '.join(chunk_targets) if chunk_targets else 'none'}",
		"",
	]
	if failures:
		report_lines.append("## Failures")
		report_lines.extend(f"- {failure}" for failure in failures)
		report_lines.append("")
	if warnings:
		report_lines.append("## Warnings")
		report_lines.extend(f"- {warning}" for warning in warnings)
		report_lines.append("")
	if suspect_turns:
		report_lines.append("## Suspect Turns")
		for turn in suspect_turns[:20]:
			report_lines.append(
				f"- turn {turn['turn_index']} chunk={turn.get('chunk_id') or 'unknown'} "
				f"ratio={turn['matched_char_ratio']} chars={turn['normalized_char_count']} "
				f"text={turn['text_head']}"
			)
		report_lines.append("")
	if unmatched_script_runs:
		report_lines.append("## Unmatched Script Runs")
		for run in unmatched_script_runs[:20]:
			report_lines.append(
				f"- chars={run['script_char_count']} turns={run['turn_indexes']} chunks={run['chunk_ids']} "
				f"snippet={run['script_snippet']}"
			)
		report_lines.append("")
	(output_dir / "audio-transcript-integrity-report.md").write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Validate final VibeVoice audio transcript integrity before subtitles/video/upload.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--min-global-matched-ratio", type=float, default=0.95)
	parser.add_argument("--min-long-turn-ratio", type=float, default=0.80)
	parser.add_argument("--min-medium-turn-ratio", type=float, default=0.60)
	parser.add_argument("--min-short-turn-ratio", type=float, default=0.45)
	parser.add_argument("--max-unmatched-script-run-chars", type=int, default=80)
	parser.add_argument("--max-unmatched-asr-run-chars", type=int, default=160)
	args = parser.parse_args()
	result = run_integrity_qa(
		args.run_dir.expanduser().resolve(),
		min_global_matched_ratio=args.min_global_matched_ratio,
		min_long_turn_ratio=args.min_long_turn_ratio,
		min_medium_turn_ratio=args.min_medium_turn_ratio,
		min_short_turn_ratio=args.min_short_turn_ratio,
		max_unmatched_script_run_chars=args.max_unmatched_script_run_chars,
		max_unmatched_asr_run_chars=args.max_unmatched_asr_run_chars,
	)
	print(json.dumps({
		"status": result["status"],
		"matched_script_ratio": result["summary"]["matched_script_ratio"],
		"suspect_turn_count": result["summary"]["suspect_turn_count"],
		"unmatched_script_run_count": result["summary"]["unmatched_script_run_count"],
		"repair_target_chunks": result["summary"]["repair_target_chunks"],
		"result": str(args.run_dir.expanduser().resolve() / "06b-audio-transcript-integrity/audio-transcript-integrity-result.json"),
	}, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
