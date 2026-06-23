---
name: youtube-dubbing-video-acceptance
description: "用于验收 YouTube 外文视频中文配音成片：检查中文字幕、中文语音和画面是否按原声音频语义锚点一一对应，检测超过 2 秒的中文静音并由 AI 判定是否合理，评估中文表达是否自然、完整、连贯，最终输出 PASS/NEEDS_FIX/FAIL QA 报告、warnings 和修复建议。"
---

# YouTube 中文配音视频验收

本 skill 只负责验收，不负责选题、下载、翻译、TTS 或合成。它判断一个中文配音视频能不能交付。

如果本 skill 目录存在脚本，优先使用：

```bash
uvx --from resemblyzer python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-dubbing-video-acceptance/scripts/check_speaker_consistency.py \
  --voiceover-audio final/audio/final_voiceover.zh-CN.m4a \
  --segments dubbing/voiceover-segments.json \
  --output-json qa/speaker-consistency.json
```

该脚本用于抽查开头、中段、结尾中文配音段的说话人 embedding 相似度。脚本 `PASS` 不是最终验收 `PASS`，但脚本 `FAIL` 应直接作为同片换人的失败证据。

现场 spot re-ASR 可使用：

```bash
ffmpeg -y -v error -ss START -to END -i source.mp4 -vn -ar 16000 -ac 1 qa/spot-asr/source_anchor.wav
uvx --from mlx-whisper mlx_whisper qa/spot-asr/source_anchor.wav \
  --word-timestamps True \
  --output-format json \
  --output-dir qa/spot-asr
```

`whisper-tiny` 或其他轻量模型只能用于确认时间窗内确实有对应词/语义，不能作为文本权威；文本仍以 `audio-semantic-turns.md`、字幕和上下文校正为准。

核心标准：

1. 字幕、语音、画面必须按原声音频语义锚点对应。
2. 中文配音不能出现不合理长空白。
3. 中文表达必须自然、完整、连贯，符合中国人口播习惯。
4. 屏幕中文字幕正文不得包含显示标点。
5. 屏幕中文字幕必须字形完整、可辨认，不能出现半乱码、缺字方框、替代符号或异常字体 fallback。
6. 同一视频的中文配音必须来自同一个原视频音色克隆 profile，不能出现明显换人。
7. 正式交付必须统一为 `1.15x` 播放速度；最终 MP4、交付中文音频、烧录字幕和交付 `.srt` / `.vtt` 都必须处于同一条 1.15 倍交付时间线。

## 输入

必需：

```json
{
  "source_video_path": "原视频",
  "final_video_path": "中文配音成片",
  "voiceover_audio_path": "中文配音音频",
  "subtitle_srt_path": "中文字幕 SRT",
  "voiceover_segments_path": "voiceover-segments.json",
  "output_dir": "qa/"
}
```

可选：

- `source_audio_path`：当 `source_video_path` 不含原声音频时必需。
- `audio_semantic_turns_path`
- `source_asr_json_path`
- `render_manifest_path`
- `segment_aligned_manifest_path`
- `tts_manifest_path`
- `subtitle_timeline_report_path`

`source_video_path` 必须能代表原视频画面；同时必须存在可用于 ASR 的原声音频。原声音频可以来自 `source_video_path` 自带音轨，也可以来自单独的 `source_audio_path`。如果两者都没有，不能做正式 PASS 验收，只能输出 `NEEDS_FIX` 或在发现明确质量问题时输出 `FAIL`。

## PASS 证据完整性

PASS 不是凭体感判断，而是要证明整条处理时间线可追溯。想判 PASS，必须同时具备三类覆盖完整处理范围的证据：

- `audio-semantic-turns.md`：记录原视频原声音频里的真实语义转折和关键词级锚点。它回答：原视频真实锚点在哪里。
- `voiceover-segments.json`：记录中文配音稿如何按这些锚点分段，每段从几秒到几秒、讲什么、哪些词必须卡点。它回答：中文配音准备怎么贴到原视频上。
- `segment_aligned_manifest_path`：记录每段 TTS 实际生成后多长、是否加速、是否补静音、尾部静音多少。它回答：最终音频实际有没有按计划贴上去。
- `tts_manifest_path` 或 `segment_aligned_manifest_path.voice_clone`：记录 TTS 是否来自同一个原视频音色克隆 profile。它回答：最终音频是不是同一个人声。

