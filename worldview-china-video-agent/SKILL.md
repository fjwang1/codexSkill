---
name: worldview-china-video-agent
description: "Worldview China 视频 Agent 的端到端总控 skill：为“世界眼中的中国”主题自动选出一个最佳视频，准备高清 YouTube 素材，按原声音频语义锚点生成中文配音、中文字幕、封面图并合成最终视频，并由无上下文评测 agent 完整 QA。"
---

# Worldview China Video Agent 总控

本 skill 是 Worldview China Video Agent 的 canonical 入口和总控编排器。它不替代子 skill，而是规定何时调用它们、如何传递文件、如何验收最终结果。

旧的 `worldview-china-video-production` 入口只保留兼容跳转。以后完整流程、维护和修改都以本文件为准。

## Reminder Gate

每次开始新的正式生产、验证或自动任务时，先按“输出目录”规则创建本轮 run 目录。Reminder Gate 的记录文件必须写在该 run 目录的 `00-reminder-read/` 下；没有独立 run 目录，不得继续执行。

每次开始新的正式生产、验证或自动任务前，必须先读取：

```text
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/reminder.md
```

该文件只记录已经踩过、且对未来生产有重大影响的问题。不要把可有可无的经验、普通日志、单次偶发错误写进去。若一次完整成功流程结束后发现新的重大坑，必须把它追加到 reminder，并在下一次任务开始前先读。

读取 reminder 后，必须在本轮 run 目录写入：

```text
00-reminder-read/reminder-read.json
```

至少记录 `reminder_path`、读取时间、文件 sha256 和本轮是否发现需要特别避开的坑。没有该文件，不得进入 `01-topic-selection`。

## 执行 Agent 职责边界

本 skill 只有一个正式执行模式。任何修改 skill 或测试 skill 稳定性的任务都属于开发对话中的研发任务，不写入本 skill 的运行模式。

正式运行时只有一个执行 agent 负责总控流程：

- 执行 agent：严格按本 skill 和子 skill 运行全流程，包括选题、素材准备、原声音频锚点、中文配音、字幕、封面、合成、节点验收、回滚、最终验收和历史写入。
- 节点评测 agent：每个节点完成后启动一个新的无上下文只读评测 agent，按 `worldview-china-node-acceptance` 独立验收该节点。它不能修改产物或 skill，只能写节点验收报告和 `PASS | NEEDS_FIX | FAIL` 结论。
- 最终评测 agent：最终成片后启动一个新的无上下文只读评测 agent，按 `youtube-dubbing-video-acceptance` 独立验收成片。它不能修改产物或 skill，只能写最终验收报告和 `PASS | NEEDS_FIX | FAIL` 结论。

评测调度方式：

- `evaluation_dispatch="direct_subagent"`：执行 agent 自己使用当前环境提供的 multi-agent/subagent 工具启动并等待评测 agent。
- `evaluation_dispatch="supervised_request"`：当执行 agent 是由外层主控派发的子 agent、且子 agent 本身没有再启动 subagent 的工具时使用。执行 agent 不得自评，也不得使用本地 Codex CLI 兜底；它必须写出 `qa/eval-request.json`，在 `logs/progress.md` 写入等待状态和 heartbeat，然后只轮询等待请求文件中指定的 result 路径。外层主控只能代为启动无上下文只读评测 agent，并把评测结果写回请求指定路径，不能替评测 agent 直接给 PASS。
- 如果没有可用的 direct subagent 工具，也没有在本轮输入中明确允许 `supervised_request`，执行 agent 必须输出 `PROCESS_RULE_DEFECT`。

执行规则：

- 执行 agent 可以根据评测结论回滚节点、清空节点和下游产物、重跑局部节点或重跑完整流程。
- 执行 agent 不能在正式运行中修改本 skill、子 skill 或脚本。若连续失败暴露流程规则缺陷，必须停止本轮并输出 `PROCESS_RULE_DEFECT`，说明需要在开发对话中修改 skill。
- 执行 agent 不能绕过节点流程直接手改最终 MP4、最终音频、最终字幕或 manifest。任何修复都必须回到责任节点重新生成，并重新经过只读评测 agent 验收。
- 执行 agent 给任一评测 agent 的输入必须是文件路径和 manifest，不是口头保证。
- 每个节点评测 agent 和最终评测 agent 都必须 `fork_context=false`，不能继承执行 agent 的上下文。
- 执行 agent 不得用本地 Codex CLI、交互式 shell 或非当前任务环境的工作流来假装启动评测 agent。若当前环境没有可用的 subagent 工具，且本轮没有明确使用 `evaluation_dispatch="supervised_request"`，必须输出 `PROCESS_RULE_DEFECT`。

目标成品必须包含：

- 原视频画面。
- 中文配音主音轨，原声默认静音。
- 烧录在画面上的中文字幕，同时保留 `.srt` / `.vtt` 文件。
- 独立封面图。
- `render_manifest.json` 和 QA 报告。
- 正式交付成片必须统一加速到 `1.15x`：最终 MP4、交付中文音频、烧录字幕和交付 `.srt` / `.vtt` 都使用 1.15 倍交付时间线。

## 子 skill 地图

必须按需读取这些子 skill，而不是凭记忆执行：

```text
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-media-preparation/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-final-video-composition/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-node-acceptance/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-dubbing-video-acceptance/SKILL.md
```

可作为回退或局部工具，但不要作为最终对齐依据：

```text
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-subtitle-to-chinese/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/timed-script-to-voiceover-segments/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/chinese-voiceover-audio-generation/SKILL.md
```

边界：

- `worldview-china-topic-selection` 负责找候选、拉字幕、评分。
- `youtube-media-preparation` 负责下载素材、抽音频、保存字幕和元信息。
- `youtube-audio-anchor-dubbing` 负责高精度原声音频锚点、中文配音段、逐段对齐和锚点 QA。它是生产方法，不应吞掉总控的候选选择、素材选择和最终交付决策。
- `youtube-final-video-composition` 负责静音原视频、叠加中文音轨、烧录中文字幕、生成封面、检查片段、manifest 和最终 QA。
- `worldview-china-node-acceptance` 负责每个流水线节点的独立验收，判断是否允许进入下一节点，并在失败时给出 `rollback_to_node`。
- `youtube-dubbing-video-acceptance` 负责最终成片验收，判断字幕、语音、画面、静音、中文表达和交付物是否达标；验收不通过不得写入最终历史。
- `youtube-subtitle-to-chinese` 只能用于理解或草稿。最终卡点不得直接依赖 YouTube 字幕时间戳。
- `timed-script-to-voiceover-segments` 只能整理已有中文稿，不能替代原声音频锚点。
- `chinese-voiceover-audio-generation` 只负责 TTS 音频生成；最终时间线和视频合成仍由本流程或 `youtube-audio-anchor-dubbing` 控制。

## 输入

所有运行都按正式执行处理：

```json
{
  "topic_window": "past_3_days",
  "selection_output": "best_video",
  "final_video_count": 1,
  "min_duration_seconds": 600,
  "max_duration_seconds": 1800,
  "evaluation_dispatch": "direct_subagent",
  "quality": {
    "source_video_height_target": 2160,
    "final_output": "1080p_high_quality"
  },
  "playback_speed": 1.15
}
```

选题阶段不再执行 3 选 1 human-in-the-loop。只有用户明确要求人工复核时，才在输出 `best_video` 后暂停；默认直接进入素材准备和成片流程。

日期必须写成绝对日期。以当前线程时区为准，运行时根据当前线程日期实时计算 `{current_date}`、`{yesterday_start_local}`、`{published_after_utc}` 等值。示例日期不得直接复制到实际运行参数。

## 执行 Gate

任何运行都必须在 `run_manifest.json` 中记录：

```json
{
  "mode": "execution",
  "evaluation_dispatch": "direct_subagent | supervised_request",
  "selection_authorization": "topic_agent_selected",
  "quality_downgrade_authorization": "none | user_confirmed",
  "cache_rescue_used": false
}
```

