---
name: worldview-china-podcast-topic-selection
description: "用于为 Worldview China 或类似中文视频生产流程选择 YouTube 上的中国相关播客视频、访谈长谈、专家圆桌、新闻对谈、panel discussion 或 think-tank/forum 长谈。Use when Codex needs to search, filter, rank, or audit recent China-related YouTube podcast episodes, interview shows, expert panels, news discussions, roundtables, or long-form conversational videos, while rejecting sources with more than 4 primary speakers because VibeVoice supports at most 4 voices."
---

# Worldview China Podcast Topic Selection

使用这个 skill 自动寻找并排序 YouTube 上的中国相关多人长谈视频。它是 `worldview-china-topic-selection` 的长谈形态分支：保留 YouTube search/detail/transcript 工具链，但把硬过滤、粗评和内容评分改成适合 podcast / interview / conversation / roundtable / expert panel / news discussion / think-tank forum 的版本。

本 skill 的目标不是只找标题里写了 `podcast` 的节目，而是找适合做中文多声道播客化视频的长谈源：主持人和嘉宾访谈、专家圆桌、新闻对谈、智库 panel、论坛式多人讨论都可以进入候选。但 VibeVoice 当前最多支持 4 个 speaker voice slot，因此一旦 metadata、描述、字幕、画面或 02a speaker census 显示主要说话人超过 4 位，必须直接放弃该候选，不得尝试合并、压缩或临时新增音色。

## Reused Tool Scripts

复用 canonical Worldview China 选题脚本：

```bash
BASE=/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection

uv run python "$BASE/scripts/search_list.py" --query "China podcast" --max-results 20 --order relevance
uv run python "$BASE/scripts/detail_list.py" --ids="$IDS" --published-after "$PUBLISHED_AFTER" --min-duration-seconds 1200 --max-duration-seconds 10800
uv run --with youtube-transcript-api python "$BASE/scripts/get_transcript.py" "https://www.youtube.com/watch?v=VIDEO_ID" --language en --language en-US --language en-GB --cache-dir "$RUN_DIR/transcripts" --video-metadata-file "$RUN_DIR/detail-results.json"
```

注意：YouTube video id 可能以 `-` 开头，传给 `detail_list.py` 时使用 `--ids="$IDS"`，不要使用 `--ids "$IDS"`。

YouTube API key 读取顺序仍然遵循 canonical skill：命令行 `--api-key`，其次 `YOUTUBE_API_KEY` / `GOOGLE_API_KEY`，最后读取 canonical skill 目录下的私有 `.env` / `.env.local`。不要在用户输出、日志或报告中打印 key。

## 本机 YouTube 授权与 transcript 依赖

2026-06-22 起，用户已对本机 Worldview China 播客生产流程给出长期授权：当 YouTube 字幕或下载返回 bot/sign-in/IP 风控时，执行 agent 可直接使用 `yt-dlp --cookies-from-browser chrome` 重试，不需要再向用户确认。仍然不得导出、打印或保存 cookie 原文；日志和报告只能记录 `cookies_from_browser=chrome` 或 `provided`。

`youtube-transcript-api` 缺包必须先修复后重试，不能算候选失败。若 `get_transcript.py` 返回 `Install youtube-transcript-api`、`ModuleNotFoundError: youtube_transcript_api` 或等价错误，改用：

```bash
uv run --with youtube-transcript-api python "$BASE/scripts/get_transcript.py" \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --language en --language en-US --language en-GB \
  --cache-dir "$RUN_DIR/transcripts" \
  --video-metadata-file "$RUN_DIR/detail-results.json"
```

只有该重试真正到达 YouTube 后仍被 request/IP block，才把它记录为 YouTube transcript failure。

## Output Directories

把运行产物放到外置盘：

```text
/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_podcast_{N}/01-topic-selection/
```

如果 `/Volumes/GT34` 不可写，先询问用户再退回内部盘。

保留这些审计文件：

- `combined-search.json`
- `detail-results.json` 或 `detail-results.enriched.json`
- `podcast-metadata-shortlist.json`
- `transcripts/*.plain.json` and `transcripts/*.plain.txt`
- `ranked-shortlist.json`
- `selection-report.md`

读取并过滤历史最终视频：

```text
/Volumes/GT34/Generated/world_and_china/final-videos.json
```

同时读取并过滤近 5 天已被播客 Agent 选中过的视频：

```text
/Volumes/GT34/world_and_china_podcast/selected-videos.json
```

这个 registry 在视频被选为 `best_video` 后立刻写入，不等最终成片完成。它用于防止同一天或近几天多次运行时重复制作同一个 YouTube 视频。

