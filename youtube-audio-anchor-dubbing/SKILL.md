---
name: youtube-audio-anchor-dubbing
description: "用于把 YouTube 外文讲解视频制作成中文配音版：必须先直接听原声音频/ASR 提取词级语义锚点，再按锚点拆小段生成中文配音稿、TTS、字幕和检查片段。适合字幕时间不准、品牌名、数字、人物、图表和画面转场必须精准对齐的长视频本地化。正式最终合成由 youtube-final-video-composition 负责。"
---

# YouTube 音频锚点中文配音

本 skill 的核心不是“翻译字幕”，而是**复现人工剪辑师的配音对齐流程**：

1. 直接听原声音频，或用 ASR word timestamps，找到真实语义变化点。
2. 按真实锚点拆小段，品牌名、数字、转折词、画面对应词必须卡在正确时间。
3. 如果中文太短，回到该段补回原文事实、因果、例子或过渡，不允许靠长静音糊时间。
4. 对有明确画面对应物的关键词，同时检查视觉锚点，避免语音/字幕已经进入新对象而画面仍停在旧对象。

没有做到这三条，不得进入最终视频合成。

## 已验证成功经验

本 skill 的目标是把既有成功案例中的有效方法沉淀为通用流程，而不是重新发明一套端到端大流程。核心经验是：

- 先用原声音频 ASR 词级时间找到真实语义锚点，而不是相信 YouTube 字幕段起点。
- 按语义锚点和高风险词把配音稿拆成细窗口；品牌、数字、人物、产品、图表、屏幕文字和明显话题转折通常要成为 segment 边界。
- 每个窗口写稿时就带上 `target_duration_sec`、字符预算、硬锚点位置和禁止提前出现的关键词。
- 写完一批窗口后立刻生成局部 TTS draft 并做时长诊断；不要先写完整全片，再到 05 被真实 TTS 整体打回。
- 失败时只修失败窗口的 `voice_text` 或该窗口附近的锚点拆分；除非根因来自锚点错误、ASR 校正错误或窗口设计错误，否则不得回滚整章或整片。
- 已通过 TTS 时长诊断和音色一致性检查的 draft 段应缓存复用；不要因为少数失败段全量重生。
- 全片正式 TTS 只能在所有窗口批次都通过局部真实 TTS 诊断后开始。

这条流程来自“硬锚点拆小段 -> 局部 TTS -> 局部修稿 -> 段级对齐 -> ASR/抽帧复核”的成功路径。该经验可以复用，但不能写入某个视频、品牌或案例的硬编码锚点。

如果本 skill 目录存在脚本，优先使用：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/generate_audio_semantic_turns.py \
  --video-id VIDEO_ID \
  --source-video /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.mp4 \
  --source-transcript /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/subtitles/VIDEO_ID.en.plain.txt \
  --start 00:00:00 \
  --end 00:03:00 \
  --output-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/03-audio-anchors
```

该脚本负责抽取原声音频、运行词级 ASR、列出候选停顿/语义节点/高辨识度锚点，并生成 `audio-semantic-turns.md` 草稿和 `audio-semantic-turns.candidates.json`。脚本产物不是最终判断；LLM 必须通读草稿、外文字幕和必要上下文，修订 ASR 错词、合并误切节点、拆开漏切节点，并标出后续 `voiceover-segments.json` 必须遵守的 `must_align` 锚点。

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/align_draft_segments.py \
  --segments /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-segments.json \
  --draft-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/tts/draft-segments \
  --tts-manifest /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/tts/manifest.json \
  --output-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/segment-aligned-audio \
  --max-auto-tempo 1.15 \
  --max-tail-silence 1.5
```

该脚本只负责把已经生成的逐段 TTS draft 音频对齐到 `voiceover-segments.json` 的锚点窗口，并输出 `segment-aligned-audio/manifest.json`、最终中文音轨、SRT 和 VTT。正式生产必须传入 `tts/manifest.json`，用于证明 draft 段来自同一个原视频音色克隆 profile。它会在 coverage、tempo、尾部静音或克隆证据缺失时直接失败。

## 禁止路径

以下做法直接判失败：

- 用 YouTube 字幕段 `start` 当精确时间线。
- 用缓存字幕时间戳生成 `voiceover-segments.json` 后直接合成。
- 先写整章中文稿，再事后整体拉伸或粗分段。
- 中文 TTS 比目标窗短很多时，直接补 3 秒以上静音。
- 为了让 TTS 通过 coverage/tail silence gate，把 `voiceover-segments.json` 的 `start/end/target_duration_sec` 改成 TTS 实际时长或累加时间线。
- `voice_text` 残留未翻译英文句子或连续英文短语，除非这些词是登记过的品牌、产品、人名、地名、节目名、单位或行业术语。
- 为了中文句子完整，把后一个时间窗的解释、因果、承诺、例子或补充信息提前塞进当前硬锚点 segment。
- 用 `--voice Dylan`、`Vivian` 等固定预设音色替代原视频音色克隆，除非用户明确授权。
- 同一个视频中混用多个音色 profile、多个 reference audio/reference text、多个模型目录或旧 draft 段。
- 高辨识度词提前到前一段，例如在某品牌、人物、国家、数字或图表锚点真实出现前先说出该关键词。
- 有明确画面对应物的关键词提前到对应画面之前，例如品牌、产品、图表、屏幕文字、人物、地点、车辆或设备尚未出现时就先讲出来。
- 输出只给视频，不给锚点证据、字幕、音频 manifest 和 QA。

允许使用字幕的方式有两种：

- 作为**文本权威来源**，用于校正 ASR 错词和补全事实。
- 作为**内容覆盖候选来源**，用于发现 ASR 漏听、漏切、硬字幕翻译和旁白遗漏。

字幕不是精确时间锚点，不能用字幕段起点替代 ASR word timestamp 或视觉锚点；但如果外文字幕、画面硬字幕或源片可见字幕提示某个时间窗存在信息，04 必须给出中文口播覆盖，或写入有证据的 `non_voice_ranges[]`。不能因为 tiny-ASR 没识别到该窗口，就默认它没有内容。

## 输入

必需：

```json
{
  "video_id": "VIDEO_ID",
  "source_video_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.mp4",
  "source_transcript_path": "外文字幕或转写文本",
  "chapter_range": "START-END",
  "output_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/03-audio-anchors"
}
```

可选：

- `voice_clone_reference_audio_path`：10-20 秒干净单人声。
- `reference_text`：参考音频对应原文。
- `existing_audio_semantic_turns_path`：已有锚点报告；如果使用，仍要核查它满足本 skill。
- `visual_anchor_notes`：画面转场或品牌画面备注，只用于复核。

## 输出

