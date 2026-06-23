#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse


SCHEMA_VERSION = "transcript.v1"


class TranscriptError(RuntimeError):
	pass


def main() -> int:
	args = _parse_args()
	video_id = _extract_youtube_video_id(args.url_or_id)
	cache_dir = Path(args.cache_dir)
	video_metadata = _load_video_metadata(args.video_metadata_file, video_id, args.url_or_id)

	if args.use_cache:
		cached_path = _find_cached_transcript(cache_dir, video_id, args.language, args.preserve_formatting)
		if cached_path:
			payload = _payload_from_transcript_file(cached_path, video_metadata)
			json_path, txt_path = _paths_from_cached_json(cached_path)
			payload["transcript_file_path"] = str(json_path)
			payload["plain_text_file_path"] = str(txt_path)
			_write_transcript_files(payload, json_path, txt_path)
			_print_json(_summary_from_payload(payload))
			return 0

	try:
		result = _fetch_transcript(args.url_or_id, video_id, args.language, args.preserve_formatting)
	except Exception as exc:
		return _fail(str(exc))

	payload = _payload_from_result(result, video_metadata, args.preserve_formatting)
	if args.use_cache:
		json_path, txt_path = _cache_paths(cache_dir, video_id, payload["transcript"]["language"], args.preserve_formatting)
		payload["transcript_file_path"] = str(json_path)
		payload["plain_text_file_path"] = str(txt_path)
		_write_transcript_files(payload, json_path, txt_path)
		_print_json(_summary_from_payload(payload))
		return 0

	_print_json(_summary_from_payload(payload))
	return 0


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Fetch public YouTube transcript JSON.")
	parser.add_argument("url_or_id")
	parser.add_argument("--language", action="append", default=None)
	parser.add_argument("--cache-dir", required=True, help="Transcript cache/output directory. In Worldview China formal runs, pass the current run's 01-topic-selection/transcripts or 02-media-preparation/subtitles directory.")
	parser.add_argument("--no-cache", action="store_false", dest="use_cache")
	parser.add_argument("--preserve-formatting", action="store_true")
	parser.add_argument(
		"--video-metadata-file",
		help="JSON detailList output or a single video metadata object. Used to write title/description into cached transcript files.",
	)
	return parser.parse_args()


def _fetch_transcript(url_or_id: str, video_id: str, languages: list[str] | None, preserve_formatting: bool) -> dict[str, Any]:
	try:
		from youtube_transcript_api import YouTubeTranscriptApi
	except ImportError as exc:
		raise TranscriptError("Install youtube-transcript-api or run with `uv run python` inside the project workspace.") from exc

	provider = _provider(YouTubeTranscriptApi)
	language_preferences = languages or ["en", "en-US", "en-GB"]

	try:
		transcript_list = _list_transcripts(provider, video_id)
		try:
			transcript = transcript_list.find_manually_created_transcript(language_preferences)
			source = "manual_caption"
		except Exception:
			transcript = transcript_list.find_generated_transcript(language_preferences)
			source = "auto_caption"
		raw_segments = _fetch_selected(transcript, preserve_formatting)
		language = getattr(transcript, "language_code", None) or language_preferences[0]
	except Exception:
		raw_segments = _fetch_fallback(provider, video_id, language_preferences, preserve_formatting)
		source = "fallback"
		language = language_preferences[0]

	segments = [_segment_from_raw(segment) for segment in raw_segments]
	transcript_text = "\n".join(segment["text"] for segment in segments if segment["text"].strip())
	if not transcript_text:
		raise TranscriptError(f"Transcript for video {video_id} was empty.")

	return {
		"tool": "getTranscript",
		"url": url_or_id if url_or_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}",
		"video_id": video_id,
		"language": language,
		"source": source,
		"transcript": transcript_text,
		"segments": segments,
	}


def _provider(api_class: Any) -> Any:
	try:
		return api_class()
	except TypeError:
		return api_class