正式执行必须同时满足：

- 覆盖原视频完整主时间线，不是局部片段。
- 选题最终视频来自 `worldview-china-topic-selection` 输出的 `best_video`，并有 `ranked_shortlist`、评分和最终选择理由。
- 高清下载如果发生降级，必须有用户确认。
- 时间线来自原声音频 ASR word anchors，并经过字幕/上下文校正。
- 中文配音来自同一个原视频音色克隆 profile；除非用户明确允许预设音色，否则正式生产不得使用固定预设 voice。
- 全片都有可追溯证据：`audio-semantic-turns.md`、`voiceover-segments.json`、`segment-aligned-audio/manifest.json` 必须覆盖完整处理范围。
- 不能只对开头或某一章做原声音频锚点，然后把后续章节接到旧的 chapter timeline、字幕时间戳或 `derived_from_chapter_range` 上。
- 输出包含最终 MP4、中文音频、SRT、VTT、封面、QA 报告、render manifest、检查片段和关键帧。
- QA 中有音频锚点误差、字幕可读性、封面可读性、源/成片分辨率码率证据。
- 完整中文 voiceover 已通过全局静音检查：不存在源 ASR 仍有讲话而中文静音 `>2.0s` 的窗口。
- 最终合成阶段必须执行 `playback_speed = 1.15`。上游锚点、配音段、TTS 对齐和输入字幕仍按原声音频时间线生产；最终 MP4、交付中文音频、烧录字幕和交付 SRT/VTT 统一映射到 `delivery_time = source_time / 1.15`。
- 最终 MP4 由临时文件原子 rename 得到，当前正式文件现场 `ffprobe` 可读，且 `render_manifest.json` 的最终文件大小、时长和流信息与当前正式文件一致。
- 最终必须通过 `youtube-dubbing-video-acceptance` 验收。验收必须由无上下文子 agent 执行，不能由生产 agent 自己给 PASS。

## 输出目录

固定工作根目录：

```text
/Volumes/GT34/Generated/world_and_china/
```

每次执行都必须在固定工作根目录下新建一个独立 run 目录，目录名格式为：

```text
{YYYYMMDD}_{N}
```

示例：

```text
/Volumes/GT34/Generated/world_and_china/20260605_0/
```

规则：

- `YYYYMMDD` 使用本机/用户所在时区的当前日期。
- 同一天从 `_0` 开始递增；如果已存在 `20260605_0`、`20260605_1`，下一次必须使用 `20260605_2`。
- 只把匹配 `YYYYMMDD_<整数>` 的目录纳入递增计算；其它临时目录忽略。
- 正式执行和自动任务都必须使用该规则创建 run 目录。
- 本轮所有中间产物、节点 QA、最终 MP4、中文音频、字幕、封面、检查片段、日志和 manifest 都必须写入本 run 目录。
- 子 skill 或脚本需要 `output_dir` 时，执行 agent 必须传入当前 run 目录下的节点子目录，不能写到旧的 `runs/`、`data/final-renders/`、桌面、下载目录或临时缓存目录。

## 节点目录、验收和回滚

每次视频生产都是一个独立 project/run。所有节点必须写入本 run 目录下的固定节点目录，不允许把不同节点的中间产物混在一起：

```text
/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/
├── 00-reminder-read/
├── 01-topic-selection/
├── 02-media-preparation/
├── 03-audio-anchors/
├── 04-voiceover-segments/
├── 05-tts-alignment/
├── 06-subtitles/
├── 07-final-composition/
├── 08-final-acceptance/
├── rollback/
├── logs/
└── run_manifest.json
```

节点执行规则：

1. 进入任何生产节点前，先确认上一节点 `node-acceptance-result.json.decision == "PASS"`。
2. 每个节点完成后，必须发起节点评测。若 `evaluation_dispatch="direct_subagent"`，通过当前环境的 multi-agent/subagent 工具新开一个 `fork_context=false` 节点评测 agent；若 `evaluation_dispatch="supervised_request"`，写出评测请求后等待外层主控代开评测 agent。
3. 节点评测请求必须包含 `worldview-china-node-acceptance` skill、`node_id`、节点目录、上游 manifest、本节点产物路径和指定输出路径。`supervised_request` 时请求文件固定写入：
   - `qa/eval-request.json`
4. `qa/eval-request.json` 至少包含：

```json
{
  "request_type": "node_acceptance",
  "run_dir": "...",
  "node_id": "03-audio-anchors",
  "node_dir": ".../03-audio-anchors",
  "skill_path": "/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-node-acceptance/SKILL.md",
  "run_manifest_path": ".../run_manifest.json",
  "upstream_manifest_paths": [],
  "artifact_paths": [],
  "output_report_path": ".../qa/node-acceptance-report.md",
  "output_result_path": ".../qa/node-acceptance-result.json",
  "evaluator_requirements": {
    "fork_context": false,
    "read_only": true,
    "no_skill_edits": true
  }
}
```

5. 节点评测 agent 只能输出验收报告，不能修改产物。输出必须写入该节点目录的 `qa/` 下：
   - `qa/node-acceptance-report.md`
   - `qa/node-acceptance-result.json`
6. `supervised_request` 等待期间，执行 agent 只能轮询指定 result 文件，并至少每 2 分钟向 `logs/progress.md` 写 heartbeat；不得自评、不得继续下一个节点、不得改用本地 Codex CLI。
7. 节点未通过时，不得进入下一个节点。执行 agent 根据 `rollback_to_node` 回滚。
8. 即使已经进行到第 5 个或更后节点，如果验收发现根因来自更早节点，允许一次回滚多个节点。例如 TTS 阶段发现锚点设计错误，可以回滚到 `03-audio-anchors`；字幕阶段发现中文词序导致硬锚点无法卡点，可以回滚到 `04-voiceover-segments`。
9. 节点评测结果写出后，执行 agent 必须立即更新 `run_manifest.json` 和 `logs/progress.md`：
   - `PASS`：把当前节点状态改为 `accepted`，记录 `qa/node-acceptance-result.json` 路径，并把下一节点状态改为 `in_progress` 后再开始下一节点。
   - `NEEDS_FIX` 或 `FAIL`：记录 decision、blocking reasons 和 `rollback_to_node`，然后执行回滚；不得停在无状态更新的等待状态。
10. 任何预计超过 2 分钟的下载、ASR、TTS、合成或评测等待，都必须至少每 2 分钟向 `logs/progress.md` 写入 heartbeat，说明当前动作、等待对象和下一步。没有 heartbeat 的长时间等待视为执行异常。

回滚规则：

- 每个节点有稳定顺序：`01-topic-selection` -> `02-media-preparation` -> `03-audio-anchors` -> `04-voiceover-segments` -> `05-tts-alignment` -> `06-subtitles` -> `07-final-composition` -> `08-final-acceptance`。
- 回滚到某节点时，必须清空该节点和所有下游节点的 active 目录，再重新生成。不要复用失败节点的中间产物。
- 节点 `NEEDS_FIX` 后不得只在正式合并产物中手改几个字段再重新提交验收。若失败来自 04 的 `voice_text`、硬锚点跨窗、preflight 漏检或 chapter checkpoint 内容，至少必须清空并重跑受影响章节 checkpoint、全片合并文件和全部 04 preflight；如果评测要求 `rollback_to_node = "04-voiceover-segments"` 且未限定局部章节，默认清空并重跑整个 04 节点。
- 为了审计，可以在清空前把轻量失败摘要复制到 `rollback/{timestamp}-{failed_node}/failure-summary.md`。不要复制大视频、draft 音频、缓存 overlay 或其它占空间的大文件。
- `run_manifest.json` 必须追加 `rollback_events[]`，记录 `failed_node`、`rollback_to_node`、失败原因、清空目录列表和下一轮 attempt id。
- 如果同一节点连续失败，先判断是否为流程规则缺陷。若是流程规则缺陷，停止本轮并输出 `PROCESS_RULE_DEFECT`；局部内容问题才只修该视频节点产物。
- 如果执行 agent 无法通过本轮指定的 `evaluation_dispatch` 发起评测、无法等待评测结果、或无法持续写入进度 heartbeat，必须输出 `PROCESS_RULE_DEFECT`，不能静默卡住，也不能改用本地 Codex CLI 兜底。

