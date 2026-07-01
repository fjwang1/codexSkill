#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
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


def _parse_clock(value: str) -> float:
	parts = value.strip().split(":")
	if len(parts) == 2:
		minutes, seconds = parts
		return int(minutes) * 60 + float(seconds)
	if len(parts) == 3:
		hours, minutes, seconds = parts
		return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
	raise ValueError(f"Unsupported timecode: {value!r}")


def _parse_range(value: str) -> tuple[float, float]:
	clean = value.strip().replace("–", "-").replace("—", "-")
	left, right = [part.strip() for part in clean.split("-", 1)]
	return _parse_clock(left), _parse_clock(right)


def _split_md_row(line: str) -> list[str]:
	return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_storyboard(path: Path) -> list[dict[str, str]]:
	lines = path.read_text(encoding="utf-8").splitlines()
	header_index = None
	for index, line in enumerate(lines):
		cells = _split_md_row(line)
		if len(cells) >= 7 and cells[0] == "Beat" and cells[1].startswith("真实时间"):
			header_index = index
			break
	if header_index is None:
		raise ValueError(f"Cannot find storyboard table in {path}")

	rows: list[dict[str, str]] = []
	for line in lines[header_index + 2:]:
		if not line.strip().startswith("|"):
			break
		cells = _split_md_row(line)
		if len(cells) < 7:
			continue
		rows.append({
			"beat": cells[0],
			"time_range": cells[1],
			"turns": cells[2],
			"voiceover": cells[3],
			"original_strategy": cells[4],
			"visual_description": cells[5],
			"production_spec": cells[6],
		})
	assert rows, f"No storyboard rows parsed from {path}"
	return rows


def _turns_to_rows(timeline: dict[str, Any], max_shots: int = 16) -> list[dict[str, str]]:
	turns = timeline.get("turns") or []
	assert turns, "dialogue_timeline.json contains no turns"
	chunk_size = max(1, round(len(turns) / max_shots))
	rows: list[dict[str, str]] = []
	for chunk_index, offset in enumerate(range(0, len(turns), chunk_size), start=1):
		chunk = turns[offset:offset + chunk_size]
		start = float(chunk[0]["start_sec"])
		end = float(chunk[-1]["end_sec"])
		text = " ".join(str(item.get("text", "")).strip() for item in chunk)
		rows.append({
			"beat": f"B{chunk_index:02d}",
			"time_range": f"{start:.2f}-{end:.2f}",
			"turns": f"T{chunk[0]['turn_index']}-T{chunk[-1]['turn_index']}",
			"voiceover": text[:90],
			"original_strategy": "ai_generated_editorial_visual",
			"visual_description": text[:120],
			"production_spec": "AI-generated editorial explainer visual; no logos; no source names",
		})
	return rows


def _slug_text(value: str) -> str:
	return re.sub(r"\s+", " ", value.replace("`", "").strip())


def _overlay_for(beat: str, voiceover: str, description: str, spec: str) -> dict[str, Any]:
	known: dict[str, dict[str, Any]] = {
		"B01": {"title": "世界最快超算，来自中国", "items": []},
		"B02": {"title": "不靠 GPU 的反常路线", "items": ["CPU-only", "本土系统工程"]},
		"B04": {"title": "LineShine", "items": ["深圳", "TOP500 No.1", "2026-06"]},
		"B05": {"title": "TOP500 时间线", "items": ["1993", "2024", "2026-06"]},
		"B06": {"title": "2.198 Exaflop/s", "items": ["约 219.8 亿亿次/秒", "42.2 MW"]},
		"B07": {"title": "GPU 路线 vs CPU-only 路线", "items": ["并行计算 / AI", "互联 / 调度 / 系统"]},
		"B09": {"title": "国产技术栈", "items": ["LX2 处理器", "灵启网络", "麒麟 OS", "应用负载"]},
		"B10": {"title": "系统组织能力", "items": ["芯片", "网络", "OS", "软件", "能源", "应用"]},
		"B11": {"title": "限制如何改变路线", "items": ["供应链不确定性", "自主架构", "工程集成"]},
		"B12": {"title": "更难、更贵，但更可控", "items": ["生态短板", "资源流向", "长期投入"]},
		"B13": {"title": "性能 / 能效 / 成本", "items": ["HPL ≠ 全部工作负载"]},
		"B15": {"title": "从榜单性能到真实生产力", "items": ["软件生态", "应用迁移", "可靠性"]},
		"B16": {"title": "中国算力生态", "items": ["芯片", "软件", "网络", "能源", "散热", "应用"]},
		"B17": {"title": "竞争的终点，是一套系统", "items": []},
	}
	if beat in known:
		return known[beat]
	if "数字" in description or "Exaflop" in spec:
		return {"title": voiceover[:24], "items": []}
	return {"title": "", "items": []}


