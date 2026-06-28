#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


VISIBLE_SOURCE_PATTERNS = (
	r"^来源[:：]",
	r"^原文[:：]",
	r"^原载[:：]",
	r"^本文[:：]",
	r"^出处[:：]",
	r"^Source[:：]",
	r"^Original[:：]",
	r"编译自",
)

FABRICATED_REPORTING_PATTERNS = (
	r"原创报道",
	r"本报记者",
	r"我采访",
	r"我们采访",
	r"我在现场",
	r"我们在现场",
	r"我来到",
	r"我们来到",
	r"我走访",
	r"我们走访",
)

EXPECTED_SELECTION_SOURCES = {
	"Bloomberg / Bloomberg Businessweek",
	"The Economist",
	"Financial Times",
	"The New York Times / The New York Times Magazine",
	"The New Yorker",
	"WIRED",
	"The Wall Street Journal",
	"Rest of World",
	"The Atlantic",
	"MIT Technology Review",
	"Foreign Affairs / Foreign Policy",
	"Reuters Special Reports / Reuters Graphics / Reuters Investigates",
	"The Guardian / Guardian Long Read / features / investigations / analysis",
	"Harper's Magazine",
	"London Review of Books",
	"New York Review of Books",
	"Noema Magazine",
	"Aeon / Psyche",
	"Quanta Magazine",
	"ProPublica",
}

REQUIRED_IMAGE_GENERATION_PROVIDER = "image_gen"
IMAGE_GENERATION_PROVIDER_FIELDS = ("generation_provider", "generated_by", "generation_tool")
IMAGE_GEN_OUTPUT_ROOT = Path.home() / ".codex" / "generated_images"
IMAGE_GEN_SOURCE_PATH_FIELDS = ("original_generated_image_path", "image_gen_source_path", "generated_image_path")
SOURCE_PUBLICATION_PREFIX_ALIASES = {
	"bloomberg",
	"bloombergbusinessweek",
	"businessweek",
	"彭博",
	"彭博商业周刊",
	"theeconomist",
	"economist",
	"经济学人",
	"financialtimes",
	"ft",
	"金融时报",
	"thenewyorktimes",
	"newyorktimes",
	"nytimes",
	"nyt",
	"纽约时报",
	"thenewyorker",
	"newyorker",
	"纽约客",
	"wired",
	"连线",
	"thewallstreetjournal",
	"wallstreetjournal",
	"wsj",
	"华尔街日报",
	"restofworld",
	"theatlantic",
	"atlantic",
	"大西洋月刊",
	"mittechnologyreview",
	"technologyreview",
	"麻省理工科技评论",
	"foreignaffairs",
	"foreignpolicy",
	"外交事务",
	"外交政策",
	"reuters",
	"路透",
	"theguardian",
	"guardian",
	"卫报",
	"harpersmagazine",
	"harpers",
	"哈珀",
	"londonreviewofbooks",
	"lrb",
	"伦敦书评",
	"newyorkreviewofbooks",
	"nyrb",
	"纽约书评",
	"noemamagazine",
	"noema",
	"aeon",
	"psyche",
	"quantamagazine",
	"quanta",
	"量子杂志",
	"propublica",
}


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _fail(errors: list[str], message: str) -> None:
	errors.append(message)


def _count_h2(markdown: str) -> int:
	return len(re.findall(r"(?m)^##\s+.+$", markdown))


def _has_lead_image_before_first_h2(markdown: str) -> bool:
	lead_index: int | None = None
	first_h2_index: int | None = None
	for index, line in enumerate(markdown.splitlines()):
		stripped = line.strip()
		if lead_index is None and re.match(r"^!\[头图\]\(\.\./illustrations/lead_00_.+_wechat_2400x1600\.jpg\)\s*$", stripped):
			lead_index = index
		if first_h2_index is None and re.match(r"^##\s+.+$", stripped):
			first_h2_index = index
		if lead_index is not None and first_h2_index is not None:
			break
	return lead_index is not None and (first_h2_index is None or lead_index < first_h2_index)


