---
name: english-article-chinese-podcast-video
description: 将本地英文文章文件端到端制作成中文双人播客视频，并自动提交 B 站投稿。只接受本地文章文件路径；默认使用 Speaker 0/Speaker 1 文稿、VibeVoice-1.5B 整篇连续 TTS、最终音频 ASR/forced alignment、PPT Master deck 图片与语义 sidecar、章节图时间线绑定、对齐字幕、硬字幕 MP4、逐句时间线 QA，最后调用 bilibili-video-upload-draft 在用户真实 Chrome 中打开 B 站投稿页、上传视频/封面、填写投稿信息、验证字段并点击最终提交按钮一次。旧 Qwen3 按回合 TTS 仅作为用户明确要求时的 legacy fallback。
---

# 英文文章转中文播客视频

这是正式生产总控。输入只能是本地文章文件；不要处理 URL，不要主动联网抓网页。产出是一个可发布并已提交到 B 站审核队列的中文双人播客视频：`Speaker 0` 女主持、`Speaker 1` 男分析者、外刊解读式封面/发布标题、VibeVoice 连续播客音轨、最终音频 ASR 对齐时间轴、4K 大字封面、PPT Master deck 图片、对齐中文字幕、最终 MP4、逐句时间线 QA，以及 B 站投稿提交报告。

## 默认架构

正式主线是：

```text
source article
-> planning/article_brief.json + context_cards.json + episode_outline.json
-> podcast_script.md with Speaker 0/Speaker 1
-> podcast script polish QA
-> cover_title.json + video_title.txt
-> cover/background.png first layer
-> cover/cover_4k.png fixed text composition
-> in parallel after podcast_script.md is final:
   A) normal PPT Master deck -> deck video images + chapter_semantics.json
   B) title/cover + VibeVoice TTS + ASR/forced alignment
-> dialogue_timeline.json
-> turn-boundary artifact QA + AI review when needed
-> bind chapter_semantics.json to dialogue_timeline.json -> final chapter_plan.json
-> subtitles
-> precompose chapter visuals with wipe_with_shadow transitions into visual_base_1x.mp4
-> final_video.mp4
-> subtitle timeline QA
-> Bilibili upload and final submit in real Chrome
```

不要把 VibeVoice 音频重新拆成旧 Qwen `draft-turns` 工作流。字幕和最终章节时间轴需要的是最终音频的真实时间轴，不是逐回合 TTS 缓存；PPT Master deck 图片资产可先由定稿播客稿并行生成。

## 产物独立性原则

每次视频生产都必须从本轮输入独立生成全部产物。允许复用通用工具、skill、模板目录、字体、模型和缓存；不得复用任何历史任务的文章包、正文、Markdown、PPT、章节图、封面、音频、字幕、视频、manifest 或其他成品。只有用户在当前请求中明确指定某个文件作为本轮输入时，才可以读取该文件。

## 强制子 Skill 顺序与并行

默认按下面依赖图调用本地 skill。每个阶段没过 gate 就停在该阶段修复，不进入依赖它的下一阶段。

1. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-episode-planning/SKILL.md`
   - 以 `mode=dialogue_podcast` 调用共享策划层。输入本地文章正文，输出 `planning/article_brief.json`、`context_cards.json`、`episode_profile.json`、`speaker_profile.json` 和 `episode_outline.json`。这是节目导演层，不写正文稿。
2. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-chinese-podcast-script/SKILL.md`
   - 读取 planning artifacts，按 segment 输出 `podcast_script.md`，正文只使用 `Speaker 0:` / `Speaker 1:`。
3. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-script-polish-qa/SKILL.md`
   - 对 `podcast_script.md` 做播客感润色、口语化、来源露出控制和事实边界 QA，输出最终 `podcast_script.md` 和 `planning/polish_report.md`。

`podcast_script.md` 定稿后，可以并行启动 PPT Master deck 图片资产阶段；不要等音频时间轴：

4A. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-visuals/SKILL.md`
   - 读取最终 `podcast_script.md` 和可用 planning 摘要，先在默认候选模板中自动选择最适合文章气质的一套 PPT Master deck template，再调用 `ppt-master-article-deck` 正常生成 PPT Master deck/PPTX，最后调用 `ppt-master-deck-video-visuals` 将该 deck 项目后处理为 `chapter_visuals/chapter_semantics.json` 和 `chapter_XX.png` 序列。本阶段不负责秒级时间轴。