“完整处理范围”指本次正式成片要交付的全部主时间线。正式执行必须覆盖整片主时间线，不能只覆盖局部片段。

硬规则：

- 三类证据缺任意一类，不能判 `PASS`。
- 三类证据只覆盖局部时间线，不能判整片 `PASS`，只能输出 `NEEDS_FIX` 或 `LIMITED/WARN` 类有限验收说明。
- 如果证据来自字幕时间戳、缓存字幕时间戳、章节粗时间窗或 `derived_from_chapter_range`，不能作为正式 PASS 证据。
- 如果 `voiceover-segments.json` 或 manifest 出现 `tts_duration_adjusted_timeline`、`source_anchor_start/source_anchor_end` 但 `start/end` 已被改为 TTS 累加时间线，不能判 `PASS`。这是生产流程为了适配 TTS 改写原声锚点，应回到补稿或原声锚点重分段。
- `voiceover-segments.json` 中每段必须有非空、唯一、稳定的 `segment_id`，且 `segment_aligned_manifest_path`、字幕报告和锚点 QA 必须能用同一个 `segment_id` 对上。缺失、空值、重复或只用数组序号追踪时不能判 `PASS`。
- `must_align` 段如果缺少段内 `anchor_checks` 或等价证据，不能判正式 `PASS`；因为整段起止时间不能证明关键词在段内正确位置出现。
- TTS manifest 必须证明 `mode == voice_clone_only`，并记录 `ref_audio_path`、`ref_audio_sha256`、`ref_text_sha256`、`model_dir`。除非用户明确授权预设音色，否则缺少克隆证据不能判 `PASS`。
- 同一成片不能混用多个 `voice_profile`、多个 ref audio/ref text、多个模型目录或旧 draft 段。若 manifest 无法证明单一 profile，不能判 `PASS`。
- 如果生产 QA 或 run manifest 提供高风险词 preflight 报告，`blocking_unlisted_high_risk_terms` 必须为空才能判 `PASS`。没有该报告时，评测 agent 要自行抽查 voiceover 文本中的品牌、产品、人物、关键数字和视觉对象是否有对应 `anchor_checks`。
- 如果已有明确失败项，例如长静音、画面错位或字幕/语音不一致，即使证据不完整，也应输出 `FAIL`，而不是 `NEEDS_FIX`。

## ASR 锚点来源

最终验收优先现场生成或现场复核原声音频 ASR。

允许复用已有 `audio-semantic-turns.md`，但必须同时满足：

- 来自同一个 `source_video_path`、同一个 `video_id`、同一个处理范围。
- 覆盖本次成片的完整处理范围。
- 记录了 ASR 模型、时间来源、文本来源和生成时间。
- 有对应 ASR JSON 或可追溯的 word timestamps。
- 不是字幕时间戳、缓存字幕时间戳或手写粗时间窗。

如果复用已有锚点，验收阶段仍要做 spot re-ASR：

- 至少复核 3 个关键锚点，覆盖开头、中段、结尾或高风险片段。
- 对每个复核片段重新抽原声音频并跑 ASR，确认锚点时间与文档差异 `<= 0.8s`。
- 如果差异超过阈值，旧锚点作废，必须现场重新生成 `audio-semantic-turns.md`。

现场生成的好处是可以做两轮校验：

1. 第一轮：生成锚点和初步 QA，定位错位、长空白、漏译、表达问题。
2. 修复后第二轮：只复核失败窗口和关键锚点，确认成片可交付。

## 验收流程

```text
准备输入文件
-> 检查原声音频是否存在
-> 检查 PASS 所需三类证据是否覆盖完整处理范围
-> 检查 TTS 克隆 profile 和同片音色一致性证据
-> 现场生成或复核 audio-semantic-turns.md
-> 检查 voiceover-segments 是否来自原声音频锚点
-> 检查 segment manifest 是否证明每段 TTS 已按锚点窗口对齐
-> 检查最终 MP4 烧录字幕是否与交付 SRT/VTT 同源
-> 检查正式交付是否统一为 1.15x 时间线
-> 检查中文字幕正文是否无显示标点
-> 抽帧检查中文字幕字形完整性和可读性
-> 检查字幕、语音、画面锚点对齐
-> 检测中文音频长静音
-> AI 判定静音是否合理
-> 检查中文表达完整性和自然度
-> 输出 PASS/NEEDS_FIX/FAIL QA 报告
```

## 1. 对齐验收