## Hard Requirements

默认硬过滤：

```text
发布时间：过去 7 天内
视频时长：20 分钟 <= duration <= 180 分钟
视频形态：横向长视频；必须是播客、访谈、专家圆桌、新闻对谈、panel discussion、think-tank/forum discussion 或类似多人长谈；不是 Shorts、trailer、纯 clip、短切片、普通新闻包或普通视频 essay
主题：China 必须是主轴，不是描述、标签或章节里的偶然关键词
说话人数：估计主要说话人必须 <= 4；如果标题、描述、嘉宾列表、字幕、章节或画面显示 5 位及以上主要说话人，直接 reject/abandon
去重：过去 5 天已写入 selected-videos.json 的 video_id 必须硬拒绝，不得成为 best_video
最终输出：只有通过字幕/ASR 内容验收的候选才能成为 best_video
```

如果上游任务给出更严格的发布时间或时长范围，使用更严格的范围。日更流程需要更强新鲜度时，可以把发布时间改回过去 3 天。

## Longform Conversation Form Signals

进入字幕拉取前，候选至少满足一类长谈形态信号：

- 标题、频道或描述包含 `podcast`、`pod`、`episode`、`ep.`、`interview`、`conversation`、`roundtable`、`dialogue`、`show`、`with`、`ft.`、`panel`、`discussion`、`debate`、`experts discuss`、`analysts discuss`、`news discussion`、`forum`、`think tank`、`briefing`。
- 频道或节目名明确是播客/访谈节目，例如 `The Prof G Pod`、`20VC`、`The Dip Podcast`、`Asian Insider podcast`、`The World Unpacked`。
- 描述包含主持人、嘉宾、moderator、panelists、experts、analysts、conversation、discussion、listen on Apple/Spotify、episode transcript、章节型长谈结构。
- 新闻机构、智库、大学、论坛或会议频道的视频，只有在它是主持人/主持人组与嘉宾/专家之间的连续讨论时才接受；单人演讲、纯 PPT webinar、新闻包剪辑、记者口播合集不算。
- 估计主要说话人必须 <= 4。若描述列出 5 位及以上嘉宾/主持/专家，或字幕/章节显式出现 5 位及以上主要 speaker，不进入字幕内容 accept；最多只能作为 rejected evidence 写入报告。

拒绝：

- 只有标题或 tag 命中 China，但主体是娱乐、旅游、普通财经泛谈或第三国国内话题。
- 纯剪辑、reaction、短视频搬运、预告片、直播回放碎片。
- 非播客频道的普通视频 essay，除非用户明确允许“播客优先但可收分析长视频”。
- 5 位及以上主要说话人的圆桌、峰会 panel 或新闻多人连线。当前 VibeVoice 只支持 4 个正式 voice slot，不得为了使用该候选而把多人强行合并成 4 人。

## Query Batch

每轮使用 4-6 个关键词批处理，不要一个关键词跑完才换下一个：

```text
China podcast
US China podcast
China geopolitics podcast
China economy podcast
China interview podcast
China Taiwan podcast
```

必要时补充：

```text
South China Sea podcast
China AI podcast
China trade podcast
China roundtable
China conversation
Beijing podcast
China panel discussion
China experts discuss
China news discussion
China analyst roundtable
US China panel
China foreign policy discussion
China economy panel
China debate experts
China think tank discussion
China forum discussion
```

## Workflow

1. 创建 run dir 和 `search/`、`transcripts/` 子目录。
2. 对关键词批量运行 `search_list.py`，每个关键词默认 `--max-results 20`。
3. 合并所有 `.videos[]`，按 `video_id` 全局去重，保留 `query_hits`。
4. 读取 `final-videos.json`，过滤已经正式成片的视频。
5. 调用 podcast agent 的 selected registry，导出过去 5 天已选视频，写入 `<run_dir>/recent-selected-videos.json` 或总控 run 的 `<run_dir>/01-topic-selection/recent-selected-videos.json`：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/selected_video_registry.py \
  recent \
  --run-dir <run_dir> \
  --days 5 \
  --out <run_dir>/recent-selected-videos.json
