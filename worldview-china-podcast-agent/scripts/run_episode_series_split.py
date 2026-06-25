#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_CHARS_PER_MINUTE = 330.0
DEFAULT_TARGET_MINUTES_MIN = 30.0
DEFAULT_TARGET_MINUTES_MAX = 40.0
DEFAULT_TARGET_MINUTES_IDEAL = 35.0
DEFAULT_EPISODE_ORDER_MARKER_TEMPLATE = "第{episode_index}集"
DEFAULT_EPISODE_TITLE_TEMPLATE = "{series_title}·{episode_order_marker}：{subtitle}"
SERIES_NODE = "04b-series-episodes"
DOWNSTREAM_NODES = [
	"02d-title-cover",
	"05-vibevoice-chunks",
	"06-audio-alignment",
	"07-subtitles",
	"08-source-video-revoice",
	"09-final-qa",
	"10-bilibili-publish",
	"11-bilibili-upload-publish",
]


@dataclass(frozen=True)
class ChapterUnit:
	chapter_id: str
	title: str
	source_start: str | None
	source_end: str | None
	source_start_sec: float | None
	source_end_sec: float | None
	segment_start: int
	segment_end: int
	segments: list[dict[str, Any]]
	turns: list[dict[str, Any]]
	char_count: int
	original_chapter_ids: list[str]
	forced_split: bool = False


