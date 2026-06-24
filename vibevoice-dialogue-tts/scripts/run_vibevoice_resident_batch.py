#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import torch


DEFAULT_REPO = Path("/Users/wangfangjia/code/VibeVoice")
DEFAULT_MODEL = Path("/Volumes/GT34/AI/code-models/VibeVoice-1.5B-modelscope-clean")
DEFAULT_SPEAKERS = ("Xinran", "BowenClean")
SPEAKER_PATTERN = re.compile(r"^Speaker\s+(\d+):\s*(.*)$", re.IGNORECASE)
EXPECTED_SHA256 = {
	"model-00001-of-00003.safetensors": "c5f0a61ddeaeb028e3af540ba4dee7933ad30f9f30b6e1320dd9c875a2daa033",
	"model-00002-of-00003.safetensors": "81c3891f7b2493eb48a9eb6f5be0df48d4f1a4bfd952d84e21683ca6d0bf7969",
	"model-00003-of-00003.safetensors": "cb6e7e5e86b4a41fffbe1f3aaf445d0d50b5e21ed47574101b777f77d75fa196",
}


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def _resolve_torch_dtype(value: str | None, device: str) -> torch.dtype:
	if value is not None and value != "auto":
		return {
			"float32": torch.float32,
			"float16": torch.float16,
			"bfloat16": torch.bfloat16,
		}[value]
	if device == "cuda":
		return torch.bfloat16
	if device == "mps":
		return torch.float16
	return torch.float32


def _resolve_attn_implementation(value: str | None, device: str) -> str:
	if value and value != "auto":
		return value
	if device == "cuda":
		return "flash_attention_2"
	if device == "mps":
		return "sdpa"
	return "eager"


def _load_vibevoice_modules(repo: Path) -> tuple[Any, Any, Any]:
	sys.path.insert(0, str(repo))
	from transformers.utils import logging
	from vibevoice.modular.lora_loading import load_lora_assets
	from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
	from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

	logging.set_verbosity_info()
	return VibeVoiceForConditionalGenerationInference, VibeVoiceProcessor, load_lora_assets


class VoiceMapper:
	def __init__(self, repo: Path) -> None:
		self.repo = repo
		self.setup_voice_presets()
		new_dict: dict[str, str] = {}
		for name, path in self.voice_presets.items():
			clean_name = name
			if "_" in clean_name:
				clean_name = clean_name.split("_")[0]
			if "-" in clean_name:
				clean_name = clean_name.split("-")[-1]
			new_dict[clean_name] = path
		self.voice_presets.update(new_dict)

	def setup_voice_presets(self) -> None:
		voices_dir = self.repo / "demo" / "voices"
		assert voices_dir.exists(), f"Voices directory not found: {voices_dir}"
		self.voice_presets = {}
		for wav_file in sorted(voices_dir.glob("*.wav")):
			if wav_file.is_file():
				self.voice_presets[wav_file.stem] = str(wav_file)
		self.available_voices = {
			name: path for name, path in self.voice_presets.items()
			if Path(path).exists()
		}
		assert self.available_voices, f"No VibeVoice wav voices found in {voices_dir}"
		print(f"Found {len(self.available_voices)} voice files in {voices_dir}", flush=True)
		print(f"Available voices: {', '.join(self.available_voices.keys())}", flush=True)

	def get_voice_path(self, speaker_name: str) -> str:
		if speaker_name in self.voice_presets:
			return self.voice_presets[speaker_name]
		speaker_lower = speaker_name.lower()
		for preset_name, path in self.voice_presets.items():
			if preset_name.lower() in speaker_lower or speaker_lower in preset_name.lower():
				return path
		default_voice = list(self.voice_presets.values())[0]
		print(f"Warning: No voice preset found for '{speaker_name}', using default voice: {default_voice}", flush=True)
		return default_voice


def _parse_txt_script(txt_content: str) -> tuple[list[str], list[str]]:
	lines = txt_content.strip().split("\n")
	scripts: list[str] = []
	speaker_numbers: list[str] = []
	current_speaker: str | None = None
	current_text = ""
	for raw_line in lines:
		line = raw_line.strip()
		if not line:
			continue
		match = SPEAKER_PATTERN.match(line)
		if match:
			if current_speaker and current_text:
				scripts.append(f"Speaker {current_speaker}: {current_text.strip()}")
				speaker_numbers.append(current_speaker)
			current_speaker = match.group(1).strip()
			current_text = match.group(2).strip()
			continue
		if current_text:
			current_text += " " + line
		else:
			current_text = line
	if current_speaker and current_text:
		scripts.append(f"Speaker {current_speaker}: {current_text.strip()}")
		speaker_numbers.append(current_speaker)
	return scripts, speaker_numbers


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
	return "single" if len(set(detected_speakers)) <= 1 else "dialogue"