def _list_transcripts(provider: Any, video_id: str) -> Any:
	if hasattr(provider, "list_transcripts"):
		return provider.list_transcripts(video_id)
	if hasattr(provider, "list"):
		return provider.list(video_id)
	raise TranscriptError("Transcript provider does not expose list_transcripts() or list().")


def _fetch_selected(transcript: Any, preserve_formatting: bool) -> list[Any]:
	try:
		fetched = transcript.fetch(preserve_formatting=preserve_formatting)
	except TypeError:
		fetched = transcript.fetch()
	return _raw_segments(fetched)


def _fetch_fallback(provider: Any, video_id: str, languages: list[str], preserve_formatting: bool) -> list[Any]:
	if not hasattr(provider, "fetch"):
		raise TranscriptError("Transcript provider does not expose fetch().")
	try:
		fetched = provider.fetch(video_id, languages=languages, preserve_formatting=preserve_formatting)
	except TypeError:
		fetched = provider.fetch(video_id, languages=languages)
	return _raw_segments(fetched)


def _raw_segments(fetched: Any) -> list[Any]:
	if hasattr(fetched, "to_raw_data"):
		raw_data = fetched.to_raw_data()
		return list(raw_data) if isinstance(raw_data, list) else []
	if isinstance(fetched, list):
		return fetched
	return list(fetched)


def _segment_from_raw(raw_segment: Any) -> dict[str, Any]:
	if isinstance(raw_segment, dict):
		return {
			"start": float(raw_segment.get("start", 0)),
			"duration": float(raw_segment.get("duration", 0)),
			"text": str(raw_segment.get("text", "")),
		}
	return {
		"start": float(getattr(raw_segment, "start", 0)),
		"duration": float(getattr(raw_segment, "duration", 0)),
		"text": str(getattr(raw_segment, "text", "")),
	}


def _cache_paths(cache_dir: Path, video_id: str, language: str, preserve_formatting: bool) -> tuple[Path, Path]:
	language_key = language.replace("/", "_")
	format_key = "formatted" if preserve_formatting else "plain"
	stem = f"{video_id}.{language_key}.{format_key}"
	return cache_dir / f"{stem}.json", cache_dir / f"{stem}.txt"


def _paths_from_cached_json(json_path: Path) -> tuple[Path, Path]:
	return json_path, Path(str(json_path).removesuffix(".json") + ".txt")


def _find_cached_transcript(
	cache_dir: Path,
	video_id: str,
	languages: list[str] | None,
	preserve_formatting: bool,
) -> Path | None:
	format_key = "formatted" if preserve_formatting else "plain"
	for language in languages or ["en", "en-US", "en-GB"]:
		path = cache_dir / f"{video_id}.{language.replace('/', '_')}.{format_key}.json"
		if path.exists():
			return path
	matches = sorted(cache_dir.glob(f"{video_id}.*.{format_key}.json"))
	return matches[0] if matches else None


def _load_video_metadata(path_value: str | None, video_id: str, url_or_id: str) -> dict[str, Any]:
	if not path_value:
		return _normalize_video_metadata({}, video_id, url_or_id)
	path = Path(path_value)
	payload = json.loads(path.read_text(encoding="utf-8"))
	if not isinstance(payload, dict):
		raise TranscriptError(f"Video metadata file must be a JSON object: {path}")
	raw_video = _select_video_metadata(payload, video_id)
	if raw_video is None:
		raise TranscriptError(f"Video metadata file does not contain video_id {video_id}: {path}")
	return _normalize_video_metadata(raw_video, video_id, url_or_id)


def _select_video_metadata(payload: dict[str, Any], video_id: str) -> dict[str, Any] | None:
	if payload.get("video_id") == video_id:
		return payload
	if isinstance(payload.get("video"), dict) and payload["video"].get("video_id") == video_id:
		return payload["video"]
	videos = payload.get("videos")
	if isinstance(videos, list):
		for item in videos:
			if isinstance(item, dict) and item.get("video_id") == video_id:
				return item
	return None