def _has_visible_source(markdown: str) -> bool:
	for pattern in VISIBLE_SOURCE_PATTERNS:
		if re.search(pattern, markdown, flags=re.MULTILINE):
			return True
	return False


def _has_fabricated_reporting_claim(markdown: str) -> bool:
	for pattern in FABRICATED_REPORTING_PATTERNS:
		if re.search(pattern, markdown):
			return True
	return False


def _source_prefix_key(value: Any) -> str:
	return re.sub(r"[\s·•'’._\-—–]+", "", str(value or "").strip().casefold())


def _source_publication_aliases(*values: Any) -> set[str]:
	aliases = set(SOURCE_PUBLICATION_PREFIX_ALIASES)
	for value in values:
		for part in re.split(r"\s*(?:/|｜|\||,|，)\s*", str(value or "")):
			key = _source_prefix_key(part)
			if key:
				aliases.add(key)
	return aliases


def _article_title_has_source_prefix(title: str, *, metadata: dict[str, Any], article: dict[str, Any]) -> bool:
	match = re.match(r"^\s*([^:：]{2,32})\s*[:：]\s*.+$", title)
	if not match:
		return False
	prefix_key = _source_prefix_key(match.group(1))
	source_aliases = _source_publication_aliases(
		metadata.get("source_publication"),
		metadata.get("source_publication_zh"),
		article.get("source_publication"),
		article.get("source_publication_zh"),
	)
	return prefix_key in source_aliases


def _title_anchor_parts(anchor: Any) -> list[str]:
	return [
		part.strip()
		for part in re.split(r"\s*(?:/|｜|\||,|，|;|；)\s*", str(anchor or ""))
		if part.strip()
	]


def _title_contains_anchor(title: str, anchor: Any) -> bool:
	parts = _title_anchor_parts(anchor)
	return bool(parts) and any(part in title for part in parts)


def _provider_value(value: Any) -> str:
	return str(value or "").strip().lower()


def _records_image_gen_provider(manifest_item: dict[str, Any]) -> bool:
	return any(
		_provider_value(manifest_item.get(field)) == REQUIRED_IMAGE_GENERATION_PROVIDER
		for field in IMAGE_GENERATION_PROVIDER_FIELDS
	)


def _is_relative_to(path: Path, parent: Path) -> bool:
	try:
		path.relative_to(parent)
	except ValueError:
		return False
	return True


def _image_gen_source_path(manifest_item: dict[str, Any]) -> Path | None:
	for field in IMAGE_GEN_SOURCE_PATH_FIELDS:
		value = manifest_item.get(field)
		if not value:
			continue
		path = Path(str(value)).expanduser()
		if path.exists():
			return path.resolve()
	return None


def _check_image_gen_source_lineage(
	manifest_item: dict[str, Any],
	*,
	candidate_id: str,
	label: str,
	errors: list[str],
) -> None:
	source_path = _image_gen_source_path(manifest_item)
	if source_path is None:
		fields = ", ".join(IMAGE_GEN_SOURCE_PATH_FIELDS)
		_fail(errors, f"{candidate_id}: {label} must record an existing original image_gen source path in one of {fields}")
		return
	if not _is_relative_to(source_path, IMAGE_GEN_OUTPUT_ROOT.resolve()):
		_fail(
			errors,
			f"{candidate_id}: {label} source path is not under image_gen output root {IMAGE_GEN_OUTPUT_ROOT}: {source_path}",
		)


def _check_image_gen_cover_manifest(
	cover_manifest: dict[str, Any],
	*,
	candidate_id: str,
	errors: list[str],
) -> None:
	if not _records_image_gen_provider(cover_manifest):
		fields = ", ".join(IMAGE_GENERATION_PROVIDER_FIELDS)
		_fail(errors, f"{candidate_id}: cover manifest must record {fields}={REQUIRED_IMAGE_GENERATION_PROVIDER!r}")
	_check_image_gen_source_lineage(cover_manifest, candidate_id=candidate_id, label="cover", errors=errors)


