#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ANALYSIS_WINDOW_SEC = 360.0
MAX_SPEAKERS = 4
SPEAKER_RE = re.compile(r"^Speaker ([0-3])$")


@dataclass(frozen=True)
class TimelineSegment:
	speaker: str
	start: float
	end: float
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


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


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


def _speaker_id(index: int) -> str:
	assert 0 <= index < MAX_SPEAKERS
	return f"Speaker {index}"


def _speaker_index(speaker: str) -> int:
	match = SPEAKER_RE.fullmatch(speaker)
	assert match, f"Unsupported speaker id: {speaker}"
	return int(match.group(1))


def _speaker_ids(count: int) -> list[str]:
	assert 1 <= count <= MAX_SPEAKERS, f"speaker count must be 1-{MAX_SPEAKERS}, got {count}"
	return [_speaker_id(index) for index in range(count)]


def _is_supported_speaker(speaker: str) -> bool:
	return SPEAKER_RE.fullmatch(speaker) is not None


def _parse_speaker_kv(values: list[str]) -> dict[str, str]:
	result: dict[str, str] = {}
	for value in values:
		if "=" not in value:
			raise RuntimeError(f"Expected SpeakerN=value, got: {value}")
		speaker, text = value.split("=", 1)
		speaker = speaker.strip()
		if re.fullmatch(r"[0-3]", speaker):
			speaker = f"Speaker {speaker}"
		if not _is_supported_speaker(speaker):
			raise RuntimeError(f"Unsupported speaker in key-value argument: {speaker}")
		result[speaker] = text.strip()
	return result


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
	if re.fullmatch(r"[0-3]", speaker):
		speaker = f"Speaker {speaker}"
	if not _is_supported_speaker(speaker):
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
	segments: list[TimelineSegment] = []
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


def _parse_unlabeled_transcript_json_timeline(path: Path) -> list[TimelineSegment]:
	if not path.exists():
		return []
	data = _read_json(path)
	if isinstance(data, dict):
		raw_segments = data.get("segments")
		if raw_segments is None and isinstance(data.get("transcript"), dict):
			raw_segments = data["transcript"].get("segments")
	elif isinstance(data, list):
		raw_segments = data
	else:
		raw_segments = []
	if raw_segments is None:
		raw_segments = []
	segments: list[dict[str, Any]] = []
	for item in raw_segments:
		if not isinstance(item, dict):
			continue
		start = item.get("start", item.get("start_sec", item.get("source_start")))
		end = item.get("end", item.get("end_sec", item.get("source_end")))
		text = str(item.get("text") or item.get("source_text") or "").strip()
		if start is None or end is None or not text:
			continue
		segments.append({"start": _parse_time(start), "end": _parse_time(end), "text": text})
	if not segments:
		return []
	timeline: list[TimelineSegment] = []
	current_speaker = "Speaker 0"
	current_start = float(segments[0]["start"])
	buffer: list[str] = []
	for segment in segments:
		text = str(segment["text"])
		if ">>" in text and buffer:
			timeline.append(TimelineSegment(
				speaker=current_speaker,
				start=current_start,
				end=float(segment["start"]),
				text=" ".join(buffer).strip(),
				source=f"{path}:caption_speaker_marker_fallback",
			))
			current_speaker = "Speaker 1" if current_speaker == "Speaker 0" else "Speaker 0"
			current_start = float(segment["start"])
			buffer = [_plain_caption_text(text)]
		else:
			buffer.append(_plain_caption_text(text))
	if buffer:
		timeline.append(TimelineSegment(
			speaker=current_speaker,
			start=current_start,
			end=float(segments[-1]["end"]),
			text=" ".join(buffer).strip(),
			source=f"{path}:caption_speaker_marker_fallback",
		))
	return [segment for segment in timeline if segment.end > segment.start and segment.text]


