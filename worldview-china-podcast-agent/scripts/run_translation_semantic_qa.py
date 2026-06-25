#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


BAD_TRANSLATION_PATTERNS: list[tuple[str, str, str]] = [
	("comma_thousands_number", r"\d{1,3}(?:,\d{3})+", "数字仍保留英文千分位逗号，TTS 容易错读；中文稿应写成 30万、1200万等自然读法"),
	("dangling_population_question", r"(?:这|那)?\d+(?:万|,\d{3})?人[^。！？]{0,24}(?:多少|几多).{0,8}人口", "人口问句残留但没有自然回答，常见于 rolling caption/机翻断裂"),
	("broken_year_range", r"(?:过去|未来|接下来).{0,8}(?:50100|\d{4,}|五零一零|五十一百|五十.?一百).{0,8}年", "时间跨度被机翻成不自然数字串，应写成“过去50到100年”等"),
	("machine_translated_hui", r"(?:胡用户界面|夏威夷穆斯林|海族穆斯林|嗨种族|HUI|H UI)", "Hui/Hui Muslims 等源词被错译或残留英文界面词"),
	("machine_translated_halal", r"(?:按摩过的哈拉餐厅|哈拉餐厅|哈拉肉面|Lano牛肉面|兰乔牛肉面)", "清真/兰州牛肉面等词被机翻错译"),
	("religious_call_mistranslation", r"(?:Allahbarum|阿拉巴鲁姆|Wii大师|人类时代|院长如何被保存)", "宗教/历史名词明显机翻错译"),
	("ad_or_sponsor_residue", r"(?:赞助商|本节目由|优惠码|使用代码|Patreon|Provision\s*Capital|Debt\s*Clinic|My\s*Debt\s*Clinic|provisioncap|\.com|www\.)", "广告、赞助、链接或会员 CTA 残留在翻译稿中"),
	("literal_translation_fragment", r"(?:切断你的联系|最大的一笔交易|大麻烦|准备金|回归者|人类时代)", "疑似字面对译词，容易造成语义断裂或敏感误读"),
]


FILLER_PHRASES = [
	"你懂我意思",
	"你知道",
	"我的意思是",
	"呃",
	"嗯",
	"对吧",
	"就是说",
]


CONNECTOR_END_RE = re.compile(r"(?:但是|所以|因为|而且|比如|例如|我的意思是|你知道)[，,。！？!?\s]*$")
REPEATED_FILLER_RE = re.compile(r"(你懂我意思|你知道|我的意思是|呃|嗯|对吧)(?:[，,。.\s]*(?:\1)){1,}")


QUALITATIVE_READING_CRITERIA = {
	"natural_chinese_oral_expression": "中文口语表达自然，不像机器直译或字幕腔",
	"clear_and_easy_to_understand": "普通中文听众能听懂，不需要反复回看上下文",
	"contextual_coherence": "上下文承接顺畅，问答、转折、代词和省略都有明确指向",
	"tts_ready_spoken_style": "适合 TTS 朗读，允许口语但不堆叠低信息口癖",
}