同时继续标题、封面和音频主线：

4B. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-title-writing/SKILL.md`
   - 基于 `source/article.txt`、`source/source_metadata.json` 和 `podcast_script.md`，生成封面大字 `cover/cover_title.json` 和发布标题 `video_title.txt`。
5. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-cover-image-generation/SKILL.md`
   - 读取文章、文稿和 `cover/cover_title.json`，必须使用 AI 图像生成工具生成完整无字底图 `cover/background_raw.png`，右侧有主体、左侧留标题区，再只做等比裁切标准化为 `cover/background.png`。严禁用 Pillow、SVG、Canvas、PPT、地图/轨迹图或任何本地程序化绘图兜底生成底图；AI 图像生成不可用时停止在封面阶段。
6. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/SKILL.md`
   - 读取 `cover/background.png` 和 `cover/cover_title.json`，用固定字体、固定位置、固定颜色规则本地叠字，输出 `cover/cover_4k.png`。
7. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/SKILL.md`
   - 先把 `Speaker 0/1` 文稿拆成观众显示稿 `audio/vibevoice_dialogue_display.txt` 和 TTS 归一化朗读稿 `audio/vibevoice_dialogue.txt`，再用本地 VibeVoice-1.5B 一次性生成 `audio/final_podcast.wav`。
8. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/SKILL.md`
   - 对 `audio/final_podcast.wav` 做 ASR/forced alignment，输出 `audio/dialogue_timeline.json`，并运行 turn 边界伪声检测；若检测状态为 `NEEDS_AI_REVIEW`，必须完成 AI 复核后再进入下一阶段。
9. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-timeline-binding/SKILL.md`
   - 等 `chapter_visuals/chapter_semantics.json` 和 `audio/dialogue_timeline.json` 都存在后，语义绑定每张 PPT slide image 的 `start_turn/end_turn`，再用确定性脚本生成连续秒级 `chapter_visuals/chapter_plan.json`。
10. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/SKILL.md`
   - 用 `audio/dialogue_timeline.json` 生成并校准 SRT/ASS 字幕，确保字幕同时或略早于语音。
11. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-static-video/SKILL.md`
   - 用已定稿音轨、章节画面、固定 `wipe_with_shadow` 章节转场、封面和字幕合成 MP4，使用已定稿 `video_title.txt` 生成 `publish_info.txt`，调用 `article-bilibili-publish-metadata` 生成 `bilibili_upload_metadata.json` 和 `planning/bilibili_tag_report.json`，并完成总 QA。
12. `/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-timeline-qa/SKILL.md`
   - 逐 cue/turn 验证字幕、ASR 时间轴、音频和最终视频时间线是否一致；未通过就回到音频对齐、字幕或视频合成阶段修复。
13. `/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md`
   - 字幕时间线 QA 通过后，读取本项目的 `bilibili_upload_metadata.json`，在用户已登录的真实 Chrome 会话中打开 B 站创作中心上传页，上传 `video/final_video.mp4` 和 `cover/cover_4k.png`，填写标题、简介、标签、分区、创作声明和可选定时发布时间，验证字段生效后点击最终提交按钮一次，并输出 `bilibili_upload_draft_report.json` 和 `bilibili_upload_draft_report.md`。

旧 `article-podcast-voice-profile` 和 `article-podcast-cloned-audio` 只在用户明确要求 Qwen3 turn-level clone 时使用。

## B 站投稿集成

本 skill 是视频生产和 B 站投稿发布总控。它必须产出标准化的 `bilibili_upload_metadata.json`，然后把该 metadata 交给 `bilibili-video-upload-draft` 作为最后阶段执行。投稿阶段完成数据录入、文件上传、字段验证后，必须点击最终 `投稿`、`立即投稿`、`提交`、`发布` 或等价最终提交按钮一次。

