#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PUBLICATION_MAP = {
	"east asia forum": "东亚论坛",
	"the diplomat": "外交学者",
	"diplomat": "外交学者",
	"the economist": "经济学人",
	"economist": "经济学人",
	"financial times": "金融时报",
	"ft": "金融时报",
	"the new york times": "纽约时报",
	"new york times": "纽约时报",
	"the new yorker": "纽约客",
	"the atlantic": "大西洋月刊",
	"the wall street journal": "华尔街日报",
	"wall street journal": "华尔街日报",
	"wired": "连线",
	"bloomberg": "彭博社",
	"foreign policy": "外交政策",
	"foreign affairs": "外交事务",
	"nikkei asia": "日经亚洲",
}

KEYWORD_PATTERNS = [
	("中国经济", r"中国经济|经济降档|高增长|房地产|消费降级"),
	("中国观察", r"中国|中美|北京|台海|香港|台湾|深圳|人民币|中国制造|中国稀土"),
	("社会观察", r"社会|中产|年轻人|餐饮|饭桌|生活方式|家庭|教育|就业|城市|阶层|消费文化"),
	("财经解读", r"经济降档|高增长|财经|贸易|金融|房地产|消费降级|产业政策|稀土|矿产|半导体|能源|制造|资源"),
	("亚洲观察", r"亚洲|韩国|日本|印尼|印度|东南亚|马六甲|台海|台湾|香港"),
	("中美关系", r"中美"),
	("贸易战", r"贸易战|关税|贸易冲突"),
	("中国稀土", r"中国稀土"),
	("稀土", r"稀土"),
	("关键矿产", r"关键矿产|矿产"),
	("半导体", r"半导体|芯片"),
	("房地产", r"房地产|房子"),
	("消费降级", r"消费降级"),
	("加州", r"加州"),
	("生活方式", r"生活方式"),
	("消费文化", r"消费文化|消费|饭桌"),
	("中国中产", r"中国中产|中产"),
	("餐饮文化", r"餐饮|饭桌"),
	("食品安全", r"食品安全"),
	("供应链", r"供应链"),
	("全球化", r"全球化"),
	("一带一路", r"一带一路"),
	("能源安全", r"能源安全|能源命门|马六甲"),
	("能源命门", r"能源命门"),
	("地缘政治", r"地缘政治|台海|马六甲|导弹防御|军事"),
	("产业政策", r"产业政策"),
	("资源民族主义", r"资源民族主义"),
	("资源国家队", r"资源国家队"),
	("国企平台", r"国企平台"),
	("卡脖子", r"卡脖子|卡矿"),
	("中国制造", r"中国制造"),
	("导弹防御", r"导弹防御"),
	("军事科技", r"军事科技"),
]

FALLBACK_TAGS = ("地缘政治", "国际经济", "政策观察", "供应链", "产业观察", "全球化")


