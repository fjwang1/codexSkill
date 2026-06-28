---
name: article-podcast-subtitle-alignment
description: 为中文播客或单人口播音频生成并校准中文字幕。适用于已有 podcast_script.md 或 single_host_script.md、audio/final_podcast.wav、audio/dialogue_timeline.json，需要基于最终音频 ASR/forced alignment 时间轴生成 final_subtitles.srt、final_subtitles.ass、subtitle_manifest.json 和对齐报告，确保字幕不晚于语音并可硬烧录。
---

# 播客/口播字幕对齐

这个 skill 负责 Gate 7：生成、校准和验收中文字幕。视频合成阶段只消费这里产出的 SRT/ASS，不再临时生成字幕。

## 输入

```text
<project>/podcast_script.md
<project>/single_host_script.md  # optional, single-host projects also keep podcast_script.md as a compatibility mirror
<project>/audio/final_podcast.wav
<project>/audio/dialogue_timeline.json
```

`dialogue_timeline.json` 必须由 `article-podcast-audio-alignment` 基于最终音频 ASR/forced alignment 生成，记录每个 turn 和 cue 的 `start_sec/end_sec`。cue 级时间必须来自最终 ASR/forced-alignment 的字/词时间 span；不得只在 turn 内按中文字符比例分配字幕时间。

## 输出

```text
<project>/video/final_subtitles.srt
<project>/video/final_subtitles.ass
<project>/video/subtitle_manifest.json
<project>/video/subtitle_alignment_report.md
```

## 字幕样式

正式字幕默认：

- 硬烧录到画面，同时保留 SRT/ASS 旁路文件。
- 不显示说话人名字，不显示 `Speaker 0:`、`Speaker 1:`。
- 只显示台词。
- 字幕是给中文观众看的显示文本；已确认来源必须使用中文媒体名。开头如果提来源，应显示类似 `今天在《外交政策》看到一篇文章`，不要显示 `Foreign Policy`、`Bloomberg`、`The Economist` 等 raw English publication。
- 不显示句号：中文 `。`、全角 `．`、以及作为句末标点的英文 `.` 不能出现在字幕里；内部句号可替换成逗号保留停顿，句尾句号直接删除。保留数字小数点和版本号中的点，例如 `3.48`、`GPT-5.5`。
- 字幕专用字体必须使用 `Noto Sans CJK SC Bold`，本机字体文件固定为 `/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf`，ASS `Fontname` 记录 `NotoSansCJKsc-Bold`。这是字幕字体设置，不要用于封面；封面仍由 `bilibili-podcast-cover` 使用自己的固定封面字体。
- 当前正式 4K 字幕固定字号为 96 px；不得为了让长句塞进一行而自动缩小字号。
- 白字、3 px 半透明深灰细描边、轻柔投影，并通过 `faux_italic_shear=0.10` 做右倾斜体效果；描边只用于提升白底可读性，不得做成粗黑边字幕。
- 正式 4K 字幕必须有轻微字距，避免粗体中文、英文缩写和长数字挤在一起；默认 `letter_spacing_px=6`，可在 `4..8px` 范围内微调。字距优先用本地绘制/overlay 实现，ASS 旁路可用 `Spacing` 字段近似记录。
- 默认一行；不要主动换成两行。
- 通过更短 cue 高频切换承载长句；一行放不下时必须拆成下一个 cue 轮播，不得缩小字号或换两行承载。
- 硬字幕块实际文字必须位于播放器控制条上方安全区：`1904 <= top_y <= 1974` 且 `bottom_y <= 2044`。这是字幕烧录坐标规则，不是章节视觉必须预留固定安全区的设计规则；相对旧版位置下移了一个 96 px 字体高度。
- 字幕在画面底部偏上摆放，避开常见播放器进度条和控制条，同时不得遮挡观众阅读。
- 字幕不得有背景底框、半透明暗底、粗黑描边、阴影色块或发光色块；只允许 3 px 以内半透明深灰细描边和轻柔投影增强可读性。
- 默认不内嵌软字幕轨，避免播放器显示双字幕。

ASS 样式必须记录 4K 坐标系：

