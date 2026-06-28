#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
	from PIL import Image, ImageDraw, ImageFont
except ModuleNotFoundError as exc:
	raise SystemExit("Pillow is required. Use the Codex workspace dependency Python.") from exc


CANVAS = (3840, 2160)
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FONT = SKILL_DIR / "assets" / "fonts" / "XinQingNianTi.ttf"
WHITE = (255, 255, 255)
YELLOW = (249, 248, 80)
BLACK = (4, 2, 2)
TITLE_X = 384
TITLE_MAX_WIDTH = 2450
FOUR_THREE_CROP_SAFE_X = 480
FOUR_THREE_CROP_SAFE_WIDTH = 2880
CENTER_TITLE_MAX_WIDTH = FOUR_THREE_CROP_SAFE_WIDTH
TARGET_TITLE_LINE_COUNT = 3
LEFT_TITLE_START_SIZES = {1: 430, 2: 380, 3: 330}
CENTER_TITLE_TWO_LINE_LARGE_FONT_SIZE = 460
CENTER_TITLE_THREE_LINE_LARGE_FONT_SIZE = 400
CENTER_TITLE_START_SIZES = {1: 520, 2: CENTER_TITLE_TWO_LINE_LARGE_FONT_SIZE, 3: CENTER_TITLE_THREE_LINE_LARGE_FONT_SIZE}
FONT_SIZE_FIT_STEP_PX = 2
BREAK_AFTER_CHARS = set("，、：；")
BREAK_BEFORE_CHARS = set("，、：；？！）】》")
BAD_LINE_END_CHARS = set("的和与及或在把被对给向从")
BAD_LINE_START_CHARS = set("的和与及或，、：；？！")


def cover_crop(im: Image.Image, size: tuple[int, int]) -> Image.Image:
	target_w, target_h = size
	w, h = im.size
	target_ratio = target_w / target_h
	if w / h > target_ratio:
		new_w = int(h * target_ratio)
		left = (w - new_w) // 2
		im = im.crop((left, 0, left + new_w, h))
	else:
		new_h = int(w / target_ratio)
		top = (h - new_h) // 2
		im = im.crop((0, top, w, top + new_h))
	return im.resize(size, Image.Resampling.LANCZOS)


def split_by_highlight(lines: list[str], highlight_texts: list[str]) -> list[list[tuple[str, bool]]]:
	if not highlight_texts:
		raise SystemExit("cover_title.json must provide highlight_text or highlight_texts.")
	compact_title = "".join(lines)
	ranges: list[tuple[int, int]] = []
	for highlight_text in highlight_texts:
		compact_highlight = highlight_text.replace("\n", "")
		if not compact_highlight:
			continue
		start = compact_title.find(compact_highlight)
		if start < 0:
			raise SystemExit(f"highlight_text not found in title_lines: {highlight_text!r}")
		end = start + len(compact_highlight)
		if any(not (end <= old_start or start >= old_end) for old_start, old_end in ranges):
			raise SystemExit(f"highlight_text overlaps another highlight: {highlight_text!r}")
		ranges.append((start, end))
	result: list[list[tuple[str, bool]]] = []
	cursor = 0
	for line in lines:
		line_segments: list[tuple[str, bool]] = []
		for char in line:
			global_idx = cursor
			is_highlight = any(start <= global_idx < end for start, end in ranges)
			if line_segments and line_segments[-1][1] == is_highlight:
				line_segments[-1] = (line_segments[-1][0] + char, is_highlight)
			else:
				line_segments.append((char, is_highlight))
			cursor += 1
		result.append(line_segments)
	return result


def _line_break_penalty(title: str, break_pos: int, highlight_ranges: list[tuple[int, int]]) -> float:
	"""Lower is better. Preserve title text, but prefer natural visual breaks."""
	penalty = 0.0
	prev_char = title[break_pos - 1]
	next_char = title[break_pos]
	if prev_char in BREAK_AFTER_CHARS:
		penalty -= 26.0
	if next_char in BREAK_BEFORE_CHARS:
		penalty += 8.0
	if prev_char in "（【《":
		penalty += 5.0
	if prev_char in BAD_LINE_END_CHARS:
		penalty += 6.0
	if next_char in BAD_LINE_START_CHARS:
		penalty += 6.0
	if any(start < break_pos < end for start, end in highlight_ranges):
		penalty += 3.0
	return penalty


