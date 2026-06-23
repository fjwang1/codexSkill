---
name: chinese-voiceover-audio-generation
description: "用于从中文配音段 JSON 生成自然连续的中文 TTS 配音音频，尤其适合 YouTube 外文视频中文化流程：使用本地 Qwen3-TTS/MLX、可选音色克隆、逐段 draft 音频、连续主音轨、manifest 和音频质检。"
---

# 中文配音音频生成

使用这个 skill 将 `voiceover-segments.v1` JSON 转成自然连续的中文配音音频。用于正式 YouTube 中文配音生产时，默认必须走 `voice_clone_only`，也就是从原视频原声音频裁取参考人声并全片复用同一个音色 profile。

本 skill 只负责 **TTS 配音音频生成**，不负责最终视频合成，也不负责剪视频。最终合成应由后续视频合成/剪辑 skill 处理：静音原视频、按自然配音剪画面、叠加中文主音轨并导出 MP4。

## 职责边界

本 skill 负责：

- 读取中文配音段 JSON。
- 准备或接收音色克隆参考音频。
- 按段生成 `draft-segments/*.wav`。
- 拼接成自然连续主音轨 `final_voiceover.continuous.*`。
- 输出 `manifest.json`、报告和机械质检结果。

本 skill 不负责：

- 外文字幕翻译或中文配音稿改写。
- 重新清洗、润色或改写 `voice_text` 的内容。
- 把音频硬拉长到原视频时长。
- 生成不自然的 `chapter_aligned` 默认版本。
- 视频剪辑、画面调速、mute 原视频、封装 MP4。

如果自然音频比原视频短，默认结论不是“拉慢音频”，而是交给视频剪辑阶段处理。

## 输入

必需输入：

- `voiceover_segments_path`：配音稿分段 JSON，也就是 `voiceover-segments.v1` 文件。必须包含 `segments[].voice_text` 和稳定的 `segment_id`。
- `reference_text_path` 或 `reference_text`：参考音频对应的原文文本。
- 模型目录：本地 MLX 版 Qwen3-TTS Base 模型，或用户指定的其他 TTS 模型。

音色克隆输入二选一：

- `reference_audio_path`：已经裁好的音色克隆参考音频，WAV 优先。
- `source_audio_path` + `reference_time_range`：只有源音频时，先从音频中裁出参考片段，再生成配音。

可选输入：

- `output_dir`：输出目录。

不要把原视频作为本 skill 输入。若只有视频，必须先由素材准备/视频处理阶段抽出音频，再把音频路径交给本 skill。

正式生产硬规则：

- `mode` 必须是 `voice_clone_only`，除非用户明确授权预设音色。
- 同一个视频只能使用一个 `voice_profile.json`；局部重生成、修复段和全片重跑都必须复用同一个 profile。
- `manifest.json` 必须记录 `ref_audio_path`、`ref_audio_sha256`、`ref_text_path` 或 `ref_text`、`ref_text_sha256`、`model_dir`、`lang_code`。
- `ref_text_sha256` 指实际送入 TTS 的规范化参考文本 hash；如果输入来自 `reference_text.txt`，应额外记录 `ref_text_file_sha256` 与 `ref_text_hash_mode`。验收时必须区分“文件原始字节 hash”和“规范化 TTS 文本 hash”，不要因为文件末尾换行误判音色证据链。
- 不得在同一个最终音频中混用不同 voice preset、不同 reference audio、不同 reference text 或不同模型目录。
- 如果复用已有 `draft-segments/*.wav`，必须先确认旧 draft 的 manifest hash 与当前 `voice_profile.json` 完全一致；否则必须 `--force` 重新生成。

### 配音稿分段 JSON 格式

`voiceover_segments_path` 指向的文件必须是 UTF-8 JSON 对象，不是 Markdown、SRT 或普通数组。

最小格式：

```json
{
  "schema_version": "voiceover-segments.v1",
  "video_id": "VIDEO_ID",
  "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "title": "Video title",
  "source_script_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-script.md",
  "language": "zh-CN",
  "segmentation_mode": "semantic",
  "time_allocation_mode": "chapter_proportional_derived",
  "segments": [
    {
      "segment_id": "voice_001",
      "start": "00:00:00",
      "end": "00:00:19.729",
      "target_duration_sec": 19.729,
      "semantic_label": "开场论点",
      "voice_text": "中国电动车已经把竞争对手甩在身后。\n它们比美国最便宜的电动车还低几万美元。",
      "source_time_range": "00:00:00-00:03:17",
      "estimated_speech_sec": 16.429,
      "line_count": 2,
      "time_source": "derived_from_chapter_range"
    }
  ]
}
```

