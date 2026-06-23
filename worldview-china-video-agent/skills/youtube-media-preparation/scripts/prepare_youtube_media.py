#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any


SCHEMA_VERSION = "youtube-media-assets.v1"
DEFAULT_TRANSCRIPT_TOOL = "/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/get_transcript.py"


class MediaPreparationError(RuntimeError):
	pass


def main() -> int:
	args = _parse_args()
	if not args.authorized:
		raise MediaPreparationError("Pass --authorized after confirming this video can be processed.")

	yt_dlp_cmd = _resolve_ytdlp_cmd(args.yt_dlp_bin)
	_require_tool("ffmpeg")
	_require_tool("ffprobe")

	yt_dlp_request_args = _yt_dlp_request_args(args)
	info = _fetch_ytdlp_info(args.url, args.height, yt_dlp_cmd, yt_dlp_request_args, args.require_target_height)
	video_id = _string(info.get("id"))
	if not video_id:
		raise MediaPreparationError("yt-dlp did not return a video id.")

	output_dir = Path(args.output_dir) if args.output_dir else Path(args.output_root) / video_id
	output_dir.mkdir(parents=True, exist_ok=True)

	paths = _asset_paths(output_dir)
	_write_json(paths["raw_info_json"], info)
	metadata = _metadata_from_info(info, args.url)
	_write_json(paths["metadata"], metadata)

	selection = _select_formats(info, args.height)
	download = _download_source_video(
		args.url,
		paths,
		selection,
		force=args.force,
		reuse_existing=args.reuse_existing,
		yt_dlp_cmd=yt_dlp_cmd,
		yt_dlp_request_args=yt_dlp_request_args,
	)
	audio = _extract_wav(paths, force=args.force, reuse_existing=args.reuse_existing)
	probe = _write_probe_files(paths)
	if download["status"] == "reused":
		selection = _reconcile_selection_with_existing_probe(selection, probe, args.height)
	thumbnail = _prepare_thumbnail(paths, info, force=args.force)
	transcript = _prepare_transcript(args, paths, metadata)

	manifest = {
		"schema_version": SCHEMA_VERSION,
		"video_id": video_id,
		"url": metadata["video_url"],
		"title": metadata["title"],
		"output_dir": str(output_dir),
		"video_path": str(paths["video"]),
		"audio_path": str(paths["audio"]),
		"thumbnail_path": str(thumbnail["path"]) if thumbnail.get("path") else None,
		"metadata_path": str(paths["metadata"]),
		"raw_info_json_path": str(paths["raw_info_json"]),
		"probe_path": str(paths["probe"]),
		"audio_probe_path": str(paths["audio_probe"]),
		"download_log_path": str(paths["download_log"]),
		"yt_dlp_command": yt_dlp_cmd,
		"yt_dlp_auth_network": _yt_dlp_auth_network_manifest(args),
		"target_video_height": args.height,
		"selected_video_format": selection["video"],
		"selected_audio_format": selection.get("audio"),
		"resolution_selection": selection["resolution"],
		"download": download,
		"audio_extract": audio,
		"probe": probe,
		"thumbnail": thumbnail,
		"transcript": transcript,
	}
	_write_json(paths["manifest"], manifest)
	_print_json(_summary_from_manifest(manifest))
	return 0


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Prepare a local YouTube media asset package.")
	parser.add_argument("url", help="Single YouTube video URL. Playlists are not processed.")
	parser.add_argument("--authorized", action="store_true", help="Required: confirms the user authorized processing this video.")
	parser.add_argument("--output-root", help="Root directory used when --output-dir is omitted.")
	parser.add_argument("--output-dir", help="Exact output directory. Defaults to {output_root}/{video_id}.")
	parser.add_argument("--height", type=int, default=1080, help="Target video height. Defaults to 1080.")
	parser.add_argument("--yt-dlp-bin", help="yt-dlp command to use. Defaults to 'uvx yt-dlp' when uvx exists, otherwise system yt-dlp.")
	parser.add_argument("--cookies", help="Netscape-format cookies.txt file for yt-dlp. The file contents are never logged.")
	parser.add_argument("--cookies-from-browser", help="Browser cookie source for yt-dlp, e.g. chrome, chrome:Default, or chrome:Profile 1.")
	parser.add_argument("--proxy", help="HTTP/HTTPS/SOCKS proxy URL for yt-dlp. Use an empty string to force direct connection.")
	parser.add_argument("--impersonate", help="yt-dlp impersonation target, e.g. chrome or chrome:macos.")
	parser.add_argument(
		"--yt-dlp-extra-args",
		action="append",
		default=None,
		help="Additional yt-dlp args parsed with shlex. Repeatable. Avoid secrets; command logs are redacted for known sensitive options.",
	)
	parser.add_argument("--require-target-height", action="store_true", help="Fail if yt-dlp cannot see a downloadable video format at least as high as --height.")
	parser.add_argument("--language", action="append", dest="languages", default=None, help="Transcript language preference. Repeatable.")
	parser.add_argument("--transcript-tool", default=DEFAULT_TRANSCRIPT_TOOL, help="Path to getTranscript script.")
	parser.add_argument("--skip-transcript", action="store_true", help="Do not fetch transcripts.")
	parser.add_argument("--require-transcript", action="store_true", help="Fail if transcript fetching fails.")
	parser.add_argument("--force", action="store_true", help="Redownload/recreate existing media outputs.")
	parser.add_argument(
		"--no-reuse-existing",
		action="store_false",
		dest="reuse_existing",
		default=True,
		help="Do not reuse existing source.mp4/source.wav in output dir.",
	)
	args = parser.parse_args()
	if args.height < 144:
		parser.error("--height must be at least 144")
	if args.cookies and args.cookies_from_browser:
		parser.error("Use either --cookies or --cookies-from-browser, not both.")
	if not args.output_dir and not args.output_root:
		parser.error("Either --output-dir or --output-root is required. In Worldview China formal runs, pass the current run's 02-media-preparation directory.")
	return args


