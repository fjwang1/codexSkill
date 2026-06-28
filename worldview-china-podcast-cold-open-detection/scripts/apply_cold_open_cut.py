#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "worldview-china-podcast-cold-open-cut.v1"

FRAGMENT_START_PATTERNS = [
	re.compile(r"^\s*(and|but|or|so|because|therefore|however|then)\b", re.I),
	re.compile(r"^\s*(number\s+two|no\.?\s*2|the\s+third|third\s+is|second\s+is)\b", re.I),
	re.compile(r"^\s*(right|yeah|yes|okay|ok)[,.\s]+", re.I),
]

GOOD_OPENING_PATTERNS = [
	re.compile(r"\bbefore we (start|begin)\b", re.I),
	re.compile(r"\bwelcome (to|back)\b", re.I),
	re.compile(r"\btoday'?s (podcast|episode|conversation)\b", re.I),
	re.compile(r"\bwhat happened\b", re.I),
]


def _default_run_paths(run_dir: Path) -> dict[str, Path]:
	return {
		"video": run_dir / "02-source-capture" / "youtube-media" / "source.mp4",
		"wav": run_dir / "02-source-capture" / "youtube-media" / "source.wav",
		"transcript_json": run_dir / "02-source-capture" / "source_transcript.en.json",
		"transcript_txt": run_dir / "02-source-capture" / "source_transcript.en.txt",
		"output_dir": run_dir / "02-source-cold-open-cut",
	}


def _load_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


def _extract_segments(data: Any) -> list[dict[str, Any]]:
	if isinstance(data, dict) and isinstance(data.get("transcript"), dict):
		return data["transcript"].get("segments", [])
	if isinstance(data, dict):
		return data.get("segments", [])
	if isinstance(data, list):
		return data
	return []


def _set_segments(data: Any, segments: list[dict[str, Any]], transcript_text: str) -> Any:
	out = copy.deepcopy(data)
	if isinstance(out, dict) and isinstance(out.get("transcript"), dict):
		out["transcript"]["segments"] = segments
		out["transcript"]["text"] = transcript_text
	elif isinstance(out, dict):
		out["segments"] = segments
		out["text"] = transcript_text
	elif isinstance(out, list):
		out = segments
	return out


def _segment_start(raw: dict[str, Any]) -> float:
	return float(raw.get("start", raw.get("source_start_sec", raw.get("start_sec"))))


def _segment_end(raw: dict[str, Any]) -> float:
	return float(raw.get("end", raw.get("source_end_sec", raw.get("end_sec"))))


def _segment_text(raw: dict[str, Any]) -> str:
	return str(raw.get("text", raw.get("source_text", "")))


def _shift_transcript(data: Any, cut_end_sec: float, tolerance: float) -> tuple[Any, str, dict[str, Any]]:
	raw_segments = [s for s in _extract_segments(data) if isinstance(s, dict)]
	kept: list[dict[str, Any]] = []
	removed: list[dict[str, Any]] = []
	for raw in raw_segments:
		start = _segment_start(raw)
		end = _segment_end(raw)
		if end <= cut_end_sec + tolerance:
			removed.append(raw)
			continue
		if start < cut_end_sec - tolerance < end:
			return data, "", {
				"status": "FAIL",
				"reason": "cut_boundary_splits_transcript_segment",
				"segment": raw,
			}
		new_raw = copy.deepcopy(raw)
		new_start = max(0.0, start - cut_end_sec)
		new_end = max(new_start, end - cut_end_sec)
		if "start" in new_raw:
			new_raw["start"] = round(new_start, 3)
		if "end" in new_raw:
			new_raw["end"] = round(new_end, 3)
		if "source_start_sec" in new_raw:
			new_raw["source_start_sec"] = round(new_start, 3)
		if "source_end_sec" in new_raw:
			new_raw["source_end_sec"] = round(new_end, 3)
		new_raw["original_start_sec"] = start
		new_raw["original_end_sec"] = end
		new_raw["cold_open_cut_shift_sec"] = cut_end_sec
		new_raw["index"] = len(kept) + 1
		kept.append(new_raw)

	transcript_text = "\n".join(f">> {_segment_text(s)}" for s in kept)
	out = _set_segments(data, kept, transcript_text)
	first_text = _segment_text(kept[0]) if kept else ""
	return out, transcript_text, {
		"status": "PASS",
		"removed_segment_count": len(removed),
		"kept_segment_count": len(kept),
		"first_text_after_cut": first_text,
		"first_original_start_sec": _segment_start(kept[0]) + cut_end_sec if kept else None,
	}


