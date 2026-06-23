#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = SKILL_DIR / "assets" / "linyao-chenche-voicedesign.json"
DEFAULT_IMAGE_PYTHON = Path("/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SUBTITLE_FONT_PATH = Path("/Volumes/GT34/Downloads/fonts/zaozigongfang-dianhei/zaozigongfangdianheitichangguiti.ttf")
SUBTITLE_FONT_FAMILY = "MFDianHeiNoncommercial"
SUBTITLE_FONT_FULL_NAME = "造字工房典黑体（非商用）常规体"


@dataclass(frozen=True)
class Turn:
	index: int
	role: str
	text: str


@dataclass(frozen=True)
class Chunk:
	turn_index: int
	chunk_index: int
	role: str
	text: str
	path: Path


@dataclass(frozen=True)
class SubtitleCue:
	index: int
	start: float
	end: float
	role: str
	text: str


@dataclass(frozen=True)
class SubtitleOverlaySet:
	paths: list[Path]
	blank_path: Path
	width: int
	height: int
	x: int
	y: int


@dataclass(frozen=True)
class VisualSegment:
	path: Path
	start: float
	end: float
	label: str


def _log(message: str) -> None:
	print(message, flush=True)


def _log_path(path: Path) -> str:
	return str(path.expanduser().resolve())


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
	return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _hash_text(value: str, length: int = 10) -> str:
	return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _file_sha256(path: Path) -> str:
	h = hashlib.sha256()
	with path.open("rb") as f:
		for block in iter(lambda: f.read(1024 * 1024), b""):
			h.update(block)
	return h.hexdigest()


def _safe_name(value: str) -> str:
	return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value).strip("_") or "role"


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ffprobe_duration(path: Path) -> float:
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


def _ffprobe_video_size(path: Path) -> tuple[int, int]:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-select_streams",
		"v:0",
		"-show_entries",
		"stream=width,height",
		"-of",
		"csv=s=x:p=0",
		str(path),
	])
	width, height = result.stdout.strip().split("x")
	return int(width), int(height)


def _ffprobe_stream_count(path: Path, codec_type: str) -> int:
	result = _run([
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"stream=codec_type",
		"-of",
		"json",
		str(path),
	])
	data = json.loads(result.stdout)
	return sum(1 for stream in data.get("streams", []) if stream.get("codec_type") == codec_type)


def _assert_tooling() -> None:
	for binary in ("ffmpeg", "ffprobe"):
		if shutil.which(binary) is None:
			raise RuntimeError(f"Missing required binary: {binary}")


def _find_script(input_dir: Path) -> Path:
	candidates = [p for p in input_dir.rglob("*.md") if p.is_file()]
	if not candidates:
		raise FileNotFoundError(f"No markdown script found in {input_dir}")
	patterns = ("podcast", "script", "播客", "文稿")
	def score(path: Path) -> tuple[int, int, str]:
		name = path.name.lower()
		return (sum(1 for pattern in patterns if pattern in name), -len(path.parts), str(path))
	return sorted(candidates, key=score, reverse=True)[0]


def _find_cover(input_dir: Path) -> Path:
	candidates = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
	if not candidates:
		raise FileNotFoundError(f"No cover image found in {input_dir}")
	preferred = [p for p in candidates if "cover" in p.name.lower() or "封面" in p.name]
	if preferred:
		return sorted(preferred, key=lambda p: ("4k" in p.name.lower(), p.stat().st_size), reverse=True)[0]
	return sorted(candidates, key=lambda p: p.stat().st_size, reverse=True)[0]


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
	if args.input_dir:
		input_dir = Path(args.input_dir).expanduser().resolve()
		if not input_dir.exists():
			raise FileNotFoundError(f"Input directory not found: {input_dir}")
		script = Path(args.script).expanduser().resolve() if args.script else _find_script(input_dir)
		cover = Path(args.cover).expanduser().resolve() if args.cover else _find_cover(input_dir)
	else:
		if not args.script or not args.cover:
			raise ValueError("Pass either --input-dir or both --script and --cover")
		script = Path(args.script).expanduser().resolve()
		cover = Path(args.cover).expanduser().resolve()
	if not script.exists():
		raise FileNotFoundError(f"Script not found: {script}")
	if not cover.exists():
		raise FileNotFoundError(f"Cover image not found: {cover}")
	return script, cover