def _check_image_gen_illustrations_manifest(
	illustrations_manifest: dict[str, Any],
	*,
	candidate_id: str,
	require_lead_image: bool,
	errors: list[str],
) -> None:
	if not _records_image_gen_provider(illustrations_manifest):
		fields = ", ".join(IMAGE_GENERATION_PROVIDER_FIELDS)
		_fail(errors, f"{candidate_id}: illustrations manifest top level must record {fields}={REQUIRED_IMAGE_GENERATION_PROVIDER!r}")

	items = illustrations_manifest.get("items")
	if items is None:
		items = illustrations_manifest.get("images")
	if not isinstance(items, list) or not items:
		_fail(errors, f"{candidate_id}: illustrations manifest must include non-empty items[] with image_gen provenance")
		return

	for position, item in enumerate(items, start=1):
		if not isinstance(item, dict):
			_fail(errors, f"{candidate_id}: illustration item #{position} must be an object")
			continue
		if not _records_image_gen_provider(item):
			chapter_index = item.get("chapter_index", position)
			fields = ", ".join(IMAGE_GENERATION_PROVIDER_FIELDS)
			_fail(errors, f"{candidate_id}: illustration item chapter_index={chapter_index} must record {fields}={REQUIRED_IMAGE_GENERATION_PROVIDER!r}")
		_check_image_gen_source_lineage(
			item,
			candidate_id=candidate_id,
			label=f"illustration item chapter_index={item.get('chapter_index', position)}",
			errors=errors,
		)

	if require_lead_image:
		lead_image = illustrations_manifest.get("lead_image")
		if not isinstance(lead_image, dict):
			_fail(errors, f"{candidate_id}: illustrations manifest must include lead_image when lead images are required")
			return
		if not illustrations_manifest.get("has_lead_image") or int(illustrations_manifest.get("lead_image_count") or 0) != 1:
			_fail(errors, f"{candidate_id}: illustrations manifest must record has_lead_image=true and lead_image_count=1")
		if not _records_image_gen_provider(lead_image):
			fields = ", ".join(IMAGE_GENERATION_PROVIDER_FIELDS)
			_fail(errors, f"{candidate_id}: lead_image must record {fields}={REQUIRED_IMAGE_GENERATION_PROVIDER!r}")
		_check_image_gen_source_lineage(lead_image, candidate_id=candidate_id, label="lead_image", errors=errors)
		inline_path = lead_image.get("inline_path")
		if not inline_path or not Path(str(inline_path)).exists():
			_fail(errors, f"{candidate_id}: lead_image inline_path is missing or does not exist")


def _article_dir_for(article: dict[str, Any], article_path: Path) -> Path:
	article_dir = article.get("article_dir")
	if article_dir:
		return Path(str(article_dir)).expanduser()
	return article_path.parent.parent


def _path_from_record(
	article: dict[str, Any],
	metadata: dict[str, Any],
	field: str,
	default_path: Path,
) -> Path:
	value = article.get(field) or metadata.get(field)
	if value:
		return Path(str(value)).expanduser()
	return default_path


def _require_file(path: Path, *, candidate_id: str, label: str, errors: list[str]) -> bool:
	if path.exists():
		return True
	_fail(errors, f"{candidate_id}: missing {label}: {path}")
	return False


def _require_status(
	record: dict[str, Any],
	key: str,
	*,
	candidate_id: str,
	label: str,
	errors: list[str],
) -> None:
	if record.get(key) != "PASS":
		_fail(errors, f"{candidate_id}: {label}.{key}={record.get(key)!r}, expected 'PASS'")