def _run(cmd: list[str]) -> None:
	subprocess.run(cmd, check=True)


def _ffprobe_duration(path: Path) -> float:
	cmd = [
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		str(path),
	]
	result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True)
	return float(result.stdout.strip())


def _render_cut(source_video: Path, out_video: Path, cut_end_sec: float, sample_duration_sec: float | None) -> None:
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-ss",
		f"{cut_end_sec:.3f}",
		"-i",
		str(source_video),
	]
	if sample_duration_sec is not None:
		cmd.extend(["-t", f"{sample_duration_sec:.3f}"])
	cmd.extend([
		"-map",
		"0",
		"-c:v",
		"libx264",
		"-preset",
		"veryfast",
		"-crf",
		"18",
		"-c:a",
		"aac",
		"-b:a",
		"192k",
		"-movflags",
		"+faststart",
		str(out_video),
	])
	_run(cmd)


def _extract_wav(video: Path, wav: Path) -> None:
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(video),
		"-vn",
		"-ac",
		"1",
		"-ar",
		"48000",
		"-c:a",
		"pcm_s16le",
		str(wav),
	]
	_run(cmd)


def _extract_opening_frame(video: Path, frame: Path) -> None:
	cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-ss",
		"0.250",
		"-i",
		str(video),
		"-frames:v",
		"1",
		"-q:v",
		"2",
		str(frame),
	]
	_run(cmd)


def _validate_first_text(text: str) -> dict[str, Any]:
	if not text.strip():
		return {"status": "FAIL", "reason": "empty_first_text"}
	for pattern in FRAGMENT_START_PATTERNS:
		if pattern.search(text):
			return {"status": "FAIL", "reason": "first_text_looks_fragmentary", "text": text}
	good = any(pattern.search(text) for pattern in GOOD_OPENING_PATTERNS)
	if good:
		return {"status": "PASS", "reason": "known_good_opening_cue", "text": text}
	if len(text.strip()) >= 40 and text.strip()[0].isupper():
		return {"status": "PASS", "reason": "complete_sentence_like_opening", "text": text}
	return {"status": "REVIEW", "reason": "first_text_needs_manual_review", "text": text}


def _promote_active(paths: dict[str, Path], output_video: Path, output_wav: Path, output_json: Path, output_txt: Path) -> list[dict[str, str]]:
	ops: list[dict[str, str]] = []
	pairs = [
		(paths["video"], paths["video"].with_name("source.original_with_cold_open.mp4"), output_video),
		(paths["wav"], paths["wav"].with_name("source.original_with_cold_open.wav"), output_wav),
		(paths["transcript_json"], paths["transcript_json"].with_name("source_transcript.en.original_with_cold_open.json"), output_json),
		(paths["transcript_txt"], paths["transcript_txt"].with_name("source_transcript.en.original_with_cold_open.txt"), output_txt),
	]
	for active, archive, replacement in pairs:
		if active.exists() and not archive.exists():
			shutil.copy2(active, archive)
			ops.append({"op": "archive", "from": str(active), "to": str(archive)})
		shutil.copy2(replacement, active)
		ops.append({"op": "promote", "from": str(replacement), "to": str(active)})
	return ops


