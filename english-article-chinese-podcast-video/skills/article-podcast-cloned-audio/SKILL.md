---
name: article-podcast-cloned-audio
description: Legacy fallback：使用已冻结的 voice_profile 和男女声参考音频，为中文双人播客稿按 speaker turn 逐回合生成 Qwen3-TTS 克隆音轨。仅当用户明确要求旧 Qwen3/Base/ref_audio 工作流或调试旧项目时使用；默认 english-article-chinese-podcast-video 主流程应使用 article-podcast-vibevoice-audio。
---

# 播客克隆音轨

这个 skill 是旧 Qwen3 按回合 TTS fallback，不再是正式默认音频主线。新项目默认使用 `article-podcast-vibevoice-audio` 整篇生成，再用 `article-podcast-audio-alignment` 对最终音频做 ASR/forced alignment。

只有在用户明确要求 Qwen3/Base/ref_audio 工作流、或旧项目必须复现旧产物时，才使用本 skill。使用本 skill 时仍必须使用冻结参考音频克隆，不得每段重新用 VoiceDesign 描述生成。

## 输入

```text
<project>/podcast_script.md
<project>/voice/voice_profile.json
<project>/voice/voice_profile.lock.json
<project>/voice/linyao_reference.wav
<project>/voice/linyao_reference.txt
<project>/voice/chenche_reference.wav
<project>/voice/chenche_reference.txt
```

## 输出

```text
<project>/audio/
  draft-turns/
  final_podcast.wav
  tts_manifest.json
  audio_report.md
```

## 生成单位

正式 TTS 生成单位是 **speaker turn**：

```text
林遥：一段连续发言。
陈澈：一段连续发言。
```

不是章节。章节可能 5-12 分钟，太长，只能作为内容结构和视觉切换参考。

推荐长度：

- 林遥：5-20 秒，约 30-100 中文字。
- 陈澈：20-60 秒，约 100-250 中文字。
- 陈澈超过 60-75 秒时，优先回到文稿里拆成两个自然回合，让林遥插入追问或确认。
- 单回合仍过长时，按语义段切块，不要机械按固定字数切碎。

## 正式生成规则

- 林遥片段必须使用 `linyao_reference.wav + linyao_reference.txt`。
- 陈澈片段必须使用 `chenche_reference.wav + chenche_reference.txt`。
- 所有 chunk 都用 `voice_profile.json` 里的 `clone_model_dir`、`speed`、`temperature`、`lang_code`。
- 每个 draft wav 的缓存键必须包含：角色、文本、voice_profile_hash、ref_audio_hash、ref_text_hash、生成参数。
- 如果缓存 wav 已存在且 hash 匹配，不要重生成。
- 回合之间默认加入约 `0.35s` 静音。

## Qwen 调用形态

正式片段应使用 Base 模型：

```python
generate_audio(
    model=clone_model,
    text=turn_text,
    ref_audio=str(role_ref_audio),
    ref_text=role_ref_text,
    output_path=str(tmp_dir),
    speed=speed,
    temperature=temperature,
    verbose=False,
)
```

不要用：

```python
generate_audio(text=turn_text, instruct=design_instruct, ...)
```

来生成正式片段。

## tts_manifest.json

至少记录：

```json
{
  "schema_version": "article-podcast-cloned-audio.v1",
  "script_sha256": "...",
  "voice_profile_sha256": "...",
  "final_audio": "audio/final_podcast.wav",
  "final_audio_sha256": "...",
  "chunks": [
    {
      "turn_index": 1,
      "chunk_index": 1,
      "role": "林遥",
      "text": "...",
      "wav": "audio/draft-turns/turn_0001_林遥.wav",
      "wav_sha256": "...",
      "ref_audio_sha256": "...",
      "ref_text_sha256": "...",
      "duration_sec": 8.42,
      "generation_mode": "qwen3_tts_base_ref_audio_ref_text_clone"
    }
  ]
}
```

## Gate

通过条件：

```text
audio/final_podcast.wav exists and ffprobe passes
audio/tts_manifest.json exists
audio/audio_report.md exists
all speaker turns in podcast_script.md are represented
all formal chunks use frozen ref_audio/ref_text cloning
tts_manifest records script_hash and voice_profile_hash
tts_manifest records each chunk text, role, wav_hash, ref_audio_hash, duration
tts_manifest records generation_mode for each chunk, and it must indicate Base ref_audio/ref_text cloning
spot checks of opening/middle/end confirm stable voices and normal turn-taking
```

如果文稿或 voice profile 的 hash 变化，`audio/final_podcast.wav` 失效，必须重做。
