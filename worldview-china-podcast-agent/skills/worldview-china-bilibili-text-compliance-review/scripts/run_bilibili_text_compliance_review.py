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
		rule_id="online_religious_proselytizing_or_conversion",
		severity="fail",
		pattern=re.compile(r"达瓦|街头达瓦|宣教|传教|外展活动|邀请桌|带你们参观清真寺|清真寺[^。！？\n]{0,24}(?:参观|讨论|外展)|皈依(?:了)?伊斯兰教|想要皈依|选择伊斯兰教作为(?:他们|自己|我的)?(?:的)?宗教"),
		message="Generated or publishable text contains online religious proselytizing, outreach, or conversion guidance risk.",
		suggestion="回到 03b 做最小必要删改；正式 B 站稿不得呈现达瓦/宣教/传教、清真寺外展邀请、皈依路径或引导信教内容。",
	),
	Rule(
		rule_id="online_religious_truth_or_mental_relief_claim",
		severity="fail",
		pattern=re.compile(r"伊斯兰教[^。！？\n]{0,24}(?:是真理|更和平|符合我的信仰)|宗教[^。！？\n]{0,36}(?:精神上的解脱|补救措施|解决方案)|(?:心理障碍|精神危机|生存危机|抑郁症|自杀率)[^。！？\n]{0,60}宗教"),
		message="Generated or publishable text frames religion as truth, superiority, or a remedy for mental/spiritual crisis.",
		suggestion="回到 03b 弱化为中性社会观察或直接 cut；不得把特定宗教包装成更和平、更真理或心理危机解决方案。",
	),
	Rule(
		rule_id="online_religious_doctrine_or_teaching_promotion",
		severity="fail",
		pattern=re.compile(r"伊斯兰(?:知识|讲座|课程)|真正的伊斯兰知识|教授[^。！？\n]{0,36}伊斯兰|传播[^。！？\n]{0,36}(?:伊斯兰|宗教|教义)|(?:教义|教规|宗教礼仪)[^。！？\n]{0,48}(?:传播|教授|宣扬|讲解)|伊斯兰文明进入现代中国强国"),
		message="Generated or publishable text promotes religious doctrine, lectures, courses, or teaching materials.",
		suggestion="回到 03b 做删改或概括为非教学性的文化/社群观察；不得在 TTS、字幕、标题、封面或简介中展示宗教教义传播和学习路径。",
	),
	Rule(
		rule_id="online_religious_commercial_promotion",
		severity="fail",
		pattern=re.compile(r"符合伊斯兰教法[^。！？\n]{0,80}(?:投资|房地产|公司)|以宗教名义[^。！？\n]{0,48}(?:商业|营销|销售|经销|宣传)|宗教用品|清真寺[^。！？\n]{0,48}(?:筹款|捐款|投资|商业)"),
		message="Generated or publishable text contains religion-themed commercial promotion risk.",
		suggestion="回到 03b 删除赞助、广告或宗教名义商业推广；不得把宗教合规、宗教用品、清真寺/宗教机构商业活动作为投稿内容。",
	),
	Rule(
		rule_id="high_risk_private_recording_or_no_upload_phrase",
		severity="fail",
		pattern=re.compile(r"(?:请(?:不要|勿)|不要|不得|不能)[^。！？\n]{0,16}(?:上传|发到|放到|发布)[^。！？\n]{0,16}(?:互联网|网上|网络|社交媒体|平台)|(?:不要|不得|不能)[^。！？\n]{0,16}(?:拍摄视频|实际拍摄视频)|只能[^。！？\n]{0,20}(?:MP3|音频)[^。！？\n]{0,20}(?:录制|流通)"),
		message="Generated or publishable text repeats a source speaker's private-recording / do-not-upload safety phrase.",
		suggestion="回到 03b/04 做最小必要删改或桥接，例如改写为较私密的学习场景、公开表达受限等中性表述。",
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
	Rule(
		rule_id="bilibili_description_production_note",
		severity="fail",
		pattern=re.compile(r"中文配音版本|保留原视频画面|替换为中文对话音频|方便中文观众理解原对话内容|外网公开播客/访谈视频制作"),
		message="Bilibili description contains production-method filler instead of an episode content summary.",
		suggestion="把简介改成面向观众的内容说明：本集谈了什么、冲突或问题是什么、核心看点是什么；不要描述制作流程。",
	),
	Rule(
		rule_id="chinese_display_comma_thousands_number",
		severity="fail",
		pattern=re.compile(r"(?:[\u4e00-\u9fff][^。！？\n]{0,24}\d{1,3}(?:,\d{3})+|\d{1,3}(?:,\d{3})+[^。！？\n]{0,24}[\u4e00-\u9fff])"),
		message="Chinese publishable text contains comma-separated large numbers, which are risky for TTS and subtitle display.",
		suggestion="把中文稿、字幕和投稿文案里的千分位数字改成中文自然写法：300,000 -> 30万；3,000 -> 3000；普通 300 不要改成 0.03万。",
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
	"07-subtitles/subtitle_manifest.json",
	"07-subtitles/final_subtitles.srt",
	"07-subtitles/final_subtitles.ass",
	"07-subtitles/final_subtitles_1x.srt",
	"07-subtitles/final_subtitles_1x.ass",
	"08-source-video-revoice/subtitles/final_subtitles.srt",
	"08-source-video-revoice/subtitles/final_subtitles.ass",
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
		"An independent review agent must also inspect whether context-sensitive Bilibili/mainland publication safety edits were preserved; whether religious content is only neutral culture/social observation rather than proselytizing, conversion guidance, doctrine teaching, ritual instruction, or religion-as-remedy framing; and whether newly generated titles, cover text, subtitles, or metadata introduced risky wording not covered by deterministic patterns.",
		"",
	])
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_review(
	run_dir: Path,
	stage: str = "after_script",
	reviewer: str = "deterministic_script",
	output_dirname: str = OUTPUT_DIRNAME,
) -> dict[str, Any]:
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
	output_dir = run_dir / output_dirname
	_write_json(output_dir / RESULT_NAME, result)
	_write_report(output_dir / REPORT_NAME, result)
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Run Bilibili text compliance review for a Worldview China podcast run.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--stage", default="after_script")
	parser.add_argument("--reviewer", default="deterministic_script")
	parser.add_argument("--output-dirname", default=OUTPUT_DIRNAME)
	args = parser.parse_args()
	result = run_review(
		args.run_dir.expanduser().resolve(),
		stage=args.stage,
		reviewer=args.reviewer,
		output_dirname=args.output_dirname,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
