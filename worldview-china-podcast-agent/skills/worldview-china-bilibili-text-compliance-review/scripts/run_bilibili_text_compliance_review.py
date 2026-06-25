#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OUTPUT_DIRNAME = "04c-bilibili-text-compliance"
RESULT_NAME = "text-compliance-review-result.json"
REPORT_NAME = "text-compliance-review-report.md"


@dataclass(frozen=True)
class Rule:
	rule_id: str
	severity: str
	pattern: re.Pattern[str]
	message: str
	suggestion: str


RULES = [
	Rule(
		rule_id="forbidden_chinese_contemporary_leader_name_zh",
		severity="fail",
		pattern=re.compile(r"习近平|习主席"),
		message="Generated or publishable text contains a specific Chinese contemporary national leader name.",
		suggestion="按语境改为自然统称，例如 中国国家领导人、中方领导人、中美领导人会晤。",
	),
	Rule(
		rule_id="forbidden_chinese_contemporary_leader_name_en",
		severity="fail",
		pattern=re.compile(r"\bXi\s+Jinping\b|\bXijinping\b|\bXi(?:'s)?\b"),
		message="Generated or publishable text contains a specific Chinese contemporary national leader English name.",
		suggestion="按语境改为 natural generic wording; for diplomatic phrases use 中美领导人会晤 / Chinese leader where appropriate.",
	),
	Rule(
		rule_id="wrong_chinese_mainland_english_term",
		severity="fail",
		pattern=re.compile(r"\b[Mm]ainland China\b"),
		message="English wording for 中国大陆 uses a disallowed form.",
		suggestion="Use Chinese mainland, China's mainland, or the mainland of China.",
	),
	Rule(
		rule_id="wrong_nanjing_memorial_name",
		severity="fail",
		pattern=re.compile(r"南京大屠杀纪念馆"),
		message="Specific venue name is not standardized.",
		suggestion="Use 侵华日军南京大屠杀遇难同胞纪念馆.",
	),
	Rule(
		rule_id="wrong_xinjiang_autonomous_region_name",
		severity="fail",
		pattern=re.compile(r"新疆维吾尔族自治区"),
		message="Autonomous region name is not standardized.",
		suggestion="Use 新疆维吾尔自治区.",
	),
	Rule(
		rule_id="taiwan_hongkong_abbreviation",
		severity="fail",
		pattern=re.compile(r"(?<!中国)台湾|(?<!中国)香港"),
		message="Generated or publishable text uses abbreviated Taiwan/Hong Kong wording.",
		suggestion="统一改为完整称呼：中国台湾、中国香港。",
	),
	Rule(
		rule_id="taiwan_named_as_country",
		severity="fail",
		pattern=re.compile(r"(?:中国台湾[^。！？\n]{0,40}(?:这个国家|我们的国家|我国|国家安全)|(?:这些|那些|其他|多个|许多)?国家[^。！？\n]{0,80}中国台湾)"),
		message="Taiwan is described or grouped as a country in generated or publishable text.",
		suggestion="使用中国台湾，并重写并列结构或所属关系，避免把中国台湾称为国家。",
	),
	Rule(
		rule_id="high_risk_xinjiang_religion_accusation",
		severity="fail",
		pattern=re.compile(r"种族灭绝|压迫(?:穆斯林|维吾尔|维吾尔人|维吾尔族|乌格尔|胡族)|中国政府如何对待穆斯林|政府[^。！？\n]{0,30}秘密压迫|政府对维吾尔人所做的事情"),
		message="Generated or publishable text contains high-risk Xinjiang / ethnic religion / government oppression accusations.",
		suggestion="回到 03b 做发布安全删改、弱化或桥接；不要把这类表达送入 TTS、字幕、标题或投稿文案。",
	),
	Rule(
		rule_id="high_risk_ideological_confrontation",
		severity="fail",
		pattern=re.compile(r"不敬虔的共产主义者|无神论(?:的)?共产主义|共产主义者[^。！？\n]{0,30}无神论|以中国为首的世界秩序"),
		message="Generated or publishable text contains high-risk ideological confrontation wording.",
		suggestion="回到 03b 做发布安全弱化，保留可发布的事实主线，不放大意识形态对抗。",
	),
	Rule(
		rule_id="sensitive_chinese_leader_name_needs_rewrite",
		severity="fail",
		pattern=re.compile(r"江泽民|胡锦涛|毛泽东|邓小平"),
		message="Generated or publishable text contains a Chinese national leader name that needs publish-safety review or may be a transcription error.",
		suggestion="核对原文；若是误植则修正，若非必要则按语境改为中性统称或在 03b 做安全处理。",
	),
	Rule(
		rule_id="polarizing_bilibili_title_or_metadata",
		severity="fail",
		pattern=re.compile(r"押注中国吗|该押注中国|押注中国"),
		message="Title, cover, or metadata contains polarizing stance/vote wording.",
		suggestion="改为基于内容的冲突、后果或观点标题，避免让宗教/族群/政治主体对中国做站队式表态。",
	),
]


TEXT_CANDIDATES = [
	"03-source-translation/source_transcript.zh.md",
	"03-source-translation/source_transcript.zh.json",
	"03-source-translation/chapter_segments.json",
	"03b-mainland-publish-safety/source_transcript.zh.safe.md",
	"03b-mainland-publish-safety/source_transcript.zh.safe.json",
	"03b-mainland-publish-safety/chapter_segments.safe.json",
	"03b-mainland-publish-safety/edit_decisions.json",
	"03b-mainland-publish-safety/safety_report.md",
	"04-podcast-script/podcast_script.md",
	"04-podcast-script/script_turns.json",
	"04-podcast-script/script_report.md",
	"podcast_script.md",
	"video_title.txt",
	"cover/cover_title.json",
	"bilibili_upload_metadata.json",
	"publish_info.txt",
	"audio/audio_manifest.json",
	"video/subtitle_manifest.json",
	"video/final_subtitles.srt",
	"video/final_subtitles.ass",
]


