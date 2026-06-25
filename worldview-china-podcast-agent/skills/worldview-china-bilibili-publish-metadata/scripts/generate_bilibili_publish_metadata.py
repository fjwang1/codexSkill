#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BASE_TAGS = ("外网热议", "海外视角", "中国观察", "国际观察")
FALLBACK_TAGS = ("国际播客", "中文配音", "财经解读", "中美关系", "国际经济", "全球化")
DESCRIPTION_PRODUCTION_NOTE_PATTERNS = (
	r"中文配音版本",
	r"保留原视频画面",
	r"替换为中文对话音频",
	r"外网公开播客/访谈视频制作",
	r"方便中文观众理解",
	r"本期是基于",
)
DESCRIPTION_TOPIC_PATTERNS = (
	("中国台湾穆斯林社群", r"中国台湾[^。！？\n]{0,40}穆斯林|穆斯林[^。！？\n]{0,40}中国台湾"),
	("印尼护理人员与清真生活", r"印尼|印度尼西亚|护理人员|清真"),
	("回族穆斯林与中国伊斯兰历史", r"回族|兰州牛肉面|清真寺|中国伊斯兰|伊斯兰教在中国"),
	("东亚低生育和家庭关系", r"低出生率|低生育|家庭关系|孝道|结婚|孩子"),
	("日本、韩国和中国台湾的社会困境", r"日本|韩国|东亚文化圈|低出生率|低生育"),
	("西方媒体叙事和中国观感", r"美国媒体|西方媒体|宣传|中国不是|中国人民"),
	("穆斯林社群如何与中国打交道", r"穆斯林[^。！？\n]{0,60}中国|中国[^。！？\n]{0,60}穆斯林|中国超级大国"),
	("华语伊斯兰教育资源", r"普通话|中文[^。！？\n]{0,20}伊斯兰|讲座|微信群|学习资源|寻求知识"),
	("动漫、叙事和东亚文化", r"动漫|漫画|讲故事|东方写作|日本写作"),
	("婚姻危机与社群项目", r"婚姻|婚介|配偶|家庭单位"),
	("贸易、战略和国际秩序", r"贸易|战略|国际秩序|全球舞台"),
)
KEYWORD_PATTERNS = [
	("中国经济", r"中国经济|经济|增长|消费|出口|房地产|内需|脆弱|疲软"),
	("财经解读", r"经济|财经|贸易|出口|消费|房地产|制造业|供应链|企业|市场"),
	("中美关系", r"中美|美国|特朗普|关税|贸易战|美中"),
	("贸易战", r"贸易战|关税|贸易冲突|Trump trade"),
	("中国制造", r"中国制造|制造业|产业|工业|dominance|industry"),
	("供应链", r"供应链|supply chain|supply chains"),
	("全球南方", r"全球南方|Global South|Africa|Asia"),
	("一带一路", r"一带一路|belt and road|BRI"),
	("地缘政治", r"地缘政治|G7|七国集团|台海|制裁|安全"),
	("中国市场", r"中国市场|foreign companies|entering the Chinese market|外企"),
	("外企在中国", r"外企|foreign companies|American Chamber|商会"),
	("黄仁勋", r"黄仁勋|Nvidia|NVIDIA|英伟达"),
	("马斯克", r"马斯克|Musk|Tesla|特斯拉"),
	("特朗普", r"特朗普|Trump"),
]


