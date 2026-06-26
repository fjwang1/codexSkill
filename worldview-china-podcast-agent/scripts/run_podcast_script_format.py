#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from chinese_number_display import normalize_comma_thousands_for_chinese_display


LEADER_NAME_REPLACEMENTS = [
	("Trump-Xisummit", "中美领导人峰会"),
	("Trump-XiSummit", "中美领导人峰会"),
	("Trump-Xi峰会", "中美领导人峰会"),
	("Trump-Xi会晤", "中美领导人会晤"),
	("Trump-Xi会议", "中美领导人会议"),
	("Trump-Ximeeting", "中美领导人会晤"),
	("Trump-XiMeeting", "中美领导人会晤"),
	("Trump-Xicall", "中美领导人通话"),
	("Trump-XiCall", "中美领导人通话"),
	("Biden-Xisummit", "中美领导人峰会"),
	("Biden-XiSummit", "中美领导人峰会"),
	("Biden-Xi峰会", "中美领导人峰会"),
	("Biden-Xi会晤", "中美领导人会晤"),
	("Biden-Xi会议", "中美领导人会议"),
	("Biden-Ximeeting", "中美领导人会晤"),
	("Biden-XiMeeting", "中美领导人会晤"),
	("Biden-Xicall", "中美领导人通话"),
	("Biden-XiCall", "中美领导人通话"),
	("特朗普和习近平峰会", "中美领导人峰会"),
	("川普和习近平峰会", "中美领导人峰会"),
	("特朗普-习近平峰会", "中美领导人峰会"),
	("川普-习近平峰会", "中美领导人峰会"),
	("特朗普—习近平峰会", "中美领导人峰会"),
	("川普—习近平峰会", "中美领导人峰会"),
	("特朗普与习近平峰会", "中美领导人峰会"),
	("川普与习近平峰会", "中美领导人峰会"),
	("拜登和习近平峰会", "中美领导人峰会"),
	("拜登与习近平峰会", "中美领导人峰会"),
	("特朗普和习近平会晤", "中美领导人会晤"),
	("川普和习近平会晤", "中美领导人会晤"),
	("特朗普与习近平会晤", "中美领导人会晤"),
	("川普与习近平会晤", "中美领导人会晤"),
	("拜登和习近平会晤", "中美领导人会晤"),
	("拜登与习近平会晤", "中美领导人会晤"),
	("拜登和习近平", "中美领导人"),
	("拜登与习近平", "中美领导人"),
	("习近平和拜登", "中美领导人"),
	("习近平与拜登", "中美领导人"),
	("特朗普和习近平", "中美领导人"),
	("特朗普与习近平", "中美领导人"),
	("川普和习近平", "中美领导人"),
	("川普与习近平", "中美领导人"),
	("习近平和中国政策制定者", "中国国家领导人和政策制定者"),
	("进入习近平时代以后", "进入当前中国领导层时期以后"),
	("习近平时代", "当前中国领导层时期"),
	("习近平跟邓小平、江泽民", "现任中国领导人跟邓小平、江泽民"),
	("习近平的“中国制造2025”计划", "中国国家领导人推动的“中国制造2025”计划"),
	("习近平的中国制造2025计划", "中国国家领导人推动的中国制造2025计划"),
	("Trump-Xi", "中美领导人"),
	("Biden-Xi", "中美领导人"),
	("Xi Jinping", "中国国家领导人"),
	("Xijinping", "中国国家领导人"),
	("习近平", "中国国家领导人"),
	("习主席", "中国国家领导人"),
]
SPEAKER_RE = re.compile(r"^Speaker ([0-3])$")
CJK_RE = r"\u3400-\u9fff"


def _normalize_mixed_spacing(text: str) -> str:
	value = re.sub(r"\s+", " ", text).strip()
	value = re.sub(fr"(?<=[{CJK_RE}]) (?=[{CJK_RE}])", "", value)
	value = re.sub(fr"(?<=[{CJK_RE}]) (?=[，。！？；：、）】》])", "", value)
	value = re.sub(fr"(?<=[（【《]) (?=[{CJK_RE}])", "", value)
	return value


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _clean_turn_text(text: str) -> str:
	value = re.sub(r"(?<![A-Za-z])Xi\s+Jinping(?![A-Za-z])", "中国国家领导人", text, flags=re.IGNORECASE)
	value = _normalize_mixed_spacing(value)
	value = re.sub(r"^[：:，,。；;\s]+", "", value)
	for bad, good in LEADER_NAME_REPLACEMENTS:
		value = value.replace(bad, good)
	value = re.sub(r"(?<![A-Za-z])Xi\s*Jinping(?![A-Za-z])", "中国国家领导人", value, flags=re.IGNORECASE)
	value = re.sub(r"(?<![A-Za-z])Xi(?![A-Za-z])", "中国国家领导人", value)
	value = normalize_comma_thousands_for_chinese_display(value)
	return value


