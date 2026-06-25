#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from chinese_number_display import normalize_comma_thousands_for_chinese_display


CHAPTER_TARGET_CHARS = 3000
CHAPTER_HARD_MAX_CHARS = 3800

FORBIDDEN_CHINESE_CONTEMPORARY_LEADER_NAMES = [
	"习近平",
	"习主席",
	"Xi Jinping",
	"Xijinping",
]

LEADER_NAME_REPLACEMENTS = [
	("Trump-Xi峰会", "中美领导人峰会"),
	("Trump-Xi会晤", "中美领导人会晤"),
	("Biden-Xi峰会", "中美领导人峰会"),
	("Biden-Xi会晤", "中美领导人会晤"),
	("特朗普和习近平峰会", "中美领导人峰会"),
	("特朗普与习近平峰会", "中美领导人峰会"),
	("川普和习近平峰会", "中美领导人峰会"),
	("拜登和习近平峰会", "中美领导人峰会"),
	("拜登与习近平峰会", "中美领导人峰会"),
	("特朗普和习近平会晤", "中美领导人会晤"),
	("特朗普与习近平会晤", "中美领导人会晤"),
	("川普和习近平会晤", "中美领导人会晤"),
	("拜登和习近平会晤", "中美领导人会晤"),
	("拜登与习近平会晤", "中美领导人会晤"),
	("习近平和拜登", "中美领导人"),
	("习近平与拜登", "中美领导人"),
	("特朗普和习近平", "中美领导人"),
	("特朗普与习近平", "中美领导人"),
	("川普和习近平", "中美领导人"),
	("川普与习近平", "中美领导人"),
	("Xi Jinping", "中国国家领导人"),
	("Xijinping", "中国国家领导人"),
	("习近平", "中国国家领导人"),
	("习主席", "中国国家领导人"),
]

SOFTEN_REPLACEMENTS = [
	(
		"到了二零一零年代，尤其进入当前中国领导层时期以后，我们面对的是另一个中国。他淡化增长，更强调收入平等。",
		"到了二零一零年代，我们面对的是另一个中国。政策重心有所变化，更强调收入分配和社会公平。",
	),
	(
		"尤其进入当前中国领导层时期以后，我们面对的是另一个中国。他淡化增长，更强调收入平等。",
		"尤其进入二零一零年代以后，中国经济政策的重点有所变化，更强调收入分配和社会公平。",
	),
	(
		"中国国家领导人并不强调增长，他强调平等，这会压缩生产率增长的空间。",
		"当前政策更强调公平与再平衡，这可能影响生产率增长空间。",
	),
	(
		"第二件相关的事，是他确实限制了科技公司的市场力量。",
		"第二件相关的事，是相关监管也改变了科技公司的市场力量。",
	),
	(
		"你看他对阿里巴巴、滴滴和其他一些公司的整顿。",
		"比如近年对阿里巴巴、滴滴和其他平台公司的监管调整。",
	),
	(
		"我不是说我支持中国国家领导人的做法，但很有意思的是，美国的一些民粹诉求，跟中国国家领导人早期做的事情之间，确实有某种平行呼应。",
		"我不是在评价这些做法本身，但很有意思的是，不同国家围绕科技平台和收入分配的争论，确实存在某种相似之处。",
	),
	(
		"可是很多人也把他归咎为熄灭了九十年代和二十一世纪初推动中国增长的那种创业精神。",
		"但也有人认为，相关政策变化影响了九十年代和二十一世纪初推动中国增长的那种创业精神。",
	),
	("比较负面、比较批评性的意见", "较为敏感或建设性的意见"),
	(
		"在中国，面子很重要，你绝不能公开批评中国政府或者政府官员。不能这样做，一定会有后果。",
		"在中国商业沟通里，面子和表达方式很重要，公开表达批评意见时必须注意方式和分寸。",
	),
	("它不是一个十英尺高、无敌的巨人", "它并不是外界想象中没有约束的巨型经济体"),
	("不会接管地球、取代所有人。那不会发生。", "也不会简单取代所有其他经济体。"),
	("中国国家领导人和政策制定者一直想", "中国政策制定者一直想"),
	("中国国家领导人推动的“中国制造2025”计划", "中国推动的“中国制造2025”计划"),
	("中国国家领导人推动的中国制造2025计划", "中国推动的中国制造2025计划"),
]

