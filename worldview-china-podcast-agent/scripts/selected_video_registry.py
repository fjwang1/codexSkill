#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_REGISTRY = Path("/Volumes/GT34/world_and_china_podcast/selected-videos.json")
SCHEMA_VERSION = "worldview-china-podcast-selected-videos.v1"


def _read_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now_utc() -> datetime:
	return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
	if not value:
		return None
	text = str(value).strip()
	if not text:
		return None
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	for candidate in (text, text.replace(" ", "T", 1)):
		try:
			dt = datetime.fromisoformat(candidate)
			if dt.tzinfo is None:
				dt = dt.replace(tzinfo=timezone.utc)
			return dt.astimezone(timezone.utc)
		except ValueError:
			continue
	return None


def _video_id_from_url(url: Any) -> str | None:
	if not url:
		return None
	parsed = urlparse(str(url))
	host = parsed.netloc.lower()
	if host.endswith("youtu.be"):
		value = parsed.path.strip("/").split("/")[0]
		return value or None
	if "youtube.com" in host:
		query = parse_qs(parsed.query)
		if query.get("v"):
			return query["v"][0]
		parts = [part for part in parsed.path.split("/") if part]
		for marker in ("shorts", "embed", "live"):
			if marker in parts:
				index = parts.index(marker)
				if index + 1 < len(parts):
					return parts[index + 1]
	return None


def canonical_video_id(item: dict[str, Any]) -> str:
	for key in ("video_id", "id", "youtube_video_id", "source_video_id"):
		value = item.get(key)
		if value:
			return str(value).strip()
	for key in ("url", "webpage_url", "original_url", "source_url"):
		value = _video_id_from_url(item.get(key))
		if value:
			return value
	raise ValueError(f"Cannot derive YouTube video_id from item keys={sorted(item)}")


def canonical_url(video_id: str, item: dict[str, Any] | None = None) -> str:
	if item:
		for key in ("url", "webpage_url", "original_url", "source_url"):
			value = item.get(key)
			if value:
				return str(value)
	return f"https://www.youtube.com/watch?v={video_id}"


