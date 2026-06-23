---
name: article-podcast-subtitle-timeline-qa
description: 逐句验证中文播客视频字幕、ASR 对齐时间轴、最终音频和视频是否一致。适用于已有 podcast_script.md、audio/final_podcast.wav、audio/dialogue_timeline.json、video/final_subtitles.srt、video/subtitle_manifest.json 和可选 final_video.mp4 的项目；输出逐 cue/turn 偏移报告，判断字幕是否系统性快、慢或视频时间轴缩放错误。
---

# 播客字幕时间线逐句 QA

这个 skill 负责独立验收字幕是否真的对上最终音频和视频。它不是字幕生成器；它只做时间线验证，发现问题时回到 `article-podcast-audio-alignment`、`article-podcast-subtitle-alignment` 或 `article-podcast-static-video` 修。

## 输入

```text
<project>/audio/final_podcast.wav
<project>/audio/dialogue_timeline.json
<project>/video/final_subtitles.srt
<project>/video/subtitle_manifest.json
<project>/video/final_video.mp4, optional but required for post-render QA
```

`dialogue_timeline.json` 必须来自最终音频 ASR/forced alignment，而不是字数估算。

## 输出

```text
<project>/video/subtitle_timeline_qa.json
<project>/video/subtitle_timeline_qa_report.md
```

## 验证层级

1. 时间轴一致性。
   - `subtitle_manifest.playback_speed_factor` 必须和当前交付视频一致。
   - `final_subtitles.srt` cue 时间必须和 `subtitle_manifest.json` 一致。
   - `final_video.mp4` 时长必须约等于 `audio/final_podcast.wav / playback_speed_factor`。
   - 最后一条字幕必须覆盖到视频结尾附近。

2. ASR timeline 一致性。
   - 每条字幕 cue 必须能映射到 `dialogue_timeline.cues` 或对应 turn。
   - cue 开始时间不应系统性晚于 ASR cue。
   - cue 结束时间不应系统性早于 ASR cue。
   - 如果一个 ASR cue 因单行 4K 字幕宽度被拆成多条连续显示 cue，逐条 cue 只验证映射和顺序；时间早晚按同一个 `source_cue_index` 的 cue group 首尾整体判断，不能把后续拆分 cue 单独拿去对齐整条 ASR cue 的开头。
   - 对 turn 边界进行聚合检查，防止某个段落字幕整体漂移。

3. 视频交付一致性。
   - 如果 `video/final_video.mp4` 存在，视频时长必须匹配音频和播放速度。
   - SRT、subtitle_manifest、render_manifest 必须在同一 1.0x 时间轴上。

## 运行命令

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-subtitle-timeline-qa/scripts/verify_subtitle_timeline.py \
  --project-dir <project>
```

可选：

```bash
python3 .../verify_subtitle_timeline.py \
  --project-dir <project> \
  --fail-on-needs-fix
```

## 判定阈值

默认阈值：

```text
cue_start_ok: subtitle starts from 0.25s early to 0.08s late against ASR cue
cue_start_needs_fix: subtitle starts >0.45s early or >0.18s late
cue_end_ok: subtitle ends from 0.10s early to 0.45s late against ASR cue
cue_end_needs_fix: subtitle ends >0.25s early or >0.75s late
video_duration_tolerance_sec: 0.75
srt_manifest_tolerance_sec: 0.04
```

解释：

- `start_delta_sec = subtitle_start_1x - asr_start_1x`。
  - 负数表示字幕提前。
  - 正数表示字幕晚于语音。
- `end_delta_sec = subtitle_end_1x - asr_end_1x`。
  - 负数表示字幕过早消失。
  - 正数表示字幕滞留。

## Gate

通过条件：

```text
video/subtitle_timeline_qa.json exists
video/subtitle_timeline_qa_report.md exists
timeline status is PASS
final video duration matches audio duration / playback_speed_factor
SRT times match subtitle_manifest cue times
every subtitle cue maps to dialogue_timeline timing
no cue cluster is systematically late against ASR cue timing
no cue cluster disappears before ASR cue ends
dialogue_timeline hash matches subtitle_manifest dialogue_timeline_hash
subtitle text uses Chinese source names for confirmed publication; raw English publication names such as Foreign Policy do not appear in final_subtitles.srt
```

如果状态是 `NEEDS_FIX` 或 `FAIL`：

- ASR 时间轴错误：回到 `article-podcast-audio-alignment`。
- 字幕整体早/晚：回到 `article-podcast-subtitle-alignment` 调整全局 lead 或 cue timing。
- 视频时间轴错误：回到 `article-podcast-static-video`，修正 speed factor、sidecar subtitle scaling 或 render manifest。
