#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(value: Any, base_dir: Path) -> Path | None:
	if not isinstance(value, str) or not value.strip():
		return None
	path = Path(value).expanduser()
	if not path.is_absolute():
		path = base_dir / path
	return path


def _write_report(path: Path, report: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(project_dir: Path) -> tuple[bool, dict[str, Any]]:
	project_dir = project_dir.expanduser().resolve()
	chapter_dir = project_dir / "chapter_visuals"
	template_path = chapter_dir / "template_selection.json"
	errors: list[str] = []

	selection: dict[str, Any] = {}
	if not template_path.exists():
		errors.append(f"missing template_selection.json: {template_path}")
	else:
		try:
			selection = _read_json(template_path)
		except Exception as exc:
			errors.append(f"cannot parse template_selection.json: {exc}")

	ppt_master_project = _resolve_path(selection.get("ppt_master_project"), project_dir)
	normal_pptx = _resolve_path(selection.get("normal_pptx"), project_dir)

	if ppt_master_project is None:
		errors.append("template_selection.json ppt_master_project is missing or empty")
	elif not ppt_master_project.is_dir():
		errors.append(f"ppt_master_project does not exist or is not a directory: {ppt_master_project}")

	if normal_pptx is None:
		errors.append("template_selection.json normal_pptx is missing or empty")
	elif not normal_pptx.is_file():
		errors.append(f"normal_pptx does not exist or is not a file: {normal_pptx}")

	if ppt_master_project is not None and ppt_master_project.is_dir():
		for required in ("design_spec.md", "spec_lock.md"):
			if not (ppt_master_project / required).is_file():
				errors.append(f"ppt_master_project missing {required}: {ppt_master_project / required}")

		svg_output = ppt_master_project / "svg_output"
		svg_final = ppt_master_project / "svg_final"
		has_svg_output = svg_output.is_dir() and any(svg_output.glob("*.svg"))
		has_svg_final = svg_final.is_dir() and any(svg_final.glob("*.svg"))
		if not (has_svg_output or has_svg_final):
			errors.append("ppt_master_project has no SVG files in svg_output/ or svg_final/")

		exports = ppt_master_project / "exports"
		if not (exports.is_dir() and any(exports.glob("*.pptx"))):
			errors.append(f"ppt_master_project has no exports/*.pptx: {exports}")

	report = {
		"schema_version": "ppt-chapter-origin-validation.v1",
		"validated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
		"project_dir": str(project_dir),
		"template_selection": str(template_path),
		"ppt_master_project": str(ppt_master_project) if ppt_master_project else None,
		"normal_pptx": str(normal_pptx) if normal_pptx else None,
		"status": "PASS" if not errors else "FAIL",
		"errors": errors,
		"checks": [
			"template_selection has non-empty existing ppt_master_project and normal_pptx",
			"ppt_master_project has design_spec.md, spec_lock.md, SVG output/final files, and exports/*.pptx",
		],
	}
	return not errors, report


def main() -> int:
	parser = argparse.ArgumentParser(description="Validate that chapter visuals came from a PPT Master project.")
	parser.add_argument("--project-dir", required=True, type=Path, help="Video project directory.")
	parser.add_argument("--report", type=Path, help="Output report path. Defaults to chapter_visuals/ppt_origin_validation.json.")
	args = parser.parse_args()

	ok, report = validate(args.project_dir)
	report_path = args.report or (args.project_dir / "chapter_visuals" / "ppt_origin_validation.json")
	_write_report(report_path, report)

	print(f"{report['status']}: {report_path}")
	if not ok:
		for error in report["errors"]:
			print(f"- {error}", file=sys.stderr)
	return 0 if ok else 1


if __name__ == "__main__":
	raise SystemExit(main())
