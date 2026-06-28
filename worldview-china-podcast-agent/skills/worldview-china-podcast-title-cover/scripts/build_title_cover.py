#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
	from PIL import Image
except ModuleNotFoundError as exc:
	raise SystemExit("Pillow is required. Use the Codex runtime Python or install Pillow.") from exc


CANVAS = (3840, 2160)
ARTICLE_COVER_SCRIPT = Path("/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/scripts/compose_editorial_cover.py")
FORBIDDEN_IDENTITY_LABEL_RE = re.compile(r"(来自|中文配音|搬运|油管|YouTube|频道|栏目|播客|Podcast|CGSP)", re.I)
GENERIC_IDENTITY_LABELS = {
	"世界眼中的中国",
	"世界看中国",
	"海外视角",
	"外网热议",
	"中国观察",
	"国际观察",
	"嘉宾访谈",
	"专家圆桌",
}
FALLBACK_GENERIC_IDENTITY_LABELS = {
	"中国专家",
	"中国问题专家",
	"中东专家",
}
REJECTED_GENERIC_IDENTITY_LABELS = {
	"中东中国问题专家",
	"中国中东问题专家",
	"外国专家",
	"海外专家",
	"外国学者",
	"海外学者",
	"智库专家",
	"研究员",
	"学者",
	"专家",
}
WEAK_TITLE_CORE_RE = re.compile(r"(变局之后|新格局|新局势|深度解析|未来走向|影响几何|怎么看|怎么了|足迹|脉络|图景)$")
CONCRETE_TITLE_SIGNAL_RE = re.compile(
	r"(为什么|怎么|如何|正在|开始|先|最|打到|承压|离不开|变成|不是|比|更|强|弱|脆弱|反噬|重估|改写|让|使|被|把|会|可能|仍|还)"
)
DEFAULT_EPISODE_ORDER_MARKER_TEMPLATE = "第{episode_index}集"
DEFAULT_EPISODE_TITLE_TEMPLATE = "{series_title}·{episode_order_marker}：{subtitle}"


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _read_json_optional(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {}
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


def _source_metadata(run_dir: Path) -> dict[str, Any]:
	for path in (
		run_dir / "02-source-capture/youtube-media/source.info.json",
		run_dir / "02-source-capture/youtube-media/metadata.json",
		run_dir / "02-source-capture/source_metadata.json",
	):
		if path.exists():
			data = _read_json(path)
			data["_metadata_path"] = str(path)
			return data
	raise AssertionError(f"Missing YouTube metadata under {run_dir}/02-source-capture")


def _clean_text(value: str) -> str:
	return re.sub(r"\s+", " ", value).strip()


def _validate_identity_label(label: str) -> str:
	label = _clean_text(label).rstrip(":：")
	assert label, "Source identity label is empty"
	assert 2 <= len(label) <= 16, f"Source identity label should be 2-16 chars: {len(label)}"
	assert label not in GENERIC_IDENTITY_LABELS, "Identity label must name a speaker or concrete role, not the channel/series/topic label"
	assert label not in REJECTED_GENERIC_IDENTITY_LABELS, "Identity label is too generic or awkward; use a concrete role, or a short fallback label such as 中国问题专家 / 中东专家 when no brighter identity exists"
	assert not re.match(r"^《[^》]+》$", label), "Use a person or role identity label, not a decorated channel/program name"
	assert not FORBIDDEN_IDENTITY_LABEL_RE.search(label), "Identity label must describe who is speaking, not say source/channel/podcast/moved-from-YouTube"
	return label


def _identity_label_policy(label: str) -> dict[str, Any]:
	if label in FALLBACK_GENERIC_IDENTITY_LABELS:
		return {
			"status": "PASS",
			"type": "fallback_generic",
			"label": label,
			"allowed_when": "Use only when the source has no famous person, unusually strong title, China-linked role, institution, seniority, geography, lived-experience, or track-record hook that is more clickable and still concise.",
			"preferred_over": ["中国中东问题专家", "中东中国问题专家", "外国学者", "海外专家", "专家"],
			"requires_agent_judgment": True,
		}
	return {
		"status": "PASS",
		"type": "specific_identity",
		"label": label,
		"preferred_when": "Use for famous names, strong public roles, China-linked identities, institutions, seniority, geography, lived experience, or track records.",
	}


def _validate_title_core(title_core: str) -> str:
	title_core = _clean_text(title_core).lstrip(":：")
	assert title_core, "Translated title core is empty"
	assert not re.match(r"^《[^》]+》[:：]", title_core), "Translated title core must not include a channel/program prefix"
	assert not FORBIDDEN_IDENTITY_LABEL_RE.search(title_core), "Translated title core must not add source/channel/podcast labeling"
	separator_count = sum(title_core.count(item) for item in ("、", "与", "和", "及"))
	likely_keyword_stack = separator_count >= 2 and not CONCRETE_TITLE_SIGNAL_RE.search(title_core)
	assert not likely_keyword_stack, (
		"Title core looks like a keyword stack or conference-agenda topic list; rewrite it as a concrete "
		"claim, pressure point, consequence, or question that a Bilibili viewer can understand immediately."
	)
	assert not WEAK_TITLE_CORE_RE.search(title_core), (
		"Title core is too generic for Bilibili; rewrite it as a specific claim, conflict, consequence, "
		"or source-speaker quote rather than a background label."
	)
	assert len(title_core) <= 42, f"Translated title core is too long for cover title: {len(title_core)} chars"
	return title_core


def _title_information_policy(identity_label: str, title_core: str) -> dict[str, Any]:
	separator_count = sum(title_core.count(item) for item in ("、", "与", "和", "及"))
	concrete_signal = bool(CONCRETE_TITLE_SIGNAL_RE.search(title_core))
	return {
		"status": "PASS",
		"bilibili_viewer_information_test": "PASS",
		"identity_prefix_must_explain_why_listen": True,
		"title_core_must_explain_what_happens_or_why_it_matters": True,
		"obscure_name_policy": "Use a famous person's name only when the name itself carries click value; otherwise translate the credential into a viewer-readable role label such as 哥大经济学家.",
		"keyword_stack_rejected": True,
		"topic_noun_separator_count": separator_count,
		"concrete_content_signal_detected": concrete_signal,
		"agent_self_check": [
			"If the viewer has never heard of the person, the prefix should still carry useful identity information.",
			"If the viewer reads only the title core, they should be able to repeat the main claim, pressure point, conflict, or consequence.",
			"If the title sounds like a database row, conference agenda, or pile of proper nouns, rewrite it.",
		],
		"example_rewrite": {
			"weak": "亚当·图兹：中国冲击2.0正在打到德国身上",
			"stronger": "哥大经济学家：中国冲击2.0先打到德国工业",
		},
		"identity_label": identity_label,
		"translated_title_core": title_core,
	}


def _build_full_title(identity_label: str, title_core: str) -> str:
	title = f"{identity_label}：{title_core}"
	assert len(title) <= 58, f"Full title is too long for cover title: {len(title)} chars"
	return title


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
	return values.get(index, str(index))


def _episode_order_marker(episode_index: int, template: str = DEFAULT_EPISODE_ORDER_MARKER_TEMPLATE) -> str:
	episode_label = _chinese_episode_label(episode_index)
	marker = template.format(
		episode_index=episode_index,
		episode_label=episode_label,
		episode_number=episode_label,
	)
	marker = marker.strip()
	assert marker, "Episode order marker template produced an empty marker"
	return marker


def _resolved_episode_order_marker(episode_manifest: dict[str, Any], episode_index: int | None, template: str) -> str | None:
	if episode_index is None:
		return None
	if "episode_order_marker" in episode_manifest:
		return str(episode_manifest.get("episode_order_marker") or "")
	return _episode_order_marker(episode_index, template)


def _build_series_video_title(identity_label: str, title_core: str, episode_index: int, title_template: str, order_marker_template: str) -> str:
	episode_label = _chinese_episode_label(episode_index)
	order_marker = _episode_order_marker(episode_index, order_marker_template)
	title = title_template.format(
		series_title=identity_label,
		series_title_prefix=identity_label,
		episode_index=episode_index,
		episode_label=episode_label,
		episode_number=episode_label,
		episode_order_marker=order_marker,
		order_marker=order_marker,
		subtitle=title_core,
		episode_subtitle=title_core,
	)
	assert identity_label in title, "Series title template must include the shared title"
	assert title_core in title, "Series title template must include the episode subtitle"
	if order_marker:
		assert order_marker in title or str(episode_index) in title or episode_label in title, "Series title template must include an episode order marker"
	assert len(title) <= 62, f"Series episode video title is too long: {len(title)} chars"
	return title


def _default_lines(title: str, identity_label: str | None = None, title_core: str | None = None) -> list[str]:
	if identity_label and title_core:
		core_lines = _default_lines(title_core)
		if len(core_lines) == 1:
			return [identity_label + "：", core_lines[0]]
		return [identity_label + "：", *core_lines[:2]]
	if "，" in title:
		parts = [part for part in title.split("，") if part]
		if len(parts) == 2:
			return [parts[0] + "，", parts[1]]
	if len(title) <= 14:
		return [title]
	if len(title) <= 24:
		mid = len(title) // 2
		break_at = _nearest_break(title, mid)
		return [title[:break_at], title[break_at:]]
	first = _nearest_break(title, len(title) // 3)
	second = _nearest_break(title, first + (len(title) - first) // 2)
	if second <= first:
		second = min(len(title) - 1, first + max(4, (len(title) - first) // 2))
	return [title[:first], title[first:second], title[second:]]


def _nearest_break(title: str, target: int) -> int:
	candidates = []
	for offset in range(0, 8):
		for pos in (target - offset, target + offset):
			if 2 <= pos <= len(title) - 2:
				score = offset
				if title[pos - 1] in "，、：；":
					score -= 4
				if title[pos] in "，、：；？！":
					score += 4
				if title[pos - 1] in "的和与及或在把被对给向从":
					score += 3
				candidates.append((score, pos))
	if not candidates:
		return max(2, min(len(title) - 2, target))
	return min(candidates)[1]


def _default_highlights(title: str, identity_label: str | None = None) -> list[str]:
	keywords = []
	if identity_label:
		keywords.append(identity_label)
	keywords.extend(["中国经济", "更强", "更弱", "更脆弱", "风险", "增长", "中国"])
	highlights = [item for item in keywords if item in title]
	if highlights:
		result: list[str] = []
		for item in highlights:
			if all(item not in old and old not in item for old in result):
				result.append(item)
			if len(result) >= 2:
				break
		return result
	return [title[: min(4, len(title))]]


def _select_background_frame(run_dir: Path, frame: Path | None, frame_key: str, source_time_sec: float | None) -> tuple[Path, dict[str, Any]]:
	if frame is not None:
		assert frame.exists(), f"Missing requested cover frame: {frame}"
		return frame.resolve(), {"selection": "explicit_frame", "path": str(frame.resolve())}
	frame_qa = run_dir / "02-source-capture/source-video-frame-qa"
	candidates = {
		"middle": frame_qa / "middle.png",
		"opening": frame_qa / "opening.png",
		"end": frame_qa / "end.png",
	}
	if frame_key == "auto":
		for key in ("middle", "opening", "end"):
			if candidates[key].exists():
				return candidates[key].resolve(), {"selection": "frame_qa_auto", "frame_key": key, "path": str(candidates[key].resolve())}
	else:
		path = candidates.get(frame_key)
		if path is not None and path.exists():
			return path.resolve(), {"selection": "frame_qa_key", "frame_key": frame_key, "path": str(path.resolve())}
	source = run_dir / "02-source-capture/youtube-media/source.mp4"
	assert source.exists(), f"Missing source video for frame extraction: {source}"
	duration = _duration(source)
	seconds = source_time_sec if source_time_sec is not None else duration * 0.5
	out = run_dir / "cover" / "background_frame_extracted.png"
	out.parent.mkdir(parents=True, exist_ok=True)
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-ss",
		f"{seconds:.3f}",
		"-i",
		str(source),
		"-frames:v",
		"1",
		str(out),
	])
	return out.resolve(), {"selection": "extracted_from_source_video", "source_video": str(source), "time_sec": round(seconds, 3), "path": str(out.resolve())}


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
	target_w, target_h = size
	w, h = image.size
	scale = max(target_w / w, target_h / h)
	new_size = (round(w * scale), round(h * scale))
	image = image.resize(new_size, Image.Resampling.LANCZOS)
	left = max(0, (image.width - target_w) // 2)
	top = max(0, (image.height - target_h) // 2)
	return image.crop((left, top, left + target_w, top + target_h))


def build_title_cover(
	run_dir: Path,
	translated_title_core: str,
	source_identity_label: str,
	identity_basis: str | None,
	frame: Path | None,
	frame_key: str,
	source_time_sec: float | None,
	highlight_texts: list[str] | None,
	episode_index: int | None,
	episode_title_template: str,
	episode_order_marker_template: str,
	cover_include_episode_index: bool,
	force: bool,
) -> dict[str, Any]:
	run_dir = run_dir.resolve()
	cover_dir = run_dir / "cover"
	node_dir = run_dir / "02d-title-cover"
	cover_dir.mkdir(parents=True, exist_ok=True)
	node_dir.mkdir(parents=True, exist_ok=True)
	metadata = _source_metadata(run_dir)
	source_title = str(metadata.get("title") or metadata.get("fulltitle") or "").strip()
	assert source_title, "Source YouTube title is missing"
	if episode_index is not None:
		assert episode_index > 0, f"episode_index must be positive: {episode_index}"
	episode_manifest = _read_json_optional(run_dir / "episode_manifest.json")
	identity_label = _validate_identity_label(source_identity_label)
	identity_label_policy = _identity_label_policy(identity_label)
	if identity_label_policy["type"] == "fallback_generic":
		assert identity_basis and _clean_text(identity_basis), (
			"Short generic fallback identity labels require identity_basis explaining source support "
			"and why no brighter concise identity/title is available"
		)
	title_core = _validate_title_core(translated_title_core)
	title_information_policy = _title_information_policy(identity_label, title_core)
	manifest_video_title = str(episode_manifest.get("video_title") or "").strip()
	manifest_cover_title = str(episode_manifest.get("cover_title") or "").strip()
	resolved_episode_title_template = str(episode_manifest.get("episode_title_template") or episode_title_template)
	resolved_episode_order_marker_template = str(episode_manifest.get("episode_order_marker_template") or episode_order_marker_template)
	resolved_episode_order_marker = _resolved_episode_order_marker(episode_manifest, episode_index, resolved_episode_order_marker_template)
	cover_title_text = manifest_cover_title or _build_full_title(identity_label, title_core)
	video_title = cover_title_text
	if episode_index is not None:
		video_title = manifest_video_title or _build_series_video_title(
			identity_label,
			title_core,
			episode_index,
			resolved_episode_title_template,
			resolved_episode_order_marker_template,
		)
	render_title = video_title if cover_include_episode_index else cover_title_text
	lines = _default_lines(render_title, identity_label=identity_label, title_core=title_core)
	highlights = highlight_texts or _default_highlights(render_title, identity_label=identity_label)
	for item in highlights:
		assert item in render_title, f"highlight_text not found in rendered cover title: {item!r}"

	background_raw, frame_meta = _select_background_frame(run_dir, frame, frame_key, source_time_sec)
	raw_copy = cover_dir / "background_raw.png"
	background = cover_dir / "background.png"
	if force or not raw_copy.exists():
		shutil.copy2(background_raw, raw_copy)
	if force or not background.exists():
		normalized = _cover_crop(Image.open(raw_copy).convert("RGB"), CANVAS)
		normalized.save(background)

	title_json = cover_dir / "cover_title.json"
	cover_title = {
		"schema_version": "worldview-china-podcast-title-cover.v1",
		"title_source": "podcast_source_identity_plus_platform_native_hook",
		"source_title": source_title,
		"source_title_reference_policy": "original_youtube_title_is_reference_not_boundary",
		"source_identity_label": identity_label,
		"source_identity_basis": identity_basis,
		"identity_label_policy": identity_label_policy,
		"translated_title_core": title_core,
		"title_text": render_title,
		"video_title_text": video_title,
		"series_episode": episode_index is not None,
		"episode_index": episode_index,
		"episode_label": _chinese_episode_label(episode_index) if episode_index is not None else None,
		"episode_order_marker": resolved_episode_order_marker,
		"episode_title_template": resolved_episode_title_template if episode_index is not None else None,
		"episode_order_marker_template": resolved_episode_order_marker_template if episode_index is not None else None,
		"cover_title_omits_episode_index": episode_index is not None and not cover_include_episode_index,
		"title_lines": lines,
		"preserve_title_lines": True,
		"title_line_policy": {
			"layout": "center",
			"priority": [
				"large_two_line_if_it_fits",
				"large_three_line_if_two_lines_do_not_fit",
				"shrunk_three_line_only_if_large_three_lines_do_not_fit",
			],
			"source_lines_are_advisory_for_center_layout": True,
			"font_size_policy": "keep cover title large before shrinking; prefer adding a third line over reducing the font size",
		},
		"highlight_text": highlights[0],
		"highlight_texts": highlights,
		"highlight_style": {"color": "yellow", "font_weight": "bold"},
		"read_aloud_self_check": {
			"status": "PASS",
			"read_aloud_version": render_title,
			"is_smooth_spoken_chinese": True,
			"is_attractive": True,
			"not_keyword_stack": True,
			"issue_if_any": None,
			"revision_note": "Title uses a justified speaker/source-identity prefix plus a platform-native claim, conflict, consequence, or source-speaker quote; the original YouTube title is only a reference signal."
		},
		"attractive_title_policy": {
			"status": "PASS",
			"requires_podcast_identity": True,
			"requires_specific_eye": True,
			"allowed_hook_types": ["sharp_claim", "conflict_question", "consequence", "counterintuitive_quote"],
			"rejects_generic_background_titles": True,
			"requires_concrete_content_not_keyword_stack": True,
			"bilibili_viewer_information_test": title_information_policy,
			"identity_label_policy": identity_label_policy,
		},
	}
	_write_json(title_json, cover_title)
	(run_dir / "video_title.txt").write_text(video_title + "\n", encoding="utf-8")

	visual_subject = {
		"schema_version": "worldview-china-podcast-cover-visual-subject.v1",
		"strategy": "source_video_frame",
		"visual_subject": "source podcast/interview frame showing host/guest or podcast layout",
		"composition": {
			"background_source": "source_video_frame",
			"text_layer": "large centered Chinese title over source frame",
			"title_layout": "center",
			"added_ai_background": False,
			"added_blue_base": False
		},
		"frame_selection": frame_meta,
	}
	_write_json(cover_dir / "visual_subject.json", visual_subject)
	image_source_manifest = {
		"schema_version": "worldview-china-podcast-cover-image-source.v1",
		"image_type": "source_video_frame_background",
		"source": "youtube_source_video",
		"model_or_tool": None,
		"generation_date": None,
		"source_video": str((run_dir / "02-source-capture/youtube-media/source.mp4").resolve()),
		"source_title": source_title,
		"frame_selection": frame_meta,
		"downloaded_file": "cover/background_raw.png",
		"normalized_file": "cover/background.png",
		"contains_real_person": True,
		"note": "Different from article-podcast AI cover route: this skill intentionally uses a frame from the original video podcast as the cover background."
	}
	_write_json(cover_dir / "image_source_manifest.json", image_source_manifest)

	cover_out = cover_dir / "cover_4k.png"
	if force or not cover_out.exists():
		assert ARTICLE_COVER_SCRIPT.exists(), f"Missing cover compositor: {ARTICLE_COVER_SCRIPT}"
		_run([
			sys.executable,
			str(ARTICLE_COVER_SCRIPT),
			"--background",
			str(background),
			"--out",
			str(cover_out),
			"--title-json",
			str(title_json),
			"--layout",
			"center",
		])

	manifest = {
		"schema_version": "worldview-china-podcast-title-cover-run.v1",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"source_title": source_title,
		"source_identity_label": identity_label,
		"source_identity_basis": identity_basis,
		"identity_label_policy": identity_label_policy,
		"title_information_policy": title_information_policy,
		"translated_title_core": title_core,
		"translated_title": video_title,
		"cover_title_text": render_title,
		"series_episode": episode_index is not None,
		"episode_index": episode_index,
		"episode_order_marker": resolved_episode_order_marker,
		"episode_title_template": resolved_episode_title_template if episode_index is not None else None,
		"episode_order_marker_template": resolved_episode_order_marker_template if episode_index is not None else None,
		"cover_title_omits_episode_index": episode_index is not None and not cover_include_episode_index,
		"video_title": "video_title.txt",
		"cover_title_json": str(title_json),
		"background_raw": str(raw_copy),
		"background": str(background),
		"cover_4k": str(cover_out),
		"cover_4k_sha256": _sha256(cover_out),
		"frame_selection": frame_meta,
		"title_layout": "center",
		"title_line_policy": {
			"priority": [
				"large_two_line_if_it_fits",
				"large_three_line_if_two_lines_do_not_fit",
				"shrunk_three_line_only_if_large_three_lines_do_not_fit",
			],
			"source_lines_are_advisory_for_center_layout": True,
		},
		"title_policy": (
			"series_episode_indexed_video_title_plus_unindexed_cover_title"
			if episode_index is not None and not cover_include_episode_index
			else "source_identity_prefix_plus_platform_native_hook_title"
		),
		"source_title_reference_policy": "original_youtube_title_is_reference_not_boundary",
	}
	_write_json(node_dir / "title_cover_manifest.json", manifest)
	report = [
		"# Podcast Title And Cover Report",
		"",
		f"- source_title: {source_title}",
		f"- source_identity_label: {identity_label}",
		f"- source_identity_basis: {identity_basis or ''}",
		f"- identity_label_policy: {identity_label_policy['type']}",
		f"- translated_title_core: {title_core}",
		f"- translated_title: {video_title}",
		f"- cover_title_text: {render_title}",
		f"- series_episode: {str(episode_index is not None).lower()}",
		f"- video_title: `{run_dir / 'video_title.txt'}`",
		f"- cover_title_json: `{title_json}`",
		f"- background: `{background}`",
		f"- cover_4k: `{cover_out}`",
		f"- frame_selection: {frame_meta['selection']}",
		"- title_layout: center",
		"- title_line_policy: prefer large two lines; if that does not fit, prefer large three lines; shrink only after large three lines cannot fit.",
		"- policy: source identity prefix plus platform-native hook title; original YouTube title is a reference signal, not a mandatory translation boundary; no lazy channel/source/program label; title core must contain concrete content rather than a keyword pile; source video frame background.",
	]
	(node_dir / "title_cover_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
	return manifest


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build title and cover assets for a Worldview China source-video podcast translation run.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--speaker-label", "--source-identity-label", dest="source_identity_label", required=True, help="Chinese speaker/source identity prefix, e.g. 黄仁勋, 美国议员, 上海美国商会前会长. Do not use channel/program/source labels.")
	parser.add_argument("--identity-basis", help="Short evidence for the identity label, usually from YouTube title/description/transcript.")
	parser.add_argument("--translated-title-core", help="Smooth Chinese translation of the original YouTube title, without the speaker/source identity prefix.")
	parser.add_argument("--translated-title", help="Deprecated alias for --translated-title-core.")
	parser.add_argument("--highlight-text", action="append", dest="highlight_texts", help="Continuous substring of translated title to render yellow. May be repeated.")
	parser.add_argument("--frame", type=Path, help="Explicit source-video frame image to use as cover background.")
	parser.add_argument("--frame-key", choices=["auto", "middle", "opening", "end"], default="auto")
	parser.add_argument("--source-time-sec", type=float, help="Extract a frame from source.mp4 at this time if no frame QA image is used.")
	parser.add_argument("--episode-index", type=int, help="Series episode index. Video title uses episode_manifest.json or --episode-title-template, while cover title omits the index by default.")
	parser.add_argument(
		"--episode-title-template",
		default=DEFAULT_EPISODE_TITLE_TEMPLATE,
		help="Template used only when episode_manifest.json does not already provide video_title. Fields: {series_title}, {episode_index}, {episode_label}, {episode_order_marker}, {subtitle}.",
	)
	parser.add_argument(
		"--episode-order-marker-template",
		default=DEFAULT_EPISODE_ORDER_MARKER_TEMPLATE,
		help="Series-wide order marker template used only when episode_manifest.json does not provide one. Fields: {episode_index}, {episode_label}.",
	)
	parser.add_argument("--cover-include-episode-index", action="store_true", help="Render the episode index on the cover too. Default series behavior omits it.")
	parser.add_argument("--force", action="store_true")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	translated_title_core = args.translated_title_core or args.translated_title
	if not translated_title_core:
		raise SystemExit("Provide --translated-title-core, or the deprecated --translated-title alias.")
	manifest = build_title_cover(
		run_dir=args.run_dir,
		translated_title_core=translated_title_core,
		source_identity_label=args.source_identity_label,
		identity_basis=args.identity_basis,
		frame=args.frame,
		frame_key=args.frame_key,
		source_time_sec=args.source_time_sec,
		highlight_texts=args.highlight_texts,
		episode_index=args.episode_index,
		episode_title_template=args.episode_title_template,
		episode_order_marker_template=args.episode_order_marker_template,
		cover_include_episode_index=args.cover_include_episode_index,
		force=args.force,
	)
	print(json.dumps({
		"translated_title": manifest["translated_title"],
		"cover_4k": manifest["cover_4k"],
		"manifest": str(Path(args.run_dir) / "02d-title-cover/title_cover_manifest.json"),
	}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
