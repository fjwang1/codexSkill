#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from statistics import mean, median
from typing import Any


DEFAULT_ROOTS = [
	Path("/Volumes/GT34/Generated"),
	Path("/Volumes/GT34/world_and_china_podcast"),
]


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _normalize_text(value: Any) -> str:
	return re.sub(r"\s+", "", str(value or "")).strip()


def _chars_from_manifest(manifest: dict[str, Any]) -> int:
	turns = manifest.get("turns")
	if isinstance(turns, list) and turns:
		return sum(len(_normalize_text(turn.get("tts_text") or turn.get("text") or turn.get("display_text"))) for turn in turns if isinstance(turn, dict))
	chunks = manifest.get("chunks")
	if isinstance(chunks, list) and chunks:
		total = 0
		for chunk in chunks:
			if not isinstance(chunk, dict):
				continue
			if chunk.get("display_characters") is not None:
				total += int(chunk["display_characters"])
			else:
				total += len(_normalize_text(chunk.get("text") or chunk.get("tts_text") or chunk.get("display_text")))
		return total
	return int(manifest.get("display_characters") or manifest.get("char_count") or manifest.get("total_display_chars") or 0)


def _duration_from_manifest(path: Path, manifest: dict[str, Any]) -> float:
	duration = manifest.get("duration_sec") or manifest.get("audio_duration_sec")
	if duration:
		return float(duration)
	for key in ("final_audio", "audio_path", "output_audio", "wav_path"):
		value = manifest.get(key)
		if not value:
			continue
		audio = Path(str(value))
		if not audio.is_absolute():
			audio = path.parent / audio
		if audio.exists():
			return _probe_duration(audio)
	return 0.0


def _probe_duration(path: Path) -> float:
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


def _kind_for_path(path: Path) -> str:
	parts = path.parts
	if "playback" in str(path).lower():
		return "skip"
	if "chunks" in parts or any(part.startswith("chunk_") for part in parts):
		return "chunk"
	if path.parent.name in {"audio", "05-vibevoice-chunks"}:
		return "aggregate"
	return "other"


def _percentile(values: list[float], q: float) -> float:
	assert values
	ordered = sorted(values)
	if len(ordered) == 1:
		return ordered[0]
	position = (len(ordered) - 1) * q
	lower = int(position)
	upper = min(lower + 1, len(ordered) - 1)
	weight = position - lower
	return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
	values = [float(record["chars_per_minute"]) for record in records]
	if not values:
		return {"n": 0}
	return {
		"n": len(values),
		"min": round(min(values), 3),
		"p10": round(_percentile(values, 0.10), 3),
		"p25": round(_percentile(values, 0.25), 3),
		"median": round(median(values), 3),
		"mean": round(mean(values), 3),
		"p75": round(_percentile(values, 0.75), 3),
		"p90": round(_percentile(values, 0.90), 3),
		"max": round(max(values), 3),
	}


def collect_records(roots: list[Path], min_duration_sec: float, min_cpm: float, max_cpm: float) -> dict[str, Any]:
	records: list[dict[str, Any]] = []
	for root in roots:
		if not root.exists():
			continue
		for path in root.rglob("audio_manifest.json"):
			kind = _kind_for_path(path)
			if kind == "skip":
				continue
			try:
				manifest = _read_json(path)
				chars = _chars_from_manifest(manifest)
				duration = _duration_from_manifest(path, manifest)
			except Exception:
				continue
			if duration < min_duration_sec or chars <= 0:
				continue
			cpm = chars / (duration / 60.0)
			if not (min_cpm <= cpm <= max_cpm):
				continue
			records.append({
				"kind": kind,
				"path": str(path),
				"chars": chars,
				"duration_sec": round(duration, 3),
				"duration_min": round(duration / 60.0, 3),
				"chars_per_minute": round(cpm, 3),
			})
	records.sort(key=lambda record: (record["kind"], record["path"]))
	aggregate = [record for record in records if record["kind"] == "aggregate"]
	chunks = [record for record in records if record["kind"] == "chunk"]
	others = [record for record in records if record["kind"] == "other"]
	return {
		"schema_version": "worldview-china-vibevoice-cpm-calibration.v1",
		"roots": [str(root) for root in roots],
		"filters": {
			"min_duration_sec": min_duration_sec,
			"min_cpm": min_cpm,
			"max_cpm": max_cpm,
		},
		"summaries": {
			"aggregate": _summary(aggregate),
			"chunk": _summary(chunks),
			"other": _summary(others),
			"all": _summary(records),
		},
		"records": records,
	}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Estimate normalized Chinese characters per minute from local VibeVoice audio manifests.")
	parser.add_argument("--root", action="append", type=Path, dest="roots", help="Root directory to scan. May be repeated.")
	parser.add_argument("--min-duration-sec", type=float, default=10.0)
	parser.add_argument("--min-cpm", type=float, default=60.0)
	parser.add_argument("--max-cpm", type=float, default=500.0)
	parser.add_argument("--json-out", type=Path, help="Optional path to write the full calibration JSON.")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	roots = [path.expanduser().resolve() for path in (args.roots or DEFAULT_ROOTS)]
	result = collect_records(roots, args.min_duration_sec, args.min_cpm, args.max_cpm)
	if args.json_out:
		args.json_out.parent.mkdir(parents=True, exist_ok=True)
		args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	print(json.dumps({
		"roots": result["roots"],
		"summaries": result["summaries"],
		"record_count": len(result["records"]),
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
