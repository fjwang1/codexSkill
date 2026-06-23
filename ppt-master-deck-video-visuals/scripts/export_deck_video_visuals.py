#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


WIDTH = 3840
HEIGHT = 2160

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


def _log(message: str) -> None:
	print(message, file=sys.stderr, flush=True)


def _natural_key(path: Path) -> tuple[int, str]:
	match = re.match(r"^(\d+)", path.stem)
	return (int(match.group(1)) if match else 10_000, path.name)


def _select_svg_dir(project: Path, explicit: Path | None) -> Path:
	if explicit:
		svg_dir = explicit
	else:
		final_dir = project / "svg_final"
		output_dir = project / "svg_output"
		svg_dir = final_dir if final_dir.is_dir() and list(final_dir.glob("*.svg")) else output_dir
	if not svg_dir.is_dir():
		raise FileNotFoundError(f"SVG directory not found: {svg_dir}")
	return svg_dir.resolve()


def _discover_svgs(svg_dir: Path) -> list[Path]:
	svgs = sorted(svg_dir.glob("*.svg"), key=_natural_key)
	if not svgs:
		raise FileNotFoundError(f"No SVG files found in {svg_dir}")
	return svgs


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


def _assert_no_forbidden_visible_text(svgs: list[Path]) -> None:
	offenders: list[str] = []
	for svg in svgs:
		try:
			root = ET.parse(svg).getroot()
		except ET.ParseError as exc:
			raise ValueError(f"unparsable SVG: {svg} ({exc})") from exc
		height = _svg_height(root)
		for element in root.iter():
			if _local_name(element.tag) != "text":
				continue
			text = _text_content(element)
			y = _element_y(element)
			if _looks_like_source_caption(text, y, height) or _looks_like_internal_note(text, y, height):
				preview = text[:120]
				offenders.append(f"{svg.name}: {preview}")
	if offenders:
		raise ValueError(
			"visible source/footer attribution or internal production note remains in SVGs; "
			"run ppt-master-article-deck/scripts/remove_source_footers.py first. Offenders: "
			+ " | ".join(offenders[:12])
		)


def _slide_title(svg: Path) -> str:
	title = re.sub(r"^\d+[_\-\s]*", "", svg.stem).strip()
	return title or svg.stem


def _clean(text: str) -> str:
	return " ".join(text.replace("\u3000", " ").split())


def _first_sentence(text: str, max_len: int = 120) -> str:
	text = _clean(text)
	if not text:
		return ""
	for sep in ("。", "！", "？", ".", "!", "?"):
		pos = text.find(sep)
		if 0 < pos <= max_len:
			return text[: pos + 1]
	return text[:max_len]


def _parse_total_notes(total_md: Path) -> dict[int, str]:
	if not total_md.exists():
		return {}
	text = total_md.read_text(encoding="utf-8")
	sections: dict[int, list[str]] = {}
	current_idx: int | None = None
	for line in text.splitlines():
		head = re.match(r"^#\s+(.+?)\s*$", line)
		if head:
			title = head.group(1)
			match = re.match(r"^(\d+)", title)
			if match:
				current_idx = int(match.group(1))
				sections.setdefault(current_idx, [])
			else:
				current_idx = None
			continue
		if current_idx is not None:
			sections.setdefault(current_idx, []).append(line)
	return {idx: _clean("\n".join(lines)) for idx, lines in sections.items()}


def _load_notes(project: Path, svgs: list[Path]) -> dict[int, str]:
	notes_dir = project / "notes"
	notes = _parse_total_notes(notes_dir / "total.md")
	for idx, svg in enumerate(svgs, start=1):
		if idx in notes and notes[idx]:
			continue
		candidates = [
			notes_dir / f"{svg.stem}.md",
			notes_dir / f"{idx:02d}_{_slide_title(svg)}.md",
		]
		for path in candidates:
			if path.exists():
				notes[idx] = _clean(path.read_text(encoding="utf-8"))
				break
	return notes


