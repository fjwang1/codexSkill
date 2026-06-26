#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "wechat-article-compliance-review.v1"


@dataclass(frozen=True)
class Rule:
	rule_id: str
	severity: str
	pattern: re.Pattern[str]
	message: str
	suggestion: str


AUTO_REPLACEMENTS = [
	("习近平", "中国国家领导人", "replace_current_chinese_leader_name"),
	("习主席", "中国国家领导人", "replace_current_chinese_leader_title"),
	("Xi Jinping", "Chinese leader", "replace_current_chinese_leader_name_en"),
	("mainland China", "Chinese mainland", "replace_mainland_china_en"),
	("Mainland China", "Chinese mainland", "replace_mainland_china_en_cap"),
	("南京大屠杀纪念馆", "侵华日军南京大屠杀遇难同胞纪念馆", "replace_nanjing_memorial"),
	("新疆维吾尔族自治区", "新疆维吾尔自治区", "replace_xinjiang_region"),
]

AUTO_REGEX_REPLACEMENTS = [
	(
		re.compile(r"(?<!中国)台湾(?!海峡|问题|当局|地区)"),
		"中国台湾",
		"replace_taiwan_standalone",
	),
	(
		re.compile(r"(?<!中国)香港(?!交易所|美元|上市|市场|地区)"),
		"中国香港",
		"replace_hongkong_standalone",
	),
]


RULES = [
	Rule(
		"visible_source_note_forbidden",
		"fail",
		re.compile(r"(?!)"),
		"Article body must not include a visible source note, original-title block, or original URL block.",
		"Move source publication, original title, original URL, and authorization basis to metadata/reports only.",
	),
	Rule(
		"privacy_personal_data",
		"fail",
		re.compile(r"\b\d{17}[\dXx]\b|(?:身份证号|家庭住址|手机号)[:：]?\s*\d{6,}"),
		"Article appears to contain private personal identifiers or contact details.",
		"Remove private personal data unless it is necessary, public, and legally publishable.",
	),
	Rule(
		"porn_gambling_drugs_illegal",
		"fail",
		re.compile(r"色情|淫秽|裸聊|博彩|赌博|赌球|六合彩|毒品|冰毒|海洛因|贩毒|枪支买卖|买卖枪支"),
		"Article contains obvious prohibited or high-risk illegal/vulgar terms.",
		"Delete or rewrite the passage unless it is clearly neutral news reporting and necessary.",
	),
	Rule(
		"graphic_violence_gore",
		"fail",
		re.compile(r"血腥|肢解|虐杀|极端暴力|自杀教程|杀人教程"),
		"Article may contain graphic violence or self-harm instruction risk.",
		"Remove instructional or graphic detail; keep only necessary neutral reporting.",
	),
	Rule(
		"taiwan_hongkong_abbreviation",
		"fail",
		re.compile(r"(?<!中国)台湾(?!海峡|问题|当局|地区)|(?<!中国)香港(?!交易所|美元|上市|市场|地区)"),
		"Publishable text uses abbreviated Taiwan/Hong Kong wording.",
		"Use 中国台湾 / 中国香港 where political geography is meant; verify non-political proper nouns manually.",
	),
	Rule(
		"taiwan_named_as_country",
		"fail",
		re.compile(r"(?:中国台湾[^。！？\n]{0,40}(?:这个国家|我们的国家|我国|国家安全)|(?:这些|那些|其他|多个|许多)?国家[^。！？\n]{0,80}中国台湾)"),
		"China Taiwan is described or grouped as a country.",
		"Rewrite the grouping or relation so 中国台湾 is not described as a country.",
	),
	Rule(
		"forbidden_current_chinese_leader_name_remaining",
		"fail",
		re.compile(r"习近平|习主席|\bXi\s+Jinping\b|\bXi(?:'s)?\b"),
		"Current Chinese national leader name remains after auto replacement.",
		"Use a natural generic term if the reference is necessary; otherwise remove.",
	),
	Rule(
		"high_risk_xinjiang_ethnicity_religion",
		"fail",
		re.compile(r"种族灭绝|集中营|强迫劳动|压迫(?:穆斯林|维吾尔|维吾尔人|维吾尔族)|新疆[^。！？\n]{0,60}(?:镇压|迫害|人权灾难)"),
		"High-risk Xinjiang / ethnicity / religion accusation appears in publishable text.",
		"Soften, attribute, or cut unless essential to the article and carefully contextualized.",
	),
	Rule(
		"religious_proselytizing_or_doctrine",
		"fail",
		re.compile(r"达瓦|宣教|传教|皈依|引导信教|宗教课程|传播教义|清真寺[^。！？\n]{0,30}(?:邀请|外展|课程)|(?:宗教|伊斯兰教|基督教)[^。！？\n]{0,30}(?:是真理|更和平|解决精神危机)"),
		"Internet religious information service risk.",
		"Cut or rewrite as neutral social/cultural observation; do not teach, promote, or invite religious participation.",
	),
	Rule(
		"defamation_insult_risk",
		"fail",
		re.compile(r"(?:骗子|汉奸|卖国贼|走狗|畜生|垃圾|恶棍|罪犯)[^。！？\n]{0,30}(?:公司|集团|个人|官员|记者|作者|创始人|CEO)"),
		"Potential insult or defamation risk.",
		"Use neutral, attributed wording and avoid personal humiliation or unsupported criminal labels.",
	),
	Rule(
		"comma_thousands_number",
		"warn",
		re.compile(r"\d{1,3}(?:,\d{3})+"),
		"Comma-separated number appears in Chinese publishable text.",
		"Convert to natural Chinese display if possible, or remove the comma.",
	),
	Rule(
		"sensational_title_or_clickbait",
		"warn",
		re.compile(r"震惊|炸裂|崩了|完了|惊天|内幕曝光|全网疯传|彻底摊牌"),
		"Sensational/clickbait wording may increase platform risk and reduce trust.",
		"Use a restrained factual title or subhead.",
	),
]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Review a WeChat article markdown draft for mainland/WeChat publishability.")
	source = parser.add_mutually_exclusive_group(required=True)
	source.add_argument("--article-dir", type=Path, help="Article directory containing wechat/article.md.")
	source.add_argument("--article-md", type=Path, help="WeChat article Markdown file.")
	parser.add_argument("--metadata", type=Path, help="Optional wechat/article_metadata.json.")
	parser.add_argument("--output-dir", type=Path, help="Defaults to the Markdown file's directory.")
	return parser.parse_args()