COVID_TERMS = ["新冠", "疫情", "清零", "奥密克戎", "德尔塔", "后疫情"]
GOVERNANCE_TERMS = ["党", "中共", "体制", "决策", "系统", "国家领导人", "政策"]
SHARP_TERMS = ["僵硬", "谁在替我们", "震动", "泄了气", "不想这么做", "不再是", "暴露出", "处理不当"]
LEADER_SHARP_TERMS = ["MAGA", "变懒", "社会主义者", "本质上", "个人责任", "怎么把这个圆", "不想这么做"]
CURRENT_HISTORICAL_ATTACK_TERMS = ["毛泽东", "文化大革命", "红卫兵", "天下大乱", "形势大好"]
CURRENT_COMPARISON_TERMS = ["MAGA", "特朗普", "DOGE", "埃隆·马斯克", "相似", "现任", "国家领导人"]


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


def _contains_any(text: str, terms: list[str]) -> bool:
	return any(term in text for term in terms)


def _seconds_to_stamp(seconds: float) -> str:
	seconds = max(0, int(round(seconds)))
	hour = seconds // 3600
	minute = (seconds % 3600) // 60
	second = seconds % 60
	return f"{hour:02d}:{minute:02d}:{second:02d}"


def _stamp_to_seconds(stamp: Any) -> float:
	value = str(stamp or "00:00:00")
	parts = [float(part) for part in value.split(":")]
	if len(parts) == 3:
		return parts[0] * 3600 + parts[1] * 60 + parts[2]
	if len(parts) == 2:
		return parts[0] * 60 + parts[1]
	return parts[0] if parts else 0.0


def _clean_text(text: str) -> str:
	value = re.sub(r"\s+", "", text).strip()
	value = normalize_comma_thousands_for_chinese_display(value)
	value = value.replace("，。", "。").replace("。。", "。")
	return value


def _replace_forbidden_names(text: str) -> str:
	value = text
	for bad, good in LEADER_NAME_REPLACEMENTS:
		value = value.replace(bad, good)
	value = re.sub(r"(?<![A-Za-z])Xi\s*Jinping(?![A-Za-z])", "中国国家领导人", value, flags=re.IGNORECASE)
	value = re.sub(r"(?<![A-Za-z])Xi(?![A-Za-z])", "中国国家领导人", value)
	return value


def _soften_text(text: str) -> str:
	value = _replace_forbidden_names(text)
	for bad, good in SOFTEN_REPLACEMENTS:
		value = value.replace(bad, good)
	value = re.sub(r"你看他对([^。]+?)的整顿", r"比如近年对\1的监管调整", value)
	value = value.replace("中国国家领导人优先考虑收入不平等、约束科技巨头", "中国政策更关注收入分配和平台监管")
	value = value.replace("中国国家领导人并不强调增长", "当前政策并不只强调增长")
	value = value.replace("他强调平等", "也更强调公平")
	return _clean_text(value)


def _decision_for_segment(segment: dict[str, Any]) -> dict[str, Any]:
	original = _clean_text(str(segment.get("zh_text") or ""))
	edited = _soften_text(original)
	categories: list[str] = []

	if _contains_any(original, FORBIDDEN_CHINESE_CONTEMPORARY_LEADER_NAMES) or re.search(r"(?<![A-Za-z])Xi(?![A-Za-z])", original):
		categories.append("chinese_contemporary_leader_specific_name")

	if _contains_any(original, COVID_TERMS) and _contains_any(original, GOVERNANCE_TERMS) and _contains_any(original, SHARP_TERMS):
		categories.append("covid_policy_governance_sharp_critique")

	if _contains_any(original, ["中共", "共产党", "党的决策能力"]) and _contains_any(original, ["决策", "能力", "问题", "震动", "信心"]):
		categories.append("party_state_decision_capacity_critique")

	if _contains_any(original, CURRENT_HISTORICAL_ATTACK_TERMS) and _contains_any(original, CURRENT_COMPARISON_TERMS):
		categories.append("current_politics_historical_movement_comparison")

	if "国家领导人" in original and _contains_any(original, LEADER_SHARP_TERMS):
		categories.append("leader_personalized_value_judgment")

	if "国家领导人" in original and _contains_any(original, ["顾问", "公共医疗", "社会福利"]) and _contains_any(original, ["不想", "比MAGA", "变懒"]):
		categories.append("leader_social_welfare_motive_critique")

	cut_categories = {
		"covid_policy_governance_sharp_critique",
		"party_state_decision_capacity_critique",
		"current_politics_historical_movement_comparison",
		"leader_social_welfare_motive_critique",
	}
	if any(category in cut_categories for category in categories):
		return {
			"action": "cut",
			"risk_categories": categories,
			"original_text": original,
			"edited_text": "",
			"reason": "Removed for mainland platform publishing risk; later bridge will preserve flow.",
		}

	action = "keep"
	reason = "No high publishing risk detected."
	if edited != original or categories:
		action = "soften"
		reason = "Softened personalized or high-friction wording while preserving the economic point."
	return {
		"action": action,
		"risk_categories": categories,
		"original_text": original,
		"edited_text": edited,
		"reason": reason,
	}


