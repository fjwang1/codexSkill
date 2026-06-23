#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SPEECH_RATE_CJK_PER_SEC = 4.5
CHAPTER_MIN_RATIO = 0.90
CHAPTER_MAX_RATIO = 1.05
NODE_MIN_RATIO = 0.90
NODE_MAX_RATIO = 1.05
HIGH_PRIORITY_NODE_MIN_RATIO = 0.92
HIGH_PRIORITY_NODE_MAX_RATIO = 1.02
HIGH_PRIORITY_MAX_DRIFT_SEC = 1.0
NORMAL_PRIORITY_MAX_DRIFT_SEC = 3.0
MANIFEST_SCHEMA_VERSION = 'voiceover-tts-manifest.v1'
MANIFEST_ALLOWED_KEYS = {'schema_version', 'inter_segment_pause_sec', 'segments'}
SEMANTIC_NODES_SCHEMA_VERSION = 'voiceover-semantic-nodes.v1'
SEMANTIC_NODES_ALLOWED_KEYS = {
	'schema_version',
	'video_id',
	'video_url',
	'title',
	'source_transcript_path',
	'source_language',
	'target_language',
	'speech_rate_model',
	'chapters',
}
SEMANTIC_NODES_REQUIRED_KEYS = SEMANTIC_NODES_ALLOWED_KEYS
CHAPTER_ALLOWED_KEYS = {
	'chapter_id',
	'start',
	'end',
	'target_duration_sec',
	'chapter_title',
	'chapter_voice_text',
	'nodes',
}
CHAPTER_REQUIRED_KEYS = CHAPTER_ALLOWED_KEYS
NODE_ALLOWED_KEYS = {
	'node_id',
	'start',
	'end',
	'source_start',
	'source_end',
	'source_subtitle_ids',
	'source_excerpt',
	'target_duration_sec',
	'sync_priority',
	'must_cover',
	'voice_text',
	'estimated_speech_sec',
	'duration_coverage_ratio',
	'coverage_status',
	'notes',
}
NODE_REQUIRED_KEYS = NODE_ALLOWED_KEYS - {'notes'}
MANIFEST_SEGMENT_REQUIRED_KEYS = {
	'node_id',
	'voice_text_sha256',
	'audio_path',
	'actual_tts_sec',
	'target_duration_sec',
	'actual_coverage_ratio',
	'cumulative_drift_sec',
	'status',
	'needs_rerun',
}
MANIFEST_STATUSES = {'approved', 'needs_rewrite', 'tts_failed', 'reused'}
MANIFEST_RERUN_STATUSES = {'needs_rewrite', 'tts_failed'}
SYNC_PRIORITIES = {'high', 'normal', 'low'}
COVERAGE_STATUSES = {'complete', 'below_target', 'sparse_source', 'needs_rewrite', 'approved'}

CHAPTER_RE = re.compile(r'^## (voice_chapter_\d+)\n\n(.*?)(?=\n## voice_chapter_|\Z)', re.M | re.S)
NODE_RE = re.compile(r'^#### ([a-zA-Z0-9_]+)\n\n(.*?)(?=\n#### |\n## voice_chapter_|\Z)', re.M | re.S)
CHAPTER_BODY_RE = re.compile(r'\[(\d\d:\d\d:\d\d) - (\d\d:\d\d:\d\d)\]\n(.*?)(?=\n### semantic_nodes|\Z)', re.S)
TIME_RANGE_RE = re.compile(r'- time_range: (\d\d:\d\d:\d\d)-(\d\d:\d\d:\d\d)')
TARGET_DURATION_RE = re.compile(r'- target_duration_sec: ([0-9]+(?:\.[0-9]+)?)')
TARGET_SPEECH_RE = re.compile(r'- target_speech_sec: ([0-9]+(?:\.[0-9]+)?)-([0-9]+(?:\.[0-9]+)?)')
ESTIMATED_RE = re.compile(r'- estimated_speech_sec: ([0-9]+(?:\.[0-9]+)?)')
DURATION_RATIO_RE = re.compile(r'- duration_coverage_ratio: ([0-9]+(?:\.[0-9]+)?)')
SYNC_PRIORITY_RE = re.compile(r'- sync_priority: ([a-zA-Z_]+)')
COVERAGE_STATUS_RE = re.compile(r'- coverage_status: ([a-zA-Z_]+)')
NOTES_RE = re.compile(r'- notes: (.+)')
MUST_COVER_RE = re.compile(r'- must_cover: (.+)')
SOURCE_START_RE = re.compile(r'- source_start: (\d\d:\d\d:\d\d)')
SOURCE_END_RE = re.compile(r'- source_end: (\d\d:\d\d:\d\d)')
SOURCE_SUBTITLE_IDS_RE = re.compile(r'- source_subtitle_ids: (.+)')
SOURCE_EXCERPT_RE = re.compile(r'- source_excerpt: (.+)')


def _seconds(value: str) -> int:
	parts = [int(part) for part in value.split(':')]
	return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _cjk_count(value: str) -> int:
	return sum(1 for char in value if '\u4e00' <= char <= '\u9fff')


