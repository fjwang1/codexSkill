from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


SKILL_DIR = Path("/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent")
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
	sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(name: str, path: Path) -> Any:
	spec = importlib.util.spec_from_file_location(name, path)
	assert spec is not None
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[name] = module
	spec.loader.exec_module(module)
	return module


series_split = _load_module("run_episode_series_split", SKILL_DIR / "scripts/run_episode_series_split.py")
series_qa = _load_module("run_series_final_qa", SKILL_DIR / "scripts/run_series_final_qa.py")
revoice = _load_module("run_source_video_revoice", SKILL_DIR / "scripts/run_source_video_revoice.py")
turn_retime = _load_module("run_turn_retime_video", SKILL_DIR / "scripts/run_turn_retime_video.py")
source_dialogue_turn_map = _load_module("build_source_dialogue_turn_map", SKILL_DIR / "scripts/build_source_dialogue_turn_map.py")
final_qa_script = _load_module("run_final_qa", SKILL_DIR / "scripts/run_final_qa.py")
voice_consistency = _load_module("run_voice_consistency_qa", SKILL_DIR / "scripts/run_voice_consistency_qa.py")
vibevoice_chunks = _load_module("run_vibevoice_chunks", SKILL_DIR / "scripts/run_vibevoice_chunks.py")
vibevoice_preflight = _load_module("run_vibevoice_preflight_audition", SKILL_DIR / "scripts/run_vibevoice_preflight_audition.py")
prepare_vibevoice_inputs = _load_module(
	"prepare_vibevoice_audio_inputs",
	Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py"),
)
audio_integrity = _load_module("run_audio_transcript_integrity_qa", SKILL_DIR / "scripts/run_audio_transcript_integrity_qa.py")
text_compliance = _load_module(
	"run_bilibili_text_compliance_review",
	SKILL_DIR / "skills/worldview-china-bilibili-text-compliance-review/scripts/run_bilibili_text_compliance_review.py",
)
selected_registry = _load_module("selected_video_registry", SKILL_DIR / "scripts/selected_video_registry.py")
publish_slot_ledger = _load_module("publish_slot_ledger", SKILL_DIR / "scripts/publish_slot_ledger.py")
source_translation = _load_module("run_source_translation", SKILL_DIR / "scripts/run_source_translation.py")
translation_semantic_qa = _load_module("run_translation_semantic_qa", SKILL_DIR / "scripts/run_translation_semantic_qa.py")
script_format = _load_module("run_podcast_script_format", SKILL_DIR / "scripts/run_podcast_script_format.py")
speaker_turn_gate = _load_module("run_speaker_turn_roster_consistency_gate", SKILL_DIR / "scripts/run_speaker_turn_roster_consistency_gate.py")
pre_tts_contract = _load_module("run_pre_tts_frozen_contract", SKILL_DIR / "scripts/run_pre_tts_frozen_contract.py")
rebuild_planner = _load_module("plan_dependency_rebuild", SKILL_DIR / "scripts/plan_dependency_rebuild.py")
source_voice_prompts = _load_module(
	"extract_source_voice_prompts",
	SKILL_DIR / "skills/worldview-china-source-voice-prompts/scripts/extract_source_voice_prompts.py",
)
speaker_census = _load_module("run_speaker_census", SKILL_DIR / "scripts/run_speaker_census.py")
source_audio_events = _load_module("run_source_audio_event_census", SKILL_DIR / "scripts/run_source_audio_event_census.py")
multimodal_spot_qa = _load_module("run_multimodal_spot_qa", SKILL_DIR / "scripts/run_multimodal_spot_qa.py")
qwen_prompts = _load_module(
	"build_qwen_vibevoice_prompts",
	SKILL_DIR / "skills/worldview-china-qwen-vibevoice-prompts/scripts/build_qwen_vibevoice_prompts.py",
)
metadata_script = _load_module(
	"generate_bilibili_publish_metadata",
	SKILL_DIR / "skills/worldview-china-bilibili-publish-metadata/scripts/generate_bilibili_publish_metadata.py",
)
title_cover_script = _load_module(
	"build_title_cover",
	SKILL_DIR / "skills/worldview-china-podcast-title-cover/scripts/build_title_cover.py",
)
cover_compositor = _load_module(
	"compose_editorial_cover",
	Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/scripts/compose_editorial_cover.py"),
)
dialogue_timeline_builder = _load_module(
	"build_dialogue_timeline_from_asr",
	Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/build_dialogue_timeline_from_asr.py"),
)
subtitle_builder = _load_module(
	"build_subtitles_from_timeline",
	Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/scripts/build_subtitles_from_timeline.py"),
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_png(path: Path, size: tuple[int, int] = (64, 36)) -> None:
	PIL_Image = pytest.importorskip("PIL.Image")
	path.parent.mkdir(parents=True, exist_ok=True)
	PIL_Image.new("RGB", size, (40, 80, 120)).save(path)


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _write_independent_review(path: Path, required_paths: dict[str, Path]) -> None:
	_write_json(path, {
		"schema_version": "worldview-china-independent-review-result.v1",
		"status": "PASS",
		"reviewed_files": [str(value) for value in required_paths.values()],
		"reviewed_file_hashes": {
			str(value.resolve()): _sha256(value)
			for value in required_paths.values()
		},
		"findings": [],
		"repair_guidance_for_parent": [],
	})


def _write_process_review(
	episode_dir: Path,
	status: str = "PASS_NO_ACTIONABLE_OPTIMIZATION",
	optimization_decision: str = "no_actionable_optimization",
) -> None:
	_write_json(episode_dir / "11d-process-review/process-review-result.json", {
		"schema_version": "worldview-china-process-review.v1",
		"status": status,
		"optimization_decision": optimization_decision,
		"longest_phase": {
			"node": "05-vibevoice-chunks",
			"duration_sec": 120.0,
			"evidence": "test fixture timing summary",
		},
		"evidence_sources": [
			str(episode_dir / "logs/progress.md"),
			str(episode_dir / "05-vibevoice-chunks/audio_report.md"),
		],
		"candidate_optimizations": [],
		"applied_changes": [],
	})


def _write_translation_reading_review(run_dir: Path, *paths: Path, status: str = "PASS") -> None:
	if not paths:
		paths = (run_dir / "03-source-translation/source_transcript.zh.json",)
	hashes = {str(path): _sha256(path) for path in paths}
	_write_json(run_dir / "03c-translation-semantic-qa/translation-reading-review-result.json", {
		"schema_version": "worldview-china-translation-reading-review.v1",
		"status": status,
		"reviewer": "test_subagent",
		"review_scope": "full_translation_read",
		"read_entire_text": True,
		"criteria": {
			"natural_chinese_oral_expression": "PASS",
			"clear_and_easy_to_understand": "PASS",
			"contextual_coherence": "PASS",
			"tts_ready_spoken_style": "PASS",
		},
		"reviewed_files": [str(path) for path in paths],
		"reviewed_file_hashes": hashes,
		"findings": [],
		"notes": "测试夹具：已完整阅读，中文口语表达清楚、通顺、好理解。",
	})


def _make_silent_wav(path: Path, duration: float) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	subprocess.run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		"anullsrc=r=24000:cl=mono",
		"-t",
		str(duration),
		"-c:a",
		"pcm_s16le",
		str(path),
	], check=True)


def _make_tone_wav(path: Path, duration: float, frequency: int = 440) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	subprocess.run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		f"sine=frequency={frequency}:sample_rate=24000:duration={duration}",
		"-ac",
		"1",
		"-c:a",
		"pcm_s16le",
		str(path),
	], check=True)


def _make_test_video(path: Path, duration: float = 1.0, size: tuple[int, int] = (320, 180)) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	width, height = size
	subprocess.run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		f"testsrc=size={width}x{height}:rate=24:duration={duration}",
		"-f",
		"lavfi",
		"-i",
		"anullsrc=r=24000:cl=mono",
		"-t",
		str(duration),
		"-c:v",
		"libx264",
		"-pix_fmt",
		"yuv420p",
		"-c:a",
		"aac",
		str(path),
	], check=True)


def _write_minimal_spot_qa_inputs(run_dir: Path, duration: float = 60.0, cue_count: int = 80) -> None:
	_make_test_video(run_dir / "video/final_video.mp4", duration=duration, size=(160, 90))
	_make_silent_wav(run_dir / "audio/final_podcast.wav", duration=duration)
	_write_json(run_dir / "video/render_manifest.json", {"subtitle_time_offset_sec": 0.0})
	_write_json(run_dir / "06d-voice-consistency-qa/voice-consistency-qa-result.json", {"overall_status": "PASS"})
	cues = []
	turns = []
	for index in range(cue_count):
		start = index * duration / cue_count
		end = min(duration, start + duration / cue_count * 0.8)
		cues.append({
			"index": index + 1,
			"start_sec": round(start, 3),
			"end_sec": round(end, 3),
			"display_text": f"第{index + 1}个锚点 2026",
		})
		turns.append({
			"turn_id": f"turn_{index + 1:04d}",
			"turn_index": index + 1,
			"speaker": "Speaker 0" if index % 2 == 0 else "Speaker 1",
			"start_sec": round(start, 3),
			"end_sec": round(end, 3),
			"text": f"第{index + 1}个锚点 2026",
		})
	_write_json(run_dir / "video/subtitle_manifest.json", {"cues": cues})
	_write_json(run_dir / "audio/dialogue_timeline.json", {"duration_sec": duration, "turns": turns})


def _make_parent_run(run_dir: Path, chapter_count: int = 4, chars_per_segment: int = 100) -> None:
	run_dir.mkdir(parents=True, exist_ok=True)
	_write_json(run_dir / "run_manifest.json", {"schema_version": "test", "nodes": {}})
	_write_json(run_dir / "02-source-capture/youtube-media/source.info.json", {
		"title": "China economy conversation",
		"channel": "Test Channel",
		"webpage_url": "https://www.youtube.com/watch?v=test",
	})
	_write_png(run_dir / "02-source-capture/source-video-frame-qa/middle.png")
	segments: list[dict[str, Any]] = []
	turns: list[dict[str, Any]] = []
	chapters: list[dict[str, Any]] = []
	for index in range(1, chapter_count + 1):
		text = f"第{index}段" + ("中" * (chars_per_segment - len(f"第{index}段")))
		segments.append({
			"segment_index": index,
			"source_start": f"00:{index - 1:02d}:00",
			"source_end": f"00:{index:02d}:00",
			"source_text": f"source {index}",
			"speaker": "Speaker 0" if index % 2 else "Speaker 1",
			"zh_text": text,
		})
		turns.append({
			"turn_index": index,
			"speaker": "Speaker 0" if index % 2 else "Speaker 1",
			"text": text,
			"source_segment_index": index,
			"char_count": len(text),
		})
		chapters.append({
			"chapter_id": f"chapter_{index:03d}",
			"title": f"中国经济主题{index}",
			"source_start": f"00:{index - 1:02d}:00",
			"source_end": f"00:{index:02d}:00",
			"segment_start": index,
			"segment_end": index,
			"estimated_zh_chars": len(text),
		})
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"schema_version": "test-translation",
		"content_coverage": "full_translation",
		"segments": segments,
	})
	_write_json(run_dir / "03-source-translation/chapter_segments.json", {
		"schema_version": "test-chapters",
		"chapters": chapters,
	})
	_write_json(run_dir / "04-podcast-script/script_turns.json", {
		"schema_version": "worldview-china-script-turns.v1",
		"content_coverage": "full_translation",
		"turns": turns,
	})
	(run_dir / "04-podcast-script").mkdir(parents=True, exist_ok=True)
	(run_dir / "04-podcast-script/podcast_script.md").write_text(
		"\n".join(f"{turn['speaker']}: {turn['text']}" for turn in turns) + "\n",
		encoding="utf-8",
	)


