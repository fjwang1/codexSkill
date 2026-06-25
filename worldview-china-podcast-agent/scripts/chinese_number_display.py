#!/usr/bin/env python3
from __future__ import annotations

import re


COMMA_THOUSANDS_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+)(?![\d.])")


def _compact_chinese_display_number(token: str) -> str:
	value = int(token.replace(",", ""))
	if value >= 100_000_000 and value % 100_000_000 == 0:
		return f"{value // 100_000_000}亿"
	if value >= 10_000 and value % 10_000 == 0:
		return f"{value // 10_000}万"
	return str(value)


def normalize_comma_thousands_for_chinese_display(text: str) -> str:
	return COMMA_THOUSANDS_RE.sub(lambda match: _compact_chinese_display_number(match.group(1)), str(text or ""))