当本 skill 在 worker/subagent 中运行时，要先区分“视频生产能力”和“真实 Chrome 控制能力”。如果当前 agent 没有 `chrome:control-chrome` 工具面，但上游主控可能拥有该工具面，本 skill 必须在 Gate 12 通过、metadata 写好、最终视频和 QA 完成后返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED`，并记录项目目录、final video、cover、metadata、QA 路径；不得把这种情况写成 `CHROME_EXTENSION_UNAVAILABLE`。真正的 B 站上传仍必须由拥有 `chrome:control-chrome` 的 agent 直接调用 `bilibili-video-upload-draft`，不能由父级手写浏览器脚本替代。

Chrome-capable agent 继续 Gate 13 时，必须使用 Chrome 插件 `control-chrome` 的真实 Chrome Extension 路线，也就是 `agent.browsers.get("extension")`；不得用 Browser 插件 `control-in-app-browser` 的 `agent.browsers.get("iab")` 代替。

边界：

- `english-article-chinese-podcast-video` 负责生成 `video/final_video.mp4`、`cover/cover_4k.png`、`video_title.txt`、`publish_info.txt`、`bilibili_upload_metadata.json`。
- `bilibili_upload_metadata.json` 包含标题、简介、标签、固定分区 `知识`、固定创作声明 `含AI生成内容`、视频/封面相对路径和可选 `scheduled_publish_at`。
- 本通用视频 skill 不自行决定定时发布时间，默认 `scheduled_publish_at=null`；如果上游 orchestration 提供 `scheduled_publish_at`、`scheduled_publish_timezone` 和 `schedule_source`，必须在调用投稿发布前写入并重新验证 `bilibili_upload_metadata.json`。
- Daily 总控根据选题模式计算 `scheduled_publish_at`，并把排期作为本 skill 的调用上下文传入；本 skill 在 Gate 12 通过后、Gate 13 上传前把该排期写入 metadata。Daily slot 必须是未来时间：当天 11:00/17:00 尚未到达则用当天，已经到达或超过则用下一天同一 slot。
- `bilibili-video-upload-draft` 是本 pipeline 的强制最终阶段。它负责在用户已登录的 Chrome 中打开新投稿页、上传视频和封面、填入 metadata、按投稿 skill 的动态 slot 规则配置外部传入的定时时间，验证后自动点击最终提交按钮一次。
- Gate 13 只能通过直接调用 `/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md` 完成。不得在本 skill 中手写 B 站 Chrome/Playwright 上传逻辑，不得用 `node_repl`、Chrome snippets、`locator.fill(input[type=file])` 或自制脚本替代投稿 skill。
- `bilibili_upload_draft_report.json` 必须由 `bilibili-video-upload-draft` 产出，并包含 `skill_name="bilibili-video-upload-draft"`、`skill_path`、`skill_invocation="direct"`、`skill_instructions_read=true`。缺少这些字段时，Gate 13 视为未执行投稿 skill，即使文件存在也不合格。
- 如果当前 agent 无法调用投稿 skill 但已完成视频和 metadata，优先返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED`，交给拥有 `chrome:control-chrome` 的上游 agent 继续调用投稿 skill；不得自行打开 B 站页试错，也不得手写 `bilibili_upload_draft_report.json` 伪装为投稿 skill 输出。只有确认当前调用链没有可用 Chrome 工具面，或投稿 skill 直接执行后阻塞，状态才是 `VIDEO_COMPLETE_UPLOAD_BLOCKED`。
- 如果 Chrome Extension 不可用、用户未登录、B 站页面不可达、文件上传权限缺失、非 daily slot 的精确定时发布时间已经过期，或同一上传字段连续失败三次，本 skill 不得把整轮标记为完全完成；状态应为 `VIDEO_COMPLETE_UPLOAD_BLOCKED`，保留最终视频和 metadata 路径，并记录具体上传 blocker 和下一步。11:00/17:00 daily slot 过期不应直接阻塞，应由投稿 skill 顺延到下一天同一 slot 并在 report 中记录。
- 成功提交时，投稿阶段必须留下 `bilibili_upload_draft_report.json` 和 `bilibili_upload_draft_report.md`，记录 live tab/audit 状态、已接受字段、已接受标签、是否设置定时发布、封面预览是否变更、`final_submit_clicked=true`、`submission_status=submitted` 以及提交证据。

## 输入前提

用户必须提供本地文章文件路径。

检查：