def _estimated_sec(value: str) -> int:
	return round(_cjk_count(value) / SPEECH_RATE_CJK_PER_SEC)


def _coverage_ratio(duration_sec: float, target_duration_sec: float) -> float:
	if target_duration_sec <= 0:
		return 0.0
	return round(duration_sec / target_duration_sec, 2)


def _normalize_text(value: str) -> str:
	return re.sub(r'\s+', '', value or '')


def _text_hash(value: str) -> str:
	return hashlib.sha256(_normalize_text(value).encode('utf-8')).hexdigest()


def _is_number(value: Any) -> bool:
	return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_bool(value: Any) -> bool:
	return isinstance(value, bool)


def _is_non_empty_str(value: Any) -> bool:
	return isinstance(value, str) and bool(value.strip())


def _safe_float(value: Any) -> float:
	return float(value) if _is_number(value) else 0.0


def _is_hhmmss(value: Any) -> bool:
	return isinstance(value, str) and re.fullmatch(r'\d\d:\d\d:\d\d', value) is not None


def _safe_seconds(value: Any, issues: list[str], item_id: str, field: str) -> int:
	if not _is_hhmmss(value):
		issues.append(f'{item_id}: {field} must be HH:MM:SS')
		return 0
	return _seconds(str(value))


def _validate_object_schema(
	*,
	item: Any,
	item_id: str,
	allowed_keys: set[str],
	required_keys: set[str],
	issues: list[str],
) -> bool:
	if not isinstance(item, dict):
		issues.append(f'{item_id}: must be an object')
		return False
	unknown_keys = sorted(set(item) - allowed_keys)
	if unknown_keys:
		issues.append(f'{item_id}: unknown keys {unknown_keys}')
	for field in sorted(required_keys):
		if field not in item:
			issues.append(f'{item_id}: missing {field}')
	return True


def _canonical_source_ids(value: Any) -> str:
	if isinstance(value, list):
		parts = [str(item).strip() for item in value]
	else:
		parts = re.split(r'[,;；，\s]+', str(value or '').strip())
	result: list[str] = []
	for part in parts:
		if not part:
			continue
		range_match = re.fullmatch(r'(\d+)-(\d+)', part)
		if range_match:
			start_text, end_text = range_match.groups()
			width = max(len(start_text), len(end_text))
			start = int(start_text)
			end = int(end_text)
			if start <= end and end - start <= 200:
				result.extend(f'{index:0{width}d}' for index in range(start, end + 1))
				continue
		result.append(part)
	return ','.join(result)


def _canonical_listish(value: Any) -> str:
	if isinstance(value, list):
		parts = [str(item).strip() for item in value]
	else:
		parts = re.split(r'[;；\n]+', str(value or '').strip())
	return '|'.join(_normalize_text(part) for part in parts if part.strip())


def _normalized_chapter_id(value: Any) -> str:
	text = str(value or '')
	return text.removeprefix('voice_')


def _line_stats(body: str) -> dict[str, float | int]:
	lines = [line.strip() for line in body.splitlines() if line.strip()]
	max_cjk = max((_cjk_count(line) for line in lines), default=0)
	return {
		'line_count': len(lines),
		'max_line_cjk': max_cjk,
		'max_line_estimated_speech_sec': round(max_cjk / SPEECH_RATE_CJK_PER_SEC, 2),
	}


def _node_body(block: str) -> str:
	lines: list[str] = []
	in_body = False
	for line in block.splitlines():
		stripped = line.strip()
		if not stripped:
			if in_body:
				lines.append('')
			continue
		if stripped.startswith('- ') and not in_body:
			continue
		in_body = True
		lines.append(line)
	return '\n'.join(lines).strip()


def _required_match(pattern: re.Pattern[str], block: str, label: str, issues: list[str], item_id: str) -> re.Match[str] | None:
	match = pattern.search(block)
	if match is None:
		issues.append(f'{item_id}: missing {label}')
	return match


def _has_front_matter(text: str) -> bool:
	return text.startswith('---\n') and '\n---\n' in text[4:]


def _timing_thresholds(sync_priority: str | None, is_chapter: bool) -> tuple[float, float]:
	if is_chapter:
		return CHAPTER_MIN_RATIO, CHAPTER_MAX_RATIO
	if sync_priority == 'high':
		return HIGH_PRIORITY_NODE_MIN_RATIO, HIGH_PRIORITY_NODE_MAX_RATIO
	return NODE_MIN_RATIO, NODE_MAX_RATIO


