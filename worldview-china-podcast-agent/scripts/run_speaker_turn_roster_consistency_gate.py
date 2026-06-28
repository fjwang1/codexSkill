#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NODE_DIRNAME = "03e-speaker-turn-roster-consistency"
RESULT_FILENAME = "speaker-turn-roster-consistency-result.json"
REPORT_FILENAME = "speaker-turn-roster-consistency-report.md"
SPEAKER_RE = re.compile(r"^Speaker ([0-3])$")
HOST_KEYWORDS = (
	"host",
	"interviewer",
	"moderator",
	"asks short",
	"ask short",
	"question",
	"主持",
	"采访",
	"提问",
	"访谈主持",
)
GUEST_KEYWORDS = (
	"guest",
	"expert",
	"primary expert",
	"answering",
	"嘉宾",
	"专家",
	"回答",
	"受访",
	"主讲",
)
CO_SPEAKER_KEYWORDS = (
	"co_speaker",
	"co-speaker",
	"co speaker",
	"two-person discussion",
	"共同讨论",
	"共同主持",
	"双人讨论",
)
HOST_QUESTION_PATTERNS = (
	r"(?m)^\s*(?:tell me|what|why|how|which|do you|can you|should we|top three)\b",
	r"(?m)^\s*(?:你告诉我|哪些|哪几个|具体是|为什么|是不是|我们是不是|你认为|你觉得|能不能|该不该)",
)
ANSWER_PATTERNS = (
	r"\bi think\b",
	r"\bi would\b",
	r"\bi believe\b",
	r"\blook\b",
	r"\blet me\b",
	r"\bfor example\b",
	r"\bno no\b",
	r"\bwe need\b",
	r"\bwe must\b",
	r"\bmy take\b",
	r"\bhere is\b",
	r"我认为",
	r"我觉得",
	r"我会说",
	r"我的看法",
	r"不妨",
	r"我解释",
	r"举个例子",
	r"我的观点",
	r"所以",
	r"因为",
	r"你看",
	r"我们需要",
	r"我们必须",
	r"它告诉我们",
)
QUESTION_THEN_ANSWER_PATTERNS = (
	r"(?is)^\s*(?:tell me|what|why|how|which|do you|can you|should we|finishing the thought|top three)\b.{0,260}\?\s*(?:look|i think|i would|let me|no no|for example|answer|now|this|that)",
	r"(?s)^\s*(?:你告诉我|哪些|哪几个|具体是|为什么|是不是|我们是不是|你认为|你觉得|能不能|该不该).{0,180}？.{0,120}(?:我会说|我认为|我觉得|不妨|我解释|我的看法|举个例子|答案是)",
	r"(?is)^\s*I'm quite intrigued\b.{0,220}\?\s*(?:look|i think|i would|let me|no no|for example|answer)",
	r"(?is)^\s*tell me\b.+\blook\b",
	r"让我很感兴趣的是.+是不是",
	r"那你告诉我.+哪些？.+我会说",
)


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _relative(run_dir: Path, path: Path) -> str:
	try:
		return str(path.relative_to(run_dir))
	except ValueError:
		return str(path)


def _is_supported_speaker(value: Any) -> bool:
	return SPEAKER_RE.fullmatch(str(value or "")) is not None


def _speaker_index(speaker: str) -> int:
	match = SPEAKER_RE.fullmatch(speaker)
	assert match, f"Unsupported speaker id: {speaker}"
	return int(match.group(1))


def _resolve_roster_path(run_dir: Path) -> Path:
	candidates = [
		run_dir / "02a-speaker-census/speaker_roster.json",
		run_dir.parent.parent / "02a-speaker-census/speaker_roster.json",
	]
	for path in candidates:
		if path.exists():
			return path
	raise FileNotFoundError(f"Missing 02a speaker roster for {run_dir}")


def _active_translation_path(run_dir: Path) -> Path:
	candidates = [
		run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json",
		run_dir / "03-source-translation/source_transcript.zh.json",
	]
	for path in candidates:
		if path.exists():
			return path
	raise FileNotFoundError(f"Missing active translated transcript for {run_dir}")


def _optional_input_paths(run_dir: Path, roster_path: Path, translation_path: Path) -> list[Path]:
	paths = [roster_path, translation_path]
	for rel in (
		"03-source-translation/source_transcript.zh.json",
		"03b-mainland-publish-safety/source_transcript.zh.safe.json",
		"04-podcast-script/script_turns.json",
		"04-podcast-script/podcast_script.md",
		"podcast_script.md",
	):
		path = run_dir / rel
		if path.exists() and path not in paths:
			paths.append(path)
	return paths


def _input_hashes(run_dir: Path, paths: list[Path]) -> dict[str, str]:
	return {
		_relative(run_dir, path): _sha256(path)
		for path in paths
		if path.exists()
	}