@dataclass(frozen=True)
class EpisodePlan:
	episode_index: int
	units: list[ChapterUnit]
	char_count: int
	estimated_minutes: float
	subtitle: str
	source_start: str | None
	source_end: str | None
	source_start_sec: float | None
	source_end_sec: float | None
	segments: list[dict[str, Any]]
	turns: list[dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_text(path: Path) -> str:
	return path.read_text(encoding="utf-8") if path.exists() else ""


def _normalize_tts_text(text: str) -> str:
	return re.sub(r"\s+", "", str(text or "")).strip()


def _char_count(text: str) -> int:
	return len(_normalize_tts_text(text))


def _parse_time_to_sec(value: Any) -> float | None:
	if value is None:
		return None
	if isinstance(value, (int, float)):
		return float(value)
	text = str(value).strip()
	if not text:
		return None
	if re.fullmatch(r"\d+(?:\.\d+)?", text):
		return float(text)
	parts = text.split(":")
	if len(parts) != 3:
		return None
	hours, minutes, seconds = parts
	return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _format_sec(seconds: float | None) -> str | None:
	if seconds is None:
		return None
	whole = int(seconds)
	millis = int(round((seconds - whole) * 1000))
	if millis == 1000:
		whole += 1
		millis = 0
	hours = whole // 3600
	minutes = (whole % 3600) // 60
	secs = whole % 60
	return f"{hours:02d}:{minutes:02d}:{secs:02d}" if millis == 0 else f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


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


def _episode_order_marker(episode_index: int, template: str = DEFAULT_EPISODE_ORDER_MARKER_TEMPLATE) -> str:
	episode_label = _chinese_episode_label(episode_index)
	marker = template.format(
		episode_index=episode_index,
		episode_label=episode_label,
		episode_number=episode_label,
	)
	marker = marker.strip()
	assert marker, "episode order marker template produced an empty marker"
	return marker


def _format_episode_title(series_title_prefix: str, episode_index: int, subtitle: str, title_template: str, order_marker_template: str) -> str:
	episode_label = _chinese_episode_label(episode_index)
	order_marker = _episode_order_marker(episode_index, order_marker_template)
	title = title_template.format(
		series_title=series_title_prefix,
		series_title_prefix=series_title_prefix,
		episode_index=episode_index,
		episode_label=episode_label,
		episode_number=episode_label,
		episode_order_marker=order_marker,
		order_marker=order_marker,
		subtitle=subtitle,
		episode_subtitle=subtitle,
	)
	assert series_title_prefix in title, "episode title template must include the shared series title"
	assert subtitle in title, "episode title template must include the episode subtitle"
	assert order_marker in title or str(episode_index) in title or episode_label in title, "episode title template must include an episode order marker"
	return title


def _cover_title(series_title_prefix: str, subtitle: str) -> str:
	return f"{series_title_prefix}：{subtitle}"


def _clean_title(value: Any, fallback: str) -> str:
	text = re.sub(r"\s+", "", str(value or "")).strip()
	text = re.sub(r"^(第[一二三四五六七八九十百0-9]+[章节部分讲集]|Chapter\s*\d+)[:：.\s-]*", "", text, flags=re.I)
	text = text.strip("：:，,。；;、- ")
	if not text or re.fullmatch(r"原文顺序分段\d+", text):
		return fallback
	return text[:24]


def _load_translation_paths(run_dir: Path) -> tuple[Path, Path | None, Path]:
	faithful_path = run_dir / "03-source-translation/source_transcript.zh.json"
	safe_path = run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json"
	assert faithful_path.exists(), f"Missing faithful Chinese translation: {faithful_path}"
	active_path = safe_path if safe_path.exists() else faithful_path
	chapter_path = (
		run_dir / "03b-mainland-publish-safety/chapter_segments.safe.json"
		if safe_path.exists()
		else run_dir / "03-source-translation/chapter_segments.json"
	)
	assert chapter_path.exists(), f"Missing chapter segments: {chapter_path}"
	return faithful_path, safe_path if safe_path.exists() else None, chapter_path


def _load_script_turns(run_dir: Path) -> list[dict[str, Any]]:
	turns_path = run_dir / "04-podcast-script/script_turns.json"
	if turns_path.exists():
		turns = list(_read_json(turns_path).get("turns") or [])
		assert turns, f"script_turns.json has no turns: {turns_path}"
		return turns
	script_path = run_dir / "04-podcast-script/podcast_script.md"
	assert script_path.exists(), f"Missing podcast script: {script_path}"
	turns: list[dict[str, Any]] = []
	for line in script_path.read_text(encoding="utf-8").splitlines():
		match = re.match(r"^(Speaker [01])[:：]\s*(.+)$", line.strip())
		if not match:
			continue
		text = _normalize_tts_text(match.group(2))
		turns.append({
			"turn_index": len(turns) + 1,
			"speaker": match.group(1),
			"text": text,
			"source_segment_index": len(turns) + 1,
			"char_count": len(text),
		})
	assert turns, f"No Speaker turns found in {script_path}"
	return turns


def _derive_chars_per_minute(run_dir: Path, explicit: float | None, calibration_audio_manifest: Path | None) -> tuple[float, dict[str, Any]]:
	if explicit is not None:
		assert explicit > 0
		return explicit, {
			"method": "explicit_cli",
			"chars_per_minute": explicit,
		}
	manifest_path = calibration_audio_manifest or run_dir / "audio/audio_manifest.json"
	if manifest_path.exists():
		manifest = _read_json(manifest_path)
		duration = float(manifest.get("duration_sec") or 0)
		turns = manifest.get("turns") or []
		chars = sum(_char_count(str(turn.get("tts_text") or turn.get("text") or "")) for turn in turns)
		if duration > 0 and chars > 0:
			cpm = chars / (duration / 60.0)
			if 180 <= cpm <= 500:
				return cpm, {
					"method": "calibrated_from_audio_manifest",
					"manifest": str(manifest_path),
					"chars": chars,
					"duration_sec": round(duration, 3),
					"chars_per_minute": round(cpm, 3),
				}
	return DEFAULT_CHARS_PER_MINUTE, {
		"method": "default_worldview_podcast_vibevoice_estimate",
		"chars_per_minute": DEFAULT_CHARS_PER_MINUTE,
		"basis": "Calibrated from local historical VibeVoice Chinese dialogue manifests on 2026-06-24 with scripts/estimate_vibevoice_chars_per_minute.py: aggregate runs n=15 median=325.8 chars/min p75=335.3; chunk runs n=102 median=341.8; all records n=117 median=336.8. Representative long Worldview runs landed at 325.8-336.8 chars/min, so 330 is used as the default planning midpoint before real audio exists.",
	}


def _segment_index(segment: dict[str, Any]) -> int:
	return int(segment.get("segment_index") or segment.get("source_segment_index") or segment.get("episode_local_segment_index"))


def _turn_source_segment_index(turn: dict[str, Any]) -> int | None:
	value = turn.get("source_segment_index")
	if value is None:
		value = turn.get("source_segment_index_original")
	if value is None:
		return None
	return int(value)


def _build_chapter_units(chapter_data: dict[str, Any], segments: list[dict[str, Any]], turns: list[dict[str, Any]], hard_max_chars: int) -> tuple[list[ChapterUnit], list[str]]:
	warnings: list[str] = []
	segments_by_index = {_segment_index(segment): segment for segment in segments}
	turns_by_segment: dict[int, list[dict[str, Any]]] = {}
	for turn in turns:
		segment_index = _turn_source_segment_index(turn)
		if segment_index is None:
			continue
		turns_by_segment.setdefault(segment_index, []).append(turn)
	chapters = list(chapter_data.get("chapters") or [])
	assert chapters, "chapter_segments has no chapters"
	units: list[ChapterUnit] = []
	for chapter_index, chapter in enumerate(chapters, start=1):
		start = int(chapter["segment_start"])
		end = int(chapter["segment_end"])
		chapter_segments = [segments_by_index[index] for index in range(start, end + 1) if index in segments_by_index]
		chapter_turns = [turn for index in range(start, end + 1) for turn in turns_by_segment.get(index, [])]
		if not chapter_segments:
			warnings.append(f"chapter {chapter.get('chapter_id') or chapter_index} has no matching translated segments")
			continue
		title = _clean_title(chapter.get("title") or chapter.get("chapter_title"), f"第{chapter_index}部分")
		unit = ChapterUnit(
			chapter_id=str(chapter.get("chapter_id") or f"chapter_{chapter_index:03d}"),
			title=title,
			source_start=chapter.get("source_start") or chapter_segments[0].get("source_start"),
			source_end=chapter.get("source_end") or chapter_segments[-1].get("source_end"),
			source_start_sec=_parse_time_to_sec(chapter.get("source_start") or chapter_segments[0].get("source_start")),
			source_end_sec=_parse_time_to_sec(chapter.get("source_end") or chapter_segments[-1].get("source_end")),
			segment_start=start,
			segment_end=end,
			segments=chapter_segments,
			turns=chapter_turns,
			char_count=sum(_char_count(str(segment.get("zh_text") or "")) for segment in chapter_segments),
			original_chapter_ids=[str(chapter.get("chapter_id") or f"chapter_{chapter_index:03d}")],
		)
		units.extend(_split_oversized_unit(unit, hard_max_chars, warnings))
	assert units, "No usable chapter units for episode split"
	return units, warnings


def _split_oversized_unit(unit: ChapterUnit, hard_max_chars: int, warnings: list[str]) -> list[ChapterUnit]:
	if unit.char_count <= hard_max_chars:
		return [unit]
	warnings.append(
		f"chapter {unit.chapter_id} estimated_chars={unit.char_count} exceeds episode hard max {hard_max_chars}; splitting inside chapter at segment boundaries"
	)
	result: list[ChapterUnit] = []
	current_segments: list[dict[str, Any]] = []
	current_turns: list[dict[str, Any]] = []
	current_chars = 0
	turns_by_segment: dict[int, list[dict[str, Any]]] = {}
	for turn in unit.turns:
		segment_index = _turn_source_segment_index(turn)
		if segment_index is not None:
			turns_by_segment.setdefault(segment_index, []).append(turn)
	for segment in unit.segments:
		segment_chars = _char_count(str(segment.get("zh_text") or ""))
		if current_segments and current_chars + segment_chars > hard_max_chars:
			result.append(_unit_from_segments(unit, len(result) + 1, current_segments, current_turns))
			current_segments = []
			current_turns = []
			current_chars = 0
		current_segments.append(segment)
		segment_index = _segment_index(segment)
		current_turns.extend(turns_by_segment.get(segment_index, []))
		current_chars += segment_chars
	if current_segments:
		result.append(_unit_from_segments(unit, len(result) + 1, current_segments, current_turns))
	return result


def _unit_from_segments(unit: ChapterUnit, part_index: int, segments: list[dict[str, Any]], turns: list[dict[str, Any]]) -> ChapterUnit:
	start = _segment_index(segments[0])
	end = _segment_index(segments[-1])
	title = f"{unit.title}（{part_index}）"
	return ChapterUnit(
		chapter_id=f"{unit.chapter_id}_part_{part_index:02d}",
		title=title,
		source_start=segments[0].get("source_start") or _format_sec(unit.source_start_sec),
		source_end=segments[-1].get("source_end") or _format_sec(unit.source_end_sec),
		source_start_sec=_parse_time_to_sec(segments[0].get("source_start")) or unit.source_start_sec,
		source_end_sec=_parse_time_to_sec(segments[-1].get("source_end")) or unit.source_end_sec,
		segment_start=start,
		segment_end=end,
		segments=segments,
		turns=turns,
		char_count=sum(_char_count(str(segment.get("zh_text") or "")) for segment in segments),
		original_chapter_ids=unit.original_chapter_ids,
		forced_split=True,
	)


def _subtitle_for_units(units: list[ChapterUnit], max_len: int = 24) -> str:
	titles: list[str] = []
	for unit in units:
		title = re.sub(r"（\d+）$", "", unit.title)
		if title and all(title not in existing and existing not in title for existing in titles):
			titles.append(title)
	if not titles:
		return "核心对话"
	if len(titles) == 1:
		return titles[0][:max_len]
	combined = f"{titles[0]}与{titles[-1]}"
	if len(combined) <= max_len:
		return combined
	return titles[0][:max_len]


def _build_episode_plans(
	units: list[ChapterUnit],
	chars_per_minute: float,
	target_minutes_min: float,
	target_minutes_max: float,
	target_minutes_ideal: float,
) -> tuple[list[EpisodePlan], list[str]]:
	assert target_minutes_min > 0
	assert target_minutes_max >= target_minutes_min
	min_chars = round(target_minutes_min * chars_per_minute)
	max_chars = round(target_minutes_max * chars_per_minute)
	ideal_chars = round(target_minutes_ideal * chars_per_minute)
	warnings: list[str] = []
	episodes_units: list[list[ChapterUnit]] = []
	current: list[ChapterUnit] = []
	current_chars = 0
	for unit in units:
		if not current:
			current = [unit]
			current_chars = unit.char_count
			continue
		candidate_chars = current_chars + unit.char_count
		if current_chars >= min_chars and abs(candidate_chars - ideal_chars) > abs(current_chars - ideal_chars):
			episodes_units.append(current)
			current = [unit]
			current_chars = unit.char_count
			continue
		if candidate_chars <= max_chars:
			current.append(unit)
			current_chars = candidate_chars
			continue
		episodes_units.append(current)
		current = [unit]
		current_chars = unit.char_count
	if current:
		episodes_units.append(current)
	if len(episodes_units) >= 2:
		last_chars = sum(unit.char_count for unit in episodes_units[-1])
		previous_chars = sum(unit.char_count for unit in episodes_units[-2])
		if last_chars < min_chars and previous_chars + last_chars <= max_chars:
			episodes_units[-2].extend(episodes_units[-1])
			episodes_units.pop()
	if len(episodes_units) == 1 and sum(unit.char_count for unit in episodes_units[0]) < min_chars:
		warnings.append("source transcript is shorter than the 30-minute target; using one shorter episode")
	plans: list[EpisodePlan] = []
	for episode_index, episode_units in enumerate(episodes_units, start=1):
		segments = [segment for unit in episode_units for segment in unit.segments]
		turns = [turn for unit in episode_units for turn in unit.turns]
		char_count = sum(unit.char_count for unit in episode_units)
		source_start_sec = next((unit.source_start_sec for unit in episode_units if unit.source_start_sec is not None), None)
		source_end_sec = next((unit.source_end_sec for unit in reversed(episode_units) if unit.source_end_sec is not None), None)
		if char_count < min_chars and len(episodes_units) > 1:
			warnings.append(f"episode_{episode_index:03d} estimated below 30 minutes: chars={char_count} min_chars={min_chars}")
		if char_count > max_chars:
			warnings.append(f"episode_{episode_index:03d} estimated above 40 minutes: chars={char_count} max_chars={max_chars}")
		plans.append(EpisodePlan(
			episode_index=episode_index,
			units=episode_units,
			char_count=char_count,
			estimated_minutes=char_count / chars_per_minute,
			subtitle=_subtitle_for_units(episode_units),
			source_start=episode_units[0].source_start or _format_sec(source_start_sec),
			source_end=episode_units[-1].source_end or _format_sec(source_end_sec),
			source_start_sec=source_start_sec,
			source_end_sec=source_end_sec,
			segments=segments,
			turns=turns,
		))
	return plans, warnings


def _remove_existing(path: Path) -> None:
	if path.is_symlink() or path.is_file():
		path.unlink()
	elif path.exists():
		shutil.rmtree(path)


def _symlink_or_copy(src: Path, dst: Path, force: bool) -> None:
	if not src.exists():
		return
	if dst.exists() or dst.is_symlink():
		if not force:
			return
		_remove_existing(dst)
	dst.parent.mkdir(parents=True, exist_ok=True)
	try:
		os.symlink(src, dst, target_is_directory=src.is_dir())
	except OSError:
		if src.is_dir():
			shutil.copytree(src, dst)
		else:
			shutil.copy2(src, dst)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _duration(path: Path) -> float:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		str(path),
	])
	return float(result.stdout.strip())