必须检查 `audio-semantic-turns.md` 中的关键锚点。先区分两类锚点：

- 硬锚点：品牌、型号、产品名、人物名、金额、百分比、年份、关键数字、屏幕文字、视觉对象、长专有短语、用户明确指定的关键词。硬锚点必须有明确 source occurrence，中文语音和字幕都不能早于或晚于 source occurrence 超过 `0.8s`。
- 背景锚点：`中国`、`美国`、`德国`、`日本`、`电动车`、`电池`、`充电`、`汽车`、`车企` 等高频背景词。背景锚点用于语义抽查，不能只靠裸字符串匹配来判定字幕或语音提前；如果要把它升级为硬锚点，必须说明它在此处对应明确画面切换、强语义转折或用户指定验收点。

硬锚点候选包括：

- 品牌名、产品名、人物名、国家名。
- 关键数字、年份、金额、比例。
- 图表标题、屏幕文字、明显画面转场。
- `but`、`however`、`meanwhile`、`in contrast` 等强转折。
- 观点结论和例子切换。

对每个 `must_align` 锚点：

- 导出前后 10-20 秒检查片段。
- 截取关键时间点画面。
- 对中文成片音频或检查片段做 ASR。
- 如果 `render_manifest.json.playback.speed = 1.15`，所有原声锚点时间必须先映射为成片交付时间：`expected_final_time = source_anchor_time / 1.15`。检查片段、截图和中文 ASR 都应围绕交付时间取样。
- 验证中文关键词、中文字幕和画面是否落在目标窗口。
- 检查 `voiceover-segments.json` 中对应的 `anchor_checks`：`target_terms`、`effective_not_before_sec`、`expected_chinese_window_sec` 和最终实际出现时间必须一致。
- 不能只看关键词是否出现在同一个 segment。若关键词在同一 segment 内早于 `effective_not_before_sec`，仍然 FAIL。
- 也不能只看关键词是否最终出现。若硬锚点被放到后一个中文短语、后一个 segment 或后续字幕 cue，晚于 source occurrence 超过阈值，仍然 FAIL。
- 如果 SRT/VTT cue 太粗，导致无法判断关键词字幕是否卡点，至少输出 `NEEDS_FIX`；若已能证明语音/画面错位，输出 `FAIL`。
- 如果 SRT/VTT 虽然单调但整段字幕被推迟到段尾，或同一 segment 开始后长时间没有字幕，属于字幕/语音错位，输出 `FAIL`。
- 如果锚点词在原声中出现多次，评测 agent 必须结合原文短语、前后句、segment 语义和画面来选择 source occurrence；不能机械选择后一个或第一个裸词命中。
- 如果发现 `anchor_checks` 把背景词误列为硬锚点，但成片语义连续、无画面错位，应记录为 `WARN` 或 `NEEDS_FIX` 给上游修 anchor 设计；不要直接按裸词提前量判 `FAIL`。

阈值：

- `must_align` 关键词误差 `<= 0.8s`。
- 硬锚点提前和延迟都按 `<=0.8s` 验收；品牌/产品/人物/数字/年份/金额/百分比/屏幕文字/视觉对象都适用。
- 普通语义转场误差 `<= 1.5s`。
- 如果画面明显转场，中文关键词不得提前到上一画面。
- 有中文口播的 segment，首条对应字幕 cue 延迟应 `<=0.8s`。
- Segment 内连续无字幕空窗应 `<=1.2s`；超过该值必须结合最终中文音频 ASR 或字幕文本判断，若音频仍在讲话则 `FAIL`。

QA 报告必须写成证据句：

```text
中文关键词“...”出现在原视频 {FINAL_VIDEO_SEC}s。
目标锚点：{SOURCE_ANCHOR_START_SEC}-{SOURCE_ANCHOR_END_SEC}s。
交付速度：1.15x，目标成片时间：{SOURCE_ANCHOR_START_SEC / 1.15}s。
截图：qa/keyframes/anchor_NNN_{FINAL_VIDEO_SEC}.jpg。
结论：PASS。
```

## 1.1 字幕烧录同源验收

正式验收必须确认最终 MP4 里烧录的字幕层和交付的 `.srt` / `.vtt` 是同一版。

检查方法：

