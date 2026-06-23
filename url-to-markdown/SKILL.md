---
name: url-to-markdown
description: "Compatibility entrypoint for old URL-to-Markdown requests. Use when a user asks to turn a URL into Markdown, but prefer the split workflow: first use url-page-capture to capture page material from the URL, then use page-to-chinese-markdown or another document-writing skill to produce the final Markdown document."
---

# URL To Markdown Compatibility Entrypoint

This skill has been split into two clearer skills:

1. `url-page-capture`: URL -> captured page material.
2. `page-to-chinese-markdown`: captured page material -> Chinese Markdown document.

## Required Workflow

When a user asks for URL-to-Markdown:

1. Use `url-page-capture` to fetch and validate the webpage content.
2. Use an appropriate document skill to write the final Markdown.
3. For Chinese article/document output, use `page-to-chinese-markdown`.

Do not run a separate one-piece workflow from this skill. This file exists only to route old prompts to the split workflow.

## Important Boundary

For third-party copyrighted publisher articles, do not produce a full verbatim article or full faithful translation unless the user provides the text or confirms they have rights. Use `page-to-chinese-markdown` to select the correct output mode.