def _asset_paths(output_dir: Path) -> dict[str, Path]:
	return {
		"output_dir": output_dir,
		"video": output_dir / "source.mp4",
		"audio": output_dir / "source.wav",
		"thumbnail": output_dir / "source.jpg",
		"raw_info_json": output_dir / "source.info.json",
		"metadata": output_dir / "metadata.json",
		"manifest": output_dir / "media_manifest.json",
		"probe": output_dir / "probe.json",
		"audio_probe": output_dir / "probe.audio.json",
		"download_log": output_dir / "download.log",
		"subtitles_dir": output_dir / "subtitles",
	}


def _fetch_ytdlp_info(
	url: str,
	target_height: int,
	yt_dlp_cmd: list[str],
	yt_dlp_request_args: list[str],
	require_target_height: bool,
) -> dict[str, Any]:
	cmd = [*yt_dlp_cmd, *yt_dlp_request_args, "--no-playlist", "--dump-single-json", "--skip-download", url]
	best_payload: dict[str, Any] | None = None
	best_height = -1
	last_error: Exception | None = None
	for attempt in range(3):
		try:
			result = _run(cmd)
			payload = json.loads(result.stdout)
			if not isinstance(payload, dict):
				raise MediaPreparationError("yt-dlp JSON payload was not an object.")
			height = _max_downloadable_video_height(payload)
			if height > best_height:
				best_payload = payload
				best_height = height
			if height >= target_height:
				return payload
		except (json.JSONDecodeError, MediaPreparationError) as exc:
			last_error = exc
		if attempt < 2:
			time.sleep(1)
	if best_payload is not None:
		if require_target_height and best_height < target_height:
			raise MediaPreparationError(
				f"Highest visible yt-dlp format is {best_height}p, below required target {target_height}p. "
				"Use a newer yt-dlp command such as 'uvx yt-dlp' or lower --height intentionally."
			)
		return best_payload
	if last_error is not None:
		raise MediaPreparationError(f"Could not read yt-dlp info: {last_error}") from last_error
	raise MediaPreparationError("Could not read yt-dlp info.")