- 文件存在。
- 文件可读。
- 能抽取文章正文。

如果失败，停止并说明输入文件不可用。不要改用 URL 抓取，不要猜测文章内容。

支持常见本地文件：`.txt`、`.md`、`.docx`、`.pdf`、`.html`。抽取后保存为 `<project>/source/article.txt`，并保存 `<project>/source/source_metadata.json`。如果文件内有可用图片素材，放入 `<project>/source/images/`。

`source_metadata.json` 必须尽量记录可从本地文件明确看到的来源信息，例如 `publication`、`article_title`、`author`、`published_date`、`source_url`。不要联网补来源，不要从文件名强猜来源。后续发布标题、口播开头、字幕和章节图只能使用已确认来源；如果 publication 是英文，面向观众的文本必须使用中文来源名，例如 `Foreign Policy` 写作 `外交政策`，`Bloomberg` 写作 `彭博社`。

## 项目目录

固定输出根目录：

```text
/Volumes/GT34/english_aircle_to_video
```

为每篇文章创建独立项目目录：

```text
/Volumes/GT34/english_aircle_to_video/<article_slug>_podcast_video/
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
    script_generation_report.md
    polish_report.md
    bilibili_tag_report.json
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
    audio_artifact_ai_review.json
    artifact_candidates/
    audio_report.md
  cover/
    background.png
    background_raw.png
    cover_title.json
    visual_subject.json
    image_source_manifest.json
    cover_4k.png
  chapter_visuals/
    chapter_semantics.json
    chapter_turn_mapping.json
    chapter_plan.json
    chapter_timeline_binding_report.md
    chapter_visuals_contact_sheet.jpg
    chapter_01.png
    chapter_02.png
    ...
  video/
    final_subtitles.srt
    final_subtitles.ass
    subtitle_manifest.json
    subtitle_alignment_report.md
    subtitle-overlays/
    visual-clips/
    visual_concat.ffconcat
    visual_base_1x.mp4
    final_video_1x.mp4
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

## Gate 总表

```text
Input precondition:
  source article file exists and is readable

Gate 1 Episode Planning:
  planning/article_brief.json exists
  planning/context_research_plan.json exists
  planning/context_cards.json exists
  planning/episode_profile.json exists
  planning/speaker_profile.json exists
  planning/episode_outline.json exists
  article_brief records primary_subject and primary_subject_type
  article_brief records proper_noun_glossary for recurring people/places/projects/organisations
  context_cards contains usable subject_orientation
  episode_outline has 5-7 segments with source_facts, dialogue_moves and avoid
  episode_outline first two segments use subject_orientation or explain why not
  external context cards include source_urls

Gate 2 Script Draft:
  podcast_script.md exists
  planning/script_generation_report.md exists
  lint passes
  only Speaker 0/Speaker 1 turns in 正文
  Speaker 0 asks, redirects, and represents listener curiosity
  Speaker 1 explains mechanisms and judgments
  major background detours map to article facts or context_cards
  opening or first two content segments use subject_orientation when available
  recurring proper nouns follow article_brief.proper_noun_glossary when available
  script_hash recorded

Gate 3 Script Polish QA:
  planning/polish_report.md exists
  polish_report status is PASS
  opening mentions confirmed publication with Chinese source name when source_metadata confirms it
  after opening, article/source phrases are rare and purposeful
  host shows real confusion, mild friction or listener empathy across segments
  subject_orientation is used near the opening when available
  recurring proper nouns are localized for Chinese audience or replaced with role descriptors when exact Chinese characters are unverified
  no unsupported concrete facts remain
  script_hash recorded

Gate 4 Title:
  cover/cover_title.json exists
  cover_title.json records title_lines, highlight_text, core_conflict and title_rationale
  title_lines has 1-3 short lines and translates the article's core conflict, not merely the English title
  title_lines is plain text, with no color markup or layout syntax
  highlight_text is one continuous substring found in title_lines
  video_title.txt exists
  if article publication is visible in source metadata or script source line, video_title.txt starts with 《<中文来源名>》：
  video_title.txt is specific and contains at least two of object/conflict/consequence/counterintuitive point
  no unsupported clickbait words such as 真相/震惊/内幕/一文看懂