def resolve_inputs(args: argparse.Namespace) -> tuple[Path | None, Path, Path | None, Path]:
	article_dir: Path | None = None
	if args.article_dir:
		article_dir = args.article_dir.expanduser().resolve()
		article_md = article_dir / "wechat" / "article.md"
	else:
		article_md = args.article_md.expanduser().resolve()
		if article_md.parent.name == "wechat":
			article_dir = article_md.parent.parent
	metadata = args.metadata.expanduser().resolve() if args.metadata else None
	if metadata is None and article_dir is not None:
		candidate = article_dir / "wechat" / "article_metadata.json"
		if candidate.exists():
			metadata = candidate
	output_dir = args.output_dir.expanduser().resolve() if args.output_dir else article_md.parent
	return article_dir, article_md, metadata, output_dir


def load_json(path: Path | None) -> dict[str, Any]:
	if path is None or not path.exists():
		return {}
	data = json.loads(path.read_text(encoding="utf-8"))
	return data if isinstance(data, dict) else {}


def sha256_text(value: str) -> str:
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def apply_replacements(text: str) -> tuple[str, list[dict[str, str]]]:
	changes: list[dict[str, str]] = []
	for old, new, rule_id in AUTO_REPLACEMENTS:
		count = text.count(old)
		if count:
			text = text.replace(old, new)
			changes.append({"rule_id": rule_id, "old": old, "new": new, "count": str(count)})
	for pattern, replacement, rule_id in AUTO_REGEX_REPLACEMENTS:
		text, count = pattern.subn(replacement, text)
		if count:
			changes.append({"rule_id": rule_id, "old": pattern.pattern, "new": replacement, "count": str(count)})
	return text, changes


def has_visible_source_note(text: str, metadata: dict[str, Any]) -> bool:
	urls = [metadata.get("original_url"), metadata.get("source_url")]
	if any(isinstance(url, str) and url and url in text for url in urls):
		return True
	for line in text.splitlines():
		stripped = line.strip()
		if re.match(r"^(?:来源|原文|原题|原载|出处|Source|Original)\s*[:：]", stripped):
			return True
		if re.match(r"^(?:本文(?:来自|编译自|译自)|编译自|译自|原载于)", stripped):
			return True
	return False


def line_number(text: str, index: int) -> int:
	return text.count("\n", 0, index) + 1


def line_excerpt(text: str, index: int) -> str:
	start = text.rfind("\n", 0, index) + 1
	end = text.find("\n", index)
	if end == -1:
		end = len(text)
	return text[start:end].strip()[:240]


