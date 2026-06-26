#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MAX_SPEAKERS = 4
DEFAULT_SCHEDULED_PUBLISH_SLOTS = ("11:00", "17:00")
SERIES_BALANCED_SLOT_SCHEDULE_SOURCE = "series_daily_11_17_balanced_ordered_slots"
SPEAKER_RE = re.compile(r"^Speaker ([0-3])$")
LOCKED_ROSTER_PATCH_POLICIES = {
	"single_speaker_patch_from_locked_roster",
}
ALLOWED_AUDIT_MONITOR_STATUSES = {
	"APPROVED",
	"REVIEW_PENDING_AFTER_MAX_CHECKS",
}


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _read_json_optional(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {}
	return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
	return path.read_text(encoding="utf-8") if path.exists() else ""


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _chinese_episode_label(index: int) -> str:
	values = {
		1: "一",
		2: "二",
		3: "三",
		4: "四",
		5: "五",
		6: "六",
		7: "七",
		8: "八",
		9: "九",
		10: "十",
		11: "十一",
		12: "十二",
		13: "十三",
		14: "十四",
		15: "十五",
		16: "十六",
		17: "十七",
		18: "十八",
		19: "十九",
		20: "二十",
	}
	if index in values:
		return values[index]
	tens = index // 10
	ones = index % 10
	prefix = values.get(tens, str(tens))
	suffix = values.get(ones, "") if ones else ""
	return f"{prefix}十{suffix}"


def _format_episode_order_marker(template: str, index: int) -> str:
	label = _chinese_episode_label(index)
	marker = template.format(
		episode_index=index,
		episode_label=label,
		episode_number=label,
	).strip()
	return marker


def _parse_dt(value: Any) -> datetime | None:
	if not value:
		return None
	return datetime.fromisoformat(str(value))


def _parse_publish_slots(value: Any) -> tuple[str, ...]:
	if isinstance(value, str):
		raw_slots = [slot.strip() for slot in value.split(",")]
	elif isinstance(value, (list, tuple)):
		raw_slots = [str(slot).strip() for slot in value]
	else:
		raw_slots = list(DEFAULT_SCHEDULED_PUBLISH_SLOTS)
	slots: list[str] = []
	for raw_slot in raw_slots:
		match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", raw_slot)
		if not match:
			continue
		slot = f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
		if slot not in slots:
			slots.append(slot)
	return tuple(slots or DEFAULT_SCHEDULED_PUBLISH_SLOTS)


def _slot_counts_for_episode_count(episode_count: int, slot_count: int) -> list[int]:
	base = episode_count // slot_count
	remainder = episode_count % slot_count
	return [base + (1 if index < remainder else 0) for index in range(slot_count)]


def _expected_balanced_slot_schedule(first_schedule: datetime, episode_index: int, episode_count: int, slots: tuple[str, ...]) -> datetime:
	counts = _slot_counts_for_episode_count(episode_count, len(slots))
	start = 1
	slot_index = 0
	for current_slot_index, count in enumerate(counts):
		end = start + count - 1
		if count > 0 and start <= episode_index <= end:
			slot_index = current_slot_index
			break
		start = end + 1
	slot = slots[slot_index]
	hour, minute = (int(part) for part in slot.split(":"))
	return first_schedule.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _speaker_index(speaker: str) -> int:
	match = SPEAKER_RE.fullmatch(speaker)
	assert match, f"Unsupported speaker id: {speaker}"
	return int(match.group(1))


def _sorted_speakers(values: Any) -> list[str]:
	speakers = [str(value) for value in values if SPEAKER_RE.fullmatch(str(value))]
	return sorted(set(speakers), key=_speaker_index)


def _is_locked_roster_policy(value: Any) -> bool:
	return str(value or "") in {"locked_multi_speaker_roster", "locked_two_speaker_roster"}


def _chunk_uses_locked_roster(chunk: dict[str, Any], expected_speaker_names: list[str]) -> bool:
	speaker_names = [str(name) for name in chunk.get("speaker_names") or []]
	if chunk.get("vibevoice_mode") == "dialogue":
		return speaker_names == expected_speaker_names
	if str(chunk.get("voice_context_policy") or "") in LOCKED_ROSTER_PATCH_POLICIES:
		return bool(speaker_names) and set(speaker_names).issubset(set(expected_speaker_names))
	return False


def _expected_speakers_from_roster(roster: dict[str, Any], failures: list[str], label: str) -> list[str]:
	count = int(roster.get("speaker_count") or 0)
	voice_count = int(roster.get("voice_count") or 0)
	if not (1 <= count <= MAX_SPEAKERS):
		failures.append(f"{label} speaker_count is not within 1-{MAX_SPEAKERS}")
		return []
	if voice_count != count:
		failures.append(f"{label} voice_count does not match speaker_count")
	speakers = _sorted_speakers((roster.get("speakers") or {}).keys())
	expected = [f"Speaker {index}" for index in range(count)]
	if speakers != expected:
		failures.append(f"{label} speakers are not contiguous Speaker 0..{count - 1}")
	return expected


def _upload_report_has_final_submit_proof(upload_report: dict[str, Any]) -> bool:
	if upload_report.get("final_submit_clicked") is True:
		return True
	if str(upload_report.get("submission_status") or "") == "submitted":
		return True
	evidence_text = json.dumps({
		"success_evidence": upload_report.get("success_evidence"),
		"submission_evidence": upload_report.get("submission_evidence"),
		"post_submit_state": upload_report.get("post_submit_state"),
	}, ensure_ascii=False)
	return "稿件投递成功" in evidence_text and "上传成功" in evidence_text


def _upload_report_has_user_submit_now_override(upload_report: dict[str, Any]) -> bool:
	field_verification = upload_report.get("field_verification") if isinstance(upload_report.get("field_verification"), dict) else {}
	schedule_override = upload_report.get("schedule_override") if isinstance(upload_report.get("schedule_override"), dict) else {}
	evidence_text = json.dumps({
		"field_verification_scheduled_publish_at": field_verification.get("scheduled_publish_at"),
		"schedule_override": schedule_override,
		"repost_reason": upload_report.get("repost_reason"),
		"scheduled_publish_at": upload_report.get("scheduled_publish_at"),
		"scheduled_publish_at_requested": upload_report.get("scheduled_publish_at_requested"),
		"scheduled_publish_at_effective": upload_report.get("scheduled_publish_at_effective"),
	}, ensure_ascii=False)
	return (
		"not_requested_user_override_submit_now" in evidence_text
		or "User requested immediate submission" in evidence_text
		or "disabled scheduled publishing per user request" in evidence_text
	)


def _validate_audit_monitor_status(
	episode_dir: Path,
	episode_index: int,
	upload_status: str,
	require_upload_submitted: bool,
	failures: list[str],
) -> None:
	if upload_status == "BLOCKED" and not require_upload_submitted:
		return
	report_path = episode_dir / "11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json"
	report = _read_json_optional(report_path)
	if not report:
		failures.append(f"episode_{episode_index:03d} audit monitor report is missing: {report_path}")
		return
	status = str(report.get("status") or "")
	if status not in ALLOWED_AUDIT_MONITOR_STATUSES:
		failures.append(
			f"episode_{episode_index:03d} audit monitor status is not allowed: "
			f"{status or 'missing'}"
		)


def run_series_qa(run_dir: Path, require_upload_submitted: bool, write_history: bool) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	series_manifest_path = run_dir / "04b-series-episodes/series_manifest.json"
	failures: list[str] = []
	warnings: list[str] = []
	if not series_manifest_path.exists():
		failures.append(f"Missing series manifest: {series_manifest_path}")
		return _write_result(run_dir, failures, warnings, write_history)
	series_manifest = _read_json(series_manifest_path)
	episodes = list(series_manifest.get("episodes") or [])
	if not episodes:
		failures.append("series_manifest has no episodes")
		return _write_result(run_dir, failures, warnings, write_history)
	if series_manifest.get("serial_execution_required") is not True or series_manifest.get("parallel_execution_allowed") is not False:
		failures.append("series_manifest must require serial execution and disallow parallel execution")
	expected_indices = list(range(1, len(episodes) + 1))
	actual_indices = [int(episode.get("episode_index") or 0) for episode in episodes]
	if actual_indices != expected_indices:
		failures.append(f"episode indices are not contiguous and ordered: {actual_indices}")
	first_schedule = _parse_dt(episodes[0].get("scheduled_publish_at"))
	schedule_slots = _parse_publish_slots(series_manifest.get("bilibili_schedule_slots"))
	seen_titles: set[str] = set()
	shared_cover_frame = str(series_manifest.get("shared_cover_frame") or "")
	series_title_template = str(series_manifest.get("episode_title_template") or "")
	series_marker_template = str(series_manifest.get("episode_order_marker_template") or "")
	for expected_index, episode in enumerate(episodes, start=1):
		episode_dir = Path(str(episode.get("episode_run_dir") or ""))
		if not episode_dir.exists():
			failures.append(f"episode run dir missing: {episode_dir}")
			continue
		episode_manifest = _read_json_optional(episode_dir / "episode_manifest.json")
		video_title = _read_text(episode_dir / "video_title.txt").strip()
		cover_title = _read_json_optional(episode_dir / "cover/cover_title.json")
		title_cover_manifest = _read_json_optional(episode_dir / "02d-title-cover/title_cover_manifest.json")
		final_qa = _read_json_optional(episode_dir / "09-final-qa/final-qa-result.json")
		render_manifest = _read_json_optional(episode_dir / "video/render_manifest.json")
		audio_manifest = _read_json_optional(episode_dir / "audio/audio_manifest.json")
		chunk_plan = _read_json_optional(episode_dir / "05-vibevoice-chunks/chunk_plan.json")
		speaker_census = _read_json_optional(episode_dir / "02a-speaker-census/speaker_roster.json")
		metadata = _read_json_optional(episode_dir / "bilibili_upload_metadata.json")
		upload_report = _read_json_optional(episode_dir / "bilibili_upload_draft_report.json")
		if int(episode_manifest.get("episode_index") or 0) != expected_index:
			failures.append(f"episode_{expected_index:03d} manifest episode_index mismatch")
		episode_title_template = str(episode_manifest.get("episode_title_template") or episode.get("episode_title_template") or "")
		episode_marker_template = str(episode_manifest.get("episode_order_marker_template") or episode.get("episode_order_marker_template") or "")
		if series_title_template and episode_title_template != series_title_template:
			failures.append(f"episode_{expected_index:03d} title template differs from series_manifest")
		if series_marker_template and episode_marker_template != series_marker_template:
			failures.append(f"episode_{expected_index:03d} order marker template differs from series_manifest")
		expected_video_title = str(episode_manifest.get("video_title") or episode.get("video_title") or "")
		if expected_video_title and video_title != expected_video_title:
			failures.append(f"episode_{expected_index:03d} title does not match episode_manifest video_title")
		series_title_prefix = str(episode_manifest.get("series_title_prefix") or "")
		episode_subtitle = str(episode_manifest.get("episode_subtitle") or "")
		episode_order_marker = str(episode_manifest.get("episode_order_marker") or "")
		if series_marker_template:
			try:
				expected_marker = _format_episode_order_marker(series_marker_template, expected_index)
			except Exception as exc:
				failures.append(f"episode order marker template is invalid: {series_marker_template!r}: {exc}")
				expected_marker = ""
			if expected_marker and episode_order_marker != expected_marker:
				failures.append(
					f"episode_{expected_index:03d} order marker does not match the series marker template: "
					f"actual={episode_order_marker} expected={expected_marker}"
				)
		if series_title_prefix and series_title_prefix not in video_title:
			failures.append(f"episode_{expected_index:03d} title does not contain the shared series title")
		if episode_subtitle and episode_subtitle not in video_title:
			failures.append(f"episode_{expected_index:03d} title does not contain the episode subtitle")
		if episode_order_marker and episode_order_marker not in video_title:
			failures.append(f"episode_{expected_index:03d} title does not contain the episode order marker")
		if video_title in seen_titles:
			failures.append(f"duplicate episode title: {video_title}")
		seen_titles.add(video_title)
		if cover_title.get("video_title_text") != video_title:
			failures.append(f"episode_{expected_index:03d} cover_title video_title_text mismatch")
		if cover_title.get("cover_title_omits_episode_index") is not True:
			failures.append(f"episode_{expected_index:03d} cover title does not omit episode index")
		if episode_order_marker and episode_order_marker in str(cover_title.get("title_text") or ""):
			failures.append(f"episode_{expected_index:03d} cover title still includes episode order marker")
		source_episode_video_status = str(episode_manifest.get("source_episode_video_status") or "")
		source_episode_video = str(episode_manifest.get("source_episode_video") or "")
		if source_episode_video_status == "pass" and (not source_episode_video or not Path(source_episode_video).exists()):
			failures.append(f"episode_{expected_index:03d} source_episode_video status is pass but file is missing")
		frame_meta = title_cover_manifest.get("frame_selection") or {}
		if shared_cover_frame and frame_meta.get("path") and str(frame_meta["path"]) != shared_cover_frame:
			failures.append(f"episode_{expected_index:03d} does not use the shared series cover background frame")
		if final_qa.get("overall_status") != "PASS":
			failures.append(f"episode_{expected_index:03d} final QA is not PASS")
		if str(render_manifest.get("subtitle_mode") or "") != "burned_ass":
			failures.append(f"episode_{expected_index:03d} render_manifest subtitle_mode is not burned_ass")
		if "burned_subtitles" not in str(render_manifest.get("visual_mode") or ""):
			failures.append(f"episode_{expected_index:03d} render_manifest visual_mode does not record burned_subtitles")
		if render_manifest.get("series_episode") is not True:
			failures.append(f"episode_{expected_index:03d} render_manifest does not record series_episode=true")
		if speaker_census.get("status") != "frozen":
			failures.append(f"episode_{expected_index:03d} speaker census is not frozen")
		expected_speakers = _expected_speakers_from_roster(speaker_census, failures, f"episode_{expected_index:03d} speaker census")
		if not _is_locked_roster_policy(audio_manifest.get("voice_context_policy")):
			failures.append(f"episode_{expected_index:03d} audio_manifest voice_context_policy is not locked_multi_speaker_roster")
		if not _is_locked_roster_policy(chunk_plan.get("voice_context_policy")):
			failures.append(f"episode_{expected_index:03d} chunk_plan voice_context_policy is not locked_multi_speaker_roster")
		locked_names = [
			(audio_manifest.get("speaker_voices") or {}).get(speaker)
			for speaker in expected_speakers
		]
		for chunk in audio_manifest.get("chunks") or []:
			if not _chunk_uses_locked_roster(chunk, locked_names):
				failures.append(f"episode_{expected_index:03d} {chunk.get('chunk_id')} speaker_names do not match locked roster")
		if audio_manifest.get("vibevoice_runner") == "resident_batch":
			report_value = audio_manifest.get("resident_batch_report")
			if not report_value:
				failures.append(f"episode_{expected_index:03d} resident_batch_report missing")
			else:
				report_path = episode_dir / str(report_value) if not Path(str(report_value)).is_absolute() else Path(str(report_value))
				resident_report = _read_json_optional(report_path)
				if not resident_report:
					failures.append(f"episode_{expected_index:03d} resident_batch_report missing")
				elif int(resident_report.get("job_count") or 0) != len(resident_report.get("jobs") or []):
					failures.append(f"episode_{expected_index:03d} resident_batch_report job_count does not match jobs length")
				final_chunk_ids = {str(chunk.get("chunk_id") or "") for chunk in audio_manifest.get("chunks") or []}
				report_job_ids = {str(job.get("job_id") or "") for job in resident_report.get("jobs") or []}
				if resident_report and not report_job_ids:
					failures.append(f"episode_{expected_index:03d} resident_batch_report has no jobs")
				elif resident_report and not report_job_ids.issubset(final_chunk_ids):
					failures.append(f"episode_{expected_index:03d} resident_batch_report contains jobs outside final audio_manifest chunks")
				elif resident_report and len(report_job_ids) != len(final_chunk_ids):
					warnings.append(f"episode_{expected_index:03d} resident_batch_report covers repaired/rerun jobs only; final chunk audio files were validated by episode final QA")
				for job in resident_report.get("jobs") or []:
					if job.get("speaker_mode") != "dialogue":
						failures.append(f"episode_{expected_index:03d} resident job {job.get('job_id')} is not dialogue mode")
					if list(job.get("speaker_names") or []) != locked_names:
						failures.append(f"episode_{expected_index:03d} resident job {job.get('job_id')} speaker_names do not match locked roster")
		if metadata.get("workflow") != "worldview-china-podcast-agent":
			failures.append(f"episode_{expected_index:03d} metadata workflow mismatch")
		if metadata.get("title") != video_title:
			failures.append(f"episode_{expected_index:03d} metadata title mismatch")
		if int(metadata.get("episode_index") or metadata.get("series_episode_index") or 0) != expected_index:
			failures.append(f"episode_{expected_index:03d} metadata episode index mismatch")
		if first_schedule is not None and _upload_report_has_user_submit_now_override(upload_report):
			warnings.append(f"episode_{expected_index:03d} scheduled publish seed was bypassed by explicit user submit-now override")
		elif first_schedule is not None:
			schedule_source = str(metadata.get("schedule_source") or episode_manifest.get("schedule_source") or episode.get("schedule_source") or "")
			if schedule_source != SERIES_BALANCED_SLOT_SCHEDULE_SOURCE:
				failures.append(
					f"episode_{expected_index:03d} schedule_source is not the balanced daily slot policy: "
					f"{schedule_source or 'missing'}"
				)
			expected_schedule = _expected_balanced_slot_schedule(first_schedule, expected_index, len(episodes), schedule_slots)
			actual_schedule = _parse_dt(metadata.get("scheduled_publish_at"))
			if actual_schedule != expected_schedule:
				failures.append(
					f"episode_{expected_index:03d} scheduled_publish_at mismatch: "
					f"actual={actual_schedule} expected={expected_schedule}"
				)
		status = str(upload_report.get("status") or "")
		if require_upload_submitted and status != "SUBMITTED":
			failures.append(f"episode_{expected_index:03d} upload report status is not SUBMITTED")
		elif not require_upload_submitted and status not in {"SUBMITTED", "BLOCKED"}:
			failures.append(f"episode_{expected_index:03d} upload report status is neither SUBMITTED nor BLOCKED")
		if status == "SUBMITTED" and not _upload_report_has_final_submit_proof(upload_report):
			failures.append(f"episode_{expected_index:03d} upload submitted without final submit proof")
		_validate_audit_monitor_status(episode_dir, expected_index, status, require_upload_submitted, failures)
	return _write_result(run_dir, failures, warnings, write_history)


def _write_result(run_dir: Path, failures: list[str], warnings: list[str], write_history: bool) -> dict[str, Any]:
	output_dir = run_dir / "12-series-final-qa"
	status = "PASS" if not failures else "FAIL"
	result = {
		"schema_version": "worldview-china-podcast-series-final-qa.v1",
		"overall_status": status,
		"failures": failures,
		"warnings": warnings,
	}
	_write_json(output_dir / "series-final-qa-result.json", result)
	lines = [
		"# Series Final QA Report",
		"",
		f"- overall_status: {status}",
		f"- failures: {len(failures)}",
		f"- warnings: {len(warnings)}",
		"",
	]
	if failures:
		lines.append("## Failures")
		lines.extend(f"- {failure}" for failure in failures)
		lines.append("")
	if warnings:
		lines.append("## Warnings")
		lines.extend(f"- {warning}" for warning in warnings)
		lines.append("")
	(output_dir / "series-final-qa-report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["12-series-final-qa"] = {
		"status": status.lower(),
		"result": str(output_dir / "series-final-qa-result.json"),
		"report": str(output_dir / "series-final-qa-report.md"),
	}
	_write_json(run_manifest_path, run_manifest)
	if status == "PASS" and write_history:
		history_path = run_dir.parent / "final-podcast-videos.json"
		history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
		series_manifest = _read_json(run_dir / "04b-series-episodes/series_manifest.json")
		entry = {
			"run_dir": str(run_dir),
			"series_manifest": str(run_dir / "04b-series-episodes/series_manifest.json"),
			"episode_count": len(series_manifest.get("episodes") or []),
			"series_qa_result": str(output_dir / "series-final-qa-result.json"),
		}
		history = [
			item for item in history
			if not (
				isinstance(item, dict)
				and item.get("run_dir") == entry["run_dir"]
				and item.get("series_manifest") == entry["series_manifest"]
			)
		]
		history.append(entry)
		history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Validate that every Worldview China podcast series episode completed in order.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--allow-blocked-upload", action="store_true", help="Accept SUBMITTED or BLOCKED upload reports. Default requires SUBMITTED for production completion.")
	parser.add_argument("--write-history", action="store_true")
	args = parser.parse_args()
	result = run_series_qa(
		args.run_dir.expanduser().resolve(),
		require_upload_submitted=not args.allow_blocked_upload,
		write_history=args.write_history,
	)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["overall_status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