def _validate_timing_item(
	*,
	item_id: str,
	body: str,
	block: str,
	target_duration_sec: float,
	sync_priority: str | None,
	is_chapter: bool,
	issues: list[str],
) -> dict[str, object]:
	estimated = _required_match(ESTIMATED_RE, block, 'estimated_speech_sec', issues, item_id)
	duration_ratio = _required_match(DURATION_RATIO_RE, block, 'duration_coverage_ratio', issues, item_id)
	target_speech = TARGET_SPEECH_RE.search(block)
	coverage_status = COVERAGE_STATUS_RE.search(block)
	notes = NOTES_RE.search(block)
	min_ratio, max_ratio = _timing_thresholds(sync_priority, is_chapter)

	cjk_chars = _cjk_count(body)
	calculated_estimate = _estimated_sec(body)
	calculated_ratio = _coverage_ratio(calculated_estimate, target_duration_sec)
	line_stats = _line_stats(body)

	if estimated is not None:
		listed_estimate = round(float(estimated.group(1)))
		if abs(listed_estimate - calculated_estimate) > 2:
			issues.append(f'{item_id}: estimated_speech_sec {listed_estimate} differs from calculated {calculated_estimate}')
	else:
		listed_estimate = None

	if duration_ratio is not None:
		listed_ratio = round(float(duration_ratio.group(1)), 2)
		if abs(listed_ratio - calculated_ratio) > 0.03:
			issues.append(f'{item_id}: duration_coverage_ratio {listed_ratio:.2f} differs from calculated {calculated_ratio:.2f}')
	else:
		listed_ratio = None

	if target_speech is not None:
		target_speech_low = round(float(target_speech.group(1)))
		target_speech_high = round(float(target_speech.group(2)))
		if calculated_estimate < target_speech_low or calculated_estimate > target_speech_high:
			issues.append(f'{item_id}: calculated estimate {calculated_estimate} outside target_speech_sec {target_speech_low}-{target_speech_high}')
	else:
		target_speech_low = None
		target_speech_high = None

	status = coverage_status.group(1) if coverage_status else ''
	if calculated_ratio < min_ratio:
		if status not in {'below_target', 'sparse_source'}:
			issues.append(f'{item_id}: coverage ratio {calculated_ratio:.2f} below {min_ratio:.2f} without below_target/sparse_source status')
		if notes is None:
			issues.append(f'{item_id}: below-target/sparse item must include notes with text evidence')
	if calculated_ratio > max_ratio:
		issues.append(f'{item_id}: coverage ratio {calculated_ratio:.2f} above {max_ratio:.2f}')
	if float(line_stats['max_line_estimated_speech_sec']) > 30:
		issues.append(f'{item_id}: longest line estimated over 30 seconds')

	return {
		'id': item_id,
		'target_duration_sec': target_duration_sec,
		'target_speech_sec': [target_speech_low, target_speech_high],
		'listed_estimated_speech_sec': listed_estimate,
		'calculated_estimated_speech_sec': calculated_estimate,
		'listed_duration_coverage_ratio': listed_ratio,
		'calculated_duration_coverage_ratio': calculated_ratio,
		'cjk_char_count': cjk_chars,
		'coverage_status': status,
		'text_hash': _text_hash(body),
		**line_stats,
	}


def _source_binding_from_block(block: str, item_id: str, issues: list[str]) -> dict[str, object]:
	source_start = _required_match(SOURCE_START_RE, block, 'source_start', issues, item_id)
	source_end = _required_match(SOURCE_END_RE, block, 'source_end', issues, item_id)
	source_subtitle_ids = _required_match(SOURCE_SUBTITLE_IDS_RE, block, 'source_subtitle_ids', issues, item_id)
	source_excerpt = _required_match(SOURCE_EXCERPT_RE, block, 'source_excerpt', issues, item_id)
	return {
		'source_time_range': f'{source_start.group(1)}-{source_end.group(1)}' if source_start and source_end else None,
		'source_subtitle_ids': _canonical_source_ids(source_subtitle_ids.group(1)) if source_subtitle_ids else None,
		'source_excerpt': source_excerpt.group(1).strip() if source_excerpt else None,
		'source_excerpt_hash': _text_hash(source_excerpt.group(1)) if source_excerpt else None,
	}