def _parse_turns(script_path: Path, roles: set[str]) -> list[Turn]:
	turns: list[Turn] = []
	current_role: str | None = None
	current_text: list[str] = []
	in_frontmatter = False
	frontmatter_seen = False
	in_code = False

	def flush() -> None:
		nonlocal current_role, current_text
		if current_role and current_text:
			text = re.sub(r"\s+", " ", " ".join(current_text)).strip()
			if text:
				turns.append(Turn(index=len(turns) + 1, role=current_role, text=text))
		current_role = None
		current_text = []

	for raw_line in script_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line:
			flush()
			continue
		if line == "---" and not frontmatter_seen:
			in_frontmatter = not in_frontmatter
			if not in_frontmatter:
				frontmatter_seen = True
			continue
		if in_frontmatter:
			continue
		if line.startswith("```"):
			in_code = not in_code
			flush()
			continue
		if in_code:
			continue
		match = re.match(r"^([^：:]{1,20})[：:]\s*(.+)$", line)
		if match and match.group(1).strip() in roles:
			flush()
			current_role = match.group(1).strip()
			current_text = [match.group(2).strip()]
			continue
		if current_role and not line.startswith("#") and not line.startswith("- "):
			current_text.append(line)
		else:
			flush()
	flush()
	return turns


def _split_text(text: str, max_chars: int) -> list[str]:
	text = re.sub(r"\s+", " ", text).strip()
	if len(text) <= max_chars:
		return [text]
	parts = re.split(r"([。！？!?；;])", text)
	sentences: list[str] = []
	for i in range(0, len(parts), 2):
		sentence = parts[i].strip()
		if not sentence:
			continue
		if i + 1 < len(parts):
			sentence += parts[i + 1]
		sentences.append(sentence)
	chunks: list[str] = []
	current = ""
	for sentence in sentences or [text]:
		if len(sentence) > max_chars:
			if current:
				chunks.append(current)
				current = ""
			for start in range(0, len(sentence), max_chars):
				chunks.append(sentence[start:start + max_chars])
			continue
		if current and len(current) + len(sentence) > max_chars:
			chunks.append(current)
			current = sentence
		else:
			current = current + sentence if current else sentence
	if current:
		chunks.append(current)
	return chunks


def _split_subtitle_text(text: str, max_chars: int = 48) -> list[str]:
	text = re.sub(r"\s+", " ", text).strip()
	if len(text) <= max_chars:
		return [text]
	parts = re.split(r"([。！？!?；;，,])", text)
	phrases: list[str] = []
	for i in range(0, len(parts), 2):
		phrase = parts[i].strip()
		if not phrase:
			continue
		if i + 1 < len(parts):
			phrase += parts[i + 1]
		phrases.append(phrase)
	cues: list[str] = []
	current = ""
	for phrase in phrases or [text]:
		if len(phrase) > max_chars:
			if current:
				cues.append(current)
				current = ""
			for start in range(0, len(phrase), max_chars):
				cues.append(phrase[start:start + max_chars])
			continue
		if current and len(current) + len(phrase) > max_chars:
			cues.append(current)
			current = phrase
		else:
			current = current + phrase if current else phrase
	if current:
		cues.append(current)
	return cues


def _wrap_subtitle_text(text: str, line_chars: int = 24, newline: str = "\n") -> str:
	text = re.sub(r"\s+", " ", text).strip()
	if len(text) <= line_chars:
		return text
	lines = [text[i:i + line_chars] for i in range(0, len(text), line_chars)]
	return newline.join(lines[:2]) if len(lines) > 2 else newline.join(lines)


def _srt_time(seconds: float) -> str:
	total_ms = max(0, int(round(seconds * 1000)))
	ms = total_ms % 1000
	total_seconds = total_ms // 1000
	sec = total_seconds % 60
	total_minutes = total_seconds // 60
	minute = total_minutes % 60
	hour = total_minutes // 60
	return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
	total_cs = max(0, int(round(seconds * 100)))
	cs = total_cs % 100
	total_seconds = total_cs // 100
	sec = total_seconds % 60
	total_minutes = total_seconds // 60
	minute = total_minutes % 60
	hour = total_minutes // 60
	return f"{hour}:{minute:02d}:{sec:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
	return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def _build_subtitles(chunks: list[Chunk], profile: dict[str, Any], output_dir: Path, speaker_labels: bool) -> tuple[Path, Path, list[SubtitleCue]]:
	silence_turn = float(profile.get("silence_between_turns_sec", 0.35))
	silence_chunk = float(profile.get("silence_between_chunks_sec", 0.12))
	cues: list[SubtitleCue] = []
	cursor = 0.0
	for i, chunk in enumerate(chunks):
		duration = _ffprobe_duration(chunk.path)
		pieces = _split_subtitle_text(chunk.text)
		total_chars = sum(max(1, len(piece)) for piece in pieces)
		chunk_start = cursor
		chunk_end = cursor + duration
		piece_start = chunk_start
		for piece_index, piece in enumerate(pieces):
			if piece_index == len(pieces) - 1:
				piece_end = chunk_end
			else:
				piece_duration = duration * (max(1, len(piece)) / total_chars)
				piece_end = min(chunk_end, piece_start + piece_duration)
			cues.append(SubtitleCue(len(cues) + 1, piece_start, piece_end, chunk.role, piece))
			piece_start = piece_end
		cursor = chunk_end
		next_chunk = chunks[i + 1] if i + 1 < len(chunks) else None
		if next_chunk:
			cursor += silence_chunk if next_chunk.turn_index == chunk.turn_index else silence_turn

	srt_path = output_dir / "final_subtitles.srt"
	with srt_path.open("w", encoding="utf-8") as f:
		for cue in cues:
			f.write(f"{cue.index}\n")
			f.write(f"{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n")
			display_text = f"{cue.role}：{cue.text}" if speaker_labels else cue.text
			f.write(f"{_wrap_subtitle_text(display_text)}\n\n")

	ass_path = output_dir / "final_subtitles.ass"
	ass_lines = [
		"[Script Info]",
		"ScriptType: v4.00+",
		"PlayResX: 3840",
		"PlayResY: 2160",
		"ScaledBorderAndShadow: yes",
		"",
		"[V4+ Styles]",
		"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
		f"Style: Default,{SUBTITLE_FONT_FAMILY},72,&H00FFFFFF,&H0000D4FF,&H00000000,&H99000000,0,0,0,0,100,100,0,0,1,6,2,2,180,180,138,1",
		"",
		"[Events]",
		"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
	]
	for cue in cues:
		display_text = f"{cue.role}：{cue.text}" if speaker_labels else cue.text
		text = _wrap_subtitle_text(display_text, newline="\\N")
		ass_lines.append(f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Default,,0,0,0,,{_ass_escape(text)}")
	ass_path.write_text("\n".join(ass_lines) + "\n", encoding="utf-8")
	return srt_path, ass_path, cues


def _create_silence(path: Path, duration: float, sample_rate: int) -> None:
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		f"anullsrc=r={sample_rate}:cl=mono",
		"-t",
		f"{duration:.3f}",
		"-c:a",
		"pcm_s16le",
		str(path),
	])


