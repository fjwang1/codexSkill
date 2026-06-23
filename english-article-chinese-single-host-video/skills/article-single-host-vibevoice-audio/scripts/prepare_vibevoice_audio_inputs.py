#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SPEAKER_ALIASES = {
	"Speaker 0": "Speaker 0",
	"主持人": "Speaker 0",
	"口播": "Speaker 0",
}

SPEAKER_MAP = {
	"Speaker 0": {
		"display_role": "单人口播主持",
		"style": "自然、清楚、沉稳、解释型、适合中文视频口播的男声",
		"default_vibevoice_name": "BowenClean",
		"available_vibevoice_names": ["BowenClean", "译制腔"],
	},
}

DIGITS = "零一二三四五六七八九"

ACRONYM_SPELLINGS = {
	"AI": "A I",
	"API": "A P I",
	"ASR": "A S R",
	"BBC": "B B C",
	"CPU": "C P U",
	"FT": "F T",
	"GDP": "G D P",
	"GPT": "G P T",
	"MP3": "M P 三",
	"MP4": "M P 四",
	"TTS": "T T S",
	"WSJ": "W S J",
}


def _digit_string_to_chinese(value: str) -> str:
	return "".join(DIGITS[int(char)] if char.isdigit() else char for char in value)


def _section_to_chinese(value: int) -> str:
	assert 0 <= value < 10000
	if value == 0:
		return ""
	units = ["", "十", "百", "千"]
	parts: list[str] = []
	zero_pending = False
	for position in range(3, -1, -1):
		unit_value = 10 ** position
		digit = value // unit_value
		value %= unit_value
		if digit == 0:
			if parts and value:
				zero_pending = True
			continue
		if zero_pending:
			parts.append("零")
			zero_pending = False
		if not (digit == 1 and position == 1 and not parts):
			parts.append(DIGITS[digit])
		parts.append(units[position])
	return "".join(parts)


def _integer_to_chinese(value: int) -> str:
	if value == 0:
		return "零"
	assert value >= 0
	section_units = ["", "万", "亿", "万亿"]
	sections: list[int] = []
	while value:
		sections.append(value % 10000)
		value //= 10000
	parts: list[str] = []
	zero_pending = False
	for index in range(len(sections) - 1, -1, -1):
		section = sections[index]
		if section == 0:
			if parts:
				zero_pending = True
			continue
		if zero_pending or (parts and section < 1000):
			parts.append("零")
			zero_pending = False
		parts.append(_section_to_chinese(section) + section_units[index])
	return "".join(parts).replace("零零", "零").rstrip("零")


def _number_token_to_chinese(value: str) -> str:
	value = value.strip()
	if "." not in value:
		return _integer_to_chinese(int(value))
	integer, decimal = value.split(".", 1)
	prefix = _integer_to_chinese(int(integer)) if integer else "零"
	return prefix + "点" + _digit_string_to_chinese(decimal)


def _classifier_number_to_chinese(value: str) -> str:
	if value == "2":
		return "两"
	return _number_token_to_chinese(value)


