#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


WIDTH = 3840
HEIGHT = 2160
YELLOW = (255, 240, 0, 255)
CYAN = (0, 212, 255, 255)
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
RED = (255, 67, 73, 255)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
	candidates = [
		"/System/Library/Fonts/PingFang.ttc",
		"/System/Library/Fonts/STHeiti Medium.ttc",
		"/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
		"/Library/Fonts/Arial Unicode.ttf",
	]
	for candidate in candidates:
		path = Path(candidate)
		if path.exists():
			return ImageFont.truetype(str(path), size)
	return ImageFont.load_default()


def _fit_background(path: Path) -> Image.Image:
	img = Image.open(path).convert("RGB")
	img.thumbnail((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
	canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
	canvas.paste(img, ((WIDTH - img.width) // 2, (HEIGHT - img.height) // 2))
	bg = canvas.filter(ImageFilter.GaussianBlur(3))
	bg = ImageEnhance.Contrast(bg).enhance(1.18)
	bg = ImageEnhance.Brightness(bg).enhance(0.82)
	return bg.convert("RGBA")


def _draw_text(
	draw: ImageDraw.ImageDraw,
	xy: tuple[int, int],
	text: str,
	font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
	fill: tuple[int, int, int, int],
	stroke: int = 12,
	center: bool = False,
) -> None:
	x, y = xy
	bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
	if center:
		x = (WIDTH - (bbox[2] - bbox[0])) // 2
	for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2), (0, 0)]:
		draw.text((x + ox, y + oy), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=BLACK)


def _wrap(text: str, size: int) -> list[str]:
	if len(text) <= size:
		return [text] if text else [text]

	lines: list[str] = []
	remaining = text
	punctuation = "，,。.:：；;、？！?!"
	while len(remaining) > size:
		split_at = size
		if len(remaining) - split_at <= max(2, size // 4):
			split_at = max(size // 2, len(remaining) // 2)

		search_start = max(1, size // 3)
		for idx in range(min(size, len(remaining) - 1), search_start - 1, -1):
			if remaining[idx] in punctuation:
				split_at = idx + 1
				break

		lines.append(remaining[:split_at])
		remaining = remaining[split_at:]

	if remaining:
		lines.append(remaining)
	return lines or [text]


def _shade(img: Image.Image, box: tuple[int, int, int, int], fill: tuple[int, int, int, int]) -> Image.Image:
	overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
	draw = ImageDraw.Draw(overlay)
	draw.rectangle(box, fill=fill)
	return Image.alpha_composite(img, overlay)


def _panel(img: Image.Image, box: tuple[int, int, int, int], fill=(0, 0, 0, 178), outline=None) -> Image.Image:
	overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
	draw = ImageDraw.Draw(overlay)
	draw.rounded_rectangle(box, radius=34, fill=fill, outline=outline, width=8 if outline else 1)
	return Image.alpha_composite(img, overlay)


def _scene_card(bg: Image.Image, chapter: str, subtitle: str, out: Path) -> None:
	img = bg.copy()
	img = _shade(img, (0, 0, WIDTH, HEIGHT), (0, 0, 0, 48))
	img = _shade(img, (0, 0, 1500, HEIGHT), (0, 0, 0, 118))
	draw = ImageDraw.Draw(img)
	draw.line((1420, 260, 1420, 1900), fill=RED, width=12)
	_draw_text(draw, (220, 330), "第一幕", _font(124), CYAN, stroke=14)
	for i, line in enumerate(_wrap(chapter, 10)[:2]):
		_draw_text(draw, (220, 530 + i * 190), line, _font(156), YELLOW, stroke=18)
	for i, line in enumerate(_wrap(subtitle, 15)[:2]):
		_draw_text(draw, (230, 1020 + i * 120), line, _font(82), WHITE, stroke=9)
	img = _panel(img, (2140, 1460, 3560, 1810), fill=(0, 0, 0, 150))
	draw = ImageDraw.Draw(img)
	_draw_text(draw, (2220, 1510), "内部邮件", _font(92), WHITE, stroke=10)
	_draw_text(draw, (2220, 1640), "流程图 / 话术 / 截图", _font(72), CYAN, stroke=8)
	img.save(out)


def _flow_card(bg: Image.Image, chapter: str, steps: list[str], out: Path) -> None:
	img = bg.copy()
	img = _shade(img, (0, 0, WIDTH, HEIGHT), (0, 0, 0, 82))
	draw = ImageDraw.Draw(img)
	_draw_text(draw, (0, 210), chapter, _font(148), YELLOW, stroke=18, center=True)
	x0 = 260
	y0 = 920
	card_w = 720
	gap = 120
	for idx, step in enumerate(steps[:4]):
		x = x0 + idx * (card_w + gap)
		img = _panel(img, (x, y0, x + card_w, y0 + 520), fill=(0, 0, 0, 185), outline=CYAN if idx == 1 else None)
		draw = ImageDraw.Draw(img)
		_draw_text(draw, (x + 48, y0 + 54), f"{idx + 1:02d}", _font(92), CYAN if idx == 1 else YELLOW, stroke=10)
		for line_idx, line in enumerate(_wrap(step, 9)[:3]):
			_draw_text(draw, (x + 48, y0 + 190 + line_idx * 92), line, _font(70), WHITE, stroke=8)
		if idx < min(4, len(steps)) - 1:
			draw.line((x + card_w + 18, y0 + 260, x + card_w + gap - 18, y0 + 260), fill=RED, width=16)
			draw.polygon([
				(x + card_w + gap - 18, y0 + 260),
				(x + card_w + gap - 66, y0 + 224),
				(x + card_w + gap - 66, y0 + 296),
			], fill=RED)
	img.save(out)


def _points_card(bg: Image.Image, chapter: str, points: list[str], out: Path) -> None:
	img = bg.copy()
	img = _shade(img, (0, 0, WIDTH, HEIGHT), (0, 0, 0, 92))
	img = _panel(img, (420, 250, 3420, 1880), fill=(0, 0, 0, 150))
	draw = ImageDraw.Draw(img)
	_draw_text(draw, (0, 370), chapter, _font(150), YELLOW, stroke=18, center=True)
	y = 780
	for idx, point in enumerate(points[:4]):
		color = CYAN if idx == 0 else YELLOW
		_draw_text(draw, (720, y), f"{idx + 1}", _font(92), color, stroke=10)
		for line_idx, line in enumerate(_wrap(point, 18)[:2]):
			_draw_text(draw, (880, y + line_idx * 90), line, _font(78), WHITE, stroke=8)
		y += 250
	img.save(out)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Compose 4K chapter-card style options for article podcast videos.")
	parser.add_argument("--background", required=True)
	parser.add_argument("--out-dir", required=True)
	parser.add_argument("--chapter", required=True)
	parser.add_argument("--subtitle", default="")
	parser.add_argument("--steps", nargs="*", default=[])
	parser.add_argument("--points", nargs="*", default=[])
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	out_dir = Path(args.out_dir).expanduser().resolve()
	out_dir.mkdir(parents=True, exist_ok=True)
	bg = _fit_background(Path(args.background).expanduser().resolve())
	steps = args.steps or ["陌生邮件出现", "内部证据传来", "诈骗流程曝光", "记者开始核验"]
	points = args.points or ["陌生邮件像诈骗，但材料越来越具体", "园区像公司一样管理诈骗业绩", "第一批证据打开了系统内部"]
	_scene_card(bg, args.chapter, args.subtitle, out_dir / "chapter_option_scene.png")
	_flow_card(bg, args.chapter, steps, out_dir / "chapter_option_flow.png")
	_points_card(bg, args.chapter, points, out_dir / "chapter_option_points.png")
	manifest = {
		"chapter": args.chapter,
		"subtitle": args.subtitle,
		"outputs": {
			"scene": str(out_dir / "chapter_option_scene.png"),
			"flow": str(out_dir / "chapter_option_flow.png"),
			"points": str(out_dir / "chapter_option_points.png"),
		},
	}
	(out_dir / "chapter_options_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	print(json.dumps(manifest, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
