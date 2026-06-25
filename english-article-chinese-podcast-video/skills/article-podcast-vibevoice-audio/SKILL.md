---
name: article-podcast-vibevoice-audio
description: 使用本地 VibeVoice-1.5B 为中文双人播客文稿生成整段连续音频。适用于已有 Speaker 0/Speaker 1 格式的 podcast_script.md，需要区分观众显示稿和 TTS 朗读稿，生成 audio/vibevoice_dialogue_display.txt、TTS 归一化后的 audio/vibevoice_dialogue.txt、audio/final_podcast.wav、audio/audio_manifest.json 和 audio/audio_report.md；这是 english-article-chinese-podcast-video 的默认音频 backend，替代旧的 Qwen3 按回合 TTS。
---

# VibeVoice 播客音频

这个 skill 负责默认 Gate 3：把已经定稿的 `Speaker 0` / `Speaker 1` 双人文稿一次性交给 VibeVoice，生成一条连续播客音轨。不要按 turn 生成，不要拼接，不要使用 Qwen/Qwen3 fallback，除非用户明确切回旧 backend。

## 输入

```text
<project>/podcast_script.md
```

文稿正文必须只使用：

```text
Speaker 0: 女主持/听众代理/追问者
Speaker 1: 男分析者/机制解释者
```

允许 `podcast_script.md` 有标题、来源和人物说明，但正式正文里的每个说话回合必须是 `Speaker 0:` 或 `Speaker 1:`。

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

`audio/vibevoice_dialogue_display.txt` 是从 `podcast_script.md` 抽出的观众显示稿，保留 `14%`、`290 万`、`GDP`、`2050` 等紧凑写法。`audio/vibevoice_dialogue.txt` 是真正喂给 VibeVoice 的 TTS 朗读稿，必须把这些表达归一化成更稳定的中文读法，例如 `百分之十四`、`二百九十万`、`G D P`、`二零五零`。

`audio_manifest.json` 记录脚本 hash、显示稿 hash、VibeVoice TTS 输入 hash、speaker map、每个 turn 的 `text` 和 `tts_text`、最终音频 hash 和时长。它不是字幕时间轴；字幕和章节不得用它猜精确时间。

音频格式职责固定如下：

- `audio/final_podcast.wav` 是内部母带和唯一对齐源。ASR、字幕时间轴、章节图时间轴和视频合成都以它为基准。
- `audio/final_podcast_preview.mp3` 是默认人工试听交付。向用户提供试听时优先给 MP3，不要让用户直接用播放器验收 24kHz mono WAV。
- `audio/final_podcast_playback.m4a` 是兼容播放副本。它可用于移动端/播放器确认听感，但不得作为 ASR/时间轴母带。
- 不要用 MP3/M4A 生成 `dialogue_timeline.json`。AAC/MP3 可能有 encoder delay、padding 或帧边界差异，虽然通常很小，但不应引入字幕/章节基准时间轴。

## 生成流程

1. 准备 VibeVoice 输入。

这一步必须同时写出两份文本：

- `audio/vibevoice_dialogue_display.txt`：原始显示文本，供排查和字幕/发布语义参考。
- `audio/vibevoice_dialogue.txt`：TTS 归一化文本，供 VibeVoice 读取。

TTS 归一化必须至少覆盖：

```text
14% -> 百分之十四
16% -> 百分之十六
60% -> 百分之六十
5% -> 百分之五
290 万 -> 二百九十万
3000 元 -> 三千元
100 万元 -> 一百万元
27 岁 -> 二十七岁
12 岁 -> 十二岁
2050 -> 二零五零
2025 年 -> 二零二五年
GDP -> G D P
```

字幕和章节图仍然使用显示文本，不要把口播归一化稿直接作为观众字幕。

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py \
  --project-dir <project>
```

2. 运行本地 VibeVoice：

```bash
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/run_article_vibevoice_audio.py \
  --project-dir <project>