def _discover_timeline(run_dir: Path, explicit: Path | None) -> tuple[str, str, list[TimelineSegment]]:
	if explicit is not None:
		segments = _load_timeline_json(explicit)
		return str(explicit), "explicit", segments
	candidates = [
		run_dir / "02a-speaker-census/source_speaker_timeline.json",
		run_dir / "02-source-capture/source_speaker_timeline.json",
		run_dir / "02b-source-voice-prompts/source_speaker_timeline.json",
		run_dir / "02b-source-voice-prompts/source_speaker_timeline.normalized.json",
	]
	for candidate in candidates:
		if candidate.exists():
			segments = _load_timeline_json(candidate)
			if segments:
				return str(candidate), "explicit", segments
	transcript_json = run_dir / "02-source-capture/source_transcript.en.json"
	segments = _parse_unlabeled_transcript_json_timeline(transcript_json)
	if segments:
		return f"{transcript_json}:caption_speaker_marker_fallback", "caption_marker_fallback", segments
	caption_path = run_dir / "02-source-capture/source_transcript.en.txt"
	segments = _parse_caption_timeline(caption_path)
	if segments:
		return str(caption_path), "caption_marker_fallback", segments
	return "none", "none", []


def _extract_review_media(
	source_video: Path | None,
	source_audio: Path,
	output_dir: Path,
	analysis_window_sec: float,
	force: bool,
) -> dict[str, str | None]:
	review_dir = output_dir / "review"
	review_dir.mkdir(parents=True, exist_ok=True)
	audio_out = review_dir / "first_6min.wav"
	if force or not audio_out.exists():
		completed = _run([
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-t",
			f"{analysis_window_sec:.3f}",
			"-i",
			str(source_audio),
			"-ac",
			"1",
			"-ar",
			"24000",
			"-c:a",
			"pcm_s16le",
			str(audio_out),
		])
		if completed.returncode != 0:
			raise RuntimeError(f"ffmpeg first-6min audio extraction failed: {completed.stderr}")
	video_out: Path | None = None
	if source_video is not None and source_video.exists():
		video_out = review_dir / "first_6min_review.mp4"
		if force or not video_out.exists():
			completed = _run([
				"ffmpeg",
				"-hide_banner",
				"-loglevel",
				"error",
				"-y",
				"-t",
				f"{analysis_window_sec:.3f}",
				"-i",
				str(source_video),
				"-vf",
				"scale=1280:-2",
				"-c:v",
				"libx264",
				"-preset",
				"veryfast",
				"-crf",
				"28",
				"-c:a",
				"aac",
				"-b:a",
				"96k",
				str(video_out),
			])
			if completed.returncode != 0:
				raise RuntimeError(f"ffmpeg first-6min review video extraction failed: {completed.stderr}")
	return {
		"analysis_window_audio": str(audio_out),
		"analysis_window_audio_sha256": _sha256(audio_out) if audio_out.exists() else None,
		"analysis_window_video": str(video_out) if video_out is not None else None,
		"analysis_window_video_sha256": _sha256(video_out) if video_out is not None and video_out.exists() else None,
	}


def _speaker_summary(segments: list[TimelineSegment], analysis_window_sec: float, speaker_ids: list[str]) -> dict[str, dict[str, Any]]:
	summaries: dict[str, dict[str, Any]] = {}
	for speaker in speaker_ids:
		speaker_segments = [segment for segment in segments if segment.speaker == speaker]
		window_speech_sec = 0.0
		for segment in speaker_segments:
			window_speech_sec += max(0.0, min(segment.end, analysis_window_sec) - max(segment.start, 0.0))
		summaries[speaker] = {
			"speaker": speaker,
			"first_seen_sec": round(min((segment.start for segment in speaker_segments), default=0.0), 3),
			"first_6min_speech_sec": round(window_speech_sec, 3),
			"segment_count": len(speaker_segments),
			"sample_texts": [
				segment.text[:180]
				for segment in speaker_segments[:3]
				if segment.text
			],
		}
	return summaries