真实风格样例：

```json
{
  "schema_version": "voiceover-segments.v1",
  "video_id": "UhhZu0ZHdw4",
  "video_url": "https://www.youtube.com/watch?v=UhhZu0ZHdw4",
  "title": "How the West Lost to China in EVs",
  "source_script_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-script.md",
  "language": "zh-CN",
  "segmentation_mode": "semantic",
  "time_allocation_mode": "chapter_proportional_derived",
  "time_source": "derived_from_chapter_range",
  "segments": [
    {
      "segment_id": "voice_001",
      "start": "00:00:00",
      "end": "00:00:19.729",
      "target_duration_sec": 19.729,
      "semantic_label": "开场论点：中国电动车领先",
      "voice_text": "中国电动车已经把竞争对手甩在身后。\n它们比美国最便宜的电动车还低几万美元，却能比二十五万美元的保时捷 Taycan 更快，续航甚至达到任何特斯拉的两倍。",
      "source_time_range": "00:00:00-00:03:17",
      "estimated_chars": 69,
      "estimated_speech_sec": 16.429,
      "line_count": 2,
      "time_source": "derived_from_chapter_range"
    },
    {
      "segment_id": "voice_002",
      "start": "00:00:19.729",
      "end": "00:00:48.407",
      "target_duration_sec": 28.678,
      "semantic_label": "功能、供应链与比亚迪案例",
      "voice_text": "有些车配折叠桌、按摩椅、冰箱和二十一英寸 OLED 屏；有些能喷香氛、横向挪进车位，还免费标配自动驾驶技术。\n这不是单纯靠廉价劳动力和大工厂堆出来的。\n比亚迪自己开采锂，生产被刺穿也不易起火的电池，甚至做出了能短暂在水上行驶的车。",
      "source_time_range": "00:00:00-00:03:17",
      "estimated_chars": 121,
      "estimated_speech_sec": 28.81,
      "line_count": 3,
      "time_source": "derived_from_chapter_range"
    }
  ]
}
```

音频生成必需字段：

- 顶层 `schema_version`: 必须是 `voiceover-segments.v1`。
- 顶层 `segments`: 非空数组。
- `segments[].segment_id`: 稳定唯一 ID，推荐 `voice_001` 这种可排序格式。
- `segments[].voice_text`: 已经适合 TTS 的中文口播文本。

强烈推荐字段：

- `video_id`、`video_url`、`title`: 写入 manifest，方便追踪。
- `source_script_path`: 上游中文配音稿路径。
- `language`: 推荐 `zh-CN`。
- `start`、`end`、`target_duration_sec`: 后续视频剪辑会用到；即使本 skill 不做视频合成，也应保留。
- `semantic_label`: 方便日志和人工定位。
- `source_time_range`: 如果时间点是从章节派生的，必须保留原章节范围。

字段约束：

- `voice_text` 只能包含要朗读的文本，不得包含 Markdown 标题、front matter、JSON 字段名、注释或校验说明。
- `voice_text` 中可以有真实换行，表示轻停顿；不要写字面量 `\n`。
- `voice_text` 不要断在顿号 `、` 后，不要切开专有名词、数字、URL 或固定短语。
- `segment_id` 不得重复。
- 如果存在 `start` / `end`，必须满足 `start < end` 且整体时间单调不重叠。
- `target_duration_sec` 单位为秒，若存在，应与 `start` / `end` 基本一致。

参考片段长度必须明确：

- 推荐：`10-20s` 干净单人声。
- 可接受：`5-30s`。
- 少于 `5s`：通常音色信息不足，除非只是快速试跑。
- 超过 `30s`：不要默认传给模型；先裁成更干净的 `10-20s`。
- 如果输入是源音频片段，也按其中可用人声长度计算，不按音频文件总长度计算。

输入样例，已有参考音频：

