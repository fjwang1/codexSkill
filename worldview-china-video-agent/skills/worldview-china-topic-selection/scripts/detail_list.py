#!/usr/bin/env python3
import argparse
from collections.abc import Iterable
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
SKILL_DIR = Path(__file__).resolve().parents[1]
_DURATION_RE = re.compile(
	r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def main() -> int:
	args = _parse_args()
	api_key = args.api_key or _load_api_key()
	if not api_key:
		return _fail("Set YOUTUBE_API_KEY / GOOGLE_API_KEY or configure the skill .env before calling detailList.")

	video_ids = _dedupe(_collect_video_ids(args))
	if not video_ids:
		return _fail("Provide at least one video id.")

	published_after = _parse_datetime(args.published_after) if args.published_after else None
	videos: list[dict[str, Any]] = []
	try:
		for batch in _chunks(video_ids, 50):
			payload = _get_json(
				YOUTUBE_VIDEOS_URL,
				{
					"part": "snippet,contentDetails,statistics,status",
					"id": ",".join(batch),
					"key": api_key,
				},
			)
			for item in payload.get("items", []):
				if isinstance(item, dict):
					videos.append(
						_video_from_item(
							item,
							published_after,
							args.min_duration_seconds,
							args.max_duration_seconds,
						)
					)
	except RuntimeError as exc:
		return _fail(str(exc))

	_print_json(
		{
			"tool": "detailList",
			"quota_units_estimate": math.ceil(len(video_ids) / 50),
			"requested_count": len(video_ids),
			"returned_count": len(videos),
			"videos": videos,
		}
	)
	return 0


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Call YouTube videos.list and return JSON video details.")
	parser.add_argument("video_ids", nargs="*")
	parser.add_argument("--ids", help="Comma-separated video ids.")
	parser.add_argument("--published-after")
	parser.add_argument("--min-duration-seconds", type=int, default=600)
	parser.add_argument("--max-duration-seconds", type=int, default=1800)
	parser.add_argument("--api-key")
	args = parser.parse_args()
	if args.min_duration_seconds < 1:
		parser.error("--min-duration-seconds must be positive")
	if args.max_duration_seconds <= args.min_duration_seconds:
		parser.error("--max-duration-seconds must be greater than --min-duration-seconds")
	return args


def _collect_video_ids(args: argparse.Namespace) -> list[str]:
	values = list(args.video_ids)
	if args.ids:
		values.extend(args.ids.split(","))
	return [value.strip() for value in values if value.strip()]


def _load_api_key() -> str | None:
	for name in ("YOUTUBE_API_KEY", "GOOGLE_API_KEY"):
		value = os.getenv(name)
		if value:
			return value

	for path in (SKILL_DIR / ".env", SKILL_DIR / ".env.local"):
		value = _load_api_key_from_env_file(path)
		if value:
			return value
	return None


def _load_api_key_from_env_file(path: Path) -> str | None:
	if not path.exists():
		return None
	for line in path.read_text(encoding="utf-8").splitlines():
		cleaned = line.strip()
		if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
			continue
		name, value = cleaned.split("=", 1)
		if name.strip() in {"YOUTUBE_API_KEY", "GOOGLE_API_KEY"}:
			return value.strip().strip("\"'")
	return None


def _video_from_item(
	item: dict[str, Any],
	published_after: datetime | None,
	min_duration_seconds: int,
	max_duration_seconds: int,
) -> dict[str, Any]:
	snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
	content_details = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
	statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
	video_id = str(item.get("id") or "")
	duration = content_details.get("duration")
	duration_seconds = _parse_youtube_duration(duration if isinstance(duration, str) else None)
	published_at = _parse_datetime(snippet.get("publishedAt")) if isinstance(snippet.get("publishedAt"), str) else None
	title = str(snippet.get("title") or "")
	description = str(snippet.get("description") or "")
	hard_filter = {
		"published_after_passed": published_after is None or (published_at is not None and published_at >= published_after),
		"min_duration_passed": duration_seconds is not None and duration_seconds > min_duration_seconds,
		"max_duration_passed": duration_seconds is not None and duration_seconds <= max_duration_seconds,
	}
	hard_filter["passed"] = all(hard_filter.values())
	view_count = _parse_int(statistics.get("viewCount"))
	like_count = _parse_int(statistics.get("likeCount"))
	comment_count = _parse_int(statistics.get("commentCount"))
	engagement_score = _engagement_score(view_count, comment_count, like_count)

	return {
		"video_id": video_id,
		"url": f"https://www.youtube.com/watch?v={video_id}",
		"title": title,
		"description": description,
		"channel": snippet.get("channelTitle") or "",
		"channel_id": snippet.get("channelId"),
		"published_at": snippet.get("publishedAt"),
		"duration": duration,
		"duration_seconds": duration_seconds,
		"view_count": view_count,
		"like_count": like_count,
		"comment_count": comment_count,
		"thumbnail_url": _best_thumbnail_url(snippet.get("thumbnails")),
		"hard_filter": hard_filter,
		"engagement_score": engagement_score if hard_filter["passed"] else 0,
		"metadata_score": None,
		"detail_score": None,
		"detail_signals": {
			"engagement_priority": "view_count > comment_count > like_count",
			"metadata_for_ai_review": True,
			"raw_engagement_score": engagement_score,
		},
	}


def _engagement_score(
	view_count: int | None,
	comment_count: int | None,
	like_count: int | None,
) -> float:
	score = 0.0
	score += min(4.5, math.log10((view_count or 0) + 1) * 0.9)
	score += min(2.0, math.log10((comment_count or 0) + 1) * 0.8)
	score += min(0.5, math.log10((like_count or 0) + 1) * 0.15)
	return round(max(0.0, min(7.0, score)), 1)


def _get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
	request = Request(f"{url}?{urlencode(params)}", headers={"Accept": "application/json"})
	try:
		with urlopen(request, timeout=30) as response:
			payload = json.loads(response.read().decode("utf-8"))
	except HTTPError as exc:
		body = exc.read().decode("utf-8", errors="replace")
		message = _extract_error_message(body) or f"YouTube API HTTP {exc.code}"
		raise RuntimeError(message) from exc
	except (URLError, TimeoutError, json.JSONDecodeError) as exc:
		raise RuntimeError(f"YouTube detailList request failed: {exc}") from exc
	if not isinstance(payload, dict):
		raise RuntimeError("YouTube detailList returned non-object JSON.")
	return payload


def _parse_youtube_duration(value: str | None) -> int | None:
	if not value:
		return None
	match = _DURATION_RE.match(value)
	if not match:
		return None
	parts = {name: int(raw_value or 0) for name, raw_value in match.groupdict().items()}
	return parts["days"] * 86_400 + parts["hours"] * 3_600 + parts["minutes"] * 60 + parts["seconds"]


def _parse_datetime(value: str) -> datetime:
	parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=UTC)
	return parsed.astimezone(UTC)


def _parse_int(value: Any) -> int | None:
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def _best_thumbnail_url(thumbnails: Any) -> str | None:
	if not isinstance(thumbnails, dict):
		return None
	for key in ("maxres", "standard", "high", "medium", "default"):
		item = thumbnails.get(key)
		if isinstance(item, dict) and isinstance(item.get("url"), str):
			return item["url"]
	return None


def _extract_error_message(body: str) -> str | None:
	try:
		payload = json.loads(body)
	except json.JSONDecodeError:
		return None
	error = payload.get("error") if isinstance(payload, dict) else None
	if isinstance(error, dict) and error.get("message"):
		return str(error["message"])
	return None


def _dedupe(values: Iterable[str]) -> list[str]:
	result: list[str] = []
	for value in values:
		if value not in result:
			result.append(value)
	return result


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
	for index in range(0, len(values), size):
		yield values[index:index + size]


def _print_json(payload: object) -> None:
	print(json.dumps(payload, ensure_ascii=False, indent=2))


def _fail(message: str) -> int:
	_print_json({"ok": False, "error": message})
	return 1


if __name__ == "__main__":
	sys.exit(main())
