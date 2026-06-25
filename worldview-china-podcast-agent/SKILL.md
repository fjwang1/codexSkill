---
name: worldview-china-podcast-agent
description: "Worldview China 播客 Agent 的端到端总控 skill：自动选择 YouTube 上的中国相关视频播客/访谈长谈，必须下载并校验源视频 source.mp4，获取字幕或音频转写，将原文忠实翻译成适合中文口语表达的双人播客稿，并在 B 站/中国内网发布前做最小必要文本合规删改与顺滑承接；若源视频为英文或其他非中文语言，必须从原视频音频中按人物抽取原声 reference，经 Qwen3-TTS 生成中文 voice prompt 后再交给 VibeVoice 克隆音色并生成完整中文播客音频。Use when Codex needs to translate a China-related YouTube video-podcast into natural Chinese speech while preserving what the source speakers said and preparing a mainland-platform publishable version."
---

# Worldview China Podcast Agent

本 skill 是 `worldview-china-video-agent` 的播客化分支。目标是把海外 YouTube 播客/访谈忠实翻译成中文口语视频：他说什么，我们就翻译什么；允许把英文表达改成中国人听得懂、说得自然的中文，但不重新策划、不总结替代原文、不新增分析观点。

第一版明确不做逐句原画面同步：不要求中文关键词卡到原视频画面、原声 word anchor 或视觉转场。但正式生产必须下载源视频并做画面抽帧 QA，确认候选是视频播客/访谈画面，不是纯音频静态上传、slideshow 或普通新闻包。最终视频默认保留源视频主画面时间线：静音英文原声，替换为新生成的中文播客音轨，并把中文硬字幕烧进正式投稿 MP4；若用户明确要求“不需要一一对应”“后半部分直接裁掉”“裁到中文音频结束”，则正式成片改为 `source_video_revoice_trim_to_audio_duration`：保留源视频从开头到中文音频结束点的画面，直接裁掉后半段，不做尾部静音补齐。只有用户明确要求“画面一模一样”“不要硬字幕”“只要 sidecar 字幕”时，才不得烧录字幕，只能输出 sidecar SRT/可选软字幕，并在 render manifest 记录该例外。静态封面/章节卡只允许作为临时试听样片或下载失败时的明确降级验证，不得作为正式目标交付。

## 核心差异

从旧视频 Agent 继承：

- 独立 run 目录、manifest、日志和可审计产物。
- 自动选题和历史去重。
- 失败时停在责任节点，不把缺证据产物标为完成。

从旧视频 Agent 删除：

- `youtube-audio-anchor-dubbing` 原声音频锚点流程。
- 视觉锚点、硬锚点、`±0.8s` 原画面对齐。
- Qwen3 逐段 TTS 和 `pad/atempo` 回填。
- 1.15x 原视频交付时间线。
- 围绕画面同步的大量节点验收。

采用：

- `worldview-china-podcast-topic-selection` 选中国相关 YouTube 播客。
- `youtube-media-preparation` 下载并校验完整 YouTube 源视频、源音频、缩略图和元信息。
- 中文 `Speaker 0` / `Speaker 1` 双人播客翻译稿：保留原说话顺序、事实、数字、人物、立场和反问，表达做中文口语化。
- 中文翻译和 TTS 文稿不得出现中国当代国家领导人的具体姓名，例如 `习近平`、`Xi Jinping`、`Xi` 等；必须按语境改成自然中文统称。优先考虑翻译表达的合理性和顺滑度，例如外交固定表达用 `中美领导人峰会`、`中美领导人会晤`，不要机械写成 `特朗普和中国国家领导人峰会`。外国国家领导人的名字可以按语义保留；历史人物和非中国当代领导人的提及不在此规则内。
- 从最早中文稿开始遵守 B 站规范用语：规范使用与国家形象相关的特定标识、呼号、称谓、用语；中国台湾、中国香港必须使用完整称呼，不得简称 `台湾`、`香港`；英文“中国大陆”只允许 `Chinese mainland`、`China's mainland` 或 `the mainland of China`，不得使用 `mainland China` / `Mainland China`；特定场所应写 `侵华日军南京大屠杀遇难同胞纪念馆`，不得写 `南京大屠杀纪念馆`；自治区应写 `新疆维吾尔自治区`，不得写 `新疆维吾尔族自治区`。这些规则必须前置到 03/03b/04/02d/07/10 的生成约束里，并由独立文本审核 gate 复查。
- 章节切分只服务于后续 TTS 分块、字幕 QA 和长稿管理，不服务于重新组织观点。
- 长播客默认在中文对话稿完成后增加 `04b-series-episodes` 发布单元拆分：按语义章节把完整中文稿拆成多个 30-40 分钟左右的 B 站子视频 episode；每个 episode 独立走 05/06/07/08/09/10/11，且必须串行执行，不得并行跑 VibeVoice。
- VibeVoice-1.5B 分块生成：先按语义章节规划，再按本机 VibeVoice 可稳定完成的长度拆成生产子块；绝不把超过 90 分钟的播音稿一次性送入 VibeVoice。
- 对英文或其他非中文源视频，强制从原视频两位主要说话人的干净单人片段中抽取原声 reference，再用 Qwen3 生成短中文 voice prompt 注册给 VibeVoice；不得跳过 02c，不得直接把英文 reference 交给 VibeVoice 做正式全片。
- 如果源视频本身已经是中文，允许直接使用 02b 抽出的中文 reference 作为 VibeVoice prompt，不需要 Qwen3 桥接。
- 拼接后的 `audio/final_podcast.wav` 作为唯一中文音频母带。
- 对最终中文音频做 ASR/forced alignment，再生成字幕；最终合成默认使用源视频画面轨替换音轨并烧录中文硬字幕，而不是静态视频。无硬字幕/sidecar-only 只允许在用户明确要求严格保留源画面流时作为例外。

## 子 Skill 地图

按需读取这些 skill，不要凭记忆执行：

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-topic-selection/SKILL.md
/Users/wangfangjia/.codex/skills/youtube-media-preparation/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-media-preparation/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-podcast-title-cover/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-text-compliance-review/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-source-voice-prompts/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-qwen-vibevoice-prompts/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-publish-metadata/SKILL.md
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/SKILL.md
/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/SKILL.md
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/SKILL.md
```

`/Users/wangfangjia/.codex/skills/youtube-media-preparation/SKILL.md`
是可触发的顶层入口；canonical 实现目前集中在
`/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-media-preparation/SKILL.md`。
执行源视频下载时读取 canonical skill，并优先使用它的
`scripts/prepare_youtube_media.py`。

可复用脚本：

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/run_article_vibevoice_audio.py
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/postprocess_vibevoice_audio.py
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/export_playback_audio.py
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/build_dialogue_timeline_from_asr.py
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/validate_dialogue_timeline.py
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/scripts/build_subtitles_from_timeline.py
```

不要使用旧 Qwen/Qwen3 逐段或整段 TTS 生成最终播客音频，除非用户明确要求 legacy fallback。Qwen3 只允许作为 `02c-qwen-vibevoice-prompts` 的短中文 voice prompt 桥接层；最终连续播客音频仍由 VibeVoice 生成。

## 本机 YouTube 授权与字幕依赖

2026-06-22 起，用户已对本机 Worldview China 播客生产流程给出长期授权：当 YouTube 字幕、格式列表或下载返回 bot/sign-in/IP 风控时，执行 agent 可直接使用本机 `yt-dlp --cookies-from-browser chrome` 重试，不需要再向用户确认。仍然禁止通过浏览器 MCP、DevTools、日志或最终回答导出、打印、保存 Google/YouTube cookie 原文；manifest 和报告只能写脱敏状态，例如 `cookies_from_browser=chrome` / `provided`。

`youtube-transcript-api` 缺包不是候选失败，也不是 YouTube 字幕失败。若 `get_transcript.py` 报 `Install youtube-transcript-api` 或 `ModuleNotFoundError: youtube_transcript_api`，必须先用临时依赖重试：

```bash
uv run --with youtube-transcript-api python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/get_transcript.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --language en \
  --language en-US \
  --language en-GB \
  --cache-dir <run_dir>/01-topic-selection/transcripts \
  --video-metadata-file <run_dir>/01-topic-selection/detail-results.json
```

只有在临时依赖重试后仍被 YouTube request/IP block、视频无字幕，且 `yt-dlp` 无 cookie 与 cookie 重试都失败时，才把 01 记为 `TRANSCRIPT_BLOCKED`。

## 输出目录

固定工作根目录：

```text
/Volumes/GT34/world_and_china_podcast/
```

根目录长期维护：

```text
/Volumes/GT34/world_and_china_podcast/selected-videos.json
```

每轮创建：

```text
/Volumes/GT34/world_and_china_podcast/{YYYYMMDD}_{N}/
├── 00-run-setup/
├── 01-topic-selection/
├── 02-source-capture/
│   ├── youtube-media/
│   │   ├── source.mp4
│   │   ├── source.wav
│   │   ├── source.jpg
│   │   ├── source.info.json
│   │   ├── metadata.json
│   │   ├── media_manifest.json
│   │   ├── probe.json
│   │   └── probe.audio.json
│   └── source-video-frame-qa/
├── 02a-speaker-census/
│   ├── review/
│   │   ├── first_6min_review.mp4
│   │   └── first_6min.wav
│   ├── speaker_roster.json
│   ├── speaker_census_evidence.json
│   └── speaker_census_report.md
├── 02d-title-cover/
│   ├── title_cover_manifest.json
│   └── title_cover_report.md
├── 02b-source-voice-prompts/
│   ├── source_speaker_timeline.normalized.json
│   ├── voice_prompt_manifest.json
│   ├── voice_prompt_report.md
│   ├── speaker0/
│   │   ├── en-<VoiceName>_source.wav
│   │   └── clips/
│   └── speaker1/
│       ├── en-<VoiceName>_source.wav
│       └── clips/
├── 02c-qwen-vibevoice-prompts/
│   ├── prompt_manifest.seed.json
│   ├── qwen_generation_input.json
│   ├── qwen_generation.stdout.txt
│   ├── qwen_generation.stderr.txt
│   ├── reference/
│   ├── qwen_speaker0/
│   ├── qwen_speaker1/
│   ├── registered/
│   ├── voice_prompt_manifest.json
│   └── voice_prompt_report.md
├── 03-source-translation/
├── 03b-mainland-publish-safety/
├── 04-podcast-script/
├── 04c-bilibili-text-compliance/
├── 04b-series-episodes/
│   ├── series_manifest.json
│   ├── series_execution_plan.md
│   ├── episode_001/
│   │   ├── episode_manifest.json
│   │   ├── podcast_script.md
│   │   ├── 04-podcast-script/
│   │   ├── 04c-bilibili-text-compliance/
│   │   ├── 05-vibevoice-chunks/
│   │   ├── 06b-audio-transcript-integrity/
│   │   ├── 06c-audio-timeline-alignment/
│   │   ├── 08-source-video-revoice/
│   │   ├── 09-final-qa/
│   │   ├── 10-bilibili-publish/
│   │   ├── bilibili_upload_metadata.json
│   │   └── bilibili_upload_draft_report.json
│   └── episode_002/
├── 05-vibevoice-chunks/
├── 06-audio-alignment/
├── 06b-audio-transcript-integrity/
├── 06c-audio-timeline-alignment/
├── 07-subtitles/
├── 08-source-video-revoice/
├── cover/
│   ├── cover_title.json
│   ├── background_raw.png
│   ├── background.png
│   ├── visual_subject.json
│   ├── image_source_manifest.json
│   └── cover_4k.png
├── video_title.txt
├── 09-final-qa/
├── 10-bilibili-publish/
│   └── publish_metadata_report.json
├── 12-series-final-qa/
│   ├── series-final-qa-result.json
│   └── series-final-qa-report.md
├── bilibili_upload_metadata.json
├── publish_info.txt
├── bilibili_upload_draft_report.json
├── bilibili_upload_draft_report.md
├── logs/
└── run_manifest.json
```

同时维护兼容路径，供现有文章播客脚本使用：

