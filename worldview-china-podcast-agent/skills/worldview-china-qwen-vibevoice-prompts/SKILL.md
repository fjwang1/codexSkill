---
name: worldview-china-qwen-vibevoice-prompts
description: "Mandatory bridge for English or other non-Chinese Worldview China podcast sources: build Chinese VibeVoice voice prompts from extracted original speaker clips by using Qwen3-TTS only as a short Chinese voice-prompt bridge. Use after worldview-china-source-voice-prompts has produced 02b-source-voice-prompts/voice_prompt_manifest.json and before any full VibeVoice audio generation for non-Chinese source videos."
---

# Worldview China Qwen VibeVoice Prompts

Use this skill after `02b Source Voice Prompts` and before `05 VibeVoice Chunks`.

For English or other non-Chinese source videos, this node is mandatory. The goal is not to generate the full podcast audio with Qwen3. The goal is to create two short Chinese prompt WAVs, one per source speaker, so VibeVoice receives Chinese voice prompts instead of English source clips.

## Inputs

Required:

```text
<run_dir>/02b-source-voice-prompts/voice_prompt_manifest.json
<run_dir>/02b-source-voice-prompts/speaker_roster.json
<run_dir>/02a-speaker-census/speaker_roster.json
<run_dir>/02-source-capture/source_transcript.en.json
```

`02b-source-voice-prompts/speaker_roster.json` must be derived from the frozen 02a census roster, not re-created during Qwen prompt generation. `source_transcript.en.json` is used to recover the English `reference_text` matching the selected source clip. If it is absent, the script falls back to `selected_clips[].text_preview`; if no usable text exists, stop and fix the source capture or 02b manifest. Do not skip this node for English source videos.

Local Qwen3 defaults:

```text
/Users/wangfangjia/code/qwen3-tts-apple-silicon-test/.venv/bin/python
/Users/wangfangjia/code/qwen3-tts-apple-silicon-test/models/Qwen3-TTS-12Hz-1.7B-Base-8bit
```

## Standard Command

Run from anywhere:

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-qwen-vibevoice-prompts/scripts/build_qwen_vibevoice_prompts.py \
  --run-dir /Volumes/GT34/Generated/world_and_china_podcast/YYYYMMDD_N \
  --force
```

Quick path check without loading Qwen3:

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-qwen-vibevoice-prompts/scripts/build_qwen_vibevoice_prompts.py \
  --run-dir /Volumes/GT34/Generated/world_and_china_podcast/YYYYMMDD_N \
  --dry-run
```

Outputs:

```text
<run_dir>/02c-qwen-vibevoice-prompts/
├── prompt_manifest.seed.json
├── qwen_generation_input.json
├── qwen_generation.stdout.txt
├── qwen_generation.stderr.txt
├── qwen_speaker0/qwen_prompt_000.wav
├── qwen_speaker1/qwen_prompt_000.wav
├── reference/speaker0/reference.wav
├── reference/speaker1/reference.wav
├── registered/zh-<VoiceName>_qwenzh.wav
├── voice_prompt_manifest.json
└── voice_prompt_report.md
```

By default, the final normalized prompt WAVs are also copied into:

```text
/Users/wangfangjia/code/VibeVoice/demo/voices/
```

Use `--no-register-voices` only for audits; downstream VibeVoice generation normally requires registration.

## Method

For each `Speaker 0` / `Speaker 1`:

1. Read `02b-source-voice-prompts/voice_prompt_manifest.json`.
2. Prefer one clean selected source clip of about `8-20s`; fall back to the 02b concatenated reference only when no selected clip exists.
3. Extract the matching English `reference_text` from `source_transcript.en.json` by time overlap.
4. Reject the clip if `reference_text` contains music markers, sponsor/ad copy, URLs/contact reads, finance-ad language, or obvious rolling-caption repetition.
5. Ask Qwen3-TTS for a short Chinese target sentence using:

```text
reference_audio = clean original English speaker clip
reference_text  = matching English text for that clip
target_text     = short Chinese natural speech prompt
lang_code       = zh
```

6. Normalize Qwen output to mono 24 kHz PCM WAV with loudness around `I=-18`, `TP=-1.5`.
7. Register the result as a VibeVoice voice named like:

```text
WC<Run>Speaker0QwenZH
WC<Run>Speaker1QwenZH
```

This keeps Qwen3 responsible for cross-lingual Chinese prompt creation, while VibeVoice remains responsible for the full continuous dialogue audio.

## Validation

After generation, require:

- `voice_prompt_manifest.json.status == "pass"`.
- Both speakers have `speaker_voices[Speaker N].vibevoice_name`.
- Both registered WAVs exist in `/Users/wangfangjia/code/VibeVoice/demo/voices/`.
- WAV format is `pcm_s16le`, `24000 Hz`, `mono`.
- Duration is normally `5-30s`.
- No long silence; `silence_ratio` should be low.
- `reference_text` must correspond to the frozen source speaker and must not be sponsor/music/rolling-caption noise.

Useful checks:

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels \
  -of default=noprint_wrappers=1 <registered.wav>

ffmpeg -hide_banner -i <registered.wav> -af volumedetect -f null - 2>&1 | tail -n 12
ffmpeg -hide_banner -i <registered.wav> -af silencedetect=noise=-45dB:d=1 -f null - 2>&1 | rg 'silence_(start|end)' || true
```

Before a long run, generate a 1-2 chunk VibeVoice audition and ask the user to evaluate timbre/language naturalness.

## Downstream Integration

The downstream VibeVoice chunk node must use:

```text
<run_dir>/02c-qwen-vibevoice-prompts/voice_prompt_manifest.json
```

over:

```text
<run_dir>/02b-source-voice-prompts/voice_prompt_manifest.json
```

Both manifests intentionally expose the same `speaker_voices[Speaker N].vibevoice_name` shape. For English or other non-Chinese source videos, if 02c is missing or not `pass`, stop and fix 02c. Direct 02b usage is allowed only for already-Chinese source audio.
