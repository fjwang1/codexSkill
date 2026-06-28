#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


OUTPUT_DIRNAME = "04-source-dialogue-turn-map"
OUTPUT_NAME = "source_dialogue_turn_map.active.json"
REPORT_NAME = "source_dialogue_turn_map.report.md"


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


def _resolve_existing(run_dir: Path, candidates: list[str], label: str) -> Path:
	for candidate in candidates:
		path = (run_dir / candidate).resolve()
		if path.exists():
			return path
	raise AssertionError(f"Missing {label}. Checked: {[str(run_dir / item) for item in candidates]}")


def _source_segment_key(segment: dict[str, Any]) -> int:
	value = segment.get("segment_index", segment.get("source_segment_index", segment.get("source_turn_index")))
	assert value is not None, f"Source segment lacks segment_index/source_turn_index: {segment}"
	return int(value)


def _source_segment_start(segment: dict[str, Any]) -> float:
	return float(segment["source_start_sec"])


def _source_segment_end(segment: dict[str, Any]) -> float:
	return float(segment["source_end_sec"])


def _source_segment_speaker(segment: dict[str, Any]) -> str:
	return str(segment.get("speaker") or "").strip()


def _source_segment_text(segment: dict[str, Any]) -> str:
	return str(segment.get("source_text") or segment.get("text") or "")


def _build_visual_segment_groups(
	source_segments: list[dict[str, Any]],
	grouped_audio_turns: dict[int, list[dict[str, Any]]],
	max_same_speaker_gap_sec: float = 0.75,
) -> list[dict[str, Any]]:
	ordered = sorted(source_segments, key=lambda item: (_source_segment_start(item), _source_segment_end(item), _source_segment_key(item)))
	groups: list[dict[str, Any]] = []
	current: dict[str, Any] | None = None
	for segment in ordered:
		segment_key = _source_segment_key(segment)
		segment_start = _source_segment_start(segment)
		segment_end = _source_segment_end(segment)
		speaker = _source_segment_speaker(segment)
		if segment_end <= segment_start:
			continue
		can_merge = (
			current is not None
			and speaker
			and speaker == current.get("speaker")
			and segment_start <= float(current["source_end_sec"]) + max_same_speaker_gap_sec
		)
		if not can_merge:
			if current is not None:
				groups.append(current)
			current = {
				"source_segment_indices": [segment_key],
				"speaker": speaker,
				"source_start_sec": segment_start,
				"source_end_sec": segment_end,
				"source_texts": [_source_segment_text(segment)] if _source_segment_text(segment) else [],
				"audio_parts": list(grouped_audio_turns.get(segment_key) or []),
			}
			continue
		assert current is not None
		current["source_segment_indices"].append(segment_key)
		current["source_end_sec"] = max(float(current["source_end_sec"]), segment_end)
		text = _source_segment_text(segment)
		if text:
			current["source_texts"].append(text)
		current["audio_parts"].extend(grouped_audio_turns.get(segment_key) or [])
	if current is not None:
		groups.append(current)
	for group in groups:
		group["audio_parts"].sort(key=lambda item: int(item["turn_index"]))
	return groups


def _timeline_visual_ends(turns: list[dict[str, Any]], manifest_duration: float | None) -> dict[int, float]:
	ordered = sorted(turns, key=lambda item: int(item["turn_index"]))
	visual_ends: dict[int, float] = {}
	for index, turn in enumerate(ordered):
		turn_index = int(turn["turn_index"])
		end = float(turn["end_sec"])
		if index + 1 < len(ordered):
			visual_end = max(end, float(ordered[index + 1]["start_sec"]))
		elif manifest_duration is not None:
			visual_end = max(end, manifest_duration)
		else:
			visual_end = end
		visual_ends[turn_index] = visual_end
	return visual_ends


def _audio_turn_target_duration(
	audio_manifest_turn: dict[str, Any],
	timeline_by_index: dict[int, dict[str, Any]],
	visual_end_by_index: dict[int, float],
) -> float:
	turn_index = int(audio_manifest_turn["turn_index"])
	timeline_turn = timeline_by_index.get(turn_index)
	if timeline_turn is None:
		return max(1.0, len(str(audio_manifest_turn.get("text") or "")) / 8.0)
	start = float(timeline_turn["start_sec"])
	visual_end = visual_end_by_index[turn_index]
	return max(0.05, visual_end - start)


