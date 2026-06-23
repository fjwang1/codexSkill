#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any


WIDTH = 3840
HEIGHT = 2160


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _text(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, str):
		return " ".join(value.split())
	return " ".join(str(value).split())


def _as_list(value: Any) -> list[str]:
	if isinstance(value, list):
		return [_text(item) for item in value if _text(item)]
	text = _text(value)
	return [text] if text else []


def _turn_lookup(timeline: dict[str, Any]) -> dict[int, dict[str, Any]]:
	turns = timeline.get("turns") or []
	lookup: dict[int, dict[str, Any]] = {}
	for turn in turns:
		index = int(turn["turn_index"])
		lookup[index] = turn
	if not lookup:
		raise ValueError("dialogue_timeline.json has no turns")
	return lookup


def _timeline_duration(timeline: dict[str, Any], turn_lookup: dict[int, dict[str, Any]]) -> float:
	duration = timeline.get("duration_sec")
	if duration is not None:
		return float(duration)
	last_turn = turn_lookup[max(turn_lookup)]
	return float(last_turn["end_sec"])


def _verify_images(chapters: list[dict[str, Any]], visual_dir: Path) -> None:
	try:
		from PIL import Image
	except ImportError as exc:
		raise RuntimeError("Pillow is required to verify chapter image dimensions.") from exc

	for chapter in chapters:
		image_value = chapter.get("image") or f"chapter_{int(chapter['chapter_index']):02d}.png"
		image_path = Path(str(image_value))
		if not image_path.is_absolute():
			image_path = visual_dir / image_path
		if not image_path.exists():
			raise FileNotFoundError(f"Missing chapter image: {image_path}")
		with Image.open(image_path) as image:
			if image.size != (WIDTH, HEIGHT):
				raise ValueError(f"{image_path} has size {image.size}, expected {(WIDTH, HEIGHT)}")


def _parse_script_heading_ranges(script_path: Path, chapter_count: int, max_turn: int) -> list[dict[str, Any]]:
	if not script_path.exists():
		return []
	lines = script_path.read_text(encoding="utf-8").splitlines()
	sections: list[dict[str, Any]] = []
	current: dict[str, Any] | None = None
	turn_counter = 0
	for line in lines:
		heading = re.match(r"^##\s*(\d{1,2})\s+(.+?)\s*$", line)
		if heading:
			if current and current["turns"]:
				sections.append(current)
			current = {
				"heading_index": int(heading.group(1)),
				"title": heading.group(2).strip(),
				"turns": [],
			}
			continue
		if re.match(r"^Speaker\s+[01]\s*:", line):
			turn_counter += 1
			if current is not None:
				current["turns"].append(turn_counter)
	if current and current["turns"]:
		sections.append(current)
	if not sections:
		return []
	mapping: list[dict[str, Any]] = []
	if chapter_count >= len(sections):
		for section_index, section in enumerate(sections):
			first_chapter = math.floor(section_index * chapter_count / len(sections)) + 1
			last_chapter = math.floor((section_index + 1) * chapter_count / len(sections))
			last_chapter = max(first_chapter, last_chapter)
			local_count = last_chapter - first_chapter + 1
			turns = list(section["turns"])
			for local_index, chapter_index in enumerate(range(first_chapter, last_chapter + 1)):
				start_pos = math.floor(local_index * len(turns) / local_count)
				end_pos = math.floor((local_index + 1) * len(turns) / local_count) - 1
				end_pos = max(start_pos, min(len(turns) - 1, end_pos))
				mapping.append({
					"chapter_index": chapter_index,
					"start_turn": max(1, int(turns[start_pos])),
					"end_turn": min(max_turn, int(turns[end_pos])),
					"confidence": "medium",
					"evidence": f"Derived from podcast_script.md heading: {section['title']}",
				})
	else:
		for chapter_index in range(1, chapter_count + 1):
			start_section = math.floor((chapter_index - 1) * len(sections) / chapter_count)
			end_section = math.floor(chapter_index * len(sections) / chapter_count) - 1
			end_section = max(start_section, min(len(sections) - 1, end_section))
			start_turn = int(sections[start_section]["turns"][0])
			end_turn = int(sections[end_section]["turns"][-1])
			titles = " / ".join(section["title"] for section in sections[start_section:end_section + 1])
			mapping.append({
				"chapter_index": chapter_index,
				"start_turn": max(1, start_turn),
				"end_turn": min(max_turn, end_turn),
				"confidence": "medium",
				"evidence": f"Derived from podcast_script.md headings: {titles}",
			})
	mapping = sorted(mapping, key=lambda item: int(item["chapter_index"]))
	if len(mapping) != chapter_count:
		return []
	return mapping