def test_bilibili_text_compliance_records_registry_and_file_hashes(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	run_dir.mkdir(parents=True)
	script_path = run_dir / "podcast_script.md"
	title_path = run_dir / "video_title.txt"
	script_path.write_text("Speaker 0: 这一集讨论中国经济和国际市场的变化。\n", encoding="utf-8")
	title_path.write_text("美国学者：中国经济还有哪些韧性\n", encoding="utf-8")

	result = text_compliance.run_review(run_dir=run_dir, stage="test")

	assert result["status"] == "PASS"
	assert result["risk_registry"]["load_status"] == "loaded"
	assert result["risk_registry"]["deterministic_rule_ids_missing_from_registry"] == []
	assert result["reviewed_file_hashes"][str(script_path.resolve())] == _sha256(script_path)
	assert result["reviewed_file_hashes"][str(title_path.resolve())] == _sha256(title_path)


def test_multimodal_spot_qa_sample_plan_covers_full_timeline(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_minimal_spot_qa_inputs(run_dir, duration=60.0, cue_count=80)

	package = multimodal_spot_qa._build_sample_plan(run_dir, min_samples=20, max_samples=24)
	times = [float(sample["sample_time_sec"]) for sample in package["samples"]]

	assert len(times) >= 20
	assert min(times) <= 1.0
	assert max(times) >= 54.0
	assert any(25.0 <= value <= 35.0 for value in times)
	assert package["policy"]["sample_strategy"] == "opening_ending_global_quantiles_speaker_switches_semantic_anchors"


def test_multimodal_spot_qa_uses_subtitle_source_turn_at_overlap(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_make_test_video(run_dir / "video/final_video.mp4", duration=12.0, size=(160, 90))
	_make_silent_wav(run_dir / "audio/final_podcast.wav", duration=12.0)
	_write_json(run_dir / "video/render_manifest.json", {"subtitle_time_offset_sec": 0.0})
	_write_json(run_dir / "06d-voice-consistency-qa/voice-consistency-qa-result.json", {"overall_status": "PASS"})
	_write_json(run_dir / "audio/dialogue_timeline.json", {
		"duration_sec": 12.0,
		"turns": [
			{
				"turn_id": "turn_0001",
				"turn_index": 1,
				"speaker": "Speaker 0",
				"start_sec": 0.0,
				"end_sec": 5.2,
				"text": "上一位说话人的回答",
			},
			{
				"turn_id": "turn_0002",
				"turn_index": 2,
				"speaker": "Speaker 1",
				"start_sec": 5.0,
				"end_sec": 8.0,
				"text": "但这不是一把双刃剑吗？",
			},
			{
				"turn_id": "turn_0003",
				"turn_index": 3,
				"speaker": "Speaker 0",
				"start_sec": 8.2,
				"end_sec": 11.5,
				"text": "下一位说话人的回答",
			},
		],
	})
	_write_json(run_dir / "video/subtitle_manifest.json", {
		"cues": [
			{
				"index": 1,
				"speaker": "Speaker 0",
				"source_turn_id": "turn_0001",
				"source_turn_index": 1,
				"start_sec": 0.0,
				"end_sec": 4.9,
				"display_text": "上一位说话人的回答 2026",
			},
			{
				"index": 2,
				"speaker": "Speaker 1",
				"source_turn_id": "turn_0002",
				"source_turn_index": 2,
				"start_sec": 5.0,
				"end_sec": 7.5,
				"display_text": "但这不是一把双刃剑吗？",
			},
			{
				"index": 3,
				"speaker": "Speaker 0",
				"source_turn_id": "turn_0003",
				"source_turn_index": 3,
				"start_sec": 8.2,
				"end_sec": 11.5,
				"display_text": "下一位说话人的回答 2026",
			},
		],
	})

	package = multimodal_spot_qa._build_sample_plan(run_dir, min_samples=3, max_samples=3)
	overlap_sample = next(sample for sample in package["samples"] if sample["cue_index"] == 2)

	assert overlap_sample["speaker"] == "Speaker 1"
	assert overlap_sample["turn_index"] == 2
	assert overlap_sample["turn_text"] == "但这不是一把双刃剑吗？"
	assert overlap_sample["reason"] == "speaker_switch"


def test_final_qa_rejects_stale_text_compliance_hashes(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	script_path = run_dir / "podcast_script.md"
	script_path.parent.mkdir(parents=True)
	script_path.write_text("Speaker 0: 第一版安全文本。\n", encoding="utf-8")
	review = {
		"reviewed_file_hashes": {
			str(script_path.resolve()): _sha256(script_path),
		},
	}
	script_path.write_text("Speaker 0: 第二版视频修复后的文本。\n", encoding="utf-8")

	failures: list[str] = []
	final_qa_script._require_reviewed_file_hashes_current(
		review,
		{"podcast_script": script_path},
		failures,
		"Bilibili text compliance review",
	)

	assert any("stale" in failure for failure in failures)


def test_final_qa_requires_independent_review_result(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	script_path = run_dir / "podcast_script.md"
	script_path.parent.mkdir(parents=True)
	script_path.write_text("Speaker 0: 当前安全文本。\n", encoding="utf-8")

	failures: list[str] = []
	final_qa_script._require_independent_review_pass(
		{},
		run_dir / "04c-bilibili-text-compliance/text-compliance-review-result.json",
		{"podcast_script": script_path},
		failures,
		"Bilibili text compliance review",
	)
	assert any("independent review result is missing" in failure for failure in failures)

	_write_independent_review(
		run_dir / "04c-bilibili-text-compliance/independent-review-result.json",
		{"podcast_script": script_path},
	)
	script_path.write_text("Speaker 0: 审核后被改动的文本。\n", encoding="utf-8")
	failures = []
	final_qa_script._require_independent_review_pass(
		{},
		run_dir / "04c-bilibili-text-compliance/text-compliance-review-result.json",
		{"podcast_script": script_path},
		failures,
		"Bilibili text compliance review",
	)
	assert any("stale" in failure for failure in failures)


def test_series_final_qa_requires_allowed_audit_monitor_status(tmp_path: Path) -> None:
	episode_dir = tmp_path / "episode_001"
	failures: list[str] = []
	series_qa._validate_audit_monitor_status(
		episode_dir,
		1,
		upload_status="SUBMITTED",
		require_upload_submitted=True,
		failures=failures,
	)
	assert any("audit monitor report is missing" in failure for failure in failures)

	_write_json(episode_dir / "11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json", {
		"status": "RETURNED_NEEDS_REPAIR",
	})
	failures = []
	series_qa._validate_audit_monitor_status(
		episode_dir,
		1,
		upload_status="SUBMITTED",
		require_upload_submitted=True,
		failures=failures,
	)
	assert any("audit monitor status is not allowed" in failure for failure in failures)

	_write_json(episode_dir / "11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json", {
		"status": "REVIEW_PENDING_AFTER_MAX_CHECKS",
	})
	failures = []
	series_qa._validate_audit_monitor_status(
		episode_dir,
		1,
		upload_status="SUBMITTED",
		require_upload_submitted=True,
		failures=failures,
	)
	assert failures == []


def test_series_final_qa_requires_post_audit_process_review(tmp_path: Path) -> None:
	episode_dir = tmp_path / "episode_001"
	failures: list[str] = []
	series_qa._validate_process_review_status(
		episode_dir,
		1,
		upload_status="SUBMITTED",
		require_upload_submitted=True,
		failures=failures,
	)
	assert any("process review report is missing" in failure for failure in failures)

	_write_json(episode_dir / "11d-process-review/process-review-result.json", {
		"status": "NEEDS_REVIEW",
		"optimization_decision": "missing",
	})
	failures = []
	series_qa._validate_process_review_status(
		episode_dir,
		1,
		upload_status="SUBMITTED",
		require_upload_submitted=True,
		failures=failures,
	)
	assert any("process review status is not allowed" in failure for failure in failures)

	_write_process_review(episode_dir)
	failures = []
	series_qa._validate_process_review_status(
		episode_dir,
		1,
		upload_status="SUBMITTED",
		require_upload_submitted=True,
		failures=failures,
	)
	assert failures == []


def test_episode_series_split_creates_ordered_episode_runs_with_balanced_daily_slot_schedule(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_make_parent_run(run_dir, chapter_count=6)
	manifest = series_split.split_series(
		run_dir=run_dir,
		series_title_prefix="嘉宾观察",
		first_scheduled_publish_at="2026-06-24 11:00",
		scheduled_publish_timezone="Asia/Shanghai",
		episode_title_template="{series_title}·{episode_order_marker}：{subtitle}",
		episode_order_marker_template="第{episode_index}集",
		chars_per_minute_override=100.0,
		calibration_audio_manifest=None,
		target_minutes_min=1.0,
		target_minutes_max=2.0,
		target_minutes_ideal=1.5,
		force=True,
	)
	assert manifest["episode_count"] == 3
	assert manifest["serial_execution_required"] is True
	assert manifest["parallel_execution_allowed"] is False
	assert manifest["bilibili_upload_overlap_allowed"] is True
	assert manifest["final_publish_after_all_uploads"] is True
	assert manifest["bilibili_schedule_policy"] == "balanced_daily_slots_ordered"
	assert manifest["bilibili_schedule_source"] == "series_daily_11_17_balanced_ordered_slots"
	assert manifest["bilibili_schedule_slots"] == ["11:00", "17:00"]
	assert manifest["episode_title_template"] == "{series_title}·{episode_order_marker}：{subtitle}"
	assert manifest["episode_order_marker_template"] == "第{episode_index}集"
	assert manifest["target_chars_min"] == 100
	assert manifest["target_chars_max"] == 200
	first = manifest["episodes"][0]
	second = manifest["episodes"][1]
	third = manifest["episodes"][2]
	assert first["video_title"] == "嘉宾观察·第1集：中国经济主题1与中国经济主题2"
	assert second["video_title"] == "嘉宾观察·第2集：中国经济主题3与中国经济主题4"
	assert third["video_title"] == "嘉宾观察·第3集：中国经济主题5与中国经济主题6"
	assert first["scheduled_publish_at"] == "2026-06-24T11:00:00+08:00"
	assert second["scheduled_publish_at"] == "2026-06-24T11:00:00+08:00"
	assert third["scheduled_publish_at"] == "2026-06-24T17:00:00+08:00"
	for episode in manifest["episodes"]:
		episode_dir = Path(episode["episode_run_dir"])
		episode_manifest = _read_json(episode_dir / "episode_manifest.json")
		assert episode_manifest["serial_execution_required"] is True
		assert episode_manifest["bilibili_upload_overlap_allowed"] is True
		assert episode_manifest["final_publish_after_all_uploads"] is True
		assert episode_manifest["episode_order_marker_template"] == manifest["episode_order_marker_template"]
		assert (episode_dir / "04-podcast-script/podcast_script.md").exists()
		metadata_seed = _read_json(episode_dir / "bilibili_upload_metadata.json")
		assert metadata_seed["scheduled_publish_at"] == episode["scheduled_publish_at"]
		assert metadata_seed["schedule_source"] == "series_daily_11_17_balanced_ordered_slots"


def test_publish_slot_ledger_plans_empty_daily_slots(tmp_path: Path) -> None:
	root_dir = tmp_path / "worldview-root"
	root_dir.mkdir()
	plan = publish_slot_ledger.plan_slots(
		root_dir=root_dir,
		target_date="2026-06-27",
		slots=("11:00", "17:00"),
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 26, 9, 0, tzinfo=timezone.utc),
	)
	assert plan["should_run"] is True
	assert plan["next_slot"] == "11:00"
	assert [slot["slot"] for slot in plan["missing_slots"]] == ["11:00", "17:00"]
	assert plan["satisfied_slots"] == []


def test_publish_slot_ledger_reserves_one_slot_without_filling_the_day(tmp_path: Path) -> None:
	root_dir = tmp_path / "worldview-root"
	root_dir.mkdir()
	reservation = publish_slot_ledger.reserve_slots(
		root_dir=root_dir,
		target_date="2026-06-27",
		slots=("11:00",),
		run_dir=tmp_path / "run-1",
		run_id="run-1",
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 26, 9, 0, tzinfo=timezone.utc),
	)
	assert reservation["reserved_slots"][0]["slot"] == "11:00"
	plan = publish_slot_ledger.plan_slots(
		root_dir=root_dir,
		target_date="2026-06-27",
		slots=("11:00", "17:00"),
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 26, 10, 0, tzinfo=timezone.utc),
	)
	assert [slot["slot"] for slot in plan["satisfied_slots"]] == ["11:00"]
	assert [slot["slot"] for slot in plan["missing_slots"]] == ["17:00"]
	assert plan["should_run"] is True
	assert plan["next_slot"] == "17:00"


def test_publish_slot_ledger_commit_run_fills_slots_from_submitted_series(tmp_path: Path) -> None:
	root_dir = tmp_path / "worldview-root"
	root_dir.mkdir()
	run_dir = root_dir / "20260626_1"
	episode_dirs = [run_dir / "04b-series-episodes/episode_001", run_dir / "04b-series-episodes/episode_002"]
	for index, (episode_dir, hour) in enumerate(zip(episode_dirs, (11, 17), strict=True), start=1):
		_write_json(episode_dir / "bilibili_upload_metadata.json", {
			"title": f"世界眼中的中国·第{index}集：测试标题",
			"scheduled_publish_at": f"2026-06-27T{hour:02d}:00:00+08:00",
			"scheduled_publish_timezone": "Asia/Shanghai",
			"video_path": str(episode_dir / "video/final_video.mp4"),
		})
		_write_json(episode_dir / "bilibili_upload_draft_report.json", {
			"status": "SUBMITTED",
			"final_submit_clicked": True,
		})
		_write_json(episode_dir / "11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json", {
			"status": "APPROVED",
		})
	_write_json(run_dir / "04b-series-episodes/series_manifest.json", {
		"episodes": [{"episode_run_dir": str(episode_dir)} for episode_dir in episode_dirs],
	})
	commit = publish_slot_ledger.commit_run(
		root_dir=root_dir,
		run_dir=run_dir,
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
	)
	assert [slot["slot"] for slot in commit["committed_slots"]] == ["11:00", "17:00"]
	plan = publish_slot_ledger.plan_slots(
		root_dir=root_dir,
		target_date="2026-06-27",
		slots=("11:00", "17:00"),
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 26, 12, 30, tzinfo=timezone.utc),
	)
	assert plan["should_run"] is False
	assert [slot["status"] for slot in plan["satisfied_slots"]] == ["APPROVED", "APPROVED"]
	assert plan["missing_slots"] == []


def test_publish_slot_ledger_ignores_stale_reservation_and_returned_submission(tmp_path: Path) -> None:
	root_dir = tmp_path / "worldview-root"
	root_dir.mkdir()
	publish_slot_ledger.reserve_slots(
		root_dir=root_dir,
		target_date="2026-06-27",
		slots=("11:00",),
		run_dir=tmp_path / "old-run",
		run_id="old-run",
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 25, 8, 0, tzinfo=timezone.utc),
	)
	run_dir = root_dir / "20260626_2"
	_write_json(run_dir / "bilibili_upload_metadata.json", {
		"title": "世界眼中的中国：退回样例",
		"scheduled_publish_at": "2026-06-27T17:00:00+08:00",
		"scheduled_publish_timezone": "Asia/Shanghai",
	})
	_write_json(run_dir / "bilibili_upload_draft_report.json", {"status": "SUBMITTED"})
	_write_json(run_dir / "11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json", {
		"status": "RETURNED_NEEDS_REPAIR",
	})
	publish_slot_ledger.commit_run(
		root_dir=root_dir,
		run_dir=run_dir,
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
	)
	plan = publish_slot_ledger.plan_slots(
		root_dir=root_dir,
		target_date="2026-06-27",
		slots=("11:00", "17:00"),
		timezone_name="Asia/Shanghai",
		now=datetime(2026, 6, 26, 12, 30, tzinfo=timezone.utc),
		reservation_ttl_hours=18,
	)
	assert [slot["slot"] for slot in plan["missing_slots"]] == ["11:00", "17:00"]
	assert plan["slot_statuses"]["2026-06-27T11:00"]["stale_reservation"] is True
	assert plan["slot_statuses"]["2026-06-27T17:00"]["status"] == "RETURNED_NEEDS_REPAIR"


def test_episode_series_split_materializes_source_episode_video_when_source_exists(tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	run_dir = tmp_path / "run"
	_make_parent_run(run_dir, chapter_count=4, chars_per_segment=100)
	_make_test_video(run_dir / "02-source-capture/youtube-media/source.mp4", duration=4.0)
	translation = _read_json(run_dir / "03-source-translation/source_transcript.zh.json")
	chapters = _read_json(run_dir / "03-source-translation/chapter_segments.json")
	for index, segment in enumerate(translation["segments"], start=1):
		segment["source_start"] = f"00:00:0{index - 1}"
		segment["source_end"] = f"00:00:0{index}"
	for index, chapter in enumerate(chapters["chapters"], start=1):
		chapter["source_start"] = f"00:00:0{index - 1}"
		chapter["source_end"] = f"00:00:0{index}"
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", translation)
	_write_json(run_dir / "03-source-translation/chapter_segments.json", chapters)
	manifest = series_split.split_series(
		run_dir=run_dir,
		series_title_prefix="嘉宾观察",
		first_scheduled_publish_at=None,
		scheduled_publish_timezone="Asia/Shanghai",
		episode_title_template="{series_title}·{episode_order_marker}：{subtitle}",
		episode_order_marker_template="第{episode_index}集",
		chars_per_minute_override=100.0,
		calibration_audio_manifest=None,
		target_minutes_min=1.0,
		target_minutes_max=2.0,
		target_minutes_ideal=1.5,
		force=True,
	)
	assert manifest["episode_count"] == 2
	first_episode = Path(manifest["episodes"][0]["episode_run_dir"])
	episode_manifest = _read_json(first_episode / "episode_manifest.json")
	source_segment = Path(episode_manifest["source_episode_video"])
	segment_manifest = _read_json(first_episode / "04b-source-video-segment/source_episode_manifest.json")
	assert source_segment.exists()
	assert segment_manifest["status"] == "pass"
	assert 1.5 <= segment_manifest["actual_duration_sec"] <= 2.2


def test_title_cover_series_mode_uses_indexed_video_title_and_unindexed_cover_title(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "02-source-capture/youtube-media/source.info.json", {"title": "China resilience"})
	_write_png(run_dir / "02-source-capture/source-video-frame-qa/middle.png")
	_write_png(run_dir / "cover/cover_4k.png")
	manifest = title_cover_script.build_title_cover(
		run_dir=run_dir,
		translated_title_core="中国的经济韧性",
		source_identity_label="嘉宾观察",
		identity_basis="test identity basis",
		frame=None,
		frame_key="auto",
		source_time_sec=None,
		highlight_texts=["嘉宾观察", "中国"],
		episode_index=2,
		episode_title_template="{series_title}·{episode_order_marker}：{subtitle}",
		episode_order_marker_template="第{episode_index}集",
		cover_include_episode_index=False,
		force=False,
	)
	cover_title = _read_json(run_dir / "cover/cover_title.json")
	assert (run_dir / "video_title.txt").read_text(encoding="utf-8").strip() == "嘉宾观察·第2集：中国的经济韧性"
	assert cover_title["title_text"] == "嘉宾观察：中国的经济韧性"
	assert cover_title["video_title_text"] == "嘉宾观察·第2集：中国的经济韧性"
	assert cover_title["cover_title_omits_episode_index"] is True
	assert cover_title["title_source"] == "podcast_source_identity_plus_platform_native_hook"
	assert cover_title["attractive_title_policy"]["status"] == "PASS"
	assert manifest["title_policy"] == "series_episode_indexed_video_title_plus_unindexed_cover_title"


def test_center_cover_prefers_large_two_lines_when_they_fit() -> None:
	PIL_Image = pytest.importorskip("PIL.Image")
	PIL_ImageDraw = pytest.importorskip("PIL.ImageDraw")
	draw = PIL_ImageDraw.Draw(PIL_Image.new("RGB", cover_compositor.CANVAS, (0, 0, 0)))
	source_lines = ["嘉宾观察：", "中国经济"]
	lines, policy = cover_compositor.choose_center_title_lines(
		draw,
		source_lines,
		["嘉宾观察", "中国经济"],
		cover_compositor.DEFAULT_FONT,
		cover_compositor.CENTER_TITLE_MAX_WIDTH,
	)
	assert len(lines) == 2
	assert policy == "center_large_two_line_fit"
	assert cover_compositor._lines_fit_at_font_size(
		draw,
		lines,
		["嘉宾观察", "中国经济"],
		cover_compositor.DEFAULT_FONT,
		cover_compositor.CENTER_TITLE_TWO_LINE_LARGE_FONT_SIZE,
		cover_compositor.CENTER_TITLE_MAX_WIDTH,
	)


def test_center_cover_uses_large_three_lines_before_shrinking_font() -> None:
	PIL_Image = pytest.importorskip("PIL.Image")
	PIL_ImageDraw = pytest.importorskip("PIL.ImageDraw")
	draw = PIL_ImageDraw.Draw(PIL_Image.new("RGB", cover_compositor.CANVAS, (0, 0, 0)))
	source_lines = ["哥大经济学家：", "中国冲击2.0先打到德国工业"]
	highlight_texts = ["哥大经济学家", "德国工业"]
	assert not cover_compositor._lines_fit_at_font_size(
		draw,
		source_lines,
		highlight_texts,
		cover_compositor.DEFAULT_FONT,
		cover_compositor.CENTER_TITLE_TWO_LINE_LARGE_FONT_SIZE,
		cover_compositor.CENTER_TITLE_MAX_WIDTH,
	)
	lines, policy = cover_compositor.choose_center_title_lines(
		draw,
		source_lines,
		highlight_texts,
		cover_compositor.DEFAULT_FONT,
		cover_compositor.CENTER_TITLE_MAX_WIDTH,
	)
	assert len(lines) == 3
	assert policy == "center_large_three_line_after_large_two_line_failed"
	assert cover_compositor._lines_fit_at_font_size(
		draw,
		lines,
		highlight_texts,
		cover_compositor.DEFAULT_FONT,
		cover_compositor.CENTER_TITLE_THREE_LINE_LARGE_FONT_SIZE,
		cover_compositor.CENTER_TITLE_MAX_WIDTH,
	)


def test_title_cover_rejects_internal_column_prefix_and_generic_core(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "02-source-capture/youtube-media/source.info.json", {"title": "The Day After: America, China and a Changed Middle East"})
	_write_png(run_dir / "02-source-capture/source-video-frame-qa/middle.png")
	with pytest.raises(AssertionError, match="not the channel/series/topic label"):
		title_cover_script.build_title_cover(
			run_dir=run_dir,
			translated_title_core="中东停火与中国经济足迹",
			source_identity_label="世界眼中的中国",
			identity_basis=None,
			frame=None,
			frame_key="auto",
			source_time_sec=None,
			highlight_texts=None,
			episode_index=None,
			episode_title_template="{series_title}：{subtitle}",
			episode_order_marker_template="",
			cover_include_episode_index=False,
			force=False,
		)
	with pytest.raises(AssertionError, match="too generic"):
		title_cover_script.build_title_cover(
			run_dir=run_dir,
			translated_title_core="中东停火与中国经济足迹",
			source_identity_label="中东中国问题专家",
			identity_basis="test identity basis",
			frame=None,
			frame_key="auto",
			source_time_sec=None,
			highlight_texts=None,
			episode_index=None,
			episode_title_template="{series_title}：{subtitle}",
			episode_order_marker_template="",
			cover_include_episode_index=False,
			force=False,
		)
	with pytest.raises(AssertionError, match="too generic"):
		title_cover_script.build_title_cover(
			run_dir=run_dir,
			translated_title_core="中国在中东做大生意，却不想接美国的安全班",
			source_identity_label="中国中东问题专家",
			identity_basis="test identity basis",
			frame=None,
			frame_key="auto",
			source_time_sec=None,
			highlight_texts=None,
			episode_index=None,
			episode_title_template="{series_title}：{subtitle}",
			episode_order_marker_template="",
			cover_include_episode_index=False,
			force=False,
		)


def test_title_cover_allows_short_generic_identity_fallback(tmp_path: Path) -> None:
	for label in ("中东专家", "中国问题专家"):
		run_dir = tmp_path / label
		_write_json(run_dir / "02-source-capture/youtube-media/source.info.json", {"title": "The Day After: America, China and a Changed Middle East"})
		_write_png(run_dir / "02-source-capture/source-video-frame-qa/middle.png")
		_write_png(run_dir / "cover/cover_4k.png")
		manifest = title_cover_script.build_title_cover(
			run_dir=run_dir,
			translated_title_core="中国在中东做大生意，却不想接美国的班？",
			source_identity_label=label,
			identity_basis="Source supports this domain label; no brighter concise public title is available for the Bilibili prefix.",
			frame=None,
			frame_key="auto",
			source_time_sec=None,
			highlight_texts=[label, "做大生意"],
			episode_index=None,
			episode_title_template="{series_title}：{subtitle}",
			episode_order_marker_template="",
			cover_include_episode_index=False,
			force=False,
		)
		cover_title = _read_json(run_dir / "cover/cover_title.json")
		assert (run_dir / "video_title.txt").read_text(encoding="utf-8").strip() == f"{label}：中国在中东做大生意，却不想接美国的班？"
		assert cover_title["identity_label_policy"]["type"] == "fallback_generic"
		assert cover_title["attractive_title_policy"]["identity_label_policy"]["type"] == "fallback_generic"
		assert manifest["identity_label_policy"]["type"] == "fallback_generic"


def test_title_cover_generic_identity_fallback_requires_basis(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "02-source-capture/youtube-media/source.info.json", {"title": "The Day After: America, China and a Changed Middle East"})
	_write_png(run_dir / "02-source-capture/source-video-frame-qa/middle.png")
	with pytest.raises(AssertionError, match="require identity_basis"):
		title_cover_script.build_title_cover(
			run_dir=run_dir,
			translated_title_core="中国在中东做大生意，却不想接美国的班？",
			source_identity_label="中东专家",
			identity_basis=None,
			frame=None,
			frame_key="auto",
			source_time_sec=None,
			highlight_texts=None,
			episode_index=None,
			episode_title_template="{series_title}：{subtitle}",
			episode_order_marker_template="",
			cover_include_episode_index=False,
			force=False,
		)


def test_title_cover_respects_single_episode_empty_order_marker(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	title = "旅居中东20年学者：中国在中东做大生意，却不想接美国的安全班"
	_write_json(run_dir / "02-source-capture/youtube-media/source.info.json", {"title": "The Day After"})
	_write_json(run_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"episode_index": 1,
		"episode_count": 1,
		"episode_order_marker": "",
		"episode_title_template": "{series_title}：{subtitle}",
		"episode_order_marker_template": "",
		"video_title": title,
		"cover_title": title,
	})
	_write_png(run_dir / "02-source-capture/source-video-frame-qa/middle.png")
	_write_png(run_dir / "cover/cover_4k.png")
	manifest = title_cover_script.build_title_cover(
		run_dir=run_dir,
		translated_title_core="中国在中东做大生意，却不想接美国的安全班",
		source_identity_label="旅居中东20年学者",
		identity_basis="test identity basis",
		frame=None,
		frame_key="auto",
		source_time_sec=None,
		highlight_texts=["旅居中东20年学者", "安全班"],
		episode_index=1,
		episode_title_template="{series_title}：{subtitle}",
		episode_order_marker_template="",
		cover_include_episode_index=False,
		force=False,
	)
	cover_title = _read_json(run_dir / "cover/cover_title.json")
	assert (run_dir / "video_title.txt").read_text(encoding="utf-8").strip() == title
	assert cover_title["episode_order_marker"] == ""
	assert manifest["episode_order_marker"] == ""


def test_bilibili_metadata_preserves_series_schedule_and_episode_fields(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	(run_dir / "video").mkdir(parents=True)
	(run_dir / "cover").mkdir(parents=True)
	(run_dir / "video/final_video.mp4").write_bytes(b"fake")
	(run_dir / "cover/cover_4k.png").write_bytes(b"fake")
	(run_dir / "video_title.txt").write_text("嘉宾观察·第1集：中国的经济韧性\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {
		"title_text": "嘉宾观察：中国的经济韧性",
		"video_title_text": "嘉宾观察·第1集：中国的经济韧性",
		"source_identity_label": "嘉宾观察",
		"translated_title_core": "中国的经济韧性",
	})
	_write_json(run_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"episode_index": 1,
		"episode_count": 2,
		"episode_label": "一",
		"episode_order_marker": "第1集",
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
		"series_title_prefix": "嘉宾观察",
		"episode_subtitle": "中国的经济韧性",
		"video_title": "嘉宾观察·第1集：中国的经济韧性",
	})
	(run_dir / "podcast_script.md").write_text(
		"Speaker 0: 中国经济韧性不是一句口号，它关系到消费、供应链和外企在中国市场的长期判断。\n",
		encoding="utf-8",
	)
	_write_json(run_dir / "bilibili_upload_metadata.json", {
		"scheduled_publish_at": "2026-06-24T11:00:00+08:00",
		"scheduled_publish_timezone": "Asia/Shanghai",
		"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		"series_schedule_policy": "balanced_daily_slots_ordered",
		"series_schedule_slots": ["11:00", "17:00"],
		"series_schedule_base_date": "2026-06-24",
		"series_schedule_slot_index": 1,
		"series_schedule_slot_time": "11:00",
		"series_schedule_slot_episode_count": 1,
		"series_schedule_position_in_slot": 1,
		"series_episode_index": 1,
		"series_episode_count": 2,
	})
	metadata, report, _ = metadata_script.generate_metadata(
		run_dir,
		run_dir / "bilibili_upload_metadata.json",
		run_dir / "10-bilibili-publish/publish_metadata_report.json",
	)
	assert metadata["scheduled_publish_at"] == "2026-06-24T11:00:00+08:00"
	assert metadata["episode_index"] == 1
	assert metadata["episode_count"] == 2
	assert metadata["cover_title_text"] == "嘉宾观察：中国的经济韧性"
	assert "中国的经济韧性" in metadata["description"]
	assert "中文配音版本" not in metadata["description"]
	assert "保留原视频画面" not in metadata["description"]
	assert report["series_episode"] is True
	assert report["scheduled_publish_at"] == "2026-06-24T11:00:00+08:00"


def test_bilibili_metadata_description_strips_markdown_headings(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	(run_dir / "video").mkdir(parents=True)
	(run_dir / "cover").mkdir(parents=True)
	(run_dir / "video/final_video.mp4").write_bytes(b"fake")
	(run_dir / "cover/cover_4k.png").write_bytes(b"fake")
	(run_dir / "video_title.txt").write_text("亚当·图兹：中国冲击2.0正在打到德国身上\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {
		"title_text": "亚当·图兹：中国冲击2.0正在打到德国身上",
		"video_title_text": "亚当·图兹：中国冲击2.0正在打到德国身上",
		"source_identity_label": "亚当·图兹",
		"translated_title_core": "中国冲击2.0正在打到德国身上",
	})
	(run_dir / "podcast_script.md").write_text(
		"---\nschema_version: worldview-china-podcast-script.v1\n---\n\n"
		"## 正文\n\n"
		"Speaker 0: 大家好，欢迎收听节目。今天我们从夏季达沃斯现场谈起，讨论中国制造、德国工业和全球贸易秩序的变化。\n",
		encoding="utf-8",
	)
	metadata, _, _ = metadata_script.generate_metadata(
		run_dir,
		run_dir / "bilibili_upload_metadata.json",
		run_dir / "10-bilibili-publish/publish_metadata_report.json",
	)
	assert "正文" not in metadata["description"]
	assert "大家好" not in metadata["description"]
	assert "欢迎收听" not in metadata["description"]
	assert "夏季达沃斯" in metadata["description"]


def test_bilibili_metadata_description_rejects_first_person_fallback_sentence(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	(run_dir / "video").mkdir(parents=True)
	(run_dir / "cover").mkdir(parents=True)
	(run_dir / "video/final_video.mp4").write_bytes(b"fake")
	(run_dir / "cover/cover_4k.png").write_bytes(b"fake")
	(run_dir / "video_title.txt").write_text("印度视角下的中美竞争·第2集：资源外交与2047大国路线\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {
		"title_text": "印度视角下的中美竞争：资源外交与2047大国路线",
		"video_title_text": "印度视角下的中美竞争·第2集：资源外交与2047大国路线",
		"source_identity_label": "印度视角下的中美竞争",
		"translated_title_core": "资源外交与2047大国路线",
	})
	(run_dir / "podcast_script.md").write_text(
		"Speaker 0: 看，我认为未来最重要、但在我们想象中很边缘的伙伴之一，就是印度尼西亚。\n"
		"Speaker 0: 中亚仍然是一片几乎没有充分开发的区域，牵动资源外交、供应链和全球南方的长期竞争。\n",
		encoding="utf-8",
	)
	metadata, _, _ = metadata_script.generate_metadata(
		run_dir,
		run_dir / "bilibili_upload_metadata.json",
		run_dir / "10-bilibili-publish/publish_metadata_report.json",
	)
	assert "看，我认为" not in metadata["description"]
	assert "我认为" not in metadata["description"]
	assert "资源外交与2047大国路线" in metadata["description"]


def test_bilibili_metadata_inherits_series_schedule_from_episode_manifest_without_seed(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	(run_dir / "video").mkdir(parents=True)
	(run_dir / "cover").mkdir(parents=True)
	(run_dir / "video/final_video.mp4").write_bytes(b"fake")
	(run_dir / "cover/cover_4k.png").write_bytes(b"fake")
	(run_dir / "video_title.txt").write_text("嘉宾观察·第2集：外企为什么仍看重中国市场\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {
		"title_text": "嘉宾观察：外企为什么仍看重中国市场",
		"video_title_text": "嘉宾观察·第2集：外企为什么仍看重中国市场",
		"source_identity_label": "嘉宾观察",
		"translated_title_core": "外企为什么仍看重中国市场",
	})
	_write_json(run_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"episode_index": 2,
		"episode_count": 2,
		"episode_label": "二",
		"episode_order_marker": "第2集",
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
		"series_title_prefix": "嘉宾观察",
		"episode_subtitle": "外企为什么仍看重中国市场",
		"video_title": "嘉宾观察·第2集：外企为什么仍看重中国市场",
		"scheduled_publish_at": "2026-06-24T17:00:00+08:00",
		"scheduled_publish_timezone": "Asia/Shanghai",
		"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		"series_schedule_policy": "balanced_daily_slots_ordered",
		"series_schedule_slots": ["11:00", "17:00"],
		"series_schedule_base_date": "2026-06-24",
		"series_schedule_slot_index": 2,
		"series_schedule_slot_time": "17:00",
		"series_schedule_slot_episode_count": 1,
		"series_schedule_position_in_slot": 1,
	})
	(run_dir / "podcast_script.md").write_text(
		"Speaker 0: 外企仍然看重中国市场，是因为供应链、消费和本地经营仍然有现实价值。\n",
		encoding="utf-8",
	)
	metadata, report, _ = metadata_script.generate_metadata(
		run_dir,
		run_dir / "bilibili_upload_metadata.json",
		run_dir / "10-bilibili-publish/publish_metadata_report.json",
	)
	assert metadata["scheduled_publish_at"] == "2026-06-24T17:00:00+08:00"
	assert metadata["scheduled_publish_timezone"] == "Asia/Shanghai"
	assert metadata["schedule_source"] == "series_daily_11_17_balanced_ordered_slots"
	assert metadata["series_episode_index"] == 2
	assert metadata["series_episode_count"] == 2
	assert "外企仍然看重中国市场" in metadata["description"]
	assert "替换为中文对话音频" not in metadata["description"]
	assert report["scheduled_publish_at"] == "2026-06-24T17:00:00+08:00"


