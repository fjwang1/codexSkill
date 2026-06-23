#!/usr/bin/env python3
"""
Render ppt-master SVG pages into 4K podcast/video chapter visual PNGs.

The script is intentionally a thin deterministic bridge:
- reads finalized slide SVGs from <project>/svg_final/ when present, else svg_output/
- renders each SVG through headless Chromium at 3840x2160
- writes <project>/chapter_visuals/chapter_XX.png
- merges optional visual semantics from chapter_semantics_seed.json
- writes chapter_semantics.json and an optional contact sheet
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_WIDTH = 3840
DEFAULT_HEIGHT = 2160


def _log(message: str) -> None:
	print(message, file=sys.stderr, flush=True)


def _natural_key(path: Path) -> tuple[int, str]:
	match = re.match(r"^(\d+)", path.stem)
	if match:
		return int(match.group(1)), path.name
	return 10_000, path.name


def _load_json(path: Path) -> Any:
	with path.open("r", encoding="utf-8") as f:
		return json.load(f)


def _write_json(path: Path, data: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=2)
		f.write("\n")


def _select_svg_dir(project_path: Path, explicit: Path | None) -> Path:
	if explicit is not None:
		svg_dir = explicit
	else:
		final_dir = project_path / "svg_final"
		output_dir = project_path / "svg_output"
		svg_dir = final_dir if final_dir.is_dir() and list(final_dir.glob("*.svg")) else output_dir
	if not svg_dir.is_dir():
		raise FileNotFoundError(f"SVG directory not found: {svg_dir}")
	return svg_dir.resolve()


def _discover_svgs(svg_dir: Path) -> list[Path]:
	svgs = sorted(svg_dir.glob("*.svg"), key=_natural_key)
	if not svgs:
		raise FileNotFoundError(f"No SVG files found in {svg_dir}")
	return svgs


def _load_seed(seed_path: Path | None) -> dict[str, Any]:
	if seed_path is None:
		return {}
	if not seed_path.exists():
		raise FileNotFoundError(f"Semantics seed not found: {seed_path}")
	data = _load_json(seed_path)
	if isinstance(data, list):
		return {"chapters": data}
	if not isinstance(data, dict):
		raise ValueError(f"Semantics seed must be a JSON object or list: {seed_path}")
	if "chapters" not in data or not isinstance(data["chapters"], list):
		raise ValueError(f"Semantics seed must contain a chapters array: {seed_path}")
	return data


def _ensure_visual_system(seed: dict[str, Any], width: int, height: int) -> dict[str, Any]:
	visual_system = dict(seed.get("visual_system") or {})
	visual_system["resolution"] = f"{width}x{height}"
	visual_system["render_source"] = "ppt-master svg via headless chromium"
	return visual_system


def _build_semantics_source(seed: dict[str, Any], svgs: list[Path], image_names: list[str], width: int, height: int) -> dict[str, Any]:
	seed_chapters = seed.get("chapters") or []
	if seed_chapters and len(seed_chapters) != len(svgs):
		raise ValueError(
			f"Semantics seed chapter count ({len(seed_chapters)}) does not match SVG count ({len(svgs)}). "
			"Generate exactly one SVG per chapter or update the seed."
		)

	chapters: list[dict[str, Any]] = []
	for idx, svg_path in enumerate(svgs, start=1):
		if seed_chapters:
			chapter = dict(seed_chapters[idx - 1])
		else:
			title = re.sub(r"^\d+[_\-\s]*", "", svg_path.stem).strip() or f"Chapter {idx:02d}"
			chapter = {
				"chapter_index": idx,
				"chapter_title": title,
				"short_title": title[:8],
				"summary": "",
				"points": [],
				"visual_type": "chosen_by_ppt_master",
			}
		chapter["chapter_index"] = int(chapter.get("chapter_index") or idx)
		chapter["image"] = image_names[idx - 1]
		chapter["source_svg"] = str(svg_path)
		chapters.append(chapter)

	return {
		"schema_version": seed.get("schema_version") or "ppt-master-chapter-semantics-source.v1",
		"generator": "ppt-master-article-deck chapter visual export mode",
		"visual_system": _ensure_visual_system(seed, width, height),
		"chapters": chapters,
	}


def _text(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, str):
		return " ".join(value.split())
	return " ".join(str(value).split())


def _list_of_text(value: Any) -> list[str]:
	if value is None:
		return []
	if isinstance(value, list):
		return [_text(item) for item in value if _text(item)]
	text = _text(value)
	return [text] if text else []


def _first_text(*values: Any) -> str:
	for value in values:
		text = _text(value)
		if text:
			return text
	return ""


def _build_semantics(source: dict[str, Any]) -> dict[str, Any]:
	semantic_chapters: list[dict[str, Any]] = []
	for idx, chapter in enumerate(source.get("chapters") or [], start=1):
		summary = _text(chapter.get("summary"))
		interpretation = _first_text(
			chapter.get("speaker_note"),
			chapter.get("interpretation"),
			chapter.get("notes"),
			summary,
		)
		entry: dict[str, Any] = {
			"chapter_index": int(chapter.get("chapter_index") or idx),
			"image": chapter.get("image") or f"chapter_{idx:02d}.png",
			"source_svg": chapter.get("source_svg"),
			"chapter_title": _text(chapter.get("chapter_title")),
			"short_title": _text(chapter.get("short_title")),
			"summary": summary,
			"points": _list_of_text(chapter.get("points")),
			"interpretation": interpretation,
			"speaker_note": interpretation,
			"visual_intent": _text(chapter.get("visual_intent")),
			"script_anchor_hint": _text(chapter.get("script_anchor_hint")),
			"visual_type": _text(chapter.get("visual_type")),
		}
		for optional_field in (
			"evidence",
			"keywords",
			"source_turn_hint",
		):
			if optional_field in chapter:
				entry[optional_field] = chapter[optional_field]

		has_rich_semantics = bool(
			entry["interpretation"]
			and entry["visual_intent"]
			and entry["script_anchor_hint"]
		)
		entry["semantic_status"] = "rich" if has_rich_semantics else "minimal"
		semantic_chapters.append(entry)

	return {
		"schema_version": "ppt-master-chapter-semantics.v1",
		"generator": "ppt-master-article-deck chapter visual export mode",
		"source_schema_version": source.get("schema_version"),
		"visual_system": source.get("visual_system"),
		"chapters": semantic_chapters,
	}


def _find_chromium_executable(explicit: str | None) -> str | None:
	if explicit:
		return explicit
	env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
	if env_path:
		return env_path
	cache_root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/Volumes/GT34/Caches/ms-playwright"))
	candidates = sorted(cache_root.glob("chromium_headless_shell-*/chrome-mac/headless_shell"))
	if candidates:
		return str(candidates[-1])
	return None


def _build_html(svg_text: str, svg_dir: Path, width: int, height: int) -> str:
	base_href = svg_dir.as_uri() + "/"
	return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <base href="{html.escape(base_href)}">
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


def _render_svgs_with_playwright(
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
		raise RuntimeError(
			"Python package 'playwright' is not installed. Install it in the selected runtime, for example:\n"
			"  /Volumes/GT34/Caches/ppt-master-venv/bin/python -m pip install playwright\n"
			"Use PLAYWRIGHT_BROWSERS_PATH=/Volumes/GT34/Caches/ms-playwright when browsers are already cached."
		) from exc

	out_dir.mkdir(parents=True, exist_ok=True)
	rendered: list[Path] = []
	executable_path = _find_chromium_executable(chromium_executable)

	with sync_playwright() as p:
		launch_kwargs: dict[str, Any] = {"headless": True}
		if executable_path:
			launch_kwargs["executable_path"] = executable_path
		browser = p.chromium.launch(**launch_kwargs)
		try:
			context = browser.new_context(
				viewport={"width": width, "height": height},
				device_scale_factor=1,
			)
			for idx, svg_path in enumerate(svgs, start=1):
				out_path = out_dir / f"chapter_{idx:02d}.png"
				svg_text = svg_path.read_text(encoding="utf-8")
				page = context.new_page()
				try:
					html_text = _build_html(svg_text, svg_dir, width, height)
					with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as tmp:
						tmp.write(html_text)
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
				_log(f"rendered {svg_path.name} -> {out_path.name}")
		finally:
			browser.close()

	return rendered


def _verify_pngs(paths: list[Path], width: int, height: int) -> None:
	try:
		from PIL import Image
	except ImportError as exc:
		raise RuntimeError("Python package 'Pillow' is required to verify chapter PNG dimensions.") from exc

	for path in paths:
		with Image.open(path) as img:
			if img.size != (width, height):
				raise ValueError(f"{path} has size {img.size}, expected {(width, height)}")


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
		with Image.open(path) as img:
			thumb = img.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
		sheet.paste(thumb, (x, y))

	out_path.parent.mkdir(parents=True, exist_ok=True)
	sheet.save(out_path, quality=92)


def main() -> int:
	parser = argparse.ArgumentParser(description="Export ppt-master SVG pages as 3840x2160 chapter visual PNGs.")
	parser.add_argument("project_path", help="ppt-master project directory")
	parser.add_argument("--svg-dir", default=None, help="Override SVG directory; defaults to svg_final then svg_output")
	parser.add_argument("--out-dir", default=None, help="Output directory; defaults to <project>/chapter_visuals")
	parser.add_argument("--semantics-seed", default=None, help="Optional chapter_semantics_seed.json with visual semantics")
	parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
	parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
	parser.add_argument("--chromium-executable", default=None, help="Optional Chromium/headless_shell executable path")
	parser.add_argument("--timeout-ms", type=int, default=30_000)
	args = parser.parse_args()

	project_path = Path(args.project_path).resolve()
	if not project_path.is_dir():
		_log(f"project not found: {project_path}")
		return 2

	try:
		svg_dir = _select_svg_dir(project_path, Path(args.svg_dir).resolve() if args.svg_dir else None)
		svgs = _discover_svgs(svg_dir)
		out_dir = Path(args.out_dir).resolve() if args.out_dir else project_path / "chapter_visuals"
		seed_arg = args.semantics_seed
		seed_path = Path(seed_arg).resolve() if seed_arg else None
		seed = _load_seed(seed_path)
		image_names = [f"chapter_{idx:02d}.png" for idx in range(1, len(svgs) + 1)]
		semantics_source = _build_semantics_source(seed, svgs, image_names, args.width, args.height)
		semantics = _build_semantics(semantics_source)
		rendered = _render_svgs_with_playwright(
			svgs=svgs,
			svg_dir=svg_dir,
			out_dir=out_dir,
			width=args.width,
			height=args.height,
			chromium_executable=args.chromium_executable,
			timeout_ms=args.timeout_ms,
		)
		_verify_pngs(rendered, args.width, args.height)
		_write_contact_sheet(rendered, out_dir / "chapter_visuals_contact_sheet.jpg", args.width, args.height)
		_write_json(out_dir / "chapter_semantics.json", semantics)
		print(json.dumps({
			"status": "PASS",
			"project_path": str(project_path),
			"svg_dir": str(svg_dir),
			"out_dir": str(out_dir),
			"chapter_count": len(rendered),
			"chapter_semantics": str(out_dir / "chapter_semantics.json"),
			"contact_sheet": str(out_dir / "chapter_visuals_contact_sheet.jpg"),
		}, ensure_ascii=False, indent=2))
		return 0
	except Exception as exc:
		_log(f"{type(exc).__name__}: {exc}")
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