def _max_downloadable_video_height(info: dict[str, Any]) -> int:
	formats = info.get("formats")
	if not isinstance(formats, list):
		return -1
	heights = []
	for item in formats:
		if isinstance(item, dict) and item.get("vcodec") not in (None, "none") and _height(item) is not None:
			heights.append(int(item["height"]))
	return max(heights) if heights else -1


def _select_formats(info: dict[str, Any], target_height: int) -> dict[str, Any]:
	formats = info.get("formats")
	if not isinstance(formats, list):
		formats = []

	video_candidates = [_format_summary(item) for item in formats if _is_video_only(item)]
	audio_candidates = [_format_summary(item) for item in formats if _is_audio_only(item)]
	combined_candidates = [_format_summary(item) for item in formats if _is_combined_video_audio(item)]

	video = _choose_video_format(video_candidates, target_height)
	audio = _choose_audio_format(audio_candidates)
	if video is None:
		video = _choose_video_format(combined_candidates, target_height)
		audio = None
	if video is None:
		raise MediaPreparationError("No downloadable video format found.")

	resolution = _resolution_result(video, target_height)
	return {
		"video": video,
		"audio": audio,
		"resolution": resolution,
		"format_selector": _format_selector(video, audio),
	}


def _is_video_only(item: Any) -> bool:
	if not isinstance(item, dict):
		return False
	return item.get("vcodec") not in (None, "none") and item.get("acodec") in (None, "none") and _height(item) is not None


def _is_audio_only(item: Any) -> bool:
	if not isinstance(item, dict):
		return False
	return item.get("acodec") not in (None, "none") and item.get("vcodec") in (None, "none")


def _is_combined_video_audio(item: Any) -> bool:
	if not isinstance(item, dict):
		return False
	return item.get("vcodec") not in (None, "none") and item.get("acodec") not in (None, "none") and _height(item) is not None


def _choose_video_format(candidates: list[dict[str, Any]], target_height: int) -> dict[str, Any] | None:
	if not candidates:
		return None
	exact = [item for item in candidates if item.get("height") == target_height]
	if exact:
		return _best_same_height(exact)
	higher = [item for item in candidates if isinstance(item.get("height"), int) and item["height"] > target_height]
	if higher:
		closest_height = min(int(item["height"]) for item in higher)
		return _best_same_height([item for item in higher if item.get("height") == closest_height])
	lower = [item for item in candidates if isinstance(item.get("height"), int) and item["height"] < target_height]
	if lower:
		closest_height = max(int(item["height"]) for item in lower)
		return _best_same_height([item for item in lower if item.get("height") == closest_height])
	return _best_same_height(candidates)


def _best_same_height(candidates: list[dict[str, Any]]) -> dict[str, Any]:
	return sorted(candidates, key=_video_quality_key, reverse=True)[0]


def _video_quality_key(item: dict[str, Any]) -> tuple[int, float, float, int, int]:
	return (
		_number(item.get("tbr")),
		_number(item.get("fps")),
		_int(item.get("filesize") or item.get("filesize_approx")),
		_int(item.get("width")),
		1 if item.get("ext") == "mp4" else 0,
	)


