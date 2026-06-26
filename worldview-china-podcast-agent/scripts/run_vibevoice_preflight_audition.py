#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import run_vibevoice_chunks as chunks


DEFAULT_AUDITION_CHUNK_COUNT = 2
DEFAULT_MIN_SOURCE_MAX_VOLUME = -10.0


def _parse_volume(stderr: str) -> dict[str, float]:
	mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
	max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
	assert mean_match and max_match, f"Could not parse volumedetect output: {stderr[-500:]}"
	return {
		"mean_volume_dbfs": float(mean_match.group(1)),
		"max_volume_dbfs": float(max_match.group(1)),
	}


def _volumedetect(path: Path) -> dict[str, float]:
	completed = subprocess.run(
		["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return _parse_volume(completed.stdout + "\n" + completed.stderr)


def _duration(path: Path) -> float:
	completed = subprocess.run(
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
	return float(completed.stdout.strip())


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_chunks(
	run_dir: Path,
	split_long_turn_max_chars: int,
	fixed_chunk_plan_json: Path | None,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
	script_path = run_dir / "04-podcast-script" / "podcast_script.md"
	source_turns = chunks._parse_turns(script_path)
	tts_safety_rule_counts = chunks._tts_safety_rule_counts(source_turns)
	turns = chunks._split_long_turns(source_turns, split_long_turn_max_chars)
	turns, dropped_tiny_turns = chunks._drop_tiny_tts_turns(turns)
	assert turns, "No TTS turns remain after dropping tiny filler turns"
	if fixed_chunk_plan_json is not None:
		chunk_sets = chunks._chunk_turns_from_fixed_plan(turns, fixed_chunk_plan_json)
	else:
		chunk_sets = chunks._chunk_turns(turns)
	return chunk_sets, turns, tts_safety_rule_counts, dropped_tiny_turns


def run_preflight(
	run_dir: Path,
	chunk_count: int,
	min_source_max_volume: float,
	voice_prompt_policy: str,
	voice_context_policy: str,
	device: str,
	torch_dtype: str,
	attn_implementation: str,
	generation_seed: int,
	no_progress_bar: bool,
	force: bool,
	split_long_turn_max_chars: int,
	fixed_chunk_plan_json: Path | None,
) -> dict[str, Any]:
	assert chunk_count > 0
	run_dir = run_dir.expanduser().resolve()
	node_dir = run_dir / "05-vibevoice-preflight-audition"
	chunks_dir = node_dir / "chunks"
	node_dir.mkdir(parents=True, exist_ok=True)
	progress = run_dir / "logs" / "progress.md"
	speaker_voices, voice_prompt_manifest = chunks._load_speaker_voices(run_dir, voice_prompt_policy)
	speaker_map = chunks._build_speaker_map(run_dir, speaker_voices)
	chunk_sets, turns, tts_safety_rule_counts, dropped_tiny_turns = _build_chunks(
		run_dir,
		split_long_turn_max_chars,
		fixed_chunk_plan_json,
	)
	selected_chunks = chunk_sets[:chunk_count]
	assert selected_chunks, "No chunks available for preflight audition"
	voice_prompt_manifest_sha256 = chunks._sha256(Path(voice_prompt_manifest)) if voice_prompt_manifest else None
	script_sha256 = chunks._sha256(run_dir / "podcast_script.md")
	jobs: list[dict[str, Any]] = []
	chunk_plan: list[dict[str, Any]] = []
	for index, chunk_turns in enumerate(selected_chunks, start=1):
		chunk_id = f"chunk_{index:03d}"
		vibevoice_mode, speaker_names = chunks._vibevoice_mode(chunk_turns, speaker_voices, voice_context_policy)
		chunk_dir = chunks_dir / chunk_id
		audio_dir = chunk_dir / "audio"
		raw_dir = audio_dir / "vibevoice_raw"
		raw_wav = raw_dir / "vibevoice_dialogue_generated.wav"
		if force and raw_dir.exists():
			for old_file in raw_dir.glob("*.wav"):
				old_file.unlink()
		chunk_dir.mkdir(parents=True, exist_ok=True)
		audio_dir.mkdir(parents=True, exist_ok=True)
		chunks._write_chunk_script(chunk_dir / "podcast_script.md", chunk_turns)
		chunks._write_chunk_speaker_map(chunk_dir, run_dir, speaker_map)
		prepare_code = chunks._run_quick(
			[
				"python3",
				str(chunks.PREPARE_SCRIPT),
				"--project-dir",
				str(chunk_dir),
				"--min-speaker-turns",
				str(chunks.MIN_SPEAKER_TURNS_PER_CHUNK),
			],
			chunk_dir / "prepare.stdout.json",
			chunk_dir / "prepare.stderr.txt",
		)
		assert prepare_code == 0, f"prepare failed for {chunk_id}; see {chunk_dir / 'prepare.stderr.txt'}"
		jobs.append({
			"job_id": chunk_id,
			"txt_path": str(audio_dir / "vibevoice_dialogue.txt"),
			"output_dir": str(raw_dir),
			"speaker_mode": vibevoice_mode,
			"speaker_names": speaker_names,
			"force": True,
			"speaker_index_base": "0" if chunks._is_locked_roster_policy(voice_context_policy) else "auto",
			"voice_context_policy": voice_context_policy,
			"seed": generation_seed,
		})
		chunk_plan.append({
			"chunk_id": chunk_id,
			"turn_start": chunk_turns[0]["turn_index"],
			"turn_end": chunk_turns[-1]["turn_index"],
			"turn_count": len(chunk_turns),
			"display_characters": sum(int(turn["char_count"]) for turn in chunk_turns),
			"max_turn_char_count": max(int(turn["char_count"]) for turn in chunk_turns),
			"speaker_counts": chunks._speaker_counts(chunk_turns),
			"vibevoice_mode": vibevoice_mode,
			"speaker_names": speaker_names,
			"raw_wav": str(raw_wav),
		})
	jobs_path = node_dir / "resident_batch_jobs.json"
	report_path = node_dir / "resident_batch_report.json"
	_write_json(jobs_path, {
		"schema_version": "worldview-china-vibevoice-preflight-jobs.v1",
		"run_dir": str(run_dir),
		"voice_prompt_manifest": voice_prompt_manifest,
		"voice_prompt_manifest_sha256": voice_prompt_manifest_sha256,
		"voice_prompt_policy": voice_prompt_policy,
		"jobs": jobs,
	})
	_write_json(node_dir / "chunk_plan.json", {
		"schema_version": "worldview-china-vibevoice-preflight-chunk-plan.v1",
		"source_total_chunk_count": len(chunk_sets),
		"audition_chunk_count": len(selected_chunks),
		"split_long_turn_max_chars": split_long_turn_max_chars,
		"fixed_chunk_plan_json": str(fixed_chunk_plan_json) if fixed_chunk_plan_json else None,
		"tts_safety_normalization_rule_counts": tts_safety_rule_counts,
		"dropped_tiny_tts_turn_count": len(dropped_tiny_turns),
		"chunks": chunk_plan,
	})
	resident_cmd = [
		str(chunks.VIBEVOICE_PYTHON),
		str(chunks.RESIDENT_BATCH_SCRIPT),
		"--jobs-json",
		str(jobs_path),
		"--report-json",
		str(report_path),
		"--device",
		device,
		"--torch-dtype",
		torch_dtype,
		"--attn-implementation",
		attn_implementation,
		"--speaker-mode",
		"auto",
	]
	if no_progress_bar:
		resident_cmd.append("--no-progress-bar")
	start = time.time()
	resident_code = chunks._run_logged(
		resident_cmd,
		run_dir,
		node_dir / "resident_batch.stdout.txt",
		node_dir / "resident_batch.stderr.txt",
		progress,
		"VibeVoice preflight audition",
	)
	(node_dir / "resident_batch.exitcode").write_text(str(resident_code) + "\n", encoding="utf-8")
	assert resident_code == 0, f"Resident VibeVoice preflight failed; see {node_dir / 'resident_batch.stderr.txt'}"
	rows: list[dict[str, Any]] = []
	for item in chunk_plan:
		raw_wav = Path(str(item["raw_wav"]))
		assert raw_wav.exists(), f"Missing preflight raw wav: {raw_wav}"
		volume = _volumedetect(raw_wav)
		row = {
			**item,
			"duration_sec": round(_duration(raw_wav), 3),
			**volume,
			"passes_min_source_max_volume": volume["max_volume_dbfs"] >= min_source_max_volume,
		}
		rows.append(row)
	status = "PASS" if all(bool(row["passes_min_source_max_volume"]) for row in rows) else "FAIL"
	result = {
		"schema_version": "worldview-china-vibevoice-preflight-audition-result.v1",
		"status": status,
		"run_dir": str(run_dir),
		"node_dir": str(node_dir),
		"audition_chunk_count": len(rows),
		"source_total_chunk_count": len(chunk_sets),
		"min_source_max_volume_dbfs": min_source_max_volume,
		"script_sha256": script_sha256,
		"voice_prompt_manifest": voice_prompt_manifest,
		"voice_prompt_manifest_sha256": voice_prompt_manifest_sha256,
		"voice_prompt_policy": voice_prompt_policy,
		"voice_context_policy": voice_context_policy,
		"vibevoice_device": device,
		"vibevoice_torch_dtype": torch_dtype,
		"vibevoice_attn_implementation": attn_implementation,
		"vibevoice_generation_seed": generation_seed,
		"elapsed_sec": round(time.time() - start, 3),
		"rows": rows,
		"failure_guidance": (
			"If status is FAIL, do not start full 05 generation. First regenerate 02c prompts with cleaner 02b clips "
			"or topic-matched target text. If still unclear, run a 2x2 text/voice crosscheck against a known-good run."
			if status == "FAIL"
			else None
		),
	}
	_write_json(node_dir / "preflight_audition_result.json", result)
	(node_dir / "preflight_audition_report.md").write_text(
		"\n".join([
			"# VibeVoice Preflight Audition",
			"",
			f"- status: {status}",
			f"- min_source_max_volume_dbfs: {min_source_max_volume}",
			f"- audition_chunk_count: {len(rows)}",
			f"- source_total_chunk_count: {len(chunk_sets)}",
			f"- voice_prompt_manifest: {voice_prompt_manifest}",
			"",
			"| chunk | mean dBFS | max dBFS | pass | duration |",
			"|---|---:|---:|---:|---:|",
			*[
				f"| {row['chunk_id']} | {row['mean_volume_dbfs']:.1f} | {row['max_volume_dbfs']:.1f} | "
				f"{str(row['passes_min_source_max_volume']).upper()} | {row['duration_sec']:.1f}s |"
				for row in rows
			],
			"",
			(
				"FAIL means full 05 generation should not start until 02b/02c voice prompts are repaired."
				if status == "FAIL"
				else "PASS means these audition chunks cleared the raw-level gate; continue full 05 generation."
			),
		]) + "\n",
		encoding="utf-8",
	)
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = chunks._read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["05-vibevoice-preflight-audition"] = {
		"status": status.lower(),
		"result": str(node_dir / "preflight_audition_result.json"),
		"report": str(node_dir / "preflight_audition_report.md"),
		"min_source_max_volume_dbfs": min_source_max_volume,
		"audition_chunk_count": len(rows),
	}
	chunks._write_json(run_manifest_path, run_manifest)
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Run a short VibeVoice raw-level audition before full Worldview China 05 generation.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--chunk-count", type=int, default=DEFAULT_AUDITION_CHUNK_COUNT)
	parser.add_argument("--min-source-max-volume", type=float, default=DEFAULT_MIN_SOURCE_MAX_VOLUME)
	parser.add_argument("--voice-prompt-policy", choices=sorted(chunks.VOICE_PROMPT_POLICIES), default="qwen_chinese_required")
	parser.add_argument("--voice-context-policy", choices=sorted(chunks.VOICE_CONTEXT_POLICIES), default="locked_multi_speaker_roster")
	parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default=chunks.DEFAULT_VIBEVOICE_DEVICE)
	parser.add_argument("--torch-dtype", choices=("auto", "float32", "float16", "bfloat16"), default=chunks.DEFAULT_VIBEVOICE_TORCH_DTYPE)
	parser.add_argument("--attn-implementation", choices=("auto", "eager", "sdpa", "flash_attention_2"), default=chunks.DEFAULT_VIBEVOICE_ATTN_IMPLEMENTATION)
	parser.add_argument("--generation-seed", type=int, default=42)
	parser.add_argument("--no-progress-bar", action="store_true")
	parser.add_argument("--force", action="store_true")
	parser.add_argument("--split-long-turn-max-chars", type=int, default=chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS)
	parser.add_argument("--fixed-chunk-plan-json", type=Path)
	args = parser.parse_args()
	result = run_preflight(
		args.run_dir,
		args.chunk_count,
		args.min_source_max_volume,
		args.voice_prompt_policy,
		args.voice_context_policy,
		args.device,
		args.torch_dtype,
		args.attn_implementation,
		args.generation_seed,
		args.no_progress_bar,
		args.force,
		args.split_long_turn_max_chars,
		args.fixed_chunk_plan_json.expanduser().resolve() if args.fixed_chunk_plan_json else None,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
