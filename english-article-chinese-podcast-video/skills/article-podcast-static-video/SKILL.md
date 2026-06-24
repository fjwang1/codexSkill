---
name: article-podcast-static-video
description: 将已定稿的中文双人播客或单人口播音轨、封面图、PPT Master 章节视觉、已对齐字幕和已定稿发布标题合成为 1.0 倍速静态视频，并生成 publish_info.txt、production_manifest 和 QA；B 站投稿 metadata 必须通过 article-bilibili-publish-metadata 子 Skill/脚本生成。正式主流程使用 VibeVoice long-form final_podcast.wav、audio/dialogue_timeline.json、已通过 subtitle alignment gate 的 SRT/ASS、已通过时间线绑定的 PPT Master 章节视觉，以及 article-podcast-title-writing 生成的 video_title.txt；本 skill 不负责重新生成音频、字幕、标题或章节图。
---

# 文章播客/口播成片交付

这个 skill 负责最后成片：画面、已定稿音轨、已对齐字幕、MP4、已定稿发布标题、发布信息文件和总 QA。正式端到端流程中的音频必须已经由 VibeVoice 整篇生成，并通过 `article-podcast-audio-alignment` 产出 `audio/dialogue_timeline.json`；字幕必须已经通过 `article-podcast-subtitle-alignment` 生成和校准；标题必须已经通过 `article-podcast-title-writing` 生成；章节图必须已经通过 `article-podcast-chapter-visuals` 生成。不要在视频阶段重新生成音频、时间轴、字幕、标题或章节图。

历史脚本 `scripts/render_static_podcast_video.py` 仍能用 VoiceDesign 描述逐回合生成音频并合成视频，但这不是正式生产路径。只有在调试旧项目或做冒烟测试时才可使用。正式项目若使用该脚本，必须先确认它不会覆盖或重生 `audio/final_podcast.wav`、`audio/dialogue_timeline.json` 或字幕文件。

## 输入

正式视频合成应具备：

```text
source/source_metadata.json, recommended
podcast_script.md
single_host_script.md, optional; single-host projects also keep podcast_script.md as a compatibility mirror
audio/final_podcast.wav
audio/audio_manifest.json
audio/dialogue_timeline.json
cover/cover_title.json
cover/cover_4k.png
video_title.txt
chapter_visuals/chapter_semantics.json, required
chapter_visuals/chapter_turn_mapping.json, required
chapter_visuals/chapter_plan.json, required, final timed plan from article-podcast-chapter-timeline-binding with start_sec/end_sec
chapter_visuals/chapter_timeline_binding_report.md, required
chapter_visuals/chapter_*.png, required
video/final_subtitles.srt
video/final_subtitles.ass
video/subtitle_manifest.json
video/subtitle_alignment_report.md
```

`audio_manifest.json` 必须记录 VibeVoice backend、脚本 hash、音频 hash 和 turn 文本。`dialogue_timeline.json` 必须记录最终音频 ASR 对齐后的 turn/cue 时间。`subtitle_manifest.json` 必须记录字幕 cue 的 `start_sec/end_sec`、样式和对齐方法。

## 输出

```text
video/final_subtitles.srt
video/final_subtitles.ass
video/final_subtitles_1x.srt
video/final_subtitles_1x.ass
video/subtitle-overlays/
video/visual-clips/
video/visual_concat.ffconcat
video/visual_base_1x.mp4
video/final_video_1x.mp4
video/final_video.mp4
video/render_manifest.json
video/render_report.md
video_title.txt
publish_info.txt
bilibili_upload_metadata.json
planning/bilibili_tag_report.json
production_manifest.json
qa_report.md
```

`publish_info.txt` 只在本最终成片阶段生成，不在项目初始化或标题阶段创建。格式固定为第一行发布标题，后续每行一个章节时间段：

```text
《外交政策》：台海导弹防御，为什么不能照搬伊朗经验？
00:00-03:12：为什么伊朗经验看起来诱人？
03:12-07:45：台海场景到底差在哪里？
```

`bilibili_upload_metadata.json` 在本阶段结束时由 `article-bilibili-publish-metadata` 子 Skill/脚本生成，作为后续 `bilibili-video-upload-draft` 的机器可读输入。不要把投稿简介和标签留到上传阶段临场生成；metadata 子节点拥有完整的标题、文章、节目策划、章节时间线和封面标题上下文，必须在这里定稿：