def read_json_optional(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {}
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except (json.JSONDecodeError, OSError):
		return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_tag(value: Any) -> str | None:
	tag = str(value or "").strip()
	if not tag:
		return None
	tag = re.sub(r"[#\s,，、;；:：\"'“”‘’《》<>【】\[\]（）()]+", "", tag)
	tag = tag.strip()
	if len(tag) < 2 or len(tag) > 20:
		return None
	if re.search(r"[A-Za-z]", tag):
		return None
	if not is_search_like_tag(tag):
		return None
	return tag


def is_search_like_tag(tag: str) -> bool:
	if len(tag) > 12:
		return False
	if re.search(r"为什么|怎么|如何|谁先|不是|不只|正在|形成|意味着|背后|到底|越来越|扛不住", tag):
		return False
	if len(tag) > 6 and "的" in tag:
		return False
	return True


def publication_cn(value: Any) -> str | None:
	publication = str(value or "").strip()
	if not publication:
		return None
	key = publication.casefold().strip()
	if key in PUBLICATION_MAP:
		return PUBLICATION_MAP[key]
	if not re.search(r"[A-Za-z]", publication):
		return publication.strip("《》")
	return None


def short_text(value: Any, max_len: int = 96) -> str:
	text = re.sub(r"\s+", " ", str(value or "")).strip()
	if len(text) <= max_len:
		return text
	return text[:max_len].rstrip("，,；;。.") + "。"


def append_tag(tags: list[str], seen: set[str], report: list[dict[str, str]], value: Any, source: str) -> None:
	tag = clean_tag(value)
	if tag and tag not in seen:
		tags.append(tag)
		seen.add(tag)
		report.append({"tag": tag, "source": source})


def append_tag_list(tags: list[str], seen: set[str], report: list[dict[str, str]], values: Any, source: str) -> None:
	if isinstance(values, list):
		for value in values:
			append_tag(tags, seen, report, value, source)


def build_context_text(*items: Any) -> str:
	parts: list[str] = []
	for item in items:
		if isinstance(item, dict):
			parts.append(json.dumps(item, ensure_ascii=False))
		elif isinstance(item, list):
			parts.append(json.dumps(item, ensure_ascii=False))
		else:
			parts.append(str(item or ""))
	return "\n".join(parts)


def keyword_tags_from_text(text: str) -> list[str]:
	tags: list[str] = []
	for tag, pattern in KEYWORD_PATTERNS:
		if re.search(pattern, text) and tag not in tags:
			tags.append(tag)
	return tags


def build_tags(source_metadata: dict[str, Any], article_brief: dict[str, Any], cover_title: dict[str, Any], title: str) -> tuple[list[str], list[dict[str, str]]]:
	tags: list[str] = []
	seen: set[str] = set()
	report: list[dict[str, str]] = []
	topic_source_metadata = {key: value for key, value in source_metadata.items() if key not in {"publication"}}
	topic_cover_title = {
		key: cover_title.get(key)
		for key in ("title_text", "core_conflict", "title_rationale", "chinese_motifs", "highlight_texts")
	}
	context_text = build_context_text(title, topic_source_metadata, article_brief, topic_cover_title)
	detected = keyword_tags_from_text(context_text)

	append_tag(tags, seen, report, "外刊解读", "base.positioning")
	append_tag(tags, seen, report, "国际观察", "base.positioning")
	if "财经解读" in detected:
		append_tag(tags, seen, report, "财经解读", "detected.category")
	elif "社会观察" in detected:
		append_tag(tags, seen, report, "社会观察", "detected.category")

	publication = publication_cn(cover_title.get("publication") or source_metadata.get("publication"))
	if publication:
		append_tag(tags, seen, report, publication, "source.publication")

	for tag in ("中国观察", "中国经济", "亚洲观察", "社会观察", "财经解读"):
		if tag in detected:
			append_tag(tags, seen, report, tag, "detected.scope")

	for tag in detected:
		append_tag(tags, seen, report, tag, "detected.keyword")

	keyword_heat = cover_title.get("keyword_heat_check") if isinstance(cover_title.get("keyword_heat_check"), dict) else {}
	append_tag_list(tags, seen, report, keyword_heat.get("best_keywords"), "cover.keyword_heat.best")
	append_tag_list(tags, seen, report, keyword_heat.get("secondary_keywords"), "cover.keyword_heat.secondary")
	append_tag_list(tags, seen, report, cover_title.get("chinese_motifs"), "cover.chinese_motifs")
	append_tag_list(tags, seen, report, cover_title.get("highlight_texts"), "cover.highlight_texts")
	append_tag(tags, seen, report, article_brief.get("primary_subject"), "article_brief.primary_subject")

	for item in article_brief.get("terminology_glossary") or []:
		if isinstance(item, dict):
			append_tag(tags, seen, report, item.get("audience_form"), "article_brief.terminology_glossary")
	for item in article_brief.get("proper_noun_glossary") or []:
		if isinstance(item, dict):
			append_tag(tags, seen, report, item.get("audience_form"), "article_brief.proper_noun_glossary")

	for fallback_tag in FALLBACK_TAGS:
		if len(tags) >= 10:
			break
		append_tag(tags, seen, report, fallback_tag, "fallback.compatible")

	return tags[:10], report[:10]


def build_description(title: str, publish_info_path: Path, article_brief: dict[str, Any], cover_title: dict[str, Any]) -> str:
	_ = publish_info_path
	lead_parts: list[str] = []
	for key_source, key in (
		(cover_title, "core_conflict"),
		(article_brief, "core_question"),
		(article_brief, "thesis"),
		(cover_title, "title_rationale"),
	):
		part = short_text(key_source.get(key))
		if part and part not in lead_parts:
			lead_parts.append(part)
		if len(lead_parts) >= 2:
			break
	if not lead_parts:
		lead_parts.append("本期围绕原文的核心问题，梳理事件背景、利益冲突和可能后果。")
	return "\n\n".join([
		title,
		"先行提要：" + " ".join(lead_parts),
	])


def load_existing_schedule(path: Path) -> dict[str, Any]:
	existing = read_json_optional(path)
	return {
		"scheduled_publish_at": existing.get("scheduled_publish_at"),
		"scheduled_publish_timezone": existing.get("scheduled_publish_timezone") or "Asia/Shanghai",
		"schedule_source": existing.get("schedule_source"),
	}


def generate_metadata(project_dir: Path, title: str | None, publish_info_path: Path | None, output_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
	source_metadata = read_json_optional(project_dir / "source" / "source_metadata.json")
	article_brief = read_json_optional(project_dir / "planning" / "article_brief.json")
	cover_title = read_json_optional(project_dir / "cover" / "cover_title.json")
	title_path = project_dir / "video_title.txt"
	if title is None:
		assert title_path.exists(), f"Missing {title_path}"
		title_lines = [line.strip() for line in title_path.read_text(encoding="utf-8").splitlines() if line.strip()]
		assert title_lines, f"Empty {title_path}"
		title = title_lines[0]
	publish_info_path = publish_info_path or (project_dir / "publish_info.txt")
	assert publish_info_path.exists(), f"Missing {publish_info_path}"

	tags, tag_sources = build_tags(source_metadata, article_brief, cover_title, title)
	schedule = load_existing_schedule(project_dir / "bilibili_upload_metadata.json")
	publication = publication_cn(cover_title.get("publication") or source_metadata.get("publication"))
	metadata = {
		"schema_version": "bilibili_upload_metadata.v1",
		"title": title,
		"description": build_description(title, publish_info_path, article_brief, cover_title),
		"tags": tags,
		"category": "知识",
		"creation_declaration": "含AI生成内容",
		**schedule,
		"selection_mode": source_metadata.get("selection_mode") or None,
		"source_title": source_metadata.get("article_title") or cover_title.get("source_title"),
		"publication": publication,
		"topic_keywords": tags[3:],
		"video_path": "video/final_video.mp4",
		"cover_path": "cover/cover_4k.png",
		"publish_info_path": "publish_info.txt",
	}
	report = {
		"schema_version": "bilibili_tag_report.v1",
		"project_dir": str(project_dir),
		"metadata_path": str(output_path),
		"tags": tags,
		"tag_sources": tag_sources,
		"tag_count": len(tags),
		"strategy": "外刊中文解读冷启动标签：账号定位优先，来源和具体主题其次，不默认使用外刊精读/英语学习。",
		"warnings": [] if len(tags) >= 8 else ["bilibili tags underfilled"],
	}
	return metadata, report


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate Bilibili upload metadata for article video projects.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--title")
	parser.add_argument("--publish-info", type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--report", type=Path)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	project_dir = args.project_dir.resolve()
	output_path = args.output or (project_dir / "bilibili_upload_metadata.json")
	report_path = args.report or (project_dir / "planning" / "bilibili_tag_report.json")
	metadata, report = generate_metadata(project_dir, args.title, args.publish_info, output_path)
	write_json(output_path, metadata)
	write_json(report_path, report)
	print(json.dumps({"metadata": str(output_path), "report": str(report_path), "tags": metadata["tags"]}, ensure_ascii=False))


if __name__ == "__main__":
	main()