在 Worldview China 总控正式流程中，本 skill 的产物必须按节点拆分写入当前 run 目录，不能混放到一个分析目录。跨节点产物集合如下：

```text
03-audio-anchors/audio-semantic-turns.md
03-audio-anchors/audio-semantic-turns.candidates.json
04-voiceover-segments/batches/batch-index.json
04-voiceover-segments/batches/batch_NNN.voiceover-segments.json
04-voiceover-segments/voiceover-segments.json
05-tts-alignment/diagnostics/batch_NNN/hard-anchor-duration-diagnostics.json
05-tts-alignment/tts/manifest.json
05-tts-alignment/tts/voice_profile.json
05-tts-alignment/segment-aligned-audio/manifest.json
05-tts-alignment/segment-aligned-audio/final_voiceover.segment_aligned.m4a
06-subtitles/zh-CN.voiceover.srt
06-subtitles/zh-CN.voiceover.vtt
05-tts-alignment/preview/anchor-check-preview.mp4
05-tts-alignment/qa/alignment-qa-report.md
05-tts-alignment/qa/check-clips/*.mp4
```

本 skill 可以生成 preview 或 check clips 用于锚点检查，但不得把这些预览文件作为正式交付 MP4。正式 `final.zh-voiceover.subtitled.mp4` 只能由 `youtube-final-video-composition` 生成。

## Workflow

```text
抽取原声音频
-> ASR word timestamps
-> 脚本生成 audio-semantic-turns.md 草稿
-> LLM 基于字幕/上下文修订锚点草稿
-> 用字幕/上下文校正 ASR 错词
-> 写正式 audio-semantic-turns.md
-> 按 2-12 秒细语义窗口生成 voiceover-segments 批次
-> 为每个窗口写 target_duration_sec、字符预算、must_align 锚点和禁止提前词
-> 对当前批次做 preflight：事实覆盖、锚点顺序、跨窗提前、低信息噪声、源字幕/ASR 覆盖缺口
-> 从原声音频裁取参考人声并生成 voice_profile.json
-> 使用同一个 voice_profile 对当前批次生成真实 TTS draft
-> 对当前批次运行 duration-fit diagnostics
-> 若失败，只修失败窗口或相邻锚点拆分，再局部重跑该批次
-> 当前批次通过后冻结其 voice_text、draft hash 和诊断证据
-> 所有批次通过后汇总正式 voiceover-segments.json
-> 生成全片正式 TTS draft，复用已通过且 hash 一致的 draft 段
-> 带 TTS manifest 逐段 pad/atempo 对齐
-> 生成中文音频和中文字幕
-> 生成锚点检查片段或预览
-> 对关键锚点片段做 ASR QA
```

## 1. 原声音频锚点

先抽取处理范围内原声音频：

```bash
ffmpeg -y -v error -ss START -to END -i source.mp4 -vn -ar 16000 -ac 1 source_audio.16k.wav
```

再做带词级时间戳的 ASR。优先使用脚本完成抽音频、ASR 和锚点草稿生成：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/generate_audio_semantic_turns.py \
  --video-id VIDEO_ID \
  --source-video source.mp4 \
  --source-transcript transcript.txt \
  --start START \
  --end END \
  --output-dir run_dir
```

如需手动运行 ASR，可使用：

```bash
uvx --from mlx-whisper mlx_whisper source_audio.16k.wav \
  --word-timestamps True \
  --output-format json \
  --output-dir asr
```

ASR 使用原则：

- 时间来源：ASR word timestamps。
- 文本来源：字幕、描述、上下文、人工复核。
- `whisper-tiny` 只能做时间草稿；错词必须校正。
- 不确定的品牌/数字/术语必须标 `needs_manual_review`。

`audio-semantic-turns.md` 必须记录：

- ASR 模型。
- 时间权威来源。
- 文本权威来源。
- 关键品牌/数字/转折的原声词级时间。
- 关键品牌/产品/图表/屏幕文字/人物/地点/车辆/设备的视觉锚点时间。
- 自动字幕段起点与真实词级时间的差异。
- 对中文配音稿的约束。

### 明显画面转场定义

明显画面转场不是所有镜头切换。只有“语义转场候选”和“视觉变化证据”同时成立，才升级为硬锚点：

```text
明显画面转场 = 1-2 秒窗口内，原声语义进入新对象、新例子、新论点或新对比，同时画面主体、场景、屏幕文字、图表或构图发生可识别变化。
```

执行顺序：

1. 先从 ASR/字幕文本找语义转场候选，例如 `now let's look at`、`but`、`however`、`meanwhile`、`in contrast`、`another example`、`next`，以及中文语义里的“接下来”“但是”“相比之下”“另一个例子”“问题在于”。
2. 只在语义转场候选附近抽帧，不要全片盲扫所有画面变化。默认抽取候选点前后各 2 秒；信息密集处可扩大到前后 5 秒。
3. 视觉变化证据包括：场景切换、画面主体切换、品牌/产品/人物/地点首次出现、屏幕文字/OCR 变化、图表标题或关键数字变化、远景/特写/实拍/动画等构图类型变化。
4. 两者同时成立时，记录为 `visual_transition_anchor` 或 `must_align`；只有轻微 B-roll 换镜头、但旁白还在讲同一语义时，不升级为硬锚点。
5. 如果视觉锚点晚于原声词级锚点，中文关键词通常不得早于视觉锚点；例外只能是原片明确先旁白后切画面，并必须在 notes 中说明。

记录格式建议：

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

如果 `audio-semantic-turns.md` 是脚本草稿，必须在进入下一步前完成 LLM 修订：删除误报锚点，补充脚本漏掉的品牌/数字/观点转折，校正 ASR 错词，并把 front matter 中的 `status` 从 `draft_needs_llm_revision` 改为 `llm_revised`。

长视频处理：

- 可以先生成全片 `audio-semantic-turns.candidates.json`，但它只是候选证据，不是正式锚点。
- 正式生产要按 3-5 分钟窗口或自然章节生成 `audio-semantic-turns.chapter_NNN.md`。
- 每个章节文件必须由 LLM 修订为 `llm_revised`，并列出该章的音频锚点、视觉锚点、文本校正依据和中文配音约束。
- 全片交付时必须有一个总索引 `audio-semantic-turns.md`，列出所有章节文件、覆盖时间范围、ASR 来源和缺口。总索引覆盖不完整时不得进入合成。

schema 示例，以下变量是占位符，不得作为任何真实视频的验证锚点：

```text
某高辨识度词原声词级时间：{SOURCE_ANCHOR_START_SEC}-{SOURCE_ANCHOR_END_SEC}
字幕段起点：{SUBTITLE_SEGMENT_START_SEC}
结论：{SUBTITLE_SEGMENT_START_SEC} 只是字幕段起点，不是该词真实发音点；中文目标词不得早于 {SOURCE_ANCHOR_START_SEC}。
```