```json
{
  "schema_version": "bilibili_upload_metadata.v1",
  "title": "《外交政策》：台海导弹防御，为什么不能照搬伊朗经验？",
  "description": "《外交政策》：台海导弹防御，为什么不能照搬伊朗经验？\n\n先行提要：本期从原文核心冲突出发，解释为什么一个看似可复制的防御经验，到了台海会被地理、产业链和升级风险重新改写。",
  "tags": ["外刊解读", "国际观察", "外交政策", "中国观察", "亚洲观察", "中美关系", "地缘政治", "导弹防御", "台海", "军事科技"],
  "category": "知识",
  "creation_declaration": "含AI生成内容",
  "scheduled_publish_at": null,
  "scheduled_publish_timezone": "Asia/Shanghai",
  "schedule_source": null,
  "source_title": "original article title if known",
  "publication": "外交政策",
  "topic_keywords": ["台海", "导弹防御", "供应链"],
  "video_path": "video/final_video.mp4",
  "cover_path": "cover/cover_4k.png",
  "publish_info_path": "publish_info.txt"
}
```

生成规则：

- `title` 必须等于 `video_title.txt`。
- `description` 面向 B 站简介，不写内部生产路径、脚本 hash、模型信息、QA 细节、`章节：`、时间轴或章节 slug。结构固定为：标题、空行、`先行提要：` 1-3 句。先行提要必须来自 `planning/article_brief.json`、`podcast_script.md`、`source/article.txt`、`cover/cover_title.json` 或节目策划材料中的可验证内容；不要联网补写，不要引入原文没有支撑的结论。`publish_info.txt` 仍保存章节时间线供 QA/发布记录使用，但不得复制进 B 站简介。
- `tags` 目标 8-10 个，按 B 站上传页实际容量尽量填满；当前上传页实测最多可接受 10 个标签。必须去重，单个标签不超过 20 个中文字符，不含空格、井号、逗号、顿号或引号。
- 标签组合由 `article-bilibili-publish-metadata` 负责。默认固定基础标签使用 `外刊解读`、`国际观察`，再按内容添加 `财经解读` / `社会观察`、确认来源媒体、`中国观察` / `中国经济` / `亚洲观察` 和具体主题词。默认不要使用 `外刊精读`、`英语学习`、`英语听力`，除非视频确实是英语学习或逐句精读产品。动态标签从国家/地区、政策对象、行业、关键制度、人物/机构、核心冲突、`cover_title.json.keyword_heat_check.best_keywords` 和 `cover_title.json.chinese_motifs` 中抽取。不要为了凑数加入与本期无关的流量词，也不要把完整标题或句子当标签。实测 `上B站看播客` 在上传页更像参与话题，普通标签输入后可能不生成 chip；不要把它作为普通标签必选项。
- `category` 固定写 `知识`。本频道文章播客视频统一投知识分区；上传 skill 只负责确认页面显示为知识，不现场猜分区。
- `creation_declaration` 固定写 `含AI生成内容`，因为本流水线包含 AI 改写、TTS、字幕和封面生成。
- `scheduled_publish_at` 默认写 `null`。本通用英文文章转播客 Skill 不决定发布时间；如果由 daily 总控调用，总控根据 `selection_mode` 更新该字段，并按“当天 slot 尚未到达则当天、已经到达或超过则下一天同一 slot”的规则生成未来 ISO 8601 时间。独立使用时也可以由调用者传入或后处理为 ISO 8601 时间；最终上传前仍由 `bilibili-video-upload-draft` 做一次 upload-time 归一化。
- 如果无法可靠生成至少 6 个高相关标签，仍然写出 metadata，但在 `qa_report.md` 记录 `WARN: bilibili tags underfilled` 和缺少的上下文来源。metadata 子节点还必须写出 `planning/bilibili_tag_report.json` 记录标签来源。

## 字幕规则