Gate 5 Cover Image:
  cover/background_raw.png exists
  cover/background.png exists
  cover/visual_subject.json exists
  cover/image_source_manifest.json exists
  cover/background.png is 3840x2160
  cover/background.png is a full-bleed AI background with right-side dominant subject and clean left title area
  cover/image_source_manifest.json proves background_raw.png was created by an AI image generation model/tool
  cover/image_source_manifest.json source/model_or_tool/image_type is not local_pillow_generated, procedural_generated, programmatic_generated, manual_composite, screenshot, ppt_export, map_diagram or chart_generated
  cover/visual_subject.json records strategy, style, image_prompt and negative_prompt
  cover/background.png has no readable stray text/logo/watermark
  cover/background.png is not a flat vector, infographic, chart, map diagram, abstract tech background or locally drawn placeholder
  if a real person image is used as reference, source/license/attribution are recorded
  if AI generated, prompt and negative_prompt are recorded

Gate 6 Cover Composition:
  cover/background.png exists
  cover/cover_title.json exists
  cover/image_source_manifest.json confirms AI-generated background provenance before local text overlay
  cover/cover_4k.png is 3840x2160
  cover title is burned into the image in large readable Chinese text
  cover title uses fixed font, fixed left position, white normal text and yellow highlight_text

Gate 7 VibeVoice Audio:
  audio/vibevoice_dialogue.txt exists and contains only Speaker 0/Speaker 1 lines
  audio/vibevoice_dialogue_display.txt exists and contains only Speaker 0/Speaker 1 lines
  audio/tts_normalization_report.md exists
  audio/vibevoice_dialogue.txt is TTS-normalized; audio/vibevoice_dialogue_display.txt preserves display text
  audio/final_podcast.wav exists and ffprobe passes
  audio/final_podcast.wav is the internal master and alignment source, not the default human audition file
  audio/final_podcast_preview.mp3 exists and is the default human audition file
  audio/final_podcast_playback.m4a exists as a playback-compatible AAC copy
  audio/playback_audio_manifest.json exists
  audio/audio_manifest.json records audio_backend=vibevoice_longform
  audio/audio_manifest.json records vibevoice_input_mode=tts_normalized
  audio/audio_manifest.json records display_dialogue_sha256 and vibevoice_input_sha256 separately
  audio/audio_manifest.json turns record both text and tts_text
  audio/audio_manifest.json records script_hash/input_hash/audio_hash/duration_sec
  spot checks confirm normal speed, stable voices, and natural turn-taking

Gate 8 Audio Timeline Alignment:
  audio/asr_alignment.json exists
  audio/dialogue_timeline.json exists
  audio/alignment_report.md exists
  audio/audio_artifact_qa.json exists
  audio/audio_artifact_qa_report.md exists
  dialogue_timeline records audio_sha256, script_sha256 and audio_manifest_sha256
  all script turns are represented in dialogue_timeline.turns
  cue and turn times are monotonic and within audio duration
  audio_artifact_qa status is PASS, or status is NEEDS_AI_REVIEW and audio_artifact_ai_review.json covers every candidate with final status PASS/PASS_WITH_WARNINGS
  no audio_artifact_ai_review decision is artifact
  opening/middle/end and at least 5 speaker switches are spot checked against real audio

Gate 9A PPT Master Deck Image Assets:
  normal PPT Master project exists
  normal PPT Master project was created for the current video project in this run, not reused from a previous comparison/demo/sample run
  normal PPTX exists
  chapter_visuals/template_selection.json exists
  template_selection.json selected_template is one of editorial_magazine / swiss_grid / risograph_zine unless the user explicitly overrides
  template_selection.json records current_video_project, ppt_master_project, and normal_pptx
  template_selection.json ppt_master_project points to the current fresh PPT Master project
  normal PPT Master project sources include the current project's podcast_script.md
  normal PPT Master project templates/design_spec.md comes from the selected explicit template path
  chapter_visuals/chapter_semantics.json exists
  chapter_semantics.json has one entry per generated PPT slide image
  every semantic entry identifies its image and gives enough text to understand what the slide is about
  one 3840x2160 PPT Master slide PNG per semantic entry exists
  images are designed for target audience: 面向 B 站观众
  chapter_semantics.json has no start_sec/end_sec/start_turn/end_turn fields
  slide images contain no visible source/footer attribution captions
  slide images contain no visible internal production notes, validation/sample labels, workflow labels, draft/debug labels, or other process notes