```

6. 将 `recent-selected-videos.json.recent_video_ids` 作为硬排除列表加入 search/detail/filter/ranking 上下文；这些视频不能成为本轮 `best_video`。
7. 分批运行 `detail_list.py`，默认 `--min-duration-seconds 1200 --max-duration-seconds 10800`。
8. 应用发布时间、时长、视频形态、longform conversation form、主要说话人数 <= 4 和近 5 天已选视频硬过滤。
9. 用标题、频道、描述和互动数据做 metadata 粗评，选出 `top_k_transcripts=12`。
10. 拉字幕：先 `get_transcript.py`；如果缺 `youtube-transcript-api`，按上面的 `uv run --with youtube-transcript-api` 重试；仍失败后用 `yt-dlp --write-subs --write-auto-subs --skip-download` 只抓字幕。
11. 如果 YouTube 要求 bot/sign-in 校验，本机已有长期授权，直接用 `yt-dlp --cookies-from-browser chrome` 对同一候选重试；cookie 原文不得出现在任何日志或报告中。
12. 对拿到字幕或抽样 ASR 的候选做内容评分，同时复核主要说话人数线索；如果 transcript、章节或描述显示 5 位及以上主要说话人，直接 reject，不允许成为 backup 或 accept。
13. 从 `accept` 候选中选择排序第一且不在近 5 天 selected registry 中、且主要说话人估计 <= 4 的视频作为 `best_video`；没有 accept 时输出明确失败原因，不硬选。
14. 写出 `best_video.json` 后，立刻登记本次选择，防止下一轮重复选中：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/selected_video_registry.py \
  record \
  --run-dir <run_dir> \
  --best-video-json <run_dir>/best_video.json \
  --out <run_dir>/selected-video-record.json
```

如果 `ranked-shortlist.json.best_video` 写出后才发现命中过去 5 天 selected registry，必须先用 `selected_video_registry.py filter` 生成 dedupe report 并选择下一个 `accept` / `backup`，不要把重复视频交给 02 下载。

## Scoring

Metadata 粗评只决定是否值得拉字幕，满分 10。为了兼容旧报告，字段名可以继续叫 `podcast_form_score`，但语义已经扩展为 longform conversation form：

```text
podcast_form_score / longform_conversation_form_score: 0-3
china_metadata_score: 0-3
engagement_score: 0-2
freshness_and_channel_score: 0-2
```

字幕内容评分满分 10：

```text
podcast_form / longform_conversation_form: 0-2
china_relevance: 0-3
foreign_perspective: 0-2
insight_density: 0-2
angle_novelty: 0-1
```

说话人数不是加分项，而是硬门槛：

```text
estimated_primary_speaker_count <= 4: may continue
estimated_primary_speaker_count > 4: reject / abandon
unknown but no evidence of >4 speakers: may continue to 02a speaker census with risk flag
02a speaker census finds >4 primary speakers: abandon candidate immediately
```

决策阈值：

```text
content_score >= 8: accept
7 <= content_score < 8: backup
content_score < 7: reject
```

没有字幕、ASR 或可复用历史缓存文本时，不得输出 `accept`，只能输出 metadata shortlist 和阻塞原因。

## Transcript Fallback Rules

字幕优先级：

1. `get_transcript.py` / `youtube-transcript-api`；若当前环境缺包，必须先用 `uv run --with youtube-transcript-api` 临时带依赖重试。
2. `yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs "en.*"`
3. 本机长期授权下，遇到 bot/sign-in/IP 风控时直接使用 `yt-dlp --cookies-from-browser chrome`；如果用户另行提供 cookies/proxy，也可使用对应参数。
4. 低成本抽样 ASR

抽样 ASR 限制：

- 只抽开头、中段、结尾，每段 90-120 秒。
- 每个候选总抽样音频不超过 6 分钟。
- 整轮最多对 3 个候选做抽样 ASR。
- 不得保留完整原声音频；如果工具临时生成完整文件，抽样后立即删除并记录。
- 抽样结果必须标记 `text_source=audio_asr_fallback` 和 `text_coverage=sampled_audio_asr`。

## Output

用中文输出。成功时包含：

- 标题、频道、URL、发布时间、时长、播放量、评论数。
- longform conversation form 证据，包括它是 podcast、访谈、圆桌、新闻对谈、专家 panel、智库讨论还是其他长谈形态。
- 主要说话人数估计及依据；如果只是 metadata 阶段无法确定，必须写 `speaker_count_needs_02a_confirmation=true`，并由 02a 最终裁决。
- 字幕内容评分五项和 `content_score`。
- 2-4 句中文摘要。
- 为什么它是中国相关播客，而不是普通 China keyword 命中。
- 主要风险。
- `ranked-shortlist.json` 或简表路径。

被 YouTube 字幕风控阻断时，输出：

- `TRANSCRIPT_BLOCKED` 或 `NO_ACCEPTABLE_VIDEO_TRANSCRIPT_BLOCKED`。
- 已完成的 search/detail/filter 统计。
- metadata-level best candidate 和 backup candidates。
- 明确说明这些候选尚未通过字幕内容验收，不能作为 canonical `best_video`。
