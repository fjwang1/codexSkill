#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


PUNCT_RE = re.compile(r"[\s,，。.!！?？;；:：、'\"“”‘’（）()《》<>\\[\\]{}—…·-]+")
SUBTITLE_MAX_NORM_CHARS = 30
CUE_LOW_CONFIDENCE_INTERPOLATION_THRESHOLD = 0.3
MIN_CUE_SEC_PER_CHAR = 0.045
SEMANTIC_CONNECTOR_BREAKS = (
	"而不是",
	"强到",
	"从而",
	"进而",
	"同时",
	"并且",
	"也就是",
	"我们不是",
	"我们一直",
	"过去只有",
	"以及",
	"允许",
	"必须",
	"应该",
	"能够",
	"可以",
	"能不能",
	"由",
)


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _duration(path: Path) -> float:
	result = subprocess.run(
		[
			"ffprobe",
			"-v",
			"error",
			"-show_entries",
			"format=duration",
			"-of",
			"default=noprint_wrappers=1:nokey=1",
			str(path),
		],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return float(result.stdout.strip())


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm(text: str) -> str:
	return "".join(char for char in text.lower() if char.isalnum())


def _script_chars(turns: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
	items: list[dict[str, Any]] = []
	chars: list[str] = []
	for turn in turns:
		display_text = str(turn["text"])
		alignment_text = str(turn.get("tts_text") or display_text)
		for raw_char in alignment_text:
			char = _norm(raw_char)
			if not char:
				continue
			for unit in char:
				items.append({
					"char": unit,
					"turn_index": int(turn["turn_index"]),
					"speaker": turn["speaker"],
					"display_role": turn.get("display_role"),
					"text": display_text,
					"tts_text": alignment_text,
				})
				chars.append(unit)
	return "".join(chars), items


def _asr_chars(asr: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
	items: list[dict[str, Any]] = []
	chars: list[str] = []
	for segment in asr.get("segments") or []:
		words = segment.get("words") or []
		if not words:
			text = _norm(str(segment.get("text") or ""))
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
					"probability": word.get("probability"),
				})
				chars.append(char)
	return "".join(chars), items


def _asr_quality(asr: dict[str, Any]) -> dict[str, Any]:
	word_probabilities: list[float] = []
	segment_logprobs: list[float] = []
	for segment in asr.get("segments") or []:
		try:
			segment_logprobs.append(float(segment["avg_logprob"]))
		except (KeyError, TypeError, ValueError):
			pass
		for word in segment.get("words") or []:
			try:
				word_probabilities.append(float(word["probability"]))
			except (KeyError, TypeError, ValueError):
				pass
	low_probability_words = sum(1 for value in word_probabilities if value < 0.6)
	return {
		"asr_word_count": len(word_probabilities),
		"avg_word_probability": round(sum(word_probabilities) / len(word_probabilities), 3) if word_probabilities else None,
		"low_word_probability_ratio": round(low_probability_words / len(word_probabilities), 3) if word_probabilities else None,
		"avg_segment_logprob": round(sum(segment_logprobs) / len(segment_logprobs), 3) if segment_logprobs else None,
	}


def _map_script_to_asr(script_text: str, asr_text: str) -> dict[int, int]:
	mapping: dict[int, int] = {}
	matcher = SequenceMatcher(a=script_text, b=asr_text, autojunk=False)
	for tag, i1, i2, j1, j2 in matcher.get_opcodes():
		if tag == "equal":
			for offset in range(i2 - i1):
				mapping[i1 + offset] = j1 + offset
		elif tag == "replace" and i2 > i1 and j2 > j1:
			s_len = i2 - i1
			a_len = j2 - j1
			if min(s_len, a_len) / max(s_len, a_len) >= 0.45:
				for offset in range(s_len):
					mapping[i1 + offset] = min(j2 - 1, j1 + math.floor(offset * a_len / s_len))
	return mapping


def _interpolate_times(script_len: int, mapped_times: dict[int, tuple[float, float]], duration: float) -> list[tuple[float, float, str]]:
	times: list[tuple[float, float, str]] = [(0.0, 0.0, "missing") for _ in range(script_len)]
	known = sorted(mapped_times)
	for idx in known:
		start, end = mapped_times[idx]
		times[idx] = (start, end, "asr")
	if not known:
		step = duration / max(1, script_len)
		return [(idx * step, (idx + 1) * step, "proportional_no_asr_match") for idx in range(script_len)]
	for idx in range(script_len):
		if times[idx][2] == "asr":
			continue
		prev_known = max((value for value in known if value < idx), default=None)
		next_known = min((value for value in known if value > idx), default=None)
		if prev_known is None:
			next_start = times[next_known][0] if next_known is not None else duration
			start = max(0.0, next_start * idx / max(1, next_known or script_len))
		elif next_known is None:
			prev_end = times[prev_known][1]
			remaining_chars = max(1, script_len - prev_known)
			start = min(duration, prev_end + (duration - prev_end) * ((idx - prev_known) / remaining_chars))
		else:
			prev_end = times[prev_known][1]
			next_start = times[next_known][0]
			start = prev_end + (next_start - prev_end) * ((idx - prev_known) / max(1, next_known - prev_known))
		end = min(duration, start + 0.08)
		times[idx] = (start, end, "interpolated")
	return times


def _turn_ranges(script_items: list[dict[str, Any]]) -> dict[int, tuple[int, int]]:
	ranges: dict[int, list[int]] = {}
	for idx, item in enumerate(script_items):
		ranges.setdefault(int(item["turn_index"]), []).append(idx)
	return {turn_index: (min(indexes), max(indexes) + 1) for turn_index, indexes in ranges.items()}


def _append_punct_units(text: str, terminal_marks: str) -> list[str]:
	units: list[str] = []
	buffer = ""
	for char in text:
		buffer += char
		if char in terminal_marks:
			cleaned = buffer.strip()
			if cleaned:
				units.append(cleaned)
			buffer = ""
	if buffer.strip():
		units.append(buffer.strip())
	return units


def _clean_subtitle_unit(text: str) -> str:
	return re.sub(r"\s+", " ", text).strip()


def _split_overlong_sentence(sentence: str, max_chars: int) -> list[str]:
	clauses = _append_punct_units(sentence, "，,；;：:、")
	assert len(clauses) > 1, (
		"Subtitle sentence is too long and has no semantic punctuation boundary; "
		"rewrite upstream instead of hard-splitting a phrase: "
		f"{sentence!r}"
	)
	units: list[str] = []
	buffer = ""
	for clause in clauses:
		clause = _clean_subtitle_unit(clause)
		for subclause in _split_overlong_clause_at_connectors(clause, max_chars):
			candidate = buffer + subclause if not buffer else buffer + subclause
			if buffer and len(_norm(candidate)) > max_chars:
				units.append(buffer.strip())
				buffer = subclause
			else:
				buffer = candidate
	if buffer.strip():
		units.append(buffer.strip())
	return units


def _split_overlong_clause_at_connectors(clause: str, max_chars: int) -> list[str]:
	clause = _clean_subtitle_unit(clause)
	if len(_norm(clause)) <= max_chars:
		return [clause]
	candidates: list[tuple[int, int, str, str]] = []
	for marker in SEMANTIC_CONNECTOR_BREAKS:
		start = 0
		while True:
			index = clause.find(marker, start)
			if index < 0:
				break
			start = index + len(marker)
			if index <= 0 or index >= len(clause) - 1:
				continue
			left = clause[:index].strip()
			right = clause[index:].strip()
			if not left or not right:
				continue
			left_len = len(_norm(left))
			right_len = len(_norm(right))
			candidates.append((max(left_len, right_len), abs(left_len - right_len), left, right))
	for _max_side, _balance, left, right in sorted(candidates):
		pieces: list[str] = []
		if len(_norm(left)) > max_chars:
			try:
				pieces.extend(_split_overlong_clause_at_connectors(left, max_chars))
			except AssertionError:
				continue
		else:
			pieces.append(left)
		if len(_norm(right)) > max_chars:
			try:
				pieces.extend(_split_overlong_clause_at_connectors(right, max_chars))
			except AssertionError:
				continue
		else:
			pieces.append(right)
		if pieces and all(len(_norm(piece)) <= max_chars for piece in pieces):
			return pieces
	assert False, (
		"Subtitle semantic clause is too long and has no safe semantic connector split; "
		"rewrite upstream instead of hard-splitting a phrase: "
		f"{clause!r}"
	)


def _split_text_for_cues(text: str, max_chars: int = SUBTITLE_MAX_NORM_CHARS) -> list[str]:
	sentences = _append_punct_units(text, "。！？!?；;")
	chunks: list[str] = []
	for sentence in sentences:
		sentence = _clean_subtitle_unit(sentence)
		if not _norm(sentence):
			continue
		if len(_norm(sentence)) <= max_chars:
			chunks.append(sentence)
		else:
			chunks.extend(_split_overlong_sentence(sentence, max_chars))
	assert chunks, f"No subtitle cue chunks produced from turn text: {text!r}"
	return chunks


def _cue_ranges_for_turn(turn_start: int, turn_end: int, text: str, chunks: list[str]) -> list[tuple[str, int, int]]:
	total = max(1, turn_end - turn_start)
	norm_lengths = [len(_norm(chunk)) for chunk in chunks]
	total_text = max(1, sum(norm_lengths))
	ranges: list[tuple[str, int, int]] = []
	cursor = turn_start
	allocated = 0
	for idx, (chunk, length) in enumerate(zip(chunks, norm_lengths, strict=True)):
		if idx == len(chunks) - 1:
			end = turn_end
		else:
			allocated += length
			end = turn_start + round(total * allocated / total_text)
			end = max(cursor + 1, min(turn_end, end))
		ranges.append((chunk, cursor, end))
		cursor = end
	return ranges


def _bounded_span(start: float, end: float, duration: float, minimum: float) -> tuple[float, float]:
	end = min(duration, max(start + minimum, end))
	if end <= start:
		start = max(0.0, end - minimum)
	return start, end


def _proportional_cue_span(turn_start_sec: float, turn_end_sec: float, turn_start_idx: int, turn_end_idx: int, cue_start_idx: int, cue_end_idx: int) -> tuple[float, float]:
	total_chars = max(1, turn_end_idx - turn_start_idx)
	turn_duration = max(0.001, turn_end_sec - turn_start_sec)
	relative_start = max(0.0, min(1.0, (cue_start_idx - turn_start_idx) / total_chars))
	relative_end = max(relative_start, min(1.0, (cue_end_idx - turn_start_idx) / total_chars))
	return turn_start_sec + turn_duration * relative_start, turn_start_sec + turn_duration * relative_end


def build_timeline(project_dir: Path, asr_json: Path, output: Path) -> dict[str, Any]:
	audio = project_dir / "audio" / "final_podcast.wav"
	manifest_path = project_dir / "audio" / "audio_manifest.json"
	manifest = _read_json(manifest_path)
	asr = _read_json(asr_json)
	duration = _duration(audio)
	turns_manifest = list(manifest.get("turns") or [])
	assert turns_manifest, "audio_manifest has no turns"

	script_text, script_items = _script_chars(turns_manifest)
	asr_text, asr_items = _asr_chars(asr)
	assert script_text, "empty normalized script text"
	assert asr_text, "empty normalized ASR text"
	script_to_asr = _map_script_to_asr(script_text, asr_text)
	mapped_times: dict[int, tuple[float, float]] = {}
	for script_idx, asr_idx in script_to_asr.items():
		if 0 <= asr_idx < len(asr_items):
			mapped_times[script_idx] = (float(asr_items[asr_idx]["start_sec"]), float(asr_items[asr_idx]["end_sec"]))
	times = _interpolate_times(len(script_items), mapped_times, duration)
	ranges = _turn_ranges(script_items)

	turns: list[dict[str, Any]] = []
	cues: list[dict[str, Any]] = []
	cue_index = 1
	for turn in turns_manifest:
		turn_index = int(turn["turn_index"])
		start_idx, end_idx = ranges[turn_index]
		range_times = times[start_idx:end_idx]
		start = max(0.0, min(item[0] for item in range_times))
		end = min(duration, max(item[1] for item in range_times))
		asr_count = sum(1 for item in range_times if item[2] == "asr")
		confidence_ratio = asr_count / max(1, len(range_times))
		confidence = "high" if confidence_ratio >= 0.6 else "medium" if confidence_ratio >= 0.3 else "low"
		turn_id = f"turn_{turn_index:04d}"
		start, end = _bounded_span(start, end, duration, 0.25)
		turns.append({
			"turn_index": turn_index,
			"turn_id": turn_id,
			"speaker": turn["speaker"],
			"display_role": turn.get("display_role"),
			"text": turn["text"],
			"tts_text": turn.get("tts_text"),
			"start_sec": round(start, 3),
			"end_sec": round(end, 3),
			"alignment_confidence": confidence,
			"asr_matched_char_ratio": round(confidence_ratio, 3),
		})
		chunks = _split_text_for_cues(str(turn["text"]))
		cue_char_ranges = _cue_ranges_for_turn(start_idx, end_idx, str(turn["text"]), chunks)
		for chunk, cue_start_idx, cue_end_idx in cue_char_ranges:
			cue_char_times = times[cue_start_idx:cue_end_idx]
			cue_asr_count = sum(1 for item in cue_char_times if item[2] == "asr")
			cue_confidence_ratio = cue_asr_count / max(1, len(cue_char_times))
			cue_confidence = "high" if cue_confidence_ratio >= 0.6 else "medium" if cue_confidence_ratio >= 0.3 else "low"
			min_cue_duration = max(0.4, min(1.2, len(_norm(chunk)) * MIN_CUE_SEC_PER_CHAR))
			proportional_start, proportional_end = _proportional_cue_span(start, end, start_idx, end_idx, cue_start_idx, cue_end_idx)
			timing_source = "asr_character_span" if cue_asr_count else "interpolated_character_span"
			if cue_confidence_ratio < CUE_LOW_CONFIDENCE_INTERPOLATION_THRESHOLD:
				cue_start, cue_end = proportional_start, proportional_end
				timing_source = "interpolated_character_span"
			else:
				cue_start = max(0.0, min(item[0] for item in cue_char_times))
				cue_end = min(duration, max(item[1] for item in cue_char_times))
				if cue_end - cue_start < min_cue_duration and proportional_end - proportional_start >= min_cue_duration:
					cue_start, cue_end = proportional_start, proportional_end
					timing_source = "interpolated_character_span"
			cue_start, cue_end = _bounded_span(cue_start, cue_end, duration, min_cue_duration)
			cues.append({
				"cue_index": cue_index,
				"turn_index": turn_index,
				"turn_id": turn_id,
				"speaker": turn["speaker"],
				"display_role": turn.get("display_role"),
				"text": chunk,
				"start_sec": round(cue_start, 3),
				"end_sec": round(cue_end, 3),
				"alignment_confidence": cue_confidence,
				"asr_matched_char_ratio": round(cue_confidence_ratio, 3),
				"timing_source": timing_source,
			})
			cue_index += 1

	timeline = {
		"schema_version": "article-podcast-dialogue-timeline.v1",
		"alignment_method": "mlx_whisper_word_timestamps_sequence_match",
		"audio": "audio/final_podcast.wav",
		"audio_sha256": _sha256(audio),
		"script_sha256": manifest["script_sha256"],
		"audio_manifest_sha256": _sha256(manifest_path),
		"asr_alignment_sha256": _sha256(asr_json),
		"duration_sec": round(duration, 3),
		"speaker_map": manifest.get("speaker_map") or {},
		"alignment_text_source": "audio_manifest.turns.tts_text" if any(turn.get("tts_text") for turn in turns_manifest) else "audio_manifest.turns.text",
		"display_text_source": "audio_manifest.turns.text",
		"subtitle_cue_policy": {
			"cue_text_policy": "complete_sentence_or_semantic_clause_no_hard_width_split",
			"cue_timing_policy": "asr_character_span",
			"max_norm_chars_per_cue": SUBTITLE_MAX_NORM_CHARS,
		},
		"asr_summary": {
			"asr_text_chars": len(asr_text),
			"script_text_chars": len(script_text),
			"matched_script_chars": len(mapped_times),
			"matched_script_ratio": round(len(mapped_times) / max(1, len(script_text)), 3),
			**_asr_quality(asr),
		},
		"turns": turns,
		"cues": cues,
	}
	_write_json(output, timeline)
	return timeline


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Build dialogue_timeline.json from MLX Whisper ASR output and audio_manifest turns.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--asr-json", type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--copy-asr-to-project", action="store_true")
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	asr_json = (args.asr_json or project_dir / "audio" / "asr_alignment.json").expanduser().resolve()
	output = (args.output or project_dir / "audio" / "dialogue_timeline.json").expanduser().resolve()
	assert asr_json.exists(), f"ASR JSON not found: {asr_json}"
	if args.copy_asr_to_project:
		target = project_dir / "audio" / "asr_alignment.json"
		if asr_json.resolve() != target.resolve():
			target.parent.mkdir(parents=True, exist_ok=True)
			shutil.copy2(asr_json, target)
			asr_json = target
	timeline = build_timeline(project_dir, asr_json, output)
	report = [
		"# 音频 ASR 对齐报告",
		"",
		f"- project: `{project_dir}`",
		f"- alignment_method: {timeline['alignment_method']}",
		f"- duration_sec: {timeline['duration_sec']}",
		f"- turns: {len(timeline['turns'])}",
		f"- cues: {len(timeline['cues'])}",
		f"- matched_script_ratio: {timeline['asr_summary']['matched_script_ratio']}",
		"",
		"## Notes",
		"",
		"- 本时间轴由最终音频 ASR 词/字时间戳和定稿文稿单调匹配生成。",
		"- 如果 `audio_manifest.turns.tts_text` 存在，匹配 ASR 时使用 TTS 朗读稿；字幕/章节输出仍使用 `turns.text` 的观众显示稿。",
		"- 仍需人工抽听 opening/middle/end 和至少 5 个 speaker switches 或段落边界。",
	]
	(project_dir / "audio" / "alignment_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
	print(json.dumps({
		"timeline": str(output),
		"turns": len(timeline["turns"]),
		"cues": len(timeline["cues"]),
		"matched_script_ratio": timeline["asr_summary"]["matched_script_ratio"],
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
