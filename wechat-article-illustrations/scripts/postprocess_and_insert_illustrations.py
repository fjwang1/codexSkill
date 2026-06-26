#!/usr/bin/env python3
"""Postprocess generated WeChat article illustrations and insert them into Markdown."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


SCHEMA_VERSION = "wechat-article-illustrations.v1"
IMAGE_MAP_SCHEMA_VERSION = "wechat-article-illustrations.image-map.v1"
STYLE_VERSION = "new-yorker-conceptual-editorial-v1"
TARGET_SIZE = (2400, 1600)
WECHAT_MAX_BYTES = 950_000


@dataclass
class Chapter:
	index: int
	heading: str
	start_line: int
	end_line: int
	content: str


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Postprocess chapter illustrations and insert Markdown images.")
	parser.add_argument("--article-dir", type=Path, required=True, help="Article directory containing wechat/reviewed_article.md.")
	parser.add_argument("--image-map", type=Path, help="JSON mapping chapter_index to generated image path.")
	parser.add_argument("--list-chapters", action="store_true", help="Print detected H2 chapters as JSON and exit.")
	parser.add_argument("--max-inline-bytes", type=int, default=WECHAT_MAX_BYTES, help="Target max bytes for WeChat inline JPG.")
	return parser.parse_args()


def article_markdown_path(article_dir: Path) -> Path:
	reviewed = article_dir / "wechat" / "reviewed_article.md"
	if reviewed.exists():
		return reviewed
	plain = article_dir / "wechat" / "article.md"
	if plain.exists():
		return plain
	raise SystemExit(f"No reviewed/article Markdown found under {article_dir / 'wechat'}")


def fallback_insert_line(lines: list[str]) -> int:
	seen_body = False
	for i, line in enumerate(lines):
		stripped = line.strip()
		if not stripped or stripped.startswith("# "):
			continue
		if stripped.startswith(">"):
			continue
		if not seen_body:
			seen_body = True
			continue
		return i
	return len(lines)


def parse_chapters(markdown: str, allow_fallback: bool = False) -> list[Chapter]:
	lines = markdown.splitlines()
	heading_rows: list[tuple[int, str]] = []
	for i, line in enumerate(lines):
		match = re.match(r"^##\s+(.+?)\s*$", line)
		if match:
			heading_rows.append((i, match.group(1).strip()))
	if not heading_rows and allow_fallback:
		title = "全文插图"
		content_lines = [
			line
			for line in lines
			if line.strip() and not line.startswith("# ") and not line.startswith(">")
		]
		return [Chapter(index=1, heading=title, start_line=fallback_insert_line(lines) - 1, end_line=len(lines), content="\n".join(content_lines))]
	chapters: list[Chapter] = []
	for idx, (start, heading) in enumerate(heading_rows, start=1):
		end = heading_rows[idx][0] if idx < len(heading_rows) else len(lines)
		content = "\n".join(lines[start + 1 : end]).strip()
		chapters.append(Chapter(index=idx, heading=heading, start_line=start, end_line=end, content=content))
	return chapters


def chapter_summary(chapter: Chapter, max_chars: int = 260) -> str:
	text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", chapter.content)
	text = re.sub(r"\s+", " ", text).strip()
	return text[:max_chars]


def slugify(value: str) -> str:
	value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value.lower()).strip("-")
	if not value:
		return "chapter"
	return value[:48].strip("-") or "chapter"


def crop_to_ratio(image: Image.Image, ratio: float) -> Image.Image:
	width, height = image.size
	current = width / height
	if current > ratio:
		new_width = int(round(height * ratio))
		left = (width - new_width) // 2
		return image.crop((left, 0, left + new_width, height))
	new_height = int(round(width / ratio))
	top = (height - new_height) // 2
	return image.crop((0, top, width, top + new_height))


def save_wechat_jpg(image: Image.Image, path: Path, max_bytes: int) -> tuple[int, int]:
	quality = 92
	while quality >= 68:
		image.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
		size = path.stat().st_size
		if size <= max_bytes:
			return quality, size
		quality -= 4
	return quality + 4, path.stat().st_size


def process_image(source: Path, output_base: Path, max_inline_bytes: int) -> dict[str, Any]:
	image = Image.open(source).convert("RGB")
	cropped = crop_to_ratio(image, TARGET_SIZE[0] / TARGET_SIZE[1])
	master = cropped.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
	source_png = output_base.with_name(output_base.name + "_source_2400x1600.png")
	wechat_jpg = output_base.with_name(output_base.name + "_wechat_2400x1600.jpg")
	master.save(source_png, optimize=True)
	quality, byte_size = save_wechat_jpg(master, wechat_jpg, max_inline_bytes)
	return {
		"generated_image_path": str(source),
		"source_size_px": f"{image.size[0]}x{image.size[1]}",
		"master_path": str(source_png),
		"master_size_px": "2400x1600",
		"inline_path": str(wechat_jpg),
		"inline_size_px": "2400x1600",
		"inline_jpeg_quality": quality,
		"inline_file_size_bytes": byte_size,
		"inline_over_target_bytes": byte_size > max_inline_bytes,
	}


def load_image_map(path: Path) -> dict[str, Any]:
	data = json.loads(path.read_text(encoding="utf-8"))
	if data.get("schema_version") != IMAGE_MAP_SCHEMA_VERSION:
		raise SystemExit(f"Unexpected image map schema: {data.get('schema_version')}")
	return data


def remove_existing_illustration_lines(lines: list[str]) -> list[str]:
	filtered: list[str] = []
	for line in lines:
		if re.match(r"^!\[插图\]\(\.\./illustrations/chapter_\d+_.+_wechat_2400x1600\.jpg\)\s*$", line.strip()):
			continue
		filtered.append(line)
	return filtered


def insert_images(markdown: str, chapters: list[Chapter], processed: dict[int, dict[str, Any]]) -> str:
	lines = remove_existing_illustration_lines(markdown.splitlines())
	# Recompute chapter starts after removing old image lines.
	current_chapters = parse_chapters("\n".join(lines))
	insertions: list[tuple[int, str]] = []
	if current_chapters:
		for chapter in current_chapters:
			item = processed.get(chapter.index)
			if not item:
				continue
			inline_path = Path(item["inline_path"])
			relative = "../" + str(inline_path.relative_to(inline_path.parents[1]))
			insertions.append((chapter.start_line + 1, f"![插图]({relative})"))
	else:
		item = processed.get(1)
		if item:
			inline_path = Path(item["inline_path"])
			relative = "../" + str(inline_path.relative_to(inline_path.parents[1]))
			insertions.append((fallback_insert_line(lines), f"![插图]({relative})"))
	offset = 0
	for line_index, image_line in insertions:
		at = line_index + offset
		lines.insert(at, "")
		lines.insert(at + 1, image_line)
		lines.insert(at + 2, "")
		offset += 3
	return "\n".join(lines).rstrip() + "\n"


def sha256(path: Path) -> str:
	return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def main() -> None:
	args = parse_args()
	article_dir = args.article_dir.expanduser().resolve()
	markdown_path = article_markdown_path(article_dir)
	markdown = markdown_path.read_text(encoding="utf-8")
	chapters = parse_chapters(markdown, allow_fallback=True)
	if args.list_chapters:
		print(json.dumps(
			{
				"article_path": str(markdown_path),
				"chapter_count": len(chapters),
				"chapters": [
					{
						"chapter_index": chapter.index,
						"heading": chapter.heading,
						"summary": chapter_summary(chapter),
						"char_count": len(chapter.content),
					}
					for chapter in chapters
				],
			},
			ensure_ascii=False,
			indent=2,
		))
		return

	if not args.image_map:
		raise SystemExit("--image-map is required unless --list-chapters is used")
	image_map = load_image_map(args.image_map.expanduser().resolve())
	image_entries = image_map.get("images")
	if not isinstance(image_entries, list):
		raise SystemExit("image map must include images[]")

	illustration_dir = article_dir / "illustrations"
	illustration_dir.mkdir(parents=True, exist_ok=True)

	chapters_by_index = {chapter.index: chapter for chapter in chapters}
	processed: dict[int, dict[str, Any]] = {}
	manifest_items: list[dict[str, Any]] = []
	for entry in image_entries:
		index = int(entry["chapter_index"])
		chapter = chapters_by_index.get(index)
		if chapter is None:
			raise SystemExit(f"No chapter_index {index} in {markdown_path}")
		source = Path(entry["generated_image_path"]).expanduser().resolve()
		if not source.exists():
			raise SystemExit(f"Generated image not found: {source}")
		base = illustration_dir / f"chapter_{index:02d}_{slugify(chapter.heading)}"
		result = process_image(source, base, args.max_inline_bytes)
		result.update(
			{
				"chapter_index": index,
				"heading": chapter.heading,
				"chapter_summary": chapter_summary(chapter),
				"prompt": entry.get("prompt", ""),
				"negative_prompt": entry.get("negative_prompt", ""),
			}
		)
		processed[index] = result
		manifest_items.append(result)

	timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
	backup = markdown_path.with_name(f"{markdown_path.stem}.before_illustrations.{timestamp}{markdown_path.suffix}")
	shutil.copy2(markdown_path, backup)
	new_markdown = insert_images(markdown, chapters, processed)
	markdown_path.write_text(new_markdown, encoding="utf-8")

	manifest = {
		"schema_version": SCHEMA_VERSION,
		"style_version": image_map.get("style_version", STYLE_VERSION),
		"article_dir": str(article_dir),
		"article_path": str(markdown_path),
		"article_sha256_before": sha256(backup),
		"article_sha256_after": sha256(markdown_path),
		"backup_path": str(backup),
		"created_at": dt.datetime.now(dt.UTC).isoformat(),
		"ratio": "3:2",
		"target_source_size_px": "2400x1600",
		"inline_image_policy": "2400x1600 optimized JPG, target under 950KB for WeChat uploadimg compatibility",
		"chapter_count": len(chapters),
		"illustration_count": len(manifest_items),
		"items": manifest_items,
	}
	manifest_path = illustration_dir / "illustrations_manifest.json"
	manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print(json.dumps({"manifest_path": str(manifest_path), "article_path": str(markdown_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