def _highlight_ranges_for_title(title: str, highlight_texts: list[str]) -> list[tuple[int, int]]:
	ranges: list[tuple[int, int]] = []
	for highlight_text in highlight_texts:
		compact_highlight = highlight_text.replace("\n", "")
		if not compact_highlight:
			continue
		start = title.find(compact_highlight)
		if start >= 0:
			ranges.append((start, start + len(compact_highlight)))
	return ranges


def rebalance_title_lines(lines: list[str], highlight_texts: list[str], target_count: int = TARGET_TITLE_LINE_COUNT) -> list[str]:
	"""Reflow visual title lines without changing title text."""
	title = "".join(lines)
	if len(lines) == target_count or len(title) < target_count:
		return lines
	highlight_ranges = _highlight_ranges_for_title(title, highlight_texts)
	n = len(title)
	best_breaks: tuple[int, ...] | None = None
	best_score = float("inf")
	target_len = n / target_count
	for breaks in _line_break_candidates(n, target_count):
		chunks = _chunks_for_breaks(title, breaks)
		if any(not chunk.strip() for chunk in chunks):
			continue
		lengths = [len(chunk) for chunk in chunks]
		score = sum((length - target_len) ** 2 for length in lengths)
		score += sum(3.0 for length in lengths if length <= 3)
		score += sum(_line_break_penalty(title, break_pos, highlight_ranges) for break_pos in breaks)
		if score < best_score:
			best_score = score
			best_breaks = tuple(breaks)
	if best_breaks is None:
		return lines
	return _chunks_for_breaks(title, best_breaks)


def _line_break_candidates(title_length: int, target_count: int):
	if target_count <= 1:
		yield ()
		return
	if target_count == 2:
		for first in range(2, title_length - 1):
			yield (first,)
		return
	if target_count == 3:
		for first in range(2, title_length - 1):
			for second in range(first + 2, title_length):
				yield (first, second)
		return
	raise ValueError(f"Unsupported title line count: {target_count}")


def _chunks_for_breaks(title: str, breaks: tuple[int, ...]) -> list[str]:
	chunks: list[str] = []
	start = 0
	for break_pos in breaks:
		chunks.append(title[start:break_pos])
		start = break_pos
	chunks.append(title[start:])
	return chunks


def _score_line_breaks(title: str, chunks: list[str], breaks: tuple[int, ...], highlight_ranges: list[tuple[int, int]], target_count: int) -> float:
	target_len = len(title) / target_count
	lengths = [len(chunk) for chunk in chunks]
	score = sum((length - target_len) ** 2 for length in lengths)
	score += sum(3.0 for length in lengths if length <= 3)
	score += sum(_line_break_penalty(title, break_pos, highlight_ranges) for break_pos in breaks)
	return score


def _lines_fit_at_font_size(
	draw: ImageDraw.ImageDraw,
	lines: list[str],
	highlight_texts: list[str],
	font_path: Path,
	font_size: int,
	max_width: int,
) -> bool:
	parsed = split_by_highlight(lines, highlight_texts)
	font = ImageFont.truetype(str(font_path), font_size)
	stroke = max(22, int(font_size * 0.115))
	gap = int(font_size * 0.03)
	return all(line_size(draw, segments, font, stroke, gap)[0] <= max_width for segments in parsed)