def _normalize_tts_text(text: str) -> tuple[str, list[dict[str, Any]]]:
	"""Convert display Chinese into safer spoken Chinese for VibeVoice only."""
	rules: list[dict[str, Any]] = []

	def sub(pattern: str, repl: Any, value: str, rule: str, flags: int = 0) -> str:
		new_value, count = re.subn(pattern, repl, value, flags=flags)
		if count:
			rules.append({"rule": rule, "count": count})
		return new_value

	normalized = text
	for acronym, spoken in sorted(ACRONYM_SPELLINGS.items(), key=lambda item: len(item[0]), reverse=True):
		normalized = sub(rf"(?<![A-Za-z]){re.escape(acronym)}(?![A-Za-z])", spoken, normalized, f"spell_acronym:{acronym}")
	normalized = sub(
		r"(?<![\d.])(\d+(?:\.\d+)?)\s*%",
		lambda match: "百分之" + _number_token_to_chinese(match.group(1)),
		normalized,
		"percent_to_spoken_chinese",
	)
	normalized = sub(
		r"(?<!\d)((?:19|20)\d{2})\s*年",
		lambda match: _digit_string_to_chinese(match.group(1)) + "年",
		normalized,
		"year_to_digit_reading",
	)
	normalized = sub(
		r"(?<!\d)((?:19|20)\d{2})(?!\d)",
		lambda match: _digit_string_to_chinese(match.group(1)),
		normalized,
		"standalone_year_to_digit_reading",
	)
	normalized = sub(
		r"(?<![\d.])(\d+(?:\.\d+)?)\s*万\s*元",
		lambda match: _number_token_to_chinese(match.group(1)) + "万元",
		normalized,
		"ten_thousand_yuan_to_spoken_chinese",
	)
	normalized = sub(
		r"(?<![\d.])(\d+(?:\.\d+)?)\s*万",
		lambda match: _number_token_to_chinese(match.group(1)) + "万",
		normalized,
		"ten_thousand_to_spoken_chinese",
	)
	normalized = sub(
		r"(?<![\d.])(\d+(?:\.\d+)?)\s*亿",
		lambda match: _number_token_to_chinese(match.group(1)) + "亿",
		normalized,
		"hundred_million_to_spoken_chinese",
	)
	normalized = sub(
		r"(?<![\d.])(\d+(?:\.\d+)?)\s*元",
		lambda match: _number_token_to_chinese(match.group(1)) + "元",
		normalized,
		"yuan_to_spoken_chinese",
	)
	normalized = sub(
		r"(?<![\d.])(\d+)\s*岁",
		lambda match: _number_token_to_chinese(match.group(1)) + "岁",
		normalized,
		"age_to_spoken_chinese",
	)
	normalized = sub(
		r"(?<![\d.])(\d+)\s*(个|条|张|句|段|点|百分点)",
		lambda match: _classifier_number_to_chinese(match.group(1)) + match.group(2),
		normalized,
		"classifier_number_to_spoken_chinese",
	)
	normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", normalized)
	normalized = re.sub(r"\s+", " ", normalized).strip()
	return normalized, rules


def _write_tts_normalization_report(path: Path, turns: list[dict[str, Any]]) -> None:
	changed = [turn for turn in turns if turn.get("tts_text") != turn.get("text")]
	lines = [
		"# VibeVoice TTS 文本归一化报告",
		"",
		"- display_text_source: `single_host_script.md`",
		"- tts_text_output: `audio/vibevoice_dialogue.txt`",
		"- display_dialogue_output: `audio/vibevoice_dialogue_display.txt`",
		f"- changed_turns: {len(changed)} / {len(turns)}",
		"",
		"## Rules",
		"",
		"- 百分号：`14%` -> `百分之十四`",
		"- 年份/项目数字：`2050` -> `二零五零`",
		"- 金额/数量：`3000 元` -> `三千元`，`290 万` -> `二百九十万`",
		"- 年龄：`27 岁` -> `二十七岁`",
		"- 英文缩写：`GDP` -> `G D P`",
		"",
		"## Changed Turns",
		"",
	]
	if not changed:
		lines.append("- No changes.")
	for turn in changed:
		rules = ", ".join(f"{item['rule']} x{item['count']}" for item in turn.get("tts_normalization_rules", []))
		lines.extend([
			f"### Turn {turn['turn_index']} {turn['speaker']}",
			"",
			f"- rules: {rules}",
			f"- display: {turn['text']}",
			f"- tts: {turn['tts_text']}",
			"",
		])
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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


def _extract_body(text: str) -> str:
	match = re.search(r"(?m)^##\s*正文\s*$", text)
	if not match:
		return text
	return text[match.end():]


