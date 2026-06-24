---
name: english-article-chinese-single-host-video
description: 将本地英文或中文外刊文章端到端制作成中文单人口播解释视频，并自动提交 B 站投稿。只接受本地文章文件路径；默认生成 single_host_script.md 与兼容镜像 podcast_script.md，不写 Speaker 0/Speaker 1 双人对话；使用 VibeVoice-1.5B 单 speaker 整篇连续 TTS、最终音频 ASR/forced alignment、PPT Master deck 章节图、对齐字幕、硬字幕 MP4，并调用 bilibili-video-upload-draft 上传视频、填写投稿信息、验证字段后点击最终提交按钮一次。适用于用户要“单人口播稿”“文章讲解视频”“不是双人播客”“把外刊文章讲清楚”的生产流程。
---

# 英文文章转中文单人口播视频

这是 `english-article-chinese-podcast-video` 的隔离单人版。原 Skill 不动；本 Skill 只服务单人口播解释视频。

输入只能是本地文章文件。不要处理 URL，不要主动联网抓网页。产出是一条中文单人讲解视频：单人口播稿、VibeVoice 单人音轨、ASR 对齐时间轴、PPT Master 章节视觉、中文字幕、最终 MP4、发布标题/封面，以及 B 站投稿提交报告。

## 总体变化

和旧双人播客版相比，本 Skill 只改核心表达层和音频输入层：

- 文稿从 `Speaker 0` / `Speaker 1` 对话改为单人解释型口播。
- 正式文稿是 `single_host_script.md`。
- 为了兼容原来的标题、封面、PPT 和视频合成阶段，同时写一个同内容镜像 `podcast_script.md`；这个文件不再代表双人播客，只是后段流程的兼容输入名。
- VibeVoice 输入由音频子 Skill 把单人口播稿拆成多个 `Speaker 0:` 段落，并只绑定一个声音。
- 后续 ASR、章节时间线、字幕、视频合成仍使用最终 `audio/final_podcast.wav` 和 `audio/dialogue_timeline.json`，不要用字数估算。

## 默认架构

```text
source article
-> planning/article_brief.json + context_cards.json + episode_outline.json
-> single_host_script.md + podcast_script.md compatibility mirror
-> title / cover / PPT Master deck / VibeVoice 单人 TTS 并行
-> audio/final_podcast.wav
-> ASR/forced alignment -> audio/dialogue_timeline.json
-> bind chapter_semantics.json to dialogue_timeline.json
-> subtitles
-> final_video.mp4
-> subtitle timeline QA
-> Bilibili upload and final submit in real Chrome
```

## 强制子 Skill 顺序

默认按下面依赖图执行。每个阶段没过 gate 就停在该阶段修复。

1. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-episode-planning/SKILL.md`
   - 以 `mode=single_host_explainer` 调用共享策划层：输出 `planning/article_brief.json`、`context_cards.json`、`episode_profile.json`、`speaker_profile.json` 和 `episode_outline.json`。这些文件只作为事实和结构素材，不强制输出双人对话。

2. `/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-explainer-script/SKILL.md`
   - 读取原文和 planning artifacts，输出 `single_host_script.md`、`podcast_script.md` 兼容镜像、`planning/single_host_explainer_plan.json` 和 `planning/single_host_script_generation_report.md`。
   - 默认使用“中文生活经验开场、现象反差、外刊命名、纠偏、主问题、核心变量组、逐变量机制拆解、约束/代价、大判断收束”的解释型主模板。

`single_host_script.md` 定稿后，可以并行启动 PPT Master 章节视觉阶段；不要等音频时间轴。

3A. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-visuals/SKILL.md`
   - 读取兼容镜像 `podcast_script.md`，调用 `ppt-master-article-deck` 生成正常 PPT Master deck/PPTX，再调用 `ppt-master-deck-video-visuals` 输出 `chapter_visuals/chapter_semantics.json` 和 `chapter_XX.png`。
   - 本阶段不负责秒级时间轴。

同时继续标题、封面和音频主线：

