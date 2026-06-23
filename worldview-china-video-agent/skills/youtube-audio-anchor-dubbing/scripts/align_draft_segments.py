from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def main() -> None:
	args = _parse_args()
	segments_path = args.segments.expanduser().resolve()
	draft_dir = args.draft_dir.expanduser().resolve()
	tts_manifest_path = args.tts_manifest.expanduser().resolve()
	output_dir = args.output_dir.expanduser().resolve()

	_require_file(segments_path)
	_require_dir(draft_dir)
	_require_file(tts_manifest_path)
	_require_command("ffmpeg")
	_require_command("ffprobe")

	payload = json.loads(segments_path.read_text(encoding="utf-8"))
	tts_manifest = json.loads(tts_manifest_path.read_text(encoding="utf-8"))
	segments = payload.get("segments")
	if not isinstance(segments, list) or not segments:
		raise ValueError("segments JSON must contain a non-empty `segments` list.")
	_assert_voice_clone_manifest(tts_manifest)
	_assert_monotonic_segments(segments)

	output_dir.mkdir(parents=True, exist_ok=True)
	aligned_dir = output_dir / "aligned-segments"
	gap_dir = output_dir / "timeline-gaps"
	aligned_dir.mkdir(parents=True, exist_ok=True)
	gap_dir.mkdir(parents=True, exist_ok=True)

	manifest_segments: list[dict[str, Any]] = []
	timeline_gaps: list[dict[str, Any]] = []
	chunks: list[Path] = []
	failures: list[dict[str, Any]] = []
	previous_end_sec = 0.0

	draft_by_id = _draft_audio_by_segment_id(tts_manifest)
	for index, segment in enumerate(segments, start=1):
		segment_id = str(segment["segment_id"])
		start_sec = _segment_start_sec(segment)
		end_sec = _segment_end_sec(segment)
		target_sec = float(segment.get("target_duration_sec") or (end_sec - start_sec))
		if not math.isclose(target_sec, end_sec - start_sec, abs_tol=0.05):
			raise ValueError(f"{segment_id} target_duration_sec does not match start/end.")

		if start_sec > previous_end_sec + 0.05:
			gap_sec = start_sec - previous_end_sec
			gap_wav = gap_dir / f"gap_before_{segment_id}.wav"
			if args.force or not gap_wav.exists():
				_make_silence(gap_wav, gap_sec)
			chunks.append(gap_wav)
			timeline_gaps.append(
				{
					"before_segment_id": segment_id,
					"start_sec": round(previous_end_sec, 3),
					"end_sec": round(start_sec, 3),
					"duration_sec": round(gap_sec, 3),
					"audio_path": str(gap_wav),
				}
			)

		draft_wav = _resolve_draft_wav(segment_id, draft_dir, draft_by_id)
		actual_sec = _probe_duration(draft_wav)
		plan = _alignment_plan(
			segment=segment,
			actual_sec=actual_sec,
			target_sec=target_sec,
			max_auto_tempo=args.max_auto_tempo,
			must_align_min_coverage=args.must_align_min_coverage,
			normal_min_coverage=args.normal_min_coverage,
			max_tail_silence_sec=args.max_tail_silence_sec,
		)
		aligned_wav = aligned_dir / f"{segment_id}.wav"
		if args.force or not aligned_wav.exists():
			_align_audio(
				input_wav=draft_wav,
				output_wav=aligned_wav,
				target_sec=target_sec,
				tempo_factor=plan["tempo_factor"],
			)
		aligned_sec = _probe_duration(aligned_wav)
		chunks.append(aligned_wav)
		previous_end_sec = end_sec

		result = {
			"segment_id": segment_id,
			"index": index,
			"sync_priority": str(segment.get("sync_priority") or "normal"),
			"start": segment["start"],
			"end": segment["end"],
			"start_sec": round(start_sec, 3),
			"end_sec": round(end_sec, 3),
			"target_duration_sec": round(target_sec, 3),
			"draft_audio_path": str(draft_wav),
			"aligned_audio_path": str(aligned_wav),
			"tts_duration_sec": round(actual_sec, 3),
			"aligned_duration_sec": round(aligned_sec, 3),
			"coverage_ratio": plan["coverage_ratio"],
			"tail_silence_sec": plan["tail_silence_sec"],
			"tempo_factor": plan["tempo_factor"],
			"sync_action": plan["sync_action"],
			"gate_flags": plan["gate_flags"],
			"pass": not plan["gate_flags"],
		}
		if segment.get("anchor_checks"):
			result["anchor_checks"] = segment.get("anchor_checks")
		manifest_segments.append(result)
		if plan["gate_flags"]:
			failures.append(result)
		_log(
			f"[{index:03d}/{len(segments):03d}] {segment_id} "
			f"target={target_sec:.2f}s tts={actual_sec:.2f}s "
			f"tail={plan['tail_silence_sec']:.2f}s tempo={plan['tempo_factor']:.3f} "
			f"flags={','.join(plan['gate_flags']) or 'ok'}"
		)

	if args.timeline_duration_sec and args.timeline_duration_sec > previous_end_sec + 0.05:
		tail_sec = args.timeline_duration_sec - previous_end_sec
		tail_wav = gap_dir / "tail_after_last_segment.wav"
		if args.force or not tail_wav.exists():
			_make_silence(tail_wav, tail_sec)
		chunks.append(tail_wav)
		timeline_gaps.append(
			{
				"after_last_segment": True,
				"start_sec": round(previous_end_sec, 3),
				"end_sec": round(args.timeline_duration_sec, 3),
				"duration_sec": round(tail_sec, 3),
				"audio_path": str(tail_wav),
			}
		)

	final_wav = output_dir / "final_voiceover.segment_aligned.wav"
	final_m4a = output_dir / "final_voiceover.segment_aligned.m4a"
	_concat_audio(chunks, final_wav)
	_encode_m4a(final_wav, final_m4a)

	manifest = {
		"schema_version": "segment-aligned-clone-voiceover.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"source_voiceover_segments_path": str(segments_path),
		"tts_manifest_path": str(tts_manifest_path),
		"mode": "voice_clone_only",
		"voice_clone": _voice_clone_evidence(tts_manifest),
		"parameters": {
			"max_auto_tempo": args.max_auto_tempo,
			"must_align_min_coverage": args.must_align_min_coverage,
			"normal_min_coverage": args.normal_min_coverage,
			"max_tail_silence_sec": args.max_tail_silence_sec,
			"timeline_duration_sec": args.timeline_duration_sec,
			"min_segment_pass_rate": args.min_segment_pass_rate,
		},
		"segment_count": len(manifest_segments),
		"final_wav_path": str(final_wav),
		"final_m4a_path": str(final_m4a),
		"timeline_duration_sec": round(_probe_duration(final_wav), 3),
		"timeline_gaps": timeline_gaps,
		"segments": manifest_segments,
		"failures": failures,
		"summary": _summary(manifest_segments, timeline_gaps, failures, args.min_segment_pass_rate),
	}
	manifest_path = output_dir / "manifest.json"
	report_path = output_dir / "alignment-report.md"
	manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	report_path.write_text(_report(manifest), encoding="utf-8")
	_log(f"manifest={manifest_path}")
	_log(f"final_m4a={final_m4a}")
	if manifest["summary"]["decision"] == "FAIL" and not args.allow_failures:
		raise SystemExit(2)


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Align cloned TTS draft segments to original audio-anchor windows.")
	parser.add_argument("--segments", type=Path, required=True)
	parser.add_argument("--draft-dir", type=Path, required=True)
	parser.add_argument("--tts-manifest", type=Path, required=True)
	parser.add_argument("--output-dir", type=Path, required=True)
	parser.add_argument("--timeline-duration-sec", type=float)
	parser.add_argument("--max-auto-tempo", type=float, default=1.15)
	parser.add_argument("--must-align-min-coverage", type=float, default=0.72)
	parser.add_argument("--normal-min-coverage", type=float, default=0.65)
	parser.add_argument("--max-tail-silence-sec", type=float, default=1.5)
	parser.add_argument("--min-segment-pass-rate", type=float, default=0.90)
	parser.add_argument("--allow-failures", action="store_true")
	parser.add_argument("--force", action="store_true")
	args = parser.parse_args()
	if not 0 < args.min_segment_pass_rate <= 1:
		parser.error("--min-segment-pass-rate must be in (0, 1].")
	return args