def _choose_audio_format(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
	if not candidates:
		return None
	return sorted(candidates, key=_audio_quality_key, reverse=True)[0]


def _audio_quality_key(item: dict[str, Any]) -> tuple[int, int, int, int, int, float, int]:
	return (
		_audio_original_score(item),
		_int(item.get("language_preference")),
		_audio_english_score(item),
		_audio_non_drc_score(item),
		1 if item.get("ext") == "m4a" else 0,
		_number(item.get("abr") or item.get("tbr")),
		_int(item.get("filesize") or item.get("filesize_approx")),
	)


def _audio_original_score(item: dict[str, Any]) -> int:
	note = _string(item.get("format_note")).lower()
	return 1 if "original" in note or "default" in note else 0


def _audio_english_score(item: dict[str, Any]) -> int:
	language = _string(item.get("language")).lower()
	return 1 if language == "en" or language.startswith("en-") else 0


def _audio_non_drc_score(item: dict[str, Any]) -> int:
	note = _string(item.get("format_note")).lower()
	return 0 if "drc" in note else 1


def _resolution_result(video: dict[str, Any], target_height: int) -> dict[str, Any]:
	height = video.get("height")
	if height == target_height:
		reason = "exact"
	elif isinstance(height, int) and height > target_height:
		reason = "nearest_higher"
	elif isinstance(height, int) and height < target_height:
		reason = "nearest_lower"
	else:
		reason = "unknown"
	return {
		"target_height": target_height,
		"actual_height": height,
		"reason": reason,
	}


def _reconcile_selection_with_existing_probe(selection: dict[str, Any], probe: dict[str, Any], target_height: int) -> dict[str, Any]:
	video_probe = probe.get("video") if isinstance(probe.get("video"), dict) else {}
	stream = video_probe.get("video") if isinstance(video_probe.get("video"), dict) else {}
	height = stream.get("height")
	if not isinstance(height, int):
		return selection
	video = {
		"format_id": "existing_file",
		"format_note": "existing source.mp4",
		"ext": "mp4",
		"height": height,
		"width": stream.get("width"),
		"fps": stream.get("r_frame_rate"),
		"vcodec": stream.get("codec_name"),
		"source": "existing_file_ffprobe",
	}
	reconciled = dict(selection)
	reconciled["video"] = video
	audio_stream = video_probe.get("audio") if isinstance(video_probe.get("audio"), dict) else {}
	if audio_stream:
		reconciled["audio"] = {
			"format_id": "existing_file_audio",
			"format_note": "audio stream in existing source.mp4",
			"acodec": audio_stream.get("codec_name"),
			"sample_rate": audio_stream.get("sample_rate"),
			"channels": audio_stream.get("channels"),
			"source": "existing_file_ffprobe",
		}
	reconciled["format_selector"] = "existing_file"
	reconciled["resolution"] = _resolution_result(video, target_height)
	return reconciled


def _format_selector(video: dict[str, Any], audio: dict[str, Any] | None) -> str:
	video_id = _string(video.get("format_id"))
	if not video_id:
		raise MediaPreparationError("Selected video format has no format_id.")
	if audio is None:
		return video_id
	audio_id = _string(audio.get("format_id"))
	if not audio_id:
		return video_id
	return f"{video_id}+{audio_id}"


def _format_summary(item: Any) -> dict[str, Any]:
	if not isinstance(item, dict):
		return {}
	keys = (
		"format_id",
		"format_note",
		"ext",
		"height",
		"width",
		"fps",
		"vcodec",
		"acodec",
		"tbr",
		"abr",
		"language",
		"language_preference",
		"filesize",
		"filesize_approx",
	)
	return {key: item.get(key) for key in keys if item.get(key) is not None}


def _download_source_video(
	url: str,
	paths: dict[str, Path],
	selection: dict[str, Any],
	force: bool,
	reuse_existing: bool,
	yt_dlp_cmd: list[str],
	yt_dlp_request_args: list[str],
) -> dict[str, Any]:
	video_path = paths["video"]
	if reuse_existing and video_path.exists() and not force:
		return {
			"status": "reused",
			"path": str(video_path),
			"format_selector": "existing_file",
		}

	for stale_path in paths["output_dir"].glob("source.*"):
		if stale_path.name in {"source.info.json"}:
			continue
		if stale_path.is_file():
			stale_path.unlink()

	cmd = [
		*yt_dlp_cmd,
		*yt_dlp_request_args,
		"--no-playlist",
		"--format",
		selection["format_selector"],
		"--concurrent-fragments",
		"8",
		"--merge-output-format",
		"mp4",
		"--write-info-json",
		"--write-thumbnail",
		"--convert-thumbnails",
		"jpg",
		"--output",
		str(paths["output_dir"] / "source.%(ext)s"),
		url,
	]
	result = _run(cmd, check=False)
	paths["download_log"].write_text(_command_log(cmd, result), encoding="utf-8")
	if result.returncode != 0:
		raise MediaPreparationError(f"yt-dlp download failed. See {paths['download_log']}")
	if not video_path.exists():
		_candidates = sorted(paths["output_dir"].glob("source.*"))
		raise MediaPreparationError(f"Downloaded video missing: {video_path}. Found: {[path.name for path in _candidates]}")
	return {
		"status": "downloaded",
		"path": str(video_path),
		"format_selector": selection["format_selector"],
	}


def _extract_wav(paths: dict[str, Path], force: bool, reuse_existing: bool) -> dict[str, Any]:
	audio_path = paths["audio"]
	if reuse_existing and audio_path.exists() and not force:
		return {
			"status": "reused",
			"path": str(audio_path),
			"sample_rate": 24000,
			"channels": 1,
		}
	cmd = [
		"ffmpeg",
		"-y",
		"-v",
		"error",
		"-i",
		str(paths["video"]),
		"-vn",
		"-ar",
		"24000",
		"-ac",
		"1",
		"-c:a",
		"pcm_s16le",
		str(audio_path),
	]
	_run(cmd)
	if not audio_path.exists():
		raise MediaPreparationError(f"Audio extraction did not create {audio_path}")
	return {
		"status": "extracted",
		"path": str(audio_path),
		"sample_rate": 24000,
		"channels": 1,
	}


def _write_probe_files(paths: dict[str, Path]) -> dict[str, Any]:
	video_probe = _ffprobe(paths["video"])
	audio_probe = _ffprobe(paths["audio"])
	_write_json(paths["probe"], video_probe)
	_write_json(paths["audio_probe"], audio_probe)
	return {
		"status": "ok",
		"video": _probe_summary(video_probe),
		"audio": _probe_summary(audio_probe),
	}


def _ffprobe(path: Path) -> dict[str, Any]:
	cmd = [
		"ffprobe",
		"-v",
		"error",
		"-print_format",
		"json",
		"-show_format",
		"-show_streams",
		str(path),
	]
	result = _run(cmd)
	try:
		payload = json.loads(result.stdout)
	except json.JSONDecodeError as exc:
		raise MediaPreparationError(f"ffprobe returned invalid JSON for {path}: {exc}") from exc
	if not isinstance(payload, dict):
		raise MediaPreparationError(f"ffprobe payload was not an object for {path}")
	return payload


def _probe_summary(payload: dict[str, Any]) -> dict[str, Any]:
	streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
	format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
	video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
	audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
	return {
		"duration": _maybe_float(format_info.get("duration")),
		"video": _stream_summary(video_stream),
		"audio": _stream_summary(audio_stream),
	}


def _stream_summary(stream: Any) -> dict[str, Any] | None:
	if not isinstance(stream, dict):
		return None
	return {
		"codec_name": stream.get("codec_name"),
		"width": stream.get("width"),
		"height": stream.get("height"),
		"sample_rate": stream.get("sample_rate"),
		"channels": stream.get("channels"),
		"r_frame_rate": stream.get("r_frame_rate"),
	}


def _prepare_thumbnail(paths: dict[str, Path], info: dict[str, Any], force: bool) -> dict[str, Any]:
	if paths["thumbnail"].exists() and not force:
		return {"status": "ok", "path": str(paths["thumbnail"])}
	matches = sorted(path for path in paths["output_dir"].glob("source.*") if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
	if matches:
		if matches[0] != paths["thumbnail"]:
			matches[0].replace(paths["thumbnail"])
		return {"status": "ok", "path": str(paths["thumbnail"])}
	return {
		"status": "missing",
		"path": None,
		"thumbnail_url": info.get("thumbnail"),
	}


def _prepare_transcript(args: argparse.Namespace, paths: dict[str, Path], metadata: dict[str, Any]) -> dict[str, Any]:
	if args.skip_transcript:
		return {"status": "skipped"}
	tool_path = Path(args.transcript_tool)
	if not tool_path.exists():
		result = {"status": "failed", "error": f"Transcript tool not found: {tool_path}"}
		if args.require_transcript:
			raise MediaPreparationError(result["error"])
		return result

	paths["subtitles_dir"].mkdir(parents=True, exist_ok=True)
	cmd = _transcript_command(tool_path, metadata["video_url"], paths, args.languages)
	result = _run(cmd, check=False)
	if result.returncode != 0:
		payload = _parse_json_or_text(result.stdout, result.stderr)
		error = _string(payload.get("error")) if isinstance(payload, dict) else ""
		if not error:
			error = result.stderr.strip() or result.stdout.strip() or "unknown transcript error"
		transcript = {"status": "failed", "error": error}
		if args.require_transcript:
			raise MediaPreparationError(error)
		return transcript

	payload = _parse_json_or_text(result.stdout, result.stderr)
	if not isinstance(payload, dict):
		return {"status": "failed", "error": "Transcript tool did not return JSON summary."}

	json_path = payload.get("transcript_file_path")
	txt_path = payload.get("plain_text_file_path")
	transcript = {
		"status": "ok",
		"language": payload.get("language"),
		"source": payload.get("source"),
		"segments_count": payload.get("segments_count"),
		"transcript_chars": payload.get("transcript_chars"),
		"json_path": json_path,
		"txt_path": txt_path,
	}
	if not json_path or not txt_path:
		transcript["status"] = "failed"
		transcript["error"] = "Transcript tool returned no output file paths."
		if args.require_transcript:
			raise MediaPreparationError(transcript["error"])
	return transcript


def _transcript_command(tool_path: Path, url: str, paths: dict[str, Path], languages: list[str] | None) -> list[str]:
	python_cmd = [sys.executable, str(tool_path)]
	uv_path = shutil.which("uv")
	if uv_path:
		python_cmd = [uv_path, "run", "--with", "youtube-transcript-api", "python", str(tool_path)]
	cmd = [
		*python_cmd,
		url,
		"--cache-dir",
		str(paths["subtitles_dir"]),
		"--video-metadata-file",
		str(paths["metadata"]),
	]
	for language in languages or ["en", "en-US", "en-GB"]:
		cmd.extend(["--language", language])
	return cmd


def _metadata_from_info(info: dict[str, Any], requested_url: str) -> dict[str, Any]:
	video_id = _string(info.get("id"))
	return {
		"video_id": video_id,
		"video_url": _string(info.get("webpage_url")) or requested_url,
		"title": _string(info.get("title")),
		"description": _string(info.get("description")),
		"channel": _string(info.get("channel") or info.get("uploader")),
		"channel_id": info.get("channel_id"),
		"published_at": _published_at(info),
		"duration_seconds": _maybe_float(info.get("duration")),
		"thumbnail_url": _string(info.get("thumbnail")),
		"view_count": info.get("view_count"),
		"like_count": info.get("like_count"),
		"comment_count": info.get("comment_count"),
	}


def _published_at(info: dict[str, Any]) -> str | None:
	if isinstance(info.get("release_timestamp"), int):
		return str(info["release_timestamp"])
	upload_date = _string(info.get("upload_date"))
	if len(upload_date) == 8 and upload_date.isdigit():
		return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
	return upload_date or None


def _summary_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
	return {
		"schema_version": manifest.get("schema_version"),
		"video_id": manifest.get("video_id"),
		"title": manifest.get("title"),
		"video_path": manifest.get("video_path"),
		"audio_path": manifest.get("audio_path"),
		"thumbnail_path": manifest.get("thumbnail_path"),
		"manifest_path": str(Path(manifest["output_dir"]) / "media_manifest.json"),
		"selected_height": manifest.get("resolution_selection", {}).get("actual_height"),
		"resolution_reason": manifest.get("resolution_selection", {}).get("reason"),
		"transcript": manifest.get("transcript"),
	}


def _require_tool(name: str) -> None:
	if shutil.which(name) is None:
		raise MediaPreparationError(f"Required tool not found on PATH: {name}")


def _resolve_ytdlp_cmd(value: str | None) -> list[str]:
	if value:
		parts = shlex.split(value)
		if not parts:
			raise MediaPreparationError("--yt-dlp-bin was empty.")
		if shutil.which(parts[0]) is None:
			raise MediaPreparationError(f"yt-dlp command not found: {parts[0]}")
		return parts
	uvx_path = shutil.which("uvx")
	if uvx_path:
		return [uvx_path, "yt-dlp"]
	yt_dlp_path = shutil.which("yt-dlp")
	if yt_dlp_path:
		return [yt_dlp_path]
	raise MediaPreparationError("Required tool not found on PATH: uvx or yt-dlp")


def _yt_dlp_request_args(args: argparse.Namespace) -> list[str]:
	request_args: list[str] = []
	if args.cookies:
		request_args.extend(["--cookies", args.cookies])
	if args.cookies_from_browser:
		request_args.extend(["--cookies-from-browser", args.cookies_from_browser])
	if args.proxy is not None:
		request_args.extend(["--proxy", args.proxy])
	if args.impersonate:
		request_args.extend(["--impersonate", args.impersonate])
	for raw_args in args.yt_dlp_extra_args or []:
		parts = shlex.split(raw_args)
		if not parts:
			raise MediaPreparationError("--yt-dlp-extra-args contained no arguments.")
		request_args.extend(parts)
	return request_args


def _yt_dlp_auth_network_manifest(args: argparse.Namespace) -> dict[str, Any]:
	return {
		"cookies": "provided" if args.cookies else None,
		"cookies_from_browser": "provided" if args.cookies_from_browser else None,
		"proxy": "provided" if args.proxy else ("direct" if args.proxy == "" else None),
		"impersonate": args.impersonate,
		"extra_args_count": len(args.yt_dlp_extra_args or []),
	}


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
	result = subprocess.run(cmd, text=True, capture_output=True)
	if check and result.returncode != 0:
		raise MediaPreparationError(_command_log(cmd, result))
	return result


def _command_log(cmd: list[str], result: subprocess.CompletedProcess[str]) -> str:
	return "\n".join(
		[
			"$ " + shlex.join(_redact_command(cmd)),
			f"returncode: {result.returncode}",
			"",
			"[stdout]",
			result.stdout,
			"",
			"[stderr]",
			result.stderr,
		]
	)


def _redact_command(cmd: list[str]) -> list[str]:
	redacted: list[str] = []
	redact_next_for = {"--cookies", "--cookies-from-browser", "--proxy"}
	i = 0
	while i < len(cmd):
		part = cmd[i]
		if part in redact_next_for:
			redacted.append(part)
			if i + 1 < len(cmd):
				redacted.append("<redacted>")
				i += 2
				continue
		if any(part.startswith(f"{option}=") for option in redact_next_for):
			option = part.split("=", 1)[0]
			redacted.append(f"{option}=<redacted>")
		else:
			redacted.append(part)
		i += 1
	return redacted


def _write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_json(payload: object) -> None:
	print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_json_or_text(stdout: str, stderr: str) -> Any:
	text = stdout.strip()
	if not text:
		text = stderr.strip()
	try:
		return json.loads(text)
	except json.JSONDecodeError:
		return {"raw_output": text}


def _height(item: dict[str, Any]) -> int | None:
	value = item.get("height")
	return value if isinstance(value, int) else None


def _string(value: Any) -> str:
	return value if isinstance(value, str) else ""


def _number(value: Any) -> float:
	if isinstance(value, int | float):
		return float(value)
	return 0.0


def _int(value: Any) -> int:
	return value if isinstance(value, int) else 0


def _maybe_float(value: Any) -> float | None:
	if isinstance(value, int | float):
		return float(value)
	if isinstance(value, str):
		try:
			return float(value)
		except ValueError:
			return None
	return None


if __name__ == "__main__":
	try:
		sys.exit(main())
	except MediaPreparationError as exc:
		print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
		sys.exit(1)