```json
{
  "voiceover_segments_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-segments.json",
  "output_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/tts",
  "model": {
    "provider": "qwen3-tts-mlx",
    "model_dir": "$QWEN_TTS_MODEL_DIR",
    "python": "$QWEN_TTS_PYTHON"
  },
  "voice_clone": {
    "reference_audio_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/voice-clone/reference.wav",
    "reference_text_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/voice-clone/reference_text.txt",
    "reference_language": "en",
    "reference_duration_sec": 20.0,
    "reference_source": {
      "source_audio_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.wav",
      "time_range": "00:01:14-00:01:34"
    }
  },
  "generation_options": {
    "lang_code": "zh",
    "inter_segment_pause_sec": 0.15,
    "output_format": "m4a"
  }
}
```

输入样例，只有源音频、需要先截参考音频：

```json
{
  "voiceover_segments_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-segments.json",
  "source_audio_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.wav",
  "source_transcript_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/subtitles/VIDEO_ID.en.plain.txt",
  "reference_selection": {
    "time_range": "00:01:14-00:01:34",
    "target_duration_sec": 20,
    "requirements": [
      "single_speaker",
      "no_background_music",
      "no_overlapping_speech",
      "stable_volume"
    ]
  },
  "output_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/tts"
}
```

调用提示样例：

```text
使用 chinese-voiceover-audio-generation：
输入配音稿分段 JSON：/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/04-voiceover-segments/voiceover-segments.json。
使用源音频 00:01:14-00:01:34 的干净单人声作为音色克隆参考。
参考片段约 20 秒，参考文本来自同一时间段字幕。
生成自然连续中文主音轨，不生成 chapter_aligned 默认版本。
先生成 5 段样本并质检，通过后再生成全片。
```

环境变量示例：

```text
QWEN_TTS_MODEL_DIR=/path/to/Qwen3-TTS-12Hz-1.7B-Base-8bit
QWEN_TTS_PYTHON=/path/to/qwen-tts-venv/bin/python
```

如果项目已有本地配置、脚本参数或用户指定路径，优先使用它们。全局 skill 不能依赖某一台机器的个人目录。

## 输出

输出目录至少包含：

- `draft-segments/*.wav`：每个配音段的原始 TTS 结果。
- `final_voiceover.continuous.wav` / `.m4a`：自然连续主音轨，后续视频合成使用它。
- `manifest.json`：模型、参考音频、参数、段落时长、输出路径。
- `voiceover-audio-report.md` 或 `sync-report.md`：给人看的音频生成报告。
- 音频质检 JSON 或终端结果：音量、削波、静音、段音频缺失、异常短段。

不要默认交付 `chapter_aligned`。如果旧脚本顺手生成了它，也只能作为调试对照，不作为推荐音轨。

`manifest.json` 最小稳定契约：

```json
{
  "schema_version": "continuous-clone-voiceover.v1",
  "source_voiceover_segments_path": "...",
  "video_id": "...",
  "model_dir": "...",
  "mode": "voice_clone_only",
  "ref_audio_path": "reference.wav",
  "ref_audio_sha256": "...",
  "ref_text": "...",
  "ref_text_path": "reference_text.txt",
  "ref_text_sha256": "...",
  "voice_profile": {
    "mode": "voice_clone_only",
    "model_dir": "...",
    "ref_audio_path": "reference.wav",
    "ref_audio_sha256": "...",
    "ref_text_path": "reference_text.txt",
    "ref_text_sha256": "...",
    "lang_code": "zh"
  },
  "reference_source": {
    "source_audio_path": "...",
    "time_range": "00:01:14-00:01:34"
  },
  "parameters": {
    "inter_segment_pause_sec": 0.15,
    "lang_code": "zh"
  },
  "outputs": {
    "continuous": {
      "audio_path": "final_voiceover.continuous.m4a",
      "wav_path": "final_voiceover.continuous.wav",
      "m4a_path": "final_voiceover.continuous.m4a"
    }
  },
  "segment_count": 0,
  "continuous_duration_sec": 0.0,
  "segments": [
    {
      "segment_id": "voice_001",
      "draft_audio_path": "draft-segments/voice_001.wav",
      "tts_duration_sec": 0.0
    }
  ]
}
```

路径可以是绝对路径，也可以相对 `manifest.json` 所在目录。时间单位一律为秒。

## 生成策略

### 1. 按上游批次做真实 TTS 诊断

长视频不要直接全片盲跑。若上游使用 `youtube-audio-anchor-dubbing`，本 skill 必须按上游批次生成真实 TTS draft，而不是随便抽 2-5 段样本就进入全片。

批次诊断要求：

