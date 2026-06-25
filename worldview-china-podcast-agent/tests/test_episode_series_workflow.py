from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


SKILL_DIR = Path("/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent")


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
final_qa_script = _load_module("run_final_qa", SKILL_DIR / "scripts/run_final_qa.py")
vibevoice_chunks = _load_module("run_vibevoice_chunks", SKILL_DIR / "scripts/run_vibevoice_chunks.py")
audio_integrity = _load_module("run_audio_transcript_integrity_qa", SKILL_DIR / "scripts/run_audio_transcript_integrity_qa.py")
text_compliance = _load_module(
	"run_bilibili_text_compliance_review",
	SKILL_DIR / "skills/worldview-china-bilibili-text-compliance-review/scripts/run_bilibili_text_compliance_review.py",
)
selected_registry = _load_module("selected_video_registry", SKILL_DIR / "scripts/selected_video_registry.py")
source_translation = _load_module("run_source_translation", SKILL_DIR / "scripts/run_source_translation.py")
source_voice_prompts = _load_module(
	"extract_source_voice_prompts",
	SKILL_DIR / "skills/worldview-china-source-voice-prompts/scripts/extract_source_voice_prompts.py",
)
metadata_script = _load_module(
	"generate_bilibili_publish_metadata",
	SKILL_DIR / "skills/worldview-china-bilibili-publish-metadata/scripts/generate_bilibili_publish_metadata.py",
)
title_cover_script = _load_module(
	"build_title_cover",
	SKILL_DIR / "skills/worldview-china-podcast-title-cover/scripts/build_title_cover.py",
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


def _make_test_video(path: Path, duration: float = 1.0) -> None:
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
		f"testsrc=size=320x180:rate=24:duration={duration}",
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


def test_episode_series_split_creates_ordered_episode_runs_with_hourly_schedule(tmp_path: Path) -> None:
	run_dir = tmp_path / "run"
	_make_parent_run(run_dir)
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
	assert manifest["episode_count"] == 2
	assert manifest["serial_execution_required"] is True
	assert manifest["parallel_execution_allowed"] is False
	assert manifest["episode_title_template"] == "{series_title}·{episode_order_marker}：{subtitle}"
	assert manifest["episode_order_marker_template"] == "第{episode_index}集"
	assert manifest["target_chars_min"] == 100
	assert manifest["target_chars_max"] == 200
	first = manifest["episodes"][0]
	second = manifest["episodes"][1]
	assert first["video_title"] == "嘉宾观察·第1集：中国经济主题1与中国经济主题2"
	assert second["video_title"] == "嘉宾观察·第2集：中国经济主题3与中国经济主题4"
	assert first["scheduled_publish_at"] == "2026-06-24T11:00:00+08:00"
	assert second["scheduled_publish_at"] == "2026-06-24T12:00:00+08:00"
	for episode in manifest["episodes"]:
		episode_dir = Path(episode["episode_run_dir"])
		episode_manifest = _read_json(episode_dir / "episode_manifest.json")
		assert episode_manifest["serial_execution_required"] is True
		assert episode_manifest["episode_order_marker_template"] == manifest["episode_order_marker_template"]
		assert (episode_dir / "04-podcast-script/podcast_script.md").exists()
		assert _read_json(episode_dir / "bilibili_upload_metadata.json")["scheduled_publish_at"] == episode["scheduled_publish_at"]


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
	_write_json(run_dir / "bilibili_upload_metadata.json", {
		"scheduled_publish_at": "2026-06-24T11:00:00+08:00",
		"scheduled_publish_timezone": "Asia/Shanghai",
		"schedule_source": "series_first_publish_at_plus_episode_index_hours",
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
	assert report["series_episode"] is True
	assert report["scheduled_publish_at"] == "2026-06-24T11:00:00+08:00"


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
		update_root=True,
	)
	assert manifest["series_episode"] is True
	assert manifest["source_episode_video_used"] is True
	assert manifest["video_input"] == str(episode_source.resolve())
	assert manifest["cut_source_start_sec"] is None
	assert manifest["visual_mode"] == "source_video_revoice_episode_segment"


def test_revoice_cli_defaults_to_burned_subtitles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	monkeypatch.setattr(sys, "argv", ["run_source_video_revoice.py", "--run-dir", str(tmp_path)])
	args = revoice.parse_args()
	assert args.burn_subtitles is True
	monkeypatch.setattr(sys, "argv", ["run_source_video_revoice.py", "--run-dir", str(tmp_path), "--no-burn-subtitles"])
	args = revoice.parse_args()
	assert args.burn_subtitles is False


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
		"Speaker 1: Mainland China 和南京大屠杀纪念馆、新疆维吾尔族自治区也都不合规。\n",
		encoding="utf-8",
	)
	(run_dir / "video_title.txt").write_text("嘉宾观察·第1集：穆斯林该押注中国吗？\n", encoding="utf-8")
	_write_json(run_dir / "cover/cover_title.json", {"title_text": "嘉宾观察：押注中国吗"})
	result = text_compliance.run_review(run_dir, stage="test")
	assert result["status"] == "FAIL"
	rule_ids = {finding["rule_id"] for finding in result["findings"]}
	assert "taiwan_hongkong_abbreviation" in rule_ids
	assert "taiwan_named_as_country" in rule_ids
	assert "wrong_chinese_mainland_english_term" in rule_ids
	assert "wrong_nanjing_memorial_name" in rule_ids
	assert "wrong_xinjiang_autonomous_region_name" in rule_ids
	assert "polarizing_bilibili_title_or_metadata" in rule_ids


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
		postprocess_min_source_max_volume=-8.0,
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
	assert plan["target_chars"] == 600
	assert plan["min_split_chars"] == 350
	assert plan["hard_max_chars"] == 800


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
	})
	_write_json(episode_dir / "bilibili_upload_draft_report.json", upload_report)
	_write_json(run_dir / "04b-series-episodes/series_manifest.json", {
		"schema_version": "worldview-china-podcast-series.v1",
		"serial_execution_required": True,
		"parallel_execution_allowed": False,
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
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
		schedule = first_schedule + timedelta(hours=index - 1)
		_write_json(episode_dir / "bilibili_upload_metadata.json", {
			"workflow": "worldview-china-podcast-agent",
			"title": title,
			"episode_index": index,
			"scheduled_publish_at": schedule.isoformat(),
		})
		_write_json(episode_dir / "bilibili_upload_draft_report.json", {
			"status": "SUBMITTED",
			"final_submit_clicked": True,
		})
		episodes.append({
			"episode_index": index,
			"episode_run_dir": str(episode_dir),
			"scheduled_publish_at": schedule.isoformat(),
		})
	_write_json(run_dir / "04b-series-episodes/series_manifest.json", {
		"schema_version": "worldview-china-podcast-series.v1",
		"serial_execution_required": True,
		"parallel_execution_allowed": False,
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
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
		})
		_write_json(episode_dir / "cover/cover_title.json", {
			"title_text": f"嘉宾观察：主题{index}",
			"video_title_text": title,
			"cover_title_omits_episode_index": True,
		})
		_write_json(episode_dir / "02d-title-cover/title_cover_manifest.json", {"frame_selection": {"path": str(shared_frame)}})
		_write_json(episode_dir / "09-final-qa/final-qa-result.json", {"overall_status": "PASS"})
		schedule = first_schedule + timedelta(hours=index - 1)
		_write_json(episode_dir / "bilibili_upload_metadata.json", {
			"workflow": "worldview-china-podcast-agent",
			"title": title,
			"episode_index": index,
			"scheduled_publish_at": schedule.isoformat(),
		})
		_write_json(episode_dir / "bilibili_upload_draft_report.json", {
			"status": "SUBMITTED",
			"final_submit_clicked": True,
		})
		episodes.append({
			"episode_index": index,
			"episode_run_dir": str(episode_dir),
			"scheduled_publish_at": schedule.isoformat(),
		})
	_write_json(run_dir / "04b-series-episodes/series_manifest.json", {
		"schema_version": "worldview-china-podcast-series.v1",
		"serial_execution_required": True,
		"parallel_execution_allowed": False,
		"episode_title_template": "{series_title}·{episode_order_marker}：{subtitle}",
		"episode_order_marker_template": "第{episode_index}集",
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
	_make_test_video(run_dir / "video/final_video.mp4", duration=1.0)
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
	})
	_write_json(run_dir / "03-source-translation/source_transcript.zh.json", {
		"content_coverage": "full_translation",
		"segments": [{"segment_index": 1, "speaker": "Speaker 0", "zh_text": "中国的经济韧性很重要"}],
	})
	(run_dir / "03-source-translation/source_transcript.zh.md").write_text("Speaker 0: 中国的经济韧性很重要\n", encoding="utf-8")
	_write_json(run_dir / "03-source-translation/chapter_segments.json", {
		"chapters": [{"segment_start": 1, "segment_end": 1, "title": "中国的经济韧性"}],
	})
	(run_dir / "podcast_script.md").write_text("Speaker 0: 中国的经济韧性很重要\n", encoding="utf-8")
	(run_dir / "04-podcast-script").mkdir(parents=True, exist_ok=True)
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
	_write_json(run_dir / "audio/audio_manifest.json", {
		"audio_backend": "vibevoice_chunked_dialogue",
		"voice_context_policy": "locked_two_speaker_roster",
		"speaker_voices": {"Speaker 0": "Voice0", "Speaker 1": "Voice1"},
		"voice_prompt_manifest": "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json",
		"chunks": [{
			"chunk_id": "chunk_001",
			"vibevoice_mode": "dialogue",
			"speaker_names": locked_speaker_names,
		}],
		"turns": [{"speaker": "Speaker 0", "text": "中国的经济韧性很重要"}],
	})
	_write_json(run_dir / "audio/dialogue_timeline.json", {
		"turns": [{"speaker": "Speaker 0", "text": "中国的经济韧性很重要"}],
		"cues": [{"text": "中国的经济韧性很重要"}],
	})
	_write_json(run_dir / "06b-audio-transcript-integrity/audio-transcript-integrity-result.json", {
		"status": "PASS",
		"summary": {
			"matched_script_ratio": 1.0,
			"repair_target_chunks": [],
		},
	})
	(run_dir / "video/final_subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n中国的经济韧性很重要\n", encoding="utf-8")
	(run_dir / "video/final_subtitles.ass").write_text("[Events]\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,中国的经济韧性很重要\n", encoding="utf-8")
	_write_json(run_dir / "video/subtitle_manifest.json", {
		"style": {"speaker_labels": False},
		"cues": [{"display_text": "中国的经济韧性很重要"}],
	})
	compliance_result = text_compliance.run_review(run_dir, stage="test")
	assert compliance_result["status"] == "PASS"
	_write_json(run_dir / "video/render_manifest.json", {
		"visual_mode": "source_video_revoice_episode_segment_burned_subtitles",
		"series_episode": True,
		"target_duration_sec": 1.0,
		"subtitle_mode": "burned_ass",
		"subtitle_delivery_policy": "burned_subtitles_default",
		"burned_subtitle_render": {"method": "test_overlay"},
		"screenshots": {
			"opening": str(run_dir / "08-source-video-revoice/screenshots/opening.png"),
			"middle": str(run_dir / "08-source-video-revoice/screenshots/middle.png"),
			"end": str(run_dir / "08-source-video-revoice/screenshots/end.png"),
		},
	})
	result = final_qa_script.run_qa(run_dir, write_history=False)
	assert result["overall_status"] == "PASS"
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
