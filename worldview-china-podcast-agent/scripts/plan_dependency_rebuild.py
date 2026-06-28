#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import run_pre_tts_frozen_contract as contract


SCOPE_TO_CHAIN = {
	"text": contract.TEXT_CHANGE_REBUILD_CHAIN,
	"audio": contract.AUDIO_CHANGE_REBUILD_CHAIN,
	"subtitle": contract.SUBTITLE_CHANGE_REBUILD_CHAIN,
	"metadata": contract.METADATA_CHANGE_REBUILD_CHAIN,
}
RESULT_REL = Path("00-rebuild-plan/rebuild-plan.json")
REPORT_REL = Path("00-rebuild-plan/rebuild-plan.md")


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now_iso() -> str:
	return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _auto_changed_inputs(run_dir: Path, contract_json: Path) -> list[dict[str, Any]]:
	if not contract_json.exists():
		return [{
			"path": str(contract_json),
			"change_type": "missing_contract",
			"scope": "text",
			"reason": "No 04d contract exists; safest rebuild scope before VibeVoice is text.",
		}]
	data = _read_json(contract_json)
	changes: list[dict[str, Any]] = []
	hashes = data.get("input_file_hashes") if isinstance(data.get("input_file_hashes"), dict) else {}
	for rel_path, expected in hashes.items():
		path = Path(rel_path)
		if not path.is_absolute():
			path = run_dir / path
		if not path.exists():
			changes.append({
				"path": str(path),
				"change_type": "deleted",
				"expected_sha256": expected,
				"current_sha256": None,
				"scope": _classify_path_scope(rel_path),
			})
			continue
		current = contract._sha256(path)
		if current != expected:
			changes.append({
				"path": str(path),
				"change_type": "modified",
				"expected_sha256": expected,
				"current_sha256": current,
				"scope": _classify_path_scope(rel_path),
			})
	return changes


def _classify_path_scope(path: str) -> str:
	lower = path.lower()
	if "bilibili_upload_metadata" in lower or "publish_info" in lower or "10-bilibili" in lower:
		return "metadata"
	if "subtitle" in lower or lower.endswith(".srt") or lower.endswith(".ass") or "07-subtitles" in lower:
		return "subtitle"
	if "audio/" in lower or "05-vibevoice" in lower or "06" in lower:
		return "audio"
	return "text"


def _scope_priority(scope: str) -> int:
	return {"text": 0, "audio": 1, "subtitle": 2, "metadata": 3}[scope]


def _narrowest_scope(scopes: list[str]) -> str:
	if not scopes:
		return "none"
	return min(scopes, key=_scope_priority)


def plan_rebuild(run_dir: Path, changed_scope: str, contract_json: Path | None = None) -> dict[str, Any]:
	run_dir = run_dir.expanduser().resolve()
	contract_json = contract_json or (run_dir / contract.RESULT_REL)
	changes: list[dict[str, Any]] = []
	if changed_scope == "auto":
		changes = _auto_changed_inputs(run_dir, contract_json)
		scope = _narrowest_scope([str(item.get("scope") or "text") for item in changes])
	elif changed_scope == "none":
		scope = "none"
	else:
		scope = changed_scope
		changes = [{"scope": scope, "change_type": "manual_scope"}]
	chain = [] if scope == "none" else SCOPE_TO_CHAIN[scope]
	result = {
		"schema_version": "worldview-china-dependency-rebuild-plan.v1",
		"status": "NO_REBUILD_NEEDED" if scope == "none" else "REBUILD_REQUIRED",
		"created_at": _now_iso(),
		"run_dir": str(run_dir),
		"contract_json": str(contract_json),
		"changed_scope": changed_scope,
		"effective_scope": scope,
		"detected_changes": changes,
		"required_rebuild_chain": chain,
		"notes": [
			"This planner does not relax QA gates; it records the minimum downstream chain that must be rebuilt after an upstream change.",
			"Run 04d again after the rebuild chain reaches a new stable pre-TTS state.",
		],
	}
	return result


def write_report(result: dict[str, Any], report_path: Path) -> None:
	lines = [
		"# Dependency Rebuild Plan",
		"",
		f"- status: `{result['status']}`",
		f"- changed_scope: `{result['changed_scope']}`",
		f"- effective_scope: `{result['effective_scope']}`",
		"",
		"## Detected Changes",
		"",
	]
	for item in result.get("detected_changes", []):
		lines.append(f"- `{item.get('scope')}` {item.get('change_type')}: `{item.get('path', '')}`")
	lines.extend(["", "## Required Rebuild Chain", ""])
	for step in result.get("required_rebuild_chain", []):
		lines.append(f"- {step}")
	report_path.parent.mkdir(parents=True, exist_ok=True)
	report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
	parser = argparse.ArgumentParser(description="Plan the required Worldview China rebuild chain after an upstream artifact changes.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--changed-scope", choices=("auto", "text", "audio", "subtitle", "metadata", "none"), default="auto")
	parser.add_argument("--contract-json", type=Path)
	args = parser.parse_args()
	run_dir = args.run_dir.expanduser().resolve()
	result = plan_rebuild(run_dir, args.changed_scope, args.contract_json.expanduser().resolve() if args.contract_json else None)
	_write_json(run_dir / RESULT_REL, result)
	write_report(result, run_dir / REPORT_REL)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "NO_REBUILD_NEEDED" else 1


if __name__ == "__main__":
	raise SystemExit(main())