def _create_episode_source_video(run_dir: Path, episode_dir: Path, plan: EpisodePlan, force: bool) -> dict[str, Any]:
	source = run_dir / "02-source-capture/youtube-media/source.mp4"
	node_dir = episode_dir / "04b-source-video-segment"
	manifest_path = node_dir / "source_episode_manifest.json"
	output = node_dir / "source_episode.mp4"
	node_dir.mkdir(parents=True, exist_ok=True)
	if not source.exists():
		result = {
			"schema_version": "worldview-china-podcast-episode-source-video.v1",
			"status": "skipped",
			"skip_reason": "parent_source_video_missing",
			"source_video": str(source),
			"source_start_sec": plan.source_start_sec,
			"source_end_sec": plan.source_end_sec,
		}
		_write_json(manifest_path, result)
		return result
	if plan.source_start_sec is None or plan.source_end_sec is None:
		result = {
			"schema_version": "worldview-china-podcast-episode-source-video.v1",
			"status": "skipped",
			"skip_reason": "episode_source_time_range_missing",
			"source_video": str(source),
			"source_start_sec": plan.source_start_sec,
			"source_end_sec": plan.source_end_sec,
		}
		_write_json(manifest_path, result)
		return result
	start_sec = max(0.0, float(plan.source_start_sec))
	end_sec = max(start_sec, float(plan.source_end_sec))
	duration_sec = end_sec - start_sec
	assert duration_sec > 0.5, f"Episode source video segment duration is too short: {duration_sec:.3f}s"
	if force or not output.exists():
		_run([
			"ffmpeg",
			"-hide_banner",
			"-loglevel",
			"error",
			"-y",
			"-ss",
			f"{start_sec:.3f}",
			"-i",
			str(source),
			"-t",
			f"{duration_sec:.3f}",
			"-map",
			"0:v:0",
			"-an",
			"-c:v",
			"libx264",
			"-preset",
			"veryfast",
			"-crf",
			"18",
			"-pix_fmt",
			"yuv420p",
			"-movflags",
			"+faststart",
			str(output),
		])
	actual_duration = _duration(output)
	result = {
		"schema_version": "worldview-china-podcast-episode-source-video.v1",
		"status": "pass",
		"source_video": str(source.resolve()),
		"source_episode_video": str(output.resolve()),
		"source_start_sec": round(start_sec, 3),
		"source_end_sec": round(end_sec, 3),
		"planned_duration_sec": round(duration_sec, 3),
		"actual_duration_sec": round(actual_duration, 3),
		"audio_policy": "silent_video_segment_for_later_chinese_revoice",
		"selection_basis": "episode semantic source_start/source_end from translated chapter segments",
	}
	_write_json(manifest_path, result)
	return result