```text
PlayResX: 3840
PlayResY: 2160
Fontname: NotoSansCJKsc-Bold
Fontsize: 96 for burned subtitle overlays
Outline: 3 px subtle translucent dark outline
Shadow: soft drop shadow in burned overlay; ASS sidecar may keep Shadow=0
BackColour: fully transparent
Alignment: bottom center
Subtitle safe band: top_y 1904..1974, bottom_y <= 2044
```

## 同步策略

字幕不得系统性晚于语音。理想状态是字幕与语音同时出现，或字幕提前一点点出现。

硬要求：

- 默认全局提前量为 `0.12s`；正式生产不得低于 `0.08s`。
- 如果一个源 cue 在字幕阶段继续拆成多个显示 cue，提前量必须应用到每个拆分后的 cue，而不是只应用到原 cue 的第一条。
- 每条字幕 cue 必须记录 `source_start_sec`、`source_end_sec`、`subtitle_start_lead_sec` 和 `subtitle_start_late_by_sec`。
- `subtitle_manifest.timing_policy.status` 必须为 `PASS`，`late_start_violation_count == 0`，`lead_applied_per_split_cue == true`。

## 默认本地命令

正式主流程使用本 skill 下脚本从 `audio/dialogue_timeline.json` 生成字幕：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-alignment/scripts/build_subtitles_from_timeline.py \
  --project-dir <project>