def _normalize_wav(src: Path, dst: Path, sample_rate: int) -> None:
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-i",
		str(src),
		"-ac",
		"1",
		"-ar",
		str(sample_rate),
		"-c:a",
		"pcm_s16le",
		str(dst),
	])


def _generate_chunk(
	model: Any,
	text: str,
	instruct: str,
	dst: Path,
	speed: float,
	temperature: float,
	lang_code: str,
	sample_rate: int,
	force: bool,
	verbose_tts: bool,
) -> None:
	if dst.exists() and dst.stat().st_size > 44 and not force:
		return
	from mlx_audio.tts.generate import generate_audio

	dst.parent.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory(prefix="article-podcast-tts-") as tmp_dir:
		tmp_path = Path(tmp_dir)
		if verbose_tts:
			generate_audio(
				model=model,
				text=text,
				instruct=instruct,
				speed=speed,
				temperature=temperature,
				lang_code=lang_code,
				output_path=str(tmp_path),
				verbose=True,
			)
		else:
			with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
				generate_audio(
					model=model,
					text=text,
					instruct=instruct,
					speed=speed,
					temperature=temperature,
					lang_code=lang_code,
					output_path=str(tmp_path),
					verbose=False,
				)
		candidates = sorted(tmp_path.glob("*.wav"))
		if not candidates:
			raise RuntimeError("Qwen generated no wav file")
		_normalize_wav(candidates[0], dst, sample_rate)


def _render_audio(
	turns: list[Turn],
	profile: dict[str, Any],
	output_dir: Path,
	max_chars: int,
	force: bool,
	verbose_tts: bool,
) -> tuple[Path, list[Chunk]]:
	from mlx_audio.tts.utils import load_model

	model_dir = Path(profile["model_dir"]).expanduser().resolve()
	if not model_dir.exists():
		raise FileNotFoundError(f"VoiceDesign model not found: {model_dir}")
	voices = profile["voices"]
	speed = float(profile.get("speed", 0.94))
	temperature = float(profile.get("temperature", 0.7))
	lang_code = str(profile.get("lang_code", "zh"))
	sample_rate = int(profile.get("sample_rate", 24000))
	silence_turn = float(profile.get("silence_between_turns_sec", 0.35))
	silence_chunk = float(profile.get("silence_between_chunks_sec", 0.12))

	draft_dir = output_dir / "draft-turns"
	draft_dir.mkdir(parents=True, exist_ok=True)
	_log(f"LOAD_MODEL {_log_path(model_dir)}")
	model = load_model(str(model_dir))
	_log("MODEL_READY")

	chunks: list[Chunk] = []
	for turn in turns:
		instruct = voices[turn.role]["instruct"]
		for chunk_index, chunk_text in enumerate(_split_text(turn.text, max_chars), start=1):
			key = _hash_text(json.dumps({
				"role": turn.role,
				"text": chunk_text,
				"instruct": instruct,
				"speed": speed,
				"temperature": temperature,
				"lang_code": lang_code,
			}, ensure_ascii=False))
			dst = draft_dir / f"turn_{turn.index:04d}_{chunk_index:02d}_{_safe_name(turn.role)}_{key}.wav"
			_log(f"GENERATE turn={turn.index:04d} chunk={chunk_index:02d} role={turn.role}")
			_generate_chunk(model, chunk_text, instruct, dst, speed, temperature, lang_code, sample_rate, force, verbose_tts)
			chunks.append(Chunk(turn.index, chunk_index, turn.role, chunk_text, dst))

	silence_dir = output_dir / "silence"
	silence_dir.mkdir(parents=True, exist_ok=True)
	silence_turn_path = silence_dir / f"silence_turn_{silence_turn:.2f}s.wav"
	silence_chunk_path = silence_dir / f"silence_chunk_{silence_chunk:.2f}s.wav"
	if force or not silence_turn_path.exists():
		_create_silence(silence_turn_path, silence_turn, sample_rate)
	if force or not silence_chunk_path.exists():
		_create_silence(silence_chunk_path, silence_chunk, sample_rate)

	concat_path = output_dir / "audio_concat.txt"
	with concat_path.open("w", encoding="utf-8") as f:
		for i, chunk in enumerate(chunks):
			f.write(f"file '{chunk.path.as_posix()}'\n")
			next_chunk = chunks[i + 1] if i + 1 < len(chunks) else None
			if next_chunk:
				silence = silence_chunk_path if next_chunk.turn_index == chunk.turn_index else silence_turn_path
				f.write(f"file '{silence.as_posix()}'\n")

	final_audio = output_dir / "final_podcast.wav"
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"concat",
		"-safe",
		"0",
		"-i",
		str(concat_path),
		"-ac",
		"1",
		"-ar",
		str(sample_rate),
		"-c:a",
		"pcm_s16le",
		str(final_audio),
	])
	return final_audio, chunks