```text
/Volumes/GT34/world_and_china_podcast/{YYYYMMDD}_{N}/
├── podcast_script.md        # 复制或软链到 04-podcast-script/podcast_script.md
├── audio/                   # 复制或软链最终音频、manifest、ASR 对齐产物
└── video/                   # 复制或软链最终字幕、视频、render manifest
```

`article-podcast-audio-alignment` 和 `article-podcast-subtitle-alignment` 的脚本默认读取项目根目录的 `podcast_script.md`、`audio/` 和 `video/`。运行这些脚本前，必须保证兼容路径存在；脚本写出的产物再复制或记录到对应节点目录，不能只存在散乱位置。

如果 `/Volumes/GT34` 不可写，先询问用户再退回内部盘。

只有最终视频通过 QA 后，才追加到：

```text
/Volumes/GT34/world_and_china_podcast/final-podcast-videos.json
```

## 输入和默认模式

默认输入为空，由 Agent 自动选题：

```json
{
  "topic_window": "past_7_days",
  "selection_output": "best_video",
  "final_video_count": 1,
  "source_type": "youtube_video_podcast",
  "source_video_download": "required",
  "source_video_height_target": 2160,
  "source_video_auth": {
    "cookies_from_browser": "chrome",
    "cookies": "none | /path/to/cookies.txt",
    "proxy": "none | proxy_url"
  },
  "quality_downgrade_authorization": "none | user_confirmed",
  "source_video_frame_qa": "required",
  "source_speaker_census": "required_first_6_minutes",
  "source_voice_prompts": "required",
  "source_language": "en | zh | other",
  "voice_prompt_policy": "qwen_chinese_required | source_chinese_direct",
  "output_type": "chinese_podcast_video",
  "audio_backend": "vibevoice_chunked_dialogue",
  "episode_series_split": {
    "enabled_for_long_podcast": true,
    "target_minutes_min": 30,
    "target_minutes_max": 40,
    "serial_execution_required": true,
    "bilibili_schedule_step_hours": 1
  },
  "target_chars_per_chunk": 600,
  "min_split_chars_per_chunk": 350,
  "hard_max_chars_per_chunk": 800,
  "mainland_publish_safety_edit": "enabled_for_bilibili",
  "bilibili_text_compliance_review": "required_after_script_and_before_upload",
  "visual_sync": "disabled_v1"
}
```

如果用户给定 YouTube URL，可以跳过自动选题，但仍需做 podcast form 和 China relevance 检查；不合格时停止并说明原因。

开发验证可以使用：

```json
{
  "smoke": true,
  "source_fixture": "local_short_transcript"
}
```

`smoke=true` 只用于验证 skill 可执行性，不是正式生产。它允许执行 agent 在 run 目录中创建一个短的本地英文播客 transcript fixture，跳过真实 YouTube 抓取阻塞，但仍必须产出 `source_metadata.json`、`source_transcript.en.txt`、忠实中文翻译稿、章节切分、chunk plan、至少一个 VibeVoice chunk 的 dry-run 或真实 smoke、最终 QA。所有报告必须写明 `production_status=smoke_validation_only`，不得写入 `final-podcast-videos.json`。

若 `smoke=true` 且 VibeVoice 选择 dry-run，不会产生最终音频母带。此时允许 `06-audio-alignment`、`07-subtitles`、`08-source-video-revoice` 跳过真实生产，但每个节点都必须写出 smoke manifest/report，至少包含：

```json
{
  "production_status": "smoke_validation_only",
  "status": "skipped_after_vibevoice_dry_run",
  "skip_reason": "no_final_audio_master_in_dry_run",
  "expected_production_outputs": ["list the production files this node would normally create"]
}
```

最终 QA 在该模式下只能是 `PASS_SMOKE`、`NEEDS_FIX_SMOKE` 或 `FAIL_SMOKE`，不能写正式生产 `PASS`。`PASS_SMOKE` 只证明 skill 机械路径可执行，不证明可发布音频/视频质量。

## 运行流程

### 00 Run Setup

创建 run 目录和 `run_manifest.json`。至少记录：

```json
{
  "schema_version": "worldview-china-podcast-run.v1",
  "mode": "execution",
  "visual_sync": "disabled_v1",
  "source_video_download": "required",
  "source_video_height_target": 2160,
  "source_video_auth": {
    "cookies_from_browser": "chrome | user_authorized_browser_profile",
    "cookies": "none | user_authorized_cookies_txt",
    "proxy": "none | user_authorized_proxy"
  },
  "quality_downgrade_authorization": "none | user_confirmed",
  "source_video_frame_qa": "required",
  "source_speaker_census": "required_first_6_minutes",
  "source_voice_prompts": "required",
  "source_language": "en | zh | other",
  "voice_prompt_policy": "qwen_chinese_required | source_chinese_direct",
  "audio_backend": "vibevoice_chunked_dialogue",
  "episode_series_split": {
    "enabled_for_long_podcast": true,
    "target_minutes_min": 30,
    "target_minutes_max": 40,
    "serial_execution_required": true,
    "bilibili_schedule_step_hours": 1
  },
  "target_chars_per_chunk": 600,
  "min_split_chars_per_chunk": 350,
  "hard_max_chars_per_chunk": 800,
  "nodes": {}
}
```

每个预计超过 2 分钟的下载、ASR、TTS、合成或评估等待，都要向 `logs/progress.md` 写 heartbeat。

### 01 Topic Selection

使用：

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-topic-selection/SKILL.md
```

输出必须包含：

- `best_video`，或明确 `NO_ACCEPTABLE_VIDEO` / `TRANSCRIPT_BLOCKED`。
- `ranked-shortlist.json` 或等价审计文件。
- 选中视频的标题、频道、URL、发布时间、时长、播放量、评论数。
- podcast form 证据和 China relevance 证据。

没有字幕、ASR 或历史缓存文本时，不得进入正式翻译；可以停在 metadata shortlist。

`01 Topic Selection` 的 `best_video` 只是候选通过文本和元数据验收；正式生产还必须在
`02 Source Capture` 下载完整源视频并通过源视频画面 QA。若 02 发现源视频是纯静态封面、
slideshow、普通新闻包或无法下载，则不要硬用该候选；应回到 `ranked-shortlist.json`
尝试下一个 `accept` / `backup` 候选。所有回退必须写入 `source_notes.md`。

本地已选视频去重：

- 根目录维护 `/Volumes/GT34/world_and_china_podcast/selected-videos.json`。它记录“被 01 选中”的 YouTube 视频，不等最终成片完成才记录。
- 每次 01 开始前，必须导出近 5 天已选视频并把它们作为硬排除列表交给选题流程：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/selected_video_registry.py \
  recent \
  --run-dir <run_dir> \
  --days 5 \
  --out <run_dir>/01-topic-selection/recent-selected-videos.json
```

- search/detail 后生成 shortlist 时，必须把 `recent-selected-videos.json.recent_video_ids` 一起给评分/筛选上下文；这些视频不得成为本轮 `best_video`。
- 如果 `ranked-shortlist.json.best_video` 命中过去 5 天已选视频，必须先运行去重过滤并选择下一个 `accept`；没有 `accept` 时才选 `backup`；没有可用候选时输出 `NO_ACCEPTABLE_VIDEO_RECENT_DUPLICATE`，不得硬选重复视频：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/selected_video_registry.py \
  filter \
  --run-dir <run_dir> \
  --days 5 \
  --input <run_dir>/01-topic-selection/ranked-shortlist.json \
  --out <run_dir>/01-topic-selection/ranked-shortlist.deduped.json \
  --report-out <run_dir>/01-topic-selection/selection-dedupe-report.json
```

- 确定最终 `best_video.json` 后，必须立刻登记，防止同一天第二次任务重复选中同一个视频：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/selected_video_registry.py \
  record \
  --run-dir <run_dir> \
  --best-video-json <run_dir>/01-topic-selection/best_video.json \
  --out <run_dir>/01-topic-selection/selected-video-record.json
```

- 如果 02 Source Capture 后放弃该候选并改用 shortlist 下一个候选，新候选一旦被确认接替为 `best_video`，也必须再次 record。旧记录保留，表示它确实被本轮占用过，近 5 天内不要再反复尝试。

### 02 Source Capture

为选中视频保存：

```text
02-source-capture/source_metadata.json
02-source-capture/source_transcript.en.txt
02-source-capture/source_transcript.en.json
02-source-capture/source_notes.md
02-source-capture/thumbnail.jpg
02-source-capture/youtube-media/source.mp4
02-source-capture/youtube-media/source.wav
02-source-capture/youtube-media/source.jpg
02-source-capture/youtube-media/source.info.json
02-source-capture/youtube-media/metadata.json
02-source-capture/youtube-media/media_manifest.json
02-source-capture/youtube-media/probe.json
02-source-capture/youtube-media/probe.audio.json
02-source-capture/source-video-frame-qa/opening.png
02-source-capture/source-video-frame-qa/middle.png
02-source-capture/source-video-frame-qa/end.png
02-source-capture/source-video-frame-qa/video_form_report.md
```

正式生产必须先用 `youtube-media-preparation` 下载完整源视频素材包。读取：

```text
/Users/wangfangjia/.codex/skills/youtube-media-preparation/SKILL.md
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-media-preparation/SKILL.md
```

优先运行 canonical 脚本：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-media-preparation/scripts/prepare_youtube_media.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --authorized \
  --output-dir <run_dir>/02-source-capture/youtube-media \
  --yt-dlp-bin "uvx yt-dlp" \
  --height 2160 \
  --require-target-height \
  --language en \
  --language en-US \
  --language en-GB
```

本机已有长期授权使用真实 Chrome 登录状态。若 YouTube 返回
`Sign in to confirm you're not a bot`、`bot_signin_required` 或等价错误，
在同一节点内用授权参数重试，不要降级为低清下载：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-media-preparation/scripts/prepare_youtube_media.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --authorized \
  --output-dir <run_dir>/02-source-capture/youtube-media \
  --yt-dlp-bin "uvx yt-dlp" \
  --height 2160 \
  --require-target-height \
  --cookies-from-browser chrome \
  --language en \
  --language en-US \
  --language en-GB