def _speaker_role_scores(speaker_info: dict[str, Any]) -> tuple[int, int, int]:
	text = " ".join(
		str(speaker_info.get(key) or "")
		for key in ("description", "identity", "role", "speaker")
	).lower()
	host_score = sum(1 for keyword in HOST_KEYWORDS if keyword.lower() in text)
	guest_score = sum(1 for keyword in GUEST_KEYWORDS if keyword.lower() in text)
	co_speaker_score = sum(1 for keyword in CO_SPEAKER_KEYWORDS if keyword.lower() in text)
	return host_score, guest_score, co_speaker_score


def _infer_two_speaker_roles(roster: dict[str, Any]) -> tuple[str | None, str | None, dict[str, dict[str, Any]]]:
	speakers = roster.get("speakers") if isinstance(roster.get("speakers"), dict) else {}
	role_evidence: dict[str, dict[str, Any]] = {}
	for speaker, info in speakers.items():
		if not _is_supported_speaker(speaker) or not isinstance(info, dict):
			continue
		host_score, guest_score, co_speaker_score = _speaker_role_scores(info)
		role_evidence[str(speaker)] = {
			"host_score": host_score,
			"guest_score": guest_score,
			"co_speaker_score": co_speaker_score,
			"description": info.get("description"),
			"role": info.get("role"),
			"identity": info.get("identity"),
		}
	candidates = sorted(role_evidence, key=_speaker_index)
	if len(candidates) != 2:
		return None, None, role_evidence
	host_candidates = [
		speaker for speaker in candidates
		if role_evidence[speaker]["host_score"] > role_evidence[speaker]["guest_score"]
	]
	guest_candidates = [
		speaker for speaker in candidates
		if role_evidence[speaker]["guest_score"] > role_evidence[speaker]["host_score"]
	]
	if len(host_candidates) == 1 and len(guest_candidates) == 1 and host_candidates[0] != guest_candidates[0]:
		return host_candidates[0], guest_candidates[0], role_evidence
	return None, None, role_evidence


def _is_explicit_two_speaker_co_speaker_roster(role_evidence: dict[str, dict[str, Any]]) -> bool:
	if len(role_evidence) != 2:
		return False
	return all(int(info.get("co_speaker_score") or 0) > 0 for info in role_evidence.values())


def _normalize_text(value: Any) -> str:
	return re.sub(r"\s+", " ", str(value or "")).strip()


def _compact_zh_len(value: Any) -> int:
	return len(re.sub(r"\s+", "", str(value or "")))


def _combined_segment_text(segment: dict[str, Any]) -> str:
	return "\n".join((
		_normalize_text(segment.get("source_text")),
		_normalize_text(segment.get("zh_text") or segment.get("text")),
	))


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
	return any(re.search(pattern, text, re.I | re.S) for pattern in patterns)


def _has_host_question_marker(segment: dict[str, Any]) -> bool:
	text = _combined_segment_text(segment)
	return _has_any_pattern(text, HOST_QUESTION_PATTERNS)


def _has_question_then_answer(segment: dict[str, Any]) -> bool:
	text = _combined_segment_text(segment)
	return _has_any_pattern(text, QUESTION_THEN_ANSWER_PATTERNS)


def _is_answer_like(segment: dict[str, Any]) -> bool:
	text = _combined_segment_text(segment)
	return _has_any_pattern(text, ANSWER_PATTERNS)


def _segment_lengths(segment: dict[str, Any]) -> tuple[int, int]:
	return _compact_zh_len(segment.get("zh_text") or segment.get("text")), len(_normalize_text(segment.get("source_text")))


def _time_to_sec(value: Any) -> float | None:
	if value is None:
		return None
	if isinstance(value, int | float):
		return float(value)
	text = str(value).strip()
	match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:\.(\d+))?", text)
	if not match:
		return None
	hours = int(match.group(1) or 0)
	minutes = int(match.group(2))
	seconds = int(match.group(3))
	fraction = float("0." + match.group(4)) if match.group(4) else 0.0
	return hours * 3600 + minutes * 60 + seconds + fraction


def _segment_start(segment: dict[str, Any]) -> float | None:
	return _time_to_sec(segment.get("source_start_sec") or segment.get("source_start"))


def _segment_end(segment: dict[str, Any]) -> float | None:
	return _time_to_sec(segment.get("source_end_sec") or segment.get("source_end"))


def _finding(
	rule_id: str,
	severity: str,
	segment: dict[str, Any],
	message: str,
	owner_node: str = "03/04 speaker attribution before VibeVoice",
) -> dict[str, Any]:
	return {
		"rule_id": rule_id,
		"severity": severity,
		"owner_node": owner_node,
		"segment_index": segment.get("segment_index") or segment.get("turn_index"),
		"speaker": segment.get("speaker"),
		"source_start": segment.get("source_start"),
		"source_end": segment.get("source_end"),
		"message": message,
		"source_text_excerpt": _normalize_text(segment.get("source_text"))[:220],
		"zh_text_excerpt": _normalize_text(segment.get("zh_text") or segment.get("text"))[:220],
	}