```

正式音频必须使用 `run_article_vibevoice_audio.py`，不要在主流程里直接调用通用 `run_vibevoice_dialogue.py`。专用 runner 会写出：

```text
<project>/audio/vibevoice_generation_config.json
```

这个 config 明确区分 locked 参数和 tunable 参数。

## 参数策略

主流程先锁定所有不应该随文稿变化的参数，只保留少量音质参数给后续调试：

| 类型 | 参数 | 当前策略 |
| --- | --- | --- |
| 路径/模型 | `repo`, `model_path`, `txt_path`, `output_dir` | 锁定 |
| 设备 | `device=cpu`, `torch_dtype=float32`, `attn_implementation=eager` | 锁定 |
| prompt 机制 | `do_sample=True`, `prefill=True`, `voice_samples=True`, `checkpoint_path=None` | 锁定 |
| 角色编号 | `speaker_index_base=auto` | 锁定 |
| 条件贴合 | `cfg_scale=1.3` | 锁定 |
| 随机性复现 | `seed=42` | 锁定 |
| 音色 | `speaker_names` | 暂时可调；选定频道音色后锁定 |
| 采样 | `temperature`, `top_p` | 暂时可调；调出稳定听感后锁定 |
| 长度 | `max_length_times` | 暂时可调；生产稿稳定后锁定 |
| 质量/速度 | `ddpm_steps` | 暂时可调；正式发布不得用低步数 smoke 参数 |
| 日志显示 | `no_progress_bar` | 只影响命令行进度条，不影响音频 |

这些参数原则上不应该根据每篇文章动态漂移。文章变化应该主要体现在文稿内容，不是硬件、随机种子或 CFG。只有在音频失败重跑或调试 VibeVoice 质量时，才调整 tunable 参数；一旦找到稳定组合，就把 tunable 也锁成频道级默认。

可以临时调音质参数：

```bash
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/run_article_vibevoice_audio.py \
  --project-dir <project> \
  --speaker-names Xinran BowenClean \
  --temperature 0.9 \
  --top-p 0.9 \
  --max-length-times 1.6 \
  --ddpm-steps 10
```

当前频道默认音色是 `Xinran + BowenClean`。`BowenClean` 来自已试听通过的 `06_VV_zh-Bowen_man.wav`，不是旧的 repo-local `zh-Bowen_man.wav`。

本双人 skill 必须继续使用通用 wrapper 的 `--speaker-mode dialogue`。不要把双人播客文稿临时改成 single 模式；单人口播走 `english-article-chinese-single-host-video/skills/article-single-host-vibevoice-audio`。

兼容说明：本 skill 的产品语义仍是文章双人播客，正式 article 流程只接受 `Speaker 0` / `Speaker 1`。其中 `scripts/prepare_vibevoice_audio_inputs.py` 同时被 Worldview 播客流程复用做 TTS 文本归一化；当调用方显式传 `--min-speaker-turns 0` 时，该脚本可以保留 `Speaker 2` / `Speaker 3` 标签，供最多 4 人的冻结 roster 流程使用。

已知正常参考：`china_shock_front_two_chapters_vibevoice_speakers_generated.wav` 是 21 turn、约 1169 个中文字、212.8 秒的 VibeVoice-only 输出。它说明本机 VibeVoice 在足够长的上下文和稳定参数下可用，但不代表 6 句超短 smoke 稿也能稳定产生好听声音。

3. 把生成的 wav 复制或移动为正式音轨：

```text
<project>/audio/final_podcast.wav
```

如果 VibeVoice 原始 wav 含有长静音或整体音量偏低，先用本 skill 的后处理脚本把原始 wav 转成正式音轨。它只压缩长静音并做响度标准化，不改文稿、不切回 Qwen：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/postprocess_vibevoice_audio.py \
  --project-dir <project>
```

后处理不是坏音频修复器。如果原始 VibeVoice wav 的 `mean_volume < -30 dB` 或 `max_volume < -8 dB`，默认视为生成质量异常并失败；不要用 loudnorm 硬拉这种音频，否则声码器噪声、气泡音、拖尾和沙哑感会一起被放大。只有在明确做实验时才可传 `--allow-low-level-source`。

