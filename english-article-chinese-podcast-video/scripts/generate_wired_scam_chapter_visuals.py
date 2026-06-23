#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


WIDTH = 3840
HEIGHT = 2160
SAFE_BOTTOM = 1540
YELLOW = (255, 240, 0, 255)
CYAN = (0, 212, 255, 255)
WHITE = (255, 255, 255, 255)
MUTED = (178, 188, 194, 255)
BLACK = (0, 0, 0, 255)
RED = (255, 67, 73, 255)
DARK = (5, 7, 10, 255)


@dataclass(frozen=True)
class ChapterSpec:
	index: int
	source_title: str
	short_title: str
	start_turn: int
	end_turn: int
	style: str
	subtitle: str
	steps: tuple[str, ...] = ()
	points: tuple[str, ...] = ()
	motif: str = "screens"


CHAPTERS: tuple[ChapterSpec, ...] = (
	ChapterSpec(1, "开场：电话那头的人，也可能是被关起来的人", "电话那头的人", 1, 10, "comic_scene", "求助，也可能来自笼子里", motif="phone_cell"),
	ChapterSpec(2, "第一幕：纽约夜里收到的一封邮件", "纽约夜里的邮件", 11, 22, "comic_scene", "陌生人说：我被困住了", motif="email"),
	ChapterSpec(3, "第二幕：他不是被骗一次，而是被一整条链条运进去", "一整条链条", 23, 40, "flow", "从招募到扣押，不是偶然被骗", steps=("招聘话术", "跨境转运", "扣证件", "进园区"), motif="route"),
	ChapterSpec(4, "第三幕：诈骗园区不是“几个人聊天”，而是情绪工厂", "情绪工厂", 41, 58, "flow", "诈骗被做成流水线", steps=("伪装人设", "建立信任", "诱导投资", "业绩考核"), motif="factory"),
	ChapterSpec(5, "第四幕：记者面临的第一个道德难题", "记者的难题", 59, 70, "points", "救人、核验和曝光互相拉扯", points=("救人还是核验", "曝光可能带来报复", "每一步都可能误伤"), motif="dilemma"),
	ChapterSpec(6, "第五幕：Red Bull 和记者建立了一套地下通信协议", "地下通信协议", 71, 82, "flow", "一套为了活下来的证据通道", steps=("加密邮箱", "分批传证据", "暗号确认", "离线备份"), motif="encrypted"),
	ChapterSpec(7, "第六幕：他为什么非要冒这个险", "为什么冒险", 83, 92, "comic_scene", "不是英雄主义，是最后的筹码", motif="risk"),
	ChapterSpec(8, "第七幕：他被抓了，所有人都不知道该不该相信他", "他被抓了", 93, 108, "comic_scene", "证据中断，信任也开始摇晃", motif="captured"),
	ChapterSpec(9, "第八幕：没有人来救他，但混乱给了他机会", "混乱给了机会", 109, 120, "comic_scene", "没人来救他，缝隙自己出现", motif="chaos"),
	ChapterSpec(10, "第九幕：他用最后一次骗局逃走了", "最后一次骗局", 121, 130, "comic_scene", "用骗子的规则，骗开一扇门", motif="escape"),
	ChapterSpec(11, "第十幕：Red Bull 变回 Mohammad Muzahir", "变回自己", 131, 140, "comic_scene", "代号消失，名字回来", motif="identity"),
	ChapterSpec(12, "第十一幕：为什么这个故事不只是一个逃亡故事", "不只是逃亡", 141, 152, "points", "一个人逃出来，不代表系统结束", points=("园区像企业", "受害者也被迫害人", "灰色地带吞掉责任"), motif="system"),
	ChapterSpec(13, "第十二幕：中国因素该怎么理解", "中国因素", 153, 158, "points", "受害者、目标与平台交织", points=("不能简化成单一国别故事", "平台、资金和身份跨境流动", "关键是跨境治理失灵"), motif="map"),
	ChapterSpec(14, "结尾：很多个 Red Bull 会不会站出来", "还有多少人", 159, 174, "comic_scene", "下一封邮件，可能来自谁", motif="many_screens"),
)


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
	bg = canvas.filter(ImageFilter.GaussianBlur(2.4))
	bg = ImageEnhance.Color(bg).enhance(0.72)
	bg = ImageEnhance.Contrast(bg).enhance(1.25)
	bg = ImageEnhance.Brightness(bg).enhance(0.62)
	return bg.convert("RGBA")


