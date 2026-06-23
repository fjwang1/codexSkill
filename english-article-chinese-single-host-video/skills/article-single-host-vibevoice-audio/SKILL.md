---
name: article-single-host-vibevoice-audio
description: 使用本地 VibeVoice-1.5B 为中文单人口播解释稿生成整段连续音频。适用于已有 single_host_script.md 的项目；默认抽取正文并拆成单个 Speaker 0 的多个段落，调用通用 VibeVoice wrapper 的 single 模式并只绑定一个声音，生成 audio/vibevoice_dialogue_display.txt、TTS 归一化后的 audio/vibevoice_dialogue.txt、audio/final_podcast.wav、audio/audio_manifest.json、audio/final_podcast_preview.mp3 和 audio/audio_report.md。用于 english-article-chinese-single-host-video 的单人音频主线。
---

# 单人口播 VibeVoice 音频

这个 skill 把 `single_host_script.md` 一次性交给 VibeVoice 生成连续单人讲解音轨，默认使用男声 `BowenClean`；可选切换为从 B 站“懂夕夕”配音视频截取并试听通过的男声 `译制腔`。不要按段生成再拼接，不要切回 Qwen/Qwen3-TTS。

## 输入

```text
<project>/single_host_script.md
```

如果只有 `podcast_script.md`，可以作为 fallback 读取，但必须确认它是单人口播兼容镜像，而不是旧的双人 `Speaker 0` / `Speaker 1` 播客稿。

## 输出

```text
<project>/audio/
  vibevoice_dialogue_display.txt
  vibevoice_dialogue.txt
  tts_normalization_report.md
  vibevoice_raw/
  final_podcast.wav
  final_podcast_preview.mp3
  final_podcast_playback.m4a
  audio_manifest.json
  playback_audio_manifest.json
  audio_report.md
```

文件名保留 `dialogue` 是为了兼容后续原流程；内容必须只有一个 speaker。默认使用 `Speaker 0:` 作为本项目内部 turn 标签。这不是双人播客。

`audio/final_podcast.wav` 是内部母带和唯一时间轴源。ASR、字幕、章节图时间轴和视频合成都以它为基准。人工试听默认给 `audio/final_podcast_preview.mp3`。

## 生成流程

1. 准备 VibeVoice 输入。

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py \
  --project-dir <project>
```

脚本会：

- 从 `single_host_script.md` 的 `## 正文` 后抽取正文。
- 跳过 Markdown 标题、来源说明和空行。
- 按自然段和标点把长段拆成 80-260 字左右的单人 turn。
- 写出只包含 `Speaker 0:` 的 `audio/vibevoice_dialogue_display.txt`。
- 写出 TTS 归一化后的 `audio/vibevoice_dialogue.txt`。
- 写出 `audio/audio_manifest.json`，其中 `voice_mode=single_host`。

TTS 归一化只作用于 VibeVoice 输入，不要把归一化文本当成字幕显示稿。例如：

```text
14% -> 百分之十四
2025 年 -> 二零二五年
GDP -> G D P
3000 元 -> 三千元
```

2. 运行本地 VibeVoice。

```bash
/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio/scripts/run_article_vibevoice_audio.py \
  --project-dir <project>
```

正式 runner 必须复用通用 VibeVoice wrapper：

```text
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py
```

不要在本子 Skill 里直接调用 VibeVoice repo 的 `demo/inference_from_file.py`。通用 wrapper 会设置稳定的 cwd、环境变量和 CPU 参数；单人版必须显式使用 `--speaker-mode single` 并且只传一个 `--speaker-names`。

默认使用一个声音，且只允许以下两个正式男声音色：

```text
Speaker 0 -> BowenClean
```