4. 回写最终音频信息：

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/prepare_vibevoice_audio_inputs.py \
  --project-dir <project> \
  --final-audio <project>/audio/final_podcast.wav
```

5. 导出人工试听/播放副本：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-vibevoice-audio/scripts/export_playback_audio.py \
  --project-dir <project>
```

正式汇报试听音频时给 `audio/final_podcast_preview.mp3`。只有在需要说明内部母带时才列出 WAV。

6. 运行音频 sanity check：

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

字幕和章节图只能使用 `dialogue_timeline.json` 的真实对齐时间，不得从字数、turn 顺序或 VibeVoice 生成进度猜时间。

进入字幕和章节图前，必须完成 turn 边界伪声检测。若 `audio/audio_artifact_qa.json` 为 `NEEDS_AI_REVIEW`，Codex 必须根据候选切片、频谱图、ASR overlap 和相邻 turn 文本写 `audio/audio_artifact_ai_review.json`。任何候选被判为 `artifact` 时，回到本音频 gate 重跑 VibeVoice 或做局部 patch，之后重新 ASR、重新检测；不要让带有“背景音/苍一声/音乐残响”的音频继续生产。

## CPU 测试策略

本机稳定后端是 CPU `float32`，质量可用但很慢。2026-06-10 的正常 VibeVoice-only 参考音频为 21 turn / 1169 字 / 212.8 秒输出，耗时约 38 分钟。后续 6-turn 超短 smoke 测试虽然能跑通链路，但出现过低音量、拖音、沙哑和发音跑偏，不能代表发布质量。

因此：

- 正式生产稿默认仍要求 18 turn 以上、完整播客结构。
- 本地 smoke/regression 可显式使用较短文稿，并在 lint 时传 `--min-turns 6`，但报告状态只能写 `pipeline smoke pass`。
- smoke 模式只能验证 VibeVoice、ASR、字幕、章节图和视频合成链路，不代表最终发布时长或听感质量。
- VibeVoice 输出后必须跑 ASR/script 和 ASR 词级置信度检查；正式发布建议 `matched_script_ratio >= 0.85`、`avg_word_probability >= 0.75`、`low_word_probability_ratio <= 0.25`。低于门槛必须换 seed/参数/文稿重跑，不能让字幕按错误音频继续生产。
- 发布前必须人工抽听 opening/middle/end 和至少 5 个 speaker switches。检查内容包括：沙哑、拖音、发音错字、角色串音、异常长静音、句尾含混和音量硬拉痕迹。

## Gate

通过条件：

```text
audio/vibevoice_dialogue.txt exists and only contains Speaker 0/Speaker 1 lines
audio/vibevoice_dialogue_display.txt exists and only contains Speaker 0/Speaker 1 lines
audio/tts_normalization_report.md exists
audio/final_podcast.wav exists and ffprobe passes
audio/audio_manifest.json exists
audio_manifest records audio_backend=vibevoice_longform
audio_manifest records script_sha256, display_dialogue_sha256, vibevoice_input_sha256, final_audio_sha256, duration_sec
audio_manifest records vibevoice_input_mode=tts_normalized
audio_manifest records all Speaker 0/Speaker 1 turns from podcast_script.md
audio_manifest turns record both text and tts_text
audio/audio_report.md exists
audio/final_podcast_preview.mp3 exists and ffprobe passes
audio/final_podcast_playback.m4a exists and ffprobe passes
audio/playback_audio_manifest.json exists
no long silence over 2 seconds after postprocess unless intentionally kept
raw VibeVoice wav is not suspiciously low-level before postprocess
audio/dialogue_timeline.json later reports ASR/script matched_script_ratio >= 0.85 for publish
audio/dialogue_timeline.json later reports avg_word_probability >= 0.75 and low_word_probability_ratio <= 0.25 for publish
audio/audio_artifact_qa.json later exists and either passes or has a complete AI review with no artifact decisions
spot checks of opening/middle/end confirm normal voices, normal speed, clear pronunciation, and natural turn-taking
```

如果 VibeVoice CPU 生成太慢，报告预计耗时；不要自动切换到 Qwen。