```

默认先使用 `--cookies-from-browser chrome`。多 Chrome profile 时，若 `chrome` 失败且错误指向 profile 选择问题，再尝试常见 profile 名称，例如
`--cookies-from-browser "chrome:Default"` 或
`--cookies-from-browser "chrome:Profile 1"`。若用户提供 `cookies.txt`，
使用 `--cookies /path/to/cookies.txt`；若用户提供代理，使用 `--proxy URL`。
不要通过浏览器 MCP、DevTools 或日志导出 Google/YouTube cookie 原文。
脚本只允许把授权参数透传给本机 `yt-dlp`，并在 manifest 中记录授权方式已使用。

要求：

- `source.mp4` 必须存在且 `ffprobe` 通过；正式生产不得只保存缩略图或只保存字幕。
- `source.wav` 必须从完整 `source.mp4` 抽取出来，供必要时做 ASR fallback。
- `media_manifest.json` 必须记录实际分辨率、格式、码率、下载命令、probe 路径、transcript 状态和高清审计字段。
- 如果无授权下载被 YouTube bot 校验阻断，错误必须先记录为 `BOT_CHECK_REQUIRED` 或 `AUTH_REQUIRED`；本机已有授权，因此必须使用 `--cookies-from-browser chrome` 重试同一 2160p 目标，失败后再尝试下一个 shortlist 候选。
- cookie 原文不得出现在 `download.log`、`media_manifest.json`、`source_notes.md`、最终回答或对话中；只能记录 `cookies_from_browser=provided`、`cookies=provided`、`proxy=provided` 等脱敏状态。
- 正式生产默认目标下载高度是 `2160p`，不是 1080p。必须优先用 `uvx yt-dlp` 查看完整格式列表，选择最高可用且码率合理的 4K/2160p；如果没有 2160p，优先 1440p，再到 1080p。
- 同一高度优先画质而不是只优先 mp4 兼容性；若 VP9/webm 明显高码率，可以下载后转码为交付所需容器。
- 多语音轨视频必须优先选择 YouTube 标记的 `original` / `default` 原始音轨；禁止只按 `m4a`、码率或文件大小误选自动多语言配音轨。若 `source.info.json` 中存在 original/default 音轨，而 `media_manifest.json.selected_audio_format` 选中了 `language_preference < 0` 的配音轨，02 必须 FAIL 并修正后重跑或重封装。
- 如果本地已有 `source.mp4` 低于目标高度，必须先用 `yt-dlp -F` 或 `source.info.json` 检查是否有更高清格式；若存在更高清格式，使用 `--force` 或新目录重新下载，不得复用低清素材。
- `media_manifest.json` 必须额外记录：
  - `available_max_height`
  - `available_formats_summary`
  - `selected_video_format`
  - `selected_audio_format`
  - `selected_height`
  - `selected_bitrate`
  - `download_status`
  - `download_blocker`
  - `downgrade_reason`
  - `quality_downgrade_authorization`
  - `partial_file_used=false`
- 如果 `available_max_height >= 1440`，但正式生产选用 1080p 或更低，必须 FAIL，除非 `quality_downgrade_authorization=user_confirmed`。
- 若 2160p 下载 2 分钟内文件大小几乎不增长，或 10 分钟内无法稳定推进，应停止该下载并记录 `download_blocker`；正式生产不得自动把 720p/360p 降级结果标记为成功交付。
- 720p/360p 只允许作为临时画面形态 QA 证据，用来判断候选是否为视频播客；不得作为正式生产源视频，除非用户明确确认低清试跑或降级交付。
- 若完整源视频下载失败，不得进入 02b/02c/03；先尝试授权重试或 shortlist 下一个候选。所有候选都下载失败时输出 `SOURCE_VIDEO_DOWNLOAD_BLOCKED`，除非用户明确批准 cookies/proxy。

下载后必须从 `source.mp4` 抽取至少三张源视频帧：

```text
opening: 60-120 秒内，避开纯片头 logo
middle: duration * 0.45-0.55
end: duration - 120 秒附近，避开片尾卡
```

如果 opening 仍是 logo 或广告，继续向后找一帧。`video_form_report.md` 必须记录：

- 抽帧时间点和截图路径。
- 是否出现主持人/嘉宾 talking-head、双人 split-screen、多人圆桌或清晰访谈画面。
- 是否只是纯音频静态封面、slideshow、股票新闻画面、普通新闻包或纯剪辑。
- `video_podcast_form = PASS | FAIL | UNCERTAIN`。

正式生产只有 `video_podcast_form=PASS` 才能进入 02b/02c/03。`UNCERTAIN` 需要主 agent 直接看截图再判定；不能自动当 PASS。

字幕优先用公开字幕。若字幕工具被 YouTube 风控阻断：

1. 先尝试 `yt-dlp --skip-download --write-subs --write-auto-subs`。
2. 仍失败时，本机已有长期授权，直接使用 `yt-dlp --cookies-from-browser chrome --skip-download --write-subs --write-auto-subs` 重试，不再询问。
3. 若改用音频 ASR，允许下载或抽取音频，但产物必须写入本节点并记录来源。

如果 `youtube-media-preparation` 已经成功拿到 transcript，把它复制或规范化为
`02-source-capture/source_transcript.en.txt` 和
`02-source-capture/source_transcript.en.json`。如果 transcript 失败但 `source.wav`
存在，可以对完整音频或抽样音频做 ASR；ASR 文本来源必须写入 `source_notes.md`。

若 `smoke=true`，允许创建本地 fixture：

```text
02-source-capture/source_metadata.json
02-source-capture/source_transcript.en.txt
02-source-capture/source_notes.md
```

fixture 必须模拟中国相关播客/访谈内容，长度足以生成至少 6 个中文 speaker turns；`source_metadata.json.source_type` 必须写 `local_smoke_fixture`。

### 02a Speaker Census

在 02 下载并校验完整源视频后、02b 抽取音色和 03 翻译之前，必须先冻结源视频真实说话人/音色清单。这个节点只判断“这个视频到底有几个人在说话、正式流程要复用几个音色”，不抽取最终 reference，也不生成中文 prompt。

运行：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_speaker_census.py \
  --run-dir <run_dir> \
  --confirm-two-speakers \
  --speaker0-description "前 6 分钟中确认的第一位主说话人，说明声音/画面/身份依据" \
  --speaker1-description "前 6 分钟中确认的第二位主说话人，说明声音/画面/身份依据" \
  --force
```

第一次不确定时，可以先不传 `--confirm-two-speakers`。脚本会生成前 6 分钟 review 包并以 `status=needs_review` 停住，主 agent 必须直接看/听 `review/first_6min_review.mp4` 或 `review/first_6min.wav`，确认说话人数和音色后再用确认参数重跑。正式生产不得跳过这个确认。

输出：

```text
02a-speaker-census/review/first_6min_review.mp4
02a-speaker-census/review/first_6min.wav
02a-speaker-census/speaker_roster.json
02a-speaker-census/speaker_census_evidence.json
02a-speaker-census/speaker_census_report.md
```

通过条件：

```text
speaker_roster.json exists
status == frozen
speaker_count == 2
voice_count == 2
analysis_window_sec >= 300
speakers contains Speaker 0 and Speaker 1
review_media records the first-6-minute audio/video evidence unless smoke/debug explicitly skipped media extraction
```

要求：

- 前 6 分钟里的片头旁白、广告口播、sponsor、插入音乐、第三方素材或短暂路人音频不得算作主说话人，也不得作为后续 voice reference。
- 如果前 6 分钟存在广告或片头干扰，`speaker_roster.json` 仍只冻结真实主说话人；02b 抽 reference 时继续向后找干净单人片段。
- 如果源视频真实主说话人超过两位，必须先决定如何稳定映射到 `Speaker 0` / `Speaker 1` 并在 `speaker_roster.json` / `speaker_mapping.json` 记录依据；不得让 05、episode 或 chunk 临时新增第三个音色。
- 02b、02c、04b series episode、05 VibeVoice chunks 都必须复用这个 `02a-speaker-census/speaker_roster.json`。任何缺失 02a、`status != frozen`、`speaker_count != 2` 或 `voice_count != 2` 的正式 run，09 QA 必须 FAIL。

### 02d Title And Cover

读取：

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-podcast-title-cover/SKILL.md
```

本节点只服务 YouTube 源视频播客，不使用文章播客的 `article-podcast-title-writing`：

- 标题采用 `<source_identity_label>：<translated_title_core>`：前半段体现“谁在说/外网来源身份”，后半段必须是有吸引力的中文平台标题核心。YouTube 原标题只能作为参考信号；如果原题弱、泛、翻译腔或没有点出“眼睛”，必须结合 transcript 和当前 episode 文稿改写成源对话支持的强观点、冲突问题、后果、反常识判断或金句引用。
- 若视频里是马斯克、特朗普、黄仁勋等明确知名人物，直接使用人物中文名；若没有名人，使用有依据的通用身份，例如 `美国议员`、`俄罗斯教授`、`美国鉴证大V`、`华尔街分析师`、`美国智库学者`、`上海美国商会前会长`。
- 禁止偷懒使用来源/频道/平台标签，例如 `来自...`、`中文配音版`、`油管搬运`、`外网播客`、`《频道名》：`、`CGSP：`、`Podcast：`。
- 禁止空泛背景题，例如 `美国中东学者：变局之后，美国、中国和新中东`。这种标题只列出人物和背景，没有告诉观众“美国、中国、新中东到底怎么了”。合格标题必须让观众立刻看到一个冲突、后果或可复述的暴论。
- 允许标题有一点锋利或夸张，但必须来自源播客语义或源说话人在特定语境下说过的话；可以抽离语境做点击钩子，不得造谣、反转立场或编造源视频没有的事实。
- 标题、封面和 metadata 也必须提前遵守 04c 文本合规规则。不得把涉疆/民族宗教/政府压迫/种族灭绝、中国台湾被称为国家、意识形态对抗等高敏表达放大成点击卖点；不得使用站队式标题，例如让某个宗教/族群主体“该押注中国吗？”。
- `cover/cover_title.json.title_text` 必须等于 `video_title.txt`。
- 封面大字也使用同一个中文标题。
- 封面大字必须居中布置，不使用文章播客封面的左侧标题布局。
- Series episode 例外：如果当前 run 是 `04b-series-episodes/episode_XXX` 且存在 `episode_manifest.json`，则 `video_title.txt` 必须包含统一系列名、清晰顺序标记和当前副标题，例如默认模板 `系列名·第1集：中国的经济韧性`；封面 `cover/cover_title.json.title_text` 默认不带顺序号，例如 `系列名：中国的经济韧性`，但 `cover/cover_title.json.video_title_text` 必须等于 `video_title.txt`，并记录 `cover_title_omits_episode_index=true`。
- 封面底图来自源视频高质量抽帧，优先使用 `02-source-capture/source-video-frame-qa/middle.png` 等已经通过 podcast form QA 的帧；不得默认使用原 YouTube 缩略图，除非用户明确要求。
- 本节点允许 `image_source_manifest.json.image_type=source_video_frame_background`，不要套用文章 AI 底图 gate。

运行示例：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-podcast-title-cover/scripts/build_title_cover.py \
  --run-dir <run_dir> \
  --speaker-label "上海美国商会前会长" \
  --identity-basis "YouTube description identifies Ker Gibbs as a longtime China-based executive and former president of the American Chamber of Commerce in Shanghai." \
  --translated-title-core "中国经济，比你想象的更强，也更脆弱" \
  --highlight-text "上海美国商会前会长" \
  --highlight-text "中国经济" \
  --highlight-text "更强" \
  --highlight-text "更脆弱" \
  --force
```

Series episode 运行示例：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-podcast-title-cover/scripts/build_title_cover.py \
  --run-dir <run_dir>/04b-series-episodes/episode_001 \
  --speaker-label "系列名" \
  --translated-title-core "中国的经济韧性" \
  --episode-index 1 \
  --frame <run_dir>/02-source-capture/source-video-frame-qa/middle.png \
  --force
```

输出：

```text
video_title.txt
cover/cover_title.json
cover/background_raw.png
cover/background.png
cover/visual_subject.json
cover/image_source_manifest.json
cover/cover_4k.png
02d-title-cover/title_cover_manifest.json
02d-title-cover/title_cover_report.md
```

`video_title.txt` 是后续发布标题；`cover/cover_4k.png` 是后续投稿封面图。

### 02b Source Voice Prompts

默认从原视频两位主要说话人的干净单人片段中抽取 VibeVoice voice prompt。读取：

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-source-voice-prompts/SKILL.md
```

执行 02b 之前必须已经通过 02a 冻结源视频说话人/音色清单：

- `02a-speaker-census/speaker_roster.json.status` 必须是 `frozen`。
- `speaker_count == 2` 且 `voice_count == 2`，并包含 `Speaker 0` / `Speaker 1` 两个固定 voice slot。
- 02b 不得再根据当前 chunk、episode、字幕片段或抽音色候选重新推断说话人数；它只能从 02a roster 中读取固定映射，再为这两个 speaker 找干净 reference。
- 02b 输出的 `02b-source-voice-prompts/speaker_roster.json` 是 02a roster 的派生副本，会补充 VibeVoice voice name 和抽取阶段 timeline evidence；不得作为新的普查结论覆盖 02a。
- 如果 02a 缺失、未冻结、不是两人两音色，02b 必须停止，不得回退到固定预设音色或自动按字幕猜测。

运行：

```bash
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-source-voice-prompts/scripts/extract_source_voice_prompts.py \
  --run-dir <run_dir> \
  --force
```

输出：

```text
02a-speaker-census/speaker_roster.json
02b-source-voice-prompts/speaker_roster.json
02b-source-voice-prompts/source_speaker_timeline.normalized.json
02b-source-voice-prompts/voice_prompt_manifest.json
02b-source-voice-prompts/voice_prompt_report.md
02b-source-voice-prompts/speaker0/en-<VoiceName>_source.wav
02b-source-voice-prompts/speaker1/en-<VoiceName>_source.wav
```

要求：