- 使用已经存在的 `video/final_subtitles.srt` 和 `video/final_subtitles.ass`。
- 默认烧录硬字幕，并保留 SRT/ASS 旁路文件。
- 默认不内嵌软字幕轨，避免播放器自动显示软字幕后和硬字幕重复。
- 字幕只显示台词，不显示 `Speaker 0:`、`Speaker 1:`。
- 字幕不显示句号：中文 `。`、全角 `．`、以及作为句末标点的英文 `.` 必须在字幕生成 gate 中处理掉；内部句号可替换成逗号保留停顿，句尾句号直接删除。数字小数点和版本号中的点可以保留。
- 字幕硬烧录专用字体必须使用 `Noto Sans CJK SC Bold`，字体文件为 `/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf`，对应 ASS `Fontname=NotoSansCJKsc-Bold`。这条只适用于字幕 overlay 和 ASS 旁路；不要改封面字体，封面仍由 `bilibili-podcast-cover` 的固定封面字体负责。
- 4K 固定字号为 96 px，白字、3 px 半透明深灰细描边、轻柔投影、右倾 `faux_italic_shear=0.10`，默认一行；不要主动换成两行，也不要为长句自动缩小字号。Pillow 硬字幕 renderer 必须给首尾 glyph 留足左右防裁切边距：`glyph_edge_pad_px >= 48` 且 `shear_edge_pad_px >= 16`，默认实现使用 `glyph_edge_pad_px=72`、`shear_edge_pad_px=24`。斜体/shear 变换必须使用正向 padding，不能把首字采样到临时图层外。
- 4K 硬字幕默认使用轻微字距，`subtitle_manifest.style.letter_spacing_px=6`；本地烧录 overlay 必须实际按这个 tracking 绘制，`render_manifest.json` 为每个字幕 segment 记录 `subtitle_layout.letter_spacing_px`。如果字距导致单行过宽，先拆 cue 轮播，不要缩成拥挤字距或缩小字号。
- 视频合成器把硬字幕文字放在常见播放器进度条和控制条上方，实际文字必须满足 `1904 <= top_y <= 1974` 且 `bottom_y <= 2044`。这是字幕渲染规则，不是章节视觉必须预留固定安全区的设计规则；相对旧版位置下移了一个 96 px 字体高度。
- 视频合成必须在 `render_manifest.json` 为每个带字幕 segment 记录 `subtitle_layout.top_y/bottom_y/font_size_px/line_count`，用于 QA 验收。
- 字幕不得有黑底框、半透明背景条、粗黑描边、阴影色块或发光色块；只允许 3 px 以内半透明深灰细描边和轻柔投影增强可读性。
- 字幕位置偏下但必须在播放器控制条上方，避免压到封面/章节画面的主体文字。
- 单条字幕过长时先拆 cue 高频切换，不要用换行承载长句；正式 `subtitle_manifest.style.max_lines=1`。
- 如果 `subtitle_manifest.json` 中相邻 cue 有小重叠，硬字幕 compositor 必须按真实时间片渲染，重叠区显示后开始的 cue（`overlap_policy=latest_started_cue_visible`），不得用简单 concat 顺延后续字幕。
- 如果字幕明显晚于语音，停止并回到 `article-podcast-subtitle-alignment` 修复，不要在视频合成阶段临时平移糊弄。

## 画面规则

正式成片必须使用章节视觉时间轴。`cover/cover_4k.png` 是封面/缩略图资产，不是整片默认画面。不要因为章节图缺失而退回全程封面；应停止并回到 `article-podcast-chapter-visuals`。

按 `chapter_plan.json` 的 `start_sec/end_sec` 合成画面时间轴。`start_turn/end_turn` 只用于校验和人工理解。正式成片的 `chapter_plan.json` 必须由 `article-podcast-chapter-timeline-binding` 生成，章节数量由 PPT Master 和播客稿结构决定；如果只有 turn 区间、缺少 `chapter_timeline_binding_report.md`，或 plan 来自 PPT 阶段的未绑定 review plan，先回到时间线绑定阶段，不要猜。

章节图片路径可以是绝对路径，也可以相对 `chapter_plan.json` 所在目录。每个章节都应有一张 `3840x2160` PPT Master 视觉页。

时间轴要求：

- 第一章通常从 `0.0` 开始。
- 每章 `end_sec` 必须大于 `start_sec`。
- 章节区间应单调递增，不要重叠。
- 章节视觉区间必须连续：第 N 章 `end_sec` 等于第 N+1 章 `start_sec`，容差 `0.01s`。这避免预合成视觉轨时产生边界漂移。
- 最后一章应覆盖到音频结尾，或明确由最后一张章节卡补尾。
- `render_manifest.json` 必须记录每张章节卡片的 `start_sec/end_sec/image/hash`。