Gate 9B Chapter Timeline Binding:
  chapter_visuals/chapter_turn_mapping.json exists
  chapter_visuals/chapter_plan.json exists with the same chapter count as chapter_semantics.json
  chapter_visuals/chapter_timeline_binding_report.md exists
  chapter_plan has the same chapter count as chapter_semantics.json
  every chapter/card has start_turn/end_turn and start_sec/end_sec derived from audio/dialogue_timeline.json
  visual intervals are continuous: chapter[i].end_sec == chapter[i+1].start_sec within 0.01s
  first chapter starts at 0.0 and last chapter ends at audio duration

Gate 10 Subtitle Alignment:
  final_subtitles.srt and final_subtitles.ass exist
  subtitle_manifest.json records script_hash, audio_hash, dialogue_timeline_hash
  subtitle_alignment_report.md exists
  subtitles are generated from dialogue_timeline cues, not text-length-only estimates
  subtitles are simultaneous with or slightly earlier than speech
  subtitles are one visible line by default; use shorter, more frequent cues instead of wrapping
  subtitles use light 4K tracking/letter spacing, default letter_spacing_px=6
  subtitles do not display sentence periods
  subtitles use Chinese source names for confirmed publication; no raw English publication such as Foreign Policy appears in SRT/ASS/subtitle_manifest
  no systematic late subtitles

Gate 11 Final Video And Publish:
  video/final_video.mp4 exists and ffprobe passes
  video/final_video.mp4 uses AAC audio derived from audio/final_podcast.wav
  final_video.mp4 is delivered at 1.0x normal speed
  render_manifest.json records playback_speed_factor=1.0 and final_duration_sec
  render_manifest.json records audio_video_check with status PASS
  render_manifest.json records visual_transition.effect=wipe_with_shadow
  render_manifest.json records visual_transition.renderer=python_pillow_fixed_compositor
  render_manifest.json records visual_transition.placement=centered_on_chapter_boundary
  render_manifest.json records visual_timeline_units and video/visual_base_1x.mp4
  frame extraction shows burned subtitles
  render_manifest proves every burned subtitle block sits above common player controls: 1904 <= top_y <= 1974 and bottom_y <= 2044
  render_manifest proves burned subtitle line_count <= 1
  video_title.txt exists and passes title attribution rules
  publish_info.txt exists; first line equals video_title.txt and chapter lines are formatted from final chapter visual segments
  bilibili_upload_metadata.json exists; title equals video_title.txt, category is 知识, creation_declaration is 含AI生成内容, description contains 先行提要 and does not contain 章节 or timestamp ranges, and tags contains 8-10 unique high-signal tags unless qa_report records a WARN with reason
  planning/bilibili_tag_report.json exists and records tag_sources for the accepted tags
  production_manifest.json status is PASS
  qa_report.md exists

Gate 12 Subtitle Timeline QA:
  video/subtitle_timeline_qa.json exists
  video/subtitle_timeline_qa_report.md exists
  subtitle_timeline_qa status is PASS
  final video duration matches audio duration / playback_speed_factor
  final_subtitles.srt cue times match subtitle_manifest.json
  every subtitle cue maps to dialogue_timeline turn/cue timing
  no subtitle cluster is systematically late or early against ASR timeline