节点验收 skill：

```text
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-node-acceptance/SKILL.md
```

最终成片仍然需要额外执行 `youtube-dubbing-video-acceptance`。节点验收通过不等于最终成片 PASS。

## 1. 选题

先使用 `worldview-china-topic-selection`。

硬要求：

- 发布时间：默认过去 3 天；用户要求昨天时，限定为昨天自然日。
- 时长：默认大于 10 分钟，且不超过 30 分钟；如果任务输入指定更严格的 `min_duration_seconds` 或 `max_duration_seconds`，以任务输入为准。
- 视频形态：横向长视频，排除 Shorts、竖屏、短切片。
- 关键词默认包含 China 或明确中国相关表达；不要在 search/detail 阶段再做“中国相关”硬过滤。
- 读取并过滤 `/Volumes/GT34/Generated/world_and_china/final-videos.json` 中已经最终使用过的视频。

执行策略：

1. 每批使用 3-5 个关键词，不要几十个关键词串行空转。
2. `search.list` 只负责召回；`videos.list` 批量补 detail。
3. detail 粗评后只拉 top K 字幕；默认 `top_k_transcripts=12`。
4. 字幕内容评分满分 10，`content_score >= 8` 才是 accept。
5. 最终只从 `accept` 里自动选择排序第一的视频作为 `best_video`。同分按 `view_count/comment_count`、`published_at` 排。
6. 保存 `ranked_shortlist` 和未选原因作为审计记录，但不等待用户从候选中选择。
7. 如果预算耗尽仍无 `accept`，输出 `NO_ACCEPTABLE_VIDEO`，不要硬选低质视频进入生产。

字幕拉取失败时：

- 先重试候选的实际语言，例如 `en-US`、`en`、`en-GB`，必要时用 `yt-dlp --write-subs --write-auto-subs` 尝试。
- 如果 YouTube 返回 429/IP block，可以使用 `/Volumes/GT34/Generated/world_and_china/` 下历史 run 中同 `video_id` 的缓存字幕继续，但必须在本轮 `content-scored.json` 和报告里写明 `cache_rescue_source`，并把被使用的文本副本或引用记录保存在当前 run 的 `01-topic-selection/` 下。
- 不能把无字幕候选假装成已评分候选。没有字幕、ASR 或缓存文本时不得进入 content accept。

昨天窗口计算模板：

```text
Asia/Shanghai {yesterday_start_local} 到 {today_start_local}
UTC publishedAfter={yesterday_start_utc}
UTC publishedBefore={today_start_utc}
```

如果工具没有 `publishedBefore` 参数，则用 `publishedAfter` 召回后在本地过滤 `published_at < publishedBefore`。

## 2. 素材准备

选题 skill 产出 `best_video` 后，使用 `youtube-media-preparation`。

高清规则覆盖子 skill 默认值：

- 默认目标下载高度为 `2160`，不是 1080。
- 调用素材脚本时必须使用 `--height 2160 --require-target-height --yt-dlp-bin "uvx yt-dlp"`，除非用户明确选择低清试跑。
- 优先选择最高可用且码率更高的 4K/2160p；如果没有 2160p，选 1440p；再退到 1080p。
- 同高度优先画质而非只优先 mp4。若 VP9 码率明显高于 AV1/mp4，可选 VP9/webm，再由 ffmpeg 转码。
- 如果已经存在低码率 `source.mp4`，必须用 `yt-dlp -F` 或 `source.info.json` 检查是否存在更高清格式。存在更高清时，使用 `--force` 或新目录重新下载，不要复用低清素材。
- 如果正式生产发现本地已有源低于目标高度，而 `yt-dlp -F` 显示目标高度或更高清晰度可用，不能直接阻塞；必须先在本次 run 的 `media/VIDEO_ID/` 目录重新下载目标高度素材。
- 只有在重新下载实际失败、卡死、被 429/IP block、格式不可用或文件不可读时，才记录 `download_blocker` 并进入用户确认/降级分支。
- 素材 manifest 必须记录 `selected_video_format`、实际分辨率、码率、下载原因。

素材 manifest 必须额外记录高清审计字段：

```json
{
  "available_max_height": 2160,
  "available_formats_summary": [
    {"format_id": "401", "height": 2160, "ext": "mp4", "vcodec": "av01", "tbr": 14117}
  ],
  "selected_video_format": "401",
  "selected_audio_format": "140",
  "selected_height": 2160,
  "selected_bitrate": 14117,
  "download_status": "complete | blocked",
  "download_blocker": "none | stalled | 429 | ip_block | unavailable",
  "downgrade_reason": "none | user_confirmed | target_unavailable",
  "partial_file_used": false
}
```

如果 `available_max_height >= 1440` 但正式输出使用 1080p 或更低，必须 FAIL，除非 `quality_downgrade_authorization=user_confirmed`。

下载卡死处理：

- 如果 2160p 下载 2 分钟内文件大小几乎不增长，或 10 分钟内无法稳定推进，停止该下载并记录 `download_blocker`。
- 正式生产模式下，遇到 2160p 卡死不得自动降级为成功交付；应询问用户是否改用 1440p/1080p。
- 未经用户确认，不要把降级素材写入最终历史。

封面规则：

- 不要默认用 YouTube 低码率缩略图做最终封面。
- 优先从高清源视频中抽一帧，或选择信息密度高的原缩略图作为构图参考后重做。
- 封面输出至少 1280x720；如果源视频 >= 2160p，优先输出 1920x1080。
- 封面只放中文主标题，除非用户要求，不要加“中文配音版”“原视频 + 中文配音 + 中文字幕”等说明行。

## 3. 原声音频锚点

最终生产必须使用 `youtube-audio-anchor-dubbing` 的方法。

原则：

- 字幕是文本来源，不是精准时间来源。
- 原声音频 ASR 词级时间戳是语义锚点来源。
- 必须把品牌名、国家名、人物名、关键数字、图表标题、强转折词列为高优先级锚点。
- 对品牌、产品、人物、图表、屏幕文字、车辆/地点/设备这类有明确画面对应物的关键词，必须同时检查视觉锚点。
- 如果画面对应物晚于原声词级时间出现，中文关键词不得早于对应画面，除非报告能证明这是原片有意“先说后给画面”的旁白结构。
- 中文配音稿必须按锚点时间窗写。不能先写整章，再事后整体拉伸。

### 明显画面转场定义

不要把所有镜头切换都升级为硬锚点。明显画面转场必须同时满足“语义转场候选”和“视觉变化证据”两类条件：

```text
明显画面转场 = 1-2 秒窗口内，原声语义进入新对象、新例子、新论点或新对比，同时画面主体、场景、屏幕文字、图表或构图发生可识别变化。
```

执行规则：

1. 先用 ASR/字幕文本找语义转场候选，例如 `now let's look at`、`but`、`however`、`meanwhile`、`in contrast`、`another example`、`next`，以及中文语义里的“接下来”“但是”“相比之下”“另一个例子”“问题在于”。
2. 只在这些候选附近抽帧复核，不要全片盲扫所有画面变化。默认抽取候选点前后各 2 秒；信息密集处可扩大到前后 5 秒。
3. 视觉变化证据包括：场景切换、画面主体切换、品牌/产品/人物/地点首次出现、屏幕文字/OCR 变化、图表标题或关键数字变化、远景/特写/实拍/动画等构图类型变化。
4. 只有“语义转场候选 + 视觉变化证据”同时成立，才升级为 `visual_transition_anchor` 或 `must_align`。
5. 如果只是 B-roll 轻微换镜头、构图小变化，旁白仍在讲同一件事，不升级为硬锚点，只记录为普通视觉备注或忽略。
6. 如果视觉转场确认后，硬关键词出现在该视觉转场之后，中文关键词不得早于该视觉转场；必要时拆成“转场前铺垫段”和“转场后关键词段”。

