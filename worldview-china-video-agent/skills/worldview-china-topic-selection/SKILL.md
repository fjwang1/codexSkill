---
name: worldview-china-topic-selection
description: "用于为 Worldview China 视频 Agent 选择和排序 YouTube 视频：寻找过去 3 天发布、时长大于 10 分钟且不超过 30 分钟、体现海外视角的中国相关长视频。提供 searchList、detailList、getTranscript 三个工具脚本，以及固定执行流程、评分标准、阈值和同分排序规则，最终直接输出一个最佳视频，不再进行 3 选 1 人类确认。"
---

# Worldview China 选题 Agent

使用这个 skill 为 Worldview China 视频 Agent 自动选出 1 个最佳 YouTube 视频。选题阶段不再输出 3 个候选等待用户确认；排序、取舍和最终选择都由 Agent 按本 skill 自动完成。

目标不是寻找“任何提到中国的视频”，而是寻找能体现海外视角、外部解释框架、观察方式或叙事方式的中国相关长视频。

## 工具脚本

尽量在项目工作区中运行脚本：

```bash
cd /Users/wangfangjia/code/worldview-china-video-agent
uv run python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/search_list.py --query "China explained" --max-results 20 --order relevance
```

YouTube Data API 调用优先使用命令行 `--api-key`，其次使用 `YOUTUBE_API_KEY` 或 `GOOGLE_API_KEY` 环境变量，最后读取 skill 目录下的私有 `.env` / `.env.local`。不要在面向用户的输出中打印 API key。

本地私有 key 文件位置：

```text
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/.env
```

该文件只保存本地运行密钥，不要把它的内容写入 `SKILL.md`、README、日志或候选结果。

## 历史最终选题文件

推荐候选前，必须先读取：

```text
/Volumes/GT34/Generated/world_and_china/final-videos.json
```

这个文件只记录已经通过最终成片验收并被正式使用的视频，不记录搜索候选、字幕评分候选或自动选择但尚未通过成片验收的视频。过滤掉所有 `video_id` 出现在 `videos[].video_id` 中的候选。

期望结构：

```json
{
  "videos": [
    {
      "video_id": "...",
      "url": "https://www.youtube.com/watch?v=...",
      "title": "...",
      "channel": "...",
      "selected_at": "...",
      "notes": "optional"
    }
  ]
}
```

如果文件不存在或为空，先创建为 `{"videos": []}` 再执行选题流程。本 skill 只读取该文件并过滤已经最终成片的视频，不负责写入。只有最终视频通过成片验收后，才由总控流程追加到 `final-videos.json`。

### searchList

脚本：

```bash
uv run python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/search_list.py --query "China explained" --max-results 20 --order relevance
```

用途：

- 调用 YouTube Data API `search.list`。
- 返回 `video_id`、标题、描述、频道、发布时间、缩略图等搜索候选。
- 不判断内容质量，不获取时长和统计数据。

配额成本：约 100 units / 次。

### detailList

脚本：

```bash
uv run python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/detail_list.py --published-after "{published_after_utc}" VIDEO_ID_1 VIDEO_ID_2
```

用途：

- 批量调用 YouTube Data API `videos.list`。
- 返回时长、秒级时长、播放量、点赞数、评论数、标题、描述、频道、发布时间、缩略图等 detail 信息。
- 添加发布时间和时长上下限的硬过滤标记。
- 添加互动指标和硬过滤标记，用于决定哪些候选值得进入 AI 粗评和字幕拉取。

配额成本：约 1 unit / 每批最多 50 个 video ids。

### getTranscript

脚本：

```bash
uv run python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/get_transcript.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --language en \
  --cache-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/01-topic-selection/transcripts \
  --video-metadata-file /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/01-topic-selection/detail-results.json
```

用途：

- 使用 `youtube-transcript-api` 获取公开视频字幕。
- 优先人工字幕，失败后回退到自动字幕。
- 必须优先传入 detailList 结果作为 `--video-metadata-file`，让缓存文件统一包含 `video_url`、标题、描述、频道、发布时间和时长。
- 按 `video_id` 和语言缓存字幕 JSON/TXT。长字幕应优先写入本地文件，并把文件路径提供给 Agent 后续读取和复用。

这不是 YouTube 官方 Captions API。它适合 Phase 1 的选题理解，但在视频无字幕、字幕受限、请求频率过高或 YouTube 前端行为变化时可能失败。

字幕回退：

