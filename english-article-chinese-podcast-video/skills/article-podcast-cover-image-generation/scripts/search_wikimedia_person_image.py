#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


USER_AGENT = "CodexCoverImageSearch/1.0 (local skill; contact: local-user)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"


def fetch_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
	if params:
		url = f"{url}?{urllib.parse.urlencode(params)}"
	req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
	with urllib.request.urlopen(req, timeout=30) as resp:
		return json.loads(resp.read().decode("utf-8"))


def download(url: str, path: Path) -> None:
	req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
	with urllib.request.urlopen(req, timeout=60) as resp:
		path.write_bytes(resp.read())


def safe_slug(text: str) -> str:
	slug = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text, flags=re.UNICODE).strip("_")
	return slug[:80] or "image"


def first_text(value: Any) -> str | None:
	if isinstance(value, dict):
		for key in ("value", "*"):
			if key in value and isinstance(value[key], str):
				return value[key]
	if isinstance(value, str):
		return value
	return None


@dataclass
class Candidate:
	source: str
	title: str
	qid: str | None
	entity_label: str | None
	image_url: str | None
	thumb_url: str | None
	width: int | None
	height: int | None
	mime: str | None
	license_short_name: str | None
	license_url: str | None
	artist: str | None
	credit: str | None
	description: str | None
	score: int
	local_path: str | None = None

	def to_json(self) -> dict[str, Any]:
		return self.__dict__


def commons_file_info(title: str, thumb_width: int) -> dict[str, Any] | None:
	data = fetch_json(
		COMMONS_API,
		{
			"action": "query",
			"format": "json",
			"titles": title,
			"prop": "imageinfo",
			"iiprop": "url|mime|size|extmetadata",
			"iiurlwidth": thumb_width,
		},
	)
	pages = data.get("query", {}).get("pages", {})
	for page in pages.values():
		imageinfo = page.get("imageinfo") or []
		if imageinfo:
			return imageinfo[0]
	return None


def metadata_value(meta: dict[str, Any], key: str) -> str | None:
	return first_text((meta.get(key) or {}))


def candidate_from_file(
	*,
	title: str,
	source: str,
	qid: str | None,
	entity_label: str | None,
	score: int,
	thumb_width: int,
) -> Candidate | None:
	info = commons_file_info(title, thumb_width)
	if not info:
		return None
	meta = info.get("extmetadata") or {}
	width = info.get("width")
	height = info.get("height")
	return Candidate(
		source=source,
		title=title,
		qid=qid,
		entity_label=entity_label,
		image_url=info.get("url"),
		thumb_url=info.get("thumburl") or info.get("url"),
		width=int(width) if width is not None else None,
		height=int(height) if height is not None else None,
		mime=info.get("mime"),
		license_short_name=metadata_value(meta, "LicenseShortName"),
		license_url=metadata_value(meta, "LicenseUrl"),
		artist=metadata_value(meta, "Artist"),
		credit=metadata_value(meta, "Credit"),
		description=metadata_value(meta, "ImageDescription") or metadata_value(meta, "ObjectName"),
		score=score,
	)


def search_wikidata_entities(name: str, language: str, limit: int) -> list[dict[str, Any]]:
	data = fetch_json(
		WIKIDATA_API,
		{
			"action": "wbsearchentities",
			"format": "json",
			"language": language,
			"search": name,
			"type": "item",
			"limit": limit,
		},
	)
	return list(data.get("search") or [])


def wikidata_p18(qid: str) -> str | None:
	data = fetch_json(WIKIDATA_ENTITY.format(qid=qid))
	entity = data.get("entities", {}).get(qid, {})
	claims = entity.get("claims", {}).get("P18") or []
	if not claims:
		return None
	value = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
	if isinstance(value, str):
		return value
	return None


def commons_search(query: str, limit: int, thumb_width: int) -> list[Candidate]:
	data = fetch_json(
		COMMONS_API,
		{
			"action": "query",
			"format": "json",
			"generator": "search",
			"gsrsearch": query,
			"gsrnamespace": 6,
			"gsrlimit": limit,
			"prop": "imageinfo",
			"iiprop": "url|mime|size|extmetadata",
			"iiurlwidth": thumb_width,
		},
	)
	candidates: list[Candidate] = []
	pages = data.get("query", {}).get("pages", {})
	for page in pages.values():
		title = page.get("title")
		imageinfo = (page.get("imageinfo") or [{}])[0]
		if not title or not imageinfo:
			continue
		meta = imageinfo.get("extmetadata") or {}
		width = imageinfo.get("width")
		height = imageinfo.get("height")
		candidates.append(
			Candidate(
				source="commons_search",
				title=title,
				qid=None,
				entity_label=None,
				image_url=imageinfo.get("url"),
				thumb_url=imageinfo.get("thumburl") or imageinfo.get("url"),
				width=int(width) if width is not None else None,
				height=int(height) if height is not None else None,
				mime=imageinfo.get("mime"),
				license_short_name=metadata_value(meta, "LicenseShortName"),
				license_url=metadata_value(meta, "LicenseUrl"),
				artist=metadata_value(meta, "Artist"),
				credit=metadata_value(meta, "Credit"),
				description=metadata_value(meta, "ImageDescription") or metadata_value(meta, "ObjectName"),
				score=40,
			)
		)
	return candidates