`audio-semantic-turns.md` 对明显画面转场至少记录：

```json
{
  "transition_id": "visual_transition_001",
  "semantic_cue": "another example is...",
  "semantic_anchor_sec": 34.2,
  "visual_change_type": "subject_change | scene_change | screen_text_change | chart_change | composition_change",
  "visual_anchor_sec": 34.8,
  "evidence": "keyframes/visual_transition_001_34.8.jpg",
  "decision": "upgrade_to_hard_anchor | visual_note_only"
}
```

每章流程：

```text
抽取该章原声音频
-> ASR word timestamps
-> 用字幕文本校正 ASR 错词
-> 写 audio-semantic-turns.md
-> 抽取关键锚点前后画面帧，记录 visual anchors
-> 按锚点生成 voiceover-segments.json
-> 为 must_align 关键词写 segment 内 anchor_checks
-> 校验中文词序不得早于音频/视觉锚点
-> 用正式 voice profile 对 must_align 段做小规模 TTS 时长适配诊断
-> 生成 TTS draft
-> 每段 pad 或 atempo 对齐到原锚点时间窗
-> 生成该章中文音频、字幕、检查片段
-> QA 通过后进入下一章
```

长视频必须分章/分批执行，不能把全片 ASR 草稿当成最终锚点文件后停止。

推荐批处理：

1. 用 `generate_audio_semantic_turns.py` 先生成全片 ASR 候选，或按 3-5 分钟窗口生成候选。
2. 将候选 turns 按语义和时间切成章节，每章建议 2-5 分钟，最多 8 分钟。
3. 对每章生成 `audio-semantic-turns.chapter_NNN.md`，状态必须从 `draft_needs_llm_revision` 修订为 `llm_revised`。
4. 每章生成 `voiceover-segments.chapter_NNN.json`。这些分段必须来自该章 ASR word anchors 和必要视觉 anchors。
5. 每章先跑少量 TTS/对齐门槛；全片正式 TTS 前，必须用同一个正式 `voice_profile` 先跑全部 `must_align` 段和少量普通段的时长适配诊断。若 tail silence 或 coverage 不达标，回到该章补稿/重分段。
6. 章节全部通过后，合并为全片：
   - `audio-semantic-turns.md`：全片总索引，列出所有章节锚点文件和覆盖范围。
   - `voiceover-segments.json`：全片单调时间线。
   - `segment-aligned-audio/manifest.json`：全片段级音频 manifest。

阻塞规则：

- 只完成全片 ASR candidate，而没有 LLM-revised anchors，不能进入合成。
- 只生成了章节粗时间线或旧中文稿，不能进入合成。
- 旧草稿如果 `time_source=derived_from_chapter_range`，只能作为中文表达素材，不能作为正式分段时间。
- 如果旧 draft TTS 段级对齐失败，不能停止在“旧稿不合格”这个结论；应进入章节补稿/重分段流程，除非缺少 ASR、TTS 或视频素材等外部能力。

禁止替代流程：

- `source_subtitle_timeline_validation`
- `cached_transcript_timestamps_as_timeline`
- 任何先按字幕粗段生成中文，再靠长静音补齐时间线的做法

如果产物出现以上字段或流程，直接 FAIL，丢弃输出并回到 `youtube-audio-anchor-dubbing`。

正式完整视频的锚点证据要求：

- `audio-semantic-turns.md` 可以按章拆分，但必须有一个总索引，覆盖 `00:00:00` 到源视频结束。
- 每章都必须记录 ASR 模型、原声音频范围、文本校正来源、高优先级音频锚点和必要视觉锚点。
- `voiceover-segments.json` 必须是全片汇总版，或有全片 manifest 明确列出所有章节分段文件；验收时必须能解析为完整单调时间线。
- `must_align` 段必须包含 `anchor_checks` 或等价字段，列出每个高辨识度关键词的原声词级时间、视觉不得早于时间、中文期望窗口和禁止提前时间。只有 segment `start/end` 不足以作为正式锚点证据。
- 如果一个 segment 中有多个高风险锚点，必须证明中文词序与 `anchor_checks` 顺序一致；相邻锚点间隔超过 `3s` 或存在画面对象切换时，应拆成多个 segment。
- 如果一个 segment 中有多个硬锚点，即使相邻锚点间隔不超过 `3s`，也必须检查每个硬锚点是否落在各自容差内。品牌、型号、产品、人物、数字、年份、金额、百分比、屏幕文字和视觉对象不能只靠“同在一个 segment”通过。
- 硬锚点默认必须成为 segment 边界。若某个硬锚点的 `effective_not_before_sec` 晚于当前 segment start 超过 `0.8s`，则目标词不得出现在该 segment 的 `voice_text` 中；应拆成“锚点前铺垫 segment”和“锚点词 segment”。只有在最终中文音频 ASR 证明该词实际落在 `±0.8s` 内时，才允许保留段内锚点。
- 一个 segment 中包含多个硬锚点时，只有这些锚点自然属于同一短语且彼此间隔 `<=0.8s` 才可保留；否则必须拆成多个 TTS segment。不要把人物名、品牌名、年份、金额、数量、专有名词列表写在同一段里等待字幕脚本调度。
- 生成 TTS 前必须做 `anchor_text_position_preflight`：检查每个 `anchor_checks.target_terms` 在 `voice_text` 中的位置。如果目标词按字符比例估算会早于 `effective_not_before_sec` 超过 `0.8s`，必须重写或拆段，不能进入 TTS。
- 对硬锚点同时检查提前和延迟：中文语音和中文字幕原则上都应在 source word anchor 的 `±0.8s` 内；如果中文语序导致前面数字被推迟、后面品牌被提前，必须重切 segment、调整词序并重新生成受影响 TTS。
- 列表型表达是高风险结构，例如多个品牌/供应商/国家名，或多个关键数字/金额/年限。不能把整串列表放进一个长字幕 cue，也不能把整串列表作为一个粗 segment 交给 TTS；应按列表项或 1-2 个强相关项拆成小段。
- 生成 TTS 前必须有高风险词 preflight 报告。`missing_anchor_checks=[]`、`invalid_anchor_checks=[]`、`blocking_unlisted_high_risk_terms=[]` 都必须满足；高频背景词可以放入 `non_blocking_unlisted_terms`，但必须写明为什么不是本处锚点。
- `voice_text` 必须是可直接送入中文 TTS 的中文口播正文。除品牌名、产品名、人名、地名、节目名、单位或确需保留的英文术语外，不得残留完整英文句子或连续英文短语。预检必须扫描 `voice_text` 中的拉丁字母片段：如果出现未登记为专名/术语的连续英文词组，应写入 `blocking_untranslated_source_text` 并禁止进入 TTS。
- 硬锚点 segment 只能承载该锚点时间窗内的事实、名词或短句。不要为了让中文更完整，把后一个 segment 的解释、因果、承诺、例子或补充信息提前塞进硬锚点段；这会让音频和画面/原声语义提前。锚点窗口过短时，应写短句或短语，并把后续信息放回后一个时间窗。
- 04 preflight 必须额外检查 `over_window_content_risks`：抽查每个 `anchor_checks` 对应的 source window 与相邻 segment，如果硬锚点 `voice_text` 明显包含后续窗口事实或后续句子的解释，应阻断而不是只给 warning。
- 跨章节边界可能会包含同一个原声锚点的上下文副本。全片合并时，任一 `source_anchor_id` 只能被物化为一个正式 `must_align` voiceover segment。若相邻章节都包含同一硬锚点，合并器必须按全局 `source_anchor_id` 去重，保留时间窗更完整、与 03 全局锚点一致的那一段，并把另一处作为上下文记录或删除，不能生成重复口播。
- 04 preflight 必须检查全局 `source_anchor_id` 唯一性和全片时间单调不重叠。`duplicate_materialized_source_anchor_ids=[]`、`timeline_overlaps=[]` 必须为空；这两个检查不能只依赖 chapter 内部自检，因为错误常发生在章节边界。
- `segment-aligned-audio/manifest.json` 必须覆盖全片每个 TTS 段；不允许只记录前几分钟或局部片段。
- 如果任一章缺锚点、缺分段或缺段级音频 manifest，正式成片不能进入最终合成，只能输出 `NEEDS_FIX`。

