#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SUBTITLE_BLOCK_TOP_MIN_Y = 1904
SUBTITLE_BLOCK_TOP_MAX_Y = 1974
SUBTITLE_BLOCK_BOTTOM_MAX_Y = 2044
EXPECTED_PLAYBACK_SPEED = 1.0
EXPECTED_FINAL_TIMELINE = f"{EXPECTED_PLAYBACK_SPEED:g}x"
EXPECTED_SUBTITLE_LETTER_SPACING_PX = 6
MIN_SUBTITLE_LETTER_SPACING_PX = 4
MAX_SUBTITLE_LETTER_SPACING_PX = 8
EXPECTED_SUBTITLE_OUTLINE = "subtle_translucent_outline"
EXPECTED_SUBTITLE_OUTLINE_WIDTH_PX = 3
MIN_SUBTITLE_GLYPH_EDGE_PAD_PX = 48
MIN_SUBTITLE_SHEAR_EDGE_PAD_PX = 16
EXPECTED_VISUAL_TRANSITION_EFFECT = "wipe_with_shadow"
MIN_AUDIO_VIDEO_CORRELATION = 0.995
MAX_AUDIO_VIDEO_RMS_DIFF_OVER_SOURCE = 0.05
MAX_SUBTITLE_OVERLAP_SEC = 0.30
FORBIDDEN_COVER_PROVENANCE_TOKENS = {
	"local_pillow_generated",
	"procedural_generated",
	"programmatic_generated",
	"manual_composite",
	"screenshot",
	"ppt_export",
	"map_diagram",
	"chart_generated",
}
AI_COVER_PROVENANCE_TOKENS = {
	"ai_generated",
	"ai-generated",
	"ai image",
	"imagegen",
	"image generation",
	"gpt-image",
	"dall-e",
	"dalle",
	"midjourney",
	"stable diffusion",
	"flux",
	"imagen",
	"recraft",
	"ideogram",
}
REQUIRED_VISUAL_SUBJECT_FIELDS = {"strategy", "style", "image_prompt", "negative_prompt"}
TITLE_PREFIX_RE = re.compile(r"^《([^》]{1,40})》：")
PUBLICATION_CHINESE_NAMES = {
	"the economist": "经济学人",
	"economist": "经济学人",
	"financial times": "金融时报",
	"ft": "金融时报",
	"the new york times": "纽约时报",
	"new york times": "纽约时报",
	"nytimes": "纽约时报",
	"the new yorker": "纽约客",
	"new yorker": "纽约客",
	"the atlantic": "大西洋月刊",
	"atlantic": "大西洋月刊",
	"the wall street journal": "华尔街日报",
	"wall street journal": "华尔街日报",
	"wsj": "华尔街日报",
	"wired": "连线",
	"bloomberg": "彭博社",
	"bloomberg news": "彭博社",
	"bloomberg businessweek": "彭博商业周刊",
	"the guardian": "卫报",
	"guardian": "卫报",
	"foreign policy": "外交政策",
	"foreign affairs": "外交事务",
	"the washington post": "华盛顿邮报",
	"washington post": "华盛顿邮报",
	"reuters": "路透社",
	"associated press": "美联社",
	"ap": "美联社",
	"bbc": "英国广播公司",
	"bbc news": "英国广播公司",
	"cnn": "美国有线电视新闻网",
	"nikkei asia": "日经亚洲",
	"the wire china": "连线中国",
	"rest of world": "世界其余地区",
	"the diplomat": "外交学者",
	"china leadership monitor": "中国领导层观察",
	"time": "时代",
}
SOURCE_FRAME_MARKERS = (
	"来源文章",
	"外媒",
	"外刊",
	"原文",
	"这篇文章",
	"报道指出",
	"报道说",
	"文章认为",
	"作者写道",
	"据外媒",
	"据外刊",
)


@dataclass(frozen=True)
class CheckResult:
	status: str
	message: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _read_text(path: Path) -> str:
	return path.read_text(encoding="utf-8", errors="replace")


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _pick_first(paths: list[Path], patterns: tuple[str, ...]) -> Path | None:
	if not paths:
		return None
	def score(path: Path) -> tuple[int, int, str]:
		name = path.name.lower()
		return (sum(1 for pattern in patterns if pattern in name), path.stat().st_size, str(path))
	return sorted(paths, key=score, reverse=True)[0]


def _find_text(project_dir: Path, explicit: str | None, patterns: tuple[str, ...]) -> Path | None:
	if explicit:
		path = Path(explicit).expanduser().resolve()
		return path if path.exists() else None
	if any(pattern in {"single_host_script", "podcast_script", "chinese_podcast", "口播", "播客", "文稿"} for pattern in patterns):
		for canonical in ("single_host_script.md", "podcast_script.md"):
			path = project_dir / canonical
			if path.exists():
				return path
	candidates = [p for p in project_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt"}]
	return _pick_first(candidates, patterns)


def _find_image(project_dir: Path, explicit: str | None) -> Path | None:
	if explicit:
		path = Path(explicit).expanduser().resolve()
		return path if path.exists() else None
	candidates = [p for p in project_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
	preferred = [p for p in candidates if "cover" in p.name.lower() or "封面" in p.name]
	return _pick_first(preferred or candidates, ("cover", "4k", "封面"))


def _find_video(project_dir: Path, explicit: str | None) -> Path | None:
	if explicit:
		path = Path(explicit).expanduser().resolve()
		return path if path.exists() else None
	canonical = project_dir / "video" / "final_video.mp4"
	if canonical.exists():
		return canonical
	candidates = [p for p in project_dir.rglob("*.mp4") if p.is_file()]
	return _pick_first(candidates, ("final_video", "final", "video"))


def _find_subtitle(project_dir: Path, explicit: str | None, suffix: str) -> Path | None:
	if explicit:
		path = Path(explicit).expanduser().resolve()
		return path if path.exists() else None
	canonical = project_dir / "video" / f"final_subtitles{suffix}"
	if canonical.exists():
		return canonical
	candidates = [p for p in project_dir.rglob(f"*{suffix}") if p.is_file()]
	return _pick_first(candidates, ("final_subtitles", "subtitle", "字幕"))


def _load_json(path: Path) -> dict[str, Any]:
	if not path.exists():
		return {}
	return json.loads(_read_text(path))


def _manifest_path(project_dir: Path, value: Any) -> Path | None:
	if not value:
		return None
	path = Path(str(value)).expanduser()
	if not path.is_absolute():
		path = project_dir / path
	return path


def _ffprobe(path: Path) -> dict[str, Any]:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration:stream=index,codec_type,codec_name,width,height",
		"-of",
		"json",
		str(path),
	])
	return json.loads(result.stdout)


def _image_size(path: Path) -> tuple[int, int] | None:
	try:
		from PIL import Image
		with Image.open(path) as img:
			return img.size
	except Exception:
		pass
	try:
		info = _ffprobe(path)
		stream, _ = _video_streams(info)
		if stream and stream.get("width") and stream.get("height"):
			return int(stream["width"]), int(stream["height"])
	except Exception:
		pass
	try:
		width_result = _run(["sips", "-g", "pixelWidth", str(path)])
		height_result = _run(["sips", "-g", "pixelHeight", str(path)])
		width_match = re.search(r"pixelWidth:\s*(\d+)", width_result.stdout)
		height_match = re.search(r"pixelHeight:\s*(\d+)", height_result.stdout)
		if width_match and height_match:
			return int(width_match.group(1)), int(height_match.group(1))
	except Exception:
		pass
	return None


def _manifest_strings(value: Any) -> list[str]:
	if isinstance(value, dict):
		strings: list[str] = []
		for key, item in value.items():
			strings.append(str(key))
			strings.extend(_manifest_strings(item))
		return strings
	if isinstance(value, list):
		strings = []
		for item in value:
			strings.extend(_manifest_strings(item))
		return strings
	if value is None:
		return []
	return [str(value)]


def _check_cover_background_provenance(project_dir: Path) -> list[CheckResult]:
	results: list[CheckResult] = []
	cover_dir = project_dir / "cover"
	raw_background = cover_dir / "background_raw.png"
	background = cover_dir / "background.png"
	manifest_path = cover_dir / "image_source_manifest.json"
	visual_subject_path = cover_dir / "visual_subject.json"

	if not raw_background.exists():
		results.append(CheckResult("FAIL", "缺少 cover/background_raw.png，无法验证 AI 底图来源"))
	if not background.exists():
		results.append(CheckResult("FAIL", "缺少 cover/background.png，无法验证封面底图"))
	if not manifest_path.exists():
		results.append(CheckResult("FAIL", "缺少 cover/image_source_manifest.json，无法证明封面底图来自 AI 图像生成"))
		return results

	try:
		manifest = _load_json(manifest_path)
	except Exception as exc:
		results.append(CheckResult("FAIL", f"cover/image_source_manifest.json 无法解析：{exc}"))
		return results

	manifest_text = "\n".join(_manifest_strings(manifest)).casefold()
	forbidden = sorted(token for token in FORBIDDEN_COVER_PROVENANCE_TOKENS if token in manifest_text)
	if forbidden:
		results.append(CheckResult("FAIL", f"封面底图来源包含禁用值：{', '.join(forbidden)}"))
	else:
		results.append(CheckResult("PASS", "封面底图来源未出现本地/程序化兜底标记"))

	has_ai_provenance = any(token in manifest_text for token in AI_COVER_PROVENANCE_TOKENS)
	if has_ai_provenance:
		results.append(CheckResult("PASS", "封面底图 manifest 含 AI 图像生成来源证据"))
	else:
		results.append(CheckResult("FAIL", "封面底图 manifest 不能证明 background_raw.png 来自 AI 图像生成模型/工具"))

	prompt = str(manifest.get("image_prompt") or manifest.get("prompt") or "").strip()
	negative_prompt = str(manifest.get("negative_prompt") or "").strip()
	if prompt and negative_prompt:
		results.append(CheckResult("PASS", "封面底图 manifest 记录 prompt 和 negative_prompt"))
	else:
		results.append(CheckResult("FAIL", "封面底图 manifest 缺少 image_prompt/prompt 或 negative_prompt"))

	if not visual_subject_path.exists():
		results.append(CheckResult("FAIL", "缺少 cover/visual_subject.json"))
		return results
	try:
		visual_subject = _load_json(visual_subject_path)
	except Exception as exc:
		results.append(CheckResult("FAIL", f"cover/visual_subject.json 无法解析：{exc}"))
		return results
	missing = sorted(field for field in REQUIRED_VISUAL_SUBJECT_FIELDS if not str(visual_subject.get(field, "")).strip())
	if missing:
		results.append(CheckResult("FAIL", f"cover/visual_subject.json 缺少字段：{', '.join(missing)}"))
	else:
		results.append(CheckResult("PASS", "cover/visual_subject.json 记录 strategy/style/image_prompt/negative_prompt"))

	return results


