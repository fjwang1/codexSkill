#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_QWEN_REPO = Path("/Users/wangfangjia/code/qwen3-tts-apple-silicon-test")
DEFAULT_QWEN_PYTHON = DEFAULT_QWEN_REPO / ".venv" / "bin" / "python"
DEFAULT_QWEN_MODEL = DEFAULT_QWEN_REPO / "models" / "Qwen3-TTS-12Hz-1.7B-Base-8bit"
DEFAULT_VIBEVOICE_VOICES_DIR = Path("/Users/wangfangjia/code/VibeVoice/demo/voices")
DEFAULT_MIN_PROMPT_SEC = 5.0
DEFAULT_MAX_PROMPT_SEC = 30.0

DEFAULT_TARGET_TEXTS = {
	"Speaker 0": "大家好，欢迎收听今天的节目。我们会从中国经济、全球贸易和企业实务几个角度，慢慢把问题讲清楚。今天的讨论不是简单下结论，而是尽量把复杂背景拆开来看。",
	"Speaker 1": "谢谢邀请，我很高兴来聊这个话题。中国市场非常复杂，既有巨大的机会，也有很多容易被忽视的约束。我的经验是，必须进入具体城市、具体行业和具体人群，才能真正理解它。",
}


@dataclass(frozen=True)
class TranscriptSegment:
	start: float
	end: float
	text: str


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


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=False, cwd=str(cwd) if cwd else None, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _duration(path: Path) -> float:
	completed = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		str(path),
	])
	if completed.returncode != 0:
		raise RuntimeError(f"ffprobe failed for {path}: {completed.stderr}")
	return float(completed.stdout.strip())


def _parse_volume(stderr: str) -> dict[str, float | None]:
	mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
	max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
	return {
		"mean_volume_db": float(mean_match.group(1)) if mean_match else None,
		"max_volume_db": float(max_match.group(1)) if max_match else None,
	}


def _parse_silence(stderr: str) -> float:
	return sum(float(value) for value in re.findall(r"silence_duration:\s*(\d+(?:\.\d+)?)", stderr))


def _audio_metrics(path: Path) -> dict[str, Any]:
	volume = _run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
	silence = _run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "silencedetect=noise=-45dB:d=1", "-f", "null", "-"])
	duration = _duration(path)
	metrics = _parse_volume(volume.stderr)
	silence_sec = _parse_silence(silence.stderr)
	metrics.update({
		"duration_sec": round(duration, 3),
		"silence_sec": round(silence_sec, 3),
		"silence_ratio": round(silence_sec / duration, 4) if duration > 0 else None,
	})
	return metrics


def _parse_time(value: Any) -> float:
	if isinstance(value, (int, float)):
		return float(value)
	text = str(value).strip()
	if not text:
		raise ValueError("empty time")
	parts = text.split(":")
	if len(parts) == 1:
		return float(parts[0])
	if len(parts) == 2:
		return int(parts[0]) * 60 + float(parts[1])
	if len(parts) == 3:
		return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
	raise ValueError(f"unsupported time: {value!r}")


def _clean_reference_text(text: str) -> str:
	text = re.sub(r">>\s*", "", text)
	text = re.sub(r"\s+", " ", text).strip()
	return text


def _has_rolling_caption_repetition(text: str) -> bool:
	words = re.findall(r"[A-Za-z][A-Za-z']+|[\u4e00-\u9fff]", text.lower())
	if len(words) < 12:
		return False
	for size in range(4, 9):
		seen: dict[tuple[str, ...], int] = {}
		for index in range(0, len(words) - size + 1):
			gram = tuple(words[index:index + size])
			seen[gram] = seen.get(gram, 0) + 1
			if seen[gram] >= 3:
				return True
	return False


