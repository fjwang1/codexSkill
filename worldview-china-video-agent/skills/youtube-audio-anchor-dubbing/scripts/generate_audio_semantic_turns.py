#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


TIMED_TRANSCRIPT_RE = re.compile(
	r"^\s*\[?(?P<start>\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?)\s*(?:-->|-|–|—|to)\s*"
	r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?)\]?\s*(?P<text>.*)$"
)

ANCHOR_STOPWORDS = {
	"a", "about", "after", "again", "all", "also", "an", "and", "are", "as", "at", "be", "because",
	"but", "by", "can", "could", "do", "does", "for", "from", "have", "he", "her", "his", "how",
	"i", "if", "in", "is", "it", "its", "just", "like", "me", "more", "my", "not", "of", "on",
	"or", "our", "she", "so", "that", "the", "their", "then", "there", "these", "they", "this",
	"to", "was", "we", "what", "when", "where", "which", "who", "why", "will", "with", "you",
	"your",
}


@dataclass(frozen=True)
class AsrWord:
	text: str
	start: float
	end: float
	source_start: float
	source_end: float
	probability: float | None = None


@dataclass(frozen=True)
class TranscriptSegment:
	start: float
	end: float
	text: str


def main() -> int:
	args = parse_args()
	output_dir = args.output_dir.resolve()
	asr_dir = output_dir / "asr"
	asr_dir.mkdir(parents=True, exist_ok=True)

	start_offset = parse_time(args.start)
	end_offset = parse_time(args.end) if args.end else None
	asr_json_path = prepare_asr_json(args, asr_dir)
	payload = json.loads(asr_json_path.read_text(encoding="utf-8"))
	words = extract_asr_words(payload, start_offset=start_offset, allow_segment_timestamps=args.allow_segment_timestamps)
	if not words:
		raise RuntimeError("ASR JSON did not contain usable word timestamps.")

	normalized_words_path = asr_dir / "asr_words.json"
	write_json(normalized_words_path, [word_to_json(word) for word in words])

	transcript_segments = parse_transcript(args.source_transcript, start_offset=start_offset)
	turns = build_candidate_turns(
		words,
		min_turn_sec=args.min_turn_sec,
		max_turn_sec=args.max_turn_sec,
		hard_max_turn_sec=args.hard_max_turn_sec,
		pause_threshold_sec=args.pause_threshold_sec,
	)
	anchors = build_anchor_candidates(words, max_anchors=args.max_anchors)
	subtitle_diffs = build_subtitle_diffs(anchors, transcript_segments)
	candidates_path = output_dir / "audio-semantic-turns.candidates.json"
	candidates_payload = {
		"schema_version": "audio-semantic-turns-candidates.v1",
		"video_id": args.video_id,
		"chapter_start": format_timestamp(start_offset),
		"chapter_end": format_timestamp(end_offset) if end_offset is not None else None,
		"source_video_path": str(args.source_video) if args.source_video else None,
		"source_audio_path": str(args.source_audio) if args.source_audio else None,
		"source_transcript_path": str(args.source_transcript) if args.source_transcript else None,
		"asr_json_path": str(asr_json_path),
		"normalized_words_path": str(normalized_words_path),
		"turns": turns,
		"anchors": anchors,
		"subtitle_diffs": subtitle_diffs,
	}
	write_json(candidates_path, candidates_payload)

	md_path = output_dir / args.output_name
	md_path.write_text(
		build_markdown(
			args=args,
			start_offset=start_offset,
			end_offset=end_offset,
			words=words,
			turns=turns,
			anchors=anchors,
			subtitle_diffs=subtitle_diffs,
			asr_json_path=asr_json_path,
			normalized_words_path=normalized_words_path,
			candidates_path=candidates_path,
		),
		encoding="utf-8",
	)
	print(json.dumps({"ok": True, "audio_semantic_turns": str(md_path), "candidates": str(candidates_path)}, ensure_ascii=False, indent=2))
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate an audio-semantic-turns.md draft from original audio ASR word timestamps.")
	parser.add_argument("--video-id", required=True)
	parser.add_argument("--source-video", type=Path)
	parser.add_argument("--source-audio", type=Path)
	parser.add_argument("--source-transcript", type=Path)
	parser.add_argument("--asr-json", type=Path)
	parser.add_argument("--output-dir", required=True, type=Path)
	parser.add_argument("--output-name", default="audio-semantic-turns.md")
	parser.add_argument("--start", default="00:00:00")
	parser.add_argument("--end")
	parser.add_argument("--asr-model", default="mlx-community/whisper-large-v3-turbo")
	parser.add_argument("--allow-segment-timestamps", action="store_true")
	parser.add_argument("--pause-threshold-sec", type=float, default=0.45)
	parser.add_argument("--min-turn-sec", type=float, default=2.0)
	parser.add_argument("--max-turn-sec", type=float, default=12.0)
	parser.add_argument("--hard-max-turn-sec", type=float, default=20.0)
	parser.add_argument("--max-anchors", type=int, default=120)
	parser.add_argument("--force", action="store_true")
	return parser.parse_args()