def _mark_contextual_orphans(segments: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> None:
	for index, decision in enumerate(decisions):
		if decision["action"] != "cut":
			continue
		for offset in (1, 2):
			next_index = index + offset
			if next_index >= len(decisions) or decisions[next_index]["action"] == "cut":
				continue
			text = decisions[next_index]["original_text"]
			is_orphan = (
				len(text) <= 12
				or text.startswith("我说的是")
				or text.startswith("但美国")
				or text.startswith("是的，就是这种想法")
				or (text.startswith("对。") and "新冠" in text)
			)
			if not is_orphan:
				continue
			decisions[next_index].update({
				"action": "cut",
				"risk_categories": sorted(set(decisions[next_index]["risk_categories"] + ["context_orphan_after_sensitive_cut"])),
				"edited_text": "",
				"reason": "Removed because preceding sensitive passage was removed and this turn no longer has standalone context.",
			})


def _bridge_text(removed: list[dict[str, Any]], next_segment: dict[str, Any] | None) -> str:
	joined = "\n".join(str(item.get("zh_text") or "") for item in removed)
	if _contains_any(joined, ["新冠", "疫情", "清零", "公共医疗", "社会福利", "MAGA", "毛泽东", "文化大革命"]):
		return "说回经济和消费这条主线，节目把重点放回家庭储蓄、保障支出和信心变化：这些因素会影响居民愿不愿意消费，也会影响企业对中国市场的判断。"
	if next_segment and _contains_any(str(next_segment.get("zh_text") or ""), ["美国商会", "外国企业", "中国市场"]):
		return "随后，话题转向外国企业在中国经营的实际经验，以及进入中国市场需要注意的现实问题。"
	return "为了保持主线连贯，节目把话题拉回中国经济和市场环境本身，继续沿着原来的讨论顺序展开。"


def _bridge_segment(removed: list[dict[str, Any]], previous: dict[str, Any] | None, next_segment: dict[str, Any] | None) -> dict[str, Any]:
	start_sec = float(removed[0].get("source_start_sec") or _stamp_to_seconds(removed[0].get("source_start")))
	end_sec = float(removed[-1].get("source_end_sec") or _stamp_to_seconds(removed[-1].get("source_end")))
	speaker = str((previous or next_segment or removed[0]).get("speaker") or "Speaker 0")
	return {
		"source_segment_index": None,
		"source_segment_indices_removed": [item.get("segment_index") for item in removed],
		"source_start": _seconds_to_stamp(start_sec),
		"source_end": _seconds_to_stamp(end_sec),
		"source_start_sec": round(start_sec, 3),
		"source_end_sec": round(end_sec, 3),
		"speaker": speaker if re.fullmatch(r"Speaker [0-3]", speaker) else "Speaker 0",
		"source_text": "",
		"zh_text": _bridge_text(removed, next_segment),
		"safety_edit_action": "bridge",
		"zh_char_count": 0,
	}


def _build_safe_segments(segments: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
	safe: list[dict[str, Any]] = []
	index = 0
	while index < len(segments):
		decision = decisions[index]
		if decision["action"] == "cut":
			start = index
			while index < len(segments) and decisions[index]["action"] == "cut":
				index += 1
			removed = segments[start:index]
			previous = safe[-1] if safe else None
			next_segment = segments[index] if index < len(segments) else None
			if previous or next_segment:
				safe.append(_bridge_segment(removed, previous, next_segment))
			continue
		segment = dict(segments[index])
		segment["source_segment_index"] = segment.get("segment_index")
		segment["zh_text"] = decision["edited_text"]
		segment["safety_edit_action"] = decision["action"]
		segment["safety_risk_categories"] = decision["risk_categories"]
		segment["zh_char_count"] = len(re.sub(r"\s+", "", str(segment["zh_text"])))
		safe.append(segment)
		index += 1

	for new_index, segment in enumerate(safe, start=1):
		segment["segment_index"] = new_index
		if segment.get("zh_char_count") == 0:
			segment["zh_char_count"] = len(re.sub(r"\s+", "", str(segment.get("zh_text") or "")))
	return [segment for segment in safe if str(segment.get("zh_text") or "").strip()]


def _chapter_payload(existing: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
	chapter_number = len(existing) + 1
	estimated_chars = sum(int(item.get("zh_char_count") or 0) for item in items)
	return {
		"chapter_id": f"chapter_{chapter_number:03d}",
		"title": f"发布优化稿顺序分段 {chapter_number}",
		"source_start": items[0]["source_start"],
		"source_end": items[-1]["source_end"],
		"segment_start": items[0]["segment_index"],
		"segment_end": items[-1]["segment_index"],
		"estimated_zh_chars": estimated_chars,
		"tts_chunk_hint": "target_8_to_10_minutes",
	}


def _build_chapters(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
	chapters: list[dict[str, Any]] = []
	current: list[dict[str, Any]] = []
	current_chars = 0
	for segment in segments:
		chars = int(segment.get("zh_char_count") or 0)
		should_flush = current and current_chars + chars > CHAPTER_TARGET_CHARS
		if should_flush and current_chars >= 2200:
			chapters.append(_chapter_payload(chapters, current))
			current = []
			current_chars = 0
		current.append(segment)
		current_chars += chars
		if current_chars >= CHAPTER_HARD_MAX_CHARS:
			chapters.append(_chapter_payload(chapters, current))
			current = []
			current_chars = 0
	if current:
		chapters.append(_chapter_payload(chapters, current))
	return chapters


def _write_markdown(path: Path, metadata: dict[str, Any], segments: list[dict[str, Any]]) -> None:
	lines = [
		"---",
		"schema_version: worldview-china-mainland-publish-safety-edit.v1",
		f"title: {json.dumps(metadata.get('title') or '', ensure_ascii=False)}",
		f"channel: {json.dumps(metadata.get('channel') or '', ensure_ascii=False)}",
		"content_coverage: mainland_publish_safety_edited",
		"source: 03-source-translation/source_transcript.zh.json",
		"---",
		"",
		"# 内网发布优化中文稿",
		"",
	]
	for segment in segments:
		action = segment.get("safety_edit_action") or "keep"
		lines.extend([
			f"## {segment['segment_index']:04d} {segment['speaker']} [{segment['source_start']} - {segment['source_end']}] {action}",
			"",
			str(segment["zh_text"]),
			"",
		])
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _forbidden_residuals(text: str) -> list[str]:
	found = [term for term in FORBIDDEN_CHINESE_CONTEMPORARY_LEADER_NAMES if term in text]
	if re.search(r"(?<![A-Za-z])Xi(?![A-Za-z])", text):
		found.append("Xi")
	return sorted(set(found))


def _high_risk_residuals(text: str) -> list[str]:
	checks = {
		"中共": "party_specific_term",
		"清零政策": "zero_covid_policy",
		"谁在替我们做决策": "covid_decision_capacity_phrase",
		"比MAGA还MAGA": "leader_maga_comparison",
		"红卫兵": "current_historical_movement_comparison",
	}
	return sorted({label for term, label in checks.items() if term in text})


def run_safety_edit(run_dir: Path) -> dict[str, Any]:
	source_dir = run_dir / "03-source-translation"
	output_dir = run_dir / "03b-mainland-publish-safety"
	output_dir.mkdir(parents=True, exist_ok=True)

	translation_path = source_dir / "source_transcript.zh.json"
	translation = _read_json(translation_path)
	metadata_path = run_dir / "02-source-capture/source_metadata.json"
	metadata = _read_json(metadata_path) if metadata_path.exists() else {}
	segments = list(translation.get("segments") or [])
	assert segments, "No translated segments found"

	decisions = [_decision_for_segment(segment) for segment in segments]
	_mark_contextual_orphans(segments, decisions)
	safe_segments = _build_safe_segments(segments, decisions)
	chapters = _build_chapters(safe_segments)

	output_json = {
		"schema_version": "worldview-china-mainland-publish-safety-edit.v1",
		"content_coverage": "mainland_publish_safety_edited",
		"source_translation": str(translation_path),
		"policy": "minimal_mainland_platform_publish_safety_edit",
		"segments": safe_segments,
	}
	_write_json(output_dir / "source_transcript.zh.safe.json", output_json)
	_write_json(output_dir / "chapter_segments.safe.json", {
		"schema_version": "worldview-china-mainland-publish-safety-chapters.v1",
		"source_order_preserved": True,
		"chapters": chapters,
	})
	_write_json(output_dir / "edit_decisions.json", {
		"schema_version": "worldview-china-mainland-publish-safety-decisions.v1",
		"source_translation": str(translation_path),
		"decisions": [
			{
				"source_segment_index": segment.get("segment_index"),
				"source_start": segment.get("source_start"),
				"source_end": segment.get("source_end"),
				"speaker": segment.get("speaker"),
				"action": decision["action"],
				"risk_categories": decision["risk_categories"],
				"reason": decision["reason"],
				"original_text": decision["original_text"],
				"edited_text": decision["edited_text"],
			}
			for segment, decision in zip(segments, decisions, strict=True)
		],
	})
	_write_markdown(output_dir / "source_transcript.zh.safe.md", metadata, safe_segments)

	cut_count = sum(1 for decision in decisions if decision["action"] == "cut")
	soften_count = sum(1 for decision in decisions if decision["action"] == "soften")
	bridge_count = sum(1 for segment in safe_segments if segment.get("safety_edit_action") == "bridge")
	final_text = "\n".join(str(segment.get("zh_text") or "") for segment in safe_segments)
	forbidden = _forbidden_residuals(final_text)
	high_risk = _high_risk_residuals(final_text)
	status = "PASS" if not forbidden and not high_risk else "NEEDS_REVIEW"
	report_lines = [
		"# Mainland Publish Safety Edit Report",
		"",
		f"- status: {status}",
		"- policy: minimal_mainland_platform_publish_safety_edit",
		"- source: 03-source-translation/source_transcript.zh.json",
		"- output: 03b-mainland-publish-safety/source_transcript.zh.safe.json",
		f"- original_segments: {len(segments)}",
		f"- output_segments: {len(safe_segments)}",
		f"- softened_segments: {soften_count}",
		f"- cut_segments: {cut_count}",
		f"- bridge_segments: {bridge_count}",
		f"- final_chars: {len(re.sub(r'\\s+', '', final_text))}",
		f"- forbidden_name_residuals: {forbidden}",
		f"- high_risk_residuals: {high_risk}",
		f"- output_sha256: {_sha256(output_dir / 'source_transcript.zh.safe.json')}",
		"",
		"## Method",
		"",
		"Preserve normal China economy and market analysis. Soften personalized leader/government-motive language. Cut high-risk passages around current Chinese leadership, COVID policy decision criticism, party-state decision capacity criticism, and current-politics comparisons to Mao/Cultural Revolution/MAGA. Insert short bridges only where deletion would make adjacent turns abrupt.",
		"",
		"## Cut Segment Ranges",
	]
	cut_ranges: list[list[dict[str, Any]]] = []
	index = 0
	while index < len(segments):
		if decisions[index]["action"] != "cut":
			index += 1
			continue
		start = index
		while index < len(segments) and decisions[index]["action"] == "cut":
			index += 1
		cut_ranges.append(segments[start:index])
	if cut_ranges:
		for items in cut_ranges:
			categories = sorted({category for item in items for category in decisions[int(item["segment_index"]) - 1]["risk_categories"]})
			report_lines.append(f"- {items[0]['segment_index']}-{items[-1]['segment_index']} [{items[0]['source_start']} - {items[-1]['source_end']}]: {', '.join(categories)}")
	else:
		report_lines.append("- none")
	(output_dir / "safety_report.md").write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")

	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["03b-mainland-publish-safety"] = {
		"status": status.lower(),
		"content_coverage": "mainland_publish_safety_edited",
		"source_transcript_zh_safe_json": str(output_dir / "source_transcript.zh.safe.json"),
		"source_transcript_zh_safe_md": str(output_dir / "source_transcript.zh.safe.md"),
		"chapter_segments_safe": str(output_dir / "chapter_segments.safe.json"),
		"edit_decisions": str(output_dir / "edit_decisions.json"),
		"safety_report": str(output_dir / "safety_report.md"),
		"cut_segments": cut_count,
		"softened_segments": soften_count,
		"bridge_segments": bridge_count,
		"forbidden_name_residuals": forbidden,
		"high_risk_residuals": high_risk,
	}
	_write_json(run_manifest_path, run_manifest)
	return run_manifest["nodes"]["03b-mainland-publish-safety"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Create a mainland-platform publish safety edit from the faithful Chinese source translation.")
	parser.add_argument("--run-dir", required=True, type=Path)
	args = parser.parse_args()
	result = run_safety_edit(args.run_dir.expanduser().resolve())
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
	raise SystemExit(main())