def _fit_scene_background(path: Path) -> Image.Image:
	img = Image.open(path).convert("RGB")
	src_ratio = img.width / img.height
	dst_ratio = WIDTH / HEIGHT
	if src_ratio > dst_ratio:
		new_h = HEIGHT
		new_w = int(new_h * src_ratio)
	else:
		new_w = WIDTH
		new_h = int(new_w / src_ratio)
	img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
	left = (new_w - WIDTH) // 2
	top = (new_h - HEIGHT) // 2
	img = img.crop((left, top, left + WIDTH, top + HEIGHT))
	img = ImageEnhance.Contrast(img).enhance(1.08)
	img = ImageEnhance.Brightness(img).enhance(0.86)
	return img.convert("RGBA")


def _alpha_rect(img: Image.Image, box: tuple[int, int, int, int], fill: tuple[int, int, int, int], radius: int = 0, outline: tuple[int, int, int, int] | None = None, width: int = 4) -> Image.Image:
	overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
	draw = ImageDraw.Draw(overlay)
	if radius:
		draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
	else:
		draw.rectangle(box, fill=fill, outline=outline, width=width)
	return Image.alpha_composite(img, overlay)


def _draw_text(
	draw: ImageDraw.ImageDraw,
	xy: tuple[int, int],
	text: str,
	font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
	fill: tuple[int, int, int, int],
	stroke: int = 12,
	center: bool = False,
	anchor: str | None = None,
) -> None:
	x, y = xy
	if center:
		bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
		x = (WIDTH - (bbox[2] - bbox[0])) // 2
	for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2), (0, 0)]:
		draw.text((x + ox, y + oy), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=BLACK, anchor=anchor)


