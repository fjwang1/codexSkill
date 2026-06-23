#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


PREPARE_SCRIPT = Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py")
RUN_SCRIPT = Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/run_article_vibevoice_audio.py")
POSTPROCESS_SCRIPT = Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/postprocess_vibevoice_audio.py")
RESIDENT_BATCH_SCRIPT = Path("/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_resident_batch.py")
VIBEVOICE_PYTHON = Path("/Users/wangfangjia/code/VibeVoice/.venv/bin/python")
RUNTIME_PYTHON = Path("/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")

TARGET_CHARS = 600
MIN_SPLIT_CHARS = 350
HARD_MAX_CHARS = 800
DEFAULT_SPLIT_LONG_TURN_MAX_CHARS = 220
MIN_SPEAKER_TURNS_PER_CHUNK = 0
INTER_CHUNK_PAUSE_SEC = 0.5
DEFAULT_SPEAKER_VOICES = {
	"Speaker 0": "Xinran",
	"Speaker 1": "BowenClean",
}
VOICE_PROMPT_POLICIES = {
	"qwen_chinese_required",
	"source_chinese_direct",
}
GENERATION_RUNNERS = {
	"resident_batch",
	"legacy_per_chunk",
}


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def _parse_turns(script_path: Path) -> list[dict[str, Any]]:
	turns: list[dict[str, Any]] = []
	for raw_line in script_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		match = re.match(r"^(Speaker [01])[:：]\s*(.+)$", line)
		if not match:
			continue
		text = re.sub(r"\s+", "", match.group(2)).strip()
		turns.append({
			"turn_index": len(turns) + 1,
			"speaker": match.group(1),
			"display_role": "女主持" if match.group(1) == "Speaker 0" else "男嘉宾",
			"text": text,
			"char_count": len(text),
		})
	assert turns, f"No Speaker turns found in {script_path}"
	return turns


def _split_long_text(text: str, max_chars: int) -> list[str]:
	assert max_chars > 0
	if len(text) <= max_chars:
		return [text]
	sentence_parts = re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text)
	if not sentence_parts:
		sentence_parts = [text]
	pieces: list[str] = []
	current = ""
	for part in sentence_parts:
		part = part.strip()
		if not part:
			continue
		if len(part) > max_chars:
			sub_parts = re.findall(r"[^，,、]+[，,、]?", part) or [part]
		else:
			sub_parts = [part]
		for sub_part in sub_parts:
			sub_part = sub_part.strip()
			if not sub_part:
				continue
			if len(sub_part) > max_chars:
				if current:
					pieces.append(current)
					current = ""
				for start in range(0, len(sub_part), max_chars):
					pieces.append(sub_part[start:start + max_chars])
				continue
			if current and len(current) + len(sub_part) > max_chars:
				pieces.append(current)
				current = sub_part
			else:
				current += sub_part
	if current:
		pieces.append(current)
	return [piece for piece in pieces if piece]