## 2. 语义节点拆分

`voiceover-segments.json` 必须使用：

```json
{
  "schema_version": "voiceover-segments.v1",
  "segmentation_mode": "audio_semantic_anchor",
  "time_allocation_mode": "original_audio_word_anchor",
  "time_source": "asr_word_timestamps_plus_transcript_correction"
}
```

每段规则：

- 每段必须有非空、唯一、稳定的 `segment_id`。字段名必须叫 `segment_id`，不能使用 `id`，不能为 `null`，不能依赖数组序号。推荐格式为 `chNNN_segNNN`、`chNNN_anchor_TERM_NNN` 或等价稳定命名。
- `start` / `end` 来自 `audio-semantic-turns.md`。
- 每段必须写 `target_duration_sec`，并与 `end - start` 基本一致。
- 每段建议写 `estimated_cjk_chars`、`char_budget_min`、`char_budget_max` 或等价字段。初始预算可以按当前 TTS/音色经验估算；完成首批 TTS 诊断后，必须用真实 `tts_duration_sec / CJK 字数` 校准后续窗口预算。
- 高辨识度词必须在本段才出现，不能提前到前一段。
- 高辨识度词不仅要在正确的段内，还必须在段内正确位置出现。一个 20 秒段的开头不能先说 5 秒后才出现的品牌、人物、产品、数字或图表关键词。
- 高辨识度词也不能被推迟到后一个窗口。一个 source word anchor 出现在 1804s 的数字，不能为了照顾 1806s 的后续短语而放到 1806s 以后才说或才显示。
- 如果高辨识度词有明确画面对应物，中文关键词不得早于视觉锚点；需要时把“音频铺垫”和“画面关键词”拆成相邻两段。
- 必须保留该窗口内的事实、数字、因果、转折、例子。
- 单段建议 2-12 秒；复杂讲解可以到 20 秒，但必须有明确语义边界。
- 如果某个窗口超过 20 秒，必须说明为什么不能再拆；如果超过 30 秒，默认必须拆分。
- `voice_text` 只包含朗读正文，不含 Markdown、字段名、注释。

### 窗口级写稿闭环

不得先生成完整全片配音稿再等 05 统一打回。正式执行必须按窗口批次闭环：

1. 从 `audio-semantic-turns.chapter_NNN.md` 选择一批连续窗口，通常 3-8 分钟，或 20-40 个 segment。
2. 为该批窗口生成 `voiceover-segments.batch_NNN.json`，每个 segment 都带 `target_duration_sec`、字符预算、`anchor_checks` 和 `voice_text`。
3. 对该批运行 `build_voiceover_preflight.py` 或等价 preflight；必须传入源字幕 JSON，检查源内容窗口是否被该批或已登记 `non_voice_ranges[]` 覆盖。
4. 对该批立即生成真实 TTS draft；使用正式 `voice_profile.json`、正式模型目录和正式停顿参数。
5. 对该批运行 duration-fit diagnostics。通过后才能把该批合并进全片正式 `voiceover-segments.json`。
6. 若失败，只重写失败 segment 或其相邻 1-2 个 segment。不得因为一个批次中少数段失败而重写整章、整片或已通过批次。

批次产物建议放在：

```text
04-voiceover-segments/batches/batch_NNN.voiceover-segments.json
04-voiceover-segments/batches/batch_NNN.preflight.json
04-voiceover-segments/batches/batch-index.json
05-tts-alignment/diagnostics/batch_NNN/tts/manifest.json
05-tts-alignment/diagnostics/batch_NNN/hard-anchor-duration-diagnostics.json
```

批次 PASS 条件：

- preflight 阻断项为空。
- 全部 `must_align` 段真实 TTS 诊断通过。
- 普通段抽样或全量诊断通过；若该批不足 20 段，应全量诊断。
- 失败段修复后，新的批次 attempt 必须重新生成诊断，不能沿用旧诊断。
- 批次合并进全片时，必须保留每个 segment 的 `batch_id`、`batch_attempt`、`voice_text_sha256` 或等价追踪字段。
- `batch-index.json` 必须记录每个批次的文件路径、attempt、batch sha、诊断 sha、decision、segment_id 列表，以及合并后的全片 `voiceover-segments.json` sha。
- 如果批次测试复用旧 run 的素材、锚点、voice profile 或旧稿，只能作为只读 seed/cache。正式 batch、TTS manifest 和 diagnostics 必须绑定当前 run 的锚点文件、voice clone reference 文件和 batch sha；不得残留旧 run 的 `duration_fit_repair.diagnostic_path`、旧诊断路径或旧正式 artifact 路径。
- 对于大体积源视频/源音频，可以用当前 run 内的 symlink 指向只读 media cache，但 manifest 必须声明其角色是 `read_only_media_cache`，且不能把旧 run 的生成产物当作当前正式产物。

只有所有批次都 PASS，才允许生成全片正式 `tts/manifest.json`。

### 段内锚点表

`must_align` 段必须在 `voiceover-segments.json` 中记录段内锚点，不允许只给整段 `start/end`：

```json
{
  "segment_id": "ch001_voice_003",
  "start": "HH:MM:SS.mmm",
  "end": "HH:MM:SS.mmm",
  "sync_priority": "must_align",
  "anchor_checks": [
    {
      "source_anchor_id": "turn_NNN",
      "target_terms": ["BRAND_A", "PRODUCT_TERM_A", "VISUAL_TERM_A"],
      "source_anchor_start_sec": SOURCE_ANCHOR_START_SEC,
      "source_anchor_end_sec": SOURCE_ANCHOR_END_SEC,
      "visual_anchor_start_sec": VISUAL_ANCHOR_START_SEC,
      "effective_not_before_sec": EFFECTIVE_NOT_BEFORE_SEC,
      "expected_chinese_window_sec": [WINDOW_START_SEC, WINDOW_END_SEC],
      "forbidden_before_sec": EFFECTIVE_NOT_BEFORE_SEC,
      "notes": "中文不得在 EFFECTIVE_NOT_BEFORE_SEC 前说出 target_terms 中的硬锚点。"
    }
  ],
  "voice_text": "这里写本时间窗内要朗读的中文内容。"
}
```

规则：