def _wrap(text: str, size: int) -> list[str]:
	if len(text) <= size:
		return [text] if text else []
	lines: list[str] = []
	remaining = text
	punctuation = "，,。.:：；;、？！?!"
	while len(remaining) > size:
		split_at = size
		if len(remaining) - split_at <= max(2, size // 4):
			split_at = max(size // 2, len(remaining) // 2)
		for idx in range(min(size, len(remaining) - 1), max(1, size // 3) - 1, -1):
			if remaining[idx] in punctuation:
				split_at = idx + 1
				break
		lines.append(remaining[:split_at])
		remaining = remaining[split_at:]
	if remaining:
		lines.append(remaining)
	return lines


def _base(bg: Image.Image, chapter: ChapterSpec) -> Image.Image:
	img = bg.copy()
	img = _alpha_rect(img, (0, 0, WIDTH, HEIGHT), (0, 0, 0, 68))
	img = _alpha_rect(img, (0, SAFE_BOTTOM, WIDTH, HEIGHT), (0, 0, 0, 112))
	draw = ImageDraw.Draw(img)
	random.seed(chapter.index * 171)
	for _ in range(22):
		x = random.randint(0, WIDTH)
		y = random.randint(0, SAFE_BOTTOM)
		r = random.randint(120, 760)
		draw.arc((x - r, y - r, x + r, y + r), random.randint(0, 180), random.randint(180, 360), fill=(255, 67, 73, random.randint(18, 52)), width=random.randint(2, 6))
	for x in range(0, WIDTH, 240):
		draw.line((x, 0, x, HEIGHT), fill=(255, 255, 255, 9), width=1)
	for y in range(0, HEIGHT, 240):
		draw.line((0, y, WIDTH, y), fill=(255, 255, 255, 8), width=1)
	draw.line((180, 1900, 3660, 1900), fill=(255, 67, 73, 78), width=8)
	_draw_text(draw, (220, 130), f"CH {chapter.index:02d}", _font(74), CYAN, stroke=8)
	return img


def _header(draw: ImageDraw.ImageDraw, chapter: ChapterSpec, centered: bool = False) -> None:
	if centered:
		_draw_text(draw, (0, 168), chapter.short_title, _font(152), YELLOW, stroke=18, center=True)
		for i, line in enumerate(_wrap(chapter.subtitle, 18)[:2]):
			_draw_text(draw, (0, 370 + i * 92), line, _font(70), WHITE, stroke=8, center=True)
		return
	_draw_text(draw, (220, 250), chapter.short_title, _font(158), YELLOW, stroke=18)
	for i, line in enumerate(_wrap(chapter.subtitle, 17)[:2]):
		_draw_text(draw, (228, 474 + i * 92), line, _font(72), WHITE, stroke=8)


def _person(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0, color: tuple[int, int, int, int] = (12, 14, 18, 255), accent: bool = False) -> None:
	r = int(58 * scale)
	body_w = int(160 * scale)
	body_h = int(300 * scale)
	draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=(255, 255, 255, 50), width=max(2, int(3 * scale)))
	draw.rounded_rectangle((x - body_w // 2, y + r - 4, x + body_w // 2, y + r + body_h), radius=int(60 * scale), fill=color, outline=(255, 255, 255, 38), width=max(2, int(3 * scale)))
	if accent:
		draw.line((x - body_w // 2, y + r + 80, x + body_w // 2, y + r + 70), fill=RED, width=max(5, int(8 * scale)))


def _phone(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], glow: bool = True) -> None:
	x1, y1, x2, y2 = box
	if glow:
		draw.rounded_rectangle((x1 - 32, y1 - 32, x2 + 32, y2 + 32), radius=80, fill=(0, 212, 255, 32))
	draw.rounded_rectangle(box, radius=80, fill=(10, 12, 16, 255), outline=(210, 220, 225, 95), width=10)
	draw.rounded_rectangle((x1 + 110, y1 + 58, x2 - 110, y1 + 104), radius=24, fill=(0, 0, 0, 255))
	for i in range(4):
		yy = y1 + 230 + i * 170
		draw.rounded_rectangle((x1 + 96, yy, x2 - 96, yy + 86), radius=38, fill=(255, 255, 255, 42))
		draw.line((x1 + 146, yy + 43, x2 - 220, yy + 43), fill=(255, 255, 255, 58), width=8)


def _laptop(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
	draw.rounded_rectangle((x, y, x + w, y + h), radius=30, fill=(8, 10, 13, 255), outline=(0, 212, 255, 128), width=8)
	draw.rectangle((x + 60, y + 70, x + w - 60, y + h - 80), fill=(2, 8, 12, 255))
	draw.line((x + 90, y + 145, x + w - 140, y + 145), fill=CYAN, width=10)
	draw.line((x + 90, y + 240, x + w - 300, y + 240), fill=(255, 255, 255, 92), width=10)
	draw.line((x + 90, y + 335, x + w - 220, y + 335), fill=(255, 255, 255, 72), width=10)
	draw.polygon([(x - 90, y + h + 30), (x + w + 90, y + h + 30), (x + w - 40, y + h + 120), (x + 40, y + h + 120)], fill=(18, 20, 25, 255))


def _door(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, open_gap: int = 0) -> None:
	draw.rectangle((x, y, x + w, y + h), fill=(8, 9, 12, 255), outline=(255, 255, 255, 82), width=8)
	if open_gap:
		draw.polygon([(x + w - open_gap, y + 35), (x + w + 140, y + 95), (x + w + 140, y + h - 80), (x + w - open_gap, y + h - 20)], fill=(255, 67, 73, 80), outline=(255, 67, 73, 150))
	draw.ellipse((x + w - 110, y + h // 2, x + w - 78, y + h // 2 + 32), fill=YELLOW)


def _route(draw: ImageDraw.ImageDraw) -> None:
	points = [(2230, 600), (2520, 760), (2810, 690), (3100, 880), (3330, 780)]
	for a, b in zip(points, points[1:]):
		draw.line((a[0], a[1], b[0], b[1]), fill=(255, 67, 73, 190), width=10)
	for i, point in enumerate(points):
		draw.ellipse((point[0] - 28, point[1] - 28, point[0] + 28, point[1] + 28), fill=CYAN if i == 0 else RED)


def _draw_motif(draw: ImageDraw.ImageDraw, motif: str) -> None:
	if motif == "phone_cell":
		_phone(draw, (2450, 420, 3220, 1420))
		for x in range(2100, 3560, 180):
			draw.line((x, 410, x, 1480), fill=(255, 255, 255, 48), width=8)
		_person(draw, 2240, 1050, 1.35, accent=True)
	elif motif == "email":
		_laptop(draw, 2100, 570, 1180, 740)
		draw.polygon([(2420, 720), (2960, 720), (2690, 940)], fill=(255, 240, 0, 36), outline=YELLOW)
		draw.rectangle((2420, 720, 2960, 1040), outline=YELLOW, width=8)
	elif motif == "risk":
		_person(draw, 2560, 850, 1.75, accent=True)
		draw.line((2090, 1390, 3370, 520), fill=(255, 67, 73, 128), width=12)
		for i, text in enumerate(("证据", "风险", "家人")):
			_draw_text(draw, (2150 + i * 430, 1320 - i * 220), text, _font(70), CYAN if i == 0 else WHITE, stroke=8)
	elif motif == "captured":
		_person(draw, 2710, 830, 1.6, accent=True)
		for y in range(410, 1420, 170):
			draw.line((2110, y, 3410, y + 120), fill=(255, 67, 73, 105), width=10)
		_door(draw, 3140, 500, 330, 850)
	elif motif == "chaos":
		for i in range(8):
			x = 2100 + i * 170
			y = 820 + int(math.sin(i) * 180)
			_person(draw, x, y, 0.82, color=(14, 14, 17, 255), accent=i % 3 == 0)
		for i in range(10):
			x = 2050 + i * 150
			draw.line((x, 430 + (i % 2) * 90, x + 480, 1250 - (i % 3) * 80), fill=(255, 67, 73, 82), width=7)
	elif motif == "escape":
		_door(draw, 2830, 470, 460, 910, open_gap=120)
		_person(draw, 2450, 970, 1.24, accent=True)
		draw.line((2200, 1390, 3310, 1390), fill=CYAN, width=12)
		draw.polygon([(3310, 1390), (3220, 1340), (3220, 1440)], fill=CYAN)
	elif motif == "identity":
		_person(draw, 2420, 830, 1.55, color=(18, 20, 24, 255), accent=True)
		_person(draw, 3020, 830, 1.55, color=(18, 20, 24, 150), accent=False)
		draw.line((2700, 1040, 2860, 1040), fill=CYAN, width=12)
		draw.polygon([(2860, 1040), (2790, 990), (2790, 1090)], fill=CYAN)
	elif motif == "many_screens":
		for i in range(9):
			x = 2060 + (i % 3) * 420
			y = 450 + (i // 3) * 310
			draw.rounded_rectangle((x, y, x + 330, y + 210), radius=24, fill=(8, 10, 14, 235), outline=(255, 255, 255, 55), width=5)
			draw.line((x + 38, y + 70, x + 250, y + 70), fill=CYAN if i == 4 else (255, 255, 255, 58), width=8)
			draw.line((x + 38, y + 130, x + 210, y + 130), fill=(255, 67, 73, 95), width=8)
		_person(draw, 3370, 1110, 1.0, accent=True)
	else:
		_phone(draw, (2450, 500, 3200, 1370))


def _comic_card(bg: Image.Image, chapter: ChapterSpec, out: Path, scene_bg: Path | None = None) -> None:
	if scene_bg and scene_bg.exists():
		img = _fit_scene_background(scene_bg)
		img = _alpha_rect(img, (0, 0, WIDTH, HEIGHT), (0, 0, 0, 34))
		img = _alpha_rect(img, (0, 0, 1620, SAFE_BOTTOM + 40), (0, 0, 0, 142))
		img = _alpha_rect(img, (0, SAFE_BOTTOM, WIDTH, HEIGHT), (0, 0, 0, 118))
	else:
		img = _base(bg, chapter)
		img = _alpha_rect(img, (1820, 250, 3580, SAFE_BOTTOM - 60), (0, 0, 0, 118), radius=54, outline=(255, 255, 255, 40), width=6)
		img = _alpha_rect(img, (1750, 335, 1865, SAFE_BOTTOM - 130), (255, 67, 73, 150))
	draw = ImageDraw.Draw(img)
	_draw_text(draw, (220, 130), f"CH {chapter.index:02d}", _font(74), CYAN, stroke=8)
	draw.line((1660, 310, 1660, SAFE_BOTTOM - 120), fill=RED, width=12)
	_header(draw, chapter)
	if scene_bg is None or not scene_bg.exists():
		_draw_motif(draw, chapter.motif)
	img.save(out)


def _flow_card(bg: Image.Image, chapter: ChapterSpec, out: Path) -> None:
	img = _base(bg, chapter)
	draw = ImageDraw.Draw(img)
	_header(draw, chapter, centered=True)
	x0 = 245
	y0 = 800
	card_w = 740
	card_h = 500
	gap = 105
	for idx, step in enumerate(chapter.steps[:4]):
		x = x0 + idx * (card_w + gap)
		active = idx == 1 or idx == 2
		img = _alpha_rect(img, (x, y0, x + card_w, y0 + card_h), (0, 0, 0, 190), radius=40, outline=CYAN if active else (255, 255, 255, 48), width=8)
		draw = ImageDraw.Draw(img)
		_draw_text(draw, (x + 54, y0 + 60), f"{idx + 1:02d}", _font(96), CYAN if active else YELLOW, stroke=9)
		for line_idx, line in enumerate(_wrap(step, 8)[:2]):
			_draw_text(draw, (x + 54, y0 + 220 + line_idx * 92), line, _font(74), WHITE, stroke=8)
		if idx < len(chapter.steps[:4]) - 1:
			draw.line((x + card_w + 22, y0 + 250, x + card_w + gap - 22, y0 + 250), fill=RED, width=16)
			draw.polygon([(x + card_w + gap - 22, y0 + 250), (x + card_w + gap - 74, y0 + 213), (x + card_w + gap - 74, y0 + 287)], fill=RED)
	if chapter.motif == "route":
		_route(draw)
	elif chapter.motif == "factory":
		for i in range(6):
			_person(draw, 2320 + i * 160, 1470, 0.55, color=(14, 14, 18, 220), accent=i == 2)
	elif chapter.motif == "encrypted":
		_phone(draw, (2850, 1310, 3270, 1810), glow=False)
		_draw_text(draw, (2160, 1535), "加密 / 暗号 / 备份", _font(78), CYAN, stroke=8)
	img.save(out)


def _points_card(bg: Image.Image, chapter: ChapterSpec, out: Path) -> None:
	img = _base(bg, chapter)
	img = _alpha_rect(img, (430, 285, 3400, SAFE_BOTTOM - 70), (0, 0, 0, 164), radius=58, outline=(255, 255, 255, 38), width=6)
	draw = ImageDraw.Draw(img)
	_header(draw, chapter, centered=True)
	y = 710
	for idx, point in enumerate(chapter.points[:4]):
		color = CYAN if idx == 0 else YELLOW
		_draw_text(draw, (700, y), f"{idx + 1}", _font(96), color, stroke=10)
		for line_idx, line in enumerate(_wrap(point, 19)[:2]):
			_draw_text(draw, (875, y + line_idx * 94), line, _font(80), WHITE, stroke=8)
		y += 255
	if chapter.motif == "map":
		draw.arc((2350, 620, 3360, 1430), 210, 340, fill=(255, 67, 73, 120), width=12)
		for x, yy in ((2580, 1120), (2910, 820), (3150, 1160)):
			draw.ellipse((x - 34, yy - 34, x + 34, yy + 34), fill=CYAN)
	elif chapter.motif == "system":
		for i in range(4):
			draw.rounded_rectangle((2480 + i * 150, 1180 - i * 80, 2600 + i * 150, 1300 - i * 80), radius=16, fill=(255, 67, 73, 82), outline=(255, 255, 255, 42), width=4)
	else:
		draw.line((2470, 850, 3200, 1300), fill=(255, 67, 73, 80), width=10)
	img.save(out)


def _render_chapter(bg: Image.Image, chapter: ChapterSpec, out: Path, scene_bg: Path | None = None) -> None:
	if chapter.style == "flow":
		_flow_card(bg, chapter, out)
	elif chapter.style == "points":
		_points_card(bg, chapter, out)
	else:
		_comic_card(bg, chapter, out, scene_bg)


def _make_contact_sheet(paths: list[Path], out: Path) -> None:
	thumb_w = 960
	thumb_h = 540
	rows = 4
	cols = 4
	sheet = Image.new("RGB", (thumb_w * cols, thumb_h * rows), (4, 5, 7))
	for idx, path in enumerate(paths):
		img = Image.open(path).convert("RGB")
		img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
		x = (idx % cols) * thumb_w
		y = (idx // cols) * thumb_h
		canvas = Image.new("RGB", (thumb_w, thumb_h), (0, 0, 0))
		canvas.paste(img, ((thumb_w - img.width) // 2, (thumb_h - img.height) // 2))
		sheet.paste(canvas, (x, y))
	sheet.save(out, quality=92)


def main() -> int:
	output_dir = Path("/Volumes/GT34/Downloads/awesome_english_latest_china/wired_scam_compound_chapter_visuals").resolve()
	background = Path("/Volumes/GT34/Downloads/awesome_english_latest_china/wired_scam_compound_cover/scam_compound_generated_background_4k.png").resolve()
	output_dir.mkdir(parents=True, exist_ok=True)
	scene_bg_dir = output_dir / "scene_backgrounds"
	bg = _fit_background(background)
	paths: list[Path] = []
	plan: dict[str, object] = {
		"schema_version": "article-podcast-chapter-visuals.v1",
		"visual_system": {
			"resolution": "3840x2160",
			"palette": {
				"background": "near-black investigative collage",
				"yellow": "#fff000",
				"cyan": "#00d4ff",
				"red": "#ff4349",
				"white": "#ffffff",
			},
			"notes": "Unified dark investigative comic/infographic style. Scene chapters use no-text AI-generated comic backgrounds plus local title overlay. Keep important text above subtitle-safe lower band.",
		},
		"chapters": [],
	}
	for chapter in CHAPTERS:
		filename = f"chapter_{chapter.index:02d}_{chapter.style}.png"
		path = output_dir / filename
		scene_bg = scene_bg_dir / f"chapter_{chapter.index:02d}_background.png"
		_render_chapter(bg, chapter, path, scene_bg if chapter.style == "comic_scene" else None)
		paths.append(path)
		plan["chapters"].append({
			"chapter_index": chapter.index,
			"chapter_title": chapter.source_title,
			"short_title": chapter.short_title,
			"start_turn": chapter.start_turn,
			"end_turn": chapter.end_turn,
			"visual_style": chapter.style,
			"onscreen_text": [chapter.short_title, chapter.subtitle, *chapter.steps, *chapter.points],
			"motif": chapter.motif,
			"image": filename,
			"scene_background": f"scene_backgrounds/chapter_{chapter.index:02d}_background.png" if chapter.style == "comic_scene" and scene_bg.exists() else None,
		})
	_make_contact_sheet(paths, output_dir / "chapter_visuals_contact_sheet.jpg")
	(output_dir / "chapter_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	print(json.dumps({
		"output_dir": str(output_dir),
		"chapter_plan": str(output_dir / "chapter_plan.json"),
		"contact_sheet": str(output_dir / "chapter_visuals_contact_sheet.jpg"),
		"images": [str(path) for path in paths],
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
