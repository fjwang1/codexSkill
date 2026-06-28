#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


GLOBAL_LEAD_SEC = 0.12
TAIL_SEC = 0.12
MIN_CUE_SEC = 0.45
NEXT_CUE_OVERLAP_SEC = 0.24
MIN_GLOBAL_LEAD_SEC = 0.08
MAX_LATE_START_SEC = 0.02
DANGLING_FRAGMENT_RE = re.compile(r"(?:如果|除了|因为|但是|所以|包括|比如|当|把|被|与|以及|或者|并且|而且)$")
DANGLING_DE_FRAGMENT_RE = re.compile(
	r"(?:项目|计划|政策|体系|问题|能力|逻辑|结构|机制|部分|方面|阶段|国家|政府|公司|市场|经济|机会|风险|背景|条件|选择|目标|空间|利益|位置|角色|结果|影响|技术|产业|供应链|制度|规则|路线|方式|模式|挑战|压力|信号|证据|观点|内容|议题|事件|安排|方向|战略|价值|趋势)的$"
)
CROSS_CUE_REPAIR_MAX_GAP_SEC = 0.80
SUBTITLE_FONT_PATH = Path("/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf")
SUBTITLE_FONT_FAMILY = "NotoSansCJKsc-Bold"
SUBTITLE_FONT_FULL_NAME = "Noto Sans CJK SC Bold"
SUBTITLE_FONT_LICENSE_NOTE = "SIL Open Font License 1.1"
SUBTITLE_FONT_SIZE_PX = 96
SUBTITLE_LETTER_SPACING_PX = 6
SUBTITLE_FAUX_ITALIC_SHEAR = 0.10
SUBTITLE_OUTLINE_WIDTH_PX = 3
SUBTITLE_OUTLINE_COLOR = "rgba(30,30,30,0.57)"
SUBTITLE_AVAILABLE_WIDTH_PX = 3320
SUBTITLE_GLYPH_EDGE_PAD_PX = 72
SUBTITLE_BLOCK_TOP_MIN_Y = 1904
SUBTITLE_BLOCK_TOP_MAX_Y = 1974
SUBTITLE_BLOCK_BOTTOM_MAX_Y = 2044
SEMANTIC_CONNECTOR_BREAKS = (
	"而不是",
	"强到",
	"从而",
	"进而",
	"同时",
	"并且",
	"也就是",
	"我们不是",
	"我们一直",
	"过去只有",
	"以及",
	"允许",
	"必须",
	"应该",
	"能够",
	"可以",
	"能不能",
	"从",
	"被",
	"由",
)
ASS_MARGIN_V = 116
PUBLICATION_CHINESE_NAMES = {
	"the economist": "经济学人",
	"economist": "经济学人",
	"financial times": "金融时报",
	"ft": "金融时报",
	"the new york times": "纽约时报",
	"new york times": "纽约时报",
	"nytimes": "纽约时报",
	"the new yorker": "纽约客",
	"new yorker": "纽约客",
	"the atlantic": "大西洋月刊",
	"atlantic": "大西洋月刊",
	"the wall street journal": "华尔街日报",
	"wall street journal": "华尔街日报",
	"wsj": "华尔街日报",
	"wired": "连线",
	"bloomberg": "彭博社",
	"bloomberg news": "彭博社",
	"bloomberg businessweek": "彭博商业周刊",
	"the guardian": "卫报",
	"guardian": "卫报",
	"foreign policy": "外交政策",
	"foreign affairs": "外交事务",
	"the washington post": "华盛顿邮报",
	"washington post": "华盛顿邮报",
	"reuters": "路透社",
	"associated press": "美联社",
	"ap": "美联社",
	"bbc": "英国广播公司",
	"bbc news": "英国广播公司",
	"cnn": "美国有线电视新闻网",
	"nikkei asia": "日经亚洲",
	"the wire china": "连线中国",
	"rest of world": "世界其余地区",
	"the diplomat": "外交学者",
	"china leadership monitor": "中国领导层观察",
	"time": "时代",
}


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _duration(path: Path) -> float:
	result = subprocess.run(
		[
			"ffprobe",
			"-v",
			"error",
			"-show_entries",
			"format=duration",
			"-of",
			"default=noprint_wrappers=1:nokey=1",
			str(path),
		],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return float(result.stdout.strip())


def _timeline_text_len(text: Any) -> int:
	return len(re.sub(r"[\s,，。.!！?？;；:：、'\"“”‘’（）()《》<>\\[\\]{}—…·-]+", "", str(text or "")))


def _asr_match_ratio(item: dict[str, Any]) -> float | None:
	try:
		return float(item["asr_matched_char_ratio"])
	except (KeyError, TypeError, ValueError):
		return None


def _assert_timeline_complete(timeline: dict[str, Any]) -> None:
	try:
		matched_ratio = float(timeline.get("asr_summary", {}).get("matched_script_ratio"))
	except (TypeError, ValueError):
		matched_ratio = -1.0
	assert matched_ratio >= 0.90, f"dialogue_timeline matched_script_ratio too low for subtitle generation: {matched_ratio:.3f} < 0.900"

	turns = list(timeline.get("turns") or [])
	cues = list(timeline.get("cues") or [])
	trailing_low_turns = 0
	for turn in reversed(turns):
		text_len = _timeline_text_len(turn.get("tts_text") or turn.get("text"))
		ratio = _asr_match_ratio(turn)
		confidence = str(turn.get("alignment_confidence") or "").lower()
		if text_len >= 20 and (confidence == "low" or (ratio is not None and ratio < 0.2)):
			trailing_low_turns += 1
			continue
		break
	assert trailing_low_turns <= 1, f"dialogue_timeline has compressed trailing low-confidence turns: {trailing_low_turns}"

	for turn in turns:
		text_len = _timeline_text_len(turn.get("tts_text") or turn.get("text"))
		if text_len < 20:
			continue
		duration = float(turn["end_sec"]) - float(turn["start_sec"])
		min_duration = max(0.5, min(5.0, text_len * 0.055))
		assert duration >= min_duration, (
			f"dialogue_timeline turn {turn.get('turn_index')} is too short for its text: "
			f"{duration:.3f}s < {min_duration:.3f}s, chars={text_len}"
		)

	for cue in cues:
		text_len = _timeline_text_len(cue.get("text"))
		if text_len < 12:
			continue
		duration = float(cue["end_sec"]) - float(cue["start_sec"])
		min_duration = max(0.25, min(1.2, text_len * 0.045))
		assert duration >= min_duration, (
			f"dialogue_timeline cue {cue.get('cue_index')} is too short for subtitle generation: "
			f"{duration:.3f}s < {min_duration:.3f}s, chars={text_len}"
		)


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _publication_key(publication: str) -> str:
	cleaned = publication.strip().strip("《》")
	cleaned = re.sub(r"\s+", " ", cleaned)
	return cleaned.casefold()


def _has_ascii_alpha(text: str) -> bool:
	return bool(re.search(r"[A-Za-z]", text))


def _chinese_publication_name(publication: str) -> str | None:
	key = _publication_key(publication)
	if not key:
		return None
	if key in PUBLICATION_CHINESE_NAMES:
		return PUBLICATION_CHINESE_NAMES[key]
	if not _has_ascii_alpha(publication):
		return publication.strip().strip("《》")
	return None


def _raw_publication_terms(publication: str) -> list[str]:
	cleaned = re.sub(r"\s+", " ", publication.strip().strip("《》"))
	if not _has_ascii_alpha(cleaned):
		return []
	terms = [cleaned]
	without_the = re.sub(r"(?i)^the\s+", "", cleaned).strip()
	if without_the and without_the != cleaned:
		terms.append(without_the)
	return sorted(set(terms), key=len, reverse=True)


def _contains_raw_publication(text: str, raw_terms: list[str]) -> str | None:
	for term in raw_terms:
		pattern = rf"(?i)(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])"
		if re.search(pattern, text):
			return term
	return None


def _is_dangling_fragment(text: str) -> bool:
	cleaned = text.strip()
	if DANGLING_FRAGMENT_RE.search(cleaned):
		return True
	# A bare trailing "的" is often a valid predicative ending in spoken Chinese
	# ("是成立的", "有理由的"), so only flag noun-modifier patterns that are
	# likely waiting for the next noun.
	return bool(DANGLING_DE_FRAGMENT_RE.search(cleaned))


def _subtitle_publication_check(project_dir: Path, cues: list[dict[str, Any]]) -> dict[str, Any]:
	metadata_path = project_dir / "source" / "source_metadata.json"
	if not metadata_path.exists():
		return {"checked": False, "reason": "source/source_metadata.json missing"}
	metadata = _read_json(metadata_path)
	publication = str(metadata.get("publication") or "").strip()
	if not publication:
		return {"checked": False, "reason": "source_metadata publication missing"}
	chinese_publication = _chinese_publication_name(publication)
	raw_terms = _raw_publication_terms(publication)
	offenders: list[dict[str, Any]] = []
	for cue in cues:
		text = str(cue.get("display_text") or cue.get("text") or "")
		raw_term = _contains_raw_publication(text, raw_terms)
		if raw_term:
			offenders.append({"cue_index": cue.get("index"), "raw_publication": raw_term, "text": text})
	if offenders:
		raise AssertionError(
			"Subtitle cue still contains raw English publication; fix podcast_script.md/dialogue_timeline.json upstream: "
			+ json.dumps(offenders[:5], ensure_ascii=False)
		)
	return {
		"checked": True,
		"publication": chinese_publication,
		"raw_publication_terms_blocked_count": len(raw_terms),
	}


def _srt_time(seconds: float) -> str:
	total_ms = max(0, int(round(seconds * 1000)))
	ms = total_ms % 1000
	total_seconds = total_ms // 1000
	sec = total_seconds % 60
	total_minutes = total_seconds // 60
	minute = total_minutes % 60
	hour = total_minutes // 60
	return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
	total_cs = max(0, int(round(seconds * 100)))
	cs = total_cs % 100
	total_seconds = total_cs // 100
	sec = total_seconds % 60
	total_minutes = total_seconds // 60
	minute = total_minutes % 60
	hour = total_minutes // 60
	return f"{hour}:{minute:02d}:{sec:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
	return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def _clean_display_text(text: str) -> str:
	text = re.sub(r"\s+", " ", text).strip()
	text = text.replace("。", "，").replace("．", "，")
	text = re.sub(r"(?<!\d)\.(?!\d)", "，", text)
	text = re.sub(r"[，,；;：:、\s]+$", "", text).strip()
	text = re.sub(r"^[，,；;：:、\s]+", "", text).strip()
	return text


def _join_subtitle_text(left: str, right: str) -> str:
	left = _clean_display_text(left)
	right = _clean_display_text(right)
	if not left:
		return right
	if not right:
		return left
	return f"{left}，{right}"


def _normalise_sentence_periods(text: str) -> str:
	text = re.sub(r"(?<!\d)\.(?!\d)", "。", text)
	return text.replace("．", "。")


def _split_by_terminal_sentence_marks(text: str) -> list[str]:
	text = _normalise_sentence_periods(text)
	units: list[str] = []
	buffer = ""
	for char in text:
		buffer += char
		if char in "。！？!?；;":
			cleaned = _clean_display_text(buffer)
			if cleaned:
				units.append(cleaned)
			buffer = ""
	if buffer.strip():
		cleaned = _clean_display_text(buffer)
		if cleaned:
			units.append(cleaned)
	return units


def _split_by_semantic_clause_marks(text: str) -> list[str]:
	clauses: list[str] = []
	buffer = ""
	for char in text:
		buffer += char
		if char in "，,；;：:、":
			cleaned = _clean_display_text(buffer)
			if cleaned:
				clauses.append(cleaned)
			buffer = ""
	if buffer.strip():
		cleaned = _clean_display_text(buffer)
		if cleaned:
			clauses.append(cleaned)
	return clauses


def _subtitle_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
	return ImageFont.truetype(str(SUBTITLE_FONT_PATH), SUBTITLE_FONT_SIZE_PX)


def _measure_spaced_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
	width = 0
	height = 0
	for index, char in enumerate(text):
		box = draw.textbbox((0, 0), char, font=font, stroke_width=SUBTITLE_OUTLINE_WIDTH_PX)
		width += box[2] - box[0]
		height = max(height, box[3] - box[1])
		if index < len(text) - 1:
			width += SUBTITLE_LETTER_SPACING_PX
	return width + round(abs(SUBTITLE_FAUX_ITALIC_SHEAR) * height) + SUBTITLE_GLYPH_EDGE_PAD_PX * 2


def _fits_single_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> bool:
	return _measure_spaced_text(draw, text, font) <= SUBTITLE_AVAILABLE_WIDTH_PX


def _avoid_ascii_token_split(text: str, cut: int) -> int:
	while cut > 1 and cut < len(text) and text[cut - 1].isascii() and text[cut - 1].isalnum() and text[cut].isascii() and text[cut].isalnum():
		cut -= 1
	return cut


def _best_fit_cut(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
	low = 1
	high = len(text)
	best = 0
	while low <= high:
		mid = (low + high) // 2
		if _fits_single_line(draw, text[:mid], font):
			best = mid
			low = mid + 1
		else:
			high = mid - 1
	assert best > 0, f"Single subtitle character does not fit at {SUBTITLE_FONT_SIZE_PX}px"
	preferred_breaks = "，,；;：:、！？?!"
	for index in range(best - 1, 3, -1):
		if text[index] in preferred_breaks:
			return index + 1
	cut = _avoid_ascii_token_split(text, best)
	return cut if cut > 0 else best


def _split_display_text_to_fit(text: str) -> list[str]:
	font = _subtitle_font()
	draw = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
	remaining = text
	parts: list[str] = []
	while remaining:
		if _fits_single_line(draw, remaining, font):
			parts.append(remaining)
			break
		cut = _best_fit_cut(draw, remaining, font)
		part = remaining[:cut].strip(" ，,；;：:、")
		assert part, f"Failed to split overlong subtitle text: {text}"
		parts.append(part)
		remaining = remaining[cut:].strip(" ，,；;：:、")
	return parts


def _split_by_semantic_connectors_to_fit(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> list[str]:
	text = text.strip()
	if _fits_single_line(draw, text, font):
		return [text]
	candidates: list[tuple[int, int, str, str]] = []
	for marker in SEMANTIC_CONNECTOR_BREAKS:
		start = 0
		while True:
			index = text.find(marker, start)
			if index < 0:
				break
			start = index + len(marker)
			if index <= 0 or index >= len(text) - 1:
				continue
			left = text[:index].strip(" ，,；;：:、")
			right = text[index:].strip(" ，,；;：:、")
			if not left or not right:
				continue
			left_width = _measure_spaced_text(draw, left, font)
			right_width = _measure_spaced_text(draw, right, font)
			candidates.append((max(left_width, right_width), abs(left_width - right_width), left, right))
	for _max_width, _balance, left, right in sorted(candidates):
		pieces: list[str] = []
		if _fits_single_line(draw, left, font):
			pieces.append(left)
		else:
			try:
				pieces.extend(_split_by_semantic_connectors_to_fit(left, draw, font))
			except AssertionError:
				continue
		if _fits_single_line(draw, right, font):
			pieces.append(right)
		else:
			try:
				pieces.extend(_split_by_semantic_connectors_to_fit(right, draw, font))
			except AssertionError:
				continue
		if pieces and all(_fits_single_line(draw, piece, font) for piece in pieces):
			return pieces
	assert False, (
		"Overlong subtitle semantic unit has no safe connector split; "
		"rewrite upstream into shorter complete sentences before subtitle generation: "
		f"{text!r}"
	)


def _subtitle_unit(
	text: str,
	unit_type: str,
	sentence_index: int,
	sentence_complete: bool,
	split_reason: str,
	rendered_width_px: int,
	semantic_clause_group_index: int | None = None,
) -> dict[str, Any]:
	unit: dict[str, Any] = {
		"text": text,
		"semantic_unit_type": unit_type,
		"sentence_index": sentence_index,
		"sentence_complete": sentence_complete,
		"split_reason": split_reason,
		"rendered_width_px": rendered_width_px,
	}
	if semantic_clause_group_index is not None:
		unit["semantic_clause_group_index"] = semantic_clause_group_index
	return unit


def _split_unit_into_clauses(text: str) -> list[str]:
	clauses = _split_by_semantic_clause_marks(text)
	if len(clauses) > 1:
		return clauses
	return []


def _make_repaired_clause_unit(
	text: str,
	base: dict[str, Any],
	draw: ImageDraw.ImageDraw,
	font: ImageFont.ImageFont,
	group_index: int,
) -> dict[str, Any]:
	return _subtitle_unit(
		text=text,
		unit_type=str(base.get("semantic_unit_type") or "semantic_clause"),
		sentence_index=int(base.get("sentence_index") or 1),
		sentence_complete=False,
		split_reason=f"{base.get('split_reason') or 'semantic_clause'}_dangling_repair",
		rendered_width_px=_measure_spaced_text(draw, text, font),
		semantic_clause_group_index=group_index,
	)


def _repair_dangling_units(
	units: list[dict[str, Any]],
	draw: ImageDraw.ImageDraw,
	font: ImageFont.ImageFont,
) -> list[dict[str, Any]]:
	repaired: list[dict[str, Any]] = []
	index = 0
	while index < len(units):
		current = dict(units[index])
		current_text = str(current.get("text") or "")
		if not _is_dangling_fragment(current_text) or index + 1 >= len(units):
			repaired.append(current)
			index += 1
			continue

		next_unit = dict(units[index + 1])
		next_text = str(next_unit.get("text") or "")
		combined = _join_subtitle_text(current_text, next_text)
		if _fits_single_line(draw, combined, font) and not _is_dangling_fragment(combined):
			next_unit["text"] = combined
			next_unit["rendered_width_px"] = _measure_spaced_text(draw, combined, font)
			next_unit["split_reason"] = f"{next_unit.get('split_reason') or 'semantic_clause'}_dangling_repair"
			repaired.append(next_unit)
			index += 2
			continue

		clauses = _split_unit_into_clauses(current_text)
		repaired_pair: tuple[dict[str, Any], dict[str, Any]] | None = None
		for move_count in range(1, len(clauses)):
			prefix = "，".join(clauses[:-move_count])
			suffix = "，".join(clauses[-move_count:])
			borrowed_next = _join_subtitle_text(suffix, next_text)
			if (
				prefix
				and borrowed_next
				and _fits_single_line(draw, prefix, font)
				and _fits_single_line(draw, borrowed_next, font)
				and not _is_dangling_fragment(prefix)
				and not _is_dangling_fragment(borrowed_next)
			):
				group_index = int(current.get("semantic_clause_group_index") or len(repaired) + 1)
				repaired_pair = (
					_make_repaired_clause_unit(prefix, current, draw, font, group_index),
					_make_repaired_clause_unit(borrowed_next, next_unit, draw, font, group_index + 1),
				)
				break
		if repaired_pair is not None:
			repaired.extend(repaired_pair)
			index += 2
			continue

		repaired.append(current)
		index += 1
	return repaired


def _semantic_subtitle_units(text: str) -> list[dict[str, Any]]:
	font = _subtitle_font()
	draw = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
	sentences = _split_by_terminal_sentence_marks(text)
	units: list[dict[str, Any]] = []
	for sentence_index, sentence in enumerate(sentences, start=1):
		if _fits_single_line(draw, sentence, font):
			units.append(_subtitle_unit(
				text=sentence,
				unit_type="sentence",
				sentence_index=sentence_index,
				sentence_complete=True,
				split_reason="sentence_boundary",
				rendered_width_px=_measure_spaced_text(draw, sentence, font),
			))
			continue
		clauses = _split_by_semantic_clause_marks(sentence)
		if len(clauses) <= 1:
			clauses = _split_by_semantic_connectors_to_fit(sentence, draw, font)
		buffer = ""
		clause_group_index = 1
		for clause in clauses:
			subclauses = [clause] if _fits_single_line(draw, clause, font) else _split_by_semantic_connectors_to_fit(clause, draw, font)
			for clause in subclauses:
				assert _fits_single_line(draw, clause, font), (
					"Subtitle semantic clause still does not fit one line; "
					"rewrite upstream into shorter complete sentences before subtitle generation: "
					f"{clause!r}"
				)
				candidate = f"{buffer}，{clause}" if buffer else clause
				if buffer and not _fits_single_line(draw, candidate, font):
					units.append(_subtitle_unit(
						text=buffer,
						unit_type="semantic_clause",
						sentence_index=sentence_index,
						sentence_complete=False,
						split_reason="overlong_sentence_semantic_clause",
						rendered_width_px=_measure_spaced_text(draw, buffer, font),
						semantic_clause_group_index=clause_group_index,
					))
					clause_group_index += 1
					buffer = clause
				else:
					buffer = candidate
		if buffer:
			units.append(_subtitle_unit(
				text=buffer,
				unit_type="semantic_clause",
				sentence_index=sentence_index,
				sentence_complete=False,
				split_reason="overlong_sentence_semantic_clause",
				rendered_width_px=_measure_spaced_text(draw, buffer, font),
				semantic_clause_group_index=clause_group_index,
			))
	assert units, f"No semantic subtitle units generated from text: {text!r}"
	return _repair_dangling_units(units, draw, font)


def _split_timing(start: float, end: float, parts: list[str]) -> list[tuple[float, float]]:
	if len(parts) == 1:
		return [(start, end)]
	duration = max(0.05, end - start)
	total_weight = sum(max(1, len(part)) for part in parts)
	cursor = start
	cumulative_weight = 0
	timings: list[tuple[float, float]] = []
	for index, part in enumerate(parts):
		if index == len(parts) - 1:
			part_end = end
		else:
			cumulative_weight += max(1, len(part))
			part_end = start + duration * cumulative_weight / total_weight
		timings.append((round(cursor, 3), round(max(cursor + 0.01, part_end), 3)))
		cursor = part_end
	return timings


def _semantic_units_are_publishable(text: str) -> bool:
	try:
		units = _semantic_subtitle_units(text)
	except AssertionError:
		return False
	return bool(units) and all(not _is_dangling_fragment(str(unit.get("text") or "")) for unit in units)


def _merge_dangling_source_units(source_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
	merged: list[dict[str, Any]] = []
	index = 0
	while index < len(source_units):
		current = dict(source_units[index])
		current_text = str(current.get("text") or "")
		if not _is_dangling_fragment(_clean_display_text(current_text)) or index + 1 >= len(source_units):
			merged.append(current)
			index += 1
			continue

		next_unit = dict(source_units[index + 1])
		same_speaker = current.get("speaker") == next_unit.get("speaker")
		gap_sec = float(next_unit["start_sec"]) - float(current["end_sec"])
		combined_text = _join_subtitle_text(current_text, str(next_unit.get("text") or ""))
		if (
			same_speaker
			and -0.05 <= gap_sec <= CROSS_CUE_REPAIR_MAX_GAP_SEC
			and _semantic_units_are_publishable(combined_text)
		):
			current["text"] = combined_text
			current["end_sec"] = float(next_unit["end_sec"])
			current["alignment_confidence"] = current.get("alignment_confidence") or next_unit.get("alignment_confidence")
			current["source_kind"] = f"{current.get('source_kind') or 'source'}_dangling_repair_group"
			current["source_cue_indices"] = [
				item
				for item in (current.get("source_cue_index"), next_unit.get("source_cue_index"))
				if item is not None
			]
			merged.append(current)
			index += 2
			continue

		merged.append(current)
		index += 1
	return merged


def _source_units_from_timeline(timeline: dict[str, Any]) -> list[dict[str, Any]]:
	source_cues = sorted(list(timeline.get("cues") or []), key=lambda item: (float(item.get("start_sec") or 0), int(item.get("cue_index") or 0)))
	if source_cues:
		return _merge_dangling_source_units([
			{
				"source_kind": "cue",
				"source_turn_id": cue.get("turn_id"),
				"source_turn_index": cue.get("turn_index"),
				"source_cue_index": cue.get("cue_index"),
				"speaker": cue.get("speaker"),
				"display_role": cue.get("display_role"),
				"text": str(cue.get("text") or ""),
				"start_sec": float(cue["start_sec"]),
				"end_sec": float(cue["end_sec"]),
				"alignment_confidence": cue.get("alignment_confidence"),
			}
			for cue in source_cues
		])
	turns = sorted(list(timeline.get("turns") or []), key=lambda item: (float(item.get("start_sec") or 0), int(item.get("turn_index") or 0)))
	if turns:
		return _merge_dangling_source_units([
			{
				"source_kind": "turn",
				"source_turn_id": turn.get("turn_id"),
				"source_turn_index": turn.get("turn_index"),
				"source_cue_index": None,
				"speaker": turn.get("speaker"),
				"display_role": turn.get("display_role"),
				"text": str(turn.get("text") or ""),
				"start_sec": float(turn["start_sec"]),
				"end_sec": float(turn["end_sec"]),
				"alignment_confidence": turn.get("alignment_confidence"),
			}
			for turn in turns
		])
	assert source_cues, "dialogue_timeline has no turns or cues"
	return []


def _build_cues(timeline: dict[str, Any], audio_duration: float, lead_sec: float, tail_sec: float, next_cue_overlap_sec: float) -> list[dict[str, Any]]:
	source_units = _source_units_from_timeline(timeline)
	planned: list[dict[str, Any]] = []
	for source_index, source in enumerate(source_units, start=1):
		source_start = float(source["start_sec"])
		source_end = min(audio_duration, max(source_start + 0.05, float(source["end_sec"])))
		text = str(source.get("text") or "")
		if not _clean_display_text(text):
			continue
		semantic_units = _semantic_subtitle_units(text)
		timings = _split_timing(source_start, source_end, [str(unit["text"]) for unit in semantic_units])
		for split_index, (unit, (part_source_start, part_source_end)) in enumerate(zip(semantic_units, timings, strict=True), start=1):
			planned.append({
				"speaker": source.get("speaker"),
				"display_role": source.get("display_role"),
				"text": unit["text"],
				"display_text": unit["text"],
				"source_kind": source.get("source_kind"),
				"source_turn_id": source.get("source_turn_id"),
				"source_turn_index": source.get("source_turn_index"),
				"source_cue_index": source.get("source_cue_index"),
				"source_cue_indices": source.get("source_cue_indices"),
				"source_unit_index": source_index,
				"source_unit_split_index": split_index,
				"source_unit_split_count": len(semantic_units),
				"source_start_sec": round(part_source_start, 3),
				"source_end_sec": round(part_source_end, 3),
				"alignment_confidence": source.get("alignment_confidence"),
				"semantic_unit_type": unit["semantic_unit_type"],
				"sentence_index": unit["sentence_index"],
				"sentence_complete": unit["sentence_complete"],
				"split_reason": unit["split_reason"],
				"semantic_clause_group_index": unit.get("semantic_clause_group_index"),
				"rendered_width_px": unit["rendered_width_px"],
				"fits_single_line": True,
			})
	output: list[dict[str, Any]] = []
	for index, item in enumerate(planned):
		source_start = float(item["source_start_sec"])
		source_end = float(item["source_end_sec"])
		start = max(0.0, source_start - lead_sec)
		end = min(audio_duration, source_end + tail_sec)
		if index + 1 < len(planned):
			next_start = max(0.0, float(planned[index + 1]["source_start_sec"]) - lead_sec)
			end = min(end, next_start + next_cue_overlap_sec)
		if end <= start:
			end = min(audio_duration, start + MIN_CUE_SEC)
		cue = {
			"index": len(output) + 1,
			**item,
			"start_sec": round(start, 3),
			"end_sec": round(max(start + 0.01, end), 3),
			"subtitle_start_lead_sec": round(max(0.0, source_start - start), 3),
			"subtitle_start_late_by_sec": round(max(0.0, start - source_start), 3),
		}
		output.append(cue)
	return output


def _subtitle_policy_summary(cues: list[dict[str, Any]], lead_sec: float) -> dict[str, Any]:
	assert cues, "No subtitle cues generated"
	late_values = [float(cue.get("subtitle_start_late_by_sec") or 0.0) for cue in cues]
	late_violations = [
		cue for cue in cues
		if float(cue.get("subtitle_start_late_by_sec") or 0.0) > MAX_LATE_START_SEC
	]
	hard_width_fallbacks = [
		cue for cue in cues
		if str(cue.get("split_reason") or "") == "hard_width_fallback"
	]
	line_violations = [
		cue for cue in cues
		if "\n" in str(cue.get("display_text") or "") or cue.get("fits_single_line") is not True
	]
	sentence_period_violations = [
		cue for cue in cues
		if re.search(r"(?<!\d)[。．.](?!\d)", str(cue.get("display_text") or ""))
	]
	dangling_fragment_violations = [
		cue for cue in cues
		if _is_dangling_fragment(str(cue.get("display_text") or ""))
	]
	starts = [float(cue["start_sec"]) for cue in cues]
	monotonic_start_violation_count = sum(
		1 for previous, current in zip(starts, starts[1:])
		if current + 0.001 < previous
	)
	unit_counts: dict[str, int] = {}
	for cue in cues:
		unit_type = str(cue.get("semantic_unit_type") or "unknown")
		unit_counts[unit_type] = unit_counts.get(unit_type, 0) + 1
	timing_status = (
		"PASS"
		if lead_sec >= MIN_GLOBAL_LEAD_SEC
		and not late_violations
		and monotonic_start_violation_count == 0
		else "FAIL"
	)
	segmentation_status = (
		"PASS"
		if not hard_width_fallbacks
		and not line_violations
		and not sentence_period_violations
		and not dangling_fragment_violations
		else "FAIL"
	)
	return {
		"timing_policy": {
			"status": timing_status,
			"global_lead_sec": lead_sec,
			"minimum_required_global_lead_sec": MIN_GLOBAL_LEAD_SEC,
			"max_allowed_late_start_sec": MAX_LATE_START_SEC,
			"max_late_start_sec": round(max(late_values) if late_values else 0.0, 3),
			"late_start_violation_count": len(late_violations),
			"monotonic_start_violation_count": monotonic_start_violation_count,
			"systematic_late_subtitles": False,
			"lead_applied_per_split_cue": True,
		},
		"segmentation_policy": {
			"status": segmentation_status,
			"unit_policy": "one_visible_line_per_complete_sentence_or_semantic_clause",
			"semantic_unit_counts": unit_counts,
			"hard_width_fallback_count": len(hard_width_fallbacks),
			"line_violation_count": len(line_violations),
			"sentence_period_violation_count": len(sentence_period_violations),
			"dangling_fragment_violation_count": len(dangling_fragment_violations),
			"dangling_fragment_examples": [
				{
					"index": cue.get("index"),
					"text": cue.get("display_text") or cue.get("text"),
				}
				for cue in dangling_fragment_violations[:10]
			],
			"requires_upstream_rewrite_for_unbreakable_overlong_sentence": True,
		},
	}


def _write_srt(path: Path, cues: list[dict[str, Any]]) -> None:
	lines: list[str] = []
	for cue in cues:
		lines.append(str(cue["index"]))
		lines.append(f"{_srt_time(float(cue['start_sec']))} --> {_srt_time(float(cue['end_sec']))}")
		lines.append(str(cue["display_text"]))
		lines.append("")
	path.write_text("\n".join(lines), encoding="utf-8")


def _write_ass(path: Path, cues: list[dict[str, Any]]) -> None:
	lines = [
		"[Script Info]",
		"ScriptType: v4.00+",
		"PlayResX: 3840",
		"PlayResY: 2160",
		"ScaledBorderAndShadow: yes",
		"",
		"[V4+ Styles]",
		"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
		f"Style: Default,{SUBTITLE_FONT_FAMILY},{SUBTITLE_FONT_SIZE_PX},&H00FFFFFF,&H000000FF,&H91000000,&HFF000000,-1,0,0,0,100,100,{SUBTITLE_LETTER_SPACING_PX},0,1,{SUBTITLE_OUTLINE_WIDTH_PX},0,2,180,180,{ASS_MARGIN_V},1",
		"",
		"[Events]",
		"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
	]
	for cue in cues:
		lines.append(
			f"Dialogue: 0,{_ass_time(float(cue['start_sec']))},{_ass_time(float(cue['end_sec']))},Default,,0,0,0,,{_ass_escape(str(cue['display_text']))}"
		)
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_subtitles(project_dir: Path, lead_sec: float, tail_sec: float, next_cue_overlap_sec: float) -> dict[str, Any]:
	audio_dir = project_dir / "audio"
	video_dir = project_dir / "video"
	video_dir.mkdir(parents=True, exist_ok=True)
	audio_path = audio_dir / "final_podcast.wav"
	timeline_path = audio_dir / "dialogue_timeline.json"
	script_path = project_dir / "podcast_script.md"
	assert audio_path.exists(), f"Missing {audio_path}"
	assert timeline_path.exists(), f"Missing {timeline_path}"
	assert SUBTITLE_FONT_PATH.exists(), f"Missing subtitle font: {SUBTITLE_FONT_PATH}"
	timeline = _read_json(timeline_path)
	_assert_timeline_complete(timeline)
	audio_duration = _duration(audio_path)
	cues = _build_cues(timeline, audio_duration, lead_sec, tail_sec, next_cue_overlap_sec)
	assert cues, "No subtitle cues generated"
	policy_summary = _subtitle_policy_summary(cues, lead_sec)
	assert policy_summary["timing_policy"]["status"] == "PASS", (
		"Subtitle timing policy failed: "
		+ json.dumps(policy_summary["timing_policy"], ensure_ascii=False)
	)
	assert policy_summary["segmentation_policy"]["status"] == "PASS", (
		"Subtitle segmentation policy failed: "
		+ json.dumps(policy_summary["segmentation_policy"], ensure_ascii=False)
	)
	publication_check = _subtitle_publication_check(project_dir, cues)
	srt_path = video_dir / "final_subtitles.srt"
	ass_path = video_dir / "final_subtitles.ass"
	_write_srt(srt_path, cues)
	_write_ass(ass_path, cues)
	shutil.copy2(srt_path, video_dir / "final_subtitles_1x.srt")
	shutil.copy2(ass_path, video_dir / "final_subtitles_1x.ass")
	manifest = {
		"schema_version": "article-podcast-subtitles.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"script_sha256": _sha256(script_path) if script_path.exists() else timeline.get("script_sha256"),
		"audio_sha256": _sha256(audio_path),
		"dialogue_timeline_sha256": _sha256(timeline_path),
		"alignment_method": "dialogue_timeline_asr",
		"global_lead_sec": lead_sec,
		"tail_sec": tail_sec,
		"next_cue_overlap_sec": next_cue_overlap_sec,
		"playback_speed_factor": 1.0,
		"source_timeline": "1x",
		"final_timeline": "1x",
		"source_publication_check": publication_check,
		"timing_policy": policy_summary["timing_policy"],
		"segmentation_policy": policy_summary["segmentation_policy"],
		"style": {
			"resolution": "3840x2160",
			"font_family": SUBTITLE_FONT_FAMILY,
			"font_full_name": SUBTITLE_FONT_FULL_NAME,
			"font_file": str(SUBTITLE_FONT_PATH),
			"font_license_note": SUBTITLE_FONT_LICENSE_NOTE,
			"font_size_px": SUBTITLE_FONT_SIZE_PX,
			"letter_spacing_px": SUBTITLE_LETTER_SPACING_PX,
			"faux_italic_shear": SUBTITLE_FAUX_ITALIC_SHEAR,
			"preferred_lines": 1,
			"max_lines": 1,
			"line_policy": "single_line_preferred_frequent_short_cues",
			"speaker_labels": False,
			"burned_subtitle_default": True,
			"embed_soft_subtitle_default": False,
			"background_box": False,
			"outline": "subtle_translucent_outline",
			"outline_width_px": SUBTITLE_OUTLINE_WIDTH_PX,
			"outline_color": SUBTITLE_OUTLINE_COLOR,
			"shadow": "soft_drop_shadow",
			"shadow_color": "rgba(0,0,0,0.38)",
			"shadow_blur_px": 2,
			"back_color": "transparent",
			"sentence_periods_displayed": False,
			"subtitle_block_top_min_y": SUBTITLE_BLOCK_TOP_MIN_Y,
			"subtitle_block_top_max_y": SUBTITLE_BLOCK_TOP_MAX_Y,
			"subtitle_block_bottom_max_y": SUBTITLE_BLOCK_BOTTOM_MAX_Y,
			"overflow_policy": "split_overlong_cues_no_font_shrink",
		},
		"cues": cues,
	}
	_write_json(video_dir / "subtitle_manifest.json", manifest)
	report = [
		"# 字幕对齐报告",
		"",
		f"- project: `{project_dir}`",
		"- alignment_method: dialogue_timeline_asr",
		f"- cues: {len(cues)}",
		f"- global_lead_sec: {lead_sec}",
		f"- tail_sec: {tail_sec}",
		f"- next_cue_overlap_sec: {next_cue_overlap_sec}",
		f"- source_publication_check: {publication_check}",
		f"- timing_policy: {policy_summary['timing_policy']['status']}",
		f"- max_late_start_sec: {policy_summary['timing_policy']['max_late_start_sec']}",
		f"- segmentation_policy: {policy_summary['segmentation_policy']['status']}",
		f"- dangling_fragment_violation_count: {policy_summary['segmentation_policy']['dangling_fragment_violation_count']}",
		"- speaker_labels: false",
		"- sentence_periods_displayed: false",
		f"- style: {SUBTITLE_FONT_FULL_NAME}, white text, subtle translucent outline, soft drop shadow, no background box",
		f"- subtitle_font_file: `{SUBTITLE_FONT_PATH}`",
		"",
		"## 抽检提示",
		"",
		"- 需要人工抽听开头、中段、结尾和至少 5 个 speaker switch。",
		"- 本脚本只使用 `audio/dialogue_timeline.json` 的 ASR cue 时间轴，不做字数反推。",
	]
	(video_dir / "subtitle_alignment_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
	return {
		"srt": str(srt_path),
		"ass": str(ass_path),
		"manifest": str(video_dir / "subtitle_manifest.json"),
		"cue_count": len(cues),
		"timing_policy": policy_summary["timing_policy"]["status"],
		"segmentation_policy": policy_summary["segmentation_policy"]["status"],
	}


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Build SRT/ASS subtitles from audio/dialogue_timeline.json.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--global-lead-sec", type=float, default=GLOBAL_LEAD_SEC)
	parser.add_argument("--tail-sec", type=float, default=TAIL_SEC)
	parser.add_argument("--next-cue-overlap-sec", type=float, default=NEXT_CUE_OVERLAP_SEC)
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	result = build_subtitles(args.project_dir.expanduser().resolve(), args.global_lead_sec, args.tail_sec, args.next_cue_overlap_sec)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