def _read_json(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _candidate_translation_files(run_dir: Path) -> list[Path]:
	candidates = [run_dir / "03-source-translation/source_transcript.zh.json"]
	safe = run_dir / "03b-mainland-publish-safety/source_transcript.zh.safe.json"
	if safe.exists():
		candidates.append(safe)
	return [path for path in candidates if path.exists()]


def _segment_excerpt(text: str, limit: int = 110) -> str:
	value = re.sub(r"\s+", "", text)
	return value if len(value) <= limit else value[:limit] + "..."


def _add_finding(
	findings: list[dict[str, Any]],
	*,
	severity: str,
	rule_id: str,
	message: str,
	file: Path,
	segment: dict[str, Any] | None = None,
	excerpt: str = "",
) -> None:
	payload: dict[str, Any] = {
		"severity": severity,
		"rule_id": rule_id,
		"message": message,
		"file": str(file),
		"excerpt": _segment_excerpt(excerpt),
	}
	if segment is not None:
		payload.update({
			"segment_index": segment.get("segment_index"),
			"source_turn_index": segment.get("source_turn_index"),
			"speaker": segment.get("speaker"),
			"source_start": segment.get("source_start"),
			"source_end": segment.get("source_end"),
		})
	findings.append(payload)


def _filler_count(text: str) -> int:
	return sum(text.count(phrase) for phrase in FILLER_PHRASES)


def _review_segment(path: Path, segment: dict[str, Any], findings: list[dict[str, Any]]) -> None:
	zh_text = str(segment.get("zh_text") or segment.get("text") or "")
	source_text = str(segment.get("source_text") or "")
	if not zh_text.strip():
		_add_finding(
			findings,
			severity="fail",
			rule_id="empty_translation_segment",
			message="翻译 segment 为空，可能导致后续音频或字幕缺段",
			file=path,
			segment=segment,
			excerpt=source_text,
		)
		return
	for rule_id, pattern, message in BAD_TRANSLATION_PATTERNS:
		if re.search(pattern, zh_text, flags=re.IGNORECASE):
			_add_finding(
				findings,
				severity="fail",
				rule_id=rule_id,
				message=message,
				file=path,
				segment=segment,
				excerpt=zh_text,
			)
	if REPEATED_FILLER_RE.search(zh_text):
		_add_finding(
			findings,
			severity="fail",
			rule_id="repeated_filler_phrase",
			message="同一口癖连续重复，翻译稿需要改成自然中文表达",
			file=path,
			segment=segment,
			excerpt=zh_text,
		)
	filler_count = _filler_count(zh_text)
	if filler_count >= max(4, len(zh_text) // 45):
		_add_finding(
			findings,
			severity="fail",
			rule_id="dense_spoken_filler",
			message="口癖密度过高，应在翻译稿阶段删减“你知道/我的意思是/呃/嗯”等低信息填充词",
			file=path,
			segment=segment,
			excerpt=zh_text,
		)
	if CONNECTOR_END_RE.search(zh_text):
		_add_finding(
			findings,
			severity="fail",
			rule_id="dangling_connector_end",
			message="句子停在转折/因果/举例连接词上，可能是翻译或字幕拼接断裂",
			file=path,
			segment=segment,
			excerpt=zh_text,
		)
	if source_text and re.search(r"(sponsored by|our sponsor|visit .*\.com|use code|provision capital|debt clinic)", source_text, flags=re.IGNORECASE):
		_add_finding(
			findings,
			severity="fail",
			rule_id="source_ad_text_not_removed",
			message="源文本中的广告/赞助片段没有在翻译前删除",
			file=path,
			segment=segment,
			excerpt=source_text,
		)


def _review_translation_file(path: Path, findings: list[dict[str, Any]]) -> dict[str, Any]:
	data = _read_json(path)
	segments = data.get("segments")
	if not isinstance(segments, list) or not segments:
		_add_finding(
			findings,
			severity="fail",
			rule_id="missing_translation_segments",
			message="翻译 JSON 没有 segments，不能进入后续播客稿生成",
			file=path,
			excerpt=str(data)[:160],
		)
		return {"path": str(path), "sha256": _sha256(path), "segment_count": 0}
	for segment in segments:
		if isinstance(segment, dict):
			_review_segment(path, segment, findings)
	return {"path": str(path), "sha256": _sha256(path), "segment_count": len(segments)}


def _resolved_path(value: Any) -> str:
	try:
		return str(Path(str(value)).expanduser().resolve())
	except OSError:
		return str(Path(str(value)).expanduser())


def _write_qualitative_reading_packet(output_dir: Path, reviewed: list[dict[str, Any]]) -> None:
	lines = [
		"# Translation Qualitative Reading Packet",
		"",
		"审核目标：请从中文听众视角完整阅读当前翻译稿，判断它是否通顺、好理解、符合中文口语表达习惯。",
		"不要只查关键词；如果读起来像机器直译、上下文断裂、问答不接、代词不明或口癖堆叠，应判 FAIL 并指出位置。",
		"",
		"## Criteria",
		"",
	]
	for key, description in QUALITATIVE_READING_CRITERIA.items():
		lines.append(f"- {key}: {description}")
	lines.append("")
	for item in reviewed:
		path = Path(str(item["path"]))
		if not path.exists():
			continue
		data = _read_json(path)
		lines.extend([
			f"## File: {path}",
			"",
			f"- sha256: {item['sha256']}",
			f"- segments: {item['segment_count']}",
			"",
		])
		for segment in data.get("segments") or []:
			if not isinstance(segment, dict):
				continue
			lines.extend([
				f"### {segment.get('segment_index')} {segment.get('speaker')} [{segment.get('source_start')} - {segment.get('source_end')}]",
				"",
				str(segment.get("zh_text") or segment.get("text") or "").strip(),
				"",
			])
	template = {
		"schema_version": "worldview-china-translation-reading-review.v1",
		"status": "PASS | FAIL",
		"reviewer": "human | subagent | main_agent",
		"review_scope": "full_translation_read",
		"read_entire_text": True,
		"criteria": {key: "PASS | FAIL" for key in QUALITATIVE_READING_CRITERIA},
		"reviewed_files": [item["path"] for item in reviewed],
		"reviewed_file_hashes": {item["path"]: item["sha256"] for item in reviewed},
		"findings": [
			{
				"severity": "fail | warning",
				"segment_index": 0,
				"issue": "哪里不通顺/不好理解/不符合中文表达习惯",
				"suggestion": "建议如何回到 03 修复",
			}
		],
		"notes": "简要说明整体阅读结论",
	}
	output_dir.mkdir(parents=True, exist_ok=True)
	(output_dir / "translation-reading-review-input.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
	_write_json(output_dir / "translation-reading-review-template.json", template)


def _validate_qualitative_reading_review(
	output_dir: Path,
	reviewed: list[dict[str, Any]],
	findings: list[dict[str, Any]],
) -> dict[str, Any]:
	result_path = output_dir / "translation-reading-review-result.json"
	if not result_path.exists():
		_add_finding(
			findings,
			severity="fail",
			rule_id="missing_qualitative_reading_review",
			message="缺少独立阅读审核结果；03c 必须让审核人完整阅读中文稿，判断是否通顺、好理解、符合中文口语表达习惯",
			file=result_path,
			excerpt=str(output_dir / "translation-reading-review-input.md"),
		)
		return {"status": "MISSING", "path": str(result_path)}
	try:
		review = _read_json(result_path)
	except json.JSONDecodeError as exc:
		_add_finding(
			findings,
			severity="fail",
			rule_id="invalid_qualitative_reading_review_json",
			message=f"阅读审核结果 JSON 无法解析：{exc}",
			file=result_path,
		)
		return {"status": "INVALID", "path": str(result_path)}
	status = str(review.get("status") or "")
	if status != "PASS":
		_add_finding(
			findings,
			severity="fail",
			rule_id="qualitative_reading_review_not_pass",
			message="独立阅读审核没有 PASS；需要回到 03 修复中文表达和上下文承接",
			file=result_path,
			excerpt=str(review.get("notes") or ""),
		)
	if review.get("read_entire_text") is not True:
		_add_finding(
			findings,
			severity="fail",
			rule_id="qualitative_review_did_not_read_entire_text",
			message="阅读审核必须确认 read_entire_text=true，不能只抽查少数片段",
			file=result_path,
		)
	criteria = review.get("criteria") if isinstance(review.get("criteria"), dict) else {}
	for key, description in QUALITATIVE_READING_CRITERIA.items():
		if criteria.get(key) != "PASS":
			_add_finding(
				findings,
				severity="fail",
				rule_id="qualitative_reading_criterion_failed",
				message=f"阅读审核维度未 PASS：{key}，{description}",
				file=result_path,
				excerpt=str(criteria.get(key) or ""),
			)
	reviewed_files = {_resolved_path(value) for value in review.get("reviewed_files") or []}
	raw_hashes = review.get("reviewed_file_hashes") if isinstance(review.get("reviewed_file_hashes"), dict) else {}
	reviewed_hashes = {_resolved_path(key): str(value) for key, value in raw_hashes.items()}
	for item in reviewed:
		resolved = _resolved_path(item["path"])
		if resolved not in reviewed_files:
			_add_finding(
				findings,
				severity="fail",
				rule_id="qualitative_review_missing_current_file",
				message="阅读审核没有覆盖当前翻译文件",
				file=result_path,
				excerpt=item["path"],
			)
		elif reviewed_hashes.get(resolved) != item["sha256"]:
			_add_finding(
				findings,
				severity="fail",
				rule_id="qualitative_review_stale_file_hash",
				message="阅读审核记录的文件 hash 和当前翻译文件不一致，说明审核结果已过期",
				file=result_path,
				excerpt=item["path"],
			)
	for finding in review.get("findings") or []:
		if isinstance(finding, dict) and finding.get("severity") == "fail":
			_add_finding(
				findings,
				severity="fail",
				rule_id="qualitative_reading_review_fail_finding",
				message=str(finding.get("issue") or "阅读审核发现中文表达问题"),
				file=result_path,
				excerpt=str(finding.get("suggestion") or ""),
			)
	return {
		"status": "PASS" if not any(finding.get("severity") == "fail" for finding in findings if finding.get("file") == str(result_path)) and status == "PASS" else "FAIL",
		"path": str(result_path),
		"reviewer": review.get("reviewer"),
		"review_scope": review.get("review_scope"),
		"read_entire_text": review.get("read_entire_text"),
	}


def _write_report(path: Path, result: dict[str, Any]) -> None:
	lines = [
		"# Translation Semantic QA",
		"",
		f"- status: {result['status']}",
		f"- files_reviewed: {result['summary']['files_reviewed']}",
		f"- fail_findings: {result['summary']['fail_findings']}",
		f"- warning_findings: {result['summary']['warning_findings']}",
		f"- qualitative_reading_review: {result['summary']['qualitative_reading_review_status']}",
		"",
	]
	if result["findings"]:
		lines.append("## Findings")
		lines.append("")
		for index, finding in enumerate(result["findings"], start=1):
			lines.append(
				f"{index}. [{finding['severity']}] {finding['rule_id']} "
				f"segment={finding.get('segment_index')} {finding['message']}"
			)
			lines.append(f"   excerpt: {finding.get('excerpt') or ''}")
			lines.append("")
	else:
		lines.append("No fail findings.")
		lines.append("")
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text("\n".join(lines), encoding="utf-8")


def run_review(run_dir: Path, stage: str = "after_translation") -> dict[str, Any]:
	output_dir = run_dir / "03c-translation-semantic-qa"
	findings: list[dict[str, Any]] = []
	files = _candidate_translation_files(run_dir)
	if not files:
		_add_finding(
			findings,
			severity="fail",
			rule_id="missing_translation_file",
			message="未找到 03-source-translation/source_transcript.zh.json",
			file=run_dir / "03-source-translation/source_transcript.zh.json",
		)
	reviewed = [_review_translation_file(path, findings) for path in files]
	_write_qualitative_reading_packet(output_dir, reviewed)
	qualitative_review = _validate_qualitative_reading_review(output_dir, reviewed, findings)
	fail_count = sum(1 for finding in findings if finding.get("severity") == "fail")
	warning_count = sum(1 for finding in findings if finding.get("severity") == "warning")
	result = {
		"schema_version": "worldview-china-translation-semantic-qa.v1",
		"stage": stage,
		"status": "PASS" if fail_count == 0 else "FAIL",
		"reviewed_files": [item["path"] for item in reviewed],
		"reviewed_file_hashes": {item["path"]: item["sha256"] for item in reviewed},
		"summary": {
			"files_reviewed": len(reviewed),
			"segments_reviewed": sum(int(item.get("segment_count") or 0) for item in reviewed),
			"fail_findings": fail_count,
			"warning_findings": warning_count,
			"qualitative_reading_review_status": qualitative_review["status"],
		},
		"policy": {
			"sponsor_ads_must_be_removed_before_translation": True,
			"dense_spoken_fillers_must_be_reduced": True,
			"machine_translation_artifacts_block_script_generation": True,
			"comma_thousands_numbers_block_tts": True,
			"independent_qualitative_reading_required": True,
		},
		"qualitative_reading_review": qualitative_review,
		"findings": findings,
	}
	_write_json(output_dir / "translation-semantic-qa-result.json", result)
	_write_report(output_dir / "translation-semantic-qa-report.md", result)

	run_manifest_path = run_dir / "run_manifest.json"
	run_manifest = _read_json(run_manifest_path) if run_manifest_path.exists() else {}
	run_manifest.setdefault("nodes", {})["03c-translation-semantic-qa"] = {
		"status": "pass" if result["status"] == "PASS" else "fail",
		"qa_result": str(output_dir / "translation-semantic-qa-result.json"),
		"qa_report": str(output_dir / "translation-semantic-qa-report.md"),
		"qualitative_reading_review": str(output_dir / "translation-reading-review-result.json"),
		"qualitative_reading_input": str(output_dir / "translation-reading-review-input.md"),
		"reviewed_files": result["reviewed_files"],
	}
	_write_json(run_manifest_path, run_manifest)
	return result


def main() -> int:
	parser = argparse.ArgumentParser(description="Review Worldview China translation text before podcast script generation.")
	parser.add_argument("--run-dir", required=True, type=Path)
	parser.add_argument("--stage", default="after_translation")
	args = parser.parse_args()
	result = run_review(args.run_dir.expanduser().resolve(), args.stage)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
	raise SystemExit(main())