def _resolve_speaker_names(mode: str, provided: list[str] | None) -> list[str]:
	if provided is None:
		return [DEFAULT_SPEAKERS[0]] if mode == "single" else list(DEFAULT_SPEAKERS)
	names = list(provided)
	if mode == "single":
		assert len(names) == 1, f"single mode requires exactly one speaker name, got {names}"
	else:
		assert len(names) == 2, f"dialogue mode requires exactly two speaker names, got {names}"
	return names


def _write_single_speaker_tagged_copy(source: Path, output_dir: Path, text: str, speaker_id: str) -> Path:
	lines: list[str] = []
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


def _prepare_input_for_mode(
	txt_path: Path,
	output_dir: Path,
	requested_mode: str,
	speaker_names: list[str] | None,
	single_speaker_id: str,
) -> tuple[Path, str, list[str]]:
	text = txt_path.read_text(encoding="utf-8")
	detected = _speaker_numbers(text)
	mode = _resolve_mode(requested_mode, detected)
	unique = sorted(set(detected), key=lambda value: int(value))
	if mode == "dialogue":
		assert detected, "dialogue mode requires explicit Speaker N: lines"
		assert len(set(detected)) == 2, f"dialogue mode requires exactly two speakers in the txt file, got {unique}"
		return txt_path, mode, _resolve_speaker_names(mode, speaker_names)
	assert len(set(detected)) <= 1, f"single mode requires zero or one speaker in the txt file, got {unique}"
	if detected:
		return txt_path, mode, _resolve_speaker_names(mode, speaker_names)
	return _write_single_speaker_tagged_copy(txt_path, output_dir, text, single_speaker_id), mode, _resolve_speaker_names(mode, speaker_names)


def _load_model(
	args: argparse.Namespace,
	model_class: Any,
	processor_class: Any,
	load_lora_assets: Any,
) -> tuple[Any, Any, str, torch.dtype, str, float]:
	device = args.device.lower()
	if device == "mpx":
		print("Note: device 'mpx' detected, treating it as 'mps'.", flush=True)
		device = "mps"
	if device == "mps" and not torch.backends.mps.is_available():
		print("Warning: MPS not available. Falling back to CPU.", flush=True)
		device = "cpu"

	load_dtype = _resolve_torch_dtype(args.torch_dtype, device)
	attn_impl = _resolve_attn_implementation(args.attn_implementation, device)
	print(f"Using device: {device}, torch_dtype: {load_dtype}, attn_implementation: {attn_impl}", flush=True)
	print(f"Loading processor & model from {args.model_path}", flush=True)
	load_start = time.time()
	processor = processor_class.from_pretrained(str(args.model_path))
	if device == "mps":
		model = model_class.from_pretrained(
			str(args.model_path),
			torch_dtype=load_dtype,
			attn_implementation=attn_impl,
			device_map=None,
		)
		model.to("mps")
	elif device == "cuda":
		model = model_class.from_pretrained(
			str(args.model_path),
			torch_dtype=load_dtype,
			device_map="cuda",
			attn_implementation=attn_impl,
		)
	else:
		model = model_class.from_pretrained(
			str(args.model_path),
			torch_dtype=load_dtype,
			device_map="cpu",
			attn_implementation=attn_impl,
		)
	if args.checkpoint_path:
		print(f"Loading fine-tuned assets from {args.checkpoint_path}", flush=True)
		report = load_lora_assets(model, str(args.checkpoint_path))
		print(f"LoRA load report: {report}", flush=True)
	model.eval()
	model.set_ddpm_inference_steps(num_steps=args.ddpm_steps)
	if hasattr(model.model, "language_model"):
		print(f"Language model attention: {model.model.language_model.config._attn_implementation}", flush=True)
	return processor, model, device, load_dtype, attn_impl, time.time() - load_start


def _to_output_path(output_dir: Path, txt_path: Path) -> Path:
	return output_dir / f"{txt_path.stem}_generated.wav"


def _special_token_counts(outputs: Any, input_tokens: int, tokenizer: Any) -> dict[str, int]:
	generated = outputs.sequences[:, input_tokens:]
	result: dict[str, int] = {}
	for name, token_id in (
		("speech_start", getattr(tokenizer, "speech_start_id", None)),
		("speech_end", getattr(tokenizer, "speech_end_id", None)),
		("speech_diffusion", getattr(tokenizer, "speech_diffusion_id", None)),
		("eos", getattr(tokenizer, "eos_token_id", None)),
		("pad", getattr(tokenizer, "pad_token_id", None)),
		("bos", getattr(tokenizer, "bos_token_id", None)),
	):
		if token_id is not None:
			result[name] = int((generated == token_id).sum().item())
	return result