def validate_markdown(path: Path) -> dict[str, object]:
	text = path.read_text(encoding='utf-8')
	issues: list[str] = []
	chapters: list[dict[str, object]] = []
	previous_chapter_end: int | None = None

	if not _has_front_matter(text):
		issues.append('missing front matter')

	for match in CHAPTER_RE.finditer(text):
		chapter_id = match.group(1)
		block = match.group(2)
		time_range = _required_match(TIME_RANGE_RE, block, 'time_range', issues, chapter_id)
		target_duration = _required_match(TARGET_DURATION_RE, block, 'target_duration_sec', issues, chapter_id)
		body_match = CHAPTER_BODY_RE.search(block)

		if time_range is None or target_duration is None or body_match is None:
			if body_match is None:
				issues.append(f'{chapter_id}: missing chapter body time range')
			continue

		meta_start, meta_end = time_range.groups()
		body_start, body_end, chapter_body = body_match.groups()
		start_sec = _seconds(meta_start)
		end_sec = _seconds(meta_end)
		duration_sec = end_sec - start_sec
		target_duration_sec = float(target_duration.group(1))

		if body_start != meta_start or body_end != meta_end:
			issues.append(f'{chapter_id}: body time range does not match metadata time_range')
		if previous_chapter_end is not None and start_sec != previous_chapter_end:
			issues.append(f'{chapter_id}: chapter timeline gap or overlap before start {meta_start}')
		if abs(target_duration_sec - duration_sec) > 0.5:
			issues.append(f'{chapter_id}: target_duration_sec {target_duration_sec} != time range duration {duration_sec}')

		chapter_report = _validate_timing_item(
			item_id=chapter_id,
			body=chapter_body,
			block=block,
			target_duration_sec=target_duration_sec,
			sync_priority=None,
			is_chapter=True,
			issues=issues,
		)

		nodes: list[dict[str, object]] = []
		previous_node_end: int | None = None
		for node_match in NODE_RE.finditer(block):
			node_id = node_match.group(1)
			node_block = node_match.group(2)
			node_time_range = _required_match(TIME_RANGE_RE, node_block, 'time_range', issues, node_id)
			node_target_duration = _required_match(TARGET_DURATION_RE, node_block, 'target_duration_sec', issues, node_id)
			node_sync_priority = _required_match(SYNC_PRIORITY_RE, node_block, 'sync_priority', issues, node_id)
			must_cover = _required_match(MUST_COVER_RE, node_block, 'must_cover', issues, node_id)
			source_binding = _source_binding_from_block(node_block, node_id, issues)
			node_body = _node_body(node_block)

			if node_time_range is None or node_target_duration is None:
				continue
			node_start, node_end = node_time_range.groups()
			node_start_sec = _seconds(node_start)
			node_end_sec = _seconds(node_end)
			node_duration_sec = node_end_sec - node_start_sec
			node_target_duration_sec = float(node_target_duration.group(1))
			sync_priority = node_sync_priority.group(1) if node_sync_priority else None

			if node_start_sec < start_sec or node_end_sec > end_sec:
				issues.append(f'{node_id}: node time range outside parent chapter')
			if previous_node_end is None and node_start_sec != start_sec:
				issues.append(f'{node_id}: first node must start at chapter start {meta_start}')
			if previous_node_end is not None and node_start_sec != previous_node_end:
				issues.append(f'{node_id}: node timeline gap or overlap before start {node_start}')
			if abs(node_target_duration_sec - node_duration_sec) > 0.5:
				issues.append(f'{node_id}: target_duration_sec {node_target_duration_sec} != time range duration {node_duration_sec}')
			if not node_body:
				issues.append(f'{node_id}: empty voice text')

			node_report = _validate_timing_item(
				item_id=node_id,
				body=node_body,
				block=node_block,
				target_duration_sec=node_target_duration_sec,
				sync_priority=sync_priority,
				is_chapter=False,
				issues=issues,
			)
			node_report['time_range'] = f'{node_start}-{node_end}'
			node_report['sync_priority'] = sync_priority
			node_report['must_cover'] = _canonical_listish(must_cover.group(1)) if must_cover else None
			node_report.update(source_binding)
			nodes.append(node_report)
			previous_node_end = node_end_sec

		if nodes and previous_node_end != end_sec:
			issues.append(f'{chapter_id}: nodes do not cover chapter end {meta_end}')

		chapter_report['time_range'] = f'{meta_start}-{meta_end}'
		chapter_report['nodes'] = nodes
		chapters.append(chapter_report)
		previous_chapter_end = end_sec

	if not chapters:
		issues.append('no voice_chapter sections found')

	return {
		'path': str(path),
		'format': 'markdown',
		'chapter_count': len(chapters),
		'node_count': sum(len(chapter['nodes']) for chapter in chapters),
		'total_calculated_estimated_speech_sec': sum(int(chapter['calculated_estimated_speech_sec']) for chapter in chapters),
		'passed': not issues,
		'issues': issues,
		'chapters': chapters,
	}


