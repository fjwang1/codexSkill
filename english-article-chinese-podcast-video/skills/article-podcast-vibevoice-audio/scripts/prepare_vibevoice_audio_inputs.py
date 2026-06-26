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
	"Speaker 1": "Speaker 1",
	"Speaker 2": "Speaker 2",
	"Speaker 3": "Speaker 3",
	"林遥": "Speaker 0",
	"陈澈": "Speaker 1",
}

SPEAKER_MAP = {
	"Speaker 0": {
		"display_role": "女主持",
		"style": "好奇、追问、代入听众",
		"default_vibevoice_name": "Xinran",
	},
	"Speaker 1": {
		"display_role": "男分析者",
		"style": "冷静、解释机制、给判断",
		"default_vibevoice_name": "BowenClean",
	},
	"Speaker 2": {
		"display_role": "第三位说话人",
		"style": "保持源播客第三位说话人的原始语气",
		"default_vibevoice_name": "Xinran",
	},
	"Speaker 3": {
		"display_role": "第四位说话人",
		"style": "保持源播客第四位说话人的原始语气",
		"default_vibevoice_name": "BowenClean",
	},
}
SPEAKER_MAP_OVERRIDE_FILENAMES = ("speaker_map.json", "audio/speaker_map.json")

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
		"- display_text_source: `podcast_script.md`",
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


def _load_speaker_map(project_dir: Path) -> tuple[dict[str, dict[str, Any]], str]:
	for filename in SPEAKER_MAP_OVERRIDE_FILENAMES:
		path = project_dir / filename
		if not path.exists():
			continue
		payload = _read_json(path)
		raw_map = payload.get("speaker_map") if isinstance(payload.get("speaker_map"), dict) else payload
		assert isinstance(raw_map, dict), f"speaker map override must be an object: {path}"
		speaker_map: dict[str, dict[str, Any]] = {}
		for speaker, default_info in SPEAKER_MAP.items():
			override_info = raw_map.get(speaker)
			if override_info is None:
				speaker_map[speaker] = dict(default_info)
				continue
			assert isinstance(override_info, dict), f"speaker map entry must be an object: {path} {speaker}"
			merged = dict(default_info)
			merged.update(override_info)
			speaker_map[speaker] = merged
		return speaker_map, str(path)
	return SPEAKER_MAP, "built_in_article_defaults"


def _parse_turns(text: str, speaker_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
	turns: list[dict[str, Any]] = []
	current_speaker: str | None = None
	current_lines: list[str] = []
	for raw_line in _extract_body(text).splitlines():
		line = raw_line.strip()
		if not line:
			continue
		match = re.match(r"^(Speaker [0-3]|林遥|陈澈)[：:]\s*(.*)$", line)
		if match:
			if current_speaker and current_lines:
				turns.append({"speaker": current_speaker, "text": " ".join(current_lines).strip()})
			current_speaker = SPEAKER_ALIASES[match.group(1)]
			current_lines = [match.group(2).strip()]
			continue
		if current_speaker:
			if re.match(r"^#{1,6}\s+", line):
				continue
			current_lines.append(line)
	if current_speaker and current_lines:
		turns.append({"speaker": current_speaker, "text": " ".join(current_lines).strip()})
	cleaned: list[dict[str, Any]] = []
	for index, turn in enumerate(turns, start=1):
		text_value = re.sub(r"\s+", " ", str(turn["text"])).strip()
		assert text_value, f"Empty text at turn {index}"
		cleaned.append({
			"turn_index": index,
			"speaker": turn["speaker"],
			"display_role": speaker_map.get(turn["speaker"], {"display_role": "说话人"})["display_role"],
			"text": text_value,
			"char_count": len(re.sub(r"\s+", "", text_value)),
		})
	return cleaned


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Prepare Speaker-tagged VibeVoice inputs for article or Worldview podcast projects.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--script-path", type=Path)
	parser.add_argument("--output-txt", type=Path)
	parser.add_argument("--display-output-txt", type=Path)
	parser.add_argument("--manifest-path", type=Path)
	parser.add_argument("--final-audio", type=Path)
	parser.add_argument("--disable-tts-normalization", action="store_true")
	parser.add_argument("--min-speaker-turns", type=int, default=2)
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	script_path = (args.script_path or project_dir / "podcast_script.md").expanduser().resolve()
	audio_dir = project_dir / "audio"
	audio_dir.mkdir(parents=True, exist_ok=True)
	output_txt = (args.output_txt or audio_dir / "vibevoice_dialogue.txt").expanduser().resolve()
	display_output_txt = (args.display_output_txt or audio_dir / "vibevoice_dialogue_display.txt").expanduser().resolve()
	normalization_report_path = audio_dir / "tts_normalization_report.md"
	manifest_path = (args.manifest_path or audio_dir / "audio_manifest.json").expanduser().resolve()
	final_audio = args.final_audio.expanduser().resolve() if args.final_audio else audio_dir / "final_podcast.wav"

	assert project_dir.exists(), f"Project directory not found: {project_dir}"
	assert script_path.exists(), f"Podcast script not found: {script_path}"
	text = script_path.read_text(encoding="utf-8")
	speaker_map, speaker_map_source = _load_speaker_map(project_dir)
	turns = _parse_turns(text, speaker_map)
	assert turns, "No Speaker turns found"
	assert args.min_speaker_turns >= 0, "--min-speaker-turns must be >= 0"
	speaker_ids = sorted({str(turn["speaker"]) for turn in turns} | {"Speaker 0", "Speaker 1"}, key=lambda value: int(value.split()[1]))
	speaker_counts = {speaker: sum(1 for turn in turns if turn["speaker"] == speaker) for speaker in speaker_ids}
	for speaker, count in speaker_counts.items():
		assert count >= args.min_speaker_turns, f"{speaker} has too few turns: {count}"

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
		"schema_version": "article-podcast-vibevoice-audio.v1",
		"audio_backend": "vibevoice_longform",
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
		"speaker_map": speaker_map,
		"speaker_map_source": speaker_map_source,
		"turn_count": len(turns),
		"speaker_counts": speaker_counts,
		"min_speaker_turns": args.min_speaker_turns,
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
		"speaker_map_source": speaker_map_source,
		"final_audio": str(final_audio) if final_audio.exists() else None,
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
