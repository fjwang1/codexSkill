from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


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
preflight = _load_module("run_vibevoice_preflight_audition_test", SKILL_DIR / "scripts/run_vibevoice_preflight_audition.py")
display_numbers = _load_module("chinese_number_display_normalization_test", SKILL_DIR / "scripts/chinese_number_display.py")
voice_policy = _load_module("apply_voice_distinctness_policy_test", SKILL_DIR / "scripts/apply_voice_distinctness_policy.py")


def _write_json(path: Path, data: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


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
	assert vibevoice_chunks.DEFAULT_MAX_CHUNKS_PER_EPISODE == 40
	assert vibevoice_chunks.CHUNKS_PER_TARGET_MINUTE == 1.0
	assert vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS == 160


def test_chunk_count_limit_tracks_episode_target_minutes(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode_001"
	parent_dir = tmp_path / "parent"
	run_dir.mkdir()
	_write_json = vibevoice_chunks._write_json
	_write_json(run_dir / "episode_manifest.json", {
		"parent_run_dir": str(parent_dir),
		"estimated_minutes": 32.0,
	})
	_write_json(parent_dir / "04b-series-episodes/series_manifest.json", {
		"target_minutes_max": 25.0,
	})

	policy = vibevoice_chunks._chunk_limit_policy(run_dir)

	assert policy["max_chunks_per_episode"] == 25
	assert policy["chunk_limit_source"] == "parent_series_manifest.target_minutes_max"


def test_chunk_count_limit_rejects_over_fragmented_plan() -> None:
	chunks = [[{"char_count": 10}] for _ in range(41)]
	policy = {
		"max_chunks_per_episode": 40,
		"chunk_limit_target_minutes": 40.0,
		"chunk_limit_source": "test",
	}

	with pytest.raises(RuntimeError, match="exceeds max_chunks_per_episode=40"):
		vibevoice_chunks._assert_chunk_count_within_limit(chunks, policy)


def test_preflight_raw_level_gate_uses_pass_yellow_fail_bands() -> None:
	assert preflight._classify_raw_level(
		{"mean_volume_dbfs": -25.0, "max_volume_dbfs": -12.0},
		-12.0,
		-15.0,
		-30.0,
	)[0] == "PASS"
	assert preflight._classify_raw_level(
		{"mean_volume_dbfs": -25.0, "max_volume_dbfs": -12.1},
		-12.0,
		-15.0,
		-30.0,
	)[0] == "YELLOW"
	assert preflight._classify_raw_level(
		{"mean_volume_dbfs": -25.0, "max_volume_dbfs": -15.0},
		-12.0,
		-15.0,
		-30.0,
	)[0] == "YELLOW"
	assert preflight._classify_raw_level(
		{"mean_volume_dbfs": -25.0, "max_volume_dbfs": -15.1},
		-12.0,
		-15.0,
		-30.0,
	)[0] == "FAIL"
	assert preflight._classify_raw_level(
		{"mean_volume_dbfs": -30.1, "max_volume_dbfs": -11.0},
		-12.0,
		-15.0,
		-30.0,
	)[0] == "FAIL"


def test_two_speaker_voice_distinctness_policy_keeps_cloned_pair_on_lightweight_warning(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	run_dir = tmp_path / "run"
	voice0 = run_dir / "voices/voice0.wav"
	voice1 = run_dir / "voices/voice1.wav"
	voice0.parent.mkdir(parents=True, exist_ok=True)
	voice0.write_bytes(b"voice0")
	voice1.write_bytes(b"voice1")
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {
				"vibevoice_name": "Clone0",
				"reference_wav": str(voice0),
			},
			"Speaker 1": {
				"vibevoice_name": "Clone1",
				"reference_wav": str(voice1),
			},
		},
	})
	monkeypatch.setattr(
		voice_policy,
		"_voice_similarity_score",
		lambda left, right: {
			"metric": "test_metric",
			"similarity_score": 0.95,
			"speaker_a_rms": 0.1,
			"speaker_b_rms": 0.1,
		},
	)
	result = voice_policy.apply_voice_distinctness_policy(
		run_dir,
		voices_dir=tmp_path / "registered_voices",
		threshold=0.90,
	)
	manifest = _read_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json")
	assert result["status"] == "WARN_LIGHTWEIGHT_SIMILARITY_HIGH_CLONED_PAIR_KEPT"
	assert "effective_speaker_voices_source" not in manifest
	assert "original_cloned_speaker_voices" not in manifest
	assert manifest["speaker_voices"]["Speaker 0"]["vibevoice_name"] == "Clone0"
	assert manifest["speaker_voices"]["Speaker 1"]["vibevoice_name"] == "Clone1"
	assert manifest["voice_distinctness_policy"]["fallback_action"] == "none_cloned_pair_kept"
	assert manifest["voice_distinctness_policy"]["legacy_threshold_exceeded"] is True
	assert "warning" in manifest["voice_distinctness_policy"]
	loaded_voices, loaded_manifest_path = vibevoice_chunks._load_speaker_voices(run_dir, "qwen_chinese_required")
	assert loaded_voices == {
		"Speaker 0": "Clone0",
		"Speaker 1": "Clone1",
	}
	assert loaded_manifest_path == str(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json")


def test_two_speaker_voice_distinctness_policy_fails_identical_reference(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	run_dir = tmp_path / "run"
	voice0 = run_dir / "voices/voice0.wav"
	voice1 = run_dir / "voices/voice1.wav"
	voice0.parent.mkdir(parents=True, exist_ok=True)
	voice0.write_bytes(b"same-registered-audio")
	voice1.write_bytes(b"same-registered-audio")
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {
				"vibevoice_name": "Clone0",
				"reference_wav": str(voice0),
			},
			"Speaker 1": {
				"vibevoice_name": "Clone1",
				"reference_wav": str(voice1),
			},
		},
	})
	monkeypatch.setattr(
		voice_policy,
		"_voice_similarity_score",
		lambda left, right: {
			"metric": "test_metric",
			"similarity_score": 0.10,
			"speaker_a_rms": 0.1,
			"speaker_b_rms": 0.1,
		},
	)

	result = voice_policy.apply_voice_distinctness_policy(
		run_dir,
		voices_dir=tmp_path / "registered_voices",
		threshold=0.90,
	)
	manifest = _read_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json")

	assert result["status"] == "FAIL_IDENTICAL_VOICE_REFERENCE_REQUIRES_REPAIR"
	assert voice_policy._policy_status_is_complete(result["policy"]) is False
	assert manifest["speaker_voices"]["Speaker 0"]["vibevoice_name"] == "Clone0"
	assert manifest["speaker_voices"]["Speaker 1"]["vibevoice_name"] == "Clone1"
	assert manifest["voice_distinctness_policy"]["reference_identity"]["registered_reference_same_sha256"] is True
	with pytest.raises(RuntimeError, match="not pass/warning/fallback"):
		vibevoice_chunks._load_speaker_voices(run_dir, "qwen_chinese_required")


def test_two_speaker_qwen_manifest_must_have_voice_distinctness_policy(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {"vibevoice_name": "Voice0"},
			"Speaker 1": {"vibevoice_name": "Voice1"},
		},
	})
	with pytest.raises(RuntimeError, match="voice distinctness policy"):
		vibevoice_chunks._load_speaker_voices(run_dir, "qwen_chinese_required")


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
