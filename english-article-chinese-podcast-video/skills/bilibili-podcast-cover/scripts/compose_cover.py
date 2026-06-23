#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
	from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except ModuleNotFoundError as exc:
	raise SystemExit("Pillow is required. Use the Codex workspace dependency Python or install Pillow.") from exc


COLOR_MAP = {
	"yellow": (255, 240, 0),
	"cyan": (0, 212, 255),
	"white": (255, 255, 255),
	"red": (255, 70, 62),
}

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TITLE_FONT = SKILL_DIR / "assets" / "fonts" / "XinQingNianTi.ttf"


def parse_line(markup: str, default_color: str) -> list[tuple[str, str]]:
	parts: list[tuple[str, str]] = []
	pos = 0
	for match in re.finditer(r"\{(yellow|cyan|white|red):([^{}]+)\}", markup):
		if match.start() > pos:
			parts.append((markup[pos:match.start()], default_color))
		parts.append((match.group(2), match.group(1)))
		pos = match.end()
	if pos < len(markup):
		parts.append((markup[pos:], default_color))
	return [(text, color) for text, color in parts if text]


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


def find_font(user_font: str | None) -> tuple[str, int]:
	if user_font:
		return user_font, 0
	candidates = [
		(str(DEFAULT_TITLE_FONT), 0),
		("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
		("/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc", 0),
		("/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc", 0),
		("/System/Library/Fonts/STHeiti Medium.ttc", 1),
		("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
		("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 0),
		("/System/Library/Fonts/PingFang.ttc", 0),
		("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),
	]
	for path, index in candidates:
		if Path(path).exists():
			return path, index
	raise SystemExit("No suitable Chinese font found. Pass --font /path/to/font.")


def load_font(font_path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
	return ImageFont.truetype(font_path, size, index=index)


def text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, stroke_width: int) -> tuple[int, int]:
	box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
	return box[2] - box[0], box[3] - box[1]


def line_width(draw: ImageDraw.ImageDraw, segments: list[tuple[str, str]], font: ImageFont.FreeTypeFont, stroke_width: int, gap: int) -> int:
	width = 0
	for idx, (text, _color) in enumerate(segments):
		w, _h = text_bbox(draw, text, font, stroke_width)
		width += w
		if idx:
			width += gap
	return width


def fit_font_size(
	draw: ImageDraw.ImageDraw,
	segments: list[tuple[str, str]],
	font_path: str,
	font_index: int,
	start_size: int,
	stroke_width: int,
	gap: int,
	max_width: int,
) -> ImageFont.FreeTypeFont:
	size = start_size
	while size > 80:
		font = load_font(font_path, font_index, size)
		if line_width(draw, segments, font, stroke_width, gap) <= max_width:
			return font
		size -= 8
	return load_font(font_path, font_index, size)


def add_readability_layers(im: Image.Image, band: bool = True) -> Image.Image:
	w, h = im.size
	im = ImageEnhance.Contrast(im).enhance(1.08)
	im = ImageEnhance.Color(im).enhance(1.06)
	layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
	draw = ImageDraw.Draw(layer)
	if band:
		draw.rounded_rectangle(
			(int(w * 0.07), int(h * 0.19), int(w * 0.93), int(h * 0.73)),
			radius=int(h * 0.042),
			fill=(0, 0, 0, 72),
		)
		layer = layer.filter(ImageFilter.GaussianBlur(int(w * 0.0045)))
	im = Image.alpha_composite(im.convert("RGBA"), layer)
	vignette = Image.new("L", (w, h), 0)
	vd = ImageDraw.Draw(vignette)
	vd.ellipse((-int(w * 0.13), -int(h * 0.18), int(w * 1.13), int(h * 1.2)), fill=255)
	vignette = vignette.filter(ImageFilter.GaussianBlur(int(w * 0.055)))
	alpha = Image.eval(vignette, lambda p: 105 - int(p * 0.38))
	black = Image.new("RGBA", (w, h), (0, 0, 0, 0))
	black.putalpha(alpha)
	return Image.alpha_composite(im, black)


def add_simple_readability_layers(im: Image.Image) -> Image.Image:
	w, h = im.size
	im = ImageEnhance.Contrast(im).enhance(1.12)
	im = ImageEnhance.Color(im).enhance(1.08)
	layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
	draw = ImageDraw.Draw(layer)
	for y in range(h):
		t = y / max(1, h - 1)
		alpha = int(80 + 82 * abs(t - 0.50))
		draw.line((0, y, w, y), fill=(0, 0, 0, alpha))
	for x in range(w):
		t = x / max(1, w - 1)
		alpha = int(76 * max(0, 1 - abs(t - 0.45) / 0.55))
		draw.line((x, 0, x, h), fill=(0, 0, 0, alpha))
	layer = layer.filter(ImageFilter.GaussianBlur(int(w * 0.002)))
	im = Image.alpha_composite(im.convert("RGBA"), layer)
	vignette = Image.new("L", (w, h), 0)
	vd = ImageDraw.Draw(vignette)
	vd.ellipse((-int(w * 0.18), -int(h * 0.24), int(w * 1.18), int(h * 1.24)), fill=255)
	vignette = vignette.filter(ImageFilter.GaussianBlur(int(w * 0.060)))
	alpha = Image.eval(vignette, lambda p: 112 - int(p * 0.46))
	black = Image.new("RGBA", (w, h), (0, 0, 0, 0))
	black.putalpha(alpha)
	return Image.alpha_composite(im, black)


def draw_heavy_text(
	draw: ImageDraw.ImageDraw,
	x: int,
	y: int,
	text: str,
	font: ImageFont.FreeTypeFont,
	fill: tuple[int, int, int],
	stroke_width: int,
	faux_bold: int,
) -> None:
	for dx, dy, alpha, extra in [
		(int(stroke_width * 0.8), int(stroke_width * 0.9), 210, int(stroke_width * 0.42)),
		(int(stroke_width * 0.42), int(stroke_width * 0.5), 165, int(stroke_width * 0.25)),
		(0, 0, 120, int(stroke_width * 0.55)),
	]:
		draw.text(
			(x + dx, y + dy),
			text,
			font=font,
			fill=(0, 0, 0, alpha),
			stroke_width=stroke_width + extra,
			stroke_fill=(0, 0, 0, alpha),
		)
	offsets: list[tuple[int, int]] = []
	for ox in range(-faux_bold, faux_bold + 1, 2):
		for oy in range(-faux_bold, faux_bold + 1, 2):
			if ox * ox + oy * oy <= faux_bold * faux_bold + 3:
				offsets.append((ox, oy))
	for ox, oy in offsets:
		draw.text((x + ox, y + oy), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=(0, 0, 0))
	draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=(0, 0, 0))


def draw_centered_segments(
	draw: ImageDraw.ImageDraw,
	canvas_w: int,
	y: int,
	segments: list[tuple[str, str]],
	font: ImageFont.FreeTypeFont,
	stroke_width: int,
	faux_bold: int,
	gap: int,
) -> int:
	widths = [text_bbox(draw, text, font, stroke_width + faux_bold)[0] for text, _color in segments]
	total = sum(widths) + gap * (len(segments) - 1)
	x = (canvas_w - total) // 2
	max_h = 0
	for (text, color), width in zip(segments, widths):
		draw_heavy_text(draw, x, y, text, font, COLOR_MAP[color], stroke_width, faux_bold)
		_h = text_bbox(draw, text, font, stroke_width)[1]
		max_h = max(max_h, _h)
		x += width + gap
	return max_h


def write_manifest(path: Path, data: dict[str, object]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
	parser = argparse.ArgumentParser(description="Compose a 4K Bilibili-style Chinese cover.")
	parser.add_argument("--background", required=True, type=Path)
	parser.add_argument("--out", required=True, type=Path)
	parser.add_argument("--line1", required=True)
	parser.add_argument("--line2", required=True)
	parser.add_argument("--line3", required=True)
	parser.add_argument("--size", default="3840x2160")
	parser.add_argument("--font", default=None)
	parser.add_argument("--jpg", action="store_true", help="Also emit a .jpg sibling.")
	parser.add_argument("--no-band", action="store_true", help="Disable the dark rounded band behind text.")
	args = parser.parse_args()

	match = re.fullmatch(r"(\d+)x(\d+)", args.size)
	if not match:
		raise SystemExit("--size must look like 3840x2160")
	canvas = (int(match.group(1)), int(match.group(2)))
	assert canvas[0] / canvas[1] > 1.7, "expected a 16:9-ish canvas"

	background = cover_crop(Image.open(args.background).convert("RGB"), canvas)
	im = add_readability_layers(background, band=not args.no_band)
	draw = ImageDraw.Draw(im)
	font_path, font_index = find_font(args.font)

	lines = [
		(parse_line(args.line1, "yellow"), int(canvas[1] * 0.142), int(canvas[0] * 0.0088), int(canvas[0] * 0.0016)),
		(parse_line(args.line2, "white"), int(canvas[1] * 0.102), int(canvas[0] * 0.0080), int(canvas[0] * 0.0016)),
		(parse_line(args.line3, "yellow"), int(canvas[1] * 0.114), int(canvas[0] * 0.0083), int(canvas[0] * 0.0016)),
	]
	max_width = int(canvas[0] * 0.86)
	gap = int(canvas[0] * 0.011)
	fonts = [
		fit_font_size(draw, segments, font_path, font_index, size, stroke, gap, max_width)
		for segments, size, stroke, _faux in lines
	]
	heights = [
		max(text_bbox(draw, text, font, stroke)[1] for text, _color in segments)
		for (segments, _size, stroke, _faux), font in zip(lines, fonts)
	]
	line_gap = int(canvas[1] * 0.08)
	block_h = sum(heights) + line_gap * 2
	y = (canvas[1] - block_h) // 2 - int(canvas[1] * 0.02)
	for (segments, _size, stroke, faux), font, height in zip(lines, fonts, heights):
		draw_centered_segments(draw, canvas[0], y, segments, font, stroke, int(faux), gap)
		y += height + line_gap

	args.out.parent.mkdir(parents=True, exist_ok=True)
	im.convert("RGB").save(args.out)
	jpg_path = args.out.with_suffix(".jpg")
	if args.jpg or args.out.suffix.lower() != ".jpg":
		im.convert("RGB").save(jpg_path, quality=94, optimize=True)
	write_manifest(
		args.out.with_suffix(".manifest.json"),
		{
			"background": str(args.background),
			"output": str(args.out),
			"jpg_output": str(jpg_path),
			"size": canvas,
			"font": font_path,
			"font_index": font_index,
			"lines": [args.line1, args.line2, args.line3],
		},
	)
	print(f"Wrote {args.out}")
	print(f"Wrote {jpg_path}")


if __name__ == "__main__":
	main()
