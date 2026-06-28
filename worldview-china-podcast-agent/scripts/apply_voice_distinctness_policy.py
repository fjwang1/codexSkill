#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parents[1]
DEFAULT_VIBEVOICE_VOICES_DIR = Path("/Users/wangfangjia/code/VibeVoice/demo/voices")
DEFAULT_PAIR_ID = "20260618_3"
DEFAULT_PAIR_MANIFEST = SKILL_DIR / "assets/default-voices/20260618_3/default_voice_pair_manifest.json"
DEFAULT_THRESHOLD = 0.90
DEFAULT_SPEAKER_VERIFICATION_THRESHOLD = 0.25
DEFAULT_SPEAKER_VERIFICATION_BACKEND = "speechbrain_ecapa"
DEFAULT_SPEAKER_VERIFICATION_CACHE_DIR = Path(os.environ.get("WORLDVIEW_CHINA_SPEAKER_VERIFICATION_CACHE", "/Volumes/GT34/Caches/speechbrain"))
SPEAKER_VERIFICATION_BACKENDS = {"speechbrain_ecapa"}
SUPPORTED_PASS_STATUSES = {
	"PASS_ORIGINAL_CLONED_PAIR",
	"DEFAULT_FALLBACK_APPLIED",
	"WARN_LIGHTWEIGHT_SIMILARITY_HIGH_CLONED_PAIR_KEPT",
	"SKIPPED_SINGLE_SPEAKER_NOT_APPLIED",
	"SKIPPED_MULTI_SPEAKER_NOT_APPLIED",
}


def _read_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _speaker_index(speaker: str) -> int:
	prefix = "Speaker "
	assert speaker.startswith(prefix), f"Unsupported speaker id: {speaker}"
	return int(speaker[len(prefix):])


def _sorted_speakers(values: Any) -> list[str]:
	return sorted([str(value) for value in values if str(value).startswith("Speaker ")], key=_speaker_index)