- 输入应是 `voiceover-segments.batch_NNN.json` 或 duration-fit subset JSON。
- 使用正式 `voice_profile.json`、正式模型目录、正式参考音频和正式停顿参数。
- 覆盖该批全部 `must_align` 段；普通段按上游要求抽样或全量覆盖。
- 输出本批 `manifest.json`，供 `build_duration_fit_diagnostics.py` 生成标准时长诊断。
- 标准时长诊断以 `segment_pass_rate >= 0.90` 作为整体 PASS；少数段级失败应写入 warning 清单，不要为了边缘段无限重生。
- 批次整体失败时，只重生失败段或受影响相邻段；不要对已通过批次全量 `--force`。
- 所有批次的整体通过率都达到 90% 后，才允许生成或汇总全片正式主音轨。

普通非锚点任务可以先生成 2-5 段样本，检查：

- 模型能否加载。
- 参考音频和参考文本是否可用。
- 中文发音是否正常。
- 音量是否正常，是否有削波。
- 段间停顿是否过长。
- 生成速度和机器负载是否可接受。

样本通过后再继续；但对于需要画面/语义锚点对齐的视频，样本通过不等于全片可生成，仍必须完成所有锚点批次诊断。

### 2. TTS 文本输入

上游配音稿/分段 skill 应该已经产出适合朗读的 `voice_text`。本 skill 不做内容级清洗，不改写句子，不删改事实、数字、品牌名或英文术语。

音频阶段只允许做机械规范化：

- 去掉 Markdown、front matter 和 JSON 字段名等非正文内容。
- 将真实换行转成空格或轻停顿；不要让 `\n` 被当作字符朗读。
- 保留中文标点、数字、品牌名、英文术语和 URL。
- 如果某一行确实缺少句末标点，可以补 `。`，但不要在顿号、逗号、冒号等未完成结构后强行补句号。

如果发现 `voice_text` 内容怪、断句不自然、术语不统一或不适合朗读，应回到上游配音稿/分段 skill 修，不要在音频阶段偷偷改稿。

### 3. 音色克隆

音色克隆输入必须包含参考音频和参考文本。

参考音频要求：

- 单人声，尽量无背景音乐、无重叠说话。
- 音量稳定，无明显爆音、混响或环境噪声。
- 推荐 `10-20s`，可接受 `5-30s`；超过 `30s` 先裁短，少于 `5s` 只适合快速试跑。
- WAV 优先，采样率可由工具统一转换。

参考文本要求：

- 与参考音频逐字或高度一致。
- 如果来自源音频，应记录 `reference_time_range` 和来源路径。
- 如果无法确认参考文本，不要假装已经克隆可靠。

如果用户提供了源音频但没有提供裁好的参考音频：

1. 从源音频中寻找一段干净单人声。
2. 截取 5-20 秒为 `reference.wav`。
3. 从对应字幕、转写文本或人工记录中取得同一时间段文本，保存为 `reference_text.txt`。
4. 生成前先确认这段参考音频和文本能被模型使用。

克隆只表示尽量贴近音色、音高和说话质感，不等于完整复刻原视频的情绪、节奏和表演。

如果用户要求情绪、预设音色或文字描述音色：

- Base 模型主要做音色克隆，不可靠承诺情绪控制。
- CustomVoice 模型更适合预设音色、情绪和语速。
- VoiceDesign 模型更适合按文字描述创建声音。
- 在没有验证前，不要声称某个模型已经实现了情绪克隆。

### 4. 自然连续主音轨

默认只生成自然连续主音轨：

- 段间停顿通常控制在 `0.10-0.20s`。
- 不为了匹配原视频时长而放慢整章音频。
- 不把空白硬塞到段尾或章尾。
- 真实音频时长以 TTS 输出为准。

如果自然配音比原视频短，这是视频剪辑阶段的问题。后续应通过剪画面、删转场、压缩无信息片段、重排 B-roll 或局部调整画面速度解决。

## 推荐命令

项目中如果存在 `scripts/generate_continuous_clone_voiceover.py`，可以使用它生成连续主音轨；即使脚本额外生成 `chapter_aligned`，也不要把它作为推荐产物：

```bash
/path/to/qwen-venv/bin/python scripts/generate_continuous_clone_voiceover.py \
  path/to/voiceover-segments.json \
  --output-dir path/to/output-dir \
  --model-dir /path/to/Qwen3-TTS-12Hz-1.7B-Base-8bit \
  --ref-audio path/to/reference.wav \
  --ref-text-file path/to/reference_text.txt \
  --inter-segment-pause-sec 0.15
```