def _ffmpeg_filter_path(path: Path) -> str:
	return str(path).replace("\\", "\\\\").replace("'", "\\'")


def _image_python() -> str:
	candidates = [
		Path(sys.executable),
		DEFAULT_IMAGE_PYTHON,
	]
	for candidate in candidates:
		if not candidate.exists():
			continue
		probe = subprocess.run(
			[str(candidate), "-c", "from PIL import Image, ImageDraw, ImageFont"],
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
		)
		if probe.returncode == 0:
			return str(candidate)
	raise RuntimeError("Pillow is required to burn subtitles, but no Python with PIL was found")


def _ffconcat_path(path: Path) -> str:
	return str(path).replace("'", "'\\''")


def _chapter_items(plan_path: Path) -> list[dict[str, Any]]:
	data = json.loads(plan_path.read_text(encoding="utf-8"))
	if isinstance(data, list):
		items = data
	elif isinstance(data, dict):
		items = data.get("chapters") or data.get("chapter_visuals") or []
	else:
		items = []
	if not isinstance(items, list):
		raise ValueError(f"Chapter plan must contain a list of chapters: {plan_path}")
	return [item for item in items if isinstance(item, dict)]


def _resolve_visual_path(item: dict[str, Any], plan_dir: Path, cover: Path) -> Path:
	for key in ("image", "image_path", "visual_path", "chapter_image", "path"):
		value = item.get(key)
		if not value:
			continue
		path = Path(str(value)).expanduser()
		if not path.is_absolute():
			path = plan_dir / path
		path = path.resolve()
		if not path.exists():
			raise FileNotFoundError(f"Chapter visual not found: {path}")
		return path
	return cover


def _turn_start_times(chunks: list[Chunk], profile: dict[str, Any]) -> dict[int, float]:
	silence_turn = float(profile.get("silence_between_turns_sec", 0.35))
	silence_chunk = float(profile.get("silence_between_chunks_sec", 0.12))
	cursor = 0.0
	starts: dict[int, float] = {}
	for i, chunk in enumerate(chunks):
		starts.setdefault(chunk.turn_index, cursor)
		cursor += _ffprobe_duration(chunk.path)
		next_chunk = chunks[i + 1] if i + 1 < len(chunks) else None
		if next_chunk:
			cursor += silence_chunk if next_chunk.turn_index == chunk.turn_index else silence_turn
	return starts


def _build_visual_segments(
	cover: Path,
	chapter_plan: Path | None,
	chunks: list[Chunk],
	profile: dict[str, Any],
	audio_duration: float,
) -> list[VisualSegment]:
	if chapter_plan is None:
		return [VisualSegment(cover, 0.0, audio_duration, "cover")]
	if not chapter_plan.exists():
		raise FileNotFoundError(f"Chapter plan not found: {chapter_plan}")

	turn_starts = _turn_start_times(chunks, profile)
	raw_segments: list[tuple[float, Path, str]] = []
	for item in _chapter_items(chapter_plan):
		start_turn_value = item.get("start_turn", item.get("start_turn_index"))
		if start_turn_value is None:
			raise ValueError(f"Chapter item is missing start_turn: {item}")
		start_turn = int(start_turn_value)
		if start_turn not in turn_starts:
			raise ValueError(f"Chapter start_turn {start_turn} is outside rendered turns")
		label = str(item.get("chapter_title") or item.get("title") or f"chapter-{len(raw_segments) + 1}")
		raw_segments.append((turn_starts[start_turn], _resolve_visual_path(item, chapter_plan.parent, cover), label))

	if not raw_segments:
		return [VisualSegment(cover, 0.0, audio_duration, "cover")]

	raw_segments = sorted(raw_segments, key=lambda item: item[0])
	segments: list[VisualSegment] = []
	if raw_segments[0][0] > 0.05:
		segments.append(VisualSegment(cover, 0.0, raw_segments[0][0], "cover"))
	for idx, (start, path, label) in enumerate(raw_segments):
		end = raw_segments[idx + 1][0] if idx + 1 < len(raw_segments) else audio_duration
		if end <= start:
			continue
		segments.append(VisualSegment(path, start, end, label))
	return segments or [VisualSegment(cover, 0.0, audio_duration, "cover")]