章节间默认必须加固定视觉转场：

- 使用脚本内置的 Python/Pillow `wipe_with_shadow` 转场，不依赖自定义 FFmpeg、GLSL、Remotion 或外部视频编辑器。
- 转场只属于视觉合成层，不能改 `chapter_visuals/chapter_plan.json` 的章节语义时间轴，不能平移字幕，不能改音频。
- 默认转场时长为 `0.8s`，居中放在相邻章节边界上；如果相邻章节太短，脚本按章节长度自动缩短或跳过该边界转场，避免视觉 unit 重叠。
- 脚本先生成 `video/visual-clips/` 下的静态 hold clips 和 `wipe_with_shadow` transition clips，再拼成 `video/visual_base_1x.mp4`，最后把字幕 overlay 和 `audio/final_podcast.wav` 合成进 `video/final_video_1x.mp4`。
- `render_manifest.json` 必须记录 `visual_transition.effect=wipe_with_shadow`、`visual_transition.renderer=python_pillow_fixed_compositor`、`visual_transition.placement=centered_on_chapter_boundary`、`visual_timeline_units`、`visual_base_hash` 和每个 transition clip 的 hash。

## 速度规则

正式交付的 `video/final_video.mp4` 必须保持 `1.0x` 正常速度。

推荐流程：

1. 按原始音频时间轴合成并硬烧录字幕，得到 `video/final_video_1x.mp4`。
2. 将 `video/final_video_1x.mp4` 复制或无损封装为正式交付的 `video/final_video.mp4`，不要对音频或画面做变速。

```bash
ffmpeg -y -i video/final_video_1x.mp4 -c copy \
  video/final_video.mp4
```

3. 将 Gate 7 的原始时间轴字幕同时保存为 `video/final_subtitles_1x.srt` 和 `video/final_subtitles_1x.ass`。
4. 最终交付的 `video/final_subtitles.srt` 和 `video/final_subtitles.ass` 保持 1.0x 时间戳，不做缩放。
5. `video/subtitle_manifest.json` 的 cue 时间也必须缩放到最终时间轴，并记录：

```json
{
  "playback_speed_factor": 1.0,
  "source_timeline": "1x",
  "final_timeline": "1x"
}
```

`render_manifest.json` 必须记录：

```json
{
  "playback_speed_factor": 1.0,
  "pre_speed_video": "video/final_video_1x.mp4",
  "pre_speed_duration_sec": 603.15,
  "final_video": "video/final_video.mp4",
  "final_duration_sec": 603.15
}
```

## 音频格式规则

- `audio/final_podcast.wav` 是内部母带和时间轴基准；视频合成从它取音频，编码为 MP4 内的 AAC 音轨。
- `audio/final_podcast_preview.mp3` 是默认给用户试听的完整音频；不要把 24kHz mono WAV 当作默认试听交付。
- `audio/final_podcast_playback.m4a` 是兼容播放器的 AAC/M4A 副本；可辅助人工播放验收，但不得作为字幕/章节对齐源。
- 合成视频后必须抽取 `video/final_video.mp4` 的音轨，重采样为 24kHz mono WAV，并和 `audio/final_podcast.wav` 做一致性检查。`render_manifest.json.audio_video_check.status` 必须为 `PASS`。
- 如果用户报告“MP3/M4A 正常但 WAV 异常”，优先怀疑播放器对 24kHz mono WAV 的兼容性；不要因此改动对齐源，除非 FFmpeg 解码 WAV 也复现异常。

## 视频验收

视频合成后立即检查：

正式 VibeVoice 主流程使用本地 compositor，而不是旧的逐回合 TTS 脚本：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-static-video/scripts/render_vibevoice_static_video.py \
  --project-dir <project>