def test_bilibili_metadata_tag_policy_uses_six_to_ten_tags() -> None:
	assert metadata_script.MIN_BILIBILI_TAGS == 6
	assert metadata_script.MAX_BILIBILI_TAGS == 10


def test_revoice_uses_episode_manifest_as_formal_source_segment(tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	run_dir = tmp_path / "episode"
	source = run_dir / "02-source-capture/youtube-media/source.mp4"
	audio = run_dir / "audio/final_podcast.wav"
	source.parent.mkdir(parents=True)
	audio.parent.mkdir(parents=True)
	subprocess.run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		"testsrc=size=320x180:rate=24:duration=3",
		"-f",
		"lavfi",
		"-i",
		"anullsrc=r=24000:cl=mono",
		"-t",
		"3",
		"-c:v",
		"libx264",
		"-pix_fmt",
		"yuv420p",
		"-c:a",
		"aac",
		str(source),
	], check=True)
	subprocess.run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		"anullsrc=r=24000:cl=mono",
		"-t",
		"1",
		"-c:a",
		"pcm_s16le",
		str(audio),
	], check=True)
	_write_json(run_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"episode_index": 1,
		"episode_count": 2,
		"source_start_sec": 0.5,
		"source_end_sec": 60.0,
	})
	manifest = revoice.run_revoice(
		run_dir=run_dir,
		source_video=None,
		audio=None,
		force=True,
		source_start_sec=None,
		match_audio_duration=False,
		allow_trim_audio=False,
		burn_subtitles=False,
		subtitle_manifest=None,
		subtitles_ass=None,
		video_encoder="libx264",
		video_bitrate="1000k",
		visual_sync_mode="disabled_v1",
		source_turn_map=None,
		turn_audio_timeline=None,
		source_time_offset_sec=None,
		update_root=True,
	)
	assert manifest["series_episode"] is True
	assert manifest["review_sample"] is False
	assert manifest["source_start_sec"] == 0.5
	assert manifest["visual_mode"] == "source_video_revoice_episode_segment"
	assert Path(manifest["outputs"]["root_final_video"]).exists()


def test_revoice_prefers_precut_episode_source_video(tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	run_dir = tmp_path / "episode"
	parent_source = run_dir / "02-source-capture/youtube-media/source.mp4"
	episode_source = run_dir / "04b-source-video-segment/source_episode.mp4"
	audio = run_dir / "audio/final_podcast.wav"
	_make_test_video(parent_source, duration=4.0)
	_make_test_video(episode_source, duration=1.5)
	_make_silent_wav(audio, duration=1.0)
	_write_json(run_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"episode_index": 1,
		"episode_count": 2,
		"source_start_sec": 30.0,
		"source_end_sec": 90.0,
		"source_episode_video": str(episode_source),
		"source_episode_video_manifest": str(run_dir / "04b-source-video-segment/source_episode_manifest.json"),
	})
	manifest = revoice.run_revoice(
		run_dir=run_dir,
		source_video=None,
		audio=None,
		force=True,
		source_start_sec=None,
		match_audio_duration=False,
		allow_trim_audio=False,
		burn_subtitles=False,
		subtitle_manifest=None,
		subtitles_ass=None,
		video_encoder="libx264",
		video_bitrate="1000k",
		visual_sync_mode="disabled_v1",
		source_turn_map=None,
		turn_audio_timeline=None,
		source_time_offset_sec=None,
		update_root=True,
	)
	assert manifest["series_episode"] is True
	assert manifest["source_episode_video_used"] is True
	assert manifest["video_input"] == str(episode_source.resolve())
	assert manifest["cut_source_start_sec"] is None
	assert manifest["visual_mode"] == "source_video_revoice_episode_segment"


def test_dialogue_timeline_uses_asr_timing_and_avoids_hard_phrase_splits(tmp_path: Path) -> None:
	project_dir = tmp_path / "project"
	text = (
		"他长期研究中国与中东，是阿布扎比扎耶德大学的政治学者、大西洋理事会非常驻高级研究员，"
		"也是China MENA Podcast的主持人。"
	)
	_make_silent_wav(project_dir / "audio/final_podcast.wav", duration=12.0)
	_write_json(project_dir / "audio/audio_manifest.json", {
		"script_sha256": "test",
		"turns": [{"turn_index": 1, "speaker": "Speaker 0", "text": text}],
	})
	norm_chars = [char for char in text.lower() if char.isalnum()]
	words = [
		{"word": char, "start": round(index * 0.12, 3), "end": round(index * 0.12 + 0.08, 3), "probability": 0.99}
		for index, char in enumerate(norm_chars)
	]
	asr_path = project_dir / "audio/asr_alignment.json"
	_write_json(asr_path, {"segments": [{"text": text, "start": 0.0, "end": 10.0, "words": words}]})
	timeline = dialogue_timeline_builder.build_timeline(project_dir, asr_path, project_dir / "audio/dialogue_timeline.json")
	cue_texts = [str(cue["text"]) for cue in timeline["cues"]]
	assert timeline["subtitle_cue_policy"]["cue_text_policy"] == "complete_sentence_or_semantic_clause_no_hard_width_split"
	assert timeline["subtitle_cue_policy"]["cue_timing_policy"] == "asr_character_span"
	assert not any(text.endswith("非") for text in cue_texts)
	assert "常驻高级研究员，" not in cue_texts
	assert any("大西洋理事会非常驻高级研究员" in text for text in cue_texts)
	assert all(cue.get("timing_source") == "asr_character_span" for cue in timeline["cues"])


def test_subtitle_builder_records_timing_and_segmentation_policy(tmp_path: Path) -> None:
	if not subtitle_builder.SUBTITLE_FONT_PATH.exists():
		pytest.skip(f"subtitle font missing: {subtitle_builder.SUBTITLE_FONT_PATH}")
	project_dir = tmp_path / "project"
	_make_silent_wav(project_dir / "audio/final_podcast.wav", duration=4.0)
	(project_dir / "podcast_script.md").write_text("Speaker 0: 这是第一句。这是第二句。\n", encoding="utf-8")
	_write_json(project_dir / "audio/dialogue_timeline.json", {
		"asr_summary": {"matched_script_ratio": 1.0},
		"turns": [{
			"turn_index": 1,
			"turn_id": "turn_0001",
			"speaker": "Speaker 0",
			"text": "这是第一句。这是第二句。",
			"start_sec": 0.25,
			"end_sec": 2.4,
			"alignment_confidence": "high",
			"asr_matched_char_ratio": 1.0,
		}],
		"cues": [
			{
				"cue_index": 1,
				"turn_index": 1,
				"turn_id": "turn_0001",
				"speaker": "Speaker 0",
				"text": "这是第一句。",
				"start_sec": 0.25,
				"end_sec": 1.2,
				"alignment_confidence": "high",
			},
			{
				"cue_index": 2,
				"turn_index": 1,
				"turn_id": "turn_0001",
				"speaker": "Speaker 0",
				"text": "这是第二句。",
				"start_sec": 1.2,
				"end_sec": 2.4,
				"alignment_confidence": "high",
			},
		],
	})
	result = subtitle_builder.build_subtitles(
		project_dir,
		subtitle_builder.GLOBAL_LEAD_SEC,
		subtitle_builder.TAIL_SEC,
		subtitle_builder.NEXT_CUE_OVERLAP_SEC,
	)
	manifest = _read_json(project_dir / "video/subtitle_manifest.json")
	assert result["timing_policy"] == "PASS"
	assert result["segmentation_policy"] == "PASS"
	assert manifest["global_lead_sec"] == 0.12
	assert manifest["timing_policy"]["status"] == "PASS"
	assert manifest["timing_policy"]["lead_applied_per_split_cue"] is True
	assert manifest["segmentation_policy"]["status"] == "PASS"
	assert manifest["segmentation_policy"]["dangling_fragment_violation_count"] == 0
	assert [cue["display_text"] for cue in manifest["cues"]] == ["这是第一句", "这是第二句"]
	assert manifest["cues"][0]["start_sec"] == pytest.approx(0.13, abs=0.001)


def test_revoice_cli_defaults_to_burned_subtitles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	monkeypatch.setattr(sys, "argv", ["run_source_video_revoice.py", "--run-dir", str(tmp_path)])
	args = revoice.parse_args()
	assert args.burn_subtitles is True
	assert args.visual_sync_mode == "turn_retimed_basic_v1"
	assert args.allow_full_render_experiments is False
	monkeypatch.setattr(sys, "argv", ["run_source_video_revoice.py", "--run-dir", str(tmp_path), "--no-burn-subtitles"])
	args = revoice.parse_args()
	assert args.burn_subtitles is False
	monkeypatch.setattr(sys, "argv", ["run_source_video_revoice.py", "--run-dir", str(tmp_path), "--allow-full-render-experiments"])
	args = revoice.parse_args()
	assert args.allow_full_render_experiments is True


def test_revoice_formal_scan_rejects_full_length_manual_test_render(tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	output_dir = tmp_path / "run/08-source-video-revoice"
	manual_test = output_dir / "work/source_retimed_basic.manual_cfr_test.mp4"
	_make_test_video(manual_test, duration=8.0)
	scan = revoice._scan_formal_full_render_experiments(
		output_dir,
		target_duration_sec=10.0,
		review_sample=False,
		allow_full_render_experiments=False,
	)
	assert scan["status"] == "FAIL"
	assert scan["candidate_count"] == 1
	assert scan["candidates"][0]["path"] == str(manual_test)
	with pytest.raises(AssertionError, match="manual/test render artifacts"):
		revoice._assert_no_formal_full_render_experiments(scan)
	review_scan = revoice._scan_formal_full_render_experiments(
		output_dir,
		target_duration_sec=10.0,
		review_sample=True,
		allow_full_render_experiments=False,
	)
	assert review_scan["status"] == "SKIPPED_REVIEW_SAMPLE"


def test_revoice_requires_materialized_source_dialogue_turn_map(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	safe_translation = run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json"
	voice_reference_timeline = run_dir / "02b-source-voice-prompts/source_speaker_timeline.normalized.json"
	_write_json(safe_translation, {"segments": [{"segment_index": 1, "source_start": "00:00:00", "source_end": "00:00:05", "speaker": "Speaker 0"}]})
	_write_json(voice_reference_timeline, [{"start": 50.0, "end": 55.0, "speaker": "Speaker 0"}])
	path, reason = revoice._select_source_turn_map(run_dir, None)
	assert path == (run_dir / "04-source-dialogue-turn-map/source_dialogue_turn_map.active.json").resolve()
	assert reason == "missing_active_source_turn_map"


def test_build_source_dialogue_turn_map_binds_split_audio_turns(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{"segment_index": 1, "speaker": "Speaker 0", "source_start_sec": 10.0, "source_end_sec": 20.0, "source_text": "one long source answer"},
			{"segment_index": 2, "speaker": "Speaker 1", "source_start_sec": 20.0, "source_end_sec": 25.0, "source_text": "short host question"},
		],
	})
	_write_json(run_dir / "audio/audio_manifest.json", {
		"turns": [
			{"turn_index": 1, "speaker": "Speaker 0", "source_turn_index": 1, "source_part_index": 1, "source_part_count": 2, "text": "第一段"},
			{"turn_index": 2, "speaker": "Speaker 0", "source_turn_index": 1, "source_part_index": 2, "source_part_count": 2, "text": "第二段"},
			{"turn_index": 3, "speaker": "Speaker 1", "source_turn_index": 2, "source_part_index": 1, "source_part_count": 1, "text": "第三段"},
		],
	})
	_write_json(run_dir / "06c-audio-timeline-alignment/turn_audio_timeline.json", {
		"duration_sec": 12.0,
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 4.0},
			{"turn_index": 2, "turn_id": "turn_0002", "speaker": "Speaker 0", "start_sec": 4.5, "end_sec": 8.0},
			{"turn_index": 3, "turn_id": "turn_0003", "speaker": "Speaker 1", "start_sec": 8.5, "end_sec": 12.0},
		],
	})
	result = source_dialogue_turn_map.build_source_dialogue_turn_map(run_dir)
	assert result["status"] == "PASS"
	assert result["mapped_turn_count"] == 3
	assert result["dropped_source_tail_sec"] == pytest.approx(3.0, abs=0.001)
	assert [turn["audio_turn_ids"] for turn in result["turns"]] == [["turn_0001"], ["turn_0002"], ["turn_0003"]]
	assert result["turns"][0]["target_visual_duration_sec"] == 4.5
	assert result["turns"][1]["target_visual_duration_sec"] == 4.0


def test_build_source_dialogue_turn_map_reuses_adjacent_same_speaker_visual_tail(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{"segment_index": 1, "speaker": "Speaker 0", "source_start_sec": 0.0, "source_end_sec": 10.0, "source_text": "long source answer"},
			{"segment_index": 2, "speaker": "Speaker 0", "source_start_sec": 10.0, "source_end_sec": 20.0, "source_text": ""},
			{"segment_index": 3, "speaker": "Speaker 1", "source_start_sec": 20.0, "source_end_sec": 25.0, "source_text": "host"},
		],
	})
	_write_json(run_dir / "audio/audio_manifest.json", {
		"turns": [
			{"turn_index": 1, "speaker": "Speaker 0", "source_turn_index": 1, "source_part_index": 1, "source_part_count": 2, "text": "第一段"},
			{"turn_index": 2, "speaker": "Speaker 0", "source_turn_index": 1, "source_part_index": 2, "source_part_count": 2, "text": "第二段"},
			{"turn_index": 3, "speaker": "Speaker 0", "source_turn_index": 2, "source_part_index": 1, "source_part_count": 1, "text": "第三段"},
			{"turn_index": 4, "speaker": "Speaker 1", "source_turn_index": 3, "source_part_index": 1, "source_part_count": 1, "text": "第四段"},
		],
	})
	_write_json(run_dir / "06c-audio-timeline-alignment/turn_audio_timeline.json", {
		"duration_sec": 27.0,
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 9.0},
			{"turn_index": 2, "turn_id": "turn_0002", "speaker": "Speaker 0", "start_sec": 9.0, "end_sec": 18.0},
			{"turn_index": 3, "turn_id": "turn_0003", "speaker": "Speaker 0", "start_sec": 18.0, "end_sec": 22.0},
			{"turn_index": 4, "turn_id": "turn_0004", "speaker": "Speaker 1", "start_sec": 22.0, "end_sec": 27.0},
		],
	})
	result = source_dialogue_turn_map.build_source_dialogue_turn_map(run_dir)
	assert result["status"] == "PASS"
	assert result["mapped_turn_count"] == 4
	assert result["extension_expected_sec"] == pytest.approx(2.0, abs=0.001)
	assert result["dropped_source_tail_sec"] == pytest.approx(0.0, abs=0.001)
	assert result["turns"][0]["source_segment_indices"] == [1, 2]
	assert result["turns"][1]["source_segment_indices"] == [1, 2]
	assert result["turns"][2]["source_segment_indices"] == [1, 2]
	assert result["turns"][2]["source_end_sec"] == pytest.approx(20.0, abs=0.001)


def test_multimodal_spot_qa_requires_all_criteria_for_every_sample() -> None:
	package = {
		"samples": [
			{"sample_id": "sample_001"},
			{"sample_id": "sample_002"},
		],
	}
	review = {
		"status": "PASS",
		"read_entire_package": True,
		"sample_reviews": [
			{
				"sample_id": "sample_001",
				"criteria": {criterion: "PASS" for criterion in multimodal_spot_qa.REQUIRED_CRITERIA},
			},
			{
				"sample_id": "sample_002",
				"criteria": {
					**{criterion: "PASS" for criterion in multimodal_spot_qa.REQUIRED_CRITERIA},
					"voice_identity_consistency": "FAIL",
				},
			},
		],
	}
	result = multimodal_spot_qa._validate_review(package, review)
	assert result["status"] == "FAIL"
	assert any("voice_identity_consistency" in failure for failure in result["failures"])


def test_revoice_burned_subtitles_outputs_2k_1440p(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	run_dir = tmp_path / "run"
	source = run_dir / "02-source-capture/youtube-media/source.mp4"
	audio = run_dir / "audio/final_podcast.wav"
	_make_test_video(source, duration=1.0, size=(320, 180))
	_make_silent_wav(audio, duration=1.0)
	_write_json(run_dir / "video/subtitle_manifest.json", {"cues": [{"index": 1, "start_sec": 0.0, "end_sec": 1.0, "text": "测试字幕"}]})

	def fake_overlay(work_dir: Path, subtitle_manifest: Path, target_duration: float, time_offset_sec: float = 0.0) -> tuple[Path, list[dict[str, Any]]]:
		assert subtitle_manifest.exists()
		assert time_offset_sec == 0.0
		work_dir.mkdir(parents=True, exist_ok=True)
		overlay = work_dir / "subtitle_overlay.mov"
		subprocess.run([
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-f",
			"lavfi",
			"-i",
			f"color=c=black@0.0:s={revoice.SUBTITLE_OVERLAY_W}x{revoice.SUBTITLE_OVERLAY_H}:r={revoice.FPS}:d={target_duration}",
			"-c:v",
			"qtrle",
			"-pix_fmt",
			"argb",
			str(overlay),
		], check=True)
		return overlay, []

	monkeypatch.setattr(revoice, "_render_subtitle_overlay_video", fake_overlay)
	manifest = revoice.run_revoice(
		run_dir=run_dir,
		source_video=None,
		audio=None,
		force=True,
		source_start_sec=None,
		match_audio_duration=True,
		allow_trim_audio=False,
		burn_subtitles=True,
		subtitle_manifest=None,
		subtitles_ass=None,
		video_encoder="libx264",
		video_bitrate="1000k",
		visual_sync_mode="disabled_v1",
		source_turn_map=None,
		turn_audio_timeline=None,
		source_time_offset_sec=None,
		update_root=False,
	)
	stream = manifest["final_video_stream"]
	assert manifest["target_video_resolution"] == "2560x1440"
	assert manifest["burned_subtitle_render"]["target_video_height"] == 1440
	assert manifest["formal_full_render_experiments_allowed"] is False
	assert manifest["formal_full_render_experiment_scan"]["status"] == "PASS"
	assert int(stream["width"]) == 2560
	assert int(stream["height"]) == 1440


def test_turn_retime_extends_short_source_turn_to_audio_boundary(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"fake source")
	source_turn_map = tmp_path / "source_turns.json"
	audio_timeline = tmp_path / "audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_plan.json"
	_write_json(source_turn_map, [
		{"turn_index": 1, "speaker": "Speaker 0", "start": 0.0, "end": 2.0, "text": "hello"},
	])
	_write_json(audio_timeline, {
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 3.0},
		],
	})
	_write_json(visual_activity, {
		"protected_ranges": [],
		"low_motion_ranges": [],
	})
	plan = turn_retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		min_extend_sec=0.01,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["target_duration_sec"] == 3.0
	assert plan["summary"]["estimated_video_duration_sec"] == 3.0
	assert plan["summary"]["extended_duration_sec"] == 1.0
	assert plan["summary"]["turn_boundary_drift_violation_count"] == 0
	assert plan["turns"][0]["extension_segments"][0]["source_mode"] == "freeze_tail"
	assert [segment["source_mode"] for segment in plan["edit_segments"]] == ["video_range", "freeze_tail"]