def _validate_json_node(node: dict[str, Any], issues: list[str], chapter_id: str) -> dict[str, object]:
	if not _validate_object_schema(
		item=node,
		item_id=f'{chapter_id}:node',
		allowed_keys=NODE_ALLOWED_KEYS,
		required_keys=NODE_REQUIRED_KEYS,
		issues=issues,
	):
		node = {}
	node_id = str(node.get('node_id') or '')
	if not node_id:
		issues.append(f'{chapter_id}: node missing node_id')
		node_id = f'{chapter_id}:unknown_node'
	body = str(node.get('voice_text') or '').strip()
	target_duration_sec = _safe_float(node.get('target_duration_sec'))
	sync_priority = str(node.get('sync_priority') or 'normal')

	for field in ('start', 'end', 'source_start', 'source_end'):
		if not _is_hhmmss(node.get(field)):
			issues.append(f'{node_id}: {field} must be HH:MM:SS')
	if 'target_duration_sec' in node and not _is_number(node.get('target_duration_sec')):
		issues.append(f'{node_id}: target_duration_sec must be a number')
	if 'estimated_speech_sec' in node and not _is_number(node.get('estimated_speech_sec')):
		issues.append(f'{node_id}: estimated_speech_sec must be a number')
	if 'duration_coverage_ratio' in node and not _is_number(node.get('duration_coverage_ratio')):
		issues.append(f'{node_id}: duration_coverage_ratio must be a number')
	if sync_priority not in SYNC_PRIORITIES:
		issues.append(f'{node_id}: sync_priority must be one of {sorted(SYNC_PRIORITIES)}')
	coverage_status = str(node.get('coverage_status') or '')
	if coverage_status not in COVERAGE_STATUSES:
		issues.append(f'{node_id}: coverage_status must be one of {sorted(COVERAGE_STATUSES)}')
	if not body:
		issues.append(f'{node_id}: empty voice_text')
	if not node.get('must_cover'):
		issues.append(f'{node_id}: missing must_cover')
	if not node.get('source_subtitle_ids'):
		issues.append(f'{node_id}: missing source_subtitle_ids')
	if not node.get('source_excerpt'):
		issues.append(f'{node_id}: missing source_excerpt')

	block = (
		f"- estimated_speech_sec: {node.get('estimated_speech_sec', '')}\n"
		f"- duration_coverage_ratio: {node.get('duration_coverage_ratio', '')}\n"
		f"- coverage_status: {node.get('coverage_status', '')}\n"
		f"- notes: {node.get('notes', '')}\n"
	)
	report = _validate_timing_item(
		item_id=node_id,
		body=body,
		block=block,
		target_duration_sec=target_duration_sec,
		sync_priority=sync_priority,
		is_chapter=False,
		issues=issues,
	)
	report['time_range'] = f"{node.get('start')}-{node.get('end')}"
	report['source_time_range'] = f"{node.get('source_start')}-{node.get('source_end')}"
	report['sync_priority'] = sync_priority
	report['source_subtitle_ids'] = _canonical_source_ids(node.get('source_subtitle_ids'))
	report['source_excerpt'] = str(node.get('source_excerpt') or '').strip()
	report['source_excerpt_hash'] = _text_hash(str(node.get('source_excerpt') or ''))
	report['must_cover'] = _canonical_listish(node.get('must_cover'))
	return report


def validate_json_nodes(path: Path) -> dict[str, object]:
	payload = json.loads(path.read_text(encoding='utf-8'))
	issues: list[str] = []
	chapters: list[dict[str, object]] = []
	if not _validate_object_schema(
		item=payload,
		item_id='json payload',
		allowed_keys=SEMANTIC_NODES_ALLOWED_KEYS,
		required_keys=SEMANTIC_NODES_REQUIRED_KEYS,
		issues=issues,
	):
		payload = {}
	if payload.get('schema_version') != SEMANTIC_NODES_SCHEMA_VERSION:
		issues.append(f'json payload schema_version must be {SEMANTIC_NODES_SCHEMA_VERSION}')
	for field in ('video_id', 'video_url', 'title', 'source_transcript_path', 'source_language', 'target_language', 'speech_rate_model'):
		if field in payload and not _is_non_empty_str(payload.get(field)):
			issues.append(f'json payload {field} must be a non-empty string')
	if not isinstance(payload.get('chapters'), list) or not payload.get('chapters'):
		issues.append('json payload must contain a non-empty chapters list')

	previous_chapter_end: int | None = None
	chapter_items = payload.get('chapters') if isinstance(payload.get('chapters'), list) else []
	seen_chapter_ids: set[str] = set()
	seen_node_ids: set[str] = set()
	for chapter in chapter_items:
		if not _validate_object_schema(
			item=chapter,
			item_id='chapter',
			allowed_keys=CHAPTER_ALLOWED_KEYS,
			required_keys=CHAPTER_REQUIRED_KEYS,
			issues=issues,
		):
			chapter = {}
		chapter_id = str(chapter.get('chapter_id') or '')
		if not chapter_id:
			issues.append('chapter missing chapter_id')
			chapter_id = 'unknown_chapter'
		elif chapter_id in seen_chapter_ids:
			issues.append(f'duplicate chapter_id {chapter_id}')
		seen_chapter_ids.add(chapter_id)
		start = str(chapter.get('start') or '')
		end = str(chapter.get('end') or '')
		body = str(chapter.get('chapter_voice_text') or '').strip()
		target_duration_sec = _safe_float(chapter.get('target_duration_sec'))
		if not _is_hhmmss(start):
			issues.append(f'{chapter_id}: start must be HH:MM:SS')
		if not _is_hhmmss(end):
			issues.append(f'{chapter_id}: end must be HH:MM:SS')
		start_sec = _safe_seconds(start, issues, chapter_id, 'start') if _is_hhmmss(start) else (previous_chapter_end or 0)
		end_sec = _safe_seconds(end, issues, chapter_id, 'end') if _is_hhmmss(end) else start_sec
		if 'target_duration_sec' in chapter and not _is_number(chapter.get('target_duration_sec')):
			issues.append(f'{chapter_id}: target_duration_sec must be a number')
		for field in ('chapter_id', 'chapter_title', 'chapter_voice_text'):
			if field in chapter and not _is_non_empty_str(chapter.get(field)):
				issues.append(f'{chapter_id}: {field} must be a non-empty string')
		if not body:
			issues.append(f'{chapter_id}: empty chapter_voice_text')
		if not isinstance(chapter.get('nodes'), list) or not chapter.get('nodes'):
			issues.append(f'{chapter_id}: nodes must be a non-empty list')
		if previous_chapter_end is not None and start_sec != previous_chapter_end:
			issues.append(f'{chapter_id}: chapter timeline gap or overlap before start {start}')
		if target_duration_sec and abs(target_duration_sec - (end_sec - start_sec)) > 0.5:
			issues.append(f'{chapter_id}: target_duration_sec {target_duration_sec} != time range duration {end_sec - start_sec}')

		nodes: list[dict[str, object]] = []
		previous_node_end: int | None = None
		node_items = chapter.get('nodes') if isinstance(chapter.get('nodes'), list) else []
		for node in node_items:
			node_report = _validate_json_node(node, issues, chapter_id)
			if not isinstance(node, dict):
				nodes.append(node_report)
				continue
			node_id = str(node.get('node_id') or '')
			if node_id:
				if node_id in seen_node_ids:
					issues.append(f'duplicate node_id {node_id}')
				seen_node_ids.add(node_id)
			node_start = str(node.get('start') or '')
			node_end = str(node.get('end') or '')
			if _is_hhmmss(node_start) and _is_hhmmss(node_end):
				node_start_sec = _safe_seconds(node_start, issues, str(node.get('node_id')), 'start')
				node_end_sec = _safe_seconds(node_end, issues, str(node.get('node_id')), 'end')
				if node_start_sec < start_sec or node_end_sec > end_sec:
					issues.append(f"{node.get('node_id')}: node time range outside parent chapter")
				if previous_node_end is None and node_start_sec != start_sec:
					issues.append(f"{node.get('node_id')}: first node must start at chapter start {start}")
				if previous_node_end is not None and node_start_sec != previous_node_end:
					issues.append(f"{node.get('node_id')}: node timeline gap or overlap before start {node_start}")
				node_target_duration = _safe_float(node.get('target_duration_sec'))
				if node_target_duration and abs(node_target_duration - (node_end_sec - node_start_sec)) > 0.5:
					issues.append(f"{node.get('node_id')}: target_duration_sec {node.get('target_duration_sec')} != time range duration {node_end_sec - node_start_sec}")
				previous_node_end = node_end_sec
			nodes.append(node_report)

		if nodes and previous_node_end != end_sec:
			issues.append(f'{chapter_id}: nodes do not cover chapter end {end}')

		chapters.append({
			'chapter_id': chapter_id,
			'time_range': f'{start}-{end}',
			'target_duration_sec': target_duration_sec,
			'text_hash': _text_hash(body),
			'node_count': len(nodes),
			'nodes': nodes,
		})
		previous_chapter_end = end_sec

	return {
		'path': str(path),
		'format': 'json',
		'chapter_count': len(chapters),
		'node_count': sum(int(chapter['node_count']) for chapter in chapters),
		'passed': not issues,
		'issues': issues,
		'chapters': chapters,
	}