ASR 模型：

- 优先使用本机能承受的较大 Whisper 模型。
- `whisper-tiny` 只能做时间草稿。文字错词必须用字幕、上下文和 LLM 校正。
- QA 报告要写清楚时间来源和文本来源。

## 4. 中文配音稿

长视频生成规则：

- `04-voiceover-segments` 必须按 `03-audio-anchors/chapters/audio-semantic-turns.chapter_NNN.md` 逐章生成，不能一次性让 LLM 生成完整 30-60 分钟视频的全量配音段。
- 每章生成完成后必须立即落盘：
  - `04-voiceover-segments/chapters/chapter_NNN.voiceover-draft.json`
  - 或等价的逐章 checkpoint 文件。
- 每章 checkpoint 必须包含该章 `chapter_id`、`source_chapter_path`、`start/end`、`segments[]`、`anchor_checks[]` 覆盖情况、估算时长统计和本章自检结果。
- 每完成一章都必须写 `logs/progress.md` heartbeat，记录已完成章节、当前章节、累计 segment 数、累计 anchor_checks 数和下一步。
- 不允许在内存中憋完整全片结果。若 04 节点超过 2 分钟没有新增 chapter checkpoint 或 heartbeat，视为执行异常；执行 agent 必须中断当前生成策略，改为逐章生成或输出 `PROCESS_RULE_DEFECT`。
- 所有章节都完成后，才能合并为：
  - `04-voiceover-segments/voiceover-segments.json`
  - `04-voiceover-segments/voiceover-segments-manifest.json`
  - `04-voiceover-segments/anchor-text-position-preflight.json`
  - `04-voiceover-segments/content-window-preflight.json`
- 合并 manifest 必须列出所有章节 checkpoint、章节覆盖范围、segment 总数、must-align anchor 总数、已覆盖 anchor 数、未覆盖 anchor 列表、非阻塞 downgrade 列表、时间单调检查和 gap/overlap 检查。
- 每次 04 重新生成、回滚修复、删除/新增/改写任意正式 `segments[]` 或 `non_voice_ranges[]` 后，必须重新生成全片 manifest 和全部 04 preflight。不得沿用上一 attempt 的 preflight。
- 每次 04 重新生成、回滚修复、删除/新增/改写任意正式 `segments[]` 或 `non_voice_ranges[]` 后，也必须同步重建受影响章节 checkpoint；如果无法可靠判断受影响章节，默认重建全部 `04-voiceover-segments/chapters/chapter_NNN.voiceover-draft.json`。章节 checkpoint 的 attempt、segment 列表和 voice_text 必须与当前全片 `voiceover-segments.json` 对应章节一致。
- 每个 04 preflight 都必须记录当前 `voiceover-segments.json` 的 `attempt`、`voiceover_segments_sha256` 和 `segment_count`。这三项必须与现场文件一致；不一致时视为旧证据污染，04 不得 PASS。
- 04 的确定性 preflight 可以使用：
  ```bash
  python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/build_voiceover_preflight.py \
    --segments /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-segments.json \
    --output-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments
  ```
  该脚本只负责当前文件 sha、attempt、时间线、重复锚点、低信息碎片和明显英文残留等确定性检查；跨窗口内容、事实覆盖和锚点语义仍必须由 LLM/评测 agent 复核。
- 04 的 `qa/eval-request.json` 必须把逐章 checkpoint、全片 `voiceover-segments.json`、manifest 和 preflight 报告都列入 `artifact_paths`。缺少逐章 checkpoint 时，节点评测不得 PASS。
- 如果 eval-request 要求 `require_chapter_checkpoint_consistency`，节点评测必须确认每个章节 checkpoint 与当前全片文件同 attempt、同章节 segment 序列、同 voice_text；旧 attempt checkpoint 不得作为当前证据。

每个 `voiceover-segments.json` 必须满足：

- `schema_version: voiceover-segments.v1`
- `segmentation_mode: audio_semantic_anchor`
- `time_allocation_mode: original_audio_word_anchor`
- `time_source: asr_word_timestamps_plus_transcript_correction`
- 每段必须有非空、唯一、稳定的 `segment_id`。字段名必须叫 `segment_id`，不能使用 `id`，不能为 `null`，不能依赖数组序号；TTS draft 文件、段级 manifest、字幕报告、锚点 QA 和验收报告都必须使用同一个 `segment_id` 串联证据。
- 每段 `start` / `end` 来自语义锚点。
- 每段只说本时间窗内的信息，高辨识度词不能提前。
- 如果本段包含有明确画面对应物的关键词，`start` 必须同时尊重原声词级锚点和视觉锚点；必要时拆成“铺垫段”和“关键词段”。
- 单段建议 4-30 秒；超过 30 秒必须拆。
- `voice_text` 只包含要朗读的中文正文，不含 Markdown、字段名、注释。
- `voice_text` 必须是可以独立朗读的完整观众句或完整短语组。正式段不得以逗号、顿号、冒号、分号、连接词、时间状语或让人等待下一段补完的半句结尾；如果中文为了锚点必须拆开，也要让每个 TTS segment 自身是可听懂的短句。
- `voice_text` 必须是观众应该听到的正文，不能是制作说明、流程说明或给剪辑/TTS 的指令。诸如“没有新的有效口播信息”“自然停顿”“过渡停顿”“保留为”“这里无需口播”“让画面...”等文本一旦出现在正式 `voice_text` 中，必须写入 `blocking_low_information_or_asr_noise` 并禁止进入 05。
- `voice_text` 不得残留未翻译英文句子。允许的拉丁字母只限专名、品牌、产品、人名、地名、单位、URL 或行业术语，并必须在 manifest 或 preflight 的 allowlist/notes 中可解释。
- `voice_text` 不得把 ASR 退化文本、断裂句、低信息废句或明显错词物化为正式中文口播。低信息检查不只适用于长窗口；短窗口如果只有孤立连词、代词、系动词、半句话、重复碎片或无法形成观众可理解命题，也不能作为正式 TTS 段。必须回到字幕、上下文和相邻 ASR 重新校正文本，不能进入 05。
- 03 中标注为 `Use ASR word time; correct wording against transcript before 04` 的文本，ASR 只提供时间，不能作为最终事实文本直接翻译。04 必须优先使用 02 plain subtitle、03 revised/corrected text、画面硬字幕和相邻上下文校正语义；如果 ASR source 与字幕冲突，以字幕/上下文为准。
- `voice_text` 不能包含 ASR 词义误译或荒谬中文搭配。例如把 `physical contact` 误成“实体内容”、把 party 语境误成“聚会高手”、把 ASR stutter 直译成重复中文，都属于 blocking ASR/semantic degradation，必须回 04 修正或转入 `non_voice_ranges[]`。
- 对低信息或 ASR 噪声的修复必须做全局清扫，而不是只修 05 诊断失败的单段。相邻时间窗若出现同一类碎片、重复短句或没有文本依据的微段，应作为一个噪声簇一起合并、改写或转入 `non_voice_ranges[]`。
- 如果源时间窗确实没有可作为观众口播的有效文本依据，不能为该窗口制造一条带制作说明的 `voice_text`。正确做法是：
  - 合并到相邻真实语义段，且不提前硬锚点；
  - 或从正式 `segments[]` 中移除该口播段，并在 `non_voice_ranges[]` 或等价 manifest 字段中记录 `reason = asr_noise_no_text_authority | visual_pause | no_speech`、原时间窗和证据来源。
  正式 `segments[]` 只放会被 TTS 朗读的正文。