def test_turn_retime_prefers_explicit_audio_turn_binding_over_speaker_group(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"fake source")
	source_turn_map = tmp_path / "source_turns.json"
	audio_timeline = tmp_path / "audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_plan.json"
	_write_json(source_turn_map, {
		"turns": [
			{"turn_index": 1, "turn_id": "source_001", "speaker": "Speaker 0", "source_start_sec": 0.0, "source_end_sec": 4.0, "audio_turn_id": "turn_0001"},
			{"turn_index": 2, "turn_id": "source_002", "speaker": "Speaker 0", "source_start_sec": 4.0, "source_end_sec": 8.0, "audio_turn_id": "turn_0002"},
		],
	})
	_write_json(audio_timeline, {
		"duration_sec": 8.0,
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 4.0},
			{"turn_index": 2, "turn_id": "turn_0002", "speaker": "Speaker 0", "start_sec": 4.0, "end_sec": 8.0},
		],
	})
	_write_json(visual_activity, {
		"protected_ranges": [],
		"low_motion_ranges": [],
	})
	plan = turn_retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
	)
	assert plan["status"] == "pass"
	assert plan["turns"][0]["audio_turn_indices"] == [1]
	assert plan["turns"][1]["audio_turn_indices"] == [2]


def test_turn_retime_accepts_source_start_sec_fields(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"fake source")
	source_turn_map = tmp_path / "source_turns.json"
	audio_timeline = tmp_path / "audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_plan.json"
	_write_json(source_turn_map, {
		"turns": [
			{"turn_index": 1, "speaker": "Speaker 0", "source_start_sec": 0.0, "source_end_sec": 2.0, "text": "hello"},
		],
	})
	_write_json(audio_timeline, {
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 2.0},
		],
	})
	_write_json(visual_activity, {
		"protected_ranges": [],
		"low_motion_ranges": [],
	})
	plan = turn_retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["turn_count"] == 1
	assert plan["turns"][0]["source_start_sec"] == 0.0


def test_turn_retime_preserves_opening_non_dialogue_as_audio_offset(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"fake source")
	source_turn_map = tmp_path / "source_turns.json"
	audio_timeline = tmp_path / "audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_plan.json"
	_write_json(source_turn_map, [
		{"turn_index": 1, "speaker": "Speaker 0", "start": 1.0, "end": 3.0, "text": "[music]"},
		{"turn_index": 2, "speaker": "Speaker 1", "start": 5.0, "end": 8.0, "text": "welcome"},
	])
	_write_json(audio_timeline, {
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 1", "start_sec": 0.0, "end_sec": 3.0},
		],
	})
	_write_json(visual_activity, {
		"protected_ranges": [],
		"low_motion_ranges": [],
	})
	plan = turn_retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		min_extend_sec=0.01,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["audio_start_offset_sec"] == 5.0
	assert plan["summary"]["target_duration_sec"] == 8.0
	assert [turn["non_dialogue"] for turn in plan["turns"][:3]] == [True, True, True]
	assert plan["turns"][3]["speaker"] == "Speaker 1"
	assert plan["turns"][3]["target_duration_sec"] == 3.0


def test_turn_retime_marks_reusable_source_background_audio_for_revoice_mix(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"fake source")
	source_turn_map = tmp_path / "source_turns.json"
	audio_timeline = tmp_path / "audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_plan.json"
	_write_json(source_turn_map, [
		{"turn_index": 1, "speaker": "Speaker 0", "start": 0.0, "end": 1.0, "text": "[music]"},
		{"turn_index": 2, "speaker": "Speaker 1", "start": 2.0, "end": 4.0, "text": "welcome"},
	])
	_write_json(audio_timeline, {
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 1", "start_sec": 0.0, "end_sec": 2.0},
		],
	})
	_write_json(visual_activity, {
		"protected_ranges": [],
		"low_motion_ranges": [],
	})
	plan = turn_retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		min_extend_sec=0.01,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["audio_start_offset_sec"] == 2.0
	music_segments = [segment for segment in plan["edit_segments"] if segment.get("source_audio_event_type") == "music"]
	assert len(music_segments) == 1
	assert music_segments[0]["reuse_source_audio"] is True
	background_segments = revoice._source_background_audio_segments(plan, audio_start_offset_sec=2.0)
	assert background_segments == [{
		"segment_index": music_segments[0]["segment_index"],
		"source_start_sec": 0.0,
		"source_end_sec": 1.0,
		"target_start_sec": 0.0,
		"target_end_sec": 1.0,
		"duration_sec": 1.0,
		"event_type": "music",
		"gain": revoice.SOURCE_BACKGROUND_AUDIO_GAIN,
	}]
	audio_filter, audio_label, mix_manifest = revoice._audio_filter_for_mix(2.0, background_segments, source_audio_input_index=2)
	assert audio_label == "[aout]"
	assert "atrim=start=0.000:end=1.000" in audio_filter
	assert "adelay=2000:all=1" in audio_filter
	assert mix_manifest["source_background_audio_reused"] is True


def test_source_audio_event_census_marks_only_non_speech_background_reusable(tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	run_dir = tmp_path / "run"
	source_audio = run_dir / "02-source-capture/youtube-media/source.wav"
	source_turn_map = run_dir / "02b-source-voice-prompts/source_speaker_timeline.normalized.json"
	_make_tone_wav(source_audio, duration=4.0)
	_write_json(source_turn_map, [
		{"turn_index": 1, "speaker": "Speaker 0", "start": 0.0, "end": 1.0, "text": "[music]"},
		{"turn_index": 2, "speaker": "Speaker 1", "start": 1.0, "end": 3.0, "text": "spoken words"},
		{"turn_index": 3, "speaker": "Speaker 0", "start": 3.0, "end": 4.0, "text": "[silence]"},
	])
	result = source_audio_events.build_source_audio_event_census(
		run_dir=run_dir,
		source_audio=source_audio,
		source_turn_map=source_turn_map,
		output_path=run_dir / "02a-source-audio-events/source_audio_events.json",
	)
	events = result["events"]
	assert [event["event_type"] for event in events if event["evidence"]["basis"] == "source_timeline_explicit_non_speech_tag"] == ["music", "silence"]
	assert next(event for event in events if event["event_type"] == "music")["reuse_source_audio"] is True
	assert next(event for event in events if event["event_type"] == "silence")["reuse_source_audio"] is False


def test_revoice_turn_audio_timeline_selection_skips_stale_06c_copy(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	audio = run_dir / "audio/final_podcast.wav"
	_make_silent_wav(audio, duration=3.0)
	_write_json(run_dir / "06c-audio-timeline-alignment/turn_audio_timeline.json", {
		"audio_sha256": "stale",
		"duration_sec": 4.0,
		"turns": [{"turn_index": 1, "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 4.0}],
	})
	_write_json(run_dir / "audio/dialogue_timeline.json", {
		"audio_sha256": _sha256(audio),
		"duration_sec": 3.0,
		"turns": [{"turn_index": 1, "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 3.0}],
	})
	path, reason = revoice._select_turn_audio_timeline(run_dir, None, audio, 3.0)
	assert path == (run_dir / "audio/dialogue_timeline.json").resolve()
	assert reason == "audio_dialogue_timeline_current_fallback"


def test_revoice_background_mix_uses_parent_source_wav_for_preclipped_episode(tmp_path: Path) -> None:
	parent = tmp_path / "parent"
	episode = parent / "04b-series-episodes/episode_001"
	source_audio = parent / "02-source-capture/youtube-media/source.wav"
	source_video = episode / "04b-source-video-segment/source_episode.mp4"
	_make_silent_wav(source_audio, duration=4.0)
	_make_test_video(source_video, duration=2.0)
	selected_audio, offset, reason = revoice._resolve_source_audio_for_background_mix(
		episode,
		source_video,
		{"parent_run_dir": str(parent)},
		source_is_preclipped_episode=True,
		semantic_source_start_sec=1.0,
	)
	assert selected_audio == source_audio.resolve()
	assert offset == 1.0
	assert reason == "parent_source_wav_for_preclipped_episode"


def test_turn_retime_groups_consecutive_audio_turns_by_speaker(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"fake source")
	source_turn_map = tmp_path / "source_turns.json"
	audio_timeline = tmp_path / "audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_plan.json"
	_write_json(source_turn_map, [
		{"turn_index": 1, "speaker": "Speaker 1", "start": 0.0, "end": 10.0, "text": "long host intro"},
		{"turn_index": 2, "speaker": "Speaker 0", "start": 10.0, "end": 12.0, "text": "guest reply"},
	])
	_write_json(audio_timeline, {
		"turns": [
			{"turn_index": 1, "turn_id": "turn_0001", "speaker": "Speaker 1", "start_sec": 0.0, "end_sec": 4.0},
			{"turn_index": 2, "turn_id": "turn_0002", "speaker": "Speaker 1", "start_sec": 4.5, "end_sec": 6.0},
			{"turn_index": 3, "turn_id": "turn_0003", "speaker": "Speaker 0", "start_sec": 6.5, "end_sec": 8.5},
		],
	})
	_write_json(visual_activity, {
		"protected_ranges": [],
		"low_motion_ranges": [{"start_sec": 2.0, "end_sec": 9.0}],
	})
	plan = turn_retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		min_trim_sec=0.1,
		min_kept_segment_sec=0.5,
	)
	assert plan["status"] == "pass"
	assert plan["turns"][0]["audio_turn_indices"] == [1, 2]
	assert plan["turns"][0]["following_silence_held_by_current_speaker_sec"] == 0.5
	assert plan["turns"][0]["target_duration_sec"] == 6.5
	assert plan["turns"][1]["audio_turn_indices"] == [3]
	assert plan["summary"]["turn_boundary_drift_violation_count"] == 0


def test_audio_transcript_integrity_qa_uses_complete_audio_asr_before_timeline(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_make_silent_wav(run_dir / "audio/final_podcast.wav", duration=1.0)
	_write_json(run_dir / "audio/audio_manifest.json", {
		"turns": [
			{"turn_index": 1, "speaker": "Speaker 0", "text": "中国经济韧性很重要", "chunk_id": "chunk_001"},
			{"turn_index": 2, "speaker": "Speaker 1", "text": "外部观察者也在重新评估中国市场", "chunk_id": "chunk_002"},
		],
	})
	_write_json(run_dir / "audio/asr_alignment.json", {
		"segments": [{
			"start": 0.0,
			"end": 1.0,
			"text": "中国经济韧性很重要外部观察者也在重新评估中国市场",
		}],
	})
	result = audio_integrity.run_integrity_qa(
		run_dir,
		min_global_matched_ratio=0.95,
		min_long_turn_ratio=0.80,
		min_medium_turn_ratio=0.60,
		min_short_turn_ratio=0.60,
		max_unmatched_script_run_chars=12,
		max_unmatched_asr_run_chars=20,
	)
	assert result["status"] == "PASS"
	assert result["inputs"]["dialogue_timeline"] is None
	_write_json(run_dir / "audio/asr_alignment.json", {
		"segments": [{
			"start": 0.0,
			"end": 1.0,
			"text": "中国经济韧性很重要",
		}],
	})
	result = audio_integrity.run_integrity_qa(
		run_dir,
		min_global_matched_ratio=0.95,
		min_long_turn_ratio=0.80,
		min_medium_turn_ratio=0.60,
		min_short_turn_ratio=0.60,
		max_unmatched_script_run_chars=12,
		max_unmatched_asr_run_chars=20,
	)
	assert result["status"] == "FAIL"
	assert result["summary"]["repair_target_chunks"] == ["chunk_002"]


def test_bilibili_text_compliance_review_flags_platform_terminology(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	(run_dir / "04-podcast-script").mkdir(parents=True)
	(run_dir / "04-podcast-script/podcast_script.md").write_text(
		"Speaker 0: 中国台湾这个国家这样的称呼不合规，香港也不能简称。\n"
		"Speaker 1: Mainland China 和南京大屠杀纪念馆、新疆维吾尔族自治区也都不合规。\n"
		"Speaker 0: 中国台湾大约有300,000名穆斯林，这300,000人不是300人。\n",
		encoding="utf-8",
	)
	(run_dir / "podcast_script.md").write_text(
		"Speaker 0: 原话说，请不要将此演讲上传到互联网上，只能录成 MP3。\n",
		encoding="utf-8",
	)
	(run_dir / "video_title.txt").write_text("嘉宾观察·第1集：穆斯林该押注中国吗？\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {"title_text": "嘉宾观察：押注中国吗"})
	(run_dir / "publish_info.txt").write_text(
		"本期是基于外网公开播客/访谈视频制作的中文配音版本：保留原视频画面，替换为中文对话音频，方便中文观众理解原对话内容。\n",
		encoding="utf-8",
	)
	result = text_compliance.run_review(run_dir, stage="test")
	assert result["status"] == "FAIL"
	rule_ids = {finding["rule_id"] for finding in result["findings"]}
	assert "taiwan_hongkong_abbreviation" in rule_ids
	assert "taiwan_named_as_country" in rule_ids
	assert "wrong_chinese_mainland_english_term" in rule_ids
	assert "wrong_nanjing_memorial_name" in rule_ids
	assert "wrong_xinjiang_autonomous_region_name" in rule_ids
	assert "polarizing_bilibili_title_or_metadata" in rule_ids
	assert "high_risk_private_recording_or_no_upload_phrase" in rule_ids
	assert "bilibili_description_production_note" in rule_ids
	assert "chinese_display_comma_thousands_number" in rule_ids


def test_bilibili_text_compliance_review_flags_online_religious_service_risks(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	(run_dir / "04-podcast-script").mkdir(parents=True)
	(run_dir / "04-podcast-script/podcast_script.md").write_text(
		"Speaker 0: 我们不能指望街头达瓦在这里发生，但可以在清真寺外面做邀请桌，带你们参观清真寺。\n"
		"Speaker 1: 当人们面对精神危机时，会从宗教中寻找解决方案；他们想要皈依，认为伊斯兰教是真理，也更和平。\n"
		"Speaker 0: 我会继续教授伊斯兰课程和伊斯兰讲座，传播这些教义。\n",
		encoding="utf-8",
	)
	(run_dir / "publish_info.txt").write_text(
		"这家公司是符合伊斯兰教法的房地产公司，适合用宗教名义进行商业宣传。\n",
		encoding="utf-8",
	)
	result = text_compliance.run_review(run_dir, stage="test")
	assert result["status"] == "FAIL"
	rule_ids = {finding["rule_id"] for finding in result["findings"]}
	assert "online_religious_proselytizing_or_conversion" in rule_ids
	assert "online_religious_truth_or_mental_relief_claim" in rule_ids
	assert "online_religious_doctrine_or_teaching_promotion" in rule_ids
	assert "online_religious_commercial_promotion" in rule_ids


def test_bilibili_text_compliance_review_accepts_required_terms(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	(run_dir / "04-podcast-script").mkdir(parents=True)
	(run_dir / "04-podcast-script/podcast_script.md").write_text(
		"Speaker 0: 中国台湾和中国香港的市场联系，需要放在 Chinese mainland 的区域背景下理解。\n"
		"Speaker 1: 侵华日军南京大屠杀遇难同胞纪念馆与新疆维吾尔自治区都使用规范全称。\n",
		encoding="utf-8",
	)
	result = text_compliance.run_review(run_dir, stage="test")
	assert result["status"] == "PASS"
	assert result["summary"]["fail_findings"] == 0


def test_podcast_script_format_normalizes_comma_thousands_without_weird_wan_units(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	(run_dir / "03-source-translation").mkdir(parents=True)
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"content_coverage": "full_translation",
		"segments": [
			{
				"segment_index": 1,
				"speaker": "Speaker 0",
				"source_start": "00:00:00",
				"source_end": "00:00:10",
				"zh_text": "中国台湾大约有300,000名穆斯林，另有3,000人参与调查，不是300人。",
			},
		],
	})
	result = script_format.format_script(run_dir)
	assert result["status"] == "pass"
	script = (run_dir / "04-podcast-script/podcast_script.md").read_text(encoding="utf-8")
	assert "30万名穆斯林" in script
	assert "3000人参与调查" in script
	assert "不是300人" in script
	assert "300,000" not in script
	assert "0.3万" not in script
	assert "0.03万" not in script


def test_source_video_revoice_subtitle_layout_shifts_down_one_font_height() -> None:
	assert revoice.SUBTITLE_VERTICAL_DOWN_SHIFT_PX == revoice.SUBTITLE_FONT_SIZE_PX
	assert revoice.SUBTITLE_VERTICAL_DOWN_SHIFT_PX == 64
	assert revoice.SUBTITLE_OVERLAY_Y == revoice._scale_px(1648) + revoice.SUBTITLE_FONT_SIZE_PX
	assert revoice.SUBTITLE_TOP_Y == revoice._scale_px(1808) + revoice.SUBTITLE_FONT_SIZE_PX
	assert revoice.SUBTITLE_BOTTOM_Y == revoice._scale_px(1948) + revoice.SUBTITLE_FONT_SIZE_PX
	assert revoice.SUBTITLE_BOTTOM_Y < revoice.HEIGHT


def test_voice_consistency_lineage_rejects_default_voice_leakage(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {
				"vibevoice_name": "Voice0",
				"reference_wav": str(run_dir / "voices/Voice0.wav"),
			},
			"Speaker 1": {
				"vibevoice_name": "Voice1",
				"reference_wav": str(run_dir / "voices/Voice1.wav"),
			},
		},
	})
	_write_json(run_dir / "audio/audio_manifest.json", {
		"speaker_voices": {"Speaker 0": "Voice0", "Speaker 1": "Voice1"},
		"voice_context_policy": "locked_two_speaker_roster",
		"chunks": [{
			"chunk_id": "chunk_001",
			"speaker_names": ["Voice0", "Voice1"],
			"voice_context_policy": "locked_two_speaker_roster",
		}],
	})
	_write_json(run_dir / "05-vibevoice-chunks/chunk_plan.json", {
		"voice_context_policy": "locked_two_speaker_roster",
		"chunks": [{
			"chunk_id": "chunk_001",
			"speaker_names": ["Voice0", "Voice1"],
		}],
	})
	_write_json(run_dir / "05-vibevoice-chunks/chunks/chunk_001/audio/audio_manifest.json", {
		"speaker_map": {
			"Speaker 0": {"default_vibevoice_name": "Xinran"},
			"Speaker 1": {"default_vibevoice_name": "BowenClean"},
		},
	})
	result = voice_consistency.run_voice_consistency_qa(run_dir, lineage_only=True)
	assert result["overall_status"] == "FAIL"
	assert result["lineage"]["status"] == "FAIL"
	messages = "\n".join(finding["message"] for finding in result["lineage"]["findings"])
	assert "default_vibevoice_name" in messages
	assert "Xinran" in messages


def test_voice_consistency_lineage_rejects_speaker_map_role_gender_conflict(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "02a-speaker-census/speaker_roster.json", {
		"schema_version": "worldview-china-speaker-census.v1",
		"status": "frozen",
		"speaker_count": 2,
		"voice_count": 2,
		"speakers": {
			"Speaker 0": {
				"description": "Jonathan Fulton, guest; male voice, right side of split-screen.",
			},
			"Speaker 1": {
				"description": "Elizabeth Economy, host; female voice, left side of split-screen.",
			},
		},
	})
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {
				"vibevoice_name": "Voice0",
				"reference_wav": str(run_dir / "voices/Voice0.wav"),
			},
			"Speaker 1": {
				"vibevoice_name": "Voice1",
				"reference_wav": str(run_dir / "voices/Voice1.wav"),
			},
		},
	})
	_write_json(run_dir / "audio/audio_manifest.json", {
		"speaker_voices": {"Speaker 0": "Voice0", "Speaker 1": "Voice1"},
		"voice_context_policy": "locked_two_speaker_roster",
		"speaker_map": {
			"Speaker 0": {"display_role": "女主持", "vibevoice_name": "Voice0"},
			"Speaker 1": {"display_role": "男分析者", "vibevoice_name": "Voice1"},
		},
	})
	_write_json(run_dir / "05-vibevoice-chunks/chunk_plan.json", {
		"voice_context_policy": "locked_two_speaker_roster",
		"chunks": [],
	})
	result = voice_consistency.run_voice_consistency_qa(run_dir, lineage_only=True)
	assert result["overall_status"] == "FAIL"
	messages = "\n".join(finding["message"] for finding in result["lineage"]["findings"])
	assert "role gender hint female conflicts" in messages
	assert "role gender hint male conflicts" in messages


def test_voice_consistency_acoustic_identity_mismatch_is_fail() -> None:
	status, reason = voice_consistency._classify_acoustic_sample(
		"Speaker 1",
		"Speaker 0",
		assigned_score=0.5,
		margin=-0.02,
		min_similarity_margin=0.01,
		min_assigned_similarity=-0.20,
		references_confusable=False,
		max_confusable_identity_mismatch_margin=0.03,
	)
	assert status == "FAIL"
	assert reason == "voice_identity_mismatch"


def test_vibevoice_chunk_annotation_removes_default_voice_metadata(tmp_path: Path) -> None:
	audio_dir = tmp_path / "chunk/audio"
	_write_json(audio_dir / "audio_manifest.json", {
		"speaker_map": {
			"Speaker 0": {"default_vibevoice_name": "Xinran"},
			"Speaker 1": {"default_vibevoice_name": "BowenClean"},
		},
	})
	vibevoice_chunks._annotate_chunk_audio_manifest(
		audio_dir,
		{"Speaker 0": "Voice0", "Speaker 1": "Voice1"},
		["Voice0", "Voice1"],
		"locked_two_speaker_roster",
		"resident_batch",
		"02c-qwen-vibevoice-prompts/voice_prompt_manifest.json",
	)
	manifest = _read_json(audio_dir / "audio_manifest.json")
	assert manifest["speaker_names"] == ["Voice0", "Voice1"]
	assert manifest["speaker_voices"] == {"Speaker 0": "Voice0", "Speaker 1": "Voice1"}
	assert manifest["voice_context_policy"] == "locked_two_speaker_roster"
	assert manifest["speaker_map"]["Speaker 0"]["vibevoice_name"] == "Voice0"
	assert "default_vibevoice_name" not in manifest["speaker_map"]["Speaker 0"]


def test_prepare_vibevoice_inputs_uses_worldview_speaker_map_override(tmp_path: Path) -> None:
	project_dir = tmp_path / "chunk"
	project_dir.mkdir()
	(project_dir / "podcast_script.md").write_text(
		"Speaker 1: 欢迎来到节目。\nSpeaker 0: 谢谢你，Liz。\n",
		encoding="utf-8",
	)
	_write_json(project_dir / "speaker_map.json", {
		"schema_version": "worldview-china-vibevoice-speaker-map.v1",
		"speaker_map": {
			"Speaker 0": {"display_role": "Jonathan Fulton", "vibevoice_name": "Voice0"},
			"Speaker 1": {"display_role": "Elizabeth Economy", "vibevoice_name": "Voice1"},
		},
	})
	speaker_map, source = prepare_vibevoice_inputs._load_speaker_map(project_dir)
	turns = prepare_vibevoice_inputs._parse_turns(
		(project_dir / "podcast_script.md").read_text(encoding="utf-8"),
		speaker_map,
	)
	assert source.endswith("speaker_map.json")
	assert turns[0]["speaker"] == "Speaker 1"
	assert turns[0]["display_role"] == "Elizabeth Economy"
	assert turns[1]["display_role"] == "Jonathan Fulton"


def test_resident_batch_remaps_out_of_order_global_speakers_to_local_slots(monkeypatch: pytest.MonkeyPatch) -> None:
	fake_torch = types.ModuleType("torch")
	monkeypatch.setitem(sys.modules, "torch", fake_torch)
	resident_batch = _load_module(
		"run_vibevoice_resident_batch_test",
		Path("/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_resident_batch.py"),
	)
	scripts, speaker_numbers = resident_batch._parse_txt_script(
		"Speaker 1: 开场由二号全局说话人先说。\nSpeaker 0: 然后一号全局说话人回答。\n"
	)
	remapped, voice_sample_speaker_numbers, global_to_local = resident_batch._remap_scripts_to_local_speakers(
		scripts,
		speaker_numbers,
	)
	assert voice_sample_speaker_numbers == ["1", "0"]
	assert global_to_local == {"1": "0", "0": "1"}
	assert remapped == [
		"Speaker 0: 开场由二号全局说话人先说。",
		"Speaker 1: 然后一号全局说话人回答。",
	]


def test_bilibili_text_compliance_review_ignores_source_text_fields(tmp_path: Path) -> None:
	run_dir = tmp_path / "episode"
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"segments": [{
			"source_text": "The guest said Mainland China and Taiwan in the original transcript.",
			"zh_text": "嘉宾谈到 Chinese mainland 与中国台湾。",
		}],
	})
	result = text_compliance.run_review(run_dir, stage="test")
	assert result["status"] == "PASS"
	assert result["summary"]["fail_findings"] == 0


def test_vibevoice_chunks_dry_run_defaults_to_mps_auto(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	(run_dir / "04-podcast-script").mkdir(parents=True)
	(run_dir / "podcast_script.md").write_text(
		"Speaker 0: 中国市场仍然很重要\nSpeaker 1: 外部观察者也在重新评估中国经济\n",
		encoding="utf-8",
	)
	(run_dir / "04-podcast-script/podcast_script.md").write_text(
		(run_dir / "podcast_script.md").read_text(encoding="utf-8"),
		encoding="utf-8",
	)
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {"vibevoice_name": "Voice0"},
			"Speaker 1": {"vibevoice_name": "Voice1"},
		},
		"voice_distinctness_policy": {
			"status": "PASS_ORIGINAL_CLONED_PAIR",
			"scope": "exactly_two_speakers_only",
			"threshold": 0.90,
		},
	})
	result = vibevoice_chunks.run_chunks(
		run_dir=run_dir,
		force=False,
		force_chunk_ids=set(),
		dry_run=True,
		no_progress_bar=True,
		split_chunk_indices=set(),
		split_max_chars=650,
		split_all_chunks=False,
		split_long_turn_max_chars=vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
		fixed_chunk_plan_json=None,
		postprocess_min_source_mean_volume=-30.0,
		postprocess_min_source_max_volume=vibevoice_chunks.DEFAULT_POSTPROCESS_MIN_SOURCE_MAX_VOLUME,
		voice_prompt_policy="qwen_chinese_required",
		generation_runner="resident_batch",
		voice_context_policy="locked_two_speaker_roster",
		device=vibevoice_chunks.DEFAULT_VIBEVOICE_DEVICE,
		torch_dtype=vibevoice_chunks.DEFAULT_VIBEVOICE_TORCH_DTYPE,
		attn_implementation=vibevoice_chunks.DEFAULT_VIBEVOICE_ATTN_IMPLEMENTATION,
		generation_seed=42,
	)
	plan = _read_json(run_dir / "05-vibevoice-chunks/chunk_plan.json")
	assert result["status"] == "dry_run"
	assert plan["vibevoice_runner"] == "resident_batch"
	assert plan["vibevoice_device"] == "mps"
	assert plan["vibevoice_torch_dtype"] == "auto"
	assert plan["vibevoice_attn_implementation"] == "auto"
	assert plan["vibevoice_generation_seed"] == 42
	assert plan["target_chars"] == 320
	assert plan["min_split_chars"] == 180
	assert plan["hard_max_chars"] == 420
	assert plan["default_split_long_turn_max_chars"] == 160


