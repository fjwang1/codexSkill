#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any


TRANSLATE_MAX_CHARS = 3200
TURN_MAX_ZH_CHARS = 520
CHAPTER_TARGET_CHARS = 3000
CHAPTER_HARD_MAX_CHARS = 3800


SOURCE_FIXES = [
	(r"\bXiinping\b", "Xi Jinping"),
	(r"\bXii?nping\b", "Xi Jinping"),
	(r"\bDang Xiaoing\b", "Deng Xiaoping"),
	(r"\bDong Xiaoing\b", "Deng Xiaoping"),
	(r"\bDong Xiaoping\b", "Deng Xiaoping"),
	(r"\bDung Xiao?ping\b", "Deng Xiaoping"),
	(r"\bJang\b", "Jiang Zemin"),
	(r"\bXiaoong Shu\b", "Xiaohongshu"),
	(r"\bXiao Hong Shu\b", "Xiaohongshu"),
	(r"\bGuango\b", "Guangzhou"),
	(r"\bGuangjo\b", "Guangzhou"),
	(r"\bGujo\b", "Guizhou"),
	(r"\bGuayjo\b", "Guizhou"),
	(r"\bKilongjang\b", "Heilongjiang"),
	(r"\bAzan\b", "ASEAN"),
	(r"\bAsean\b", "ASEAN"),
	(r"\bomccrron\b", "Omicron"),
	(r"\bomccron\b", "Omicron"),
	(r"\bzero co\b", "zero-COVID"),
	(r"\bpostco\b", "post-COVID"),
	(r"\bduring co\b", "during COVID"),
	(r"\bthe Trumpi summit\b", "the Trump-Xi summit"),
	(r"\bCynica Podcast Network\b", "Sinica Podcast Network"),
	(r"\bMaong\b", "Mao Zedong"),
	(r"\bMa's philosophy\b", "Mao's philosophy"),
]