- 每个品牌、产品、人物、国家、关键数字、图表标题、屏幕文字和明显转场词都要有 `anchor_checks`。
- `effective_not_before_sec = max(source_anchor_start_sec, visual_anchor_start_sec)`；没有视觉锚点时使用原声词级时间。
- `voice_text` 的语义顺序必须与 `anchor_checks` 顺序一致。不能把后一个锚点的中文放在前一个锚点之前。
- 硬锚点默认必须成为 TTS segment 边界。若某个硬锚点的 `effective_not_before_sec` 晚于 segment start 超过 `0.8s`，该 `target_terms` 不得出现在这个 segment 的 `voice_text` 里；必须拆出一个从该锚点附近开始的新 segment，或提供最终中文音频 ASR 证据证明该词没有被提前说出。
- 多个硬锚点不应挤在同一个 segment 中。只有当它们属于同一个短短语、彼此间隔 `<=0.8s`、且最终中文音频 ASR 复核通过时，才允许同段保留。人物名、品牌名、年份、数量、金额、地点/机构名列表应拆成多个 TTS segment。
- 如果一个段内包含多个 `anchor_checks`，相邻锚点间隔超过 `3s` 或中间有画面对象切换时，优先拆成多个 segment。确实不能拆时，必须提供 `text_before_anchor` / `text_at_anchor` 说明哪些中文在锚点前、哪些中文从锚点开始。
- 如果一个段内包含品牌、产品、供应商、数字、年份、金额、百分比或图表数值的列表，即使相邻锚点间隔不超过 `3s`，也应优先拆成多个小 segment 或至少多个硬锚点 cue。整串列表不能作为一条长字幕同时显示。
- 硬锚点同时检查提前和延迟。中文语音与中文字幕都应在各自 source word anchor 的 `±0.8s` 内；超过阈值时，回到分段/词序/TTS 修复，而不是靠字幕隐藏、尾部补静音或整体拉伸解决。
- 如果为了中文连贯需要铺垫，只能用不暴露后续关键词的中性表达。例如可以说“接下来另一个例子是...”，不能提前说出后续品牌名或产品名。
- 硬锚点 segment 只能说本锚点窗口内的事实、名词或短句。锚点窗口很短时，不要把后一个时间窗的解释、因果、承诺、例子或完整长句提前塞入；应把锚点段写短，把后续信息放回后续 segment。
- `voice_text` 必须是可直接送入中文 TTS 的中文口播正文。允许保留的拉丁字母只限品牌、产品、人名、地名、节目名、单位、URL 或行业术语，并应在 preflight allowlist/notes 中可解释。若出现未登记的连续英文词组或完整英文句子，必须回稿翻译，不能进入 TTS。
- `voice_text` 必须是可以独立朗读的完整观众句或完整短语组。正式段不得以逗号、顿号、冒号、分号、连接词、时间状语或让人等待下一段补完的半句结尾；如果中文为了锚点必须拆开，也要让每个 TTS segment 自身是可听懂的短句。
- `voice_text` 不得把 ASR 退化文本、断裂句、低信息废句或明显错词物化为正式中文口播。低信息检查不只适用于长窗口；短窗口如果只有孤立连词、代词、系动词、半句话、重复碎片或无法形成观众可理解命题，也不能作为正式 TTS 段。必须回到字幕、上下文、画面硬字幕和相邻 ASR 校正文本。不要把破碎 ASR 逐字翻成中文，也不要把明显错词登记成 non-blocking 术语。
- 03 中标注为 `Use ASR word time; correct wording against transcript before 04` 的文本，ASR 只提供时间，不能作为最终事实文本直接翻译。04 必须优先使用 02 plain subtitle、03 revised/corrected text、画面硬字幕和相邻上下文校正语义；如果 ASR source 与字幕冲突，以字幕/上下文为准。
- `voice_text` 不能包含 ASR 词义误译或荒谬中文搭配。例如把 `physical contact` 误成“实体内容”、把 party 语境误成“聚会高手”、把 ASR stutter 直译成重复中文，都属于 blocking ASR/semantic degradation，必须回 04 修正或转入 `non_voice_ranges[]`。
- 对低信息或 ASR 噪声的修复必须做全局清扫，而不是只修 05 诊断失败的单段。相邻时间窗若出现同一类碎片、重复短句或没有文本依据的微段，应作为一个噪声簇一起合并、改写或转入 `non_voice_ranges[]`。
- `voice_text` 不能包含制作说明或给剪辑/TTS 的指令，例如“没有新的有效口播信息”“可配音信息”“自然停顿”“过渡停顿”“保留为”“无需口播”“让画面”。这些不是观众应该听到的旁白，必须进入 `blocking_low_information_or_asr_noise`。
- 如果某个 ASR 噪声窗口没有字幕、上下文或画面证据可生成观众正文，不能为它编造说明性口播。应把该窗口从正式 `segments[]` 移除并记录到 `non_voice_ranges[]`，或并入相邻真实语义段；`non_voice_ranges[]` 要写明 `reason = asr_noise_no_text_authority | visual_pause | no_speech` 和证据。
- 跨章节边界可能重复包含同一个原声硬锚点。合并全片 `voiceover-segments.json` 时，任一 `source_anchor_id` 只能对应一个正式 `must_align` segment。若同一锚点在两个章节 checkpoint 中出现，保留与 03 全局锚点时间窗一致的一段，删除或降级另一个上下文副本；不能让同一句口播在章节边界重复出现，也不能制造时间重叠。
- `anchor_checks` 缺失、与 `voice_text` 顺序不一致，或关键术语提前/延迟，直接回稿重分段，不得进入 TTS。

### 高风险词 preflight

生成 TTS 前必须跑一次高风险词 preflight，输出 JSON 报告。报告至少包含：

```json
{
  "missing_anchor_checks": [],
  "invalid_anchor_checks": [],
  "blocking_unlisted_high_risk_terms": [],
  "blocking_untranslated_source_text": [],
  "blocking_low_information_or_asr_noise": [],
  "over_window_content_risks": [],
  "duplicate_materialized_source_anchor_ids": [],
  "timeline_overlaps": [],
  "non_blocking_unlisted_terms": []
}
```

分类规则：

- blocking：品牌、产品、人物、公司、关键数字/金额/年份/比例、图表/屏幕文字、明确视觉对象、强转折和本段主题切换词。它们出现在 `voice_text` 中却没有 `anchor_checks` 时，必须补锚点或重分段。
- blocking untranslated source text：`voice_text` 中存在未登记的连续英文词组或完整英文句子。专名和术语可以保留，但必须能解释为什么不翻译。
- blocking low information or ASR noise：源时间窗较长但 `voice_text` 是异常短碎片、半句话、无完整谓语/宾语、明显错词、与字幕/上下文冲突的 ASR 直译，或制作说明/停顿说明。必须回到字幕、上下文、画面硬字幕和相邻 ASR 修正；无可修正文案时，应转成 `non_voice_ranges[]` 或合并到相邻段，不能作为 non-blocking 放行。
- over-window content risks：硬锚点段包含相邻后续时间窗的解释、因果、承诺、例子或补充事实。锚点段的中文不得因为追求完整句而跨窗搬运信息。
- duplicate materialized source anchors：同一个 `source_anchor_id` 在最终全片 `segments[]` 中以多个正式 `must_align` 口播段出现，尤其常见于章节边界。这是 blocking，必须合并或去重。
- timeline overlaps：最终全片 `segments[]` 任意相邻段 `next.start < previous.end`。这是 blocking，即使各章节内部都通过也不能进入 TTS。

