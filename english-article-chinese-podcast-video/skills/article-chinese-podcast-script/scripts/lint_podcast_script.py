#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


BANNED_PATTERNS = [
	r"这篇文章(说|讲|提到|指出|认为)",
	r"文章(说|讲|提到|指出|认为|写道)",
	r"作者(说|讲|提到|指出|认为|写道)",
	r"原文(说|讲|提到|指出|认为|写道|里)",
	r"本文(说|讲|提到|指出|认为|分析)",
]

QUESTION_MARKERS = ("?", "？", "为什么", "怎么", "是不是", "难道", "那", "所以", "什么意思", "有没有", "会不会")


def parse_turns(text: str, allowed_names: set[str] | None = None) -> list[tuple[str, str]]:
	turns: list[tuple[str, str]] = []
	current_name: str | None = None
	current_lines: list[str] = []
	for raw_line in text.splitlines():
		line = raw_line.strip()
		if line.startswith("#"):
			continue
		match = re.match(r"^([^：:]{1,20})[：:]\s*(.*)$", line)
		if match:
			name = match.group(1).strip()
			if allowed_names is not None and name not in allowed_names:
				continue
			if current_name:
				turns.append((current_name, "\n".join(current_lines).strip()))
			current_name = name
			current_lines = [match.group(2).strip()]
		elif current_name and line:
			current_lines.append(line)
	if current_name:
		turns.append((current_name, "\n".join(current_lines).strip()))
	return [(name, body) for name, body in turns if body]


def contains_question(text: str) -> bool:
	return any(marker in text for marker in QUESTION_MARKERS)


def longest_run(turns: list[tuple[str, str]], name: str) -> int:
	best = 0
	current = 0
	for turn_name, _body in turns:
		if turn_name == name:
			current += 1
			best = max(best, current)
		else:
			current = 0
	return best


def count_banned(text: str) -> dict[str, int]:
	counts: dict[str, int] = {}
	for pattern in BANNED_PATTERNS:
		count = len(re.findall(pattern, text))
		if count:
			counts[pattern] = count
	return counts


def main() -> None:
	parser = argparse.ArgumentParser(description="Lint a Chinese two-person podcast script.")
	parser.add_argument("script", type=Path)
	parser.add_argument("--host", default="Speaker 0")
	parser.add_argument("--expert", default="Speaker 1")
	parser.add_argument("--min-turns", type=int, default=18)
	parser.add_argument("--json", action="store_true")
	args = parser.parse_args()

	text = args.script.read_text(encoding="utf-8")
	turns = parse_turns(text, {args.host, args.expert})
	names = sorted(set(name for name, _body in turns))
	host_turns = [body for name, body in turns if name == args.host]
	expert_turns = [body for name, body in turns if name == args.expert]
	host_questions = [body for body in host_turns if contains_question(body)]
	banned = count_banned(text)

	host_chars = sum(len(body) for body in host_turns)
	expert_chars = sum(len(body) for body in expert_turns)
	total_chars = max(1, host_chars + expert_chars)

	failures: list[str] = []
	warnings: list[str] = []
	if len(turns) < args.min_turns:
		failures.append(f"对话轮次太少，可能不像完整播客：{len(turns)} < {args.min_turns}。")
	if args.host not in names:
		failures.append(f"缺少主持人角色：{args.host}")
	if args.expert not in names:
		failures.append(f"缺少回答者角色：{args.expert}")
	unexpected = [name for name in names if name not in {args.host, args.expert}]
	if unexpected:
		failures.append(f"正文检测到非标准说话人：{', '.join(unexpected)}")
	if host_turns and len(host_questions) / len(host_turns) < 0.45:
		failures.append("主持人提问/追问比例过低。")
	if expert_turns and expert_chars / total_chars < 0.45:
		warnings.append("回答者内容占比偏低，可能解释不够。")
	if host_turns and host_chars / total_chars > 0.55:
		warnings.append("主持人内容占比过高，可能不像主持追问。")
	if longest_run(turns, args.expert) > 2:
		failures.append("回答者连续发言超过 2 轮，容易变成独白。")
	if sum(banned.values()) > 3:
		failures.append("过多出现“文章/原文/作者提到”等读稿感表达。")

	result = {
		"turn_count": len(turns),
		"speakers": names,
		"host_turns": len(host_turns),
		"expert_turns": len(expert_turns),
		"host_question_turns": len(host_questions),
		"host_char_ratio": round(host_chars / total_chars, 3),
		"expert_char_ratio": round(expert_chars / total_chars, 3),
		"banned_counts": banned,
		"failures": failures,
		"warnings": warnings,
		"ok": not failures,
	}
	if args.json:
		print(json.dumps(result, ensure_ascii=False, indent=2))
	else:
		status = "OK" if result["ok"] else "FAIL"
		print(f"{status}: {args.script}")
		print(json.dumps(result, ensure_ascii=False, indent=2))
	raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
	main()
