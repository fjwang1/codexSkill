#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path("/Volumes/GT34/daily_china_article_video")
TZ = ZoneInfo("Asia/Shanghai")


def _read_json(path: Path) -> dict:
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except Exception:
		return {}


def _parse_date(value: str | None) -> date:
	if value:
		return date.fromisoformat(value)
	return datetime.now(TZ).date()


def _candidate_target_dates(run_date: date, selection_date: str | None) -> list[date]:
	if selection_date:
		return [date.fromisoformat(selection_date)]
	return [run_date - timedelta(days=1), run_date - timedelta(days=2)]


def _first_existing(paths: list[Path]) -> Path | None:
	for path in paths:
		if path.exists() and path.is_file() and path.stat().st_size > 0:
			return path
	return None


def _article_from_orchestration(run_dir: Path, selected_id: str | None) -> tuple[Path | None, Path | None, str | None]:
	manifest = _read_json(run_dir / "orchestration_manifest.json")
	articles = manifest.get("articles") or []
	for article in articles:
		if selected_id and article.get("selection_id") not in {selected_id, None, ""}:
			continue
		package_dir = article.get("article_package_dir")
		if not package_dir:
			continue
		text_path = Path(package_dir) / "source" / "article.txt"
		meta_path = Path(package_dir) / "source" / "source_metadata.json"
		if text_path.exists() and text_path.is_file() and text_path.stat().st_size > 0:
			return text_path, meta_path if meta_path.exists() else None, "orchestration_article_package"
	return None, None, None


def _article_from_articles_dir(run_dir: Path) -> tuple[Path | None, Path | None, str | None]:
	candidates = sorted(run_dir.glob("articles/article_*/source/article.txt"))
	for text_path in candidates:
		if text_path.exists() and text_path.is_file() and text_path.stat().st_size > 0:
			meta_path = text_path.with_name("source_metadata.json")
			return text_path, meta_path if meta_path.exists() else None, "articles_dir_article_package"
	return None, None, None


def _article_from_ranked_top5(run_dir: Path, selected_id: str | None) -> tuple[Path | None, str | None]:
	ranked = _read_json(run_dir / "selection" / "ranked-top5.json")
	candidates = ranked.get("top_candidates") or ranked.get("candidates") or []
	for candidate in candidates:
		if selected_id and candidate.get("candidate_id") != selected_id:
			continue
		capture = candidate.get("capture_output_path") or candidate.get("local_material_path")
		if capture:
			path = Path(capture)
			if path.exists() and path.is_file() and path.stat().st_size > 0:
				return path, "ranked_top5_capture_output"
	return None, None


def _locate_for_target(target_date: date) -> dict:
	run_dir = ROOT / f"{target_date.isoformat()}_china_viral"
	decision_path = run_dir / "selection" / "selection-decision.json"
	decision = _read_json(decision_path)
	selected_id = decision.get("selected_candidate_id")

	text_path, meta_path, source = _article_from_articles_dir(run_dir)
	if not text_path:
		text_path, meta_path, source = _article_from_orchestration(run_dir, selected_id)

	if not text_path:
		capture = decision.get("capture_output_path")
		if capture:
			capture_path = Path(capture)
			if capture_path.exists() and capture_path.is_file() and capture_path.stat().st_size > 0:
				text_path = capture_path
				source = "selection_decision_capture_output"

	if not text_path:
		capture_path, ranked_source = _article_from_ranked_top5(run_dir, selected_id)
		if capture_path:
			text_path = capture_path
			source = ranked_source

	return {
		"target_date": target_date.isoformat(),
		"run_dir": str(run_dir),
		"run_dir_exists": run_dir.exists(),
		"selection_decision_path": str(decision_path),
		"selection_decision_exists": decision_path.exists(),
		"selected_candidate_id": selected_id,
		"title_original": decision.get("selected_title_original"),
		"title_zh": decision.get("selected_title_zh"),
		"source": decision.get("selected_source"),
		"original_url": decision.get("selected_original_url"),
		"material_source_url": decision.get("selected_material_source_url"),
		"article_text_path": str(text_path) if text_path else None,
		"article_text_exists": bool(text_path and text_path.exists()),
		"article_metadata_path": str(meta_path) if meta_path else None,
		"material_locator": source,
	}


def main() -> int:
	parser = argparse.ArgumentParser(description="Locate the daily selected China article material.")
	parser.add_argument("--run-date", help="Digest run date in Asia/Shanghai, YYYY-MM-DD. Defaults to today.")
	parser.add_argument("--selection-date", help="Force a specific selection target date, YYYY-MM-DD.")
	args = parser.parse_args()

	run_date = _parse_date(args.run_date)
	checked: list[dict] = []
	for target_date in _candidate_target_dates(run_date, args.selection_date):
		result = _locate_for_target(target_date)
		checked.append(result)
		if result["article_text_exists"]:
			output = {
				"status": "found",
				"run_date": run_date.isoformat(),
				"selected_target_date": result["target_date"],
				"checked": checked,
				**result,
			}
			print(json.dumps(output, ensure_ascii=False, indent=2))
			return 0

	print(json.dumps({
		"status": "not_found",
		"run_date": run_date.isoformat(),
		"checked": checked,
	}, ensure_ascii=False, indent=2))
	return 1


if __name__ == "__main__":
	sys.exit(main())