def _flatten_nodes(report: dict[str, object]) -> dict[str, dict[str, object]]:
	nodes: dict[str, dict[str, object]] = {}
	for chapter in report.get('chapters', []):
		for node in chapter.get('nodes', []):
			nodes[str(node['id'])] = node
	return nodes


def compare_reports(primary: dict[str, object], paired: dict[str, object]) -> list[str]:
	issues: list[str] = []
	if int(primary.get('chapter_count') or 0) != int(paired.get('chapter_count') or 0):
		issues.append('markdown/json chapter counts differ')
	primary_chapters = primary.get('chapters', [])
	paired_chapters = paired.get('chapters', [])
	for index, (left_chapter, right_chapter) in enumerate(zip(primary_chapters, paired_chapters), start=1):
		left_id = _normalized_chapter_id(left_chapter.get('id') or left_chapter.get('chapter_id'))
		right_id = _normalized_chapter_id(right_chapter.get('id') or right_chapter.get('chapter_id'))
		if left_id != right_id:
			issues.append(f'chapter {index}: paired chapter_id mismatch')
		if left_chapter.get('time_range') != right_chapter.get('time_range'):
			issues.append(f'chapter {index}: paired time_range mismatch')
		if left_chapter.get('text_hash') != right_chapter.get('text_hash'):
			issues.append(f'chapter {index}: paired chapter voice text mismatch')
	primary_nodes = _flatten_nodes(primary)
	paired_nodes = _flatten_nodes(paired)
	if set(primary_nodes) != set(paired_nodes):
		issues.append('markdown/json node id sets differ')
	for node_id in sorted(set(primary_nodes) & set(paired_nodes)):
		left = primary_nodes[node_id]
		right = paired_nodes[node_id]
		for field in (
			'time_range',
			'source_time_range',
			'source_subtitle_ids',
			'source_excerpt_hash',
			'must_cover',
			'sync_priority',
			'text_hash',
		):
			if left.get(field) != right.get(field):
				issues.append(f'{node_id}: paired {field} mismatch')
	return issues


