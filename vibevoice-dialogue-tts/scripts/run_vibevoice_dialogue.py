#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


DEFAULT_REPO = Path("/Users/wangfangjia/code/VibeVoice")
DEFAULT_MODEL = Path("/Volumes/GT34/AI/code-models/VibeVoice-1.5B-modelscope-clean")
DEFAULT_SPEAKERS = ("Xinran", "BowenClean")
SPEAKER_PATTERN = re.compile(r"^Speaker\s+(\d+):\s*(.*)$", re.IGNORECASE)
EXPECTED_SHA256 = {
	"model-00001-of-00003.safetensors": "c5f0a61ddeaeb028e3af540ba4dee7933ad30f9f30b6e1320dd9c875a2daa033",
	"model-00002-of-00003.safetensors": "81c3891f7b2493eb48a9eb6f5be0df48d4f1a4bfd952d84e21683ca6d0bf7969",
	"model-00003-of-00003.safetensors": "cb6e7e5e86b4a41fffbe1f3aaf445d0d50b5e21ed47574101b777f77d75fa196",
}


def _hash_file(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _check_model(model_path: Path) -> None:
	for filename, expected in EXPECTED_SHA256.items():
		path = model_path / filename
		assert path.exists(), f"Missing model shard: {path}"
		actual = _hash_file(path)
		assert actual == expected, f"SHA256 mismatch for {path}: {actual} != {expected}"
	print(f"Model SHA256 checks passed: {model_path}", flush=True)


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Run local VibeVoice long-form TTS in dialogue or single-speaker mode.")
	parser.add_argument("--txt-path", required=True, type=Path, help="Speaker-tagged input txt file.")
	parser.add_argument("--output-dir", required=True, type=Path, help="Directory for generated wav output.")
	parser.add_argument("--repo", default=DEFAULT_REPO, type=Path, help="Local VibeVoice repo path.")
	parser.add_argument("--model-path", default=DEFAULT_MODEL, type=Path, help="Local VibeVoice model directory.")
	parser.add_argument("--speaker-mode", default="dialogue", choices=("dialogue", "single", "auto"), help="VibeVoice input mode. Default dialogue preserves the original two-speaker wrapper behavior.")
	parser.add_argument("--speaker-names", nargs="+", default=None, help="VibeVoice speaker names. Dialogue mode requires two names; single mode uses one name.")
	parser.add_argument("--single-speaker-id", default="1", choices=("0", "1"), help="Speaker id used when single mode receives plain text without Speaker tags. VibeVoice's processor treats plain text as Speaker 1.")
	parser.add_argument("--device", default="mps", choices=("cpu", "mps", "cuda"), help="Inference device. MPS is the default/recommended path on this Mac; use cpu as an explicit fallback.")
	parser.add_argument("--torch-dtype", default="auto", choices=("auto", "float32", "float16", "bfloat16"), help="Torch dtype. auto => cpu/float32, mps/float16, cuda/bfloat16.")
	parser.add_argument("--attn-implementation", default="auto", choices=("auto", "eager", "sdpa", "flash_attention_2"), help="Attention implementation. auto => cpu/eager, mps/sdpa, cuda/flash_attention_2.")
	parser.add_argument("--cfg-scale", default="1.3", help="Classifier-free guidance scale.")
	parser.add_argument("--seed", default="42", help="Random seed.")
	parser.add_argument("--temperature", default="0.9", help="Sampling temperature.")
	parser.add_argument("--top-p", default="0.9", help="Sampling top-p.")
	parser.add_argument("--max-length-times", default="1.6", help="Generation max_length_times.")
	parser.add_argument("--ddpm-steps", default=None, help="Override diffusion steps.")
	parser.add_argument("--speaker-index-base", default="auto", choices=("auto", "0", "1"), help="Speaker index base for patched inference script.")
	parser.add_argument("--no-progress-bar", action="store_true", help="Disable VibeVoice progress bar.")
	parser.add_argument("--check-model", action="store_true", help="Verify known VibeVoice-1.5B model shard SHA256 hashes before running.")
	parser.add_argument("--dry-run", action="store_true", help="Print the command without executing.")
	return parser


def _speaker_numbers(text: str) -> list[str]:
	numbers: list[str] = []
	for raw_line in text.splitlines():
		match = SPEAKER_PATTERN.match(raw_line.strip())
		if match:
			numbers.append(match.group(1).strip())
	return numbers


def _resolve_mode(requested_mode: str, detected_speakers: list[str]) -> str:
	if requested_mode != "auto":
		return requested_mode
	unique = set(detected_speakers)
	return "single" if len(unique) <= 1 else "dialogue"


def _resolve_speaker_names(mode: str, provided: list[str] | None) -> list[str]:
	if provided is None:
		return [DEFAULT_SPEAKERS[0]] if mode == "single" else list(DEFAULT_SPEAKERS)
	names = list(provided)
	if mode == "single":
		assert len(names) == 1, f"single mode requires exactly one --speaker-names value, got {len(names)}"
	else:
		assert len(names) == 2, f"dialogue mode requires exactly two --speaker-names values, got {len(names)}"
	return names


def _resolve_torch_dtype_arg(value: str, device: str) -> str:
	if value != "auto":
		return value
	if device == "cuda":
		return "bfloat16"
	if device == "mps":
		return "float16"
	return "float32"


def _resolve_attn_implementation_arg(value: str, device: str) -> str:
	if value != "auto":
		return value
	if device == "cuda":
		return "flash_attention_2"
	if device == "mps":
		return "sdpa"
	return "eager"


def _write_single_speaker_tagged_copy(source: Path, output_dir: Path, text: str, speaker_id: str) -> Path:
	lines = []
	for raw_line in text.splitlines():
		line = raw_line.strip()
		if not line:
			continue
		match = SPEAKER_PATTERN.match(line)
		lines.append(match.group(2).strip() if match else line)
	assert lines, f"Input txt is empty: {source}"
	prepared = output_dir / f"{source.stem}__single_speaker_{speaker_id}.txt"
	prepared.write_text("\n".join(f"Speaker {speaker_id}: {line}" for line in lines) + "\n", encoding="utf-8")
	return prepared


def _prepare_input_for_mode(args: argparse.Namespace) -> tuple[Path, str, list[str]]:
	text = args.txt_path.read_text(encoding="utf-8")
	detected = _speaker_numbers(text)
	mode = _resolve_mode(args.speaker_mode, detected)
	unique = sorted(set(detected), key=lambda value: int(value))
	if mode == "dialogue":
		assert detected, "dialogue mode requires explicit Speaker N: lines"
		assert len(set(detected)) == 2, f"dialogue mode requires exactly two speakers in the txt file, got {unique}"
		return args.txt_path, mode, _resolve_speaker_names(mode, args.speaker_names)
	assert len(set(detected)) <= 1, f"single mode requires zero or one speaker in the txt file, got {unique}"
	if detected:
		return args.txt_path, mode, _resolve_speaker_names(mode, args.speaker_names)
	return _write_single_speaker_tagged_copy(args.txt_path, args.output_dir, text, args.single_speaker_id), mode, _resolve_speaker_names(mode, args.speaker_names)


def _validate_args(args: argparse.Namespace) -> None:
	assert args.repo.exists(), f"VibeVoice repo not found: {args.repo}"
	assert (args.repo / ".venv/bin/python").exists(), f"VibeVoice venv python not found: {args.repo / '.venv/bin/python'}"
	assert (args.repo / "demo/inference_from_file.py").exists(), "demo/inference_from_file.py not found"
	assert args.model_path.exists(), f"Model path not found: {args.model_path}"
	assert args.txt_path.exists(), f"Input txt not found: {args.txt_path}"
	assert args.txt_path.is_file(), f"Input txt is not a file: {args.txt_path}"
	args.output_dir.mkdir(parents=True, exist_ok=True)


def _build_command(args: argparse.Namespace, prepared_txt_path: Path, speaker_names: list[str]) -> list[str]:
	python_bin = args.repo / ".venv/bin/python"
	torch_dtype = _resolve_torch_dtype_arg(args.torch_dtype, args.device)
	attn_implementation = _resolve_attn_implementation_arg(args.attn_implementation, args.device)
	command = [
		str(python_bin),
		"demo/inference_from_file.py",
		"--model_path",
		str(args.model_path),
		"--txt_path",
		str(prepared_txt_path),
		"--speaker_names",
		*speaker_names,
		"--output_dir",
		str(args.output_dir),
		"--device",
		args.device,
		"--attn_implementation",
		attn_implementation,
		"--torch_dtype",
		torch_dtype,
		"--cfg_scale",
		args.cfg_scale,
		"--seed",
		args.seed,
		"--do_sample",
		"--temperature",
		args.temperature,
		"--top_p",
		args.top_p,
		"--max_length_times",
		args.max_length_times,
	]
	if args.speaker_index_base != "auto":
		command.extend(["--speaker_index_base", args.speaker_index_base])
	if args.ddpm_steps is not None:
		command.extend(["--ddpm_steps", args.ddpm_steps])
	if args.no_progress_bar:
		command.append("--no_progress_bar")
	return command


def main() -> int:
	args = _build_parser().parse_args()
	args.repo = args.repo.expanduser().resolve()
	args.model_path = args.model_path.expanduser().resolve()
	args.txt_path = args.txt_path.expanduser().resolve()
	args.output_dir = args.output_dir.expanduser().resolve()
	_validate_args(args)
	if args.check_model:
		_check_model(args.model_path)

	prepared_txt_path, resolved_mode, speaker_names = _prepare_input_for_mode(args)
	command = _build_command(args, prepared_txt_path, speaker_names)
	print(f"Resolved VibeVoice mode: {resolved_mode}", flush=True)
	print(f"Prepared txt path: {prepared_txt_path}", flush=True)
	print(f"Resolved speaker names: {speaker_names}", flush=True)
	print("Running:", " ".join(shlex.quote(part) for part in command), flush=True)
	if args.dry_run:
		return 0

	env = os.environ.copy()
	env.setdefault("TOKENIZERS_PARALLELISM", "false")
	if args.device == "mps":
		env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
	completed = subprocess.run(command, cwd=args.repo, env=env)
	return completed.returncode


if __name__ == "__main__":
	sys.exit(main())
