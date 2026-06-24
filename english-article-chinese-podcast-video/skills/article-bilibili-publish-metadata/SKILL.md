---
name: article-bilibili-publish-metadata
description: Generate and validate Bilibili upload metadata for an English-article-to-Chinese video project after video_title.txt and publish_info.txt exist. Use for article podcast or explainer projects that need bilibili_upload_metadata.json with title, description, high-signal Bilibili tags, category, AI declaration, file paths, and tag provenance before invoking bilibili-video-upload-draft.
---

# Article Bilibili Publish Metadata

Generate `bilibili_upload_metadata.json` as the source of truth for Bilibili upload and submission. This node owns the publishing description and tag strategy; video rendering should not hard-code platform tags.

## Inputs

Run after `video_title.txt` and `publish_info.txt` exist.

Recommended context:

```text
source/source_metadata.json
planning/article_brief.json
cover/cover_title.json
video_title.txt
publish_info.txt
```

## Command

Use the bundled script:

```bash
python3 scripts/generate_bilibili_publish_metadata.py --project-dir <project>
```

Outputs:

```text
<project>/bilibili_upload_metadata.json
<project>/planning/bilibili_tag_report.json
```

For tests or dry runs, keep production metadata untouched:

```bash
python3 scripts/generate_bilibili_publish_metadata.py \
  --project-dir <project> \
  --output /Volumes/GT34/Generated/bilibili_metadata_tests/<slug>.json \
  --report /Volumes/GT34/Generated/bilibili_metadata_tests/<slug>.report.json
```

## Tag Strategy

Target 8-10 visible Bilibili tags. The first three tags should orient cold-start traffic, not merely describe the article source.

Prefer this order:

1. Account/content positioning: `外刊解读`, `国际观察`, then `财经解读` or `社会观察` when supported.
2. Source publication if confirmed: `经济学人`, `金融时报`, `外交政策`, `彭博社`, `外交学者`, etc.
3. China/Asia scope only when material to the article: `中国观察`, `中国经济`, `亚洲观察`.
4. Concrete topic tags from title, article brief, cover title keyword heat check, motifs, terminology glossary, and proper noun glossary.
5. Fallback tags only when still underfilled and clearly compatible: `地缘政治`, `国际经济`, `政策观察`, `供应链`, `产业观察`, `全球化`.

Hard rules:

- Do not use `外刊精读` by default. Use it only for true English-learning/close-reading videos with source text or bilingual teaching value.
- Do not use `英语学习`, `英语听力`, or similar tags unless the video is actually an English-learning product.
- Do not turn a whole title or sentence into a tag.
- Keep each tag short, search-like, and user-facing; reject sentence fragments such as `为什么...`, `...正在形成...`, or long article title subtitles.
- Remove duplicates, punctuation, spaces, `#`, commas, quotes, and brackets.
- Keep each tag under 20 Chinese characters, but prefer 2-10 characters.

## Metadata Rules

`bilibili_upload_metadata.json` must use:

```json
{
  "schema_version": "bilibili_upload_metadata.v1",
  "title": "same as video_title.txt",
  "description": "title + 先行提要",
  "tags": ["外刊解读", "国际观察"],
  "category": "知识",
  "creation_declaration": "含AI生成内容",
  "scheduled_publish_at": null,
  "scheduled_publish_timezone": "Asia/Shanghai",
  "schedule_source": null,
  "video_path": "video/final_video.mp4",
  "cover_path": "cover/cover_4k.png",
  "publish_info_path": "publish_info.txt"
}
```

`description` is the user-facing Bilibili intro. Keep it short: title, blank line, then `先行提要：` with 1-3 supported sentences. Do not include `章节：`, timestamp ranges such as `00:00-01:09`, chapter slugs, local paths, model names, QA details, or production manifests. `publish_info.txt` may still contain the chapter timeline for internal QA and release records, but it must not be copied into `description`.

Preserve existing schedule fields from an existing metadata file unless the caller overrides the output path. This metadata node does not recalculate current-time scheduling; Daily orchestration computes the initial future slot, and `bilibili-video-upload-draft` performs the final upload-time rollover for passed 11:00/17:00 daily slots.
