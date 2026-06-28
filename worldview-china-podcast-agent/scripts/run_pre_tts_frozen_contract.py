#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RESULT_REL = Path("04d-pre-tts-frozen-contract/pre-tts-frozen-contract-result.json")
REPORT_REL = Path("04d-pre-tts-frozen-contract/pre-tts-frozen-contract-report.md")
MAX_SPEAKERS = 4

TEXT_CHANGE_REBUILD_CHAIN = [
	"03c-translation-semantic-qa",
	"03d-risk-compliance-review",
	"03e-speaker-turn-roster-consistency",
	"04c-bilibili-text-compliance",
	"04d-pre-tts-frozen-contract",
	"05-vibevoice-preflight-audition",
	"05-vibevoice-chunks",
	"06-audio-alignment",
	"06b-audio-transcript-integrity",
	"06c-audio-timeline-alignment",
	"06d-voice-consistency-qa",
	"07-subtitles",
	"04c-bilibili-text-compliance-after-subtitles",
	"08-source-video-revoice",
	"09a-multimodal-spot-qa",
	"09-final-qa",
	"10-bilibili-publish",
	"04c-bilibili-text-compliance-after-metadata",
	"11-bilibili-upload",
	"11c-bilibili-audit-monitor",
	"11d-process-review",
]
AUDIO_CHANGE_REBUILD_CHAIN = [
	"06-audio-alignment",
	"06b-audio-transcript-integrity",
	"06c-audio-timeline-alignment",
	"06d-voice-consistency-qa",
	"07-subtitles",
	"04c-bilibili-text-compliance-after-subtitles",
	"08-source-video-revoice",
	"09a-multimodal-spot-qa",
	"09-final-qa",
	"10-bilibili-publish",
	"04c-bilibili-text-compliance-after-metadata",
	"11-bilibili-upload",
	"11c-bilibili-audit-monitor",
	"11d-process-review",
]
SUBTITLE_CHANGE_REBUILD_CHAIN = [
	"04c-bilibili-text-compliance-after-subtitles",
	"08-source-video-revoice",
	"09a-multimodal-spot-qa",
	"09-final-qa",
	"10-bilibili-publish",
	"04c-bilibili-text-compliance-after-metadata",
	"11-bilibili-upload",
	"11c-bilibili-audit-monitor",
	"11d-process-review",
]
METADATA_CHANGE_REBUILD_CHAIN = [
	"04c-bilibili-text-compliance-after-metadata",
	"11-bilibili-upload",
	"11c-bilibili-audit-monitor",
	"11d-process-review",
]


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _now_iso() -> str:
	return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _resolve_hash_map(values: Any, run_dir: Path) -> dict[str, str]:
	if not isinstance(values, dict):
		return {}
	resolved: dict[str, str] = {}
	for key, value in values.items():
		if not isinstance(key, str) or not key.strip():
			continue
		path = Path(key).expanduser()
		if not path.is_absolute():
			path = run_dir / path
		try:
			path = path.resolve()
		except OSError:
			pass
		resolved[str(path)] = str(value)
	return resolved


def _rel(run_dir: Path, path: Path) -> str:
	try:
		return str(path.resolve().relative_to(run_dir.resolve()))
	except ValueError:
		return str(path.resolve())


def _current_input_paths(run_dir: Path) -> dict[str, Path]:
	paths: dict[str, Path] = {}
	candidates = {
		"speaker_roster": "02a-speaker-census/speaker_roster.json",
		"qwen_voice_prompt_manifest": "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json",
		"faithful_translation_json": "03-source-translation/source_transcript.zh.json",
		"faithful_translation_md": "03-source-translation/source_transcript.zh.md",
		"safe_translation_json": "03b-mainland-publish-safety/source_transcript.zh.safe.json",
		"safe_translation_md": "03b-mainland-publish-safety/source_transcript.zh.safe.md",
		"script_turns": "04-podcast-script/script_turns.json",
		"node_podcast_script": "04-podcast-script/podcast_script.md",
		"root_podcast_script": "podcast_script.md",
		"video_title": "video_title.txt",
		"cover_title": "cover/cover_title.json",
	}
	for label, rel_path in candidates.items():
		path = run_dir / rel_path
		if path.exists():
			paths[label] = path
	return paths