def _write_report(result: dict[str, Any], path: Path) -> None:
	lines = [
		"# Cold Open Cut Validation Report",
		"",
		f"- status: {result['status']}",
		f"- reason: {result.get('reason')}",
		f"- cut: {result['cut']['start_sec']:.3f}-{result['cut']['end_sec']:.3f}s",
		f"- output_video: {result.get('output_video')}",
		f"- output_wav: {result.get('output_wav')}",
		f"- first_text_validation: {json.dumps(result.get('first_text_validation'), ensure_ascii=False)}",
	]
	if result.get("promote_operations"):
		lines.extend(["", "## Promote Operations", ""])
		for op in result["promote_operations"]:
			lines.append(f"- {op['op']}: {op['from']} -> {op['to']}")
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
	parser = argparse.ArgumentParser(description="Apply a confirmed podcast cold-open cut and validate the new opening.")
	parser.add_argument("--run-dir", type=Path)
	parser.add_argument("--source-video", type=Path)
	parser.add_argument("--transcript-json", type=Path)
	parser.add_argument("--detection-json", type=Path, required=True)
	parser.add_argument("--output-dir", type=Path)
	parser.add_argument("--sample-duration-sec", type=float)
	parser.add_argument("--promote-active", action="store_true")
	parser.add_argument("--boundary-tolerance-sec", type=float, default=0.35)
	args = parser.parse_args()

	if args.run_dir:
		paths = _default_run_paths(args.run_dir)
		source_video = args.source_video or paths["video"]
		transcript_json = args.transcript_json or paths["transcript_json"]
		output_dir = args.output_dir or paths["output_dir"]
	else:
		if not args.source_video or not args.transcript_json or not args.output_dir:
			parser.error("--source-video, --transcript-json and --output-dir are required without --run-dir")
		paths = {
			"video": args.source_video,
			"wav": args.output_dir / "source.wav",
			"transcript_json": args.transcript_json,
			"transcript_txt": args.output_dir / "source_transcript.en.txt",
			"output_dir": args.output_dir,
		}
		source_video = args.source_video
		transcript_json = args.transcript_json
		output_dir = args.output_dir
	output_dir.mkdir(parents=True, exist_ok=True)

	detection = _load_json(args.detection_json)
	if detection.get("status") != "CUT_CONFIRMED":
		raise SystemExit(f"refusing to cut: detection status is {detection.get('status')}, not CUT_CONFIRMED")
	cut = detection.get("cut") or {}
	cut_start = float(cut.get("start_sec", 0.0))
	cut_end = float(cut.get("end_sec"))
	if abs(cut_start) > 0.01:
		raise SystemExit("refusing to cut: only start-at-zero cold-open cuts are supported")

	transcript_data = _load_json(transcript_json)
	cleaned_transcript, transcript_text, transcript_validation = _shift_transcript(transcript_data, cut_end, args.boundary_tolerance_sec)
	if transcript_validation.get("status") != "PASS":
		result = {
			"schema_version": SCHEMA_VERSION,
			"status": "FAIL",
			"reason": transcript_validation.get("reason"),
			"cut": {"start_sec": cut_start, "end_sec": cut_end},
			"transcript_validation": transcript_validation,
		}
		(output_dir / "cold_open_cut_validation_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
		_write_report(result, output_dir / "cold_open_cut_validation_report.md")
		raise SystemExit(2)

	out_video = output_dir / ("source.cleaned.sample.mp4" if args.sample_duration_sec else "source.cleaned.mp4")
	out_wav = output_dir / ("source.cleaned.sample.wav" if args.sample_duration_sec else "source.cleaned.wav")
	out_json = output_dir / "source_transcript.en.cleaned.json"
	out_txt = output_dir / "source_transcript.en.cleaned.txt"
	opening_frame = output_dir / "source.cleaned.opening.jpg"
	_render_cut(source_video, out_video, cut_end, args.sample_duration_sec)
	_extract_wav(out_video, out_wav)
	_extract_opening_frame(out_video, opening_frame)

	out_json.write_text(json.dumps(cleaned_transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	out_txt.write_text(transcript_text + "\n", encoding="utf-8")
	duration = _ffprobe_duration(out_video)
	first_text_validation = _validate_first_text(str(transcript_validation.get("first_text_after_cut", "")))
	status = "PASS" if first_text_validation["status"] == "PASS" else "REVIEW"
	reason = "cut_rendered_and_opening_validated" if status == "PASS" else "cut_rendered_but_opening_needs_review"
	promote_operations: list[dict[str, str]] = []
	if args.promote_active:
		if args.sample_duration_sec is not None:
			raise SystemExit("--promote-active cannot be used with --sample-duration-sec")
		if status != "PASS":
			raise SystemExit("refusing to promote active source: validation did not PASS")
		promote_operations = _promote_active(paths, out_video, out_wav, out_json, out_txt)

	result = {
		"schema_version": SCHEMA_VERSION,
		"status": status,
		"reason": reason,
		"detection_json": str(args.detection_json),
		"source_video": str(source_video),
		"output_video": str(out_video),
		"output_wav": str(out_wav),
		"output_transcript_json": str(out_json),
		"output_transcript_txt": str(out_txt),
		"opening_frame": str(opening_frame),
		"sample_duration_sec": args.sample_duration_sec,
		"output_duration_sec": duration,
		"cut": {"start_sec": cut_start, "end_sec": cut_end, "duration_sec": cut_end - cut_start},
		"transcript_validation": transcript_validation,
		"first_text_validation": first_text_validation,
		"promote_operations": promote_operations,
	}
	result_path = output_dir / "cold_open_cut_validation_result.json"
	report_path = output_dir / "cold_open_cut_validation_report.md"
	result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	_write_report(result, report_path)
	print(json.dumps({"status": status, "result": str(result_path), "report": str(report_path)}, ensure_ascii=False))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
