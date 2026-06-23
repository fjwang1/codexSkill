---
name: worldview-china-node-acceptance
description: "用于 Worldview China Video Agent 每个生产节点的独立验收：选题、素材准备、原声音频锚点、配音段、TTS 对齐、字幕、最终合成等节点完成后，必须由无上下文评测 agent 按本 skill 判断是否可进入下一节点，并在失败时给出回滚目标。"
---

# Worldview China 节点验收

本 skill 只负责单个节点验收，不负责生产、修复、下载、TTS、合成或最终成片验收。

每个节点完成后，执行 agent 必须新开一个 `fork_context=false` 评测 agent，传入本 skill、节点目录、上游 manifest 和本节点产物路径。评测 agent 不能修改任何产物，只能写验收报告和结构化结论。

最终成片还必须额外使用：

```text
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-dubbing-video-acceptance/SKILL.md
```

节点验收 PASS 只表示可以进入下一节点，不等于最终视频可交付。

## 输入

```json
{
  "run_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}",
  "node_id": "01-topic-selection | 02-media-preparation | 03-audio-anchors | 04-voiceover-segments | 05-tts-alignment | 06-subtitles | 07-final-composition",
  "node_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/{node_id}",
  "upstream_manifest_paths": [],
  "artifact_paths": [],
  "output_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/{node_id}/qa"
}
```

## 输出

必须写入：

```text
qa/node-acceptance-report.md
qa/node-acceptance-result.json
```

`node-acceptance-result.json` 最小结构：

```json
{
  "node_id": "03-audio-anchors",
  "decision": "PASS | NEEDS_FIX | FAIL",
  "rollback_to_node": "03-audio-anchors",
  "blocking_reasons": [],
  "warnings": [],
  "checked_artifacts": [],
  "next_node_allowed": false
}
```

规则：

- `PASS`：本节点产物完整、可追溯、满足进入下一节点的最低要求；可以带非阻塞 `warnings`。
- `NEEDS_FIX`：产物缺证据、缺 manifest、覆盖范围不完整或存在可修复问题；不得进入下一节点。
- `FAIL`：存在明确错误、错误事实、不可读文件、错位、旧产物污染或违反硬规则；不得进入下一节点。
- 只要问题会影响下游质量、证据链、锚点对齐、字幕可读性、音色一致性或最终交付可信度，就不能放在 `warnings`，必须输出 `NEEDS_FIX` 或 `FAIL`。
- `rollback_to_node` 必须是当前节点或更早节点。若根因来自上游，必须指向最早需要重做的节点。
- 评测 agent 不能写“人工复核”作为唯一动作。需要复核时，应给出 AI 可执行的检查或回滚目标。

## 节点通用检查

每个节点都必须检查：

- 节点目录存在，产物都在该节点目录或明确的上游目录中。
- `run_dir` 必须位于 `/Volumes/GT34/Generated/world_and_china/` 下，目录名必须匹配 `{YYYYMMDD}_{N}`，例如 `20260605_0`。
- 除了 skill 文件、历史文件 `/Volumes/GT34/Generated/world_and_china/final-videos.json` 和明确声明的只读缓存，本轮中间产物和最终产物都必须在当前 `run_dir` 内。
- 关键 JSON/Markdown/SRT/VTT/MP4/WAV/M4A 文件可读。
- manifest 路径指向当前 run，而不是旧 run 或缓存临时目录。
- 没有把局部片段或未完成产物冒充正式完整视频。
- 没有复用被判失败的旧 draft、旧 overlay、旧字幕、旧 final mp4。
- 节点 QA 报告中有足够路径证据，不只写口头保证。

## 01-topic-selection

验收目标：确认选题可以直接进入素材准备。

必须检查：

- `00-reminder-read/reminder-read.json` 存在，证明本轮开始前已读取 reminder。
- 存在 `best_video`，且来自 `accept`。
- `content_score >= 8`，并包含四项内容评分：`china_relevance`、`foreign_perspective`、`insight_density`、`angle_novelty`。
- 存在 `ranked_shortlist` 或等价审计记录，说明为什么选择第一名、为什么未选其他高分候选。
- 通过硬过滤：发布时间窗口、10 分钟到 30 分钟、横向长视频。
- 已读取并过滤 `/Volumes/GT34/Generated/world_and_china/final-videos.json` 中最终使用过的视频。
- 字幕或 ASR/缓存文本存在；没有文本依据的候选不得被选为 `best_video`。

失败回滚：

- 无 `accept`：`rollback_to_node = "01-topic-selection"`，扩大或更换关键词。
- `best_video` 已在历史中：`rollback_to_node = "01-topic-selection"`。
- 文本评分缺失或分数低于阈值却被选中：`rollback_to_node = "01-topic-selection"`。

## 02-media-preparation