def _normalize_video_metadata(raw_video: dict[str, Any], video_id: str, url_or_id: str) -> dict[str, Any]:
	video_url = raw_video.get("video_url") or raw_video.get("url")
	if not isinstance(video_url, str) or not video_url:
		video_url = url_or_id if url_or_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"
	video = {
		"video_id": video_id,
		"video_url": video_url,
		"title": _string_or_empty(raw_video.get("title")),
		"description": _string_or_empty(raw_video.get("description")),
		"channel": _string_or_empty(raw_video.get("channel") or raw_video.get("channel_title")),
		"channel_id": raw_video.get("channel_id"),
		"published_at": raw_video.get("published_at") or raw_video.get("publishedAt"),
		"duration_seconds": raw_video.get("duration_seconds"),
		"thumbnail_url": raw_video.get("thumbnail_url"),
	}
	video["metadata_incomplete"] = not all(video.get(field) for field in ("title", "description"))
	return video


def _string_or_empty(value: Any) -> str:
	return value if isinstance(value, str) else ""


def _payload_from_transcript_file(path: Path, video_metadata: dict[str, Any]) -> dict[str, Any]:
	payload = json.loads(path.read_text(encoding="utf-8"))
	if not isinstance(payload, dict):
		raise TranscriptError(f"Cached transcript file is invalid: {path}")
	if payload.get("schema_version") == SCHEMA_VERSION:
		return _merge_video_metadata(payload, video_metadata)
	return _payload_from_legacy_result(payload, video_metadata)


def _payload_from_legacy_result(result: dict[str, Any], video_metadata: dict[str, Any]) -> dict[str, Any]:
	return _payload_from_result(
		{
			"url": result.get("url"),
			"video_id": result.get("video_id"),
			"language": result.get("language"),
			"source": result.get("source"),
			"transcript": result.get("transcript") or "",
			"segments": result.get("segments") or [],
		},
		video_metadata,
		preserve_formatting=False,
	)


def _payload_from_result(
	result: dict[str, Any],
	video_metadata: dict[str, Any],
	preserve_formatting: bool,
) -> dict[str, Any]:
	transcript_text = result.get("transcript") if isinstance(result.get("transcript"), str) else ""
	segments = result.get("segments") if isinstance(result.get("segments"), list) else []
	return {
		"schema_version": SCHEMA_VERSION,
		"tool": "getTranscript",
		"video": video_metadata,
		"transcript": {
			"language": result.get("language"),
			"source": result.get("source"),
			"preserve_formatting": preserve_formatting,
			"text": transcript_text,
			"segments": segments,
		},
	}


def _merge_video_metadata(payload: dict[str, Any], video_metadata: dict[str, Any]) -> dict[str, Any]:
	video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
	merged = dict(video_metadata)
	for key, value in video.items():
		if value not in (None, ""):
			merged[key] = value
	for key, value in video_metadata.items():
		if value not in (None, "") and video.get(key) in (None, ""):
			merged[key] = value
	merged["metadata_incomplete"] = not all(merged.get(field) for field in ("title", "description"))
	payload["video"] = merged
	payload.setdefault("schema_version", SCHEMA_VERSION)
	payload.setdefault("tool", "getTranscript")
	return payload


def _write_transcript_files(payload: dict[str, Any], json_path: Path, txt_path: Path) -> None:
	json_path.parent.mkdir(parents=True, exist_ok=True)
	json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
	txt_path.write_text(_plain_text_from_payload(payload), encoding="utf-8")