def _renumber_segments(segments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, int]]:
	renumbered: list[dict[str, Any]] = []
	mapping: dict[int, int] = {}
	for local_index, segment in enumerate(segments, start=1):
		original_index = _segment_index(segment)
		mapping[original_index] = local_index
		item = dict(segment)
		item["source_segment_index_original"] = original_index
		item["segment_index"] = local_index
		renumbered.append(item)
	return renumbered, mapping


def _renumber_turns(turns: list[dict[str, Any]], segment_mapping: dict[int, int]) -> list[dict[str, Any]]:
	renumbered: list[dict[str, Any]] = []
	for turn in turns:
		original_segment = _turn_source_segment_index(turn)
		if original_segment is None or original_segment not in segment_mapping:
			continue
		item = dict(turn)
		item["source_turn_index_original"] = int(turn.get("turn_index") or len(renumbered) + 1)
		item["turn_index"] = len(renumbered) + 1
		item["source_segment_index_original"] = original_segment
		item["source_segment_index"] = segment_mapping[original_segment]
		item["text"] = _normalize_tts_text(str(item.get("text") or ""))
		item["char_count"] = _char_count(str(item.get("text") or ""))
		renumbered.append(item)
	assert renumbered, "Episode has no script turns after renumbering"
	return renumbered