验收目标：确认源视频、源音频、字幕、缩略图和素材 manifest 可供后续处理。

必须检查：

- `source.mp4` 存在且 `ffprobe` 可读。
- `source.wav` 存在且可读，推荐单声道 WAV。
- `media_manifest.json` 存在，记录 URL、video_id、视频路径、音频路径、缩略图路径、元信息路径。
- 正式生产目标高度优先 2160p；如果降级，manifest 必须记录原因和授权。
- 字幕成功时 JSON/TXT 都存在；失败时 manifest 有失败原因，不伪造字幕。
- 复用已有素材时，manifest 的分辨率和流信息来自现场 `ffprobe`，不是旧推断。

失败回滚：

- 下载素材不可读或低清误用：`rollback_to_node = "02-media-preparation"`。
- 选题 URL 错、视频不可用、不是长横视频：`rollback_to_node = "01-topic-selection"`。

## 03-audio-anchors

验收目标：确认原声音频锚点是可信时间线来源。

必须检查：

- `audio-semantic-turns.md` 或章节锚点文件覆盖本次处理范围。
- 状态已从草稿修订为 `llm_revised` 或有等价明确说明。
- 时间来源是原声音频 ASR word timestamps，不是 YouTube 字幕段时间。
- 文本来源明确：字幕、上下文、屏幕硬字幕或人工/LLM 校正说明。
- 品牌、产品、人物、关键数字、年份、金额、百分比、屏幕文字等高风险项有锚点或明确降级说明。
- 明显画面转场只在“语义转场候选 + 视觉变化证据”同时成立时升级为 hard anchor。
- 数字、线路号、站数、屏幕文字等已优先用画面硬字幕/关键帧复核；ASR 冲突必须有校正说明。

失败回滚：

- 锚点来自字幕时间戳：`rollback_to_node = "03-audio-anchors"`。
- 原声 ASR 不可用或源音频错误：`rollback_to_node = "02-media-preparation"`。
- 发现选题内容和主题不符：`rollback_to_node = "01-topic-selection"`。

## 04-voiceover-segments

验收目标：确认中文配音段可以进入 TTS。

必须检查：

- `voiceover-segments.json` 可解析，顶层 `schema_version = voiceover-segments.v1`。
- `segmentation_mode = audio_semantic_anchor`，`time_allocation_mode = original_audio_word_anchor`。
- 每段 `segment_id` 非空、唯一、稳定。
- `start < end`，全片时间单调不重叠。
- 每段只说本时间窗内的信息，硬锚点词没有提前到前一段。
- `must_align` 段有 `anchor_checks`，包括 `source_anchor_start_sec`、`effective_not_before_sec`、`target_terms`。
- 高风险事实、数字、线路号、屏幕文字已与锚点文件一致。
- `voice_text` 是可直接送入中文 TTS 的中文口播正文。除品牌、产品、人名、地名、节目名、单位、URL 或行业术语外，不得残留未翻译英文句子或连续英文短语。
- `voice_text` 必须是可以独立朗读的完整观众句或完整短语组。正式段不得以逗号、顿号、冒号、分号、连接词、时间状语或让人等待下一段补完的半句结尾；否则必须 `NEEDS_FIX`。
- `voice_text` 不能是 ASR 退化文本、断裂句、低信息废句或明显错词的中文化。若正文只有异常短碎片、孤立连词/代词/系动词、半句话、语义不完整表达，或与字幕/上下文明显冲突，必须 `NEEDS_FIX` 或 `FAIL`，并回滚到 `04-voiceover-segments` 修正文本。短窗口也要检查；不能只因为窗口短就放行没有观众信息量的 TTS 段。
- 若 03 标注 `Use ASR word time; correct wording against transcript before 04`，评测时必须把 ASR 当时间草稿而不是事实来源。formal `voice_text` 若与 02 plain subtitle、03 revised/corrected text 或相邻上下文冲突，或包含明显 ASR 词义误译、重复 stutter 直译、荒谬中文搭配，必须 `NEEDS_FIX` 或 `FAIL`。
- 如果某个低信息碎片已修复，必须抽查相邻时间窗是否存在同类 ASR 噪声簇。只把一个碎片移入 `non_voice_ranges[]`，但周边同类碎片仍留在正式 `segments[]`，不得 PASS。
- `voice_text` 不能是制作说明、流程说明或停顿说明。若正式段中出现“没有新的有效口播信息”“可配音信息”“自然停顿”“过渡停顿”“保留为”“无需口播”“让画面”等观众不应听到的文本，必须 `FAIL`。如果该时间窗确实不应有中文语音，应在 `non_voice_ranges[]` 或 manifest 中记录，而不是放入正式 `segments[].voice_text`。
- 硬锚点段只说本时间窗内的信息；不得把相邻后续窗口的解释、因果、承诺、例子或补充事实提前塞进当前硬锚点段。
- 同一个 `source_anchor_id` 不得在最终全片 `segments[]` 中物化为多个正式 `must_align` 口播段。章节边界重复锚点必须在全片合并时去重，不能制造重复口播或时间重叠。
- preflight 阻断项为空：`missing_anchor_checks`、`invalid_anchor_checks`、`blocking_unlisted_high_risk_terms`、`blocking_untranslated_source_text`、`blocking_low_information_or_asr_noise`、`over_window_content_risks`、`duplicate_materialized_source_anchor_ids`、`timeline_overlaps`、`early_risk_terms`。
- 每个 04 preflight 必须证明它对应当前现场 `voiceover-segments.json`：`attempt`、`voiceover_segments_sha256` 和 `segment_count` 必须与当前文件一致。若 preflight 指向旧 attempt、旧 sha 或旧段数，即使阻断列表为空也必须 `FAIL`。
- 若 eval-request、manifest 或 artifact list 包含章节 checkpoint，必须确认 checkpoint 与当前现场 `voiceover-segments.json` 一致：attempt 相同，对应章节的正式 segment 序列相同，关键 `voice_text` 相同。旧 attempt checkpoint 或与当前全片不一致的 checkpoint 不得 PASS。
- 若采用批次写稿/批次 TTS 诊断流程，必须检查 `04-voiceover-segments/batches/` 或等价批次目录：每个批次有 preflight、attempt、segment 范围和当前 `voiceover-segments.json` 的一致性证据。必须存在 `batch-index.json` 或等价索引，记录 batch sha、diagnostic sha、decision、segment_id 列表和合并后的全片 sha。批次合并后的全片文件不得遗漏、重复或改写已通过批次的 segment。

