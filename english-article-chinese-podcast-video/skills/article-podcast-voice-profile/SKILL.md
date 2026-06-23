---
name: article-podcast-voice-profile
description: Legacy fallback：为旧 Qwen3 按回合 TTS 流程生成并冻结男女声参考音频和 voice_profile。仅当用户明确要求 Qwen3 VoiceDesign/Base voice cloning 或调试旧项目时使用；默认 english-article-chinese-podcast-video 主流程应跳过本 skill，改用 article-podcast-vibevoice-audio。
---

# 播客声音定稿

这个 skill 是旧 Qwen3 turn-level clone 路线的一部分，不再是默认正式主线。新项目默认跳过本 skill，直接使用 `article-podcast-vibevoice-audio` 生成 VibeVoice long-form 音频。

只有在用户明确要求 Qwen3 VoiceDesign/Base voice cloning、或旧项目必须复现旧音色时，才使用本 skill。它不生成正式长音轨；旧路线的正式长音轨由 `article-podcast-cloned-audio` 使用冻结参考音频克隆生成。

## 输入

```text
<project>/podcast_script.md
```

文稿必须已经定稿，并且正文只有：

```text
林遥：...
陈澈：...
```

## 输出

```text
<project>/voice/
  voice_design_brief.md
  linyao_reference.wav
  linyao_reference.txt
  chenche_reference.wav
  chenche_reference.txt
  dialogue_sample.wav
  voice_profile.json
  voice_profile.lock.json
```

## 默认环境

```text
QWEN_TTS_PYTHON=/Users/wangfangjia/code/qwen3-tts-apple-silicon-test/.venv/bin/python
QWEN_VOICE_DESIGN_MODEL_DIR=/Volumes/GT34/AI/qwen3-tts-apple-silicon-test-models/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit
QWEN_BASE_MODEL_DIR=/Volumes/GT34/AI/qwen3-tts-apple-silicon-test-models/Qwen3-TTS-12Hz-1.7B-Base-8bit
```

必须使用 `QWEN_TTS_PYTHON`，系统 Python 通常没有 `mlx_audio`。

## 流程

1. 读完整 `podcast_script.md`。
   - 判断本期内容气质：经济/产业/科技/调查/人物、严肃程度、情绪边界、是否需要压低戏剧性。
   - 保存 `voice_design_brief.md`。

2. 写两段 VoiceDesign 描述。
   - 林遥：女主持，追问、转场、替听众确认问题。
   - 陈澈：男分析者，解释机制、数字和背景。
   - 描述只写声音、年龄感、距离感、语速、停顿、情绪边界。
   - 不要把文章事实、标题、数字或观点写进声音描述。

3. 从文稿中选参考文本。
   - 每个角色选 12-30 秒左右内容。
   - 优先选有代表性的自然句，不要选列表、标题或太多英文缩写。
   - `*_reference.txt` 必须和参考音频实际朗读内容一致。

4. 用 VoiceDesign 生成参考音频。
   - `linyao_reference.wav`
   - `chenche_reference.wav`

5. 生成短 `dialogue_sample.wav`。
   - 用两个参考声音各读一小段，拼接成 20-60 秒对话样本。
   - 只用于人工听感检查。

6. 冻结 profile。
   - 写 `voice_profile.json`。
   - 写 `voice_profile.lock.json`，记录所有 hash。

## voice_profile.json

至少包含：

```json
{
  "schema_version": "article-podcast-voice-profile.v2",
  "provider": "qwen3-tts-mlx-clone-from-voicedesign-anchor",
  "design_model_dir": "/Volumes/GT34/AI/qwen3-tts-apple-silicon-test-models/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
  "clone_model_dir": "/Volumes/GT34/AI/qwen3-tts-apple-silicon-test-models/Qwen3-TTS-12Hz-1.7B-Base-8bit",
  "speed": 0.94,
  "temperature": 0.7,
  "lang_code": "zh",
  "sample_rate": 24000,
  "silence_between_turns_sec": 0.35,
  "voices": {
    "林遥": {
      "role": "female_host",
      "design_instruct": "...",
      "ref_audio": "voice/linyao_reference.wav",
      "ref_text": "voice/linyao_reference.txt"
    },
    "陈澈": {
      "role": "male_expert",
      "design_instruct": "...",
      "ref_audio": "voice/chenche_reference.wav",
      "ref_text": "voice/chenche_reference.txt"
    }
  }
}
```

## lock 文件

`voice_profile.lock.json` 至少记录：

```json
{
  "script_sha256": "...",
  "voice_profile_sha256": "...",
  "references": {
    "林遥": {
      "ref_audio_sha256": "...",
      "ref_text_sha256": "..."
    },
    "陈澈": {
      "ref_audio_sha256": "...",
      "ref_text_sha256": "..."
    }
  }
}
```

## Gate

通过条件：

```text
voice/voice_design_brief.md exists
voice/linyao_reference.wav exists and ffprobe passes
voice/linyao_reference.txt exists
voice/chenche_reference.wav exists and ffprobe passes
voice/chenche_reference.txt exists
voice/dialogue_sample.wav exists and ffprobe passes
voice/voice_profile.json exists
voice/voice_profile.lock.json exists
lock records script_hash, voice_profile_hash, ref_audio_hashes, ref_text_hashes
```

冻结后不要覆盖 `voice_profile.json`。如果要重新调音，创建新版本，例如 `voice_profile.v2.json`，并让后续音频、字幕和视频全部失效重做。

## 重要限制

VoiceDesign 本身不是数学意义上的稳定 speaker embedding。正式一致性来自：

- 固定参考音频和参考文本。
- 后续用 Base 模型做 `ref_audio + ref_text` cloning。
- 不重生成已经缓存的 draft wav。

所以正式音轨不得每段继续用 VoiceDesign 描述生成。