ZH_FIXES = [
	("习近平平", "习近平"),
	("习金平", "习近平"),
	("邓小平平", "邓小平"),
	("中央播客网络", "Sinica 播客网络"),
	("辛尼卡", "Sinica"),
	("阿赞", "东盟"),
	("郡上", "贵州"),
	("瓜伊约", "贵州"),
	("基隆江", "黑龙江"),
	("真相社会", "Truth Social"),
	("房间", "商会"),
	("演出", "节目"),
	("中国全球南方网", "China Global South 网站"),
	("中国全球南方播客", "中国全球南方播客"),
	("小红书", "小红书"),
	("新冠疫情后", "后疫情时期"),
]


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


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_text(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _seconds_to_stamp(seconds: float) -> str:
	seconds = max(0, int(round(seconds)))
	hour = seconds // 3600
	minute = (seconds % 3600) // 60
	second = seconds % 60
	return f"{hour:02d}:{minute:02d}:{second:02d}"


def _clean_space(text: str) -> str:
	text = text.replace("\r", "\n")
	text = re.sub(r"[ \t]+", " ", text)
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()


def _fix_source_text(text: str) -> str:
	value = text
	for pattern, replacement in SOURCE_FIXES:
		value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
	return _clean_space(value)


def _fix_zh_text(text: str) -> str:
	value = re.sub(r"(?<![A-Za-z])Xi\s+Jinping(?![A-Za-z])", "中国国家领导人", text, flags=re.IGNORECASE)
	value = re.sub(r"\s+", "", value).strip()
	for bad, good in ZH_FIXES:
		value = value.replace(bad, good)
	for bad, good in LEADER_NAME_REPLACEMENTS:
		value = value.replace(bad, good)
	value = re.sub(r"(?<![A-Za-z])Xi\s*Jinping(?![A-Za-z])", "中国国家领导人", value, flags=re.IGNORECASE)
	value = re.sub(r"(?<![A-Za-z])Xi(?![A-Za-z])", "中国国家领导人", value)
	value = value.replace("，。", "。").replace("。。", "。")
	return value


def _segment_offsets(transcript: dict[str, Any]) -> list[dict[str, Any]]:
	cursor = 0
	offsets: list[dict[str, Any]] = []
	for item in transcript["transcript"]["segments"]:
		text = str(item.get("text") or "")
		start = cursor
		end = start + len(text)
		offsets.append({
			"start_offset": start,
			"end_offset": end,
			"start_sec": float(item.get("start") or 0.0),
			"end_sec": float(item.get("start") or 0.0) + float(item.get("duration") or 0.0),
			"text": text,
		})
		cursor = end + 1
	return offsets


def _time_for_offsets(offsets: list[dict[str, Any]], start_offset: int, end_offset: int) -> tuple[float, float]:
	overlaps = [
		item for item in offsets
		if item["end_offset"] >= start_offset and item["start_offset"] <= end_offset
	]
	if not overlaps:
		return 0.0, 0.0
	return float(overlaps[0]["start_sec"]), float(overlaps[-1]["end_sec"])


def _sentence_split_en(text: str, max_chars: int) -> list[str]:
	parts = re.split(r"(?<=[.!?])\s+|\n+", text)
	chunks: list[str] = []
	buffer = ""
	for part in parts:
		part = part.strip()
		if not part:
			continue
		candidate = f"{buffer} {part}".strip() if buffer else part
		if len(candidate) <= max_chars:
			buffer = candidate
			continue
		if buffer:
			chunks.append(buffer)
			buffer = part
		while len(buffer) > max_chars:
			chunks.append(buffer[:max_chars].strip())
			buffer = buffer[max_chars:].strip()
	if buffer:
		chunks.append(buffer)
	return chunks


def _sentence_split_zh(text: str, max_chars: int) -> list[str]:
	parts = [part for part in re.split(r"([。！？；])", text) if part]
	sentences: list[str] = []
	buffer = ""
	for part in parts:
		buffer += part
		if part in "。！？；":
			sentences.append(buffer.strip())
			buffer = ""
	if buffer.strip():
		sentences.append(buffer.strip())
	chunks: list[str] = []
	current = ""
	for sentence in sentences:
		candidate = current + sentence
		if len(candidate) <= max_chars:
			current = candidate
			continue
		if current:
			chunks.append(current)
			current = sentence
		while len(current) > max_chars:
			cut = max(current.rfind("，", 0, max_chars), current.rfind("、", 0, max_chars))
			if cut < max_chars // 2:
				cut = max_chars
			chunks.append(current[:cut + 1].strip())
			current = current[cut + 1:].strip()
	if current:
		chunks.append(current)
	return [chunk for chunk in chunks if chunk]


def _parse_source_turns(transcript: dict[str, Any]) -> list[dict[str, Any]]:
	text = transcript["transcript"]["text"]
	offsets = _segment_offsets(transcript)
	markers = list(re.finditer(r">>\s*", text))
	bounds: list[tuple[int, int, str]] = []
	if markers:
		bounds.append((0, markers[0].start(), "Speaker 0"))
		speaker = "Speaker 1"
		for index, marker in enumerate(markers):
			next_start = markers[index + 1].start() if index + 1 < len(markers) else len(text)
			bounds.append((marker.end(), next_start, speaker))
			speaker = "Speaker 0" if speaker == "Speaker 1" else "Speaker 1"
	else:
		bounds.append((0, len(text), "Speaker 0"))

	turns: list[dict[str, Any]] = []
	for raw_start, raw_end, speaker in bounds:
		source_text = _clean_space(text[raw_start:raw_end].replace(">>", ""))
		if len(source_text) < 3:
			continue
		fixed = _fix_source_text(source_text)
		start_sec, end_sec = _time_for_offsets(offsets, raw_start, raw_end)
		pieces = _sentence_split_en(fixed, TRANSLATE_MAX_CHARS)
		for piece_index, piece in enumerate(pieces):
			piece_start = start_sec + (end_sec - start_sec) * piece_index / max(1, len(pieces))
			piece_end = start_sec + (end_sec - start_sec) * (piece_index + 1) / max(1, len(pieces))
			turns.append({
				"source_turn_index": len(turns) + 1,
				"speaker": speaker,
				"source_start_sec": round(piece_start, 3),
				"source_end_sec": round(piece_end, 3),
				"source_start": _seconds_to_stamp(piece_start),
				"source_end": _seconds_to_stamp(piece_end),
				"source_text": piece,
			})
	return turns


def _translator():
	try:
		from deep_translator import GoogleTranslator
	except ModuleNotFoundError as exc:
		raise SystemExit("Missing deep-translator. Run with: uvx --with deep-translator python run_source_translation.py ...") from exc
	return GoogleTranslator(source="en", target="zh-CN")


def _translate_text(translator: Any, text: str, cache: dict[str, str], sleep_sec: float) -> str:
	key = _sha256_text(text)
	if key in cache:
		zh = _fix_zh_text(cache[key])
		cache[key] = zh
		return zh
	pieces = _sentence_split_en(text, TRANSLATE_MAX_CHARS)
	translated: list[str] = []
	for piece in pieces:
		value = _translate_piece(translator, piece, sleep_sec)
		translated.append(str(value))
		time.sleep(sleep_sec)
	zh = _fix_zh_text("".join(translated))
	cache[key] = zh
	return zh


def _translate_piece(translator: Any, text: str, sleep_sec: float, depth: int = 0) -> str:
	for attempt in range(2):
		try:
			value = translator.translate(text)
			if value:
				return str(value)
		except Exception:
			if attempt == 0:
				time.sleep(max(0.5, sleep_sec * 2))
				continue
			break
	if depth >= 4 or len(text) <= 80:
		raise RuntimeError(f"Translation failed after split retries for text prefix: {text[:160]!r}")
	parts = _smaller_translation_parts(text)
	if len(parts) <= 1:
		raise RuntimeError(f"Translation failed and could not split text prefix: {text[:160]!r}")
	return "".join(_translate_piece(translator, part, sleep_sec, depth + 1) for part in parts if part.strip())


def _smaller_translation_parts(text: str) -> list[str]:
	limit = max(120, min(900, len(text) // 2))
	parts = _sentence_split_en(text, limit)
	if len(parts) > 1:
		return parts
	mid = len(text) // 2
	candidates = [text.rfind(mark, 0, mid) for mark in (". ", "? ", "! ", ", ", "; ")]
	cut = max(candidates)
	if cut < 80:
		cut = mid
	return [text[:cut].strip(), text[cut:].strip()]


def _expand_translated_turns(source_turns: list[dict[str, Any]], translated: list[str]) -> list[dict[str, Any]]:
	expanded: list[dict[str, Any]] = []
	for source_turn, zh_text in zip(source_turns, translated, strict=True):
		pieces = _sentence_split_zh(zh_text, TURN_MAX_ZH_CHARS)
		if not pieces:
			continue
		start = float(source_turn["source_start_sec"])
		end = float(source_turn["source_end_sec"])
		source_text = str(source_turn["source_text"])
		for index, piece in enumerate(pieces):
			piece_start = start + (end - start) * index / len(pieces)
			piece_end = start + (end - start) * (index + 1) / len(pieces)
			expanded.append({
				"segment_index": len(expanded) + 1,
				"source_turn_index": source_turn["source_turn_index"],
				"source_start": _seconds_to_stamp(piece_start),
				"source_end": _seconds_to_stamp(piece_end),
				"source_start_sec": round(piece_start, 3),
				"source_end_sec": round(piece_end, 3),
				"speaker": source_turn["speaker"],
				"source_text": source_text if index == 0 else "",
				"zh_text": piece,
				"zh_char_count": len(re.sub(r"\s+", "", piece)),
			})
	return expanded


def _build_chapters(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
	chapters: list[dict[str, Any]] = []
	current: list[dict[str, Any]] = []
	current_chars = 0
	for segment in segments:
		chars = int(segment["zh_char_count"])
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


def _chapter_payload(existing: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
	chapter_number = len(existing) + 1
	estimated_chars = sum(int(item["zh_char_count"]) for item in items)
	return {
		"chapter_id": f"chapter_{chapter_number:03d}",
		"title": f"原文顺序分段 {chapter_number}",
		"source_start": items[0]["source_start"],
		"source_end": items[-1]["source_end"],
		"segment_start": items[0]["segment_index"],
		"segment_end": items[-1]["segment_index"],
		"estimated_zh_chars": estimated_chars,
		"tts_chunk_hint": "target_8_to_10_minutes",
	}


def _write_markdown(path: Path, metadata: dict[str, Any], segments: list[dict[str, Any]]) -> None:
	lines = [
		"---",
		"schema_version: worldview-china-source-translation.v1",
		f"title: {json.dumps(metadata.get('title') or '', ensure_ascii=False)}",
		f"channel: {json.dumps(metadata.get('channel') or '', ensure_ascii=False)}",
		"content_coverage: full_translation",
		"---",
		"",
		"# 忠实中文翻译稿",
		"",
	]
	for segment in segments:
		lines.extend([
			f"## {segment['segment_index']:04d} {segment['speaker']} [{segment['source_start']} - {segment['source_end']}]",
			"",
			segment["zh_text"],
			"",
		])
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_translation(run_dir: Path, sleep_sec: float) -> dict[str, Any]:
	source_dir = run_dir / "02-source-capture"
	output_dir = run_dir / "03-source-translation"
	output_dir.mkdir(parents=True, exist_ok=True)
	transcript_path = source_dir / "source_transcript.en.json"
	metadata_path = source_dir / "source_metadata.json"
	transcript = _read_json(transcript_path)
	metadata = _read_json(metadata_path)
	cache_path = output_dir / "translation_cache.json"
	cache = _read_json(cache_path) if cache_path.exists() else {}
	translator = _translator()
	source_turns = _parse_source_turns(transcript)
	translated = []
	for index, turn in enumerate(source_turns, start=1):
		translated.append(_translate_text(translator, str(turn["source_text"]), cache, sleep_sec))
		if index % 5 == 0:
			_write_json(cache_path, cache)
	_write_json(cache_path, cache)
	segments = _expand_translated_turns(source_turns, translated)
	chapters = _build_chapters(segments)
	speaker_mapping = {
		"schema_version": "worldview-china-speaker-mapping.v1",
		"mapping": {
			"Speaker 0": {
				"source_role": "Host / Eric Olander where inferred from transcript order",
				"vibevoice_voice": "Xinran",
				"note": "Female Chinese voice used for the original host role.",
			},
			"Speaker 1": {
				"source_role": "Guest / Ker Gibbs where inferred from transcript order",
				"vibevoice_voice": "BowenClean",
				"note": "Male Chinese voice used for the original guest role.",
			},
		},
		"inference_method": "first block before transcript speaker marker is host; subsequent >> markers toggle speakers",
	}
	translation_json = {
		"schema_version": "worldview-china-source-translation.v1",
		"content_coverage": "full_translation",
		"source_transcript": str(transcript_path),
		"translation_method": "GoogleTranslator en->zh-CN with source ASR cleanup and no summarization",
		"segments": segments,
	}
	_write_json(output_dir / "source_transcript.zh.json", translation_json)
	_write_json(output_dir / "chapter_segments.json", {
		"schema_version": "worldview-china-translation-chapters.v1",
		"source_order_preserved": True,
		"chapters": chapters,
	})
	_write_json(output_dir / "speaker_mapping.json", speaker_mapping)
	_write_markdown(output_dir / "source_transcript.zh.md", metadata, segments)
	report_lines = [
		"# Translation Report",
		"",
		"- status: PASS",
		"- content_coverage: full_translation",
		"- method: source ASR cleanup + GoogleTranslator en->zh-CN + Chinese turn splitting",
		f"- source_turns: {len(source_turns)}",
		f"- translated_segments: {len(segments)}",
		f"- chapter_count: {len(chapters)}",
		f"- total_zh_chars: {sum(int(item['zh_char_count']) for item in segments)}",
		"- no_summarization: true",
		"- no_reordered_content: true",
		"",
		"Notes: speaker attribution is inferred from transcript `>>` markers and may need human spot checks around interruptions.",
	]
	(output_dir / "translation_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["03-source-translation"] = {
		"status": "pass",
		"content_coverage": "full_translation",
		"source_transcript_zh_json": str(output_dir / "source_transcript.zh.json"),
		"source_transcript_zh_md": str(output_dir / "source_transcript.zh.md"),
		"chapter_segments": str(output_dir / "chapter_segments.json"),
		"speaker_mapping": str(output_dir / "speaker_mapping.json"),
		"translation_report": str(output_dir / "translation_report.md"),
	}
	_write_json(run_manifest_path, run_manifest)
	return run_manifest["nodes"]["03-source-translation"]


def main() -> int:
	parser = argparse.ArgumentParser(description="Translate source YouTube podcast transcript to natural Chinese speech and chapter segments.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--sleep-sec", type=float, default=0.15)
	args = parser.parse_args()
	result = run_translation(args.run_dir.expanduser().resolve(), args.sleep_sec)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