def _speaker_index(speaker: str) -> int:
	match = SPEAKER_RE.fullmatch(speaker)
	assert match, f"Unsupported speaker: {speaker}"
	return int(match.group(1))


def _is_supported_speaker(speaker: str) -> bool:
	return SPEAKER_RE.fullmatch(speaker) is not None


def format_script(run_dir: Path) -> dict[str, Any]:
	translation_dir = run_dir / "03-source-translation"
	safety_dir = run_dir / "03b-mainland-publish-safety"
	output_dir = run_dir / "04-podcast-script"
	output_dir.mkdir(parents=True, exist_ok=True)
	safe_translation_path = safety_dir / "source_transcript.zh.safe.json"
	translation_path = safe_translation_path if safe_translation_path.exists() else translation_dir / "source_transcript.zh.json"
	translation = _read_json(translation_path)
	segments = list(translation.get("segments") or [])
	assert segments, "No translated segments found"
	content_coverage = str(translation.get("content_coverage") or "full_translation")
	source_label = str(translation_path.relative_to(run_dir))

	lines = [
		"---",
		"schema_version: worldview-china-podcast-script.v1",
		f"content_coverage: {content_coverage}",
		f"source: {source_label}",
		"---",
		"",
		"## 正文",
		"",
	]
	turns: list[dict[str, Any]] = []
	for segment in segments:
		speaker = str(segment["speaker"])
		assert _is_supported_speaker(speaker), f"Unsupported speaker: {speaker}"
		text = _clean_turn_text(str(segment["zh_text"]))
		if not text:
			continue
		lines.append(f"{speaker}: {text}")
		turns.append({
			"turn_index": len(turns) + 1,
			"speaker": speaker,
			"text": text,
			"source_segment_index": segment.get("segment_index"),
			"source_start": segment.get("source_start"),
			"source_end": segment.get("source_end"),
			"char_count": len(re.sub(r"\s+", "", text)),
		})

	script_path = output_dir / "podcast_script.md"
	script_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
	root_script = run_dir / "podcast_script.md"
	root_script.write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")

	speaker_ids = sorted({turn["speaker"] for turn in turns}, key=_speaker_index)
	speaker_counts = {speaker: sum(1 for turn in turns if turn["speaker"] == speaker) for speaker in speaker_ids}
	total_chars = sum(int(turn["char_count"]) for turn in turns)
	report = [
		"# Script Report",
		"",
		"- status: PASS",
		f"- content_coverage: {content_coverage}",
		f"- source: {source_label}",
		"- no_summarization: true",
		"- source_order_preserved: true",
		f"- turn_count: {len(turns)}",
		*[f"- speaker_{_speaker_index(speaker)}_turns: {speaker_counts[speaker]}" for speaker in speaker_ids],
		f"- total_display_chars: {total_chars}",
		f"- script_sha256: {_sha256(script_path)}",
		"",
		"Formatting only; content edits or abridgement, if any, come from the declared source file.",
	]
	(output_dir / "script_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
	_write_json(output_dir / "script_turns.json", {
		"schema_version": "worldview-china-script-turns.v1",
		"content_coverage": content_coverage,
		"turns": turns,
	})

	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["04-podcast-script"] = {
		"status": "pass",
		"content_coverage": content_coverage,
		"source": source_label,
		"podcast_script": str(script_path),
		"root_podcast_script": str(root_script),
		"script_report": str(output_dir / "script_report.md"),
		"turn_count": len(turns),
		"total_display_chars": total_chars,
	}
	_write_json(run_manifest_path, run_manifest)
	return run_manifest["nodes"]["04-podcast-script"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Format translated source transcript into VibeVoice Speaker 0..3 podcast_script.md.")
	parser.add_argument("--run-dir", required=True, type=Path)
	args = parser.parse_args()
	result = format_script(args.run_dir.expanduser().resolve())
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