1. 读取 `render_manifest.json` 的字幕版本字段：`input_srt_sha256`、`final_srt_sha256`、`input_cue_sha256`、`overlay_source_srt_sha256`、`overlay_source_cue_sha256`、`overlay_cue_count`。
2. 现场计算交付 SRT 的 sha256 和 cue 数，确认和 manifest 一致。
3. 在至少 3 个时间点从最终 MP4 现场抽帧：开头、中段、一个关键锚点或随机点。
4. 对照同一时间点的 SRT cue 文本做目视/截图检查。若最终帧显示的是旧字幕、上一版长字幕或与当前 SRT 不同的文本，直接 `FAIL`，修复点是最终合成。

硬规则：

- 缺少字幕版本字段时，不能判正式 `PASS`。
- 正式 1.15x 交付时，最终 SRT/VTT、overlay 来源字幕和最终抽帧必须使用交付时间线；输入原始时间线 SRT 可以和最终 SRT hash 不同，但 manifest 必须证明最终字幕由输入 SRT 等比例缩放得到，并且最终 SRT、VTT、overlay 和 MP4 抽帧同源。
- SRT/VTT 是新版本但最终 MP4 烧着旧字幕时，直接 `FAIL`。
- 不能用 overlay 文件抽帧代替最终 MP4 抽帧；overlay 只能证明字幕层本身，不能证明它已经烧进最终成片。

## 1.2 字幕显示格式验收

屏幕显示的中文字幕正文不保留标点，且必须字形完整、清晰可辨。验收时必须检查交付的 `.srt` / `.vtt`，并结合最终 MP4 抽帧确认烧录字幕没有来自旧版本，也没有字体 fallback 或渲染问题。

检查范围：

- 只检查实际显示给观众的字幕正文。
- SRT 的 cue 序号、时间码、`-->` 箭头和时间码里的逗号不计入标点违规。
- VTT 的 `WEBVTT` 头、NOTE、STYLE、cue 时间码和 cue setting 不计入标点违规。
- 如果字幕正文分成多行，所有正文行都要检查。

禁止出现在字幕正文中的显示标点包括：

```text
，。！？；：、,.!?;:…“”‘’"'`（）()《》〈〉【】[]{}
```

硬规则：

- 字幕正文出现任意上述显示标点，直接 `FAIL`，不能判 `PASS`。
- 如果某个数字、缩写或专有名词原本依赖标点表达，应在上游改写为无标点中文表达或拆成更清楚的 cue，不能在验收阶段放行。
- 如果交付 SRT/VTT 无标点，但最终 MP4 抽帧显示旧版有标点字幕，按“字幕烧录不同源”直接 `FAIL`。
- 如果最终 MP4 抽帧中出现汉字笔画残缺、像半乱码、缺字方框、替代符号、异常字体 fallback，或用户指出某个字幕字形不可接受，不能判 `PASS`。若 SRT 文本正常但烧录显示异常，修复点是 `07-final-composition` 更换字体并重烧；若只需要避开某个显示风险字或改写 cue，修复点是 `06-subtitles`。
- 字幕正文不能出现单字 cue，且任一正文 cue 的显示时长不得低于 `0.5s`。单字/超短 cue 会造成闪烁观感，即使没有标点也不能判正式 `PASS`；修复点是 `06-subtitles` 字幕拆分或同源重新合成。
- 如果同一锚点的多个目标词被切成一串 `0.25s` 微 cue，应判 `FAIL` 或 `NEEDS_FIX`，不能通过放宽锚点 tolerance 解决；应回到字幕生成逻辑，把同一 source anchor 时间折叠为一个排程约束。
- QA 报告必须记录 `subtitle_punctuation_violations`，至少包含 cue index、违规正文和违规字符；无违规时写空数组。
- QA 报告必须记录 `subtitle_glyph_readability_issues`，至少包含截图路径、时间点、cue index、问题字符或问题描述；无问题时写空数组。

## 2. 长静音验收

对中文配音音频运行：

```bash
ffmpeg -i final_voiceover.m4a \
  -af silencedetect=noise=-35dB:d=0.35 -f null -
