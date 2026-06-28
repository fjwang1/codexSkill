#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import subprocess
from pathlib import Path
from typing import Any


OUTPUT_DIRNAME = "06d-voice-consistency-qa"
RESULT_NAME = "voice-consistency-qa-result.json"
REPORT_NAME = "voice-consistency-qa-report.md"
SPEAKER_RE = re.compile(r"^Speaker ([0-3])$")
LOCKED_POLICIES = {
	"locked_multi_speaker_roster",
	"locked_two_speaker_roster",
	"single_speaker_patch_from_locked_roster",
}
FORBIDDEN_DEFAULT_VOICES = {"Xinran", "Bowen", "BowenClean"}


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


def _speaker_index(speaker: str) -> int:
	match = SPEAKER_RE.fullmatch(speaker)
	assert match, f"Unsupported speaker id: {speaker}"
	return int(match.group(1))


def _sorted_speakers(values: Any) -> list[str]:
	speakers = [str(value) for value in values if SPEAKER_RE.fullmatch(str(value))]
	return sorted(set(speakers), key=_speaker_index)


def _resolve_run_path(run_dir: Path, value: Any) -> Path:
	path = Path(str(value))
	return path if path.is_absolute() else run_dir / path


def _duration(path: Path) -> float:
	result = subprocess.run(
		["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return float(result.stdout.strip())


def _voice_prompt_manifest_path(run_dir: Path) -> Path:
	qwen = run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json"
	return qwen if qwen.exists() else run_dir / "02b-source-voice-prompts/voice_prompt_manifest.json"


def _expected_voice_names(run_dir: Path) -> tuple[dict[str, str], dict[str, Path], Path, list[str]]:
	manifest_path = _voice_prompt_manifest_path(run_dir)
	failures: list[str] = []
	if not manifest_path.exists():
		return {}, {}, manifest_path, [f"Missing voice_prompt_manifest: {manifest_path}"]
	manifest = _read_json(manifest_path)
	if manifest.get("status") != "pass":
		failures.append("voice_prompt_manifest status is not pass")
	voices: dict[str, str] = {}
	references: dict[str, Path] = {}
	for speaker in _sorted_speakers((manifest.get("speaker_voices") or {}).keys()):
		info = (manifest.get("speaker_voices") or {}).get(speaker)
		if not isinstance(info, dict):
			failures.append(f"voice_prompt_manifest entry is not an object: {speaker}")
			continue
		voice_name = str(info.get("vibevoice_name") or "")
		if not voice_name:
			failures.append(f"voice_prompt_manifest missing vibevoice_name for {speaker}")
			continue
		voices[speaker] = voice_name
		reference_value = str(info.get("local_registered_wav") or info.get("reference_wav") or info.get("registered_path") or "")
		if reference_value:
			references[speaker] = Path(reference_value)
		else:
			failures.append(f"voice_prompt_manifest missing reference wav for {speaker}")
	return voices, references, manifest_path, failures


def _speaker_roster(run_dir: Path) -> dict[str, Any]:
	path = run_dir / "02a-speaker-census" / "speaker_roster.json"
	if not path.exists():
		return {}
	try:
		roster = _read_json(path)
	except json.JSONDecodeError:
		return {}
	return roster if isinstance(roster, dict) else {}


def _gender_hint(value: Any) -> str | None:
	text = str(value or "").lower()
	if re.search(r"\bfemale\b|\bwoman\b|\bwomen\b|女", text):
		return "female"
	if re.search(r"\bmale\b|\bman\b|\bmen\b|男", text):
		return "male"
	return None


def _speaker_roster_gender_hints(roster: dict[str, Any]) -> dict[str, str]:
	speakers = roster.get("speakers")
	if not isinstance(speakers, dict):
		return {}
	result: dict[str, str] = {}
	for speaker, info in speakers.items():
		if not isinstance(info, dict):
			continue
		hint = _gender_hint(" ".join(str(info.get(key) or "") for key in ("identity", "description", "role")))
		if hint:
			result[str(speaker)] = hint
	return result


def _speaker_map_lineage_findings(
	path: Path,
	key_path: str,
	speaker_map: dict[str, Any],
	expected_voices: dict[str, str],
	roster_gender_hints: dict[str, str],
) -> list[dict[str, Any]]:
	findings: list[dict[str, Any]] = []
	for speaker in _sorted_speakers(speaker_map.keys()):
		info = speaker_map.get(speaker)
		if not isinstance(info, dict):
			continue
		vibevoice_name = str(info.get("vibevoice_name") or "")
		if vibevoice_name and expected_voices.get(speaker) and vibevoice_name != expected_voices[speaker]:
			findings.append({
				"file": str(path),
				"path": f"{key_path}.{speaker}.vibevoice_name",
				"message": f"speaker_map vibevoice_name {vibevoice_name} does not match locked roster {expected_voices[speaker]}",
			})
		expected_gender = roster_gender_hints.get(speaker)
		role_gender = _gender_hint(" ".join(str(info.get(key) or "") for key in ("display_role", "style")))
		if expected_gender and role_gender and expected_gender != role_gender:
			findings.append({
				"file": str(path),
				"path": f"{key_path}.{speaker}.display_role",
				"message": (
					f"speaker_map role gender hint {role_gender} conflicts with 02a roster "
					f"gender hint {expected_gender} for {speaker}"
				),
			})
	return findings


def _resident_report_lineage_findings(
	path: Path,
	payload: dict[str, Any],
	expected_voices: dict[str, str],
) -> list[dict[str, Any]]:
	if "resident_batch_report" not in path.name:
		return []
	findings: list[dict[str, Any]] = []
	for index, job in enumerate(payload.get("jobs") or [], start=1):
		if not isinstance(job, dict) or job.get("status") not in {None, "pass", "skipped_existing"}:
			continue
		job_path = f"jobs[{index - 1}]"
		voice_sample_speakers = [str(value) for value in (job.get("voice_sample_speaker_numbers") or [])]
		actual_speakers = [str(value) for value in (job.get("actual_speakers") or [])]
		if job.get("status") == "pass" and (not voice_sample_speakers or not actual_speakers):
			findings.append({
				"file": str(path),
				"path": job_path,
				"message": "resident report is missing voice_sample_speaker_numbers/actual_speakers proof for locked roster mapping",
			})
			continue
		for sample_index, speaker in enumerate(voice_sample_speakers):
			expected_name = expected_voices.get(f"Speaker {speaker}") or expected_voices.get(speaker)
			actual_name = actual_speakers[sample_index] if sample_index < len(actual_speakers) else ""
			if expected_name and actual_name and actual_name != expected_name:
				findings.append({
					"file": str(path),
					"path": f"{job_path}.actual_speakers[{sample_index}]",
					"message": f"resident voice sample for {speaker} used {actual_name}, expected {expected_name}",
				})
	return findings


def _lineage_input_paths(run_dir: Path) -> list[Path]:
	paths = [
		run_dir / "audio/audio_manifest.json",
		run_dir / "05-vibevoice-chunks/audio_manifest.json",
		run_dir / "05-vibevoice-chunks/chunk_plan.json",
		run_dir / "05-vibevoice-chunks/resident_batch_jobs.json",
		run_dir / "05-vibevoice-chunks/resident_batch_report.json",
		run_dir / "05-vibevoice-chunks/resident_batch_report.effective_final.json",
	]
	paths.extend(sorted((run_dir / "05-vibevoice-chunks/chunks").glob("chunk_*/chunk_manifest.json")))
	paths.extend(sorted((run_dir / "05-vibevoice-chunks/chunks").glob("chunk_*/audio/audio_manifest.json")))
	paths.extend(sorted((run_dir / "05-vibevoice-chunks").glob("manual_*repair*/repair_manifest.json")))
	paths.extend(sorted((run_dir / "05-vibevoice-chunks").glob("manual_*repair*/resident_report.json")))
	paths.extend(sorted((run_dir / "05-vibevoice-chunks").glob("manual_*repair*/**/audio/audio_manifest.json")))
	return [path for path in paths if path.exists()]


def _iter_named_values(value: Any, path: str = "") -> list[tuple[str, Any]]:
	items: list[tuple[str, Any]] = []
	if isinstance(value, dict):
		for key, child in value.items():
			child_path = f"{path}.{key}" if path else str(key)
			items.append((child_path, child))
			items.extend(_iter_named_values(child, child_path))
	elif isinstance(value, list):
		for index, child in enumerate(value):
			child_path = f"{path}[{index}]"
			items.extend(_iter_named_values(child, child_path))
	return items


def _expected_voice_list(expected_voices: dict[str, str]) -> list[str]:
	return [expected_voices[speaker] for speaker in _sorted_speakers(expected_voices.keys())]


def _check_payload_lineage(
	path: Path,
	payload: dict[str, Any],
	expected_voices: dict[str, str],
	roster_gender_hints: dict[str, str],
) -> list[dict[str, Any]]:
	findings: list[dict[str, Any]] = []
	expected_list = _expected_voice_list(expected_voices)
	expected_set = set(expected_list)
	for key_path, value in _iter_named_values(payload):
		if key_path.endswith("voice_context_policy") and value and str(value) not in LOCKED_POLICIES:
			findings.append({
				"file": str(path),
				"path": key_path,
				"message": f"voice_context_policy is not locked roster: {value}",
			})
		if key_path.endswith("speaker_names") and isinstance(value, list) and value:
			names = [str(item) for item in value]
			if names != expected_list and not set(names).issubset(expected_set):
				findings.append({
					"file": str(path),
					"path": key_path,
					"message": f"speaker_names {names} are not drawn from locked roster {expected_list}",
				})
		if key_path.endswith("speaker_voices") and isinstance(value, dict):
			flat = {speaker: str(voice) for speaker, voice in value.items() if isinstance(voice, str)}
			if flat and flat != expected_voices:
				findings.append({
					"file": str(path),
					"path": key_path,
					"message": f"speaker_voices {flat} do not match locked roster {expected_voices}",
				})
		if key_path.endswith("default_vibevoice_name") and str(value) not in expected_set:
			findings.append({
				"file": str(path),
				"path": key_path,
				"message": f"default_vibevoice_name is not an expected locked voice: {value}",
			})
		if key_path.endswith("vibevoice_name") and str(value) in FORBIDDEN_DEFAULT_VOICES and str(value) not in expected_set:
			findings.append({
				"file": str(path),
				"path": key_path,
				"message": f"forbidden default VibeVoice voice appears in lineage: {value}",
			})
		if key_path.endswith("speaker_map") and isinstance(value, dict):
			findings.extend(_speaker_map_lineage_findings(path, key_path, value, expected_voices, roster_gender_hints))
	if "audio/audio_manifest.json" in str(path) or "chunk_plan.json" in str(path) or "chunk_manifest.json" in str(path):
		if payload.get("voice_context_policy") and str(payload.get("voice_context_policy")) not in LOCKED_POLICIES:
			findings.append({"file": str(path), "path": "voice_context_policy", "message": "top-level voice_context_policy is not locked"})
	findings.extend(_resident_report_lineage_findings(path, payload, expected_voices))
	return findings


def run_lineage_qa(run_dir: Path, expected_voices: dict[str, str]) -> dict[str, Any]:
	findings: list[dict[str, Any]] = []
	reviewed: list[str] = []
	roster_gender_hints = _speaker_roster_gender_hints(_speaker_roster(run_dir))
	if not expected_voices:
		findings.append({"file": str(run_dir), "path": "voice_prompt_manifest", "message": "no expected locked voices found"})
	for path in _lineage_input_paths(run_dir):
		reviewed.append(str(path))
		try:
			payload = _read_json(path)
		except json.JSONDecodeError as exc:
			findings.append({"file": str(path), "path": "$", "message": f"invalid json: {exc}"})
			continue
		findings.extend(_check_payload_lineage(path, payload, expected_voices, roster_gender_hints))
	required = [
		run_dir / "audio/audio_manifest.json",
		run_dir / "05-vibevoice-chunks/chunk_plan.json",
	]
	for path in required:
		if not path.exists():
			findings.append({"file": str(path), "path": "$", "message": "required lineage file is missing"})
	return {
		"status": "PASS" if not findings else "FAIL",
		"reviewed_files": reviewed,
		"finding_count": len(findings),
		"findings": findings,
	}


def _import_numpy():
	try:
		import numpy as np  # type: ignore
	except Exception as exc:  # pragma: no cover - exercised in production environment differences
		raise RuntimeError("numpy is required for acoustic voice consistency QA; run with `uv run --with numpy`") from exc
	return np


def _decode_audio(path: Path, start_sec: float | None = None, duration_sec: float | None = None, sample_rate: int = 16000):
	np = _import_numpy()
	cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
	if start_sec is not None:
		cmd.extend(["-ss", f"{max(0.0, start_sec):.3f}"])
	cmd.extend(["-i", str(path)])
	if duration_sec is not None:
		cmd.extend(["-t", f"{max(0.05, duration_sec):.3f}"])
	cmd.extend(["-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"])
	result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	return np.frombuffer(result.stdout, dtype=np.float32)


def _spectral_embedding(samples: Any, sample_rate: int = 16000) -> tuple[Any, float]:
	np = _import_numpy()
	if len(samples) < sample_rate:
		raise ValueError("audio sample is shorter than 1 second")
	samples = samples.astype(np.float32)
	samples = samples - float(np.mean(samples))
	rms = float(np.sqrt(np.mean(np.square(samples)) + 1e-12))
	if rms < 1e-4:
		raise ValueError("audio sample is too silent for voice embedding")
	frame = int(0.03 * sample_rate)
	hop = int(0.015 * sample_rate)
	frame_count = 1 + max(0, (len(samples) - frame) // hop)
	if frame_count < 5:
		raise ValueError("not enough frames for voice embedding")
	window = np.hanning(frame).astype(np.float32)
	vectors = []
	for index in range(frame_count):
		start = index * hop
		chunk = samples[start:start + frame]
		if len(chunk) < frame:
			break
		spec = np.abs(np.fft.rfft(chunk * window)) + 1e-8
		log_spec = np.log(spec)
		bands = np.array_split(log_spec[2:220], 48)
		vectors.append([float(np.mean(band)) for band in bands])
	matrix = np.asarray(vectors, dtype=np.float32)
	embedding = np.concatenate([matrix.mean(axis=0), matrix.std(axis=0), np.asarray([rms], dtype=np.float32)])
	embedding = embedding - embedding.mean()
	norm = float(np.linalg.norm(embedding))
	if norm <= 0:
		raise ValueError("zero voice embedding norm")
	return embedding / norm, rms


def _cosine(left: Any, right: Any) -> float:
	np = _import_numpy()
	return float(np.dot(left, right) / ((np.linalg.norm(left) * np.linalg.norm(right)) + 1e-12))


def _timeline_turns(run_dir: Path) -> list[dict[str, Any]]:
	path = run_dir / "audio/dialogue_timeline.json"
	if not path.exists():
		return []
	timeline = _read_json(path)
	turns = []
	for item in timeline.get("turns") or []:
		speaker = str(item.get("speaker") or "")
		start = float(item.get("start_sec") or 0)
		end = float(item.get("end_sec") or 0)
		if SPEAKER_RE.fullmatch(speaker) and end - start >= 1.0:
			turns.append({**item, "speaker": speaker, "start_sec": start, "end_sec": end})
	return turns


def _chunk_ranges(run_dir: Path) -> dict[str, tuple[float, float]]:
	path = run_dir / "audio/audio_manifest.json"
	if not path.exists():
		return {}
	manifest = _read_json(path)
	ranges = {}
	for chunk in manifest.get("chunks") or []:
		chunk_id = str(chunk.get("chunk_id") or "")
		if chunk_id:
			ranges[chunk_id] = (float(chunk.get("global_start_sec") or 0), float(chunk.get("global_end_sec") or 0))
	return ranges


def _repair_chunk_ids(run_dir: Path) -> set[str]:
	ids: set[str] = set()
	for path in (run_dir / "05-vibevoice-chunks").glob("manual_*repair*/repair_manifest.json"):
		try:
			payload = _read_json(path)
		except json.JSONDecodeError:
			continue
		ids.update(str(key) for key in (payload.get("repaired_chunks") or {}).keys())
	report = run_dir / "05-vibevoice-chunks/resident_batch_report.effective_final.json"
	if report.exists():
		payload = _read_json(report)
		for note in payload.get("repair_notes") or []:
			for match in re.finditer(r"Chunks?\s+([0-9, and]+)", str(note)):
				for value in re.findall(r"\d+", match.group(1)):
					ids.add(f"chunk_{int(value):03d}")
	return ids


def _sample_window(turn: dict[str, Any], duration_sec: float) -> tuple[float, float]:
	start = float(turn["start_sec"])
	end = float(turn["end_sec"])
	length = max(0.0, end - start)
	if length <= duration_sec:
		return start, length
	mid = start + length / 2
	return max(start, mid - duration_sec / 2), duration_sec


def _select_samples(
	turns: list[dict[str, Any]],
	chunk_ranges: dict[str, tuple[float, float]],
	repair_chunk_ids: set[str],
	max_random_per_speaker: int,
	sample_duration_sec: float,
) -> list[dict[str, Any]]:
	samples: dict[str, dict[str, Any]] = {}

	def add(label: str, turn: dict[str, Any], reason: str) -> None:
		start, duration = _sample_window(turn, sample_duration_sec)
		if duration >= 1.0:
			samples[label] = {
				"sample_id": label,
				"reason": reason,
				"speaker": turn["speaker"],
				"turn_index": turn.get("turn_index"),
				"start_sec": round(start, 3),
				"duration_sec": round(duration, 3),
			}

	for chunk_id, (chunk_start, chunk_end) in chunk_ranges.items():
		inside = [turn for turn in turns if float(turn["end_sec"]) > chunk_start and float(turn["start_sec"]) < chunk_end]
		if inside:
			add(f"{chunk_id}_head", inside[0], "chunk_head")
			add(f"{chunk_id}_tail", inside[-1], "chunk_tail")
		if chunk_id in repair_chunk_ids and inside:
			add(f"{chunk_id}_repair_mid", inside[len(inside) // 2], "repair_chunk")

	by_speaker: dict[str, list[dict[str, Any]]] = {}
	for turn in turns:
		if float(turn["end_sec"]) - float(turn["start_sec"]) >= 3.0:
			by_speaker.setdefault(turn["speaker"], []).append(turn)
	rng = random.Random(42)
	for speaker, speaker_turns in by_speaker.items():
		selected = speaker_turns[:]
		rng.shuffle(selected)
		for index, turn in enumerate(selected[:max_random_per_speaker], start=1):
			add(f"{speaker.replace(' ', '_')}_random_{index:02d}", turn, "speaker_random")
	return sorted(samples.values(), key=lambda item: (float(item["start_sec"]), item["sample_id"]))


def _classify_acoustic_sample(
	expected_speaker: str,
	best_speaker: str,
	assigned_score: float,
	margin: float,
	min_similarity_margin: float,
	min_assigned_similarity: float,
	references_confusable: bool,
	max_confusable_identity_mismatch_margin: float,
) -> tuple[str, str]:
	if best_speaker != expected_speaker:
		if (
			references_confusable
			and assigned_score >= min_assigned_similarity
			and abs(margin) <= max_confusable_identity_mismatch_margin
		):
			return "REVIEW", "confusable_reference_identity_margin"
		return "FAIL", "voice_identity_mismatch"
	if assigned_score < min_assigned_similarity:
		return "REVIEW", "low_assigned_similarity"
	if margin < min_similarity_margin:
		return "REVIEW", "low_similarity_margin"
	return "PASS", "passed_thresholds"


def run_acoustic_qa(
	run_dir: Path,
	expected_voices: dict[str, str],
	reference_paths: dict[str, Path],
	max_random_per_speaker: int,
	sample_duration_sec: float,
	min_similarity_margin: float,
	min_assigned_similarity: float,
	confusable_reference_similarity: float,
	max_confusable_identity_mismatch_margin: float,
) -> dict[str, Any]:
	failures: list[dict[str, Any]] = []
	warnings: list[str] = []
	try:
		_import_numpy()
	except RuntimeError as exc:
		return {"status": "FAIL", "skip_reason": str(exc), "samples": [], "failures": [{"message": str(exc)}], "warnings": []}
	final_audio = run_dir / "audio/final_podcast.wav"
	if not final_audio.exists():
		return {"status": "FAIL", "samples": [], "failures": [{"message": f"Missing final audio: {final_audio}"}], "warnings": []}
	reference_embeddings: dict[str, Any] = {}
	reference_metrics: dict[str, Any] = {}
	for speaker in _sorted_speakers(expected_voices.keys()):
		ref_path = reference_paths.get(speaker)
		if ref_path is None:
			failures.append({"speaker": speaker, "message": "missing reference path"})
			continue
		ref_path = ref_path if ref_path.is_absolute() else run_dir / ref_path
		if not ref_path.exists():
			failures.append({"speaker": speaker, "message": f"missing reference wav: {ref_path}"})
			continue
		try:
			embedding, rms = _spectral_embedding(_decode_audio(ref_path))
		except Exception as exc:
			failures.append({"speaker": speaker, "message": f"reference embedding failed: {exc}"})
			continue
		reference_embeddings[speaker] = embedding
		reference_metrics[speaker] = {"reference_wav": str(ref_path), "rms": round(rms, 6), "sha256": _sha256(ref_path)}
	reference_pair_similarities: list[dict[str, Any]] = []
	reference_speakers = _sorted_speakers(reference_embeddings.keys())
	for left_index, left_speaker in enumerate(reference_speakers):
		for right_speaker in reference_speakers[left_index + 1:]:
			score = _cosine(reference_embeddings[left_speaker], reference_embeddings[right_speaker])
			reference_pair_similarities.append({
				"speaker_a": left_speaker,
				"speaker_b": right_speaker,
				"cosine_similarity": round(score, 6),
			})
	max_reference_similarity = max(
		(float(item["cosine_similarity"]) for item in reference_pair_similarities),
		default=-1.0,
	)
	references_confusable = max_reference_similarity >= confusable_reference_similarity
	turns = _timeline_turns(run_dir)
	if not turns:
		failures.append({"message": "audio/dialogue_timeline.json has no usable speaker turns"})
		return {
			"status": "FAIL",
			"samples": [],
			"reference_metrics": reference_metrics,
			"reference_pair_similarities": reference_pair_similarities,
			"references_confusable": references_confusable,
			"failures": failures,
			"warnings": warnings,
		}
	samples = _select_samples(turns, _chunk_ranges(run_dir), _repair_chunk_ids(run_dir), max_random_per_speaker, sample_duration_sec)
	results: list[dict[str, Any]] = []
	for sample in samples:
		speaker = str(sample["speaker"])
		if speaker not in reference_embeddings:
			continue
		try:
			embedding, rms = _spectral_embedding(_decode_audio(final_audio, float(sample["start_sec"]), float(sample["duration_sec"])))
		except Exception as exc:
			failures.append({**sample, "message": f"sample embedding failed: {exc}"})
			continue
		similarities = {candidate: _cosine(embedding, ref_embedding) for candidate, ref_embedding in reference_embeddings.items()}
		ranked = sorted(similarities.items(), key=lambda item: item[1], reverse=True)
		best_speaker, best_score = ranked[0]
		assigned_score = similarities.get(speaker, -1.0)
		second_score = ranked[1][1] if len(ranked) > 1 else -1.0
		margin = assigned_score - max(score for candidate, score in similarities.items() if candidate != speaker)
		status, status_reason = _classify_acoustic_sample(
			speaker,
			best_speaker,
			assigned_score,
			margin,
			min_similarity_margin,
			min_assigned_similarity,
			references_confusable,
			max_confusable_identity_mismatch_margin,
		)
		result = {
			**sample,
			"status": status,
			"status_reason": status_reason,
			"rms": round(rms, 6),
			"assigned_similarity": round(assigned_score, 6),
			"best_speaker": best_speaker,
			"best_similarity": round(best_score, 6),
			"margin": round(margin, 6),
			"similarities": {key: round(value, 6) for key, value in similarities.items()},
		}
		results.append(result)
		if status == "FAIL":
			failures.append({**result, "message": "sample is acoustically closer to a different speaker"})
		elif status == "REVIEW":
			warnings.append(f"{sample['sample_id']} has low voice similarity confidence: {status_reason}")
	status = "PASS" if not failures else "FAIL"
	return {
		"status": status,
		"sample_count": len(results),
		"identity_mismatch_count": sum(1 for item in results if item.get("status_reason") == "voice_identity_mismatch"),
		"reference_metrics": reference_metrics,
		"reference_pair_similarities": reference_pair_similarities,
		"references_confusable": references_confusable,
		"samples": results,
		"failures": failures,
		"warnings": warnings,
		"thresholds": {
			"sample_duration_sec": sample_duration_sec,
			"max_random_per_speaker": max_random_per_speaker,
			"min_similarity_margin": min_similarity_margin,
			"min_assigned_similarity": min_assigned_similarity,
			"confusable_reference_similarity": confusable_reference_similarity,
			"max_confusable_identity_mismatch_margin": max_confusable_identity_mismatch_margin,
		},
	}


def _write_report(path: Path, result: dict[str, Any]) -> None:
	lines = [
		"# Voice Consistency QA",
		"",
		f"- overall_status: {result['overall_status']}",
		f"- lineage_status: {result['lineage']['status']}",
		f"- acoustic_status: {result['acoustic']['status']}",
		f"- expected_voices: {result['expected_voices']}",
		"",
	]
	if result["lineage"].get("findings"):
		lines.append("## Lineage Findings")
		for finding in result["lineage"]["findings"]:
			lines.append(f"- {finding['file']} `{finding['path']}`: {finding['message']}")
		lines.append("")
	if result["acoustic"].get("failures"):
		lines.append("## Acoustic Failures")
		for failure in result["acoustic"]["failures"]:
			lines.append(f"- {failure.get('sample_id', 'sample')}: {failure.get('message')}")
		lines.append("")
	if result["acoustic"].get("warnings"):
		lines.append("## Acoustic Warnings")
		lines.extend(f"- {warning}" for warning in result["acoustic"]["warnings"])
		lines.append("")
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_voice_consistency_qa(
	run_dir: Path,
	lineage_only: bool = False,
	max_random_per_speaker: int = 10,
	sample_duration_sec: float = 6.0,
	min_similarity_margin: float = 0.01,
	min_assigned_similarity: float = -0.20,
	confusable_reference_similarity: float = 0.98,
	max_confusable_identity_mismatch_margin: float = 0.03,
) -> dict[str, Any]:
	expected_voices, reference_paths, manifest_path, voice_failures = _expected_voice_names(run_dir)
	lineage = run_lineage_qa(run_dir, expected_voices)
	if voice_failures:
		lineage["status"] = "FAIL"
		lineage.setdefault("findings", []).extend(
			{"file": str(manifest_path), "path": "voice_prompt_manifest", "message": failure}
			for failure in voice_failures
		)
		lineage["finding_count"] = len(lineage["findings"])
	if lineage_only:
		acoustic = {
			"status": "SKIPPED",
			"skip_reason": "lineage_only_requested",
			"samples": [],
			"failures": [],
			"warnings": [],
		}
	else:
		acoustic = run_acoustic_qa(
			run_dir,
			expected_voices,
			reference_paths,
			max_random_per_speaker,
			sample_duration_sec,
			min_similarity_margin,
			min_assigned_similarity,
			confusable_reference_similarity,
			max_confusable_identity_mismatch_margin,
		)
	overall = "PASS" if lineage["status"] == "PASS" and acoustic["status"] in {"PASS", "SKIPPED"} else "FAIL"
	result = {
		"schema_version": "worldview-china-voice-consistency-qa.v1",
		"overall_status": overall,
		"expected_voices": expected_voices,
		"voice_prompt_manifest": str(manifest_path),
		"lineage": lineage,
		"acoustic": acoustic,
	}
	output_dir = run_dir / OUTPUT_DIRNAME
	_write_json(output_dir / RESULT_NAME, result)
	_write_report(output_dir / REPORT_NAME, result)
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["06d-voice-consistency-qa"] = {
		"status": overall.lower(),
		"result": str(output_dir / RESULT_NAME),
		"report": str(output_dir / REPORT_NAME),
		"lineage_status": lineage["status"],
		"acoustic_status": acoustic["status"],
	}
	_write_json(run_manifest_path, run_manifest)
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Run voice lineage and acoustic consistency QA for a Worldview China podcast episode.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--lineage-only", action="store_true")
	parser.add_argument("--max-random-per-speaker", type=int, default=10)
	parser.add_argument("--sample-duration-sec", type=float, default=6.0)
	parser.add_argument("--min-similarity-margin", type=float, default=0.01)
	parser.add_argument("--min-assigned-similarity", type=float, default=-0.20)
	parser.add_argument("--confusable-reference-similarity", type=float, default=0.98)
	parser.add_argument("--max-confusable-identity-mismatch-margin", type=float, default=0.03)
	args = parser.parse_args()
	result = run_voice_consistency_qa(
		args.run_dir.expanduser().resolve(),
		lineage_only=args.lineage_only,
		max_random_per_speaker=args.max_random_per_speaker,
		sample_duration_sec=args.sample_duration_sec,
		min_similarity_margin=args.min_similarity_margin,
		min_assigned_similarity=args.min_assigned_similarity,
		confusable_reference_similarity=args.confusable_reference_similarity,
		max_confusable_identity_mismatch_margin=args.max_confusable_identity_mismatch_margin,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["overall_status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