def scan_rules(text: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
	findings: list[dict[str, Any]] = []
	if has_visible_source_note(text, metadata):
		findings.append({
			"rule_id": "visible_source_note_forbidden",
			"severity": "fail",
			"line": 1,
			"match": "",
			"excerpt": "",
			"message": "Article body must not include a visible source note, original-title block, or original URL block.",
			"suggestion": "Move source publication, original title, original URL, and authorization basis to metadata/reports only.",
		})
	for rule in RULES:
		if rule.rule_id == "visible_source_note_forbidden":
			continue
		for match in rule.pattern.finditer(text):
			findings.append({
				"rule_id": rule.rule_id,
				"severity": rule.severity,
				"line": line_number(text, match.start()),
				"match": match.group(0)[:120],
				"excerpt": line_excerpt(text, match.start()),
				"message": rule.message,
				"suggestion": rule.suggestion,
			})
	return findings


def render_report(result: dict[str, Any]) -> str:
	lines = [
		"# WeChat Article Compliance Review",
		"",
		f"- Status: `{result['status']}`",
		f"- Article: `{result['article_markdown']}`",
		f"- Reviewed article: `{result['reviewed_article']}`",
		f"- Fail findings: `{result['fail_count']}`",
		f"- Warnings: `{result['warn_count']}`",
	]
	if result["auto_changes"]:
		lines.extend(["", "## Auto Changes"])
		for change in result["auto_changes"]:
			lines.append(f"- {change['rule_id']}: `{change['old']}` -> `{change['new']}` x {change['count']}")
	if result["findings"]:
		lines.extend(["", "## Findings"])
		for finding in result["findings"]:
			lines.append(
				f"- `{finding['severity']}` `{finding['rule_id']}` line {finding['line']}: "
				f"{finding['message']} Match: `{finding['match']}`"
			)
			if finding["excerpt"]:
				lines.append(f"  Excerpt: {finding['excerpt']}")
			lines.append(f"  Suggestion: {finding['suggestion']}")
	lines.extend(["", "## Editorial Note", "A deterministic PASS is not a legal guarantee. High-risk topics still need a human/editorial context review."])
	return "\n".join(lines) + "\n"


def update_metadata(metadata_path: Path | None, reviewed_path: Path, result_path: Path, report_path: Path, status: str) -> None:
	if metadata_path is None or not metadata_path.exists():
		return
	metadata = load_json(metadata_path)
	metadata.update({
		"reviewed_article_path": str(reviewed_path),
		"compliance_review_result_path": str(result_path),
		"compliance_review_report_path": str(report_path),
		"compliance_status": status,
		"compliance_reviewed_at": dt.datetime.now(dt.UTC).isoformat(),
	})
	metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
	args = parse_args()
	article_dir, article_md, metadata_path, output_dir = resolve_inputs(args)
	if not article_md.exists():
		raise SystemExit(f"Missing article markdown: {article_md}")
	metadata = load_json(metadata_path)
	original = article_md.read_text(encoding="utf-8")
	reviewed, auto_changes = apply_replacements(original)
	findings = scan_rules(reviewed, metadata)
	fail_count = sum(1 for item in findings if item["severity"] == "fail")
	warn_count = sum(1 for item in findings if item["severity"] == "warn")
	status = "PASS" if fail_count == 0 and warn_count == 0 else "PASS_WITH_WARNINGS" if fail_count == 0 else "FAIL"
	output_dir.mkdir(parents=True, exist_ok=True)
	reviewed_path = output_dir / "reviewed_article.md"
	result_path = output_dir / "compliance_review_result.json"
	report_path = output_dir / "compliance_review_report.md"
	reviewed_path.write_text(reviewed, encoding="utf-8")
	result = {
		"schema_version": SCHEMA_VERSION,
		"status": status,
		"article_dir": str(article_dir) if article_dir else None,
		"article_markdown": str(article_md),
		"metadata_path": str(metadata_path) if metadata_path else None,
		"reviewed_article": str(reviewed_path),
		"original_sha256": sha256_text(original),
		"reviewed_sha256": sha256_text(reviewed),
		"auto_changes": auto_changes,
		"findings": findings,
		"fail_count": fail_count,
		"warn_count": warn_count,
		"checked_at": dt.datetime.now(dt.UTC).isoformat(),
	}
	result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	report_path.write_text(render_report(result), encoding="utf-8")
	update_metadata(metadata_path, reviewed_path, result_path, report_path, status)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if fail_count == 0 else 2


if __name__ == "__main__":
	raise SystemExit(main())
