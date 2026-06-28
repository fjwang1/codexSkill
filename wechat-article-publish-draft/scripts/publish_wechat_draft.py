#!/usr/bin/env python3
"""Create a WeChat public-account draft from local Markdown.

This script intentionally stops at draft creation. It never calls final publish.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import mimetypes
import os
import re
import ssl
import sys
import textwrap
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


API_BASE = "https://api.weixin.qq.com"
REPORT_SCHEMA_VERSION = "wechat-article-publish-draft.v1"
FORBIDDEN_ENDPOINT = "/cgi-bin/freepublish/submit"
DEFAULT_AUTHOR = "他山译读"
STYLE_SPEC_VERSION = "wechat-swiss-grid-v1"

STYLE = {
	"container": "max-width:100%;font-family:Arial,'Helvetica Neue',Helvetica,'PingFang SC','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.78;color:#1A1A1A;letter-spacing:0;text-align:left;background:#fff;",
	"h1": "font-size:28px;line-height:1.24;margin:32px 0 16px;font-weight:900;",
	"h2_wrap": "margin:44px 0 18px;padding-top:14px;border-top:3px solid #D9251D;",
	"h2": "font-size:22px;line-height:1.32;margin:0;font-weight:900;",
	"h3": "font-size:17px;line-height:1.48;margin:30px 0 12px;padding-left:10px;border-left:3px solid #D9251D;font-weight:900;",
	"paragraph": "margin:0 0 18px;",
	"lead": "margin:18px 0 26px;line-height:1.72;font-size:18px;font-weight:700;",
	"source": "margin:0 0 32px;padding:14px 0 14px 16px;border-left:3px solid #D9251D;color:#666;font-size:12px;line-height:1.7;",
	"quote": "margin:28px 0;padding:16px 0 16px 18px;border-left:4px solid #D9251D;font-size:18px;line-height:1.65;font-weight:700;",
	"ul": "padding-left:22px;margin:0 0 18px;",
	"ol": "padding-left:22px;margin:0 0 18px;",
	"li": "margin:6px 0;",
	"hr": "border:none;border-top:1px solid #E8E8E8;margin:32px 0;",
	"image_wrap": "margin:28px 0;",
	"image": "display:block;width:100%;max-width:100%;height:auto;margin:0;",
	"caption": "margin:8px 0 0;color:#666;font-size:12px;line-height:1.55;",
	"code": "font-family:Consolas,'Courier New',monospace;background:#F4F4F4;padding:1px 4px;font-size:14px;",
	"pre": "white-space:pre-wrap;background:#F4F4F4;padding:16px;font-size:14px;line-height:1.65;overflow-wrap:break-word;border-left:3px solid #D9251D;",
}

SKILL_DIR = Path(__file__).resolve().parents[1]
LOCAL_ENV_PATH = SKILL_DIR / ".env"

PUBLICATION_NAME_MAP = {
	"the economist": "经济学人",
	"economist": "经济学人",
	"financial times": "金融时报",
	"ft": "金融时报",
	"foreign policy": "外交政策",
	"foreign affairs": "外交事务",
	"the diplomat": "外交学者",
	"diplomat": "外交学者",
	"bloomberg": "彭博社",
	"bloomberg news": "彭博社",
	"bloomberg businessweek": "彭博商业周刊",
	"the new york times": "纽约时报",
	"new york times": "纽约时报",
	"nytimes": "纽约时报",
	"nyt": "纽约时报",
	"new york daily news": "纽约每日新闻",
	"the wall street journal": "华尔街日报",
	"wall street journal": "华尔街日报",
	"wsj": "华尔街日报",
	"the washington post": "华盛顿邮报",
	"washington post": "华盛顿邮报",
	"the guardian": "卫报",
	"guardian": "卫报",
	"reuters": "路透社",
	"associated press": "美联社",
	"ap": "美联社",
	"nikkei asia": "日经亚洲",
	"nikkei": "日本经济新闻",
	"the new yorker": "纽约客",
	"new yorker": "纽约客",
	"wired": "连线",
	"rest of world": "Rest of World",
	"south china morning post": "南华早报",
	"scmp": "南华早报",
	"los angeles times": "洛杉矶时报",
	"politico": "政客",
	"bbc": "英国广播公司",
	"cnn": "美国有线电视新闻网",
}

TITLE_SOURCE_PREFIX_RE = re.compile(r"^(?:《([^》]+)》|([^:：\n]{2,32}))\s*[:：]\s*(.+)$")


class DraftError(RuntimeError):
	pass


@dataclass
class UploadedImage:
	source: str
	url: str


@dataclass
class DraftResult:
	status: str
	draft_created: bool
	final_publish_clicked: bool
	article_dir: str | None
	article_markdown: str
	metadata_path: str | None
	cover_path: str
	title: str
	author: str
	digest: str
	content_source_url: str
	html_sha256: str
	payload_sha256: str
	style_version: str = STYLE_SPEC_VERSION
	public_ip: str | None = None
	bundle_manifest: str | None = None
	article_count: int = 1
	articles: list[dict[str, Any]] = field(default_factory=list)
	cover_media_id: str | None = None
	cover_url: str | None = None
	draft_media_id: str | None = None
	inline_images: list[UploadedImage] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)
	blockers: list[str] = field(default_factory=list)
	api_response: dict[str, Any] | None = None
	outputs: dict[str, str] = field(default_factory=dict)
	checked_at: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())

	def to_json(self) -> dict[str, Any]:
		return {
			"schema_version": REPORT_SCHEMA_VERSION,
			"status": self.status,
			"draft_created": self.draft_created,
			"final_publish_clicked": self.final_publish_clicked,
			"article_dir": self.article_dir,
			"article_markdown": self.article_markdown,
			"metadata_path": self.metadata_path,
			"cover_path": self.cover_path,
			"title": self.title,
			"author": self.author,
			"digest": self.digest,
			"content_source_url": self.content_source_url,
			"html_sha256": self.html_sha256,
			"payload_sha256": self.payload_sha256,
			"style_version": self.style_version,
			"public_ip": self.public_ip,
			"bundle_manifest": self.bundle_manifest,
			"article_count": self.article_count,
			"articles": self.articles,
			"cover_media_id": self.cover_media_id,
			"cover_url": self.cover_url,
			"draft_media_id": self.draft_media_id,
			"inline_images": [image.__dict__ for image in self.inline_images],
			"warnings": self.warnings,
			"blockers": self.blockers,
			"api_response": self.api_response,
			"outputs": self.outputs,
			"checked_at": self.checked_at,
		}


def parse_args() -> argparse.Namespace:
	load_local_env()
	parser = argparse.ArgumentParser(description="Create a WeChat public-account draft from Markdown.")
	source = parser.add_mutually_exclusive_group(required=True)
	source.add_argument("--bundle-manifest", type=Path, help="wechat_bundle_manifest.json for a multi-article WeChat draft.")
	source.add_argument("--article-dir", type=Path, help="Directory containing wechat/reviewed_article.md and cover/main_cover.png.")
	source.add_argument("--article-md", type=Path, help="Markdown file to publish as a draft.")
	parser.add_argument("--metadata", type=Path, help="Article metadata JSON. Defaults to <article-dir>/wechat/article_metadata.json.")
	parser.add_argument("--cover", type=Path, help="Cover image. Defaults to metadata cover_path or <article-dir>/cover/main_cover.png.")
	parser.add_argument("--output-dir", type=Path, help="Report output directory. Defaults to <article-dir>/publish or <article-md parent>/publish.")
	parser.add_argument("--title", help="Override title.")
	parser.add_argument("--author", help=f"Deprecated and ignored. Author is always {DEFAULT_AUTHOR}.")
	parser.add_argument("--digest", help="Override digest.")
	parser.add_argument("--content-source-url", help="Override 阅读原文 URL.")
	parser.add_argument("--keep-title-in-body", action="store_true", help="Keep the first Markdown H1 in the body.")
	parser.add_argument("--dry-run", action="store_true", help="Generate payload and reports without calling WeChat.")
	parser.add_argument("--live", action="store_true", help="Call WeChat APIs and create a draft.")
	parser.add_argument("--access-token", default=os.environ.get("WECHAT_ACCESS_TOKEN"), help="Existing WeChat access_token. Prefer env var.")
	parser.add_argument("--appid", default=os.environ.get("WECHAT_APP_ID"), help="WeChat appid. Prefer env var.")
	parser.add_argument("--secret", default=os.environ.get("WECHAT_APP_SECRET"), help="WeChat app secret. Prefer env var.")
	parser.add_argument("--force-refresh-token", action="store_true", help="Force refresh when using stable_token.")
	parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout seconds.")
	args = parser.parse_args()
	if args.dry_run == args.live:
		parser.error("Choose exactly one of --dry-run or --live.")
	return args


def load_local_env() -> None:
	if not LOCAL_ENV_PATH.exists():
		return
	for raw_line in LOCAL_ENV_PATH.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		value = value.strip().strip("\"'")
		if key in {"WECHAT_ACCESS_TOKEN", "WECHAT_APP_ID", "WECHAT_APP_SECRET"} and value:
			os.environ.setdefault(key, value)


def resolve_inputs(args: argparse.Namespace) -> tuple[Path | None, Path, Path | None, Path, Path]:
	article_dir: Path | None
	if args.article_dir:
		article_dir = args.article_dir.expanduser().resolve()
		article_md = article_dir / "wechat" / "reviewed_article.md"
	else:
		article_md = args.article_md.expanduser().resolve()
		article_dir = infer_article_dir(article_md)

	metadata_path = args.metadata.expanduser().resolve() if args.metadata else None
	if metadata_path is None and article_dir is not None:
		candidate = article_dir / "wechat" / "article_metadata.json"
		if candidate.exists():
			metadata_path = candidate

	metadata = load_json(metadata_path) if metadata_path else {}
	cover_path = args.cover.expanduser().resolve() if args.cover else None
	if cover_path is None and isinstance(metadata.get("cover_path"), str):
		cover_path = Path(metadata["cover_path"]).expanduser().resolve()
	if cover_path is None and article_dir is not None:
		cover_path = article_dir / "cover" / "main_cover.png"
	if cover_path is None:
		raise DraftError("Missing cover image. Provide --cover or metadata cover_path.")

	output_dir = args.output_dir.expanduser().resolve() if args.output_dir else None
	if output_dir is None:
		output_dir = (article_dir or article_md.parent) / "publish"

	return article_dir, article_md, metadata_path, cover_path, output_dir


def default_bundle_output_dir(bundle_manifest: Path) -> Path:
	if bundle_manifest.parent.name == "wechat_bundle":
		return bundle_manifest.parent.parent / "publish"
	return bundle_manifest.parent / "publish"


def bundle_run_dir(bundle_manifest: Path) -> Path:
	if bundle_manifest.parent.name == "wechat_bundle":
		return bundle_manifest.parent.parent
	return bundle_manifest.parent


def resolve_bundle_article_refs(bundle_manifest: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
	articles = manifest.get("articles")
	if isinstance(articles, list) and articles:
		return [resolve_bundle_article_ref(bundle_manifest, item, index) for index, item in enumerate(articles)]

	main_id = manifest.get("main_article_id")
	attached_ids = manifest.get("attached_article_ids", [])
	if not isinstance(main_id, str) or not main_id:
		raise DraftError("Bundle manifest must include articles[] or main_article_id.")
	if not isinstance(attached_ids, list):
		raise DraftError("Bundle manifest attached_article_ids must be a list.")
	ids = [main_id] + [str(item) for item in attached_ids]
	return [
		resolve_bundle_article_ref(
			bundle_manifest,
			{
				"candidate_id": article_id,
				"wechat_role": "main" if index == 0 else "attached",
			},
			index,
		)
		for index, article_id in enumerate(ids)
	]


def resolve_bundle_article_ref(bundle_manifest: Path, item: Any, index: int) -> dict[str, Any]:
	if not isinstance(item, dict):
		raise DraftError(f"Bundle manifest article at index {index} must be an object.")
	run_dir = bundle_run_dir(bundle_manifest)
	article_id = str(item.get("candidate_id") or item.get("article_id") or item.get("id") or "").strip()
	role = str(item.get("wechat_role") or item.get("role") or ("main" if index == 0 else "attached"))

	article_dir = resolve_optional_path(item, "article_dir", bundle_manifest.parent)
	if article_dir is None and article_id:
		matches = sorted((run_dir / "articles").glob(f"{article_id}_*"))
		if len(matches) == 1:
			article_dir = matches[0].resolve()
		elif len(matches) > 1:
			raise DraftError(f"Multiple article directories matched {article_id}: {matches}")
	if article_dir is None:
		wechat_path = first_existing_path(item, ["wechat_article_path", "article_markdown", "article_path", "markdown_path"], bundle_manifest.parent)
		if wechat_path is not None and wechat_path.parent.name == "wechat":
			article_dir = wechat_path.parent.parent

	article_md = first_existing_path(item, ["wechat_article_path", "article_markdown", "article_path", "markdown_path"], bundle_manifest.parent)
	if article_md is None and article_dir is not None:
		article_md = article_dir / "wechat" / "reviewed_article.md"
	if article_md is None:
		raise DraftError(f"Missing article Markdown path for bundle article {article_id or index}.")

	metadata_path = first_existing_path(item, ["metadata_path", "article_metadata_path"], bundle_manifest.parent)
	if metadata_path is None and article_dir is not None:
		metadata_path = article_dir / "wechat" / "article_metadata.json"

	metadata = load_json(metadata_path) if metadata_path and metadata_path.exists() else {}
	cover_path = first_existing_path(
		item,
		["wechat_upload_cover_path", "cover_path", "thumb_path", "thumbnail_path"],
		bundle_manifest.parent,
	)
	if cover_path is None:
		for metadata_key in ("wechat_upload_cover_path", "cover_path", "thumb_path", "thumbnail_path"):
			if isinstance(metadata.get(metadata_key), str):
				cover_path = Path(metadata[metadata_key]).expanduser().resolve()
				break
	if cover_path is None and article_dir is not None:
		for candidate in (
			article_dir / "cover" / "main_cover.jpg",
			article_dir / "cover" / "main_cover.png",
			article_dir / "cover" / "thumb_square_500x500.jpg",
			article_dir / "cover" / "thumb_square_500x500.png",
		):
			if candidate.exists():
				cover_path = candidate
				break
	if cover_path is None:
		raise DraftError(f"Missing cover/thumb path for bundle article {article_id or index}.")

	return {
		"candidate_id": article_id or metadata.get("candidate_id") or f"A{index + 1}",
		"wechat_role": role,
		"article_dir": str(article_dir) if article_dir else None,
		"article_md": str(article_md.expanduser().resolve()),
		"metadata_path": str(metadata_path.expanduser().resolve()) if metadata_path else None,
		"cover_path": str(cover_path.expanduser().resolve()),
	}


def resolve_optional_path(item: dict[str, Any], key: str, base_dir: Path) -> Path | None:
	value = item.get(key)
	if not isinstance(value, str) or not value.strip():
		return None
	path = Path(value).expanduser()
	if not path.is_absolute():
		path = base_dir / path
	return path.resolve()


def first_existing_path(item: dict[str, Any], keys: list[str], base_dir: Path) -> Path | None:
	for key in keys:
		path = resolve_optional_path(item, key, base_dir)
		if path is not None:
			return path
	return None


def infer_article_dir(article_md: Path) -> Path | None:
	parts = article_md.parts
	if len(parts) >= 2 and parts[-2] == "wechat":
		return article_md.parent.parent
	return None


def load_json(path: Path | None) -> dict[str, Any]:
	if path is None:
		return {}
	with path.open("r", encoding="utf-8") as f:
		data = json.load(f)
	if not isinstance(data, dict):
		raise DraftError(f"Expected JSON object in {path}")
	return data


def read_text(path: Path) -> str:
	if not path.exists():
		raise DraftError(f"Missing file: {path}")
	return path.read_text(encoding="utf-8")


def sha256_text(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def first_h1(markdown: str) -> str | None:
	for line in markdown.splitlines():
		match = re.match(r"^#\s+(.+?)\s*$", line)
		if match:
			return strip_inline_markdown(match.group(1)).strip()
	return None


def strip_first_h1(markdown: str) -> str:
	lines = markdown.splitlines()
	for index, line in enumerate(lines):
		if re.match(r"^#\s+.+", line):
			return "\n".join(lines[:index] + lines[index + 1 :]).lstrip()
	return markdown


def strip_inline_markdown(value: str) -> str:
	value = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
	value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
	value = re.sub(r"([*_`~])", "", value)
	return value


def truncate_utf8(value: str, max_bytes: int, max_chars: int | None = None) -> str:
	if max_chars is not None:
		value = value[:max_chars]
	while len(value.encode("utf-8")) > max_bytes:
		value = value[:-1]
	return value


def build_digest(markdown: str, override: str | None, metadata: dict[str, Any]) -> str:
	if override:
		return truncate_utf8(strip_inline_markdown(override.strip()), 120, 128)
	for key in ("digest", "summary", "description"):
		value = metadata.get(key)
		if isinstance(value, str) and value.strip():
			return truncate_utf8(strip_inline_markdown(value.strip()), 120, 128)
	plain_lines: list[str] = []
	for line in markdown.splitlines():
		stripped = line.strip()
		if (
			not stripped
			or stripped.startswith("#")
			or stripped.startswith(">")
			or re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", stripped)
		):
			continue
		plain_lines.append(strip_inline_markdown(stripped))
	plain = re.sub(r"\s+", " ", "".join(plain_lines)).strip()
	return truncate_utf8(plain, 120, 128)


def choose_author(args: argparse.Namespace, metadata: dict[str, Any]) -> str:
	return DEFAULT_AUTHOR


def choose_source_url(args: argparse.Namespace, metadata: dict[str, Any]) -> str:
	if args.content_source_url is None:
		return ""
	return str(args.content_source_url).strip()[:1024]


def choose_title(args: argparse.Namespace, metadata: dict[str, Any], markdown: str) -> str:
	title = args.title or metadata.get("title") or first_h1(markdown)
	if not title:
		raise DraftError("Missing title. Provide --title, metadata title, or a Markdown H1.")
	title = strip_inline_markdown(str(title)).strip()
	if not title:
		raise DraftError("Title is empty after Markdown cleanup.")
	return title[:32]


def apply_source_title_prefix(title: str, metadata: dict[str, Any]) -> str:
	publication = chinese_publication_name(metadata)
	if not publication:
		return title
	match = TITLE_SOURCE_PREFIX_RE.match(title)
	body = title
	if match:
		prefix = (match.group(1) or match.group(2) or "").strip()
		if normalize_publication_name(prefix) == publication:
			body = match.group(3).strip()
	if not body:
		return title
	return f"{publication}：{body}"


def chinese_publication_name(metadata: dict[str, Any]) -> str | None:
	for key in ("source_publication_zh", "publication_zh", "publication_cn"):
		value = metadata.get(key)
		if isinstance(value, str) and value.strip():
			return value.strip().strip("《》")
	for key in ("source_publication", "publication", "publisher", "source"):
		value = metadata.get(key)
		if isinstance(value, str) and value.strip():
			return normalize_publication_name(value)
	return None


def normalize_publication_name(publication: str) -> str | None:
	cleaned = re.sub(r"\s+", " ", publication.strip().strip("《》"))
	if not cleaned:
		return None
	key = cleaned.lower()
	if key in PUBLICATION_NAME_MAP:
		return PUBLICATION_NAME_MAP[key]
	if not re.search(r"[A-Za-z]", cleaned):
		return cleaned
	return None


def markdown_to_wechat_html(markdown: str) -> str:
	blocks: list[str] = []
	lines = markdown.splitlines()
	i = 0
	lead_used = False
	while i < len(lines):
		line = lines[i].rstrip()
		if not line.strip():
			i += 1
			continue
		if line.startswith("```"):
			code_lines: list[str] = []
			i += 1
			while i < len(lines) and not lines[i].startswith("```"):
				code_lines.append(lines[i])
				i += 1
			i += 1
			code = html.escape("\n".join(code_lines))
			blocks.append(f'<pre style="{STYLE["pre"]}">{code}</pre>')
			continue
		if line.startswith("#"):
			level = min(len(line) - len(line.lstrip("#")), 3)
			text = inline_markdown_to_html(line[level:].strip())
			if level == 1:
				blocks.append(f'<h1 style="{STYLE["h1"]}">{text}</h1>')
			elif level == 2:
				blocks.append(f'<section style="{STYLE["h2_wrap"]}"><h2 style="{STYLE["h2"]}">{text}</h2></section>')
			else:
				blocks.append(f'<h3 style="{STYLE["h3"]}">{text}</h3>')
			i += 1
			continue
		if line.startswith(">"):
			quote_lines: list[str] = []
			while i < len(lines) and lines[i].startswith(">"):
				quote_lines.append(lines[i].lstrip(">").strip())
				i += 1
			raw_quote = " ".join(quote_lines)
			quote = "<br/>".join(inline_markdown_to_html(x) for x in quote_lines)
			if is_source_note(raw_quote):
				blocks.append(f'<section style="{STYLE["source"]}">{quote}</section>')
			else:
				blocks.append(f'<blockquote style="{STYLE["quote"]}">{quote}</blockquote>')
			continue
		image = markdown_image_line(line)
		if image:
			alt, src = image
			blocks.append(render_image_block(alt, src))
			i += 1
			continue
		if re.match(r"^\s*[-*]\s+", line):
			items: list[str] = []
			while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
				item = re.sub(r"^\s*[-*]\s+", "", lines[i]).strip()
				items.append(f'<li style="{STYLE["li"]}">{inline_markdown_to_html(item)}</li>')
				i += 1
			blocks.append(f'<ul style="{STYLE["ul"]}">{"".join(items)}</ul>')
			continue
		if re.match(r"^\s*\d+\.\s+", line):
			items = []
			while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
				item = re.sub(r"^\s*\d+\.\s+", "", lines[i]).strip()
				items.append(f'<li style="{STYLE["li"]}">{inline_markdown_to_html(item)}</li>')
				i += 1
			blocks.append(f'<ol style="{STYLE["ol"]}">{"".join(items)}</ol>')
			continue
		if line.strip() in {"---", "***"}:
			blocks.append(f'<hr style="{STYLE["hr"]}"/>')
			i += 1
			continue

		paragraph_lines = [line.strip()]
		i += 1
		while i < len(lines) and lines[i].strip() and not starts_special_block(lines[i]):
			paragraph_lines.append(lines[i].strip())
			i += 1
		raw_paragraph = " ".join(paragraph_lines)
		paragraph = inline_markdown_to_html(raw_paragraph)
		if is_source_note(raw_paragraph):
			blocks.append(f'<section style="{STYLE["source"]}">{paragraph}</section>')
		elif not lead_used:
			blocks.append(f'<p style="{STYLE["lead"]}">{paragraph}</p>')
			lead_used = True
		else:
			blocks.append(f'<p style="{STYLE["paragraph"]}">{paragraph}</p>')

	return f'<section style="{STYLE["container"]}" data-codex-style="{STYLE_SPEC_VERSION}">\n' + "\n".join(blocks) + "\n</section>"


def starts_special_block(line: str) -> bool:
	stripped = line.strip()
	return (
		stripped.startswith("#")
		or stripped.startswith(">")
		or stripped.startswith("```")
		or markdown_image_line(stripped) is not None
		or stripped in {"---", "***"}
		or re.match(r"^[-*]\s+", stripped) is not None
		or re.match(r"^\d+\.\s+", stripped) is not None
	)


def markdown_image_line(value: str) -> tuple[str, str] | None:
	match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", value.strip())
	if not match:
		return None
	return match.group(1).strip(), match.group(2).strip()


def is_source_note(value: str) -> bool:
	stripped = strip_inline_markdown(value).strip()
	return bool(re.match(r"^(来源|原文|原载|本文|译注|出处|Source|Original)(：|:)", stripped, flags=re.IGNORECASE))


def render_image_block(alt: str, src: str) -> str:
	escaped_alt = html.escape(alt, quote=True)
	escaped_src = html.escape(src, quote=True)
	image = f'<img src="{escaped_src}" alt="{escaped_alt}" style="{STYLE["image"]}"/>'
	caption = f'<p style="{STYLE["caption"]}">{inline_markdown_to_html(alt)}</p>' if should_show_caption(alt) else ""
	return f'<section style="{STYLE["image_wrap"]}">{image}{caption}</section>'


def should_show_caption(alt: str) -> bool:
	alt = alt.strip()
	if not alt or len(alt) <= 2:
		return False
	return alt.lower() not in {"image", "img", "photo", "picture", "cover", "图片", "图"}


def inline_markdown_to_html(value: str) -> str:
	placeholders: list[str] = []

	def stash(replacement: str) -> str:
		placeholders.append(replacement)
		return f"\u0000{len(placeholders) - 1}\u0000"

	def image_repl(match: re.Match[str]) -> str:
		return stash(render_image_block(match.group(1).strip(), match.group(2).strip()))

	def link_repl(match: re.Match[str]) -> str:
		label = html.escape(match.group(1))
		url = html.escape(match.group(2), quote=True)
		return stash(f'<a href="{url}">{label}</a>')

	value = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image_repl, value)
	value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, value)
	value = html.escape(value)
	value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
	value = re.sub(r"`([^`]+)`", rf'<code style="{STYLE["code"]}">\1</code>', value)
	for index, replacement in enumerate(placeholders):
		value = value.replace(f"\u0000{index}\u0000", replacement)
	return value


def find_markdown_image_paths(markdown: str, base_dir: Path) -> list[tuple[str, Path]]:
	images: list[tuple[str, Path]] = []
	for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
		raw = match.group(1).strip()
		parsed = urllib.parse.urlparse(raw)
		if parsed.scheme in {"http", "https"}:
			continue
		path = Path(urllib.parse.unquote(raw))
		if not path.is_absolute():
			path = (base_dir / path).resolve()
		images.append((raw, path))
	return images


def markdown_local_images_to_file_urls(markdown: str, base_dir: Path) -> str:
	def repl(match: re.Match[str]) -> str:
		alt = match.group(1)
		raw = match.group(2).strip()
		parsed = urllib.parse.urlparse(raw)
		if parsed.scheme in {"http", "https", "file"}:
			return match.group(0)
		path = Path(urllib.parse.unquote(raw))
		if not path.is_absolute():
			path = (base_dir / path).resolve()
		return f"![{alt}]({path.as_uri()})"

	return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, markdown)


def replace_markdown_image_url(markdown: str, original: str, uploaded_url: str) -> str:
	escaped_original = re.escape(original)
	return re.sub(rf"(!\[[^\]]*\]\(){escaped_original}(\))", rf"\g<1>{uploaded_url}\2", markdown)


def find_external_markdown_images(markdown: str) -> list[str]:
	urls: list[str] = []
	for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
		raw = match.group(1).strip()
		if urllib.parse.urlparse(raw).scheme in {"http", "https"}:
			urls.append(raw)
	return urls


def get_access_token(args: argparse.Namespace) -> str:
	if args.access_token:
		return args.access_token
	if not args.appid or not args.secret:
		raise DraftError("Missing credentials. Set WECHAT_ACCESS_TOKEN, or WECHAT_APP_ID and WECHAT_APP_SECRET.")
	payload = {
		"grant_type": "client_credential",
		"appid": args.appid,
		"secret": args.secret,
		"force_refresh": bool(args.force_refresh_token),
	}
	try:
		response = http_json("POST", f"{API_BASE}/cgi-bin/stable_token", payload, args.timeout)
	except DraftError:
		query = urllib.parse.urlencode({
			"grant_type": "client_credential",
			"appid": args.appid,
			"secret": args.secret,
		})
		response = http_json("GET", f"{API_BASE}/cgi-bin/token?{query}", None, args.timeout)
	token = response.get("access_token")
	if not isinstance(token, str) or not token:
		raise DraftError(f"Failed to obtain access_token: {redact_response(response)}")
	return token


def http_json(method: str, url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
	assert FORBIDDEN_ENDPOINT not in url
	data: bytes | None = None
	headers: dict[str, str] = {"User-Agent": "codex-wechat-draft-skill/1.0"}
	if payload is not None:
		data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
		headers["Content-Type"] = "application/json; charset=utf-8"
	request = urllib.request.Request(url, data=data, headers=headers, method=method)
	try:
		with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
			body = response.read().decode("utf-8", errors="replace")
	except urllib.error.HTTPError as exc:
		body = exc.read().decode("utf-8", errors="replace")
		raise DraftError(f"HTTP {exc.code} from {safe_url(url)}: {body}") from exc
	except urllib.error.URLError as exc:
		raise DraftError(f"Network error calling {safe_url(url)}: {exc}") from exc
	try:
		result = json.loads(body)
	except json.JSONDecodeError as exc:
		raise DraftError(f"Non-JSON response from {safe_url(url)}: {body[:500]}") from exc
	if isinstance(result, dict) and result.get("errcode") not in (None, 0):
		raise DraftError(f"WeChat API error from {safe_url(url)}: {redact_response(result)}")
	if not isinstance(result, dict):
		raise DraftError(f"Unexpected JSON response from {safe_url(url)}: {result!r}")
	return result


def http_multipart(url: str, fields: dict[str, str], file_field: str, file_path: Path, timeout: float) -> dict[str, Any]:
	assert FORBIDDEN_ENDPOINT not in url
	if not file_path.exists():
		raise DraftError(f"Missing upload file: {file_path}")
	boundary = f"----codexwechat{int(time.time() * 1000)}"
	body = bytearray()
	for name, value in fields.items():
		body.extend(f"--{boundary}\r\n".encode())
		body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
		body.extend(value.encode("utf-8"))
		body.extend(b"\r\n")
	mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
	body.extend(f"--{boundary}\r\n".encode())
	body.extend(f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode())
	body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode())
	body.extend(file_path.read_bytes())
	body.extend(b"\r\n")
	body.extend(f"--{boundary}--\r\n".encode())
	request = urllib.request.Request(
		url,
		data=bytes(body),
		headers={
			"Content-Type": f"multipart/form-data; boundary={boundary}",
			"User-Agent": "codex-wechat-draft-skill/1.0",
		},
		method="POST",
	)
	try:
		with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
			raw = response.read().decode("utf-8", errors="replace")
	except urllib.error.HTTPError as exc:
		raw = exc.read().decode("utf-8", errors="replace")
		raise DraftError(f"HTTP {exc.code} from {safe_url(url)}: {raw}") from exc
	except urllib.error.URLError as exc:
		raise DraftError(f"Network error calling {safe_url(url)}: {exc}") from exc
	try:
		result = json.loads(raw)
	except json.JSONDecodeError as exc:
		raise DraftError(f"Non-JSON response from {safe_url(url)}: {raw[:500]}") from exc
	if isinstance(result, dict) and result.get("errcode") not in (None, 0):
		raise DraftError(f"WeChat API error from {safe_url(url)}: {redact_response(result)}")
	if not isinstance(result, dict):
		raise DraftError(f"Unexpected JSON response from {safe_url(url)}: {result!r}")
	return result


def upload_inline_images(markdown: str, base_dir: Path, access_token: str, timeout: float) -> tuple[str, list[UploadedImage], list[str]]:
	uploaded: list[UploadedImage] = []
	warnings: list[str] = []
	for original, path in find_markdown_image_paths(markdown, base_dir):
		if not path.exists():
			warnings.append(f"Inline image not found and left unchanged: {original}")
			continue
		if path.stat().st_size > 1_000_000:
			warnings.append(f"Inline image is over 1MB and may be rejected: {path}")
		url = f"{API_BASE}/cgi-bin/media/uploadimg?{urllib.parse.urlencode({'access_token': access_token})}"
		response = http_multipart(url, {}, "media", path, timeout)
		uploaded_url = response.get("url")
		if not isinstance(uploaded_url, str) or not uploaded_url:
			raise DraftError(f"uploadimg response missing url: {redact_response(response)}")
		markdown = replace_markdown_image_url(markdown, original, uploaded_url)
		uploaded.append(UploadedImage(source=str(path), url=uploaded_url))
	return markdown, uploaded, warnings


def upload_cover(cover_path: Path, access_token: str, timeout: float) -> tuple[str, str | None, dict[str, Any]]:
	query = urllib.parse.urlencode({"access_token": access_token, "type": "image"})
	url = f"{API_BASE}/cgi-bin/material/add_material?{query}"
	response = http_multipart(url, {}, "media", cover_path, timeout)
	media_id = response.get("media_id")
	if not isinstance(media_id, str) or not media_id:
		raise DraftError(f"add_material response missing media_id: {redact_response(response)}")
	cover_url = response.get("url") if isinstance(response.get("url"), str) else None
	return media_id, cover_url, response


def create_draft(payload: dict[str, Any], access_token: str, timeout: float) -> dict[str, Any]:
	url = f"{API_BASE}/cgi-bin/draft/add?{urllib.parse.urlencode({'access_token': access_token})}"
	response = http_json("POST", url, payload, timeout)
	if "media_id" not in response:
		raise DraftError(f"draft/add response missing media_id: {redact_response(response)}")
	return response


def build_article_item(title: str, author: str, digest: str, content: str, source_url: str, thumb_media_id: str) -> dict[str, Any]:
	return {
		"article_type": "news",
		"title": title,
		"author": author,
		"digest": digest,
		"content": content,
		"content_source_url": source_url,
		"thumb_media_id": thumb_media_id,
		"need_open_comment": 0,
		"only_fans_can_comment": 0,
		"pic_crop_235_1": "0_0_1_1",
		"pic_crop_1_1": "0.287222_0_0.712778_1",
	}


def build_payload(title: str, author: str, digest: str, content: str, source_url: str, thumb_media_id: str) -> dict[str, Any]:
	return {"articles": [build_article_item(title, author, digest, content, source_url, thumb_media_id)]}


def validate_payload(payload: dict[str, Any], cover_path: Path) -> list[str]:
	warnings: list[str] = []
	articles = payload.get("articles")
	if not isinstance(articles, list) or not articles:
		return ["Payload has no articles."]
	article = articles[0]
	if not isinstance(article, dict):
		return ["Payload first article is not an object."]
	title = str(article.get("title", ""))
	author = str(article.get("author", ""))
	digest = str(article.get("digest", ""))
	content = str(article.get("content", ""))
	source_url = str(article.get("content_source_url", ""))
	if len(title) > 32:
		warnings.append(f"Title is over 32 characters: {len(title)}")
	if len(author) > 16:
		warnings.append(f"Author is over 16 characters: {len(author)}")
	if len(digest) > 128:
		warnings.append(f"Digest is over 128 characters: {len(digest)}")
	if len(digest.encode("utf-8")) > 120:
		warnings.append(f"Digest is over 120 UTF-8 bytes: {len(digest.encode('utf-8'))}")
	if len(content) >= 20_000:
		warnings.append(f"Content is near/over WeChat's 20,000 character limit: {len(content)}")
	if len(content.encode("utf-8")) >= 1_000_000:
		warnings.append(f"Content is near/over WeChat's 1MB limit: {len(content.encode('utf-8'))} bytes")
	if len(source_url.encode("utf-8")) > 1024:
		warnings.append(f"content_source_url is over 1KB: {len(source_url.encode('utf-8'))} bytes")
	if cover_path.exists() and cover_path.stat().st_size > 10_000_000:
		warnings.append(f"Cover image is over 10MB and may be rejected: {cover_path}")
	return warnings


def redacted_payload(payload: dict[str, Any]) -> dict[str, Any]:
	return json.loads(json.dumps(payload, ensure_ascii=False))


def redact_response(response: dict[str, Any]) -> dict[str, Any]:
	redacted = dict(response)
	for key in ("access_token", "refresh_token", "secret"):
		if key in redacted:
			redacted[key] = "***REDACTED***"
	return redacted


def safe_url(url: str) -> str:
	parsed = urllib.parse.urlsplit(url)
	query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
	redacted_keys = {"access_token", "secret", "appsecret", "component_appsecret"}
	safe_query = urllib.parse.urlencode([(k, "***REDACTED***" if k.lower() in redacted_keys else v) for k, v in query])
	return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, parsed.fragment))


def discover_public_ip(timeout: float) -> tuple[str | None, str | None]:
	for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
		request = urllib.request.Request(url, headers={"User-Agent": "codex-wechat-draft-skill/1.0"})
		try:
			with urllib.request.urlopen(request, timeout=min(timeout, 10), context=ssl.create_default_context()) as response:
				body = response.read().decode("utf-8", errors="replace").strip()
		except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
			continue
		if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", body):
			return body, None
	return None, "Could not discover public IP; check API IP allowlist manually before live calls."


def write_outputs(
	output_dir: Path,
	result: DraftResult,
	html_content: str,
	payload: dict[str, Any],
	preview_html_content: str | None = None,
) -> None:
	output_dir.mkdir(parents=True, exist_ok=True)
	html_path = output_dir / "wechat_article.html"
	preview_path = output_dir / "wechat_article.preview.html"
	payload_path = output_dir / "draft_payload.redacted.json"
	report_json_path = output_dir / "wechat_draft_report.json"
	report_md_path = output_dir / "wechat_draft_report.md"
	html_path.write_text(html_content, encoding="utf-8")
	preview_path.write_text(
		render_preview_html(result.title or "WeChat Article Preview", preview_html_content or html_content),
		encoding="utf-8",
	)
	payload_path.write_text(json.dumps(redacted_payload(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	result.outputs = {
		"html": str(html_path),
		"preview_html": str(preview_path),
		"payload_redacted": str(payload_path),
		"report_json": str(report_json_path),
		"report_markdown": str(report_md_path),
	}
	report_json_path.write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	report_md_path.write_text(render_markdown_report(result), encoding="utf-8")


def render_preview_html(title: str, html_content: str) -> str:
	escaped_title = html.escape(title)
	return textwrap.dedent(
		f"""\
		<!doctype html>
		<html lang="zh-CN">
		<head>
		  <meta charset="utf-8">
		  <meta name="viewport" content="width=device-width, initial-scale=1">
		  <title>{escaped_title}</title>
		  <style>
		    body {{
		      margin: 0;
		      background: #E8E8E8;
		      color: #1A1A1A;
		      font-family: Arial, "Helvetica Neue", Helvetica, "PingFang SC", "Microsoft YaHei", sans-serif;
		    }}
		    .phone {{
		      box-sizing: border-box;
		      width: min(414px, 100vw);
		      min-height: 100vh;
		      margin: 0 auto;
		      padding: 28px 22px 48px;
		      background: #ffffff;
		    }}
		    .meta {{
		      margin: 0 0 28px;
		      padding: 0 0 20px;
		      border-bottom: 3px solid #1A1A1A;
		    }}
		    .title {{
		      margin: 16px 0 14px;
		      color: #1A1A1A;
		      font-size: 30px;
		      line-height: 1.18;
		      font-weight: 900;
		      letter-spacing: 0;
		    }}
		    .byline {{
		      margin: 0;
		      color: #666666;
		      font-size: 11px;
		      line-height: 1.6;
		      letter-spacing: 1.5px;
		      text-transform: uppercase;
		    }}
		    .red-rule {{
		      display: block;
		      width: 56px;
		      height: 3px;
		      background: #D9251D;
		      margin: 0 0 12px;
		    }}
		  </style>
		</head>
		<body>
		  <main class="phone">
		    <header class="meta">
		      <span class="red-rule"></span>
		      <h1 class="title">{escaped_title}</h1>
		      <p class="byline">{html.escape(DEFAULT_AUTHOR)} / {STYLE_SPEC_VERSION}</p>
		    </header>
		    {html_content}
		  </main>
		</body>
		</html>
		"""
	)


def render_markdown_report(result: DraftResult) -> str:
	lines = [
		"# WeChat Draft Report",
		"",
		f"- Status: `{result.status}`",
		f"- Draft created: `{str(result.draft_created).lower()}`",
		"- Final publish clicked: `false`",
		f"- Title: {result.title}",
		f"- Author: {result.author or '(empty)'}",
		f"- Style version: `{result.style_version}`",
		f"- Public IP: {result.public_ip or '(unavailable)'}",
		f"- Article count: `{result.article_count}`",
		f"- Article markdown: `{result.article_markdown}`",
		f"- Cover: `{result.cover_path}`",
	]
	if result.bundle_manifest:
		lines.append(f"- Bundle manifest: `{result.bundle_manifest}`")
	if result.draft_media_id:
		lines.append(f"- Draft media_id: `{result.draft_media_id}`")
	if result.cover_media_id:
		lines.append(f"- Cover media_id: `{result.cover_media_id}`")
	if result.articles:
		lines.extend(["", "## Articles"])
		for article in result.articles:
			lines.append(
				f"- {article.get('candidate_id')}: {article.get('title')} "
				f"({article.get('wechat_role')}, cover_media_id={article.get('cover_media_id') or 'n/a'})"
			)
	if result.outputs:
		lines.extend(["", "## Outputs"])
		for key, value in result.outputs.items():
			lines.append(f"- {key}: `{value}`")
	if result.warnings:
		lines.extend(["", "## Warnings"])
		lines.extend(f"- {warning}" for warning in result.warnings)
	if result.blockers:
		lines.extend(["", "## Blockers"])
		lines.extend(f"- {blocker}" for blocker in result.blockers)
	lines.extend(["", "This skill intentionally stops at WeChat draft creation. It did not call final publish."])
	return "\n".join(lines) + "\n"


def run_bundle(args: argparse.Namespace) -> int:
	bundle_manifest = args.bundle_manifest.expanduser().resolve()
	output_dir = args.output_dir.expanduser().resolve() if args.output_dir else default_bundle_output_dir(bundle_manifest)
	payload: dict[str, Any] = {}
	combined_html = ""
	combined_preview_html = ""
	result: DraftResult | None = None
	try:
		manifest = load_json(bundle_manifest)
		article_refs = resolve_bundle_article_refs(bundle_manifest, manifest)
		if not article_refs:
			raise DraftError("Bundle manifest resolved zero articles.")
		public_ip, public_ip_warning = discover_public_ip(args.timeout)
		warnings: list[str] = []
		if public_ip_warning:
			warnings.append(public_ip_warning)

		access_token = get_access_token(args) if args.live else None
		payload_articles: list[dict[str, Any]] = []
		article_reports: list[dict[str, Any]] = []
		all_inline_images: list[UploadedImage] = []
		html_parts: list[str] = []
		preview_html_parts: list[str] = []
		first_title = ""
		first_digest = ""
		first_source_url = ""
		first_cover_path = ""
		first_cover_media_id: str | None = None
		first_cover_url: str | None = None

		for index, ref in enumerate(article_refs):
			article_md = Path(ref["article_md"])
			metadata_path = Path(ref["metadata_path"]) if ref.get("metadata_path") else None
			cover_path = Path(ref["cover_path"])
			if not article_md.exists():
				raise DraftError(f"Missing bundle article Markdown: {article_md}")
			if not cover_path.exists():
				raise DraftError(f"Missing bundle cover image: {cover_path}")
			metadata = load_json(metadata_path) if metadata_path else {}
			original_markdown = read_text(article_md)
			body_markdown = original_markdown if args.keep_title_in_body else strip_first_h1(original_markdown)
			title = choose_title(args, metadata, original_markdown)
			author = choose_author(args, metadata)
			digest = build_digest(body_markdown, args.digest if index == 0 else None, metadata)
			source_url = choose_source_url(args, metadata)
			uploaded_images: list[UploadedImage] = []
			if args.live:
				assert access_token is not None
				body_markdown, uploaded_images, upload_warnings = upload_inline_images(body_markdown, article_md.parent, access_token, args.timeout)
				warnings.extend(upload_warnings)
				cover_media_id, cover_url, _cover_response = upload_cover(cover_path, access_token, args.timeout)
			else:
				cover_media_id = f"DRY_RUN_COVER_MEDIA_ID_{index + 1}"
				cover_url = None
			html_content = markdown_to_wechat_html(body_markdown)
			preview_markdown = body_markdown if args.live else markdown_local_images_to_file_urls(body_markdown, article_md.parent)
			preview_html_content = markdown_to_wechat_html(preview_markdown)
			item = build_article_item(title, author, digest, html_content, source_url, cover_media_id)
			payload_articles.append(item)
			warnings.extend(validate_payload({"articles": [item]}, cover_path))
			all_inline_images.extend(uploaded_images)
			html_parts.append(f"<!-- {ref['candidate_id']} {title} -->\n{html_content}")
			preview_html_parts.append(f"<!-- {ref['candidate_id']} {title} -->\n{preview_html_content}")
			article_report = {
				"candidate_id": ref["candidate_id"],
				"wechat_role": ref["wechat_role"],
				"title": title,
				"author": author,
				"digest": digest,
				"article_markdown": str(article_md),
				"metadata_path": str(metadata_path) if metadata_path else None,
				"cover_path": str(cover_path),
				"cover_media_id": cover_media_id if args.live else None,
				"cover_url": cover_url,
				"content_source_url": source_url,
				"html_sha256": sha256_text(html_content),
			}
			article_reports.append(article_report)
			if index == 0:
				first_title = title
				first_digest = digest
				first_source_url = source_url
				first_cover_path = str(cover_path)
				first_cover_media_id = cover_media_id if args.live else None
				first_cover_url = cover_url

		payload = {"articles": payload_articles}
		payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
		combined_html = "\n<hr/>\n".join(html_parts)
		combined_preview_html = "\n<hr/>\n".join(preview_html_parts)
		api_response = None
		draft_media_id = None
		status = "DRY_RUN_OK"
		draft_created = False
		if args.live:
			assert access_token is not None
			api_response = create_draft(payload, access_token, args.timeout)
			draft_media_id = str(api_response["media_id"])
			status = "DRAFT_CREATED"
			draft_created = True

		result = DraftResult(
			status=status,
			draft_created=draft_created,
			final_publish_clicked=False,
			article_dir=None,
			article_markdown=str(bundle_manifest),
			metadata_path=None,
			cover_path=first_cover_path,
			title=first_title,
			author=DEFAULT_AUTHOR,
			digest=first_digest,
			content_source_url=first_source_url,
			html_sha256=sha256_text(combined_html),
			payload_sha256=sha256_text(payload_json),
			public_ip=public_ip,
			bundle_manifest=str(bundle_manifest),
			article_count=len(article_reports),
			articles=article_reports,
			cover_media_id=first_cover_media_id,
			cover_url=first_cover_url,
			draft_media_id=draft_media_id,
			inline_images=all_inline_images,
			warnings=warnings,
			api_response=redact_response(api_response) if api_response else None,
		)
		write_outputs(output_dir, result, combined_html, payload, preview_html_content=combined_preview_html)
		print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
		return 0
	except DraftError as exc:
		blocker = str(exc)
		status = "BLOCKED" if "Missing credentials" in blocker else "FAILED"
		if result is None:
			result = DraftResult(
				status=status,
				draft_created=False,
				final_publish_clicked=False,
				article_dir=None,
				article_markdown=str(bundle_manifest),
				metadata_path=None,
				cover_path="",
				title="",
				author=DEFAULT_AUTHOR,
				digest="",
				content_source_url="",
				html_sha256=sha256_text(combined_html),
				payload_sha256=sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
				bundle_manifest=str(bundle_manifest),
				blockers=[blocker],
			)
		else:
			result.status = status
			result.blockers.append(blocker)
		write_outputs(output_dir, result, combined_html, payload, preview_html_content=combined_preview_html or None)
		print(json.dumps(result.to_json(), ensure_ascii=False, indent=2), file=sys.stderr)
		return 2


def main() -> int:
	args = parse_args()
	if args.bundle_manifest:
		return run_bundle(args)
	article_dir: Path | None = None
	output_dir: Path | None = None
	payload: dict[str, Any] = {}
	html_content = ""
	preview_html_content = ""
	result: DraftResult | None = None
	try:
		article_dir, article_md, metadata_path, cover_path, output_dir = resolve_inputs(args)
		if not article_md.exists():
			raise DraftError(f"Missing article Markdown: {article_md}")
		if not cover_path.exists():
			raise DraftError(f"Missing cover image: {cover_path}")
		metadata = load_json(metadata_path)
		original_markdown = read_text(article_md)
		body_markdown = original_markdown if args.keep_title_in_body else strip_first_h1(original_markdown)
		title = choose_title(args, metadata, original_markdown)
		author = choose_author(args, metadata)
		digest = build_digest(body_markdown, args.digest, metadata)
		source_url = choose_source_url(args, metadata)
		warnings = []
		public_ip, public_ip_warning = discover_public_ip(args.timeout)
		if public_ip_warning:
			warnings.append(public_ip_warning)
		external_images = find_external_markdown_images(body_markdown)
		if external_images:
			warnings.append("External Markdown image URLs may be filtered by WeChat: " + ", ".join(external_images))

		inline_images: list[UploadedImage] = []
		cover_media_id = "DRY_RUN_COVER_MEDIA_ID"
		cover_url: str | None = None
		access_token: str | None = None
		html_content = markdown_to_wechat_html(body_markdown)
		preview_markdown = body_markdown if args.live else markdown_local_images_to_file_urls(body_markdown, article_md.parent)
		preview_html_content = markdown_to_wechat_html(preview_markdown)
		payload = build_payload(title, author, digest, html_content, source_url, cover_media_id)
		warnings.extend(validate_payload(payload, cover_path))

		result = DraftResult(
			status="PREPARED",
			draft_created=False,
			final_publish_clicked=False,
			article_dir=str(article_dir) if article_dir else None,
			article_markdown=str(article_md),
			metadata_path=str(metadata_path) if metadata_path else None,
			cover_path=str(cover_path),
			title=title,
			author=author,
			digest=digest,
			content_source_url=source_url,
			html_sha256=sha256_text(html_content),
			payload_sha256=sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
			public_ip=public_ip,
			warnings=warnings,
		)

		if args.live:
			access_token = get_access_token(args)
			body_markdown, inline_images, upload_warnings = upload_inline_images(body_markdown, article_md.parent, access_token, args.timeout)
			warnings.extend(upload_warnings)
			cover_media_id, cover_url, _cover_response = upload_cover(cover_path, access_token, args.timeout)

		html_content = markdown_to_wechat_html(body_markdown)
		preview_markdown = body_markdown if args.live else markdown_local_images_to_file_urls(body_markdown, article_md.parent)
		preview_html_content = markdown_to_wechat_html(preview_markdown)
		payload = build_payload(title, author, digest, html_content, source_url, cover_media_id)
		payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)

		status = "DRY_RUN_OK"
		draft_created = False
		draft_media_id = None
		api_response = None
		if args.live:
			assert access_token is not None
			api_response = create_draft(payload, access_token, args.timeout)
			draft_media_id = str(api_response["media_id"])
			status = "DRAFT_CREATED"
			draft_created = True

		result.status = status
		result.draft_created = draft_created
		result.html_sha256 = sha256_text(html_content)
		result.payload_sha256 = sha256_text(payload_json)
		result.cover_media_id = cover_media_id if args.live else None
		result.cover_url = cover_url
		result.draft_media_id = draft_media_id
		result.inline_images = inline_images
		result.warnings = warnings
		result.api_response = redact_response(api_response) if api_response else None
		write_outputs(output_dir, result, html_content, payload, preview_html_content=preview_html_content)
		print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
		return 0
	except DraftError as exc:
		blocker = str(exc)
		status = "BLOCKED" if "Missing credentials" in blocker else "FAILED"
		if output_dir is None:
			output_dir = Path.cwd() / "publish"
		if result is None:
			result = DraftResult(
				status=status,
				draft_created=False,
				final_publish_clicked=False,
				article_dir=str(article_dir) if article_dir else None,
				article_markdown=str(getattr(args, "article_md", "") or ""),
				metadata_path=str(getattr(args, "metadata", "") or "") or None,
				cover_path=str(getattr(args, "cover", "") or ""),
				title=str(getattr(args, "title", "") or ""),
				author=str(getattr(args, "author", "") or ""),
				digest=str(getattr(args, "digest", "") or ""),
				content_source_url=str(getattr(args, "content_source_url", "") or ""),
				html_sha256=sha256_text(html_content),
				payload_sha256=sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
				public_ip=None,
				blockers=[blocker],
			)
		else:
			result.status = status
			result.blockers.append(blocker)
		write_outputs(output_dir, result, html_content, payload, preview_html_content=preview_html_content or None)
		print(json.dumps(result.to_json(), ensure_ascii=False, indent=2), file=sys.stderr)
		return 2


if __name__ == "__main__":
	raise SystemExit(main())
