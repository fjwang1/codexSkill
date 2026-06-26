#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "worldview-china-publish-slot-ledger.v1"
DEFAULT_ROOT_DIR = Path("/Volumes/GT34/world_and_china_podcast")
DEFAULT_LEDGER_NAME = "publish-slots.json"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_SLOTS = ("11:00", "17:00")
DEFAULT_RESERVATION_TTL_HOURS = 18.0

FILLED_STATUSES = {
	"RESERVED",
	"READY_TO_SUBMIT",
	"SUBMITTED",
	"APPROVED",
	"REVIEW_PENDING_AFTER_MAX_CHECKS",
}
TERMINAL_FILLED_STATUSES = {
	"READY_TO_SUBMIT",
	"SUBMITTED",
	"APPROVED",
	"REVIEW_PENDING_AFTER_MAX_CHECKS",
}
UNFILLED_STATUSES = {
	"EMPTY",
	"METADATA_READY",
	"RELEASED",
	"FAILED",
	"BLOCKED",
	"UNKNOWN",
	"RETURNED_NEEDS_REPAIR",
}
STATUS_PRIORITY = (
	"APPROVED",
	"REVIEW_PENDING_AFTER_MAX_CHECKS",
	"SUBMITTED",
	"READY_TO_SUBMIT",
	"RESERVED",
	"RETURNED_NEEDS_REPAIR",
	"BLOCKED",
	"FAILED",
	"METADATA_READY",
	"UNKNOWN",
	"RELEASED",
	"EMPTY",
)


def _ensure_root_writable(root_dir: Path) -> Path:
	root_dir = Path(root_dir).expanduser()
	root_text = str(root_dir)
	if root_text == "/Volumes/GT34" or root_text.startswith("/Volumes/GT34/"):
		volume = Path("/Volumes/GT34")
		if not volume.exists() or not os.path.ismount(volume):
			raise RuntimeError("/Volumes/GT34 is not mounted; refusing to create publish slot ledger on the internal disk")
		if not os.access(volume, os.W_OK):
			raise RuntimeError("/Volumes/GT34 is not writable; cannot update publish slot ledger")
	root_dir.mkdir(parents=True, exist_ok=True)
	if not os.access(root_dir, os.W_OK):
		raise RuntimeError(f"Root directory is not writable: {root_dir}")
	return root_dir


def _ledger_path(root_dir: Path, ledger_name: str = DEFAULT_LEDGER_NAME) -> Path:
	return Path(root_dir) / ledger_name


def _now(timezone_name: str, now: datetime | None = None) -> datetime:
	timezone = ZoneInfo(timezone_name)
	if now is None:
		return datetime.now(timezone)
	if now.tzinfo is None:
		return now.replace(tzinfo=timezone)
	return now.astimezone(timezone)


def _parse_target_date(value: str | date | datetime | None, timezone_name: str, now: datetime | None = None) -> str:
	current = _now(timezone_name, now)
	if value is None:
		return (current.date() + timedelta(days=1)).isoformat()
	if isinstance(value, datetime):
		return value.astimezone(ZoneInfo(timezone_name)).date().isoformat() if value.tzinfo else value.date().isoformat()
	if isinstance(value, date):
		return value.isoformat()
	text = str(value).strip()
	if not text:
		return (current.date() + timedelta(days=1)).isoformat()
	if "T" in text or " " in text:
		return _parse_datetime(text, timezone_name).date().isoformat()
	return date.fromisoformat(text).isoformat()


def _parse_slots(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
	raw_slots = [slot.strip() for slot in value.split(",")] if isinstance(value, str) else [str(slot).strip() for slot in value]
	slots: list[str] = []
	for raw_slot in raw_slots:
		if not raw_slot:
			continue
		match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", raw_slot)
		if not match:
			raise ValueError(f"Publish slot must use HH:MM 24-hour time: {raw_slot}")
		slot = f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
		if slot not in slots:
			slots.append(slot)
	if not slots:
		raise ValueError("At least one publish slot is required")
	return tuple(slots)


def _parse_datetime(value: Any, timezone_name: str) -> datetime:
	text = str(value or "").strip()
	if not text:
		raise ValueError("empty datetime value")
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	if "T" not in text and " " in text:
		text = text.replace(" ", "T", 1)
	parsed = datetime.fromisoformat(text)
	timezone = ZoneInfo(timezone_name)
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone)
	return parsed.astimezone(timezone)