- 保留关键事实、数字、专有名词、因果、转折、例子和立场，不要做摘要式缩水。
- 硬锚点段尤其不能提前包含后一个时间窗的事实、解释、因果或例子；如果该锚点窗口太短，只写本窗口内的短句，后续信息放到后续 segment。
- preflight 必须包含并通过 `blocking_untranslated_source_text=[]`、`over_window_content_risks=[]` 和 `blocking_low_information_or_asr_noise=[]`，否则不得进入 `05-tts-alignment`。
- 全片合并后必须重新计算而不是沿用章节自检：
  - `timeline_overlaps=[]`
  - `duplicate_materialized_source_anchor_ids=[]`
  - `duplicate_segment_ids=[]`
  - `chapter_boundary_conflicts=[]`
  若同一 `source_anchor_id` 在两个章节中出现，保留一个正式 `must_align` 段，其余只能作为上下文，不得进入最终 `segments[]`。

如果 TTS 生成后某段空白太长，优先回到该段补回原文信息或重分段；不要用整章慢放。

补稿策略：

- 对 tail silence 超过阈值的段，读取同一时间窗内的 ASR 原文、字幕文本、前后语义节点和视觉锚点。
- 补回遗漏的事实、数字、限定词、因果、例子、比较对象或自然过渡。
- 如果源 ASR 原文显然破碎、错词或低信息，必须使用同一时间窗的字幕文本、前后上下文、画面硬字幕或章节语义来修正；不能把破碎 ASR 逐字翻成中文。
- 如果修正后仍没有观众应该听到的正文，必须把该时间窗转成 `non_voice_ranges[]` 或并入相邻段，不能生成“保留为停顿”之类的口播。
- 不要补无意义套话；新增文本必须能在原文或上下文中找到信息依据。
- 如果补稿会让下一个高辨识度词提前，必须拆段，而不是把信息塞进原段。
- 对同一章节多段都偏短的情况，优先重分章/重分段；不要逐段机械加句子。

如果 `draft_duration / target_duration` 过低，优先先补稿；这些规则用于标记段级失败：

- `must_align` 段低于 `0.72` 标记为段级失败。
- 普通段低于 `0.65` 标记为段级失败。
- 单段尾部静音超过 `2.0s` 标记为段级失败，并进入长静音复核。
- 不得在报告中把超过阈值的长静音写成 `None`。
- 不得为了通过上述门槛，把 `voiceover-segments.json` 的 `start/end/target_duration_sec` 改成 TTS 实际时长或累加时间线。时间戳必须来自原声音频 ASR word anchors。修复只能回到补稿、重分段或重生成 TTS。
- 这些门槛不能只等全片 TTS 后再发现。进入全片正式 TTS 前，必须先用正式 `voice_profile` 对全部 `must_align` 段做真实 draft TTS 诊断，并写入 `05-tts-alignment/diagnostics/hard-anchor-duration-diagnostics.json` 或等价文件。诊断整体通过标准是 `segment_pass_rate >= 0.90`；若低于 90%，不得继续生成全片正式音频，必须记录轻量失败摘要，清空 `04-voiceover-segments` 及下游 active 目录，回到 04 重新补稿/重分段并重新经过 04 独立验收。达到 90% 时，少数失败段作为 warning 记录，不再阻塞流程。
- `hard-anchor-duration-diagnostics.json` 必须可审计：顶层必须填 `attempt`、`source_voiceover_attempt`、`source_segments_sha256`、`decision`、`overall_pass`、`pass_count`、`segment_pass_rate`、`min_segment_pass_rate`、`failed_count`、`failed_segment_ids`、`tolerated_failed_segment_ids`、`segment_count`、`must_align_count`、`normal_sample_count`；每个诊断段必须包含 `segment_id`、`sync_priority`、`target_duration_sec`、`tts_duration_sec`、`coverage_ratio`、`tail_silence_sec`、`tempo_factor_if_compressed`、`gate_flags`、`pass` 和当前正式 `voice_text`。如果这些字段缺失、为空或与当前 04 attempt 不匹配，05 必须视为自身审计失败，不能进入全片 TTS，也不能把该诊断当作可信回滚依据。

## 5. TTS 和对齐

默认 TTS：

- 使用本地 Qwen3-TTS/MLX。
- 优先使用已经验证过的 1.7B Base 8bit 模型。
- 正式生产必须使用原视频音频做音色克隆。参考音频必须来自同一个源视频的原声音频，推荐 10-20 秒干净单人声，可接受 5-30 秒。
- 只有用户明确要求或授权时，才允许使用固定预设 voice；该产物必须在 manifest 和 QA 中标记为 `preset_voice_authorized`，不能冒充克隆音色。
- 克隆参考必须同时保存 `reference.wav`、`reference_text.txt` 和 `voice_profile.json`，记录 source audio 路径、参考时间段、模型目录、`ref_audio_sha256`、`ref_text_sha256`。
- TTS draft 必须由 `voice_clone_only` manifest 生成。生成后再调用逐段对齐脚本时，必须传入该 TTS manifest；缺少克隆 manifest 不得进入最终合成。
- 全片正式 TTS 前必须先做 `duration_fit_diagnostic`：
  - 使用同一个 `voice_profile.json`、同一个模型目录和同一套生成参数。
  - 覆盖全部 `sync_priority=must_align` 段；同时抽取至少 5 个普通段，覆盖短段、长段、数字密集段和普通叙述段。
  - 输出 `diagnostics/hard-anchor-duration-diagnostics.json`，记录每段 `target_duration_sec`、`draft_duration_sec`、`coverage_ratio`、`tail_silence_sec`、失败原因和建议回滚节点。
  - 单段低于上述 coverage、tail silence 或 tempo 阈值时，标记为段级失败；只有当诊断 `segment_pass_rate < 0.90` 时才必须停止 05 并回滚到 04。不能把诊断候选文本直接作为正式 TTS 输入；正式文本修改必须落在新的 04 attempt，并重新通过 04 独立验收。
  - 诊断 `segment_pass_rate >= 0.90` 后，才能生成全片 `tts/manifest.json` 和 `segment-aligned-audio/manifest.json`。诊断用 draft 不得混入正式全片 draft，除非 manifest 证明它们来自同一个 voice profile 且对应的正式 `voiceover-segments.json` 内容 hash 完全一致。
- 不允许在同一个视频中混用不同 `voice_profile`、不同 ref audio、不同 ref text 或不同预设 voice。局部重生成必须复用同一个 `voice_profile.json`。

推荐正式路径：

```bash
python /Users/wangfangjia/code/worldview-china-video-agent/scripts/generate_continuous_clone_voiceover.py \
  dubbing/voiceover-segments.json \
  --output-dir dubbing/tts \
  --model-dir /path/to/Qwen3-TTS-12Hz-1.7B-Base-8bit \
  --ref-audio dubbing/reference-audio/reference.wav \
  --ref-text-file dubbing/reference-audio/reference_text.txt \
  --inter-segment-pause-sec 0.15 \
  --force

python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/align_draft_segments.py \
  --segments dubbing/voiceover-segments.json \
  --draft-dir dubbing/tts/draft-segments \
  --tts-manifest dubbing/tts/manifest.json \
  --output-dir dubbing/segment-aligned-audio \
  --force
```

`generate_aligned_voiceover.py --voice Dylan` 这类预设音色路径只能作为调试或用户授权的 fallback，不能作为默认正式路径。

对齐规则：

- 每段先生成 draft 音频，记录真实时长。
- `draft_duration <= target_duration`：段尾补静音，不拉慢。
- `draft_duration > target_duration`：轻微 `atempo` 压缩。
- 单段加速最好 `<= 1.15x`。
- 单段尾部补静音最好 `<= 2.0s`。
- 超过阈值时回到配音稿或锚点分段修正。

不要交付旧的 `chapter_aligned` 版本作为最终音轨。

## 6. 中文字幕