def _best_lines_for_count(
	draw: ImageDraw.ImageDraw,
	source_lines: list[str],
	highlight_texts: list[str],
	font_path: Path,
	max_width: int,
	target_count: int,
	required_font_size: int | None = None,
) -> list[str] | None:
	title = "".join(source_lines)
	if len(title) < target_count:
		return source_lines if len(source_lines) == target_count else None
	highlight_ranges = _highlight_ranges_for_title(title, highlight_texts)
	best_lines: list[str] | None = None
	best_score = float("inf")
	for breaks in _line_break_candidates(len(title), target_count):
		chunks = _chunks_for_breaks(title, tuple(breaks))
		if len(chunks) != target_count or any(not chunk.strip() for chunk in chunks):
			continue
		if required_font_size is not None and not _lines_fit_at_font_size(
			draw,
			chunks,
			highlight_texts,
			font_path,
			required_font_size,
			max_width,
		):
			continue
		score = _score_line_breaks(title, chunks, tuple(breaks), highlight_ranges, target_count)
		if score < best_score:
			best_score = score
			best_lines = chunks
	return best_lines


def choose_center_title_lines(
	draw: ImageDraw.ImageDraw,
	source_lines: list[str],
	highlight_texts: list[str],
	font_path: Path,
	max_width: int,
) -> tuple[list[str], str]:
	"""Prefer large two-line covers, then large three-line covers, then shrink only in three lines."""
	title = "".join(source_lines)
	if len(title) <= 1:
		return source_lines, "center_source_lines_too_short_to_reflow"
	two_line = _best_lines_for_count(
		draw,
		source_lines,
		highlight_texts,
		font_path,
		max_width,
		2,
		required_font_size=CENTER_TITLE_TWO_LINE_LARGE_FONT_SIZE,
	)
	if two_line is not None:
		return two_line, "center_large_two_line_fit"
	three_line_large = _best_lines_for_count(
		draw,
		source_lines,
		highlight_texts,
		font_path,
		max_width,
		3,
		required_font_size=CENTER_TITLE_THREE_LINE_LARGE_FONT_SIZE,
	)
	if three_line_large is not None:
		return three_line_large, "center_large_three_line_after_large_two_line_failed"
	three_line = _best_lines_for_count(
		draw,
		source_lines,
		highlight_texts,
		font_path,
		max_width,
		3,
		required_font_size=None,
	)
	if three_line is not None:
		return three_line, "center_three_line_shrink_after_large_two_and_large_three_failed"
	return source_lines, "center_source_lines_fallback"


def text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, stroke: int) -> tuple[int, int]:
	box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
	return box[2] - box[0], box[3] - box[1]


def text_bbox_full(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, stroke: int) -> tuple[int, int, int, int]:
	return draw.textbbox((0, 0), text, font=font, stroke_width=stroke)


def line_size(
	draw: ImageDraw.ImageDraw,
	segments: list[tuple[str, bool]],
	font: ImageFont.FreeTypeFont,
	stroke: int,
	gap: int,
) -> tuple[int, int]:
	width = 0
	height = 0
	for idx, (text, _is_highlight) in enumerate(segments):
		segment_stroke = stroke + int(stroke * 0.16) if _is_highlight else stroke
		w, h = text_bbox(draw, text, font, segment_stroke)
		width += w
		height = max(height, h)
		if idx:
			width += gap
	return width, height


def fit_font(
	draw: ImageDraw.ImageDraw,
	segments: list[tuple[str, bool]],
	font_path: Path,
	start_size: int,
	max_width: int,
) -> ImageFont.FreeTypeFont:
	size = start_size
	while size >= 120:
		font = ImageFont.truetype(str(font_path), size)
		stroke = max(22, int(size * 0.115))
		gap = int(size * 0.03)
		width, _height = line_size(draw, segments, font, stroke, gap)
		if width <= max_width:
			return font
		size -= FONT_SIZE_FIT_STEP_PX
	return ImageFont.truetype(str(font_path), size)


def fit_common_font(
	draw: ImageDraw.ImageDraw,
	all_segments: list[list[tuple[str, bool]]],
	font_path: Path,
	start_size: int,
	max_width: int,
) -> ImageFont.FreeTypeFont:
	size = start_size
	while size >= 120:
		font = ImageFont.truetype(str(font_path), size)
		stroke = max(22, int(size * 0.115))
		gap = int(size * 0.03)
		if all(line_size(draw, segments, font, stroke, gap)[0] <= max_width for segments in all_segments):
			return font
		size -= FONT_SIZE_FIT_STEP_PX
	return ImageFont.truetype(str(font_path), size)