Gate 13 Bilibili Upload Publish:
  /Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md was read and followed
  if this agent lacks chrome:control-chrome but video/metadata/QA are complete, status may be UPLOAD_READY_CHROME_HANDOFF_REQUIRED and the parent agent must run this same Gate 13 directly
  the upload stage was executed by bilibili-video-upload-draft itself, not by parent-skill ad hoc Chrome/Playwright code
  parent skill did not write or synthesize bilibili_upload_draft_report.json except to preserve a report already produced by bilibili-video-upload-draft
  bilibili_upload_metadata.json exists and has schema_version=bilibili_upload_metadata.v1
  bilibili_upload_metadata.json title/description/tags/category/creation_declaration/video_path/cover_path validate before browser work
  if scheduled_publish_at is present, the effective scheduled time after bilibili-video-upload-draft normalization is in the future and records scheduled_publish_timezone
  real user Google Chrome is used through Chrome Extension / chrome:control-chrome
  no in-app browser, CDP, Playwright-launched profile, temporary Chrome profile, or auto-launched browser is used for Bilibili
  a fresh Bilibili upload tab is opened
  video/final_video.mp4 is uploaded or the exact upload blocker is recorded
  cover/cover_4k.png is uploaded after video upload succeeds, or the exact cover blocker is recorded
  title, description, tags, category=知识, creation_declaration=含AI生成内容 are filled and read back from the page
  if scheduled_publish_at is present, Bilibili's scheduled publishing controls are set to the effective time and read back
  final submit/post button is clicked exactly once after verification
  bilibili_upload_draft_report.json exists
  bilibili_upload_draft_report.md exists
  bilibili_upload_draft_report.json records skill_name=bilibili-video-upload-draft, skill_path=/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md, skill_invocation=direct, skill_instructions_read=true
  bilibili_upload_draft_report.json records status SUBMITTED or BLOCKED, tab/audit evidence, field verification, accepted tags, final_submit_clicked=true when submitted, submission_status=submitted when submitted, blocker if any