def _summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
	video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
	transcript = payload.get("transcript") if isinstance(payload.get("transcript"), dict) else {}
	segments = transcript.get("segments", [])
	transcript_text = transcript.get("text", "")
	return {
		"tool": "getTranscript",
		"schema_version": payload.get("schema_version"),
		"url": video.get("video_url"),
		"video_id": video.get("video_id"),
		"title": video.get("title"),
		"description_chars": len(video.get("description", "")) if isinstance(video.get("description"), str) else None,
		"metadata_incomplete": video.get("metadata_incomplete"),
		"language": transcript.get("language"),
		"source": transcript.get("source"),
		"segments_count": len(segments) if isinstance(segments, list) else None,
		"transcript_chars": len(transcript_text) if isinstance(transcript_text, str) else None,
		"transcript_file_path": payload.get("transcript_file_path"),
		"plain_text_file_path": payload.get("plain_text_file_path"),
	}


def _plain_text_from_payload(payload: dict[str, Any]) -> str:
	video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
	transcript = payload.get("transcript") if isinstance(payload.get("transcript"), dict) else {}
	segments = transcript.get("segments") if isinstance(transcript.get("segments"), list) else []
	lines = [
		"---",
		f"schema_version: {_front_matter_scalar(payload.get('schema_version', SCHEMA_VERSION))}",
		f"video_id: {_front_matter_scalar(video.get('video_id'))}",
		f"video_url: {_front_matter_scalar(video.get('video_url'))}",
		f"title: {_front_matter_scalar(video.get('title'))}",
		f"channel: {_front_matter_scalar(video.get('channel'))}",
		f"published_at: {_front_matter_scalar(video.get('published_at'))}",
		f"duration_seconds: {_front_matter_scalar(video.get('duration_seconds'))}",
		f"language: {_front_matter_scalar(transcript.get('language'))}",
		f"source: {_front_matter_scalar(transcript.get('source'))}",
		f"metadata_incomplete: {str(bool(video.get('metadata_incomplete'))).lower()}",
		"description: |",
	]
	description = str(video.get("description") or "")
	if description:
		lines.extend(f"  {line}" for line in description.splitlines())
	else:
		lines.append("  ")
	lines.extend(["---", ""])
	lines.extend(_plain_text_lines_from_segments(segments))
	return "\n".join(lines) + "\n"


def _front_matter_scalar(value: Any) -> str:
	text = "" if value is None else str(value)
	return json.dumps(text, ensure_ascii=False)


def _plain_text_lines_from_segments(segments: list[dict[str, Any]]) -> list[str]:
	lines = []
	for segment in segments:
		start = float(segment.get("start", 0))
		end = start + float(segment.get("duration", 0))
		text = str(segment.get("text", "")).strip()
		if text:
			lines.append(f"[{_timestamp(start)} - {_timestamp(end)}] {text}")
	return lines


def _timestamp(seconds: float) -> str:
	total_seconds = max(0, int(seconds))
	hours, remainder = divmod(total_seconds, 3600)
	minutes, seconds = divmod(remainder, 60)
	return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _extract_youtube_video_id(url_or_id: str) -> str:
	value = url_or_id.strip()
	if _looks_like_video_id(value):
		return value
	parsed = urlparse(value)
	host = parsed.netloc.lower().removeprefix("www.")
	path_parts = [part for part in parsed.path.split("/") if part]
	if host == "youtu.be" and path_parts and _looks_like_video_id(path_parts[0]):
		return path_parts[0]
	if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
		query_video_id = parse_qs(parsed.query).get("v", [None])[0]
		if query_video_id and _looks_like_video_id(query_video_id):
			return query_video_id
		if len(path_parts) >= 2 and path_parts[0] in {"embed", "shorts", "live"} and _looks_like_video_id(path_parts[1]):
			return path_parts[1]
	raise TranscriptError(f"Could not extract YouTube video id from: {url_or_id}")


def _looks_like_video_id(value: str) -> bool:
	return len(value) == 11 and all(char.isalnum() or char in {"-", "_"} for char in value)


def _print_json(payload: object) -> None:
	print(json.dumps(payload, ensure_ascii=False, indent=2))


def _fail(message: str) -> int:
	_print_json({"ok": False, "error": message})
	return 1


if __name__ == "__main__":
	sys.exit(main())