def _reference_text_noise_reasons(text: str) -> list[str]:
	lower = text.lower()
	reasons = []
	for label, patterns in {
		"music_or_non_speech": ("[music]", "[laughter]"),
		"sponsor_or_ad": ("sponsor", "patreon", "my debt clinic", "debt clinic", "provision capital", "partnering with"),
		"contact_or_url": ("visit ", ".com", "www.", "http", "use code", "subscribe", "become a member", "membership"),
		"finance_ad_terms": ("credit card", "personal loans", "debt relief", "across the nation"),
	}.items():
		if any(pattern in lower for pattern in patterns):
			reasons.append(label)
	if _has_rolling_caption_repetition(text):
		reasons.append("rolling_caption_repetition")
	return sorted(set(reasons))


def _coerce_transcript_segment(item: dict[str, Any]) -> TranscriptSegment | None:
	start_value = item.get("start", item.get("start_sec", item.get("source_start")))
	end_value = item.get("end", item.get("end_sec", item.get("source_end")))
	duration_value = item.get("duration", item.get("duration_sec"))
	if start_value is None:
		return None
	try:
		start = _parse_time(start_value)
		if end_value is not None:
			end = _parse_time(end_value)
		elif duration_value is not None:
			end = start + float(duration_value)
		else:
			return None
	except (TypeError, ValueError):
		return None
	text = str(item.get("text") or item.get("source_text") or item.get("transcript") or "").strip()
	if not text or end <= start:
		return None
	return TranscriptSegment(start=start, end=end, text=_clean_reference_text(text))


def _walk_transcript_items(data: Any) -> list[dict[str, Any]]:
	if isinstance(data, list):
		items: list[dict[str, Any]] = []
		for item in data:
			items.extend(_walk_transcript_items(item))
		return items
	if isinstance(data, dict):
		if any(key in data for key in ("start", "start_sec", "source_start")):
			return [data]
		items = []
		for key in ("segments", "transcript", "timeline", "speaker_segments"):
			if key in data:
				items.extend(_walk_transcript_items(data[key]))
		return items
	return []


def _load_transcript_segments(run_dir: Path) -> list[TranscriptSegment]:
	candidates = [
		run_dir / "02-source-capture" / "source_transcript.en.json",
		run_dir / "02-source-capture" / "youtube-media" / "transcript.en.json",
		run_dir / "02-source-capture" / "youtube-media" / "transcript.json",
	]
	for candidate in candidates:
		if not candidate.exists():
			continue
		data = _read_json(candidate)
		segments = [
			segment
			for item in _walk_transcript_items(data)
			if (segment := _coerce_transcript_segment(item)) is not None
		]
		if segments:
			return sorted(segments, key=lambda segment: (segment.start, segment.end))
	return []


def _text_for_time_range(segments: list[TranscriptSegment], start: float | None, end: float | None) -> str:
	if start is None or end is None or end <= start:
		return ""
	parts = []
	for segment in segments:
		overlap = max(0.0, min(segment.end, end) - max(segment.start, start))
		if overlap > 0:
			parts.append(segment.text)
	return _clean_reference_text(" ".join(parts))


def _safe_name(value: str) -> str:
	value = re.sub(r"[^A-Za-z0-9]+", "", value)
	return value or "Voice"


def _speaker_index(speaker: str) -> int:
	return 0 if speaker == "Speaker 0" else 1


def _load_target_texts(path: Path | None) -> dict[str, str]:
	if path is None:
		return dict(DEFAULT_TARGET_TEXTS)
	data = _read_json(path.expanduser().resolve())
	result = dict(DEFAULT_TARGET_TEXTS)
	for speaker in ("Speaker 0", "Speaker 1"):
		if isinstance(data, dict) and data.get(speaker):
			result[speaker] = str(data[speaker])
	return result