def _check_china_perspective_artifacts(
	article: dict[str, Any],
	metadata: dict[str, Any],
	markdown: str,
	article_path: Path,
	*,
	candidate_id: str,
	errors: list[str],
) -> None:
	article_dir = _article_dir_for(article, article_path)
	translation_dir = article_dir / "translation"
	plan_path = _path_from_record(
		article,
		metadata,
		"china_perspective_adaptation_plan_path",
		translation_dir / "china_perspective_adaptation_plan.json",
	)
	version_path = _path_from_record(
		article,
		metadata,
		"china_perspective_version_path",
		translation_dir / "china_perspective_version.md",
	)
	adaptation_path = _path_from_record(
		article,
		metadata,
		"china_perspective_adaptation_result_path",
		translation_dir / "china_perspective_adaptation_result.json",
	)
	coverage_path = _path_from_record(
		article,
		metadata,
		"china_perspective_coverage_result_path",
		translation_dir / "china_perspective_coverage_result.json",
	)

	required_files = (
		(plan_path, "China-perspective adaptation plan"),
		(version_path, "China-perspective version"),
		(adaptation_path, "China-perspective adaptation result"),
		(coverage_path, "China-perspective coverage result"),
	)
	files_ok = True
	for path, label in required_files:
		files_ok = _require_file(path, candidate_id=candidate_id, label=label, errors=errors) and files_ok
	if not files_ok:
		return

	plan = _read_json(plan_path)
	adaptation = _read_json(adaptation_path)
	coverage = _read_json(coverage_path)

	if plan.get("content_mode") != "china_perspective_full_adaptation":
		_fail(errors, f"{candidate_id}: adaptation plan content_mode={plan.get('content_mode')!r}")
	if plan.get("source_based") is not True:
		_fail(errors, f"{candidate_id}: adaptation plan source_based must be true")
	if plan.get("original_reporting") is not False:
		_fail(errors, f"{candidate_id}: adaptation plan original_reporting must be false")

	if adaptation.get("content_mode") != "china_perspective_full_adaptation":
		_fail(errors, f"{candidate_id}: adaptation content_mode={adaptation.get('content_mode')!r}")
	if adaptation.get("source_based") is not True:
		_fail(errors, f"{candidate_id}: adaptation source_based must be true")
	if adaptation.get("original_reporting") is not False:
		_fail(errors, f"{candidate_id}: adaptation original_reporting must be false")
	for key in (
		"status",
		"readability_status",
		"china_perspective_status",
		"structure_status",
		"localization_status",
		"no_fabricated_reporting_status",
		"source_fidelity_status",
		"title_china_perspective_status",
	):
		_require_status(adaptation, key, candidate_id=candidate_id, label="adaptation", errors=errors)
	title = str(metadata.get("title") or article.get("title") or "")
	title_anchor = adaptation.get("title_country_or_region_anchor")
	if not title_anchor:
		_fail(errors, f"{candidate_id}: adaptation title_country_or_region_anchor is required")
	elif not _title_contains_anchor(title, title_anchor):
		_fail(errors, f"{candidate_id}: title does not contain country/region anchor {title_anchor!r}: {title}")
	if not adaptation.get("title_phenomenon_anchor"):
		_fail(errors, f"{candidate_id}: adaptation title_phenomenon_anchor is required")
	if not adaptation.get("title_explainer_frame"):
		_fail(errors, f"{candidate_id}: adaptation title_explainer_frame is required")
	if not adaptation.get("title_rationale"):
		_fail(errors, f"{candidate_id}: adaptation title_rationale is required")

	for key in (
		"status",
		"high_importance_retention_status",
		"distortion_status",
		"no_summary_or_abridgement_status",
		"no_fabricated_reporting_status",
		"not_original_claim_status",
	):
		_require_status(coverage, key, candidate_id=candidate_id, label="coverage", errors=errors)
	retention_ratio = float(coverage.get("retained_substantive_unit_ratio") or 0)
	if retention_ratio < 0.9:
		_fail(errors, f"{candidate_id}: retained_substantive_unit_ratio={retention_ratio}, expected >= 0.9")

	if metadata.get("content_mode") != "china_perspective_full_adaptation":
		_fail(errors, f"{candidate_id}: metadata content_mode={metadata.get('content_mode')!r}")
	if metadata.get("source_based") is not True:
		_fail(errors, f"{candidate_id}: metadata source_based must be true for China-perspective adaptation")
	if metadata.get("original_reporting") is not False:
		_fail(errors, f"{candidate_id}: metadata original_reporting must be false")
	if metadata.get("title_china_perspective_status") != "PASS":
		_fail(errors, f"{candidate_id}: metadata title_china_perspective_status={metadata.get('title_china_perspective_status')!r}")
	metadata_title_anchor = metadata.get("title_country_or_region_anchor")
	if not metadata_title_anchor:
		_fail(errors, f"{candidate_id}: metadata title_country_or_region_anchor is required")
	elif not _title_contains_anchor(title, metadata_title_anchor):
		_fail(errors, f"{candidate_id}: title does not contain metadata country/region anchor {metadata_title_anchor!r}: {title}")
	for key in ("title_phenomenon_anchor", "title_explainer_frame", "title_rationale"):
		if not metadata.get(key):
			_fail(errors, f"{candidate_id}: metadata {key} is required")
	if metadata.get("retained_substantive_unit_ratio") is not None and float(metadata.get("retained_substantive_unit_ratio") or 0) < 0.9:
		_fail(errors, f"{candidate_id}: metadata retained_substantive_unit_ratio must be >= 0.9")

	if _has_fabricated_reporting_claim(markdown):
		_fail(errors, f"{candidate_id}: article body appears to claim original reporting/interview/scene access")