def prepare_asr_json(args: argparse.Namespace, asr_dir: Path) -> Path:
	if args.asr_json:
		require_file(args.asr_json)
		target = asr_dir / "raw_asr.json"
		if args.force or not target.exists():
			shutil.copyfile(args.asr_json, target)
		return target

	source_media = args.source_audio or args.source_video
	if source_media is None:
		raise RuntimeError("Either --asr-json or --source-audio/--source-video is required.")
	require_file(source_media)
	require_tool("ffmpeg")
	require_tool("uvx")

	audio_path = asr_dir / "source_audio.16k.wav"
	if args.force or not audio_path.exists():
		extract_audio(source_media, audio_path, start=args.start, end=args.end, is_video=args.source_video is not None)

	before = set(asr_dir.glob("*.json"))
	run([
		"uvx",
		"--from",
		"mlx-whisper",
		"mlx_whisper",
		str(audio_path),
		"--model",
		args.asr_model,
		"--word-timestamps",
		"True",
		"--output-format",
		"json",
		"--output-dir",
		str(asr_dir),
	])
	after = set(asr_dir.glob("*.json"))
	new_jsons = sorted(after - before, key=lambda path: path.stat().st_mtime, reverse=True)
	if not new_jsons:
		new_jsons = sorted(asr_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
	if not new_jsons:
		raise RuntimeError("ASR command completed but no JSON output was found.")
	target = asr_dir / "raw_asr.json"
	if args.force or not target.exists():
		shutil.copyfile(new_jsons[0], target)
	return target


def extract_audio(source_media: Path, audio_path: Path, *, start: str, end: str | None, is_video: bool) -> None:
	cmd = ["ffmpeg", "-y", "-v", "error", "-ss", start]
	if end:
		cmd.extend(["-to", end])
	cmd.extend(["-i", str(source_media)])
	if is_video:
		cmd.append("-vn")
	cmd.extend(["-ar", "16000", "-ac", "1", str(audio_path)])
	run(cmd)


def extract_asr_words(payload: Any, *, start_offset: float, allow_segment_timestamps: bool) -> list[AsrWord]:
	entries: list[dict[str, Any]] = []
	if isinstance(payload, dict):
		segments = payload.get("segments")
		if isinstance(segments, list):
			for segment in segments:
				if not isinstance(segment, dict):
					continue
				segment_words = segment.get("words")
				if isinstance(segment_words, list) and segment_words:
					for item in segment_words:
						if isinstance(item, dict):
							entries.append(item)
				elif allow_segment_timestamps:
					entries.append({
						"word": str(segment.get("text") or "").strip(),
						"start": segment.get("start"),
						"end": segment.get("end"),
						"probability": segment.get("avg_logprob"),
					})
		if not entries and isinstance(payload.get("words"), list):
			entries = [item for item in payload["words"] if isinstance(item, dict)]
	elif isinstance(payload, list):
		entries = [item for item in payload if isinstance(item, dict)]

	words: list[AsrWord] = []
	for entry in entries:
		word = parse_word_entry(entry, start_offset=start_offset)
		if word is not None:
			words.append(word)
	words.sort(key=lambda item: (item.source_start, item.source_end))
	return words


def parse_word_entry(entry: dict[str, Any], *, start_offset: float) -> AsrWord | None:
	text = str(entry.get("word") or entry.get("text") or "").strip()
	start = entry.get("start")
	end = entry.get("end")
	if start is None or end is None:
		timestamp = entry.get("timestamp") or entry.get("timestamps")
		if isinstance(timestamp, list | tuple) and len(timestamp) >= 2:
			start, end = timestamp[0], timestamp[1]
	if not text or start is None or end is None:
		return None
	start_sec = float(start)
	end_sec = float(end)
	if end_sec <= start_sec:
		return None
	probability_raw = entry.get("probability")
	probability = float(probability_raw) if isinstance(probability_raw, int | float) else None
	return AsrWord(
		text=text,
		start=start_sec,
		end=end_sec,
		source_start=start_sec + start_offset,
		source_end=end_sec + start_offset,
		probability=probability,
	)


def build_candidate_turns(
	words: list[AsrWord],
	*,
	min_turn_sec: float,
	max_turn_sec: float,
	hard_max_turn_sec: float,
	pause_threshold_sec: float,
) -> list[dict[str, Any]]:
	assert words
	turns: list[dict[str, Any]] = []
	start_index = 0
	for index, word in enumerate(words):
		next_word = words[index + 1] if index + 1 < len(words) else None
		duration = word.source_end - words[start_index].source_start
		gap = (next_word.source_start - word.source_end) if next_word else 0.0
		reasons = break_reasons(word, duration=duration, gap=gap, pause_threshold_sec=pause_threshold_sec, max_turn_sec=max_turn_sec, hard_max_turn_sec=hard_max_turn_sec)
		strong_pause = gap >= max(0.8, pause_threshold_sec * 2)
		if next_word is not None and duration < min_turn_sec and not strong_pause and "hard_max_duration" not in reasons:
			continue
		if next_word is None or reasons:
			chunk = words[start_index:index + 1]
			turns.append(build_turn(len(turns) + 1, chunk, reasons or ["end_of_range"]))
			start_index = index + 1
	return turns


def break_reasons(
	word: AsrWord,
	*,
	duration: float,
	gap: float,
	pause_threshold_sec: float,
	max_turn_sec: float,
	hard_max_turn_sec: float,
) -> list[str]:
	reasons: list[str] = []
	if gap >= pause_threshold_sec:
		reasons.append(f"pause_{gap:.2f}s")
	if ends_sentence(word.text) and duration >= 2.0:
		reasons.append("sentence_punctuation")
	if duration >= max_turn_sec and (gap >= 0.2 or ends_soft_boundary(word.text)):
		reasons.append("max_turn_duration")
	if duration >= hard_max_turn_sec:
		reasons.append("hard_max_duration")
	return reasons


def build_turn(index: int, words: list[AsrWord], reasons: list[str]) -> dict[str, Any]:
	text = normalize_asr_text(" ".join(word.text for word in words))
	start = words[0].source_start
	end = words[-1].source_end
	anchors = [anchor for anchor in (detect_anchor(word, local_index=i) for i, word in enumerate(words)) if anchor is not None]
	return {
		"turn_id": f"turn_{index:03d}",
		"start": format_timestamp(start),
		"end": format_timestamp(end),
		"start_sec": round(start, 3),
		"end_sec": round(end, 3),
		"duration_sec": round(end - start, 3),
		"break_reasons": reasons,
		"asr_text": text,
		"candidate_anchor_words": anchors[:8],
		"llm_revision_status": "needs_review",
	}


def build_anchor_candidates(words: list[AsrWord], *, max_anchors: int) -> list[dict[str, Any]]:
	anchors: list[dict[str, Any]] = []
	for index, word in enumerate(words):
		anchor = detect_anchor(word, local_index=index)
		if anchor is None:
			continue
		context_words = words[max(0, index - 5):min(len(words), index + 6)]
		anchor["context"] = normalize_asr_text(" ".join(item.text for item in context_words))
		anchors.append(anchor)
		if len(anchors) >= max_anchors:
			break
	return anchors


def detect_anchor(word: AsrWord, *, local_index: int) -> dict[str, Any] | None:
	clean = clean_anchor_token(word.text)
	if not clean:
		return None
	anchor_types: list[str] = []
	if any(char.isdigit() for char in clean):
		anchor_types.append("number")
	if re.fullmatch(r"[A-Z]{2,}[A-Za-z0-9]*", clean) or re.fullmatch(r"[A-Z]{2,}s", clean):
		anchor_types.append("acronym_or_brand")
	if re.search(r"[$€£¥%]", clean):
		anchor_types.append("money_or_percent")
	if clean[:1].isupper() and clean.lower() not in ANCHOR_STOPWORDS and len(clean) >= 3:
		anchor_types.append("proper_noun_candidate")
	if not anchor_types:
		return None
	return {
		"word": clean,
		"start": format_timestamp(word.source_start),
		"end": format_timestamp(word.source_end),
		"start_sec": round(word.source_start, 3),
		"end_sec": round(word.source_end, 3),
		"types": sorted(set(anchor_types)),
		"local_word_index": local_index,
		"sync_constraint": f"中文对应词不得早于 {format_timestamp(word.source_start)}。",
	}


def build_subtitle_diffs(anchors: list[dict[str, Any]], transcript_segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
	if not transcript_segments:
		return []
	diffs: list[dict[str, Any]] = []
	for anchor in anchors[:80]:
		token = str(anchor["word"])
		match = find_best_transcript_match(token, float(anchor["start_sec"]), transcript_segments)
		if match is None:
			continue
		diff = match.start - float(anchor["start_sec"])
		diffs.append({
			"anchor_word": token,
			"asr_word_start": anchor["start"],
			"transcript_segment_start": format_timestamp(match.start),
			"diff_sec": round(diff, 3),
			"transcript_text": match.text[:180],
			"interpretation": "字幕段时间不能当作该词真实发音时间" if abs(diff) >= 0.8 else "差异较小，仍以 ASR 词级时间为准",
		})
	return diffs


def find_best_transcript_match(token: str, anchor_start: float, segments: list[TranscriptSegment]) -> TranscriptSegment | None:
	needle = normalize_for_search(token)
	matches = [segment for segment in segments if needle and needle in normalize_for_search(segment.text)]
	if not matches:
		return None
	return min(matches, key=lambda segment: abs(segment.start - anchor_start))


def parse_transcript(path: Path | None, *, start_offset: float) -> list[TranscriptSegment]:
	if path is None:
		return []
	require_file(path)
	segments: list[TranscriptSegment] = []
	for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
		match = TIMED_TRANSCRIPT_RE.match(line)
		if not match:
			continue
		start = parse_time(match.group("start"))
		end = parse_time(match.group("end"))
		text = match.group("text").strip()
		segments.append(TranscriptSegment(start=start, end=end, text=text))
	if not segments:
		return []
	if max(segment.start for segment in segments) < start_offset - 10:
		return [TranscriptSegment(start=segment.start + start_offset, end=segment.end + start_offset, text=segment.text) for segment in segments]
	return segments


def build_markdown(
	*,
	args: argparse.Namespace,
	start_offset: float,
	end_offset: float | None,
	words: list[AsrWord],
	turns: list[dict[str, Any]],
	anchors: list[dict[str, Any]],
	subtitle_diffs: list[dict[str, Any]],
	asr_json_path: Path,
	normalized_words_path: Path,
	candidates_path: Path,
) -> str:
	lines: list[str] = [
		"---",
		f"video_id: {args.video_id}",
		f"source_video_path: {args.source_video or ''}",
		f"source_audio_path: {args.source_audio or ''}",
		f"source_transcript_path: {args.source_transcript or ''}",
		f"chapter_start: {format_timestamp(start_offset)}",
		f"chapter_end: {format_timestamp(end_offset) if end_offset is not None else ''}",
		f"generated_at: {datetime.now(timezone.utc).isoformat()}",
		"generator: generate_audio_semantic_turns.py",
		"status: draft_needs_llm_revision",
		f"asr_model: {args.asr_model}",
		"time_authority: original_audio_asr_word_timestamps",
		"text_authority: source_transcript_plus_asr_correction",
		f"raw_asr_json_path: {asr_json_path}",
		f"normalized_words_path: {normalized_words_path}",
		f"candidate_json_path: {candidates_path}",
		"---",
		"",
		"# Audio Semantic Turns",
		"",
		"本文件是脚本生成的锚点草稿。LLM 必须基于原声 ASR 词级时间、外文字幕/转写文本和上下文进行修订后，才能把它作为正式配音锚点使用。",
		"",
		"## ASR 摘要",
		"",
		f"- 词级时间数量：`{len(words)}`",
		f"- 原声时间范围：`{format_timestamp(words[0].source_start)}` - `{format_timestamp(words[-1].source_end)}`",
		f"- 候选语义节点数量：`{len(turns)}`",
		f"- 高辨识度锚点候选数量：`{len(anchors)}`",
		"- 时间权威：原声音频 ASR word timestamps。",
		"- 文本权威：字幕、描述、上下文和 LLM 校正后的原文；ASR 错词不能直接照抄。",
		"",
		"## 候选语义节点",
		"",
		"| 节点 | 时间 | 时长 | 断点原因 | ASR 文本草稿 |",
		"| --- | --- | ---: | --- | --- |",
	]
	for turn in turns:
		lines.append(
			f"| `{turn['turn_id']}` | `{turn['start']}` - `{turn['end']}` | `{turn['duration_sec']}` | "
			f"{', '.join(turn['break_reasons'])} | {escape_md(str(turn['asr_text'])[:260])} |"
		)
	lines.extend([
		"",
		"## 高辨识度锚点候选",
		"",
		"这些词适合用于检查中文配音是否提前或滞后。LLM 需要删除误报，并补充脚本漏掉但画面/语义关键的锚点。",
		"",
		"| 词 | 原声词级时间 | 类型 | 上下文 | 对中文配音的约束 |",
		"| --- | --- | --- | --- | --- |",
	])
	for anchor in anchors:
		lines.append(
			f"| {escape_md(anchor['word'])} | `{anchor['start']}` - `{anchor['end']}` | "
			f"{', '.join(anchor['types'])} | {escape_md(anchor.get('context', '')[:180])} | {escape_md(anchor['sync_constraint'])} |"
		)
	lines.extend([
		"",
		"## 字幕时间与原声词级时间差异",
		"",
	])
	if subtitle_diffs:
		lines.extend(["| 词 | ASR 词级起点 | 字幕段起点 | 差异秒 | 说明 |", "| --- | ---: | ---: | ---: | --- |"])
		for diff in subtitle_diffs[:60]:
			lines.append(
				f"| {escape_md(diff['anchor_word'])} | `{diff['asr_word_start']}` | `{diff['transcript_segment_start']}` | "
				f"`{diff['diff_sec']}` | {escape_md(diff['interpretation'])} |"
			)
	else:
		lines.append("未提供可解析时间轴字幕，或未发现可匹配差异。")
	lines.extend([
		"",
		"## LLM 修订要求",
		"",
		"- 合并脚本误切的碎片，拆开脚本漏切的语义转折。",
		"- 保留品牌名、人物名、国家名、数字、图表标题、观点转折的真实词级时间。",
		"- 对 ASR 错词做文本校正，但不得移动它的时间锚点。",
		"- 明确写出哪些锚点是 `must_align`，并把对应约束传递到 `voiceover-segments.json`。",
		"- 如果字幕段起点和 ASR 词级时间冲突，以 ASR 词级时间为准。",
		"- 修订完成后，把 `status` 改为 `llm_revised`，并在 QA 中说明修订依据。",
		"",
	])
	return "\n".join(lines)


def parse_time(value: str) -> float:
	value = value.strip().replace(",", ".")
	parts = value.split(":")
	if len(parts) == 3:
		hours, minutes, seconds = parts
		return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
	if len(parts) == 2:
		minutes, seconds = parts
		return int(minutes) * 60 + float(seconds)
	return float(value)


def format_timestamp(value: float | None) -> str:
	if value is None:
		return ""
	total_millis = max(0, int(round(value * 1000)))
	hours, remainder = divmod(total_millis, 3_600_000)
	minutes, remainder = divmod(remainder, 60_000)
	seconds, millis = divmod(remainder, 1000)
	return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def normalize_asr_text(value: str) -> str:
	return re.sub(r"\s+", " ", value).strip()


def clean_anchor_token(value: str) -> str:
	return value.strip().strip("\"'“”‘’()[]{}.,!?;:，。！？；：")


def normalize_for_search(value: str) -> str:
	return re.sub(r"[^0-9a-zA-Z]+", "", value).lower()


def ends_sentence(value: str) -> bool:
	return clean_anchor_token(value) != value.strip() or value.strip().endswith((".", "?", "!", "。", "？", "！"))


def ends_soft_boundary(value: str) -> bool:
	return value.strip().endswith((".", "?", "!", ",", ";", ":", "。", "？", "！", "，", "；", "："))


def word_to_json(word: AsrWord) -> dict[str, Any]:
	return {
		"text": word.text,
		"start": round(word.start, 3),
		"end": round(word.end, 3),
		"source_start": round(word.source_start, 3),
		"source_end": round(word.source_end, 3),
		"probability": word.probability,
	}


def write_json(path: Path, payload: Any) -> None:
	path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def escape_md(value: str) -> str:
	return value.replace("|", "\\|").replace("\n", " ")


def require_file(path: Path) -> None:
	if not path.exists():
		raise FileNotFoundError(path)


def require_tool(name: str) -> None:
	if shutil.which(name) is None:
		raise RuntimeError(f"Missing required tool: {name}")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	result = subprocess.run(cmd, text=True, capture_output=True)
	if result.returncode != 0:
		raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
	return result


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except Exception as exc:
		print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
		raise