- `source.wav` 必须来自完整 `source.mp4`，不是缩略图、预览或低清临时素材。
- 优先使用 02 后生成的 speaker timeline；没有时可用字幕中的 `>>` speaker marker fallback；在已有旧 run 上回填验证时，允许临时读取 `03-source-translation/source_transcript.zh.json`。
- 每人最终 reference wav 目标 `30-60s`，最低 `25s`；由多个 `8-18s` 干净单人片段拼接。
- reference wav 必须来自 `speaker_roster.json` 中冻结的对应人物；不得使用广告口播、节目 sponsor、音乐底、字幕滚动重复段、多人重叠段、主持/嘉宾混杂段或来源不确定段。
- reference wav 必须是 `pcm_s16le`、`24000 Hz`、`mono`。
- 默认把 reference wav 注册到 `/Users/wangfangjia/code/VibeVoice/demo/voices/`，并在 manifest 里记录 `vibevoice_name`。
- 若 `source_voice_prompts=required`，本节点失败不得继续 02c/05；正式生产不得回退到固定预设音色。
- 本节点不是严格说话人分离评测；自动抽取后必须至少抽听两个 reference wav，确认没有串音、音乐或大段静音，再进入 02c。

### 02c Qwen Chinese VibeVoice Prompts

对英文或其他非中文源视频，必须把 02b 抽出的原声 reference 转成短中文 VibeVoice prompt。读取：

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-qwen-vibevoice-prompts/SKILL.md
```

运行：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-qwen-vibevoice-prompts/scripts/build_qwen_vibevoice_prompts.py \
  --run-dir <run_dir> \
  --force
```

输出：

```text
02c-qwen-vibevoice-prompts/prompt_manifest.seed.json
02c-qwen-vibevoice-prompts/voice_prompt_manifest.json
02c-qwen-vibevoice-prompts/voice_prompt_report.md
02c-qwen-vibevoice-prompts/registered/zh-<VoiceName>_qwenzh.wav
```

要求：

- 本节点只生成每人 `5-30s` 的中文 voice prompt，不生成最终播客音频。
- `reference_audio` 使用 02b 的干净原声 clip；英文源必须提供与该 clip 匹配的英文 `reference_text`，优先来自 `02-source-capture/source_transcript.en.json` 中同一时间段文本。
- `target_text` 是短中文自然口语提示，用来让 Qwen3 输出中文声纹桥接音频；不得把完整播客稿送入 Qwen3。
- 成功后必须把两个中文 prompt 注册到 `/Users/wangfangjia/code/VibeVoice/demo/voices/`。
- `02c-qwen-vibevoice-prompts/voice_prompt_manifest.json.status` 必须为 `pass`，并包含 `speaker_voices["Speaker 0"].vibevoice_name` 和 `speaker_voices["Speaker 1"].vibevoice_name`。
- 若 `voice_prompt_policy=qwen_chinese_required`，02c 失败不得继续 05；英文或其他非中文源视频必须使用该策略。
- 只有 `source_language=zh` 且 `voice_prompt_policy=source_chinese_direct` 时，才允许跳过 02c 并直接使用 02b 的中文 source prompt。
- 正式完整跑前，建议先用 1-2 个 VibeVoice chunk 做试听验收；若中文/英文混杂、口音异常或两人音色混淆，先修 02b clip 或 02c target prompt，不要直接跑全片。

### 03 Source Translation And Chapter Segmentation

根据 `02-source-capture/source_transcript.en.txt` 或规范化后的字幕/ASR 文本，生成忠实中文翻译和章节切分：

```text
03-source-translation/source_transcript.zh.md
03-source-translation/source_transcript.zh.json
03-source-translation/chapter_segments.json
03-source-translation/speaker_mapping.json
03-source-translation/translation_report.md
```

本节点的目标是翻译，不是策划：

- 他说什么，就翻译什么；不得删掉原文主线，不得新增分析观点，不得替原节目做总结。
- 若 `source_transcript.en.json` 是为了 02b 说话人/voice prompt 回退而生成的粗分段稿，或其文本量明显短于 `source_transcript.en.txt`，03 翻译必须优先使用完整 `source_transcript.en.txt`；`run_source_translation.py` 会记录 `source_transcript_input_mode=plain_txt_preferred_over_shorter_json`。
- 对 YouTube rolling captions 必须先做重叠去重，再翻译；不得把自动字幕窗口里的重复滚动文本原样写入 `source_transcript.zh.json`、`podcast_script.md` 或 TTS 输入。
- 允许把英文直译改成中国人自然会说、容易听懂的中文口语；但事实、数字、人物、机构、因果关系、态度强弱和反方观点必须保留。
- 原文中的口误、重复、寒暄和主持人口头过渡可以轻微清理，让中文更适合 TTS；但不能用新的论证替代原内容。
- 原文有明确归因时保留归因，例如“Ker 的意思是”“主持人追问的是”；没有归因时不要擅自把观点包装成确定事实。
- 当原文提到中国当代国家领导人的具体姓名时，翻译稿必须使用统称，不直接写人名；同时优先保证中文表达自然、准确、好听，不做机械逐词替换。示例：`Xi Jinping` / `习近平` -> `中国国家领导人`；`Trump-Xi summit` / `特朗普和习近平峰会` -> `中美领导人峰会`；`Biden-Xi meeting` / `拜登与习近平会晤` -> `中美领导人会晤`。外国国家领导人的名字可以保留，例如 `特朗普政府` 不必改成 `美国政府`。不得只在字幕阶段替换，必须在 `source_transcript.zh.json`、`podcast_script.md`、TTS 输入和字幕中保持一致。
- 从翻译初稿开始写入 B 站规范用语，不要等审核阶段再替换：英文“中国大陆”统一写 `Chinese mainland`、`China's mainland` 或 `the mainland of China`，不得写 `mainland China` / `Mainland China`；涉及特定场所时写全称 `侵华日军南京大屠杀遇难同胞纪念馆`；涉及自治区时写 `新疆维吾尔自治区`，不得写 `新疆维吾尔族自治区`。如果原文使用了不规范表达，中文稿和后续英文 metadata 都要规范化。
- 涉台、涉港表达从翻译阶段就要规范：统一写 `中国台湾`、`中国香港`，不得简称 `台湾`、`香港`；不得把中国台湾称为国家，不得写 `中国台湾这个国家`、中国台湾语境下的 `我们的国家`、`这些国家...中国台湾` 等；必要时重写并列结构。
- 原播客多人参与时，尽量保留原说话轮次；VibeVoice 只支持双人时，才把原始说话人稳定映射到 `Speaker 0` / `Speaker 1`，并在 `speaker_mapping.json` 记录映射依据。
- 字幕没有可靠说话人标签时，可以根据 `>>`、问答结构、上下文和源视频画面推断主持/嘉宾切换；不确定处在 `translation_report.md` 标记，不要硬编第三人。
- 章节切分只服务于后续 TTS 分块：按原视频话题转折、自然段落和时长切分，不重排内容。

`source_transcript.zh.json` 每个翻译单元至少包含：

```json
{
  "segment_index": 1,
  "source_start": "00:00:05",
  "source_end": "00:00:12",
  "source_text": "original transcript text",
  "speaker": "Speaker 0",
  "zh_text": "自然中文口语翻译"
}
```

`chapter_segments.json` 每个章节至少包含：

```json
{
  "chapter_id": "chapter_001",
  "title": "仅用于内部切分的短标题",
  "source_start": "00:00:05",
  "source_end": "00:09:50",
  "segment_start": 1,
  "segment_end": 120,
  "estimated_zh_chars": 3000,
  "tts_chunk_hint": "target_8_to_10_minutes"
}
```

章节标题只是内部生产标签，不得作为新的节目标题或观点摘要混入最终播客正文。

### 03b Mainland Publish Safety Edit

在 `03 Source Translation` 之后、`04 Podcast Script Formatting` 之前，默认运行中国内网/B 站发布前文本安全编辑。03 必须保留完整忠实翻译；03b 是派生的发布优化稿，允许为了过审做最小必要删改、弱化和承接，不得反向覆盖 03 原稿。

运行：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_mainland_publish_safety_edit.py \
  --run-dir <run_dir>
```

输出：

```text
03b-mainland-publish-safety/source_transcript.zh.safe.json
03b-mainland-publish-safety/source_transcript.zh.safe.md
03b-mainland-publish-safety/chapter_segments.safe.json
03b-mainland-publish-safety/edit_decisions.json
03b-mainland-publish-safety/safety_report.md
```

编辑目标是“最小改动提高内网平台通过率”，不是重新写节目：

- 保留正常的中国经济、贸易、产业、市场、消费、人口和外企经营分析；不得因为观点不够正面就一刀切。
- 当原文把判断强绑定到中国当代国家领导人个人、党政决策能力、疫情治理决策、尖锐政府动机批评时，优先弱化为政策/市场/信心层面的中性表达。
- 当一段集中讨论中国当代领导人、党政决策能力、新冠/清零/奥密克戎决策批评，或把当前政治人物与毛泽东、文化大革命、红卫兵、MAGA 等做尖锐类比时，允许整段 cut。
- 当原文涉及中国台湾被称为国家、涉疆/民族宗教/政府压迫/种族灭绝叙述、意识形态对抗或“请不要上传到互联网”这类发布安全高敏表达时，03 可以忠实保留原文语义，03b 必须为 B 站发布做最小必要删改、弱化或桥接。不得把高敏表达原样送入 04 播客稿、TTS、字幕、标题、封面或 metadata。
- cut 后必须检查相邻 turn 是否变成“是的”“这种想法”“我说的是”这类失去上下文的孤立回应；必要时一并移除，并插入不超过一两句的 bridge，桥接回“经济、消费、储蓄、市场环境、外企经营”等原主线。
- bridge 只负责顺滑承接，不得添加新的事实、立场或总结性结论。
- 外国国家领导人、美国政治人物、历史人物在正常语境下可以保留；中国当代国家领导人仍不得出现具体姓名。
- 03 的 B 站规范用语规则在本节点继续生效；如果为了发布安全做 bridge，也必须使用规范称谓和地点/自治区全称，不得引入 `mainland China`、`南京大屠杀纪念馆`、`新疆维吾尔族自治区` 等不合规表达。
- 输出必须保留原 speaker 顺序和 source_start/source_end 审计字段；每个删改决策写入 `edit_decisions.json`，每个 cut range 写入 `safety_report.md`。
- 如果 `safety_report.md` 不是 `status: PASS`，不得进入 04 正式 TTS 文稿。

参考规则来源只作为边界启发：官方/平台规则强调违法和不良信息治理、平台审核责任、理性表达和避免煽动对立；开源敏感词库和审查研究说明可用关键词召回，但误伤高，不能直接整库硬过滤。实际生产以本节点的“语境判断 + 最小删改 + 审计记录”为准。

### 04 Podcast Script Formatting

把中文翻译稿整理成 VibeVoice 可读的中文双人播客脚本。若存在 `03b-mainland-publish-safety/source_transcript.zh.safe.json`，必须优先使用它；否则使用 `03-source-translation/source_transcript.zh.json`：

```text
04-podcast-script/podcast_script.md
04-podcast-script/script_report.md
```

脚本定稿后，同步写出或软链：

```text
podcast_script.md
```

正文只能使用：

```text
Speaker 0: ...
Speaker 1: ...
```

要求：

- `podcast_script.md` 是翻译稿的 TTS 版本，不是新节目策划稿。
- 严格沿用 03 或 03b 的顺序和 speaker 映射；不得重新排序章节，不得把长段内容总结成短观点。03b 已经做过的发布安全删改和 bridge 必须保留。
- 如果发现 03b 没有处理干净的中国台湾/中国香港完整称呼、中国台湾被称为国家、涉疆/民族宗教/政府压迫/种族灭绝叙述、意识形态对抗或疑似中国领导人姓名误植，不要继续格式化成 TTS 稿；先回到 03b 修复。
- 中文自然口语，适合听，不像字幕直译；必要时可把英文长句拆成 1-4 句中文，但语义不得丢失。
- 每个 turn 不宜过长；如果原说话人连续讲很久，可以在不改变 speaker 的情况下按自然语义拆成多个连续 turn。
- 保留关键人物、机构、数字、因果、争议和反方观点。
- 对中国当代国家领导人继续沿用 03 的统称规则；如果上游漏掉具体姓名，本节点必须在写入 `podcast_script.md` 前清洗。不要让 TTS 朗读具体姓名后再试图只改字幕。
- 继续沿用 B 站规范用语规则；本节点是 TTS 前最后一次正文定稿，不得把 `mainland China` / `Mainland China`、`南京大屠杀纪念馆`、`新疆维吾尔族自治区` 或其他已知不规范称谓写入 `podcast_script.md`。
- 不得出现制作说明、Markdown 列表、章节标题混入正文 turn。
- `script_report.md` 必须记录 source 和 content_coverage。未启用 03b 时正式生产默认 `content_coverage=full_translation`；启用 03b 时必须写 `content_coverage=mainland_publish_safety_edited`。如果因为用户明确要求压缩而删减，必须写明 `content_coverage=abridged_user_authorized`。

建议全片长度：

- 默认翻译完整源播客；不要为了控制节目长度擅自只选“最强主线”。
- 如果完整翻译估算超过 90 分钟，不是删内容，而是继续分块；VibeVoice 永远不要一次性接收超过上限的长稿。
- 若用户明确要求删减版，仍必须在报告里区分“原文完整翻译”和“授权删减版”。

### 04c Bilibili Text Compliance Review

在 `04 Podcast Script Formatting` 之后、`04b Series Episode Split` 或 `05 VibeVoice Chunks` 之前，必须运行独立文本合规审核。读取：

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-text-compliance-review/SKILL.md
```

