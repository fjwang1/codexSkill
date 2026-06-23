#!/usr/bin/env python3
import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
SKILL_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
	args = _parse_args()
	api_key = args.api_key or _load_api_key()
	if not api_key:
		return _fail("Set YOUTUBE_API_KEY / GOOGLE_API_KEY or configure the skill .env before calling searchList.")

	params = {
		"part": "snippet",
		"type": "video",
		"q": args.query,
		"maxResults": str(args.max_results),
		"order": args.order,
		"key": api_key,
	}
	if args.published_after:
		params["publishedAfter"] = _format_rfc3339(args.published_after)
	if args.region_code:
		params["regionCode"] = args.region_code
	if args.relevance_language:
		params["relevanceLanguage"] = args.relevance_language
	if args.safe_search:
		params["safeSearch"] = args.safe_search

	try:
		payload = _get_json(YOUTUBE_SEARCH_URL, params)
	except RuntimeError as exc:
		return _fail(str(exc))

	videos = []
	for item in payload.get("items", []):
		if not isinstance(item, dict):
			continue
		item_id = item.get("id", {})
		snippet = item.get("snippet", {})
		if not isinstance(item_id, dict) or not isinstance(snippet, dict):
			continue
		video_id = item_id.get("videoId")
		if not isinstance(video_id, str):
			continue
		videos.append(
			{
				"video_id": video_id,
				"url": f"https://www.youtube.com/watch?v={video_id}",
				"title": snippet.get("title") or "",
				"description": snippet.get("description") or "",
				"channel": snippet.get("channelTitle") or "",
				"channel_id": snippet.get("channelId"),
				"published_at": snippet.get("publishedAt"),
				"thumbnail_url": _best_thumbnail_url(snippet.get("thumbnails")),
			}
		)

	_print_json(
		{
			"tool": "searchList",
			"query": args.query,
			"quota_units_estimate": 100,
			"next_page_token": payload.get("nextPageToken"),
			"videos": videos,
		}
	)
	return 0


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Call YouTube search.list and return JSON video candidates.")
	parser.add_argument("--query", required=True)
	parser.add_argument("--max-results", type=int, default=20)
	parser.add_argument("--published-after")
	parser.add_argument("--order", choices=["relevance", "date", "viewCount", "rating"], default="relevance")
	parser.add_argument("--region-code")
	parser.add_argument("--relevance-language")
	parser.add_argument("--safe-search", choices=["moderate", "none", "strict"])
	parser.add_argument("--api-key")
	args = parser.parse_args()
	if args.max_results < 1 or args.max_results > 50:
		parser.error("--max-results must be between 1 and 50")
	return args


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
		raise RuntimeError(f"YouTube searchList request failed: {exc}") from exc
	if not isinstance(payload, dict):
		raise RuntimeError("YouTube searchList returned non-object JSON.")
	return payload


def _extract_error_message(body: str) -> str | None:
	try:
		payload = json.loads(body)
	except json.JSONDecodeError:
		return None
	error = payload.get("error") if isinstance(payload, dict) else None
	if isinstance(error, dict) and error.get("message"):
		return str(error["message"])
	return None


def _format_rfc3339(value: str) -> str:
	parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=UTC)
	return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _best_thumbnail_url(thumbnails: Any) -> str | None:
	if not isinstance(thumbnails, dict):
		return None
	for key in ("maxres", "standard", "high", "medium", "default"):
		item = thumbnails.get(key)
		if isinstance(item, dict) and isinstance(item.get("url"), str):
			return item["url"]
	return None


def _print_json(payload: object) -> None:
	print(json.dumps(payload, ensure_ascii=False, indent=2))


def _fail(message: str) -> int:
	_print_json({"ok": False, "error": message})
	return 1


if __name__ == "__main__":
	sys.exit(main())