def test_speaker_census_freezes_three_speaker_roster(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	source_audio = run_dir / "02-source-capture/youtube-media/source.wav"
	_make_silent_wav(source_audio, duration=420.0)
	timeline_json = run_dir / "02-source-capture/source_speaker_timeline.json"
	_write_json(timeline_json, {
		"segments": [
			{"speaker": "Speaker 0", "start": 0.0, "end": 80.0, "text": "Host opens"},
			{"speaker": "Speaker 1", "start": 90.0, "end": 180.0, "text": "Guest answers"},
			{"speaker": "Speaker 2", "start": 190.0, "end": 260.0, "text": "Second guest adds context"},
		],
	})
	roster = speaker_census.run_speaker_census(
		run_dir,
		source_video=None,
		source_audio=source_audio,
		timeline_json=timeline_json,
		output_dir=None,
		analysis_window_sec=360.0,
		force=True,
		skip_review_media=True,
		confirm_two_speakers=False,
		confirm_speaker_count=3,
		speaker_descriptions={
			"Speaker 0": "host voice",
			"Speaker 1": "first guest voice",
			"Speaker 2": "second guest voice",
		},
	)
	assert roster["status"] == "frozen"
	assert roster["speaker_count"] == 3
	assert roster["voice_count"] == 3
	assert list(roster["speakers"]) == ["Speaker 0", "Speaker 1", "Speaker 2"]


def test_source_voice_prompts_extracts_three_speaker_roster(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "run_manifest.json", {"nodes": {}})
	source_audio = run_dir / "02-source-capture/youtube-media/source.wav"
	_make_tone_wav(source_audio, duration=40.0)
	_write_json(run_dir / "02a-speaker-census/speaker_roster.json", {
		"schema_version": "worldview-china-speaker-census.v1",
		"status": "frozen",
		"speaker_count": 3,
		"voice_count": 3,
		"analysis_window_sec": 360.0,
		"speakers": {
			"Speaker 0": {"description": "host", "role": "host", "identity": ""},
			"Speaker 1": {"description": "guest one", "role": "guest", "identity": ""},
			"Speaker 2": {"description": "guest two", "role": "guest", "identity": ""},
		},
	})
	timeline_json = run_dir / "02-source-capture/source_speaker_timeline.json"
	_write_json(timeline_json, {
		"segments": [
			{"speaker": "Speaker 0", "start": 1.0, "end": 7.0, "text": "clean source text for the first speaker"},
			{"speaker": "Speaker 1", "start": 12.0, "end": 18.0, "text": "clean source text for the second speaker"},
			{"speaker": "Speaker 2", "start": 23.0, "end": 29.0, "text": "clean source text for the third speaker"},
		],
	})

	result = source_voice_prompts.extract_voice_prompts(
		run_dir,
		source_audio=source_audio,
		timeline_json=timeline_json,
		output_dir=None,
		voices_dir=tmp_path / "voices",
		register_voices=False,
		target_sec=3.0,
		min_total_sec=2.0,
		max_clip_sec=3.0,
		min_clip_sec=2.0,
		boundary_trim_sec=0.0,
		skip_before_sec=0.0,
		inter_clip_pause_sec=0.0,
		force=True,
	)

	manifest = _read_json(run_dir / "02b-source-voice-prompts/voice_prompt_manifest.json")
	assert result["status"] == "pass"
	assert list(result["speaker_names"]) == ["Speaker 0", "Speaker 1", "Speaker 2"]
	assert manifest["speaker_roster"]["speaker_count"] == 3
	assert manifest["speaker_roster"]["voice_count"] == 3
	assert list(manifest["speaker_voices"]) == ["Speaker 0", "Speaker 1", "Speaker 2"]
	for index in range(3):
		assert Path(manifest["speaker_voices"][f"Speaker {index}"]["reference_wav"]).exists()


def test_qwen_prompt_seed_supports_three_speaker_source_manifest(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	run_dir.mkdir()
	_write_json(run_dir / "run_manifest.json", {"nodes": {}})
	_write_json(run_dir / "02a-speaker-census/speaker_roster.json", {
		"status": "frozen",
		"speaker_count": 3,
		"voice_count": 3,
		"speakers": {
			"Speaker 0": {"description": "host"},
			"Speaker 1": {"description": "guest one"},
			"Speaker 2": {"description": "guest two"},
		},
	})
	census_path = run_dir / "02a-speaker-census/speaker_roster.json"
	speaker_voices: dict[str, Any] = {}
	for index in range(3):
		clip = run_dir / f"clips/speaker{index}.wav"
		_make_silent_wav(clip, duration=10.0)
		speaker = f"Speaker {index}"
		speaker_voices[speaker] = {
			"vibevoice_name": f"Voice{index}",
			"selected_clips": [{
				"clip": str(clip),
				"start_sec": 0.0,
				"end_sec": 10.0,
				"text_preview": f"Clean reference text for speaker {index}",
				"metrics": {"duration_sec": 10.0},
			}],
		}
	_write_json(run_dir / "02b-source-voice-prompts/voice_prompt_manifest.json", {
		"status": "pass",
		"speaker_census_roster_path": str(census_path),
		"speaker_census_roster_sha256": _sha256(census_path),
		"speaker_roster": {
			"status": "frozen",
			"speaker_count": 3,
			"voice_count": 3,
			"speakers": {
				"Speaker 0": {},
				"Speaker 1": {},
				"Speaker 2": {},
			},
		},
		"speaker_voices": speaker_voices,
	})
	result = qwen_prompts.build_prompts(
		run_dir,
		source_manifest=None,
		output_dir=None,
		qwen_repo=tmp_path / "missing-qwen-repo",
		qwen_python=tmp_path / "missing-python",
		qwen_model=tmp_path / "missing-model",
		voices_dir=tmp_path / "voices",
		target_text_json=None,
		dry_run=True,
		force=True,
		register_voices=False,
		min_prompt_sec=5.0,
		max_prompt_sec=30.0,
		max_tokens=900,
	)
	seed = _read_json(run_dir / "02c-qwen-vibevoice-prompts/prompt_manifest.seed.json")
	assert result["status"] == "dry_run"
	assert list(seed["speakers"]) == ["Speaker 0", "Speaker 1", "Speaker 2"]
	assert seed["speakers"]["Speaker 2"]["vibevoice_name"] == "Voice2QwenZH"


def test_vibevoice_chunks_locked_roster_supports_single_speaker_chunk_from_three_speaker_run(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	(run_dir / "04-podcast-script").mkdir(parents=True)
	(run_dir / "podcast_script.md").write_text(
		"Speaker 2: 第三位说话人单独讲完这一段内容，其他人这个 chunk 不说话。\n",
		encoding="utf-8",
	)
	(run_dir / "04-podcast-script/podcast_script.md").write_text(
		(run_dir / "podcast_script.md").read_text(encoding="utf-8"),
		encoding="utf-8",
	)
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {"vibevoice_name": "Voice0"},
			"Speaker 1": {"vibevoice_name": "Voice1"},
			"Speaker 2": {"vibevoice_name": "Voice2"},
		},
	})
	result = vibevoice_chunks.run_chunks(
		run_dir=run_dir,
		force=False,
		force_chunk_ids=set(),
		dry_run=True,
		no_progress_bar=True,
		split_chunk_indices=set(),
		split_max_chars=650,
		split_all_chunks=False,
		split_long_turn_max_chars=vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
		fixed_chunk_plan_json=None,
		postprocess_min_source_mean_volume=-30.0,
		postprocess_min_source_max_volume=vibevoice_chunks.DEFAULT_POSTPROCESS_MIN_SOURCE_MAX_VOLUME,
		voice_prompt_policy="qwen_chinese_required",
		generation_runner="resident_batch",
		voice_context_policy="locked_multi_speaker_roster",
		device=vibevoice_chunks.DEFAULT_VIBEVOICE_DEVICE,
		torch_dtype=vibevoice_chunks.DEFAULT_VIBEVOICE_TORCH_DTYPE,
		attn_implementation=vibevoice_chunks.DEFAULT_VIBEVOICE_ATTN_IMPLEMENTATION,
		generation_seed=42,
	)
	plan = _read_json(run_dir / "05-vibevoice-chunks/chunk_plan.json")
	assert result["status"] == "dry_run"
	assert plan["voice_context_policy"] == "locked_multi_speaker_roster"
	assert plan["chunks"][0]["vibevoice_mode"] == "dialogue"
	assert plan["chunks"][0]["speaker_names"] == ["Voice0", "Voice1", "Voice2"]
	assert plan["chunks"][0]["speaker_counts"] == {"Speaker 2": 1}


def _write_two_speaker_host_guest_roster(run_dir: Path) -> None:
	_write_json(run_dir / "02a-speaker-census/speaker_roster.json", {
		"schema_version": "worldview-china-speaker-census.v1",
		"status": "frozen",
		"speaker_count": 2,
		"voice_count": 2,
		"speakers": {
			"Speaker 0": {
				"speaker": "Speaker 0",
				"description": "Dr. Expert, guest/expert, primary expert voice answering most questions; use as guest voice slot.",
				"role": "guest_or_speaker_0",
			},
			"Speaker 1": {
				"speaker": "Speaker 1",
				"description": "Raj Host, host/interviewer, asks short questions; use as host voice slot.",
				"role": "host_or_speaker_1",
			},
		},
	})


def _write_two_speaker_qwen_manifest(run_dir: Path) -> Path:
	manifest_path = run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json"
	_write_json(manifest_path, {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {"vibevoice_name": "Voice0"},
			"Speaker 1": {"vibevoice_name": "Voice1"},
		},
		"voice_distinctness_policy": {
			"status": "PASS_ORIGINAL_CLONED_PAIR",
			"scope": "exactly_two_speakers_only",
			"threshold": 0.90,
		},
	})
	return manifest_path


def _write_pass_review(path: Path, required_paths: dict[str, Path]) -> None:
	_write_json(path, {
		"schema_version": "worldview-china-test-review.v1",
		"status": "PASS",
		"reviewed_files": [str(item) for item in required_paths.values()],
		"reviewed_file_hashes": {
			str(item.resolve()): _sha256(item)
			for item in required_paths.values()
		},
		"summary": {
			"fail_findings": 0,
		},
		"risk_registry": {
			"load_status": "loaded",
			"deterministic_rule_ids_missing_from_registry": [],
		},
		"findings": [],
	})


def _write_pre_tts_contract_inputs(run_dir: Path) -> None:
	safe_path = run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json"
	safe_data = _read_json(safe_path)
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", safe_data)
	(run_dir / "03-source-translation/source_transcript.zh.md").parent.mkdir(parents=True, exist_ok=True)
	(run_dir / "03-source-translation/source_transcript.zh.md").write_text("Speaker 1: 你告诉我，这为什么重要？\nSpeaker 0: 我认为重要，因为这关系到投资。\n", encoding="utf-8")
	(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.md").write_text("Speaker 1: 你告诉我，这为什么重要？\nSpeaker 0: 我认为重要，因为这关系到投资。\n", encoding="utf-8")
	(run_dir / "video_title.txt").write_text("印度视角下的中美竞争·第2集：资源外交与2047大国路线\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {
		"title_text": "印度视角下的中美竞争：资源外交与2047大国路线",
		"video_title_text": "印度视角下的中美竞争·第2集：资源外交与2047大国路线",
	})
	faithful = run_dir / "03-source-translation/source_transcript.zh.json"
	active = safe_path
	translation_required = {
		"faithful_translation_json": faithful,
		"active_translation_json": active,
	}
	_write_pass_review(run_dir / "03c-translation-semantic-qa/translation-semantic-qa-result.json", translation_required)
	_write_pass_review(run_dir / "03d-risk-compliance-review/text-compliance-review-result.json", translation_required)
	_write_pass_review(run_dir / "03d-risk-compliance-review/independent-review-result.json", translation_required)
	gate_result = speaker_turn_gate.run_gate(run_dir)
	assert gate_result["status"] == "PASS"
	publishable_required = {
		"active_translation_json": active,
		"script_turns": run_dir / "04-podcast-script/script_turns.json",
		"node_podcast_script": run_dir / "04-podcast-script/podcast_script.md",
		"root_podcast_script": run_dir / "podcast_script.md",
		"video_title": run_dir / "video_title.txt",
		"cover_title": run_dir / "cover/cover_title.json",
	}
	_write_pass_review(run_dir / "04c-bilibili-text-compliance/text-compliance-review-result.json", publishable_required)
	_write_pass_review(run_dir / "04c-bilibili-text-compliance/independent-review-result.json", publishable_required)


def _write_passing_pre_tts_contract(run_dir: Path) -> None:
	_write_pre_tts_contract_inputs(run_dir)
	result = pre_tts_contract.run_contract(run_dir, force=True)
	assert result["status"] == "PASS"


def _make_two_speaker_clean_script_run(run_dir: Path) -> Path:
	_write_two_speaker_host_guest_roster(run_dir)
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{
				"segment_index": 1,
				"source_start": "00:00:01",
				"source_end": "00:00:04",
				"speaker": "Speaker 1",
				"source_text": "Tell me, why does this matter?",
				"zh_text": "你告诉我，这为什么重要？",
			},
			{
				"segment_index": 2,
				"source_start": "00:00:04",
				"source_end": "00:00:12",
				"speaker": "Speaker 0",
				"source_text": "I think it matters because this is about investment.",
				"zh_text": "我认为重要，因为这关系到投资。",
			},
		],
	})
	script_format.format_script(run_dir)
	assert (run_dir / "podcast_script.md").exists()
	manifest_path = _write_two_speaker_qwen_manifest(run_dir)
	gate_result = speaker_turn_gate.run_gate(run_dir)
	assert gate_result["status"] == "PASS"
	return manifest_path


def _write_preflight_gate_result(run_dir: Path, manifest_path: Path, status: str, row_status: str | None = None, **extra: Any) -> None:
	row_status = row_status or status
	_write_json(run_dir / "05-vibevoice-preflight-audition/preflight_audition_result.json", {
		"schema_version": "worldview-china-vibevoice-preflight-audition-result.v1",
		"status": status,
		"script_sha256": _sha256(run_dir / "podcast_script.md"),
		"voice_prompt_manifest": str(manifest_path),
		"voice_prompt_manifest_sha256": _sha256(manifest_path),
		"voice_prompt_policy": "qwen_chinese_required",
		"voice_context_policy": "locked_two_speaker_roster",
		"rows": [{"chunk_id": "chunk_001", "raw_level_status": row_status}],
		**extra,
	})
	_write_json(run_dir / "05-vibevoice-preflight-audition/chunk_plan.json", {
		"schema_version": "worldview-china-vibevoice-preflight-chunk-plan.v1",
		"split_long_turn_max_chars": vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
		"fixed_chunk_plan_json": None,
	})


def _run_vibevoice_chunks_full_until_gate(run_dir: Path) -> dict[str, Any]:
	return vibevoice_chunks.run_chunks(
		run_dir=run_dir,
		force=False,
		force_chunk_ids=set(),
		dry_run=False,
		no_progress_bar=True,
		split_chunk_indices=set(),
		split_max_chars=650,
		split_all_chunks=False,
		split_long_turn_max_chars=vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
		fixed_chunk_plan_json=None,
		postprocess_min_source_mean_volume=-30.0,
		postprocess_min_source_max_volume=vibevoice_chunks.DEFAULT_POSTPROCESS_MIN_SOURCE_MAX_VOLUME,
		voice_prompt_policy="qwen_chinese_required",
		generation_runner="legacy_per_chunk",
		voice_context_policy="locked_two_speaker_roster",
		device="cpu",
		torch_dtype="float32",
		attn_implementation="eager",
		generation_seed=42,
	)