def run_speaker_census(
	run_dir: Path,
	*,
	source_video: Path | None,
	source_audio: Path | None,
	timeline_json: Path | None,
	output_dir: Path | None,
	analysis_window_sec: float,
	force: bool,
	skip_review_media: bool,
	confirm_two_speakers: bool,
	confirm_speaker_count: int | None = None,
	reviewer: str = "main_agent",
	speaker0_description: str = "",
	speaker1_description: str = "",
	speaker0_role: str = "host_or_speaker_0",
	speaker1_role: str = "guest_or_speaker_1",
	speaker0_identity: str = "",
	speaker1_identity: str = "",
	speaker_descriptions: dict[str, str] | None = None,
	speaker_roles: dict[str, str] | None = None,
	speaker_identities: dict[str, str] | None = None,
	note: list[str] | None = None,
) -> dict[str, Any]:
	run_dir = run_dir.expanduser().resolve()
	output_dir = (output_dir or run_dir / "02a-speaker-census").expanduser().resolve()
	source_audio = (source_audio or run_dir / "02-source-capture/youtube-media/source.wav").expanduser().resolve()
	default_source_video = run_dir / "02-source-capture/youtube-media/source.mp4"
	source_video = (source_video.expanduser().resolve() if source_video else default_source_video.resolve())
	assert source_audio.exists(), f"Missing source audio: {source_audio}"
	output_dir.mkdir(parents=True, exist_ok=True)
	review_media = {
		"analysis_window_audio": None,
		"analysis_window_audio_sha256": None,
		"analysis_window_video": None,
		"analysis_window_video_sha256": None,
	}
	if not skip_review_media:
		review_media = _extract_review_media(
			source_video if source_video.exists() else None,
			source_audio,
			output_dir,
			analysis_window_sec,
			force,
		)
	timeline_source, timeline_confidence, segments = _discover_timeline(
		run_dir,
		timeline_json.expanduser().resolve() if timeline_json else None,
	)
	window_segments = [
		segment
		for segment in segments
		if segment.end > 0 and segment.start < analysis_window_sec
	]
	observed_speakers_all = sorted(
		{segment.speaker for segment in window_segments if _is_supported_speaker(segment.speaker)},
		key=_speaker_index,
	)
	if confirm_two_speakers:
		if confirm_speaker_count is not None and confirm_speaker_count != 2:
			raise RuntimeError("--confirm-two-speakers conflicts with --confirm-speaker-count other than 2")
		confirm_speaker_count = 2
	if confirm_speaker_count is not None:
		if not 1 <= confirm_speaker_count <= MAX_SPEAKERS:
			raise RuntimeError(f"--confirm-speaker-count must be 1-{MAX_SPEAKERS}")
		speaker_ids = _speaker_ids(confirm_speaker_count)
	else:
		review_count = max(2, len(observed_speakers_all))
		speaker_ids = _speaker_ids(min(MAX_SPEAKERS, review_count))
	speaker_descriptions = dict(speaker_descriptions or {})
	speaker_roles = dict(speaker_roles or {})
	speaker_identities = dict(speaker_identities or {})
	if speaker0_description.strip():
		speaker_descriptions.setdefault("Speaker 0", speaker0_description.strip())
	if speaker1_description.strip():
		speaker_descriptions.setdefault("Speaker 1", speaker1_description.strip())
	if speaker0_role.strip():
		speaker_roles.setdefault("Speaker 0", speaker0_role.strip())
	if speaker1_role.strip():
		speaker_roles.setdefault("Speaker 1", speaker1_role.strip())
	if speaker0_identity.strip():
		speaker_identities.setdefault("Speaker 0", speaker0_identity.strip())
	if speaker1_identity.strip():
		speaker_identities.setdefault("Speaker 1", speaker1_identity.strip())
	summaries = _speaker_summary(segments, analysis_window_sec, speaker_ids)
	observed_in_window = [
		speaker
		for speaker, summary in summaries.items()
		if float(summary["first_6min_speech_sec"]) > 0
	]
	warnings: list[str] = []
	if timeline_confidence != "explicit":
		warnings.append("speaker timeline is not explicit; reviewer confirmation is required")
	if set(observed_in_window) != set(speaker_ids):
		warnings.append(
			"timeline evidence does not show every confirmed speaker in the first analysis window: "
			f"expected={speaker_ids}, observed={observed_in_window}"
		)
	if confirm_speaker_count is not None:
		missing_descriptions = [speaker for speaker in speaker_ids if not speaker_descriptions.get(speaker, "").strip()]
		if missing_descriptions:
			raise RuntimeError(
				"--confirm-speaker-count requires descriptions for every speaker; missing "
				+ ", ".join(missing_descriptions)
			)
	status = "frozen" if confirm_speaker_count is not None else "needs_review"
	speaker_details = {}
	for speaker in speaker_ids:
		index = _speaker_index(speaker)
		speaker_details[speaker] = {
			**summaries[speaker],
			"role": speaker_roles.get(speaker, f"source_speaker_{index}"),
			"identity": speaker_identities.get(speaker, ""),
			"description": speaker_descriptions.get(speaker, ""),
			"voice_slot": f"voice{index}",
		}
	roster = {
		"schema_version": "worldview-china-speaker-census.v1",
		"status": status,
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"run_dir": str(run_dir),
		"speaker_count": len(speaker_ids) if status == "frozen" else None,
		"voice_count": len(speaker_ids) if status == "frozen" else None,
		"max_supported_speakers": MAX_SPEAKERS,
		"analysis_window_sec": analysis_window_sec,
		"analysis_window_start_sec": 0.0,
		"analysis_window_end_sec": analysis_window_sec,
		"reviewer": reviewer,
		"confirmation_required": True,
		"confirmation": f"confirmed_{len(speaker_ids)}_main_speakers" if confirm_speaker_count is not None else "not_confirmed",
		"policy": "freeze_up_to_four_speaker_voice_roster_before_voice_extraction_episode_split_and_tts",
		"source_audio": str(source_audio),
		"source_audio_duration_sec": round(_duration(source_audio), 3),
		"source_video": str(source_video) if source_video.exists() else None,
		"review_media": review_media,
		"timeline_source": timeline_source,
		"timeline_confidence": timeline_confidence,
		"observed_speakers_in_first_6min": observed_in_window,
		"excluded_as_voice_evidence": [
			"intro_narration",
			"sponsor_or_ad_read",
			"music_bed",
			"third_party_clip",
			"overlapping_speech",
			"rolling_caption_repetition",
		],
		"warnings": warnings,
		"notes": note or [],
		"speakers": speaker_details,
	}
	evidence = {
		"schema_version": "worldview-china-speaker-census-evidence.v1",
		"status": status,
		"timeline_source": timeline_source,
		"timeline_confidence": timeline_confidence,
		"analysis_window_sec": analysis_window_sec,
		"review_media": review_media,
		"timeline_segments_in_window": [
			{
				"speaker": segment.speaker,
				"start_sec": round(segment.start, 3),
				"end_sec": round(segment.end, 3),
				"start_time": _format_time(segment.start),
				"end_time": _format_time(segment.end),
				"text": segment.text[:300],
				"source": segment.source,
			}
			for segment in window_segments[:200]
		],
	}
	_write_json(output_dir / "speaker_roster.json", roster)
	_write_json(output_dir / "speaker_census_evidence.json", evidence)
	report_lines = [
		"# Speaker Census",
		"",
		f"- status: {status}",
		f"- analysis_window_sec: {analysis_window_sec}",
		f"- reviewer: {reviewer}",
		f"- timeline_source: {timeline_source}",
		f"- timeline_confidence: {timeline_confidence}",
		f"- observed_speakers_in_first_6min: {', '.join(observed_in_window) if observed_in_window else 'none'}",
		f"- review_video: {review_media.get('analysis_window_video') or 'none'}",
		f"- review_audio: {review_media.get('analysis_window_audio') or 'none'}",
		"",
		"## Frozen Roster",
		"",
	]
	for speaker in speaker_ids:
		info = speaker_details[speaker]
		report_lines.extend([
			f"- {speaker}: {info['role']}",
			f"  - identity: {info['identity'] or 'unknown'}",
			f"  - description: {info['description'] or 'missing'}",
			f"  - first_6min_speech_sec: {info['first_6min_speech_sec']}",
		])
	if warnings:
		report_lines.extend(["", "## Warnings", ""])
		report_lines.extend(f"- {warning}" for warning in warnings)
	(output_dir / "speaker_census_report.md").write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")
	return roster