def _read_json_optional(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {}
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except (json.JSONDecodeError, OSError):
		return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_text_optional(path: Path, limit: int | None = None) -> str:
	if not path.exists():
		return ""
	text = path.read_text(encoding="utf-8", errors="ignore")
	return text[:limit] if limit else text


def _clean_text(value: Any, max_len: int | None = None) -> str:
	text = re.sub(r"\s+", " ", str(value or "")).strip()
	if max_len is not None and len(text) > max_len:
		return text[:max_len].rstrip("，,；;。. ") + "。"
	return text


def _clean_tag(value: Any) -> str | None:
	tag = str(value or "").strip()
	if not tag:
		return None
	tag = re.sub(r"[#\s,，、;；:：\"'“”‘’《》<>【】\[\]（）()]+", "", tag)
	tag = tag.strip()
	if len(tag) < 2 or len(tag) > 20:
		return None
	if re.search(r"[A-Za-z]", tag):
		return None
	if re.search(r"为什么|怎么|如何|是谁|到底|比你想象|意味着|正在|形成|不是", tag):
		return None
	return tag


def _append_tag(tags: list[str], seen: set[str], report: list[dict[str, str]], value: Any, source: str) -> None:
	tag = _clean_tag(value)
	if tag and tag not in seen:
		tags.append(tag)
		seen.add(tag)
		report.append({"tag": tag, "source": source})


def _context_text(*items: Any) -> str:
	parts: list[str] = []
	for item in items:
		if isinstance(item, (dict, list)):
			parts.append(json.dumps(item, ensure_ascii=False))
		else:
			parts.append(str(item or ""))
	return "\n".join(parts)


def _keyword_tags(text: str) -> list[str]:
	tags: list[str] = []
	for tag, pattern in KEYWORD_PATTERNS:
		if re.search(pattern, text, re.I) and tag not in tags:
			tags.append(tag)
	return tags


def _source_metadata(run_dir: Path) -> dict[str, Any]:
	for path in (
		run_dir / "02-source-capture/youtube-media/source.info.json",
		run_dir / "02-source-capture/youtube-media/metadata.json",
		run_dir / "02-source-capture/source_metadata.json",
		run_dir / "source/source_metadata.json",
	):
		data = _read_json_optional(path)
		if data:
			data["_metadata_path"] = str(path)
			return data
	return {}


def _chapter_lines(run_dir: Path) -> list[str]:
	chapter_data = _read_json_optional(run_dir / "03-source-translation/chapter_segments.json")
	chapters = chapter_data.get("chapters") if isinstance(chapter_data, dict) else None
	if isinstance(chapters, list) and chapters:
		lines: list[str] = []
		for idx, chapter in enumerate(chapters, start=1):
			title = _clean_text(chapter.get("title") or chapter.get("chapter_title") or f"第 {idx} 章", max_len=32)
			if re.fullmatch(r"原文顺序分段\s*\d+", title):
				continue
			lines.append(f"{idx}. {title}")
		return lines
	render_report = _read_text_optional(run_dir / "video/render_report.md")
	if render_report:
		return [line.strip("- ") for line in render_report.splitlines() if line.strip().startswith("- ")][:8]
	return []


def _strip_speaker_and_markup(text: str) -> str:
	text = re.sub(r"(?s)^---.*?---", " ", text)
	text = re.sub(r"^#+\s*", " ", text, flags=re.M)
	text = re.sub(r"\bSpeaker\s+\d+\s*:\s*", " ", text)
	text = re.sub(r"\[[^\]]{1,20}\]", " ", text)
	text = re.sub(r"\([^)]{1,40}\)", " ", text)
	return _clean_text(text)


def _title_core(title: str, cover_title: dict[str, Any], episode_manifest: dict[str, Any]) -> str:
	for value in (
		episode_manifest.get("episode_subtitle"),
		cover_title.get("translated_title_core"),
		cover_title.get("title_text"),
		title,
	):
		core = _clean_text(value, max_len=42)
		if core:
			core = re.sub(r"^.+?[：:]", "", core).strip()
			core = re.sub(r"^第\s*\d+\s*集[：:：]?", "", core).strip()
			if core:
				return core
	return "本集核心话题"


def _description_topic_terms(text: str) -> list[str]:
	matches: list[tuple[int, int, str]] = []
	for label, pattern in DESCRIPTION_TOPIC_PATTERNS:
		match = re.search(pattern, text, re.I)
		if match:
			matches.append((match.start(), len(matches), label))
	matches.sort()
	terms: list[str] = []
	for _, _, label in matches:
		if label not in terms:
			terms.append(label)
	return terms


def _fallback_script_sentence(text: str) -> str:
	for sentence in re.split(r"[。！？]\s*", text):
		sentence = _clean_text(sentence)
		if 18 <= len(sentence) <= 72 and not re.search(r"赞助|广告|访问|http|www|\.com|音乐", sentence, re.I):
			return sentence
	return ""


def _is_production_note(description: str) -> bool:
	return any(re.search(pattern, description) for pattern in DESCRIPTION_PRODUCTION_NOTE_PATTERNS)


def _build_tags(run_dir: Path, title: str, source_metadata: dict[str, Any], cover_title: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
	tags: list[str] = []
	seen: set[str] = set()
	report: list[dict[str, str]] = []
	for tag in BASE_TAGS:
		_append_tag(tags, seen, report, tag, "base.worldview_video")

	identity = cover_title.get("source_identity_label")
	_append_tag(tags, seen, report, identity, "cover.source_identity_label")
	source_channel = source_metadata.get("channel") or source_metadata.get("uploader")
	if source_channel and not re.search(r"CGSP|Podcast|播客", str(source_channel), re.I):
		_append_tag(tags, seen, report, source_channel, "source.channel")

	context = _context_text(
		title,
		source_metadata.get("title"),
		source_metadata.get("description"),
		source_metadata.get("tags"),
		cover_title,
		_read_text_optional(run_dir / "03-source-translation/source_transcript.zh.md", limit=8000),
		_read_json_optional(run_dir / "03-source-translation/chapter_segments.json"),
	)
	for tag in _keyword_tags(context):
		_append_tag(tags, seen, report, tag, "detected.keyword")

	for item in cover_title.get("highlight_texts") or []:
		_append_tag(tags, seen, report, item, "cover.highlight_texts")

	for tag in FALLBACK_TAGS:
		if len(tags) >= 10:
			break
		_append_tag(tags, seen, report, tag, "fallback.compatible")

	return tags[:10], report[:10]


def _build_description(run_dir: Path, title: str, source_metadata: dict[str, Any], cover_title: dict[str, Any], tags: list[str]) -> str:
	episode_manifest = _read_json_optional(run_dir / "episode_manifest.json")
	core = _title_core(title, cover_title, episode_manifest)
	script_text = _strip_speaker_and_markup(_read_text_optional(run_dir / "podcast_script.md", limit=16000))
	context = _context_text(core, cover_title.get("title_text"), cover_title.get("video_title_text"), script_text)
	terms = _description_topic_terms(context)
	if "中国台湾" in core and "看中国" not in core:
		terms = [term for term in terms if term != "穆斯林社群如何与中国打交道"]
	terms = terms[:3]
	if terms:
		topic_phrase = "、".join(terms[:-1]) + ("，以及" + terms[-1] if len(terms) > 1 else terms[0])
		if "？" in core or "?" in core:
			description = f"这一集从“{core}”这个问题切入，重点谈到{topic_phrase}。"
		else:
			description = f"这一集围绕“{core}”展开，重点谈到{topic_phrase}。"
	else:
		fallback = _fallback_script_sentence(script_text)
		description = f"这一集围绕“{core}”展开，梳理{fallback or '人物经历、社群处境与背后的现实张力'}。"
	description = _clean_text(description, max_len=120).rstrip("；;，,")
	if not description.endswith(("。", "！", "？")):
		description += "。"
	assert not _is_production_note(description), f"Description reads like a production note: {description}"
	return description


def _load_existing_schedule(path: Path, episode_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
	existing = _read_json_optional(path)
	episode_manifest = episode_manifest or {}
	return {
		"scheduled_publish_at": existing.get("scheduled_publish_at") or episode_manifest.get("scheduled_publish_at"),
		"scheduled_publish_timezone": existing.get("scheduled_publish_timezone") or episode_manifest.get("scheduled_publish_timezone") or "Asia/Shanghai",
		"schedule_source": existing.get("schedule_source") or episode_manifest.get("schedule_source"),
		"series_episode_index": existing.get("series_episode_index") or episode_manifest.get("episode_index"),
		"series_episode_count": existing.get("series_episode_count") or episode_manifest.get("episode_count"),
	}


def generate_metadata(run_dir: Path, output_path: Path, report_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
	run_dir = run_dir.resolve()
	title_path = run_dir / "video_title.txt"
	cover_path = run_dir / "cover/cover_4k.png"
	video_path = run_dir / "video/final_video.mp4"
	assert title_path.exists(), f"Missing {title_path}"
	assert cover_path.exists(), f"Missing {cover_path}"
	assert video_path.exists(), f"Missing {video_path}"
	title = _read_text_optional(title_path).strip()
	assert title, f"Empty {title_path}"
	cover_title = _read_json_optional(run_dir / "cover/cover_title.json")
	episode_manifest = _read_json_optional(run_dir / "episode_manifest.json")
	source_metadata = _source_metadata(run_dir)
	tags, tag_sources = _build_tags(run_dir, title, source_metadata, cover_title)
	if len(tags) < 8:
		for tag in FALLBACK_TAGS:
			if len(tags) >= 8:
				break
			_append_tag(tags, {item["tag"] for item in tag_sources}, tag_sources, tag, "fallback.underfilled")
		tags = [item["tag"] for item in tag_sources][:10]

	description = _build_description(run_dir, title, source_metadata, cover_title, tags)
	publish_info_path = run_dir / "publish_info.txt"
	publish_info_path.write_text(description + "\n", encoding="utf-8")

	metadata = {
		"schema_version": "bilibili_upload_metadata.v1",
		"workflow": "worldview-china-podcast-agent",
		"title": title,
		"description": description,
		"tags": tags,
		"category": "知识",
		"creation_declaration": "含AI生成内容",
		**_load_existing_schedule(run_dir / "bilibili_upload_metadata.json", episode_manifest),
		"selection_mode": source_metadata.get("selection_mode") or "youtube_podcast_translation",
		"source_title": source_metadata.get("title") or cover_title.get("source_title"),
		"source_channel": source_metadata.get("channel") or source_metadata.get("uploader"),
		"source_url": source_metadata.get("webpage_url") or source_metadata.get("original_url") or source_metadata.get("url"),
		"source_identity_label": cover_title.get("source_identity_label"),
		"translated_title_core": cover_title.get("translated_title_core"),
		"series_episode": bool(episode_manifest),
		"series_title_prefix": episode_manifest.get("series_title_prefix"),
		"episode_index": episode_manifest.get("episode_index"),
		"episode_count": episode_manifest.get("episode_count"),
		"episode_label": episode_manifest.get("episode_label"),
		"episode_subtitle": episode_manifest.get("episode_subtitle"),
		"cover_title_text": cover_title.get("title_text"),
		"topic_keywords": tags[4:],
		"video_path": "video/final_video.mp4",
		"cover_path": "cover/cover_4k.png",
		"publish_info_path": "publish_info.txt",
	}
	report = {
		"schema_version": "worldview_china_bilibili_publish_metadata_report.v1",
		"project_dir": str(run_dir),
		"metadata_path": str(output_path),
		"publish_info_path": str(publish_info_path),
		"tags": tags,
		"tag_sources": tag_sources,
		"tag_count": len(tags),
		"description": description,
		"description_strategy": "one_sentence_content_summary_from_episode_title_script_and_topic_terms",
		"series_episode": bool(episode_manifest),
		"episode_index": episode_manifest.get("episode_index"),
		"episode_count": episode_manifest.get("episode_count"),
		"scheduled_publish_at": metadata.get("scheduled_publish_at"),
		"scheduled_publish_timezone": metadata.get("scheduled_publish_timezone"),
		"schedule_source": metadata.get("schedule_source"),
		"strategy": "Worldview China 外网播客视频标签：外网/海外视角定位优先，中国主题和具体议题其次；不使用外刊文章专属标签。",
		"warnings": [] if len(tags) >= 8 else ["bilibili tags underfilled"],
	}
	return metadata, report, publish_info_path


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate Bilibili upload metadata for Worldview China translated YouTube podcast videos.")
	parser.add_argument("--run-dir", "--project-dir", dest="run_dir", required=True, type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--report", type=Path)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	run_dir = args.run_dir.resolve()
	output_path = args.output or (run_dir / "bilibili_upload_metadata.json")
	report_path = args.report or (run_dir / "10-bilibili-publish/publish_metadata_report.json")
	metadata, report, publish_info_path = generate_metadata(run_dir, output_path, report_path)
	_write_json(output_path, metadata)
	_write_json(report_path, report)
	print(json.dumps({
		"metadata": str(output_path),
		"report": str(report_path),
		"publish_info": str(publish_info_path),
		"tags": metadata["tags"],
	}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