def _visual_family(strategy: str, description: str, spec: str) -> str:
	joined = f"{strategy} {description} {spec}".lower()
	if any(marker in joined for marker in ["diagram", "flow", "timeline", "card", "chart", "funnel", "stack", "comparison", "数据", "流程", "对比", "时间线", "漏斗", "层级"]):
		return "ai_editorial_infographic"
	return "ai_cinematic_documentary_frame"


def _prompt(topic: str, shot: dict[str, Any]) -> str:
	overlay = shot["overlay_text"]
	text_note = "The base image should contain no readable text; leave clean panels where exact labels can be overlaid later."
	if overlay.get("title") or overlay.get("items"):
		text_note = (
			"Create blank visual panels or clean negative space for later exact text overlays. "
			"Do not render any readable words, letters, numbers, brand marks, or fake UI text inside the image."
		)

	return "\n".join([
		"Use case: productivity-visual",
		"Asset type: 16:9 AI-generated key visual for a Chinese single-host editorial explainer video",
		f"Primary request: Create shot {shot['beat']} for a video about {topic}.",
		f"Narrative beat: {shot['voiceover']}",
		f"Scene/visual idea: {shot['visual_description']}",
		f"Production spec: {shot['production_spec']}",
		"Style/medium: cinematic editorial technology documentary, realistic texture mixed with refined data-visualization composition, high-end public-affairs explainer, not a PowerPoint slide",
		"Composition/framing: horizontal 16:9 frame, clear subject, strong depth, stable news-documentary composition, lower 18 percent kept dark and uncluttered for burned subtitles",
		"Lighting/mood: sober, precise, intelligent, modern engineering atmosphere; natural contrast, no sensational sci-fi glow",
		"Color palette: graphite black, steel gray, clean white, restrained cyan and amber accents; avoid purple-blue gradients and one-note dark-blue palette",
		f"Text handling: {text_note}",
		"Constraints: AI-generated only; no stock-photo look, no visible logo, no watermark, no newspaper/magazine masthead, no source publication name, no URL, no fake brand UI, no recognizable close-up faces",
		"Avoid: illegible text, random letters, company logos, national flags as the main subject, exaggerated cyberpunk, decorative gradient blobs, cramped infographic labels, important content in the subtitle safe area",
		"Target size: 3840x2160 pixels, landscape 16:9",
	])


