#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


FAIL_FLAGS = {
	"long_chapter_tail_silence",
	"chapter_rewrite_recommended",
	"chapter_tempo_over_preferred_limit",
}
WARN_FLAGS = {
	"distributed_gap_padding",
	"large_distributed_gap",
	"chapter_slowdown_applied",
}
MAX_TAIL_SILENCE_SEC = 5.0
WARN_TAIL_SILENCE_SEC = 2.0
MAX_CONTINUOUS_SILENCE_SEC = 2.0
MAX_ALIGNED_SILENCE_SEC = 4.0
WARN_DISTRIBUTED_EXTRA_GAP_SEC = 1.2
MAX_DISTRIBUTED_EXTRA_GAP_SEC = 2.5
MIN_SEGMENT_AUDIO_SEC = 0.25
MIN_HARD_TEMPO = 0.75
MAX_HARD_TEMPO = 1.2
MIN_SOFT_TEMPO = 0.82
MAX_SOFT_TEMPO = 1.08
MAX_VOLUME_DBFS = -0.1
MIN_MEAN_VOLUME_DBFS = -36.0
MAX_MEAN_VOLUME_DBFS = -10.0
SUPPORTED_SCHEMA_VERSIONS = {
	"continuous-clone-voiceover.v1",
	"segment-aligned-clone-voiceover.v1",
}


def main() -> int:
	args = _parse_args()
	_require_command("ffprobe")
	_require_command("ffmpeg")
	manifest_path = args.manifest.expanduser().resolve()
	manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
	result = evaluate_manifest(manifest_path, manifest, args)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["passed"] else 1


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Evaluate generated Chinese voiceover audio manifest and files.")
	parser.add_argument("manifest", type=Path)
	parser.add_argument("--silence-threshold-db", type=float, default=-45.0)
	parser.add_argument("--continuous-silence-sec", type=float, default=1.0)
	parser.add_argument("--aligned-silence-sec", type=float, default=1.5)
	parser.add_argument("--require-aligned", action="store_true", help="Fail if chapter_aligned output is missing.")
	return parser.parse_args()