def _tokenize(text: str) -> set[str]:
	text = _text(text).lower()
	words = set(re.findall(r"[a-z0-9]{2,}", text))
	cjk = set(re.findall(r"[\u4e00-\u9fff]", text))
	stop = set("的是了在和与也就都而及中对有到一个我们他们这里这个那种因为所以如果不是")
	return {token for token in words | cjk if token not in stop}


def _heuristic_mapping(chapters: list[dict[str, Any]], timeline: dict[str, Any], script_path: Path) -> list[dict[str, Any]]:
	turn_lookup = _turn_lookup(timeline)
	max_turn = max(turn_lookup)
	from_headings = _parse_script_heading_ranges(script_path, len(chapters), max_turn)
	if from_headings:
		return from_headings

	turns = [turn_lookup[index] for index in sorted(turn_lookup)]
	turn_tokens = [(int(turn["turn_index"]), _tokenize(turn.get("text") or "")) for turn in turns]
	mapping: list[dict[str, Any]] = []
	min_start = 1
	for idx, chapter in enumerate(chapters, start=1):
		text_parts = [
			chapter.get("chapter_title"),
			chapter.get("short_title"),
			chapter.get("summary"),
			chapter.get("interpretation") or chapter.get("speaker_note"),
			chapter.get("visual_intent"),
			chapter.get("script_anchor_hint"),
			" ".join(_as_list(chapter.get("points"))),
		]
		chapter_tokens = _tokenize(" ".join(_text(part) for part in text_parts))
		expected = math.floor((idx - 1) * len(turns) / len(chapters)) + 1
		best_turn = max(min_start, expected)
		best_score = -1.0
		for turn_index, tokens in turn_tokens:
			if turn_index < min_start:
				continue
			overlap = len(chapter_tokens & tokens)
			distance_penalty = abs(turn_index - expected) / max(1, len(turns))
			score = overlap - distance_penalty
			if score > best_score:
				best_turn = turn_index
				best_score = score
		if idx < len(chapters):
			next_expected = math.floor(idx * len(turns) / len(chapters)) + 1
			end_turn = max(best_turn, min(max_turn, next_expected - 1))
		else:
			end_turn = max_turn
		mapping.append({
			"chapter_index": idx,
			"start_turn": best_turn,
			"end_turn": end_turn,
			"confidence": "low",
			"evidence": "Heuristic fallback based on heading or token overlap; review recommended.",
		})
		min_start = min(max_turn, end_turn + 1)
	return mapping


def _load_mapping(mapping_path: Path, chapters: list[dict[str, Any]], timeline: dict[str, Any], script_path: Path, allow_heuristic: bool) -> dict[str, Any]:
	if mapping_path.exists():
		data = _read_json(mapping_path)
		items = data.get("chapters")
		if not isinstance(items, list):
			raise ValueError(f"{mapping_path} must contain chapters array")
		return data
	if not allow_heuristic:
		raise FileNotFoundError(f"Missing {mapping_path}. Write AI mapping first or rerun with --allow-heuristic for debugging.")
	items = _heuristic_mapping(chapters, timeline, script_path)
	data = {
		"schema_version": "article-podcast-chapter-turn-mapping.v1",
		"method": "heuristic_fallback",
		"chapters": items,
	}
	_write_json(mapping_path, data)
	return data