本节点不是事后兜底，而是验证 03/03b/04 已经提前遵守规则：

- 主 agent 先运行 deterministic check，召回明确违规词：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-text-compliance-review/scripts/run_bilibili_text_compliance_review.py \
  --run-dir <run_dir> \
  --stage after_script
```

- 当前运行环境支持 subagent 时，必须另外启动一个独立审核子 agent，使用本 child skill 审核 `03-source-translation`、`03b-mainland-publish-safety`、`04-podcast-script`、`podcast_script.md` 以及当时已存在的标题/封面/字幕/metadata。子 agent 不参与正文生成，只给 `PASS` / `FAIL`、命中位置和建议修复方向。
- 输出固定为：

```text
04c-bilibili-text-compliance/text-compliance-review-result.json
04c-bilibili-text-compliance/text-compliance-review-report.md
```

通过条件：

```text
text-compliance-review-result.json exists
status == PASS
summary.fail_findings == 0
reviewed_files includes the current generated script and any title/cover/subtitle/metadata files already created
independent reviewer result is PASS when a subagent was available
```

如果 04c FAIL，不得进入 04b/05/06/07/08/10/11；必须回到 03、03b、04 或标题/封面/metadata 生成节点做最小必要修复，再重新运行 04c。

02d 标题/封面、07 字幕或 10 B 站 metadata 生成/修改后，必须用同一个 child skill 复跑审核，保证投稿前的 `04c-bilibili-text-compliance` PASS 结果覆盖最新文本。不要只审核分段文稿；最终稿、标题、封面文字和投稿文案都属于发布文本。

### 04b Series Episode Split

长播客正式生产默认在 `04 Podcast Script Formatting` 之后、`05 VibeVoice Chunks` 之前运行本节点。它把完整中文对话稿按 `chapter_segments.json` / `chapter_segments.safe.json` 的语义章节拆成多个可发布 episode，而不是按原视频时长机械切割。

运行：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_episode_series_split.py \
  --run-dir <run_dir> \
  --series-title-prefix "系列名" \
  --episode-title-template "{series_title}·{episode_order_marker}：{subtitle}" \
  --episode-order-marker-template "第{episode_index}集" \
  --first-scheduled-publish-at "2026-06-24 11:00" \
  --scheduled-publish-timezone Asia/Shanghai \
  --force
```

若用户给出大 skill 的 B 站投稿时间，该时间就是第一个 episode 的投稿时间；后续 episode 每集递增 1 小时。例如首集 `2026-06-24 11:00 Asia/Shanghai`，第二集 `12:00`，第三集 `13:00`。拆分脚本会在每个 episode run 的 `bilibili_upload_metadata.json` 里预写 schedule seed，后续 `10 Bilibili Publish Metadata` 必须保留这些字段。

估算规则：

- 估算基于 TTS 归一化中文字符数，不基于原视频时长。
- 默认 `330 中文字符/分钟`；若已有同类 `audio/audio_manifest.json` 可校准，脚本会用真实 `chars / audio_duration` 计算 chars-per-minute，并写入 `duration_estimation`。
- 这个默认值不是凭空估计：2026-06-24 用 `scripts/estimate_vibevoice_chars_per_minute.py` 扫描本机 `/Volumes/GT34/Generated` 和 `/Volumes/GT34/world_and_china_podcast` 的历史 VibeVoice `audio_manifest.json` 后，aggregate audio n=15 的 median=325.8 chars/min、p75=335.3；chunk n=102 的 median=341.8；全部记录 n=117 的 median=336.8。代表性的长 Worldview run 约在 325.8-336.8 chars/min，因此默认用 330 作为规划中位值。`300 chars/min` 只作为低分位保守参照，不再作为默认值。
- 可用 `scripts/estimate_vibevoice_chars_per_minute.py` 重新扫描历史样本。默认 30-40 分钟约等于 `9900-13200` 归一化中文字；脚本默认 `target_minutes_min=30`、`target_minutes_max=40`、`target_minutes_ideal=35`。
- 必须优先按语义章节组合 episode；只有单个章节本身超过 40 分钟估算上限时，才允许在该章节内按 segment 边界拆，并在 `series_manifest.json.warnings` 记录。
- 不得为了时长删掉原文内容；每个 episode 是完整翻译稿的连续子集。

输出：

```text
04b-series-episodes/series_manifest.json
04b-series-episodes/series_execution_plan.md
04b-series-episodes/episode_001/episode_manifest.json
04b-series-episodes/episode_001/03-source-translation/source_transcript.zh.json
04b-series-episodes/episode_001/03b-mainland-publish-safety/source_transcript.zh.safe.json  # 若父 run 启用 03b
04b-series-episodes/episode_001/04-podcast-script/podcast_script.md
04b-series-episodes/episode_001/podcast_script.md
04b-series-episodes/episode_001/04b-source-video-segment/source_episode.mp4
04b-series-episodes/episode_001/04b-source-video-segment/source_episode_manifest.json
```

每个 episode run 会通过软链复用父 run 的：

```text
02-source-capture/
02a-speaker-census/
02b-source-voice-prompts/
02c-qwen-vibevoice-prompts/
```

分集标题规则：

- `series_title_prefix` 是全系列统一大标题，例如 `世界眼中的中国`、`华尔街看中国`、`某某访谈`；不要把用户临时举例里的节目名当成固定文案。
- B 站视频标题必须带顺序，但序号样式可配置。默认标题模板是 `{series_title}·{episode_order_marker}：{subtitle}`，默认序号模板是 `{episode_index}` 生成的 `第1集`、`第2集`，例如 `世界眼中的中国·第1集：中国的经济韧性`、`世界眼中的中国·第2集：外企为什么仍看重中国市场`。如果你判断 `EP01`、`（一）` 更适合该系列，可以用 `--episode-order-marker-template` 和 `--episode-title-template` 改，但必须写入 `episode_manifest.json` 并通过 QA。
- 同一系列的可识别序号必须统一：`series_manifest.json.episode_order_marker_template`、每个 `episode_manifest.json.episode_order_marker_template` 和实际 `episode_order_marker` 必须一致。不得首集用 `第1集`、后续改用罗马数字、括号数字或其他样式。
- `episode_manifest.json.video_title` 必须等于该 episode 的 `video_title.txt`。
- `episode_manifest.json.episode_subtitle` 必须和当前 episode 内容强相关，默认从该 episode 覆盖的章节标题生成；执行 agent 可以在运行标题封面前人工/LLM 审核并改成更自然的副标题，但不得打乱 episode 顺序或改变正文覆盖范围。
- `episode_manifest.json.source_start_sec/source_end_sec` 必须对应当前 episode 覆盖的原视频语义区间。04b 会先把父 `02-source-capture/youtube-media/source.mp4` 裁成该 episode 的 `04b-source-video-segment/source_episode.mp4`，后续 08 必须优先使用这个子视频画面，而不是再从完整父视频临时取画面。

封面规则：

- 全系列必须共享同一张源视频 frame 作为封面底图；`series_manifest.json.shared_cover_frame` 记录该路径。
- 每集封面标题默认不体现顺序，只写 `系列名：中国的经济韧性`；因此 series episode 模式下允许 `cover/cover_title.json.title_text != video_title.txt`，但必须满足 `cover/cover_title.json.video_title_text == video_title.txt` 且 `cover_title_omits_episode_index=true`。

串行执行：

- `series_manifest.json.serial_execution_required` 必须为 `true`，`parallel_execution_allowed` 必须为 `false`。
- 逐集执行完整链路：`02d title/cover -> 04c text compliance refresh -> 05 VibeVoice -> 06 final audio ASR -> 06b audio transcript integrity QA -> 06c audio timeline alignment -> 07 subtitles -> 04c text compliance refresh -> 08 source video revoice -> 09 final QA -> 10 Bilibili metadata -> 04c text compliance refresh -> 11 Bilibili upload publish`。
- 完成 `episode_001` 的 11 节点后才能开始 `episode_002`；不得并行跑 VibeVoice 或同时上传多个 episode。
- 父级大任务只有在所有 episode 都完成后，运行 `12 Series Final QA` 通过，才算达标。

### 05 VibeVoice Chunks

这是正式音频节点。不要把完整长稿一次性送入 VibeVoice。

如果存在 `04b-series-episodes/series_manifest.json`，本节点必须在每个 `episode_XXX` run 目录内串行运行，而不是在父 run 上一次性生成完整两小时音频。`episode_001` 完成 05-11 后，才能开始 `episode_002` 的 05；VibeVoice 常驻 batch runner 只服务当前 episode 的 chunks。默认优先使用 `vibevoice-dialogue-tts` 的 MPS 路径；CPU 只是显式 fallback。

先把 `04-podcast-script/podcast_script.md` 拆成语义 chunk：

```text
05-vibevoice-chunks/chunk_plan.json
05-vibevoice-chunks/chunks/chunk_001/podcast_script.md
05-vibevoice-chunks/chunks/chunk_001/audio/vibevoice_dialogue_display.txt
05-vibevoice-chunks/chunks/chunk_001/audio/vibevoice_dialogue.txt
05-vibevoice-chunks/chunks/chunk_001/audio/final_podcast.wav
05-vibevoice-chunks/chunks/chunk_001/chunk_manifest.json
...
05-vibevoice-chunks/final_podcast.wav
05-vibevoice-chunks/final_podcast_preview.mp3
05-vibevoice-chunks/final_podcast_playback.m4a
05-vibevoice-chunks/audio_manifest.json
05-vibevoice-chunks/audio_report.md
```

分块规则：

- 默认先按语义章节切分，再把章节拆成可稳定送入 VibeVoice 的生产子块。
- 当前本机正式生产优先使用 `350-600` 中文字符左右的生产子块，硬上限 `800` 中文字符；这台机器的 VibeVoice 对 `900+` 中文字符且包含 `400+` 中文字符单 speaker turn 的块可能长时间无产物，不能作为正式全流程默认。MPS 比 CPU 快，但仍必须先控制单 turn 和 chunk 形状。
- 如果以后有更快且稳定的推理设备，可把生产子块提升到约 8-10 分钟；单块硬上限仍为 12 分钟，任何估算超过 12 分钟的 chunk 必须继续拆。
- 绝不把超过 90 分钟的播音稿一次性送入 VibeVoice。
- 即使总稿低于 90 分钟，正式生产也优先走 chunked 模式；只有总稿估算不超过 12 分钟时，才允许单 chunk。
- 默认必须把过长的单 speaker turn 切开。正式生产默认 `split_long_turn_max_chars = 220`；如果单个 speaker turn 超过该上限，必须按句号、问号、感叹号、分号、逗号或顿号等自然边界拆成同一 speaker 的连续 turn。不要把 `400+` 中文字符独白原样送入 VibeVoice。
- 原始语义 turn 可以被拆成多个同 speaker turn；这不算删改内容。不得为了保留原始 turn 边界而牺牲 VibeVoice 可完成性。
- 优先按 `03-source-translation/chapter_segments.json` 的原文章节、话题转折和自然小结切分。
- 每个 chunk 尽量包含多个 turn；若源节目本身长时间单人铺垫或连续回答，允许单 speaker chunk，不得为了凑齐双方 speaker 而把 VibeVoice 子块撑大到不可完成。
- 每个 chunk 开头可以保留 1 个很短的自然承接句，但不得重复上一 chunk 的事实正文。

