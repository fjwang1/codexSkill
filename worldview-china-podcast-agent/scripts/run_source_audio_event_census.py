#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


NON_SPEECH_EVENT_RE = re.compile(r"^\[(?P<label>music|applause|silence|intro|outro|sound|sfx|laughter|noise)\]$", re.IGNORECASE)
REUSABLE_EVENT_TYPES = {"music", "applause", "intro", "outro", "sound", "sfx", "laughter"}


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


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
	text = str(value or "").strip()
	if not text:
		raise ValueError("empty timestamp")
	parts = text.split(":")
	if len(parts) == 1:
		return float(parts[0])
	if len(parts) == 2:
		return int(parts[0]) * 60 + float(parts[1])
	if len(parts) == 3:
		return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
	raise ValueError(f"unsupported timestamp: {value!r}")


def _round_range(start: float, end: float) -> dict[str, float]:
	return {
		"start_sec": round(start, 3),
		"end_sec": round(end, 3),
		"duration_sec": round(max(0.0, end - start), 3),
	}


def _merge_ranges(ranges: list[tuple[float, float]], gap: float = 0.05) -> list[tuple[float, float]]:
	ordered = sorted((float(start), float(end)) for start, end in ranges if end > start)
	merged: list[tuple[float, float]] = []
	for start, end in ordered:
		if not merged or start > merged[-1][1] + gap:
			merged.append((start, end))
		else:
			merged[-1] = (merged[-1][0], max(merged[-1][1], end))
	return merged


def _intersect(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float] | None:
	start = max(a[0], b[0])
	end = min(a[1], b[1])
	if end <= start:
		return None
	return start, end


def _range_duration(ranges: list[tuple[float, float]]) -> float:
	return sum(max(0.0, end - start) for start, end in ranges)