def _manifest_segments(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
	result: dict[str, dict[str, Any]] = {}
	segments = manifest.get('segments')
	if not isinstance(segments, list):
		return result
	for segment in segments:
		if not isinstance(segment, dict):
			continue
		segment_id = segment.get('node_id')
		if segment_id:
			result[str(segment_id)] = segment
	return result


def _validate_manifest_shape(manifest: dict[str, Any], issues: list[str]) -> None:
	extra_top_level = sorted(set(manifest) - MANIFEST_ALLOWED_KEYS)
	if extra_top_level:
		issues.append(f'manifest has unknown top-level keys: {extra_top_level}')
	if manifest.get('schema_version') != MANIFEST_SCHEMA_VERSION:
		issues.append(f"manifest schema_version must be {MANIFEST_SCHEMA_VERSION}")
	if not _is_number(manifest.get('inter_segment_pause_sec')):
		issues.append('manifest inter_segment_pause_sec must be a number')
	segments = manifest.get('segments')
	if not isinstance(segments, list) or not segments:
		issues.append('manifest must contain a non-empty segments list')
		return
	seen_node_ids: set[str] = set()
	for index, segment in enumerate(segments, start=1):
		if not isinstance(segment, dict):
			issues.append(f'manifest segment {index}: must be an object')
			continue
		node_id = str(segment.get('node_id') or '')
		if node_id:
			if node_id in seen_node_ids:
				issues.append(f'manifest segment {index}: duplicate node_id {node_id}')
			seen_node_ids.add(node_id)
		unknown_keys = sorted(set(segment) - MANIFEST_SEGMENT_REQUIRED_KEYS)
		if unknown_keys:
			issues.append(f'manifest segment {index}: unknown keys {unknown_keys}')
		for field in sorted(MANIFEST_SEGMENT_REQUIRED_KEYS):
			if field not in segment:
				issues.append(f'manifest segment {index}: missing {field}')
		for field in ('node_id', 'voice_text_sha256', 'audio_path', 'status'):
			if field in segment and not _is_non_empty_str(segment[field]):
				issues.append(f'manifest segment {index}: {field} must be a non-empty string')
		for field in ('actual_tts_sec', 'target_duration_sec', 'actual_coverage_ratio', 'cumulative_drift_sec'):
			if field in segment and not _is_number(segment[field]):
				issues.append(f'manifest segment {index}: {field} must be a number')
		if 'needs_rerun' in segment and not _is_bool(segment['needs_rerun']):
			issues.append(f'manifest segment {index}: needs_rerun must be a boolean')


def validate_manifest(report: dict[str, object], manifest_path: Path) -> dict[str, object]:
	manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
	issues: list[str] = []
	_validate_manifest_shape(manifest, issues)
	segments = _manifest_segments(manifest)
	nodes = _flatten_nodes(report)
	if set(segments) != set(nodes):
		missing = sorted(set(nodes) - set(segments))
		extra = sorted(set(segments) - set(nodes))
		if missing:
			issues.append(f'manifest missing node ids: {missing}')
		if extra:
			issues.append(f'manifest has extra node ids: {extra}')
	inter_pause = _safe_float(manifest.get('inter_segment_pause_sec'))
	cumulative_actual = 0.0
	cumulative_target = 0.0
	node_results: list[dict[str, object]] = []

	for index, (node_id, node) in enumerate(nodes.items()):
		segment = segments.get(node_id)
		if segment is None:
			issues.append(f'{node_id}: missing manifest segment')
			continue
		actual = _safe_float(segment.get('actual_tts_sec'))
		target = float(node.get('target_duration_sec') or 0)
		manifest_target = _safe_float(segment.get('target_duration_sec'))
		sync_priority = str(node.get('sync_priority') or 'normal')
		min_ratio, max_ratio = _timing_thresholds(sync_priority, is_chapter=False)
		actual_ratio = _coverage_ratio(actual, target)
		hash_matches = segment.get('voice_text_sha256') == node.get('text_hash')
		status = str(segment.get('status') or '')
		needs_rerun = segment.get('needs_rerun') is True
		if not actual:
			issues.append(f'{node_id}: actual_tts_sec must be positive')
		if abs(manifest_target - target) > 0.05:
			issues.append(f'{node_id}: manifest target_duration_sec {manifest_target:.2f} differs from node target {target:.2f}')
		if not hash_matches:
			issues.append(f'{node_id}: manifest voice_text_sha256 does not match node text hash')
		if status not in MANIFEST_STATUSES:
			issues.append(f'{node_id}: manifest status {status!r} is not one of {sorted(MANIFEST_STATUSES)}')
		if not str(segment.get('audio_path') or '').strip():
			issues.append(f'{node_id}: manifest audio_path must not be empty')
		if actual_ratio < min_ratio:
			issues.append(f'{node_id}: actual coverage ratio {actual_ratio:.2f} below {min_ratio:.2f}')
		if actual_ratio > max_ratio:
			issues.append(f'{node_id}: actual coverage ratio {actual_ratio:.2f} above {max_ratio:.2f}')
		if 'actual_coverage_ratio' in segment and _is_number(segment['actual_coverage_ratio']) and abs(float(segment['actual_coverage_ratio']) - actual_ratio) > 0.03:
			issues.append(f'{node_id}: manifest actual_coverage_ratio {float(segment["actual_coverage_ratio"]):.2f} differs from calculated {actual_ratio:.2f}')
		cumulative_actual += actual
		if index < len(nodes) - 1:
			cumulative_actual += inter_pause
		cumulative_target += target
		drift = round(cumulative_actual - cumulative_target, 3)
		max_drift = HIGH_PRIORITY_MAX_DRIFT_SEC if sync_priority == 'high' else NORMAL_PRIORITY_MAX_DRIFT_SEC
		if abs(drift) > max_drift:
			issues.append(f'{node_id}: cumulative drift {drift:.2f}s exceeds {max_drift:.2f}s')
		if 'cumulative_drift_sec' in segment and _is_number(segment['cumulative_drift_sec']) and abs(float(segment['cumulative_drift_sec']) - drift) > 0.05:
			issues.append(f'{node_id}: manifest cumulative_drift_sec {float(segment["cumulative_drift_sec"]):.2f}s differs from calculated {drift:.2f}s')
		ratio_failed = actual_ratio < min_ratio or actual_ratio > max_ratio
		drift_failed = abs(drift) > max_drift
		must_rerun = (not hash_matches) or status in MANIFEST_RERUN_STATUSES or ratio_failed or drift_failed
		if must_rerun and not needs_rerun:
			issues.append(f'{node_id}: needs_rerun must be true when hash/status/ratio/drift fails')
		if not must_rerun and status in {'approved', 'reused'} and needs_rerun:
			issues.append(f'{node_id}: needs_rerun should be false for approved/reused segment with matching hash and passing timing')
		node_results.append({
			'node_id': node_id,
			'actual_tts_sec': actual,
			'target_duration_sec': target,
			'actual_coverage_ratio': actual_ratio,
			'cumulative_drift_sec': drift,
			'sync_priority': sync_priority,
		})

	chapter_results: list[dict[str, object]] = []
	for chapter in report.get('chapters', []):
		chapter_actual = 0.0
		chapter_target = 0.0
		chapter_nodes = list(chapter.get('nodes', []))
		for index, node in enumerate(chapter_nodes):
			segment = segments.get(str(node.get('id')))
			if segment is None:
				continue
			chapter_actual += _safe_float(segment.get('actual_tts_sec'))
			if index < len(chapter_nodes) - 1:
				chapter_actual += inter_pause
			chapter_target += float(node.get('target_duration_sec') or 0)
		chapter_ratio = _coverage_ratio(chapter_actual, chapter_target)
		chapter_id = str(chapter.get('id') or chapter.get('chapter_id') or 'unknown_chapter')
		if chapter_nodes and chapter_ratio < CHAPTER_MIN_RATIO:
			issues.append(f'{chapter_id}: actual chapter coverage ratio {chapter_ratio:.2f} below {CHAPTER_MIN_RATIO:.2f}')
		chapter_results.append({
			'chapter_id': chapter_id,
			'actual_tts_sec': round(chapter_actual, 3),
			'target_duration_sec': round(chapter_target, 3),
			'actual_coverage_ratio': chapter_ratio,
		})

	return {
		'manifest_path': str(manifest_path),
		'passed': not issues,
		'issues': issues,
		'chapter_results': chapter_results,
		'node_results': node_results,
	}


def validate(path: Path) -> dict[str, object]:
	if path.suffix.lower() == '.json':
		return validate_json_nodes(path)
	return validate_markdown(path)


def main() -> int:
	parser = argparse.ArgumentParser(description='Validate zh-CN voiceover script, semantic nodes, and optional TTS manifest.')
	parser.add_argument('path', type=Path)
	parser.add_argument('--paired', type=Path, help='Paired Markdown/JSON file to compare with the primary file.')
	parser.add_argument('--manifest', type=Path, help='TTS manifest to validate actual durations and cumulative drift.')
	parser.add_argument('--json', action='store_true', help='Print full JSON report.')
	args = parser.parse_args()

	report = validate(args.path)
	all_issues = list(report['issues'])

	if args.paired:
		paired_report = validate(args.paired)
		paired_issues = compare_reports(report, paired_report)
		report['paired_report'] = paired_report
		report['paired_issues'] = paired_issues
		all_issues.extend(paired_report['issues'])
		all_issues.extend(paired_issues)

	if args.manifest:
		manifest_report = validate_manifest(report, args.manifest)
		report['manifest_report'] = manifest_report
		all_issues.extend(manifest_report['issues'])

	report['passed'] = not all_issues
	report['all_issues'] = all_issues

	if args.json:
		print(json.dumps(report, ensure_ascii=False, indent=2))
	else:
		print(f"path: {report['path']}")
		print(f"format: {report['format']}")
		print(f"chapter_count: {report['chapter_count']}")
		print(f"node_count: {report['node_count']}")
		print(f"passed: {report['passed']}")
		if all_issues:
			print('issues:')
			for issue in all_issues:
				print(f'- {issue}')

	return 0 if report['passed'] else 1


if __name__ == '__main__':
	sys.exit(main())