def evaluate_manifest(manifest_path: Path, manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
	errors: list[str] = []
	warnings: list[str] = []
	schema_version = manifest.get("schema_version")
	is_segment_aligned = schema_version == "segment-aligned-clone-voiceover.v1"
	if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
		errors.append(f"unsupported or missing schema_version: {schema_version!r}")

	continuous_path = _audio_path_from_manifest(
		manifest_path,
		manifest,
		label="continuous",
		candidates=[
			"outputs.continuous.audio_path",
			"outputs.continuous.wav_path",
			"outputs.continuous.m4a_path",
			"continuous_wav_path",
			"continuous_m4a_path",
			"final_wav_path",
			"final_m4a_path",
		],
		errors=errors,
		warnings=warnings,
		required=True,
	)
	aligned_path = _audio_path_from_manifest(
		manifest_path,
		manifest,
		label="chapter_aligned",
		candidates=[
			"outputs.chapter_aligned.audio_path",
			"outputs.chapter_aligned.wav_path",
			"outputs.chapter_aligned.m4a_path",
			"chapter_aligned_wav_path",
			"chapter_aligned_m4a_path",
		],
		errors=errors,
		warnings=warnings,
		required=args.require_aligned,
	)
	manifest_files = {
		"continuous_audio_path": str(continuous_path) if continuous_path else None,
		"chapter_aligned_audio_path": str(aligned_path) if aligned_path else None,
	}

	durations: dict[str, float] = {}
	volume: dict[str, dict[str, float]] = {}
	silence: dict[str, dict[str, Any]] = {}

	if continuous_path and continuous_path.exists():
		durations["continuous_sec"] = _probe_duration(continuous_path)
		volume["continuous"] = _volume_detect(continuous_path)
		silence["continuous"] = _silence_detect(
			continuous_path,
			threshold_db=args.silence_threshold_db,
			min_duration_sec=args.continuous_silence_sec,
		)
		_check_volume("continuous", volume["continuous"], errors, warnings)
		if silence["continuous"]["max_silence_sec"] > MAX_CONTINUOUS_SILENCE_SEC:
			message = f"continuous has silence {silence['continuous']['max_silence_sec']:.3f}s > {MAX_CONTINUOUS_SILENCE_SEC:.3f}s"
			if is_segment_aligned:
				warnings.append(message)
			else:
				errors.append(message)

	if aligned_path and aligned_path.exists():
		durations["aligned_sec"] = _probe_duration(aligned_path)
		volume["aligned"] = _volume_detect(aligned_path)
		silence["aligned"] = _silence_detect(
			aligned_path,
			threshold_db=args.silence_threshold_db,
			min_duration_sec=args.aligned_silence_sec,
		)
		_check_volume("aligned", volume["aligned"], errors, warnings)
		if silence["aligned"]["max_silence_sec"] > MAX_ALIGNED_SILENCE_SEC:
			errors.append(f"aligned has silence {silence['aligned']['max_silence_sec']:.3f}s > {MAX_ALIGNED_SILENCE_SEC:.3f}s")

	timeline_duration = _as_float(manifest.get("timeline_duration_sec"))
	if timeline_duration is not None and "aligned_sec" in durations and abs(timeline_duration - durations["aligned_sec"]) > 1.0:
		errors.append(
			f"aligned duration {durations['aligned_sec']:.3f}s differs from manifest timeline {timeline_duration:.3f}s by >1s"
		)

	segment_issues = _evaluate_segments(manifest_path, manifest, errors, warnings)
	segment_pass_summary = _evaluate_segment_pass_summary(manifest, errors, warnings)
	chapter_issues = _evaluate_chapters(manifest_path, manifest, aligned_total_sec=durations.get("aligned_sec"), errors=errors, warnings=warnings)
	review_flags = _collect_review_flags(manifest)
	for flag, count in sorted(review_flags.items()):
		if flag in FAIL_FLAGS:
			errors.append(f"review flag {flag} appears {count} time(s)")
		elif flag not in WARN_FLAGS:
			warnings.append(f"unclassified review flag {flag} appears {count} time(s)")

	return {
		"schema_version": "voiceover-audio-evaluation.v1",
		"manifest_path": str(manifest_path),
		"video_id": manifest.get("video_id"),
		"segment_count": manifest.get("segment_count"),
		"chapter_count": manifest.get("chapter_count"),
		"files": manifest_files,
		"durations": durations,
		"volume": volume,
		"silence": silence,
		"review_flags": review_flags,
		"segment_pass_summary": segment_pass_summary,
		"segment_issues": segment_issues,
		"chapter_issues": chapter_issues,
		"errors": errors,
		"warnings": warnings,
		"passed": not errors,
	}


def _audio_path_from_manifest(
	manifest_path: Path,
	manifest: dict[str, Any],
	*,
	label: str,
		candidates: list[str],
		errors: list[str],
		warnings: list[str],
		required: bool,
) -> Path | None:
	seen_missing: list[tuple[str, Path]] = []
	for candidate in candidates:
		value = _nested_get(manifest, candidate)
		if not isinstance(value, str) or not value:
			continue
		path = _resolve_manifest_path(manifest_path, value)
		if not path.exists():
			seen_missing.append((candidate, path))
			continue
		return path
	for candidate, path in seen_missing:
		warnings.append(f"{label} candidate path missing from {candidate}: {path}")
	if seen_missing:
		if required:
			errors.append(f"{label} has path fields but none exists")
		else:
			warnings.append(f"{label} has path fields but none exists")
		return seen_missing[0][1]
	message = f"manifest missing {label} audio path; checked {', '.join(candidates)}"
	if required:
		errors.append(message)
	else:
		warnings.append(message)
	return None


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
	value: Any = data
	for part in dotted_key.split("."):
		if not isinstance(value, dict) or part not in value:
			return None
		value = value[part]
	return value


def _resolve_manifest_path(manifest_path: Path, value: str) -> Path:
	path = Path(value).expanduser()
	if path.is_absolute():
		return path
	return manifest_path.parent / path


def _path_from_manifest(manifest_path: Path, manifest: dict[str, Any], key: str, errors: list[str]) -> Path | None:
	value = _nested_get(manifest, key)
	if not isinstance(value, str) or not value:
		errors.append(f"manifest missing {key}")
		return None
	path = _resolve_manifest_path(manifest_path, value)
	if not path.exists():
		errors.append(f"{key} does not exist: {path}")
		return path
	return path


def _evaluate_segment_pass_summary(
	manifest: dict[str, Any],
	errors: list[str],
	warnings: list[str],
) -> dict[str, Any] | None:
	summary = manifest.get("summary")
	if not isinstance(summary, dict):
		return None
	pass_rate = _as_float(summary.get("segment_pass_rate"))
	min_pass_rate = _as_float(summary.get("min_segment_pass_rate")) or 0.90
	decision = str(summary.get("decision") or "")
	if pass_rate is None:
		return None
	output = {
		"decision": decision,
		"segment_pass_rate": pass_rate,
		"min_segment_pass_rate": min_pass_rate,
		"failed_segment_ids": summary.get("failed_segment_ids") or [],
		"tolerated_failed_segment_ids": summary.get("tolerated_failed_segment_ids") or [],
	}
	if pass_rate < min_pass_rate or decision == "FAIL":
		errors.append(f"segment_pass_rate {pass_rate:.3f} < min_segment_pass_rate {min_pass_rate:.3f}")
	elif output["failed_segment_ids"]:
		warnings.append(
			f"segment_pass_rate {pass_rate:.3f} passes with tolerated failed segments: {len(output['failed_segment_ids'])}"
		)
	return output


def _evaluate_segments(manifest_path: Path, manifest: dict[str, Any], errors: list[str], warnings: list[str]) -> list[dict[str, Any]]:
	issues: list[dict[str, Any]] = []
	segments = manifest.get("segments")
	segment_count = manifest.get("segment_count")
	if not isinstance(segments, list):
		errors.append("manifest.segments is missing or invalid")
		return issues
	if isinstance(segment_count, int) and segment_count != len(segments):
		errors.append(f"manifest.segment_count={segment_count} but len(segments)={len(segments)}")
	for index, segment in enumerate(segments):
		if not isinstance(segment, dict):
			errors.append(f"segments[{index}] is not an object")
			continue
		segment_id = str(segment.get("segment_id") or f"segments[{index}]")
		draft_value = segment.get("draft_audio_path")
		item: dict[str, Any] = {"segment_id": segment_id}
		if not isinstance(draft_value, str) or not draft_value:
			errors.append(f"{segment_id} missing draft_audio_path")
			issues.append(item)
			continue
		draft_path = _resolve_manifest_path(manifest_path, draft_value)
		item["draft_audio_path"] = str(draft_path)
		if not draft_path.exists():
			errors.append(f"{segment_id} draft audio missing: {draft_path}")
			issues.append(item)
			continue
		duration = _probe_duration(draft_path)
		item["actual_duration_sec"] = round(duration, 3)
		recorded_duration = _as_float(segment.get("tts_duration_sec"))
		if duration < MIN_SEGMENT_AUDIO_SEC:
			errors.append(f"{segment_id} draft audio duration {duration:.3f}s is too short")
			issues.append(item)
		if recorded_duration is not None and abs(recorded_duration - duration) > 1.0:
			warnings.append(f"{segment_id} recorded tts_duration_sec differs from actual audio by >1s")
			issues.append(item)
	return issues


def _evaluate_chapters(
	manifest_path: Path,
	manifest: dict[str, Any],
	*,
	aligned_total_sec: float | None,
	errors: list[str],
	warnings: list[str],
) -> list[dict[str, Any]]:
	issues: list[dict[str, Any]] = []
	chapters = manifest.get("chapters")
	chapter_count = manifest.get("chapter_count")
	if chapters is None:
		return issues
	if not isinstance(chapters, list):
		warnings.append("manifest.chapters is invalid")
		return issues
	if isinstance(chapter_count, int) and chapter_count != len(chapters):
		errors.append(f"manifest.chapter_count={chapter_count} but len(chapters)={len(chapters)}")
	aligned_duration_sum = 0.0
	has_all_aligned_duration = True
	for chapter in chapters:
		if not isinstance(chapter, dict):
			continue
		chapter_id = str(chapter.get("chapter_id") or "unknown")
		tail = _as_float(chapter.get("tail_silence_sec")) or 0.0
		extra_gap = _as_float(chapter.get("distributed_extra_gap_sec")) or 0.0
		tempo = _as_float(chapter.get("tempo_factor")) or 1.0
		target = _as_float(chapter.get("target_duration_sec"))
		aligned_duration = _as_float(chapter.get("aligned_duration_sec"))
		item = {
			"chapter_id": chapter_id,
			"tail_silence_sec": tail,
			"distributed_extra_gap_sec": extra_gap,
			"tempo_factor": tempo,
			"target_duration_sec": target,
			"aligned_duration_sec": aligned_duration,
			"review_flags": chapter.get("review_flags") or [],
		}
		if tail > MAX_TAIL_SILENCE_SEC:
			errors.append(f"{chapter_id} tail_silence_sec {tail:.3f}s > {MAX_TAIL_SILENCE_SEC:.3f}s")
			_record_issue(issues, item)
		elif tail > WARN_TAIL_SILENCE_SEC:
			warnings.append(f"{chapter_id} tail_silence_sec {tail:.3f}s > {WARN_TAIL_SILENCE_SEC:.3f}s")
			_record_issue(issues, item)
		if extra_gap > MAX_DISTRIBUTED_EXTRA_GAP_SEC:
			errors.append(f"{chapter_id} distributed_extra_gap_sec {extra_gap:.3f}s > {MAX_DISTRIBUTED_EXTRA_GAP_SEC:.3f}s")
			_record_issue(issues, item)
		elif extra_gap > WARN_DISTRIBUTED_EXTRA_GAP_SEC:
			warnings.append(f"{chapter_id} distributed_extra_gap_sec {extra_gap:.3f}s > {WARN_DISTRIBUTED_EXTRA_GAP_SEC:.3f}s")
			_record_issue(issues, item)
		elif extra_gap > 0:
			_record_issue(issues, item)
		if tempo < MIN_HARD_TEMPO:
			errors.append(f"{chapter_id} tempo_factor {tempo:.3f} is slower than hard floor {MIN_HARD_TEMPO:.3f}")
			_record_issue(issues, item)
		elif tempo < MIN_SOFT_TEMPO:
			warnings.append(f"{chapter_id} tempo_factor {tempo:.3f} is slower than preferred floor {MIN_SOFT_TEMPO:.3f}")
			_record_issue(issues, item)
		if tempo > MAX_HARD_TEMPO:
			errors.append(f"{chapter_id} tempo_factor {tempo:.3f} is faster than hard ceiling {MAX_HARD_TEMPO:.3f}")
			_record_issue(issues, item)
		elif tempo > MAX_SOFT_TEMPO:
			warnings.append(f"{chapter_id} tempo_factor {tempo:.3f} is faster than preferred ceiling {MAX_SOFT_TEMPO:.3f}")
			_record_issue(issues, item)
		if target is not None and aligned_duration is not None and abs(target - aligned_duration) > 0.75:
			errors.append(f"{chapter_id} aligned_duration_sec differs from target_duration_sec by >0.75s")
			_record_issue(issues, item)
		if aligned_duration is None:
			has_all_aligned_duration = False
		else:
			aligned_duration_sum += aligned_duration
		aligned_path_value = chapter.get("aligned_audio_path")
		if isinstance(aligned_path_value, str) and aligned_path_value:
			aligned_path = _resolve_manifest_path(manifest_path, aligned_path_value)
			if not aligned_path.exists():
				errors.append(f"{chapter_id} aligned_audio_path missing: {aligned_path}")
				_record_issue(issues, item)
			elif target is not None and abs(_probe_duration(aligned_path) - target) > 0.75:
				errors.append(f"{chapter_id} aligned audio file duration differs from target by >0.75s")
				_record_issue(issues, item)
	if aligned_total_sec is not None and has_all_aligned_duration and abs(aligned_duration_sum - aligned_total_sec) > 1.0:
		errors.append(
			f"sum(chapters[].aligned_duration_sec)={aligned_duration_sum:.3f}s differs from final aligned duration {aligned_total_sec:.3f}s by >1s"
		)
	return issues


def _record_issue(issues: list[dict[str, Any]], item: dict[str, Any]) -> None:
	chapter_id = item.get("chapter_id")
	if chapter_id is None:
		issues.append(item)
		return
	if not any(existing.get("chapter_id") == chapter_id for existing in issues):
		issues.append(item)


def _collect_review_flags(manifest: dict[str, Any]) -> dict[str, int]:
	summary = manifest.get("summary")
	if isinstance(summary, dict) and isinstance(summary.get("review_flags"), dict):
		return {str(key): int(value) for key, value in summary["review_flags"].items()}
	flags: dict[str, int] = {}
	chapters = manifest.get("chapters")
	if isinstance(chapters, list):
		for chapter in chapters:
			if not isinstance(chapter, dict):
				continue
			for flag in chapter.get("review_flags") or []:
				flags[str(flag)] = flags.get(str(flag), 0) + 1
	return flags


def _check_volume(label: str, volume: dict[str, float], errors: list[str], warnings: list[str]) -> None:
	max_volume = volume.get("max_volume_db")
	mean_volume = volume.get("mean_volume_db")
	if max_volume is not None and max_volume > MAX_VOLUME_DBFS:
		errors.append(f"{label} max_volume {max_volume:.1f} dBFS is too close to clipping")
	if mean_volume is not None and mean_volume < MIN_MEAN_VOLUME_DBFS:
		warnings.append(f"{label} mean_volume {mean_volume:.1f} dBFS is low; loudness normalization may be needed")
	if mean_volume is not None and mean_volume > MAX_MEAN_VOLUME_DBFS:
		warnings.append(f"{label} mean_volume {mean_volume:.1f} dBFS is high")


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
		capture_output=True,
		text=True,
	)
	return float(result.stdout.strip())