3B. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-title-writing/SKILL.md`
   - 读取 `source/article.txt`、`source/source_metadata.json` 和兼容镜像 `podcast_script.md`，生成 `cover/cover_title.json` 和 `video_title.txt`。

4. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-cover-image-generation/SKILL.md`
   - 沿用原封面底图规则：用 AI 图像生成无字底图 `cover/background_raw.png`，标准化为 `cover/background.png`。

5. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/SKILL.md`
   - 沿用原本地叠字规则，输出 `cover/cover_4k.png`。

6. `/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio/SKILL.md`
   - 读取 `single_host_script.md`，抽取正文，拆成单人 `Speaker 0:` 段落。
   - 写出 `audio/vibevoice_dialogue_display.txt` 和 TTS 归一化后的 `audio/vibevoice_dialogue.txt`。
   - 使用本地 VibeVoice-1.5B 一次性生成 `audio/final_podcast.wav`，默认使用男声 `BowenClean`；如用户明确选择，可切换为从 B 站“懂夕夕”配音视频截取并试听通过的男声 `译制腔`。

7. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/SKILL.md`
   - 对 `audio/final_podcast.wav` 做 ASR/forced alignment，输出 `audio/dialogue_timeline.json`。
   - 单人模式不要求 speaker switch 抽听；改为抽听 opening/middle/end 和至少 5 个段落边界。

8. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-timeline-binding/SKILL.md`
   - 等 `chapter_visuals/chapter_semantics.json` 和 `audio/dialogue_timeline.json` 都存在后，语义绑定 slide 与口播 turn，生成 `chapter_visuals/chapter_plan.json`。

9. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/SKILL.md`
   - 用 `audio/dialogue_timeline.json` 生成并校准 SRT/ASS 字幕。

10. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-static-video/SKILL.md`
   - 用已定稿音轨、章节画面、封面和字幕合成 MP4，生成 `publish_info.txt`、`bilibili_upload_metadata.json`、`planning/bilibili_tag_report.json` 和 `production_manifest.json`。

11. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-timeline-qa/SKILL.md`
   - 逐 cue/turn 验证字幕、ASR 时间轴、音频和最终视频时间线一致。

12. `/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md`
   - 字幕时间线 QA 通过后，读取本项目的 `bilibili_upload_metadata.json`，在用户已登录的真实 Chrome 会话中打开 B 站创作中心上传页，上传 `video/final_video.mp4` 和 `cover/cover_4k.png`，填写标题、简介、标签、分区、创作声明和可选定时发布时间，验证字段生效后点击最终提交按钮一次，并输出 `bilibili_upload_draft_report.json` 和 `bilibili_upload_draft_report.md`。如果当前 agent 缺少 `chrome:control-chrome`，返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED`，交给拥有 Chrome 工具面的上游 agent 继续调用投稿 skill。

本单人主线不包含旧 Qwen3 turn-level clone，也不包含双人 `article-podcast-vibevoice-audio`。如果用户以后要做双人实验，回到原 `english-article-chinese-podcast-video`，不要在本 Skill 里临时混用。

## B 站投稿集成

本 skill 是视频生产和 B 站投稿发布总控。它必须产出标准化的 `bilibili_upload_metadata.json`，然后把该 metadata 交给 `bilibili-video-upload-draft` 作为最后阶段执行。投稿阶段完成数据录入、文件上传、字段验证后，必须点击最终 `投稿`、`立即投稿`、`提交`、`发布` 或等价最终提交按钮一次。

当本 skill 在 worker/subagent 中运行时，要先区分“视频生产能力”和“真实 Chrome 控制能力”。如果当前 agent 没有 `chrome:control-chrome` 工具面，但上游主控可能拥有该工具面，本 skill 必须在字幕时间线 QA 通过、metadata 写好、最终视频和 QA 完成后返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED`，并记录项目目录、final video、cover、metadata、QA 路径；不得把这种情况写成 `CHROME_EXTENSION_UNAVAILABLE`。真正的 B 站上传仍必须由拥有 `chrome:control-chrome` 的 agent 直接调用 `bilibili-video-upload-draft`，不能由父级手写浏览器脚本替代。