字幕是中文配音字幕，不是外文字幕直译。

要求：

- 时间线对应最终中文配音音轨。
- 默认由 `voiceover-segments.json` 的段时间生成；单段过长时按中文标点拆成 1-3 条 cue。
- 最终交付 SRT/VTT 必须来自 `generate_voiceover_subtitles.py` 或等价的逐 cue 字幕生成器，而不是直接把每个 `voiceover segment` 写成一条字幕。任何单条字幕 cue 超过 `8s` 或可见文本超过 `48` 字，都必须回到字幕拆分或上游分段修复。
- 屏幕显示字幕不保留标点符号。`voice_text` 可以保留标点用于 TTS 断句和内部拆分，但最终 `.srt` / `.vtt` 和烧录字幕应去掉逗号、句号、顿号、冒号、分号、问号、感叹号、引号和括号等显示标点。
- 字幕不得早于对应配音关键词。
- 字幕时间线必须先跟随中文口播的阅读顺序连续铺开，再用 `anchor_checks` 做局部校验；不要用 `anchor_checks` 的裸字符串匹配结果直接调度整段字幕。
- 如果同一个锚点词在 `voice_text` 中出现多次，或属于“中国/美国/德国/日本/电动车”等高频背景词，不能靠 `text.find(term)` 决定 cue 时间；必须把它记为歧义锚点，必要时回到分段或 anchor 设计里消歧。
- 每个有 `voice_text` 的 segment，第一条字幕 cue 必须在 segment start 后 `0.8s` 内出现；segment 内字幕空窗不得超过 `1.2s`。如果同一 segment 的字幕被推迟到段尾，即使音频锚点正确也必须 FAIL。
- 不要为了让某个 anchor 词不提前，把该词之前的整段中文字幕藏到 anchor 时间之后。正确做法是：前文按阅读顺序显示；真正必须卡点的词需要通过更细分段、调整词序或更明确的 anchor occurrence 来解决。
- 输出 `.srt`、`.vtt`；最终 mp4 必须烧录中文字幕。
- 如果上游只生成了 `.srt`，最终合成阶段必须从 `.srt` 自动生成 `.vtt`。
- 正式交付缺少 `.srt` 或 `.vtt` 必须 FAIL。
- 如果本机 ffmpeg 没有 `subtitles` / `ass` / `drawtext`，用 Pillow 渲染透明字幕 PNG 序列，再合成 alpha overlay 视频，最后 `overlay` 到原视频。

推荐使用字幕脚本：

```bash
python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/generate_voiceover_subtitles.py \
  --segments dubbing/voiceover-segments.json \
  --output-dir dubbing/subtitles
```

脚本会输出 `subtitle-timeline-report.json`。正式合成前，至少这些阻断项必须为空：

- `segment_start_delay_violations`
- `in_segment_gap_violations`
- `cue_duration_violations`
- `unambiguous_anchor_early_violations`
- `unambiguous_anchor_late_violations`

字幕脚本返回非零、`subtitle-timeline-report.json.decision != PASS`、或最终 SRT 与报告中的 `srt_path` 不是同一文件时，禁止进入最终合成。合成阶段不得覆盖已通过 QA 的 SRT；如果必须重新生成 SRT，必须同步重新生成 `subtitle-timeline-report.json` 并重新校验。

`anchor_ambiguities`、`unambiguous_anchor_early_violations` 和 `unambiguous_anchor_late_violations` 不能被忽略：它们通常说明 anchor 词太泛、出现多次、中文词序和原声锚点冲突，或分段把硬锚点放到了错误窗口。若涉及品牌、产品、人物、数字、屏幕文字、视觉对象或用户指定锚点，必须回到分段/配音稿/anchor 设计修复；若只是高频背景词，应在 QA 说明为什么不构成交付阻断。

字幕硬锚点分级：

- 硬锚点：品牌、型号、产品名、金额、百分比、年份、关键数字、屏幕文字、视觉对象、长专有短语。硬锚点对应的 cue 不能早于或晚于原声锚点超过 `0.8s`。
- 背景锚点：中国、美国、德国、日本、电动车、电池、充电等高频背景词，不能靠裸字符串匹配来强行排字幕；它们主要用于语义检查和抽查，不应把整段字幕推迟到段尾。
- 如果一个硬锚点词位于 `voice_text` 开头，但 `forbidden_before_sec` 晚于 segment start 超过 `0.8s`，说明配音稿词序不满足锚点。不能靠隐藏字幕解决，必须拆 segment、调整中文词序并重新生成对应 TTS。
- 如果一个硬锚点词的原声锚点早于当前 segment start 超过 `0.8s`，也说明分段已经太晚；不能把该词塞到后一个 segment 里，应把它移回对应 source window，必要时重做前后两个 segment 的配音稿和 TTS。

字幕样式：

- 底部居中。
- 粗体白字、黑色厚描边，可带极轻黑色投影。
- 默认不加半透明背景条、背景色块或背景阴影。
- 字幕位置应比传统底部字幕略低，但不能贴边或遮挡播放器安全区。
- 不遮挡画面关键主体；检查 16:9 1080p 下可读。

## 7. 视频合成

使用 `youtube-final-video-composition` 做最终合成。

最终合成：

```text
原视频画面
-> 原声静音
-> 中文逐段对齐音频
-> 烧录中文字幕
-> 统一 1.15x 交付速度
-> 输出 final.zh-voiceover.subtitled.mp4
```

质量规则：

- 如果源素材是 4K，默认输出 `1080p_high_quality`，从高清源缩到 1080p；需要时可额外输出 4K。
- 1080p 输出建议 H.264 `8-12 Mbps` 或 CRF 18-20。
- 正式成片必须是 `1.15x` 交付版本。最终时长必须约等于 `min(source_duration, voiceover_duration) / 1.15`，允许小于 `0.3s` 的容差。
- 交付目录中的中文音频、烧录字幕、`.srt` 和 `.vtt` 必须和最终 MP4 使用同一个 1.15 倍交付时间线。
- 评测锚点时必须把原声音频锚点映射到成片时间：`expected_final_time = source_anchor_time / 1.15`。
- 不要为了中文短音频粗暴剪掉整章画面。对齐优先靠锚点分段、稿件补足、轻微加速和段尾短静音。
- 合成脚本会在合成前拒绝长字幕 cue、超长字幕文本和显示标点。该失败应视为上游字幕/分段失败，不得通过手写粗字幕绕过。

## 8. QA

每个最终视频必须有 QA 报告：

```text
qa/final-render-qa-report.md
render_manifest.json
qa/check-clips/*.mp4
qa/keyframes/*.jpg
```

机械 QA：

- JSON 可解析。
- 音视频时长匹配。
- `render_manifest.json.playback.speed == 1.15`，最终 MP4 时长、交付中文音频时长和交付 SRT/VTT 时间线均落在 1.15 倍交付时间线。
- 字幕 cue 单调不重叠。
- 字幕连续性通过：每个有中文口播的 segment，首条 cue 延迟 `<=0.8s`，segment 内字幕空窗 `<=1.2s`，不存在把整段字幕压到段尾快速闪过的情况。
- 字幕 QA 必须读取 `subtitle-timeline-report.json`；若缺少该报告，执行 agent 不能进入最终合成。
- `subtitle-timeline-report.json` 必须与最终合成输入 SRT 同源。正式 1.15x 交付时，最终 `07-final-composition/subtitles/zh-CN.voiceover.srt` 可以是缩放后的交付时间线文件，但 `render_manifest.json` 必须同时记录原始输入 SRT hash、最终 SRT hash、`input_timeline`、`final_timeline` 和 overlay 来源 hash；若无法证明等比例缩放和 overlay 同源，直接 FAIL。
- 最终 MP4 里烧录的字幕必须和交付的 `.srt` / `.vtt` 同源：执行 agent 必须在 `render_manifest.json` 记录 SRT hash、cue hash、overlay 来源 hash 和 cue 数，并从最终 MP4 现场抽帧对照当前 SRT，而不是只检查 overlay 文件。
- 所有必需文件存在，包括 MP4、中文音频、SRT、VTT、封面、QA 报告和 render manifest。
- `max_tempo_factor <= 1.15` 是段级失败标记阈值；最终是否卡住看 TTS 诊断和对齐 manifest 的 `segment_pass_rate >= 0.90`。
- `max_tail_padding_sec <= 2.0` 是段级失败标记阈值；超过的段必须列入 warning 或失败清单。
- 单段尾部静音超过 2.0 秒不得写成 `None` 或忽略；必须列出 segment id、目标时长、draft 时长、尾部静音秒数和处理建议。
- 对完整中文 voiceover 跑 `silencedetect=noise=-35dB:d=2.0`，并与源音频 silencedetect 和源 ASR word timestamps 对比。
- 如果中文 voiceover 存在 `>2.0s` 静音，而源音频同区间没有对应长静音且源 ASR 有词，必须回到配音稿、分段或 TTS 重生成，不能进入最终合成。
- 最终 MP4 必须在交给验收前现场 `ffprobe` 成功；如果出现 `moov atom not found`、缺音轨、缺视频流或文件大小与 render manifest 不一致，不能进入最终验收。