def test_pre_tts_frozen_contract_passes_and_detects_stale_script(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_make_two_speaker_clean_script_run(run_dir)
	_write_pre_tts_contract_inputs(run_dir)

	result = pre_tts_contract.run_contract(run_dir, force=True)

	assert result["status"] == "PASS"
	assert "text_change" in result["dependency_rebuild_contract"]
	pre_tts_contract.validate_contract_gate(run_dir)

	(run_dir / "podcast_script.md").write_text("Speaker 0: 审核之后被改动的文本。\n", encoding="utf-8")
	with pytest.raises(RuntimeError, match="04d pre-TTS frozen contract is stale"):
		pre_tts_contract.validate_contract_gate(run_dir)

	plan = rebuild_planner.plan_rebuild(run_dir, "auto")
	assert plan["status"] == "REBUILD_REQUIRED"
	assert plan["effective_scope"] == "text"
	assert plan["required_rebuild_chain"][0] == "03c-translation-semantic-qa"
	assert "05-vibevoice-chunks" in plan["required_rebuild_chain"]


def test_vibevoice_chunks_requires_pre_tts_frozen_contract_when_04c_exists(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_make_two_speaker_clean_script_run(run_dir)
	_write_pre_tts_contract_inputs(run_dir)

	with pytest.raises(RuntimeError, match="04d pre-TTS frozen contract"):
		vibevoice_chunks.run_chunks(
			run_dir=run_dir,
			force=False,
			force_chunk_ids=set(),
			dry_run=True,
			no_progress_bar=True,
			split_chunk_indices=set(),
			split_max_chars=650,
			split_all_chunks=False,
			split_long_turn_max_chars=vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
			fixed_chunk_plan_json=None,
			postprocess_min_source_mean_volume=-30.0,
			postprocess_min_source_max_volume=vibevoice_chunks.DEFAULT_POSTPROCESS_MIN_SOURCE_MAX_VOLUME,
			voice_prompt_policy="qwen_chinese_required",
			generation_runner="resident_batch",
			voice_context_policy="locked_two_speaker_roster",
			device=vibevoice_chunks.DEFAULT_VIBEVOICE_DEVICE,
			torch_dtype=vibevoice_chunks.DEFAULT_VIBEVOICE_TORCH_DTYPE,
			attn_implementation=vibevoice_chunks.DEFAULT_VIBEVOICE_ATTN_IMPLEMENTATION,
			generation_seed=42,
		)


def test_vibevoice_preflight_requires_pre_tts_contract_before_model_work(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_make_two_speaker_clean_script_run(run_dir)
	with pytest.raises(RuntimeError, match="04d pre-TTS frozen contract"):
		vibevoice_preflight.run_preflight(
			run_dir=run_dir,
			chunk_count=1,
			min_source_max_volume=-12.0,
			yellow_source_max_volume=-15.0,
			min_source_mean_volume=-30.0,
			voice_prompt_policy="qwen_chinese_required",
			voice_context_policy="locked_two_speaker_roster",
			device=vibevoice_chunks.DEFAULT_VIBEVOICE_DEVICE,
			torch_dtype=vibevoice_chunks.DEFAULT_VIBEVOICE_TORCH_DTYPE,
			attn_implementation=vibevoice_chunks.DEFAULT_VIBEVOICE_ATTN_IMPLEMENTATION,
			generation_seed=42,
			no_progress_bar=True,
			force=False,
			split_long_turn_max_chars=vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
			fixed_chunk_plan_json=None,
		)


def test_speaker_turn_roster_consistency_gate_blocks_host_label_on_guest_answer(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_two_speaker_host_guest_roster(run_dir)
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{
				"segment_index": 1,
				"source_start": "00:00:01",
				"source_end": "00:00:12",
				"speaker": "Speaker 1",
				"source_text": "No no don't get me wrong. I think it is absolutely imperative for us to engage closely with these geographies, and I will explain with one example.",
				"zh_text": "不，不，别误会。我认为我们绝对必须和这些地区深入打交道。我解释一下，给你举个例子。",
			},
		],
	})
	script_format.format_script(run_dir)
	result = speaker_turn_gate.run_gate(run_dir)
	assert result["status"] == "FAIL"
	assert any(finding["rule_id"] == "host_label_on_long_guest_answer" for finding in result["findings"])


def test_speaker_turn_roster_consistency_gate_passes_clean_host_question_guest_answer(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_two_speaker_host_guest_roster(run_dir)
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{
				"segment_index": 1,
				"source_start": "00:00:01",
				"source_end": "00:00:04",
				"speaker": "Speaker 1",
				"source_text": "Tell me, why does this matter for India?",
				"zh_text": "你告诉我，这为什么对印度重要？",
			},
			{
				"segment_index": 2,
				"source_start": "00:00:04",
				"source_end": "00:00:24",
				"speaker": "Speaker 0",
				"source_text": "I think it matters because India needs capital, manufacturing capability, and a wider global imagination.",
				"zh_text": "我认为它很重要，因为印度需要资本、制造能力，也需要更宽的全球想象。",
			},
		],
	})
	script_format.format_script(run_dir)
	result = speaker_turn_gate.run_gate(run_dir)
	assert result["status"] == "PASS"
	assert result["role_inference"]["host_speaker"] == "Speaker 1"
	assert result["role_inference"]["guest_speaker"] == "Speaker 0"


def test_speaker_turn_roster_consistency_gate_allows_guest_explanation_with_embedded_why(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_two_speaker_host_guest_roster(run_dir)
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{
				"segment_index": 1,
				"source_start": "00:02:05",
				"source_end": "00:02:15",
				"speaker": "Speaker 0",
				"source_text": "And I'll come back to why I'm saying this. A large constituency. I said I didn't say all of them.",
				"zh_text": "我一会儿会回到我为什么这么说。是一个很大的群体，我说的不是所有人。",
			},
		],
	})
	script_format.format_script(run_dir)
	result = speaker_turn_gate.run_gate(run_dir)
	assert result["status"] == "PASS"
	assert not any(finding["rule_id"] == "host_question_assigned_to_guest_voice" for finding in result["findings"])


def test_speaker_turn_roster_consistency_gate_blocks_short_host_question_on_guest(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_two_speaker_host_guest_roster(run_dir)
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{
				"segment_index": 1,
				"source_start": "00:00:01",
				"source_end": "00:00:04",
				"speaker": "Speaker 0",
				"source_text": "Tell me, why does this matter for India?",
				"zh_text": "你告诉我，这为什么对印度重要？",
			},
		],
	})
	script_format.format_script(run_dir)
	result = speaker_turn_gate.run_gate(run_dir)
	assert result["status"] == "FAIL"
	assert any(finding["rule_id"] == "host_question_assigned_to_guest_voice" for finding in result["findings"])


def test_vibevoice_chunks_requires_current_speaker_turn_roster_gate(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_two_speaker_host_guest_roster(run_dir)
	_write_json(run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json", {
		"segments": [
			{
				"segment_index": 1,
				"source_start": "00:00:01",
				"source_end": "00:00:04",
				"speaker": "Speaker 1",
				"source_text": "Tell me, why does this matter?",
				"zh_text": "你告诉我，这为什么重要？",
			},
			{
				"segment_index": 2,
				"source_start": "00:00:04",
				"source_end": "00:00:12",
				"speaker": "Speaker 0",
				"source_text": "I think it matters because this is about investment.",
				"zh_text": "我认为重要，因为这关系到投资。",
			},
		],
	})
	script_format.format_script(run_dir)
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": {
			"Speaker 0": {"vibevoice_name": "Voice0"},
			"Speaker 1": {"vibevoice_name": "Voice1"},
		},
		"voice_distinctness_policy": {
			"status": "PASS_ORIGINAL_CLONED_PAIR",
			"scope": "exactly_two_speakers_only",
			"threshold": 0.90,
		},
	})
	with pytest.raises(RuntimeError, match="03e speaker-turn roster"):
		vibevoice_chunks.run_chunks(
			run_dir=run_dir,
			force=False,
			force_chunk_ids=set(),
			dry_run=True,
			no_progress_bar=True,
			split_chunk_indices=set(),
			split_max_chars=650,
			split_all_chunks=False,
			split_long_turn_max_chars=vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
			fixed_chunk_plan_json=None,
			postprocess_min_source_mean_volume=-30.0,
			postprocess_min_source_max_volume=vibevoice_chunks.DEFAULT_POSTPROCESS_MIN_SOURCE_MAX_VOLUME,
			voice_prompt_policy="qwen_chinese_required",
			generation_runner="resident_batch",
			voice_context_policy="locked_two_speaker_roster",
			device=vibevoice_chunks.DEFAULT_VIBEVOICE_DEVICE,
			torch_dtype=vibevoice_chunks.DEFAULT_VIBEVOICE_TORCH_DTYPE,
			attn_implementation=vibevoice_chunks.DEFAULT_VIBEVOICE_ATTN_IMPLEMENTATION,
			generation_seed=42,
		)


