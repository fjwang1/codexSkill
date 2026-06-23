---
name: article-podcast-audio-alignment
description: 对 VibeVoice 生成的最终中文播客或单人口播音频做 ASR 或 forced alignment，并检测 turn/段落边界非语音伪声。适用于已有 podcast_script.md 或 single_host_script.md、audio/final_podcast.wav、audio/audio_manifest.json 的项目；必须生成 audio/dialogue_timeline.json、audio/asr_alignment.json、audio/alignment_report.md、audio/audio_artifact_qa.json 和 audio/audio_artifact_qa_report.md，供 subtitles、chapter visuals、artifact QA 和 timeline QA 使用。
---

# 播客/口播音频时间轴对齐

这个 skill 负责音频时间轴 gate：先听最终音频，再把最终音频和定稿文稿对齐。字幕和章节图都必须使用这里产出的 `audio/dialogue_timeline.json`，不要用字数估算或旧 TTS chunk 时间。

## 输入

```text
<project>/podcast_script.md
<project>/single_host_script.md  # optional, single-host projects also keep podcast_script.md as a compatibility mirror
<project>/audio/final_podcast.wav
<project>/audio/audio_manifest.json
```

`audio_manifest.json` 应记录 `audio_backend=vibevoice_longform` 和所有 turns。双人播客通常包含 `Speaker 0` / `Speaker 1`；单人口播通常只有 `Speaker 0` 且 `voice_mode=single_host`。若 manifest 中存在 `turns[].tts_text`，它是 VibeVoice 实际朗读文本；`turns[].text` 是观众显示文本。

## 输出

```text
<project>/audio/
  asr_alignment.json
  dialogue_timeline.json
  alignment_report.md
  audio_artifact_qa.json
  audio_artifact_qa_report.md
  artifact_candidates/
  audio_artifact_ai_review.json  # 仅当 audio_artifact_qa.json 状态为 NEEDS_AI_REVIEW 时需要
```

## 对齐原则

- 必须基于最终 `audio/final_podcast.wav` 做真实 ASR/forced alignment。
- 不要把 `audio_manifest.json` 的 turn 顺序或字数比例当作最终时间。
- 如果本地没有可用 ASR/forced-alignment 工具，停在本 gate 并报告 `BLOCKED`；不要进入字幕或章节图阶段。
- speaker 归属默认来自 `audio_manifest.turns`。双人播客使用 `Speaker 0/1`；单人口播通常全部是 `Speaker 0`。不要求做说话人 diarization。
- ASR 文本和文稿之间允许同义小差异，但关键数字、专名和顺序必须能匹配。

本机默认先尝试 MLX Whisper：

```bash
/Users/wangfangjia/code/bilibili-mcp/.venv-asr/bin/mlx_whisper \
  <project>/audio/final_podcast.wav \
  --language zh \
  --task transcribe \
  --word-timestamps True \
  --output-format json \
  --output-dir <project>/audio \
  --output-name asr_alignment
```

如果该入口不可用，再按环境选择 WhisperX、faster-whisper、whisper.cpp 或其他本地 ASR。优先使用能给出词级或短句级时间戳的工具。

ASR 原始 JSON 不能直接当最终时间轴。必须把 ASR 的 segment/word 时间和 `audio_manifest.turns` 做单调匹配，生成 `dialogue_timeline.json`。匹配规则：

- 如果 `turns[].tts_text` 存在，用 `tts_text` 匹配 ASR，因为这是实际喂给 VibeVoice 的朗读稿。
- `dialogue_timeline.turns[].text` 和 `dialogue_timeline.cues[].text` 仍然使用 `turns[].text` 的观众显示稿，供字幕和章节图使用。
- 不要把 `百分之十四`、`二百九十万` 这类 TTS 朗读写法泄漏到最终字幕，除非原文稿本来就是这么写的。
- 观众显示稿里的已确认来源必须使用中文来源名。若 `source_metadata.json.publication` 是 `Foreign Policy`，`dialogue_timeline.turns[].text` / `cues[].text` 应写 `外交政策`，不能把 `Foreign Policy` 带进后续字幕。

如果 ASR 漏字、幻觉或错位严重，人工抽查并修正 turn/cue 边界；不要让错误 ASR 继续流入字幕和章节。

生成 `dialogue_timeline.json`：

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/build_dialogue_timeline_from_asr.py \
  --project-dir <project> \
  --asr-json <project>/audio/asr_alignment.json