语义锚点 QA：

- 至少抽 3 个高风险锚点，每个输出前后 10-20 秒检查片段。
- 对最终中文音频或片段做 ASR，确认关键词落在目标时间附近。不能只检查 SRT cue 或烧录字幕。
- 本轮所有硬锚点都必须做最终中文音频 ASR 复核；长视频至少按章覆盖并复核所有高风险硬锚点。列表型硬锚点至少复核列表第一项、中间项和最后一项。若最终中文 ASR 显示关键词晚于或早于 source anchor 超过 `0.8s`，执行 agent 不能进入最终验收。
- 关键品牌/画面锚点误差目标 `<= 0.8s`；普通语义转场目标 `<= 1.5s`。
- 报告必须给出证据，例如“中文关键词出现在 {FINAL_VIDEO_SEC}s，目标锚点 {SOURCE_ANCHOR_START_SEC}-{SOURCE_ANCHOR_END_SEC}s”。
- 若最终成片为 1.15x，报告里的目标锚点必须同时写出原始时间和交付时间，例如“原声锚点 {SOURCE_ANCHOR_START_SEC}s，交付目标 {SOURCE_ANCHOR_START_SEC / 1.15}s”。
- 抽查必须覆盖段内锚点，不得只验证 segment 起止时间。若中文关键词和原声/视觉锚点在同一 segment 内但相差超过阈值，仍然 FAIL。
- 对高风险锚点，SRT/VTT cue 应尽量按句内关键词拆分；如果字幕 cue 粗到无法判断关键词时机，必须输出 `NEEDS_FIX` 或重分字幕。
- 如果字幕已经卡住硬锚点，但最终中文音频 ASR 仍显示关键词滞后或提前，修复点是配音稿、分段或 TTS 对齐；不能只移动字幕，因为那会制造字幕和原声锚点错位。
- 对最终中文音轨跑 `silencedetect`；如果原视频对应区间没有长静默，中文配音不得出现超过 `2.0s` 的连续静音。
- 空白 QA 必须列出 `global_silence_over_2s`。如果为非空，且无法证明原片同区间也静默，只能输出 `BLOCKED` 或回到上游修复。

视觉 QA：

- 抽帧确认中文字幕可读。
- 抽帧确认封面中文标题可读且没有多余说明行。
- 报告源素材分辨率、最终分辨率、视频码率。
- 对所有高风险视觉锚点，至少抽取关键词前、关键词时、关键词后 3 张帧；如果字幕/语音已经进入新对象而画面仍停在旧对象，必须 FAIL。

最终验收 Gate：

- 合成完成后必须启动一个新的无上下文子 agent，传入 `youtube-dubbing-video-acceptance` skill 路径和完整输入文件路径。若 `evaluation_dispatch="supervised_request"`，执行 agent 必须先在 `08-final-acceptance/qa/eval-request.json` 写出最终验收请求，并等待外层主控代开无上下文只读评测 agent。
- 最终验收请求至少包含 `request_type="final_acceptance"`、run dir、最终 MP4、中文音频、SRT/VTT、封面、`render_manifest.json`、`audio-semantic-turns.md`、`voiceover-segments.json`、`segment-aligned-audio/manifest.json`、最终验收 skill 路径和指定输出路径。
- 子 agent 必须输出 `acceptance-report.md` 和 `acceptance-result.json`。
- 只有 `acceptance-result.json.decision == "PASS"` 才能把视频称为正式完整视频；`PASS` 可以包含非阻塞 `warnings`，但 warnings 必须写入报告和最终回答。
- 如果子 agent 输出 `NEEDS_FIX`，执行 agent 必须回到最近责任节点做局部修复。不要大回滚到选题或素材，除非 `rollback_to_node` 指向那里。
- 如果子 agent 输出 `FAIL`，执行 agent 必须按 `rollback_to_node` 回滚到责任节点；若失败暴露流程规则缺陷，停止本轮并输出 `PROCESS_RULE_DEFECT`，不要在正式执行中修改 skill。
- 每次修复后都要重新生成受影响产物，并重新开一个新的无上下文验收子 agent；不能复用同一个验收 agent 的上下文。

失败处理：

- 如果问题是流程规则缺陷，停止执行并报告；这类问题只能在开发对话中修改 skill，不能由执行 agent 在正式运行中修改。
- 如果问题只是某个视频局部锚点错误，回到 `03-audio-anchors` 或 `04-voiceover-segments` 修正该章后重跑下游节点。
- 如果问题只是字幕样式、封面、manifest 证据、检查片段缺失等局部产物问题，回到最近责任节点重做该节点和下游节点。
- 不要只在最终视频上手工硬切补丁而不更新上游记录。

## 9. 历史记录

只有最终被采用并生成过成片的视频才追加到：

```text
/Volumes/GT34/Generated/world_and_china/final-videos.json
```

不要把搜索候选、`ranked_shortlist` 或尚未通过验收的 `best_video` 写入历史。只有最终成片通过验收后，才写入本轮实际使用的视频。写入字段至少包含：

```json
{
  "video_id": "...",
  "url": "https://www.youtube.com/watch?v=...",
  "title": "...",
  "channel": "...",
  "selected_at": "YYYY-MM-DDTHH:MM:SSZ",
  "final_render_manifest": "...",
  "selection_reason": "...",
  "selection_ranked_shortlist": "...",
  "notes": "..."
}
```

## 10. 执行纪律

- 本 skill 不包含任何其它运行模式。需要调试或修改 skill 时，在开发对话中完成，不由执行 agent 在正式运行中完成。
- 执行 agent 每次运行只做一件事：按当前 skill 生产一个正式视频，并按节点验收结果回滚或继续。
- 节点验收和最终验收必须由新的无上下文只读评测 agent 完成。执行 agent 不能自评 PASS；`supervised_request` 只是评测 agent 的调度方式变化，不是放宽验收。
- 如果评测结果暴露当前 skill 无法指导稳定产出，执行 agent 停止本轮并输出 `PROCESS_RULE_DEFECT`，保留失败摘要和关键证据，等待开发对话修订 skill。
- 不允许在 skill、脚本、提示或验证规则中写入某个视频的品牌名、标题、`video_id`、时间点或“golden validation”补丁。

## 交付

最终回答必须简洁列出：

- 自动选择的 `best_video` 和最终选择理由。
- `ranked_shortlist` 路径或简短审计摘要。
- 最终视频路径。
- 中文音频路径。
- 中文字幕路径。
- 封面图路径。
- QA 报告路径。
- 关键检查片段路径。
- 最终验收结论和 warnings；如果是 `PASS` with warnings，必须列出 warnings 摘要。
- 是否已写入 `final-videos.json`。

不要粘贴 API key、完整字幕、完整 manifest 或长日志。