def draw_text_line(
	im: Image.Image,
	draw: ImageDraw.ImageDraw,
	x: int,
	y: int,
	segments: list[tuple[str, bool]],
	font: ImageFont.FreeTypeFont,
	stroke: int,
	gap: int,
) -> int:
	cursor = x
	max_h = 0
	for text, is_highlight in segments:
		fill = YELLOW if is_highlight else WHITE
		segment_stroke = stroke + int(stroke * 0.16) if is_highlight else stroke
		shadow_stroke = segment_stroke + int(segment_stroke * 0.22)
		shadow_dx = int(segment_stroke * 0.34)
		shadow_dy = int(segment_stroke * 0.40)
		box = text_bbox_full(draw, text, font, shadow_stroke)
		padding = max(18, shadow_stroke + 12)
		layer_w = box[2] - box[0] + padding * 2 + abs(shadow_dx)
		layer_h = box[3] - box[1] + padding * 2 + abs(shadow_dy)
		layer = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
		layer_draw = ImageDraw.Draw(layer)
		origin_x = padding - box[0]
		origin_y = padding - box[1]
		layer_draw.text(
			(origin_x + shadow_dx, origin_y + shadow_dy),
			text,
			font=font,
			fill=(0, 0, 0, 185),
			stroke_width=shadow_stroke,
			stroke_fill=(0, 0, 0, 185),
		)
		layer_draw.text((origin_x, origin_y), text, font=font, fill=fill, stroke_width=segment_stroke, stroke_fill=BLACK)
		im.alpha_composite(layer, (cursor + box[0] - padding, y + box[1] - padding))
		w, h = text_bbox(draw, text, font, segment_stroke)
		cursor += w + gap
		max_h = max(max_h, h)
	return max_h


def load_title_data(args: argparse.Namespace) -> tuple[list[str], list[str], bool]:
	if args.title_json:
		data = json.loads(Path(args.title_json).read_text(encoding="utf-8"))
		lines = data.get("title_lines") or []
		highlight_texts = data.get("highlight_texts") or []
		if not highlight_texts:
			highlight_texts = [data.get("highlight_text") or ""]
		preserve_title_lines = bool(data.get("preserve_title_lines"))
	else:
		lines = [item for item in [args.line1, args.line2, args.line3] if item]
		highlight_texts = [args.highlight_text or ""]
		preserve_title_lines = False
	if not isinstance(lines, list) or not lines:
		raise SystemExit("No title lines found.")
	lines = [str(line) for line in lines if str(line).strip()]
	if len(lines) > 3:
		raise SystemExit("At most 3 title lines are supported.")
	if not isinstance(highlight_texts, list):
		raise SystemExit("highlight_texts must be a list of strings.")
	highlight_texts = [str(item) for item in highlight_texts if str(item).strip()]
	return lines, highlight_texts, preserve_title_lines