def _alignment_plan(
	*,
	segment: dict[str, Any],
	actual_sec: float,
	target_sec: float,
	max_auto_tempo: float,
	must_align_min_coverage: float,
	normal_min_coverage: float,
	max_tail_silence_sec: float,
) -> dict[str, Any]:
	assert actual_sec > 0
	assert target_sec > 0
	sync_priority = str(segment.get("sync_priority") or "normal")
	min_coverage = must_align_min_coverage if sync_priority == "must_align" else normal_min_coverage
	coverage_ratio = round(actual_sec / target_sec, 6)
	gate_flags: list[str] = []
	if coverage_ratio < min_coverage:
		gate_flags.append("coverage_below_threshold")
	if actual_sec > target_sec:
		tempo_factor = round(actual_sec / target_sec, 6)
		tail_silence_sec = 0.0
		sync_action = "speed_up_to_fit"
		if tempo_factor > max_auto_tempo:
			gate_flags.append("tempo_factor_gt_limit")
	else:
		tempo_factor = 1.0
		tail_silence_sec = round(target_sec - actual_sec, 6)
		sync_action = "pad_tail_silence"
		if tail_silence_sec > max_tail_silence_sec:
			gate_flags.append("tail_silence_gt_limit")
	return {
		"coverage_ratio": coverage_ratio,
		"tempo_factor": tempo_factor,
		"tail_silence_sec": tail_silence_sec,
		"sync_action": sync_action,
		"gate_flags": gate_flags,
	}