每次 04 重新生成、回滚修复、删除/新增/改写任意正式 `segments[]` 或 `non_voice_ranges[]` 后，必须重新生成全片 manifest 和全部 preflight。每个 preflight 都必须记录当前 `voiceover-segments.json` 的 `attempt`、`voiceover_segments_sha256` 和 `segment_count`；三者必须与现场文件一致，不一致时不得进入 TTS。

每次 04 重新生成、回滚修复、删除/新增/改写任意正式 `segments[]` 或 `non_voice_ranges[]` 后，也必须同步重建受影响章节 checkpoint；如果无法可靠判断受影响章节，默认重建全部 `04-voiceover-segments/chapters/chapter_NNN.voiceover-draft.json`。章节 checkpoint 的 attempt、segment 列表和 voice_text 必须与当前全片 `voiceover-segments.json` 对应章节一致。

可先运行确定性 preflight 辅助脚本，再由 LLM/评测 agent 做事实覆盖和跨窗口复核：

```bash
python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/build_voiceover_preflight.py \
  --segments /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-segments.json \
  --output-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments \
  --source-transcript-json /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/subtitles/VIDEO_ID.en.plain.json
```

`source-coverage-preflight.json` 是 04 的阻断 gate：如果 `source_coverage.source_coverage_gaps[]` 非空，说明外文字幕/源内容候选窗口存在超过阈值的未覆盖区间。此时不能进入 TTS；必须补中文口播段，或用源音频/源画面证据把对应窗口登记为 `non_voice_ranges[]`。不能用“ASR 没有 turn”作为放行理由。

### 事实数字和画面硬字幕复核

ASR 对数字、线路号、站数、年份、百分比、金额、单位和专有名词很容易错。生成 `voiceover-segments.json` 前必须把这些高风险事实和原视频画面/硬字幕交叉校验：

- 线路号、车站数、年份、公里数、金额、百分比、楼层、面积、型号等都属于 blocking high-risk terms。
- 如果原视频画面里有硬字幕、图表、屏幕文字或明显数字，它们优先作为文本校正证据；ASR 只能提供时间线草稿。
- 高风险数字/线路号出现在 `voice_text` 中，必须有对应 `anchor_checks` 或在 preflight 报告中说明为什么不是锚点。
- 发现 ASR 和画面硬字幕冲突时，以画面硬字幕/上下文校正后的文本为准，并在 `audio-semantic-turns.md` notes 里记录修正。
- 不能把 ASR 错词直接写进中文配音稿。例如 `Line 8` 不能因 ASR 错读为 `line 15` 而生成“十五号线”；`37 stations` 不能因 ASR 错读而生成“三十座车站”。
- non-blocking：反复出现的背景词或泛称，例如“中国”“美国”“电动车”等，在不是视觉对象、不是转场、不是关键论点切换时，可以不逐次卡点，但必须在 `non_blocking_unlisted_terms` 中说明降级理由。
- 如果同一个词在某处是背景词、另一处是转场或视觉对象，后者仍是 blocking。不要按词面一刀切。

`blocking_unlisted_high_risk_terms`、`blocking_untranslated_source_text`、`blocking_low_information_or_asr_noise`、`over_window_content_risks`、`duplicate_materialized_source_anchor_ids` 和 `timeline_overlaps` 必须为空才能进入 TTS。只有 `missing_anchor_checks=[]` 不够。

还必须输出 `anchor_text_position_preflight`：

```json
{
  "early_risk_terms": [],
  "multi_anchor_segments_requiring_split": [],
  "segments_allowed_by_final_asr": []
}
```

规则：

- 对每个 `anchor_checks.target_terms`，检查它在 `voice_text` 中第一次出现的位置。若按字符比例粗估，该词会早于 `effective_not_before_sec` 超过 `0.8s`，放入 `early_risk_terms` 并回稿拆段。
- 一个 segment 中若存在多个硬锚点，且任意两个 `effective_not_before_sec` 相差超过 `0.8s`，放入 `multi_anchor_segments_requiring_split`。
- `early_risk_terms` 和 `multi_anchor_segments_requiring_split` 必须为空才能进入 TTS；例外只能在最终中文音频 ASR 已证明锚点实际落点正确时记录到 `segments_allowed_by_final_asr`。

品牌名、人物名、国家名、关键数字、图表标题这类高辨识度锚点，通常要拆成相邻两段：

```json
[
  {
    "segment_id": "ch001_anchor_before_brand",
    "start": "HH:MM:SS.mmm",
    "end": "HH:MM:SS.mmm",
    "sync_priority": "must_align",
    "turning_point": "进入品牌例子前的解释：此处不能提前说品牌名",
    "voice_text": "这不是靠一个简单原因就能解释。"
  },
  {
    "segment_id": "ch001_anchor_brand",
    "start": "HH:MM:SS.mmm",
    "end": "HH:MM:SS.mmm",
    "sync_priority": "must_align",
    "turning_point": "品牌名词级锚点",
    "voice_text": "该品牌的关键能力从这里开始说明。"
  }
]
```

视觉锚点规则：

- 对 `must_align` 段和高风险锚点，抽取原视频该锚点前后至少 10 秒的关键帧；信息密集场景建议 1-2 fps。
- 记录画面中首次出现对应对象、图表、屏幕文字、人物或地点的时间。
- 如果原声词级锚点早于视觉锚点，中文关键词通常应以视觉锚点为不得早于的下限；例外只能是原片明显先旁白后切画面，并要在 notes 中说明。
- 如果一个时间窗内出现多个画面对象切换，必须拆分成多个 voiceover segment，不能把后一个对象的中文提前放在前一个画面上。
- 在 `audio-semantic-turns.md` 或 `voiceover-segments.json` 中记录 `visual_anchor_start`、`visual_anchor_evidence` 或等价字段，供最终验收复核。

## 3. 覆盖率和空白门槛

生成 TTS 之前，先做文字覆盖自检：

- 该时间窗原文事实是否都覆盖。
- 是否漏掉数字、品牌、对比、因果、转折、例子。
- 是否把下一时间窗的信息提前。
- 是否存在 `anchor_checks` 里的关键词在 `voice_text` 中提前出现，或顺序与原声/画面锚点不一致。
- 如果一个 segment 的 `voice_text` 中出现了 `anchor_checks` 没列出的高辨识度词，必须补锚点或重分段。

