---
name: english-article-chinese-single-host-video-remake
description: 从选题或本地文章开始，将英文或中文长文改造成以中国视角讲述中国故事的中文单人口播解释视频，并沿用原流程生成音频、字幕、视频和 B 站投稿草稿/提交。未提供本地文章路径时，先调用 china-longform-article-selection 选择最近三个完整自然日内发布、已去重、正文可获取的中国相关英文深度好文；提供本地文章路径时直接标准化为 source/article.txt。只保留原单人口播视频制作流程。
---

# 中国故事单人口播视频

这是“以中国视角讲述中国故事”的单人口播视频总控 skill。输入可以是本地文章文件路径，也可以没有输入文章。没有本地文章路径时，先按本 skill 的选题依赖选择 1 篇可用文章；有本地文章路径时，直接进入本地文章标准化。

本 skill 只保留原流程视频制作：

```text
topic selection when no local article is provided
-> selected/local source article material
-> source/article.txt + source/source_metadata.json
-> planning/article_brief.json + context_cards.json + episode_outline.json
-> single_host_script.md + podcast_script.md compatibility mirror
-> title / cover / PPT Master deck / VibeVoice single-speaker TTS
-> audio/final_podcast.wav
-> ASR/forced alignment -> audio/dialogue_timeline.json
-> bind chapter_semantics.json to dialogue_timeline.json
-> subtitles
-> video/final_video.mp4
-> subtitle timeline QA
-> Bilibili upload and final submit in real Chrome
```

不要生成微信公众号审阅稿，不要创建 `wechat/` 产物，不要生成微信封面占位图，不要调用 `wechat-article-publish-draft`、`md-to-wechat` 或任何微信 API。

## 选题阶段

只有当用户没有提供本地文章文件路径时执行。

直接调用：

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video-remake/skills/china-longform-article-selection/SKILL.md
```

要求：

- 读取并服从该 selection skill 的当前规则，不要在父 prompt 里重写选题规则。
- 当前默认选题窗口是 Asia/Shanghai 最近三个完整自然日；selection skill 会先读取近三天已使用文章 registry 并去重，再执行三级正文获取策略。
- 若 selection skill 无法给出 `material_available=true` 且有本地正文材料的候选，停止在 `SELECTION_BLOCKED`，不要临时指定文章或跳过材料门禁。

默认运行上下文只用于传参，不改变选题标准：

```json
{
  "selection_start_date": "Asia/Shanghai yesterday - 2 days",
  "selection_end_date": "Asia/Shanghai yesterday",
  "target_timezone": "Asia/Shanghai",
  "requested_count": 1,
  "minimum_returned_count": 1
}
```

选题产物必须复制或记录到当前项目目录：

```text
selection/source-shortlist.json
selection/ranked-top5.json
selection/selection-decision.json
selection/selection-result.md
selection/final-report.md
selection/used-article-dedupe.json
```

自动选择规则：使用 selection skill 推荐的最高分且 `material_available=true` 的候选。把候选的本地正文材料标准化为 `source/article.txt` 和 `source/source_metadata.json`。

## 本地文章输入

如果用户提供本地文章路径，跳过选题阶段。

检查：

- 文件存在。
- 文件可读。
- 能抽取文章正文。

支持 `.txt`、`.md`、`.docx`、`.pdf`、`.html`。抽取后保存为当前项目的 `source/article.txt`，并保存 `source/source_metadata.json`。如果文件内有明确可见素材，可复制到 `source/images/`。

不要联网补来源，不要从文件名强猜来源。`source_metadata.json` 只记录本地文件明确可见的信息，例如 `publication`、`article_title`、`author`、`published_date`、`source_url`。这些字段只用于内部溯源和事实边界；面向观众的标题、口播稿、字幕和简介不得出现来源框架。

## 输出目录

开始前确认 `/Volumes/GT34` 已挂载且可写。

固定输出根目录：

```text
/Volumes/GT34/english_aircle_to_video
```

每次运行创建新的项目目录：

```text
/Volumes/GT34/english_aircle_to_video/<article_slug>_<YYYYMMDD_HHMMSS>_single_host_video/
```

不要复用历史项目目录。新目录创建后，只允许把当前输入文章和输入文件内明确可见的素材复制进 `source/`。不得复制历史项目的 `single_host_script.md`、`audio/`、`cover/`、`chapter_visuals/`、`video/`、`publish/`、metadata、QA report 或 manifest。

如果候选目录已存在，追加短随机后缀或重新取当前时间，直到得到不存在的新目录。

## 子 Skill 顺序

按顺序读取并调用：

1. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-episode-planning/SKILL.md`
   - 以 `mode=single_host_explainer` 输出 planning artifacts。
