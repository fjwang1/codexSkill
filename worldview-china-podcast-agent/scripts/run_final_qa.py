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
MAX_SPEAKERS = 4
SPEAKER_RE = re.compile(r"^Speaker ([0-3])$")
TARGET_SOURCE_VIDEO_HEIGHT = 1440
TARGET_FINAL_VIDEO_WIDTH = 2560
TARGET_FINAL_VIDEO_HEIGHT = 1440


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


def _speaker_index(speaker: str) -> int:
	match = SPEAKER_RE.fullmatch(speaker)
	assert match, f"Unsupported speaker id: {speaker}"
	return int(match.group(1))


def _sorted_speakers(values: Any) -> list[str]:
	speakers = [str(value) for value in values if SPEAKER_RE.fullmatch(str(value))]
	return sorted(set(speakers), key=_speaker_index)


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


def _is_locked_roster_policy(value: Any) -> bool:
	return str(value or "") in {"locked_multi_speaker_roster", "locked_two_speaker_roster"}


def _has_rolling_caption_repetition(text: str) -> bool:
	words = re.findall(r"[A-Za-z][A-Za-z']+|[\u4e00-\u9fff]", text.lower())
	if len(words) < 12:
		return False
	for size in range(4, 9):
		seen: dict[tuple[str, ...], int] = {}
		for index in range(0, len(words) - size + 1):
			gram = tuple(words[index:index + size])
			seen[gram] = seen.get(gram, 0) + 1
			if seen[gram] >= 3:
				return True
	return False


def _reference_text_noise_reasons(text: str) -> list[str]:
	lower = text.lower()
	reasons = []
	for label, patterns in {
		"music_or_non_speech": ("[music]", "[laughter]"),
		"sponsor_or_ad": ("sponsor", "patreon", "my debt clinic", "debt clinic", "provision capital", "partnering with"),
		"contact_or_url": ("visit ", ".com", "www.", "http", "use code", "subscribe", "become a member", "membership"),
		"finance_ad_terms": ("credit card", "personal loans", "debt relief", "across the nation"),
	}.items():
		if any(pattern in lower for pattern in patterns):
			reasons.append(label)
	if _has_rolling_caption_repetition(text):
		reasons.append("rolling_caption_repetition")
	return sorted(set(reasons))


def _resolve_run_path(run_dir: Path, value: Any) -> Path:
	path = Path(str(value))
	return path if path.is_absolute() else run_dir / path


def _resolved_path_set(values: Any) -> set[str]:
	if not isinstance(values, list):
		return set()
	resolved: set[str] = set()
	for value in values:
		if not isinstance(value, str) or not value.strip():
			continue
		try:
			resolved.add(str(Path(value).expanduser().resolve()))
		except OSError:
			resolved.add(str(Path(value).expanduser()))
	return resolved


def _source_frame_report_has_podcast_pass(text: str) -> bool:
	return bool(
		re.search(r"(?im)^\s*video_podcast_form\s*[:=]\s*PASS\s*$", text)
		or re.search(r"(?im)^\s*video_podcast_form:\s*PASS\s*$", text)
		or "Video podcast / interview form: PASS" in text
	)