估算方法：

- 用 TTS 归一化后的中文字符数估算时长。
- 初始估算可按 `280-330 中文字符/分钟`；保守拆分时按 `260 中文字符/分钟`。
- 当前本机正式生产默认 `target_chars_per_chunk = 600`、`min_split_chars = 350`、`hard_max_chars_per_chunk = 800`、`split_long_turn_max_chars = 220`、`min_speaker_turns_per_chunk = 0`。设备默认 `mps`，`torch_dtype=auto`，`attn_implementation=auto`；底层 `vibevoice-dialogue-tts` 会在 MPS 上解析为 `float16 + sdpa`，CPU fallback 解析为 `float32 + eager`。
- `chunk_plan.json` 必须记录 `split_long_turn_max_chars` 和每个 chunk 的 `max_turn_char_count`。如果 `max_turn_char_count > 220`，不要启动正式 VibeVoice；先重建 chunk plan。
- 若未来切换到已验证稳定的更快设备，可升至 `target_chars_per_chunk = 2600-3200`、`hard_max_chars_per_chunk = 3800`。
- 生成后以真实 wav duration 为准；若某 chunk 真实时长超过 15 分钟，回到分块计划拆小并重跑该 chunk。

2026-06-22 经验修正：一次正式 run 卡在 `05-vibevoice-chunks`，不是 YouTube 或字幕问题。根因是 `run_vibevoice_chunks.py` 当时只限制 chunk 总字数，未默认拆长 turn；`chunk_001` 虽只有 916 字，但包含一个 458 字的 `Speaker 0` turn，全稿还有多个 470-517 字 turn。VibeVoice CPU `float32/eager` 对这类长单 turn 会在 `model.generate(...)` 内长时间 CPU 满载且直到完成前不写 wav/report；把它当作“20 分钟无 wav = timeout”会误判。以后先检查 `max_turn_char_count`，并用默认长 turn 拆分重建计划。

每个 chunk 仍作为一个临时小项目保存脚本、归一化文本、raw/final 音频和 manifest，但正式生产默认使用模型常驻 batch runner：先为所有待生成 chunk 运行 `prepare_vibevoice_audio_inputs.py`，再一次性启动 VibeVoice 进程加载模型，并批量生成所有 chunk 的 raw wav，最后逐 chunk 运行 postprocess。不得在正式全片生产中为每个 chunk 单独重启 VibeVoice，除非 resident runner 失败且已在报告中记录回退原因。

默认要求读取 `02c-qwen-vibevoice-prompts/voice_prompt_manifest.json`；若它存在且 `status=pass`，必须用其中的中文 prompt voice。只有 `source_language=zh` 且 `voice_prompt_policy=source_chinese_direct` 时，才读取 `02b-source-voice-prompts/voice_prompt_manifest.json`。读取 manifest 中的 `speaker_voices`：

```text
Speaker 0 -> speaker_voices["Speaker 0"].vibevoice_name
Speaker 1 -> speaker_voices["Speaker 1"].vibevoice_name
```

再把这两个名字作为冻结的双人 voice roster 传给 VibeVoice。正式生产不得 fallback 到 `Xinran` / `BowenClean`；固定预设只允许在显式调试或 smoke 验证中使用，并必须写入报告。

正式生产默认 `voice_context_policy=locked_two_speaker_roster`：

- 所有 chunk、所有 episode 都必须复用同一套 `Speaker 0` / `Speaker 1` voice roster。
- chunk 内即使只有一个 speaker 的台词，也不得重新选择、重命名、重排或换用另一个音色；底层 runner 必须按全局 `Speaker 0 -> voice0`、`Speaker 1 -> voice1` 映射。
- `chunk_plan.json`、每个 `chunk_manifest.json` 和 `audio/audio_manifest.json` 必须记录 `voice_context_policy=locked_two_speaker_roster`。
- 正式产物中任何 `auto_by_chunk`、缺失 `voice_context_policy`、chunk speaker_names 与冻结 roster 不一致、或 resident batch report 没覆盖全部最终 chunk，09 QA 必须 FAIL。

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py \
  --project-dir <chunk_dir>

/Users/wangfangjia/code/VibeVoice/.venv/bin/python \
  /Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_resident_batch.py \
  --jobs-json <run_dir>/05-vibevoice-chunks/resident_batch_jobs.json \
  --report-json <run_dir>/05-vibevoice-chunks/resident_batch_report.json \
  --device mps \
  --torch-dtype auto \
  --attn-implementation auto

/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/postprocess_vibevoice_audio.py \
  --project-dir <chunk_dir>
```

推荐直接使用总控脚本，它会自动生成 chunk plan、resident batch jobs、batch report、逐块 postprocess 和最终拼接：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_vibevoice_chunks.py \
  --run-dir <run_dir> \
  --generation-runner resident_batch \
  --voice-prompt-policy qwen_chinese_required
```

上面示例不再传 CPU 三件套；`run_vibevoice_chunks.py` 默认就是 `--device mps --torch-dtype auto --attn-implementation auto`。只有 MPS 不可用、生成 NaN/空音频、长时间无输出或质量异常，并且记录原因后，才显式 fallback：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_vibevoice_chunks.py \
  --run-dir <run_dir> \
  --generation-runner resident_batch \
  --device cpu \
  --torch-dtype float32 \
  --attn-implementation eager \
  --voice-prompt-policy qwen_chinese_required
```

该脚本默认会启用 `--split-long-turn-max-chars 220`。只有在明确调试旧计划时才允许传 `--split-long-turn-max-chars 0` 禁用；正式生产不得禁用。

`--generation-runner legacy_per_chunk` 只用于定位 resident runner 问题或做回归对比；使用时必须写入 `05-vibevoice-chunks/audio_report.md` 或节点日志。

CPU/MPS 对比必须基于同一个 resident batch runner、同一份 `resident_batch_jobs.json`、同一文本、同一 speaker prompt 和同一采样参数。比较指标至少包括：

- 时间：`resident_batch_report.json.model_load_sec`、`total_elapsed_sec`、每个 job 的 `generation_sec`、`audio_duration_sec` 和 RTF。
- 质量：ffprobe 是否通过、raw wav loudness 是否达标、silencedetect 是否出现非预期长静音、是否生成 NaN/空音频/异常重复、试听开头和至少一个 speaker switch 是否自然。
- MPS 若 timeout、NaN、长时间无输出或质量异常，不得用于正式生产；记录为 `mps_not_qualified`，继续使用 CPU `float32/eager`。

然后拼接所有 chunk：

- chunk 间插入 `0.35-0.8s` 自然停顿。
- 输出的 `05-vibevoice-chunks/final_podcast.wav` 是后续唯一母带。
- 记录每个 chunk 的 `global_start_sec` / `global_end_sec`、sha256、duration、turn range、script hash、VibeVoice 参数。
- 拼接后重新导出 preview mp3 和 playback m4a。

聚合 `05-vibevoice-chunks/audio_manifest.json` 必须包含完整脚本 turn 列表，而不是只记录 chunk 文件：

```json
{
  "schema_version": "worldview-china-podcast-vibevoice-audio.v1",
  "audio_backend": "vibevoice_chunked_dialogue",
  "generation_mode": "semantic_chunked_vibevoice",
  "generation_status": "complete | dry_run_not_synthesized",
  "speaker_voices": {
    "Speaker 0": "WC20260618S3Speaker0",
    "Speaker 1": "WC20260618S3Speaker1"
  },
  "voice_prompt_manifest": "02c-qwen-vibevoice-prompts/voice_prompt_manifest.json",
  "script": "podcast_script.md",
  "final_audio": "audio/final_podcast.wav",
  "chunk_count": 0,
  "chunks": [
    {
      "chunk_id": "chunk_001",
      "turn_start": 1,
      "turn_end": 12,
      "global_start_sec": 0.0,
      "global_end_sec": 600.0,
      "duration_sec": 600.0,
      "audio": "05-vibevoice-chunks/chunks/chunk_001/audio/final_podcast.wav"
    }
  ],
  "turns": [
    {
      "turn_index": 1,
      "speaker": "Speaker 0",
      "text": "观众显示稿",
      "tts_text": "TTS 归一化朗读稿"
    }
  ]
}
```

`smoke=true` dry-run 例外：

- 只有当 `generation_status="dry_run_not_synthesized"` 且 `production_status="smoke_validation_only"` 时，`final_audio` 可以是 `null`。
- 只有在同一条件下，`chunks[].global_start_sec`、`chunks[].global_end_sec` 和 `chunks[].duration_sec` 可以是 `null`。
- dry-run chunk 必须提供 `dry_run_artifact`，并记录本来会调用的 VibeVoice 命令或配置。
- 正式生产或真实 smoke 只要生成了 wav，上述字段都必须填真实值。

进入 06 前，把聚合产物同步到兼容路径：

```text
audio/final_podcast.wav
audio/final_podcast_preview.mp3
audio/final_podcast_playback.m4a
audio/audio_manifest.json
```

音频 QA：

- 每个 chunk 和最终 wav 都必须 `ffprobe` 通过。
- 跑 `volumedetect`；raw VibeVoice 若 `mean_volume < -30 dB` 或 `max_volume < -8 dB`，不要靠 loudnorm 硬救，优先重跑该 chunk。
- 跑 `silencedetect=noise=-45dB:d=2`；非刻意长停顿要复核。
- 抽听 opening/middle/end 和至少 5 个 speaker switches。

### 06 Final Audio ASR

把 `05-vibevoice-chunks/final_podcast.wav` 复制或链接为：

```text
audio/final_podcast.wav
audio/audio_manifest.json
```

然后使用：

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/SKILL.md
```

本节点只做完整音频统一 ASR，不做字幕时间轴。必须对所有 VibeVoice chunk 合并后的唯一母带 `audio/final_podcast.wav` 整体识别，不能分段分别验收后再推断整体无问题。先运行：

```bash
/Users/wangfangjia/code/bilibili-mcp/.venv-asr/bin/mlx_whisper \
  <run_dir>/audio/final_podcast.wav \
  --language zh \
  --task transcribe \
  --word-timestamps True \
  --output-format json \
  --output-dir <run_dir>/audio \
  --output-name asr_alignment
```

输出：

```text
06-audio-alignment/asr_alignment.json
audio/asr_alignment.json
```

如果本地没有可用 ASR/forced-alignment 工具，停在本 gate 并报告 `BLOCKED`；不要进入 06b、字幕或视频合成。

### 06b Audio Transcript Integrity QA

这是上传前最重要的音频完整性门禁之一。它发生在字幕时间轴/字幕对齐之前，复用 `06 Final Audio ASR` 产出的完整音频 ASR：

```text
audio/final_podcast.wav
audio/audio_manifest.json
audio/asr_alignment.json
podcast_script.md
```

运行：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_audio_transcript_integrity_qa.py \
  --run-dir <run_dir>