def _group_audio_manifest_turns(audio_manifest: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
	grouped: dict[int, list[dict[str, Any]]] = {}
	for turn in audio_manifest.get("turns") or []:
		if not isinstance(turn, dict) or turn.get("source_turn_index") is None:
			continue
		grouped.setdefault(int(turn["source_turn_index"]), []).append(turn)
	for turns in grouped.values():
		turns.sort(key=lambda item: int(item["turn_index"]))
	return grouped


def build_source_dialogue_turn_map(
	run_dir: Path,
	source_translation: Path | None = None,
	audio_manifest_path: Path | None = None,
	turn_audio_timeline_path: Path | None = None,
	output_path: Path | None = None,
) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	source_translation = source_translation or _resolve_existing(
		run_dir,
		[
			"03b-mainland-publish-safety/source_transcript.zh.safe.json",
			"03-source-translation/source_transcript.zh.json",
		],
		"current source translation",
	)
	audio_manifest_path = audio_manifest_path or _resolve_existing(
		run_dir,
		[
			"audio/audio_manifest.json",
			"05-vibevoice-chunks/audio_manifest.json",
		],
		"current audio manifest",
	)
	turn_audio_timeline_path = turn_audio_timeline_path or _resolve_existing(
		run_dir,
		[
			"06c-audio-timeline-alignment/turn_audio_timeline.json",
			"audio/dialogue_timeline.json",
		],
		"current turn audio timeline",
	)
	output_path = output_path or run_dir / OUTPUT_DIRNAME / OUTPUT_NAME

	source_data = _read_json(source_translation)
	audio_manifest = _read_json(audio_manifest_path)
	turn_audio_timeline = _read_json(turn_audio_timeline_path)
	source_segments = list(source_data.get("segments") or [])
	audio_manifest_turns = list(audio_manifest.get("turns") or [])
	timeline_turns = list(turn_audio_timeline.get("turns") or [])
	assert source_segments, f"No source segments found in {source_translation}"
	assert audio_manifest_turns, f"No audio manifest turns found in {audio_manifest_path}"
	assert timeline_turns, f"No turn audio timeline turns found in {turn_audio_timeline_path}"

	segments_by_index = {_source_segment_key(segment): segment for segment in source_segments}
	timeline_by_index = {int(turn["turn_index"]): turn for turn in timeline_turns}
	manifest_duration = turn_audio_timeline.get("duration_sec")
	visual_end_by_index = _timeline_visual_ends(timeline_turns, float(manifest_duration) if manifest_duration is not None else None)
	grouped_audio_turns = _group_audio_manifest_turns(audio_manifest)
	visual_segment_groups = _build_visual_segment_groups(source_segments, grouped_audio_turns)

	mapped_turns: list[dict[str, Any]] = []
	warnings: list[str] = []
	dropped_source_tail_sec = 0.0
	extension_expected_sec = 0.0
	for group in visual_segment_groups:
		parts = list(group.get("audio_parts") or [])
		if not parts:
			continue
		source_indices = [int(item) for item in group["source_segment_indices"]]
		segment_start = float(group["source_start_sec"])
		segment_end = float(group["source_end_sec"])
		source_duration = max(0.0, segment_end - segment_start)
		if source_duration <= 0:
			warnings.append(f"invalid source segment range for source_turn_indices {source_indices}")
			continue
		target_durations = [
			_audio_turn_target_duration(part, timeline_by_index, visual_end_by_index)
			for part in parts
		]
		total_target_duration = sum(target_durations)
		if total_target_duration <= source_duration:
			source_durations = list(target_durations)
			dropped_source_tail_sec += source_duration - total_target_duration
		else:
			source_durations = [
				source_duration * (duration / total_target_duration)
				for duration in target_durations
			]
			extension_expected_sec += total_target_duration - source_duration

		cursor = segment_start
		for part_index, (part, source_duration_for_part, target_duration) in enumerate(zip(parts, source_durations, target_durations), start=1):
			part_end = min(segment_end, cursor + source_duration_for_part)
			if part_end <= cursor:
				part_end = min(segment_end, cursor + 0.05)
			audio_turn_index = int(part["turn_index"])
			audio_turn_id = f"turn_{audio_turn_index:04d}"
			timeline_turn = timeline_by_index.get(audio_turn_index)
			source_index = int(part.get("source_turn_index") or source_indices[0])
			source_segment = segments_by_index.get(source_index) or {}
			mapped_turns.append({
				"turn_id": audio_turn_id,
				"turn_index": audio_turn_index,
				"speaker": str(part.get("speaker") or source_segment.get("speaker") or ""),
				"source_start_sec": round(cursor, 3),
				"source_end_sec": round(part_end, 3),
				"source_text": " ".join(str(item) for item in group.get("source_texts") or [])[:500],
				"source_segment_index": source_index,
				"source_segment_indices": source_indices,
				"source_part_index": int(part.get("source_part_index") or part_index),
				"source_part_count": int(part.get("source_part_count") or len(parts)),
				"audio_turn_id": audio_turn_id,
				"audio_turn_ids": [audio_turn_id],
				"audio_turn_index": audio_turn_index,
				"audio_start_sec": round(float(timeline_turn["start_sec"]), 3) if timeline_turn is not None else None,
				"audio_end_sec": round(float(timeline_turn["end_sec"]), 3) if timeline_turn is not None else None,
				"target_visual_duration_sec": round(target_duration, 3),
				"explicit_audio_turn_binding": True,
				"map_method": "source_segment_fit_to_current_audio_visual_turn_duration",
			})
			cursor = part_end
	for source_index in sorted(set(grouped_audio_turns) - set(segments_by_index)):
		warnings.append(f"missing source segment for source_turn_index {source_index}")

	mapped_turns.sort(key=lambda item: int(item["turn_index"]))
	expected_turn_indices = {int(turn["turn_index"]) for turn in audio_manifest_turns if turn.get("source_turn_index") is not None}
	mapped_turn_indices = {int(turn["turn_index"]) for turn in mapped_turns}
	missing_audio_bindings = sorted(expected_turn_indices - mapped_turn_indices)
	if missing_audio_bindings:
		warnings.append(f"missing audio turn bindings: {missing_audio_bindings[:20]}")
	status = "PASS" if not warnings and len(mapped_turns) == len(expected_turn_indices) else "WARN"
	return {
		"schema_version": "worldview-china-source-dialogue-turn-map.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"status": status,
		"method": "episode_audio_manifest_bound_source_segment_visual_duration_fit",
		"source_translation": str(source_translation),
		"source_translation_sha256": _sha256(source_translation),
		"audio_manifest": str(audio_manifest_path),
		"audio_manifest_sha256": _sha256(audio_manifest_path),
		"turn_audio_timeline": str(turn_audio_timeline_path),
		"turn_audio_timeline_sha256": _sha256(turn_audio_timeline_path),
		"source_turn_count": len(source_segments),
		"source_visual_group_count": len(visual_segment_groups),
		"audio_turn_count": len(audio_manifest_turns),
		"mapped_turn_count": len(mapped_turns),
		"dropped_source_tail_sec": round(dropped_source_tail_sec, 3),
		"extension_expected_sec": round(extension_expected_sec, 3),
		"warnings": warnings,
		"turns": mapped_turns,
	}


def _write_report(path: Path, manifest: dict[str, Any]) -> None:
	lines = [
		"# Source Dialogue Turn Map",
		"",
		f"- status: {manifest['status']}",
		f"- method: {manifest['method']}",
		f"- source_turn_count: {manifest['source_turn_count']}",
		f"- audio_turn_count: {manifest['audio_turn_count']}",
		f"- mapped_turn_count: {manifest['mapped_turn_count']}",
		f"- dropped_source_tail_sec: {manifest['dropped_source_tail_sec']}",
		f"- extension_expected_sec: {manifest['extension_expected_sec']}",
		f"- warnings: {len(manifest['warnings'])}",
	]
	if manifest["warnings"]:
		lines.extend(["", "## Warnings", ""])
		lines.extend(f"- {warning}" for warning in manifest["warnings"])
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build an episode source dialogue turn map bound to the current Chinese audio turns.")
	parser.add_argument("--run-dir", type=Path, required=True)
	parser.add_argument("--source-translation", type=Path)
	parser.add_argument("--audio-manifest", type=Path)
	parser.add_argument("--turn-audio-timeline", type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--force", action="store_true")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	output_path = (args.output or args.run_dir / OUTPUT_DIRNAME / OUTPUT_NAME).resolve()
	if output_path.exists() and not args.force:
		raise AssertionError(f"Output exists; pass --force to overwrite: {output_path}")
	manifest = build_source_dialogue_turn_map(
		args.run_dir,
		source_translation=args.source_translation,
		audio_manifest_path=args.audio_manifest,
		turn_audio_timeline_path=args.turn_audio_timeline,
		output_path=output_path,
	)
	_write_json(output_path, manifest)
	_write_report(output_path.parent / REPORT_NAME, manifest)
	print(json.dumps({
		"status": manifest["status"],
		"output": str(output_path),
		"mapped_turn_count": manifest["mapped_turn_count"],
		"warnings": manifest["warnings"],
	}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