- 默认：`BowenClean`。它来自旧双人播客音频 Skill 中已试听通过的 `06_VV_zh-Bowen_man.wav`，适合稳妥、克制、偏通用的中文解释视频。
- 可选：`译制腔`。它对应 VibeVoice voice prompt 文件 `/Users/wangfangjia/code/VibeVoice/demo/voices/zh-译制腔_man.wav`，来源记录在 `/Volumes/GT34/Generated/bilibili_voice_clone/BV1Sfj76CEyF/voice_samples/voice_reference_manifest.json`。它来自 B 站视频 `BV1Sfj76CEyF` 的 04:50 开始 29.5 秒干净男声片段，并已用约 72.8 秒样音试听通过，适合更接近中配知识视频的听感。

注意：VibeVoice 原生 processor 的纯文本单人输入会隐式归到 `Speaker 1`，但本文章项目为了后续 manifest、ASR 和字幕绑定稳定，仍写显式 `Speaker 0:` turn。通用 wrapper 的 `single` 模式会自动把唯一 speaker 映射到唯一传入的声音；不得再补 inert second speaker。

如果用户明确想要使用 `译制腔`，传：

```bash
/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio/scripts/run_article_vibevoice_audio.py \
  --project-dir <project> \
  --speaker-names 译制腔
```

如果不传 `--speaker-names`，runner 必须默认使用 `BowenClean`。不要传这两个正式选项以外的音色名，避免 VibeVoice partial-match 或 fallback 造成不可控音色。

3. 后处理为正式音轨。

如果 VibeVoice 原始 wav 已经自然、音量正常，可以把原始 wav 复制为 `audio/final_podcast.wav`。如果存在长静音或响度需要标准化，运行：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio/scripts/postprocess_vibevoice_audio.py \
  --project-dir <project>
```

后处理只压缩长静音并做响度标准化，不修坏音频。如果原始音频明显低电平、沙哑、拖尾或发音混乱，要重跑 VibeVoice，不要硬拉音量。

4. 回写最终音频信息。

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py \
  --project-dir <project> \
  --final-audio <project>/audio/final_podcast.wav
```

5. 导出试听副本。

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio/scripts/export_playback_audio.py \
  --project-dir <project>
```

6. 做音频 sanity check。

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels \
  -of default=noprint_wrappers=1 <project>/audio/final_podcast.wav
ffmpeg -hide_banner -i <project>/audio/final_podcast.wav -af volumedetect -f null - 2>&1 | tail -n 12
ffmpeg -hide_banner -i <project>/audio/final_podcast.wav -af silencedetect=noise=-45dB:d=2 -f null - 2>&1 | rg 'silence_(start|end)' || true
```

## 后续契约

VibeVoice 不提供字幕时间戳。生成音频后必须进入 `article-podcast-audio-alignment`，对 `audio/final_podcast.wav` 做 ASR/forced alignment，并输出：

```text
audio/dialogue_timeline.json
audio/asr_alignment.json
audio/alignment_report.md
audio/audio_artifact_qa.json
audio/audio_artifact_qa_report.md
```

字幕和章节图只能使用 `dialogue_timeline.json` 的真实对齐时间，不得从字数、turn 顺序或生成进度猜时间。

单人模式没有 speaker switch。音频抽检改为：

- opening 30 秒
- middle 30 秒
- ending 30 秒
- 至少 5 个段落/turn 边界
- 至少 5 个包含数字、专名或英文缩写的句子

## CPU 策略

本机稳定后端沿用旧双人流程：`vibevoice-dialogue-tts` wrapper + CPU `float32` + `eager`。质量可用但较慢。正式生产不要使用极短 smoke 稿判断音质；单人口播也应给 VibeVoice 足够上下文。发布稿如果很长，先报告预计耗时，不要自动切换 TTS backend。

单人口播默认 `max_length_times=2.4`。这是单人口播自己的生成余量，用来避免 10 分钟级中文稿在 `1.6` 附近提前到达最大生成步数并截断尾部；旧双人 wrapper 默认值不因此改变。若后续 ASR 显示文稿尾部没有被读出、最后多个 turn 被压缩到音频末尾，必须用更充分的长度余量重跑 VibeVoice，不得用字幕或时间轴插值伪造完整性。