def load_registry(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {
			"schema_version": SCHEMA_VERSION,
			"records": [],
		}
	data = _read_json(path)
	if isinstance(data, list):
		return {
			"schema_version": SCHEMA_VERSION,
			"records": data,
		}
	assert isinstance(data, dict), f"Registry must be an object or list: {path}"
	records = data.get("records")
	if records is None and isinstance(data.get("videos"), list):
		records = data["videos"]
	assert isinstance(records, list), f"Registry has no records list: {path}"
	return {
		**data,
		"schema_version": data.get("schema_version") or SCHEMA_VERSION,
		"records": records,
	}


def _record_selected_at(record: dict[str, Any]) -> datetime | None:
	for key in ("selected_at", "created_at", "updated_at", "completed_at"):
		dt = _parse_datetime(record.get(key))
		if dt is not None:
			return dt
	return None


def recent_records(registry: dict[str, Any], days: int, now: datetime | None = None, exclude_run_dir: Path | None = None) -> list[dict[str, Any]]:
	now = now or _now_utc()
	cutoff = now - timedelta(days=days)
	result: list[dict[str, Any]] = []
	exclude = str(exclude_run_dir.resolve()) if exclude_run_dir is not None else None
	for raw in registry.get("records") or []:
		if not isinstance(raw, dict):
			continue
		if exclude and str(raw.get("run_dir") or "") == exclude:
			continue
		selected_at = _record_selected_at(raw)
		if selected_at is None or selected_at < cutoff:
			continue
		try:
			video_id = canonical_video_id(raw)
		except ValueError:
			continue
		item = dict(raw)
		item["video_id"] = video_id
		item["url"] = canonical_url(video_id, item)
		item["selected_at"] = selected_at.isoformat()
		result.append(item)
	result.sort(key=lambda item: str(item.get("selected_at") or ""), reverse=True)
	return result


def recent_payload(registry_path: Path, days: int, run_dir: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
	registry = load_registry(registry_path)
	records = recent_records(registry, days, now=now, exclude_run_dir=run_dir)
	video_ids = sorted({canonical_video_id(record) for record in records})
	return {
		"schema_version": "worldview-china-podcast-recent-selected-videos.v1",
		"registry": str(registry_path),
		"dedupe_window_days": days,
		"recent_video_ids": video_ids,
		"recent_urls": [canonical_url(video_id) for video_id in video_ids],
		"records": records,
	}


def _candidate_lists(payload: Any) -> list[list[dict[str, Any]]]:
	if isinstance(payload, list):
		return [payload]
	if not isinstance(payload, dict):
		return []
	result: list[list[dict[str, Any]]] = []
	for key in ("ranked", "candidates", "items", "videos", "shortlist"):
		value = payload.get(key)
		if isinstance(value, list):
			result.append(value)
	return result


def _candidate_decision(item: dict[str, Any]) -> str:
	return str(item.get("decision") or item.get("metadata_decision") or item.get("status") or "").lower()


def _candidate_rank_key(item: dict[str, Any]) -> tuple[int, int]:
	decision = _candidate_decision(item)
	priority = 0 if "accept" in decision else 1 if "backup" in decision else 2
	try:
		rank = int(item.get("rank") or 999999)
	except (TypeError, ValueError):
		rank = 999999
	return priority, rank


def extract_best_video(payload: Any) -> dict[str, Any]:
	if isinstance(payload, dict):
		best = payload.get("best_video")
		if isinstance(best, dict):
			return best
		if payload.get("video_id") or payload.get("url") or payload.get("webpage_url"):
			return payload
	for candidates in _candidate_lists(payload):
		sorted_candidates = sorted((item for item in candidates if isinstance(item, dict)), key=_candidate_rank_key)
		for item in sorted_candidates:
			decision = _candidate_decision(item)
			if "accept" in decision or "backup" in decision:
				return item
		if sorted_candidates:
			return sorted_candidates[0]
	raise ValueError("Could not extract a best video from the provided JSON")


def record_video(registry_path: Path, item: dict[str, Any], run_dir: Path | None, source: str, selected_at: datetime | None = None) -> dict[str, Any]:
	registry = load_registry(registry_path)
	selected_at = selected_at or _now_utc()
	video_id = canonical_video_id(item)
	run_dir_text = str(run_dir.resolve()) if run_dir is not None else None
	record = {
		"selected_at": selected_at.isoformat(),
		"source": source,
		"run_dir": run_dir_text,
		"video_id": video_id,
		"url": canonical_url(video_id, item),
		"title": item.get("title"),
		"channel": item.get("channel") or item.get("channel_title"),
		"published_at": item.get("published_at") or item.get("publishedAt"),
		"duration_seconds": item.get("duration_seconds"),
		"view_count": item.get("view_count"),
		"comment_count": item.get("comment_count"),
	}
	records = [entry for entry in registry.get("records") or [] if not (
		isinstance(entry, dict)
		and str(entry.get("video_id") or "") == video_id
		and str(entry.get("run_dir") or "") == str(run_dir_text or "")
	)]
	records.append(record)
	registry["records"] = records
	registry["schema_version"] = SCHEMA_VERSION
	registry["updated_at"] = selected_at.isoformat()
	_write_json(registry_path, registry)
	return {
		"schema_version": "worldview-china-podcast-selected-video-record.v1",
		"registry": str(registry_path),
		"record": record,
		"recent_video_ids": recent_payload(registry_path, 5, run_dir=None, now=selected_at)["recent_video_ids"],
	}


def filter_payload(payload: Any, registry_path: Path, days: int, run_dir: Path | None = None, now: datetime | None = None) -> tuple[Any, dict[str, Any]]:
	now = now or _now_utc()
	recent = recent_payload(registry_path, days, run_dir=run_dir, now=now)
	recent_ids = set(recent["recent_video_ids"])
	if isinstance(payload, dict):
		output = dict(payload)
	else:
		output = list(payload) if isinstance(payload, list) else payload
	duplicate_ids: set[str] = set()
	available_candidates: list[dict[str, Any]] = []
	for candidates in _candidate_lists(output):
		for item in candidates:
			if not isinstance(item, dict):
				continue
			try:
				video_id = canonical_video_id(item)
			except ValueError:
				continue
			is_duplicate = video_id in recent_ids
			item["recent_selection_duplicate"] = is_duplicate
			if is_duplicate:
				item["recent_selection_duplicate_reason"] = f"selected within the past {days} days"
				duplicate_ids.add(video_id)
			else:
				available_candidates.append(item)
	if isinstance(output, dict) and isinstance(output.get("best_video"), dict):
		best_video = output["best_video"]
		try:
			best_id = canonical_video_id(best_video)
		except ValueError:
			best_id = ""
		if best_id in recent_ids:
			output["best_video_before_recent_dedupe"] = best_video
			replacement = next((item for item in sorted(available_candidates, key=_candidate_rank_key) if "accept" in _candidate_decision(item)), None)
			if replacement is None:
				replacement = next((item for item in sorted(available_candidates, key=_candidate_rank_key) if "backup" in _candidate_decision(item)), None)
			output["best_video"] = replacement
			output["status"] = "NEEDS_NEW_SELECTION_RECENT_DUPLICATE" if replacement is None else "BEST_VIDEO_REPLACED_AFTER_RECENT_DEDUPE"
			output["recent_duplicate_blocker"] = {
				"video_id": best_id,
				"reason": f"best_video was selected within the past {days} days",
			}
	report = {
		"schema_version": "worldview-china-podcast-selection-dedupe-report.v1",
		"registry": str(registry_path),
		"dedupe_window_days": days,
		"recent_video_ids": sorted(recent_ids),
		"duplicate_video_ids": sorted(duplicate_ids),
		"duplicate_count": len(duplicate_ids),
		"available_candidate_count": len({canonical_video_id(item) for item in available_candidates}),
	}
	return output, report


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Maintain local selected YouTube video registry for Worldview China podcast runs.")
	parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
	subparsers = parser.add_subparsers(dest="command", required=True)

	recent_parser = subparsers.add_parser("recent", help="Write or print videos selected within the dedupe window.")
	recent_parser.add_argument("--days", type=int, default=5)
	recent_parser.add_argument("--run-dir", type=Path)
	recent_parser.add_argument("--out", type=Path)

	record_parser = subparsers.add_parser("record", help="Record the selected best_video immediately after topic selection.")
	record_parser.add_argument("--best-video-json", required=True, type=Path)
	record_parser.add_argument("--run-dir", type=Path)
	record_parser.add_argument("--source", default="topic_selection_best_video")
	record_parser.add_argument("--out", type=Path)

	filter_parser = subparsers.add_parser("filter", help="Annotate or replace shortlist best_video when it was recently selected.")
	filter_parser.add_argument("--input", required=True, type=Path)
	filter_parser.add_argument("--out", required=True, type=Path)
	filter_parser.add_argument("--report-out", type=Path)
	filter_parser.add_argument("--days", type=int, default=5)
	filter_parser.add_argument("--run-dir", type=Path)
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	registry_path = args.registry.expanduser().resolve()
	if args.command == "recent":
		run_dir = args.run_dir.expanduser().resolve() if args.run_dir else None
		payload = recent_payload(registry_path, args.days, run_dir=run_dir)
		if args.out:
			_write_json(args.out.expanduser().resolve(), payload)
		print(json.dumps(payload, ensure_ascii=False, indent=2))
		return 0
	if args.command == "record":
		payload = _read_json(args.best_video_json.expanduser().resolve())
		item = extract_best_video(payload)
		run_dir = args.run_dir.expanduser().resolve() if args.run_dir else None
		result = record_video(registry_path, item, run_dir, args.source)
		if args.out:
			_write_json(args.out.expanduser().resolve(), result)
		print(json.dumps(result, ensure_ascii=False, indent=2))
		return 0
	if args.command == "filter":
		payload = _read_json(args.input.expanduser().resolve())
		run_dir = args.run_dir.expanduser().resolve() if args.run_dir else None
		output, report = filter_payload(payload, registry_path, args.days, run_dir=run_dir)
		_write_json(args.out.expanduser().resolve(), output)
		if args.report_out:
			_write_json(args.report_out.expanduser().resolve(), report)
		print(json.dumps(report, ensure_ascii=False, indent=2))
		return 0
	raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
	raise SystemExit(main())
