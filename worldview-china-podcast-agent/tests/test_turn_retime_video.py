from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest


SKILL_DIR = Path("/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent")
REAL_VIDEO_FIXTURE = Path(os.environ.get(
	"WORLDVIEW_PODCAST_RETIME_REAL_VIDEO",
	"/Volumes/GT34/Generated/worldview_podcast_retime_tests/source_10min.mp4",
))


def _load_module(name: str, path: Path) -> Any:
	spec = importlib.util.spec_from_file_location(name, path)
	assert spec is not None
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[name] = module
	spec.loader.exec_module(module)
	return module


retime = _load_module("run_turn_retime_video", SKILL_DIR / "scripts/run_turn_retime_video.py")


def _write_json(path: Path, data: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


def _make_video(path: Path, lavfi: str, duration: float = 12.0) -> None:
	if shutil.which("ffmpeg") is None:
		pytest.skip("ffmpeg not available")
	path.parent.mkdir(parents=True, exist_ok=True)
	subprocess_cmd = [
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		lavfi,
		"-t",
		str(duration),
		"-c:v",
		"libx264",
		"-pix_fmt",
		"yuv420p",
		str(path),
	]
	import subprocess

	subprocess.run(subprocess_cmd, check=True)


def _ranges_overlap(left: dict[str, float], right: tuple[float, float]) -> bool:
	return max(float(left["start_sec"]), right[0]) < min(float(left["end_sec"]), right[1])


def test_retime_plan_prefers_silence_and_low_motion_without_cutting_protected_ranges(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"not-a-real-video-needed-for-plan")
	source_turn_map = tmp_path / "source_turn_map.json"
	audio_timeline = tmp_path / "turn_audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_edit_plan.json"
	_write_json(source_turn_map, {
		"turns": [
			{
				"turn_id": "turn_0001",
				"turn_index": 1,
				"speaker": "Speaker 0",
				"source_start": 0.0,
				"source_end": 5.0,
			},
			{
				"turn_id": "turn_0002",
				"turn_index": 2,
				"speaker": "Speaker 1",
				"source_start": 5.0,
				"source_end": 25.0,
				"silence_ranges": [[9.0, 13.0], [17.0, 21.0]],
				"filler_ranges": [[13.0, 15.0]],
			},
			{
				"turn_id": "turn_0003",
				"turn_index": 3,
				"speaker": "Speaker 0",
				"source_start": 25.0,
				"source_end": 30.0,
			},
		],
	})
	_write_json(audio_timeline, {
		"turns": [
			{"turn_id": "turn_0001", "turn_index": 1, "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 4.6},
			{"turn_id": "turn_0002", "turn_index": 2, "speaker": "Speaker 1", "start_sec": 4.6, "end_sec": 14.6},
			{"turn_id": "turn_0003", "turn_index": 3, "speaker": "Speaker 0", "start_sec": 14.6, "end_sec": 19.6},
		],
	})
	_write_json(visual_activity, {
		"schema_version": "worldview-china-visual-activity.v1",
		"low_motion_ranges": [{"start_sec": 8.0, "end_sec": 22.0, "duration_sec": 14.0}],
		"protected_ranges": [{"start_sec": 15.0, "end_sec": 16.0, "duration_sec": 1.0, "reason": "scene_cut"}],
	})
	plan = retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		turn_edge_protect_sec=0.5,
		min_trim_sec=0.8,
		min_kept_segment_sec=1.2,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["turn_count"] == 3
	assert plan["summary"]["trimmed_duration_sec"] >= 9.5
	assert abs(plan["summary"]["duration_delta_vs_target_sec"]) <= 0.75
	assert plan["summary"]["protected_range_violation_count"] == 0
	turn_2 = [turn for turn in plan["turns"] if turn["turn_id"] == "turn_0002"][0]
	assert {item["reason"] for item in turn_2["trimmed_source_ranges"]} >= {"source_silence", "source_filler"}
	assert not any(_ranges_overlap(item, (15.0, 16.0)) for item in turn_2["trimmed_source_ranges"])
	assert plan["summary"]["min_kept_segment_duration_sec"] >= 1.2
	assert output_plan.exists()


def test_retime_plan_does_not_double_count_overlapping_audio_turns(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"not-a-real-video-needed-for-plan")
	source_turn_map = tmp_path / "source_turn_map.json"
	audio_timeline = tmp_path / "turn_audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_edit_plan.json"
	_write_json(source_turn_map, {
		"turns": [
			{
				"turn_id": "turn_0001",
				"turn_index": 1,
				"speaker": "Speaker 0",
				"source_start": 0.0,
				"source_end": 4.5,
				"audio_turn_ids": ["turn_0001"],
			},
			{
				"turn_id": "turn_0002",
				"turn_index": 2,
				"speaker": "Speaker 1",
				"source_start": 4.5,
				"source_end": 8.0,
				"audio_turn_ids": ["turn_0002"],
			},
		],
	})
	_write_json(audio_timeline, {
		"duration_sec": 8.0,
		"turns": [
			{"turn_id": "turn_0001", "turn_index": 1, "speaker": "Speaker 0", "start_sec": 0.0, "end_sec": 5.0},
			{"turn_id": "turn_0002", "turn_index": 2, "speaker": "Speaker 1", "start_sec": 4.5, "end_sec": 8.0},
		],
	})
	_write_json(visual_activity, {
		"schema_version": "worldview-china-visual-activity.v1",
		"low_motion_ranges": [],
		"protected_ranges": [],
	})
	plan = retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		turn_edge_protect_sec=0.2,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["target_duration_sec"] == pytest.approx(8.0, abs=0.001)
	assert plan["turns"][0]["target_duration_sec"] == pytest.approx(4.5, abs=0.001)
	assert plan["turns"][1]["target_duration_sec"] == pytest.approx(3.5, abs=0.001)


def test_retime_plan_rebalances_accumulated_small_surplus(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	source_video.write_bytes(b"not-a-real-video-needed-for-plan")
	source_turn_map = tmp_path / "source_turn_map.json"
	audio_timeline = tmp_path / "turn_audio_timeline.json"
	visual_activity = tmp_path / "visual_activity.json"
	output_plan = tmp_path / "retime_edit_plan.json"
	_write_json(source_turn_map, {
		"turns": [
			{
				"turn_id": f"turn_{index:04d}",
				"turn_index": index,
				"speaker": "Speaker 0",
				"source_start": (index - 1) * 5.3,
				"source_end": index * 5.3,
				"audio_turn_ids": [f"turn_{index:04d}"],
			}
			for index in range(1, 4)
		],
	})
	_write_json(audio_timeline, {
		"duration_sec": 15.0,
		"turns": [
			{"turn_id": f"turn_{index:04d}", "turn_index": index, "speaker": "Speaker 0", "start_sec": (index - 1) * 5.0, "end_sec": index * 5.0}
			for index in range(1, 4)
		],
	})
	_write_json(visual_activity, {
		"schema_version": "worldview-china-visual-activity.v1",
		"low_motion_ranges": [],
		"protected_ranges": [],
	})
	plan = retime.build_retime_plan(
		source_video,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		turn_edge_protect_sec=0.2,
		min_trim_sec=0.8,
		min_kept_segment_sec=1.2,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["target_duration_sec"] == pytest.approx(15.0, abs=0.001)
	assert plan["summary"]["estimated_video_duration_sec"] == pytest.approx(15.0, abs=0.001)
	assert plan["summary"]["trimmed_duration_sec"] == pytest.approx(0.9, abs=0.001)
	assert all(abs(float(turn["duration_delta_vs_target_sec"])) <= 0.001 for turn in plan["turns"])
	assert {
		cut["reason"]
		for turn in plan["turns"]
		for cut in turn["trimmed_source_ranges"]
	} == {"global_surplus_tail_rebalance"}


def test_static_video_range_gate_fails_when_rendered_frame_freezes_but_source_moves(tmp_path: Path) -> None:
	source_video = tmp_path / "source.mp4"
	rendered_video = tmp_path / "rendered_static.mp4"
	_make_video(source_video, "testsrc=size=320x180:rate=24:duration=12", duration=12)
	_make_video(rendered_video, "color=c=black:size=320x180:rate=24:duration=12", duration=12)
	plan = {
		"source_video": str(source_video),
		"edit_segments": [
			{
				"segment_index": 1,
				"turn_index": 1,
				"source_mode": "video_range",
				"source_start_sec": 0.0,
				"source_end_sec": 12.0,
				"target_start_sec": 0.0,
				"target_end_sec": 12.0,
				"duration_sec": 12.0,
			}
		],
	}
	result = retime.detect_static_video_range_mismatches(plan, rendered_video, max_samples=1)
	assert result["status"] == "FAIL"
	assert result["failure_count"] == 1
	assert result["failures"][0]["reason"] == "rendered_video_range_static_while_mapped_source_moves"


@pytest.mark.skipif(not REAL_VIDEO_FIXTURE.exists(), reason="real 10-minute podcast fixture not available on this machine")
def test_real_ten_minute_video_fixture_builds_visual_activity_and_retime_plan() -> None:
	pytest.importorskip("PIL")
	if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
		pytest.skip("ffmpeg/ffprobe not available")
	work_root = Path("/Volumes/GT34/Generated/worldview_podcast_retime_tests/pytest_work") / f"pid_{os.getpid()}"
	if work_root.exists():
		shutil.rmtree(work_root)
	work_root.mkdir(parents=True, exist_ok=True)
	source_turn_map = work_root / "source_turn_map.json"
	audio_timeline = work_root / "turn_audio_timeline.json"
	visual_activity = work_root / "visual_activity.json"
	output_plan = work_root / "retime_edit_plan.json"
	source_turns = []
	audio_turns = []
	audio_cursor = 0.0
	for index in range(6):
		source_start = index * 100.0
		source_end = source_start + 100.0
		audio_start = audio_cursor
		audio_end = audio_start + 70.0
		source_turns.append({
			"turn_id": f"turn_{index + 1:04d}",
			"turn_index": index + 1,
			"speaker": "Speaker 0" if index % 2 == 0 else "Speaker 1",
			"source_start": source_start,
			"source_end": source_end,
			"silence_ranges": [[source_start + 30.0, source_start + 38.0], [source_start + 62.0, source_start + 70.0]],
		})
		audio_turns.append({
			"turn_id": f"turn_{index + 1:04d}",
			"turn_index": index + 1,
			"speaker": "Speaker 0" if index % 2 == 0 else "Speaker 1",
			"start_sec": audio_start,
			"end_sec": audio_end,
		})
		audio_cursor = audio_end
	_write_json(source_turn_map, {"turns": source_turns})
	_write_json(audio_timeline, {"turns": audio_turns})
	activity = retime.analyze_visual_activity(
		REAL_VIDEO_FIXTURE,
		visual_activity,
		work_root / "work",
		frame_interval_sec=2.0,
		max_duration_sec=600.0,
		force=True,
	)
	assert activity["analysis_duration_sec"] >= 599.0
	assert activity["window_count"] >= 250
	assert len(activity["low_motion_ranges"]) > 0
	plan = retime.build_retime_plan(
		REAL_VIDEO_FIXTURE,
		source_turn_map,
		audio_timeline,
		visual_activity,
		output_plan,
		turn_edge_protect_sec=1.0,
		min_trim_sec=0.8,
		min_kept_segment_sec=1.2,
	)
	assert plan["status"] == "pass"
	assert plan["summary"]["turn_count"] == 6
	assert plan["summary"]["trimmed_duration_sec"] >= 150.0
	assert abs(plan["summary"]["duration_delta_vs_target_sec"]) <= 0.75
	assert plan["summary"]["cuts_per_minute"] <= 10.0