def build_manifest(project_dir: Path, storyboard_md: Path | None, dialogue_timeline: Path, topic: str, out_dir: Path) -> dict[str, Any]:
	timeline = _read_json(dialogue_timeline)
	audio_duration = float(timeline.get("duration_sec") or timeline.get("audio", {}).get("duration_sec") or 0)
	assert audio_duration > 0, "dialogue_timeline.json must include duration_sec"
	rows = _parse_storyboard(storyboard_md) if storyboard_md else _turns_to_rows(timeline)
	raw_shots: list[dict[str, Any]] = []
	for row in rows:
		if re.match(r"^\d+(\.\d+)?-\d+(\.\d+)?$", row["time_range"]):
			start_text, end_text = row["time_range"].split("-", 1)
			speech_start, speech_end = float(start_text), float(end_text)
		else:
			speech_start, speech_end = _parse_range(row["time_range"])
		beat = row["beat"].strip()
		voiceover = _slug_text(row["voiceover"])
		description = _slug_text(row["visual_description"])
		spec = _slug_text(row["production_spec"])
		raw_shots.append({
			"beat": beat,
			"speech_start_sec": round(speech_start, 3),
			"speech_end_sec": round(speech_end, 3),
			"turns": row["turns"],
			"voiceover": voiceover,
			"original_strategy": row["original_strategy"],
			"visual_family": _visual_family(row["original_strategy"], description, spec),
			"visual_description": description,
			"production_spec": spec,
			"overlay_text": _overlay_for(beat, voiceover, description, spec),
			"safe_area": {"subtitle_bottom_fraction": 0.18, "keep_uncluttered": True},
			"target_image": f"generated/shot_{beat}.png",
		})
	raw_shots.sort(key=lambda item: item["speech_start_sec"])
	for index, shot in enumerate(raw_shots):
		visual_start = 0.0 if index == 0 else raw_shots[index]["speech_start_sec"]
		visual_end = audio_duration if index == len(raw_shots) - 1 else raw_shots[index + 1]["speech_start_sec"]
		if index > 0:
			visual_start = raw_shots[index - 1]["visual_end_sec"]
		assert visual_end > visual_start, f"Invalid visual interval for {shot['beat']}: {visual_start}..{visual_end}"
		shot["shot_index"] = index + 1
		shot["visual_start_sec"] = round(visual_start, 3)
		shot["visual_end_sec"] = round(visual_end, 3)
		shot["duration_sec"] = round(visual_end - visual_start, 3)
		shot["prompt"] = _prompt(topic, shot)

	manifest = {
		"schema_version": "article_ai_video_visuals.v1",
		"created_at": datetime.now(timezone.utc).isoformat(),
		"project_dir": str(project_dir),
		"topic": topic,
		"storyboard_md": str(storyboard_md) if storyboard_md else None,
		"storyboard_sha256": _sha256(storyboard_md) if storyboard_md else None,
		"dialogue_timeline": str(dialogue_timeline),
		"dialogue_timeline_sha256": _sha256(dialogue_timeline),
		"audio_duration_sec": round(audio_duration, 3),
		"target_dimensions": {"width": 3840, "height": 2160, "aspect_ratio": "16:9"},
		"style": {
			"name": "Chinese editorial tech documentary",
			"palette": "graphite, steel gray, clean white, restrained cyan and amber",
			"no_stock_footage": True,
			"exact_text_rendered_in_post": True,
		},
		"shots": raw_shots,
	}
	_write_json(out_dir / "visual_manifest.json", manifest)
	_write_json(out_dir / "image_prompts.json", {
		"schema_version": "article_ai_video_visuals.prompts.v1",
		"target_dir": str(out_dir / "generated"),
		"shots": [
			{
				"beat": shot["beat"],
				"target_image": shot["target_image"],
				"prompt": shot["prompt"],
			}
			for shot in raw_shots
		],
	})
	return manifest


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--project-dir", required=True, type=Path)
	parser.add_argument("--storyboard-md", type=Path)
	parser.add_argument("--dialogue-timeline", required=True, type=Path)
	parser.add_argument("--topic", required=True)
	parser.add_argument("--out-dir", required=True, type=Path)
	args = parser.parse_args()
	manifest = build_manifest(args.project_dir, args.storyboard_md, args.dialogue_timeline, args.topic, args.out_dir)
	print(json.dumps({
		"status": "ok",
		"shots": len(manifest["shots"]),
		"visual_manifest": str(args.out_dir / "visual_manifest.json"),
		"image_prompts": str(args.out_dir / "image_prompts.json"),
	}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