```

这个脚本只消费已经存在的 `audio/final_podcast.wav`、`video/final_subtitles.srt`、`video/final_subtitles.ass`、`video/subtitle_manifest.json`、`chapter_visuals/chapter_plan.json` 和 `video_title.txt`。它会用 Pillow 生成透明硬字幕 overlay 和章节间 `wipe_with_shadow` 转场 clips，再用 ffmpeg 合成 `video/visual_base_1x.mp4`、`video/final_video_1x.mp4` 和 `video/final_video.mp4`，并写出 `publish_info.txt`；不会重新生成 TTS。

```bash
ffprobe -v error \
  -show_entries format=duration:stream=index,codec_type,codec_name,width,height \
  -of json <project>/video/final_video.mp4
```

通过条件：

```text
video/final_video.mp4 exists and ffprobe passes
video has one video track and one audio track
video duration matches audio/final_podcast.wav within acceptable tolerance
render_manifest.json records audio_video_check
render_manifest.json audio_video_check.status is PASS
render_manifest.json audio_video_check.sample_correlation >= 0.995
render_manifest.json records playback_speed_factor=1.0
render_manifest.json records subtitle_layout_rule.subtitle_block_top_min_y=1904, subtitle_block_top_max_y=1974, subtitle_block_bottom_max_y=2044
render_manifest.json records subtitle_layout_rule.glyph_edge_pad_px >= 48 and subtitle_layout_rule.shear_edge_pad_px >= 16
render_manifest.json records subtitle_layout_rule.shear_transform=forward_x_plus_shear_y_with_positive_padding
render_manifest.json records subtitle_layout_rule.font_family=NotoSansCJKsc-Bold
render_manifest.json records subtitle_layout_rule.font_file=/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf
render_manifest.json records subtitle_layout_rule.overlap_policy=latest_started_cue_visible
every burned subtitle segment has 1904 <= subtitle_layout.top_y <= 1974 and subtitle_layout.bottom_y <= 2044
every burned subtitle segment records glyph_edge_pad_px >= 48 and shear_edge_pad_px >= 16 so the first and last glyph are not clipped
every burned subtitle segment has subtitle_layout.line_count <= 1
video/final_subtitles.srt exists
video/final_subtitles.ass exists
video/final_subtitles.srt and final_subtitles.ass match the 1.0x final video timeline
video/final_subtitles_1x.srt and final_subtitles_1x.ass preserve the original audio timeline
video/subtitle_manifest.json exists
video/subtitle_alignment_report.md exists
subtitle_manifest.style.letter_spacing_px exists and render_manifest subtitle layouts record the same value
frame extraction shows burned subtitles
frame extraction shows subtitles have no background box, no thick black outline, and only subtle translucent outline plus soft drop shadow
frame extraction and render_manifest show subtitles sit above common player controls
frame extraction and sidecar checks show subtitles do not display sentence periods
render_manifest.json records script_hash, audio_hash, dialogue_timeline_hash, cover_hash, subtitle_hash, subtitle_manifest_hash, and chapter_visual_hashes
render_manifest.json records visual_transition.effect=wipe_with_shadow
render_manifest.json records visual_transition.renderer=python_pillow_fixed_compositor
render_manifest.json records visual_transition.placement=centered_on_chapter_boundary
render_manifest.json records visual_timeline_units with existing clip paths and hashes
video/visual_base_1x.mp4 exists and is recorded in render_manifest outputs
chapter_visuals are placed by explicit start_sec/end_sec
chapter_visuals/chapter_timeline_binding_report.md exists
chapter visual intervals are continuous with no gaps that could drift ffconcat timing
```

如果 `ffprobe` 报 `moov atom not found`，等待 ffmpeg 进程结束；如果没有进程，删除坏文件后重跑视频合成。

## 发布标题

视频标题应已由 `article-podcast-title-writing` 写入 `<project>/video_title.txt`。它不同于封面三行大字。本阶段只验证和记录，不现场重写；如果缺失或不合格，停止并回到标题 skill。

验证规则：

- 18-36 个中文字符为宜。
- 如果能从 `source/source_metadata.json`、本地原文正文/页眉、或 `podcast_script.md` 的来源行明确确认文章来源，标题必须以前缀声明中文来源：`《<中文来源名>》：标题主体`。例如 `《经济学人》：中国为什么如此强大？`
- 来源必须是可见且可验证的；不要联网补来源，不要只凭文件名或主题猜来源。
- 来源前缀必须使用中文媒体名，不允许把英文 publication 原样放进标题。常见英文来源使用稳定中文名：`The Economist` 写作 `经济学人`，`Financial Times` 写作 `金融时报`，`The New York Times` 写作 `纽约时报`，`The New Yorker` 写作 `纽约客`，`The Atlantic` 写作 `大西洋月刊`，`The Wall Street Journal` 写作 `华尔街日报`，`WIRED` 写作 `连线`，`Bloomberg` 写作 `彭博社`，`Foreign Policy` 写作 `外交政策`，`Foreign Affairs` 写作 `外交事务`。没有公认中文名时保守直译成中文媒体名；如果无法可靠翻译，停止并回到标题 skill 或人工确认，不要保留英文名称。
- 前缀不计入标题主体的 18-36 中文字符建议；标题主体仍要具体、有冲突或后果。
- 必须具体，包含对象、冲突、后果或反直觉点中的至少两项。
- 像视频题目，不像报刊标题或论文标题。
- 不歪曲文章事实，不把复杂议题压成单一阴谋论。
- 避免空泛词：`真相`、`内幕`、`震惊`、`深度解析`，除非事实支撑。

## 总 QA

生成 `production_manifest.json` 和 `qa_report.md`。

`production_manifest.json` 至少记录：

```json
{
  "status": "PASS",
  "script_sha256": "...",
  "audio_manifest_sha256": "...",
  "dialogue_timeline_sha256": "...",
  "audio_sha256": "...",
  "cover_sha256": "...",
  "subtitle_manifest_sha256": "...",
  "video_sha256": "...",
  "title_attribution": {
    "publication": "经济学人",
    "used_in_video_title": true,
    "evidence": "source/source_metadata.json publication"
  },
  "deliverables": {
    "visual_base": "video/visual_base_1x.mp4",
    "final_video": "video/final_video.mp4",
    "normal_speed_video": "video/final_video_1x.mp4",
    "cover": "cover/cover_4k.png",
    "subtitles": "video/final_subtitles.srt",
    "normal_speed_subtitles": "video/final_subtitles_1x.srt",
    "video_title": "video_title.txt",
    "publish_info": "publish_info.txt",
    "bilibili_upload_metadata": "bilibili_upload_metadata.json"
  }
}
```

运行总 QA：

```bash
python /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/scripts/qa_article_podcast_video.py \
  --project-dir <project> \
  --min-duration-sec 60