def _validate_mapping(mapping: dict[str, Any], chapters: list[dict[str, Any]], turn_lookup: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
	items = list(mapping.get("chapters") or [])
	if len(items) != len(chapters):
		raise ValueError(f"Mapping chapter count {len(items)} does not match semantics chapter count {len(chapters)}")
	max_turn = max(turn_lookup)
	normalized: list[dict[str, Any]] = []
	previous_start = 0
	previous_end = 0
	for expected_index, raw in enumerate(sorted(items, key=lambda item: int(item.get("chapter_index") or 0)), start=1):
		chapter_index = int(raw.get("chapter_index") or expected_index)
		if chapter_index != expected_index:
			raise ValueError(f"Mapping chapter_index must be sequential; expected {expected_index}, got {chapter_index}")
		start_turn = int(raw["start_turn"])
		end_turn = int(raw["end_turn"])
		if start_turn < 1 or end_turn < 1 or start_turn > max_turn or end_turn > max_turn:
			raise ValueError(f"Chapter {chapter_index} turn range out of bounds: {start_turn}-{end_turn}; max={max_turn}")
		if end_turn < start_turn:
			raise ValueError(f"Chapter {chapter_index} end_turn before start_turn: {start_turn}-{end_turn}")
		if start_turn < previous_start or end_turn < previous_end:
			raise ValueError(f"Chapter {chapter_index} mapping is not monotonic")
		if start_turn <= previous_end:
			raise ValueError(f"Chapter {chapter_index} overlaps previous chapter: {start_turn} <= {previous_end}")
		normalized.append({
			"chapter_index": chapter_index,
			"start_turn": start_turn,
			"end_turn": end_turn,
			"confidence": _text(raw.get("confidence") or "unknown"),
			"evidence": _text(raw.get("evidence")),
		})
		previous_start = start_turn
		previous_end = end_turn
	return normalized


def _merge_plan(
	semantics: dict[str, Any],
	mapping_items: list[dict[str, Any]],
	timeline: dict[str, Any],
	timeline_path: Path,
	semantics_path: Path,
	visual_dir: Path,
) -> dict[str, Any]:
	turn_lookup = _turn_lookup(timeline)
	duration = _timeline_duration(timeline, turn_lookup)
	semantic_chapters = list(semantics.get("chapters") or [])
	plan_chapters: list[dict[str, Any]] = []
	for idx, semantic in enumerate(semantic_chapters, start=1):
		mapped = mapping_items[idx - 1]
		start_turn = int(mapped["start_turn"])
		end_turn = int(mapped["end_turn"])
		start_sec = 0.0 if idx == 1 else float(turn_lookup[start_turn]["start_sec"])
		if idx < len(mapping_items):
			next_start_turn = int(mapping_items[idx]["start_turn"])
			end_sec = float(turn_lookup[next_start_turn]["start_sec"])
		else:
			end_sec = duration
		if end_sec <= start_sec:
			raise ValueError(f"Chapter {idx} has non-positive visual duration: {start_sec}-{end_sec}")

		image = semantic.get("image") or f"chapter_{idx:02d}.png"
		chapter = {
			"chapter_index": idx,
			"chapter_title": _text(semantic.get("chapter_title")),
			"short_title": _text(semantic.get("short_title")),
			"summary": _text(semantic.get("summary")),
			"points": _as_list(semantic.get("points")),
			"interpretation": _text(semantic.get("interpretation") or semantic.get("speaker_note")),
			"speaker_note": _text(semantic.get("speaker_note") or semantic.get("interpretation")),
			"visual_intent": _text(semantic.get("visual_intent")),
			"script_anchor_hint": _text(semantic.get("script_anchor_hint")),
			"visual_type": _text(semantic.get("visual_type")),
			"start_turn": start_turn,
			"end_turn": end_turn,
			"semantic_end_sec": round(float(turn_lookup[end_turn]["end_sec"]), 3),
			"start_sec": round(start_sec, 3),
			"end_sec": round(end_sec, 3),
			"image": image,
			"source_svg": semantic.get("source_svg"),
			"binding_confidence": mapped.get("confidence"),
			"binding_evidence": mapped.get("evidence"),
		}
		plan_chapters.append(chapter)

	for idx in range(len(plan_chapters) - 1):
		current = plan_chapters[idx]
		nxt = plan_chapters[idx + 1]
		if abs(float(current["end_sec"]) - float(nxt["start_sec"])) > 0.01:
			raise ValueError(f"Visual intervals are not continuous at chapter {idx + 1}")
	plan_chapters[0]["start_sec"] = 0.0
	plan_chapters[-1]["end_sec"] = round(duration, 3)

	visual_system = dict(semantics.get("visual_system") or {})
	visual_system["resolution"] = f"{WIDTH}x{HEIGHT}"
	visual_system["timeline_binding"] = "semantic_turn_mapping_to_continuous_visual_intervals"
	return {
		"schema_version": "article-podcast-chapter-visuals.v4",
		"generator": "article-podcast-chapter-timeline-binding",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"dialogue_timeline_sha256": _sha256(timeline_path),
		"chapter_semantics_sha256": _sha256(semantics_path),
		"visual_system": visual_system,
		"chapters": plan_chapters,
	}


def _write_report(path: Path, plan: dict[str, Any], mapping: dict[str, Any]) -> None:
	lines = [
		"# Chapter Timeline Binding Report",
		"",
		f"- status: PASS",
		f"- method: {mapping.get('method') or 'ai_semantic_turn_binding'}",
		f"- chapters: {len(plan.get('chapters') or [])}",
		"",
		"| # | title | turns | seconds | confidence | evidence |",
		"| - | ----- | ----- | ------- | ---------- | -------- |",
	]
	for chapter in plan.get("chapters") or []:
		lines.append(
			"| {idx} | {title} | {st}-{et} | {ss:.3f}-{es:.3f} | {conf} | {evidence} |".format(
				idx=chapter["chapter_index"],
				title=str(chapter.get("chapter_title") or "").replace("|", " "),
				st=chapter["start_turn"],
				et=chapter["end_turn"],
				ss=float(chapter["start_sec"]),
				es=float(chapter["end_sec"]),
				conf=str(chapter.get("binding_confidence") or "").replace("|", " "),
				evidence=str(chapter.get("binding_evidence") or "").replace("|", " "),
			)
		)
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def bind(project_dir: Path, allow_heuristic: bool) -> dict[str, Any]:
	visual_dir = project_dir / "chapter_visuals"
	semantics_path = visual_dir / "chapter_semantics.json"
	timeline_path = project_dir / "audio" / "dialogue_timeline.json"
	mapping_path = visual_dir / "chapter_turn_mapping.json"
	script_path = project_dir / "podcast_script.md"

	if not semantics_path.exists():
		raise FileNotFoundError(f"Missing {semantics_path}")
	if not timeline_path.exists():
		raise FileNotFoundError(f"Missing {timeline_path}")
	semantics = _read_json(semantics_path)
	timeline = _read_json(timeline_path)
	chapters = list(semantics.get("chapters") or [])
	if not chapters:
		raise ValueError("chapter_semantics must contain at least one chapter")
	_verify_images(chapters, visual_dir)
	mapping = _load_mapping(mapping_path, chapters, timeline, script_path, allow_heuristic)
	turn_lookup = _turn_lookup(timeline)
	mapping_items = _validate_mapping(mapping, chapters, turn_lookup)
	plan = _merge_plan(semantics, mapping_items, timeline, timeline_path, semantics_path, visual_dir)
	_write_json(visual_dir / "chapter_plan.json", plan)
	_write_report(visual_dir / "chapter_timeline_binding_report.md", plan, mapping)
	return {
		"status": "PASS",
		"project_dir": str(project_dir),
		"chapter_count": len(plan["chapters"]),
		"chapter_plan": str(visual_dir / "chapter_plan.json"),
		"binding_report": str(visual_dir / "chapter_timeline_binding_report.md"),
		"mapping": str(mapping_path),
	}


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Bind PPT chapter semantics to dialogue_timeline turn ranges.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--allow-heuristic", action="store_true", help="Create a low-confidence fallback mapping when chapter_turn_mapping.json is absent.")
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	result = bind(args.project_dir.expanduser().resolve(), args.allow_heuristic)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