还必须做源内容覆盖 gate：

- 用源字幕 JSON、`audio-semantic-turns.md` / chapter 文件、必要抽帧/OCR 或可见硬字幕，列出所有“可能存在信息”的源窗口。
- `voiceover-segments.json.segments[]` 与 `non_voice_ranges[]` 的时间覆盖必须覆盖这些源窗口；单个未覆盖窗口超过 `2.0s` 默认 FAIL。
- 如果源字幕窗口有旁白、对话、数字、人物关系、任务进展、价值判断、画面硬英文字幕或屏幕文字，必须补中文口播段。中文可以压缩，但不能让最终中文音轨空白。
- 如果窗口只是片头、转场、音乐、建立镜头、重复口头词、无可靠文本权威的 ASR 噪声，才允许进入 `non_voice_ranges[]`；必须写明证据来源和原因。
- plain transcript 可能漏掉源片硬字幕。对最终或 05 中出现的 `>2s` 长静音，必须抽帧复核；如果画面可见英文硬字幕或屏幕文字，也视为源内容窗口，不能只看 transcript/ASR。
- `source-coverage-preflight.json.decision` 必须是 `PASS` 才能进入 TTS。

生成 draft TTS 后，必须检查：

```text
coverage_ratio = draft_duration / target_duration
```

段级失败规则：

- `must_align` 段：`coverage_ratio >= 0.72`。
- 普通段：`coverage_ratio >= 0.65`。
- 段尾补静音 `tail_silence_sec <= 1.5s`。
- 任何段 `tail_silence_sec > 2.0s` 必须标记为段级失败。
- TTS 时长诊断和逐段对齐的整体通过标准是 `segment_pass_rate >= 0.90`。达到 90% 时，节点可以 PASS；失败段必须写入 `failed_segment_ids` / `tolerated_failed_segment_ids`，作为后续抽查和最终 QA 的 warning，不要为了少数边缘段无限回稿。
- 若 `segment_pass_rate < 0.90`，才视为 TTS/对齐节点失败，回到失败段或相邻窗口补稿、重分段或重生成。
- 段间 gap 超过 `1.5s` 必须列入报告；如果 gap 内源 ASR 仍有词，必须回稿或重分段。
- 段间 gap 超过 `1.5s` 时，还必须检查源字幕窗口和抽帧/硬字幕；只检查 ASR 不够。
- 完整中文 voiceover 必须跑全局 `silencedetect=noise=-35dB:d=2.0`。任何 `>2.0s` 静音都必须和源音频/源 ASR 对比。
- 如果源 ASR、源字幕、可见硬字幕或屏幕文字同区间仍有信息，或源音频没有对应长静音，中文 voiceover 静音 `>2.0s` 直接 FAIL。
- 即使每段 `tail_silence_sec <= 1.5s`，只要段尾静音、段间 gap 和 TTS 内部停顿叠加导致全局静音 `>2.0s`，仍然 FAIL。

如果中文太短：

1. 回到该段原文和锚点。
2. 补回被省掉的事实、原因、例子、限定词或自然过渡。
3. 必要时重分段。
4. 重新生成 draft TTS。

不要用长静音、整章慢放或无意义废话解决。修复全局静音只能补回源文事实、因果、例子、限定词，缩短段窗，或把锚点拆得更细。

### 批次级真实 TTS 时长诊断

正式全片 TTS 前不得只做一次“小规模诊断”然后赌全片通过。必须对每个已写稿批次做真实 TTS 时长诊断：

- 使用正式 `voice_profile.json`、同一个模型目录和同一套生成参数。
- 每个批次必须覆盖该批全部 `sync_priority=must_align` 段；同时抽取普通段，覆盖短段、长段、数字密集段和普通叙述段。
- 若批次 segment 数少于 20，普通段也应全量诊断；若批次较大，普通段抽样不得少于 5 个。
- 诊断 subset JSON 的 `segments[]` 必须按 `start_sec` 从小到大排序；即使先选出全部 `must_align` 再追加普通抽样段，写入文件前也必须重新排序。TTS 脚本会拒绝时间重叠或乱序 subset，不能把该错误当成稿件问题。
- 输出批次诊断文件，例如 `05-tts-alignment/diagnostics/batch_NNN/hard-anchor-duration-diagnostics.json`。全片汇总诊断可以存在，但不能替代批次诊断。
- 诊断 draft TTS 生成完成后，必须立即用固定脚本从本次 subset 和本次 TTS manifest 生成标准诊断 JSON；不得手写残缺 JSON，也不得沿用上一 attempt 的 `hard-anchor-duration-diagnostics.json`：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/build_duration_fit_diagnostics.py \
  --subset /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/diagnostics/batch_NNN/duration-fit-subset-attemptN.voiceover-segments.json \
  --manifest /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/diagnostics/batch_NNN/tts-duration-fit-drafts-attemptN/manifest.json \
  --output /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/diagnostics/batch_NNN/hard-anchor-duration-diagnostics.json \
  --attempt N \
  --source-voiceover-attempt CURRENT_04_ATTEMPT \
  --source-segments-sha256 CURRENT_BATCH_OR_FULL_VOICEOVER_SEGMENTS_SHA256 \
  --min-segment-pass-rate 0.90