```

## dialogue_timeline.json

至少包含：

```json
{
  "schema_version": "article-podcast-dialogue-timeline.v1",
  "alignment_method": "asr_forced_alignment_final_audio",
  "audio": "audio/final_podcast.wav",
  "audio_sha256": "...",
  "script_sha256": "...",
  "audio_manifest_sha256": "...",
  "duration_sec": 603.12,
  "speaker_map": {
    "Speaker 0": {"display_role": "女主持或单人口播主持"},
    "Speaker 1": {"display_role": "男分析者，单人口播项目可不存在"}
  },
  "alignment_text_source": "audio_manifest.turns.tts_text",
  "display_text_source": "audio_manifest.turns.text",
  "turns": [
    {
      "turn_index": 1,
      "turn_id": "turn_0001",
      "speaker": "Speaker 0",
      "display_role": "女主持",
      "text": "今天我们先从一个反直觉的地方讲起。",
      "start_sec": 0.0,
      "end_sec": 3.42,
      "alignment_confidence": "high"
    }
  ],
  "cues": [
    {
      "cue_index": 1,
      "turn_index": 1,
      "speaker": "Speaker 0",
      "text": "今天我们先从一个反直觉的地方讲起",
      "start_sec": 0.0,
      "end_sec": 3.42,
      "alignment_confidence": "high"
    }
  ]
}
```

`turns` 给章节图和 turn-level QA 使用；`cues` 给字幕使用。字幕 cue 应尽量短，通常 8-18 个中文字符，最长约 24 个中文字符。

## 验证

写完 `dialogue_timeline.json` 后运行：

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/validate_dialogue_timeline.py \
  --project-dir <project>
```

## Turn 边界伪声检测

VibeVoice 长音频在 speaker turn 或单人口播段落边界可能偶发短促非语音伪声、背景音、金属声或类似音乐残响。`dialogue_timeline.json` 生成并验证后，必须立即运行边界伪声检测：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-audio-alignment/scripts/detect_turn_boundary_artifacts.py \
  --project-dir <project>
```

脚本只做第一层筛选：它在相邻 turn 的空档里寻找“应静而不静”的可疑声学片段，并读取 `asr_alignment.json` 判断该空档是否有 ASR 文本重叠。输出：

```text
audio/audio_artifact_qa.json
audio/audio_artifact_qa_report.md
audio/artifact_candidates/<candidate_id>.wav
audio/artifact_candidates/<candidate_id>_spectrogram.png
```

判定规则：

- `status=PASS`：没有发现需要复核的候选，可进入字幕和章节图。
- `status=NEEDS_AI_REVIEW`：必须由 Codex 做第二层判断，不得直接进入字幕或视频合成。

AI 复核必须读取 `audio_artifact_qa_report.md`、候选 wav/spectrogram、ASR overlap 和相邻 turn 文本。判断重点：

- 如果候选在两个 turn 之间、ASR 无对应文字、且听感/频谱明显不是自然气口或尾音，判为 `artifact`。
- 如果只是句尾呼吸、口腔音、自然尾音、低能量环境底噪或 ASR/timeline 边界轻微误差，判为 `acceptable_tail` 或 `false_positive`。
- 如果任一候选判为 `artifact`，本 gate 失败；必须重跑 VibeVoice、换 seed/参数，或对该边界做局部 patch 后重新 ASR、重新跑本检测。

AI 复核文件固定为：

```json
{
  "schema_version": "article-podcast-audio-artifact-ai-review.v1",
  "status": "PASS | PASS_WITH_WARNINGS | FAIL",
  "reviewer": "codex",
  "decisions": [
    {
      "candidate_id": "boundary_0002_candidate_01",
      "decision": "artifact | acceptable_tail | false_positive",
      "rationale": "..."
    }
  ]
}
```

`decisions` 必须覆盖 `audio_artifact_qa.json` 里的每一个 candidate。不要把 `NEEDS_AI_REVIEW` 当作通过状态。

## Gate

通过条件：

```text
audio/asr_alignment.json exists
audio/dialogue_timeline.json exists
audio/alignment_report.md exists
audio/audio_artifact_qa.json exists
audio/audio_artifact_qa_report.md exists
dialogue_timeline records audio_sha256, script_sha256, audio_manifest_sha256
dialogue_timeline duration_sec matches audio/final_podcast.wav
all script turns are represented once in dialogue_timeline.turns
turn start_sec/end_sec are monotonic and within audio duration
cue start_sec/end_sec are monotonic and within audio duration
every cue maps to a turn_index
ASR/script matched_script_ratio must be >= 0.95 by default; 0.85 is not acceptable for production
no long script tail may be interpolated or compressed into the final seconds
no run of more than 1 trailing low-confidence turn is allowed
long turns/cues must have plausible duration for their Chinese text length; if dozens of characters are squeezed into less than a second, this gate fails
alignment_report records ASR tool, model, language, confidence notes, and manual spot checks
audio_artifact_qa status is PASS, or status is NEEDS_AI_REVIEW and audio_artifact_ai_review.json covers every candidate with final status PASS/PASS_WITH_WARNINGS
no candidate is AI-reviewed as artifact
opening/middle/end and at least 5 speaker switches or paragraph boundaries were spot checked against real audio
```

如果 ASR 对齐质量不足，先修对齐或重跑 ASR，不要让字幕和章节图用错误时间轴继续生产。