def _write_json(path: Path, data: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _find_chromium(executable: str | None) -> str | None:
	if executable:
		return executable
	env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
	if env_path:
		return env_path
	cache_root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/Volumes/GT34/Caches/ms-playwright"))
	candidates = sorted(cache_root.glob("chromium_headless_shell-*/chrome-mac/headless_shell"))
	return str(candidates[-1]) if candidates else None


def _build_html(svg_text: str, svg_dir: Path, width: int, height: int) -> str:
	return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <base href="{html.escape(svg_dir.as_uri() + '/')}">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: {width}px;
      height: {height}px;
      overflow: hidden;
      background: white;
    }}
    svg {{
      display: block;
      width: {width}px !important;
      height: {height}px !important;
    }}
  </style>
</head>
<body>
{svg_text}
</body>
</html>
"""


def _render_svgs(
	svgs: list[Path],
	svg_dir: Path,
	out_dir: Path,
	width: int,
	height: int,
	chromium_executable: str | None,
	timeout_ms: int,
) -> list[Path]:
	try:
		from playwright.sync_api import sync_playwright
	except ImportError as exc:
		raise RuntimeError("Python package 'playwright' is required for rendering.") from exc

	out_dir.mkdir(parents=True, exist_ok=True)
	rendered: list[Path] = []
	executable = _find_chromium(chromium_executable)

	with sync_playwright() as p:
		launch_kwargs: dict[str, Any] = {"headless": True}
		if executable:
			launch_kwargs["executable_path"] = executable
		browser = p.chromium.launch(**launch_kwargs)
		try:
			context = browser.new_context(
				viewport={"width": width, "height": height},
				device_scale_factor=1,
			)
			for idx, svg in enumerate(svgs, start=1):
				out_path = out_dir / f"chapter_{idx:02d}.png"
				page = context.new_page()
				try:
					with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as tmp:
						tmp.write(_build_html(svg.read_text(encoding="utf-8"), svg_dir, width, height))
						tmp_path = Path(tmp.name)
					try:
						page.goto(tmp_path.as_uri(), wait_until="networkidle", timeout=timeout_ms)
						page.screenshot(path=str(out_path), type="png", full_page=False, timeout=timeout_ms)
					finally:
						try:
							tmp_path.unlink()
						except FileNotFoundError:
							pass
				finally:
					page.close()
				rendered.append(out_path)
				_log(f"rendered {svg.name} -> {out_path.name}")
		finally:
			browser.close()
	return rendered


def _verify_pngs(paths: list[Path], width: int, height: int) -> None:
	from PIL import Image

	for path in paths:
		with Image.open(path) as image:
			if image.size != (width, height):
				raise ValueError(f"{path} has size {image.size}, expected {(width, height)}")


def _write_contact_sheet(paths: list[Path], out_path: Path, width: int, height: int) -> None:
	from PIL import Image

	cols = min(3, max(1, len(paths)))
	thumb_w = 960
	thumb_h = int(thumb_w * height / width)
	gap = 24
	rows = (len(paths) + cols - 1) // cols
	sheet_w = cols * thumb_w + (cols + 1) * gap
	sheet_h = rows * thumb_h + (rows + 1) * gap
	sheet = Image.new("RGB", (sheet_w, sheet_h), "#f4f1ea")
	for i, path in enumerate(paths):
		row, col = divmod(i, cols)
		x = gap + col * (thumb_w + gap)
		y = gap + row * (thumb_h + gap)
		with Image.open(path) as image:
			thumb = image.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
		sheet.paste(thumb, (x, y))
	out_path.parent.mkdir(parents=True, exist_ok=True)
	sheet.save(out_path, quality=92)


def _build_semantics(project: Path, svgs: list[Path], notes: dict[int, str], width: int, height: int) -> dict[str, Any]:
	chapters: list[dict[str, Any]] = []
	for idx, svg in enumerate(svgs, start=1):
		title = _slide_title(svg)
		note = notes.get(idx, "")
		summary = _first_sentence(note) or f"PPT Master deck slide: {title}"
		chapters.append({
			"chapter_index": idx,
			"image": f"chapter_{idx:02d}.png",
			"source_svg": str(svg),
			"chapter_title": title,
			"short_title": title[:12],
			"summary": summary,
			"points": [],
			"interpretation": note or summary,
			"speaker_note": note or summary,
			"visual_intent": f"Rendered from the normal PPT Master deck slide '{title}' without design changes.",
			"script_anchor_hint": summary,
			"visual_type": "ppt_master_deck_slide",
			"semantic_status": "rich" if note else "minimal",
		})
	return {
		"schema_version": "ppt-master-deck-video-semantics.v1",
		"generator": "ppt-master-deck-video-visuals",
		"project_path": str(project),
		"visual_system": {
			"resolution": f"{width}x{height}",
			"render_source": "ppt-master svg via headless chromium",
			"mode": "postprocess_existing_deck",
		},
		"chapters": chapters,
	}


def _assert_no_timing(semantics: dict[str, Any]) -> None:
	for chapter in semantics.get("chapters", []):
		for field in ("start_sec", "end_sec", "start_turn", "end_turn"):
			if field in chapter:
				raise ValueError(f"timing field not allowed in semantics: {field}")


def _copy_outputs(out_dir: Path, copy_to: Path) -> None:
	copy_to.mkdir(parents=True, exist_ok=True)
	for path in out_dir.glob("chapter_*.png"):
		shutil.copy2(path, copy_to / path.name)
	for name in ("chapter_semantics.json", "chapter_visuals_contact_sheet.jpg"):
		source = out_dir / name
		if source.exists():
			shutil.copy2(source, copy_to / name)


def main() -> int:
	parser = argparse.ArgumentParser(description="Render an existing PPT Master deck project to 4K video slide images.")
	parser.add_argument("project_path")
	parser.add_argument("--svg-dir", default=None)
	parser.add_argument("--out-dir", default=None)
	parser.add_argument("--copy-to", default=None)
	parser.add_argument("--width", type=int, default=WIDTH)
	parser.add_argument("--height", type=int, default=HEIGHT)
	parser.add_argument("--chromium-executable", default=None)
	parser.add_argument("--timeout-ms", type=int, default=30_000)
	args = parser.parse_args()

	try:
		project = Path(args.project_path).resolve()
		if not project.is_dir():
			raise FileNotFoundError(f"project not found: {project}")
		svg_dir = _select_svg_dir(project, Path(args.svg_dir).resolve() if args.svg_dir else None)
		svgs = _discover_svgs(svg_dir)
		_assert_no_forbidden_visible_text(svgs)
		out_dir = Path(args.out_dir).resolve() if args.out_dir else project / "chapter_visuals"
		notes = _load_notes(project, svgs)
		rendered = _render_svgs(svgs, svg_dir, out_dir, args.width, args.height, args.chromium_executable, args.timeout_ms)
		_verify_pngs(rendered, args.width, args.height)
		semantics = _build_semantics(project, svgs, notes, args.width, args.height)
		_assert_no_timing(semantics)
		_write_json(out_dir / "chapter_semantics.json", semantics)
		_write_contact_sheet(rendered, out_dir / "chapter_visuals_contact_sheet.jpg", args.width, args.height)
		if args.copy_to:
			_copy_outputs(out_dir, Path(args.copy_to).resolve())
		print(json.dumps({
			"status": "PASS",
			"project_path": str(project),
			"svg_dir": str(svg_dir),
			"out_dir": str(out_dir),
			"copy_to": str(Path(args.copy_to).resolve()) if args.copy_to else None,
			"slide_count": len(rendered),
			"chapter_semantics": str(out_dir / "chapter_semantics.json"),
			"contact_sheet": str(out_dir / "chapter_visuals_contact_sheet.jpg"),
		}, ensure_ascii=False, indent=2))
		return 0
	except Exception as exc:
		_log(f"{type(exc).__name__}: {exc}")
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