def main() -> int:
	parser = argparse.ArgumentParser(description="Create the first-six-minute speaker and voice roster gate for a Worldview China podcast run.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--source-video", type=Path)
	parser.add_argument("--source-audio", type=Path)
	parser.add_argument("--timeline-json", type=Path)
	parser.add_argument("--output-dir", type=Path)
	parser.add_argument("--analysis-window-sec", type=float, default=DEFAULT_ANALYSIS_WINDOW_SEC)
	parser.add_argument("--force", action="store_true")
	parser.add_argument("--skip-review-media", action="store_true")
	parser.add_argument("--confirm-two-speakers", action="store_true", help="Backward-compatible alias for --confirm-speaker-count 2.")
	parser.add_argument("--confirm-speaker-count", type=int, choices=range(1, MAX_SPEAKERS + 1), help="Freeze a confirmed source speaker/voice roster of 1-4 speakers.")
	parser.add_argument("--reviewer", default="main_agent")
	parser.add_argument("--speaker0-description", default="")
	parser.add_argument("--speaker1-description", default="")
	parser.add_argument("--speaker0-role", default="host_or_speaker_0")
	parser.add_argument("--speaker1-role", default="guest_or_speaker_1")
	parser.add_argument("--speaker0-identity", default="")
	parser.add_argument("--speaker1-identity", default="")
	parser.add_argument("--speaker-description", action="append", default=[], help="Additional speaker description as 'Speaker 2=...' or '2=...'.")
	parser.add_argument("--speaker-role", action="append", default=[], help="Additional speaker role as 'Speaker 2=...' or '2=...'.")
	parser.add_argument("--speaker-identity", action="append", default=[], help="Additional speaker identity as 'Speaker 2=...' or '2=...'.")
	parser.add_argument("--note", action="append", default=[])
	args = parser.parse_args()
	result = run_speaker_census(
		args.run_dir,
		source_video=args.source_video,
		source_audio=args.source_audio,
		timeline_json=args.timeline_json,
		output_dir=args.output_dir,
		analysis_window_sec=args.analysis_window_sec,
		force=args.force,
		skip_review_media=args.skip_review_media,
		confirm_two_speakers=args.confirm_two_speakers,
		confirm_speaker_count=args.confirm_speaker_count,
		reviewer=args.reviewer,
		speaker0_description=args.speaker0_description,
		speaker1_description=args.speaker1_description,
		speaker0_role=args.speaker0_role,
		speaker1_role=args.speaker1_role,
		speaker0_identity=args.speaker0_identity,
		speaker1_identity=args.speaker1_identity,
		speaker_descriptions=_parse_speaker_kv(args.speaker_description),
		speaker_roles=_parse_speaker_kv(args.speaker_role),
		speaker_identities=_parse_speaker_kv(args.speaker_identity),
		note=args.note,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "frozen" else 2


if __name__ == "__main__":
	raise SystemExit(main())