如果后续需要把 draft 段按原声音频锚点逐段对齐，必须把本脚本输出的 TTS manifest 传给对齐脚本：

```bash
python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-audio-anchor-dubbing/scripts/align_draft_segments.py \
  --segments path/to/voiceover-segments.json \
  --draft-dir path/to/output-dir/draft-segments \
  --tts-manifest path/to/output-dir/manifest.json \
  --output-dir path/to/segment-aligned-audio
```

先跑样本：

```bash
... --limit 5 --force
```

如果已有 `draft-segments/*.wav`，不要轻易用 `--force`，因为它通常会重新生成所有段音频。

### 5. 返工与局部重跑

Qwen3-TTS 这类生成式 TTS 对同一段文本重跑时，真实时长可能有轻微波动。已经通过时长和听感验收的 draft 段，不要为了修一两个节点而全量重生。

如果 manifest 或人工试听只暴露少数失败段：

1. 回到上游配音稿/分段 JSON 修改对应 `voice_text`。
2. 只删除失败段对应的 `draft-segments/{segment_id}.wav`。
3. 重新运行生成脚本，但不要加全量 `--force`。
4. 如果脚本支持，使用 `--force-align` 或等价参数，复用已通过的 draft WAV，只重建连续主音轨、报告和 manifest。
5. 再次跑 manifest/音频质检；仍失败时继续局部修稿和局部重跑。

只有当参考音频、模型、语速、停顿策略或全局声音质量不对时，才全量删除或全量 `--force` 重跑。

对于锚点配音流程，局部返工还必须遵守：

- `segment_id`、`start`、`end`、`target_duration_sec` 默认不变；只有上游锚点文件明确修订时才允许改时间。
- 修改 `voice_text` 后必须产生新的 `voice_text_sha256` 或等价记录。
- 旧 draft 只有在 `voice_text_sha256`、voice profile、模型和参数都一致时才能复用。
- 若失败原因是 `tail_silence_sec` 过大，优先回稿补回源窗口事实，而不是补静音。
- 若失败原因是 `tempo_factor > 1.15`，优先压缩冗余中文或拆成更合理的原声锚点窗口，而不是强行加速。

## 质检

完成后必须做机械质检。若本 skill 的脚本存在，运行：

```bash
python3 {skill_dir}/scripts/evaluate_voiceover_audio.py path/to/manifest.json
```

检查重点：

- `continuous` 输出文件存在。
- 所有 `draft-segments` 存在，且没有 0 秒或近 0 秒音频。
- `continuous` 没有异常长静音。
- 音频峰值不要接近 0 dBFS；出现削波或爆音必须重做或归一化。
- 平均音量过低时，后续合成前应 loudness normalize。
- 如果旧脚本额外生成 `chapter_aligned`，可以附带检测，但不作为主产物。

机械质检不能替代人工试听。它只能判断文件、时长、静音和音量风险。

硬性失败与软性复核建议：

- `continuous` 出现超过约 2 秒的静音：失败。
- draft 段音频缺失、0 秒或近 0 秒：失败。
- 音频峰值接近 0 dBFS：失败。
- 平均音量过低或过高：复核或做 loudness normalization。

## 反馈闭环

如果输出不合适，先判断问题属于哪一层：

- 发音、错读、内容怪：回到配音稿或分段文本。
- 声音不像、音色飘：更换或清理参考音频/参考文本。
- 情绪不够：不要硬说 Base 模型能解决；改用 CustomVoice/VoiceDesign 或等待专门情绪方案。
- 停顿太长：检查段间停顿和分段，不要生成 `chapter_aligned` 来硬补。
- 音频太短：交给视频剪辑阶段；只有确实漏掉源字幕信息时，才回到配音稿补内容。
- 音频太长：先听是否自然；必要时回到配音稿压缩重复表达，不要过度加速。

常规生成任务中，不要默认修改本 skill。只有用户明确要求维护、升级或优化本 skill 时，才修改 skill 本身。

## 交付

完成后告诉用户：

- 输入 segments JSON 路径。
- 模型、参考音频、参考文本和参考来源。
- 输出目录。
- 连续主音轨路径。
- 段数和连续音频时长。
- 质检是否通过。
- 仍需人工试听或后续视频合成阶段处理的问题。

不要在最终回答中贴 manifest 全文。