失败回滚：

- 中文稿词序导致硬锚点无法卡点：`rollback_to_node = "04-voiceover-segments"`。
- 缺失或错误锚点导致无法写段：`rollback_to_node = "03-audio-anchors"`。
- 发现素材/字幕文本不对：`rollback_to_node = "02-media-preparation"`。

## 05-tts-alignment

验收目标：确认中文 TTS 和段级对齐可以供字幕与合成使用。

必须检查：

- `tts/manifest.json` 存在且 `mode = voice_clone_only`。
- manifest 记录同一个 `ref_audio_path`、`ref_audio_sha256`、`ref_text_sha256`、`model_dir`。
- 没有混用预设 voice、多个 reference audio、多个模型目录或旧 draft。
- `diagnostics/hard-anchor-duration-diagnostics.json`、`diagnostics/batch_*/hard-anchor-duration-diagnostics.json` 或等价时长适配诊断存在；它必须使用同一个 `voice_profile` 和正式 TTS 参数，覆盖全部 `must_align` 段，并记录普通段抽样。
- 若采用批次诊断，必须存在批次索引或可从诊断文件推导出完整覆盖：所有已进入正式 `voiceover-segments.json` 的 `must_align` 段都属于某个 PASS 批次；失败批次不得混入正式全片 TTS。批次诊断的 `source_segments_sha256` 可以绑定 batch 文件，但必须能通过 `batch-index.json` 映射到最终全片 `voiceover-segments.json` 的 sha。
- 时长适配诊断必须可审计：顶层 `attempt`、`source_voiceover_attempt`、`source_segments_sha256`、`decision`、`overall_pass`、`pass_count`、`segment_pass_rate`、`min_segment_pass_rate`、`failed_count`、`failed_segment_ids`、`segment_count`、`must_align_count`、`normal_sample_count` 必须完整；每个诊断段必须包含当前正式 `voice_text` 和各项时长指标。若诊断字段缺失、为空或绑定到旧 04 attempt，不得 PASS。
- 时长适配诊断整体通过标准是 `segment_pass_rate >= 0.90` 且 `decision = PASS`。少数段级失败可以作为 warning 放行，但必须出现在 `failed_segment_ids` 或 `tolerated_failed_segment_ids` 中；不得隐藏为 `None`。
- 如果诊断发现中文稿系统性缩水，导致 `segment_pass_rate < 0.90`，正式全片 TTS 不应存在；正确状态是回滚到 `04-voiceover-segments`，而不是继续用长静音或临时候选文本生成正式音频。
- `segment-aligned-audio/manifest.json` 覆盖所有 segments。
- 对齐未修改 `voiceover-segments.json` 的原声 `start/end/target_duration_sec`。
- `max_tempo_factor <= 1.15` 是段级失败标记阈值；节点是否继续由 `segment_pass_rate >= 0.90` 决定。
- 单段尾部静音一般 `<= 1.5s`；超过阈值必须有处理建议，整体通过率达到 90% 时可以作为 warning 放行。
- draft 太短时，修复路径是补稿/重分段/重生成，不是改时间线或硬补长静音。