def rank_candidate(candidate: Candidate) -> int:
	score = candidate.score
	if candidate.width and candidate.height:
		area = candidate.width * candidate.height
		if area >= 1_000_000:
			score += 20
		elif area >= 400_000:
			score += 10
		ratio = candidate.width / max(1, candidate.height)
		if 0.55 <= ratio <= 1.35:
			score += 8
		if candidate.height >= candidate.width:
			score += 5
	if candidate.license_short_name:
		score += 8
	if candidate.image_url:
		score += 4
	return score


def rerank_with_role_keywords(candidate: Candidate, role_keywords: list[str]) -> int:
	score = candidate.score
	if not role_keywords:
		return score
	haystack = " ".join(
		part or ""
		for part in [
			candidate.title,
			candidate.entity_label,
			candidate.description,
			candidate.credit,
		]
	).lower()
	matches = [keyword for keyword in role_keywords if keyword.lower() in haystack]
	if matches:
		score += 28 + len(matches) * 7
	else:
		score -= 22
	return score


def main() -> None:
	parser = argparse.ArgumentParser(description="Search Wikidata/Wikimedia Commons for a public-person cover portrait.")
	parser.add_argument("--name", required=True, help="Person name, e.g. 'Ma Ning' or '马宁'")
	parser.add_argument("--out-dir", required=True, type=Path)
	parser.add_argument("--language", default="en", help="Wikidata search language, default: en")
	parser.add_argument("--limit", type=int, default=5)
	parser.add_argument("--thumb-width", type=int, default=1800)
	parser.add_argument("--role-keywords", default="", help="Comma-separated role/context keywords, e.g. 'referee,football,FIFA,World Cup'.")
	parser.add_argument("--download-best", action="store_true", help="Download the top candidate preview image.")
	args = parser.parse_args()

	args.out_dir.mkdir(parents=True, exist_ok=True)
	candidates: list[Candidate] = []

	for entity in search_wikidata_entities(args.name, args.language, args.limit):
		qid = entity.get("id")
		label = entity.get("label")
		if not qid:
			continue
		filename = wikidata_p18(qid)
		if not filename:
			continue
		title = "File:" + filename.replace(" ", "_")
		candidate = candidate_from_file(
			title=title,
			source="wikidata_p18",
			qid=qid,
			entity_label=label,
			score=85,
			thumb_width=args.thumb_width,
		)
		if candidate:
			candidates.append(candidate)

	for query in (f'"{args.name}" portrait', f'"{args.name}"', f'{args.name}'):
		candidates.extend(commons_search(query, max(3, args.limit), args.thumb_width))

	seen: set[str] = set()
	unique: list[Candidate] = []
	for candidate in candidates:
		key = candidate.title
		if key in seen:
			continue
		seen.add(key)
		candidate.score = rank_candidate(candidate)
		unique.append(candidate)
	unique.sort(key=lambda item: item.score, reverse=True)

	role_keywords = [item.strip() for item in args.role_keywords.split(",") if item.strip()]
	if role_keywords:
		for candidate in unique:
			candidate.score = rerank_with_role_keywords(candidate, role_keywords)
		unique.sort(key=lambda item: item.score, reverse=True)

	if args.download_best and unique:
		best = unique[0]
		url = best.thumb_url or best.image_url
		if url:
			ext = ".jpg"
			if best.mime == "image/png":
				ext = ".png"
			path = args.out_dir / f"best_{safe_slug(args.name)}{ext}"
			download(url, path)
			best.local_path = str(path)

	result = {
		"query": args.name,
		"language": args.language,
		"candidate_count": len(unique),
		"candidates": [candidate.to_json() for candidate in unique],
		"notes": [
			"Prefer wikidata_p18 results for named public figures.",
			"Check license_short_name, license_url, attribution and personality/publicity-right concerns before publishing.",
			"Do not use random web-search images without a traceable source and reuse rights.",
		],
	}
	out_path = args.out_dir / "wikimedia_person_image_candidates.json"
	out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print(out_path)
	if unique and unique[0].local_path:
		print(unique[0].local_path)
	if not unique:
		sys.exit(1)


if __name__ == "__main__":
	main()