```

- 批次诊断发生在全片汇总前时，`source_segments_sha256` 可以是该批 `voiceover-segments.batch_NNN.json` 的 sha；汇总后必须在 `batch-index.json` 中把批次 sha 映射到最终全片 `voiceover-segments.json` sha。
- `hard-anchor-duration-diagnostics.json` 必须可审计：顶层必须填 `attempt`、`source_voiceover_attempt`、`source_segments_sha256`、`decision`、`overall_pass`、`pass_count`、`segment_pass_rate`、`min_segment_pass_rate`、`failed_count`、`failed_segment_ids`、`tolerated_failed_segment_ids`、`segment_count`、`must_align_count`、`normal_sample_count`；每个诊断段必须包含 `segment_id`、`sync_priority`、`target_duration_sec`、`tts_duration_sec`、`coverage_ratio`、`tail_silence_sec`、`tempo_factor_if_compressed`、`gate_flags`、`pass` 和当前正式 `voice_text`。如果这些字段缺失、为空或与当前批次/04 attempt 不匹配，05 必须视为自身审计失败，不能进入全片 TTS，也不能把该诊断当作可信回滚依据。
- 若批次或全片诊断 `segment_pass_rate < 0.90`，必须停止该批次合并，回到失败 segment 或相邻窗口补稿或重分段；若 `segment_pass_rate >= 0.90`，可以合并并继续，少数失败段进入 warning 清单。
- 批次失败时，优先操作顺序是：先补回该窗口漏掉的事实/限定/因果；仍太短则拆小或合并相邻真实语义；太长则删冗余表达；最后才考虑调整锚点边界。不得先改原声时间线。
- 诊断候选文本只能用于判断补稿方向，不能直接在 05 冒充正式稿。任何 `voice_text` 内容修改都必须写入新的 04 attempt，并重新通过 04 节点验收。
- 某批诊断通过后，冻结该批通过段的 `voice_text_sha256`、draft 音频 hash、TTS manifest hash 和诊断结果。
- 所有批次诊断通过后，才能生成全片正式 `tts/manifest.json` 和 `segment-aligned-audio/manifest.json`。
- 诊断 draft 可以复用为正式 draft 的唯一条件：voice profile、模型、生成参数、`voice_text_sha256`、segment_id 和目标窗口完全一致；否则必须重生该段。

## 4. TTS 与段级对齐

正式生产必须使用原视频音色克隆：

- 从同一个 `source_audio_path` 或 `source_video_path` 的原声音轨中选取 10-20 秒干净单人声作为 `reference.wav`，可接受 5-30 秒。
- 参考文本必须来自同一时间段的字幕、ASR 或人工校正文本，保存为 `reference_text.txt`。
- 生成 `tts/voice_profile.json`，至少包含 `mode: voice_clone_only`、`model_dir`、`ref_audio_path`、`ref_audio_sha256`、`ref_text_path`、`ref_text_sha256`、`reference_time_range`。
- `ref_text_sha256` 默认表示实际送入 TTS 的规范化参考文本 hash，也就是去掉首尾空白后的 UTF-8 文本。若参考文本来自文件，manifest 还应记录 `ref_text_file_sha256` 和 `ref_text_hash_mode`；验收时不要把文件末尾换行造成的原始文件 hash 与规范化文本 hash 混为一谈。更稳妥的做法是让 `reference_text.txt` 不带多余尾部空白。
- 全片和所有局部修复段必须复用同一个 `voice_profile.json`。如果 reference、模型或参数变化，旧 draft 段全部作废，必须重跑。
- 除非用户明确授权，禁止使用 `--voice Dylan`、`Vivian` 等固定预设音色作为正式产物。
- `segment-aligned-audio/manifest.json` 必须能追溯到 `tts/manifest.json`；缺少 `voice_clone.mode == voice_clone_only` 时不得进入最终合成。

推荐生成顺序：

在当前本机环境中，Qwen3-TTS/MLX 依赖安装在：

```text
/Users/wangfangjia/code/qwen3-tts-apple-silicon-test/.venv/bin/python
```

执行 `generate_continuous_clone_voiceover.py` 时必须优先使用这个解释器或等价的 `QWEN_TTS_PYTHON`；不要使用系统 `python3`，否则会因为缺少 `mlx_audio` 而失败。当前已验证模型目录：

```text
/Volumes/GT34/AI/qwen3-tts-apple-silicon-test-models/Qwen3-TTS-12Hz-1.7B-Base-8bit
```

```bash
/Users/wangfangjia/code/qwen3-tts-apple-silicon-test/.venv/bin/python /Users/wangfangjia/code/worldview-china-video-agent/scripts/generate_continuous_clone_voiceover.py \
  voiceover-segments.json \
  --output-dir tts \
  --model-dir /Volumes/GT34/AI/qwen3-tts-apple-silicon-test-models/Qwen3-TTS-12Hz-1.7B-Base-8bit \
  --ref-audio reference-audio/reference.wav \
  --ref-text-file reference-audio/reference_text.txt \
  --inter-segment-pause-sec 0.15 \
  --force

python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/align_draft_segments.py \
  --segments voiceover-segments.json \
  --draft-dir tts/draft-segments \
  --tts-manifest tts/manifest.json \
  --output-dir segment-aligned-audio \
  --min-segment-pass-rate 0.90 \
  --force
```

每段先生成 draft 音频，再决定对齐方式：

- `draft_duration <= target_duration`：只允许短尾静音。
- `draft_duration > target_duration`：可用 `atempo` 轻微压缩。
- `tempo_factor <= 1.15`。
- 单段超过阈值时标记为失败段；若整体 `segment_pass_rate >= 0.90`，可以作为 warning 放行，不再为少数边缘段无限回稿。
- TTS gate 因整体通过率低于 90% 失败时，`start/end/target_duration_sec` 仍必须保持原声音频锚点来源。只能通过补稿、删改冗余表达、在原声词级锚点上重分段、或重生成 TTS 修复；不能把时间戳改成生成音频长度。
- 如果确实需要拆段，新 segment 的边界必须来自原声音频 ASR word timestamps、停顿或文档化语义锚点，并在 `audio-semantic-turns.md` 中补充依据。

最终音轨必须是**逐段对齐后的 segment-aligned 音轨**。

不要把 `chapter_aligned` 或整章连续音轨当最终音轨，除非它同时满足所有段级 QA。

## 5. 中文字幕

字幕是中文配音字幕：

- 时间线来自最终 `voiceover-segments.json` 和段级音轨。
- SRT/VTT 都要输出。
- 字幕不得早于配音关键词。
- 单条字幕过长时按中文语义和锚点拆分；不能只按 segment 输出一条长 cue。任何 cue 超过 `8s` 或可见文本超过 `48` 字，都必须回到字幕拆分或上游分段修复。
- 屏幕显示字幕不要保留标点符号。`voice_text` 可以保留标点用于 TTS 断句和内部分句，但写入 SRT/VTT、烧录到画面时应去掉逗号、句号、顿号、冒号、分号、问号、感叹号、引号和括号等显示标点。
- 字幕必须跟随中文口播阅读顺序连续显示。不要把 `anchor_checks` 当作字幕排程器；`anchor_checks` 只用于校验高风险词是否提前或错位。
- 同一个 source anchor 时间如果有多个 `target_terms`，字幕排程只需要一个 start 约束；不要把同一锚点里的多个词拆成一串 `0.25s` 微 cue。
- 如果 hard anchor 的 `forbidden_before_sec` 与 segment start 基本相同，说明整个 segment 已经从锚点开始；字幕可以从 segment start 显示正常语义 cue，不要为了目标词位置把“在”“但”“从”等前缀切成单独字幕。
- 正式 SRT/VTT 不得包含单字正文 cue，也不得包含低于 `0.5s` 的正文 cue；如出现，应合并到同 segment 的前后 cue 或回到字幕拆分逻辑修复。
- 对有 `voice_text` 的 segment，第一条字幕 cue 必须在 segment start 后 `0.8s` 内出现，segment 内连续无字幕窗口不得超过 `1.2s`。
- 如果某段字幕整体延迟到段尾，再用一串极短 cue 闪过，这是明确失败，即使音频锚点和容器都正常。
- 如果锚点词在中文稿里出现多次，或是“中国/美国/德国/日本/电动车”等高频背景词，不能用简单字符串匹配来决定字幕时间；应在报告里标记为歧义锚点，并在必要时回到分段、词序或 anchor occurrence 设计修复。

推荐在段级音频对齐后运行：

```bash
python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/generate_voiceover_subtitles.py \
  --segments dubbing/voiceover-segments.json \
  --output-dir dubbing/subtitles