def _check_article(
	article: dict[str, Any],
	*,
	min_h2: int,
	require_swiss_cover: bool,
	require_swiss_illustrations: bool,
	require_image_gen_cover: bool,
	require_image_gen_illustrations: bool,
	require_lead_image: bool,
	require_china_perspective_adaptation: bool,
	errors: list[str],
) -> None:
	candidate_id = article.get("candidate_id", "UNKNOWN")
	article_path = Path(article["wechat_article_path"])
	metadata_path = Path(article["metadata_path"])
	cover_manifest_path = Path(article["cover_manifest_path"])
	illustrations_manifest_path = Path(article["illustrations_manifest_path"])

	if not article_path.exists():
		_fail(errors, f"{candidate_id}: missing reviewed article {article_path}")
		return
	if not metadata_path.exists():
		_fail(errors, f"{candidate_id}: missing metadata {metadata_path}")
		return
	if not cover_manifest_path.exists():
		_fail(errors, f"{candidate_id}: missing cover manifest {cover_manifest_path}")
		return
	if not illustrations_manifest_path.exists():
		_fail(errors, f"{candidate_id}: missing illustrations manifest {illustrations_manifest_path}")
		return

	markdown = article_path.read_text(encoding="utf-8")
	metadata = _read_json(metadata_path)
	cover_manifest = _read_json(cover_manifest_path)
	illustrations_manifest = _read_json(illustrations_manifest_path)

	h2_count = _count_h2(markdown)
	if h2_count < min_h2:
		_fail(errors, f"{candidate_id}: only {h2_count} H2 chapters found, require at least {min_h2}")

	if _has_visible_source(markdown):
		_fail(errors, f"{candidate_id}: visible source declaration/original-link block still present")

	if require_china_perspective_adaptation:
		_check_china_perspective_artifacts(
			article,
			metadata,
			markdown,
			article_path,
			candidate_id=candidate_id,
			errors=errors,
		)

	title = str(metadata.get("title") or article.get("title") or "")
	if _article_title_has_source_prefix(title, metadata=metadata, article=article):
		_fail(errors, f"{candidate_id}: title appears to contain a source prefix: {title}")

	if illustrations_manifest.get("fallback_single_illustration"):
		_fail(errors, f"{candidate_id}: fallback_single_illustration=true is forbidden for repaired deep-longform runs")

	illustration_count = int(illustrations_manifest.get("illustration_count") or 0)
	if illustration_count != h2_count:
		_fail(errors, f"{candidate_id}: illustration_count={illustration_count} does not match h2_count={h2_count}")

	if require_lead_image and not _has_lead_image_before_first_h2(markdown):
		_fail(errors, f"{candidate_id}: missing lead image before the first H2 chapter")

	if require_swiss_cover:
		cover_blob = json.dumps(cover_manifest, ensure_ascii=False).lower()
		if "瑞士" not in cover_blob and "swiss" not in cover_blob:
			_fail(errors, f"{candidate_id}: cover manifest does not record a Swiss-style variant")

	if require_swiss_illustrations:
		ill_blob = json.dumps(illustrations_manifest, ensure_ascii=False).lower()
		if "瑞士" not in ill_blob and "swiss" not in ill_blob:
			_fail(errors, f"{candidate_id}: illustrations manifest does not record a Swiss-style variant")

	if require_image_gen_cover:
		_check_image_gen_cover_manifest(cover_manifest, candidate_id=candidate_id, errors=errors)

	if require_image_gen_illustrations or require_lead_image:
		_check_image_gen_illustrations_manifest(
			illustrations_manifest,
			candidate_id=candidate_id,
			require_lead_image=require_lead_image,
			errors=errors,
		)