如果 CPU 生成太慢，优先检查是否仍在走旧 wrapper；不要先改成 MPS。已知旧 wrapper 的 Skill 记录：MPS `float16` 产生过 NaN，MPS `float32` 出现过 stall。

## Gate Failure Policy

不要把 `audio/final_podcast.wav` 缺失直接等同于最终失败。先按失败类型处理：

1. 输入 gate 失败：如果 `single_host_script.md`、`audio/vibevoice_dialogue.txt`、`audio/audio_manifest.json` 缺失或内容不是单人 `Speaker 0`，重跑输入准备脚本一次。若仍失败，停止并报告 `AUDIO_INPUT_GATE_FAILED`，不要进入 VibeVoice。
2. 资源竞争：如果本机同时有其他 VibeVoice、Whisper、ffmpeg 或视频合成等重任务运行，不要立即判定 VibeVoice 卡死。记录竞争进程，等待 5-10 分钟后复查；无人值守自动化最多等待 90 分钟。资源释放后从本音频阶段继续，不要重跑选题、脚本、封面或 PPT。超过等待上限仍有竞争任务时，报告 `BLOCKED_AUDIO_WAITING_FOR_RESOURCES`。
3. 生成超时：只有在没有明显资源竞争、且 VibeVoice 在有边界等待后仍无 WAV 产出时，才报告 `AUDIO_GENERATION_VIBEVOICE_TIMEOUT`。先尝试整篇单次生成；若吞吐估算明显不适合当前自动化窗口，停止并切到 `vibevoice-dialogue-tts` 的 resident batch。resident batch 的首个 chunk 超过 20 分钟无 WAV 时，允许同参数重试一次；第二次仍无 WAV 才停止。
4. 输出质量失败：如果 WAV 存在但 ffprobe、音量、长静音或抽听失败，同参数重跑 VibeVoice 一次。若再次失败，报告 `AUDIO_GENERATION_VIBEVOICE_BAD_OUTPUT`。不要用响度硬拉、字幕插值或时间轴伪造来通过 gate。
5. 禁止的自动兜底：除非用户明确批准，不要切到 Qwen/Qwen3-TTS，不要先改 MPS，不要把发布稿降为 smoke 参数，不要显著降低 `ddpm_steps` 或 `max_length_times`。

所有 gate 失败报告必须写明：失败阶段、已执行命令或脚本、等待/重试次数、是否检测到资源竞争、缺失产物、下一次应从哪个阶段恢复。

## Gate

```text
audio/vibevoice_dialogue.txt exists and only contains Speaker 0 lines
audio/vibevoice_dialogue_display.txt exists and only contains Speaker 0 lines
audio/tts_normalization_report.md exists
audio/audio_manifest.json exists
audio_manifest records audio_backend=vibevoice_longform
audio_manifest records voice_mode=single_host
audio_manifest records vibevoice_generation_tunable.speaker_mode=single
audio_manifest records vibevoice_generation_tunable.speaker_names=["BowenClean"] by default, or ["译制腔"] when explicitly selected by the user
audio_manifest records script_sha256, display_dialogue_sha256, vibevoice_input_sha256, final_audio_sha256, duration_sec
audio_manifest records all Speaker 0 turns from single_host_script.md
audio_manifest turns record both text and tts_text
audio/final_podcast.wav exists and ffprobe passes
audio/final_podcast_preview.mp3 exists and ffprobe passes
audio/final_podcast_playback.m4a exists and ffprobe passes
audio/playback_audio_manifest.json exists
no long silence over 2 seconds after postprocess unless intentionally kept
spot checks of opening/middle/end confirm normal voice, normal speed, clear pronunciation, and natural paragraph flow
```
