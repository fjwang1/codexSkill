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

from PIL import Image, ImageDraw, ImageFont


WIDTH = 3840
HEIGHT = 2160
PALETTE = {
	"paper": "#f7f2e8",
	"paper_alt": "#eef4f2",
	"ink": "#14171a",
	"muted": "#697077",
	"cyan": "#00a9c8",
	"yellow": "#e6c700",
	"red": "#f05b5f",
	"green": "#25a26b",
	"blue": "#315ee7",
}


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
	candidates = [
		("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
		("/System/Library/Fonts/STHeiti Medium.ttc", 1),
		("/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc", 0),
		("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),
	]
	for candidate, index in candidates:
		path = Path(candidate)
		if path.exists():
			return ImageFont.truetype(str(path), size, index=index)
	return ImageFont.load_default()


def _hex(value: str) -> tuple[int, int, int]:
	value = value.lstrip("#")
	return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _wrap(text: str, chars: int) -> list[str]:
	text = re.sub(r"\s+", " ", text).strip()
	if len(text) <= chars:
		return [text] if text else []
	lines: list[str] = []
	rest = text
	punctuation = "，,。.:：；;、？！?!"
	while len(rest) > chars:
		split_at = chars
		for index in range(min(chars, len(rest) - 1), max(1, chars // 2) - 1, -1):
			if rest[index] in punctuation:
				split_at = index + 1
				break
		lines.append(rest[:split_at])
		rest = rest[split_at:]
	if rest:
		lines.append(rest)
	return lines


def _draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, fill: str, stroke: int = 0) -> None:
	draw.text(xy, text, font=font, fill=_hex(fill), stroke_width=stroke, stroke_fill=_hex(PALETTE["paper"]))


def _read_seed(project_dir: Path) -> list[dict[str, Any]]:
	seed_path = project_dir / "chapter_visuals" / "chapter_plan_seed.json"
	if seed_path.exists():
		data = _read_json(seed_path)
		items = data.get("chapters") if isinstance(data, dict) else data
		if isinstance(items, list) and items:
			return [dict(item) for item in items if isinstance(item, dict)]
	return []


def _default_chapters(project_dir: Path, count: int) -> list[dict[str, Any]]:
	title = ""
	title_path = project_dir / "video_title.txt"
	if title_path.exists():
		title = title_path.read_text(encoding="utf-8").strip().splitlines()[0]
	title = re.sub(r"^《[^》]+》：", "", title).strip() or "中国问题的六个切面"
	labels = ["问题打开", "结构矛盾", "关键机制", "赢家输家", "外溢后果", "最后判断"]
	return [
		{
			"chapter_title": labels[index],
			"summary": title if index == 0 else "把文稿里的追问压成一页可视化判断",
			"points": ["看对象，不看口号", "看机制，不看热闹", "看后果，不看单点"],
			"visual_type": ["scorecard", "split", "flow", "matrix", "bar", "takeaway"][index % 6],
		}
		for index in range(count)
	]


def _assign_timing(seed: list[dict[str, Any]], timeline: dict[str, Any], count: int) -> list[dict[str, Any]]:
	turns = sorted(list(timeline.get("turns") or []), key=lambda item: int(item.get("turn_index") or 0))
	assert turns, "dialogue_timeline has no turns"
	duration = float(timeline.get("duration_sec") or turns[-1]["end_sec"])
	chapters: list[dict[str, Any]] = []
	for index in range(count):
		start_pos = math.floor(index * len(turns) / count)
		end_pos = math.floor((index + 1) * len(turns) / count) - 1
		end_pos = max(start_pos, min(len(turns) - 1, end_pos))
		start_turn = turns[start_pos]
		end_turn = turns[end_pos]
		item = dict(seed[index] if index < len(seed) else {})
		item.setdefault("chapter_title", f"第 {index + 1} 章")
		item.setdefault("summary", str(start_turn.get("text") or "")[:32])
		item.setdefault("points", [str(turns[pos].get("text") or "")[:18] for pos in range(start_pos, min(end_pos + 1, start_pos + 3))])
		item.setdefault("visual_type", ["scorecard", "split", "flow", "matrix", "bar", "takeaway"][index % 6])
		item.update({
			"chapter_index": index + 1,
			"short_title": str(item.get("short_title") or item["chapter_title"])[:8],
			"start_turn": int(start_turn["turn_index"]),
			"end_turn": int(end_turn["turn_index"]),
			"start_sec": round(0.0 if index == 0 else float(start_turn["start_sec"]), 3),
			"end_sec": round(duration if index == count - 1 else float(end_turn["end_sec"]), 3),
			"image": f"chapter_{index + 1:02d}.png",
		})
		chapters.append(item)
	for index in range(1, len(chapters)):
		if chapters[index]["start_sec"] < chapters[index - 1]["end_sec"]:
			chapters[index]["start_sec"] = chapters[index - 1]["end_sec"]
		if chapters[index]["end_sec"] <= chapters[index]["start_sec"]:
			chapters[index]["end_sec"] = min(duration, chapters[index]["start_sec"] + 0.5)
	chapters[-1]["end_sec"] = round(duration, 3)
	return chapters


def _draw_grid(draw: ImageDraw.ImageDraw) -> None:
	line = (222, 226, 220)
	for x in range(160, WIDTH, 160):
		draw.line((x, 0, x, HEIGHT), fill=line, width=1)
	for y in range(140, HEIGHT, 140):
		draw.line((0, y, WIDTH, y), fill=line, width=1)


def _draw_header(draw: ImageDraw.ImageDraw, chapter: dict[str, Any], total: int) -> None:
	idx = int(chapter["chapter_index"])
	_draw_text(draw, (220, 170), f"CH {idx:02d}", _font(62), PALETTE["cyan"])
	_draw_text(draw, (430, 168), str(chapter.get("short_title") or chapter["chapter_title"]), _font(58), PALETTE["muted"])
	for line_index, line in enumerate(_wrap(str(chapter["chapter_title"]), 12)[:2]):
		_draw_text(draw, (220, 300 + line_index * 130), line, _font(112, bold=True), PALETTE["ink"])
	for line_index, line in enumerate(_wrap(str(chapter.get("summary") or ""), 24)[:2]):
		_draw_text(draw, (226, 590 + line_index * 74), line, _font(54), PALETTE["muted"])


def _draw_points(draw: ImageDraw.ImageDraw, points: list[str]) -> None:
	y = 820
	for index, point in enumerate(points[:4], start=1):
		draw.rounded_rectangle((230, y, 1580, y + 170), radius=28, fill=(255, 255, 255), outline=_hex(PALETTE["ink"]), width=4)
		draw.ellipse((280, y + 46, 358, y + 124), fill=_hex(PALETTE["yellow"]), outline=_hex(PALETTE["ink"]), width=3)
		_draw_text(draw, (305, y + 55), str(index), _font(42, bold=True), PALETTE["ink"])
		for line_index, line in enumerate(_wrap(point, 18)[:2]):
			_draw_text(draw, (400, y + 42 + line_index * 58), line, _font(48), PALETTE["ink"])
		y += 215


def _draw_visual(draw: ImageDraw.ImageDraw, visual_type: str, chapter: dict[str, Any]) -> None:
	box = (1780, 300, 3520, 1650)
	draw.rounded_rectangle(box, radius=44, fill=(255, 255, 255), outline=_hex(PALETTE["ink"]), width=5)
	title = str(chapter.get("visual_label") or chapter.get("visual_type") or "MECHANISM")
	_draw_text(draw, (1880, 390), title.upper()[:18], _font(46), PALETTE["muted"])
	if visual_type in {"flow", "pipeline"}:
		labels = chapter.get("flow_labels") or ["投入", "筛选", "放大", "后果"]
		for index, label in enumerate(labels[:4]):
			x = 1910 + index * 380
			draw.rounded_rectangle((x, 830, x + 250, 1060), radius=28, fill=_hex([PALETTE["cyan"], PALETTE["yellow"], PALETTE["green"], PALETTE["red"]][index % 4]), outline=_hex(PALETTE["ink"]), width=4)
			for line_index, line in enumerate(_wrap(str(label), 4)[:2]):
				_draw_text(draw, (x + 44, 900 + line_index * 54), line, _font(44, bold=True), PALETTE["ink"])
			if index < 3:
				draw.line((x + 275, 945, x + 345, 945), fill=_hex(PALETTE["ink"]), width=7)
				draw.polygon([(x + 345, 945), (x + 310, 920), (x + 310, 970)], fill=_hex(PALETTE["ink"]))
	elif visual_type in {"matrix", "risk"}:
		draw.line((2080, 1380, 3260, 1380), fill=_hex(PALETTE["ink"]), width=6)
		draw.line((2080, 620, 2080, 1380), fill=_hex(PALETTE["ink"]), width=6)
		for x, y, color, text in [
			(2220, 1180, PALETTE["green"], "低风险"),
			(2880, 1030, PALETTE["yellow"], "转折点"),
			(3020, 720, PALETTE["red"], "高压力"),
		]:
			draw.ellipse((x, y, x + 170, y + 170), fill=_hex(color), outline=_hex(PALETTE["ink"]), width=4)
			_draw_text(draw, (x - 10, y + 190), text, _font(42), PALETTE["ink"])
	else:
		values = chapter.get("chart_values") or [72, 48, 64, 38]
		labels = chapter.get("chart_labels") or ["A", "B", "C", "D"]
		for index, value in enumerate(values[:4]):
			x = 1960 + index * 330
			h = int(680 * float(value) / max(1, max(values)))
			draw.rounded_rectangle((x, 1350 - h, x + 190, 1350), radius=24, fill=_hex([PALETTE["cyan"], PALETTE["yellow"], PALETTE["green"], PALETTE["red"]][index % 4]), outline=_hex(PALETTE["ink"]), width=4)
			_draw_text(draw, (x + 35, 1390), str(labels[index])[:5], _font(42), PALETTE["ink"])
	draw.rounded_rectangle((1880, 1460, 3380, 1565), radius=22, fill=_hex(PALETTE["paper_alt"]))
	_draw_text(draw, (1930, 1482), str(chapter.get("note") or "本页只保留核心变量和关系"), _font(42), PALETTE["muted"])


def _render_card(path: Path, chapter: dict[str, Any], total: int) -> None:
	bg = _hex(PALETTE["paper" if int(chapter["chapter_index"]) % 2 else "paper_alt"])
	img = Image.new("RGB", (WIDTH, HEIGHT), bg)
	draw = ImageDraw.Draw(img)
	_draw_grid(draw)
	_draw_header(draw, chapter, total)
	points = [str(point) for point in chapter.get("points", []) if str(point).strip()]
	_draw_points(draw, points or ["核心矛盾", "关键机制", "主要后果"])
	_draw_visual(draw, str(chapter.get("visual_type") or "scorecard"), chapter)
	img.save(path)


def _contact_sheet(paths: list[Path], out: Path) -> None:
	thumbs = []
	for path in paths:
		img = Image.open(path).convert("RGB")
		img.thumbnail((640, 360), Image.Resampling.LANCZOS)
		thumbs.append(img.copy())
	sheet = Image.new("RGB", (640 * 3, 360 * 2), (245, 245, 245))
	for index, img in enumerate(thumbs[:6]):
		x = (index % 3) * 640
		y = (index // 3) * 360
		sheet.paste(img, (x, y))
	sheet.save(out, quality=92)


def generate(project_dir: Path, target_cards: int) -> dict[str, Any]:
	timeline_path = project_dir / "audio" / "dialogue_timeline.json"
	assert timeline_path.exists(), f"Missing {timeline_path}"
	timeline = _read_json(timeline_path)
	out_dir = project_dir / "chapter_visuals"
	out_dir.mkdir(parents=True, exist_ok=True)
	seed = _read_seed(project_dir)
	if not seed:
		seed = _default_chapters(project_dir, target_cards)
	card_count = len(seed)
	chapters = _assign_timing(seed, timeline, card_count)
	paths: list[Path] = []
	for chapter in chapters:
		path = out_dir / str(chapter["image"])
		_render_card(path, chapter, len(chapters))
		paths.append(path)
	plan = {
		"schema_version": "article-podcast-chapter-visuals.v3",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"dialogue_timeline_sha256": _sha256(timeline_path),
		"visual_system": {
			"style": "legacy deterministic PPT visuals",
			"resolution": "3840x2160",
			"palette": PALETTE,
		},
		"chapters": chapters,
	}
	_write_json(out_dir / "chapter_plan.json", plan)
	_contact_sheet(paths, out_dir / "chapter_visuals_contact_sheet.jpg")
	return {
		"chapter_plan": str(out_dir / "chapter_plan.json"),
		"cards": len(chapters),
		"contact_sheet": str(out_dir / "chapter_visuals_contact_sheet.jpg"),
	}


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Generate legacy deterministic PPT visuals from dialogue_timeline.json.")
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--target-cards", type=int, default=6)
	return parser


def main() -> int:
	args = _build_parser().parse_args()
	result = generate(args.project_dir.expanduser().resolve(), args.target_cards)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
