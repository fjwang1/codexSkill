---
name: timed-script-to-voiceover-segments
description: "用于把带时间点的中文口播稿、中文字幕或翻译字幕，按语义完整性拆成适合 TTS 生成和视频合成的配音段。输入通常是 [HH:MM:SS - HH:MM:SS] 中文文本，输出 voiceover_segments JSON，供后续中文配音、时长校验和视频合成使用。"
---

# 时间轴口播稿配音分段

使用这个 skill 将带时间点的中文口播稿或中文字幕拆成适合 TTS 的配音段。

这个 skill 不生成音频，也不直接合成视频。它只负责把已有中文文本整理成稳定的“配音段计划”，让后续 TTS 和视频合成工具可以逐段执行。

## 输入

优先使用带时间点的 TXT/Markdown 文本：

```text
---
video_id: "..."
video_url: "..."
title: "..."
target_language: "zh-CN"
---

[00:00:00 - 00:00:07] 中国电动车已经把竞争对手远远甩在身后。
[00:00:07 - 00:00:15] 它们比保时捷更快，续航也更长。
```

也可以处理 SRT、JSON 字幕或普通口播稿，但如果没有时间点，只能输出语义段落，不能输出可直接合成的视频时间线。

如果输入是章节级中文配音稿，例如每章只有一个 `[HH:MM:SS - HH:MM:SS]` 时间范围，而章内没有逐句小时间点，也可以输出可用于 TTS 的段落计划。但这种情况下，段内 `start` / `end` 是从章节时间范围按语义块和估算口播时长派生出来的，不是原字幕真实小时间点。必须在顶层和每段中显式标注：

```json
{
  "time_allocation_mode": "chapter_proportional_derived",
  "time_source": "derived_from_chapter_range"
}
```

派生时间线只是 provisional allocation，用来安排 TTS 生成和第一版视频合成。它不能被当作源字幕级精确卡点。完成真实 TTS 音频后，必须再根据实际音频时长、章节空白、削波、静音和画面对齐结果进行二次校准。

如果输入保留了原始字幕小时间点，优先沿用真实小时间点，不要退化成派生时间线。

## 输出

默认输出到输入文件附近的 `voiceover-segments/` 目录：

```text
voiceover-segments/{video_id}.zh-CN.voiceover-segments.json
```

输出必须是 UTF-8 JSON。

有两种 schema profile：

- `source_cues`: 输入保留了逐条字幕或逐句时间点，配音段由真实输入时间线合并而来。
- `chapter_derived`: 输入只有章节级时间点，配音段时间由章节范围内的语义块和估算口播时长派生而来。

`source_cues` profile 示例：

```json
{
  "schema_version": "voiceover-segments.v1",
  "video_id": "VIDEO_ID",
  "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "source_script_path": "...",
  "language": "zh-CN",
  "segmentation_mode": "semantic",
  "time_allocation_mode": "source_timeline",
  "time_source": "source_cues",
  "segments": [
    {
      "segment_id": "voice_001",
      "start": "00:00:00",
      "end": "00:00:28",
      "target_duration_sec": 28.0,
      "semantic_label": "开场论点：中国电动车全面领先",
      "voice_text": "中国电动车已经把竞争对手远远甩在身后。\n价格比美国最便宜的电动车，还低几万美元。\n它们比 25 万美元的保时捷 Taycan 更快。",
      "source_time_range": "00:00:00-00:00:28",
      "source_cue_count": 6,
      "estimated_chars": 94,
      "estimated_speech_sec": 22.4,
      "line_count": 3,
      "max_sentence_estimated_sec": 8.2,
      "timing_fit": "ok",
      "time_source": "source_cues",
      "notes": "开场，语气有冲击力但不要夸张。"
    }
  ]
}
```

`chapter_derived` profile 与上面结构相同，但必须使用：