def _align_audio(*, input_wav: Path, output_wav: Path, target_sec: float, tempo_factor: float) -> None:
	filters: list[str] = []
	if not math.isclose(tempo_factor, 1.0, abs_tol=0.005):
		filters.extend(_atempo_filters(tempo_factor))
	filters.append("apad")
	_run(
		[
			"ffmpeg",
			"-y",
			"-v",
			"error",
			"-i",
			str(input_wav),
			"-af",
			",".join(filters),
			"-t",
			f"{target_sec:.3f}",
			"-ar",
			"24000",
			"-ac",
			"1",
			"-c:a",
			"pcm_s16le",
			str(output_wav),
		]
	)


def _atempo_filters(tempo_factor: float) -> list[str]:
	assert tempo_factor > 0
	filters: list[str] = []
	remaining = tempo_factor
	while remaining > 2.0:
		filters.append("atempo=2.0")
		remaining /= 2.0
	while remaining < 0.5:
		filters.append("atempo=0.5")
		remaining /= 0.5
	filters.append(f"atempo={remaining:.6f}")
	return filters


def _concat_audio(chunks: list[Path], output_wav: Path) -> None:
	if not chunks:
		raise ValueError("No audio chunks to concatenate.")
	with tempfile.TemporaryDirectory() as temp_dir:
		list_path = Path(temp_dir) / "concat.txt"
		list_path.write_text("".join(f"file '{_escape_concat_path(path)}'\n" for path in chunks), encoding="utf-8")
		_run(
			[
				"ffmpeg",
				"-y",
				"-v",
				"error",
				"-f",
				"concat",
				"-safe",
				"0",
				"-i",
				str(list_path),
				"-ar",
				"24000",
				"-ac",
				"1",
				"-c:a",
				"pcm_s16le",
				str(output_wav),
			]
		)


def _encode_m4a(input_wav: Path, output_m4a: Path) -> None:
	_run(
		[
			"ffmpeg",
			"-y",
			"-v",
			"error",
			"-i",
			str(input_wav),
			"-c:a",
			"aac",
			"-b:a",
			"192k",
			str(output_m4a),
		]
	)