- 先重试候选的实际语言，例如 `en-US`、`en`、`en-GB`，必要时用 `yt-dlp --write-subs --write-auto-subs` 尝试。
- 如果某个候选的 `youtube-transcript-api` 和 `yt-dlp` 字幕都失败，优先跳到下一个 detail 粗评分靠前的候选，不要立刻对当前候选做音频 ASR。
- 如果同一批 `top_k_transcripts` 中没有任何候选拿到字幕或历史缓存，才允许使用原声音频 ASR 作为低成本内容评分兜底。
- 选题阶段 ASR 兜底只能做抽样，不得转写完整视频。每个候选最多抽 3 个片段：开头、中段、结尾；每段 90-120 秒，总抽样音频不得超过 6 分钟。整轮最多对 `max_asr_fallback_candidates=3` 个候选做抽样 ASR。
- 选题阶段不得下载或保留完整原声音频用于 ASR。必须使用 `yt-dlp --download-sections`、`ffmpeg -ss/-t` 或等价方式只保存抽样片段；如果工具不得不临时生成完整音频，抽样完成后必须立即删除完整音频，并在日志中记录清理。
- 选题阶段 ASR 只能使用已经可用或可快速加载的小模型。模型下载、加载或转写单个候选超过 2 分钟仍无结果时，必须停止该候选 ASR，换下一个候选或换关键词；不要让选题节点被一个候选拖住。
- ASR 文本必须缓存为统一 transcript schema，路径应位于当前 run 的 `01-topic-selection/transcripts/` 下，例如 `/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/01-topic-selection/transcripts/{video_id}.asr.plain.json` 和 `.txt`，并在评分结果中标记 `text_source=audio_asr_fallback`。
- 通过抽样 ASR 得到的内容评分必须标记 `text_coverage=sampled_audio_asr`，并记录抽样片段时间范围。它只用于选题取舍；后续生产仍必须在 `03-audio-anchors` 对完整原声音频重新生成 word-level anchors，不能复用选题抽样 ASR 作为最终时间线。
- 如果可以使用同 `video_id` 的历史字幕缓存继续评分，必须在 `content-scored.json` 和报告里写明 `cache_rescue_source`。
- 不能把无字幕候选假装成已评分候选。没有字幕、ASR 或缓存文本时不得进入 content accept。

## 硬性要求

进入字幕评分前，候选必须满足：

```text
发布时间：过去 3 天内
视频时长：大于 10 分钟，且不超过 30 分钟
视频形态：目标是长横视频，不是 Shorts 或竖屏切片
最终输出：直接选择 1 个最佳视频，同时保留排序审计记录
```

如果上游任务输入指定更严格的时长范围，例如 `min_duration_seconds=1800`，必须用更严格的范围覆盖默认值。不要选出低于用户明确下限的视频。

不要在 search/detail 阶段额外做“中国相关”的硬关键词过滤。关键词本身已经偏向中国相关，真正的中国相关性留到字幕内容评分阶段判断。

## 执行流程

不要按“一个关键词完整跑完再换下一个关键词”的方式串行执行。使用关键词批处理。

```text
1. 选择一批 3-5 个中国相关关键词。
2. 对每个关键词运行 searchList。
3. 合并所有返回的 video_id，并做全局去重。
4. 读取 `/Volumes/GT34/Generated/world_and_china/final-videos.json`，移除已经最终成片并写入历史的视频。
5. 对剩余 video_id 运行 detailList。
6. 应用硬过滤：过去 3 天、默认 10 分钟 < 时长 <= 30 分钟；如上游输入指定更严格时长范围，以更严格范围为准。
7. 根据互动指标和 AI detail 粗评分选择 `top_k_transcripts=12` 个候选拉字幕。
8. 只对 top K 运行 getTranscript；整次任务最多拉取 `max_transcripts_per_run=30` 个字幕。字幕失败时先换候选；只有整批没有可用字幕或历史缓存时，才允许按“字幕回退”规则做抽样音频 ASR。
9. getTranscript 调用时传入 detailList 元信息文件，缓存统一格式字幕，并返回 `transcript_file_path` / `plain_text_file_path` 等路径。
10. Agent 根据字幕长度决定全文读取、抽样读取或分块读取，再用四维标准给字幕内容评分。若使用抽样 ASR，必须按抽样覆盖范围降低置信度并写明证据，不得声称已经完成全字幕深读。
11. 对所有已评分候选排序。
12. 如果没有 `accept` 候选，在预算内尝试下一批关键词；预算耗尽仍无 `accept` 时输出 `NO_ACCEPTABLE_VIDEO`，不要硬选低质视频。
13. 从 `accept` 中选择排序第一的视频作为 `best_video`，不等待用户确认。
14. 同时保存 `ranked_shortlist` 作为审计记录，说明为什么最终选择第一名、为什么没有选择其他高分候选。
```

尽量使用缓存。不要重复拉取同一个 `video_id` 的字幕。

## detail 粗评分

detail 粗评分只决定是否值得消耗字幕和 LLM 成本，不决定最终质量。

所有评分都使用 10 分制。detail 粗评分满分 10 分，由两部分组成：

```text
1. 互动数是否达标：7 分
   权重顺序为 view_count > comment_count > like_count

2. AI 对标题和描述的判断：3 分
   判断标题/描述是否有吸引力、角度是否新颖、是否像一个值得深读的选题
```

互动指标是重点。`view_count` 权重最高，因为它代表视频已经被市场验证；`comment_count` 次之，因为评论意味着讨论度；`like_count` 再次，因为点赞是较弱的轻交互。

最终 `detail_score` 是两项累加，满分 10 分。这两个分项目前没有严格参照标尺。先用相对判断，等跑出一批真实 case 后再校准详细标准。

粗评输出建议包含：