Chrome-capable agent 继续投稿 Gate 时，必须使用 Chrome 插件 `control-chrome` 的真实 Chrome Extension 路线，也就是 `agent.browsers.get("extension")`；不得用 Browser 插件 `control-in-app-browser` 的 `agent.browsers.get("iab")` 代替。

边界：

- `english-article-chinese-single-host-video` 负责生成 `video/final_video.mp4`、`cover/cover_4k.png`、`video_title.txt`、`publish_info.txt`、`bilibili_upload_metadata.json`。
- `bilibili_upload_metadata.json` 包含标题、简介、标签、固定分区 `知识`、固定创作声明 `含AI生成内容`、视频/封面相对路径和可选 `scheduled_publish_at`。
- 本通用视频 skill 不自行决定定时发布时间，默认 `scheduled_publish_at=null`；如果上游 orchestration 提供 `scheduled_publish_at`、`scheduled_publish_timezone` 和 `schedule_source`，必须在调用投稿发布前写入并重新验证 `bilibili_upload_metadata.json`。
- 如果上游传入的是 11:00/17:00 daily slot，本 skill 只透传排期；投稿阶段由 `bilibili-video-upload-draft` 在真实上传时再次归一化：尚未到达则保持原时间，已经到达或超过则顺延到下一天同一 slot。
- `bilibili-video-upload-draft` 是本 pipeline 的强制最终阶段。Gate 只能通过直接调用 `/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md` 完成。不得在本 skill 中手写 B 站 Chrome/Playwright 上传逻辑，不得用 `node_repl`、Chrome snippets、`locator.fill(input[type=file])` 或自制脚本替代投稿 skill。
- `bilibili_upload_draft_report.json` 必须由 `bilibili-video-upload-draft` 产出，并包含 `skill_name="bilibili-video-upload-draft"`、`skill_path`、`skill_invocation="direct"`、`skill_instructions_read=true`。缺少这些字段时，投稿 Gate 视为未执行投稿 skill，即使文件存在也不合格。
- 如果当前 agent 无法调用投稿 skill 但已完成视频和 metadata，优先返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED`，交给拥有 `chrome:control-chrome` 的上游 agent 继续调用投稿 skill；不得自行打开 B 站页试错，也不得手写 `bilibili_upload_draft_report.json` 伪装为投稿 skill 输出。只有确认当前调用链没有可用 Chrome 工具面，或投稿 skill 直接执行后阻塞，状态才是 `VIDEO_COMPLETE_UPLOAD_BLOCKED`。
- 成功提交时，投稿阶段必须留下 `bilibili_upload_draft_report.json` 和 `bilibili_upload_draft_report.md`，记录 live tab/audit 状态、已接受字段、已接受标签、是否设置定时发布、封面预览是否变更、`final_submit_clicked=true`、`submission_status=submitted` 以及提交证据。

## 输入前提

用户必须提供本地文章文件路径。

检查：

- 文件存在。
- 文件可读。
- 能抽取文章正文。

支持常见本地文件：`.txt`、`.md`、`.docx`、`.pdf`、`.html`。抽取后保存为 `<project>/source/article.txt`，并保存 `<project>/source/source_metadata.json`。如果文件内有图片素材，放入 `<project>/source/images/`。

不要联网补来源，不要从文件名强猜来源。`source_metadata.json` 只记录本地文件明确可见的信息，例如 `publication`、`article_title`、`author`、`published_date`、`source_url`。如果 publication 是英文，面向观众的文本必须使用中文来源名，例如 `Foreign Policy` 写作 `外交政策`，`The Economist` 写作 `经济学人`，`Bloomberg` 写作 `彭博社`。

## 项目目录

固定输出根目录：

```text
/Volumes/GT34/english_aircle_to_video
```

为每次正式运行创建独立项目目录。目录名必须包含时间戳，确保同一篇文章重复验收时也不会复用旧半成品：

```text
/Volumes/GT34/english_aircle_to_video/<article_slug>_<YYYYMMDD_HHMMSS>_single_host_video/
  source/
    article.txt
    source_metadata.json
    fact_notes.md
    images/
  planning/
    article_brief.json
    context_research_plan.json
    context_cards.json
    episode_profile.json
    speaker_profile.json
    episode_outline.json
    planning_report.md
    single_host_explainer_plan.json
    single_host_script_generation_report.md
    bilibili_tag_report.json
  single_host_script.md
  podcast_script.md
  audio/
    vibevoice_dialogue_display.txt
    vibevoice_dialogue.txt
    tts_normalization_report.md
    vibevoice_raw/
    final_podcast.wav
    final_podcast_preview.mp3
    final_podcast_playback.m4a
    audio_manifest.json
    playback_audio_manifest.json
    asr_alignment.json
    dialogue_timeline.json
    alignment_report.md
    audio_artifact_qa.json
    audio_artifact_qa_report.md
  cover/
    background.png
    background_raw.png
    cover_title.json
    visual_subject.json
    image_source_manifest.json
    cover_4k.png
  chapter_visuals/
    template_selection.json
    chapter_semantics.json
    chapter_turn_mapping.json
    chapter_plan.json
    chapter_01.png
    chapter_02.png
    ...
  video/
    final_subtitles.srt
    final_subtitles.ass
    subtitle_manifest.json
    subtitle_alignment_report.md
    visual_base_1x.mp4
    final_video.mp4
    render_manifest.json
    render_report.md
    subtitle_timeline_qa.json
    subtitle_timeline_qa_report.md
  video_title.txt
  publish_info.txt
  bilibili_upload_metadata.json
  bilibili_upload_draft_report.json
  bilibili_upload_draft_report.md
  production_manifest.json
  qa_report.md