```json
{
  "time_allocation_mode": "chapter_proportional_derived",
  "time_source": "derived_from_chapter_range",
  "segments": [
    {
      "source_time_range": "00:00:00-00:03:17",
      "source_cue_count": 3,
      "time_source": "derived_from_chapter_range",
      "notes": "章节级时间范围内按语义块和估算口播时长比例派生时间点。"
    }
  ]
}
```

在 `chapter_derived` profile 中，`source_cue_count` 表示该配音段合并了多少个口播行或语义行，不表示真实字幕 cue 数量。

## 核心原则

- 以语义完整性拆分，而不是按固定 20 秒、30 秒或固定行数拆分。
- 每段应表达一个完整小论点、例子、转折、广告口播、解释链条或场景。
- 保留原时间线。如果输入有逐句或逐条字幕时间点，配音段的 `start` 和 `end` 必须来自输入时间轴，不能凭空创造时间。
- 如果输入只有章节级时间范围，允许在章节内部派生连续时间点，但只能在该章节 `start` / `end` 范围内分配，不能跨章、重叠或制造总时长变化。
- 派生时间点必须基于语义块的估算口播时长按比例分配，而不是机械平均分配。
- 使用派生时间线时，必须把 `time_allocation_mode` 设为 `chapter_proportional_derived`，并在每段写明 `source_time_range` 为原章节范围。
- 不要把字幕小时间轴丢掉。小时间轴仍是底层参考，配音段只是 TTS 的执行单位。
- 不要为了凑时长硬塞废话；时长不匹配时，优先标记风险，后续再压缩口播稿或调整 TTS。

## 分段策略

不要机械套用固定长度。按以下优先级找边界：

1. 话题切换。
2. 论点完成。
3. 例子结束。
4. 转折词前后，例如“但是”“相比之下”“归根结底”。
5. 广告、片头、片尾、行动号召等内容类型变化。
6. 原字幕中明显停顿或段落结束。

长度规则：

- 常见配音段：10-30 秒。
- 很短的转场、标题、反问：4-10 秒可以接受。
- 单个配音段的 `target_duration_sec` 不得超过 30 秒。
- 如果一个语义单元超过 30 秒，必须拆成多个连续配音段，并用 `semantic_label` 表明它们属于同一论点的不同部分。

对于章节级配音稿，推荐先按正文中的自然换行、段落、转折词和论点推进拆成候选语义块，再根据估算口播时长合并或拆分：

- 优先保留作者已经写出的换气换行。
- 相邻短句属于同一个小论点时可以合并为一段。
- 估算后可能超过 30 秒目标时长的段，必须继续拆。
- 单句过长时，先在中文标点、并列结构或转折词处断句，再考虑拆成多个段。
- 派生出的章节内段落必须首尾相接，第一段从章节开始，最后一段到章节结束。

## 口播文本策略

`voice_text` 不是逐条字幕拼接，也不是重新写一篇稿。

`voice_text` 必须做口播断句。用换行 `\n` 表示自然停顿、换气或语义小停顿。不要把一大段文字塞进一个长句里让 TTS 自己猜停顿。

`voice_text` 应在本阶段尽量整理成 TTS-ready 文本。后续音频生成 skill 可以做机械兜底，但不应该承担内容清洗责任。

TTS-ready 要求：

- 只包含要朗读的正文，不包含 Markdown 标题、front matter、JSON 字段名、注释或校验说明。
- 保留中文标点、数字、品牌名、英文术语和 URL。
- 不要把字面量 `\n` 写进文本；JSON 中的换行应是真实换行。
- 不要在顿号 `、` 后断行，避免后续 TTS 规范化误补句号。
- 不要把专有名词、数字表达、并列短语或 URL 从中间切开。
- 每个口播句尽量以完整句号、问号、感叹号、分号等自然边界结束；逗号处断行可以接受，但必须读起来像自然停顿。

每一行视为一个“口播句”：

- 单行估算口播时长不得超过 30 秒。
- 单行通常控制在 6-15 秒更自然。
- 如果一句话估算超过 30 秒，必须拆成多行；如果拆行后该配音段仍超过 30 秒，必须拆成多个配音段。
- 可以在逗号、分号、转折词、并列结构处断行，但不要破坏专有名词和数字表达。