```

最终通过条件：

```text
video_title.txt exists
publish_info.txt exists, first line equals video_title.txt, and chapter lines match chapter_plan/render_manifest visual segments
bilibili_upload_metadata.json exists, title equals video_title.txt, category is 知识, creation_declaration is 含AI生成内容, description contains 先行提要 and does not contain 章节 or timestamp ranges, and tags contains 8-10 unique high-signal tags unless qa_report records a WARN with reason
planning/bilibili_tag_report.json exists and records tag_sources for the accepted tags
production_manifest.json exists and status is PASS
if publication is visible, production_manifest.json records title_attribution.publication and used_in_video_title=true
qa_report.md exists
final_video.mp4, cover_4k.png, final_subtitles.srt, video_title.txt, publish_info.txt, bilibili_upload_metadata.json all exist
video/visual_base_1x.mp4 exists
render_manifest.json records visual_transition.effect=wipe_with_shadow and visual_timeline_units
final_video.mp4 is 1.0x and sidecar subtitles match the final normal-speed timeline
burned subtitle text top_y is 1904..1974 and bottom_y <= 2044
burned subtitles are one visible line by default; long sentences are split into shorter cues
subtitle text has no displayed sentence periods
if publication is visible, video_title.txt uses 《<中文来源名>》：前缀 and does not keep raw English publication names
QA does not report FAIL or NEEDS_FIX
```

## 旧脚本注意事项

`scripts/render_static_podcast_video.py` 当前默认会读取文稿并使用 VoiceDesign profile 生成音频和字幕。正式主流程要求音频来自 VibeVoice long-form，时间轴来自 `audio/dialogue_timeline.json`，字幕来自独立字幕对齐 gate，因此不要把这个旧默认路径当作最终生产命令。若需要继续使用该脚本，应先改造或包装它，让它接受已存在的 `audio/final_podcast.wav`、`audio/dialogue_timeline.json`、`video/final_subtitles.srt` 和 `video/final_subtitles.ass`，只负责画面合成和硬烧录。