```

项目目录创建规则：

- 不要把 `<article_slug>_single_host_video` 当作可复用固定目录。
- 每次从本地文章文件启动本 skill，都必须新建一个当前时间戳目录。
- 如果候选目录已经存在，必须追加短随机后缀或重新取当前时间，直到得到一个不存在的新目录。
- 新目录创建后，只允许把输入文章和输入文件内明确可见的素材复制进 `source/`；不得复制任何历史项目的 `planning/`、`single_host_script.md`、`podcast_script.md`、`audio/`、`cover/`、`chapter_visuals/`、`video/`、`publish_info.txt`、`bilibili_upload_metadata.json`、QA report 或 manifest。
- 做独立评测或子 agent 验证时，发现目标目录不是本次新建，必须停止并报告 `BLOCKED_REUSED_EXISTING_PROJECT_DIR`，不能继续跑。

## Gate 总表

```text
Input:
  source article file exists and is readable

Gate 1 Planning:
  planning/article_brief.json exists
  planning/context_cards.json exists
  planning/episode_outline.json exists
  facts, glossary and do_not_invent are usable as boundaries

Gate 2 Single Host Script:
  single_host_script.md exists
  podcast_script.md exists as compatibility mirror
  planning/single_host_explainer_plan.json exists
  planning/single_host_script_generation_report.md exists
  single_host_script.md has no Speaker 0/Speaker 1 dialogue labels in the body
  opening starts from viewer hook or Chinese life scene, not "今天我们来读一篇文章"
  main question appears early
  default explanatory articles name the driver set early
  facts stay within source/planning boundaries

Gate 3 Title/Cover/PPT:
  cover/cover_title.json exists
  video_title.txt exists
  cover/background.png and cover/cover_4k.png exist when cover stage is requested
  chapter_visuals/chapter_semantics.json and chapter_XX.png exist when PPT stage is requested

Gate 4 Single Host VibeVoice:
  audio/vibevoice_dialogue.txt exists and contains only Speaker 0 lines
  audio/vibevoice_dialogue_display.txt exists and contains only Speaker 0 lines
  audio/audio_manifest.json records audio_backend=vibevoice_longform and voice_mode=single_host
  audio/audio_manifest.json turns record text and tts_text
  audio/final_podcast.wav exists and ffprobe passes
  audio/final_podcast_preview.mp3 and audio/final_podcast_playback.m4a exist

Gate 5 Audio Timeline:
  audio/asr_alignment.json exists
  audio/dialogue_timeline.json exists
  audio/alignment_report.md exists
  all script turns are represented once in dialogue_timeline.turns
  cue and turn times are monotonic and within audio duration
  ASR/script matched_script_ratio >= 0.95
  no script tail is interpolated or compressed into the final seconds
  no run of more than 1 trailing low-confidence turn
  long turns/cues have plausible duration for their Chinese text length
  opening/middle/end and at least 5 paragraph boundaries are spot checked