def _count_srt_cues(path: Path | None) -> int:
	if not path or not path.exists():
		return 0
	text = _read_text(path)
	return len(re.findall(r"(?m)^\d+\s*$", text))


def _count_dialogue_turns(path: Path | None) -> dict[str, int]:
	if not path or not path.exists():
		return {}
	text = _read_text(path)
	counts: dict[str, int] = {}
	for role in re.findall(r"(?m)^([^：:\n]{1,20})[：:]", text):
		if role in {"Speaker 0", "Speaker 1", "林遥", "陈澈"}:
			counts[role] = counts.get(role, 0) + 1
	return counts


def _manifest_voice_mode(project_dir: Path) -> str:
	manifest_path = project_dir / "audio" / "audio_manifest.json"
	try:
		return str(_load_json(manifest_path).get("voice_mode") or "")
	except Exception:
		return ""


def _video_streams(info: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
	video = None
	audio = None
	for stream in info.get("streams", []):
		if stream.get("codec_type") == "video" and video is None:
			video = stream
		if stream.get("codec_type") == "audio" and audio is None:
			audio = stream
	return video, audio


def _subtitle_streams(info: dict[str, Any]) -> list[dict[str, Any]]:
	return [stream for stream in info.get("streams", []) if stream.get("codec_type") == "subtitle"]


def _read_title(path: Path | None) -> str:
	if not path or not path.exists():
		return ""
	return _read_text(path).strip().splitlines()[0].strip()


def _publish_time(seconds: float) -> str:
	total = max(0, int(round(seconds)))
	hours = total // 3600
	minutes = (total % 3600) // 60
	secs = total % 60
	if hours:
		return f"{hours:02d}:{minutes:02d}:{secs:02d}"
	return f"{minutes:02d}:{secs:02d}"


def _publish_segments(project_dir: Path) -> list[dict[str, Any]]:
	render_manifest = _load_json(project_dir / "video" / "render_manifest.json")
	render_segments = render_manifest.get("visual_segments")
	if isinstance(render_segments, list) and render_segments:
		return [
			{
				"index": int(segment.get("index") or idx),
				"start_sec": float(segment.get("start_sec")),
				"end_sec": float(segment.get("end_sec")),
				"title": str(segment.get("title") or "").strip() or f"第 {idx} 章",
			}
			for idx, segment in enumerate(render_segments, start=1)
		]
	plan = _load_json(project_dir / "chapter_visuals" / "chapter_plan.json")
	chapters = plan.get("chapters")
	if not isinstance(chapters, list):
		return []
	return [
		{
			"index": int(chapter.get("chapter_index") or idx),
			"start_sec": float(chapter.get("start_sec")),
			"end_sec": float(chapter.get("end_sec")),
			"title": str(chapter.get("chapter_title") or chapter.get("short_title") or "").strip() or f"第 {idx} 章",
		}
		for idx, chapter in enumerate(chapters, start=1)
	]


def _check_publish_info(project_dir: Path, title: str) -> list[CheckResult]:
	path = project_dir / "publish_info.txt"
	if not path.exists():
		return [CheckResult("FAIL", "缺少 publish_info.txt")]
	lines = [line.strip() for line in _read_text(path).splitlines() if line.strip()]
	if not lines:
		return [CheckResult("FAIL", "publish_info.txt 为空")]
	results: list[CheckResult] = []
	if lines[0] == title:
		results.append(CheckResult("PASS", "publish_info.txt 第一行匹配 video_title.txt"))
	else:
		results.append(CheckResult("FAIL", f"publish_info.txt 第一行不等于 video_title.txt：{lines[0]}"))
	try:
		segments = _publish_segments(project_dir)
	except (TypeError, ValueError) as exc:
		return results + [CheckResult("FAIL", f"无法从章节时间轴生成 publish_info 期望行：{exc}")]
	if not segments:
		return results + [CheckResult("FAIL", "publish_info.txt 缺少可验证的章节时间轴来源")]
	expected = [
		f"{_publish_time(float(segment['start_sec']))}-{_publish_time(float(segment['end_sec']))}：{segment['title']}"
		for segment in segments
	]
	actual = lines[1:]
	if actual == expected:
		results.append(CheckResult("PASS", f"publish_info.txt 记录 {len(expected)} 条章节时间轴"))
	else:
		results.append(CheckResult("FAIL", f"publish_info.txt 章节时间轴不匹配：expected={expected[:5]} actual={actual[:5]}"))
	return results


def _check_bilibili_upload_metadata(project_dir: Path, title: str) -> list[CheckResult]:
	path = project_dir / "bilibili_upload_metadata.json"
	if not path.exists():
		return [CheckResult("FAIL", "缺少 bilibili_upload_metadata.json")]
	try:
		metadata = _load_json(path)
	except json.JSONDecodeError as exc:
		return [CheckResult("FAIL", f"bilibili_upload_metadata.json 不是合法 JSON：{exc}")]
	results: list[CheckResult] = []
	if metadata.get("schema_version") == "bilibili_upload_metadata.v1":
		results.append(CheckResult("PASS", "B 站投稿元数据 schema 正常"))
	else:
		results.append(CheckResult("FAIL", f"B 站投稿元数据 schema 不正确：{metadata.get('schema_version')}"))
	if metadata.get("title") == title:
		results.append(CheckResult("PASS", "B 站投稿标题匹配 video_title.txt"))
	else:
		results.append(CheckResult("FAIL", "B 站投稿标题不匹配 video_title.txt"))
	description = str(metadata.get("description") or "")
	if "先行提要" in description and "章节" in description:
		results.append(CheckResult("PASS", "B 站简介包含先行提要和章节"))
	else:
		results.append(CheckResult("FAIL", "B 站简介缺少先行提要或章节"))
	tags = metadata.get("tags")
	if not isinstance(tags, list):
		results.append(CheckResult("FAIL", "B 站标签不是数组"))
	else:
		clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
		if len(clean_tags) != len(set(clean_tags)):
			results.append(CheckResult("FAIL", "B 站标签存在重复"))
		elif 8 <= len(clean_tags) <= 10:
			results.append(CheckResult("PASS", f"B 站标签数量正常：{len(clean_tags)} 个"))
		else:
			results.append(CheckResult("NEEDS_FIX", f"B 站标签数量不理想：{len(clean_tags)} 个"))
		invalid = [tag for tag in clean_tags if len(tag) > 20 or re.search(r"[#\s,，、\"'“”‘’]", tag)]
		if invalid:
			results.append(CheckResult("FAIL", f"B 站标签格式不合格：{invalid}"))
		else:
			results.append(CheckResult("PASS", "B 站标签格式正常"))
		report_path = project_dir / "planning" / "bilibili_tag_report.json"
		if not report_path.exists():
			results.append(CheckResult("FAIL", "缺少 planning/bilibili_tag_report.json"))
		else:
			try:
				tag_report = _load_json(report_path)
			except json.JSONDecodeError as exc:
				results.append(CheckResult("FAIL", f"planning/bilibili_tag_report.json 不是合法 JSON：{exc}"))
			else:
				report_tags = [str(tag).strip() for tag in tag_report.get("tags") or [] if str(tag).strip()]
				tag_sources = tag_report.get("tag_sources")
				if tag_report.get("schema_version") != "bilibili_tag_report.v1":
					results.append(CheckResult("FAIL", f"B 站标签报告 schema 不正确：{tag_report.get('schema_version')}"))
				elif report_tags != clean_tags:
					results.append(CheckResult("FAIL", f"B 站标签报告与 metadata 不一致：report={report_tags} metadata={clean_tags}"))
				elif not isinstance(tag_sources, list) or len(tag_sources) != len(clean_tags):
					results.append(CheckResult("FAIL", "B 站标签报告缺少每个标签的来源"))
				else:
					results.append(CheckResult("PASS", "B 站标签报告记录 tag_sources"))
	if metadata.get("category") == "知识":
		results.append(CheckResult("PASS", "B 站分区固定为知识"))
	else:
		results.append(CheckResult("FAIL", f"B 站分区不是知识：{metadata.get('category')}"))
	if metadata.get("creation_declaration") == "含AI生成内容":
		results.append(CheckResult("PASS", "B 站创作声明固定为含AI生成内容"))
	else:
		results.append(CheckResult("FAIL", f"B 站创作声明不正确：{metadata.get('creation_declaration')}"))
	return results


def _publication_key(publication: str) -> str:
	cleaned = publication.strip().strip("《》")
	cleaned = re.sub(r"\s+", " ", cleaned)
	return cleaned.casefold()


def _has_ascii_alpha(text: str) -> bool:
	return bool(re.search(r"[A-Za-z]", text))


def _has_cjk(text: str) -> bool:
	return bool(re.search(r"[\u3400-\u9fff]", text))


def _chinese_publication_name(publication: str) -> str | None:
	key = _publication_key(publication)
	if not key:
		return None
	if key in PUBLICATION_CHINESE_NAMES:
		return PUBLICATION_CHINESE_NAMES[key]
	if not _has_ascii_alpha(publication):
		return publication.strip().strip("《》")
	return None


def _raw_publication_terms(publication: str) -> list[str]:
	cleaned = re.sub(r"\s+", " ", publication.strip().strip("《》"))
	if not _has_ascii_alpha(cleaned):
		return []
	terms = [cleaned]
	without_the = re.sub(r"(?i)^the\s+", "", cleaned).strip()
	if without_the and without_the != cleaned:
		terms.append(without_the)
	return sorted(set(terms), key=len, reverse=True)


def _contains_raw_publication(text: str, raw_terms: list[str]) -> str | None:
	for term in raw_terms:
		pattern = rf"(?i)(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])"
		if re.search(pattern, text):
			return term
	return None


def _source_visibility_terms(publication: str) -> list[str]:
	terms = list(SOURCE_FRAME_MARKERS)
	terms.extend(_raw_publication_terms(publication))
	chinese_publication = _chinese_publication_name(publication)
	if chinese_publication:
		terms.append(chinese_publication)
	elif publication and not _has_ascii_alpha(publication):
		terms.append(publication.strip().strip("《》"))
	return sorted({term for term in terms if term}, key=len, reverse=True)


def _contains_source_visibility_marker(text: str, terms: list[str]) -> str | None:
	for term in terms:
		if _has_ascii_alpha(term):
			pattern = rf"(?i)(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])"
			if re.search(pattern, text):
				return term
		elif term in text:
			return term
	if re.search(r"据.{0,12}(报道|消息|文章|媒体)", text):
		return "据...报道/消息/文章/媒体"
	return None


def _audience_text_targets(project_dir: Path, srt: Path | None, ass: Path | None) -> list[Path]:
	targets = [
		project_dir / "single_host_script.md",
		project_dir / "podcast_script.md",
		project_dir / "video_title.txt",
		project_dir / "publish_info.txt",
		project_dir / "bilibili_upload_metadata.json",
		project_dir / "cover" / "cover_title.json",
		project_dir / "audio" / "vibevoice_dialogue_display.txt",
		project_dir / "audio" / "vibevoice_dialogue.txt",
		project_dir / "audio" / "audio_manifest.json",
		project_dir / "audio" / "dialogue_timeline.json",
		project_dir / "chapter_visuals" / "chapter_plan.json",
		project_dir / "video" / "subtitle_manifest.json",
		project_dir / "video" / "subtitle_manifest_1x.json",
		project_dir / "video" / "render_manifest.json",
		project_dir / "video" / "final_subtitles_1x.srt",
		project_dir / "video" / "final_subtitles_1x.ass",
	]
	if srt:
		targets.append(srt)
	if ass:
		targets.append(ass)
	return targets


def _playback_speed(project_dir: Path) -> tuple[float, list[CheckResult]]:
	render_manifest = _load_json(project_dir / "video" / "render_manifest.json")
	try:
		speed = float(render_manifest.get("playback_speed_factor"))
	except (TypeError, ValueError):
		return 1.0, [CheckResult("FAIL", "render_manifest.json 缺少 playback_speed_factor")]
	results: list[CheckResult] = []
	if abs(speed - EXPECTED_PLAYBACK_SPEED) <= 0.001:
		results.append(CheckResult("PASS", f"最终视频播放速度为 {EXPECTED_FINAL_TIMELINE}"))
	else:
		results.append(CheckResult("FAIL", f"最终视频播放速度不是 {EXPECTED_FINAL_TIMELINE}：{speed}"))
	if render_manifest.get("pre_speed_video") and render_manifest.get("pre_speed_duration_sec") and render_manifest.get("final_duration_sec"):
		results.append(CheckResult("PASS", "render_manifest 记录速度处理前后视频和时长"))
	else:
		results.append(CheckResult("FAIL", "render_manifest 缺少 pre_speed_video/pre_speed_duration_sec/final_duration_sec"))
	return speed, results


def _title_attribution(project_dir: Path, title: str) -> tuple[dict[str, Any], CheckResult | None]:
	metadata = _load_json(project_dir / "source" / "source_metadata.json")
	publication = str(metadata.get("publication") or "").strip()
	terms = _source_visibility_terms(publication)
	offender = _contains_source_visibility_marker(title, terms)
	attribution = {
		"publication_hidden_in_video_title": offender is None,
		"publication_original": publication,
		"offender": offender,
		"evidence": "source/source_metadata.json publication; remake requires source-erased audience title",
	}
	if offender:
		return attribution, CheckResult("FAIL", f"标题仍有来源露出，应删除而不是中文化：{offender}")
	return attribution, CheckResult("PASS", "标题来源隐身通过：未出现报刊名或来源框架")


def _check_chapter_visuals(project_dir: Path, video_duration: float, playback_speed_factor: float) -> list[CheckResult]:
	results: list[CheckResult] = []
	plan_path = project_dir / "chapter_visuals" / "chapter_plan.json"
	if not plan_path.exists():
		return [CheckResult("FAIL", "缺少 chapter_visuals/chapter_plan.json")]
	plan = _load_json(plan_path)
	chapters = plan.get("chapters", [])
	if not chapters:
		results.append(CheckResult("FAIL", "章节视觉为空"))
		return results
	else:
		results.append(CheckResult("PASS", f"章节视觉数量正常：{len(chapters)} 张"))
	prev_end = -1.0
	for chapter in chapters:
		index = chapter.get("chapter_index")
		image_value = str(chapter.get("image") or "")
		image_path = Path(image_value)
		if not image_path.is_absolute():
			image_path = plan_path.parent / image_path
		size = _image_size(image_path) if image_path.exists() else None
		if size == (3840, 2160):
			results.append(CheckResult("PASS", f"章节 {index} 图片为 3840x2160"))
		else:
			results.append(CheckResult("FAIL", f"章节 {index} 图片尺寸异常：{size}"))
		try:
			start = float(chapter.get("start_sec"))
			end = float(chapter.get("end_sec"))
		except (TypeError, ValueError):
			results.append(CheckResult("FAIL", f"章节 {index} 缺少有效 start_sec/end_sec"))
			continue
		if start < prev_end - 0.001 or end <= start:
			results.append(CheckResult("FAIL", f"章节 {index} 时间轴异常：{start:.3f}-{end:.3f} after {prev_end:.3f}"))
		prev_end = max(prev_end, end)
	expected_final_duration = prev_end / playback_speed_factor if playback_speed_factor else prev_end
	if video_duration and abs(expected_final_duration - video_duration) > 0.75:
		results.append(CheckResult("NEEDS_FIX", f"章节源时间轴按播放速度换算后未覆盖视频结尾：source_last={prev_end:.2f}s speed={playback_speed_factor:.2f} expected={expected_final_duration:.2f}s video={video_duration:.2f}s"))
	elif video_duration:
		results.append(CheckResult("PASS", f"章节时间轴覆盖 {playback_speed_factor:g}x 后视频：source={prev_end:.2f}s final={video_duration:.2f}s"))
	contact = project_dir / "chapter_visuals" / "chapter_visuals_contact_sheet.jpg"
	if contact.exists():
		results.append(CheckResult("PASS", "章节 contact sheet 存在"))
	return results


def _check_visual_transition(project_dir: Path) -> list[CheckResult]:
	render_manifest = _load_json(project_dir / "video" / "render_manifest.json")
	results: list[CheckResult] = []
	visual_segments = render_manifest.get("visual_segments")
	if not isinstance(visual_segments, list) or not visual_segments:
		return [CheckResult("FAIL", "render_manifest 缺少 visual_segments，无法验证章节视觉转场")]
	visual_transition = render_manifest.get("visual_transition") or {}
	outputs = render_manifest.get("outputs") or {}
	visual_base_value = outputs.get("visual_base") or visual_transition.get("visual_base")
	visual_base_path = _manifest_path(project_dir, visual_base_value)
	if visual_base_path and visual_base_path.exists():
		results.append(CheckResult("PASS", "visual_base_1x.mp4 存在，最终视频使用预合成章节视觉轨"))
	else:
		results.append(CheckResult("FAIL", f"缺少 visual_base_1x.mp4 或 manifest 未记录：{visual_base_value}"))
	if len(visual_segments) <= 1:
		results.append(CheckResult("PASS", "只有一张章节图，不需要章节间转场"))
		return results
	if visual_transition.get("effect") == EXPECTED_VISUAL_TRANSITION_EFFECT:
		results.append(CheckResult("PASS", f"章节视觉转场为 {EXPECTED_VISUAL_TRANSITION_EFFECT}"))
	else:
		results.append(CheckResult("FAIL", f"章节视觉转场不是 {EXPECTED_VISUAL_TRANSITION_EFFECT}：{visual_transition}"))
	if visual_transition.get("renderer") == "python_pillow_fixed_compositor":
		results.append(CheckResult("PASS", "章节视觉转场由固定 Python/Pillow compositor 生成"))
	else:
		results.append(CheckResult("FAIL", f"章节视觉转场 renderer 异常：{visual_transition.get('renderer')}"))
	if visual_transition.get("placement") == "centered_on_chapter_boundary":
		results.append(CheckResult("PASS", "章节视觉转场居中绑定在章节边界，不改字幕/音频时间轴"))
	else:
		results.append(CheckResult("FAIL", f"章节视觉转场 placement 异常：{visual_transition.get('placement')}"))
	try:
		transition_count = int(visual_transition.get("transition_count"))
	except (TypeError, ValueError):
		transition_count = -1
	default_duration = float(visual_transition.get("default_duration_sec") or 0.8)
	min_duration = float(visual_transition.get("min_duration_sec") or 0.2)
	max_adjacent_ratio = float(visual_transition.get("max_adjacent_segment_ratio") or 0.4)
	expected = 0
	skipped_too_short = 0
	for previous, current in zip(visual_segments, visual_segments[1:]):
		try:
			previous_duration = float(previous["end_sec"]) - float(previous["start_sec"])
			current_duration = float(current["end_sec"]) - float(current["start_sec"])
		except (KeyError, TypeError, ValueError):
			expected = max(0, len(visual_segments) - 1)
			skipped_too_short = 0
			break
		candidate_duration = min(default_duration, previous_duration * max_adjacent_ratio, current_duration * max_adjacent_ratio)
		if candidate_duration >= min_duration:
			expected += 1
		else:
			skipped_too_short += 1
	if transition_count == expected:
		message = f"章节边界转场数量匹配：{transition_count}"
		if skipped_too_short:
			message += f"，另有 {skipped_too_short} 个过短边界按规则跳过"
		results.append(CheckResult("PASS", message))
	elif transition_count > 0:
		results.append(CheckResult("NEEDS_FIX", f"章节边界转场数量异常：transition_count={transition_count} expected={expected} skipped_too_short={skipped_too_short}"))
	else:
		results.append(CheckResult("FAIL", f"多章节视频没有可用章节转场：transition_count={transition_count} expected={expected} skipped_too_short={skipped_too_short}"))
	units = render_manifest.get("visual_timeline_units")
	if not isinstance(units, list) or not units:
		results.append(CheckResult("FAIL", "render_manifest 缺少 visual_timeline_units"))
		return results
	transition_units = [unit for unit in units if unit.get("kind") == "transition"]
	missing_clips = [
		unit.get("clip")
		for unit in units
		if (clip_path := _manifest_path(project_dir, unit.get("clip"))) is None or not clip_path.exists()
	]
	if missing_clips:
		results.append(CheckResult("FAIL", f"visual_timeline_units 存在缺失 clip：{missing_clips[:5]}"))
	else:
		results.append(CheckResult("PASS", f"visual_timeline_units clip 均存在：{len(units)} 段"))
	if len(transition_units) == transition_count:
		results.append(CheckResult("PASS", "visual_timeline_units 中 transition 段数量匹配 manifest"))
	else:
		results.append(CheckResult("FAIL", f"visual_timeline_units transition 数量不匹配：units={len(transition_units)} manifest={transition_count}"))
	return results


def _check_tts_manifest(project_dir: Path) -> list[CheckResult]:
	audio_manifest_path = project_dir / "audio" / "audio_manifest.json"
	timeline_path = project_dir / "audio" / "dialogue_timeline.json"
	results: list[CheckResult] = []
	if audio_manifest_path.exists():
		manifest = _load_json(audio_manifest_path)
		if manifest.get("audio_backend") == "vibevoice_longform":
			results.append(CheckResult("PASS", "audio_manifest 记录 VibeVoice long-form backend"))
		else:
			results.append(CheckResult("FAIL", f"audio_manifest audio_backend 异常：{manifest.get('audio_backend')}"))
		turns = manifest.get("turns", [])
		if turns:
			results.append(CheckResult("PASS", f"audio_manifest 记录 {len(turns)} 个 Speaker turn"))
		else:
			results.append(CheckResult("FAIL", "audio_manifest 没有 turns"))
		if manifest.get("vibevoice_input_mode") == "tts_normalized":
			results.append(CheckResult("PASS", "audio_manifest 记录 VibeVoice 输入为 TTS 归一化稿"))
		else:
			results.append(CheckResult("FAIL", f"audio_manifest vibevoice_input_mode 不是 tts_normalized：{manifest.get('vibevoice_input_mode')}"))
		if manifest.get("display_dialogue") and manifest.get("display_dialogue_sha256") and manifest.get("vibevoice_input_sha256"):
			results.append(CheckResult("PASS", "audio_manifest 分别记录显示稿和 TTS 输入稿 hash"))
		else:
			results.append(CheckResult("FAIL", "audio_manifest 缺少 display_dialogue/display_dialogue_sha256/vibevoice_input_sha256"))
		missing_tts_text = [turn.get("turn_index") for turn in turns if not str(turn.get("tts_text") or "").strip()]
		if missing_tts_text:
			results.append(CheckResult("FAIL", f"audio_manifest turns 缺少 tts_text：{missing_tts_text[:8]}"))
		elif turns:
			results.append(CheckResult("PASS", "audio_manifest turns 同时记录显示 text 和 TTS tts_text"))
		display_path = project_dir / str(manifest.get("display_dialogue") or "")
		tts_report_path = project_dir / str(manifest.get("tts_normalization_report") or "audio/tts_normalization_report.md")
		if display_path.exists():
			results.append(CheckResult("PASS", "显示稿 audio/vibevoice_dialogue_display.txt 存在"))
		else:
			results.append(CheckResult("FAIL", f"缺少显示稿：{manifest.get('display_dialogue')}"))
		if tts_report_path.exists():
			results.append(CheckResult("PASS", "TTS 归一化报告存在"))
		else:
			results.append(CheckResult("FAIL", f"缺少 TTS 归一化报告：{tts_report_path.relative_to(project_dir) if tts_report_path.is_relative_to(project_dir) else tts_report_path}"))
		if manifest.get("final_audio_sha256") and manifest.get("duration_sec"):
			results.append(CheckResult("PASS", "audio_manifest 记录最终音频 hash 和时长"))
		else:
			results.append(CheckResult("FAIL", "audio_manifest 缺少 final_audio_sha256 或 duration_sec"))
	else:
		legacy_path = project_dir / "audio" / "tts_manifest.json"
		if not legacy_path.exists():
			results.append(CheckResult("FAIL", "缺少 audio/audio_manifest.json"))
		else:
			legacy = _load_json(legacy_path)
			chunks = legacy.get("chunks", [])
			if chunks:
				results.append(CheckResult("PASS", f"legacy tts_manifest 记录 {len(chunks)} 个 chunk"))
			else:
				results.append(CheckResult("FAIL", "legacy tts_manifest 没有 chunks"))
	if timeline_path.exists():
		timeline = _load_json(timeline_path)
		if timeline.get("audio_sha256") and timeline.get("audio_manifest_sha256"):
			results.append(CheckResult("PASS", "dialogue_timeline 记录音频和 audio_manifest hash"))
		else:
			results.append(CheckResult("FAIL", "dialogue_timeline 缺少 audio_sha256 或 audio_manifest_sha256"))
		if timeline.get("cues") or timeline.get("turns"):
			results.append(CheckResult("PASS", "dialogue_timeline 有 ASR 对齐时间轴"))
		else:
			results.append(CheckResult("FAIL", "dialogue_timeline 没有 cues/turns"))
	else:
		results.append(CheckResult("FAIL", "缺少 audio/dialogue_timeline.json"))
	return results


def _check_audio_artifact_qa(project_dir: Path) -> list[CheckResult]:
	artifact_path = project_dir / "audio" / "audio_artifact_qa.json"
	review_path = project_dir / "audio" / "audio_artifact_ai_review.json"
	results: list[CheckResult] = []
	if not artifact_path.exists():
		return [CheckResult("FAIL", "缺少 audio/audio_artifact_qa.json，未运行 turn 边界伪声检测")]
	artifact = _load_json(artifact_path)
	if artifact.get("schema_version") != "article-podcast-audio-artifact-qa.v1":
		results.append(CheckResult("NEEDS_FIX", f"audio_artifact_qa schema 异常：{artifact.get('schema_version')}"))
	status = str(artifact.get("status") or "")
	candidates = list(artifact.get("candidates") or [])
	candidate_ids = {str(candidate.get("candidate_id")) for candidate in candidates if candidate.get("candidate_id")}
	high_risk_count = int((artifact.get("summary") or {}).get("high_risk_count") or 0)
	if status == "PASS":
		results.append(CheckResult("PASS", "turn 边界伪声检测通过：未发现需要复核的候选"))
		return results
	if status != "NEEDS_AI_REVIEW":
		results.append(CheckResult("FAIL", f"audio_artifact_qa 状态异常：{status or '缺失'}"))
		return results
	if not review_path.exists():
		results.append(CheckResult(
			"NEEDS_FIX",
			f"turn 边界伪声检测发现 {len(candidates)} 个候选（高风险 {high_risk_count} 个），缺少 AI 复核文件 audio/audio_artifact_ai_review.json",
		))
		return results
	review = _load_json(review_path)
	review_status = str(review.get("status") or "")
	decisions = list(review.get("decisions") or [])
	decision_by_id = {str(decision.get("candidate_id")): str(decision.get("decision") or "") for decision in decisions}
	missing = sorted(candidate_ids - set(decision_by_id))
	invalid = sorted(
		candidate_id for candidate_id, decision in decision_by_id.items()
		if decision not in {"artifact", "acceptable_tail", "false_positive"}
	)
	artifact_ids = sorted(candidate_id for candidate_id, decision in decision_by_id.items() if decision == "artifact")
	if review_status == "FAIL":
		results.append(CheckResult("FAIL", f"AI 复核状态为 FAIL，确认音频边界伪声未通过：{artifact_ids[:8]}"))
	elif missing:
		results.append(CheckResult("NEEDS_FIX", f"AI 复核未覆盖所有音频伪声候选：missing={missing[:8]}"))
	elif invalid:
		results.append(CheckResult("NEEDS_FIX", f"AI 复核包含无效 decision：{invalid[:8]}"))
	elif artifact_ids:
		results.append(CheckResult("FAIL", f"AI 复核确认存在 turn 边界非语音伪声：{artifact_ids[:8]}"))
	elif review_status in {"PASS", "PASS_WITH_WARNINGS"}:
		results.append(CheckResult("PASS", f"turn 边界伪声候选已 AI 复核通过：{len(candidates)} 个候选，高风险 {high_risk_count} 个"))
	else:
		results.append(CheckResult("NEEDS_FIX", f"AI 复核状态异常：{review_status or '缺失'}"))
	return results


def _check_playback_audio_outputs(project_dir: Path) -> list[CheckResult]:
	results: list[CheckResult] = []
	audio_dir = project_dir / "audio"
	source_wav = audio_dir / "final_podcast.wav"
	preview_mp3 = audio_dir / "final_podcast_preview.mp3"
	playback_m4a = audio_dir / "final_podcast_playback.m4a"
	manifest_path = audio_dir / "playback_audio_manifest.json"
	if source_wav.exists():
		results.append(CheckResult("PASS", "WAV master 存在，仅作为内部对齐/合成源"))
	else:
		results.append(CheckResult("FAIL", "缺少 audio/final_podcast.wav 内部 master"))
	if preview_mp3.exists():
		results.append(CheckResult("PASS", "默认人工试听 MP3 存在：audio/final_podcast_preview.mp3"))
	else:
		results.append(CheckResult("FAIL", "缺少默认人工试听 MP3：audio/final_podcast_preview.mp3"))
	if playback_m4a.exists():
		results.append(CheckResult("PASS", "播放兼容 M4A 存在：audio/final_podcast_playback.m4a"))
	else:
		results.append(CheckResult("FAIL", "缺少播放兼容 M4A：audio/final_podcast_playback.m4a"))
	if not manifest_path.exists():
		results.append(CheckResult("FAIL", "缺少 audio/playback_audio_manifest.json"))
		return results
	manifest = _load_json(manifest_path)
	if manifest.get("source_wav") == "audio/final_podcast.wav" and manifest.get("human_audition_default") == "audio/final_podcast_preview.mp3":
		results.append(CheckResult("PASS", "playback_audio_manifest 声明 WAV 为内部源、MP3 为默认试听"))
	else:
		results.append(CheckResult("FAIL", f"playback_audio_manifest 输入/试听声明异常：source={manifest.get('source_wav')} audition={manifest.get('human_audition_default')}"))
	outputs = manifest.get("outputs", {})
	mp3_codec = outputs.get("mp3", {}).get("ffprobe", {}).get("streams", [{}])[0].get("codec_name")
	m4a_codec = outputs.get("m4a", {}).get("ffprobe", {}).get("streams", [{}])[0].get("codec_name")
	if mp3_codec == "mp3":
		results.append(CheckResult("PASS", "试听文件编码为 MP3"))
	else:
		results.append(CheckResult("FAIL", f"试听文件编码不是 MP3：{mp3_codec}"))
	if m4a_codec == "aac":
		results.append(CheckResult("PASS", "M4A 播放副本编码为 AAC"))
	else:
		results.append(CheckResult("FAIL", f"M4A 播放副本编码不是 AAC：{m4a_codec}"))
	return results


def _check_final_video_audio_integrity(project_dir: Path) -> list[CheckResult]:
	results: list[CheckResult] = []
	render_manifest = _load_json(project_dir / "video" / "render_manifest.json")
	check = render_manifest.get("audio_video_check") or {}
	if not check:
		return [CheckResult("FAIL", "render_manifest 缺少 audio_video_check，无法确认视频合成没有损伤音频")]
	status = check.get("status")
	try:
		correlation = float(check.get("sample_correlation"))
		rms_ratio = float(check.get("rms_diff_over_source"))
	except (TypeError, ValueError):
		return [CheckResult("FAIL", f"audio_video_check 缺少有效相关性/RMS 指标：{check}")]
	if status == "PASS" and correlation >= MIN_AUDIO_VIDEO_CORRELATION and rms_ratio <= MAX_AUDIO_VIDEO_RMS_DIFF_OVER_SOURCE:
		results.append(CheckResult("PASS", f"视频抽取音频与 WAV master 一致：corr={correlation:.6f}, rms_diff/source={rms_ratio:.6f}"))
	else:
		results.append(CheckResult("FAIL", f"视频音频与 WAV master 校验失败：status={status}, corr={correlation:.6f}, rms_diff/source={rms_ratio:.6f}"))
	if Path(str(check.get("extracted_audio") or "")).exists():
		results.append(CheckResult("PASS", "视频抽取音频检查文件存在"))
	else:
		results.append(CheckResult("FAIL", f"缺少视频抽取音频检查文件：{check.get('extracted_audio')}"))
	return results


def _check_subtitle_style(project_dir: Path, ass: Path | None) -> list[CheckResult]:
	results: list[CheckResult] = []
	subtitle_manifest = _load_json(project_dir / "video" / "subtitle_manifest.json")
	style = subtitle_manifest.get("style", {})
	shadow = style.get("shadow")
	try:
		outline_width = float(style.get("outline_width_px"))
	except (TypeError, ValueError):
		outline_width = -1.0
	if (
		style.get("background_box") is False
		and style.get("outline") == EXPECTED_SUBTITLE_OUTLINE
		and 0 < outline_width <= EXPECTED_SUBTITLE_OUTLINE_WIDTH_PX
		and shadow == "soft_drop_shadow"
		and str(style.get("back_color") or "").lower() == "transparent"
	):
		results.append(CheckResult("PASS", "字幕样式无背景底框，使用 3px 以内半透明细描边和柔和投影"))
	else:
		results.append(CheckResult("FAIL", f"字幕样式未明确使用 A 方案（无底框、半透明细描边、柔和投影）：{style}"))
	if int(style.get("preferred_lines") or -1) == 1 and int(style.get("max_lines") or -1) == 1 and "single_line" in str(style.get("line_policy") or ""):
		results.append(CheckResult("PASS", "字幕样式声明单行优先：preferred_lines=1/max_lines=1"))
	else:
		results.append(CheckResult("FAIL", f"字幕样式未声明单行策略：{style}"))
	try:
		letter_spacing = float(style.get("letter_spacing_px"))
	except (TypeError, ValueError):
		results.append(CheckResult("FAIL", f"字幕样式缺少 letter_spacing_px={EXPECTED_SUBTITLE_LETTER_SPACING_PX}：{style}"))
	else:
		if MIN_SUBTITLE_LETTER_SPACING_PX <= letter_spacing <= MAX_SUBTITLE_LETTER_SPACING_PX:
			results.append(CheckResult("PASS", f"字幕字距正常：letter_spacing_px={letter_spacing:g}"))
		else:
			results.append(CheckResult("FAIL", f"字幕字距不在 {MIN_SUBTITLE_LETTER_SPACING_PX}..{MAX_SUBTITLE_LETTER_SPACING_PX}px：{letter_spacing:g}"))
	if int(style.get("subtitle_block_top_min_y") or -1) == SUBTITLE_BLOCK_TOP_MIN_Y:
		results.append(CheckResult("PASS", f"字幕块安全区上沿记录正常：min_y={SUBTITLE_BLOCK_TOP_MIN_Y}"))
	else:
		results.append(CheckResult("FAIL", f"字幕样式未记录 subtitle_block_top_min_y={SUBTITLE_BLOCK_TOP_MIN_Y}：{style}"))
	if int(style.get("subtitle_block_top_max_y") or -1) == SUBTITLE_BLOCK_TOP_MAX_Y and int(style.get("subtitle_block_bottom_max_y") or -1) == SUBTITLE_BLOCK_BOTTOM_MAX_Y:
		results.append(CheckResult("PASS", f"字幕块播放器控制条安全区正常：top_y<={SUBTITLE_BLOCK_TOP_MAX_Y}, bottom_y<={SUBTITLE_BLOCK_BOTTOM_MAX_Y}"))
	else:
		results.append(CheckResult("FAIL", f"字幕样式未记录播放器控制条安全区 top_max/bottom_max：{style}"))
	if ass is None or not ass.exists():
		return results
	text = _read_text(ass)
	style_line = next((line for line in text.splitlines() if line.startswith("Style:")), "")
	if not style_line:
		results.append(CheckResult("FAIL", "ASS 缺少 Style 行"))
		return results
	fields = [field.strip() for field in style_line.removeprefix("Style:").split(",")]
	if len(fields) < 18:
		results.append(CheckResult("FAIL", f"ASS Style 字段不足：{style_line}"))
		return results
	border_style = fields[15]
	outline_colour = fields[5]
	back_colour = fields[6]
	ass_outline_width = fields[16]
	shadow = fields[17]
	spacing = fields[13]
	if border_style == "1":
		results.append(CheckResult("PASS", "ASS BorderStyle=1，没有字幕背景框"))
	else:
		results.append(CheckResult("FAIL", f"ASS BorderStyle 应为 1，实际为 {border_style}"))
	if re.match(r"(?i)&HFF[0-9A-F]{6}$", back_colour):
		results.append(CheckResult("PASS", f"ASS BackColour 全透明：{back_colour}"))
	else:
		results.append(CheckResult("FAIL", f"ASS BackColour 不是全透明：{back_colour}"))
	try:
		ass_outline_width_value = float(ass_outline_width)
	except ValueError:
		results.append(CheckResult("FAIL", f"ASS Outline 不是数字：{ass_outline_width}"))
	else:
		if 0 < ass_outline_width_value <= EXPECTED_SUBTITLE_OUTLINE_WIDTH_PX:
			results.append(CheckResult("PASS", f"ASS Outline 为半透明细描边宽度：{ass_outline_width_value:g}px"))
		else:
			results.append(CheckResult("FAIL", f"ASS Outline 应为 0 < width <= {EXPECTED_SUBTITLE_OUTLINE_WIDTH_PX}px 的细描边，实际为 {ass_outline_width_value:g}px"))
	if re.match(r"(?i)&H[7-9A-F][0-9A-F]000000$", outline_colour):
		results.append(CheckResult("PASS", f"ASS OutlineColour 为半透明深色：{outline_colour}"))
	else:
		results.append(CheckResult("FAIL", f"ASS OutlineColour 应为半透明深色而不是粗黑边色：{outline_colour}"))
	if shadow in {"0", "0.0"}:
		results.append(CheckResult("PASS", "ASS Shadow=0，没有阴影色"))
	else:
		results.append(CheckResult("FAIL", f"ASS Shadow 应为 0，实际为 {shadow}"))
	try:
		ass_spacing = float(spacing)
	except ValueError:
		results.append(CheckResult("FAIL", f"ASS Spacing 不是数字：{spacing}"))
	else:
		if MIN_SUBTITLE_LETTER_SPACING_PX <= ass_spacing <= MAX_SUBTITLE_LETTER_SPACING_PX:
			results.append(CheckResult("PASS", f"ASS Spacing 记录轻微字距：{ass_spacing:g}"))
		else:
			results.append(CheckResult("FAIL", f"ASS Spacing 不在 {MIN_SUBTITLE_LETTER_SPACING_PX}..{MAX_SUBTITLE_LETTER_SPACING_PX}px：{ass_spacing:g}"))
	return results


def _check_burned_subtitle_safe_zone(project_dir: Path) -> list[CheckResult]:
	results: list[CheckResult] = []
	render_manifest = _load_json(project_dir / "video" / "render_manifest.json")
	layout_rule = render_manifest.get("subtitle_layout_rule", {})
	if int(layout_rule.get("subtitle_block_top_min_y") or -1) == SUBTITLE_BLOCK_TOP_MIN_Y:
		results.append(CheckResult("PASS", f"render_manifest 记录字幕安全区上沿 min_y={SUBTITLE_BLOCK_TOP_MIN_Y}"))
	else:
		results.append(CheckResult("FAIL", f"render_manifest 缺少字幕起始线 y={SUBTITLE_BLOCK_TOP_MIN_Y}：{layout_rule}"))
	if int(layout_rule.get("subtitle_block_top_max_y") or -1) == SUBTITLE_BLOCK_TOP_MAX_Y and int(layout_rule.get("subtitle_block_bottom_max_y") or -1) == SUBTITLE_BLOCK_BOTTOM_MAX_Y:
		results.append(CheckResult("PASS", f"render_manifest 记录播放器控制条安全区 top_y<={SUBTITLE_BLOCK_TOP_MAX_Y}, bottom_y<={SUBTITLE_BLOCK_BOTTOM_MAX_Y}"))
	else:
		results.append(CheckResult("FAIL", f"render_manifest 缺少播放器控制条安全区 top_max/bottom_max：{layout_rule}"))
	if layout_rule.get("overlap_policy") == "latest_started_cue_visible":
		results.append(CheckResult("PASS", "硬字幕重叠策略为 latest_started_cue_visible，不会顺延后续字幕"))
	else:
		results.append(CheckResult("FAIL", f"render_manifest 缺少硬字幕重叠策略 latest_started_cue_visible：{layout_rule}"))
	try:
		glyph_edge_pad = float(layout_rule.get("glyph_edge_pad_px"))
		shear_edge_pad = float(layout_rule.get("shear_edge_pad_px"))
	except (TypeError, ValueError):
		results.append(CheckResult("FAIL", f"render_manifest 缺少字幕左右 glyph/shear 防裁切边距：{layout_rule}"))
	else:
		if glyph_edge_pad >= MIN_SUBTITLE_GLYPH_EDGE_PAD_PX and shear_edge_pad >= MIN_SUBTITLE_SHEAR_EDGE_PAD_PX:
			results.append(CheckResult("PASS", f"硬字幕左右防裁切边距正常：glyph={glyph_edge_pad:g}px, shear={shear_edge_pad:g}px"))
		else:
			results.append(CheckResult("FAIL", f"硬字幕左右防裁切边距不足：glyph={glyph_edge_pad:g}px, shear={shear_edge_pad:g}px"))
	if layout_rule.get("shear_transform") == "forward_x_plus_shear_y_with_positive_padding":
		results.append(CheckResult("PASS", "硬字幕斜体变换使用正向 padding，不会把首字采样到画布外"))
	else:
		results.append(CheckResult("FAIL", f"硬字幕斜体变换未声明防首字裁切策略：{layout_rule}"))
	offenders: list[str] = []
	spacing_offenders: list[str] = []
	edge_pad_offenders: list[str] = []
	checked = 0
	for segment in render_manifest.get("segments", []):
		if not str(segment.get("subtitle_text") or "").strip():
			continue
		checked += 1
		layout = segment.get("subtitle_layout") or {}
		try:
			top_y = float(layout.get("top_y"))
			bottom_y = float(layout.get("bottom_y"))
		except (TypeError, ValueError):
			offenders.append(f"segment {segment.get('index')} missing layout")
			continue
		if top_y < SUBTITLE_BLOCK_TOP_MIN_Y - 0.001:
			offenders.append(f"segment {segment.get('index')} top_y={top_y:.1f} above safe band")
		if top_y > SUBTITLE_BLOCK_TOP_MAX_Y + 0.001:
			offenders.append(f"segment {segment.get('index')} top_y={top_y:.1f} too low for player controls")
		if bottom_y > SUBTITLE_BLOCK_BOTTOM_MAX_Y + 0.001:
			offenders.append(f"segment {segment.get('index')} bottom_y={bottom_y:.1f} too low for player controls")
		if bottom_y > 2160:
			offenders.append(f"segment {segment.get('index')} bottom_y={bottom_y:.1f}")
		try:
			letter_spacing = float(layout.get("letter_spacing_px"))
		except (TypeError, ValueError):
			spacing_offenders.append(f"segment {segment.get('index')} missing letter_spacing_px")
		else:
			if not (MIN_SUBTITLE_LETTER_SPACING_PX <= letter_spacing <= MAX_SUBTITLE_LETTER_SPACING_PX):
				spacing_offenders.append(f"segment {segment.get('index')} letter_spacing_px={letter_spacing:g}")
		try:
			glyph_edge_pad = float(layout.get("glyph_edge_pad_px"))
			shear_edge_pad = float(layout.get("shear_edge_pad_px"))
		except (TypeError, ValueError):
			edge_pad_offenders.append(f"segment {segment.get('index')} missing edge pad")
		else:
			if glyph_edge_pad < MIN_SUBTITLE_GLYPH_EDGE_PAD_PX or shear_edge_pad < MIN_SUBTITLE_SHEAR_EDGE_PAD_PX:
				edge_pad_offenders.append(f"segment {segment.get('index')} glyph={glyph_edge_pad:g} shear={shear_edge_pad:g}")
	if offenders:
		results.append(CheckResult("FAIL", f"硬字幕位置异常或越过画布：{offenders[:8]}"))
	elif checked:
		results.append(CheckResult("PASS", f"硬字幕布局通过：{checked} 个字幕 segment 位于播放器控制条上方安全区"))
	else:
		results.append(CheckResult("FAIL", "render_manifest 没有可检查的硬字幕布局记录"))
	if spacing_offenders:
		results.append(CheckResult("FAIL", f"硬字幕字距记录异常：{spacing_offenders[:8]}"))
	elif checked:
		results.append(CheckResult("PASS", f"硬字幕字距布局通过：{checked} 个 segment 记录轻微 tracking"))
	if edge_pad_offenders:
		results.append(CheckResult("FAIL", f"硬字幕左右防裁切边距异常：{edge_pad_offenders[:8]}"))
	elif checked:
		results.append(CheckResult("PASS", f"硬字幕左右防裁切边距通过：{checked} 个 segment 记录 glyph/shear padding"))
	return results


def _has_sentence_period(text: str) -> bool:
	if "。" in text or "．" in text:
		return True
	return bool(re.search(r"(?<!\d)\.(?!\d)", text))


def _srt_visible_text(path: Path | None) -> list[str]:
	if path is None or not path.exists():
		return []
	lines: list[str] = []
	for line in _read_text(path).splitlines():
		clean = line.strip()
		if not clean or clean.isdigit() or "-->" in clean:
			continue
		lines.append(clean)
	return lines


def _srt_visible_blocks(path: Path | None) -> list[list[str]]:
	if path is None or not path.exists():
		return []
	blocks: list[list[str]] = []
	for block in re.split(r"\n\s*\n", _read_text(path).strip()):
		visible_lines: list[str] = []
		for line in block.splitlines():
			clean = line.strip()
			if not clean or clean.isdigit() or "-->" in clean:
				continue
			visible_lines.append(clean)
		if visible_lines:
			blocks.append(visible_lines)
	return blocks


def _ass_dialogue_text(path: Path | None) -> list[str]:
	if path is None or not path.exists():
		return []
	lines: list[str] = []
	for line in _read_text(path).splitlines():
		if not line.startswith("Dialogue:"):
			continue
		parts = line.split(",", 9)
		if len(parts) == 10:
			lines.append(parts[9].replace("\\N", "\n"))
	return lines


def _check_subtitle_line_policy(project_dir: Path, srt: Path | None, ass: Path | None) -> list[CheckResult]:
	results: list[CheckResult] = []
	subtitle_manifest = _load_json(project_dir / "video" / "subtitle_manifest.json")
	bad_manifest: list[int] = []
	for cue in subtitle_manifest.get("cues", []):
		display_text = str(cue.get("display_text") or "")
		if "\\N" in display_text or len(display_text.splitlines()) > 1:
			bad_manifest.append(int(cue.get("index") or 0))
	if bad_manifest:
		results.append(CheckResult("FAIL", f"subtitle_manifest 存在两行字幕 cue：{bad_manifest[:8]}"))
	else:
		results.append(CheckResult("PASS", "subtitle_manifest 字幕均为单行 display_text"))
	bad_srt = [idx for idx, block in enumerate(_srt_visible_blocks(srt), start=1) if len(block) > 1]
	if bad_srt:
		results.append(CheckResult("FAIL", f"SRT 存在两行字幕 cue：{bad_srt[:8]}"))
	elif srt and srt.exists():
		results.append(CheckResult("PASS", "SRT 字幕均为单行 cue"))
	bad_ass = [idx for idx, text in enumerate(_ass_dialogue_text(ass), start=1) if "\\N" in text or len(text.splitlines()) > 1]
	if bad_ass:
		results.append(CheckResult("FAIL", f"ASS 存在两行字幕 cue：{bad_ass[:8]}"))
	elif ass and ass.exists():
		results.append(CheckResult("PASS", "ASS Dialogue 字幕均为单行"))
	render_manifest = _load_json(project_dir / "video" / "render_manifest.json")
	bad_render: list[str] = []
	checked = 0
	for segment in render_manifest.get("segments", []):
		subtitle_text = str(segment.get("subtitle_text") or "")
		if not subtitle_text.strip():
			continue
		checked += 1
		layout = segment.get("subtitle_layout") or {}
		try:
			line_count = int(layout.get("line_count"))
		except (TypeError, ValueError):
			bad_render.append(f"segment {segment.get('index')} missing line_count")
			continue
		if "\\n" in subtitle_text or "\n" in subtitle_text or line_count > 1:
			bad_render.append(f"segment {segment.get('index')} line_count={line_count}")
	if bad_render:
		results.append(CheckResult("FAIL", f"硬烧录字幕存在两行布局：{bad_render[:8]}"))
	elif checked:
		results.append(CheckResult("PASS", f"硬烧录字幕布局均为单行：{checked} 个 segment"))
	else:
		results.append(CheckResult("FAIL", "render_manifest 没有可检查的硬字幕单行记录"))
	return results


def _check_no_sentence_periods(project_dir: Path, srt: Path | None, ass: Path | None) -> list[CheckResult]:
	results: list[CheckResult] = []
	subtitle_manifest = _load_json(project_dir / "video" / "subtitle_manifest.json")
	style = subtitle_manifest.get("style", {})
	if style.get("sentence_periods_displayed") is False:
		results.append(CheckResult("PASS", "字幕样式明确禁用句号显示"))
	else:
		results.append(CheckResult("FAIL", "subtitle_manifest style 缺少 sentence_periods_displayed=false"))
	bad_manifest: list[int] = []
	for cue in subtitle_manifest.get("cues", []):
		index = int(cue.get("index") or 0)
		if _has_sentence_period(str(cue.get("text") or "")) or _has_sentence_period(str(cue.get("display_text") or "")):
			bad_manifest.append(index)
	if bad_manifest:
		results.append(CheckResult("FAIL", f"subtitle_manifest 存在带句号的字幕 cue：{bad_manifest[:8]}"))
	else:
		results.append(CheckResult("PASS", "subtitle_manifest 字幕文本不显示句号"))
	bad_srt = [line for line in _srt_visible_text(srt) if _has_sentence_period(line)]
	if bad_srt:
		results.append(CheckResult("FAIL", f"SRT 可见字幕仍含句号：{bad_srt[:3]}"))
	elif srt and srt.exists():
		results.append(CheckResult("PASS", "SRT 可见字幕不显示句号"))
	bad_ass = [line for line in _ass_dialogue_text(ass) if _has_sentence_period(line)]
	if bad_ass:
		results.append(CheckResult("FAIL", f"ASS Dialogue 字幕仍含句号：{bad_ass[:3]}"))
	elif ass and ass.exists():
		results.append(CheckResult("PASS", "ASS Dialogue 字幕不显示句号"))
	return results


def _check_preferred_chinese_names(project_dir: Path, srt: Path | None, ass: Path | None) -> list[CheckResult]:
	results: list[CheckResult] = []
	zhipu_targets = [
		project_dir / "podcast_script.md",
		project_dir / "source" / "fact_notes.md",
		project_dir / "audio" / "audio_manifest.json",
		project_dir / "audio" / "dialogue_timeline.json",
		project_dir / "chapter_visuals" / "chapter_plan.json",
		project_dir / "video" / "subtitle_manifest.json",
		project_dir / "video" / "subtitle_manifest_1x.json",
		project_dir / "video" / "render_manifest.json",
	]
	if srt:
		zhipu_targets.append(srt)
	if ass:
		zhipu_targets.append(ass)
	zhipu_offenders: list[str] = []
	for path in zhipu_targets:
		if path.exists() and re.search(r"\bZhipu(?:\s+AI)?\b", _read_text(path), flags=re.IGNORECASE):
			zhipu_offenders.append(str(path.relative_to(project_dir)))
	if zhipu_offenders:
		results.append(CheckResult("FAIL", f"面向观众的衍生产物仍有未中文化公司名，应改为智谱：{zhipu_offenders[:8]}"))
	else:
		results.append(CheckResult("PASS", "专名中文化通过：衍生产物使用智谱"))

	metadata = _load_json(project_dir / "source" / "source_metadata.json")
	publication = str(metadata.get("publication") or "").strip()
	source_terms = _source_visibility_terms(publication)
	source_offenders: list[str] = []
	for path in _audience_text_targets(project_dir, srt, ass):
		if not path.exists():
			continue
		offender = _contains_source_visibility_marker(_read_text(path), source_terms)
		if offender:
			source_offenders.append(f"{path.relative_to(project_dir)} contains {offender}")
	if source_offenders:
		results.append(CheckResult("FAIL", f"观众可见产物仍有来源露出，应删除而不是中文化：{source_offenders[:8]}"))
	else:
		results.append(CheckResult("PASS", "来源隐身通过：文稿、标题、封面、时间轴和字幕未出现报刊名或来源框架"))
	return results


def _check_subtitle_timing(project_dir: Path, video_duration: float, playback_speed_factor: float) -> list[CheckResult]:
	results: list[CheckResult] = []
	subtitle_manifest = _load_json(project_dir / "video" / "subtitle_manifest.json")
	cues = subtitle_manifest.get("cues", [])
	try:
		subtitle_speed = float(subtitle_manifest.get("playback_speed_factor"))
	except (TypeError, ValueError):
		subtitle_speed = 0.0
	if abs(subtitle_speed - playback_speed_factor) <= 0.001 and abs(subtitle_speed - EXPECTED_PLAYBACK_SPEED) <= 0.001:
		results.append(CheckResult("PASS", f"subtitle_manifest 记录 {EXPECTED_FINAL_TIMELINE} 最终字幕时间轴"))
	else:
		results.append(CheckResult("FAIL", f"subtitle_manifest playback_speed_factor 异常：{subtitle_manifest.get('playback_speed_factor')}"))
	if subtitle_manifest.get("source_timeline") == "1x" and subtitle_manifest.get("final_timeline") == EXPECTED_FINAL_TIMELINE:
		results.append(CheckResult("PASS", f"subtitle_manifest 明确记录 1x 来源和 {EXPECTED_FINAL_TIMELINE} 最终时间轴"))
	else:
		results.append(CheckResult("FAIL", f"subtitle_manifest 缺少 source_timeline=1x / final_timeline={EXPECTED_FINAL_TIMELINE}"))
	if (project_dir / "video" / "final_subtitles_1x.srt").exists() and (project_dir / "video" / "final_subtitles_1x.ass").exists():
		results.append(CheckResult("PASS", "保留 1x 原始字幕副本"))
	else:
		results.append(CheckResult("FAIL", "缺少 final_subtitles_1x.srt/final_subtitles_1x.ass 原始字幕副本"))
	if not isinstance(cues, list) or not cues:
		results.append(CheckResult("FAIL", "subtitle_manifest 没有 cues"))
		return results
	prev_end = -1.0
	max_overlap = 0.0
	last_end = 0.0
	for cue in cues:
		try:
			start = float(cue.get("start_sec"))
			end = float(cue.get("end_sec"))
		except (AttributeError, TypeError, ValueError):
			results.append(CheckResult("FAIL", "subtitle_manifest 存在无效 cue 时间"))
			return results
		max_overlap = max(max_overlap, max(0.0, prev_end - start))
		if start < prev_end - MAX_SUBTITLE_OVERLAP_SEC or end <= start:
			results.append(CheckResult("FAIL", f"字幕 cue 时间轴异常：{start:.3f}-{end:.3f} after {prev_end:.3f}"))
			return results
		prev_end = end
		last_end = end
	results.append(CheckResult("PASS", f"字幕 cue 时间轴正常：{len(cues)} 条，最大相邻 overlap={max_overlap:.3f}s"))
	if video_duration and abs(last_end - video_duration) <= 1.5:
		results.append(CheckResult("PASS", f"最终字幕覆盖 {EXPECTED_FINAL_TIMELINE} 视频结尾：last={last_end:.2f}s video={video_duration:.2f}s"))
	elif video_duration:
		results.append(CheckResult("FAIL", f"最终字幕未覆盖 {EXPECTED_FINAL_TIMELINE} 视频结尾：last={last_end:.2f}s video={video_duration:.2f}s"))
	return results


def _status(results: list[CheckResult]) -> str:
	if any(result.status == "FAIL" for result in results):
		return "FAIL"
	if any(result.status == "NEEDS_FIX" for result in results):
		return "NEEDS_FIX"
	return "PASS"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="QA an English-article-to-Chinese-podcast-video production folder.")
	parser.add_argument("--project-dir", required=True)
	parser.add_argument("--script")
	parser.add_argument("--cover")
	parser.add_argument("--video")
	parser.add_argument("--title")
	parser.add_argument("--srt")
	parser.add_argument("--ass")
	parser.add_argument("--min-duration-sec", type=float, default=60.0)
	parser.add_argument("--allow-non-4k", action="store_true")
	parser.add_argument("--require-mp4-subtitle-track", action="store_true")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	project_dir = Path(args.project_dir).expanduser().resolve()
	if not project_dir.exists():
		raise FileNotFoundError(project_dir)

	script = _find_text(project_dir, args.script, ("single_host_script", "podcast_script", "chinese_podcast", "口播", "文稿"))
	title_path = _find_text(project_dir, args.title, ("video_title", "title", "标题"))
	cover = _find_image(project_dir, args.cover)
	video = _find_video(project_dir, args.video)
	srt = _find_subtitle(project_dir, args.srt, ".srt")
	ass = _find_subtitle(project_dir, args.ass, ".ass")

	results: list[CheckResult] = []
	duration = 0.0
	voice_mode = _manifest_voice_mode(project_dir)
	if script is None:
		results.append(CheckResult("FAIL", "缺少 single_host_script.md / podcast_script.md 或可识别的中文口播文稿"))
	else:
		turn_counts = _count_dialogue_turns(script)
		if voice_mode == "single_host" or script.name == "single_host_script.md":
			body = _read_text(script).split("## 正文", 1)[-1]
			if re.search(r"(?m)^Speaker\s+\d+\s*[:：]", body):
				results.append(CheckResult("FAIL", "单人口播正文不应包含 Speaker 标签"))
			elif len(re.sub(r"\s+", "", body)) < 1200:
				results.append(CheckResult("NEEDS_FIX", "单人口播正文偏短"))
			else:
				results.append(CheckResult("PASS", f"单人口播文稿存在：{script.name}"))
		else:
			host_count = turn_counts.get("Speaker 0", 0) or turn_counts.get("林遥", 0)
			expert_count = turn_counts.get("Speaker 1", 0) or turn_counts.get("陈澈", 0)
			if host_count < 2 or expert_count < 2:
				results.append(CheckResult("NEEDS_FIX", f"文稿角色回合偏少：{turn_counts}"))
			else:
				results.append(CheckResult("PASS", f"文稿角色结构正常：{turn_counts}"))

	title = _read_title(title_path)
	if not title:
		results.append(CheckResult("FAIL", "缺少 video_title.txt 或标题为空"))
	else:
		title_len = len(re.sub(r"\s+", "", title))
		if title_len < 12 or title_len > 48:
			results.append(CheckResult("NEEDS_FIX", f"视频标题长度不理想：{title_len} 字"))
		else:
			results.append(CheckResult("PASS", f"视频标题存在：{title}"))
	title_attribution, attribution_result = _title_attribution(project_dir, title)
	if attribution_result:
		results.append(attribution_result)
	results.extend(_check_publish_info(project_dir, title))
	results.extend(_check_bilibili_upload_metadata(project_dir, title))

	cover_size = _image_size(cover) if cover else None
	if cover is None:
		results.append(CheckResult("FAIL", "缺少封面图"))
	elif cover_size is None:
		results.append(CheckResult("NEEDS_FIX", f"无法用 Pillow 读取封面尺寸：{cover}"))
	elif cover_size != (3840, 2160):
		results.append(CheckResult("FAIL", f"封面不是 4K 16:9：{cover_size[0]}x{cover_size[1]}"))
	else:
		results.append(CheckResult("PASS", "封面尺寸为 3840x2160"))
	results.extend(_check_cover_background_provenance(project_dir))

	video_info: dict[str, Any] | None = None
	if video is None:
		results.append(CheckResult("FAIL", "缺少 final_video.mp4"))
	else:
		try:
			video_info = _ffprobe(video)
		except subprocess.CalledProcessError as exc:
			detail = (exc.stderr or exc.stdout or str(exc)).strip().splitlines()[-1]
			results.append(CheckResult("FAIL", f"视频无法被 ffprobe 读取：{detail}"))
		else:
			video_stream, audio_stream = _video_streams(video_info)
			subtitle_streams = _subtitle_streams(video_info)
			duration = float(video_info.get("format", {}).get("duration") or 0)
			if video_stream is None:
				results.append(CheckResult("FAIL", "视频缺少 video stream"))
			elif not args.allow_non_4k and (video_stream.get("width"), video_stream.get("height")) != (3840, 2160):
				results.append(CheckResult("FAIL", f"视频不是 3840x2160：{video_stream.get('width')}x{video_stream.get('height')}"))
			else:
				results.append(CheckResult("PASS", f"视频轨正常：{video_stream.get('codec_name')} {video_stream.get('width')}x{video_stream.get('height')}"))
			if audio_stream is None:
				results.append(CheckResult("FAIL", "视频缺少 audio stream"))
			elif audio_stream.get("codec_name") == "aac":
				results.append(CheckResult("PASS", "视频音频轨为 AAC"))
			else:
				results.append(CheckResult("FAIL", f"视频音频轨不是 AAC：{audio_stream.get('codec_name')}"))
			if duration < args.min_duration_sec:
				results.append(CheckResult("NEEDS_FIX", f"视频时长低于阈值：{duration:.2f}s < {args.min_duration_sec:.2f}s"))
			else:
				results.append(CheckResult("PASS", f"视频时长正常：{duration:.2f}s"))
			if subtitle_streams:
				codecs = ", ".join(str(stream.get("codec_name")) for stream in subtitle_streams)
				results.append(CheckResult("PASS", f"MP4 内置字幕轨正常：{len(subtitle_streams)} 条（{codecs}）"))
			elif args.require_mp4_subtitle_track:
				results.append(CheckResult("FAIL", "MP4 缺少内置字幕轨"))
			else:
				results.append(CheckResult("PASS", "MP4 未内置软字幕轨，使用画面硬字幕和旁路 SRT"))

	srt_cues = _count_srt_cues(srt)
	if srt is None:
		results.append(CheckResult("FAIL", "缺少 SRT 字幕文件"))
	elif srt_cues == 0:
		results.append(CheckResult("FAIL", "SRT 字幕没有 cue"))
	else:
		results.append(CheckResult("PASS", f"SRT 字幕存在：{srt_cues} 条"))
	if ass is None:
		results.append(CheckResult("NEEDS_FIX", "缺少 ASS 字幕文件"))
	else:
		results.append(CheckResult("PASS", "ASS 字幕存在"))
	results.extend(_check_subtitle_style(project_dir, ass))
	results.extend(_check_burned_subtitle_safe_zone(project_dir))
	results.extend(_check_subtitle_line_policy(project_dir, srt, ass))
	results.extend(_check_no_sentence_periods(project_dir, srt, ass))
	results.extend(_check_preferred_chinese_names(project_dir, srt, ass))
	results.extend(_check_tts_manifest(project_dir))
	results.extend(_check_audio_artifact_qa(project_dir))
	results.extend(_check_playback_audio_outputs(project_dir))
	results.extend(_check_final_video_audio_integrity(project_dir))
	playback_speed_factor, speed_results = _playback_speed(project_dir)
	results.extend(speed_results)
	results.extend(_check_subtitle_timing(project_dir, duration, playback_speed_factor))
	results.extend(_check_chapter_visuals(project_dir, duration, playback_speed_factor))
	results.extend(_check_visual_transition(project_dir))

	final_status = _status(results)
	manifest = {
		"schema_version": "english-article-chinese-single-host-video-remake.qa.v3",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"status": final_status,
		"project_dir": str(project_dir),
		"playback_speed_factor": playback_speed_factor,
		"title_attribution": title_attribution,
		"outputs": {
			"video_title": title,
			"title_path": str(title_path) if title_path else None,
			"publish_info": str(project_dir / "publish_info.txt") if (project_dir / "publish_info.txt").exists() else None,
			"publish_info_sha256": _sha256(project_dir / "publish_info.txt") if (project_dir / "publish_info.txt").exists() else None,
			"bilibili_upload_metadata": str(project_dir / "bilibili_upload_metadata.json") if (project_dir / "bilibili_upload_metadata.json").exists() else None,
			"bilibili_upload_metadata_sha256": _sha256(project_dir / "bilibili_upload_metadata.json") if (project_dir / "bilibili_upload_metadata.json").exists() else None,
			"podcast_script": str(script) if script else None,
			"cover": str(cover) if cover else None,
			"visual_base": str(project_dir / "video" / "visual_base_1x.mp4") if (project_dir / "video" / "visual_base_1x.mp4").exists() else None,
			"final_video": str(video) if video else None,
			"subtitles_srt": str(srt) if srt else None,
			"subtitles_ass": str(ass) if ass else None,
		},
		"video_probe": video_info,
		"checks": [result.__dict__ for result in results],
	}
	_write_json(project_dir / "production_manifest.json", manifest)

	report = [
		"# 中文播客视频 QA 报告",
		"",
		f"状态：{final_status}",
		"",
		"## 输出",
		"",
		f"- 视频标题：{title or '缺失'}",
		f"- 标题文件：`{title_path}`" if title_path else "- 标题文件：缺失",
		f"- 发布信息：`{project_dir / 'publish_info.txt'}`" if (project_dir / "publish_info.txt").exists() else "- 发布信息：缺失",
		f"- B 站投稿元数据：`{project_dir / 'bilibili_upload_metadata.json'}`" if (project_dir / "bilibili_upload_metadata.json").exists() else "- B 站投稿元数据：缺失",
		f"- 文稿：`{script}`" if script else "- 文稿：缺失",
		f"- 封面：`{cover}`" if cover else "- 封面：缺失",
		f"- 视频：`{video}`" if video else "- 视频：缺失",
		f"- SRT：`{srt}`" if srt else "- SRT：缺失",
		f"- ASS：`{ass}`" if ass else "- ASS：缺失",
		"",
		"## 检查",
		"",
	]
	for result in results:
		report.append(f"- {result.status}: {result.message}")
	(project_dir / "qa_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

	print(json.dumps({"status": final_status, "manifest": str(project_dir / "production_manifest.json"), "report": str(project_dir / "qa_report.md")}, ensure_ascii=False, indent=2))
	return 0 if final_status == "PASS" else 2


if __name__ == "__main__":
	raise SystemExit(main())