def _decode_audio(path: Path, sample_rate: int = 16000):
	import numpy as np  # type: ignore

	result = subprocess.run(
		[
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-i",
			str(path),
			"-ac",
			"1",
			"-ar",
			str(sample_rate),
			"-f",
			"f32le",
			"pipe:1",
		],
		check=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return np.frombuffer(result.stdout, dtype=np.float32)


def _spectral_embedding(samples: Any, sample_rate: int = 16000) -> tuple[Any, float]:
	import numpy as np  # type: ignore

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
	import numpy as np  # type: ignore

	return float(np.dot(left, right) / ((np.linalg.norm(left) * np.linalg.norm(right)) + 1e-12))


def _voice_similarity_score(left: Path, right: Path) -> dict[str, Any]:
	left_embedding, left_rms = _spectral_embedding(_decode_audio(left))
	right_embedding, right_rms = _spectral_embedding(_decode_audio(right))
	return {
		"metric": "spectral_cosine_lightweight_v1",
		"similarity_score": round(_cosine(left_embedding, right_embedding), 6),
		"speaker_a_rms": round(left_rms, 6),
		"speaker_b_rms": round(right_rms, 6),
	}


def _reference_path(info: dict[str, Any]) -> Path:
	for key in ("local_registered_wav", "reference_wav", "registered_path"):
		value = str(info.get(key) or "").strip()
		if value:
			return Path(value).expanduser()
	raise RuntimeError(f"speaker voice entry has no reference wav path: {info}")


def _voice_reference_identity(
	left_info: dict[str, Any],
	right_info: dict[str, Any],
	left_ref: Path,
	right_ref: Path,
) -> dict[str, Any]:
	left_sha = _sha256(left_ref)
	right_sha = _sha256(right_ref)
	left_source = str(left_info.get("source_reference_audio") or "").strip()
	right_source = str(right_info.get("source_reference_audio") or "").strip()
	return {
		"speaker_a_reference_sha256": left_sha,
		"speaker_b_reference_sha256": right_sha,
		"registered_reference_same_path": left_ref.resolve() == right_ref.resolve(),
		"registered_reference_same_sha256": left_sha == right_sha,
		"source_reference_same_path": bool(left_source and right_source and Path(left_source).expanduser().resolve() == Path(right_source).expanduser().resolve()),
	}


def _optional_path(value: Any) -> Path | None:
	text = str(value or "").strip()
	return Path(text).expanduser() if text else None


def _time_overlap_sec(left_start: Any, left_end: Any, right_start: Any, right_end: Any) -> float | None:
	try:
		ls = float(left_start)
		le = float(left_end)
		rs = float(right_start)
		re = float(right_end)
	except (TypeError, ValueError):
		return None
	return max(0.0, min(le, re) - max(ls, rs))


def _source_reference_evidence(left_info: dict[str, Any], right_info: dict[str, Any]) -> dict[str, Any]:
	left_source = _optional_path(left_info.get("source_reference_audio"))
	right_source = _optional_path(right_info.get("source_reference_audio"))
	evidence: dict[str, Any] = {
		"status": "PASS_DISTINCT_SOURCE_REFERENCES",
		"speaker_a_source_reference_audio": str(left_source) if left_source else None,
		"speaker_b_source_reference_audio": str(right_source) if right_source else None,
		"source_reference_same_path": False,
		"source_reference_same_sha256": False,
		"source_reference_time_overlap_sec": None,
		"source_identity_fields_distinct": bool(
			str(left_info.get("source_vibevoice_name") or "").strip()
			and str(right_info.get("source_vibevoice_name") or "").strip()
			and str(left_info.get("source_vibevoice_name")) != str(right_info.get("source_vibevoice_name"))
		),
	}
	if left_source is None or right_source is None:
		evidence.update({
			"status": "MISSING_SOURCE_REFERENCE_EVIDENCE",
			"reason": "02c speaker voice entries do not both record source_reference_audio",
		})
		return evidence
	if not left_source.exists() or not right_source.exists():
		evidence.update({
			"status": "MISSING_SOURCE_REFERENCE_AUDIO_FILE",
			"reason": "source_reference_audio path missing on disk",
		})
		return evidence
	evidence["source_reference_same_path"] = left_source.resolve() == right_source.resolve()
	left_sha = _sha256(left_source)
	right_sha = _sha256(right_source)
	evidence["speaker_a_source_reference_sha256"] = left_sha
	evidence["speaker_b_source_reference_sha256"] = right_sha
	evidence["source_reference_same_sha256"] = left_sha == right_sha
	overlap = _time_overlap_sec(
		left_info.get("source_start_sec"),
		left_info.get("source_end_sec"),
		right_info.get("source_start_sec"),
		right_info.get("source_end_sec"),
	)
	evidence["source_reference_time_overlap_sec"] = overlap
	if evidence["source_reference_same_path"]:
		evidence.update({
			"status": "FAIL_SAME_SOURCE_REFERENCE_PATH",
			"reason": "two speaker prompts point at the same source_reference_audio path",
		})
	elif evidence["source_reference_same_sha256"]:
		evidence.update({
			"status": "FAIL_SAME_SOURCE_REFERENCE_SHA256",
			"reason": "two speaker prompts use byte-identical source reference audio",
		})
	elif overlap is not None and overlap > 0.5:
		evidence.update({
			"status": "FAIL_OVERLAPPING_SOURCE_REFERENCE_TIME_RANGE",
			"reason": "two speaker prompts use overlapping source time ranges",
		})
	return evidence


_SPEECHBRAIN_CLASSIFIER_CACHE: dict[str, Any] = {}


def _torch_scalar(value: Any) -> float:
	try:
		return float(value.detach().cpu().reshape(-1)[0])
	except AttributeError:
		try:
			return float(value.reshape(-1)[0])
		except AttributeError:
			return float(value)


def _load_speechbrain_classifier(cache_dir: Path) -> Any:
	cache_key = str(cache_dir.expanduser().resolve())
	if cache_key in _SPEECHBRAIN_CLASSIFIER_CACHE:
		return _SPEECHBRAIN_CLASSIFIER_CACHE[cache_key]
	try:
		from speechbrain.inference.speaker import EncoderClassifier  # type: ignore
	except ModuleNotFoundError:
		from speechbrain.pretrained import EncoderClassifier  # type: ignore
	savedir = cache_dir.expanduser().resolve() / "spkrec-ecapa-voxceleb"
	savedir.mkdir(parents=True, exist_ok=True)
	classifier = EncoderClassifier.from_hparams(
		source="speechbrain/spkrec-ecapa-voxceleb",
		savedir=str(savedir),
	)
	_SPEECHBRAIN_CLASSIFIER_CACHE[cache_key] = classifier
	return classifier


def _load_speechbrain_waveform(path: Path):
	import torch  # type: ignore
	import torchaudio  # type: ignore

	wav, sample_rate = torchaudio.load(str(path))
	if wav.ndim != 2:
		raise RuntimeError(f"unexpected audio tensor shape for speaker verification: {tuple(wav.shape)}")
	if wav.shape[0] > 1:
		wav = wav.mean(dim=0, keepdim=True)
	if sample_rate != 16000:
		wav = torchaudio.functional.resample(wav, sample_rate, 16000)
	wav = wav.squeeze(0).to(dtype=torch.float32)
	if wav.numel() < 16000:
		raise RuntimeError(f"audio sample is shorter than 1 second for speaker verification: {path}")
	return wav.unsqueeze(0)


def _speechbrain_ecapa_verification_score(
	left: Path,
	right: Path,
	*,
	threshold: float,
	cache_dir: Path,
) -> dict[str, Any]:
	classifier = _load_speechbrain_classifier(cache_dir)
	left_wav = _load_speechbrain_waveform(left)
	right_wav = _load_speechbrain_waveform(right)
	try:
		score, prediction = classifier.verify_batch(left_wav, right_wav, threshold=threshold)
	except TypeError:
		score, prediction = classifier.verify_batch(left_wav, right_wav)
	score_value = round(_torch_scalar(score), 6)
	prediction_value = bool(_torch_scalar(prediction) >= 0.5)
	return {
		"backend": "speechbrain_ecapa",
		"model": "speechbrain/spkrec-ecapa-voxceleb",
		"metric": "speaker_verification_cosine",
		"threshold": threshold,
		"similarity_score": score_value,
		"same_speaker_prediction": prediction_value,
		"status": "PASS",
	}


def _speaker_verification_score(
	left: Path,
	right: Path,
	*,
	backend: str,
	threshold: float,
	cache_dir: Path,
) -> dict[str, Any]:
	if backend not in SPEAKER_VERIFICATION_BACKENDS:
		raise RuntimeError(f"unsupported speaker verification backend: {backend}")
	try:
		if backend == "speechbrain_ecapa":
			return _speechbrain_ecapa_verification_score(left, right, threshold=threshold, cache_dir=cache_dir)
	except ModuleNotFoundError as exc:
		return {
			"backend": backend,
			"status": "UNAVAILABLE",
			"reason": f"missing python dependency: {exc.name}",
		}
	except ImportError as exc:
		return {
			"backend": backend,
			"status": "UNAVAILABLE",
			"reason": f"import failed: {exc}",
		}
	raise AssertionError("unreachable speaker verification backend branch")


def _speaker_verification_comparisons(
	left_info: dict[str, Any],
	right_info: dict[str, Any],
	left_ref: Path,
	right_ref: Path,
	*,
	backend: str,
	threshold: float,
	cache_dir: Path,
) -> dict[str, Any]:
	result = {
		"backend": backend,
		"threshold": threshold,
		"prompt_reference": _speaker_verification_score(
			left_ref,
			right_ref,
			backend=backend,
			threshold=threshold,
			cache_dir=cache_dir,
		),
		"source_reference": None,
	}
	left_source = _optional_path(left_info.get("source_reference_audio"))
	right_source = _optional_path(right_info.get("source_reference_audio"))
	if left_source and right_source and left_source.exists() and right_source.exists():
		result["source_reference"] = _speaker_verification_score(
			left_source,
			right_source,
			backend=backend,
			threshold=threshold,
			cache_dir=cache_dir,
		)
	return result


def _ensure_default_voice_registered(asset_path: Path, voices_dir: Path, expected_sha256: str) -> Path:
	if _sha256(asset_path) != expected_sha256:
		raise RuntimeError(f"default voice asset sha256 mismatch: {asset_path}")
	registered_path = voices_dir / asset_path.name
	if registered_path.exists():
		if _sha256(registered_path) != expected_sha256:
			raise RuntimeError(f"registered default voice sha256 mismatch: {registered_path}")
	else:
		voices_dir.mkdir(parents=True, exist_ok=True)
		shutil.copy2(asset_path, registered_path)
	return registered_path


def _build_default_speaker_voices(default_manifest: dict[str, Any], voices_dir: Path) -> dict[str, dict[str, Any]]:
	base_dir = DEFAULT_PAIR_MANIFEST.parent
	result: dict[str, dict[str, Any]] = {}
	voices = default_manifest.get("voices")
	if not isinstance(voices, dict):
		raise RuntimeError("default voice pair manifest missing voices")
	for speaker in _sorted_speakers(voices.keys()):
		info = voices.get(speaker)
		if not isinstance(info, dict):
			raise RuntimeError(f"default voice pair manifest entry is not an object: {speaker}")
		filename = str(info.get("filename") or "")
		voice_name = str(info.get("vibevoice_name") or "")
		expected_sha = str(info.get("sha256") or "")
		if not filename or not voice_name or not expected_sha:
			raise RuntimeError(f"default voice pair manifest entry incomplete: {speaker}")
		asset_path = base_dir / filename
		if not asset_path.exists():
			raise RuntimeError(f"default voice asset missing: {asset_path}")
		registered_path = _ensure_default_voice_registered(asset_path, voices_dir, expected_sha)
		result[speaker] = {
			"status": "pass",
			"vibevoice_name": voice_name,
			"reference_wav": str(registered_path),
			"registered_path": str(registered_path),
			"local_registered_wav": str(asset_path),
			"duration_sec": float(info.get("duration_sec") or 0),
			"sha256": expected_sha,
			"voice_distinctness_fallback": True,
			"default_pair_id": str(default_manifest.get("default_pair_id") or DEFAULT_PAIR_ID),
			"default_pair_asset_manifest": str(DEFAULT_PAIR_MANIFEST),
		}
	return result


def _policy_status_is_complete(policy: Any) -> bool:
	return isinstance(policy, dict) and str(policy.get("status") or "") in SUPPORTED_PASS_STATUSES


def apply_voice_distinctness_policy(
	run_dir: Path,
	*,
	manifest_path: Path | None = None,
	default_pair_manifest: Path = DEFAULT_PAIR_MANIFEST,
	voices_dir: Path = DEFAULT_VIBEVOICE_VOICES_DIR,
	threshold: float = DEFAULT_THRESHOLD,
	speaker_verification_backend: str = DEFAULT_SPEAKER_VERIFICATION_BACKEND,
	speaker_verification_threshold: float = DEFAULT_SPEAKER_VERIFICATION_THRESHOLD,
	speaker_verification_cache_dir: Path = DEFAULT_SPEAKER_VERIFICATION_CACHE_DIR,
	apply_default_fallback: bool = True,
) -> dict[str, Any]:
	run_dir = run_dir.expanduser().resolve()
	manifest_path = (manifest_path or run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json").expanduser().resolve()
	assert manifest_path.exists(), f"Missing 02c voice prompt manifest: {manifest_path}"
	assert default_pair_manifest.exists(), f"Missing default voice pair manifest: {default_pair_manifest}"
	manifest = _read_json(manifest_path)
	if manifest.get("status") != "pass":
		raise RuntimeError(f"voice_prompt_manifest status is not pass: {manifest_path}")
	speaker_voices = manifest.get("original_cloned_speaker_voices") or manifest.get("speaker_voices")
	if not isinstance(speaker_voices, dict):
		raise RuntimeError("voice_prompt_manifest missing speaker_voices")
	speaker_ids = _sorted_speakers(speaker_voices.keys())
	base_policy = {
		"schema_version": "worldview-china-voice-distinctness-policy.v1",
		"scope": "exactly_two_speakers_only",
		"threshold": threshold,
		"threshold_unit": "similarity_score",
		"threshold_percent": int(round(threshold * 100)),
		"comparison": "speaker_verification_then_source_evidence_then_default_fallback",
		"auto_default_fallback_enabled": bool(apply_default_fallback),
		"legacy_apply_default_fallback_arg": bool(apply_default_fallback),
		"speaker_verification_backend": speaker_verification_backend,
		"speaker_verification_threshold": speaker_verification_threshold,
		"speaker_verification_cache_dir": str(speaker_verification_cache_dir),
		"metric_limitations": (
			"spectral_cosine_lightweight_v1 is retained only as a diagnostic. Fallback decisions require "
			"a speaker verification backend plus distinct source-reference evidence."
		),
		"applied_at": datetime.now(timezone.utc).isoformat(),
	}
	if len(speaker_ids) == 1:
		policy = {
			**base_policy,
			"status": "SKIPPED_SINGLE_SPEAKER_NOT_APPLIED",
			"speaker_count": 1,
			"reason": "single_speaker_run_has_no_pairwise_voice_distinctness_gate",
		}
	elif len(speaker_ids) != 2:
		policy = {
			**base_policy,
			"status": "SKIPPED_MULTI_SPEAKER_NOT_APPLIED",
			"speaker_count": len(speaker_ids),
			"reason": "three_or_four_speaker_runs_skip_this_two_speaker_similarity_fallback",
		}
	else:
		left, right = speaker_ids
		left_info = speaker_voices[left]
		right_info = speaker_voices[right]
		left_ref = _reference_path(left_info)
		right_ref = _reference_path(right_info)
		if not left_ref.exists() or not right_ref.exists():
			raise RuntimeError(f"missing prompt wav for similarity check: {left_ref} / {right_ref}")
		lightweight_similarity = _voice_similarity_score(left_ref, right_ref)
		reference_identity = _voice_reference_identity(left_info, right_info, left_ref, right_ref)
		source_evidence = _source_reference_evidence(left_info, right_info)
		verification = _speaker_verification_comparisons(
			left_info,
			right_info,
			left_ref,
			right_ref,
			backend=speaker_verification_backend,
			threshold=speaker_verification_threshold,
			cache_dir=speaker_verification_cache_dir,
		)
		policy = {
			**base_policy,
			"status": "PASS_ORIGINAL_CLONED_PAIR",
			"speaker_count": 2,
			"speaker_a": left,
			"speaker_b": right,
			"speaker_a_reference_wav": str(left_ref),
			"speaker_b_reference_wav": str(right_ref),
			"similarity": lightweight_similarity,
			"speaker_verification": verification,
			"reference_identity": reference_identity,
			"source_reference_evidence": source_evidence,
			"reason": "speaker_verification_did_not_trigger_default_fallback",
			"fallback_action": "none",
		}
		if reference_identity["registered_reference_same_path"] or reference_identity["registered_reference_same_sha256"]:
			policy.update({
				"status": "FAIL_IDENTICAL_VOICE_REFERENCE_REQUIRES_REPAIR",
				"reason": "two_speakers_resolve_to_the_same_registered_reference_audio",
				"repair_guidance": "Rerun 02b/02c with distinct speaker clips; do not mask an identical-reference bug with default voices.",
			})
		elif reference_identity["source_reference_same_path"]:
			policy.update({
				"status": "FAIL_IDENTICAL_SOURCE_REFERENCE_REQUIRES_REPAIR",
				"reason": "two_speakers_resolve_to_the_same_source_reference_audio",
				"repair_guidance": "Rerun 02b with a corrected speaker timeline/reference clip.",
			})
		elif str(source_evidence.get("status") or "").startswith("FAIL_"):
			policy.update({
				"status": "FAIL_SOURCE_REFERENCE_EVIDENCE_REQUIRES_REPAIR",
				"reason": source_evidence.get("reason") or "source reference evidence failed",
				"repair_guidance": "Rerun 02b/02c with distinct source clips before considering default fallback.",
			})
		else:
			prompt_verification = verification.get("prompt_reference") if isinstance(verification.get("prompt_reference"), dict) else {}
			source_verification = verification.get("source_reference") if isinstance(verification.get("source_reference"), dict) else None
			unavailable = [
				item for item in (prompt_verification, source_verification)
				if isinstance(item, dict) and item.get("status") == "UNAVAILABLE"
			]
			if unavailable:
				policy.update({
					"status": "BLOCKED_SPEAKER_VERIFICATION_BACKEND_UNAVAILABLE",
					"reason": "reliable speaker verification backend is unavailable; refusing to decide fallback from lightweight spectral cosine",
					"repair_guidance": (
						"Run with the required backend dependencies, for example: uv run --with numpy --with torch "
						"--with torchaudio --with speechbrain python .../apply_voice_distinctness_policy.py"
					),
				})
			else:
				prompt_same = bool(prompt_verification.get("same_speaker_prediction"))
				source_same = bool(source_verification.get("same_speaker_prediction")) if isinstance(source_verification, dict) else False
				source_evidence_pass = source_evidence.get("status") == "PASS_DISTINCT_SOURCE_REFERENCES"
				if (prompt_same or source_same) and not source_evidence_pass:
					policy.update({
						"status": "FAIL_SOURCE_REFERENCE_EVIDENCE_MISSING_REQUIRES_REPAIR",
						"reason": "speaker verification says the two-speaker pair is too similar, but source-reference distinctness evidence is missing",
						"repair_guidance": "Rerun 02b/02c so each prompt records distinct source_reference_audio before fallback can be applied.",
					})
				elif prompt_same or source_same:
					if apply_default_fallback:
						default_manifest = _read_json(default_pair_manifest)
						default_voices = _build_default_speaker_voices(default_manifest, voices_dir)
						manifest["original_cloned_speaker_voices"] = speaker_voices
						manifest["speaker_voices"] = default_voices
						manifest["effective_speaker_voices_source"] = f"default_pair_{DEFAULT_PAIR_ID}"
						policy.update({
							"status": "DEFAULT_FALLBACK_APPLIED",
							"reason": "reliable_speaker_verification_high_similarity_and_source_references_distinct",
							"fallback_action": "replace_both_speakers_with_default_pair",
							"fallback_source": f"default_pair_{DEFAULT_PAIR_ID}",
							"source_references_confirmed_distinct": True,
							"speaker_verification_trigger": {
								"prompt_reference_same_speaker_prediction": prompt_same,
								"source_reference_same_speaker_prediction": source_same,
							},
						})
					else:
						policy.update({
							"status": "WARN_RELIABLE_SIMILARITY_HIGH_FALLBACK_DISABLED",
							"reason": "speaker verification high similarity, but default fallback was disabled by CLI",
							"fallback_action": "none_fallback_disabled",
							"source_references_confirmed_distinct": True,
						})
		if manifest.get("original_cloned_speaker_voices") and manifest.get("effective_speaker_voices_source"):
			if policy.get("status") != "DEFAULT_FALLBACK_APPLIED":
				manifest["speaker_voices"] = speaker_voices
				manifest.pop("effective_speaker_voices_source", None)
	manifest["voice_distinctness_policy"] = policy
	_write_json(manifest_path, manifest)
	output_dir = manifest_path.parent
	result = {
		"schema_version": "worldview-china-voice-distinctness-policy-result.v1",
		"status": policy["status"],
		"run_dir": str(run_dir),
		"voice_prompt_manifest": str(manifest_path),
		"voice_prompt_manifest_sha256": _sha256(manifest_path),
		"policy": policy,
		"speaker_voices": {
			speaker: info.get("vibevoice_name")
			for speaker, info in (manifest.get("speaker_voices") or {}).items()
			if isinstance(info, dict)
		},
	}
	_write_json(output_dir / "voice_distinctness_policy_result.json", result)
	_write_report(output_dir / "voice_distinctness_policy_report.md", result)
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["02c-voice-distinctness-policy"] = {
		"status": policy["status"],
		"result": str(output_dir / "voice_distinctness_policy_result.json"),
		"report": str(output_dir / "voice_distinctness_policy_report.md"),
		"voice_prompt_manifest": str(manifest_path),
	}
	_write_json(run_manifest_path, run_manifest)
	return result


def _write_report(path: Path, result: dict[str, Any]) -> None:
	policy = result["policy"]
	lines = [
		"# Voice Distinctness Policy",
		"",
		f"- status: {result['status']}",
		f"- scope: {policy.get('scope')}",
		f"- threshold: {policy.get('threshold_percent')}%",
		f"- comparison: {policy.get('comparison')}",
		f"- voice_prompt_manifest: {result['voice_prompt_manifest']}",
	]
	if policy.get("similarity"):
		similarity = policy["similarity"]
		lines.extend([
			f"- diagnostic_metric: {similarity.get('metric')}",
			f"- diagnostic_similarity_score: {similarity.get('similarity_score')}",
		])
	if policy.get("speaker_verification"):
		verification = policy["speaker_verification"]
		lines.extend([
			f"- speaker_verification_backend: {verification.get('backend')}",
			f"- speaker_verification_threshold: {verification.get('threshold')}",
		])
		prompt = verification.get("prompt_reference") if isinstance(verification.get("prompt_reference"), dict) else {}
		if prompt:
			lines.append(
				"- prompt_reference_verification: "
				f"status={prompt.get('status')}, score={prompt.get('similarity_score')}, "
				f"same_speaker={prompt.get('same_speaker_prediction')}"
			)
		source = verification.get("source_reference") if isinstance(verification.get("source_reference"), dict) else {}
		if source:
			lines.append(
				"- source_reference_verification: "
				f"status={source.get('status')}, score={source.get('similarity_score')}, "
				f"same_speaker={source.get('same_speaker_prediction')}"
			)
	if policy.get("source_reference_evidence"):
		source_evidence = policy["source_reference_evidence"]
		lines.append(f"- source_reference_evidence_status: {source_evidence.get('status')}")
	if policy.get("fallback_action"):
		lines.append(f"- fallback_action: {policy.get('fallback_action')}")
	if policy.get("fallback_source"):
		lines.append(f"- fallback_source: {policy.get('fallback_source')}")
	if policy.get("warning"):
		lines.append(f"- warning: {policy.get('warning')}")
	lines.extend(["", "## Effective Voices", ""])
	for speaker, voice_name in result.get("speaker_voices", {}).items():
		lines.append(f"- {speaker}: {voice_name}")
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
	parser = argparse.ArgumentParser(description="Apply Worldview China two-speaker voice reference identity and lightweight distinctness diagnostics.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--manifest-path", type=Path)
	parser.add_argument("--default-pair-manifest", type=Path, default=DEFAULT_PAIR_MANIFEST)
	parser.add_argument("--voices-dir", type=Path, default=DEFAULT_VIBEVOICE_VOICES_DIR)
	parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
	parser.add_argument("--speaker-verification-backend", choices=sorted(SPEAKER_VERIFICATION_BACKENDS), default=DEFAULT_SPEAKER_VERIFICATION_BACKEND)
	parser.add_argument("--speaker-verification-threshold", type=float, default=DEFAULT_SPEAKER_VERIFICATION_THRESHOLD)
	parser.add_argument("--speaker-verification-cache-dir", type=Path, default=DEFAULT_SPEAKER_VERIFICATION_CACHE_DIR)
	parser.add_argument("--no-apply-default-fallback", action="store_true", help="Debug flag; formal production should allow default fallback after reliable verification and source evidence pass.")
	args = parser.parse_args()
	result = apply_voice_distinctness_policy(
		args.run_dir,
		manifest_path=args.manifest_path,
		default_pair_manifest=args.default_pair_manifest.expanduser().resolve(),
		voices_dir=args.voices_dir.expanduser().resolve(),
		threshold=args.threshold,
		speaker_verification_backend=args.speaker_verification_backend,
		speaker_verification_threshold=args.speaker_verification_threshold,
		speaker_verification_cache_dir=args.speaker_verification_cache_dir.expanduser().resolve(),
		apply_default_fallback=not args.no_apply_default_fallback,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if _policy_status_is_complete(result.get("policy")) else 1


if __name__ == "__main__":
	raise SystemExit(main())