def main() -> None:
	parser = argparse.ArgumentParser(description="Compose a 4K Bilibili editorial cover with white/yellow title text.")
	parser.add_argument("--background", required=True, type=Path, help="16:9 generated image with subject on the right.")
	parser.add_argument("--out", required=True, type=Path)
	parser.add_argument("--title-json", type=Path)
	parser.add_argument("--line1")
	parser.add_argument("--line2")
	parser.add_argument("--line3")
	parser.add_argument("--highlight-text")
	parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
	parser.add_argument("--layout", choices=["left", "center"], default="left", help="Title placement. Keep left for article covers; use center for source-video podcast covers.")
	args = parser.parse_args()

	if not args.font.exists():
		raise SystemExit(f"Font not found: {args.font}")

	background = cover_crop(Image.open(args.background).convert("RGB"), CANVAS)
	im = background.convert("RGBA")
	draw = ImageDraw.Draw(im)

	max_width = CENTER_TITLE_MAX_WIDTH if args.layout == "center" else TITLE_MAX_WIDTH
	source_lines, highlight_texts, preserve_title_lines = load_title_data(args)
	if args.layout == "center":
		lines, visual_line_policy = choose_center_title_lines(draw, source_lines, highlight_texts, args.font, max_width)
	else:
		lines = source_lines if preserve_title_lines else rebalance_title_lines(source_lines, highlight_texts)
		visual_line_policy = "preserve_title_json_lines" if preserve_title_lines else "auto_reflow_to_three_lines_preserve_title_text"
	if "".join(lines) != "".join(source_lines):
		raise SystemExit("Internal title reflow error: visual line breaks changed title text.")
	parsed = split_by_highlight(lines, highlight_texts)

	start_sizes = CENTER_TITLE_START_SIZES if args.layout == "center" else LEFT_TITLE_START_SIZES
	start_size = start_sizes[len(lines)]
	common_font = fit_common_font(draw, parsed, args.font, start_size, max_width)
	fonts = [common_font for _segments in parsed]
	metrics: list[tuple[int, int, int, int]] = []
	for segments, font in zip(parsed, fonts):
		size = font.size
		stroke = max(22, int(size * 0.115))
		gap = int(size * 0.03)
		w, h = line_size(draw, segments, font, stroke, gap)
		metrics.append((w, h, stroke, gap))
	line_gap = max(74 if len(lines) == 2 else 58, int(common_font.size * 0.18))
	block_h = sum(h for _w, h, _stroke, _gap in metrics) + line_gap * (len(lines) - 1)
	y = (CANVAS[1] - block_h) // 2 if args.layout == "center" else {1: 790, 2: 600, 3: 450}[len(lines)]

	line_positions: list[dict[str, int]] = []
	for segments, font, (width, height, stroke, gap) in zip(parsed, fonts, metrics):
		x = (CANVAS[0] - width) // 2 if args.layout == "center" else TITLE_X
		line_positions.append({"x": x, "y": y, "width": width, "height": height})
		draw_text_line(im, draw, x, y, segments, font, stroke, gap)
		y += height + line_gap

	args.out.parent.mkdir(parents=True, exist_ok=True)
	im.convert("RGB").save(args.out)
	manifest = {
		"canvas": {"width": CANVAS[0], "height": CANVAS[1]},
		"background": str(args.background),
		"font": str(args.font),
		"source_title_lines": source_lines,
		"title_lines": lines,
		"highlight_texts": highlight_texts,
		"highlight_text": highlight_texts[0] if highlight_texts else "",
		"colors": {"white": "#FFFFFF", "yellow": "#F9F850", "stroke": "#040202"},
		"highlight_rule": "highlight_texts are non-overlapping substrings; script renders them yellow with a heavier stroke and all other title text white",
		"layout": {
			"mode": args.layout,
			"title_x": line_positions[0]["x"],
			"title_y": line_positions[0]["y"],
			"title_max_width": max_width,
			"four_three_crop_safe_area": {
				"x": FOUR_THREE_CROP_SAFE_X,
				"y": 0,
				"width": FOUR_THREE_CROP_SAFE_WIDTH,
				"height": CANVAS[1],
				"applies_to_center_layout": args.layout == "center",
			},
			"font_size_px": common_font.size,
			"font_start_size_px": start_size,
			"font_size_fit_step_px": FONT_SIZE_FIT_STEP_PX,
			"line_font_size_policy": "uniform_across_title_lines",
			"visual_line_policy": visual_line_policy,
			"source_preserve_title_lines": preserve_title_lines,
			"center_line_priority": [
				"large_two_line",
				"large_three_line",
				"shrunk_three_line",
			] if args.layout == "center" else None,
			"subject_expected_position": "right" if args.layout == "left" else "background_source_frame",
			"line_positions": line_positions,
		},
	}
	args.out.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"Wrote {args.out}")


if __name__ == "__main__":
	main()
