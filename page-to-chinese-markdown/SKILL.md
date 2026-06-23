---
name: page-to-chinese-markdown
description: Convert captured webpage/article material into a Chinese Markdown document. Use after `url-page-capture` has produced page metadata and source material, or when the user provides article/page text directly. Supports faithful full Chinese translation for user-owned, authorized, internal, public-domain, or permissively licensed content; for third-party copyrighted publisher articles, produces a Chinese reading document or asks for authorized source text instead of reproducing the full article.
---

# Page To Chinese Markdown

## Goal

Turn captured page material into a Chinese Markdown document.

This skill does not fetch URLs. It consumes:

- a `url-page-capture` capture package,
- a local text/HTML/Markdown file,
- pasted source text,
- or another structured page extraction artifact.

## First Decision: Translation Mode

Before writing the document, decide which mode is allowed.

### Faithful Full Translation Mode

Use this mode when one of these is true:

- the user provided the full source text in the chat or a local file,
- the content is user-owned or internal,
- the user confirms they have translation rights,
- the content is public-domain or permissively licensed,
- the source is short enough to be safely transformed under applicable content limits.

In this mode, produce a complete Chinese Markdown translation that preserves the original meaning, structure, order, claims, numbers, caveats, tone, and paragraph boundaries. Do not summarize. Do not add analysis into the body. Keep headings, lists, tables, quotes, and links in equivalent Markdown form.

### Reading Document Mode

Use this mode for third-party copyrighted publisher articles fetched from the web, including paywalled or archived news articles, unless the user provides the text or confirms rights.

In this mode, do not reproduce the full article or full translation. Produce a Chinese Markdown reading document with metadata, source links, summary, structured notes, key claims, context, and short sparse excerpts only when needed.

If the user explicitly asks for a faithful full translation of such an article, explain that exact full translation requires user-provided or authorized source text, then offer either:

- a Chinese reading document, or
- a faithful translation of a user-provided excerpt.

## Faithful Full Translation Rules

When full translation mode is allowed:

1. Translate into natural, accurate Chinese.
2. Preserve the original document order.
3. Preserve the original heading hierarchy.
4. Preserve paragraph boundaries unless the source paragraph is malformed.
5. Preserve all numbers, dates, names, locations, institutions, currencies, and units.
6. Keep proper nouns in English when common Chinese rendering is uncertain; optionally add Chinese translation once.
7. Do not omit hedges such as "may", "could", "some experts say", "according to".
8. Do not strengthen or weaken claims.
9. Do not add commentary inside the translated body.
10. Add a short source note at the end if useful.

Recommended structure:

```markdown
# <中文标题>

> 原文：<source URL>
> 译文模式：忠实全文翻译

<translated body preserving original structure>

## 译注

- ...
```

Only include `译注` when it helps clarify terms, currencies, or ambiguous proper nouns.

## Reading Document Rules

When reading document mode is required:

```markdown
# <中文标题>

> 原文：<source URL>
> 归档：<archive URL if any>
> 文档模式：中文阅读文档，不是原文逐字翻译

## 元信息

...

## 摘要

...

## 关键要点

- ...

## 详细笔记

...

## 重要数字与说法

| 数字或说法 | 语境 |
| --- | --- |

## 值得继续追问的问题

- ...

## 来源与抽取说明

- ...
```

Keep it useful and complete as a reading artifact, but do not pretend it is the original text.

## Input Contract From url-page-capture

Expect a capture package with fields like:

- `input_url`
- `resolved_url`
- `title`
- `metadata`
- `access_limited`
- `source_markdown`
- `source_markdown_length`
- `manifest`

If `access_limited` is true or source material is clearly navigation/CAPTCHA/subscription UI, reject the input and ask for a valid capture.

## Quality Checklist

Before delivering:

- The output language is Chinese.
- The document is Markdown.
- The selected mode is clearly stated.
- In full translation mode, the document is not a summary.
- In reading document mode, the document is not represented as a full translation.
- Source URL and archive URL, if any, are preserved.
- No paragraphs or claims are fabricated.