允许：

- 合并相邻字幕碎句。
- 删除重复口头填充词。
- 调整语序，让中文更适合配音。
- 把过长句拆成更顺的短句。

禁止：

- 摘要替代原内容。
- 删除关键事实、数字、因果关系、转折关系。
- 添加原文没有的新观点。
- 为了填满时间添加空话。
- 输出没有断句的一整段长文本。

## 时长评估

先用粗估，不要冒充真实 TTS 时长。

默认按普通中文解说语速估算：

```text
estimated_speech_sec = 中文字符数 / 4.2
```

其中中文字符数不包含空格和大部分标点。这个数只用于判断风险，真实时长以后必须以 TTS 生成后的音频为准。

`timing_fit` 取值：

- `ok`: 估计口播时长约为目标时长的 70%-105%。
- `short_ok`: 估计时长短于目标时长，但可以通过自然停顿或留原声解决。
- `too_long`: 估计时长超过目标时长 105%，后续应压缩或轻微加速。
- `needs_split`: 单段超过 30 秒、单句超过 30 秒，或信息过密，必须拆分。
- `needs_review`: 时间点、语义边界或文本完整性不确定。

当 `time_allocation_mode = chapter_proportional_derived` 时，`timing_fit` 只表示文本长度与派生目标时长的大致匹配，不代表真实字幕卡点准确。真实对齐必须等 TTS 音频生成后再用音频时长复核；若音频显示章节尾部空白过长、语速需要过度加速，或段落听感不连贯，应回到配音稿或分段计划修正，而不是把派生时间线视为最终答案。

## 处理长视频

长视频可以分批处理，但最终 JSON 必须完整。

推荐方式：

1. 先通读标题、元信息和全文结构。
2. 建立全片章节草图，例如开场、广告、技术解释、案例、结论。
3. 再按章节生成配音段。
4. 每批完成后记录已覆盖到的时间点。
5. 合并后检查时间单调、无重叠、无明显缺口。

可以维护临时进度文件：

```text
voiceover-segments/{video_id}.zh-CN.voiceover-segments.progress.md
```

## 校验

完成后必须检查：

- JSON 可以解析。
- `segments` 非空。
- 每段 `start < end`。
- 段落按时间单调递增。
- 相邻段不重叠。
- 每段 `target_duration_sec` 不超过 30 秒。
- 如果使用派生时间线，顶层必须有 `time_allocation_mode: chapter_proportional_derived`，每段必须有 `time_source: derived_from_chapter_range`。
- 使用派生时间线时，同一章节内第一段必须从章节开始，最后一段必须到章节结束，章节内不能有重叠或缺口。
- 最后一段覆盖到输入字幕最后时间点或明确说明尾部为何不需要配音。
- 每段 `voice_text` 非空。
- 每段 `voice_text` 必须有清晰口播断句；长文本必须使用换行。
- 每段 `voice_text` 必须是 TTS-ready 文本，不含 Markdown/front matter/JSON 字段名/注释。
- 不得包含字面量 `\n`。
- 口播行不得断在顿号 `、` 后，不得把专有名词、数字、URL 或固定短语切开。
- 每个口播句估算时长不超过 30 秒。
- 没有大段外文残留。
- `timing_fit` 对过长段有风险提示。

如果本 skill 目录有 `scripts/validate_voiceover_segments.py`，优先运行它做格式和时间轴校验：

```bash
python3 {skill_dir}/scripts/validate_voiceover_segments.py path/to/voiceover-segments.json
```

## 交付

完成后告诉用户：

- 输出 JSON 路径。
- 源口播稿/字幕路径。
- 一共拆成多少个配音段。
- 平均段长、最长段、需要复核的段。
- 是否通过校验。

不要在最终回答中贴完整 JSON；只给 1-2 个片段样例即可。