def _normalize_source_name(value: Any) -> str:
	return re.sub(r"\s+", " ", str(value or "").strip())


def _check_selection_coverage(
	run_dir: Path,
	*,
	required_source_count: int,
	required_per_source_cap: int,
	fail_on_source_failed: bool,
	errors: list[str],
) -> dict[str, Any]:
	shortlist_path = run_dir / "selection" / "source-shortlist.json"
	if not shortlist_path.exists():
		_fail(errors, f"missing selection source shortlist: {shortlist_path}")
		return {"source_count": 0, "found_count": 0}

	shortlist = _read_json(shortlist_path)
	sources = shortlist.get("sources")
	if not isinstance(sources, list):
		_fail(errors, "source-shortlist.json must contain sources[]")
		return {"source_count": 0, "found_count": 0}

	production_sources = [
		item
		for item in sources
		if str(item.get("source_layer") or item.get("layer") or "production_whitelist").strip()
		in {"production_whitelist", "production", "fixed_whitelist", "fixed"}
	]

	if len(production_sources) != required_source_count:
		_fail(errors, f"selection has {len(production_sources)} production sources, require {required_source_count}")

	declared_count = shortlist.get("production_source_count", shortlist.get("required_source_count"))
	if declared_count is not None and int(declared_count) != required_source_count:
		_fail(errors, f"production/required source count={declared_count}, expected {required_source_count}")

	declared_cap = shortlist.get("per_source_candidate_cap")
	if declared_cap is not None and int(declared_cap) != required_per_source_cap:
		_fail(errors, f"per_source_candidate_cap={declared_cap}, expected {required_per_source_cap}")

	actual_names = {_normalize_source_name(item.get("source")) for item in production_sources}
	if required_source_count == len(EXPECTED_SELECTION_SOURCES):
		missing = sorted(EXPECTED_SELECTION_SOURCES - actual_names)
		extra = sorted(actual_names - EXPECTED_SELECTION_SOURCES)
		if missing:
			_fail(errors, f"selection missing expected sources: {missing}")
		if extra:
			_fail(errors, f"selection includes unexpected sources: {extra}")

	valid_statuses = {"FOUND", "NO_SOURCE_CANDIDATE", "SOURCE_FAILED"}
	found_count = 0
	for item in sources:
		source = _normalize_source_name(item.get("source"))
		source_layer = str(item.get("source_layer") or item.get("layer") or "production_whitelist").strip()
		is_production_source = source_layer in {"production_whitelist", "production", "fixed_whitelist", "fixed"}
		status = item.get("status")
		if status not in valid_statuses:
			_fail(errors, f"{source}: invalid source status {status!r}")
		if is_production_source and fail_on_source_failed and status == "SOURCE_FAILED":
			_fail(errors, f"{source}: SOURCE_FAILED is not allowed in strict selection coverage")
		articles = item.get("articles") or []
		if not isinstance(articles, list):
			_fail(errors, f"{source}: articles must be a list")
			continue
		if len(articles) > required_per_source_cap:
			_fail(errors, f"{source}: has {len(articles)} article(s), per-source cap is {required_per_source_cap}")
		if is_production_source and status == "FOUND":
			found_count += 1
			if len(articles) != 1:
				_fail(errors, f"{source}: status FOUND requires exactly 1 best article")
			if not item.get("best_candidate_selection_reason") and articles and not articles[0].get("best_candidate_selection_reason"):
				_fail(errors, f"{source}: missing best_candidate_selection_reason")
		if status == "NO_SOURCE_CANDIDATE" and not item.get("no_candidate_reason"):
			_fail(errors, f"{source}: missing no_candidate_reason")
		if status == "SOURCE_FAILED" and not item.get("source_failure_reason"):
			_fail(errors, f"{source}: missing source_failure_reason")

	return {"source_count": len(sources), "found_count": found_count}