```

连续静音超过 `2.0s` 时，不是让用户人工判断，而是由 AI 做分级处理：

1. 导出静音前后各 5-10 秒检查片段。
2. 对原视频同时间段原声音频也跑 `silencedetect`。
3. 读取该时间窗的 `audio-semantic-turns.md`、`voiceover-segments.json` 和字幕。
4. 截取静音期间的画面帧。
5. 判断原因并给出处理动作。

AI 判定类型：

- `acceptable_original_pause`：原视频同区间也有停顿、音乐、转场或纯画面展示；可接受，但报告要说明。
- `acceptable_visual_breath`：画面需要短暂停顿承接，且中文没有漏信息；可接受，但通常不应超过 3 秒。
- `fail_missing_content`：原声仍在说话或字幕有信息，但中文空白；失败，回到配音稿补信息。
- `fail_bad_segmentation`：静音来自粗分段或时间窗错误；失败，重分段。
- `fail_tts_too_short`：TTS 太短靠补静音；失败，补稿或重生成。

硬规则：

- 如果原视频同时间段仍有讲话，而中文静音超过 `2.0s`，直接 FAIL。
- 如果同一个成片出现多个 `acceptable_visual_breath`，需要整体复查节奏。
- 静音修复不能靠无意义废话；必须补回原文事实、因果、例子或重分段。

## 3. 中文表达验收

AI 需要逐章或逐 3-5 分钟片段检查中文稿和成片：

- 表达是否符合中文口播习惯。
- 是否有明显直译腔、病句、断句怪异。
- 是否遗漏关键事实、数字、因果、转折、例子、立场。
- 是否为了卡时间过度摘要，导致逻辑不完整。
- 是否把下一段信息提前，造成画面/语义错位。
- 专有名词、数字、品牌、地名是否正确。

判定：

- 小措辞问题：`WARN`，给出建议。
- 影响理解或导致错位：`FAIL`，回到配音稿修。

## 4. 音频质量验收

检查：

- 无明显爆音、断裂、吞字、重复、异常口音。
- 正式交付音频必须是 1.15 倍交付版本；如果 `audio/final_voiceover.zh-CN.m4a` 仍是原速音频拷贝，不能判 PASS。
- 上游 TTS/对齐 manifest 必须记录 `segment_pass_rate`，整体标准为 `segment_pass_rate >= 0.90`。
- 单段 `tempo_factor > 1.15` 或 `tail_padding_sec > 1.5s` 是段级失败或 warning 来源，不再自动导致最终 FAIL；若整体通过率达到 90%，按 warning 抽查。
- 单段 `tail_padding_sec > 2.0s` 必须按长静音规则判定：只有当原视频同区间仍有讲话、画面/语义被破坏或中文表达明显断裂时，才判 `FAIL`。
- 最终音频和最终视频时长差 `<= 0.3s`，否则必须解释。

## 4.1 音色克隆与同片音色一致性验收

正式生产默认要求中文配音来自原视频音色克隆，而不是固定预设音色。

证据检查：

- 读取 `tts_manifest_path`；如果没有单独输入，则读取 `segment_aligned_manifest_path.voice_clone`。
- `mode` 必须是 `voice_clone_only`。
- 必须存在 `ref_audio_path`、`ref_audio_sha256`、`ref_text_sha256`、`model_dir`、`segment_count`。
- `ref_audio_path` 必须能追溯到本视频原声音频的某个参考时间段；如果 manifest 未写 `reference_time_range`，至少 QA 报告要记录来源路径和选取理由。
- `segment_aligned_manifest_path.segments[].draft_audio_path` 对应的 draft 段必须来自同一个 TTS manifest。不能把旧 draft、预设 voice draft 或不同参考音频的 draft 混进同一 final voiceover。

听感和机器辅助检查：

- 至少抽查开头、中段、结尾各 1 段中文配音；如果成片不足 3 段则全查。
- 如果本机可用 speaker embedding / speaker verification 工具，可对抽查段计算相似度；如果不可用，评测 agent 需要用听感描述判断是否存在明显换人、男女声切换、音高/音色突变或口音突变。
- 优先运行本 skill 的 `scripts/check_speaker_consistency.py`。默认阈值：最小 pairwise cosine `>=0.70` 为通过，`<0.55` 为失败，中间值为 `WARN` 并要求结合听感或更多片段复核。
- 音色轻微变化、语气变化或情绪起伏可以 `WARN`；明显像不同说话人，直接 `FAIL`。
- 如果发现换人，修复点是 TTS：统一 `voice_profile.json`，删除旧 draft 段，使用 `--force` 重生成，再重新对齐和合成。

硬规则：

- 没有用户授权时，固定预设 `voice` 不能判正式 `PASS`。
- 同片出现明显不同人声，直接 `FAIL`，即使锚点、字幕和静音都通过。
- 只检查最终拼接音频或最终 MP4 不够；必须同时检查 manifest 证据和抽样听感。

## 输出

输出目录必须包含：

```text
qa/acceptance-report.md
qa/acceptance-result.json
qa/check-clips/*.mp4
qa/keyframes/*.jpg
qa/silence-review/*.mp4
```

`acceptance-result.json` 必须包含：

```json
{
  "decision": "PASS | FAIL | NEEDS_FIX",
  "warnings": [],
  "rollback_to_node": "03-audio-anchors | 04-voiceover-segments | 05-tts-alignment | 06-subtitles | 07-final-composition | null",
  "alignment": {
    "must_align_checked": 0,
    "failed": []
  },
  "silence": {
    "over_2s": [],
    "accepted": [],
    "failed": []
  },
  "language_quality": {
    "decision": "PASS | WARN | FAIL",
    "issues": []
  },
  "subtitle_format": {
    "decision": "PASS | FAIL",
    "punctuation_violations": [],
    "glyph_readability_issues": [],
    "max_cue_duration_sec": 0,
    "max_visible_chars": 0
  },
  "playback": {
    "decision": "PASS | FAIL",
    "speed": 1.15,
    "final_timeline": "delivery_timeline",
    "issues": []
  },
  "speaker_consistency": {
    "decision": "PASS | WARN | FAIL",
    "mode": "voice_clone_only | preset_voice_authorized | missing",
    "ref_audio_sha256": "",
    "checked_segments": [],
    "issues": []
  },
  "evidence_completeness": {
    "decision": "PASS | LIMITED | FAIL",
    "full_range_covered": false,
    "missing": [],
    "limited_ranges": []
  },
  "required_fixes": [],
  "non_blocking_issues": []
}
```

## 通过条件

PASS 不要求零问题，但硬性项必须全部通过。只有同时满足以下条件才能 PASS：

- 原视频画面和原声音频都可用；原声音频可来自 `source_video_path` 或 `source_audio_path`。
- `audio-semantic-turns.md`、`voiceover-segments.json`、`segment_aligned_manifest_path` 三类证据都存在，并覆盖完整处理范围。
- 三类证据的时间来源可追溯到原声音频 ASR word timestamps，不是字幕时间戳、缓存字幕时间戳或章节粗时间窗。
- `voiceover-segments.json.start/end` 没有被改写为 TTS duration 累加时间线。
- 最终 MP4 烧录字幕与交付 `.srt` / `.vtt` 同源，manifest 哈希和现场抽帧证据一致。
- `render_manifest.json.playback.speed == 1.15`，最终 MP4、交付中文音频、烧录字幕和交付 `.srt` / `.vtt` 处于同一条 1.15 倍交付时间线。
- 最终时长约等于 `min(source_duration, voiceover_duration) / 1.15`，容差 `<=0.3s`。
- TTS manifest 证明同一原视频音色克隆 profile，且抽查未发现明显换人。
- 所有 `must_align` 锚点通过。
- 没有未解释的超过 `2s` 中文静音。
- 字幕、语音、画面没有明显错位。
- 中文表达自然、完整、连贯。
- 音频质量和时长匹配达标。
- QA 报告提供了可验证的截图、片段、ASR/manifest 证据和文件路径。

允许 `PASS` 带 `warnings`，但 warnings 必须是不影响理解、交付可信度、锚点对齐、字幕可读性和音色一致性的非阻塞问题，例如：

- 个别非关键句表达略硬，但不影响语义理解。
- 个别随机检查帧字幕位置略偏，但仍清晰可读，且不是关键锚点帧。
- 非关键背景画面和语音没有强绑定，但语义连续、无对象错位。
- 音色有轻微情绪或语气波动，但仍可判断为同一说话人。

否则输出 `FAIL` 或 `NEEDS_FIX`，并明确应该回到哪个上游步骤修：锚点、分段、配音稿、TTS、字幕或合成。

判定优先级：

- 有明确硬性质量失败：输出 `FAIL`。例如硬锚点错位、事实/数字/品牌错误、字幕与语音不一致、原视频仍讲话但中文静音超过阈值、混用音色、最终 MP4/manifest 不可信。
- 没有明确硬性质量失败，但证据不完整、只覆盖局部、SRT/VTT cue 太粗导致无法判断关键时机、检查片段/manifest 缺失或存在可局部修复问题：输出 `NEEDS_FIX`，并给出最近责任节点。
- 硬性项和证据链都通过，仅存在非阻塞问题：输出 `PASS`，同时填写 `warnings` 和 `non_blocking_issues`。