def _split_long_paragraph(text: str, min_chars: int = 80, max_chars: int = 260) -> list[str]:
	text = re.sub(r"\s+", " ", text).strip()
	if len(text) <= max_chars:
		return [text] if text else []
	sentence_parts = [part for part in re.split(r"([。！？；])", text) if part]
	sentences: list[str] = []
	buffer = ""
	for part in sentence_parts:
		buffer += part
		if part in "。！？；":
			sentences.append(buffer.strip())
			buffer = ""
	if buffer.strip():
		sentences.append(buffer.strip())
	chunks: list[str] = []
	current = ""
	for sentence in sentences:
		if current and len(current) + len(sentence) > max_chars:
			chunks.append(current.strip())
			current = sentence
		else:
			current += sentence
	if current.strip():
		chunks.append(current.strip())
	refined: list[str] = []
	for chunk in chunks:
		if len(chunk) <= max_chars:
			refined.append(chunk)
			continue
		pieces = [piece for piece in re.split(r"([，、])", chunk) if piece]
		current = ""
		for piece in pieces:
			current += piece
			if len(current) >= max_chars:
				refined.append(current.strip())
				current = ""
		if current.strip():
			refined.append(current.strip())
	balanced: list[str] = []
	for chunk in refined:
		if balanced and len(chunk) < min_chars:
			balanced[-1] = (balanced[-1] + chunk).strip()
		else:
			balanced.append(chunk)
	return [chunk for chunk in balanced if chunk]


def _extract_single_host_paragraphs(text: str) -> list[str]:
	body = _extract_body(text)
	paragraphs: list[str] = []
	current_lines: list[str] = []

	def flush() -> None:
		nonlocal current_lines
		if not current_lines:
			return
		paragraph = re.sub(r"\s+", " ", " ".join(current_lines)).strip()
		current_lines = []
		if not paragraph:
			return
		paragraphs.extend(_split_long_paragraph(paragraph))

	in_code_block = False
	for raw_line in body.splitlines():
		line = raw_line.strip()
		if line.startswith("```"):
			in_code_block = not in_code_block
			flush()
			continue
		if in_code_block:
			continue
		if not line:
			flush()
			continue
		if re.match(r"^#{1,6}\s+", line):
			flush()
			continue
		if line.startswith(("来源文章：", "形式：", "建议时长：")):
			continue
		match = re.match(r"^(Speaker\s+\d+|主持人|口播)[：:]\s*(.*)$", line)
		if match:
			label = match.group(1).replace("　", " ").strip()
			assert label in SPEAKER_ALIASES, f"Only single-host Speaker 0 is allowed, got: {label}"
			line = match.group(2).strip()
		line = re.sub(r"^[-*]\s+", "", line).strip()
		if line:
			current_lines.append(line)
	flush()
	return paragraphs