def _split_long_turns(turns: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
	if max_chars <= 0:
		return turns
	result: list[dict[str, Any]] = []
	for turn in turns:
		pieces = _split_long_text(str(turn["text"]), max_chars)
		for part_index, piece in enumerate(pieces, start=1):
			new_turn = dict(turn)
			new_turn["source_turn_index"] = int(turn["turn_index"])
			new_turn["source_part_index"] = part_index
			new_turn["source_part_count"] = len(pieces)
			new_turn["text"] = piece
			new_turn["char_count"] = len(piece)
			result.append(new_turn)
	for index, turn in enumerate(result, start=1):
		turn["turn_index"] = index
	return result


def _speaker_counts(turns: list[dict[str, Any]]) -> dict[str, int]:
	return {
		"Speaker 0": sum(1 for turn in turns if turn["speaker"] == "Speaker 0"),
		"Speaker 1": sum(1 for turn in turns if turn["speaker"] == "Speaker 1"),
	}


def _speaker_voices_from_manifest(manifest_path: Path) -> dict[str, str] | None:
	if not manifest_path.exists():
		return None
	manifest = _read_json(manifest_path)
	if manifest.get("status") != "pass":
		return None
	speaker_voices = manifest.get("speaker_voices")
	if not isinstance(speaker_voices, dict):
		return None
	result = dict(DEFAULT_SPEAKER_VOICES)
	for speaker in ("Speaker 0", "Speaker 1"):
		info = speaker_voices.get(speaker)
		if not isinstance(info, dict) or not info.get("vibevoice_name"):
			return None
		result[speaker] = str(info["vibevoice_name"])
	return result


def _load_speaker_voices(run_dir: Path, voice_prompt_policy: str) -> tuple[dict[str, str], str | None]:
	assert voice_prompt_policy in VOICE_PROMPT_POLICIES
	qwen_manifest_path = run_dir / "02c-qwen-vibevoice-prompts" / "voice_prompt_manifest.json"
	qwen_voices = _speaker_voices_from_manifest(qwen_manifest_path)
	if qwen_voices is not None:
		return qwen_voices, str(qwen_manifest_path)
	source_manifest_path = run_dir / "02b-source-voice-prompts" / "voice_prompt_manifest.json"
	if voice_prompt_policy == "source_chinese_direct":
		source_voices = _speaker_voices_from_manifest(source_manifest_path)
		if source_voices is not None:
			return source_voices, str(source_manifest_path)
		raise RuntimeError(
			"voice_prompt_policy=source_chinese_direct requires a passing "
			f"source Chinese/direct prompt manifest: {source_manifest_path}"
		)
	raise RuntimeError(
		"English/non-Chinese source podcast runs must use Qwen3 Chinese VibeVoice prompts. "
		f"Missing or invalid required manifest: {qwen_manifest_path}. "
		"Run 02c-qwen-vibevoice-prompts before 05, or use "
		"--voice-prompt-policy source_chinese_direct only for already-Chinese source audio."
	)


def _vibevoice_mode(turns: list[dict[str, Any]], speaker_voices: dict[str, str]) -> tuple[str, list[str]]:
	counts = _speaker_counts(turns)
	present = [speaker for speaker in ("Speaker 0", "Speaker 1") if counts[speaker] > 0]
	assert present, "Cannot run VibeVoice on an empty chunk"
	if len(present) == 1:
		return "single", [speaker_voices[present[0]]]
	return "dialogue", [speaker_voices["Speaker 0"], speaker_voices["Speaker 1"]]


def _chunk_turns(turns: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
	count = len(turns)
	prefix_chars = [0]
	for turn in turns:
		prefix_chars.append(prefix_chars[-1] + int(turn["char_count"]))

	def span_chars(start: int, end: int) -> int:
		return prefix_chars[end] - prefix_chars[start]

	def span_ready(start: int, end: int) -> bool:
		return _speaker_ready(turns[start:end])

	best: list[tuple[float, int | None]] = [(float("inf"), None) for _ in range(count + 1)]
	best[count] = (0.0, None)
	for start in range(count - 1, -1, -1):
		for end in range(start + 1, count + 1):
			chars = span_chars(start, end)
			if chars > HARD_MAX_CHARS:
				break
			if not span_ready(start, end):
				continue
			next_cost, _ = best[end]
			if next_cost == float("inf"):
				continue
			too_short_penalty = max(0, MIN_SPLIT_CHARS - chars) / TARGET_CHARS
			target_penalty = abs(chars - TARGET_CHARS) / TARGET_CHARS
			cost = 1.0 + (target_penalty * 0.1) + (too_short_penalty * 0.5) + next_cost
			if cost < best[start][0]:
				best[start] = (cost, end)

	if best[0][1] is None:
		raise RuntimeError(
			"Unable to build VibeVoice chunks that satisfy configured speaker turn minimums "
			f"within hard_max_chars={HARD_MAX_CHARS}."
		)

	chunks: list[list[dict[str, Any]]] = []
	start = 0
	while start < count:
		end = best[start][1]
		assert end is not None
		chunks.append(turns[start:end])
		start = end
	return chunks


def _chunk_turns_from_fixed_plan(turns: list[dict[str, Any]], plan_path: Path) -> list[list[dict[str, Any]]]:
	plan = _read_json(plan_path)
	plan_chunks = list(plan.get("chunks") or [])
	assert plan_chunks, f"Fixed chunk plan has no chunks: {plan_path}"
	turn_lookup = {int(turn["turn_index"]): turn for turn in turns}
	chunks: list[list[dict[str, Any]]] = []
	for item in plan_chunks:
		start = int(item["turn_start"])
		end = int(item["turn_end"])
		assert start <= end, f"Invalid fixed chunk range in {plan_path}: {start}-{end}"
		chunk = [turn_lookup[index] for index in range(start, end + 1)]
		assert chunk, f"Fixed chunk range produced no turns: {start}-{end}"
		chunks.append(chunk)
	covered = [int(turn["turn_index"]) for chunk in chunks for turn in chunk]
	expected = list(range(1, len(turns) + 1))
	assert covered == expected, (
		f"Fixed chunk plan must cover current turns contiguously. "
		f"covered={covered[:5]}...{covered[-5:]} expected={expected[:5]}...{expected[-5:]}"
	)
	return chunks


def _chunk_chars(turns: list[dict[str, Any]]) -> int:
	return sum(int(turn["char_count"]) for turn in turns)


def _speaker_ready(turns: list[dict[str, Any]]) -> bool:
	counts = _speaker_counts(turns)
	return (
		counts["Speaker 0"] >= MIN_SPEAKER_TURNS_PER_CHUNK
		and counts["Speaker 1"] >= MIN_SPEAKER_TURNS_PER_CHUNK
	)


def _rebalance_tail_chunks(chunks: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
	if len(chunks) < 2 or _speaker_ready(chunks[-1]):
		return chunks
	previous = chunks[-2]
	tail = chunks[-1]
	while previous and not _speaker_ready(tail):
		candidate_tail = [previous[-1], *tail]
		candidate_previous = previous[:-1]
		if _chunk_chars(candidate_tail) > HARD_MAX_CHARS:
			break
		if candidate_previous and not _speaker_ready(candidate_previous):
			break
		tail = candidate_tail
		previous = candidate_previous
	chunks[-2] = previous
	chunks[-1] = tail
	return [chunk for chunk in chunks if chunk]


def _split_selected_chunks(
	chunks: list[list[dict[str, Any]]],
	chunk_indices: set[int],
	max_chars: int,
	split_all_chunks: bool,
) -> list[list[dict[str, Any]]]:
	if not chunk_indices and not split_all_chunks:
		return chunks
	assert max_chars > 0
	result: list[list[dict[str, Any]]] = []
	for original_index, chunk in enumerate(chunks, start=1):
		if not split_all_chunks and original_index not in chunk_indices:
			result.append(chunk)
			continue
		current: list[dict[str, Any]] = []
		current_chars = 0
		for turn in chunk:
			turn_chars = int(turn["char_count"])
			if current and current_chars + turn_chars > max_chars:
				result.append(current)
				current = [turn]
				current_chars = turn_chars
			else:
				current.append(turn)
				current_chars += turn_chars
		if current:
			result.append(current)
	return result


def _write_chunk_script(path: Path, turns: list[dict[str, Any]]) -> None:
	lines = ["---", "schema_version: worldview-china-vibevoice-chunk-script.v1", "---", "", "## 正文", ""]
	lines.extend(f"{turn['speaker']}: {turn['text']}" for turn in turns)
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _run_logged(cmd: list[str], cwd: Path, stdout_path: Path, stderr_path: Path, heartbeat_path: Path, label: str) -> int:
	stdout_path.parent.mkdir(parents=True, exist_ok=True)
	heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
	with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
		process = subprocess.Popen(cmd, cwd=str(cwd), stdout=stdout, stderr=stderr, text=True)
		start = time.time()
		last_heartbeat = 0.0
		while process.poll() is None:
			elapsed = time.time() - start
			if elapsed - last_heartbeat >= 60:
				with heartbeat_path.open("a", encoding="utf-8") as heartbeat:
					heartbeat.write(f"- {time.strftime('%Y-%m-%d %H:%M:%S')} {label} running elapsed_sec={elapsed:.0f}\n")
				last_heartbeat = elapsed
			time.sleep(5)
		return int(process.returncode or 0)


def _run_quick(cmd: list[str], stdout_path: Path, stderr_path: Path) -> int:
	completed = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	stdout_path.write_text(completed.stdout, encoding="utf-8")
	stderr_path.write_text(completed.stderr, encoding="utf-8")
	return int(completed.returncode)


def _ffprobe_json(path: Path, output: Path) -> None:
	completed = subprocess.run(
		["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	output.write_text(completed.stdout, encoding="utf-8")


def _run_audio_checks(path: Path, out_dir: Path, prefix: str) -> dict[str, Any]:
	volume_code = _run_quick(
		["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
		out_dir / f"{prefix}.volumedetect.stdout.txt",
		out_dir / f"{prefix}.volumedetect.stderr.txt",
	)
	silence_code = _run_quick(
		["ffmpeg", "-hide_banner", "-i", str(path), "-af", "silencedetect=noise=-45dB:d=2", "-f", "null", "-"],
		out_dir / f"{prefix}.silencedetect.stdout.txt",
		out_dir / f"{prefix}.silencedetect.stderr.txt",
	)
	return {"volumedetect_returncode": volume_code, "silencedetect_returncode": silence_code}


def _copy_tree_file(src: Path, dst: Path) -> None:
	dst.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(src, dst)


def run_chunks(
	run_dir: Path,
	force: bool,
	force_chunk_ids: set[str],
	dry_run: bool,
	no_progress_bar: bool,
	split_chunk_indices: set[int],
	split_max_chars: int,
	split_all_chunks: bool,
	split_long_turn_max_chars: int,
	fixed_chunk_plan_json: Path | None,
	postprocess_min_source_max_volume: float,
	voice_prompt_policy: str,
	generation_runner: str,
	device: str,
	torch_dtype: str,
	attn_implementation: str,
) -> dict[str, Any]:
	assert PREPARE_SCRIPT.exists()
	assert RUN_SCRIPT.exists()
	assert POSTPROCESS_SCRIPT.exists()
	assert generation_runner in GENERATION_RUNNERS
	if generation_runner == "resident_batch":
		assert RESIDENT_BATCH_SCRIPT.exists(), f"Missing resident batch script: {RESIDENT_BATCH_SCRIPT}"
		assert VIBEVOICE_PYTHON.exists(), f"Missing VibeVoice Python: {VIBEVOICE_PYTHON}"
	python_for_post = RUNTIME_PYTHON if RUNTIME_PYTHON.exists() else Path("python3")
	script_path = run_dir / "04-podcast-script" / "podcast_script.md"
	speaker_voices, voice_prompt_manifest = _load_speaker_voices(run_dir, voice_prompt_policy)
	turns = _parse_turns(script_path)
	turns = _split_long_turns(turns, split_long_turn_max_chars)
	if split_long_turn_max_chars > 0:
		max_turn_chars = max(int(turn["char_count"]) for turn in turns)
		assert max_turn_chars <= split_long_turn_max_chars, (
			"Long speaker turn split failed: "
			f"max_turn_chars={max_turn_chars} limit={split_long_turn_max_chars}"
		)
	if fixed_chunk_plan_json is not None:
		chunks = _chunk_turns_from_fixed_plan(turns, fixed_chunk_plan_json)
	else:
		chunks = _chunk_turns(turns)
		chunks = _split_selected_chunks(chunks, split_chunk_indices, split_max_chars, split_all_chunks)
	node_dir = run_dir / "05-vibevoice-chunks"
	chunks_dir = node_dir / "chunks"
	node_dir.mkdir(parents=True, exist_ok=True)
	progress = run_dir / "logs" / "progress.md"
	chunk_plan: list[dict[str, Any]] = []
	for index, chunk_turns in enumerate(chunks, start=1):
		chunk_id = f"chunk_{index:03d}"
		display_chars = sum(int(turn["char_count"]) for turn in chunk_turns)
		vibevoice_mode, speaker_names = _vibevoice_mode(chunk_turns, speaker_voices)
		chunk_plan.append({
			"chunk_id": chunk_id,
			"turn_start": chunk_turns[0]["turn_index"],
			"turn_end": chunk_turns[-1]["turn_index"],
			"turn_count": len(chunk_turns),
			"display_characters": display_chars,
			"max_turn_char_count": max(int(turn["char_count"]) for turn in chunk_turns),
			"speaker_counts": _speaker_counts(chunk_turns),
			"vibevoice_mode": vibevoice_mode,
			"speaker_names": speaker_names,
		})
	_write_json(node_dir / "chunk_plan.json", {
		"schema_version": "worldview-china-vibevoice-chunk-plan.v1",
		"target_chars": TARGET_CHARS,
		"min_split_chars": MIN_SPLIT_CHARS,
		"hard_max_chars": HARD_MAX_CHARS,
		"min_speaker_turns_per_chunk": MIN_SPEAKER_TURNS_PER_CHUNK,
		"split_chunk_indices": sorted(split_chunk_indices),
		"split_all_chunks": split_all_chunks,
		"split_max_chars": split_max_chars if split_chunk_indices or split_all_chunks else None,
		"split_long_turn_max_chars": split_long_turn_max_chars if split_long_turn_max_chars > 0 else None,
		"default_split_long_turn_max_chars": DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
		"fixed_chunk_plan_json": str(fixed_chunk_plan_json) if fixed_chunk_plan_json is not None else None,
		"force_chunk_ids": sorted(force_chunk_ids),
		"speaker_voices": speaker_voices,
		"voice_prompt_manifest": voice_prompt_manifest,
		"voice_prompt_policy": voice_prompt_policy,
		"vibevoice_runner": generation_runner,
		"vibevoice_device": device,
		"vibevoice_torch_dtype": torch_dtype,
		"vibevoice_attn_implementation": attn_implementation,
		"chunk_count": len(chunk_plan),
		"chunks": chunk_plan,
	})
	if dry_run:
		return {"status": "dry_run", "chunk_count": len(chunks), "chunk_plan": str(node_dir / "chunk_plan.json")}

	chunk_contexts: list[dict[str, Any]] = []
	resident_jobs: list[dict[str, Any]] = []
	for index, chunk_turns in enumerate(chunks, start=1):
		chunk_id = f"chunk_{index:03d}"
		vibevoice_mode, speaker_names = _vibevoice_mode(chunk_turns, speaker_voices)
		chunk_dir = chunks_dir / chunk_id
		audio_dir = chunk_dir / "audio"
		final_wav = audio_dir / "final_podcast.wav"
		chunk_dir.mkdir(parents=True, exist_ok=True)
		audio_dir.mkdir(parents=True, exist_ok=True)
		_write_chunk_script(chunk_dir / "podcast_script.md", chunk_turns)
		needs_generation = not final_wav.exists() or force or chunk_id in force_chunk_ids
		context = {
			"chunk_id": chunk_id,
			"chunk_turns": chunk_turns,
			"chunk_dir": chunk_dir,
			"audio_dir": audio_dir,
			"final_wav": final_wav,
			"vibevoice_mode": vibevoice_mode,
			"speaker_names": speaker_names,
			"needs_generation": needs_generation,
		}
		chunk_contexts.append(context)
		if not needs_generation:
			continue
		prepare_code = _run_quick(
			[
				"python3",
				str(PREPARE_SCRIPT),
				"--project-dir",
				str(chunk_dir),
				"--min-speaker-turns",
				str(MIN_SPEAKER_TURNS_PER_CHUNK),
			],
			chunk_dir / "prepare.stdout.json",
			chunk_dir / "prepare.stderr.txt",
		)
		assert prepare_code == 0, f"prepare failed for {chunk_id}; see {chunk_dir / 'prepare.stderr.txt'}"
		if generation_runner == "resident_batch":
			resident_jobs.append({
				"job_id": chunk_id,
				"txt_path": str(audio_dir / "vibevoice_dialogue.txt"),
				"output_dir": str(audio_dir / "vibevoice_raw"),
				"speaker_mode": vibevoice_mode,
				"speaker_names": speaker_names,
				"force": True,
				"speaker_index_base": "auto",
			})
			continue
		run_cmd = [
			"python3",
			str(RUN_SCRIPT),
			"--project-dir",
			str(chunk_dir),
			"--speaker-mode",
			vibevoice_mode,
			"--speaker-names",
			*speaker_names,
		]
		if no_progress_bar:
			run_cmd.append("--no-progress-bar")
		run_code = _run_logged(
			run_cmd,
			run_dir,
			chunk_dir / "vibevoice.stdout.txt",
			chunk_dir / "vibevoice.stderr.txt",
			progress,
			f"VibeVoice {chunk_id}",
		)
		(chunk_dir / "vibevoice.exitcode").write_text(str(run_code) + "\n", encoding="utf-8")
		assert run_code == 0, f"VibeVoice failed for {chunk_id}; see {chunk_dir / 'vibevoice.stderr.txt'}"
		post_code = _run_quick(
			[
				str(python_for_post),
				str(POSTPROCESS_SCRIPT),
				"--project-dir",
				str(chunk_dir),
				"--min-source-max-volume",
				str(postprocess_min_source_max_volume),
			],
			chunk_dir / "postprocess.stdout.json",
			chunk_dir / "postprocess.stderr.txt",
		)
		assert post_code == 0, f"postprocess failed for {chunk_id}; see {chunk_dir / 'postprocess.stderr.txt'}"

	if resident_jobs:
		resident_jobs_path = node_dir / "resident_batch_jobs.json"
		resident_report_path = node_dir / "resident_batch_report.json"
		_write_json(resident_jobs_path, {
			"schema_version": "worldview-china-vibevoice-resident-jobs.v1",
			"run_dir": str(run_dir),
			"voice_prompt_manifest": voice_prompt_manifest,
			"voice_prompt_policy": voice_prompt_policy,
			"jobs": resident_jobs,
		})
		resident_cmd = [
			str(VIBEVOICE_PYTHON),
			str(RESIDENT_BATCH_SCRIPT),
			"--jobs-json",
			str(resident_jobs_path),
			"--report-json",
			str(resident_report_path),
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
		resident_code = _run_logged(
			resident_cmd,
			run_dir,
			node_dir / "resident_batch.stdout.txt",
			node_dir / "resident_batch.stderr.txt",
			progress,
			"VibeVoice resident batch",
		)
		(node_dir / "resident_batch.exitcode").write_text(str(resident_code) + "\n", encoding="utf-8")
		assert resident_code == 0, f"Resident VibeVoice batch failed; see {node_dir / 'resident_batch.stderr.txt'}"
		for context in chunk_contexts:
			if not context["needs_generation"]:
				continue
			chunk_dir = context["chunk_dir"]
			post_code = _run_quick(
				[
					str(python_for_post),
					str(POSTPROCESS_SCRIPT),
					"--project-dir",
					str(chunk_dir),
					"--min-source-max-volume",
					str(postprocess_min_source_max_volume),
				],
				chunk_dir / "postprocess.stdout.json",
				chunk_dir / "postprocess.stderr.txt",
			)
			assert post_code == 0, f"postprocess failed for {context['chunk_id']}; see {chunk_dir / 'postprocess.stderr.txt'}"

	chunk_results: list[dict[str, Any]] = []
	for context in chunk_contexts:
		chunk_id = str(context["chunk_id"])
		chunk_turns = context["chunk_turns"]
		chunk_dir = context["chunk_dir"]
		final_wav = context["final_wav"]
		vibevoice_mode = str(context["vibevoice_mode"])
		speaker_names = list(context["speaker_names"])
		assert final_wav.exists(), f"Missing chunk final wav: {final_wav}"
		_ffprobe_json(final_wav, chunk_dir / "ffprobe.final.json")
		checks = _run_audio_checks(final_wav, chunk_dir, "chunk")
		chunk_manifest = {
			"schema_version": "worldview-china-vibevoice-chunk.v1",
			"chunk_id": chunk_id,
			"turn_start": chunk_turns[0]["turn_index"],
			"turn_end": chunk_turns[-1]["turn_index"],
			"turn_count": len(chunk_turns),
			"display_characters": sum(int(turn["char_count"]) for turn in chunk_turns),
			"vibevoice_mode": vibevoice_mode,
			"speaker_names": speaker_names,
			"vibevoice_runner": generation_runner,
			"audio": str(final_wav),
			"duration_sec": round(_duration(final_wav), 3),
			"audio_sha256": _sha256(final_wav),
			"checks": checks,
		}
		_write_json(chunk_dir / "chunk_manifest.json", chunk_manifest)
		chunk_results.append(chunk_manifest)

	silence_path = node_dir / "inter_chunk_pause.wav"
	subprocess.run(
		["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(INTER_CHUNK_PAUSE_SEC), "-c:a", "pcm_s16le", str(silence_path)],
		check=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	concat_path = node_dir / "concat.txt"
	concat_lines: list[str] = []
	for index, result in enumerate(chunk_results):
		concat_lines.append(f"file '{Path(result['audio']).as_posix()}'")
		if index + 1 < len(chunk_results):
			concat_lines.append(f"file '{silence_path.as_posix()}'")
	concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
	final_audio = node_dir / "final_podcast.wav"
	subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy", str(final_audio)], check=True)
	subprocess.run(["ffmpeg", "-y", "-i", str(final_audio), "-codec:a", "libmp3lame", "-b:a", "128k", str(node_dir / "final_podcast_preview.mp3")], check=True)
	subprocess.run(["ffmpeg", "-y", "-i", str(final_audio), "-c:a", "aac", "-b:a", "128k", str(node_dir / "final_podcast_playback.m4a")], check=True)
	_ffprobe_json(final_audio, node_dir / "ffprobe.final.json")
	final_checks = _run_audio_checks(final_audio, node_dir, "final")

	global_start = 0.0
	for result in chunk_results:
		duration = float(result["duration_sec"])
		result["global_start_sec"] = round(global_start, 3)
		result["global_end_sec"] = round(global_start + duration, 3)
		global_start += duration + INTER_CHUNK_PAUSE_SEC
	if chunk_results:
		chunk_results[-1]["global_end_sec"] = round(_duration(final_audio), 3)

	turn_lookup: dict[int, dict[str, Any]] = {int(turn["turn_index"]): dict(turn) for turn in turns}
	for result in chunk_results:
		for turn_index in range(int(result["turn_start"]), int(result["turn_end"]) + 1):
			turn_lookup[turn_index]["chunk_id"] = result["chunk_id"]
	aggregate_turns = [turn_lookup[index] for index in sorted(turn_lookup)]
	manifest = {
		"schema_version": "worldview-china-podcast-vibevoice-audio.v1",
		"audio_backend": "vibevoice_chunked_dialogue",
		"generation_mode": "semantic_chunked_vibevoice",
		"generation_status": "complete",
		"speaker_voices": speaker_voices,
		"voice_prompt_manifest": voice_prompt_manifest,
		"voice_prompt_policy": voice_prompt_policy,
		"vibevoice_runner": generation_runner,
		"vibevoice_device": device,
		"vibevoice_torch_dtype": torch_dtype,
		"vibevoice_attn_implementation": attn_implementation,
		"resident_batch_report": "05-vibevoice-chunks/resident_batch_report.json" if generation_runner == "resident_batch" else None,
		"script": "podcast_script.md",
		"script_sha256": _sha256(run_dir / "podcast_script.md"),
		"final_audio": "audio/final_podcast.wav",
		"final_audio_node_path": "05-vibevoice-chunks/final_podcast.wav",
		"final_audio_sha256": _sha256(final_audio),
		"duration_sec": round(_duration(final_audio), 3),
		"chunk_count": len(chunk_results),
		"inter_chunk_pause_sec": INTER_CHUNK_PAUSE_SEC,
		"chunks": [
			{
				"chunk_id": result["chunk_id"],
				"turn_start": result["turn_start"],
				"turn_end": result["turn_end"],
				"global_start_sec": result["global_start_sec"],
				"global_end_sec": result["global_end_sec"],
				"duration_sec": result["duration_sec"],
				"audio": str(Path(result["audio"]).relative_to(run_dir)),
				"audio_sha256": result["audio_sha256"],
				"display_characters": result["display_characters"],
				"vibevoice_mode": result["vibevoice_mode"],
				"speaker_names": result["speaker_names"],
			}
			for result in chunk_results
		],
		"turn_count": len(aggregate_turns),
		"turns": aggregate_turns,
		"checks": final_checks,
	}
	_write_json(node_dir / "audio_manifest.json", manifest)
	(node_dir / "audio_report.md").write_text(
		"\n".join([
			"# VibeVoice Chunk Audio Report",
			"",
				"- status: PASS",
				"- audio_backend: vibevoice_chunked_dialogue",
				f"- vibevoice_runner: {generation_runner}",
				f"- vibevoice_device: {device}",
				f"- chunk_count: {len(chunk_results)}",
				f"- duration_sec: {manifest['duration_sec']}",
				f"- final_audio: {final_audio}",
		]) + "\n",
		encoding="utf-8",
	)

	root_audio = run_dir / "audio"
	root_audio.mkdir(parents=True, exist_ok=True)
	for name in ["final_podcast.wav", "final_podcast_preview.mp3", "final_podcast_playback.m4a", "audio_manifest.json"]:
		src = node_dir / name
		if name == "audio_manifest.json":
			src = node_dir / "audio_manifest.json"
		_copy_tree_file(src, root_audio / name)

	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["05-vibevoice-chunks"] = {
		"status": "pass",
		"chunk_plan": str(node_dir / "chunk_plan.json"),
		"chunk_count": len(chunk_results),
		"final_audio": str(final_audio),
		"root_final_audio": str(root_audio / "final_podcast.wav"),
		"audio_manifest": str(node_dir / "audio_manifest.json"),
		"duration_sec": manifest["duration_sec"],
		"vibevoice_runner": generation_runner,
		"vibevoice_device": device,
		"vibevoice_torch_dtype": torch_dtype,
		"vibevoice_attn_implementation": attn_implementation,
	}
	_write_json(run_manifest_path, run_manifest)
	return run_manifest["nodes"]["05-vibevoice-chunks"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Generate chunked VibeVoice audio for the translated podcast.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--force", action="store_true")
	parser.add_argument("--force-chunk-id", action="append", default=[])
	parser.add_argument("--dry-run", action="store_true")
	parser.add_argument("--no-progress-bar", action="store_true")
	parser.add_argument("--split-chunk-index", action="append", type=int, default=[])
	parser.add_argument("--split-max-chars", type=int, default=650)
	parser.add_argument("--split-all-chunks", action="store_true")
	parser.add_argument("--split-long-turn-max-chars", type=int, default=DEFAULT_SPLIT_LONG_TURN_MAX_CHARS)
	parser.add_argument("--fixed-chunk-plan-json", type=Path)
	parser.add_argument("--postprocess-min-source-max-volume", type=float, default=-8.0)
	parser.add_argument("--generation-runner", choices=sorted(GENERATION_RUNNERS), default="resident_batch")
	parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
	parser.add_argument("--torch-dtype", choices=("float32", "float16", "bfloat16"), default="float32")
	parser.add_argument("--attn-implementation", default="eager")
	parser.add_argument(
		"--voice-prompt-policy",
		choices=sorted(VOICE_PROMPT_POLICIES),
		default="qwen_chinese_required",
		help=(
			"qwen_chinese_required requires 02c Chinese Qwen prompts; "
			"source_chinese_direct allows 02b direct source prompts only for already-Chinese sources."
		),
	)
	args = parser.parse_args()
	result = run_chunks(
		args.run_dir.expanduser().resolve(),
		args.force,
		set(args.force_chunk_id),
		args.dry_run,
		args.no_progress_bar,
		set(args.split_chunk_index),
		args.split_max_chars,
		args.split_all_chunks,
		args.split_long_turn_max_chars,
		args.fixed_chunk_plan_json.expanduser().resolve() if args.fixed_chunk_plan_json else None,
		args.postprocess_min_source_max_volume,
		args.voice_prompt_policy,
		args.generation_runner,
		args.device,
		args.torch_dtype,
		args.attn_implementation,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