```

输出：

```text
06b-audio-transcript-integrity/audio-transcript-integrity-result.json
06b-audio-transcript-integrity/audio-transcript-integrity-report.md
06b-audio-transcript-integrity/final-audio-asr-transcript.txt
```

检查目标：

- 用最终完整音频 ASR 文字稿和 `audio_manifest.turns` / `podcast_script.md` 做单调文本匹配，确认所有 chunk 拼接后的整体音频确实覆盖了定稿文稿。
- 禁止分段单独看后直接放行。单个 chunk 可能正常，但拼接、漏拼、错拼、覆盖文件、chunk 顺序或边界处理出错，只能通过完整母带统一 ASR 发现。
- 不能只看全局 `matched_script_ratio`。必须检查逐 turn 覆盖率、连续低覆盖区间、长脚本缺口、长 ASR-only 片段和明显短句循环。
- 如果发现某个 turn 或连续区间缺失、乱序、重复或被异常压缩，报告必须定位到 `turn_index`、`chunk_id`、文本片段和建议修复方式。
- 本节点只诊断，不自动修复。定向修复策略通常是重跑对应 VibeVoice chunk，或局部 patch 该 chunk 后重新执行 `05 final audio assembly -> 06 -> 06b -> 06c -> 07 -> 08 -> 09`。

通过条件：

```text
audio-transcript-integrity-result.json exists
status == PASS
global matched_script_ratio >= 0.95
no long turn has matched_char_ratio below threshold
no short turn is almost missing
no unmatched script run exceeds threshold
no obvious repeated phrase loop in ASR transcript
repair_targets is empty
```

如果 06b 失败，不得进入 06c 字幕时间轴、07 字幕、08 视频合成、10 B 站 metadata 或 11 投稿。不要用字幕阶段或视频阶段去掩盖音频缺段问题。

### 06c Audio Timeline Alignment

只有 06b `status == PASS` 后，才允许用同一份完整音频 ASR 生成字幕时间轴：

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/build_dialogue_timeline_from_asr.py \
  --project-dir <run_dir> \
  --asr-json <run_dir>/audio/asr_alignment.json

python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/validate_dialogue_timeline.py \
  --project-dir <run_dir>

/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/detect_turn_boundary_artifacts.py \
  --project-dir <run_dir>
```

输出：

```text
audio/dialogue_timeline.json
audio/alignment_report.md
audio/audio_artifact_qa.json
audio/audio_artifact_qa_report.md
06c-audio-timeline-alignment/dialogue_timeline.json
06c-audio-timeline-alignment/alignment_report.md
06c-audio-timeline-alignment/audio_artifact_qa.json
06c-audio-timeline-alignment/audio_artifact_qa_report.md
```

不要用 chunk 局部时间、turn 字数比例或 VibeVoice 进度猜字幕时间。字幕只认通过 06b 后由完整音频 ASR 生成的最终 `dialogue_timeline.json`。

### 07 Subtitles

使用：

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/SKILL.md
```

输出：

```text
07-subtitles/final_subtitles.srt
07-subtitles/final_subtitles.ass
07-subtitles/subtitle_manifest.json
07-subtitles/subtitle_alignment_report.md
```

字幕要求：

- 基于最终音频 ASR/forced alignment。
- 字幕文本不得重新引入 04c 已禁止的具体姓名、中国台湾/中国香港简称、中国台湾被称为国家、不规范英文/中文称谓、涉疆/宗教压迫高敏表达或意识形态对抗表达。字幕生成后必须复跑 04c 文本合规审核，再进入 08 视频合成。
- 不显示 speaker 标签。
- 不显示句号。
- 不做原视频硬锚点同步。
- 字幕不系统性晚于语音。

脚本若默认写入 `video/final_subtitles.srt`、`video/final_subtitles.ass`、`video/subtitle_manifest.json`，保留根级文件，并在 `07-subtitles/` 下复制一份或写 manifest 引用。

### 08 Source Video Revoice

正式目标视频：

```text
08-source-video-revoice/final_video.mp4
08-source-video-revoice/audio/final_podcast.wav
08-source-video-revoice/subtitles/final_subtitles.srt
08-source-video-revoice/screenshots/opening.png
08-source-video-revoice/screenshots/middle.png
08-source-video-revoice/screenshots/end.png
08-source-video-revoice/render_manifest.json
08-source-video-revoice/render_report.md
```

画面策略：

- 默认使用 `02-source-capture/youtube-media/source.mp4` 的视频流，静音源视频原音，替换为 `audio/final_podcast.wav`。
- 默认 `playback_speed=1.0`；播客流程不得继承旧讲解视频 agent 的 `1.15x` 强制加速规则，除非用户明确要求。
- 正式 B 站交付默认产出 `source_video_revoice_burned_subtitles`、`source_video_revoice_episode_segment_burned_subtitles` 或 `source_video_revoice_burned_subtitles_trim_to_audio_duration` 版本，并把该版本同步为根级 `video/final_video.mp4`。该版本底层画面来自源视频，但因为字幕 overlay 需要重编码，不再宣称“画面一模一样”。
- 严格保真例外 `visual_mode=source_video_revoice_strict`：只有用户明确要求“画面一模一样”“不要硬字幕”或“只要 sidecar 字幕”时才允许，必须 `-map 0:v:0 -c:v copy` 保留源视频画面流，不烧录字幕；中文字幕作为 sidecar `.srt`，可另行提供软字幕或 B 站字幕文件，且 `render_manifest.json.subtitle_delivery_policy` 必须记录 `sidecar_user_requested_no_burn_subtitles`。
- 硬字幕必须使用 07 生成的 `video/final_subtitles.ass`，不得现场按字数估算字幕时间。字幕样式沿用文章转视频链路：4K 坐标、`NotoSansCJKsc-Bold`、字号 96、底部安全区、只显示台词、不显示 Speaker 标签。
- 不做逐句原画面同步；中文音频和原视频内容顺序必须来自同一完整翻译稿。若中文音频比源视频短，正式生产不得静音空跑很长尾巴，应回到 03/04/05 调整翻译密度、语速或分块；只有小于 2 秒的差异可补静音。若中文音频比源视频长，正式生产不得截断内容或黑屏延展，应回到上游处理。
- 临时试听样片可以用 `--source-start-sec` 和 `--match-audio-duration` 截取源视频片段展示“原视频画面 + 中文音频”效果，但必须在 manifest 中标记 `review_sample=true`，不得写入正式历史。

默认运行：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_source_video_revoice.py \
  --run-dir <run_dir> \
  --force
```

上面的默认命令会烧录字幕。只有用户明确要求无硬字幕时，才可传 `--no-burn-subtitles`：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_source_video_revoice.py \
  --run-dir <run_dir> \
  --no-burn-subtitles \
  --force
```

Series episode 运行时，`run_source_video_revoice.py` 必须优先读取当前 episode 的 `episode_manifest.json.source_episode_video`，也就是 04b 已按语义区间从原视频裁出的 `04b-source-video-segment/source_episode.mp4`。最终子任务使用这个子视频画面来替换音轨；如果该文件缺失，才允许读取 `episode_manifest.json.source_start_sec` 从父源视频现场裁一段作为修复路径，这不是 `review_sample`。manifest 必须记录：

```json
{
  "visual_mode": "source_video_revoice_episode_segment_burned_subtitles",
  "series_episode": true,
  "episode_index": 1,
  "source_start_sec": 123.0,
  "source_episode_video_used": true,
  "subtitle_mode": "burned_ass",
  "subtitle_delivery_policy": "burned_subtitles_default",
  "target_duration_sec": 1800.0
}
```

如果用户此前明确要求“后半部分直接裁剪掉，我们不需要一一对应”，保留 `--match-audio-duration`，使源视频画面从开头裁到中文音频结束点：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_source_video_revoice.py \
  --run-dir <run_dir> \
  --match-audio-duration \
  --burn-subtitles \
  --force
```

硬字幕模式不依赖 FFmpeg `subtitles` / `ass` filter；脚本用 Pillow 按 `video/subtitle_manifest.json` 生成透明字幕层，再用 FFmpeg `overlay` 叠到源视频上。若当前 FFmpeg 没有 libass，这不是阻塞。

若需要保留完整源视频长度而不是裁到中文音频，去掉 `--match-audio-duration`，但不得让长尾静音成为正式交付。

合成后同步写出或软链：

```text
video/final_video.mp4
video/render_manifest.json
video/render_report.md
```

每次最终渲染或重渲染后，必须从最终 `video/final_video.mp4`
重新抽取 opening / middle / end 三张截图，并让
`render_manifest.json.screenshots` 指向这三张最终视频截图。若因为封面文字、
字幕安全区或 overlay 问题做了二次重渲染，旧截图必须覆盖或标记为
`pre_fix_obsolete`，不能继续作为 QA 证据。严格保真模式截图 QA 只确认源视频画面来自最终文件；硬字幕模式还必须确认字幕安全区和字形完整。

Legacy/debug：`scripts/run_static_video.py` 和 `08-static-video/` 只用于试听样片、上游音频验证或显式降级，不是正式目标交付节点。

### 09 Final QA

输出：

```text
09-final-qa/final-qa-report.md
09-final-qa/final-qa-result.json
```

通过条件：

```text
best_video exists and has podcast + China evidence
source video downloaded at 02-source-capture/youtube-media/source.mp4 and ffprobe passes
source audio extracted at 02-source-capture/youtube-media/source.wav and ffprobe passes
02a-speaker-census/speaker_roster.json exists and status == frozen
02a speaker_roster speaker_count == 2 and voice_count == 2
if source_voice_prompts=required, 02b-source-voice-prompts/voice_prompt_manifest.json exists and status=pass
if source_voice_prompts=required, 02b-source-voice-prompts/voice_prompt_manifest.json references the current 02a speaker census roster
if voice_prompt_policy=qwen_chinese_required, 02c-qwen-vibevoice-prompts/voice_prompt_manifest.json exists and status=pass
if voice_prompt_policy=qwen_chinese_required, both Speaker 0 and Speaker 1 Chinese prompt wavs exist, are 24000 Hz mono pcm_s16le, are 5-30 seconds, and are registered in the VibeVoice voices directory
if voice_prompt_policy=qwen_chinese_required, source_language must not bypass 02c even when 02b English source reference exists
if voice_prompt_policy=source_chinese_direct, source_language must be zh and both 02b Speaker 0 and Speaker 1 reference wavs exist, are 24000 Hz mono pcm_s16le, and are at least 25 seconds
if source_voice_prompts=required, audio_manifest speaker_voices matches the selected 02c manifest, or the 02b manifest only when source_language=zh and voice_prompt_policy=source_chinese_direct
source media_manifest.json exists and records actual source video resolution, bitrate, selected format, available_max_height, selected_height, download_blocker, downgrade_reason, quality_downgrade_authorization, and redacted yt_dlp_auth_network status
if bot/auth retry was used, logs and manifest must not contain raw cookie values, cookie file contents, or proxy credentials
selected source video height is 2160 when available; if available_max_height >= 1440 but selected_height <= 1080, QA must FAIL unless quality_downgrade_authorization=user_confirmed
selected source audio is the original/default track when YouTube exposes multiple audio languages; selecting a non-original translated/dubbed track is a FAIL
720p/360p source material is not accepted for formal production and may only appear as frame-form QA evidence
source video frame QA exists with video_podcast_form=PASS
opening/middle/end source-video screenshots exist and show video podcast/interview visual evidence
video_title.txt exists and contains `<source_identity_label>：<translated_title_core>` where the prefix is a justified speaker/source identity, not a lazy platform/channel label
cover/cover_title.json exists and title_text equals video_title.txt
cover/cover_title.json title_source is youtube_original_title_translated_with_source_identity
cover/cover_title.json source_identity_label equals the prefix before `：`
cover/cover_title.json translated_title_core equals the title core after `：`
if episode_manifest.json exists, video_title.txt contains episode_manifest.series_title_prefix, episode_manifest.episode_order_marker and episode_manifest.episode_subtitle; cover/cover_title.json.video_title_text equals video_title.txt; cover/cover_title.json.title_text omits the episode marker; cover_title_omits_episode_index == true
cover/image_source_manifest.json records image_type=source_video_frame_background
cover/cover_4k.png exists and is 3840x2160
cover/cover_4k.png uses centered title layout
source transcript or ASR exists
source_transcript.zh.json and source_transcript.zh.md exist
if 03b-mainland-publish-safety exists, source_transcript.zh.safe.json, source_transcript.zh.safe.md, chapter_segments.safe.json, edit_decisions.json and safety_report.md exist, safety_report records status: PASS, and 04-podcast-script uses source: 03b-mainland-publish-safety/source_transcript.zh.safe.json
if 03b-mainland-publish-safety exists, script_report records content_coverage=mainland_publish_safety_edited; otherwise script_report records content_coverage=full_translation unless user explicitly authorized abridgement
04c-bilibili-text-compliance/text-compliance-review-result.json exists and status == PASS
04c text compliance summary.fail_findings == 0 and reviewed_files covers the current podcast_script.md, video_title.txt, cover/cover_title.json, audio/audio_manifest.json, video/subtitle_manifest.json, final_subtitles.srt and final_subtitles.ass when those files exist
chapter_segments.json or chapter_segments.safe.json exists and follows original source order
podcast_script.md exists and only uses Speaker 0/Speaker 1
source_transcript.zh.json, podcast_script.md, audio_manifest turns, final_subtitles.srt/ass and subtitle_manifest do not contain specific names of Chinese contemporary national leaders such as 习近平, Xi Jinping, Xi; foreign leader names are allowed when natural, and diplomatic fixed phrases should use smooth Chinese such as 中美领导人峰会
publishable text does not contain known Bilibili terminology violations such as mainland China/Mainland China, abbreviated 台湾/香港 instead of 中国台湾/中国香港, 中国台湾作为国家, 南京大屠杀纪念馆, 新疆维吾尔族自治区, or high-risk title/metadata amplification of sensitive ethnic/religious/government-oppression claims
when 03b is enabled, podcast_script.md, audio_manifest turns, final_subtitles.srt/ass and subtitle_manifest must not reintroduce phrases cut by 03b such as current Chinese leader + COVID policy decision criticism, current-politics comparisons to Mao/Cultural Revolution/Red Guards/MAGA, or party-state decision-capacity attacks
chunk_plan.json exists and no chunk exceeds hard limits
every chunk wav exists and ffprobe passes
final_podcast.wav exists and ffprobe passes
audio_manifest records audio_backend=vibevoice_chunked_dialogue
audio_manifest records speaker_voices and voice_prompt_manifest when original source voice prompts were used; qwen_chinese_required runs must point at 02c-qwen-vibevoice-prompts/voice_prompt_manifest.json
audio_manifest records chunk_count and chunk global time ranges
06b-audio-transcript-integrity/audio-transcript-integrity-result.json exists and status == PASS before subtitle alignment
06b audio transcript integrity matched_script_ratio >= 0.95 and repair_targets is empty
dialogue_timeline.json exists and validates
final_subtitles.srt and final_subtitles.ass exist
final_video.mp4 exists and ffprobe passes
render_manifest visual_mode explicitly marks burned subtitles / review sample / legacy static fallback; formal source-video Bilibili delivery defaults to burned subtitles
if episode_manifest.json exists, render_manifest visual_mode contains episode_segment and render_manifest.series_episode == true
unless user explicitly requested no burned subtitles, render_manifest subtitle_mode == burned_ass and visual_mode contains burned_subtitles
if render_manifest subtitle_mode != burned_ass, render_manifest subtitle_delivery_policy == sidecar_user_requested_no_burn_subtitles must exist and final QA must treat it as an explicit exception rather than the default path
render_manifest.json exists
render_manifest screenshots exist and were extracted after the last final_video render
formal source-video delivery burns subtitles into the video frames; opening/middle/end screenshots show subtitles are readable and do not obscure critical podcast faces or on-screen source text
QA confirms visual_sync=disabled_v1, so original-video visual anchors are intentionally out of scope
```