def _choose_reference_clip(info: dict[str, Any], *, min_ref_sec: float, max_ref_sec: float) -> dict[str, Any]:
	selected = info.get("selected_clips")
	if isinstance(selected, list):
		candidates = []
		for clip in selected:
			if not isinstance(clip, dict):
				continue
			clip_path = Path(str(clip.get("clip") or ""))
			if not clip_path.exists():
				continue
			duration = float(clip.get("metrics", {}).get("duration_sec") or clip.get("candidate_duration_sec") or _duration(clip_path))
			score = abs(duration - 15.0)
			in_range = min_ref_sec <= duration <= max_ref_sec
			candidates.append((0 if in_range else 1, score, clip, duration))
		if candidates:
			_, _, clip, duration = sorted(candidates, key=lambda item: item[:2])[0]
			return {
				"audio": str(Path(str(clip["clip"])).expanduser().resolve()),
				"start_sec": clip.get("start_sec"),
				"end_sec": clip.get("end_sec"),
				"text_preview": clip.get("text_preview") or "",
				"duration_sec": duration,
				"source": "selected_clip",
			}
	reference_wav = Path(str(info.get("reference_wav") or ""))
	if reference_wav.exists():
		return {
			"audio": str(reference_wav.expanduser().resolve()),
			"start_sec": None,
			"end_sec": None,
			"text_preview": "",
			"duration_sec": _duration(reference_wav),
			"source": "source_reference_wav",
		}
	raise RuntimeError(f"No usable reference clip in source voice info: {info}")


def _copy_reference_audio(src: Path, dst: Path) -> None:
	dst.parent.mkdir(parents=True, exist_ok=True)
	completed = _run([
		"ffmpeg",
		"-y",
		"-hide_banner",
		"-loglevel",
		"error",
		"-i",
		str(src),
		"-ac",
		"1",
		"-ar",
		"24000",
		"-c:a",
		"pcm_s16le",
		str(dst),
	])
	if completed.returncode != 0:
		raise RuntimeError(f"reference audio conversion failed: {completed.stderr}")


def _write_qwen_runner(path: Path) -> None:
	path.write_text(
		"""
import json
import shutil
import sys
import time
from pathlib import Path

from mlx_audio.tts.generate import generate_audio
from mlx_audio.tts.utils import load_model


def main() -> int:
	payload_path = Path(sys.argv[1])
	payload = json.loads(payload_path.read_text(encoding="utf-8"))
	model_path = Path(payload["model_path"])
	print(f"Loading Qwen3 model: {model_path}", flush=True)
	model = load_model(model_path)
	for speaker, info in payload["speakers"].items():
		out_dir = Path(info["qwen_output_dir"])
		if payload.get("force") and out_dir.exists():
			shutil.rmtree(out_dir)
		out_dir.mkdir(parents=True, exist_ok=True)
		print(f"Generating {speaker} -> {out_dir}", flush=True)
		start = time.time()
		generate_audio(
			model=model,
			text=info["target_text"],
			ref_audio=info["reference_audio"],
			ref_text=info["reference_text"],
			lang_code="zh",
			output_path=str(out_dir),
			file_prefix="qwen_prompt",
			audio_format="wav",
			play=False,
			verbose=True,
			max_tokens=int(payload.get("max_tokens", 900)),
		)
		print(f"Done {speaker} elapsed_sec={time.time() - start:.1f}", flush=True)
	print("Qwen prompt generation complete", flush=True)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
""".lstrip(),
		encoding="utf-8",
	)


def _run_qwen(payload_path: Path, qwen_python: Path, qwen_repo: Path, stdout_path: Path, stderr_path: Path) -> None:
	runner = payload_path.parent / "run_qwen_generation.py"
	_write_qwen_runner(runner)
	completed = _run([str(qwen_python), str(runner), str(payload_path)], cwd=qwen_repo)
	stdout_path.write_text(completed.stdout, encoding="utf-8")
	stderr_path.write_text(completed.stderr, encoding="utf-8")
	if completed.returncode != 0:
		raise RuntimeError(f"Qwen3 prompt generation failed; see {stderr_path}")


def _find_qwen_output(out_dir: Path) -> Path:
	candidates = sorted(out_dir.glob("qwen_prompt_*.wav"))
	if not candidates:
		raise RuntimeError(f"No Qwen output wav found in {out_dir}")
	return candidates[0]


def _normalize_prompt(src: Path, dst: Path) -> None:
	dst.parent.mkdir(parents=True, exist_ok=True)
	completed = _run([
		"ffmpeg",
		"-y",
		"-hide_banner",
		"-loglevel",
		"error",
		"-i",
		str(src),
		"-af",
		"loudnorm=I=-18:TP=-1.5:LRA=11",
		"-ac",
		"1",
		"-ar",
		"24000",
		"-c:a",
		"pcm_s16le",
		str(dst),
	])
	if completed.returncode != 0:
		raise RuntimeError(f"prompt normalization failed: {completed.stderr}")