```

`subtitle-timeline-report.json` 中以下字段必须为空，才能进入最终合成：

- `segment_start_delay_violations`
- `in_segment_gap_violations`
- `cue_duration_violations`

`anchor_ambiguities`、`unambiguous_anchor_early_violations` 和 `unambiguous_anchor_late_violations` 是锚点设计风险清单。生成 agent 必须阅读它们；对品牌、产品、人物、关键数字、屏幕文字、视觉对象或用户指定锚点，不能只写“已知风险”，要回到上游修复或拆分。

字幕脚本返回非零或 `subtitle-timeline-report.json.decision != PASS` 时，禁止进入最终合成。最终合成使用的 SRT 必须就是通过该报告校验的 SRT；不能在合成阶段重新写一个每段一条的粗 SRT。

硬锚点和背景锚点要分开处理：

- 硬锚点包括品牌、型号、产品名、金额、百分比、年份、关键数字、屏幕文字、视觉对象和长专有短语。硬锚点字幕 cue 不得早于或晚于原声锚点超过 `0.8s`。
- 背景锚点包括“中国/美国/德国/日本/电动车/电池/充电”等短高频词。它们不能用裸字符串匹配来驱动字幕排程，否则容易把整段字幕推迟到段尾；只用于语义抽查或需要 LLM 消歧时的参考。
- 例外：如果背景词已经出现在 `sync_priority: must_align` 段的 `anchor_checks.target_terms` 中，它就是本段显式硬锚点。字幕生成器必须拆 cue，确保该词不早于 `forbidden_before_sec - 0.8s` 显示。
- 如果硬锚点词在 `voice_text` 开头，但原声 `forbidden_before_sec` 晚于 segment start 超过 `0.8s`，这是配音稿词序问题。必须拆 segment、改写前置句或重新生成该段 TTS，不能用字幕空白、旧字幕延长或段尾闪字幕掩盖。
- 如果硬锚点词的原声锚点早于当前 segment start 超过 `0.8s`，这是分段太晚或词序错误。必须把该词移回对应 source window，并重做受影响段的 TTS、字幕和最终合成。

## 6. 视频合成

合成时：

- 原视频画面保留。
- 原声静音。
- 使用 segment-aligned 中文主音轨。
- 烧录或至少同步生成中文字幕。
- 关键锚点必须导出检查片段。

## 7. QA

QA 报告必须包含四类证据。

机械 QA：

- JSON 合法。
- 时间轴单调不重叠。
- 总时长匹配处理范围。
- 字幕连续性通过：每个有中文口播的 segment 首条 cue 延迟 `<=0.8s`，segment 内无字幕空窗 `<=1.2s`。
- `subtitle-timeline-report.json` 必须存在；`segment_start_delay_violations`、`in_segment_gap_violations`、`cue_duration_violations` 必须为空。
- `subtitle-timeline-report.json` 的 `srt_path` 必须与最终合成使用的 SRT 哈希一致；如果最终 SRT 被覆盖或 cue 数变化，必须重新生成报告。
- `max_tempo_factor <= 1.15`。
- `max_tail_padding_sec <= 1.5s`，不得超过 `2.0s`。
- `tail_over_2_sec` 必须为空。

锚点 QA：

- 至少抽 3 个高风险锚点。
- 对合成后中文音频或检查片段做 ASR。
- 所有硬锚点必须做最终中文音频 ASR 复核；样片验证必须全量复核，完整长视频至少按章覆盖并复核全部高风险硬锚点。列表型硬锚点至少复核列表第一项、中间项和最后一项。只验证 SRT cue 或最终画面字幕不够。
- 关键品牌/画面锚点误差目标 `<= 0.8s`。
- 对每个抽查锚点，必须同时检查 `anchor_checks`、最终 SRT cue、最终音频 ASR 或人工听取结果和关键帧；只检查整段 start/end 不够。
- 如果中文关键词落在同一 segment 内但早于 `effective_not_before_sec`，仍然 FAIL。
- 如果最终 SRT/画面字幕已经按锚点出现，但中文音频 ASR 中关键词仍早于或晚于 source anchor 超过 `0.8s`，必须回到配音稿、分段或 TTS 重生成；不能通过移动字幕掩盖。
- 必须写出证据，例如：

```text
中文关键词出现在检查片段 {CLIP_LOCAL_SEC}s，换算原视频 {FINAL_VIDEO_SEC}s。
目标锚点：{SOURCE_ANCHOR_START_SEC}-{SOURCE_ANCHOR_END_SEC}s。
结论：PASS。
```

空白 QA：

- 对最终中文音轨跑 `silencedetect`。
- 任何非原片静默造成的连续静音超过 `2s` 都必须解释。
- 如果原视频同区间没有长静默，中文配音也不得出现长静默。
- QA 不能只报告单段 tail padding；必须报告完整 voiceover 的 `global_silence_over_2s`。
- 如果源 ASR 同区间有讲话，必须列出对应 segment id、源 ASR 摘要和修复建议，且不得进入最终合成。

视觉 QA：

- 至少输出关键锚点前后 10-30 秒检查片段。
- 需要时抽帧确认品牌/画面转场和中文关键词体感一致。
- 对每个高风险视觉锚点，至少保存关键词前、关键词时、关键词后 3 张帧。
- 如果字幕或语音已经切到新品牌/产品/人物/图表，但画面仍停在上一个对象，必须 FAIL 并回到分段/稿件重写。

## 8. 失败处理

如果 QA 失败：

- 锚点错：重做 `audio-semantic-turns.md`。
- 关键词提前：重写相邻 `voiceover-segments`。
- 中文太短：补回原文事实后重跑 TTS。
- TTS 读错：改写该段或换音色/参考音频。
- 合成错误：只修合成，不改锚点。

失败后丢弃旧输出，按新 skill 重新生成；不要在成片上做不可追溯补丁。

## 交付

交付必须列出：

- 成片路径。
- 中文音频路径。
- SRT/VTT 路径。
- `audio-semantic-turns.md` 路径。
- `voiceover-segments.json` 路径。
- QA 报告路径。
- 关键检查片段路径。
- 关键锚点误差和空白 QA 结果。
