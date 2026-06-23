#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
	from PIL import Image
except ModuleNotFoundError as exc:
	raise SystemExit("Pillow is required. Use the Codex workspace dependency Python.") from exc


CANVAS_W = 3840
CANVAS_H = 2160

# The title compositor places text here. The generated background must keep
# this area visually clean; this script only records the constraint.
TEXT_SAFE_X = 384
TEXT_SAFE_W = 1843


def cover_crop(im: Image.Image, size: tuple[int, int], anchor: str) -> Image.Image:
	target_w, target_h = size
	w, h = im.size
	scale = max(target_w / w, target_h / h)
	new_size = (round(w * scale), round(h * scale))
	im = im.resize(new_size, Image.Resampling.LANCZOS)
	w, h = im.size

	if anchor == "top":
		left = (w - target_w) // 2
		top = 0
	elif anchor == "bottom":
		left = (w - target_w) // 2
		top = h - target_h
	elif anchor == "left":
		left = 0
		top = (h - target_h) // 2
	elif anchor == "right":
		left = w - target_w
		top = (h - target_h) // 2
	else:
		left = (w - target_w) // 2
		top = (h - target_h) // 2

	left = max(0, min(left, w - target_w))
	top = max(0, min(top, h - target_h))
	return im.crop((left, top, left + target_w, top + target_h))


def main() -> None:
	parser = argparse.ArgumentParser(description="Normalize a full-cover AI background to 3840x2160. No blue base is added.")
	parser.add_argument("--input", "--subject", dest="input", required=True, type=Path, help="AI-generated full background image.")
	parser.add_argument("--out", required=True, type=Path, help="Output 3840x2160 background.png.")
	parser.add_argument("--anchor", choices=["center", "top", "bottom", "left", "right"], default="center")
	args = parser.parse_args()

	background = Image.open(args.input).convert("RGB")
	canvas = cover_crop(background, (CANVAS_W, CANVAS_H), args.anchor)

	args.out.parent.mkdir(parents=True, exist_ok=True)
	canvas.save(args.out)
	manifest = {
		"canvas": {"width": CANVAS_W, "height": CANVAS_H},
		"background_source": str(args.input),
		"fit": "cover",
		"anchor": args.anchor,
		"added_blue_base": False,
		"text_safe_area": {"x": TEXT_SAFE_X, "y": 0, "width": TEXT_SAFE_W, "height": CANVAS_H},
		"background_requirements": [
			"full-bleed editorial image",
			"dominant subject on the right",
			"clean low-detail headline space on the left",
			"no readable text/logo/watermark",
		],
	}
	args.out.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"Wrote {args.out}")


if __name__ == "__main__":
	main()
