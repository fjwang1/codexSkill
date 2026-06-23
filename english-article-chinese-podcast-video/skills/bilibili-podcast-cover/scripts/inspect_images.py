#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
	from PIL import Image, ImageDraw, ImageFont
except ModuleNotFoundError as exc:
	raise SystemExit("Pillow is required. Use the Codex workspace dependency Python or install Pillow.") from exc


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def find_images(input_dir: Path) -> list[Path]:
	assert input_dir.exists(), f"missing input dir: {input_dir}"
	return sorted(
		[p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS],
		key=lambda p: str(p).lower(),
	)


def image_info(path: Path, root: Path) -> dict[str, object] | None:
	try:
		with Image.open(path) as im:
			width, height = im.size
	except Exception:
		return None
	aspect = width / height if height else 0
	return {
		"path": str(path),
		"relative_path": str(path.relative_to(root)),
		"width": width,
		"height": height,
		"aspect": round(aspect, 4),
		"bytes": path.stat().st_size,
	}


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
	for font_path in [
		"/System/Library/Fonts/PingFang.ttc",
		"/System/Library/Fonts/Hiragino Sans GB.ttc",
		"/System/Library/Fonts/STHeiti Medium.ttc",
		"/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
	]:
		if Path(font_path).exists():
			try:
				return ImageFont.truetype(font_path, size)
			except Exception:
				pass
	return ImageFont.load_default()


def make_contact_sheet(records: list[dict[str, object]], out_path: Path) -> None:
	if not records:
		return
	thumb_w, thumb_h = 360, 230
	label_h = 56
	cols = 3
	rows = (len(records) + cols - 1) // cols
	sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + label_h)), "white")
	draw = ImageDraw.Draw(sheet)
	font = load_font(16)
	font_small = load_font(13)
	for index, record in enumerate(records):
		path = Path(str(record["path"]))
		with Image.open(path) as source:
			im = source.convert("RGB")
			im.thumbnail((thumb_w - 18, thumb_h - 18), Image.Resampling.LANCZOS)
		col = index % cols
		row = index // cols
		x = col * thumb_w + (thumb_w - im.width) // 2
		y = row * (thumb_h + label_h) + 8
		sheet.paste(im, (x, y))
		lx = col * thumb_w + 10
		ly = row * (thumb_h + label_h) + thumb_h
		label = f"{index + 1:02d} {record['relative_path']}"
		if len(label) > 38:
			label = label[:35] + "..."
		draw.text((lx, ly), label, fill=(0, 0, 0), font=font)
		draw.text(
			(lx, ly + 23),
			f"{record['width']}x{record['height']}  {int(record['bytes']) // 1024}KB",
			fill=(80, 80, 80),
			font=font_small,
		)
	out_path.parent.mkdir(parents=True, exist_ok=True)
	sheet.save(out_path, quality=92)


def main() -> None:
	parser = argparse.ArgumentParser(description="Inspect source images and create a contact sheet.")
	parser.add_argument("input_dir", type=Path)
	parser.add_argument("--out-dir", type=Path, default=None)
	args = parser.parse_args()

	input_dir = args.input_dir.resolve()
	out_dir = (args.out_dir or input_dir / "cover_work").resolve()
	out_dir.mkdir(parents=True, exist_ok=True)

	records = [info for p in find_images(input_dir) if (info := image_info(p, input_dir))]
	records.sort(key=lambda r: (int(r["width"]) * int(r["height"])), reverse=True)

	inventory = out_dir / "image_inventory.json"
	contact = out_dir / "contact_sheet.jpg"
	inventory.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
	make_contact_sheet(records, contact)
	print(f"Wrote {inventory}")
	if records:
		print(f"Wrote {contact}")


if __name__ == "__main__":
	main()