def _make_silence(output_wav: Path, duration_sec: float) -> None:
	assert duration_sec > 0
	_run(
		[
			"ffmpeg",
			"-y",
			"-v",
			"error",
			"-f",
			"lavfi",
			"-i",
			"anullsrc=r=24000:cl=mono",
			"-t",
			f"{duration_sec:.3f}",
			"-c:a",
			"pcm_s16le",
			str(output_wav),
		]
	)


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


def _draft_audio_by_segment_id(tts_manifest: dict[str, Any]) -> dict[str, Path]:
	by_id: dict[str, Path] = {}
	for segment in tts_manifest.get("segments") or []:
		if not isinstance(segment, dict):
			continue
		segment_id = segment.get("segment_id")
		draft_audio_path = segment.get("draft_audio_path")
		if segment_id and draft_audio_path:
			by_id[str(segment_id)] = Path(str(draft_audio_path)).expanduser().resolve()
	return by_id


def _resolve_draft_wav(segment_id: str, draft_dir: Path, draft_by_id: dict[str, Path]) -> Path:
	path = draft_by_id.get(segment_id) or draft_dir / f"{segment_id}.wav"
	_require_file(path)
	return path


def _voice_clone_evidence(tts_manifest: dict[str, Any]) -> dict[str, Any]:
	voice_profile = tts_manifest.get("voice_profile")
	if isinstance(voice_profile, dict):
		return {
			"mode": voice_profile.get("mode"),
			"model_dir": voice_profile.get("model_dir"),
			"ref_audio_path": voice_profile.get("ref_audio_path"),
			"ref_audio_sha256": voice_profile.get("ref_audio_sha256"),
			"ref_text_path": voice_profile.get("ref_text_path"),
			"ref_text_sha256": voice_profile.get("ref_text_sha256"),
			"reference_source": voice_profile.get("reference_source"),
		}
	return {
		"mode": tts_manifest.get("mode"),
		"model_dir": tts_manifest.get("model_dir"),
		"ref_audio_path": tts_manifest.get("ref_audio_path"),
		"ref_audio_sha256": tts_manifest.get("ref_audio_sha256"),
		"ref_text_path": tts_manifest.get("ref_text_path"),
		"ref_text_sha256": tts_manifest.get("ref_text_sha256"),
	}


def _assert_voice_clone_manifest(tts_manifest: dict[str, Any]) -> None:
	mode = tts_manifest.get("mode")
	voice_profile = tts_manifest.get("voice_profile")
	profile_mode = voice_profile.get("mode") if isinstance(voice_profile, dict) else None
	if mode != "voice_clone_only" and profile_mode != "voice_clone_only":
		raise ValueError("tts manifest must prove voice_clone_only mode.")
	for key in ("model_dir", "ref_audio_path", "ref_audio_sha256", "ref_text_sha256"):
		if not tts_manifest.get(key) and not (isinstance(voice_profile, dict) and voice_profile.get(key)):
			raise ValueError(f"tts manifest is missing voice clone evidence: {key}")


def _assert_monotonic_segments(segments: list[dict[str, Any]]) -> None:
	previous_end = -1.0
	seen: set[str] = set()
	for segment in segments:
		segment_id = str(segment.get("segment_id") or "")
		if not segment_id:
			raise ValueError("segment_id must not be empty.")
		if segment_id in seen:
			raise ValueError(f"duplicate segment_id: {segment_id}")
		seen.add(segment_id)
		start = _segment_start_sec(segment)
		end = _segment_end_sec(segment)
		if start < previous_end - 0.05:
			raise ValueError(f"Segment {segment_id} overlaps previous segment.")
		if end <= start:
			raise ValueError(f"Segment {segment_id} has invalid time range.")
		previous_end = end


def _segment_start_sec(segment: dict[str, Any]) -> float:
	value = segment.get("start_sec")
	if isinstance(value, int | float):
		return float(value)
	return _parse_hhmmss(str(segment["start"]))


def _segment_end_sec(segment: dict[str, Any]) -> float:
	value = segment.get("end_sec")
	if isinstance(value, int | float):
		return float(value)
	return _parse_hhmmss(str(segment["end"]))