def _write_translation_subset(
	episode_dir: Path,
	parent_translation: dict[str, Any],
	segments: list[dict[str, Any]],
	chapter_units: list[ChapterUnit],
	segment_mapping: dict[int, int],
	safe_enabled: bool,
) -> None:
	faithful_dir = episode_dir / "03-source-translation"
	faithful_dir.mkdir(parents=True, exist_ok=True)
	translation = dict(parent_translation)
	translation["segments"] = segments
	translation["series_episode_scope"] = "episode_subset_full_for_this_part"
	_write_json(faithful_dir / "source_transcript.zh.json", translation)
	_write_translation_md(faithful_dir / "source_transcript.zh.md", segments)
	_write_json(faithful_dir / "chapter_segments.json", _chapter_subset_payload(chapter_units, segment_mapping, "worldview-china-podcast-episode-chapters.v1"))
	if safe_enabled:
		safe_dir = episode_dir / "03b-mainland-publish-safety"
		safe_dir.mkdir(parents=True, exist_ok=True)
		safe_translation = dict(translation)
		safe_translation["content_coverage"] = "mainland_publish_safety_edited"
		_write_json(safe_dir / "source_transcript.zh.safe.json", safe_translation)
		_write_translation_md(safe_dir / "source_transcript.zh.safe.md", segments)
		_write_json(safe_dir / "chapter_segments.safe.json", _chapter_subset_payload(chapter_units, segment_mapping, "worldview-china-podcast-episode-safe-chapters.v1"))
		_write_json(safe_dir / "edit_decisions.json", {
			"schema_version": "worldview-china-mainland-publish-safety-decisions.v1",
			"series_episode_subset": True,
			"decisions": [],
		})
		(safe_dir / "safety_report.md").write_text(
			"\n".join([
				"# Mainland Publish Safety Episode Report",
				"",
				"- status: PASS",
				"- content_coverage: mainland_publish_safety_edited",
				"- series_episode_subset: true",
				"- note: parent 03b safety edit was already applied before episode splitting; this file preserves the episode-local contract.",
			]) + "\n",
			encoding="utf-8",
		)


def _chapter_subset_payload(chapter_units: list[ChapterUnit], segment_mapping: dict[int, int], schema_version: str) -> dict[str, Any]:
	chapters: list[dict[str, Any]] = []
	for local_index, unit in enumerate(chapter_units, start=1):
		start = segment_mapping[unit.segment_start]
		end = segment_mapping[unit.segment_end]
		chapters.append({
			"chapter_id": f"episode_chapter_{local_index:03d}",
			"source_chapter_ids": unit.original_chapter_ids,
			"title": unit.title,
			"source_start": unit.source_start,
			"source_end": unit.source_end,
			"source_start_sec": unit.source_start_sec,
			"source_end_sec": unit.source_end_sec,
			"segment_start": start,
			"segment_end": end,
			"original_segment_start": unit.segment_start,
			"original_segment_end": unit.segment_end,
			"estimated_zh_chars": unit.char_count,
			"forced_split_inside_chapter": unit.forced_split,
		})
	return {
		"schema_version": schema_version,
		"series_episode_subset": True,
		"chapters": chapters,
	}


def _write_translation_md(path: Path, segments: list[dict[str, Any]]) -> None:
	lines = ["# 中文翻译稿（分集子集）", ""]
	for segment in segments:
		lines.append(f"{segment.get('speaker', 'Speaker 0')}: {segment.get('zh_text', '')}")
	path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_script_subset(episode_dir: Path, turns: list[dict[str, Any]], safe_enabled: bool) -> None:
	output_dir = episode_dir / "04-podcast-script"
	output_dir.mkdir(parents=True, exist_ok=True)
	content_coverage = "mainland_publish_safety_edited" if safe_enabled else "full_translation"
	source = "03b-mainland-publish-safety/source_transcript.zh.safe.json" if safe_enabled else "03-source-translation/source_transcript.zh.json"
	lines = [
		"---",
		"schema_version: worldview-china-podcast-script.v1",
		f"content_coverage: {content_coverage}",
		f"source: {source}",
		"series_episode_subset: true",
		"---",
		"",
		"## 正文",
		"",
	]
	lines.extend(f"{turn['speaker']}: {turn['text']}" for turn in turns)
	script_path = output_dir / "podcast_script.md"
	script_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
	(episode_dir / "podcast_script.md").write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")
	total_chars = sum(int(turn["char_count"]) for turn in turns)
	(output_dir / "script_report.md").write_text(
		"\n".join([
			"# Script Report",
			"",
			"- status: PASS",
			f"- content_coverage: {content_coverage}",
			f"- source: {source}",
			"- series_episode_subset: true",
			"- no_summarization: true",
			"- source_order_preserved: true",
			f"- turn_count: {len(turns)}",
			f"- total_display_chars: {total_chars}",
		]) + "\n",
		encoding="utf-8",
	)
	_write_json(output_dir / "script_turns.json", {
		"schema_version": "worldview-china-script-turns.v1",
		"content_coverage": content_coverage,
		"series_episode_subset": True,
		"turns": turns,
	})