def test_vibevoice_chunks_requires_preflight_before_full_generation(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_make_two_speaker_clean_script_run(run_dir)
	_write_passing_pre_tts_contract(run_dir)
	with pytest.raises(RuntimeError, match="05-vibevoice-preflight-audition"):
		_run_vibevoice_chunks_full_until_gate(run_dir)


def test_vibevoice_chunks_rejects_stale_preflight_script_hash(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	manifest_path = _make_two_speaker_clean_script_run(run_dir)
	_write_passing_pre_tts_contract(run_dir)
	_write_preflight_gate_result(run_dir, manifest_path, "PASS")
	result_path = run_dir / "05-vibevoice-preflight-audition/preflight_audition_result.json"
	result = _read_json(result_path)
	result["script_sha256"] = "stale"
	_write_json(result_path, result)
	with pytest.raises(RuntimeError, match="stale for podcast_script.md"):
		_run_vibevoice_chunks_full_until_gate(run_dir)


def test_vibevoice_chunks_rejects_yellow_preflight_without_secondary_qa(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	manifest_path = _make_two_speaker_clean_script_run(run_dir)
	_write_passing_pre_tts_contract(run_dir)
	_write_preflight_gate_result(run_dir, manifest_path, "YELLOW")
	with pytest.raises(RuntimeError, match="status is YELLOW"):
		_run_vibevoice_chunks_full_until_gate(run_dir)


def test_vibevoice_preflight_gate_accepts_yellow_with_secondary_qa(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	manifest_path = _make_two_speaker_clean_script_run(run_dir)
	_write_preflight_gate_result(
		run_dir,
		manifest_path,
		"YELLOW",
		secondary_qa={"status": "PASS", "reviewer": "test", "criteria": {"spot_listening": "PASS"}},
	)
	vibevoice_chunks._validate_vibevoice_preflight_audition_gate(
		run_dir,
		str(manifest_path),
		"qwen_chinese_required",
		"locked_two_speaker_roster",
		vibevoice_chunks.DEFAULT_SPLIT_LONG_TURN_MAX_CHARS,
		None,
	)


def test_vibevoice_chunk_state_reuses_existing_raw_for_postprocess_only(tmp_path: Path) -> None:
	final_wav = tmp_path / "audio/final_podcast.wav"
	raw_wav = tmp_path / "audio/vibevoice_raw/vibevoice_dialogue_generated.wav"
	raw_wav.parent.mkdir(parents=True)
	raw_wav.write_bytes(b"raw")
	state = vibevoice_chunks._chunk_generation_state(final_wav, raw_wav, force=False, force_chunk=False)
	assert state == {"needs_generation": False, "needs_postprocess": True}
	forced = vibevoice_chunks._chunk_generation_state(final_wav, raw_wav, force=False, force_chunk=True)
	assert forced == {"needs_generation": True, "needs_postprocess": True}


def test_vibevoice_chunk_state_reprocesses_newer_raw_than_final(tmp_path: Path) -> None:
	final_wav = tmp_path / "audio/final_podcast.wav"
	raw_wav = tmp_path / "audio/vibevoice_raw/vibevoice_dialogue_generated.wav"
	raw_wav.parent.mkdir(parents=True)
	final_wav.parent.mkdir(parents=True, exist_ok=True)
	final_wav.write_bytes(b"old-final")
	raw_wav.write_bytes(b"new-raw")
	old_time = final_wav.stat().st_mtime - 10
	new_time = final_wav.stat().st_mtime + 10
	os.utime(final_wav, (old_time, old_time))
	os.utime(raw_wav, (new_time, new_time))
	state = vibevoice_chunks._chunk_generation_state(final_wav, raw_wav, force=False, force_chunk=False)
	assert state == {"needs_generation": False, "needs_postprocess": True}


def test_vibevoice_resident_reports_are_archived_and_effective_report_covers_final_chunks(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	node_dir = run_dir / "05-vibevoice-chunks"
	report_path = node_dir / "resident_batch_report.json"
	_write_json(report_path, {
		"schema_version": "resident",
		"job_count": 2,
		"jobs": [
			{"job_id": "chunk_001", "status": "pass", "speaker_mode": "dialogue", "speaker_names": ["Voice0", "Voice1"]},
			{"job_id": "chunk_002", "status": "pass", "speaker_mode": "dialogue", "speaker_names": ["Voice0", "Voice1"]},
		],
	})
	archived = vibevoice_chunks._archive_existing_resident_report(node_dir, report_path, "formal_generation", [])
	assert archived is not None
	_write_json(report_path, {
		"schema_version": "resident",
		"job_count": 1,
		"jobs": [
			{"job_id": "chunk_002", "status": "pass", "speaker_mode": "dialogue", "speaker_names": ["Voice0", "Voice1"]},
		],
	})
	registered = vibevoice_chunks._register_current_resident_report(node_dir, report_path, "formal_generation", ["chunk_002"])
	assert registered is not None

	effective_rel = vibevoice_chunks._write_effective_resident_batch_report(node_dir, ["chunk_001", "chunk_002"])
	effective = _read_json(run_dir / effective_rel)
	assert effective["status"] == "PASS"
	assert effective["job_count"] == 2
	assert [job["job_id"] for job in effective["jobs"]] == ["chunk_001", "chunk_002"]
	assert effective["jobs"][0]["source_resident_batch_report"] != effective["jobs"][1]["source_resident_batch_report"]
	index = _read_json(node_dir / "resident_batch_runs/index.json")
	assert [entry["role"] for entry in index["reports"]] == ["archived_before_overwrite", "completed_batch_snapshot"]
	assert index["reports"][0]["job_ids"] == ["chunk_001", "chunk_002"]


def test_vibevoice_resident_batch_output_coverage_fails_fast_for_missing_raw(tmp_path: Path) -> None:
	node_dir = tmp_path / "run/05-vibevoice-chunks"
	jobs = [
		{"job_id": "chunk_016", "output_dir": str(node_dir / "chunks/chunk_016/audio/vibevoice_raw")},
	]
	with pytest.raises(RuntimeError, match="chunk_016.*--force-chunk-id chunk_016"):
		vibevoice_chunks._assert_resident_batch_raw_outputs(node_dir, jobs)
	report = _read_json(node_dir / "resident_batch_output_coverage.json")
	assert report["status"] == "FAIL"
	assert report["failure_count"] == 1
	assert report["failures"][0]["job_id"] == "chunk_016"


def test_vibevoice_logged_command_records_start_and_finish(tmp_path: Path) -> None:
	code = vibevoice_chunks._run_logged(
		[sys.executable, "-c", "print('ok')"],
		tmp_path,
		tmp_path / "stdout.txt",
		tmp_path / "stderr.txt",
		tmp_path / "progress.md",
		"unit command",
	)
	assert code == 0
	progress = (tmp_path / "progress.md").read_text(encoding="utf-8")
	assert "unit command started" in progress
	assert "unit command finished" in progress
	assert "elapsed_sec=" in progress


def test_vibevoice_drops_tiny_tts_filler_turns() -> None:
	turns = [
		{"turn_index": 1, "speaker": "Speaker 0", "text": "是的。", "char_count": 3},
		{"turn_index": 2, "speaker": "Speaker 0", "text": "你能再说一遍吗？", "char_count": 8},
		{"turn_index": 3, "speaker": "Speaker 0", "text": "和", "char_count": 1},
		{"turn_index": 4, "speaker": "Speaker 1", "text": "这是一段正常回答。", "char_count": 9},
	]
	kept, dropped = vibevoice_chunks._drop_tiny_tts_turns(turns)
	assert [turn["text"] for turn in kept] == ["你能再说一遍吗？", "这是一段正常回答。"]
	assert [turn["turn_index"] for turn in kept] == [1, 2]
	assert [turn["text"] for turn in dropped] == ["是的。", "和"]


def test_selected_video_registry_filters_recent_duplicate_best_video(tmp_path: Path) -> None:
	registry_path = tmp_path / "selected-videos.json"
	now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
	selected_registry.record_video(
		registry_path,
		{
			"video_id": "duplicate123",
			"url": "https://www.youtube.com/watch?v=duplicate123",
			"title": "Already selected",
			"channel": "Channel A",
		},
		tmp_path / "old_run",
		"test",
		selected_at=now - timedelta(days=1),
	)
	selected_registry.record_video(
		registry_path,
		{
			"video_id": "expired999",
			"url": "https://www.youtube.com/watch?v=expired999",
			"title": "Expired selection",
		},
		tmp_path / "expired_run",
		"test",
		selected_at=now - timedelta(days=7),
	)
	recent = selected_registry.recent_payload(registry_path, 5, now=now)
	assert recent["recent_video_ids"] == ["duplicate123"]
	shortlist = {
		"schema_version": "test",
		"status": "BEST_VIDEO",
		"best_video": {
			"video_id": "duplicate123",
			"url": "https://www.youtube.com/watch?v=duplicate123",
			"title": "Already selected",
			"decision": "accept",
		},
		"ranked": [
			{
				"rank": 1,
				"video_id": "duplicate123",
				"url": "https://www.youtube.com/watch?v=duplicate123",
				"title": "Already selected",
				"decision": "accept",
			},
			{
				"rank": 2,
				"video_id": "fresh456",
				"url": "https://www.youtube.com/watch?v=fresh456",
				"title": "Fresh candidate",
				"decision": "accept",
			},
		],
	}
	filtered, report = selected_registry.filter_payload(shortlist, registry_path, 5, now=now)
	assert report["duplicate_video_ids"] == ["duplicate123"]
	assert filtered["status"] == "BEST_VIDEO_REPLACED_AFTER_RECENT_DEDUPE"
	assert filtered["best_video"]["video_id"] == "fresh456"
	assert filtered["ranked"][0]["recent_selection_duplicate"] is True
	assert filtered["ranked"][1]["recent_selection_duplicate"] is False


def test_source_voice_prompts_discovers_unlabeled_transcript_json_speaker_changes(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	segments: list[dict[str, Any]] = [
		{"start_sec": 0.0, "end_sec": 5.0, "text": "Host opens the interview"},
		{"start_sec": 5.0, "end_sec": 10.0, "text": "Host asks a question"},
		{"start_sec": 10.0, "end_sec": 10.1, "text": ">> Guest begins answering"},
		{"start_sec": 10.1, "end_sec": 20.0, "text": "Guest explains the background"},
		{"start_sec": 20.0, "end_sec": 20.1, "text": ">> Host follows up"},
		{"start_sec": 20.1, "end_sec": 31.0, "text": "Host asks about China"},
		{"start_sec": 31.0, "end_sec": 31.1, "text": ">> Guest returns"},
		{"start_sec": 31.1, "end_sec": 42.0, "text": "Guest gives a detailed answer"},
	]
	_write_json(run_dir / "02-source-capture/source_transcript.en.json", {
		"schema_version": "test",
		"segments": segments,
	})
	source, timeline = source_voice_prompts._discover_timeline(run_dir, None)
	assert source.endswith("source_transcript.en.json:unlabeled_caption_speaker_change_fallback")
	assert len(timeline) == 4
	assert [segment.speaker for segment in timeline] == ["Speaker 0", "Speaker 1", "Speaker 0", "Speaker 1"]
	assert timeline[0].start == 0.0
	assert timeline[-1].end == 42.0
	assert "Guest begins answering" in timeline[1].text


def test_source_translation_dedupes_rolling_caption_overlap() -> None:
	transcript = {
		"transcript": {
			"text": "",
			"segments": [
				{
					"speaker": "Speaker 0",
					"start": 0.0,
					"duration": 30.0,
					"text": (
						"This week joining us is Imm Abdullah "
						"This week joining us is Imm Abdullah Chung. "
						"He is joining us from Taiwan. Now "
						"He is joining us from Taiwan. Now this is a story "
						"this is a story about a young generation "
						"this is a story about a young generation Muslim."
					),
				},
				{
					"speaker": "Speaker 1",
					"start": 30.0,
					"duration": 10.0,
					"text": (
						">> What's the population? What's the population? "
						"Okay. So if we break it down, Okay. So if we break it down,"
					),
				},
			],
		},
	}
	turns = source_translation._parse_source_turns(transcript)
	assert len(turns) == 2
	assert turns[0]["speaker"] == "Speaker 0"
	assert turns[1]["speaker"] == "Speaker 1"
	assert turns[0]["source_text"].count("This week joining us is Imm Abdullah") == 1
	assert turns[0]["source_text"].count("He is joining us from Taiwan") == 1
	assert turns[0]["source_text"].count("this is a story about a young generation") == 1
	assert turns[1]["source_text"].count("What's the population") == 1
	assert turns[1]["source_text_cleaned_char_count"] < turns[1]["source_text_raw_char_count"]


def test_source_translation_prefers_complete_plain_txt_over_short_json(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "02-source-capture/source_transcript.en.json", {
		"schema_version": "test",
		"transcript": {
			"text": "Short duplicate caption",
			"segments": [{"text": "Short duplicate caption", "start": 0.0, "duration": 5.0, "speaker": "Speaker 0"}],
		},
	})
	(run_dir / "02-source-capture/source_transcript.en.txt").write_text(
		"Host opening. " * 200 + ">> Guest answer. " * 200,
		encoding="utf-8",
	)
	_write_json(run_dir / "02-source-capture/source_metadata.json", {"duration_seconds": 600})
	transcript, path, mode = source_translation._load_source_transcript(run_dir)
	assert path.name == "source_transcript.en.txt"
	assert mode == "plain_txt_preferred_over_shorter_json"
	turns = source_translation._parse_source_turns(transcript)
	assert {turn["speaker"] for turn in turns} == {"Speaker 0", "Speaker 1"}
	assert turns[-1]["source_end_sec"] > 250


def test_source_translation_dedupes_repeated_plain_caption_marker_lines() -> None:
	text = "\n".join([
		"Host opens the show.",
		"Host opens the show.",
		">> Guest answers the question.",
		">> Guest answers the question.",
		">> Guest answers the question.",
		"with more detail.",
		"with more detail.",
		">> Host follows up.",
		">> Host follows up.",
	])
	turns = source_translation._parse_plain_source_turns(text, duration_sec=90.0)
	assert [turn["speaker"] for turn in turns] == ["Speaker 0", "Speaker 1", "Speaker 0"]
	assert turns[0]["source_text"] == "Host opens the show."
	assert turns[1]["source_text"] == "Guest answers the question. with more detail."
	assert turns[2]["source_text"] == "Host follows up."


def test_source_translation_dedupes_adjacent_short_prefix_turns() -> None:
	turns = source_translation._dedupe_adjacent_source_turns([
		{
			"source_turn_index": 1,
			"speaker": "Speaker 1",
			"source_start_sec": 10.0,
			"source_end_sec": 11.0,
			"source_start": "00:00:10",
			"source_end": "00:00:11",
			"source_text": "So subhan Allah 300,000 Muslims in Taiwan",
		},
		{
			"source_turn_index": 2,
			"speaker": "Speaker 0",
			"source_start_sec": 11.0,
			"source_end_sec": 20.0,
			"source_start": "00:00:11",
			"source_end": "00:00:20",
			"source_text": "So subhan Allah 300,000 Muslims in Taiwan, how many Taiwanese people are there?",
		},
	])
	assert len(turns) == 1
	assert turns[0]["source_turn_index"] == 1
	assert turns[0]["source_start_sec"] == 10.0
	assert "how many Taiwanese people" in turns[0]["source_text"]


def test_source_translation_pretranslation_cleanup_drops_ads_and_reduces_fillers() -> None:
	ad_text, original_ad_text, dropped_as_ad, ad_reasons = source_translation._prepare_source_text_for_translation(
		"[Music] This episode is sponsored by Provision Capital. Visit provisioncap.com and use code CHINA."
	)
	assert ad_text == ""
	assert original_ad_text
	assert dropped_as_ad is True
	assert {"sponsor_or_ad", "contact_or_url", "known_ad_terms"} <= set(ad_reasons)

	cleaned, _original_text, dropped, reasons = source_translation._prepare_source_text_for_translation(
		"I mean, you know, uh, the Hawaii Muslims in Taiwan have hala restaurants and Lano beef noodles "
		"over the last 50 100 years."
	)
	assert dropped is False
	assert reasons == []
	assert "you know" not in cleaned.lower()
	assert "i mean" not in cleaned.lower()
	assert "uh" not in cleaned.lower()
	assert "Hui Muslims" in cleaned
	assert "halal restaurants" in cleaned
	assert "Lanzhou beef noodles" in cleaned
	assert "50 to 100 years" in cleaned

	visit_cleaned, _visit_original, visit_dropped, _visit_reasons = source_translation._prepare_source_text_for_translation(
		"When you visit Taiwan, you can see local communities and restaurants."
	)
	assert visit_dropped is False
	assert "visit Taiwan" in visit_cleaned
	go_cleaned, _go_original, go_dropped, _go_reasons = source_translation._prepare_source_text_for_translation(
		"Many business owners go to China to understand the market directly."
	)
	assert go_dropped is False
	assert "go to China" in go_cleaned
	site_cleaned, _site_original, site_dropped, _site_reasons = source_translation._prepare_source_text_for_translation(
		"They discussed how Amazon.com and Chinese platforms changed cross-border retail."
	)
	assert site_dropped is False
	assert "Amazon" in site_cleaned
	assert "com" in site_cleaned


def test_source_translation_splits_post_cold_open_cta_question_and_answer(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "02a-speaker-census/speaker_roster.json", {
		"schema_version": "worldview-china-speaker-census.v1",
		"status": "frozen",
		"speaker_count": 2,
		"voice_count": 2,
		"speakers": {
			"Speaker 0": {
				"role": "guest_or_speaker_0",
				"description": "Male guest and primary expert voice answering most questions.",
			},
			"Speaker 1": {
				"role": "host_or_speaker_1",
				"description": "Male host/interviewer asks short questions and delivers the subscribe CTA.",
			},
		},
	})
	text = (
		"before we start today's podcast if you have found anything valuable from this channel please subscribe "
		"it's free it takes less than a minute, but it means a lot to us. And to listen to the audio experience "
		"of this episode, please follow us on Spotify. What happened with America? What happened? Like we were "
		"just we were in good terms or are we still in good? I don't know. It's like dicey in my head. "
		"So let me first start with the top line and then I'll come back to the top line."
	)
	transcript = {
		"transcript": {
			"text": text,
			"segments": [{
				"speaker": "Speaker 0",
				"start": 0.0,
				"duration": 61.599,
				"text": text,
			}],
		},
	}
	turns = source_translation._parse_source_turns(transcript, run_dir=run_dir)
	assert len(turns) == 3
	assert [turn["speaker"] for turn in turns] == ["Speaker 1", "Speaker 1", "Speaker 0"]
	assert turns[0]["source_text"].startswith("Before we start today's podcast")
	assert turns[0]["pre_translation_cleanup"]["source_opening_bridge_inserted"] is True
	assert turns[0]["pre_translation_cleanup"]["removed_opening_cta"] is True
	assert turns[1]["source_text"].startswith("What happened with America?")
	assert turns[2]["source_text"].startswith("So let me first start")
	assert 0.0 < turns[1]["source_start_sec"] < turns[2]["source_start_sec"]
	assert turns[2]["source_start_sec"] < turns[2]["source_end_sec"]


def test_source_translation_repairs_two_speaker_host_guest_label_flips(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "02a-speaker-census/speaker_roster.json", {
		"schema_version": "worldview-china-speaker-census.v1",
		"status": "frozen",
		"speaker_count": 2,
		"voice_count": 2,
		"speakers": {
			"Speaker 0": {
				"role": "guest_or_speaker_0",
				"description": "Male guest, primary expert voice answering most questions.",
			},
			"Speaker 1": {
				"role": "host_or_speaker_1",
				"description": "Male host/interviewer, asks short questions.",
			},
		},
	})
	transcript = {
		"transcript": {
			"text": "",
			"segments": [
				{
					"speaker": "Speaker 1",
					"start": 90.0,
					"duration": 30.0,
					"text": (
						"Right. So look let's be very clear. The state continues to engage with us, "
						"and we have to be honest about the hostile White House."
					),
				},
				{
					"speaker": "Speaker 0",
					"start": 120.0,
					"duration": 3.0,
					"text": "Really? Do they like us?",
				},
			],
		},
	}
	turns = source_translation._parse_source_turns(transcript, run_dir=run_dir)
	assert [turn["speaker"] for turn in turns] == ["Speaker 0", "Speaker 1"]
	assert turns[0]["pre_translation_cleanup"]["speaker_repair"] == "long_or_answer_like_turn_to_guest"
	assert turns[1]["pre_translation_cleanup"]["speaker_repair"] == "short_host_question_to_host"


def test_translation_semantic_qa_flags_bad_translation_artifacts(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"schema_version": "worldview-china-source-translation.v1",
		"content_coverage": "full_translation",
		"segments": [
			{
				"segment_index": 1,
				"source_turn_index": 1,
				"speaker": "Speaker 0",
				"source_start": "00:01:27",
				"source_end": "00:01:34",
				"source_text": "This episode is sponsored by Provision Capital. Visit provisioncap.com.",
				"zh_text": "呃，你知道，你知道，我的意思是，这300,000人实际上有多少人口，但是你可以实际感受到。",
			},
				{
					"segment_index": 2,
					"source_turn_index": 2,
					"speaker": "Speaker 1",
					"source_start": "00:02:00",
					"source_end": "00:02:12",
					"source_text": "Hui Muslims have halal restaurants and Lanzhou beef noodles.",
					"zh_text": "胡用户界面有按摩过的哈拉餐厅，过去50100年来一直如此，所以",
				},
				{
					"segment_index": 3,
					"source_turn_index": 3,
					"speaker": "Speaker 0",
					"source_start": "00:02:13",
					"source_end": "00:02:20",
					"source_text": "But I am just saying this as a pilot exercise.",
					"zh_text": "ButImjustsayingjustasapilotexercisepeoplelookthere",
				},
		],
	})
	result = translation_semantic_qa.run_review(run_dir, stage="test")
	assert result["status"] == "FAIL"
	rule_ids = {finding["rule_id"] for finding in result["findings"]}
	assert {
		"comma_thousands_number",
		"dangling_population_question",
		"dense_spoken_filler",
		"machine_translated_hui",
			"machine_translated_halal",
			"broken_year_range",
			"untranslated_latin_run_in_zh_text",
			"dangling_connector_end",
			"source_ad_text_not_removed",
		} <= rule_ids


def test_translation_semantic_qa_accepts_clean_translation(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"schema_version": "worldview-china-source-translation.v1",
		"content_coverage": "full_translation",
		"segments": [
			{
				"segment_index": 1,
				"source_turn_index": 1,
				"speaker": "Speaker 0",
				"source_start": "00:01:27",
				"source_end": "00:01:34",
				"source_text": "There are about 300,000 Muslims in Taiwan.",
				"zh_text": "中国台湾大约有30万穆斯林，这个数字放在人口结构里不算大，但在当地社区里能被真实看见。",
			},
			{
				"segment_index": 2,
				"source_turn_index": 2,
				"speaker": "Speaker 1",
				"source_start": "00:02:00",
				"source_end": "00:02:12",
				"source_text": "Hui Muslims have halal restaurants and Lanzhou beef noodles.",
				"zh_text": "他提到，在当地也能看到回族穆斯林经营的清真餐馆，以及兰州牛肉面这样的日常生活场景。",
			},
		],
	})
	_write_translation_reading_review(run_dir)
	result = translation_semantic_qa.run_review(run_dir, stage="test")
	assert result["status"] == "PASS"
	assert result["summary"]["fail_findings"] == 0
	assert result["summary"]["qualitative_reading_review_status"] == "PASS"


def test_translation_semantic_qa_requires_qualitative_reading_review(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"schema_version": "worldview-china-source-translation.v1",
		"content_coverage": "full_translation",
		"segments": [{
			"segment_index": 1,
			"source_turn_index": 1,
			"speaker": "Speaker 0",
			"source_start": "00:00:00",
			"source_end": "00:00:10",
			"source_text": "China's economy remains complex.",
			"zh_text": "中国经济仍然很复杂，但这段表达整体是清楚的。",
		}],
	})
	result = translation_semantic_qa.run_review(run_dir, stage="test")
	assert result["status"] == "FAIL"
	assert result["summary"]["qualitative_reading_review_status"] == "MISSING"
	assert any(finding["rule_id"] == "missing_qualitative_reading_review" for finding in result["findings"])
	assert (run_dir / "03c-translation-semantic-qa/translation-reading-review-input.md").exists()
	assert (run_dir / "03c-translation-semantic-qa/translation-reading-review-template.json").exists()


def test_translation_semantic_qa_blocks_skipped_post_cold_open_opening(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "02-source-capture/source_transcript.en.json", {
		"schema_version": "test",
		"transcript": {
			"segments": [{
				"speaker": "Speaker 0",
				"start": 0.0,
				"duration": 61.599,
				"text": (
					"before we start today's podcast please subscribe and follow us on Spotify. "
					"What happened with America? So let me first start with the top line."
				),
			}],
		},
	})
	translation_path = run_dir / "03-source-translation/source_transcript.zh.json"
	_write_json(translation_path, {
		"schema_version": "worldview-china-source-translation.v1",
		"content_coverage": "full_translation",
		"segments": [{
			"segment_index": 1,
			"source_turn_index": 1,
			"speaker": "Speaker 0",
			"source_start": "00:00:18",
			"source_start_sec": 18.0,
			"source_end": "00:00:30",
			"source_text": "What happened with America?",
			"zh_text": "美国到底怎么了？",
		}],
	})
	_write_translation_reading_review(run_dir, translation_path)
	result = translation_semantic_qa.run_review(run_dir, stage="test")
	assert result["status"] == "FAIL"
	assert any(
		finding["rule_id"] == "post_cold_open_opening_skipped_after_cta_cleanup"
		for finding in result["findings"]
	)


def test_translation_semantic_qa_skips_post_cold_open_gate_for_non_initial_series_episode(tmp_path: Path) -> None:
	run_dir = tmp_path / "run" / "04b-series-episodes" / "episode_002"
	_write_json(run_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"episode_index": 2,
		"episode_count": 2,
	})
	_write_json(run_dir / "02-source-capture/source_transcript.en.json", {
		"schema_version": "test",
		"transcript": {
			"segments": [{
				"speaker": "Speaker 0",
				"start": 0.0,
				"duration": 61.599,
				"text": (
					"before we start today's podcast please subscribe and follow us on Spotify. "
					"What happened with America? So let me first start with the top line."
				),
			}],
		},
	})
	translation_path = run_dir / "03-source-translation/source_transcript.zh.json"
	_write_json(translation_path, {
		"schema_version": "worldview-china-source-translation.v1",
		"content_coverage": "full_translation",
		"segments": [{
			"segment_index": 1,
			"source_turn_index": 110,
			"speaker": "Speaker 0",
			"source_start": "00:43:32",
			"source_start_sec": 2612.0,
			"source_end": "00:44:54",
			"source_text": "Look, I would argue that Indonesia is one of our most important future partners.",
			"zh_text": "看，我认为印度尼西亚会是印度未来最重要的伙伴之一。",
		}],
	})
	_write_translation_reading_review(run_dir, translation_path)
	result = translation_semantic_qa.run_review(run_dir, stage="test")
	assert result["status"] == "PASS"
	assert not any(
		finding["rule_id"] == "post_cold_open_opening_skipped_after_cta_cleanup"
		for finding in result["findings"]
	)


def test_translation_semantic_qa_accepts_post_cold_open_opening_bridge(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_json(run_dir / "02-source-capture/source_transcript.en.json", {
		"schema_version": "test",
		"transcript": {
			"segments": [{
				"speaker": "Speaker 0",
				"start": 0.0,
				"duration": 61.599,
				"text": (
					"before we start today's podcast please subscribe and follow us on Spotify. "
					"What happened with America? So let me first start with the top line."
				),
			}],
		},
	})
	translation_path = run_dir / "03-source-translation/source_transcript.zh.json"
	_write_json(translation_path, {
		"schema_version": "worldview-china-source-translation.v1",
		"content_coverage": "full_translation",
		"segments": [
			{
				"segment_index": 1,
				"source_turn_index": 1,
				"speaker": "Speaker 1",
				"source_start": "00:00:00",
				"source_start_sec": 0.0,
				"source_end": "00:00:18",
				"source_text": "Before we start today's podcast, here is a brief opening note. Then we move into today's question.",
				"zh_text": "今天的播客开始前，先做一个简短开场，然后进入今天的问题。",
				"pre_translation_cleanup": {
					"source_opening_bridge_inserted": True,
					"removed_opening_cta": True,
				},
			},
			{
				"segment_index": 2,
				"source_turn_index": 2,
				"speaker": "Speaker 1",
				"source_start": "00:00:18",
				"source_start_sec": 18.0,
				"source_end": "00:00:30",
				"source_text": "What happened with America?",
				"zh_text": "美国到底怎么了？",
			},
		],
	})
	_write_translation_reading_review(run_dir, translation_path)
	result = translation_semantic_qa.run_review(run_dir, stage="test")
	assert result["status"] == "PASS"


def _write_minimal_series_episode_runtime_contracts(episode_dir: Path) -> None:
	locked_speaker_names = ["Voice0", "Voice1"]
	_write_json(episode_dir / "02a-speaker-census/speaker_roster.json", {
		"status": "frozen",
		"speaker_count": 2,
		"voice_count": 2,
		"analysis_window_sec": 360.0,
		"speakers": {
			"Speaker 0": {"description": "host"},
			"Speaker 1": {"description": "guest"},
		},
	})
	_write_json(episode_dir / "video/render_manifest.json", {
		"subtitle_mode": "burned_ass",
		"visual_mode": "source_video_revoice_episode_segment_burned_subtitles",
		"series_episode": True,
	})
	_write_json(episode_dir / "audio/audio_manifest.json", {
		"voice_context_policy": "locked_two_speaker_roster",
		"speaker_voices": {"Speaker 0": "Voice0", "Speaker 1": "Voice1"},
		"chunks": [{
			"chunk_id": "chunk_001",
			"vibevoice_mode": "dialogue",
			"speaker_names": locked_speaker_names,
		}],
	})
	_write_json(episode_dir / "05-vibevoice-chunks/chunk_plan.json", {
		"voice_context_policy": "locked_two_speaker_roster",
		"chunks": [{
			"chunk_id": "chunk_001",
			"vibevoice_mode": "dialogue",
			"speaker_names": locked_speaker_names,
		}],
	})
	_write_json(episode_dir / "11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json", {
		"status": "APPROVED",
	})
	_write_process_review(episode_dir)


def _write_minimal_series_final_qa_run(
	run_dir: Path,
	upload_report: dict[str, Any],
	*,
	final_qa_status: str = "PASS",
) -> None:
	series_dir = run_dir / "04b-series-episodes"
	shared_frame = run_dir / "shared.png"
	_write_png(shared_frame)
	episode_dir = series_dir / "episode_001"
	episode_dir.mkdir(parents=True, exist_ok=True)
	title = "嘉宾观察·第1集：主题1"
	schedule = datetime.fromisoformat("2026-06-24T11:00:00+08:00")
	(episode_dir / "video_title.txt").write_text(title + "\n", encoding="utf-8")
	_write_json(episode_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"episode_index": 1,
		"episode_count": 1,
		"series_title_prefix": "嘉宾观察",
		"episode_subtitle": "主题1",
		"episode_order_marker": "第1集",
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
		"video_title": title,
		"scheduled_publish_at": schedule.isoformat(),
		"scheduled_publish_timezone": "Asia/Shanghai",
		"schedule_source": "series_daily_11_17_balanced_ordered_slots",
	})
	_write_json(episode_dir / "cover/cover_title.json", {
		"title_text": "嘉宾观察：主题1",
		"video_title_text": title,
		"cover_title_omits_episode_index": True,
	})
	_write_json(episode_dir / "02d-title-cover/title_cover_manifest.json", {
		"frame_selection": {"path": str(shared_frame)},
	})
	_write_json(episode_dir / "09-final-qa/final-qa-result.json", {"overall_status": final_qa_status})
	_write_minimal_series_episode_runtime_contracts(episode_dir)
	_write_json(episode_dir / "bilibili_upload_metadata.json", {
		"workflow": "worldview-china-podcast-agent",
		"title": title,
		"episode_index": 1,
		"scheduled_publish_at": schedule.isoformat(),
		"schedule_source": "series_daily_11_17_balanced_ordered_slots",
	})
	_write_json(episode_dir / "bilibili_upload_draft_report.json", upload_report)
	_write_json(run_dir / "04b-series-episodes/series_manifest.json", {
		"schema_version": "worldview-china-podcast-series.v1",
		"serial_execution_required": True,
		"parallel_execution_allowed": False,
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
		"bilibili_schedule_source": "series_daily_11_17_balanced_ordered_slots",
		"bilibili_schedule_slots": ["11:00", "17:00"],
		"shared_cover_frame": str(shared_frame),
		"episodes": [{
			"episode_index": 1,
			"episode_run_dir": str(episode_dir),
			"scheduled_publish_at": schedule.isoformat(),
		}],
	})


def test_series_final_qa_passes_when_all_episode_contracts_are_complete(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	series_dir = run_dir / "04b-series-episodes"
	shared_frame = run_dir / "shared.png"
	_write_png(shared_frame)
	first_schedule = datetime.fromisoformat("2026-06-24T11:00:00+08:00")
	episodes: list[dict[str, Any]] = []
	for index in (1, 2):
		episode_dir = series_dir / f"episode_{index:03d}"
		episode_dir.mkdir(parents=True, exist_ok=True)
		title = f"嘉宾观察·第{index}集：主题{index}"
		(run_dir / "run_manifest.json").parent.mkdir(parents=True, exist_ok=True)
		(episode_dir / "video_title.txt").write_text(title + "\n", encoding="utf-8")
		_write_json(episode_dir / "episode_manifest.json", {
			"schema_version": "worldview-china-podcast-series-episode.v1",
			"episode_index": index,
			"episode_count": 2,
			"series_title_prefix": "嘉宾观察",
			"episode_subtitle": f"主题{index}",
			"episode_order_marker": f"第{index}集",
			"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
			"episode_order_marker_template": "第{episode_index}集",
			"video_title": title,
			"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		})
		_write_json(episode_dir / "cover/cover_title.json", {
			"title_text": f"嘉宾观察：主题{index}",
			"video_title_text": title,
			"cover_title_omits_episode_index": True,
		})
		_write_json(episode_dir / "02d-title-cover/title_cover_manifest.json", {
			"frame_selection": {"path": str(shared_frame)},
		})
		_write_json(episode_dir / "09-final-qa/final-qa-result.json", {"overall_status": "PASS"})
		_write_minimal_series_episode_runtime_contracts(episode_dir)
		schedule = first_schedule.replace(hour=11 if index == 1 else 17)
		_write_json(episode_dir / "bilibili_upload_metadata.json", {
			"workflow": "worldview-china-podcast-agent",
			"title": title,
			"episode_index": index,
			"scheduled_publish_at": schedule.isoformat(),
			"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		})
		_write_json(episode_dir / "bilibili_upload_draft_report.json", {
			"status": "SUBMITTED",
			"final_submit_clicked": True,
		})
		episodes.append({
			"episode_index": index,
			"episode_run_dir": str(episode_dir),
			"scheduled_publish_at": schedule.isoformat(),
			"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		})
	_write_json(run_dir / "04b-series-episodes/series_manifest.json", {
		"schema_version": "worldview-china-podcast-series.v1",
		"serial_execution_required": True,
		"parallel_execution_allowed": False,
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
		"bilibili_schedule_source": "series_daily_11_17_balanced_ordered_slots",
		"bilibili_schedule_slots": ["11:00", "17:00"],
		"shared_cover_frame": str(shared_frame),
		"episodes": episodes,
	})
	result = series_qa.run_series_qa(run_dir, require_upload_submitted=True, write_history=False)
	assert result["overall_status"] == "PASS"


def test_series_final_qa_accepts_legacy_bilibili_success_evidence(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_minimal_series_final_qa_run(run_dir, {
		"status": "SUBMITTED",
		"post_submit_state": {
			"text": "稿件投递成功\n视频嘉宾观察·第1集：主题1上传成功",
		},
	})
	result = series_qa.run_series_qa(run_dir, require_upload_submitted=True, write_history=False)
	assert result["overall_status"] == "PASS"


def test_series_final_qa_accepts_user_submit_now_override_for_stale_schedule_seed(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_minimal_series_final_qa_run(run_dir, {
		"status": "SUBMITTED",
		"final_submit_clicked": True,
		"field_verification": {
			"scheduled_publish_at": "not_requested_user_override_submit_now",
		},
		"schedule_override": {
			"reason": "User requested immediate submission because the scheduled time had already passed.",
		},
	})
	metadata_path = run_dir / "04b-series-episodes/episode_001/bilibili_upload_metadata.json"
	metadata = _read_json(metadata_path)
	metadata["scheduled_publish_at"] = None
	metadata["schedule_source"] = "series_first_publish_at_plus_episode_index_hours"
	_write_json(metadata_path, metadata)

	result = series_qa.run_series_qa(run_dir, require_upload_submitted=True, write_history=False)

	assert result["overall_status"] == "PASS"
	assert any("submit-now override" in warning for warning in result["warnings"])


def test_series_final_qa_rejects_submitted_upload_without_final_submit_proof(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_write_minimal_series_final_qa_run(run_dir, {
		"status": "SUBMITTED",
	})
	result = series_qa.run_series_qa(run_dir, require_upload_submitted=True, write_history=False)
	assert result["overall_status"] == "FAIL"
	assert any("final submit proof" in failure for failure in result["failures"])


def test_series_final_qa_rejects_mixed_order_marker_template(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	series_dir = run_dir / "04b-series-episodes"
	shared_frame = run_dir / "shared.png"
	_write_png(shared_frame)
	first_schedule = datetime.fromisoformat("2026-06-24T11:00:00+08:00")
	episodes: list[dict[str, Any]] = []
	for index in (1, 2):
		episode_dir = series_dir / f"episode_{index:03d}"
		episode_dir.mkdir(parents=True, exist_ok=True)
		title = f"嘉宾观察·第{index}集：主题{index}"
		marker_template = "EP{episode_index:02d}" if index == 2 else "第{episode_index}集"
		(episode_dir / "video_title.txt").write_text(title + "\n", encoding="utf-8")
		_write_json(episode_dir / "episode_manifest.json", {
			"schema_version": "worldview-china-podcast-series-episode.v1",
			"episode_index": index,
			"episode_count": 2,
			"series_title_prefix": "嘉宾观察",
			"episode_subtitle": f"主题{index}",
			"episode_order_marker": f"第{index}集",
			"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
			"episode_order_marker_template": marker_template,
			"video_title": title,
			"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		})
		_write_json(episode_dir / "cover/cover_title.json", {
			"title_text": f"嘉宾观察：主题{index}",
			"video_title_text": title,
			"cover_title_omits_episode_index": True,
		})
		_write_json(episode_dir / "02d-title-cover/title_cover_manifest.json", {"frame_selection": {"path": str(shared_frame)}})
		_write_json(episode_dir / "09-final-qa/final-qa-result.json", {"overall_status": "PASS"})
		schedule = first_schedule.replace(hour=11 if index == 1 else 17)
		_write_json(episode_dir / "bilibili_upload_metadata.json", {
			"workflow": "worldview-china-podcast-agent",
			"title": title,
			"episode_index": index,
			"scheduled_publish_at": schedule.isoformat(),
			"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		})
		_write_json(episode_dir / "bilibili_upload_draft_report.json", {
			"status": "SUBMITTED",
			"final_submit_clicked": True,
		})
		episodes.append({
			"episode_index": index,
			"episode_run_dir": str(episode_dir),
			"scheduled_publish_at": schedule.isoformat(),
			"schedule_source": "series_daily_11_17_balanced_ordered_slots",
		})
	_write_json(run_dir / "04b-series-episodes/series_manifest.json", {
		"schema_version": "worldview-china-podcast-series.v1",
		"serial_execution_required": True,
		"parallel_execution_allowed": False,
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
		"bilibili_schedule_source": "series_daily_11_17_balanced_ordered_slots",
		"bilibili_schedule_slots": ["11:00", "17:00"],
		"shared_cover_frame": str(shared_frame),
		"episodes": episodes,
	})
	result = series_qa.run_series_qa(run_dir, require_upload_submitted=True, write_history=False)
	assert result["overall_status"] == "FAIL"
	assert any("order marker template differs from series_manifest" in failure for failure in result["failures"])


def test_final_qa_accepts_series_episode_title_cover_and_episode_segment_render(tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	run_dir = tmp_path / "episode"
	_make_test_video(run_dir / "02-source-capture/youtube-media/source.mp4", duration=1.0)
	_make_silent_wav(run_dir / "02-source-capture/youtube-media/source.wav", duration=1.0)
	_make_silent_wav(run_dir / "audio/final_podcast.wav", duration=1.0)
	_make_test_video(run_dir / "video/final_video.mp4", duration=1.0, size=(2560, 1440))
	_write_png(run_dir / "cover/cover_4k.png", size=(3840, 2160))
	for name in ("opening", "middle", "end"):
		_write_png(run_dir / f"08-source-video-revoice/screenshots/{name}.png")
	_write_json(run_dir / "episode_manifest.json", {
		"schema_version": "worldview-china-podcast-series-episode.v1",
		"series_title_prefix": "嘉宾观察",
		"episode_subtitle": "中国的经济韧性",
		"episode_index": 1,
		"episode_count": 2,
		"episode_order_marker": "第1集",
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
		"video_title": "嘉宾观察·第1集：中国的经济韧性",
	})
	_write_json(run_dir / "02-source-capture/youtube-media/media_manifest.json", {
		"selected_height": 2160,
		"available_max_height": 2160,
		"selected_audio_format": {"format_note": "original default"},
	})
	(run_dir / "02-source-capture/source-video-frame-qa").mkdir(parents=True, exist_ok=True)
	(run_dir / "02-source-capture/source-video-frame-qa/video_form_report.md").write_text(
		"video_podcast_form: PASS\n",
		encoding="utf-8",
	)
	(run_dir / "video_title.txt").write_text("嘉宾观察·第1集：中国的经济韧性\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {
		"title_source": "podcast_source_identity_plus_platform_native_hook",
		"source_identity_label": "嘉宾观察",
		"translated_title_core": "中国的经济韧性",
		"title_text": "嘉宾观察：中国的经济韧性",
		"video_title_text": "嘉宾观察·第1集：中国的经济韧性",
		"cover_title_omits_episode_index": True,
		"attractive_title_policy": {"status": "PASS"},
		"highlight_texts": ["嘉宾观察", "经济韧性"],
	})
	_write_json(run_dir / "cover/image_source_manifest.json", {"image_type": "source_video_frame_background"})
	_write_json(run_dir / "cover/cover_4k.manifest.json", {"layout": {"mode": "center"}})
	_write_json(run_dir / "02d-title-cover/title_cover_manifest.json", {
		"title_layout": "center",
		"title_policy": "series_episode_indexed_video_title_plus_unindexed_cover_title",
	})
	for speaker, voice_name in (("Speaker 0", "Voice0"), ("Speaker 1", "Voice1")):
		ref = run_dir / f"02c-qwen-vibevoice-prompts/registered/{voice_name}.wav"
		_make_silent_wav(ref, duration=5.0)
		registered = run_dir / f"registered/{voice_name}.wav"
		registered.parent.mkdir(parents=True, exist_ok=True)
		shutil.copy2(ref, registered)

	speaker_voices = {
		"Speaker 0": {
			"vibevoice_name": "Voice0",
			"reference_wav": str(run_dir / "02c-qwen-vibevoice-prompts/registered/Voice0.wav"),
			"registered_path": str(run_dir / "registered/Voice0.wav"),
			"sha256": _sha256(run_dir / "02c-qwen-vibevoice-prompts/registered/Voice0.wav"),
		},
		"Speaker 1": {
			"vibevoice_name": "Voice1",
			"reference_wav": str(run_dir / "02c-qwen-vibevoice-prompts/registered/Voice1.wav"),
			"registered_path": str(run_dir / "registered/Voice1.wav"),
			"sha256": _sha256(run_dir / "02c-qwen-vibevoice-prompts/registered/Voice1.wav"),
		},
	}
	_write_json(run_dir / "02a-speaker-census/speaker_roster.json", {
		"schema_version": "worldview-china-speaker-census.v1",
		"status": "frozen",
		"speaker_count": 2,
		"voice_count": 2,
		"analysis_window_sec": 360.0,
		"speakers": {
			"Speaker 0": {"description": "host voice"},
			"Speaker 1": {"description": "guest voice"},
		},
	})
	speaker_census_path = run_dir / "02a-speaker-census/speaker_roster.json"
	_write_json(run_dir / "02b-source-voice-prompts/voice_prompt_manifest.json", {
		"status": "pass",
		"speaker_census_roster_path": str(speaker_census_path),
		"speaker_census_roster_sha256": _sha256(speaker_census_path),
		"speaker_roster": {
			"status": "frozen",
			"speaker_count": 2,
			"voice_count": 2,
			"speakers": {
				"Speaker 0": {"description": "host voice"},
				"Speaker 1": {"description": "guest voice"},
			},
		},
		"speaker_voices": {
			"Speaker 0": {"selected_clips": []},
			"Speaker 1": {"selected_clips": []},
		},
	})
	_write_json(run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json", {
		"schema_version": "worldview-china-qwen-vibevoice-prompts.v1",
		"status": "pass",
		"speaker_voices": speaker_voices,
		"voice_distinctness_policy": {
			"status": "PASS_ORIGINAL_CLONED_PAIR",
			"scope": "exactly_two_speakers_only",
			"threshold": 0.90,
		},
	})
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"content_coverage": "full_translation",
		"segments": [{"segment_index": 1, "speaker": "Speaker 0", "zh_text": "中国的经济韧性很重要"}],
	})
	(run_dir / "03-source-translation/source_transcript.zh.md").write_text("Speaker 0: 中国的经济韧性很重要\n", encoding="utf-8")
	_write_json(run_dir / "03-source-translation/chapter_segments.json", {
		"chapters": [{"segment_start": 1, "segment_end": 1, "title": "中国的经济韧性"}],
	})
	_write_translation_reading_review(run_dir)
	translation_semantic_result = translation_semantic_qa.run_review(run_dir, stage="test")
	assert translation_semantic_result["status"] == "PASS"
	early_compliance_result = text_compliance.run_review(
		run_dir,
		stage="after_translation_gate",
		output_dirname="03d-risk-compliance-review",
	)
	assert early_compliance_result["status"] == "PASS"
	_write_independent_review(
		run_dir / "03d-risk-compliance-review/independent-review-result.json",
		{
			"faithful_translation_json": run_dir / "03-source-translation/source_transcript.zh.json",
			"active_translation_json": run_dir / "03-source-translation/source_transcript.zh.json",
		},
	)
	(run_dir / "podcast_script.md").write_text("Speaker 0: 中国的经济韧性很重要\n", encoding="utf-8")
	(run_dir / "04-podcast-script").mkdir(parents=True, exist_ok=True)
	(run_dir / "04-podcast-script/podcast_script.md").write_text("Speaker 0: 中国的经济韧性很重要\n", encoding="utf-8")
	_write_json(run_dir / "04-podcast-script/script_turns.json", {
		"turns": [{
			"turn_index": 1,
			"speaker": "Speaker 0",
			"text": "中国的经济韧性很重要",
		}],
	})
	(run_dir / "04-podcast-script/script_report.md").write_text("content_coverage: full_translation\n", encoding="utf-8")
	locked_speaker_names = ["Voice0", "Voice1"]
	_write_json(run_dir / "05-vibevoice-chunks/chunk_plan.json", {
		"voice_context_policy": "locked_two_speaker_roster",
		"chunks": [{
			"chunk_id": "chunk_001",
			"vibevoice_mode": "dialogue",
			"speaker_names": locked_speaker_names,
		}],
	})
	chunk_audio_path = run_dir / "05-vibevoice-chunks/chunks/chunk_001/audio/final_podcast.wav"
	_make_silent_wav(chunk_audio_path, duration=1.0)
	_write_json(run_dir / "audio/audio_manifest.json", {
		"audio_backend": "vibevoice_chunked_dialogue",
		"voice_context_policy": "locked_two_speaker_roster",
		"speaker_voices": {"Speaker 0": "Voice0", "Speaker 1": "Voice1"},
		"voice_prompt_manifest": "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json",
		"chunks": [{
			"chunk_id": "chunk_001",
			"vibevoice_mode": "dialogue",
			"speaker_names": locked_speaker_names,
			"audio": str(chunk_audio_path),
		}],
		"turns": [{"speaker": "Speaker 0", "text": "中国的经济韧性很重要"}],
	})
	_write_json(run_dir / "audio/dialogue_timeline.json", {
		"audio_sha256": _sha256(run_dir / "audio/final_podcast.wav"),
		"duration_sec": 1.0,
		"subtitle_cue_policy": {
			"cue_text_policy": "complete_sentence_or_semantic_clause_no_hard_width_split",
			"cue_timing_policy": "asr_character_span",
		},
		"turns": [{
			"turn_index": 1,
			"turn_id": "turn_0001",
			"speaker": "Speaker 0",
			"text": "中国的经济韧性很重要",
			"start_sec": 0.0,
			"end_sec": 1.0,
			"alignment_confidence": "high",
		}],
		"cues": [{
			"cue_index": 1,
			"turn_index": 1,
			"turn_id": "turn_0001",
			"speaker": "Speaker 0",
			"text": "中国的经济韧性很重要",
			"start_sec": 0.0,
			"end_sec": 1.0,
			"timing_source": "asr_character_span",
		}],
	})
	_write_json(run_dir / "06b-audio-transcript-integrity/audio-transcript-integrity-result.json", {
		"status": "PASS",
		"summary": {
			"matched_script_ratio": 1.0,
			"repair_target_chunks": [],
		},
	})
	_write_json(run_dir / "06d-voice-consistency-qa/voice-consistency-qa-result.json", {
		"schema_version": "worldview-china-voice-consistency-qa.v1",
		"overall_status": "PASS",
		"expected_voices": {"Speaker 0": "Voice0", "Speaker 1": "Voice1"},
		"lineage": {"status": "PASS", "finding_count": 0, "findings": []},
		"acoustic": {"status": "PASS", "sample_count": 2, "samples": []},
	})
	(run_dir / "video/final_subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n中国的经济韧性很重要\n", encoding="utf-8")
	(run_dir / "video/final_subtitles.ass").write_text("[Events]\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,中国的经济韧性很重要\n", encoding="utf-8")
	_write_json(run_dir / "video/subtitle_manifest.json", {
		"global_lead_sec": 0.12,
		"timing_policy": {
			"status": "PASS",
			"global_lead_sec": 0.12,
			"late_start_violation_count": 0,
			"lead_applied_per_split_cue": True,
		},
		"segmentation_policy": {
			"status": "PASS",
			"hard_width_fallback_count": 0,
			"line_violation_count": 0,
			"dangling_fragment_violation_count": 0,
		},
		"style": {"speaker_labels": False, "max_lines": 1},
		"cues": [{
			"index": 1,
			"display_text": "中国的经济韧性很重要",
			"fits_single_line": True,
			"start_sec": 0.0,
			"end_sec": 1.0,
		}],
	})
	compliance_result = text_compliance.run_review(run_dir, stage="test")
	assert compliance_result["status"] == "PASS"
	_write_independent_review(
		run_dir / "04c-bilibili-text-compliance/independent-review-result.json",
		{
			"active_translation_json": run_dir / "03-source-translation/source_transcript.zh.json",
			"script_turns": run_dir / "04-podcast-script/script_turns.json",
			"node_podcast_script": run_dir / "04-podcast-script/podcast_script.md",
			"podcast_script": run_dir / "podcast_script.md",
			"video_title": run_dir / "video_title.txt",
			"cover_title": run_dir / "cover/cover_title.json",
			"subtitles_srt": run_dir / "video/final_subtitles.srt",
			"subtitles_ass": run_dir / "video/final_subtitles.ass",
		},
	)
	gate_result = speaker_turn_gate.run_gate(run_dir)
	assert gate_result["status"] == "PASS"
	pre_tts_result = pre_tts_contract.run_contract(run_dir, force=True)
	assert pre_tts_result["status"] == "PASS"
	retimed_video = run_dir / "08-source-video-revoice/work/source_retimed_basic.mp4"
	retimed_video.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(run_dir / "video/final_video.mp4", retimed_video)
	source_turn_map = run_dir / "04-source-dialogue-turn-map/source_dialogue_turn_map.active.json"
	_write_json(source_turn_map, {
		"schema_version": "worldview-china-source-dialogue-turn-map.v1",
		"status": "PASS",
		"method": "episode_audio_manifest_bound_source_segment_visual_duration_fit",
		"turns": [
			{
				"turn_id": "turn_0001",
				"turn_index": 1,
				"speaker": "Speaker 0",
				"source_start_sec": 0.0,
				"source_end_sec": 1.0,
				"audio_turn_id": "turn_0001",
				"audio_turn_ids": ["turn_0001"],
			},
		],
	})
	_write_json(run_dir / "08-source-video-revoice/visual_activity.json", {"schema_version": "worldview-china-visual-activity.v1"})
	_write_json(run_dir / "08-source-video-revoice/retime_edit_plan.json", {
		"schema_version": "worldview-china-turn-retime-edit-plan.v1",
		"status": "pass",
		"source_turn_map": str(source_turn_map),
		"source_turn_map_sha256": _sha256(source_turn_map),
		"summary": {
			"target_duration_sec": 1.0,
			"audio_start_offset_sec": 0.0,
			"duration_delta_vs_target_sec": 0.0,
			"protected_range_violation_count": 0,
			"turn_boundary_drift_violation_count": 0,
			"audio_turn_missing_count": 0,
			"speaker_mismatch_count": 0,
			"extension_policy_violation_count": 0,
			"cuts_per_minute": 0.0,
			"min_kept_segment_duration_sec": 1.2,
		},
		"edit_segments": [],
	})

	def write_spot_qa_result(motion_status: str = "PASS") -> None:
		input_paths = [
			run_dir / "video/final_video.mp4",
			run_dir / "audio/final_podcast.wav",
			run_dir / "video/render_manifest.json",
			run_dir / "video/subtitle_manifest.json",
			run_dir / "audio/dialogue_timeline.json",
			run_dir / "06d-voice-consistency-qa/voice-consistency-qa-result.json",
		]
		_write_json(run_dir / "09a-multimodal-spot-qa/multimodal-spot-qa-result.json", {
			"schema_version": "worldview-china-multimodal-spot-qa-result.v1",
			"status": "PASS",
			"required_criteria": [
				"visual_audio_semantic_alignment",
				"subtitle_audio_timing",
				"subtitle_text_segmentation",
				"voice_identity_consistency",
				"speaker_switch_coherence",
				"video_motion_integrity",
			],
			"summary": {
				"sample_count": 20,
				"reviewed_sample_count": 20,
				"fail_count": 0,
				"warn_count": 0,
			},
			"automatic_checks": {
				"video_motion_integrity": {
					"status": motion_status,
					"reason": "unit_test_minimal_fixture" if motion_status == "SKIPPED" else "unit_test_minimal_motion_pass",
					"failures": [],
				},
			},
			"input_file_hashes": {str(path.resolve()): _sha256(path) for path in input_paths},
		})

	_write_json(run_dir / "video/render_manifest.json", {
		"visual_mode": "source_video_revoice_episode_segment_turn_retimed_basic_burned_subtitles",
		"series_episode": True,
		"visual_sync_mode": "turn_retimed_basic_v1",
		"turn_retime": {
			"visual_sync_mode": "turn_retimed_basic_v1",
			"source_turn_map": str(source_turn_map),
			"source_turn_map_selection": "active_dialogue_turn_map",
			"visual_activity": str(run_dir / "08-source-video-revoice/visual_activity.json"),
			"retime_edit_plan": str(run_dir / "08-source-video-revoice/retime_edit_plan.json"),
			"retimed_video": str(retimed_video),
			"audio_start_offset_sec": 0.0,
			"subtitle_time_offset_sec": 0.0,
		},
		"target_duration_sec": 1.0,
		"target_video_height": 1440,
		"subtitle_mode": "burned_ass",
		"subtitle_delivery_policy": "burned_subtitles_default",
		"burned_subtitle_render": {
			"method": "test_overlay",
			"subtitle_layout_rule": {
				"font_size_px": 64,
				"subtitle_vertical_down_shift_px": 64,
				"subtitle_vertical_down_shift_unit": "one_font_height",
			},
		},
		"screenshots": {
			"opening": str(run_dir / "08-source-video-revoice/screenshots/opening.png"),
			"middle": str(run_dir / "08-source-video-revoice/screenshots/middle.png"),
			"end": str(run_dir / "08-source-video-revoice/screenshots/end.png"),
		},
	})
	write_spot_qa_result()
	result = final_qa_script.run_qa(run_dir, write_history=False)
	assert result["overall_status"] == "PASS"
	valid_render_manifest = _read_json(run_dir / "video/render_manifest.json")
	broken_render_manifest = json.loads(json.dumps(valid_render_manifest))
	broken_render_manifest["turn_retime"]["retime_edit_plan"] = str(run_dir / "08-source-video-revoice/missing_retime_edit_plan.json")
	_write_json(run_dir / "video/render_manifest.json", broken_render_manifest)
	write_spot_qa_result()
	result = final_qa_script.run_qa(run_dir, write_history=False)
	assert result["overall_status"] == "FAIL"
	assert any("retime_edit_plan path is missing" in failure for failure in result["failures"])
	_write_json(run_dir / "video/render_manifest.json", valid_render_manifest)
	write_spot_qa_result(motion_status="SKIPPED")
	result = final_qa_script.run_qa(run_dir, write_history=False)
	assert result["overall_status"] == "FAIL"
	assert any("video motion integrity automatic check must PASS" in failure for failure in result["failures"])
	write_spot_qa_result()
	subtitle_manifest = _read_json(run_dir / "video/subtitle_manifest.json")
	subtitle_manifest["segmentation_policy"]["status"] = "WARN"
	subtitle_manifest["segmentation_policy"]["hard_width_fallback_count"] = 1
	subtitle_manifest["segmentation_policy"]["line_violation_count"] = 1
	subtitle_manifest["style"]["max_lines"] = 2
	subtitle_manifest["cues"] = [{"display_text": "中国的经济韧性\n很重要", "fits_single_line": False}]
	_write_json(run_dir / "video/subtitle_manifest.json", subtitle_manifest)
	write_spot_qa_result()
	result = final_qa_script.run_qa(run_dir, write_history=False)
	assert result["overall_status"] == "PASS"
	assert any("hard width fallback" in warning for warning in result["warnings"])
	assert any("line break" in warning for warning in result["warnings"])
	_write_json(run_dir / "video/render_manifest.json", {
		"visual_mode": "source_video_revoice_episode_segment",
		"series_episode": True,
		"target_duration_sec": 1.0,
		"subtitle_mode": "sidecar_not_burned",
		"screenshots": {
			"opening": str(run_dir / "08-source-video-revoice/screenshots/opening.png"),
			"middle": str(run_dir / "08-source-video-revoice/screenshots/middle.png"),
			"end": str(run_dir / "08-source-video-revoice/screenshots/end.png"),
		},
	})
	result = final_qa_script.run_qa(run_dir, write_history=False)
	assert result["overall_status"] == "FAIL"
	assert any("must burn subtitles" in failure for failure in result["failures"])