def build_prompts(
	run_dir: Path,
	*,
	source_manifest: Path | None,
	output_dir: Path | None,
	qwen_repo: Path,
	qwen_python: Path,
	qwen_model: Path,
	voices_dir: Path,
	target_text_json: Path | None,
	dry_run: bool,
	force: bool,
	register_voices: bool,
	min_prompt_sec: float,
	max_prompt_sec: float,
	max_tokens: int,
) -> dict[str, Any]:
	run_dir = run_dir.expanduser().resolve()
	source_manifest = (source_manifest or run_dir / "02b-source-voice-prompts" / "voice_prompt_manifest.json").expanduser().resolve()
	output_dir = (output_dir or run_dir / "02c-qwen-vibevoice-prompts").expanduser().resolve()
	assert source_manifest.exists(), f"Missing source voice prompt manifest: {source_manifest}"
	source_data = _read_json(source_manifest)
	assert source_data.get("status") == "pass", f"Source voice prompt manifest is not pass: {source_manifest}"
	census_roster_path = source_data.get("speaker_census_roster_path")
	if not census_roster_path:
		raise RuntimeError("Source voice prompt manifest missing speaker_census_roster_path; run 02a speaker census and rerun 02b.")
	census_roster = Path(str(census_roster_path))
	if not census_roster.is_absolute():
		census_roster = run_dir / census_roster
	if not census_roster.exists():
		raise RuntimeError(f"Missing speaker census roster referenced by 02b: {census_roster}")
	if str(source_data.get("speaker_census_roster_sha256") or "") != _sha256(census_roster):
		raise RuntimeError(f"Speaker census roster sha256 mismatch: {census_roster}")
	source_roster = source_data.get("speaker_roster") or {}
	if source_roster.get("status") != "frozen" or int(source_roster.get("speaker_count") or 0) != 2 or int(source_roster.get("voice_count") or 0) != 2:
		raise RuntimeError("Source voice prompt manifest does not carry a frozen two-speaker/two-voice roster.")
	speaker_voices = source_data.get("speaker_voices")
	assert isinstance(speaker_voices, dict), "source manifest missing speaker_voices"
	transcript_segments = _load_transcript_segments(run_dir)
	target_texts = _load_target_texts(target_text_json)
	output_dir.mkdir(parents=True, exist_ok=True)
	seed_speakers: dict[str, Any] = {}
	for speaker in ("Speaker 0", "Speaker 1"):
		info = speaker_voices.get(speaker)
		if not isinstance(info, dict):
			raise RuntimeError(f"Missing {speaker} in {source_manifest}")
		chosen = _choose_reference_clip(info, min_ref_sec=8.0, max_ref_sec=20.0)
		reference_dir = output_dir / "reference" / f"speaker{_speaker_index(speaker)}"
		reference_audio = reference_dir / "reference.wav"
		if force or not reference_audio.exists():
			_copy_reference_audio(Path(chosen["audio"]), reference_audio)
		reference_text = _text_for_time_range(
			transcript_segments,
			float(chosen["start_sec"]) if chosen.get("start_sec") is not None else None,
			float(chosen["end_sec"]) if chosen.get("end_sec") is not None else None,
		) or _clean_reference_text(str(chosen.get("text_preview") or ""))
		if not reference_text:
			raise RuntimeError(f"Cannot determine English reference text for {speaker}; provide transcript JSON or selected clip text.")
		noise_reasons = _reference_text_noise_reasons(reference_text)
		if noise_reasons:
			raise RuntimeError(
				f"Rejected noisy Qwen reference text for {speaker}: {', '.join(noise_reasons)}. "
				"Rerun 02b with a corrected speaker timeline/reference clip."
			)
		source_name = str(info.get("vibevoice_name") or f"WC{_safe_name(run_dir.name)}Speaker{_speaker_index(speaker)}")
		vibevoice_name = f"{_safe_name(source_name)}QwenZH"
		seed_speakers[speaker] = {
			"vibevoice_name": vibevoice_name,
			"source_vibevoice_name": source_name,
			"reference_audio": str(reference_audio),
			"reference_audio_sha256": _sha256(reference_audio),
			"source_reference_audio": chosen["audio"],
			"source_reference_kind": chosen["source"],
			"source_start_sec": chosen.get("start_sec"),
			"source_end_sec": chosen.get("end_sec"),
			"reference_text": reference_text,
			"target_text": target_texts[speaker],
			"qwen_output_dir": str(output_dir / f"qwen_speaker{_speaker_index(speaker)}"),
		}
	seed_manifest = {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.seed.v1",
		"status": "dry_run" if dry_run else "prepared",
		"run_dir": str(run_dir),
		"source_voice_prompt_manifest": str(source_manifest),
		"qwen_repo": str(qwen_repo),
		"qwen_python": str(qwen_python),
		"qwen_model": str(qwen_model),
		"max_tokens": max_tokens,
		"force": force,
		"speakers": seed_speakers,
	}
	_write_json(output_dir / "prompt_manifest.seed.json", seed_manifest)
	if dry_run:
		run_manifest_path = run_dir / "run_manifest.json"
		run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
		run_manifest.setdefault("nodes", {})["02c-qwen-vibevoice-prompts"] = {
			"status": "dry_run",
			"prompt_manifest_seed": str(output_dir / "prompt_manifest.seed.json"),
			"source_voice_prompt_manifest": str(source_manifest),
		}
		_write_json(run_manifest_path, run_manifest)
		return run_manifest["nodes"]["02c-qwen-vibevoice-prompts"]
	assert qwen_repo.exists(), f"Missing Qwen repo: {qwen_repo}"
	assert qwen_python.exists(), f"Missing Qwen python: {qwen_python}"
	assert qwen_model.exists(), f"Missing Qwen model: {qwen_model}"
	qwen_payload = {
		"model_path": str(qwen_model),
		"force": force,
		"max_tokens": max_tokens,
		"speakers": seed_speakers,
	}
	payload_path = output_dir / "qwen_generation_input.json"
	_write_json(payload_path, qwen_payload)
	_run_qwen(payload_path, qwen_python, qwen_repo, output_dir / "qwen_generation.stdout.txt", output_dir / "qwen_generation.stderr.txt")
	registered_dir = output_dir / "registered"
	final_speakers: dict[str, Any] = {}
	if register_voices:
		voices_dir.mkdir(parents=True, exist_ok=True)
	for speaker, info in seed_speakers.items():
		qwen_output = _find_qwen_output(Path(info["qwen_output_dir"]))
		voice_filename = f"zh-{info['vibevoice_name']}_qwenzh.wav"
		registered_local = registered_dir / voice_filename
		_normalize_prompt(qwen_output, registered_local)
		registered_path = voices_dir / voice_filename
		if register_voices:
			shutil.copy2(registered_local, registered_path)
		else:
			registered_path = registered_local
		metrics = _audio_metrics(registered_local)
		duration = float(metrics["duration_sec"])
		if duration < min_prompt_sec or duration > max_prompt_sec:
			raise RuntimeError(
				f"{speaker} Chinese prompt duration {duration:.1f}s outside allowed "
				f"{min_prompt_sec:.1f}-{max_prompt_sec:.1f}s: {registered_local}"
			)
		final_speakers[speaker] = {
			"status": "pass",
			"vibevoice_name": info["vibevoice_name"],
			"reference_wav": str(registered_path),
			"registered_path": str(registered_path),
			"local_registered_wav": str(registered_local),
			"duration_sec": round(duration, 3),
			"sha256": _sha256(registered_local),
			"source_vibevoice_name": info["source_vibevoice_name"],
			"source_reference_audio": info["source_reference_audio"],
			"source_reference_kind": info["source_reference_kind"],
			"source_start_sec": info["source_start_sec"],
			"source_end_sec": info["source_end_sec"],
			"reference_text": info["reference_text"],
			"target_text": info["target_text"],
			"qwen_output_wav": str(qwen_output),
			"metrics": metrics,
		}
	manifest = {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
			"method": "source_english_reference_to_qwen3_chinese_prompt_to_vibevoice_voice",
			"run_dir": str(run_dir),
			"source_voice_prompt_manifest": str(source_manifest),
			"speaker_census_roster_path": str(census_roster),
			"speaker_census_roster_sha256": _sha256(census_roster),
			"output_dir": str(output_dir),
		"qwen_repo": str(qwen_repo),
		"qwen_model": str(qwen_model),
		"registered_to_vibevoice": register_voices,
		"voices_dir": str(voices_dir),
		"speaker_voices": final_speakers,
	}
	_write_json(output_dir / "voice_prompt_manifest.json", manifest)
	(output_dir / "voice_prompt_report.md").write_text(
		"\n".join([
			"# Qwen Chinese VibeVoice Prompt Report",
			"",
			"- status: PASS",
			"- method: source English voice reference -> Qwen3 Chinese prompt -> VibeVoice voice",
			f"- source_voice_prompt_manifest: {source_manifest}",
			f"- qwen_model: {qwen_model}",
			f"- registered_to_vibevoice: {register_voices}",
			"",
			"## Speaker Voices",
			"",
			*[
				"\n".join([
					f"### {speaker}",
					"",
					f"- vibevoice_name: {info['vibevoice_name']}",
					f"- reference_wav: {info['reference_wav']}",
					f"- duration_sec: {info['duration_sec']}",
					f"- source_reference_audio: {info['source_reference_audio']}",
				])
				for speaker, info in final_speakers.items()
			],
		]) + "\n",
		encoding="utf-8",
	)
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["02c-qwen-vibevoice-prompts"] = {
		"status": "pass",
		"voice_prompt_manifest": str(output_dir / "voice_prompt_manifest.json"),
		"source_voice_prompt_manifest": str(source_manifest),
		"speaker_names": {
			speaker: info["vibevoice_name"]
			for speaker, info in final_speakers.items()
		},
	}
	_write_json(run_manifest_path, run_manifest)
	return run_manifest["nodes"]["02c-qwen-vibevoice-prompts"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Build Qwen3 Chinese VibeVoice voice prompts from source-speaker references.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--source-manifest", type=Path)
	parser.add_argument("--output-dir", type=Path)
	parser.add_argument("--qwen-repo", type=Path, default=DEFAULT_QWEN_REPO)
	parser.add_argument("--qwen-python", type=Path, default=DEFAULT_QWEN_PYTHON)
	parser.add_argument("--qwen-model", type=Path, default=DEFAULT_QWEN_MODEL)
	parser.add_argument("--voices-dir", type=Path, default=DEFAULT_VIBEVOICE_VOICES_DIR)
	parser.add_argument("--target-text-json", type=Path)
	parser.add_argument("--dry-run", action="store_true")
	parser.add_argument("--force", action="store_true")
	parser.add_argument("--no-register-voices", action="store_true")
	parser.add_argument("--min-prompt-sec", type=float, default=DEFAULT_MIN_PROMPT_SEC)
	parser.add_argument("--max-prompt-sec", type=float, default=DEFAULT_MAX_PROMPT_SEC)
	parser.add_argument("--max-tokens", type=int, default=900)
	args = parser.parse_args()
	result = build_prompts(
		args.run_dir,
		source_manifest=args.source_manifest,
		output_dir=args.output_dir,
		qwen_repo=args.qwen_repo.expanduser().resolve(),
		qwen_python=args.qwen_python.expanduser(),
		qwen_model=args.qwen_model.expanduser().resolve(),
		voices_dir=args.voices_dir.expanduser().resolve(),
		target_text_json=args.target_text_json,
		dry_run=args.dry_run,
		force=args.force,
		register_voices=not args.no_register_voices,
		min_prompt_sec=args.min_prompt_sec,
		max_prompt_sec=args.max_prompt_sec,
		max_tokens=args.max_tokens,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
