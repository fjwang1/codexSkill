---
name: worldview-china-bilibili-publish-metadata
description: "Generate Bilibili upload metadata for Worldview China translated YouTube podcast/video runs after video/final_video.mp4, cover/cover_4k.png, video_title.txt, and cover/cover_title.json exist. Use this before bilibili-video-upload-draft to create bilibili_upload_metadata.json, publish_info.txt, and a tag report with YouTube/video-podcast-specific tags such as 外网热议, 海外视角, 中国观察, 国际播客, 中文配音, 中国经济, 中美关系, or other concrete topic tags; do not use article-only tags like 外刊解读 unless the source is actually an article."
---

# Worldview China Bilibili Publish Metadata

This skill is the Bilibili metadata node for Worldview China translated YouTube podcast/video runs. It exists because article-video tags such as `外刊解读` do not fit a source-video podcast workflow.

It does not open Bilibili and does not automate Chrome. After this node passes, call the standalone upload skill:

```text
/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md
```

## Contract

Generate `bilibili_upload_metadata.json` as the source of truth for the upload draft.

Rules:

- Use `video_title.txt` as the exact Bilibili title.
- Use `cover/cover_4k.png` as the upload cover.
- Use `video/final_video.mp4` as the upload video.
- Write `publish_info.txt` with exactly one concise public-facing content summary sentence. The Bilibili description must tell viewers what this episode discusses, using the episode subtitle, chapter/script content, and key topics as evidence. Do not describe the production method.
- Target 8-10 visible Bilibili tags.
- Tags must fit a translated YouTube podcast/video product, not an article product.
- Set `category` to `知识`.
- Set `creation_declaration` to `含AI生成内容`.
- Preserve existing schedule fields from an existing `bilibili_upload_metadata.json` when present.
- For series episode runs, preserve the schedule seed written by `04b-series-episodes`, where episode 1 uses the user-provided publish time and episode N adds N-1 hours. Record `episode_index`, `episode_count`, `episode_subtitle`, `series_title_prefix`, and `cover_title_text` from `episode_manifest.json` / `cover_title.json`.

## Inputs

Required:

```text
<run_dir>/video/final_video.mp4
<run_dir>/cover/cover_4k.png
<run_dir>/video_title.txt
<run_dir>/cover/cover_title.json
```

Recommended:

```text
<run_dir>/02-source-capture/youtube-media/source.info.json
<run_dir>/03-source-translation/source_transcript.zh.md
<run_dir>/03-source-translation/chapter_segments.json
```

## Outputs

```text
<run_dir>/bilibili_upload_metadata.json
<run_dir>/publish_info.txt
<run_dir>/10-bilibili-publish/publish_metadata_report.json
```

`bilibili_upload_metadata.json` uses `schema_version="bilibili_upload_metadata.v1"` so the existing `bilibili-video-upload-draft` skill can consume it directly.

## Tag Strategy

Start with platform/product positioning:

```text
外网热议
海外视角
中国观察
国际观察
```

Then add source identity and concrete topic tags when supported by title, YouTube metadata, chapter segments, or translated transcript:

```text
上海美国商会前会长
国际播客
中文配音
中国经济
财经解读
中美关系
贸易战
中国制造
供应链
全球南方
中国市场
外企在中国
```

Hard rules:

- Do not default to `外刊解读`, `外刊精读`, `英语学习`, or `英语听力`.
- Do not use a whole sentence or the whole title as a tag.
- Do not include `#`, spaces, punctuation, commas, quotes, or brackets.
- Keep tags short, search-like, and under 20 Chinese characters.
- Prefer the source speaker/role identity when it is concise and already validated by `cover/cover_title.json`.

## Command

Use the bundled script:

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-publish-metadata/scripts/generate_bilibili_publish_metadata.py \
  --run-dir <run_dir>
```

For a dry metadata test without touching production output:

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-publish-metadata/scripts/generate_bilibili_publish_metadata.py \
  --run-dir <run_dir> \
  --output /Volumes/GT34/Generated/bilibili_metadata_tests/worldview.json \
  --report /Volumes/GT34/Generated/bilibili_metadata_tests/worldview.report.json
```

## Gate

Pass only if:

```text
bilibili_upload_metadata.json exists
publish_info.txt exists
10-bilibili-publish/publish_metadata_report.json exists
metadata.schema_version == bilibili_upload_metadata.v1
metadata.workflow == worldview-china-podcast-agent
metadata.title equals video_title.txt
metadata.video_path == video/final_video.mp4
metadata.cover_path == cover/cover_4k.png
metadata.category == 知识
metadata.creation_declaration == 含AI生成内容
metadata.tags has 8-10 unique tags
metadata.tags does not contain 外刊解读, 外刊精读, 英语学习, or 英语听力 unless explicitly justified by source type
metadata.description does not contain local file paths, model names, manifest paths, internal QA notes, or production-method filler such as 中文配音版本, 保留原视频画面, 替换为中文对话音频, 方便中文观众理解
metadata.description is exactly one public-facing content summary sentence and contains concrete episode topics supported by the current episode script, subtitle, chapter segments, title, or cover title
if episode_manifest.json exists, metadata.title equals the ordered episode title in video_title.txt
if episode_manifest.json exists, metadata.episode_index and metadata.episode_count match episode_manifest.json
if episode_manifest.json exists, metadata.cover_title_text equals cover/cover_title.json.title_text
if scheduled_publish_at exists, metadata preserves scheduled_publish_at, scheduled_publish_timezone, and schedule_source from the preexisting metadata seed
metadata.description does not include title/source/channel/url/tag/chapter blocks such as 观点身份, 核心议题, 身份依据, 原视频标题, 来源频道, 原链接, 标签, or 章节
```

After this gate passes, invoke `bilibili-video-upload-draft` directly. Do not reimplement Bilibili Chrome automation in this skill.