`smoke=true` dry-run QA 通过条件改为：

```text
overall_status == PASS_SMOKE
production_status == smoke_validation_only
VibeVoice dry-run artifact exists
audio_manifest generation_status == dry_run_not_synthesized
audio_manifest final_audio == null is allowed only in dry-run
06/07/08 each has a smoke manifest/report with skip_reason and expected_production_outputs
final-podcast-videos.json was not written
```

`expected_production_outputs` 在 smoke skip manifest/report 中必须是非空数组。例如 06 应列出 `dialogue_timeline.json`、`asr_alignment.json`，07 应列出 `final_subtitles.srt`、`final_subtitles.ass`，08 应列出 `final_video.mp4`、`render_manifest.json`。

`PASS_SMOKE` 不得触发历史写入。只有正式生产最终 QA 才能写入 `final-podcast-videos.json`。

建议人工/AI 抽查：

- 开头 2 分钟是否自然。
- 中段 2 分钟是否没有角色串音、长静音、明显错读。
- 结尾 2 分钟是否完整收束。
- 至少 5 个 speaker switch 是否自然。
- 字幕是否可读、没有明显大面积滞后。

只有最终 QA 通过，才写入 `final-podcast-videos.json`。

### 10 Bilibili Publish Metadata

最终视频和最终 QA 通过后，自动生成 B 站投稿 metadata。读取：

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-publish-metadata/SKILL.md
```

本节点替代文章播客的 `article-bilibili-publish-metadata`，不得复用外刊文章标签策略。标签必须服务于 YouTube 源视频/外网播客产品，例如：

```text
外网热议
海外视角
中国观察
国际观察
国际播客
中文配音
中国经济
财经解读
中美关系
贸易战
中国制造
供应链
```

运行：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-publish-metadata/scripts/generate_bilibili_publish_metadata.py \
  --run-dir <run_dir>
```

输出：

```text
bilibili_upload_metadata.json
publish_info.txt
10-bilibili-publish/publish_metadata_report.json
```

通过条件：

```text
bilibili_upload_metadata.json exists
publish_info.txt exists
10-bilibili-publish/publish_metadata_report.json exists
metadata.workflow == worldview-china-podcast-agent
metadata.title equals video_title.txt
metadata.video_path == video/final_video.mp4
metadata.cover_path == cover/cover_4k.png
metadata.tags has 8-10 unique video/podcast tags
metadata.tags does not contain article-only tags such as 外刊解读, 外刊精读, 英语学习, 英语听力 unless explicitly justified by source type
metadata.category == 知识
metadata.creation_declaration == 含AI生成内容
if episode_manifest.json exists, metadata.title equals the ordered episode title in video_title.txt, metadata.cover_title_text equals the unnumbered cover title, metadata.episode_index and metadata.episode_count match episode_manifest.json
if a schedule seed exists, metadata.scheduled_publish_at preserves it; in a series, episode N scheduled_publish_at must equal first episode scheduled_publish_at + (N-1) hours
04c-bilibili-text-compliance/text-compliance-review-result.json is rerun after metadata generation and status == PASS before upload
```

### 11 Bilibili Upload Publish

`10 Bilibili Publish Metadata` 通过后，自动触发本地 B 站投稿发布 Skill。读取：

```text
/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md
```

硬边界：

- 必须使用现有 `bilibili-video-upload-draft` Skill，不得在本总控 Skill 内手写 Chrome/Bilibili 自动化。
- 必须使用 `<run_dir>/bilibili_upload_metadata.json` 作为标题、简介、标签、分区、创作声明、视频路径和封面路径的 source of truth。
- 投稿 Skill 在上传、封面、字段和可选定时发布全部验证通过后，必须自动点击最终 `投稿`、`立即投稿`、`发布` 或等价最终提交按钮一次。
- 若 Chrome 扩展、登录态、本地文件权限或 B 站页面导致阻塞，必须写出 `bilibili_upload_draft_report.json` 和 `bilibili_upload_draft_report.md`，并把 `status=BLOCKED`、`blocker.code`、可操作下一步写清楚。

正式发布完成条件：

```text
bilibili_upload_draft_report.json exists
report.skill_name == bilibili-video-upload-draft
report.skill_instructions_read == true
report.status == SUBMITTED
report.final_submit_clicked == true, or report.submission_status == submitted, or report contains Bilibili page evidence such as 稿件投递成功 / 上传成功
report.video_upload_status == accepted when the upload skill records that field
report.cover_upload_status == accepted when the upload skill records that field
report.field_verification.title == matched when the upload skill records field verification
accepted_tags matches or reasonably explains Bilibili rejected/capped tags
```

`status=BLOCKED` 只表示上传节点写出了可诊断阻塞报告，不算测试通过，不算发布完成。阻塞报告必须包含 `blocker.code` 和 exact next step，但最终验收仍然是 FAIL / NEEDS_FIX，直到重新上传并得到 `SUBMITTED` 与最终提交证据。

### 12 Series Final QA

如果本轮启用了 `04b-series-episodes`，所有 episode 完成 09/10/11 后，必须在父 run 上运行系列最终门禁：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_series_final_qa.py \
  --run-dir <run_dir>
```

默认正式生产要求每个 episode 的 `bilibili_upload_draft_report.json.status == SUBMITTED`。只有调试或用户明确允许“上传阻塞也先验收机械链路”时，才可传 `--allow-blocked-upload`；该模式不得声称正式发布完成。

正式生产测试通过的硬标准是两项同时满足：

```text
1. 产出的每个 episode 视频质量没问题：09-final-qa/final-qa-result.json overall_status == PASS
2. 每个 episode 已完成 B 站投稿/发布动作：bilibili_upload_draft_report.json status == SUBMITTED，并且存在最终提交证据
```

最终提交证据包括新版上传报告的 `final_submit_clicked=true` 或 `submission_status=submitted`；旧版上传报告至少必须有 B 站页面返回的 `稿件投递成功` / `上传成功` 等成功证据。只有生成视频、metadata 或草稿页截图，都不能算通过。

通过条件：

```text
04b-series-episodes/series_manifest.json exists
series_manifest.serial_execution_required == true
series_manifest.parallel_execution_allowed == false
series_manifest.episode_order_marker_template exists and every episode_manifest.json uses the same template
episode indices are contiguous and sorted from 1
each episode video_title.txt contains the ordered marker recorded in episode_manifest.json, such as 第1集, EP01, or （一）
each episode order marker equals series_manifest.episode_order_marker_template formatted with that episode index
each episode cover_title.json.title_text omits the ordered marker
each episode cover_title.json.video_title_text equals video_title.txt
all episodes use the shared series cover background frame recorded in series_manifest.shared_cover_frame
each episode 09-final-qa/final-qa-result.json overall_status == PASS
each episode bilibili_upload_metadata.json title and episode_index match episode_manifest.json
if scheduled_publish_at exists, episode N time == episode 1 time + (N-1) hours
each episode bilibili_upload_draft_report.json status == SUBMITTED for formal completion
each episode bilibili_upload_draft_report.json contains final submit proof for formal completion
```

`12-series-final-qa` 通过后，父级大任务才可写入 `final-podcast-videos.json`。启用 series mode 时，不要把单个 episode 的 PASS 单独写入父级历史作为整个长播客完成。

## 开发验证纪律

修改本 skill 后，不要只靠主 agent 自评完成。必须：

1. 启动一个全新、`fork_context=false` 的执行子 agent，让它只根据本 skill 跑一个 fresh trial。试跑可以使用 `smoke=true`，但必须覆盖选题或指定 URL、脚本生成、chunk plan、至少一个 VibeVoice chunk 的 dry-run 或真实 smoke、QA 产物。
2. 执行子 agent 完成后，启动另一个全新、`fork_context=false` 的评估子 agent，只读检查执行产物和本 skill，输出 PASS / NEEDS_FIX / FAIL。
3. 如果评估不通过，修改本 skill 或相关节点规则，然后重复执行子 agent + 评估子 agent。
4. 如果某个节点反复失败，把该节点拆成独立节点测试，也必须使用一个执行子 agent 和一个评估子 agent。

评估通过前，不要声称 skill 完成。

## 最终回答

完成正式运行时，简洁列出：

- 选中源播客标题、频道、URL。
- 源视频 `source.mp4` 路径、实际分辨率和源视频画面 QA 结论。
- 若启用 series mode，列出 `04b-series-episodes/series_manifest.json`、episode 数量、每集标题、每集定时投稿时间、每集最终 MP4 和每集投稿状态。
- 中文标题 `video_title.txt` 路径。
- 封面图 `cover/cover_4k.png` 路径。
- 中文播客稿路径。
- chunk plan 路径和 chunk 数。
- 最终中文音频路径。
- 字幕路径。
- 最终 MP4 路径。
- QA 报告路径。
- B 站投稿 metadata `bilibili_upload_metadata.json` 路径和标签列表。
- B 站投稿发布报告 `bilibili_upload_draft_report.json` 路径，以及状态 `SUBMITTED` 或 `BLOCKED`。
- 是否写入 `final-podcast-videos.json`。

不要粘贴 API key、完整字幕、完整 manifest 或长日志。