def _write_visual_concat(segments: list[VisualSegment], output_dir: Path) -> Path:
	concat_path = output_dir / "visual_concat.ffconcat"
	with concat_path.open("w", encoding="utf-8") as f:
		f.write("ffconcat version 1.0\n")
		for segment in segments:
			duration = max(0.05, segment.end - segment.start)
			f.write(f"file '{_ffconcat_path(segment.path)}'\n")
			f.write(f"duration {duration:.3f}\n")
		f.write(f"file '{_ffconcat_path(segments[-1].path)}'\n")
	return concat_path


def _render_subtitle_overlay_images(cues: list[SubtitleCue], output_dir: Path, width: int, height: int, force: bool, speaker_labels: bool) -> SubtitleOverlaySet:
	overlay_dir = output_dir / "subtitle-overlays"
	overlay_dir.mkdir(parents=True, exist_ok=True)
	cues_json = overlay_dir / "subtitle_cues.json"
	overlay_width = min(width - 360, 3200)
	overlay_height = 420
	overlay_x = (width - overlay_width) // 2
	overlay_y = height - 120 - overlay_height
	overlay_paths = [overlay_dir / f"cue_{cue.index:04d}.png" for cue in cues]
	blank_path = overlay_dir / "blank.png"
	if (
		blank_path.exists()
		and blank_path.stat().st_size > 0
		and overlay_paths
		and all(path.exists() and path.stat().st_size > 0 for path in overlay_paths)
		and not force
	):
		return SubtitleOverlaySet(overlay_paths, blank_path, overlay_width, overlay_height, overlay_x, overlay_y)
	payload = {
		"width": overlay_width,
		"height": overlay_height,
		"out_dir": str(overlay_dir),
		"subtitle_font_path": str(SUBTITLE_FONT_PATH),
		"subtitle_font_full_name": SUBTITLE_FONT_FULL_NAME,
		"cues": [
			{
				"index": cue.index,
				"role": cue.role,
				"text": cue.text,
				"display_text": f"{cue.role}：{cue.text}" if speaker_labels else cue.text,
			}
			for cue in cues
		],
	}
	_write_json(cues_json, payload)
	code = r'''
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

payload = json.loads(Path(__import__("sys").argv[1]).read_text(encoding="utf-8"))
width = int(payload["width"])
height = int(payload["height"])
out_dir = Path(payload["out_dir"])
font_path = Path(payload["subtitle_font_path"])
assert font_path.exists(), f"Missing subtitle font: {font_path}"
font = ImageFont.truetype(str(font_path), 96)

def wrap(text, line_chars=22):
	text = " ".join(text.split())
	return [text[i:i + line_chars] for i in range(0, len(text), line_chars)][:2] or [text]

Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(out_dir / "blank.png")

for cue in payload["cues"]:
	img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
	draw = ImageDraw.Draw(img)
	lines = wrap(cue["display_text"])
	line_spacing = 22
	stroke_width = 9
	bold_offsets = [(-2, 0), (2, 0), (0, -2), (0, 2), (0, 0)]
	bboxes = [draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width) for line in lines]
	line_heights = [bbox[3] - bbox[1] for bbox in bboxes]
	total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
	max_w = max((bbox[2] - bbox[0] for bbox in bboxes), default=0)
	box_pad_x = 64
	box_pad_y = 40
	box_w = min(width, max_w + box_pad_x * 2)
	box_h = total_h + box_pad_y * 2
	box_x0 = (width - box_w) // 2
	box_y0 = (height - box_h) // 2
	box_x1 = box_x0 + box_w
	box_y1 = box_y0 + box_h
	draw.rounded_rectangle((box_x0, box_y0, box_x1, box_y1), radius=28, fill=(0, 0, 0, 170))
	y = box_y0 + box_pad_y
	for line, line_h in zip(lines, line_heights):
		bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
		x = (width - (bbox[2] - bbox[0])) // 2
		for ox, oy in bold_offsets:
			draw.text((x + ox, y + oy), line, font=font, fill=(255, 255, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 255))
		y += line_h + line_spacing
	img.save(out_dir / f'cue_{int(cue["index"]):04d}.png')
'''
	_run([_image_python(), "-c", code, str(cues_json)])
	return SubtitleOverlaySet(overlay_paths, blank_path, overlay_width, overlay_height, overlay_x, overlay_y)