def _parse_publish_start(value: str | None, timezone_name: str) -> datetime | None:
	if not value:
		return None
	timezone = ZoneInfo(timezone_name)
	text = value.strip()
	if "T" not in text and " " in text:
		text = text.replace(" ", "T", 1)
	dt = datetime.fromisoformat(text)
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=timezone)
	return dt.astimezone(timezone)


def _schedule_for_episode(first_publish: datetime | None, episode_index: int) -> dict[str, Any]:
	if first_publish is None:
		return {
			"scheduled_publish_at": None,
			"scheduled_publish_timezone": None,
			"schedule_source": None,
		}
	publish_at = first_publish + timedelta(hours=episode_index - 1)
	return {
		"scheduled_publish_at": publish_at.isoformat(),
		"scheduled_publish_timezone": str(first_publish.tzinfo.key if hasattr(first_publish.tzinfo, "key") else first_publish.tzinfo),
		"schedule_source": "series_first_publish_at_plus_episode_index_hours",
	}


def _write_episode_seed_metadata(episode_dir: Path, schedule: dict[str, Any], episode_index: int, episode_count: int) -> None:
	if not schedule.get("scheduled_publish_at"):
		return
	_write_json(episode_dir / "bilibili_upload_metadata.json", {
		"schema_version": "bilibili_upload_metadata.v1",
		"scheduled_publish_at": schedule["scheduled_publish_at"],
		"scheduled_publish_timezone": schedule["scheduled_publish_timezone"] or "Asia/Shanghai",
		"schedule_source": schedule["schedule_source"],
		"series_episode_index": episode_index,
		"series_episode_count": episode_count,
	})