def _validate_roster_and_speakers(roster: dict[str, Any], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
	findings: list[dict[str, Any]] = []
	speaker_count = int(roster.get("speaker_count") or 0)
	roster_speakers = roster.get("speakers") if isinstance(roster.get("speakers"), dict) else {}
	expected = [f"Speaker {index}" for index in range(speaker_count)]
	if roster.get("status") != "frozen":
		findings.append({
			"rule_id": "speaker_roster_not_frozen",
			"severity": "FAIL",
			"owner_node": "02a speaker census",
			"message": "02a speaker roster is not frozen.",
		})
	if speaker_count < 1 or speaker_count > 4 or int(roster.get("voice_count") or 0) != speaker_count:
		findings.append({
			"rule_id": "speaker_roster_count_invalid",
			"severity": "FAIL",
			"owner_node": "02a speaker census",
			"message": "Speaker roster must contain 1-4 speakers and voice_count must equal speaker_count.",
		})
	if sorted(roster_speakers, key=str) != expected:
		findings.append({
			"rule_id": "speaker_roster_ids_not_contiguous",
			"severity": "FAIL",
			"owner_node": "02a speaker census",
			"message": f"Expected contiguous roster speakers {expected}, got {sorted(roster_speakers, key=str)}.",
		})
	for segment in segments:
		speaker = str(segment.get("speaker") or "")
		if speaker not in expected:
			findings.append(_finding(
				"translated_turn_speaker_not_in_roster",
				"FAIL",
				segment,
				f"Translated segment uses {speaker}, which is not present in the frozen roster.",
			))
	return findings


def _validate_two_speaker_host_guest_roles(
	segments: list[dict[str, Any]],
	host_speaker: str,
	guest_speaker: str,
) -> list[dict[str, Any]]:
	findings: list[dict[str, Any]] = []
	for segment in segments:
		speaker = str(segment.get("speaker") or "")
		zh_len, source_len = _segment_lengths(segment)
		answer_like = _is_answer_like(segment)
		host_question = _has_host_question_marker(segment)
		question_then_answer = _has_question_then_answer(segment)
		if speaker == host_speaker and answer_like and (zh_len >= 90 or source_len >= 120):
			findings.append(_finding(
				"host_label_on_long_guest_answer",
				"FAIL",
				segment,
				"Host/interviewer voice slot is assigned to an answer-like segment that is too long for a normal host prompt.",
			))
		if speaker == guest_speaker and question_then_answer and (zh_len >= 100 or source_len >= 160):
			findings.append(_finding(
				"mixed_host_question_and_guest_answer_in_one_turn",
				"FAIL",
				segment,
				"One source segment appears to combine a host question and guest answer; split it into separate speaker turns before VibeVoice.",
			))
		elif speaker == guest_speaker and host_question and not answer_like and zh_len <= 140:
			findings.append(_finding(
				"host_question_assigned_to_guest_voice",
				"FAIL",
				segment,
				"A short host-question-like turn is assigned to the guest voice slot.",
			))
	return findings


def _validate_adjacent_overlap(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
	findings: list[dict[str, Any]] = []
	for prev, current in zip(segments, segments[1:]):
		if prev.get("speaker") == current.get("speaker"):
			continue
		prev_start = _segment_start(prev)
		prev_end = _segment_end(prev)
		cur_start = _segment_start(current)
		cur_end = _segment_end(current)
		if prev_start is None or prev_end is None or cur_start is None or cur_end is None:
			continue
		overlap = min(prev_end, cur_end) - max(prev_start, cur_start)
		if overlap > 1.5 and (_is_answer_like(prev) or _is_answer_like(current)):
			findings.append({
				"rule_id": "overlapping_source_segments_with_speaker_flip",
				"severity": "WARN",
				"owner_node": "03/04 speaker attribution before VibeVoice",
				"segments": [
					prev.get("segment_index") or prev.get("turn_index"),
					current.get("segment_index") or current.get("turn_index"),
				],
				"speakers": [prev.get("speaker"), current.get("speaker")],
				"overlap_sec": round(overlap, 3),
				"message": "Adjacent source segments overlap while speaker labels flip; verify this is not rolling-caption diarization noise.",
			})
	return findings


def _load_segments(path: Path) -> list[dict[str, Any]]:
	data = _read_json(path)
	segments = data.get("segments")
	if not isinstance(segments, list):
		raise ValueError(f"Translated transcript has no segments list: {path}")
	return [segment for segment in segments if isinstance(segment, dict)]


def _write_report(run_dir: Path, result: dict[str, Any]) -> None:
	path = run_dir / NODE_DIRNAME / REPORT_FILENAME
	lines = [
		"# Speaker-Turn Roster Consistency Gate",
		"",
		f"- status: {result['status']}",
		f"- speaker_count: {result['summary'].get('speaker_count')}",
		f"- segment_count: {result['summary'].get('segment_count')}",
		f"- fail_findings: {result['summary'].get('fail_findings')}",
		f"- warn_findings: {result['summary'].get('warn_findings')}",
		f"- host_speaker: {result['role_inference'].get('host_speaker')}",
		f"- guest_speaker: {result['role_inference'].get('guest_speaker')}",
		"",
		"## Findings",
		"",
	]
	if not result["findings"]:
		lines.append("- none")
	for finding in result["findings"]:
		lines.append(
			f"- [{finding.get('severity')}] {finding.get('rule_id')}: "
			f"segment={finding.get('segment_index') or finding.get('segments')} "
			f"speaker={finding.get('speaker') or finding.get('speakers')} "
			f"{finding.get('message')}"
		)
	lines.extend([
		"",
		"## Repair Guidance",
		"",
		"- Repair 03/03b speaker attribution and split mixed host-question plus guest-answer turns.",
		"- Regenerate 04 podcast script, rerun this 03e gate, then rerun 05 and all downstream dependent nodes.",
	])
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_gate(run_dir: Path) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	roster_path = _resolve_roster_path(run_dir)
	translation_path = _active_translation_path(run_dir)
	roster = _read_json(roster_path)
	segments = _load_segments(translation_path)
	findings = _validate_roster_and_speakers(roster, segments)
	host_speaker, guest_speaker, role_evidence = _infer_two_speaker_roles(roster)
	speaker_count = int(roster.get("speaker_count") or 0)
	if speaker_count == 2:
		if host_speaker and guest_speaker:
			findings.extend(_validate_two_speaker_host_guest_roles(segments, host_speaker, guest_speaker))
		elif _is_explicit_two_speaker_co_speaker_roster(role_evidence):
			pass
		else:
			findings.append({
				"rule_id": "two_speaker_host_guest_roles_uncertain",
				"severity": "FAIL",
				"owner_node": "02a speaker census / 03 speaker attribution",
				"message": "Exactly-two-speaker run cannot infer a stable host/interviewer versus guest/expert role from the frozen roster.",
			})
	findings.extend(_validate_adjacent_overlap(segments))
	fail_count = sum(1 for finding in findings if finding.get("severity") == "FAIL")
	warn_count = sum(1 for finding in findings if finding.get("severity") == "WARN")
	status = "PASS" if fail_count == 0 else "FAIL"
	input_paths = _optional_input_paths(run_dir, roster_path, translation_path)
	result = {
		"schema_version": "worldview-china-speaker-turn-roster-consistency.v1",
		"status": status,
		"created_at": datetime.now(timezone.utc).isoformat(),
		"run_dir": str(run_dir),
		"node": NODE_DIRNAME,
		"roster_path": _relative(run_dir, roster_path),
		"active_translation_path": _relative(run_dir, translation_path),
		"input_file_hashes": _input_hashes(run_dir, input_paths),
		"role_inference": {
			"host_speaker": host_speaker,
			"guest_speaker": guest_speaker,
			"co_speaker_mode": speaker_count == 2 and _is_explicit_two_speaker_co_speaker_roster(role_evidence),
			"role_evidence": role_evidence,
			"policy": (
				"explicit_two_speaker_co_speaker_discussion_no_host_guest_heuristics"
				if speaker_count == 2 and _is_explicit_two_speaker_co_speaker_roster(role_evidence)
				else "exactly_two_speakers_host_guest_deterministic_heuristics"
			),
		},
		"summary": {
			"speaker_count": speaker_count,
			"segment_count": len(segments),
			"fail_findings": fail_count,
			"warn_findings": warn_count,
			"finding_count": len(findings),
		},
		"findings": findings,
		"repair_guidance_for_parent": [
			"Repair source/Chinese speaker attribution before VibeVoice.",
			"Split any mixed host question and guest answer into separate speaker turns.",
			"Regenerate source_transcript.zh.json or source_transcript.zh.safe.json, podcast_script.md, script_turns.json, chunk plan, audio, subtitles, video and QA.",
		] if fail_count else [],
	}
	_write_json(run_dir / NODE_DIRNAME / RESULT_FILENAME, result)
	_write_report(run_dir, result)
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Gate 03/04 speaker-turn attribution against the frozen 02a speaker roster.")
	parser.add_argument("--run-dir", required=True, type=Path)
	args = parser.parse_args()
	result = run_gate(args.run_dir.expanduser().resolve())
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