def _render_subtitle_overlay_video(
	cues: list[SubtitleCue],
	overlay_set: SubtitleOverlaySet,
	audio_duration: float,
	output_dir: Path,
	fps: int,
	force: bool,
) -> Path:
	overlay_video = output_dir / "subtitle_overlay.mov"
	concat_path = output_dir / "subtitle_overlay_concat.ffconcat"
	dependencies = [path.stat().st_mtime for path in overlay_set.paths]
	dependencies.append(overlay_set.blank_path.stat().st_mtime)
	if (
		overlay_video.exists()
		and overlay_video.stat().st_size > 0
		and overlay_video.stat().st_mtime >= max(dependencies)
		and not force
	):
		return overlay_video
	segments: list[tuple[Path, float]] = []
	cursor = 0.0
	for cue, path in zip(cues, overlay_set.paths):
		if cue.start > cursor + 0.01:
			segments.append((overlay_set.blank_path, cue.start - cursor))
		segments.append((path, max(0.05, cue.end - cue.start)))
		cursor = max(cursor, cue.end)
	if audio_duration > cursor + 0.01:
		segments.append((overlay_set.blank_path, audio_duration - cursor))
	if not segments:
		segments.append((overlay_set.blank_path, max(0.05, audio_duration)))
	with concat_path.open("w", encoding="utf-8") as f:
		f.write("ffconcat version 1.0\n")
		last_path: Path | None = None
		for path, duration in segments:
			last_path = path
			f.write(f"file '{_ffconcat_path(path)}'\n")
			f.write(f"duration {duration:.3f}\n")
		if last_path:
			f.write(f"file '{_ffconcat_path(last_path)}'\n")
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"concat",
		"-safe",
		"0",
		"-i",
		str(concat_path),
		"-vf",
		f"fps={fps},format=argb",
		"-c:v",
		"qtrle",
		"-pix_fmt",
		"argb",
		"-t",
		f"{audio_duration:.3f}",
		str(overlay_video),
	])
	return overlay_video


def _render_video(
	cover: Path,
	visual_segments: list[VisualSegment],
	chapter_plan: Path | None,
	audio: Path,
	subtitle_srt: Path | None,
	subtitle_ass: Path | None,
	subtitle_cues: list[SubtitleCue],
	subtitle_mode: str,
	output_dir: Path,
	width: int,
	height: int,
	fps: int,
	speaker_labels: bool,
	embed_subtitle_track: bool,
	force: bool,
) -> Path:
	final_video = output_dir / "final_video.mp4"
	dependencies = [audio.stat().st_mtime, *(segment.path.stat().st_mtime for segment in visual_segments)]
	if chapter_plan is not None:
		dependencies.append(chapter_plan.stat().st_mtime)
	if subtitle_mode != "none":
		if subtitle_srt is None:
			raise ValueError("subtitle_srt is required when subtitle_mode is not none")
		dependencies.append(subtitle_srt.stat().st_mtime)
	if subtitle_mode == "burn":
		if subtitle_ass is None:
			raise ValueError("subtitle_ass is required when subtitle_mode is burn")
		dependencies.append(subtitle_ass.stat().st_mtime)
	try:
		existing_subtitle_streams = _ffprobe_stream_count(final_video, "subtitle") if final_video.exists() and final_video.stat().st_size > 0 else 0
	except Exception:
		existing_subtitle_streams = 0
	has_required_subtitle_stream = not embed_subtitle_track or subtitle_mode == "none" or existing_subtitle_streams > 0
	if (
		final_video.exists()
		and final_video.stat().st_size > 0
		and final_video.stat().st_mtime >= max(dependencies)
		and has_required_subtitle_stream
		and not force
	):
		return final_video
	vf = (
		f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
		f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
		f"setsar=1,fps={fps}"
	)
	if len(visual_segments) == 1 and visual_segments[0].path == cover:
		input_args: list[str] = [
			"-loop",
			"1",
			"-framerate",
			str(fps),
			"-i",
			str(cover),
			"-i",
			str(audio),
		]
	else:
		visual_concat = _write_visual_concat(visual_segments, output_dir)
		input_args = [
			"-f",
			"concat",
			"-safe",
			"0",
			"-i",
			str(visual_concat),
			"-i",
			str(audio),
		]
	filter_args: list[str]
	srt_input_index: int | None = None
	if subtitle_mode == "burn":
		audio_duration = _ffprobe_duration(audio)
		overlay_set = _render_subtitle_overlay_images(subtitle_cues, output_dir, width, height, force, speaker_labels)
		overlay_video = _render_subtitle_overlay_video(subtitle_cues, overlay_set, audio_duration, output_dir, fps, force)
		input_args.extend(["-i", str(overlay_video)])
		if embed_subtitle_track and subtitle_srt:
			srt_input_index = 3
			input_args.extend(["-i", str(subtitle_srt)])
		filter_args = [
			"-filter_complex",
			f"[0:v]{vf}[base];[base][2:v]overlay={overlay_set.x}:{overlay_set.y}:format=auto:shortest=1,format=yuv420p[vout]",
			"-map",
			"[vout]",
			"-map",
			"1:a",
		]
	else:
		if embed_subtitle_track and subtitle_srt:
			srt_input_index = 2
			input_args.extend(["-i", str(subtitle_srt)])
		filter_args = ["-vf", vf, "-map", "0:v", "-map", "1:a"]
	subtitle_args: list[str] = []
	if srt_input_index is not None:
		subtitle_args = [
			"-map",
			f"{srt_input_index}:0",
			"-c:s",
			"mov_text",
			"-metadata:s:s:0",
			"language=chi",
			"-metadata:s:s:0",
			"handler_name=Chinese subtitles",
		]
	_run([
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		*input_args,
		*filter_args,
		*subtitle_args,
		"-c:v",
		"libx264",
		"-preset",
		"veryfast",
		"-tune",
		"stillimage",
		"-pix_fmt",
		"yuv420p",
		"-c:a",
		"aac",
		"-b:a",
		"192k",
		"-shortest",
		"-movflags",
		"+faststart",
		str(final_video),
	])
	return final_video