def _subtract_ranges(base_ranges: list[tuple[float, float]], cut_ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
	result = _merge_ranges(base_ranges)
	for cut_start, cut_end in _merge_ranges(cut_ranges):
		next_ranges: list[tuple[float, float]] = []
		for start, end in result:
			if cut_end <= start or cut_start >= end:
				next_ranges.append((start, end))
				continue
			if cut_start > start:
				next_ranges.append((start, min(cut_start, end)))
			if cut_end < end:
				next_ranges.append((max(cut_end, start), end))
		result = next_ranges
	return _merge_ranges(result)


def _coerce_timeline_items(path: Path) -> list[dict[str, Any]]:
	data = _read_json(path)
	if isinstance(data, dict):
		raw = data.get("turns") or data.get("segments") or data.get("timeline") or data.get("speaker_segments") or []
	elif isinstance(data, list):
		raw = data
	else:
		raw = []
	items: list[dict[str, Any]] = []
	for index, item in enumerate(raw, start=1):
		if not isinstance(item, dict):
			continue
		start_value = item.get("source_start", item.get("source_start_sec", item.get("start", item.get("start_sec"))))
		end_value = item.get("source_end", item.get("source_end_sec", item.get("end", item.get("end_sec"))))
		if start_value is None or end_value is None:
			continue
		start = _parse_time(start_value)
		end = _parse_time(end_value)
		if end <= start:
			continue
		text = str(item.get("source_text") or item.get("text") or item.get("transcript") or "").strip()
		speaker = str(item.get("speaker") or item.get("speaker_id") or "").strip()
		items.append({
			"index": index,
			"speaker": speaker,
			"start_sec": start,
			"end_sec": end,
			"text": text,
			"source": str(path),
		})
	return sorted(items, key=lambda item: (item["start_sec"], item["end_sec"]))


def _event_type_from_text(text: str) -> str | None:
	match = NON_SPEECH_EVENT_RE.fullmatch(re.sub(r"\s+", " ", str(text or "")).strip())
	if not match:
		return None
	label = match.group("label").lower()
	if label == "silence":
		return "silence"
	if label == "noise":
		return "background_audio_unknown"
	return label


def _detect_silence_ranges(source_audio: Path, noise_threshold_db: str, min_silence_sec: float) -> list[tuple[float, float]]:
	completed = _run([
		"ffmpeg",
		"-hide_banner",
		"-i",
		str(source_audio),
		"-af",
		f"silencedetect=noise={noise_threshold_db}:d={min_silence_sec}",
		"-f",
		"null",
		"-",
	])
	text = "\n".join([completed.stdout, completed.stderr])
	starts = [float(match.group(1)) for match in re.finditer(r"silence_start:\s*(\d+(?:\.\d+)?)", text)]
	ends = [float(match.group(1)) for match in re.finditer(r"silence_end:\s*(\d+(?:\.\d+)?)", text)]
	ranges: list[tuple[float, float]] = []
	for start, end in zip(starts, ends, strict=False):
		if end > start:
			ranges.append((start, end))
	return _merge_ranges(ranges)


def build_source_audio_event_census(
	run_dir: Path,
	source_audio: Path | None = None,
	source_turn_map: Path | None = None,
	output_path: Path | None = None,
	min_event_duration_sec: float = 0.5,
	noise_threshold_db: str = "-45dB",
	min_silence_sec: float = 0.5,
) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	source_audio = (source_audio or run_dir / "02-source-capture/youtube-media/source.wav").resolve()
	source_turn_map = (source_turn_map or run_dir / "02b-source-voice-prompts/source_speaker_timeline.normalized.json").resolve()
	output_path = (output_path or run_dir / "02a-source-audio-events/source_audio_events.json").resolve()
	assert source_audio.exists(), f"Missing source audio: {source_audio}"
	assert source_turn_map.exists(), f"Missing source turn map: {source_turn_map}"
	source_duration = _duration(source_audio)
	timeline_items = _coerce_timeline_items(source_turn_map)
	speech_ranges = _merge_ranges([
		(float(item["start_sec"]), float(item["end_sec"]))
		for item in timeline_items
		if _event_type_from_text(str(item.get("text") or "")) is None
	])
	silence_ranges = _detect_silence_ranges(source_audio, noise_threshold_db, min_silence_sec)
	events: list[dict[str, Any]] = []
	for item in timeline_items:
		event_type = _event_type_from_text(str(item.get("text") or ""))
		if event_type is None:
			continue
		start = float(item["start_sec"])
		end = float(item["end_sec"])
		if end - start < min_event_duration_sec:
			continue
		speech_overlap = _range_duration([
			overlap
			for speech_range in speech_ranges
			if (overlap := _intersect((start, end), speech_range)) is not None
		])
		reuse = event_type in REUSABLE_EVENT_TYPES and speech_overlap <= 0.05
		events.append({
			"event_id": f"event_{len(events) + 1:04d}",
			"event_type": event_type,
			**_round_range(start, end),
			"confidence": 0.95 if reuse else 0.8,
			"reuse_source_audio": reuse,
			"requires_no_speech_overlap": True,
			"speech_overlap_sec": round(speech_overlap, 3),
			"evidence": {
				"basis": "source_timeline_explicit_non_speech_tag",
				"text": item.get("text") or "",
				"timeline_index": item.get("index"),
				"source": item.get("source"),
			},
		})
	# Gaps before the first speech or between speech ranges may contain stingers/room tone.
	# They are only reusable when not detected as hard silence; this stays conservative.
	if speech_ranges:
		candidate_gaps = _subtract_ranges([(0.0, min(source_duration, speech_ranges[-1][1]))], speech_ranges)
		for start, end in candidate_gaps:
			if end - start < min_event_duration_sec:
				continue
			silence_overlap = _range_duration([
				overlap
				for silence_range in silence_ranges
				if (overlap := _intersect((start, end), silence_range)) is not None
			])
			if silence_overlap / max(0.001, end - start) >= 0.8:
				event_type = "silence"
				reuse = False
				confidence = 0.9
			else:
				event_type = "background_audio_unknown"
				reuse = False
				confidence = 0.55
			events.append({
				"event_id": f"event_{len(events) + 1:04d}",
				"event_type": event_type,
				**_round_range(start, end),
				"confidence": confidence,
				"reuse_source_audio": reuse,
				"requires_no_speech_overlap": True,
				"speech_overlap_sec": 0.0,
				"evidence": {
					"basis": "no_speaker_turn_gap_with_silencedetect",
					"silence_overlap_sec": round(silence_overlap, 3),
					"silence_overlap_ratio": round(silence_overlap / max(0.001, end - start), 4),
				},
			})
	events = sorted(events, key=lambda item: (float(item["start_sec"]), float(item["end_sec"]), item["event_id"]))
	for index, event in enumerate(events, start=1):
		event["event_id"] = f"event_{index:04d}"
	result = {
		"schema_version": "worldview-china-source-audio-event-census.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"source_audio": str(source_audio),
		"source_audio_sha256": _sha256(source_audio),
		"source_duration_sec": round(source_duration, 3),
		"source_turn_map": str(source_turn_map),
		"source_turn_map_sha256": _sha256(source_turn_map),
		"detection_policy": {
			"mode": "conservative_no_speech_overlap_only",
			"speech_basis": "source_speaker_timeline_non_tag_turns",
			"event_basis": "explicit_non_speech_tags_plus_no_speaker_gaps",
			"reuse_gate": "reuse only when the interval has no speaker turn overlap; silence is not mixed back",
			"noise_threshold_db": noise_threshold_db,
			"min_silence_sec": min_silence_sec,
			"min_event_duration_sec": min_event_duration_sec,
		},
		"speech_ranges": [_round_range(start, end) for start, end in speech_ranges],
		"silence_ranges": [_round_range(start, end) for start, end in silence_ranges],
		"events": events,
		"summary": {
			"event_count": len(events),
			"reusable_event_count": sum(1 for event in events if event.get("reuse_source_audio")),
			"reusable_duration_sec": round(sum(float(event["duration_sec"]) for event in events if event.get("reuse_source_audio")), 3),
			"speech_range_count": len(speech_ranges),
			"silence_range_count": len(silence_ranges),
		},
	}
	_write_json(output_path, result)
	return result


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build conservative source audio background event census.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--source-audio", type=Path)
	parser.add_argument("--source-turn-map", type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--min-event-duration-sec", type=float, default=0.5)
	parser.add_argument("--noise-threshold-db", default="-45dB")
	parser.add_argument("--min-silence-sec", type=float, default=0.5)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	result = build_source_audio_event_census(
		run_dir=args.run_dir,
		source_audio=args.source_audio,
		source_turn_map=args.source_turn_map,
		output_path=args.output,
		min_event_duration_sec=args.min_event_duration_sec,
		noise_threshold_db=args.noise_threshold_db,
		min_silence_sec=args.min_silence_sec,
	)
	print(json.dumps({
		"source_audio_events": str((args.output or args.run_dir / "02a-source-audio-events/source_audio_events.json").resolve()),
		"summary": result["summary"],
	}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