def _required_review_hash_current(
	review: dict[str, Any],
	required_paths: dict[str, Path],
	run_dir: Path,
	hash_field: str = "reviewed_file_hashes",
) -> list[str]:
	failures: list[str] = []
	hashes = _resolve_hash_map(review.get(hash_field), run_dir)
	if not hashes:
		return [f"{hash_field} missing"]
	for label, path in required_paths.items():
		resolved = str(path.resolve())
		expected = hashes.get(resolved)
		if expected is None:
			failures.append(f"missing hash for {label}: {_rel(run_dir, path)}")
			continue
		current = _sha256(path)
		if expected != current:
			failures.append(f"stale hash for {label}: {_rel(run_dir, path)}")
	return failures


def _gate_result(
	name: str,
	path: Path,
	run_dir: Path,
	required_paths: dict[str, Path],
	status_field: str = "status",
	pass_values: set[str] | None = None,
	hash_field: str = "reviewed_file_hashes",
) -> dict[str, Any]:
	pass_values = pass_values or {"PASS"}
	if not path.exists():
		return {
			"name": name,
			"status": "FAIL",
			"path": str(path),
			"failures": [f"missing {name}: {_rel(run_dir, path)}"],
		}
	try:
		review = _read_json(path)
	except json.JSONDecodeError as exc:
		return {
			"name": name,
			"status": "FAIL",
			"path": str(path),
			"failures": [f"invalid json: {exc}"],
		}
	status = str(review.get(status_field) or "")
	failures = []
	if status not in pass_values:
		failures.append(f"status is {status or 'MISSING'}, expected one of {sorted(pass_values)}")
	failures.extend(_required_review_hash_current(review, required_paths, run_dir, hash_field=hash_field))
	return {
		"name": name,
		"status": "PASS" if not failures else "FAIL",
		"path": str(path),
		"reported_status": status,
		"required_paths": {label: _rel(run_dir, item) for label, item in required_paths.items()},
		"failures": failures,
	}


def _validate_roster(run_dir: Path, roster_path: Path) -> dict[str, Any]:
	failures: list[str] = []
	try:
		roster = _read_json(roster_path)
	except json.JSONDecodeError as exc:
		return {"name": "02a-speaker-census", "status": "FAIL", "path": str(roster_path), "failures": [str(exc)]}
	if roster.get("status") != "frozen":
		failures.append("speaker_roster.status is not frozen")
	count = int(roster.get("speaker_count") or 0)
	voice_count = int(roster.get("voice_count") or 0)
	if not (1 <= count <= MAX_SPEAKERS):
		failures.append(f"speaker_count is not within 1-{MAX_SPEAKERS}: {count}")
	if voice_count != count:
		failures.append(f"voice_count {voice_count} does not equal speaker_count {count}")
	speakers = roster.get("speakers") if isinstance(roster.get("speakers"), dict) else {}
	expected = [f"Speaker {index}" for index in range(count)]
	if sorted(speakers.keys()) != expected:
		failures.append(f"speakers are not contiguous {expected}")
	return {
		"name": "02a-speaker-census",
		"status": "PASS" if not failures else "FAIL",
		"path": str(roster_path),
		"speaker_count": count,
		"failures": failures,
	}


def _gate_applies(run_dir: Path) -> bool:
	return (run_dir / "04c-bilibili-text-compliance/text-compliance-review-result.json").exists() or (run_dir / RESULT_REL).exists()