def _parse_turns(text: str) -> list[dict[str, Any]]:
	paragraphs = _extract_single_host_paragraphs(text)
	assert paragraphs, "No single-host paragraphs found"
	turns = [{"speaker": "Speaker 0", "text": paragraph} for paragraph in paragraphs]
	cleaned: list[dict[str, Any]] = []
	for index, turn in enumerate(turns, start=1):
		text_value = re.sub(r"\s+", " ", str(turn["text"])).strip()
		assert text_value, f"Empty text at turn {index}"
		cleaned.append({
			"turn_index": index,
			"speaker": turn["speaker"],
			"display_role": SPEAKER_MAP[turn["speaker"]]["display_role"],
			"text": text_value,
			"char_count": len(re.sub(r"\s+", "", text_value)),
		})
	return cleaned


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Prepare single-host Speaker 0 VibeVoice inputs for article explainer projects.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--script-path", type=Path)
	parser.add_argument("--output-txt", type=Path)
	parser.add_argument("--display-output-txt", type=Path)
	parser.add_argument("--manifest-path", type=Path)
	parser.add_argument("--final-audio", type=Path)
	parser.add_argument("--disable-tts-normalization", action="store_true")
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	default_script = project_dir / "single_host_script.md"
	if not default_script.exists():
		default_script = project_dir / "podcast_script.md"
	script_path = (args.script_path or default_script).expanduser().resolve()
	audio_dir = project_dir / "audio"
	audio_dir.mkdir(parents=True, exist_ok=True)
	output_txt = (args.output_txt or audio_dir / "vibevoice_dialogue.txt").expanduser().resolve()
	display_output_txt = (args.display_output_txt or audio_dir / "vibevoice_dialogue_display.txt").expanduser().resolve()
	normalization_report_path = audio_dir / "tts_normalization_report.md"
	manifest_path = (args.manifest_path or audio_dir / "audio_manifest.json").expanduser().resolve()
	final_audio = args.final_audio.expanduser().resolve() if args.final_audio else audio_dir / "final_podcast.wav"

	assert project_dir.exists(), f"Project directory not found: {project_dir}"
	assert script_path.exists(), f"Single-host script not found: {script_path}"
	text = script_path.read_text(encoding="utf-8")
	turns = _parse_turns(text)
	assert turns, "No Speaker 0 turns found"
	speaker_counts = {speaker: sum(1 for turn in turns if turn["speaker"] == speaker) for speaker in SPEAKER_MAP}
	assert speaker_counts.get("Speaker 0", 0) >= 2, f"Speaker 0 has too few turns: {speaker_counts.get('Speaker 0', 0)}"

	for turn in turns:
		if args.disable_tts_normalization:
			tts_text = str(turn["text"])
			rules: list[dict[str, Any]] = []
		else:
			tts_text, rules = _normalize_tts_text(str(turn["text"]))
		turn["tts_text"] = tts_text
		turn["tts_char_count"] = len(re.sub(r"\s+", "", tts_text))
		turn["tts_normalization_rules"] = rules
		turn["tts_normalized"] = tts_text != turn["text"]

	display_lines = [f"{turn['speaker']}: {turn['text']}" for turn in turns]
	display_output_txt.write_text("\n".join(display_lines) + "\n", encoding="utf-8")
	vibevoice_lines = [f"{turn['speaker']}: {turn['tts_text']}" for turn in turns]
	output_txt.write_text("\n".join(vibevoice_lines) + "\n", encoding="utf-8")
	_write_tts_normalization_report(normalization_report_path, turns)

	manifest: dict[str, Any] = _read_json(manifest_path) if manifest_path.exists() else {}
	manifest.update({
		"schema_version": "article-single-host-vibevoice-audio.v1",
		"audio_backend": "vibevoice_longform",
		"voice_mode": "single_host",
		"generation_mode": "vibevoice_longform_single_pass",
		"script": str(script_path.relative_to(project_dir)) if script_path.is_relative_to(project_dir) else str(script_path),
		"script_sha256": _sha256(script_path),
		"display_dialogue": str(display_output_txt.relative_to(project_dir)) if display_output_txt.is_relative_to(project_dir) else str(display_output_txt),
		"display_dialogue_sha256": _sha256(display_output_txt),
		"vibevoice_input": str(output_txt.relative_to(project_dir)) if output_txt.is_relative_to(project_dir) else str(output_txt),
		"vibevoice_input_sha256": _sha256(output_txt),
		"vibevoice_input_mode": "tts_normalized" if not args.disable_tts_normalization else "display_text_unmodified",
		"tts_normalization_enabled": not args.disable_tts_normalization,
		"tts_normalization_report": str(normalization_report_path.relative_to(project_dir)) if normalization_report_path.is_relative_to(project_dir) else str(normalization_report_path),
		"speaker_map": SPEAKER_MAP,
		"turn_count": len(turns),
		"speaker_counts": speaker_counts,
		"turns": turns,
		"requires_alignment": True,
		"alignment_artifact": "audio/dialogue_timeline.json",
	})
	if final_audio.exists():
		manifest.update({
			"final_audio": str(final_audio.relative_to(project_dir)) if final_audio.is_relative_to(project_dir) else str(final_audio),
			"final_audio_sha256": _sha256(final_audio),
			"duration_sec": round(_duration(final_audio), 3),
		})
	_write_json(manifest_path, manifest)
	print(json.dumps({
		"vibevoice_input": str(output_txt),
		"display_dialogue": str(display_output_txt),
		"tts_normalization_report": str(normalization_report_path),
		"manifest": str(manifest_path),
		"turn_count": len(turns),
		"speaker_counts": speaker_counts,
		"final_audio": str(final_audio) if final_audio.exists() else None,
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