def _write_report(
	output_dir: Path,
	script: Path,
	cover: Path,
	chapter_plan: Path | None,
	visual_segments: list[VisualSegment],
	final_audio: Path,
	final_video: Path,
	srt_path: Path | None,
	ass_path: Path | None,
	subtitle_mode: str,
	speaker_labels: bool,
	embed_subtitle_track: bool,
	turns: list[Turn],
	chunks: list[Chunk],
	subtitle_cues: list[SubtitleCue],
	profile: dict[str, Any],
) -> None:
	audio_duration = _ffprobe_duration(final_audio)
	video_duration = _ffprobe_duration(final_video)
	video_width, video_height = _ffprobe_video_size(final_video)
	video_subtitle_streams = _ffprobe_stream_count(final_video, "subtitle")
	manifest = {
		"schema_version": "article-podcast-visual-video.v2",
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
		"inputs": {
			"script": str(script),
			"script_sha256": _file_sha256(script),
			"cover": str(cover),
			"cover_sha256": _file_sha256(cover),
			"chapter_plan": str(chapter_plan) if chapter_plan else None,
		},
		"voice_profile": {
			"profile_name": profile.get("profile_name"),
			"provider": profile.get("provider"),
			"model_dir": profile.get("model_dir"),
			"lang_code": profile.get("lang_code"),
			"speed": profile.get("speed"),
			"temperature": profile.get("temperature"),
			"voices": list(profile.get("voices", {}).keys()),
		},
		"counts": {
			"turns": len(turns),
			"chunks": len(chunks),
			"subtitle_cues": len(subtitle_cues),
		},
		"outputs": {
			"final_audio": str(final_audio),
			"final_audio_duration_sec": audio_duration,
			"final_video": str(final_video),
			"final_video_duration_sec": video_duration,
			"final_video_width": video_width,
			"final_video_height": video_height,
			"subtitle_mode": subtitle_mode,
			"subtitle_speaker_labels": speaker_labels,
			"embed_subtitle_track": embed_subtitle_track,
			"final_video_subtitle_streams": video_subtitle_streams,
			"subtitles_srt": str(srt_path) if srt_path else None,
			"subtitles_ass": str(ass_path) if ass_path else None,
			"visual_segments": [
				{
					"label": segment.label,
					"start_sec": segment.start,
					"end_sec": segment.end,
					"duration_sec": segment.end - segment.start,
					"image": str(segment.path),
				}
				for segment in visual_segments
			],
		},
	}
	_write_json(output_dir / "render_manifest.json", manifest)
	report = [
		"# 静态播客视频渲染报告",
		"",
		f"- 文稿：`{script}`",
		f"- 封面：`{cover}`",
		f"- 章节计划：`{chapter_plan}`" if chapter_plan else "- 章节计划：未使用，整片保持封面画面",
		f"- 画面段数：{len(visual_segments)}",
		f"- 回合数：{len(turns)}",
		f"- 音频分块数：{len(chunks)}",
		f"- 字幕条数：{len(subtitle_cues)}",
		f"- 完整音频：`{final_audio}`",
		f"- 音频时长：{audio_duration:.2f} 秒",
		f"- SRT 字幕：`{srt_path}`" if srt_path else "- SRT 字幕：未生成",
		f"- ASS 字幕：`{ass_path}`" if ass_path else "- ASS 字幕：未生成",
		f"- 字幕模式：{subtitle_mode}",
		f"- 字幕显示说话人：{speaker_labels}",
		f"- MP4 内置软字幕：{embed_subtitle_track}",
		f"- MP4 字幕轨：{video_subtitle_streams}",
		f"- 完整视频：`{final_video}`",
		f"- 视频时长：{video_duration:.2f} 秒",
		f"- 视频尺寸：{video_width}x{video_height}",
		"",
		"## 复用音色",
		"",
		"本次使用 `assets/linyao-chenche-voicedesign.json` 中的 VoiceDesign 描述和参数。试听 wav 只是人工参考，不作为克隆输入。",
	]
	(output_dir / "render_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Render a Chinese two-speaker podcast script into a single-cover or chapter-visual video.")
	parser.add_argument("--input-dir", help="Project folder containing a script and cover image.")
	parser.add_argument("--script", help="Markdown podcast script path.")
	parser.add_argument("--cover", help="Cover image path.")
	parser.add_argument("--chapter-plan", help="Optional JSON plan for chapter images. Each item needs start_turn and may include image/image_path/visual_path.")
	parser.add_argument("--output-dir", required=True, help="Output directory.")
	parser.add_argument("--voice-profile", default=str(DEFAULT_PROFILE), help="Voice profile JSON path.")
	parser.add_argument("--turn-limit", type=int, help="Render only the first N dialogue turns for smoke tests.")
	parser.add_argument("--max-chars", type=int, default=140, help="Max characters per generated TTS chunk.")
	parser.add_argument("--video-width", type=int, default=3840)
	parser.add_argument("--video-height", type=int, default=2160)
	parser.add_argument("--fps", type=int, default=30)
	parser.add_argument("--subtitle-mode", choices=("burn", "sidecar", "none"), default="burn", help="Burn subtitles into video, write sidecar only, or disable subtitles.")
	parser.add_argument("--subtitle-speaker-labels", action="store_true", help="Prefix each subtitle with the speaker name.")
	parser.add_argument("--embed-subtitle-track", action="store_true", help="Mux SRT into the MP4 as a mov_text subtitle track. Disabled by default to avoid duplicate subtitles when burn mode is used.")
	parser.add_argument("--force", action="store_true", help="Regenerate cached draft wavs and final outputs.")
	parser.add_argument("--verbose-tts", action="store_true", help="Show per-token TTS generation logs.")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	_assert_tooling()
	output_dir = Path(args.output_dir).expanduser().resolve()
	output_dir.mkdir(parents=True, exist_ok=True)
	script, cover = _resolve_inputs(args)
	chapter_plan = Path(args.chapter_plan).expanduser().resolve() if args.chapter_plan else None
	profile = _read_json(Path(args.voice_profile).expanduser().resolve())
	roles = set(profile["voices"].keys())
	turns = _parse_turns(script, roles)
	missing_roles = roles - {turn.role for turn in turns}
	if missing_roles:
		raise RuntimeError(f"Script does not contain required role(s): {sorted(missing_roles)}")
	if args.turn_limit:
		turns = turns[:args.turn_limit]
	if not turns:
		raise RuntimeError(f"No dialogue turns found for roles {sorted(roles)} in {script}")
	_log(f"SCRIPT {_log_path(script)}")
	_log(f"COVER {_log_path(cover)}")
	_log(f"TURNS {len(turns)}")
	final_audio, chunks = _render_audio(turns, profile, output_dir, args.max_chars, args.force, args.verbose_tts)
	audio_duration = _ffprobe_duration(final_audio)
	_log(f"AUDIO {_log_path(final_audio)} duration={audio_duration:.2f}s")
	visual_segments = _build_visual_segments(cover, chapter_plan, chunks, profile, audio_duration)
	_log(f"VISUAL_SEGMENTS {len(visual_segments)}")
	if args.subtitle_mode == "none":
		srt_path = None
		ass_path = None
		subtitle_cues: list[SubtitleCue] = []
	else:
		srt_path, ass_path, subtitle_cues = _build_subtitles(chunks, profile, output_dir, args.subtitle_speaker_labels)
		_log(f"SUBTITLES {_log_path(srt_path)} cues={len(subtitle_cues)}")
	final_video = _render_video(cover, visual_segments, chapter_plan, final_audio, srt_path, ass_path, subtitle_cues, args.subtitle_mode, output_dir, args.video_width, args.video_height, args.fps, args.subtitle_speaker_labels, args.embed_subtitle_track, args.force)
	_log(f"VIDEO {_log_path(final_video)} duration={_ffprobe_duration(final_video):.2f}s")
	_write_report(output_dir, script, cover, chapter_plan, visual_segments, final_audio, final_video, srt_path, ass_path, args.subtitle_mode, args.subtitle_speaker_labels, args.embed_subtitle_track, turns, chunks, subtitle_cues, profile)
	_log(f"REPORT {_log_path(output_dir / 'render_report.md')}")
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except Exception as exc:
		print(f"ERROR: {exc}", file=sys.stderr, flush=True)
		raise
