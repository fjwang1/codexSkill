# Worldview China Video Agent Reminder

本文件只记录未来执行前必须先看的重大提醒。普通日志、偶发问题、可有可无的经验不要写入。

## 必读提醒

1. 不可信 YouTube 字幕时间戳。
   正式卡点必须来自原声音频 ASR word timestamps；字幕只能作为文本来源和 ASR 错词校正来源。

2. 高风险事实必须用画面/硬字幕复核。
   数字、线路号、车站数、年份、金额、百分比、图表文字和屏幕文字不能只信 ASR。曾出现 `Line 8 / 37 stations` 被写成“15 号线 / 30 座车站”的错误。

3. TTS 太短不能改原声时间线。
   不得把 `voiceover-segments.json` 的 `start/end/target_duration_sec` 改成 TTS 实际累计时间。正确修复是补稿、重分段或重生成 TTS。

4. 正式配音必须使用同一个原视频音色克隆 profile。
   未经用户授权，不能用 Dylan/Vivian 等预设 voice；同一视频不能混用多个 reference audio、reference text、模型目录或旧 draft。

5. 合成前必须清理旧字幕 overlay 并证明字幕同源。
   最终 MP4 抽帧必须显示当前 SRT/VTT 对应字幕；render manifest 必须记录输入 SRT、最终 SRT、overlay 来源 SRT 和 cue hash/cue count 一致。

6. 每个节点必须独立验收后才能进入下一节点。
   验收要由新的无上下文子 agent 执行。节点失败时，清空失败节点和所有下游 active 目录；必要时允许一次回滚多个节点。

7. 当前字幕 manifest 必须唯一且同源。
   若 06 修复后留下旧 `subtitle_manifest.json`、旧 QA 或旧 overlay 证据，独立验收可能按旧产物判失败。06 通过前必须清理或归档 stale manifest，并确保 run manifest、07 render manifest、最终 MP4 抽帧都指向同一份当前 SRT/VTT、cue hash 和 cue count。

8. 超过 2 秒中文静音需要证据分级，不是口头放行。
   最终验收发现长静音时，必须结合原声 ASR turn、`non_voice_ranges`、字幕 cue 和画面片段逐一分类。只有原声同区间没有连续有效讲话、或已在 04 明确为无口播/视觉停顿时才可接受；否则回滚到 04 补稿或重分段。