```

该脚本会写出 `video/final_subtitles.srt`、`video/final_subtitles.ass`、`video/final_subtitles_1x.srt`、`video/final_subtitles_1x.ass`、`video/subtitle_manifest.json` 和 `video/subtitle_alignment_report.md`。脚本使用 Pillow 和正式字幕字体测量 96 px 固定字号下的单行宽度，长 cue 必须按完整句或完整语义分句拆成多个同字号 cue；不得为了单行宽度硬切词组。

### 第一层：ASR 对齐时间轴

用 `audio/dialogue_timeline.json` 中的 `cues` 作为字幕基础时间轴。不得用字数比例从整段音频时长反推字幕时间。

`article-podcast-audio-alignment/scripts/build_dialogue_timeline_from_asr.py` 必须遵守：

- `timeline.subtitle_cue_policy.cue_text_policy == complete_sentence_or_semantic_clause_no_hard_width_split`
- `timeline.subtitle_cue_policy.cue_timing_policy == asr_character_span`
- cue 文本优先按 `。！？；` 完整句切分；单句过长时只按 `，、：；` 等语义边界拆分。
- 不得把词组、机构名、人名、数字单位、固定头衔硬切成两条 cue，例如 `大西洋理事会非` / `常驻高级研究员` 这类拆法必须 FAIL。
- 如果已有标点分句仍超过字幕长度上限，允许只在明确中文语义连接点处继续拆分，例如 `强到`、`而不是`、`从而`、`进而`、`同时`、`并且`、`能够`、`可以`、`由` 等；这仍属于语义分句，不是按固定字数硬切。若找不到安全语义连接点，必须 FAIL 并回上游改写。
- 如果 ASR cue 把一句话切在明显悬空连接成分处，而下一条 cue 是同一说话人、时间紧邻且合并后仍能按单行语义分句通过门禁，字幕生成器可以先临时合并这两个 cue 再重新分显示 cue，并在 manifest 中记录 `source_cue_indices`。不得跨说话人合并，不得为了通过门禁吞掉停顿很远的下一句。
- 若某个句子/分句长到单行放不下且没有语义标点可拆，回到上游文稿拆句，不得按字符数硬切。
- cue 的 `start_sec/end_sec` 必须来自该 cue 对应脚本文字在 ASR 字/词时间轴中的 span；只有 ASR 局部缺字时才允许插值，并记录 `timing_source` / `asr_matched_char_ratio`。
- 若媒体级删除、重剪或平台退回修复改变了音频、字幕或 audio manifest，必须重建 `audio/dialogue_timeline.json` 和字幕；旧时间轴不得复用。

如果 `dialogue_timeline.json` 缺失、未通过验证，或只有 turn 级粗时间没有 cue 级时间，停止并回到 `article-podcast-audio-alignment`。

如果 `dialogue_timeline.json` 的 `matched_script_ratio < 0.95`，或尾部存在连续低置信度 turn，或长句 cue/turn 被压缩到最后几百毫秒，必须停止。不要用字幕阶段把未朗读的稿件硬塞进音频尾部；这代表 `audio/final_podcast.wav` 没有完整覆盖文稿，应回到 VibeVoice 重跑。

### 第二层：cue 拆分

基于 `dialogue_timeline.cues` 做字幕显示文本清理和必要细拆：

- 优先按 `。！？；` 拆成完整句。
- `。` 可以作为拆分依据，但拆完后的正式显示文本必须没有句号；内部停顿可改为 `，`。
- 每条 cue 默认一行，不插入换行；长句只能按完整语义分句拆成多个 cue。
- 不要把半个词、数字单位、人名拆开。
- 不要生成悬空字幕，例如以 `的`、`如果`、`除了`、`因为`、`但是`、`所以`、`包括`、`比如`、`当`、`把`、`被`、`与`、`以及`、`或者`、`并且`、`而且` 等明显未完成连接成分结尾的 cue。不要把国家名或专名尾字误判为连接成分，例如 `南非` 不能只因为结尾是 `非` 被拦截。
- 不要为了短而破坏语义。
- 不要把来源英文名带进字幕。如果 `source_metadata.json.publication` 是 `Foreign Policy`，字幕中应出现 `外交政策`，不能出现 `Foreign Policy`。如果 `dialogue_timeline.cues[].text` 已经含有 raw English publication，停止并回到上游文稿生成/润色节点或 `article-podcast-audio-alignment` 修正显示稿和时间轴；不要只在 SRT 里偷偷替换导致字幕和口播语义不一致。

必要时可以在一个 ASR cue 内按语义细拆，但细拆后的 cue 时间必须仍落在该 ASR cue 的真实时间范围内。

### 第三层：提前量和抽检

字幕生成时可以应用很小的全局提前量。校准目标：

- cue 开始时间不晚于对应语音开头。
- cue 可提前 `0.08-0.15s`。
- cue 结束时间可晚于语音 `0.10-0.25s`，但不要拖太久。
- 为避免相邻语句抢话或连读导致尾音被截断，字幕生成允许相邻 cue 有很小重叠；默认 `next_cue_overlap_sec=0.24`。重叠只表达时间轴真实边界，不代表画面必须同时显示两行。
- 相邻 cue 不应产生明显闪烁；最短显示时长通常不小于 `0.75s`。

如果当前环境无法做 ASR/forced alignment，不要在本 skill 里 fallback 估算；应回到 `article-podcast-audio-alignment` 并报告阻塞。

## subtitle_manifest.json

至少记录：

```json
{
  "schema_version": "article-podcast-subtitles.v1",
  "script_sha256": "...",
  "audio_sha256": "...",
  "dialogue_timeline_sha256": "...",
  "alignment_method": "dialogue_timeline_asr",
  "global_lead_sec": 0.12,
  "tail_sec": 0.12,
  "next_cue_overlap_sec": 0.24,
  "timing_policy": {
    "status": "PASS",
    "global_lead_sec": 0.12,
    "minimum_required_global_lead_sec": 0.08,
    "max_allowed_late_start_sec": 0.02,
    "max_late_start_sec": 0.0,
    "late_start_violation_count": 0,
    "lead_applied_per_split_cue": true
  },
  "segmentation_policy": {
    "status": "PASS",
    "unit_policy": "one_visible_line_per_complete_sentence_or_semantic_clause",
    "hard_width_fallback_count": 0,
    "line_violation_count": 0,
    "dangling_fragment_violation_count": 0
  },
  "style": {
    "resolution": "3840x2160",
    "font_family": "NotoSansCJKsc-Bold",
    "font_full_name": "Noto Sans CJK SC Bold",
    "font_file": "/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf",
    "font_license_note": "SIL Open Font License 1.1",
    "font_size_px": 96,
    "letter_spacing_px": 6,
    "preferred_lines": 1,
    "max_lines": 1,
    "line_policy": "single_line_preferred_frequent_short_cues",
    "speaker_labels": false,
    "burned_subtitle_default": true,
    "embed_soft_subtitle_default": false,
    "background_box": false,
    "outline": "subtle_translucent_outline",
    "outline_width_px": 3,
    "outline_color": "rgba(30,30,30,0.57)",
    "shadow": "soft_drop_shadow",
    "shadow_color": "rgba(0,0,0,0.38)",
    "shadow_blur_px": 2,
    "faux_italic_shear": 0.10,
    "back_color": "transparent",
    "sentence_periods_displayed": false,
    "subtitle_block_top_min_y": 1904,
    "subtitle_block_top_max_y": 1974,
    "subtitle_block_bottom_max_y": 2044,
    "overflow_policy": "split_overlong_cues_no_font_shrink"
  },
  "cues": [
    {
      "index": 1,
      "speaker": "Speaker 0",
      "display_role": "女主持",
      "text": "...",
      "display_text": "...",
      "start_sec": 0.0,
      "end_sec": 2.84,
      "source_start_sec": 0.12,
      "source_end_sec": 2.72,
      "subtitle_start_lead_sec": 0.12,
      "subtitle_start_late_by_sec": 0.0,
      "source_turn_id": "turn_0001",
      "source_cue_index": 1,
      "semantic_unit_type": "sentence",
      "split_reason": "sentence_boundary",
      "fits_single_line": true,
      "alignment_confidence": "high"
    }
  ]
}
```

## 对齐验收

必须抽检：

- 开头 30 秒。
- 中段 30 秒。
- 结尾 30 秒。
- 至少 5 个角色切换点。
- 至少 5 条包含数字、英文缩写、人名或专有名词的 cue。

`subtitle_alignment_report.md` 必须记录：

- 使用了哪种对齐方法。
- 是否用了 ASR/forced alignment。
- 是否应用全局提前量。
- 抽检位置。
- 是否发现字幕晚于语音。
- 是否有过长 cue、三行 cue、遮挡章节卡片文字。

## Gate

通过条件：

```text
video/final_subtitles.srt exists
video/final_subtitles.ass exists
video/subtitle_manifest.json exists
video/subtitle_alignment_report.md exists
subtitle_manifest records script_hash, audio_hash, dialogue_timeline_hash
all cues have monotonic start_sec/end_sec
no cue has start_sec >= end_sec
dialogue_timeline matched_script_ratio >= 0.95
no trailing low-confidence script tail or compressed end-of-audio cue cluster
speaker labels are not displayed
cue display_text is one visible line by default; no automatic wrapping into two lines
subtitle_manifest.timing_policy.status == PASS
subtitle_manifest.timing_policy.global_lead_sec >= 0.08
subtitle_manifest.timing_policy.late_start_violation_count == 0
subtitle_manifest.timing_policy.lead_applied_per_split_cue == true
subtitle_manifest.segmentation_policy.status == PASS
subtitle_manifest.segmentation_policy.hard_width_fallback_count == 0
subtitle_manifest.segmentation_policy.line_violation_count == 0
subtitle_manifest.segmentation_policy.dangling_fragment_violation_count == 0
style matches 4K burned subtitle requirements
subtitle style records font_family=NotoSansCJKsc-Bold and font_file=/Volumes/GT34/Downloads/podcast_visual_style_prototypes/fonts/NotoSansCJKsc-Bold.otf
style records letter_spacing_px, default 6, and the rendered subtitle overlay uses light tracking
style explicitly disables subtitle background boxes and black outline; only soft_drop_shadow is allowed
subtitle style records subtitle_block_top_min_y=1904, subtitle_block_top_max_y=1974, subtitle_block_bottom_max_y=2044
subtitle text does not display sentence periods
subtitle text uses Chinese source names for confirmed publication; no raw English publication remains in subtitle_manifest/SRT/ASS
every cue maps to source_turn_id or source_cue_index from dialogue_timeline
spot checks show subtitles are simultaneous with or slightly earlier than speech
no systematic late subtitles
no cue is a dangling fragment or an obviously cut phrase
```

如果发现字幕明显晚于语音，先修字幕，不要进入视频合成。