2. `/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video-remake/skills/article-china-story-voiceover-script/SKILL.md`
   - 输出 `single_host_script.md` 和兼容镜像 `podcast_script.md`。
   - 口播稿必须以中国视角讲述中国故事；不得出现报刊名、作者名、来源 URL、“外媒/外刊/原文/这篇文章说/报道指出/文章认为”等来源框架。
3. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-visuals/SKILL.md`
   - 生成 PPT Master deck 章节视觉和 `chapter_visuals/chapter_semantics.json`。
4. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-title-writing/SKILL.md`
5. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-cover-image-generation/SKILL.md`
6. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/SKILL.md`
7. `/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video-remake/skills/article-single-host-vibevoice-audio/SKILL.md`
8. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/SKILL.md`
9. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-timeline-binding/SKILL.md`
10. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/SKILL.md`
11. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-static-video/SKILL.md`
12. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-timeline-qa/SKILL.md`
13. `/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md`

B 站投稿必须通过 `bilibili-video-upload-draft`。不得在本 skill 中手写 B 站 Chrome/Playwright 上传逻辑，不得伪造投稿 report。当前 agent 缺少 `chrome:control-chrome` 但视频和 metadata 已完成时，返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED`。

## Gate 总表

```text
Input Gate:
  /Volumes/GT34 is mounted and writable
  fresh timestamped project directory created
  if no local article path is provided, selection stage ran through this skill's selection dependency
  source/article.txt exists and is readable
  source/source_metadata.json exists

Selection Gate when no local article was provided:
  china-longform-article-selection/SKILL.md was read and followed
  selection artifacts exist under selection/
  selection-decision.json records selected candidate and material source
  selected material was standardized into source/article.txt and source/source_metadata.json
  no ad hoc parent-prompt selection rules were used

Planning Gate:
  planning/article_brief.json exists
  planning/context_cards.json exists
  planning/episode_outline.json exists

Script Gate:
  single_host_script.md exists
  podcast_script.md compatibility mirror exists
  reader/viewer-facing text contains no publication name, author name, source URL, "外媒", "外刊", "原文", "这篇文章", "报道指出", "文章认为" or equivalent source framing

Video Gates:
  title and cover artifacts exist
  chapter_visuals/chapter_plan.json exists
  audio/final_podcast.wav exists and is the timeline source
  audio/dialogue_timeline.json exists
  video/final_subtitles.srt and video/final_subtitles.ass exist
  video/final_video.mp4 exists and ffprobe passes
  subtitle timeline QA status is PASS
  bilibili-video-upload-draft creates bilibili_upload_draft_report.json/.md or returns explicit upload handoff/blocker
```

## 不可变规则

- 只保留原单人口播视频流程；不要提供微信公众号模式。
- 不生成 `wechat/`、`wechat/reviewed_article.md`、`wechat/article_metadata.json`、微信封面占位图或微信发布报告。
- 不调用 `wechat-article-publish-draft`、`md-to-wechat`、微信 API 或微信浏览器自动化。
- 必须调用 VibeVoice、ASR、字幕、视频合成和 B 站投稿链路，除非环境阻塞。
- 面向观众的衍生内容不得出现报刊名、作者名、来源 URL 或“外媒/外刊/这篇文章/报道指出”等来源框架；来源信息只保留在内部 metadata、plan 和生产报告中。

## 最终回复

成功时列出：

- `single_host_script.md`
- `audio/final_podcast_preview.mp3`
- `video/final_video.mp4`
- `cover/cover_4k.png`
- `video/final_subtitles.srt`
- `video_title.txt`
- `publish_info.txt`
- `bilibili_upload_metadata.json`
- `bilibili_upload_draft_report.json`
- `bilibili_upload_draft_report.md`

如果任何 gate 被环境阻塞，回复 `BLOCKED`，给出失败命令、错误信息和停在哪个 gate。
