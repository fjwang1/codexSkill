#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


WRAPPER = Path("/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py")

LOCKED_CONFIG: dict[str, Any] = {
	"repo": "/Users/wangfangjia/code/VibeVoice",
	"model_path": "/Volumes/GT34/AI/code-models/VibeVoice-1.5B-modelscope-clean",
	"device": "cpu",
	"torch_dtype": "float32",
	"attn_implementation": "eager",
	"cfg_scale": "1.3",
	"seed": "42",
	"speaker_index_base": "auto",
	"do_sample": True,
	"checkpoint_path": None,
	"prefill": True,
	"voice_samples": True,
}

TUNABLE_DEFAULTS: dict[str, Any] = {
	"speaker_names": ["Xinran", "BowenClean"],
	"temperature": "0.9",
	"top_p": "0.9",
	"max_length_times": "1.6",
	"ddpm_steps": "10",
}


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative(path: Path, root: Path) -> str:
	return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Run VibeVoice for article podcast audio with locked production parameters.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--speaker-mode", default="dialogue", choices=("dialogue", "single", "auto"))
	parser.add_argument("--speaker-names", nargs="+", default=None)
	parser.add_argument("--temperature", default=TUNABLE_DEFAULTS["temperature"])
	parser.add_argument("--top-p", default=TUNABLE_DEFAULTS["top_p"])
	parser.add_argument("--max-length-times", default=TUNABLE_DEFAULTS["max_length_times"])
	parser.add_argument("--ddpm-steps", default=TUNABLE_DEFAULTS["ddpm_steps"])
	parser.add_argument("--no-progress-bar", action="store_true")
	parser.add_argument("--check-model", action="store_true")
	parser.add_argument("--dry-run", action="store_true")
	return parser


def _build_command(project_dir: Path, args: argparse.Namespace) -> tuple[list[str], dict[str, Any]]:
	audio_dir = project_dir / "audio"
	txt_path = audio_dir / "vibevoice_dialogue.txt"
	output_dir = audio_dir / "vibevoice_raw"
	assert WRAPPER.exists(), f"Missing VibeVoice wrapper: {WRAPPER}"
	assert txt_path.exists(), f"Missing VibeVoice input: {txt_path}"
	output_dir.mkdir(parents=True, exist_ok=True)

	speaker_names = list(args.speaker_names or TUNABLE_DEFAULTS["speaker_names"])
	if args.speaker_mode == "single" and args.speaker_names is None:
		speaker_names = [TUNABLE_DEFAULTS["speaker_names"][0]]
	if args.speaker_mode == "single":
		assert len(speaker_names) == 1, f"single mode requires exactly one speaker name, got {speaker_names}"
	elif args.speaker_mode == "dialogue":
		assert len(speaker_names) == 2, f"dialogue mode requires exactly two speaker names, got {speaker_names}"

	tunable_config = {
		"speaker_mode": args.speaker_mode,
		"speaker_names": speaker_names,
		"temperature": str(args.temperature),
		"top_p": str(args.top_p),
		"max_length_times": str(args.max_length_times),
		"ddpm_steps": str(args.ddpm_steps),
	}
	command = [
		str(WRAPPER),
		"--txt-path",
		str(txt_path),
		"--output-dir",
		str(output_dir),
		"--speaker-mode",
		args.speaker_mode,
		"--repo",
		LOCKED_CONFIG["repo"],
		"--model-path",
		LOCKED_CONFIG["model_path"],
		"--speaker-names",
		*tunable_config["speaker_names"],
		"--device",
		LOCKED_CONFIG["device"],
		"--torch-dtype",
		LOCKED_CONFIG["torch_dtype"],
		"--attn-implementation",
		LOCKED_CONFIG["attn_implementation"],
		"--cfg-scale",
		LOCKED_CONFIG["cfg_scale"],
		"--seed",
		LOCKED_CONFIG["seed"],
		"--temperature",
		tunable_config["temperature"],
		"--top-p",
		tunable_config["top_p"],
		"--max-length-times",
		tunable_config["max_length_times"],
		"--ddpm-steps",
		tunable_config["ddpm_steps"],
		"--speaker-index-base",
		LOCKED_CONFIG["speaker_index_base"],
	]
	if args.no_progress_bar:
		command.append("--no-progress-bar")
	if args.check_model:
		command.append("--check-model")
	return command, tunable_config


def _write_generation_config(project_dir: Path, command: list[str], tunable_config: dict[str, Any], dry_run: bool) -> Path:
	audio_dir = project_dir / "audio"
	config_path = audio_dir / "vibevoice_generation_config.json"
	payload = {
		"schema_version": "article-podcast-vibevoice-generation-config.v1",
		"profile": "article_podcast_vibevoice_locked_v1",
		"locked": LOCKED_CONFIG,
		"tunable": tunable_config,
		"paths": {
			"vibevoice_input": _relative(audio_dir / "vibevoice_dialogue.txt", project_dir),
			"output_dir": _relative(audio_dir / "vibevoice_raw", project_dir),
		},
		"dry_run": dry_run,
		"command": command,
		"command_display": " ".join(shlex.quote(part) for part in command),
	}
	_write_json(config_path, payload)

	manifest_path = audio_dir / "audio_manifest.json"
	if manifest_path.exists():
		manifest = _read_json(manifest_path)
		manifest["vibevoice_generation_config"] = _relative(config_path, project_dir)
		manifest["vibevoice_generation_profile"] = payload["profile"]
		manifest["vibevoice_generation_locked"] = LOCKED_CONFIG
		manifest["vibevoice_generation_tunable"] = tunable_config
		_write_json(manifest_path, manifest)
	return config_path


def main() -> int:
	args = _build_parser().parse_args()
	project_dir = args.project_dir.expanduser().resolve()
	assert project_dir.exists(), f"Missing project directory: {project_dir}"
	command, tunable_config = _build_command(project_dir, args)
	config_path = _write_generation_config(project_dir, command, tunable_config, args.dry_run)
	print(json.dumps({
		"profile": "article_podcast_vibevoice_locked_v1",
		"config": str(config_path),
		"locked": LOCKED_CONFIG,
		"tunable": tunable_config,
		"command": " ".join(shlex.quote(part) for part in command),
	}, ensure_ascii=False, indent=2))
	if args.dry_run:
		return 0
	return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
	raise SystemExit(main())
