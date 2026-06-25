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
final_qa_script = _load_module("run_final_qa", SKILL_DIR / "scripts/run_final_qa.py")
voice_consistency = _load_module("run_voice_consistency_qa", SKILL_DIR / "scripts/run_voice_consistency_qa.py")
vibevoice_chunks = _load_module("run_vibevoice_chunks", SKILL_DIR / "scripts/run_vibevoice_chunks.py")
audio_integrity = _load_module("run_audio_transcript_integrity_qa", SKILL_DIR / "scripts/run_audio_transcript_integrity_qa.py")
text_compliance = _load_module(
	"run_bilibili_text_compliance_review",
	SKILL_DIR / "skills/worldview-china-bilibili-text-compliance-review/scripts/run_bilibili_text_compliance_review.py",
)
selected_registry = _load_module("selected_video_registry", SKILL_DIR / "scripts/selected_video_registry.py")
source_translation = _load_module("run_source_translation", SKILL_DIR / "scripts/run_source_translation.py")
translation_semantic_qa = _load_module("run_translation_semantic_qa", SKILL_DIR / "scripts/run_translation_semantic_qa.py")
script_format = _load_module("run_podcast_script_format", SKILL_DIR / "scripts/run_podcast_script_format.py")
source_voice_prompts = _load_module(
	"extract_source_voice_prompts",
	SKILL_DIR / "skills/worldview-china-source-voice-prompts/scripts/extract_source_voice_prompts.py",
)
speaker_census = _load_module("run_speaker_census", SKILL_DIR / "scripts/run_speaker_census.py")
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
	assert manifest["bilibili_upload_overlap_allowed"] is True
	assert manifest["final_publish_after_all_uploads"] is True
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
		assert episode_manifest["bilibili_upload_overlap_allowed"] is True
		assert episode_manifest["final_publish_after_all_uploads"] is True
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
	(run_dir / "podcast_script.md").write_text(
		"Speaker 0: 中国经济韧性不是一句口号，它关系到消费、供应链和外企在中国市场的长期判断。\n",
		encoding="utf-8",
	)
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
	assert "中国的经济韧性" in metadata["description"]
	assert "中文配音版本" not in metadata["description"]
	assert "保留原视频画面" not in metadata["description"]
	assert report["series_episode"] is True
	assert report["scheduled_publish_at"] == "2026-06-24T11:00:00+08:00"


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
		"scheduled_publish_at": "2026-06-24T12:00:00+08:00",
		"scheduled_publish_timezone": "Asia/Shanghai",
		"schedule_source": "series_first_publish_at_plus_episode_index_hours",
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
	assert metadata["scheduled_publish_at"] == "2026-06-24T12:00:00+08:00"
	assert metadata["scheduled_publish_timezone"] == "Asia/Shanghai"
	assert metadata["schedule_source"] == "series_first_publish_at_plus_episode_index_hours"
	assert metadata["series_episode_index"] == 2
	assert metadata["series_episode_count"] == 2
	assert "外企仍然看重中国市场" in metadata["description"]
	assert "替换为中文对话音频" not in metadata["description"]
	assert report["scheduled_publish_at"] == "2026-06-24T12:00:00+08:00"


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


def test_revoice_cli_defaults_to_burned_subtitles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	monkeypatch.setattr(sys, "argv", ["run_source_video_revoice.py", "--run-dir", str(tmp_path)])
	args = revoice.parse_args()
	assert args.burn_subtitles is True
	monkeypatch.setattr(sys, "argv", ["run_source_video_revoice.py", "--run-dir", str(tmp_path), "--no-burn-subtitles"])
	args = revoice.parse_args()
	assert args.burn_subtitles is False


def test_revoice_burned_subtitles_outputs_2k_1440p(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	run_dir = tmp_path / "run"
	source = run_dir / "02-source-capture/youtube-media/source.mp4"
	audio = run_dir / "audio/final_podcast.wav"
	_make_test_video(source, duration=1.0, size=(320, 180))
	_make_silent_wav(audio, duration=1.0)
	_write_json(run_dir / "video/subtitle_manifest.json", {"cues": [{"index": 1, "start_sec": 0.0, "end_sec": 1.0, "text": "测试字幕"}]})

	def fake_overlay(work_dir: Path, subtitle_manifest: Path, target_duration: float) -> tuple[Path, list[dict[str, Any]]]:
		assert subtitle_manifest.exists()
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
	assert int(stream["width"]) == 2560
	assert int(stream["height"]) == 1440


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
		postprocess_min_source_max_volume=-8.0,
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
		"style": {"speaker_labels": False},
		"cues": [{"display_text": "中国的经济韧性很重要"}],
	})
	compliance_result = text_compliance.run_review(run_dir, stage="test")
	assert compliance_result["status"] == "PASS"
	_write_json(run_dir / "video/render_manifest.json", {
		"visual_mode": "source_video_revoice_episode_segment_burned_subtitles",
		"series_episode": True,
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