def _write_execution_plan(run_dir: Path, series_manifest: dict[str, Any]) -> None:
	lines = [
		"# Series Episode Execution Plan",
		"",
		"- serial_execution_required: true",
		"- note: Run every episode to completion before starting the next one; VibeVoice generation must not run concurrently. Default device is MPS; CPU is a fallback.",
		"",
	]
	for episode in series_manifest["episodes"]:
		episode_dir = episode["episode_run_dir"]
		index = int(episode["episode_index"])
		lines.extend([
			f"## Episode {index:02d}",
			"",
			f"- title: {episode['video_title']}",
			f"- scheduled_publish_at: {episode.get('scheduled_publish_at') or 'none'}",
			f"- source_episode_video: {episode.get('source_episode_video') or episode.get('source_episode_video_status') or 'not materialized'}",
			"",
			"```bash",
			"/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \\",
			"  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-podcast-title-cover/scripts/build_title_cover.py \\",
			f"  --run-dir {episode_dir} \\",
			f"  --speaker-label {json.dumps(series_manifest['series_title_prefix'], ensure_ascii=False)} \\",
			f"  --translated-title-core {json.dumps(episode['episode_subtitle'], ensure_ascii=False)} \\",
			f"  --episode-index {index} \\",
			f"  --episode-title-template {json.dumps(series_manifest['episode_title_template'], ensure_ascii=False)} \\",
			f"  --episode-order-marker-template {json.dumps(series_manifest['episode_order_marker_template'], ensure_ascii=False)} \\",
			f"  --frame {json.dumps(series_manifest['shared_cover_frame'], ensure_ascii=False)} \\",
			"  --force",
			"",
			"python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_vibevoice_chunks.py \\",
			f"  --run-dir {episode_dir} \\",
			"  --generation-runner resident_batch",
			"",
			"/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \\",
			"  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_source_video_revoice.py \\",
			f"  --run-dir {episode_dir} --match-audio-duration --force",
			"```",
			"",
			"Then run 06 alignment, 07 subtitles, 09 QA, 10 metadata, and 11 Bilibili upload publish for this episode before continuing.",
			"",
		])
	(run_dir / SERIES_NODE / "series_execution_plan.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def split_series(
	run_dir: Path,
	series_title_prefix: str,
	first_scheduled_publish_at: str | None,
	scheduled_publish_timezone: str,
	episode_title_template: str,
	episode_order_marker_template: str,
	chars_per_minute_override: float | None,
	calibration_audio_manifest: Path | None,
	target_minutes_min: float,
	target_minutes_max: float,
	target_minutes_ideal: float,
	force: bool,
) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	assert run_dir.exists(), f"Missing run dir: {run_dir}"
	assert series_title_prefix and "：" not in series_title_prefix, "series_title_prefix should be the shared prefix before `：`"
	faithful_path, safe_path, chapter_path = _load_translation_paths(run_dir)
	parent_translation = _read_json(safe_path or faithful_path)
	segments = list(parent_translation.get("segments") or [])
	assert segments, f"No translated segments in {safe_path or faithful_path}"
	turns = _load_script_turns(run_dir)
	chars_per_minute, estimation = _derive_chars_per_minute(run_dir, chars_per_minute_override, calibration_audio_manifest)
	max_chars = round(target_minutes_max * chars_per_minute)
	chapter_units, chapter_warnings = _build_chapter_units(_read_json(chapter_path), segments, turns, max_chars)
	episode_plans, grouping_warnings = _build_episode_plans(
		chapter_units,
		chars_per_minute,
		target_minutes_min,
		target_minutes_max,
		target_minutes_ideal,
	)
	first_publish = _parse_publish_start(first_scheduled_publish_at, scheduled_publish_timezone)
	node_dir = run_dir / SERIES_NODE
	node_dir.mkdir(parents=True, exist_ok=True)
	shared_cover_frame = _select_shared_cover_frame(run_dir)
	episodes: list[dict[str, Any]] = []
	for plan in episode_plans:
		episode_dir = node_dir / f"episode_{plan.episode_index:03d}"
		episode_dir.mkdir(parents=True, exist_ok=True)
		for name in ("02-source-capture", "02a-speaker-census", "02b-source-voice-prompts", "02c-qwen-vibevoice-prompts"):
			_symlink_or_copy(run_dir / name, episode_dir / name, force)
		renumbered_segments, segment_mapping = _renumber_segments(plan.segments)
		renumbered_turns = _renumber_turns(plan.turns, segment_mapping)
		safe_enabled = safe_path is not None
		_write_translation_subset(episode_dir, parent_translation, renumbered_segments, plan.units, segment_mapping, safe_enabled)
		_write_script_subset(episode_dir, renumbered_turns, safe_enabled)
		source_video_segment = _create_episode_source_video(run_dir, episode_dir, plan, force)
		episode_label = _chinese_episode_label(plan.episode_index)
		order_marker = _episode_order_marker(plan.episode_index, episode_order_marker_template)
		video_title = _format_episode_title(series_title_prefix, plan.episode_index, plan.subtitle, episode_title_template, episode_order_marker_template)
		cover_title = _cover_title(series_title_prefix, plan.subtitle)
		schedule = _schedule_for_episode(first_publish, plan.episode_index)
		_write_episode_seed_metadata(episode_dir, schedule, plan.episode_index, len(episode_plans))
		episode_manifest = {
			"schema_version": "worldview-china-podcast-series-episode.v1",
			"parent_run_dir": str(run_dir),
			"series_node": SERIES_NODE,
			"episode_index": plan.episode_index,
			"episode_count": len(episode_plans),
			"episode_label": episode_label,
			"episode_order_marker": order_marker,
			"episode_id": f"episode_{plan.episode_index:03d}",
			"series_title_prefix": series_title_prefix,
			"episode_subtitle": plan.subtitle,
			"episode_title_template": episode_title_template,
			"episode_order_marker_template": episode_order_marker_template,
			"video_title": video_title,
			"cover_title": cover_title,
			"cover_title_omits_episode_index": True,
			"source_start": plan.source_start,
			"source_end": plan.source_end,
			"source_start_sec": plan.source_start_sec,
			"source_end_sec": plan.source_end_sec,
			"source_episode_video_status": source_video_segment.get("status"),
			"source_episode_video": source_video_segment.get("source_episode_video"),
			"source_episode_video_manifest": str(episode_dir / "04b-source-video-segment/source_episode_manifest.json"),
			"source_episode_video_duration_sec": source_video_segment.get("actual_duration_sec"),
			"estimated_zh_chars": plan.char_count,
			"estimated_minutes": round(plan.estimated_minutes, 3),
			"duration_estimation": estimation,
			"chapter_ids": [unit.chapter_id for unit in plan.units],
			"original_chapter_ids": [chapter_id for unit in plan.units for chapter_id in unit.original_chapter_ids],
			"original_segment_start": _segment_index(plan.segments[0]),
			"original_segment_end": _segment_index(plan.segments[-1]),
			"turn_count": len(renumbered_turns),
			"serial_execution_required": True,
			"downstream_nodes": DOWNSTREAM_NODES,
			**schedule,
		}
		_write_json(episode_dir / "episode_manifest.json", episode_manifest)
		_write_json(episode_dir / "run_manifest.json", {
			"schema_version": "worldview-china-podcast-episode-run.v1",
			"parent_run_dir": str(run_dir),
			"episode_manifest": "episode_manifest.json",
			"series_episode": True,
			"nodes": {
				"04b-series-episode-materialization": {
					"status": "pass",
					"episode_manifest": str(episode_dir / "episode_manifest.json"),
				}
			},
		})
		episodes.append({
			"episode_index": plan.episode_index,
			"episode_label": episode_label,
			"episode_id": f"episode_{plan.episode_index:03d}",
			"episode_run_dir": str(episode_dir),
			"episode_manifest": str(episode_dir / "episode_manifest.json"),
			"video_title": video_title,
			"cover_title": cover_title,
			"episode_subtitle": plan.subtitle,
			"episode_order_marker": order_marker,
			"episode_title_template": episode_title_template,
			"episode_order_marker_template": episode_order_marker_template,
			"estimated_zh_chars": plan.char_count,
			"estimated_minutes": round(plan.estimated_minutes, 3),
			"source_start_sec": plan.source_start_sec,
			"source_end_sec": plan.source_end_sec,
			"source_episode_video_status": source_video_segment.get("status"),
			"source_episode_video": source_video_segment.get("source_episode_video"),
			"source_episode_video_manifest": str(episode_dir / "04b-source-video-segment/source_episode_manifest.json"),
			"scheduled_publish_at": schedule["scheduled_publish_at"],
			"scheduled_publish_timezone": schedule["scheduled_publish_timezone"],
			"schedule_source": schedule["schedule_source"],
		})
	series_manifest = {
		"schema_version": "worldview-china-podcast-series.v1",
		"parent_run_dir": str(run_dir),
		"node": SERIES_NODE,
		"series_title_prefix": series_title_prefix,
		"episode_count": len(episodes),
		"episode_title_template": episode_title_template,
		"episode_order_marker_template": episode_order_marker_template,
		"serial_execution_required": True,
		"parallel_execution_allowed": False,
		"duration_estimation": estimation,
		"target_minutes_min": target_minutes_min,
		"target_minutes_max": target_minutes_max,
		"target_minutes_ideal": target_minutes_ideal,
		"target_chars_min": round(target_minutes_min * chars_per_minute),
		"target_chars_max": round(target_minutes_max * chars_per_minute),
		"shared_cover_frame": str(shared_cover_frame),
		"warnings": chapter_warnings + grouping_warnings,
		"episodes": episodes,
		"completion_gate": "all episodes must complete downstream nodes in order before the parent run is complete",
	}
	_write_json(node_dir / "series_manifest.json", series_manifest)
	_write_execution_plan(run_dir, series_manifest)
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})[SERIES_NODE] = {
		"status": "pass",
		"series_manifest": str(node_dir / "series_manifest.json"),
		"episode_count": len(episodes),
		"serial_execution_required": True,
	}
	_write_json(run_manifest_path, run_manifest)
	return series_manifest