def main() -> int:
	parser = argparse.ArgumentParser(description="Final acceptance gate for daily WeChat longform bundle.")
	parser.add_argument("--run-dir", type=Path, required=True)
	parser.add_argument("--require-article-count", type=int, default=1)
	parser.add_argument("--min-h2", type=int, default=3)
	parser.add_argument("--require-swiss-cover", action="store_true")
	parser.add_argument("--require-swiss-illustrations", action="store_true")
	parser.add_argument("--require-image-gen-cover", action="store_true")
	parser.add_argument("--require-image-gen-illustrations", action="store_true")
	parser.add_argument("--require-lead-image", action="store_true")
	parser.add_argument("--require-china-perspective-adaptation", action="store_true")
	parser.add_argument("--require-selection-source-count", type=int, default=0)
	parser.add_argument("--require-per-source-cap", type=int, default=1)
	parser.add_argument("--fail-on-source-failed", action="store_true")
	args = parser.parse_args()

	run_dir = args.run_dir.expanduser().resolve()
	bundle_manifest_path = run_dir / "wechat_bundle" / "wechat_bundle_manifest.json"
	publish_report_path = run_dir / "publish" / "wechat_draft_report.json"
	preview_html_path = run_dir / "publish" / "wechat_article.preview.html"

	errors: list[str] = []
	if not bundle_manifest_path.exists():
		_fail(errors, f"missing bundle manifest: {bundle_manifest_path}")
	if not publish_report_path.exists():
		_fail(errors, f"missing publish report: {publish_report_path}")
	if not preview_html_path.exists():
		_fail(errors, f"missing preview html: {preview_html_path}")
	if errors:
		print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
		return 1

	bundle_manifest = _read_json(bundle_manifest_path)
	publish_report = _read_json(publish_report_path)
	selection_summary: dict[str, Any] = {}
	if args.require_selection_source_count:
		selection_summary = _check_selection_coverage(
			run_dir,
			required_source_count=args.require_selection_source_count,
			required_per_source_cap=args.require_per_source_cap,
			fail_on_source_failed=args.fail_on_source_failed,
			errors=errors,
		)
	articles = bundle_manifest.get("articles") or []
	if len(articles) != args.require_article_count:
		_fail(errors, f"bundle has {len(articles)} article(s), require exactly {args.require_article_count}")

	if publish_report.get("article_count") != args.require_article_count:
		_fail(errors, f"publish report article_count={publish_report.get('article_count')} expected {args.require_article_count}")
	if publish_report.get("final_publish_clicked") is not False:
		_fail(errors, "publish report indicates final publish was clicked")

	for article in articles:
		_check_article(
			article,
			min_h2=args.min_h2,
			require_swiss_cover=args.require_swiss_cover,
			require_swiss_illustrations=args.require_swiss_illustrations,
			require_image_gen_cover=args.require_image_gen_cover,
			require_image_gen_illustrations=args.require_image_gen_illustrations,
			require_lead_image=args.require_lead_image,
			require_china_perspective_adaptation=args.require_china_perspective_adaptation,
			errors=errors,
		)

	status = "PASS" if not errors else "FAIL"
	print(
		json.dumps(
			{
				"status": status,
				"run_dir": str(run_dir),
				"required_article_count": args.require_article_count,
				"article_count": len(articles),
				"selection": selection_summary,
				"errors": errors,
			},
			ensure_ascii=False,
			indent=2,
		)
	)
	return 0 if not errors else 1


if __name__ == "__main__":
	sys.exit(main())
