#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


FORBIDDEN_CHINESE_CONTEMPORARY_LEADER_NAMES = [
	"习近平",
	"习主席",
	"Xi Jinping",
	"Xijinping",
]


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _duration(path: Path) -> float:
	result = subprocess.run(
		["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return float(result.stdout.strip())


def _probe(path: Path) -> dict[str, Any]:
	result = subprocess.run(
		["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
		check=True,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	return json.loads(result.stdout)


def _exists(path: Path, failures: list[str], label: str) -> bool:
	if not path.exists():
		failures.append(f"Missing {label}: {path}")
		return False
	return True


def _read_text(path: Path) -> str:
	return path.read_text(encoding="utf-8") if path.exists() else ""


def _forbidden_chinese_leader_names(text: str) -> list[str]:
	found = [name for name in FORBIDDEN_CHINESE_CONTEMPORARY_LEADER_NAMES if name in text]
	if re.search(r"(?<![A-Za-z])Xi(?![A-Za-z])", text):
		found.append("Xi")
	return sorted(set(found))


def run_qa(run_dir: Path, write_history: bool) -> dict[str, Any]:
	failures: list[str] = []
	warnings: list[str] = []
	source_voice_prompt_manifest = run_dir / "02b-source-voice-prompts/voice_prompt_manifest.json"
	qwen_voice_prompt_manifest = run_dir / "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json"
	voice_prompt_manifest = qwen_voice_prompt_manifest if qwen_voice_prompt_manifest.exists() else source_voice_prompt_manifest
	mainland_safety_json = run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json"
	mainland_safety_enabled = mainland_safety_json.exists()
	translation_json_path = mainland_safety_json if mainland_safety_enabled else run_dir / "03-source-translation/source_transcript.zh.json"
	translation_md_path = run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.md" if mainland_safety_enabled else run_dir / "03-source-translation/source_transcript.zh.md"
	chapter_segments_path = run_dir / "03b-mainland-publish-safety/chapter_segments.safe.json" if mainland_safety_enabled else run_dir / "03-source-translation/chapter_segments.json"
	paths = {
		"source_video": run_dir / "02-source-capture/youtube-media/source.mp4",
		"source_audio": run_dir / "02-source-capture/youtube-media/source.wav",
		"source_voice_prompt_manifest": source_voice_prompt_manifest,
		"voice_prompt_manifest": voice_prompt_manifest,
		"source_manifest": run_dir / "02-source-capture/youtube-media/media_manifest.json",
		"frame_report": run_dir / "02-source-capture/source-video-frame-qa/video_form_report.md",
		"video_title": run_dir / "video_title.txt",
		"cover_title": run_dir / "cover/cover_title.json",
		"cover_image_source": run_dir / "cover/image_source_manifest.json",
		"cover_4k": run_dir / "cover/cover_4k.png",
		"cover_compositor_manifest": run_dir / "cover/cover_4k.manifest.json",
		"title_cover_manifest": run_dir / "02d-title-cover/title_cover_manifest.json",
		"faithful_translation_json": run_dir / "03-source-translation/source_transcript.zh.json",
		"translation_json": translation_json_path,
		"translation_md": translation_md_path,
		"chapter_segments": chapter_segments_path,
		"podcast_script": run_dir / "podcast_script.md",
		"script_report": run_dir / "04-podcast-script/script_report.md",
		"chunk_plan": run_dir / "05-vibevoice-chunks/chunk_plan.json",
		"final_audio": run_dir / "audio/final_podcast.wav",
		"audio_manifest": run_dir / "audio/audio_manifest.json",
		"dialogue_timeline": run_dir / "audio/dialogue_timeline.json",
		"subtitles_srt": run_dir / "video/final_subtitles.srt",
		"subtitles_ass": run_dir / "video/final_subtitles.ass",
		"subtitle_manifest": run_dir / "video/subtitle_manifest.json",
		"final_video": run_dir / "video/final_video.mp4",
		"render_manifest": run_dir / "video/render_manifest.json",
	}
	for label, path in paths.items():
		_exists(path, failures, label)
	if mainland_safety_enabled:
		for label, path in {
			"mainland_safety_decisions": run_dir / "03b-mainland-publish-safety/edit_decisions.json",
			"mainland_safety_report": run_dir / "03b-mainland-publish-safety/safety_report.md",
		}.items():
			_exists(path, failures, label)
	if failures:
		return _write_result(run_dir, failures, warnings, write_history)

	source_manifest = _read_json(paths["source_manifest"])
	selected_height = int(source_manifest.get("resolution_selection", {}).get("actual_height") or source_manifest.get("selected_height") or 0)
	available_max_height = int(source_manifest.get("available_max_height") or selected_height or 0)
	if selected_height <= 0:
		failures.append("source video selected height is missing")
	elif available_max_height >= 1440 and selected_height <= 1080:
		failures.append(
			"source video selected height is 1080p or lower while 1440p+ was available "
			"without recorded user downgrade authorization"
		)
	elif available_max_height > 0 and selected_height < available_max_height:
		failures.append(f"source video selected height is below available max: selected={selected_height}, available={available_max_height}")
	audio_format = source_manifest.get("selected_audio_format") or {}
	if "original" not in str(audio_format.get("format_note", "")).lower() and "default" not in str(audio_format.get("format_note", "")).lower():
		failures.append("selected source audio is not original/default")
	if "video_podcast_form: PASS" not in _read_text(paths["frame_report"]) and "Video podcast / interview form: PASS" not in _read_text(paths["frame_report"]):
		failures.append("source frame QA does not record podcast form PASS")
	video_title = _read_text(paths["video_title"]).strip()
	if not video_title:
		failures.append("video_title.txt is empty")
	if "：" not in video_title:
		failures.append("video_title.txt must contain a justified source identity prefix followed by `：`")
	title_prefix, title_core = video_title.split("：", 1) if "：" in video_title else ("", video_title)
	if not title_prefix or not title_core:
		failures.append("video_title.txt source identity prefix or translated title core is empty")
	if len(title_prefix) > 16:
		failures.append(f"video_title.txt source identity prefix is too long: {len(title_prefix)} chars")
	if re.search(r"(来自|中文配音|搬运|油管|YouTube|频道|栏目|播客|Podcast|CGSP)", title_prefix, re.I):
		failures.append("video_title.txt source identity prefix is a lazy source/channel/platform label")
	if re.match(r"^《[^》]+》$", title_prefix):
		failures.append("video_title.txt source identity prefix must describe a person or role, not a decorated channel/program name")
	cover_title = _read_json(paths["cover_title"])
	if str(cover_title.get("title_text") or "").strip() != video_title:
		failures.append("cover_title.json title_text does not equal video_title.txt")
	if cover_title.get("title_source") != "youtube_original_title_translated_with_source_identity":
		failures.append("cover_title.json title_source is not youtube_original_title_translated_with_source_identity")
	if str(cover_title.get("source_identity_label") or "").strip() != title_prefix:
		failures.append("cover_title.json source_identity_label does not equal video_title prefix")
	if str(cover_title.get("translated_title_core") or "").strip() != title_core:
		failures.append("cover_title.json translated_title_core does not equal video_title core")
	cover_image_source = _read_json(paths["cover_image_source"])
	if cover_image_source.get("image_type") != "source_video_frame_background":
		failures.append("cover image source is not source_video_frame_background")
	title_cover_manifest = _read_json(paths["title_cover_manifest"])
	if title_cover_manifest.get("title_layout") != "center":
		failures.append("title_cover_manifest title_layout is not center")
	if title_cover_manifest.get("title_policy") != "source_identity_prefix_plus_youtube_original_title_translated_smoothly":
		failures.append("title_cover_manifest title_policy is not source_identity_prefix_plus_youtube_original_title_translated_smoothly")
	cover_compositor_manifest = _read_json(paths["cover_compositor_manifest"])
	if cover_compositor_manifest.get("layout", {}).get("mode") != "center":
		failures.append("cover compositor layout mode is not center")
	cover_probe = _probe(paths["cover_4k"])
	cover_streams = [stream for stream in cover_probe.get("streams", []) if stream.get("codec_type") == "video"]
	if not cover_streams:
		failures.append("cover_4k.png has no readable image/video stream")
	else:
		cover_stream = cover_streams[0]
		if int(cover_stream.get("width") or 0) != 3840 or int(cover_stream.get("height") or 0) != 2160:
			failures.append(f"cover_4k.png is not 3840x2160: {cover_stream.get('width')}x{cover_stream.get('height')}")

	source_voice_prompt_manifest_data = _read_json(paths["source_voice_prompt_manifest"])
	if source_voice_prompt_manifest_data.get("status") != "pass":
		failures.append("source_voice_prompt_manifest status is not pass")
	voice_prompt_manifest_data = _read_json(paths["voice_prompt_manifest"])
	if voice_prompt_manifest_data.get("status") != "pass":
		failures.append("voice_prompt_manifest status is not pass")
	voice_prompt_schema = str(voice_prompt_manifest_data.get("schema_version") or "")
	is_qwen_chinese_prompt = voice_prompt_schema == "worldview-china-qwen-vibevoice-prompts.v1"
	speaker_voice_names: dict[str, str] = {}
	for speaker in ("Speaker 0", "Speaker 1"):
		info = voice_prompt_manifest_data.get("speaker_voices", {}).get(speaker)
		if not isinstance(info, dict):
			failures.append(f"voice_prompt_manifest missing {speaker}")
			continue
		vibevoice_name = str(info.get("vibevoice_name") or "")
		if not vibevoice_name:
			failures.append(f"voice_prompt_manifest missing vibevoice_name for {speaker}")
		speaker_voice_names[speaker] = vibevoice_name
		reference = Path(str(info.get("reference_wav") or ""))
		registered = Path(str(info.get("registered_path") or ""))
		if not reference.exists():
			failures.append(f"voice reference wav missing for {speaker}: {reference}")
			continue
		if not registered.exists():
			failures.append(f"registered VibeVoice reference missing for {speaker}: {registered}")
		expected_sha = str(info.get("sha256") or "")
		if expected_sha:
			actual_sha = _sha256(reference)
			if actual_sha != expected_sha:
				failures.append(f"voice reference sha256 mismatch for {speaker}: {reference}")
			if registered.exists() and _sha256(registered) != expected_sha:
				failures.append(f"registered voice reference sha256 mismatch for {speaker}: {registered}")
		probe = _probe(reference)
		audio_streams = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
		if not audio_streams:
			failures.append(f"voice reference has no audio stream for {speaker}: {reference}")
			continue
		stream = audio_streams[0]
		if stream.get("codec_name") != "pcm_s16le":
			failures.append(f"voice reference codec is not pcm_s16le for {speaker}: {stream.get('codec_name')}")
		if str(stream.get("sample_rate")) != "24000":
			failures.append(f"voice reference sample_rate is not 24000 for {speaker}: {stream.get('sample_rate')}")
		if int(stream.get("channels") or 0) != 1:
			failures.append(f"voice reference channels is not mono for {speaker}: {stream.get('channels')}")
		duration = float(probe.get("format", {}).get("duration") or 0)
		if is_qwen_chinese_prompt:
			if duration < 5 or duration > 35:
				failures.append(f"Qwen Chinese voice prompt duration is outside 5-35s for {speaker}: {duration:.2f}s")
		elif duration < 25:
			failures.append(f"voice reference is shorter than 25s for {speaker}: {duration:.2f}s")

	translation = _read_json(paths["translation_json"])
	translation_coverage = str(translation.get("content_coverage") or "")
	if mainland_safety_enabled:
		if translation_coverage != "mainland_publish_safety_edited":
			failures.append("mainland safety translation content_coverage is not mainland_publish_safety_edited")
		safety_report = _read_text(run_dir / "03b-mainland-publish-safety/safety_report.md")
		if "status: PASS" not in safety_report:
			failures.append("mainland publish safety report does not record status: PASS")
	else:
		if translation_coverage != "full_translation":
			failures.append("translation content_coverage is not full_translation")
	chapters = _read_json(paths["chapter_segments"]).get("chapters") or []
	if not chapters:
		failures.append("chapter_segments has no chapters")
	else:
		last_end = 0
		for chapter in chapters:
			start = int(chapter["segment_start"])
			end = int(chapter["segment_end"])
			if start <= last_end or end < start:
				failures.append("chapter_segments do not preserve source order")
				break
			last_end = end
	report = _read_text(paths["script_report"])
	if mainland_safety_enabled:
		if "content_coverage: mainland_publish_safety_edited" not in report:
			failures.append("script_report does not record content_coverage=mainland_publish_safety_edited")
		if "source: 03b-mainland-publish-safety/source_transcript.zh.safe.json" not in report:
			failures.append("script_report does not record 03b mainland safety source")
	elif "content_coverage: full_translation" not in report:
		failures.append("script_report does not record content_coverage=full_translation")
	if re.search(r"(?m)^Speaker [^01]:", _read_text(paths["podcast_script"])):
		failures.append("podcast_script contains unsupported Speaker labels")
	translation_display_text = "\n".join(str(segment.get("zh_text") or "") for segment in translation.get("segments") or [])
	for label, text in {
		"translation zh_text": translation_display_text,
		"podcast_script": _read_text(paths["podcast_script"]),
	}.items():
		forbidden = _forbidden_chinese_leader_names(text)
		if forbidden:
			failures.append(f"{label} contains forbidden Chinese contemporary leader names: {', '.join(forbidden)}")

	audio_manifest = _read_json(paths["audio_manifest"])
	audio_manifest_text = "\n".join(
		f"{turn.get('text') or ''}\n{turn.get('tts_text') or ''}"
		for turn in audio_manifest.get("turns") or []
	)
	forbidden_audio_names = _forbidden_chinese_leader_names(audio_manifest_text)
	if forbidden_audio_names:
		failures.append(f"audio_manifest turns contain forbidden Chinese contemporary leader names: {', '.join(forbidden_audio_names)}")
	if audio_manifest.get("audio_backend") != "vibevoice_chunked_dialogue":
		failures.append("audio_manifest audio_backend is not vibevoice_chunked_dialogue")
	if audio_manifest.get("speaker_voices") != speaker_voice_names:
		failures.append("audio_manifest speaker_voices does not match voice_prompt_manifest")
	if not audio_manifest.get("voice_prompt_manifest"):
		failures.append("audio_manifest missing voice_prompt_manifest")
	if not audio_manifest.get("chunks"):
		failures.append("audio_manifest has no chunks")
	if not audio_manifest.get("turns"):
		failures.append("audio_manifest has no turns")
	audio_duration = _duration(paths["final_audio"])
	video_duration = _duration(paths["final_video"])
	render_manifest = _read_json(paths["render_manifest"])
	visual_mode = str(render_manifest.get("visual_mode") or "")
	if visual_mode.startswith("source_video_revoice"):
		target_duration = float(render_manifest.get("target_duration_sec") or render_manifest.get("source_duration_sec") or 0)
		if abs(video_duration - target_duration) > 0.5:
			failures.append(f"source-video revoice duration mismatch: video={video_duration:.2f} target={target_duration:.2f}")
		if visual_mode == "source_video_revoice_strict" and render_manifest.get("subtitle_mode") != "sidecar_not_burned":
			failures.append("strict source-video revoice must keep subtitles sidecar-only, not burned into frames")
	else:
		if abs(video_duration - audio_duration) > 2.0:
			failures.append(f"final video/audio duration mismatch: video={video_duration:.2f} audio={audio_duration:.2f}")

	timeline = _read_json(paths["dialogue_timeline"])
	if not timeline.get("turns") or not timeline.get("cues"):
		failures.append("dialogue_timeline missing turns or cues")
	subtitle_manifest = _read_json(paths["subtitle_manifest"])
	if subtitle_manifest.get("style", {}).get("speaker_labels") is not False:
		failures.append("subtitle_manifest does not disable speaker labels")
	subtitle_manifest_text = "\n".join(str(cue.get("display_text") or cue.get("text") or "") for cue in subtitle_manifest.get("cues") or [])
	subtitle_sidecar_text = "\n".join([
		subtitle_manifest_text,
		_read_text(paths["subtitles_srt"]),
		_read_text(paths["subtitles_ass"]),
	])
	forbidden_subtitle_names = _forbidden_chinese_leader_names(subtitle_sidecar_text)
	if forbidden_subtitle_names:
		failures.append(f"subtitle outputs contain forbidden Chinese contemporary leader names: {', '.join(forbidden_subtitle_names)}")
	for key in ("opening", "middle", "end"):
		screenshot = Path(str(render_manifest.get("screenshots", {}).get(key) or ""))
		if not screenshot.exists():
			failures.append(f"render screenshot missing: {key}")

	return _write_result(run_dir, failures, warnings, write_history)


def _write_result(run_dir: Path, failures: list[str], warnings: list[str], write_history: bool) -> dict[str, Any]:
	output_dir = run_dir / "09-final-qa"
	status = "PASS" if not failures else "FAIL"
	result = {
		"schema_version": "worldview-china-podcast-final-qa.v1",
		"overall_status": status,
		"failures": failures,
		"warnings": warnings,
	}
	_write_json(output_dir / "final-qa-result.json", result)
	lines = [
		"# Final QA Report",
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
	(output_dir / "final-qa-report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["09-final-qa"] = {
		"status": status.lower(),
		"result": str(output_dir / "final-qa-result.json"),
		"report": str(output_dir / "final-qa-report.md"),
	}
	_write_json(run_manifest_path, run_manifest)
	if status == "PASS" and write_history:
		history_path = run_dir.parent / "final-podcast-videos.json"
		history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
		history.append({
			"run_dir": str(run_dir),
			"final_video": str(run_dir / "video/final_video.mp4"),
			"qa_result": str(output_dir / "final-qa-result.json"),
		})
		history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Run final QA for Worldview China podcast video.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--write-history", action="store_true")
	args = parser.parse_args()
	result = run_qa(args.run_dir.expanduser().resolve(), args.write_history)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["overall_status"] == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