```json
{
  "engagement_score": 0,
  "metadata_score": 0,
  "detail_score": 0,
  "engagement_reason": "...",
  "metadata_judgement": "...",
  "recommended_for_transcript": true
}
```

## 字幕内容评分

字幕内容评分满分 10 分，四个维度累加：

```text
china_relevance
3 分。字幕内容是否真正围绕中国，而不是标题或关键词蹭 China。

foreign_perspective
2 分。是否体现海外视角、外部叙事、比较框架或解释框架。

insight_density
3 分。是否有分析、解释、比较、判断，而不是表层描述或流水账。

angle_novelty
2 分。角度是否新颖，是否有新的观察切口。
```

内容分为四项累加，满分 10 分：

```text
content_score = china_relevance + foreign_perspective + insight_density + angle_novelty
```

评分项：

```text
china_relevance: 0-3
字幕内容是否真正围绕中国，而不是标题或关键词蹭 China。

foreign_perspective: 0-2
是否体现海外视角、外部叙事、比较框架或解释框架。

insight_density: 0-3
是否有分析、解释、比较、判断，而不是表层描述或流水账。

angle_novelty: 0-2
角度是否新颖，是否有新的观察切口。
```

决策阈值：

```text
content_score >= 8：accept，强候选
7 <= content_score < 8：backup，备选
content_score < 7：reject，不推荐
```

最终只从 `accept` 候选中挑选 1 个最佳视频。`backup` 只用于诊断和复盘，不进入最终输出，也不能作为正式视频来源，除非后续明确修改阈值规则。

长字幕可以先抽样评分：开头、中段、结尾。只有明显有潜力或接近阈值的候选，才需要全字幕分块评分。

## 同分排序

最终视频只从 `accept` 中挑选。如果多个 `accept` 候选 `content_score` 相同，按以下顺序排序：

```text
1. content_score 从高到低
2. view_count/comment_count 从高到低
3. published_at 越新越靠前
```

## 字幕缓存与长字幕读取

字幕文件后续还会用于中文口播稿、翻译、字幕生成和素材对齐，所以必须缓存到项目本地文件，而不是只作为一次性工具返回值。

推荐路径：

```text
/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/01-topic-selection/transcripts/{video_id}.{language}.plain.json
/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/01-topic-selection/transcripts/{video_id}.{language}.plain.txt
```

JSON 文件保留统一结构和结构化 `segments`，用于程序处理和后续对齐；TXT 文件保留相同元信息和带时间戳的纯文本，方便 Agent 快速阅读。

缓存文件必须使用统一 schema，不要临时拼接自由格式：

```json
{
  "schema_version": "transcript.v1",
  "tool": "getTranscript",
  "video": {
    "video_id": "VIDEO_ID",
    "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "title": "...",
    "description": "...",
    "channel": "...",
    "published_at": "...",
    "duration_seconds": 0,
    "metadata_incomplete": false
  },
  "transcript": {
    "language": "en",
    "source": "manual_caption | auto_caption | fallback",
    "preserve_formatting": false,
    "text": "...",
    "segments": [
      {
        "start": 0.0,
        "duration": 4.2,
        "text": "..."
      }
    ]
  }
}
```

TXT 文件开头必须有同源 front matter：

```text
---
schema_version: "transcript.v1"
video_id: "VIDEO_ID"
video_url: "https://www.youtube.com/watch?v=VIDEO_ID"
title: "..."
channel: "..."
published_at: "..."
duration_seconds: "0"
language: "en"
source: "auto_caption"
metadata_incomplete: false
description: |
  ...
---

[00:00:00 - 00:00:04] ...
```

getTranscript 推荐返回：

```json
{
  "schema_version": "transcript.v1",
  "video_id": "...",
  "title": "...",
  "description_chars": 0,
  "metadata_incomplete": false,
  "language": "en",
  "source": "manual_caption",
  "segments_count": 820,
  "transcript_chars": 68000,
  "transcript_file_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/01-topic-selection/transcripts/VIDEO_ID.en.plain.json",
  "plain_text_file_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/01-topic-selection/transcripts/VIDEO_ID.en.plain.txt"
}
```

Agent 拿到字幕文件路径后按长度选择读取策略：

```text
短字幕：可以全文读取。
长字幕：先抽样开头、中段、结尾。
有潜力或接近阈值：再按时间分块精读。
明显低质：不要读取完整长字幕。
```

## 输出

固定输出 1 个最佳视频。所有说明使用中文。

输出必须包含：

- 标题、频道、URL、发布时间、时长、播放量和评论数。
- 四个字幕评分维度和 `content_score`。
- 2-4 句中文摘要。
- 为什么它符合「世界眼中的中国」。
- 主要疑虑或风险。
- 最终选择理由：为什么它是本轮 `best_video`。
- `ranked_shortlist` 路径或简表：记录前若干名 accept/backup 的分数和未选原因，仅作审计，不作为等待用户选择的候选列表。

本 skill 完成后，总控流程可以直接把 `best_video` 交给素材准备、中文配音和视频合成阶段。选题阶段不再需要用户确认。
