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


DEFAULT_VIBEVOICE_VOICES_DIR = Path("/Users/wangfangjia/code/VibeVoice/demo/voices")
DEFAULT_TARGET_SEC = 45.0
DEFAULT_MIN_TOTAL_SEC = 25.0
DEFAULT_MAX_CLIP_SEC = 18.0
DEFAULT_MIN_CLIP_SEC = 8.0
DEFAULT_BOUNDARY_TRIM_SEC = 1.0
DEFAULT_SKIP_BEFORE_SEC = 60.0
DEFAULT_INTER_CLIP_PAUSE_SEC = 0.25


@dataclass(frozen=True)
class TimelineSegment:
	speaker: str
	start: float
	end: float
	text: str
	source: str


@dataclass(frozen=True)
class CandidateClip:
	speaker: str
	start: float
	end: float
	duration: float
	text: str
	source: str


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


def _run(cmd: list[str], *, stdout: Path | None = None, stderr: Path | None = None) -> subprocess.CompletedProcess[str]:
	completed = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if stdout is not None:
		stdout.parent.mkdir(parents=True, exist_ok=True)
		stdout.write_text(completed.stdout, encoding="utf-8")
	if stderr is not None:
		stderr.parent.mkdir(parents=True, exist_ok=True)
		stderr.write_text(completed.stderr, encoding="utf-8")
	return completed


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


