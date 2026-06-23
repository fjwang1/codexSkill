#!/usr/bin/env python3
"""Remove visible footer attribution and internal production notes from SVG output.

This script is intentionally narrow: it removes bottom-positioned SVG <text>
elements that look like source attribution captions or internal validation /
workflow notes, while leaving page numbers and normal slide body text alone.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

SOURCE_PREFIXES = (
	"source:",
	"sources:",
	"data source:",
	"source ",
	"sources ",
	"来源:",
	"来源：",
	"来源 ",
	"资料来源:",
	"资料来源：",
	"资料来源 ",
	"数据来源:",
	"数据来源：",
	"数据来源 ",
	"本文来源",
	"出处:",
	"出处：",
)

INTERNAL_NOTE_PATTERNS = (
	re.compile(r"\bdeck\s+mode\s+validation\b", re.IGNORECASE),
	re.compile(r"\bvalidation\s+sample\b", re.IGNORECASE),
	re.compile(r"\bbased\s+on\s+article\b", re.IGNORECASE),
	re.compile(r"\bworkflow\b", re.IGNORECASE),
	re.compile(r"\bdraft\b", re.IGNORECASE),
	re.compile(r"\bdebug\b", re.IGNORECASE),
	re.compile(r"\bplaceholder\b", re.IGNORECASE),
	re.compile(r"\binternal\s+(?:note|production|process)\b", re.IGNORECASE),
	re.compile(r"\bproduction\s+(?:note|process|label)\b", re.IGNORECASE),
	re.compile(r"^(?:p|page|slide)\s*\d{1,3}\s*(?:[-–—:：·\.]|$)", re.IGNORECASE),
	re.compile(r"^(?:p|page|slide)\s*\d{1,3}\s*[-–—:：].*(?:validation|sample|article|workflow|draft|debug|placeholder)", re.IGNORECASE),
	re.compile(r"(?:内部|生产说明|工作流|验证|样例|示例|占位|调试)"),
)


def _local_name(tag: str) -> str:
	return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text_content(element: ET.Element) -> str:
	text = "".join(element.itertext())
	return re.sub(r"\s+", " ", text).strip()


def _first_number(value: str | None) -> float | None:
	if not value:
		return None
	match = re.search(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)", value)
	if match is None:
		return None
	try:
		return float(match.group(0))
	except ValueError:
		return None


def _svg_height(root: ET.Element) -> float:
	view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
	if view_box:
		parts = re.findall(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)", view_box)
		if len(parts) == 4:
			try:
				return float(parts[3])
			except ValueError:
				pass
	height = _first_number(root.attrib.get("height"))
	return height if height and height > 0 else 720.0


def _element_y(element: ET.Element) -> float | None:
	y_values: list[float] = []
	y = _first_number(element.attrib.get("y"))
	if y is not None:
		y_values.append(y)
	for child in element.iter():
		if child is element:
			continue
		child_y = _first_number(child.attrib.get("y"))
		if child_y is not None:
			y_values.append(child_y)
	return max(y_values) if y_values else None


def _looks_like_source_caption(text: str, y: float | None, svg_height: float) -> bool:
	normalized = text.strip().lower()
	if not normalized:
		return False
	if not normalized.startswith(SOURCE_PREFIXES):
		return False
	if y is None:
		return True
	return y >= svg_height * 0.65


def _looks_like_internal_note(text: str, y: float | None, svg_height: float) -> bool:
	normalized = text.strip()
	if not normalized:
		return False
	if y is not None and y < svg_height * 0.78:
		return False
	return any(pattern.search(normalized) for pattern in INTERNAL_NOTE_PATTERNS)


def _process_svg(path: Path, dry_run: bool) -> int:
	try:
		tree = ET.parse(path)
	except ET.ParseError as exc:
		print(f"[WARN] Skipping unparsable SVG: {path} ({exc})", file=sys.stderr)
		return 0

	root = tree.getroot()
	height = _svg_height(root)
	parent_by_child = {child: parent for parent in root.iter() for child in parent}
	to_remove: list[ET.Element] = []

	for element in root.iter():
		if _local_name(element.tag) != "text":
			continue
		text = _text_content(element)
		y = _element_y(element)
		if _looks_like_source_caption(text, y, height) or _looks_like_internal_note(text, y, height):
			to_remove.append(element)

	for element in to_remove:
		parent = parent_by_child.get(element)
		if parent is not None:
			parent.remove(element)

	if to_remove and not dry_run:
		tree.write(path, encoding="utf-8", xml_declaration=False)

	return len(to_remove)


def _svg_dirs(project_path: Path, also_final: bool) -> list[Path]:
	dirs = [project_path / "svg_output"]
	if also_final:
		dirs.append(project_path / "svg_final")
	return [path for path in dirs if path.is_dir()]


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Remove bottom source attribution captions and internal production notes from ppt-master SVG files."
	)
	parser.add_argument("project_path", type=Path)
	parser.add_argument("--also-final", action="store_true", help="also scan svg_final/")
	parser.add_argument("--dry-run", action="store_true", help="report matches without editing")
	args = parser.parse_args()

	if not args.project_path.is_dir():
		print(f"[ERROR] Project path not found: {args.project_path}", file=sys.stderr)
		return 2

	total = 0
	files = 0
	for svg_dir in _svg_dirs(args.project_path, args.also_final):
		for svg_path in sorted(svg_dir.glob("*.svg")):
			removed = _process_svg(svg_path, dry_run=args.dry_run)
			if removed:
				mode = "would remove" if args.dry_run else "removed"
				print(f"{svg_path}: {mode} {removed} footer/internal text element(s)")
				files += 1
				total += removed

	mode = "would remove" if args.dry_run else "removed"
	print(f"[OK] {mode} {total} footer/internal text element(s) across {files} file(s)")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