def _torch_dtype_name(dtype: torch.dtype) -> str:
	return str(dtype).replace("torch.", "")


def _job_value(job: dict[str, Any], key: str, default: Any) -> Any:
	return job[key] if key in job and job[key] is not None else default


def _run_job(
	job: dict[str, Any],
	args: argparse.Namespace,
	voice_mapper: VoiceMapper,
	processor: Any,
	model: Any,
	device: str,
) -> dict[str, Any]:
	job_id = str(job.get("job_id") or Path(str(job["txt_path"])).stem)
	txt_path = Path(str(job["txt_path"])).expanduser().resolve()
	output_dir = Path(str(job.get("output_dir") or txt_path.parent / "vibevoice_raw")).expanduser().resolve()
	output_dir.mkdir(parents=True, exist_ok=True)
	requested_mode = str(_job_value(job, "speaker_mode", args.speaker_mode))
	speaker_names_value = _job_value(job, "speaker_names", None)
	speaker_names = [str(item) for item in speaker_names_value] if speaker_names_value else None
	single_speaker_id = str(_job_value(job, "single_speaker_id", args.single_speaker_id))
	speaker_index_base_value = _job_value(job, "speaker_index_base", args.speaker_index_base)
	prepared_txt_path, resolved_mode, resolved_speaker_names = _prepare_input_for_mode(
		txt_path,
		output_dir,
		requested_mode,
		speaker_names,
		single_speaker_id,
	)
	output_path = _to_output_path(output_dir, prepared_txt_path)
	force = bool(_job_value(job, "force", args.force))
	if output_path.exists() and not force:
		return {
			"job_id": job_id,
			"status": "skipped_existing",
			"txt_path": str(txt_path),
			"prepared_txt_path": str(prepared_txt_path),
			"output_wav": str(output_path),
			"speaker_mode": resolved_mode,
			"speaker_names": resolved_speaker_names,
		}

	txt_content = prepared_txt_path.read_text(encoding="utf-8")
	scripts, speaker_numbers = _parse_txt_script(txt_content)
	assert scripts, f"No valid speaker scripts found in {prepared_txt_path}"

	speaker_name_mapping: dict[str, str] = {}
	if speaker_index_base_value == "auto":
		speaker_index_base = min(int(speaker_num) for speaker_num in speaker_numbers)
	else:
		speaker_index_base = int(speaker_index_base_value)
	for offset, name in enumerate(resolved_speaker_names, speaker_index_base):
		speaker_name_mapping[str(offset)] = name

	unique_speaker_numbers: list[str] = []
	seen: set[str] = set()
	for speaker_num in speaker_numbers:
		if speaker_num not in seen:
			unique_speaker_numbers.append(speaker_num)
			seen.add(speaker_num)
	voice_samples: list[str] = []
	actual_speakers: list[str] = []
	for speaker_num in unique_speaker_numbers:
		speaker_name = speaker_name_mapping.get(speaker_num, f"Speaker {speaker_num}")
		voice_path = voice_mapper.get_voice_path(speaker_name)
		voice_samples.append(voice_path)
		actual_speakers.append(speaker_name)
		print(f"{job_id}: Speaker {speaker_num} ('{speaker_name}') -> Voice: {Path(voice_path).name}", flush=True)

	full_script = "\n".join(scripts).replace("’", "'")
	processor_voice_samples = None if args.no_voice_samples else [voice_samples]
	inputs = processor(
		text=[full_script],
		voice_samples=processor_voice_samples,
		padding=True,
		return_tensors="pt",
		return_attention_mask=True,
	)
	target_device = device if device != "cpu" else "cpu"
	for key, value in inputs.items():
		if torch.is_tensor(value):
			inputs[key] = value.to(target_device)

	seed = _job_value(job, "seed", args.seed)
	if seed is not None:
		torch.manual_seed(int(seed))
		if torch.cuda.is_available():
			torch.cuda.manual_seed_all(int(seed))
	temperature = float(_job_value(job, "temperature", args.temperature))
	top_p = float(_job_value(job, "top_p", args.top_p))
	do_sample = bool(_job_value(job, "do_sample", args.do_sample))
	cfg_scale = float(_job_value(job, "cfg_scale", args.cfg_scale))
	max_length_times = float(_job_value(job, "max_length_times", args.max_length_times))
	ddpm_steps = int(_job_value(job, "ddpm_steps", args.ddpm_steps))
	model.set_ddpm_inference_steps(num_steps=ddpm_steps)
	generation_config = {
		"do_sample": do_sample,
		"temperature": temperature if do_sample else 1.0,
		"top_p": top_p if do_sample else 1.0,
	}

	print(f"{job_id}: Starting generation with cfg_scale={cfg_scale}, max_length_times={max_length_times}, ddpm_steps={ddpm_steps}", flush=True)
	start_time = time.time()
	with torch.inference_mode():
		outputs = model.generate(
			**inputs,
			max_new_tokens=None,
			cfg_scale=cfg_scale,
			tokenizer=processor.tokenizer,
			generation_config=generation_config,
			verbose=True,
			is_prefill=not args.disable_prefill,
			max_length_times=max_length_times,
			show_progress_bar=not args.no_progress_bar,
		)
	generation_sec = time.time() - start_time
	generated_audio = outputs.speech_outputs[0] if outputs.speech_outputs else None
	if generated_audio is None:
		raise RuntimeError(f"{job_id}: No audio output generated")
	audio_samples = generated_audio.shape[-1] if len(generated_audio.shape) > 0 else len(generated_audio)
	audio_duration_sec = float(audio_samples) / 24000.0
	input_tokens = int(inputs["input_ids"].shape[1])
	output_tokens = int(outputs.sequences.shape[1])
	generated_tokens = output_tokens - input_tokens
	output_dir.mkdir(parents=True, exist_ok=True)
	processor.save_audio(generated_audio, output_path=str(output_path))
	print(f"{job_id}: Saved output to {output_path}", flush=True)
	rtf = generation_sec / audio_duration_sec if audio_duration_sec > 0 else None
	result = {
		"job_id": job_id,
		"status": "pass",
		"txt_path": str(txt_path),
		"prepared_txt_path": str(prepared_txt_path),
		"output_dir": str(output_dir),
		"output_wav": str(output_path),
		"speaker_mode": resolved_mode,
		"speaker_names": resolved_speaker_names,
		"actual_speakers": actual_speakers,
		"voice_samples": voice_samples,
		"segment_count": len(scripts),
		"generation_sec": round(generation_sec, 3),
		"audio_duration_sec": round(audio_duration_sec, 3),
		"rtf": round(rtf, 3) if rtf is not None else None,
		"prefill_tokens": input_tokens,
		"generated_tokens": generated_tokens,
		"total_tokens": output_tokens,
		"special_token_counts": _special_token_counts(outputs, input_tokens, processor.tokenizer),
		"generation_config": {
			"do_sample": do_sample,
			"temperature": temperature,
			"top_p": top_p,
			"cfg_scale": cfg_scale,
			"max_length_times": max_length_times,
			"ddpm_steps": ddpm_steps,
			"seed": seed,
		},
	}
	del inputs
	del outputs
	del generated_audio
	gc.collect()
	if device == "mps" and hasattr(torch, "mps"):
		torch.mps.empty_cache()
	return result


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Run VibeVoice 1.5B jobs with one resident processor/model load.")
	parser.add_argument("--jobs-json", required=True, type=Path, help="JSON file with a top-level jobs array.")
	parser.add_argument("--report-json", type=Path, help="Path to write the batch report JSON.")
	parser.add_argument("--repo", default=DEFAULT_REPO, type=Path)
	parser.add_argument("--model-path", default=DEFAULT_MODEL, type=Path)
	parser.add_argument("--speaker-mode", default="dialogue", choices=("dialogue", "single", "auto"))
	parser.add_argument("--speaker-names", nargs="+", default=None)
	parser.add_argument("--single-speaker-id", default="1", choices=("0", "1"))
	parser.add_argument("--device", default="mps", choices=("cpu", "mps", "cuda"), help="Inference device. MPS is the default/recommended path on this Mac; use cpu as an explicit fallback.")
	parser.add_argument("--torch-dtype", default="auto", choices=("auto", "float32", "float16", "bfloat16"))
	parser.add_argument("--attn-implementation", default="auto", choices=("auto", "eager", "sdpa", "flash_attention_2"))
	parser.add_argument("--cfg-scale", default=1.3, type=float)
	parser.add_argument("--seed", default=42, type=int)
	parser.set_defaults(do_sample=True)
	parser.add_argument("--do-sample", dest="do_sample", action="store_true", help="Enable sampling during speech token generation.")
	parser.add_argument("--no-do-sample", dest="do_sample", action="store_false", help="Disable sampling during speech token generation.")
	parser.add_argument("--temperature", default=0.9, type=float)
	parser.add_argument("--top-p", default=0.9, type=float)
	parser.add_argument("--max-length-times", default=1.6, type=float)
	parser.add_argument("--ddpm-steps", default=10, type=int)
	parser.add_argument("--speaker-index-base", default="auto", choices=("auto", "0", "1"))
	parser.add_argument("--checkpoint-path", type=Path)
	parser.add_argument("--disable-prefill", action="store_true")
	parser.add_argument("--no-voice-samples", action="store_true")
	parser.add_argument("--no-progress-bar", action="store_true")
	parser.add_argument("--check-model", action="store_true")
	parser.add_argument("--force", action="store_true")
	parser.add_argument("--continue-on-error", action="store_true")
	parser.add_argument("--dry-run", action="store_true")
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	args.jobs_json = args.jobs_json.expanduser().resolve()
	args.repo = args.repo.expanduser().resolve()
	args.model_path = args.model_path.expanduser().resolve()
	args.checkpoint_path = args.checkpoint_path.expanduser().resolve() if args.checkpoint_path else None
	args.report_json = (args.report_json or args.jobs_json.with_suffix(".report.json")).expanduser().resolve()
	assert args.jobs_json.exists(), f"Missing jobs JSON: {args.jobs_json}"
	assert args.repo.exists(), f"VibeVoice repo not found: {args.repo}"
	assert (args.repo / ".venv/bin/python").exists(), f"VibeVoice venv python not found: {args.repo / '.venv/bin/python'}"
	assert args.model_path.exists(), f"Model path not found: {args.model_path}"
	if args.check_model:
		_check_model(args.model_path)
	payload = _read_json(args.jobs_json)
	jobs = payload.get("jobs")
	assert isinstance(jobs, list) and jobs, f"{args.jobs_json} must contain a non-empty jobs array"
	if args.dry_run:
		_write_json(args.report_json, {
			"schema_version": "vibevoice-resident-batch-report.v1",
			"status": "dry_run",
			"jobs_json": str(args.jobs_json),
			"job_count": len(jobs),
			"jobs": jobs,
		})
		print(json.dumps({"status": "dry_run", "report_json": str(args.report_json)}, ensure_ascii=False, indent=2), flush=True)
		return 0

	os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
	if args.device == "mps":
		os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
	model_class, processor_class, load_lora_assets = _load_vibevoice_modules(args.repo)
	batch_start = time.time()
	processor, model, device, load_dtype, attn_impl, model_load_sec = _load_model(args, model_class, processor_class, load_lora_assets)
	voice_mapper = VoiceMapper(args.repo)
	results: list[dict[str, Any]] = []
	batch_status = "pass"
	for index, job in enumerate(jobs, start=1):
		assert isinstance(job, dict), f"Job {index} must be an object"
		job_id = str(job.get("job_id") or f"job_{index:03d}")
		try:
			print(f"=== Resident VibeVoice job {index}/{len(jobs)}: {job_id} ===", flush=True)
			results.append(_run_job(job, args, voice_mapper, processor, model, device))
		except Exception as exc:
			batch_status = "fail"
			error = {
				"job_id": job_id,
				"status": "fail",
				"error_type": type(exc).__name__,
				"error": str(exc),
				"traceback": traceback.format_exc(),
			}
			results.append(error)
			print(json.dumps(error, ensure_ascii=False, indent=2), flush=True)
			if not args.continue_on_error:
				break
	report = {
		"schema_version": "vibevoice-resident-batch-report.v1",
		"status": batch_status,
		"jobs_json": str(args.jobs_json),
		"repo": str(args.repo),
		"model_path": str(args.model_path),
		"device": device,
		"torch_dtype": _torch_dtype_name(load_dtype),
		"attn_implementation": attn_impl,
		"model_load_sec": round(model_load_sec, 3),
		"total_elapsed_sec": round(time.time() - batch_start, 3),
		"job_count": len(jobs),
		"completed_job_count": sum(1 for item in results if item.get("status") in {"pass", "skipped_existing"}),
		"failed_job_count": sum(1 for item in results if item.get("status") == "fail"),
		"jobs": results,
	}
	_write_json(args.report_json, report)
	print(json.dumps({"status": batch_status, "report_json": str(args.report_json)}, ensure_ascii=False, indent=2), flush=True)
	return 0 if batch_status == "pass" else 1


if __name__ == "__main__":
	raise SystemExit(main())