Gate 6 Subtitle And Video:
  video/final_subtitles.srt and video/final_subtitles.ass exist
  video/final_video.mp4 exists and ffprobe passes
  video uses AAC audio derived from audio/final_podcast.wav
  render_manifest records playback_speed_factor=1.0
  subtitle timeline QA status is PASS

Gate 7 Bilibili Upload Publish:
  /Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md was read and followed
  if this agent lacks chrome:control-chrome but video/metadata/QA are complete, status may be UPLOAD_READY_CHROME_HANDOFF_REQUIRED and the parent agent must run this same Gate directly
  the upload stage was executed by bilibili-video-upload-draft itself, not by parent-skill ad hoc Chrome/Playwright code
  bilibili_upload_metadata.json exists and has schema_version=bilibili_upload_metadata.v1
  planning/bilibili_tag_report.json exists and records tag_sources for the accepted tags
  real user Google Chrome is used through Chrome Extension / chrome:control-chrome
  final submit/post button is clicked exactly once after verification
  bilibili_upload_draft_report.json exists
  bilibili_upload_draft_report.md exists
  bilibili_upload_draft_report.json records skill_name=bilibili-video-upload-draft, skill_path=/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md, skill_invocation=direct, skill_instructions_read=true
  bilibili_upload_draft_report.json records status SUBMITTED or BLOCKED, tab/audit evidence, field verification, accepted tags, final_submit_clicked=true when submitted, submission_status=submitted when submitted, blocker if any
```

## 不可变规则

- 不要把单人口播稿写成双人对话。
- `single_host_script.md` 是正式文稿；`podcast_script.md` 只是兼容镜像。
- 默认正式音频 backend 是 VibeVoice long-form single pass；不要按段生成再拼接。
- VibeVoice 单人输入仍使用 `Speaker 0:` 标签，这是 VibeVoice TXT 格式要求，不代表双人播客。
- 字幕和章节时间轴必须使用最终音频 ASR/forced alignment 得到的 `audio/dialogue_timeline.json`。
- `audio/final_podcast.wav` 是内部母带、ASR 对齐源和视频合成源；人工试听默认给 `audio/final_podcast_preview.mp3`。
- 不得用 MP3/M4A 作为 ASR、字幕或章节时间轴源。
- 如果 `single_host_script.md` 变化，标题、音频、ASR 时间轴、字幕、封面、PPT slide 语义、章节时间线绑定和视频全部失效，必须重做。
- 面向观众的衍生内容使用中文专名和中文来源名，不要让 raw English publication 出现在口播、字幕或封面标题里。
- 最终视频必须为 1.0 倍正常速度。
- 字幕时间线 QA 通过后必须调用 `bilibili-video-upload-draft` 作为最终阶段，或在当前 agent 缺少 `chrome:control-chrome` 时返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED` 给拥有 Chrome 工具面的上游 agent。除非用户在当前请求中明确说“只生成视频、不打开 B 站上传页”，否则不要停在 `bilibili_upload_metadata.json`。
- 调用 `bilibili-video-upload-draft` 是强制边界，不是建议。不得在本 skill 中用临时 Chrome JS、`node_repl` 代码、直接 DOM 操作或自制脚本替代投稿 skill；不得手写投稿 report。
- B 站投稿发布必须使用用户真实 Chrome 登录态，通过 Chrome Extension / `chrome:control-chrome` 控制；不得用 in-app browser、CDP、Playwright 新 profile 或临时 Chrome profile。
- B 站投稿阶段必须在字段验证通过后点击最终提交按钮一次；成功状态是 `SUBMITTED`。
- 如果视频完成但 B 站投稿发布被环境阻塞，保留最终视频、metadata 和投稿 report，状态使用 `VIDEO_COMPLETE_UPLOAD_BLOCKED`，不要重跑视频生产。

## 最终回复

全部 gate 通过时列出绝对路径：

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
