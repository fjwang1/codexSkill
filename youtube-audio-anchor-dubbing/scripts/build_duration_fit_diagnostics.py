from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def main() -> None:
	args = _parse_args()
	subset_path = args.subset.expanduser().resolve()
	manifest_path = args.manifest.expanduser().resolve()
	output_path = args.output.expanduser().resolve()
	_require_file(subset_path)
	_require_file(manifest_path)
	subset = json.loads(subset_path.read_text(encoding="utf-8"))
	manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
	segments = _diagnose_segments(subset=subset, manifest=manifest, args=args)
	failed = [segment for segment in segments if not segment["pass"]]
	pass_count = len(segments) - len(failed)
	segment_pass_rate = pass_count / len(segments)
	overall_pass = segment_pass_rate >= args.min_segment_pass_rate
	must_align_count = sum(1 for segment in segments if segment["sync_priority"] == "must_align")
	normal_sample_count = len(segments) - must_align_count
	result = {
		"schema_version": "hard-anchor-duration-diagnostics.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"attempt": args.attempt,
		"source_voiceover_attempt": args.source_voiceover_attempt,
		"source_segments_sha256": args.source_segments_sha256,
		"subset_path": str(subset_path),
		"subset_sha256": _sha256_file(subset_path),
		"tts_manifest_path": str(manifest_path),
		"tts_manifest_sha256": _sha256_file(manifest_path),
		"decision": "PASS" if overall_pass else "FAIL",
		"overall_pass": overall_pass,
		"pass_count": pass_count,
		"segment_pass_rate": round(segment_pass_rate, 6),
		"min_segment_pass_rate": args.min_segment_pass_rate,
		"failed_count": len(failed),
		"failed_segment_ids": [segment["segment_id"] for segment in failed],
		"tolerated_failure_count": len(failed) if overall_pass else 0,
		"tolerated_failed_segment_ids": [segment["segment_id"] for segment in failed] if overall_pass else [],
		"segment_count": len(segments),
		"must_align_count": must_align_count,
		"normal_sample_count": normal_sample_count,
		"thresholds": {
			"must_align_min_coverage_ratio": args.must_align_min_coverage_ratio,
			"normal_min_coverage_ratio": args.normal_min_coverage_ratio,
			"max_tail_silence_sec": args.max_tail_silence,
			"max_tempo_factor": args.max_tempo_factor,
			"min_segment_pass_rate": args.min_segment_pass_rate,
		},
		"segments": segments,
	}
	output_path.parent.mkdir(parents=True, exist_ok=True)
	output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print(json.dumps({"output": str(output_path), "decision": result["decision"], "failed_segment_ids": result["failed_segment_ids"]}, ensure_ascii=False))


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build auditable duration-fit diagnostics from a TTS subset manifest.")
	parser.add_argument("--subset", type=Path, required=True, help="Subset voiceover-segments JSON used for diagnostic TTS.")
	parser.add_argument("--manifest", type=Path, required=True, help="TTS manifest generated for the diagnostic subset.")
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--attempt", type=int, required=True)
	parser.add_argument("--source-voiceover-attempt", type=int, required=True)
	parser.add_argument("--source-segments-sha256", required=True)
	parser.add_argument("--must-align-min-coverage-ratio", type=float, default=0.72)
	parser.add_argument("--normal-min-coverage-ratio", type=float, default=0.65)
	parser.add_argument("--max-tail-silence", type=float, default=1.5)
	parser.add_argument("--max-tempo-factor", type=float, default=1.15)
	parser.add_argument("--min-segment-pass-rate", type=float, default=0.90)
	args = parser.parse_args()
	if not 0 < args.min_segment_pass_rate <= 1:
		parser.error("--min-segment-pass-rate must be in (0, 1].")
	return args


def _diagnose_segments(*, subset: dict[str, Any], manifest: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
	subset_segments = subset.get("segments")
	manifest_segments = manifest.get("segments")
	if not isinstance(subset_segments, list) or not subset_segments:
		raise ValueError("subset must contain non-empty segments list.")
	if not isinstance(manifest_segments, list) or not manifest_segments:
		raise ValueError("manifest must contain non-empty segments list.")
	manifest_by_id = {str(segment.get("segment_id")): segment for segment in manifest_segments}
	output: list[dict[str, Any]] = []
	for subset_segment in subset_segments:
		segment_id = str(subset_segment.get("segment_id") or "")
		if not segment_id:
			raise ValueError("subset contains segment without segment_id.")
		manifest_segment = manifest_by_id.get(segment_id)
		if manifest_segment is None:
			raise ValueError(f"manifest missing diagnostic segment {segment_id}.")
		sync_priority = str(subset_segment.get("sync_priority") or manifest_segment.get("sync_priority") or "normal")
		target_sec = _as_float(subset_segment.get("target_duration_sec") or manifest_segment.get("target_duration_sec"))
		tts_sec = _as_float(manifest_segment.get("tts_duration_sec"))
		coverage_ratio = tts_sec / target_sec if target_sec > 0 else 0.0
		tail_silence_sec = max(target_sec - tts_sec, 0.0)
		tempo_factor = tts_sec / target_sec if tts_sec > target_sec and target_sec > 0 else 1.0
		gate_flags: list[str] = []
		min_coverage = args.must_align_min_coverage_ratio if sync_priority == "must_align" else args.normal_min_coverage_ratio
		if coverage_ratio < min_coverage:
			gate_flags.append("coverage_ratio_lt_limit")
		if tail_silence_sec > args.max_tail_silence:
			gate_flags.append("tail_silence_gt_limit")
		if tempo_factor > args.max_tempo_factor:
			gate_flags.append("tempo_factor_gt_limit")
		voice_text = str(subset_segment.get("voice_text") or manifest_segment.get("voice_text") or "")
		output.append(
			{
				"segment_id": segment_id,
				"sync_priority": sync_priority,
				"target_duration_sec": round(target_sec, 3),
				"tts_duration_sec": round(tts_sec, 3),
				"coverage_ratio": round(coverage_ratio, 6),
				"tail_silence_sec": round(tail_silence_sec, 3),
				"tempo_factor_if_compressed": round(tempo_factor, 6),
				"gate_flags": gate_flags,
				"pass": not gate_flags,
				"voice_text": voice_text,
				"voice_text_sha256": hashlib.sha256(voice_text.encode("utf-8")).hexdigest(),
				"manifest_voice_text_sha256": manifest_segment.get("voice_text_sha256"),
			}
		)
	return output


def _as_float(value: Any) -> float:
	if not isinstance(value, int | float):
		raise ValueError(f"Expected numeric value, got {value!r}.")
	return float(value)


def _sha256_file(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _require_file(path: Path) -> None:
	if not path.exists() or not path.is_file():
		raise FileNotFoundError(path)


if __name__ == "__main__":
	main()
