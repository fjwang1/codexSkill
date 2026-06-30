#!/usr/bin/env python3
"""轻量检查中国故事单人口播稿。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
	if len(sys.argv) != 2:
		print("用法：lint_single_host_script.py <single_host_script.md>", file=sys.stderr)
		return 2

	path = Path(sys.argv[1])
	if not path.exists():
		print(f"缺少稿件文件：{path}", file=sys.stderr)
		return 1

	text = path.read_text(encoding="utf-8")
	errors: list[str] = []
	warnings: list[str] = []

	if "Speaker 0:" in text or "Speaker 1:" in text:
		errors.append("稿件包含 Speaker 0/Speaker 1 标签")
	if re.search(r"^Speaker\s+\d+\s*:", text, flags=re.MULTILINE):
		errors.append("稿件包含说话人回合标签")
	if not re.search(r"^#\s*(单人口播稿|单人视频讲解稿)", text, flags=re.MULTILINE):
		warnings.append("标题没有以 '# 单人口播稿' 或 '# 单人视频讲解稿' 开头")
	if "## 正文" not in text:
		errors.append("缺少 '## 正文'")

	source_markers = (
		"来源文章",
		"外媒",
		"外刊",
		"原文",
		"这篇文章",
		"报道指出",
		"报道说",
		"文章认为",
		"作者写道",
		"The Economist",
		"Economist",
		"Bloomberg",
		"Foreign Policy",
		"Financial Times",
		"New York Times",
		"Wall Street Journal",
		"Washington Post",
		"Reuters",
		"Associated Press",
		"经济学人",
		"彭博社",
		"外交政策",
		"金融时报",
		"纽约时报",
		"华尔街日报",
		"华盛顿邮报",
		"路透社",
		"美联社",
	)
	for marker in source_markers:
		if marker.lower() in text.lower():
			errors.append(f"稿件包含来源露出标记：{marker}")
	if re.search(r"据.{0,12}(报道|消息|文章|媒体)", text):
		errors.append("稿件包含 '据...报道/媒体/文章' 来源框架")

	body = text.split("## 正文", 1)[-1].strip()
	if len(body) < 2200:
		errors.append("正文过短，像是未完成稿；完整中国故事口播稿通常不应低于 2200 字符")
	opening = body[:220]
	bad_openings = ("今天我们来读", "今天我们来看一篇文章", "本文主要讲", "这篇文章主要讲", "最近有一篇", "有一篇文章")
	if any(phrase in opening for phrase in bad_openings):
		errors.append("开头像文章报告或外部来源解读，而不是中国故事钩子")

	process_artifacts = (
		r"\bNo\.",
		r"\bNo\b",
		r"\bYes\b",
		r"TODO",
		r"FIXME",
		r"待补",
		r"这里需要",
		r"我应该",
		r"纠正一下",
		r"\?\s*No",
	)
	if any(re.search(pattern, body, flags=re.IGNORECASE) for pattern in process_artifacts):
		errors.append("正文包含生成过程残留、英文自我纠错或未完成标记")

	if not any(mark in body[:1600] for mark in ("为什么", "问题", "真正", "关键")):
		warnings.append("主问题可能没有足够早地出现")

	early = body[:900]
	driver_patterns = (
		r"(几个|四个|五个|六个).{0,12}(变量|原因|因素|驱动)",
		r"(变量|原因|因素|驱动).{0,12}(几个|四个|五个|六个)",
		r"第一[，,、].{0,80}第二[，,、].{0,80}第三",
	)
	if not any(re.search(pattern, early) for pattern in driver_patterns):
		warnings.append("前段变量组不明显；中国故事稿件在材料支持时应尽早说出主要变量")

	if not any(mark in body for mark in ("但", "不过", "问题是", "真正", "不是", "限制", "约束", "反过来")):
		warnings.append("稿件可能缺少张力、反差或约束")

	if re.search(r"（[^）]+）", body):
		warnings.append("稿件包含括号内容；确认这些内容适合被 TTS 读出来")

	for warning in warnings:
		print(f"提示：{warning}")
	for error in errors:
		print(f"错误：{error}", file=sys.stderr)

	if errors:
		return 1
	print("lint 通过")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