def _volume_detect(path: Path) -> dict[str, float]:
	result = subprocess.run(
		["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
		check=True,
		capture_output=True,
		text=True,
	)
	output = result.stderr
	mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", output)
	max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", output)
	return {
		"mean_volume_db": float(mean_match.group(1)) if mean_match else float("nan"),
		"max_volume_db": float(max_match.group(1)) if max_match else float("nan"),
	}


def _silence_detect(path: Path, *, threshold_db: float, min_duration_sec: float) -> dict[str, Any]:
	result = subprocess.run(
		[
			"ffmpeg",
			"-hide_banner",
			"-nostats",
			"-i",
			str(path),
			"-af",
			f"silencedetect=n={threshold_db}dB:d={min_duration_sec}",
			"-f",
			"null",
			"-",
		],
		check=True,
		capture_output=True,
		text=True,
	)
	events: list[dict[str, float]] = []
	current_start: float | None = None
	for line in result.stderr.splitlines():
		start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
		if start_match:
			current_start = float(start_match.group(1))
			continue
		end_match = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
		if end_match and current_start is not None:
			events.append(
				{
					"start_sec": current_start,
					"end_sec": float(end_match.group(1)),
					"duration_sec": float(end_match.group(2)),
				}
			)
			current_start = None
	max_silence = max((event["duration_sec"] for event in events), default=0.0)
	return {
		"threshold_db": threshold_db,
		"min_duration_sec": min_duration_sec,
		"event_count": len(events),
		"max_silence_sec": round(max_silence, 3),
		"events": events[:20],
	}


def _as_float(value: Any) -> float | None:
	if isinstance(value, int | float):
		return float(value)
	return None


def _require_command(command: str) -> None:
	if shutil.which(command) is None:
		raise RuntimeError(f"required command not found: {command}")


if __name__ == "__main__":
	raise SystemExit(main())
