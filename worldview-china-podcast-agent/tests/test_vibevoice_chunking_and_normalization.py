from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path("/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent")
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
	sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(name: str, path: Path) -> Any:
	spec = importlib.util.spec_from_file_location(name, path)
	assert spec is not None
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[name] = module
	spec.loader.exec_module(module)
	return module


vibevoice_chunks = _load_module("run_vibevoice_chunks_normalization_test", SKILL_DIR / "scripts/run_vibevoice_chunks.py")
display_numbers = _load_module("chinese_number_display_normalization_test", SKILL_DIR / "scripts/chinese_number_display.py")


def test_chinese_display_number_normalization_is_not_blanket_wan_conversion() -> None:
	text = "中国台湾大约有300,000名穆斯林，另有3,000人和300人，12,345个样本。"
	normalized = display_numbers.normalize_comma_thousands_for_chinese_display(text)
	assert normalized == "中国台湾大约有30万名穆斯林，另有3000人和300人，12345个样本。"
	assert "0.3万" not in normalized
	assert "0.03万" not in normalized


def test_tts_safety_normalizes_mixed_script_digits_and_units() -> None:
	text = "那么subhanAllah300,000中国台湾穆斯林，在2026年6小时内就有500人加入，比例是8%到9%。"
	normalized, rules = vibevoice_chunks._normalize_tts_safety_text(text)
	assert "苏布罕阿拉" in normalized
	assert "三十万中国台湾穆斯林" in normalized
	assert "二零二六年" in normalized
	assert "六小时" in normalized
	assert "五百人" in normalized
	assert "百分之八到百分之九" in normalized
	assert {item["rule"] for item in rules} >= {
		"latin_phrase_to_chinese:subhanallah",
		"comma_number_to_spoken_chinese",
		"year_with_suffix_to_digit_reading",
		"classifier_number_to_spoken_chinese",
		"percent_range_to_spoken_chinese",
	}


def test_parse_turns_records_original_text_when_tts_safety_changes(tmp_path: Path) -> None:
	script = tmp_path / "podcast_script.md"
	script.write_text(
		"\n".join([
			"Speaker 0: 那么subhanAllah300,000中国台湾穆斯林有多少？",
			"Speaker 1: 一共有2个人先报名。",
		]) + "\n",
		encoding="utf-8",
	)
	turns = vibevoice_chunks._parse_turns(script)
	assert len(turns) == 2
	assert turns[0]["original_text"] == "那么subhanAllah300,000中国台湾穆斯林有多少？"
	assert turns[0]["text"] == "那么苏布罕阿拉三十万中国台湾穆斯林有多少？"
	assert turns[0]["tts_safety_normalization_rules"]
	assert turns[1]["text"] == "一共有两个人先报名。"
	assert vibevoice_chunks._tts_safety_rule_counts(turns)["classifier_number_to_spoken_chinese"] == 1


def test_default_chunk_shape_is_small_enough_for_production() -> None:
	assert vibevoice_chunks.TARGET_CHARS == 320
	assert vibevoice_chunks.MIN_SPLIT_CHARS == 180
	assert vibevoice_chunks.HARD_MAX_CHARS == 420
	assert vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS == 160


def test_long_turns_are_split_before_chunking() -> None:
	long_text = "第一句" + ("很重要，" * 30) + "最后一句。"
	turns = [
		{"turn_index": 1, "speaker": "Speaker 0", "text": long_text, "char_count": len(long_text)},
		{"turn_index": 2, "speaker": "Speaker 1", "text": "我理解了。", "char_count": 5},
	]
	split_turns = vibevoice_chunks._split_long_turns(turns, max_chars=80)
	assert len(split_turns) > 2
	assert max(int(turn["char_count"]) for turn in split_turns) <= 80
	chunks = vibevoice_chunks._chunk_turns(split_turns)
	assert chunks
	assert all(sum(int(turn["char_count"]) for turn in chunk) <= vibevoice_chunks.HARD_MAX_CHARS for chunk in chunks)