def _select_shared_cover_frame(run_dir: Path) -> Path:
	for path in (
		run_dir / "02-source-capture/source-video-frame-qa/middle.png",
		run_dir / "02-source-capture/source-video-frame-qa/opening.png",
		run_dir / "02-source-capture/source-video-frame-qa/end.png",
		run_dir / "cover/background_raw.png",
	):
		if path.exists():
			return path.resolve()
	return (run_dir / "02-source-capture/youtube-media/source.mp4").resolve()


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Split a translated Worldview China podcast run into serial publishable episode runs.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--series-title-prefix", required=True, help="Shared series title, e.g. 沃尔夫访谈, 世界眼中的中国, or any justified concise series name.")
	parser.add_argument("--first-scheduled-publish-at", help="First Bilibili scheduled publish datetime. Later episodes add one hour each. Accepts ISO or 'YYYY-MM-DD HH:MM'.")
	parser.add_argument("--scheduled-publish-timezone", default="Asia/Shanghai")
	parser.add_argument(
		"--episode-title-template",
		default=DEFAULT_EPISODE_TITLE_TEMPLATE,
		help=(
			"Episode Bilibili title template. Available fields: {series_title}, {episode_index}, "
			"{episode_label}, {episode_order_marker}, {subtitle}. Default: "
			f"{DEFAULT_EPISODE_TITLE_TEMPLATE}"
		),
	)
	parser.add_argument(
		"--episode-order-marker-template",
		default=DEFAULT_EPISODE_ORDER_MARKER_TEMPLATE,
		help=(
			"Series-wide order marker template. Available fields: {episode_index}, {episode_label}. "
			f"Default: {DEFAULT_EPISODE_ORDER_MARKER_TEMPLATE}"
		),
	)
	parser.add_argument("--chars-per-minute", type=float, help="Override normalized Chinese characters per minute. Default is calibrated from audio_manifest if present, otherwise 330.")
	parser.add_argument("--calibration-audio-manifest", type=Path)
	parser.add_argument("--target-minutes-min", type=float, default=DEFAULT_TARGET_MINUTES_MIN)
	parser.add_argument("--target-minutes-max", type=float, default=DEFAULT_TARGET_MINUTES_MAX)
	parser.add_argument("--target-minutes-ideal", type=float, default=DEFAULT_TARGET_MINUTES_IDEAL)
	parser.add_argument("--force", action="store_true")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	manifest = split_series(
		run_dir=args.run_dir.expanduser().resolve(),
		series_title_prefix=args.series_title_prefix,
		first_scheduled_publish_at=args.first_scheduled_publish_at,
		scheduled_publish_timezone=args.scheduled_publish_timezone,
		episode_title_template=args.episode_title_template,
		episode_order_marker_template=args.episode_order_marker_template,
		chars_per_minute_override=args.chars_per_minute,
		calibration_audio_manifest=args.calibration_audio_manifest.expanduser().resolve() if args.calibration_audio_manifest else None,
		target_minutes_min=args.target_minutes_min,
		target_minutes_max=args.target_minutes_max,
		target_minutes_ideal=args.target_minutes_ideal,
		force=args.force,
	)
	print(json.dumps({
		"series_manifest": str(Path(args.run_dir).expanduser().resolve() / SERIES_NODE / "series_manifest.json"),
		"episode_count": manifest["episode_count"],
		"serial_execution_required": manifest["serial_execution_required"],
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