def build_contract(run_dir: Path) -> dict[str, Any]:
	run_dir = run_dir.expanduser().resolve()
	inputs = _current_input_paths(run_dir)
	failures: list[str] = []
	gates: list[dict[str, Any]] = []

	required_input_labels = [
		"speaker_roster",
		"qwen_voice_prompt_manifest",
		"faithful_translation_json",
		"script_turns",
		"node_podcast_script",
		"root_podcast_script",
	]
	for label in required_input_labels:
		if label not in inputs:
			failures.append(f"missing required frozen input: {label}")
	active_translation = inputs.get("safe_translation_json") or inputs.get("faithful_translation_json")
	if active_translation is None:
		failures.append("missing active translation file")

	if "speaker_roster" in inputs:
		gates.append(_validate_roster(run_dir, inputs["speaker_roster"]))

	if active_translation is not None and "faithful_translation_json" in inputs:
		translation_required = {
			"faithful_translation_json": inputs["faithful_translation_json"],
			"active_translation_json": active_translation,
		}
		gates.append(_gate_result(
			"03c-translation-semantic-qa",
			run_dir / "03c-translation-semantic-qa/translation-semantic-qa-result.json",
			run_dir,
			translation_required,
		))
		gates.append(_gate_result(
			"03d-risk-compliance-review",
			run_dir / "03d-risk-compliance-review/text-compliance-review-result.json",
			run_dir,
			translation_required,
		))
		gates.append(_gate_result(
			"03d-independent-risk-review",
			run_dir / "03d-risk-compliance-review/independent-review-result.json",
			run_dir,
			translation_required,
		))

	if active_translation is not None and "speaker_roster" in inputs and "script_turns" in inputs and "node_podcast_script" in inputs and "root_podcast_script" in inputs:
		roster_required = {
			"speaker_roster": inputs["speaker_roster"],
			"active_translation_json": active_translation,
			"script_turns": inputs["script_turns"],
			"node_podcast_script": inputs["node_podcast_script"],
			"root_podcast_script": inputs["root_podcast_script"],
		}
		gates.append(_gate_result(
			"03e-speaker-turn-roster-consistency",
			run_dir / "03e-speaker-turn-roster-consistency/speaker-turn-roster-consistency-result.json",
			run_dir,
			roster_required,
			hash_field="input_file_hashes",
		))

	publishable_required = {
		label: path
		for label, path in {
			"active_translation_json": active_translation,
			"script_turns": inputs.get("script_turns"),
			"node_podcast_script": inputs.get("node_podcast_script"),
			"root_podcast_script": inputs.get("root_podcast_script"),
			"video_title": inputs.get("video_title"),
			"cover_title": inputs.get("cover_title"),
		}.items()
		if path is not None and path.exists()
	}
	if publishable_required:
		gates.append(_gate_result(
			"04c-bilibili-text-compliance",
			run_dir / "04c-bilibili-text-compliance/text-compliance-review-result.json",
			run_dir,
			publishable_required,
		))
		gates.append(_gate_result(
			"04c-independent-text-review",
			run_dir / "04c-bilibili-text-compliance/independent-review-result.json",
			run_dir,
			publishable_required,
		))

	for gate in gates:
		if gate["status"] != "PASS":
			failures.extend(f"{gate['name']}: {failure}" for failure in gate.get("failures", []))

	input_hashes = {
		_rel(run_dir, path): _sha256(path)
		for path in sorted(inputs.values(), key=lambda item: str(item))
	}
	result = {
		"schema_version": "worldview-china-pre-tts-frozen-contract.v1",
		"status": "PASS" if not failures else "FAIL",
		"created_at": _now_iso(),
		"run_dir": str(run_dir),
		"node": "04d-pre-tts-frozen-contract",
		"purpose": "Freeze current speaker, translation, script, title/cover and text-compliance hashes before any full VibeVoice generation.",
		"input_file_hashes": input_hashes,
		"active_translation": _rel(run_dir, active_translation) if active_translation else None,
		"gates": gates,
		"failures": failures,
		"dependency_rebuild_contract": {
			"text_change": TEXT_CHANGE_REBUILD_CHAIN,
			"audio_change": AUDIO_CHANGE_REBUILD_CHAIN,
			"subtitle_change": SUBTITLE_CHANGE_REBUILD_CHAIN,
			"metadata_change": METADATA_CHANGE_REBUILD_CHAIN,
		},
	}
	return result