失败回滚：

- 音色克隆证据缺失或混音色：`rollback_to_node = "05-tts-alignment"`。
- TTS 太短来自中文稿缩水：`rollback_to_node = "04-voiceover-segments"`。
- 锚点窗口设计错误导致无法对齐：`rollback_to_node = "03-audio-anchors"`。

## 06-subtitles

验收目标：确认中文字幕可读、无标点、与配音段和锚点同源。

必须检查：

- SRT 和 VTT 都存在且可解析。
- 字幕正文无显示标点；SRT 时间码和序号不算正文。
- 字幕正文不得含替代字符、缺字方框、乱码占位符或明显异常字形风险字符；如果用户或抽帧证据指出某个汉字显示像半乱码，应回到 `06-subtitles` 改写该 cue 文本或拆分字幕，不能只按“UTF-8 文本正常”放行。
- `subtitle-timeline-report.json` 存在且 `decision = PASS`。
- 单条 cue 时长 `<= 8s`，可见文本 `<= 48` 字。
- 每个有口播的 segment，首条 cue 延迟 `<= 0.8s`，segment 内字幕空窗 `<= 1.2s`。
- 硬锚点 cue 不早于或晚于原声/视觉锚点超过阈值。
- 字幕不是“一段一个 cue”的粗字幕。

失败回滚：

- 标点、cue 太长、字幕空窗、乱码占位符或字形显示异常：`rollback_to_node = "06-subtitles"`。
- 字幕无法卡点是因为 segment 过粗或词序错误：`rollback_to_node = "04-voiceover-segments"`。
- 锚点定义错误：`rollback_to_node = "03-audio-anchors"`。

## 07-final-composition

验收目标：确认最终合成产物可交给最终成片验收。

必须检查：

- `final.zh-voiceover.subtitled.mp4` 存在且现场 `ffprobe` 可读。
- MP4 有视频流和中文音频流，原声默认静音。
- 最终 MP4 由临时文件验证后原子 rename，不是边写边覆盖的坏文件。
- `render_manifest.json` 存在，最终文件大小、时长和流信息与现场 `ffprobe` 一致。
- 正式交付必须记录并满足 `render_manifest.json.playback.speed == 1.15`。
- 最终 MP4、交付目录里的中文音频、烧录字幕和交付 SRT/VTT 必须处于同一条 1.15 倍交付时间线；最终时长应约等于 `min(source_duration, voiceover_duration) / 1.15`。
- 如果输入 SRT 是原始时间线，最终交付 SRT/VTT 必须是等比例缩放后的交付时间线，且 manifest 必须记录 `input_timeline`、`final_timeline`、输入 hash、最终 hash 和 overlay 来源 hash。
- 最终 SRT/VTT、overlay 来源 SRT、render manifest 中的 SRT hash/cue hash/cue count 同源一致。
- 从最终 MP4 现场抽帧能看到当前版本字幕，不是旧 overlay 字幕。
- 关键帧里的中文字幕必须字形完整、可辨认；不能出现单个汉字笔画残缺、像半乱码、缺字方框、替代符号或异常字体 fallback。若抽帧发现此类问题，不能判 PASS，应回滚到 `06-subtitles` 改写该 cue 或到 `07-final-composition` 更换字体并重烧字幕。
- 封面存在，分辨率至少 1280x720，默认不含“中文配音版”等多余说明行。
- 检查片段和关键帧存在。
- TTS 克隆证据已写入 render manifest 或 QA。

失败回滚：

- MP4 不可读、缺流、manifest 不一致：`rollback_to_node = "07-final-composition"`。
- 正式交付未统一执行 1.15 倍加速，或最终视频、交付音频、烧录字幕、交付 SRT/VTT 时间线不一致：`rollback_to_node = "07-final-composition"`。
- 烧录旧字幕或字幕不同源：`rollback_to_node = "06-subtitles"`，必要时清空合成 overlay 缓存。
- 烧录字幕出现字形残缺、半乱码或字体 fallback 异常：优先 `rollback_to_node = "07-final-composition"` 更换字体重烧；若只需避开某个显示风险字或改写 cue 文本，则 `rollback_to_node = "06-subtitles"`。
- 中文音频不合格：`rollback_to_node = "05-tts-alignment"`。
- 画面/锚点错位：`rollback_to_node = "04-voiceover-segments"` 或更早。

## 报告要求

报告必须写清：

- 检查了哪些文件。
- 哪些 gate PASS。
- 哪些 gate FAIL 或 NEEDS_FIX。
- 是否允许进入下一节点。
- 如果失败，`rollback_to_node` 是哪里，为什么不是只重做当前节点。

不要输出“建议人工看看”作为结论。需要判断时，导出检查片段、截图、manifest 摘要或重跑可执行检查。