def _parse_hhmmss(value: str) -> float:
	parts = value.split(":")
	if len(parts) != 3:
		raise ValueError(f"Expected HH:MM:SS, got {value!r}.")
	hours, minutes, seconds = parts
	return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _summary(
	segments: list[dict[str, Any]],
	timeline_gaps: list[dict[str, Any]],
	failures: list[dict[str, Any]],
	min_segment_pass_rate: float,
) -> dict[str, Any]:
	pass_count = sum(1 for segment in segments if segment["pass"])
	segment_pass_rate = pass_count / len(segments)
	overall_pass = segment_pass_rate >= min_segment_pass_rate
	return {
		"decision": "PASS" if overall_pass else "FAIL",
		"overall_pass": overall_pass,
		"pass_count": pass_count,
		"segment_pass_rate": round(segment_pass_rate, 6),
		"min_segment_pass_rate": min_segment_pass_rate,
		"failure_count": len(failures),
		"failed_segment_ids": [failure["segment_id"] for failure in failures],
		"tolerated_failure_count": len(failures) if overall_pass else 0,
		"tolerated_failed_segment_ids": [failure["segment_id"] for failure in failures] if overall_pass else [],
		"min_coverage_ratio": round(min(float(segment["coverage_ratio"]) for segment in segments), 6),
		"max_tail_silence_sec": round(max(float(segment["tail_silence_sec"]) for segment in segments), 6),
		"max_tempo_factor": round(max(float(segment["tempo_factor"]) for segment in segments), 6),
		"timeline_gap_count": len(timeline_gaps),
		"total_timeline_gap_duration_sec": round(sum(float(gap["duration_sec"]) for gap in timeline_gaps), 3),
	}


def _report(manifest: dict[str, Any]) -> str:
	summary = manifest["summary"]
	lines = [
		"# Segment-Aligned Clone Voiceover Report",
		"",
		f"- Decision: {summary['decision']}",
		f"- Source segments: {manifest['source_voiceover_segments_path']}",
		f"- TTS manifest: {manifest['tts_manifest_path']}",
		f"- Final M4A: {manifest['final_m4a_path']}",
		f"- Segment count: {manifest['segment_count']}",
		f"- Segment pass rate: {summary['segment_pass_rate']} (minimum {summary['min_segment_pass_rate']})",
		f"- Pass count: {summary['pass_count']}",
		f"- Failure count: {summary['failure_count']}",
		f"- Tolerated failure count: {summary['tolerated_failure_count']}",
		f"- Min coverage ratio: {summary['min_coverage_ratio']}",
		f"- Max tail silence sec: {summary['max_tail_silence_sec']}",
		f"- Max tempo factor: {summary['max_tempo_factor']}",
		f"- Timeline gaps: {summary['timeline_gap_count']} gap(s), {summary['total_timeline_gap_duration_sec']}s",
		"",
		"## Failures",
		"",
	]
	if manifest["failures"]:
		for failure in manifest["failures"]:
			lines.append(
				f"- {failure['segment_id']}: flags={','.join(failure['gate_flags'])}, "
				f"coverage={failure['coverage_ratio']}, tail={failure['tail_silence_sec']}, "
				f"tempo={failure['tempo_factor']}"
			)
	else:
		lines.append("- None")
	lines.append("")
	return "\n".join(lines)


def _escape_concat_path(path: Path) -> str:
	return str(path.resolve()).replace("'", "'\\''")


def _run(cmd: list[str]) -> None:
	subprocess.run(cmd, check=True)


def _require_file(path: Path) -> None:
	if not path.exists() or not path.is_file():
		raise FileNotFoundError(path)


def _require_dir(path: Path) -> None:
	if not path.exists() or not path.is_dir():
		raise NotADirectoryError(path)


def _require_command(name: str) -> None:
	if subprocess.run(["/usr/bin/which", name], capture_output=True, text=True).returncode != 0:
		raise RuntimeError(f"Required command not found: {name}")


def _log(message: str) -> None:
	print(message, flush=True)


if __name__ == "__main__":
	main()