def run_qa(run_dir: Path, write_history: bool) -> dict[str, Any]:
	failures: list[str] = []
	warnings: list[str] = []
	episode_manifest_path = run_dir / "episode_manifest.json"
	episode_manifest = _read_json(episode_manifest_path) if episode_manifest_path.exists() else {}
	series_episode = episode_manifest.get("schema_version") == "worldview-china-podcast-series-episode.v1"
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
		"speaker_census": run_dir / "02a-speaker-census/speaker_roster.json",
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
		"translation_semantic_qa": run_dir / "03c-translation-semantic-qa/translation-semantic-qa-result.json",
		"translation_reading_review": run_dir / "03c-translation-semantic-qa/translation-reading-review-result.json",
		"early_text_compliance": run_dir / "03d-risk-compliance-review/text-compliance-review-result.json",
		"text_compliance": run_dir / "04c-bilibili-text-compliance/text-compliance-review-result.json",
		"podcast_script": run_dir / "podcast_script.md",
		"script_report": run_dir / "04-podcast-script/script_report.md",
		"chunk_plan": run_dir / "05-vibevoice-chunks/chunk_plan.json",
		"final_audio": run_dir / "audio/final_podcast.wav",
		"audio_manifest": run_dir / "audio/audio_manifest.json",
		"audio_transcript_integrity": run_dir / "06b-audio-transcript-integrity/audio-transcript-integrity-result.json",
		"voice_consistency": run_dir / "06d-voice-consistency-qa/voice-consistency-qa-result.json",
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
	elif available_max_height >= TARGET_SOURCE_VIDEO_HEIGHT and selected_height < TARGET_SOURCE_VIDEO_HEIGHT:
		failures.append(
			f"source video selected height is below {TARGET_SOURCE_VIDEO_HEIGHT}p while {TARGET_SOURCE_VIDEO_HEIGHT}p+ was available "
			"without recorded user downgrade authorization"
		)
	elif selected_height > TARGET_SOURCE_VIDEO_HEIGHT:
		warnings.append(
			f"source video selected height is above the podcast 2K target; final render must downscale: "
			f"selected={selected_height}, target={TARGET_SOURCE_VIDEO_HEIGHT}"
		)
	audio_format = source_manifest.get("selected_audio_format") or {}
	if "original" not in str(audio_format.get("format_note", "")).lower() and "default" not in str(audio_format.get("format_note", "")).lower():
		failures.append("selected source audio is not original/default")
	if not _source_frame_report_has_podcast_pass(_read_text(paths["frame_report"])):
		failures.append("source frame QA does not record podcast form PASS")
	video_title = _read_text(paths["video_title"]).strip()
	if not video_title:
		failures.append("video_title.txt is empty")
	if "：" not in video_title:
		failures.append("video_title.txt must contain a justified source identity prefix followed by `：`")
	title_prefix, title_core = video_title.split("：", 1) if "：" in video_title else ("", video_title)
	base_title_prefix = title_prefix
	if series_episode:
		base_title_prefix = str(episode_manifest.get("series_title_prefix") or "")
		episode_subtitle = str(episode_manifest.get("episode_subtitle") or "")
		episode_order_marker = str(episode_manifest.get("episode_order_marker") or episode_manifest.get("episode_index") or "")
		expected_video_title = str(episode_manifest.get("video_title") or "")
		if expected_video_title and video_title != expected_video_title:
			failures.append("series episode video_title.txt does not match episode_manifest video_title")
		if base_title_prefix and base_title_prefix not in video_title:
			failures.append("series episode video_title does not contain the shared series title")
		if episode_subtitle and episode_subtitle not in video_title:
			failures.append("series episode video_title does not contain the episode subtitle")
		if episode_order_marker and episode_order_marker not in video_title:
			failures.append("series episode video_title does not contain the episode order marker")
		title_core = episode_subtitle or title_core
	if not title_prefix or not title_core:
		failures.append("video_title.txt source identity prefix or translated title core is empty")
	if len(base_title_prefix) > 16:
		failures.append(f"video_title.txt source identity prefix is too long: {len(base_title_prefix)} chars")
	if re.search(r"(来自|中文配音|搬运|油管|YouTube|频道|栏目|播客|Podcast|CGSP)", base_title_prefix, re.I):
		failures.append("video_title.txt source identity prefix is a lazy source/channel/platform label")
	if re.match(r"^《[^》]+》$", base_title_prefix):
		failures.append("video_title.txt source identity prefix must describe a person or role, not a decorated channel/program name")
	cover_title = _read_json(paths["cover_title"])
	if series_episode:
		expected_cover_title = str(episode_manifest.get("cover_title") or f"{base_title_prefix}：{title_core}")
		if str(cover_title.get("video_title_text") or "").strip() != video_title:
			failures.append("series cover_title.json video_title_text does not equal video_title.txt")
		if str(cover_title.get("title_text") or "").strip() != expected_cover_title:
			failures.append("series cover_title.json title_text must omit episode index but keep the episode subtitle")
		if cover_title.get("cover_title_omits_episode_index") is not True:
			failures.append("series cover_title.json must record cover_title_omits_episode_index=true")
	else:
		if str(cover_title.get("title_text") or "").strip() != video_title:
			failures.append("cover_title.json title_text does not equal video_title.txt")
	if cover_title.get("title_source") not in {
		"youtube_original_title_translated_with_source_identity",
		"podcast_source_identity_plus_platform_native_hook",
	}:
		failures.append("cover_title.json title_source is not an accepted Worldview podcast title source policy")
	if cover_title.get("title_source") == "podcast_source_identity_plus_platform_native_hook":
		attractive_policy = cover_title.get("attractive_title_policy") or {}
		if attractive_policy.get("status") != "PASS":
			failures.append("cover_title.json attractive_title_policy.status is not PASS")
	if str(cover_title.get("source_identity_label") or "").strip() != base_title_prefix:
		failures.append("cover_title.json source_identity_label does not equal video_title prefix")
	if str(cover_title.get("translated_title_core") or "").strip() != title_core:
		failures.append("cover_title.json translated_title_core does not equal video_title core")
	cover_image_source = _read_json(paths["cover_image_source"])
	if cover_image_source.get("image_type") != "source_video_frame_background":
		failures.append("cover image source is not source_video_frame_background")
	title_cover_manifest = _read_json(paths["title_cover_manifest"])
	if title_cover_manifest.get("title_layout") != "center":
		failures.append("title_cover_manifest title_layout is not center")
	expected_title_policies = {
		"source_identity_prefix_plus_youtube_original_title_translated_smoothly",
		"source_identity_prefix_plus_platform_native_hook_title",
	}
	if series_episode:
		expected_title_policies.add("series_episode_indexed_video_title_plus_unindexed_cover_title")
	if title_cover_manifest.get("title_policy") not in expected_title_policies:
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

	speaker_census = _read_json(paths["speaker_census"])
	if speaker_census.get("status") != "frozen":
		failures.append("02a speaker census status is not frozen")
	expected_speakers = _expected_speakers_from_roster(speaker_census, failures, "02a speaker census")
	if float(speaker_census.get("analysis_window_sec") or 0) < 300:
		failures.append("02a speaker census analysis window is shorter than 5 minutes")
	for speaker in expected_speakers:
		if speaker not in (speaker_census.get("speakers") or {}):
			failures.append(f"02a speaker census missing {speaker}")

	source_voice_prompt_manifest_data = _read_json(paths["source_voice_prompt_manifest"])
	if source_voice_prompt_manifest_data.get("status") != "pass":
		failures.append("source_voice_prompt_manifest status is not pass")
	source_census_value = source_voice_prompt_manifest_data.get("speaker_census_roster_path")
	if not source_census_value:
		failures.append("source voice prompt manifest missing speaker_census_roster_path")
	else:
		source_census_path = _resolve_run_path(run_dir, source_census_value)
		if source_census_path.resolve() != paths["speaker_census"].resolve():
			failures.append("source voice prompt manifest does not reference the current 02a speaker census")
	expected_census_sha = str(source_voice_prompt_manifest_data.get("speaker_census_roster_sha256") or "")
	if expected_census_sha and expected_census_sha != _sha256(paths["speaker_census"]):
		failures.append("source voice prompt manifest speaker census sha256 does not match current 02a roster")
	source_speaker_roster = source_voice_prompt_manifest_data.get("speaker_roster") or {}
	if source_speaker_roster.get("status") != "frozen":
		failures.append("source voice prompt manifest does not include a frozen speaker_roster")
	source_expected_speakers = _expected_speakers_from_roster(source_speaker_roster, failures, "source speaker_roster")
	if expected_speakers and source_expected_speakers and source_expected_speakers != expected_speakers:
		failures.append("source speaker_roster speaker list does not match 02a speaker census")
	for speaker in expected_speakers:
		info = source_voice_prompt_manifest_data.get("speaker_voices", {}).get(speaker)
		if not isinstance(info, dict):
			failures.append(f"source voice prompt manifest missing {speaker}")
			continue
		for clip in info.get("selected_clips") or []:
			text_preview = str(clip.get("text_preview") or "")
			noise_reasons = _reference_text_noise_reasons(text_preview)
			if noise_reasons:
				failures.append(
					f"source voice selected clip for {speaker} is noisy: {', '.join(noise_reasons)}"
				)
	voice_prompt_manifest_data = _read_json(paths["voice_prompt_manifest"])
	if voice_prompt_manifest_data.get("status") != "pass":
		failures.append("voice_prompt_manifest status is not pass")
	voice_prompt_schema = str(voice_prompt_manifest_data.get("schema_version") or "")
	is_qwen_chinese_prompt = voice_prompt_schema == "worldview-china-qwen-vibevoice-prompts.v1"
	speaker_voice_names: dict[str, str] = {}
	for speaker in expected_speakers:
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
		local_registered_value = str(info.get("local_registered_wav") or "").strip()
		local_registered = Path(local_registered_value) if local_registered_value else None
		validation_reference = local_registered if is_qwen_chinese_prompt and local_registered and local_registered.exists() else reference
		if not validation_reference.exists():
			failures.append(f"voice reference wav missing for {speaker}: {validation_reference}")
			continue
		if is_qwen_chinese_prompt and local_registered and local_registered.exists() and reference != local_registered and not reference.exists():
			warnings.append(f"global VibeVoice reference missing for {speaker}, validated local_registered_wav instead: {reference}")
		elif not reference.exists():
			failures.append(f"voice reference wav missing for {speaker}: {reference}")
			continue
		if not registered.exists():
			if is_qwen_chinese_prompt and local_registered and local_registered.exists():
				warnings.append(f"global VibeVoice registered reference missing for {speaker}, validated local_registered_wav instead: {registered}")
			else:
				failures.append(f"registered VibeVoice reference missing for {speaker}: {registered}")
		expected_sha = str(info.get("sha256") or "")
		if expected_sha:
			actual_sha = _sha256(validation_reference)
			if actual_sha != expected_sha:
				failures.append(f"voice reference sha256 mismatch for {speaker}: {validation_reference}")
			if registered.exists() and _sha256(registered) != expected_sha:
				if is_qwen_chinese_prompt and local_registered and local_registered.exists():
					warnings.append(
						f"global VibeVoice registered reference sha256 differs for {speaker}; "
						f"validated immutable local_registered_wav instead: {registered}"
					)
				else:
					failures.append(f"registered voice reference sha256 mismatch for {speaker}: {registered}")
		probe = _probe(validation_reference)
		audio_streams = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
		if not audio_streams:
			failures.append(f"voice reference has no audio stream for {speaker}: {validation_reference}")
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
			reference_text = str(info.get("reference_text") or "")
			noise_reasons = _reference_text_noise_reasons(reference_text)
			if noise_reasons:
				failures.append(
					f"Qwen Chinese prompt reference_text for {speaker} is noisy: {', '.join(noise_reasons)}"
				)
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
	translation_semantic_qa = _read_json(paths["translation_semantic_qa"])
	if translation_semantic_qa.get("status") != "PASS":
		failures.append("translation semantic QA status is not PASS")
	if int(translation_semantic_qa.get("summary", {}).get("fail_findings") or 0) != 0:
		failures.append("translation semantic QA still has fail findings")
	if translation_semantic_qa.get("summary", {}).get("qualitative_reading_review_status") != "PASS":
		failures.append("translation semantic QA qualitative reading review status is not PASS")
	translation_semantic_reviewed_files = _resolved_path_set(translation_semantic_qa.get("reviewed_files"))
	for label, path in {
		"faithful_translation_json": paths["faithful_translation_json"],
		"active_translation_json": paths["translation_json"],
	}.items():
		if str(path.resolve()) not in translation_semantic_reviewed_files:
			failures.append(f"translation semantic QA did not cover current {label}: {path}")
	translation_reading_review = _read_json(paths["translation_reading_review"])
	if translation_reading_review.get("status") != "PASS":
		failures.append("translation qualitative reading review status is not PASS")
	if translation_reading_review.get("read_entire_text") is not True:
		failures.append("translation qualitative reading review did not confirm read_entire_text=true")
	for criterion in (
		"natural_chinese_oral_expression",
		"clear_and_easy_to_understand",
		"contextual_coherence",
		"tts_ready_spoken_style",
	):
		if (translation_reading_review.get("criteria") or {}).get(criterion) != "PASS":
			failures.append(f"translation qualitative reading review criterion is not PASS: {criterion}")
	for finding in translation_reading_review.get("findings") or []:
		if isinstance(finding, dict) and finding.get("severity") == "fail":
			failures.append("translation qualitative reading review still has fail findings")
			break
	reading_reviewed_files = _resolved_path_set(translation_reading_review.get("reviewed_files"))
	reading_hashes_raw = translation_reading_review.get("reviewed_file_hashes") if isinstance(translation_reading_review.get("reviewed_file_hashes"), dict) else {}
	reading_hashes: dict[str, str] = {}
	for key, value in reading_hashes_raw.items():
		try:
			reading_hashes[str(Path(str(key)).expanduser().resolve())] = str(value)
		except OSError:
			reading_hashes[str(Path(str(key)).expanduser())] = str(value)
	for label, path in {
		"faithful_translation_json": paths["faithful_translation_json"],
		"active_translation_json": paths["translation_json"],
	}.items():
		resolved = str(path.resolve())
		if resolved not in reading_reviewed_files:
			failures.append(f"translation qualitative reading review did not cover current {label}: {path}")
		elif reading_hashes.get(resolved) != _sha256(path):
			failures.append(f"translation qualitative reading review is stale for current {label}: {path}")
	early_text_compliance = _read_json(paths["early_text_compliance"])
	if early_text_compliance.get("status") != "PASS":
		failures.append("early risk compliance review status is not PASS")
	if int(early_text_compliance.get("summary", {}).get("fail_findings") or 0) != 0:
		failures.append("early risk compliance review still has fail findings")
	early_reviewed_files = _resolved_path_set(early_text_compliance.get("reviewed_files"))
	for label, path in {
		"faithful_translation_json": paths["faithful_translation_json"],
		"active_translation_json": paths["translation_json"],
	}.items():
		if str(path.resolve()) not in early_reviewed_files:
			failures.append(f"early risk compliance review did not cover current {label}: {path}")
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
	if re.search(r"(?m)^Speaker (?:[4-9]|\d{2,})[:：]", _read_text(paths["podcast_script"])):
		failures.append("podcast_script contains unsupported Speaker labels")
	text_compliance = _read_json(paths["text_compliance"])
	if text_compliance.get("status") != "PASS":
		failures.append("Bilibili text compliance review status is not PASS")
	if int(text_compliance.get("summary", {}).get("fail_findings") or 0) != 0:
		failures.append("Bilibili text compliance review still has fail findings")
	reviewed_files = _resolved_path_set(text_compliance.get("reviewed_files"))
	for label, path in {
		"podcast_script": paths["podcast_script"],
		"video_title": paths["video_title"],
		"cover_title": paths["cover_title"],
		"audio_manifest": paths["audio_manifest"],
		"subtitle_manifest": paths["subtitle_manifest"],
		"subtitles_srt": paths["subtitles_srt"],
		"subtitles_ass": paths["subtitles_ass"],
	}.items():
		if str(path.resolve()) not in reviewed_files:
			failures.append(f"Bilibili text compliance review did not cover current {label}: {path}")
	translation_display_text = "\n".join(str(segment.get("zh_text") or "") for segment in translation.get("segments") or [])
	for label, text in {
		"translation zh_text": translation_display_text,
		"podcast_script": _read_text(paths["podcast_script"]),
	}.items():
		forbidden = _forbidden_chinese_leader_names(text)
		if forbidden:
			failures.append(f"{label} contains forbidden Chinese contemporary leader names: {', '.join(forbidden)}")

	audio_manifest = _read_json(paths["audio_manifest"])
	audio_integrity = _read_json(paths["audio_transcript_integrity"])
	if audio_integrity.get("status") != "PASS":
		failures.append("audio transcript integrity QA is not PASS")
	if float(audio_integrity.get("summary", {}).get("matched_script_ratio") or 0) < 0.95:
		failures.append("audio transcript integrity matched_script_ratio is below 0.95")
	if audio_integrity.get("summary", {}).get("repair_target_chunks"):
		failures.append("audio transcript integrity QA still has repair target chunks")
	voice_consistency = _read_json(paths["voice_consistency"])
	if voice_consistency.get("overall_status") != "PASS":
		failures.append("voice consistency QA overall_status is not PASS")
	if voice_consistency.get("lineage", {}).get("status") != "PASS":
		failures.append("voice lineage QA status is not PASS")
	if voice_consistency.get("acoustic", {}).get("status") != "PASS":
		failures.append("voice acoustic consistency QA status is not PASS")
	if voice_consistency.get("expected_voices") and voice_consistency.get("expected_voices") != speaker_voice_names:
		failures.append("voice consistency QA expected_voices does not match voice_prompt_manifest")
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
	if not _is_locked_roster_policy(audio_manifest.get("voice_context_policy")):
		failures.append("audio_manifest voice_context_policy is not locked_multi_speaker_roster")
	if not audio_manifest.get("voice_prompt_manifest"):
		failures.append("audio_manifest missing voice_prompt_manifest")
	if not audio_manifest.get("chunks"):
		failures.append("audio_manifest has no chunks")
	if not audio_manifest.get("turns"):
		failures.append("audio_manifest has no turns")
	expected_locked_speaker_names = [speaker_voice_names.get(speaker) for speaker in expected_speakers]
	chunk_plan = _read_json(paths["chunk_plan"])
	if not _is_locked_roster_policy(chunk_plan.get("voice_context_policy")):
		failures.append("chunk_plan voice_context_policy is not locked_multi_speaker_roster")
	for chunk in chunk_plan.get("chunks") or []:
		if chunk.get("vibevoice_mode") != "dialogue":
			failures.append(f"{chunk.get('chunk_id')} chunk_plan is not dialogue mode under locked roster")
		if list(chunk.get("speaker_names") or []) != expected_locked_speaker_names:
			failures.append(f"{chunk.get('chunk_id')} chunk_plan speaker_names do not match locked roster")
	for chunk in audio_manifest.get("chunks") or []:
		if chunk.get("vibevoice_mode") != "dialogue":
			failures.append(f"{chunk.get('chunk_id')} audio_manifest chunk is not dialogue mode under locked roster")
		if list(chunk.get("speaker_names") or []) != expected_locked_speaker_names:
			failures.append(f"{chunk.get('chunk_id')} audio_manifest speaker_names do not match locked roster")
	if audio_manifest.get("vibevoice_runner") == "resident_batch":
		resident_report_value = audio_manifest.get("resident_batch_report")
		if not resident_report_value:
			failures.append("audio_manifest missing resident_batch_report for resident_batch generation")
		else:
			resident_report_path = _resolve_run_path(run_dir, resident_report_value)
			if not resident_report_path.exists():
				failures.append(f"resident_batch_report is missing: {resident_report_path}")
			else:
				resident_report = _read_json(resident_report_path)
				if int(resident_report.get("job_count") or 0) != len(audio_manifest.get("chunks") or []):
					failures.append("resident_batch_report job_count does not cover every final chunk")
				for job in resident_report.get("jobs") or []:
					if job.get("status") != "pass":
						failures.append(f"resident batch job {job.get('job_id')} status is not pass")
					if job.get("speaker_mode") != "dialogue":
						failures.append(f"resident batch job {job.get('job_id')} is not dialogue mode")
					if list(job.get("speaker_names") or []) != expected_locked_speaker_names:
						failures.append(f"resident batch job {job.get('job_id')} speaker_names do not match locked roster")
	audio_duration = _duration(paths["final_audio"])
	video_duration = _duration(paths["final_video"])
	final_video_probe = _probe(paths["final_video"])
	final_video_streams = [stream for stream in final_video_probe.get("streams", []) if stream.get("codec_type") == "video"]
	final_video_width = int(final_video_streams[0].get("width") or 0) if final_video_streams else 0
	final_video_height = int(final_video_streams[0].get("height") or 0) if final_video_streams else 0
	if not final_video_streams:
		failures.append("final_video.mp4 has no readable video stream")
	elif final_video_height > TARGET_FINAL_VIDEO_HEIGHT:
		failures.append(
			f"final_video.mp4 exceeds podcast 2K target height: "
			f"{final_video_width}x{final_video_height}, target={TARGET_FINAL_VIDEO_WIDTH}x{TARGET_FINAL_VIDEO_HEIGHT}"
		)
	render_manifest = _read_json(paths["render_manifest"])
	visual_mode = str(render_manifest.get("visual_mode") or "")
	if visual_mode.startswith("source_video_revoice"):
		target_duration = float(render_manifest.get("target_duration_sec") or render_manifest.get("source_duration_sec") or 0)
		if abs(video_duration - target_duration) > 0.5:
			failures.append(f"source-video revoice duration mismatch: video={video_duration:.2f} target={target_duration:.2f}")
		subtitle_mode = str(render_manifest.get("subtitle_mode") or "")
		subtitle_delivery_policy = str(render_manifest.get("subtitle_delivery_policy") or "")
		sidecar_exception = subtitle_delivery_policy == "sidecar_user_requested_no_burn_subtitles"
		if subtitle_mode != "burned_ass" and not sidecar_exception:
			failures.append("formal source-video revoice must burn subtitles into final_video.mp4 by default")
		if subtitle_mode == "burned_ass" and "burned_subtitles" not in visual_mode:
			failures.append("burned subtitle render must record burned_subtitles in visual_mode")
		if subtitle_mode == "burned_ass" and not render_manifest.get("burned_subtitle_render"):
			failures.append("burned subtitle render is missing burned_subtitle_render evidence")
		if subtitle_mode == "burned_ass" and render_manifest.get("burned_subtitle_render"):
			subtitle_layout_rule = (render_manifest.get("burned_subtitle_render") or {}).get("subtitle_layout_rule") or {}
			subtitle_shift_px = int(subtitle_layout_rule.get("subtitle_vertical_down_shift_px") or 0)
			subtitle_font_size_px = int(subtitle_layout_rule.get("font_size_px") or 0)
			if subtitle_layout_rule.get("subtitle_vertical_down_shift_unit") != "one_font_height":
				failures.append("burned subtitle render must record subtitle_vertical_down_shift_unit=one_font_height")
			if subtitle_shift_px != subtitle_font_size_px or subtitle_shift_px <= 0:
				failures.append("burned subtitle render vertical down shift must equal the current subtitle font size")
		if subtitle_mode == "burned_ass" and (
			final_video_width != TARGET_FINAL_VIDEO_WIDTH or final_video_height != TARGET_FINAL_VIDEO_HEIGHT
		):
			failures.append(
				f"burned-subtitle formal video must be 2K/1440p "
				f"{TARGET_FINAL_VIDEO_WIDTH}x{TARGET_FINAL_VIDEO_HEIGHT}, got {final_video_width}x{final_video_height}"
			)
		if subtitle_mode == "burned_ass" and int(render_manifest.get("target_video_height") or 0) != TARGET_FINAL_VIDEO_HEIGHT:
			failures.append("render_manifest target_video_height does not record 1440p 2K output")
		if visual_mode == "source_video_revoice_strict" and subtitle_mode != "sidecar_not_burned":
			failures.append("strict source-video revoice must keep subtitles sidecar-only, not burned into frames")
		if series_episode and render_manifest.get("series_episode") is not True:
			failures.append("series episode render_manifest does not record series_episode=true")
		if series_episode and "episode_segment" not in visual_mode:
			failures.append("series episode render visual_mode must be an episode segment render")
		if series_episode and episode_manifest.get("source_episode_video_status") == "pass":
			source_episode_video = Path(str(episode_manifest.get("source_episode_video") or ""))
			if not source_episode_video.exists():
				failures.append(f"series episode source_episode_video is missing: {source_episode_video}")
			if render_manifest.get("source_episode_video_used") is not True:
				failures.append("series episode render did not use the pre-cut source_episode_video")
		if "turn_retimed_basic" in visual_mode or render_manifest.get("visual_sync_mode") == "turn_retimed_basic_v1":
			turn_retime = render_manifest.get("turn_retime") or {}
			if turn_retime.get("visual_sync_mode") != "turn_retimed_basic_v1":
				failures.append("turn-retimed render missing turn_retime.visual_sync_mode=turn_retimed_basic_v1")
			for label in ("visual_activity", "retime_edit_plan", "retimed_video"):
				value = turn_retime.get(label)
				if not value:
					failures.append(f"turn-retimed render missing {label}")
					continue
				if not _resolve_run_path(run_dir, value).exists():
					failures.append(f"turn-retimed render {label} path is missing: {value}")
			retime_plan_value = turn_retime.get("retime_edit_plan")
			if retime_plan_value:
				retime_plan_path = _resolve_run_path(run_dir, retime_plan_value)
				if retime_plan_path.exists():
					retime_plan = _read_json(retime_plan_path)
					summary = retime_plan.get("summary") or {}
					if retime_plan.get("status") != "pass":
						failures.append("turn-retimed edit plan status is not pass")
					if int(summary.get("protected_range_violation_count") or 0) != 0:
						failures.append("turn-retimed edit plan cuts through protected scene ranges")
					if float(summary.get("min_kept_segment_duration_sec") or 0) < 1.2:
						failures.append("turn-retimed edit plan has kept video segments shorter than 1.2s")
					if abs(float(summary.get("duration_delta_vs_target_sec") or 0)) > 0.75:
						failures.append("turn-retimed edit plan duration is not within 0.75s of target audio timeline")
					if float(summary.get("cuts_per_minute") or 0) > 10.0:
						failures.append("turn-retimed edit plan cut density exceeds 10 cuts/minute")
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