def _format_time(seconds: float) -> str:
	seconds = max(0.0, float(seconds))
	hours = int(seconds // 3600)
	minutes = int((seconds % 3600) // 60)
	secs = seconds % 60
	return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _parse_source_time_range(text: str) -> tuple[float, float] | None:
	match = re.search(
		r"(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s*[-–]\s*(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)",
		text,
	)
	if not match:
		return None
	return _parse_time(match.group(1)), _parse_time(match.group(2))


def _coerce_segment(item: dict[str, Any], source: str) -> TimelineSegment | None:
	speaker = str(item.get("speaker") or item.get("speaker_id") or "").strip()
	if speaker in {"0", "1"}:
		speaker = f"Speaker {speaker}"
	if speaker not in {"Speaker 0", "Speaker 1"}:
		return None

	start_value = item.get("source_start", item.get("start", item.get("start_sec")))
	end_value = item.get("source_end", item.get("end", item.get("end_sec")))
	if (start_value is None or end_value is None) and item.get("source_time"):
		parsed = _parse_source_time_range(str(item["source_time"]))
		if parsed is not None:
			start_value, end_value = parsed
	if start_value is None or end_value is None:
		return None
	start = _parse_time(start_value)
	end = _parse_time(end_value)
	if end <= start:
		return None
	text = str(item.get("source_text") or item.get("text") or item.get("transcript") or "").strip()
	return TimelineSegment(speaker=speaker, start=start, end=end, text=text, source=source)


def _load_timeline_json(path: Path) -> list[TimelineSegment]:
	data = _read_json(path)
	if isinstance(data, dict):
		raw_segments = data.get("segments") or data.get("timeline") or data.get("speaker_segments") or []
	elif isinstance(data, list):
		raw_segments = data
	else:
		raw_segments = []
	segments = []
	for item in raw_segments:
		if isinstance(item, dict):
			segment = _coerce_segment(item, str(path))
			if segment is not None:
				segments.append(segment)
	return segments


def _parse_caption_timeline(path: Path) -> list[TimelineSegment]:
	if not path.exists():
		return []
	current_speaker = "Speaker 0"
	turns: list[TimelineSegment] = []
	current_start: float | None = None
	current_end: float | None = None
	current_text: list[str] = []
	line_re = re.compile(
		r"^\[(?P<start>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s*[-–]\s*(?P<end>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\]\s*(?P<text>.*)$"
	)

	def flush() -> None:
		nonlocal current_start, current_end, current_text
		if current_start is None or current_end is None:
			current_text = []
			return
		text = " ".join(current_text).strip()
		if text:
			turns.append(TimelineSegment(current_speaker, current_start, current_end, text, str(path)))
		current_start = None
		current_end = None
		current_text = []

	for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
		match = line_re.match(raw_line.strip())
		if not match:
			continue
		start = _parse_time(match.group("start"))
		end = _parse_time(match.group("end"))
		text = match.group("text").strip()
		if not text:
			continue
		if text.startswith(">>"):
			flush()
			current_speaker = "Speaker 1" if current_speaker == "Speaker 0" else "Speaker 0"
			text = text.lstrip(">").strip()
		if current_start is None:
			current_start = start
			current_end = end
			current_text = [text]
		elif start <= (current_end or start) + 3.0:
			current_end = max(current_end or end, end)
			current_text.append(text)
		else:
			flush()
			current_start = start
			current_end = end
			current_text = [text]
	flush()
	return turns


def _plain_caption_text(text: str) -> str:
	text = re.sub(r">>+", " ", text)
	text = re.sub(r"\[[^\]]+\]", " ", text)
	return re.sub(r"\s+", " ", text).strip()


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


def _caption_event_time(item: dict[str, Any]) -> float | None:
	text = str(item.get("text") or "").strip()
	if ">>" not in text:
		return None
	start_value = item.get("start_sec", item.get("start"))
	end_value = item.get("end_sec", item.get("end"))
	if start_value is None or end_value is None:
		return None
	start = _parse_time(start_value)
	end = _parse_time(end_value)
	return start if text.startswith(">>") else end


def _collapse_event_times(times: list[float], min_gap_sec: float = 1.5) -> list[float]:
	collapsed: list[float] = []
	for value in sorted(times):
		if collapsed and value - collapsed[-1] <= min_gap_sec:
			collapsed[-1] = min(collapsed[-1], value)
			continue
		collapsed.append(value)
	return collapsed


def _interval_text(raw_segments: list[dict[str, Any]], start: float, end: float, max_chars: int = 500) -> str:
	parts: list[str] = []
	seen: set[str] = set()
	for item in raw_segments:
		start_value = item.get("start_sec", item.get("start"))
		end_value = item.get("end_sec", item.get("end"))
		if start_value is None or end_value is None:
			continue
		seg_start = _parse_time(start_value)
		seg_end = _parse_time(end_value)
		midpoint = (seg_start + seg_end) / 2.0
		if not (start <= midpoint <= end):
			continue
		text = _plain_caption_text(str(item.get("text") or ""))
		if not text or text in seen:
			continue
		seen.add(text)
		parts.append(text)
		if sum(len(part) for part in parts) >= max_chars:
			break
	return " ".join(parts).strip()[:max_chars]


def _parse_unlabeled_transcript_json_timeline(path: Path) -> list[TimelineSegment]:
	if not path.exists():
		return []
	data = _read_json(path)
	raw_segments = data.get("segments") if isinstance(data, dict) else data
	if not isinstance(raw_segments, list):
		return []
	segments = [item for item in raw_segments if isinstance(item, dict)]
	if not segments:
		return []
	duration = 0.0
	for item in segments:
		end_value = item.get("end_sec", item.get("end"))
		if end_value is not None:
			duration = max(duration, _parse_time(end_value))
	if duration <= 0:
		return []
	event_times = _collapse_event_times([
		event
		for item in segments
		for event in [_caption_event_time(item)]
		if event is not None
	])
	if len(event_times) < 2:
		return []
	timeline: list[TimelineSegment] = []
	current_speaker = "Speaker 0"
	current_start = 0.0
	for event_time in event_times:
		if event_time - current_start >= 2.0:
			timeline.append(TimelineSegment(
				speaker=current_speaker,
				start=current_start,
				end=event_time,
				text=_interval_text(segments, current_start, event_time),
				source=f"{path}:unlabeled_caption_speaker_change_fallback",
			))
		current_speaker = "Speaker 1" if current_speaker == "Speaker 0" else "Speaker 0"
		current_start = event_time
	if duration - current_start >= 2.0:
		timeline.append(TimelineSegment(
			speaker=current_speaker,
			start=current_start,
			end=duration,
			text=_interval_text(segments, current_start, duration),
			source=f"{path}:unlabeled_caption_speaker_change_fallback",
		))
	return timeline


def _discover_timeline(run_dir: Path, explicit: Path | None) -> tuple[str, list[TimelineSegment]]:
	if explicit is not None:
		segments = _load_timeline_json(explicit)
		return str(explicit), segments
	candidates = [
		run_dir / "02b-source-voice-prompts" / "source_speaker_timeline.json",
		run_dir / "02-source-capture" / "source_speaker_timeline.json",
		run_dir / "03-source-translation" / "source_transcript.zh.json",
	]
	for candidate in candidates:
		if candidate.exists():
			segments = _load_timeline_json(candidate)
			if segments:
				return str(candidate), segments
	transcript_json = run_dir / "02-source-capture" / "source_transcript.en.json"
	segments = _parse_unlabeled_transcript_json_timeline(transcript_json)
	if segments:
		return f"{transcript_json}:unlabeled_caption_speaker_change_fallback", segments
	caption_path = run_dir / "02-source-capture" / "source_transcript.en.txt"
	segments = _parse_caption_timeline(caption_path)
	if segments:
		return str(caption_path), segments
	return "none", []


def _build_candidates(
	segments: list[TimelineSegment],
	*,
	target_sec: float,
	max_clip_sec: float,
	min_clip_sec: float,
	boundary_trim_sec: float,
	skip_before_sec: float,
) -> dict[str, list[CandidateClip]]:
	result: dict[str, list[CandidateClip]] = {"Speaker 0": [], "Speaker 1": []}
	for segment in sorted(segments, key=lambda item: (item.start, item.end)):
		if segment.speaker not in result:
			continue
		if _reference_text_is_noisy(segment.text):
			continue
		safe_start = max(segment.start, skip_before_sec) + boundary_trim_sec
		safe_end = segment.end - boundary_trim_sec
		if safe_end - safe_start < min_clip_sec:
			continue
		pos = safe_start
		while safe_end - pos >= min_clip_sec:
			end = min(pos + max_clip_sec, safe_end)
			duration = end - pos
			if duration >= min_clip_sec:
				result[segment.speaker].append(CandidateClip(
					speaker=segment.speaker,
					start=pos,
					end=end,
					duration=duration,
					text=segment.text[:300],
					source=segment.source,
				))
			if sum(clip.duration for clip in result[segment.speaker]) >= target_sec * 2:
				break
			pos = end + 2.0
	return result


def _reference_text_is_noisy(text: str) -> bool:
	lower = text.lower()
	return _has_rolling_caption_repetition(text) or any(pattern in lower for pattern in (
		"[music]",
		"sponsor",
		"patreon",
		"my debt clinic",
		"debt clinic",
		"credit card",
		"personal loans",
		"partnering with",
		"provision capital",
		"become a member",
		"membership",
		"subscribe",
		"use code",
		"www.",
		"http",
		"visit ",
		".com",
	))


def _build_speaker_roster(
	segments: list[TimelineSegment],
	voice_names: dict[str, str],
	*,
	analysis_window_sec: float,
) -> dict[str, Any]:
	speakers: dict[str, Any] = {}
	for speaker in ("Speaker 0", "Speaker 1"):
		speaker_segments = [segment for segment in segments if segment.speaker == speaker]
		window_speech_sec = 0.0
		for segment in speaker_segments:
			overlap = max(0.0, min(segment.end, analysis_window_sec) - max(segment.start, 0.0))
			window_speech_sec += overlap
		speakers[speaker] = {
			"speaker": speaker,
			"vibevoice_name": voice_names[speaker],
			"segment_count": len(speaker_segments),
			"first_seen_sec": round(min((segment.start for segment in speaker_segments), default=0.0), 3),
			"first_6min_speech_sec": round(window_speech_sec, 3),
			"sample_texts": [
				segment.text[:180]
				for segment in speaker_segments[:3]
				if segment.text
			],
		}
	observed_in_window = [
		speaker
		for speaker, info in speakers.items()
		if float(info["first_6min_speech_sec"]) > 0
	]
	status = "frozen" if all(info["segment_count"] > 0 for info in speakers.values()) else "needs_review"
	return {
		"schema_version": "worldview-china-source-speaker-roster.v1",
		"status": status,
		"speaker_count": 2,
		"analysis_window_sec": analysis_window_sec,
		"observed_speakers_in_first_6min": observed_in_window,
		"policy": "freeze_two_speaker_roster_before_episode_split_and_tts",
		"speakers": speakers,
	}


def _load_frozen_speaker_census(run_dir: Path, voice_names: dict[str, str]) -> dict[str, Any]:
	census_path = run_dir / "02a-speaker-census" / "speaker_roster.json"
	if not census_path.exists():
		raise RuntimeError(
			"Missing frozen speaker census. Run "
			"/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_speaker_census.py "
			f"--run-dir {run_dir} before 02b source voice extraction."
		)
	census = _read_json(census_path)
	if census.get("status") != "frozen":
		raise RuntimeError(f"Speaker census is not frozen: {census_path}")
	if int(census.get("speaker_count") or 0) != 2 or int(census.get("voice_count") or 0) != 2:
		raise RuntimeError(f"Speaker census must freeze exactly two speakers and two voices: {census_path}")
	source_speakers = census.get("speakers") or {}
	speakers: dict[str, Any] = {}
	for speaker in ("Speaker 0", "Speaker 1"):
		info = dict(source_speakers.get(speaker) or {})
		if not info:
			raise RuntimeError(f"Speaker census missing {speaker}: {census_path}")
		info["speaker"] = speaker
		info["vibevoice_name"] = voice_names[speaker]
		speakers[speaker] = info
	return {
		"schema_version": "worldview-china-source-speaker-roster.v1",
		"status": "frozen",
		"speaker_count": 2,
		"voice_count": 2,
		"analysis_window_sec": float(census.get("analysis_window_sec") or 360.0),
		"observed_speakers_in_first_6min": census.get("observed_speakers_in_first_6min") or [],
		"policy": "freeze_two_speaker_roster_before_voice_extraction_episode_split_and_tts",
		"source_census_roster_path": str(census_path),
		"source_census_roster_sha256": _sha256(census_path),
		"census_schema_version": census.get("schema_version"),
		"census_reviewer": census.get("reviewer"),
		"speakers": speakers,
	}


def _parse_volume(stderr: str) -> dict[str, float | None]:
	mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
	max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr)
	return {
		"mean_volume_db": float(mean_match.group(1)) if mean_match else None,
		"max_volume_db": float(max_match.group(1)) if max_match else None,
	}


def _parse_silence(stderr: str) -> float:
	return sum(float(value) for value in re.findall(r"silence_duration:\s*(\d+(?:\.\d+)?)", stderr))


def _extract_candidate(source_audio: Path, clip: CandidateClip, output: Path) -> dict[str, Any]:
	output.parent.mkdir(parents=True, exist_ok=True)
	duration = clip.end - clip.start
	completed = _run([
		"ffmpeg",
		"-y",
		"-ss",
		f"{clip.start:.3f}",
		"-t",
		f"{duration:.3f}",
		"-i",
		str(source_audio),
		"-ac",
		"1",
		"-ar",
		"24000",
		"-c:a",
		"pcm_s16le",
		str(output),
	])
	if completed.returncode != 0:
		raise RuntimeError(f"ffmpeg clip extraction failed: {completed.stderr}")
	actual_duration = _duration(output)
	volume = _run(["ffmpeg", "-hide_banner", "-i", str(output), "-af", "volumedetect", "-f", "null", "-"])
	silence = _run(["ffmpeg", "-hide_banner", "-i", str(output), "-af", "silencedetect=noise=-45dB:d=0.8", "-f", "null", "-"])
	metrics = _parse_volume(volume.stderr)
	silence_sec = _parse_silence(silence.stderr)
	metrics.update({
		"duration_sec": round(actual_duration, 3),
		"silence_sec": round(silence_sec, 3),
		"silence_ratio": round(silence_sec / actual_duration, 4) if actual_duration > 0 else None,
	})
	return metrics


def _clip_passes(metrics: dict[str, Any]) -> tuple[bool, str]:
	mean_volume = metrics.get("mean_volume_db")
	max_volume = metrics.get("max_volume_db")
	silence_ratio = metrics.get("silence_ratio")
	if mean_volume is not None and mean_volume < -38:
		return False, "mean_volume_too_low"
	if max_volume is not None and max_volume < -20:
		return False, "max_volume_too_low"
	if silence_ratio is not None and silence_ratio > 0.4:
		return False, "too_much_silence"
	return True, "pass"


def _concat_clips(clips: list[Path], output: Path, *, pause_sec: float) -> None:
	assert clips, "No clips to concatenate"
	output.parent.mkdir(parents=True, exist_ok=True)
	work_dir = output.parent / "_concat"
	work_dir.mkdir(parents=True, exist_ok=True)
	pause = work_dir / "pause.wav"
	_run([
		"ffmpeg",
		"-y",
		"-f",
		"lavfi",
		"-i",
		"anullsrc=r=24000:cl=mono",
		"-t",
		f"{pause_sec:.3f}",
		"-c:a",
		"pcm_s16le",
		str(pause),
	])
	concat = work_dir / f"{output.stem}.concat.txt"
	lines: list[str] = []
	for index, clip in enumerate(clips):
		lines.append(f"file '{clip.as_posix()}'")
		if index + 1 < len(clips):
			lines.append(f"file '{pause.as_posix()}'")
	concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
	completed = _run([
		"ffmpeg",
		"-y",
		"-f",
		"concat",
		"-safe",
		"0",
		"-i",
		str(concat),
		"-ac",
		"1",
		"-ar",
		"24000",
		"-c:a",
		"pcm_s16le",
		str(output),
	])
	if completed.returncode != 0:
		raise RuntimeError(f"ffmpeg concat failed: {completed.stderr}")


def _safe_run_slug(run_dir: Path) -> str:
	name = run_dir.name
	safe = re.sub(r"[^A-Za-z0-9]+", "S", name).strip("S")
	return safe or "Run"


def extract_voice_prompts(
	run_dir: Path,
	*,
	source_audio: Path | None,
	timeline_json: Path | None,
	output_dir: Path | None,
	voices_dir: Path,
	register_voices: bool,
	target_sec: float,
	min_total_sec: float,
	max_clip_sec: float,
	min_clip_sec: float,
	boundary_trim_sec: float,
	skip_before_sec: float,
	inter_clip_pause_sec: float,
	force: bool,
) -> dict[str, Any]:
	run_dir = run_dir.expanduser().resolve()
	source_audio = (source_audio or run_dir / "02-source-capture" / "youtube-media" / "source.wav").expanduser().resolve()
	output_dir = (output_dir or run_dir / "02b-source-voice-prompts").expanduser().resolve()
	assert source_audio.exists(), f"Missing source audio: {source_audio}"
	source_duration = _duration(source_audio)
	timeline_source, segments = _discover_timeline(run_dir, timeline_json.expanduser().resolve() if timeline_json else None)
	if not segments:
		raise RuntimeError("No speaker timeline found. Provide --timeline-json or a transcript with speaker markers.")
	output_dir.mkdir(parents=True, exist_ok=True)
	_write_json(output_dir / "source_speaker_timeline.normalized.json", [
		{
			"speaker": segment.speaker,
			"start": round(segment.start, 3),
			"end": round(segment.end, 3),
			"start_time": _format_time(segment.start),
			"end_time": _format_time(segment.end),
			"text": segment.text,
			"source": segment.source,
		}
		for segment in segments
	])
	candidates = _build_candidates(
		segments,
		target_sec=target_sec,
		max_clip_sec=max_clip_sec,
		min_clip_sec=min_clip_sec,
		boundary_trim_sec=boundary_trim_sec,
		skip_before_sec=skip_before_sec,
	)
	run_slug = _safe_run_slug(run_dir)
	voice_names = {
		"Speaker 0": f"WC{run_slug}Speaker0",
		"Speaker 1": f"WC{run_slug}Speaker1",
	}
	timeline_roster_evidence = _build_speaker_roster(
		segments,
		voice_names,
		analysis_window_sec=360.0,
	)
	speaker_roster = _load_frozen_speaker_census(run_dir, voice_names)
	speaker_roster["timeline_evidence_at_extraction"] = timeline_roster_evidence
	_write_json(output_dir / "speaker_roster.json", speaker_roster)
	if speaker_roster["status"] != "frozen":
		raise RuntimeError(
			"Speaker roster could not be frozen before voice extraction. "
			f"Inspect {run_dir / '02a-speaker-census/speaker_roster.json'} and rerun 02a speaker census."
		)
	selected_summary: dict[str, Any] = {}
	for speaker in ("Speaker 0", "Speaker 1"):
		speaker_dir = output_dir / speaker.lower().replace(" ", "")
		clips_dir = speaker_dir / "clips"
		reference_path = speaker_dir / f"en-{voice_names[speaker]}_source.wav"
		if reference_path.exists() and not force:
			selected_summary[speaker] = {
				"status": "reused_existing",
				"vibevoice_name": voice_names[speaker],
				"reference_wav": str(reference_path),
				"duration_sec": round(_duration(reference_path), 3),
				"selected_clips": [],
			}
			continue
		selected_clips: list[Path] = []
		clip_records: list[dict[str, Any]] = []
		total = 0.0
		for index, candidate in enumerate(candidates[speaker], start=1):
			if total >= target_sec:
				break
			clip_path = clips_dir / f"clip_{index:03d}.wav"
			metrics = _extract_candidate(source_audio, candidate, clip_path)
			passed, reason = _clip_passes(metrics)
			record = {
				"clip": str(clip_path),
				"speaker": speaker,
				"start_sec": round(candidate.start, 3),
				"end_sec": round(candidate.end, 3),
				"start_time": _format_time(candidate.start),
				"end_time": _format_time(candidate.end),
				"candidate_duration_sec": round(candidate.duration, 3),
				"text_preview": candidate.text,
				"metrics": metrics,
				"selected": passed,
				"decision": reason,
			}
			clip_records.append(record)
			if passed:
				selected_clips.append(clip_path)
				total += float(metrics["duration_sec"])
		if total < min_total_sec:
			raise RuntimeError(
				f"Insufficient clean voice prompt audio for {speaker}: selected {total:.1f}s, "
				f"required at least {min_total_sec:.1f}s. See {clips_dir}."
			)
		_concat_clips(selected_clips, reference_path, pause_sec=inter_clip_pause_sec)
		selected_summary[speaker] = {
			"status": "created",
			"vibevoice_name": voice_names[speaker],
			"reference_wav": str(reference_path),
			"duration_sec": round(_duration(reference_path), 3),
			"sha256": _sha256(reference_path),
			"selected_clips": [record for record in clip_records if record["selected"]],
			"rejected_clips": [record for record in clip_records if not record["selected"]],
		}

	registered: dict[str, str | None] = {}
	if register_voices:
		voices_dir.mkdir(parents=True, exist_ok=True)
		for speaker, info in selected_summary.items():
			reference = Path(str(info["reference_wav"]))
			destination = voices_dir / reference.name
			shutil.copy2(reference, destination)
			registered[speaker] = str(destination)
	else:
		registered = {"Speaker 0": None, "Speaker 1": None}

	for speaker, destination in registered.items():
		selected_summary[speaker]["registered_path"] = destination

	manifest = {
		"schema_version": "worldview-china-source-voice-prompts.v1",
		"status": "pass",
		"source_audio": str(source_audio),
		"source_audio_duration_sec": round(source_duration, 3),
			"timeline_source": timeline_source,
			"output_dir": str(output_dir),
			"method": "speaker_timeline_guided_ffmpeg_reference_extraction",
			"speaker_census_roster_path": speaker_roster["source_census_roster_path"],
			"speaker_census_roster_sha256": speaker_roster["source_census_roster_sha256"],
			"speaker_roster_path": str(output_dir / "speaker_roster.json"),
			"speaker_roster": speaker_roster,
			"parameters": {
			"target_sec_per_speaker": target_sec,
			"min_total_sec_per_speaker": min_total_sec,
			"max_clip_sec": max_clip_sec,
			"min_clip_sec": min_clip_sec,
			"boundary_trim_sec": boundary_trim_sec,
			"skip_before_sec": skip_before_sec,
			"inter_clip_pause_sec": inter_clip_pause_sec,
		},
		"speaker_voices": selected_summary,
	}
	_write_json(output_dir / "voice_prompt_manifest.json", manifest)
	(output_dir / "voice_prompt_report.md").write_text(
		"\n".join([
			"# Source Voice Prompt Report",
			"",
			"- status: PASS",
			f"- source_audio: {source_audio}",
			f"- timeline_source: {timeline_source}",
			f"- speaker_roster: {output_dir / 'speaker_roster.json'}",
			f"- target_sec_per_speaker: {target_sec}",
			"",
			"## Speaker Voices",
			"",
			*[
				"\n".join([
					f"### {speaker}",
					"",
					f"- vibevoice_name: {info['vibevoice_name']}",
					f"- reference_wav: {info['reference_wav']}",
					f"- registered_path: {info.get('registered_path')}",
					f"- duration_sec: {info['duration_sec']}",
					f"- selected_clip_count: {len(info.get('selected_clips', []))}",
				])
				for speaker, info in selected_summary.items()
			],
		]) + "\n",
		encoding="utf-8",
	)
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["02b-source-voice-prompts"] = {
		"status": "pass",
		"voice_prompt_manifest": str(output_dir / "voice_prompt_manifest.json"),
		"speaker_roster": str(output_dir / "speaker_roster.json"),
		"speaker_names": {
			speaker: info["vibevoice_name"]
			for speaker, info in selected_summary.items()
		},
	}
	_write_json(run_manifest_path, run_manifest)
	return run_manifest["nodes"]["02b-source-voice-prompts"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Extract clean source-speaker voice prompts for VibeVoice.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--source-audio", type=Path)
	parser.add_argument("--timeline-json", type=Path)
	parser.add_argument("--output-dir", type=Path)
	parser.add_argument("--voices-dir", type=Path, default=DEFAULT_VIBEVOICE_VOICES_DIR)
	parser.add_argument("--no-register-voices", action="store_true")
	parser.add_argument("--target-sec", type=float, default=DEFAULT_TARGET_SEC)
	parser.add_argument("--min-total-sec", type=float, default=DEFAULT_MIN_TOTAL_SEC)
	parser.add_argument("--max-clip-sec", type=float, default=DEFAULT_MAX_CLIP_SEC)
	parser.add_argument("--min-clip-sec", type=float, default=DEFAULT_MIN_CLIP_SEC)
	parser.add_argument("--boundary-trim-sec", type=float, default=DEFAULT_BOUNDARY_TRIM_SEC)
	parser.add_argument("--skip-before-sec", type=float, default=DEFAULT_SKIP_BEFORE_SEC)
	parser.add_argument("--inter-clip-pause-sec", type=float, default=DEFAULT_INTER_CLIP_PAUSE_SEC)
	parser.add_argument("--force", action="store_true")
	args = parser.parse_args()
	result = extract_voice_prompts(
		args.run_dir,
		source_audio=args.source_audio,
		timeline_json=args.timeline_json,
		output_dir=args.output_dir,
		voices_dir=args.voices_dir.expanduser().resolve(),
		register_voices=not args.no_register_voices,
		target_sec=args.target_sec,
		min_total_sec=args.min_total_sec,
		max_clip_sec=args.max_clip_sec,
		min_clip_sec=args.min_clip_sec,
		boundary_trim_sec=args.boundary_trim_sec,
		skip_before_sec=args.skip_before_sec,
		inter_clip_pause_sec=args.inter_clip_pause_sec,
		force=args.force,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
