from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
from typing import Any

import pytest


SKILL_DIR = Path("/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts")


def _load_module(name: str, path: Path) -> Any:
	spec = importlib.util.spec_from_file_location(name, path)
	assert spec is not None
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[name] = module
	spec.loader.exec_module(module)
	return module


dialogue_runner = _load_module("run_vibevoice_dialogue", SKILL_DIR / "scripts/run_vibevoice_dialogue.py")
if "torch" not in sys.modules:
	torch_stub = ModuleType("torch")
	torch_stub.float32 = object()
	torch_stub.float16 = object()
	torch_stub.bfloat16 = object()
	torch_stub.dtype = object
	sys.modules["torch"] = torch_stub
resident_runner = _load_module("run_vibevoice_resident_batch", SKILL_DIR / "scripts/run_vibevoice_resident_batch.py")


def test_dialogue_runner_accepts_four_speaker_roster(tmp_path: Path) -> None:
	txt_path = tmp_path / "dialogue_4p.txt"
	txt_path.write_text(
		"\n".join([
			"Speaker 0: 第一位说话。",
			"Speaker 1: 第二位回应。",
			"Speaker 2: 第三位补充。",
			"Speaker 3: 第四位收束。",
		]) + "\n",
		encoding="utf-8",
	)
	args = SimpleNamespace(
		txt_path=txt_path,
		output_dir=tmp_path / "out",
		speaker_mode="dialogue",
		speaker_names=["Voice0", "Voice1", "Voice2", "Voice3"],
		single_speaker_id="1",
	)
	args.output_dir.mkdir()
	prepared, mode, names = dialogue_runner._prepare_input_for_mode(args)
	assert prepared == txt_path
	assert mode == "dialogue"
	assert names == ["Voice0", "Voice1", "Voice2", "Voice3"]
	assert dialogue_runner._resolve_speaker_index_base("auto", ["0", "1", "2", "3"], names) == 0


def test_dialogue_runner_rejects_more_than_four_speakers(tmp_path: Path) -> None:
	txt_path = tmp_path / "dialogue_5p.txt"
	txt_path.write_text(
		"\n".join(f"Speaker {index}: 第{index}位说话。" for index in range(5)) + "\n",
		encoding="utf-8",
	)
	args = SimpleNamespace(
		txt_path=txt_path,
		output_dir=tmp_path / "out",
		speaker_mode="dialogue",
		speaker_names=["Voice0", "Voice1", "Voice2", "Voice3", "Voice4"],
		single_speaker_id="1",
	)
	args.output_dir.mkdir()
	with pytest.raises(AssertionError, match="one to 4 speakers"):
		dialogue_runner._prepare_input_for_mode(args)


def test_resident_runner_keeps_single_speaker_chunk_on_global_four_speaker_base(tmp_path: Path) -> None:
	txt_path = tmp_path / "speaker2_only.txt"
	txt_path.write_text("Speaker 2: 这个 chunk 只有第三位说话人。\n", encoding="utf-8")
	prepared, mode, names = resident_runner._prepare_input_for_mode(
		txt_path,
		tmp_path / "out",
		"dialogue",
		["Voice0", "Voice1", "Voice2", "Voice3"],
		"1",
	)
	assert prepared == txt_path
	assert mode == "dialogue"
	assert names == ["Voice0", "Voice1", "Voice2", "Voice3"]
	assert resident_runner._resolve_speaker_index_base("0", ["2"], names) == 0


def test_resident_runner_auto_base_supports_official_one_indexed_examples() -> None:
	assert resident_runner._resolve_speaker_index_base("auto", ["1", "2", "3", "4"], ["A", "B", "C", "D"]) == 1