def write_report(result: dict[str, Any], report_path: Path) -> None:
	lines = [
		"# Pre-TTS Frozen Contract",
		"",
		f"- status: `{result['status']}`",
		f"- run_dir: `{result['run_dir']}`",
		f"- active_translation: `{result.get('active_translation')}`",
		"",
		"## Gates",
		"",
		"| gate | status | failures |",
		"|---|---|---|",
	]
	for gate in result.get("gates", []):
		failures = "; ".join(gate.get("failures") or [])
		lines.append(f"| {gate['name']} | {gate['status']} | {failures} |")
	lines.extend([
		"",
		"## Dependency Rebuild Contract",
		"",
		"- Text changes invalidate 03c/03d/03e/04c/04d and every downstream audio, subtitle, video, metadata, upload, audit and process-review artifact.",
		"- Audio changes invalidate 06 onward.",
		"- Subtitle changes invalidate 04c-after-subtitles, 08 onward, metadata/upload/audit/process-review.",
		"- Metadata changes invalidate 04c-after-metadata, upload/audit/process-review.",
		"",
	])
	if result.get("failures"):
		lines.append("## Failures")
		lines.append("")
		for failure in result["failures"]:
			lines.append(f"- {failure}")
	report_path.parent.mkdir(parents=True, exist_ok=True)
	report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_contract(run_dir: Path, force: bool = False) -> dict[str, Any]:
	run_dir = run_dir.expanduser().resolve()
	result_path = run_dir / RESULT_REL
	report_path = run_dir / REPORT_REL
	if result_path.exists() and not force:
		existing = _read_json(result_path)
		if existing.get("status") == "PASS":
			try:
				validate_contract_gate(run_dir)
				return existing
			except RuntimeError:
				pass
	result = build_contract(run_dir)
	_write_json(result_path, result)
	write_report(result, report_path)
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["04d-pre-tts-frozen-contract"] = {
		"status": result["status"].lower(),
		"result": str(result_path),
		"report": str(report_path),
	}
	_write_json(run_manifest_path, run_manifest)
	return result


def validate_contract_gate(run_dir: Path) -> None:
	run_dir = run_dir.expanduser().resolve()
	result_path = run_dir / RESULT_REL
	if not result_path.exists():
		raise RuntimeError(
			"Missing required 04d pre-TTS frozen contract before VibeVoice. "
			f"Run: python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_pre_tts_frozen_contract.py --run-dir {run_dir} --force"
		)
	result = _read_json(result_path)
	status = str(result.get("status") or "")
	if status != "PASS":
		raise RuntimeError(f"04d pre-TTS frozen contract is {status}; see {result_path}")
	hashes = result.get("input_file_hashes") if isinstance(result.get("input_file_hashes"), dict) else {}
	if not hashes:
		raise RuntimeError(f"04d pre-TTS frozen contract has no input_file_hashes: {result_path}")
	for rel_path, expected in hashes.items():
		path = Path(rel_path)
		if not path.is_absolute():
			path = run_dir / path
		if not path.exists():
			raise RuntimeError(f"04d pre-TTS frozen contract input disappeared: {path}")
		current = _sha256(path)
		if current != expected:
			raise RuntimeError(
				f"04d pre-TTS frozen contract is stale for {rel_path}: expected sha256 {expected}, current {current}. "
				"Run plan_dependency_rebuild.py to identify the required rebuild chain, then rerun 04d."
			)


def validate_if_applicable(run_dir: Path) -> None:
	if _gate_applies(run_dir):
		validate_contract_gate(run_dir)


def main() -> int:
	parser = argparse.ArgumentParser(description="Freeze pre-TTS text/roster/review contract before full VibeVoice generation.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--force", action="store_true")
	args = parser.parse_args()
	result = run_contract(args.run_dir, force=args.force)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