def _slot_key(target_date: str, slot: str) -> str:
	return f"{target_date}T{slot}"


def _slot_from_datetime(value: datetime) -> tuple[str, str, str]:
	target_date = value.date().isoformat()
	slot = f"{value.hour:02d}:{value.minute:02d}"
	return _slot_key(target_date, slot), target_date, slot


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	tmp_path = path.with_name(f".{path.name}.tmp")
	tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
	os.replace(tmp_path, path)


def _load_ledger(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {
			"schema_version": SCHEMA_VERSION,
			"slots": {},
		}
	ledger = _read_json(path)
	if not isinstance(ledger.get("slots"), dict):
		ledger["slots"] = {}
	ledger.setdefault("schema_version", SCHEMA_VERSION)
	return ledger


def _save_ledger(path: Path, ledger: dict[str, Any], timezone_name: str, now: datetime | None = None) -> None:
	ledger["schema_version"] = SCHEMA_VERSION
	ledger["updated_at"] = _now(timezone_name, now).isoformat()
	_write_json_atomic(path, ledger)


@contextlib.contextmanager
def _locked(root_dir: Path):
	lock_path = Path(root_dir) / ".publish-slots.lock"
	lock_path.parent.mkdir(parents=True, exist_ok=True)
	with lock_path.open("a+", encoding="utf-8") as handle:
		fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
		try:
			yield
		finally:
			fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _reservation_is_stale(entry: dict[str, Any], current: datetime, reservation_ttl_hours: float) -> bool:
	if entry.get("status") != "RESERVED":
		return False
	try:
		reserved_at = _parse_datetime(entry.get("reserved_at"), str(current.tzinfo.key if hasattr(current.tzinfo, "key") else current.tzinfo))
	except Exception:
		return True
	return current - reserved_at > timedelta(hours=reservation_ttl_hours)


def _entry_is_satisfied(entry: dict[str, Any] | None, current: datetime, reservation_ttl_hours: float) -> bool:
	if not entry:
		return False
	status = str(entry.get("status") or "UNKNOWN")
	if status == "RESERVED":
		return not _reservation_is_stale(entry, current, reservation_ttl_hours)
	return status in TERMINAL_FILLED_STATUSES


def _entry_summary(key: str, target_date: str, slot: str, entry: dict[str, Any] | None, current: datetime, reservation_ttl_hours: float) -> dict[str, Any]:
	status = str((entry or {}).get("status") or "EMPTY")
	stale = bool(entry and _reservation_is_stale(entry, current, reservation_ttl_hours))
	return {
		"key": key,
		"date": target_date,
		"slot": slot,
		"status": status,
		"satisfied": _entry_is_satisfied(entry, current, reservation_ttl_hours),
		"stale_reservation": stale,
		"run_dir": (entry or {}).get("run_dir"),
		"run_id": (entry or {}).get("run_id"),
		"title": (entry or {}).get("title"),
		"item_count": len((entry or {}).get("items") or []),
		"updated_at": (entry or {}).get("updated_at"),
		"reserved_at": (entry or {}).get("reserved_at"),
		"scheduled_publish_at": (entry or {}).get("scheduled_publish_at"),
	}


def _build_plan(
	ledger: dict[str, Any],
	ledger_file: Path,
	target_date: str,
	slots: tuple[str, ...],
	timezone_name: str,
	now: datetime | None,
	reservation_ttl_hours: float,
) -> dict[str, Any]:
	current = _now(timezone_name, now)
	slot_statuses: dict[str, dict[str, Any]] = {}
	satisfied_slots: list[dict[str, Any]] = []
	missing_slots: list[dict[str, Any]] = []
	for slot in slots:
		key = _slot_key(target_date, slot)
		entry = ledger.get("slots", {}).get(key)
		summary = _entry_summary(key, target_date, slot, entry, current, reservation_ttl_hours)
		slot_statuses[key] = summary
		if summary["satisfied"]:
			satisfied_slots.append(summary)
		else:
			missing_slots.append(summary)
	return {
		"schema_version": "worldview-china-publish-slot-plan.v1",
		"status": "OK",
		"generated_at": current.isoformat(),
		"ledger_path": str(ledger_file),
		"target_date": target_date,
		"timezone": timezone_name,
		"slots": list(slots),
		"satisfied_slots": satisfied_slots,
		"missing_slots": missing_slots,
		"slot_statuses": slot_statuses,
		"should_run": bool(missing_slots),
		"next_slot": missing_slots[0]["slot"] if missing_slots else None,
	}


def plan_slots(
	root_dir: Path,
	target_date: str | date | datetime | None = None,
	slots: str | tuple[str, ...] | list[str] = DEFAULT_SLOTS,
	timezone_name: str = DEFAULT_TIMEZONE,
	now: datetime | None = None,
	reservation_ttl_hours: float = DEFAULT_RESERVATION_TTL_HOURS,
	ledger_name: str = DEFAULT_LEDGER_NAME,
) -> dict[str, Any]:
	root_dir = _ensure_root_writable(Path(root_dir))
	parsed_date = _parse_target_date(target_date, timezone_name, now)
	parsed_slots = _parse_slots(slots)
	ledger_file = _ledger_path(root_dir, ledger_name)
	with _locked(root_dir):
		ledger = _load_ledger(ledger_file)
		return _build_plan(ledger, ledger_file, parsed_date, parsed_slots, timezone_name, now, reservation_ttl_hours)


def reserve_slots(
	root_dir: Path,
	target_date: str | date | datetime | None,
	slots: str | tuple[str, ...] | list[str],
	run_dir: Path,
	run_id: str | None = None,
	timezone_name: str = DEFAULT_TIMEZONE,
	now: datetime | None = None,
	reservation_ttl_hours: float = DEFAULT_RESERVATION_TTL_HOURS,
	ledger_name: str = DEFAULT_LEDGER_NAME,
	force: bool = False,
) -> dict[str, Any]:
	root_dir = _ensure_root_writable(Path(root_dir))
	parsed_date = _parse_target_date(target_date, timezone_name, now)
	parsed_slots = _parse_slots(slots)
	current = _now(timezone_name, now)
	ledger_file = _ledger_path(root_dir, ledger_name)
	run_dir_text = str(Path(run_dir))
	run_id = run_id or Path(run_dir).name
	with _locked(root_dir):
		ledger = _load_ledger(ledger_file)
		reserved: list[dict[str, Any]] = []
		for slot in parsed_slots:
			key = _slot_key(parsed_date, slot)
			existing = ledger["slots"].get(key)
			if existing and _entry_is_satisfied(existing, current, reservation_ttl_hours) and not force:
				raise RuntimeError(f"Publish slot already satisfied or actively reserved: {key}")
			previous_entry = None
			if existing and _reservation_is_stale(existing, current, reservation_ttl_hours):
				previous_entry = {
					"status": existing.get("status"),
					"run_dir": existing.get("run_dir"),
					"reserved_at": existing.get("reserved_at"),
				}
			entry = {
				"key": key,
				"date": parsed_date,
				"slot": slot,
				"status": "RESERVED",
				"run_dir": run_dir_text,
				"run_id": run_id,
				"reserved_at": current.isoformat(),
				"reservation_ttl_hours": reservation_ttl_hours,
				"updated_at": current.isoformat(),
				"items": [],
			}
			if previous_entry:
				entry["previous_stale_entry"] = previous_entry
			ledger["slots"][key] = entry
			reserved.append(_entry_summary(key, parsed_date, slot, entry, current, reservation_ttl_hours))
		_save_ledger(ledger_file, ledger, timezone_name, current)
		plan = _build_plan(ledger, ledger_file, parsed_date, parsed_slots, timezone_name, current, reservation_ttl_hours)
		return {
			"schema_version": "worldview-china-publish-slot-reservation.v1",
			"status": "RESERVED",
			"ledger_path": str(ledger_file),
			"target_date": parsed_date,
			"timezone": timezone_name,
			"reserved_slots": reserved,
			"plan_after_reserve": plan,
		}


def release_run(
	root_dir: Path,
	run_dir: Path | None = None,
	run_id: str | None = None,
	target_date: str | date | datetime | None = None,
	slots: str | tuple[str, ...] | list[str] | None = None,
	status: str = "RELEASED",
	timezone_name: str = DEFAULT_TIMEZONE,
	now: datetime | None = None,
	ledger_name: str = DEFAULT_LEDGER_NAME,
) -> dict[str, Any]:
	root_dir = _ensure_root_writable(Path(root_dir))
	current = _now(timezone_name, now)
	ledger_file = _ledger_path(root_dir, ledger_name)
	run_dir_text = str(Path(run_dir)) if run_dir is not None else None
	allowed_keys: set[str] | None = None
	if target_date is not None and slots is not None:
		parsed_date = _parse_target_date(target_date, timezone_name, now)
		allowed_keys = {_slot_key(parsed_date, slot) for slot in _parse_slots(slots)}
	with _locked(root_dir):
		ledger = _load_ledger(ledger_file)
		released: list[dict[str, Any]] = []
		for key, entry in list(ledger.get("slots", {}).items()):
			if allowed_keys is not None and key not in allowed_keys:
				continue
			if run_dir_text and entry.get("run_dir") != run_dir_text:
				continue
			if run_id and entry.get("run_id") != run_id:
				continue
			if entry.get("status") != "RESERVED":
				continue
			entry["status"] = status
			entry["released_at"] = current.isoformat()
			entry["updated_at"] = current.isoformat()
			released.append(_entry_summary(key, entry.get("date") or key[:10], entry.get("slot") or key[11:16], entry, current, DEFAULT_RESERVATION_TTL_HOURS))
		_save_ledger(ledger_file, ledger, timezone_name, current)
		return {
			"schema_version": "worldview-china-publish-slot-release.v1",
			"status": "OK",
			"ledger_path": str(ledger_file),
			"released_slots": released,
		}


def _read_json_if_exists(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {}
	return _read_json(path)


def _episode_dirs_for_run(run_dir: Path) -> list[Path]:
	series_manifest_path = run_dir / "04b-series-episodes/series_manifest.json"
	if series_manifest_path.exists():
		manifest = _read_json(series_manifest_path)
		episode_dirs = []
		for episode in manifest.get("episodes") or []:
			episode_dir = Path(str(episode.get("episode_run_dir") or ""))
			if episode_dir:
				episode_dirs.append(episode_dir)
		return episode_dirs
	return [run_dir]


def _derive_status(episode_dir: Path) -> tuple[str, dict[str, str]]:
	paths: dict[str, str] = {}
	audit_report_path = episode_dir / "11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json"
	audit_report = _read_json_if_exists(audit_report_path)
	if audit_report:
		paths["audit_report"] = str(audit_report_path)
		status = str(audit_report.get("status") or "UNKNOWN")
		if status:
			return status, paths
	upload_report_path = episode_dir / "bilibili_upload_draft_report.json"
	upload_report = _read_json_if_exists(upload_report_path)
	if upload_report:
		paths["upload_report"] = str(upload_report_path)
		status = str(upload_report.get("status") or "UNKNOWN")
		if status:
			return status, paths
	metadata_path = episode_dir / "bilibili_upload_metadata.json"
	if metadata_path.exists():
		paths["metadata"] = str(metadata_path)
		return "METADATA_READY", paths
	return "UNKNOWN", paths


def _scheduled_publish_at(metadata: dict[str, Any], upload_report: dict[str, Any]) -> Any:
	for key in (
		"scheduled_publish_at",
		"scheduled_publish_at_effective",
		"scheduled_publish_at_requested",
	):
		value = metadata.get(key)
		if value:
			return value
	for key in (
		"scheduled_publish_at_effective",
		"scheduled_publish_at",
		"scheduled_publish_at_requested",
	):
		value = upload_report.get(key)
		if value:
			return value
	field_verification = upload_report.get("field_verification") if isinstance(upload_report.get("field_verification"), dict) else {}
	return field_verification.get("scheduled_publish_at")


def _title_for_episode(episode_dir: Path, metadata: dict[str, Any]) -> str | None:
	title = metadata.get("title")
	if title:
		return str(title)
	title_path = episode_dir / "video_title.txt"
	if title_path.exists():
		return title_path.read_text(encoding="utf-8").strip()
	return None


def _item_for_episode(episode_dir: Path, run_dir: Path, timezone_name: str) -> tuple[str, str, str, dict[str, Any]] | None:
	metadata_path = episode_dir / "bilibili_upload_metadata.json"
	metadata = _read_json_if_exists(metadata_path)
	upload_report_path = episode_dir / "bilibili_upload_draft_report.json"
	upload_report = _read_json_if_exists(upload_report_path)
	scheduled_value = _scheduled_publish_at(metadata, upload_report)
	if not scheduled_value or str(scheduled_value).startswith("not_requested"):
		return None
	scheduled_dt = _parse_datetime(scheduled_value, timezone_name)
	key, target_date, slot = _slot_from_datetime(scheduled_dt)
	status, paths = _derive_status(episode_dir)
	if metadata_path.exists():
		paths["metadata"] = str(metadata_path)
	final_video = metadata.get("video_path") or str(episode_dir / "video/final_video.mp4")
	subtitle_path = episode_dir / "video/final_subtitles.srt"
	item = {
		"run_dir": str(run_dir),
		"episode_run_dir": str(episode_dir),
		"title": _title_for_episode(episode_dir, metadata),
		"status": status,
		"scheduled_publish_at": scheduled_dt.isoformat(),
		"scheduled_publish_timezone": timezone_name,
		"final_video": str(final_video) if final_video else None,
		"subtitle": str(subtitle_path) if subtitle_path.exists() else None,
		"reports": paths,
	}
	return key, target_date, slot, item


def _status_from_items(items: list[dict[str, Any]]) -> str:
	statuses = [str(item.get("status") or "UNKNOWN") for item in items]
	for status in STATUS_PRIORITY:
		if status in statuses:
			return status
	return "UNKNOWN"


def commit_run(
	root_dir: Path,
	run_dir: Path,
	timezone_name: str = DEFAULT_TIMEZONE,
	now: datetime | None = None,
	ledger_name: str = DEFAULT_LEDGER_NAME,
) -> dict[str, Any]:
	root_dir = _ensure_root_writable(Path(root_dir))
	run_dir = Path(run_dir)
	current = _now(timezone_name, now)
	ledger_file = _ledger_path(root_dir, ledger_name)
	with _locked(root_dir):
		ledger = _load_ledger(ledger_file)
		committed: list[dict[str, Any]] = []
		skipped: list[dict[str, Any]] = []
		for episode_dir in _episode_dirs_for_run(run_dir):
			item_info = _item_for_episode(episode_dir, run_dir, timezone_name)
			if item_info is None:
				skipped.append({
					"episode_run_dir": str(episode_dir),
					"reason": "missing_scheduled_publish_at",
				})
				continue
			key, target_date, slot, item = item_info
			entry = dict(ledger["slots"].get(key) or {
				"key": key,
				"date": target_date,
				"slot": slot,
				"items": [],
			})
			items = [
				existing
				for existing in list(entry.get("items") or [])
				if existing.get("episode_run_dir") != item.get("episode_run_dir")
			]
			items.append(item)
			entry.update({
				"key": key,
				"date": target_date,
				"slot": slot,
				"status": _status_from_items(items),
				"run_dir": str(run_dir),
				"run_id": run_dir.name,
				"title": item.get("title"),
				"scheduled_publish_at": item.get("scheduled_publish_at"),
				"updated_at": current.isoformat(),
				"items": items,
			})
			ledger["slots"][key] = entry
			committed.append(_entry_summary(key, target_date, slot, entry, current, DEFAULT_RESERVATION_TTL_HOURS))
		_save_ledger(ledger_file, ledger, timezone_name, current)
		return {
			"schema_version": "worldview-china-publish-slot-commit.v1",
			"status": "OK",
			"ledger_path": str(ledger_file),
			"run_dir": str(run_dir),
			"committed_slots": committed,
			"skipped_items": skipped,
		}


def sync_runs(
	root_dir: Path,
	timezone_name: str = DEFAULT_TIMEZONE,
	now: datetime | None = None,
	ledger_name: str = DEFAULT_LEDGER_NAME,
) -> dict[str, Any]:
	root_dir = _ensure_root_writable(Path(root_dir))
	synced: list[dict[str, Any]] = []
	for child in sorted(root_dir.iterdir()):
		if not child.is_dir():
			continue
		if not re.fullmatch(r"\d{8}_\d+", child.name):
			continue
		if not (child / "bilibili_upload_metadata.json").exists() and not (child / "04b-series-episodes/series_manifest.json").exists():
			continue
		synced.append(commit_run(root_dir, child, timezone_name=timezone_name, now=now, ledger_name=ledger_name))
	return {
		"schema_version": "worldview-china-publish-slot-sync.v1",
		"status": "OK",
		"root_dir": str(root_dir),
		"synced_run_count": len(synced),
		"synced_runs": synced,
	}


def _add_common_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--root-dir", default=str(DEFAULT_ROOT_DIR))
	parser.add_argument("--ledger-name", default=DEFAULT_LEDGER_NAME)
	parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)


def _print_json(data: dict[str, Any]) -> None:
	print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Maintain the Worldview China daily Bilibili publish slot ledger.")
	subparsers = parser.add_subparsers(dest="command", required=True)

	plan_parser = subparsers.add_parser("plan", help="Show missing/satisfied slots for one target publish date.")
	_add_common_args(plan_parser)
	plan_parser.add_argument("--target-date")
	plan_parser.add_argument("--slots", default=",".join(DEFAULT_SLOTS))
	plan_parser.add_argument("--reservation-ttl-hours", type=float, default=DEFAULT_RESERVATION_TTL_HOURS)

	reserve_parser = subparsers.add_parser("reserve", help="Reserve one or more slots for a production run.")
	_add_common_args(reserve_parser)
	reserve_parser.add_argument("--target-date", required=True)
	reserve_parser.add_argument("--slot", action="append", dest="slots", required=True)
	reserve_parser.add_argument("--run-dir", required=True)
	reserve_parser.add_argument("--run-id")
	reserve_parser.add_argument("--reservation-ttl-hours", type=float, default=DEFAULT_RESERVATION_TTL_HOURS)
	reserve_parser.add_argument("--force", action="store_true")

	release_parser = subparsers.add_parser("release", help="Release active reservations for a run.")
	_add_common_args(release_parser)
	release_parser.add_argument("--run-dir")
	release_parser.add_argument("--run-id")
	release_parser.add_argument("--target-date")
	release_parser.add_argument("--slot", action="append", dest="slots")
	release_parser.add_argument("--status", default="RELEASED")

	commit_parser = subparsers.add_parser("commit-run", help="Commit submitted/monitored episode schedules into the ledger.")
	_add_common_args(commit_parser)
	commit_parser.add_argument("--run-dir", required=True)

	sync_parser = subparsers.add_parser("sync", help="Scan top-level run directories and merge submitted schedules into the ledger.")
	_add_common_args(sync_parser)

	args = parser.parse_args(argv)
	try:
		root_dir = Path(args.root_dir)
		if args.command == "plan":
			_print_json(plan_slots(
				root_dir=root_dir,
				target_date=args.target_date,
				slots=args.slots,
				timezone_name=args.timezone,
				reservation_ttl_hours=args.reservation_ttl_hours,
				ledger_name=args.ledger_name,
			))
		elif args.command == "reserve":
			_print_json(reserve_slots(
				root_dir=root_dir,
				target_date=args.target_date,
				slots=args.slots,
				run_dir=Path(args.run_dir),
				run_id=args.run_id,
				timezone_name=args.timezone,
				reservation_ttl_hours=args.reservation_ttl_hours,
				ledger_name=args.ledger_name,
				force=args.force,
			))
		elif args.command == "release":
			_print_json(release_run(
				root_dir=root_dir,
				run_dir=Path(args.run_dir) if args.run_dir else None,
				run_id=args.run_id,
				target_date=args.target_date,
				slots=args.slots,
				status=args.status,
				timezone_name=args.timezone,
				ledger_name=args.ledger_name,
			))
		elif args.command == "commit-run":
			_print_json(commit_run(
				root_dir=root_dir,
				run_dir=Path(args.run_dir),
				timezone_name=args.timezone,
				ledger_name=args.ledger_name,
			))
		elif args.command == "sync":
			_print_json(sync_runs(
				root_dir=root_dir,
				timezone_name=args.timezone,
				ledger_name=args.ledger_name,
			))
		else:
			raise AssertionError(f"Unhandled command: {args.command}")
		return 0
	except Exception as exc:
		_print_json({
			"schema_version": "worldview-china-publish-slot-error.v1",
			"status": "ERROR",
			"error": str(exc),
		})
		return 2


if __name__ == "__main__":
	raise SystemExit(main())