```

## 经验参考：中文稿字数与音频时长

这只是估算经验，不是 gate，不是硬性生产规则。实际时长以 `audio/final_podcast.wav` 和 `audio/dialogue_timeline.json` 为准。

可作为同类中文双人播客的粗略估算：

```text
预计分钟数 ≈ 中文汉字数 / 240
预计分钟数 ≈ 去空格总字符数（含标点） / 275
```

参考区间：

```text
2000 中文汉字 ≈ 8 分钟
2500 中文汉字 ≈ 10 分钟
3000 中文汉字 ≈ 12.5 分钟
3500 中文汉字 ≈ 14.5 分钟
4000 中文汉字 ≈ 16.5 分钟
4500 中文汉字 ≈ 19 分钟
4800-5200 中文汉字 ≈ 20-22 分钟
```

## 不可变规则

- 正文 speaker 标签必须是 `Speaker 0:` 和 `Speaker 1:`。
- 默认正式音频 backend 是 VibeVoice long-form single pass；不要按回合生成再拼接。
- 字幕和最终章节时间轴必须使用最终音频 ASR/forced alignment 得到的 `audio/dialogue_timeline.json`；PPT Master deck 图片资产可以在 `podcast_script.md` 定稿后先并行生成。
- `audio/final_podcast.wav` 只作为内部母带、ASR 对齐源和视频合成源；人工试听默认交付 `audio/final_podcast_preview.mp3`，兼容播放副本为 `audio/final_podcast_playback.m4a`。
- 不得用 MP3/M4A 作为 ASR、字幕或章节时间轴源；这些压缩格式只用于人工试听、播放兼容或最终 MP4/AAC 交付。
- 最终 MP4 合成后必须抽取视频音轨并与 `audio/final_podcast.wav` 做一致性检查，防止视频合成阶段错用音轨、变速、叠加或转码损坏。
- 如果 `dialogue_timeline.json` 不存在或未通过验证，停止在 Gate 8，不进入章节时间线绑定、字幕或视频合成；但已定稿文稿驱动的章节图视觉资产可并行先做。
- 如果 `audio/audio_artifact_qa.json` 为 `NEEDS_AI_REVIEW` 但没有完整 AI 复核，或 AI 复核确认存在 `artifact`，停止在 Gate 8，先重跑/patch 音频并重新 ASR。
- 旧 Qwen3 VoiceDesign/Base clone 只作为用户明确要求的 legacy fallback，不得悄悄启用。
- 封面底图必须由 AI 图像生成模型/工具生成；Pillow/本地脚本只能做等比裁切、尺寸检查和中文标题叠字，不得绘制或兜底生成底图主体。
- 封面必须本地叠中文大字；不要让图像模型直接生成中文标题。
- 封面大字标题和发布标题必须先由 `article-podcast-title-writing` 生成。封面阶段只实现视觉，不临时另写一套标题；静态视频阶段只使用和验证 `video_title.txt`。
- 每条正式视频必须有 PPT Master deck 图片，并且最终视频合成只能消费经过 `article-podcast-chapter-timeline-binding` 生成的 timed `chapter_plan.json`；章节转场只在视频合成层生成 `visual_base_1x.mp4`，不得反写或平移 `chapter_plan.json`。
- 字幕必须先通过字幕对齐 gate，再进入视频合成。默认硬烧录；默认不内嵌软字幕轨，避免重复字幕。
- 字幕使用 `Noto Sans CJK SC Bold`、96 px、白字、3 px 半透明深灰细描边、轻柔投影、右倾 `faux_italic_shear=0.10`；不得有黑底框、半透明背景条、粗黑描边、阴影色块或发光色块。
- 硬字幕块的实际文字必须位于播放器控制条上方安全区：`1904 <= top_y <= 1974` 且 `bottom_y <= 2044`；这是字幕烧录坐标，不是章节视觉必须预留固定安全区的设计规则。
- 正式字幕默认一行显示。长句必须拆成更短 cue 高频切换；`subtitle_manifest.style.max_lines=1` 且 `preferred_lines=1`。
- 字幕允许非常小的相邻 cue overlap 以保护尾音；视频硬字幕合成必须按真实时间片处理 overlap，重叠区显示后开始的 cue，不得顺延后续字幕。
- 字幕不得显示句号：中文 `。`、全角 `．`、以及作为句末标点的英文 `.` 不能出现在字幕里；数字小数点和版本号中的点可以保留。
- 面向观众的衍生内容使用稳定中文专名；`Zhipu` / `Zhipu AI` 在文稿、音频文本、字幕和章节图中写作 `智谱`。已确认的英文媒体 publication 也必须中文化，尤其开头口播和字幕要写 `《外交政策》`、`《经济学人》`、`《彭博社》` 这类中文来源名，不要显示 `Foreign Policy`、`The Economist`、`Bloomberg`。
- 最终交付视频必须为 1.0 倍正常速度；画面、硬字幕和音频保持同一原始时间轴。
- 最终回复前必须运行字幕时间线逐句 QA。
- 字幕时间线 QA 通过后必须调用 `bilibili-video-upload-draft` 作为最终阶段，或在当前 agent 缺少 `chrome:control-chrome` 时返回 `UPLOAD_READY_CHROME_HANDOFF_REQUIRED` 给拥有 Chrome 工具面的上游 agent。除非用户在当前请求中明确说“只生成视频、不打开 B 站上传页”，否则不要停在 `bilibili_upload_metadata.json`。
- 调用 `bilibili-video-upload-draft` 是强制边界，不是建议。不得在本 skill 中用临时 Chrome JS、`node_repl` 代码、直接 DOM 操作或自制脚本替代投稿 skill；不得手写投稿 report。
- B 站投稿发布必须使用用户真实 Chrome 登录态，通过 Chrome Extension / `chrome:control-chrome` 控制；不得用 in-app browser、CDP、Playwright 新 profile 或临时 Chrome profile。
- B 站投稿阶段必须在字段验证通过后点击最终提交按钮一次；成功状态是 `SUBMITTED`。
- 如果视频已完成但 B 站投稿发布被环境阻塞，保留并报告 `video/final_video.mp4`、`bilibili_upload_metadata.json`、`bilibili_upload_draft_report.json`，状态使用 `VIDEO_COMPLETE_UPLOAD_BLOCKED`，不要重跑视频生产。
- 如果能明确确认文章来源，发布标题必须声明来源，格式如 `《经济学人》：中国为什么如此强大？`；不能确认来源时不要添加来源前缀。
- 如果 `podcast_script.md` 变化，标题、音频、ASR 时间轴、字幕、封面、PPT slide 语义、章节时间线绑定和视频全部失效，必须重做。

## 最终回复

最终回复前确认全部 gate 通过，并列出绝对路径：

- `video/final_video.mp4`
- `cover/cover_4k.png`
- `video/final_subtitles.srt`
- `video_title.txt`
- `publish_info.txt`
- `bilibili_upload_metadata.json`
- `bilibili_upload_draft_report.json`
- `bilibili_upload_draft_report.md`

如果任何 gate 被环境阻塞，回复 `BLOCKED`，并给出失败命令、错误信息和停在哪个 gate。