SKIP_JSON_TEXT_KEYS = {
	"audio",
	"cover_path",
	"file",
	"final_audio",
	"hash",
	"original_text",
	"original_title",
	"path",
	"raw_text",
	"reference_text",
	"schema_version",
	"sha256",
	"source_end",
	"source_episode_video",
	"source_original_text",
	"source_start",
	"source_text",
	"source_title",
	"text_preview",
	"url",
	"video_path",
	"voice_prompt_manifest",
	"webpage_url",
}


def _read_text(path: Path) -> str:
	return path.read_text(encoding="utf-8", errors="replace")


def _iter_publishable_json_strings(value: Any, key: str = "") -> list[str]:
	if key in SKIP_JSON_TEXT_KEYS:
		return []
	if isinstance(value, dict):
		strings: list[str] = []
		for child_key, child_value in value.items():
			strings.extend(_iter_publishable_json_strings(child_value, str(child_key)))
		return strings
	if isinstance(value, list):
		strings = []
		for item in value:
			strings.extend(_iter_publishable_json_strings(item, key))
		return strings
	if isinstance(value, str):
		return [value]
	return []


def _read_publishable_text(path: Path) -> str:
	text = _read_text(path)
	if path.suffix != ".json":
		return text
	try:
		payload = json.loads(text)
	except json.JSONDecodeError:
		return text
	return "\n".join(_iter_publishable_json_strings(payload))


def _line_number(text: str, index: int) -> int:
	return text.count("\n", 0, index) + 1


def _line_excerpt(text: str, index: int) -> str:
	start = text.rfind("\n", 0, index) + 1
	end = text.find("\n", index)
	if end == -1:
		end = len(text)
	return text[start:end].strip()[:240]


def _iter_existing_inputs(run_dir: Path) -> list[Path]:
	paths: list[Path] = []
	for relative in TEXT_CANDIDATES:
		path = run_dir / relative
		if path.exists() and path.is_file():
			paths.append(path)
	return paths


def _find_rule_hits(path: Path, text: str) -> list[dict[str, Any]]:
	findings: list[dict[str, Any]] = []
	for rule in RULES:
		for match in rule.pattern.finditer(text):
			findings.append({
				"rule_id": rule.rule_id,
				"severity": rule.severity,
				"file": str(path),
				"line": _line_number(text, match.start()),
				"match": match.group(0),
				"excerpt": _line_excerpt(text, match.start()),
				"message": rule.message,
				"suggestion": rule.suggestion,
			})
	return findings


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_report(path: Path, result: dict[str, Any]) -> None:
	lines = [
		"# Bilibili Text Compliance Review",
		"",
		f"- status: {result['status']}",
		f"- stage: {result['stage']}",
		f"- reviewed_files: {len(result['reviewed_files'])}",
		f"- fail_findings: {result['summary']['fail_findings']}",
		"",
	]
	if result["findings"]:
		lines.append("## Findings")
		for finding in result["findings"]:
			lines.extend([
				f"- {finding['severity'].upper()} {finding['rule_id']}",
				f"  - file: {finding['file']}:{finding['line']}",
				f"  - match: {finding['match']}",
				f"  - excerpt: {finding['excerpt']}",
				f"  - suggestion: {finding['suggestion']}",
			])
		lines.append("")
	else:
		lines.append("No deterministic rule violations found.")
		lines.append("")
	lines.extend([
		"## Required Manual Review",
		"",
		"An independent review agent must also inspect whether context-sensitive Bilibili/mainland publication safety edits were preserved and whether newly generated titles, cover text, subtitles, or metadata introduced risky wording not covered by deterministic patterns.",
		"",
	])
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_review(run_dir: Path, stage: str = "after_script", reviewer: str = "deterministic_script") -> dict[str, Any]:
	inputs = _iter_existing_inputs(run_dir)
	findings: list[dict[str, Any]] = []
	for path in inputs:
		findings.extend(_find_rule_hits(path, _read_publishable_text(path)))
	fail_findings = [finding for finding in findings if finding["severity"] == "fail"]
	status = "PASS" if not fail_findings else "FAIL"
	result = {
		"schema_version": "worldview-china-bilibili-text-compliance-review.v1",
		"status": status,
		"stage": stage,
		"reviewer": reviewer,
		"reviewed_files": [str(path) for path in inputs],
		"rules": [
			{
				"rule_id": rule.rule_id,
				"severity": rule.severity,
				"message": rule.message,
				"suggestion": rule.suggestion,
			}
			for rule in RULES
		],
		"summary": {
			"reviewed_file_count": len(inputs),
			"finding_count": len(findings),
			"fail_findings": len(fail_findings),
		},
		"findings": findings,
	}
	output_dir = run_dir / OUTPUT_DIRNAME
	_write_json(output_dir / RESULT_NAME, result)
	_write_report(output_dir / REPORT_NAME, result)
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Run Bilibili text compliance review for a Worldview China podcast run.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--stage", default="after_script")
	parser.add_argument("--reviewer", default="deterministic_script")
	args = parser.parse_args()
	result = run_review(args.run_dir.expanduser().resolve(), stage=args.stage, reviewer=args.reviewer)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
