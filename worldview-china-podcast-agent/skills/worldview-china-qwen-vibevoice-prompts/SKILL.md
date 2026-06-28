---
name: worldview-china-qwen-vibevoice-prompts
description: "Mandatory bridge for English or other non-Chinese Worldview China podcast sources: build Chinese VibeVoice voice prompts from extracted original speaker clips by using Qwen3-TTS only as a short Chinese voice-prompt bridge. Use after worldview-china-source-voice-prompts has produced 02b-source-voice-prompts/voice_prompt_manifest.json and before any full VibeVoice audio generation for non-Chinese source videos."
---

# Worldview China Qwen VibeVoice Prompts

Use this skill after `02b Source Voice Prompts` and before `05 VibeVoice Chunks`.

For English or other non-Chinese source videos, this node is mandatory. The goal is not to generate the full podcast audio with Qwen3. The goal is to create one short Chinese prompt WAV per frozen source speaker, up to 4 speakers, so VibeVoice receives Chinese voice prompts instead of English source clips.

## Inputs

Required:

```text
<run_dir>/02b-source-voice-prompts/voice_prompt_manifest.json
<run_dir>/02b-source-voice-prompts/speaker_roster.json
<run_dir>/02a-speaker-census/speaker_roster.json
<run_dir>/02-source-capture/source_transcript.en.json
```

`02b-source-voice-prompts/speaker_roster.json` must be derived from the frozen 02a census roster, not re-created during Qwen prompt generation. `source_transcript.en.json` is used to recover the English `reference_text` matching the selected source clip. If it is absent, the script falls back to `selected_clips[].text_preview`; if no usable text exists, block downstream generation and fix source capture or the 02b manifest. Do not skip this node for English source videos.

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
├── ...
├── qwen_speaker<N-1>/qwen_prompt_000.wav
├── reference/speaker0/reference.wav
├── ...
├── reference/speaker<N-1>/reference.wav
├── registered/zh-<VoiceName>_qwenzh.wav
├── voice_prompt_manifest.json
├── voice_distinctness_policy_result.json
├── voice_distinctness_policy_report.md
└── voice_prompt_report.md
```

By default, the final normalized prompt WAVs are also copied into:

```text
/Users/wangfangjia/code/VibeVoice/demo/voices/
```

Use `--no-register-voices` only for audits; downstream VibeVoice generation normally requires registration.

After successful prompt generation, formal runs must apply the Worldview China two-speaker voice distinctness policy before any VibeVoice preflight or full generation:

```bash
uv run --with numpy python /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/apply_voice_distinctness_policy.py \
  --run-dir <run_dir> \
  --threshold 0.90
```

This policy is intentionally scoped to exactly two-speaker podcasts. If the two generated Chinese prompts are too similar at the configured 90% threshold, the whole effective two-speaker roster is replaced with the shared `20260618_3` default pair stored under:

```text
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/assets/default-voices/20260618_3/
```

The policy must replace both speakers together and preserve the original cloned prompts under `original_cloned_speaker_voices`; downstream VibeVoice reads only the effective `speaker_voices`. Three- and four-speaker podcasts skip this automatic fallback principle.

## Method

For each frozen `Speaker 0..Speaker N-1`:

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
WC<Run>Speaker<N-1>QwenZH
```

This keeps Qwen3 responsible for cross-lingual Chinese prompt creation, while VibeVoice remains responsible for the full continuous dialogue audio.

## Validation

After generation, require:

- `voice_prompt_manifest.json.status == "pass"`.
- Every frozen speaker has `speaker_voices["Speaker <index>"].vibevoice_name`.
- Every registered WAV exists in `/Users/wangfangjia/code/VibeVoice/demo/voices/`.
- WAV format is `pcm_s16le`, `24000 Hz`, `mono`.
- Duration is normally `5-30s`.
- No long silence; `silence_ratio` should be low.
- `reference_text` must correspond to the frozen source speaker and must not be sponsor/music/rolling-caption noise.
- For exactly two speakers, `voice_prompt_manifest.json.voice_distinctness_policy.status` must be `PASS_ORIGINAL_CLONED_PAIR` or `DEFAULT_FALLBACK_APPLIED`, and `threshold` must be `0.90`. If fallback is applied, `effective_speaker_voices_source` must be `default_pair_20260618_3`.

Useful checks:

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels \
  -of default=noprint_wrappers=1 <registered.wav>

ffmpeg -hide_banner -i <registered.wav> -af volumedetect -f null - 2>&1 | tail -n 12
ffmpeg -hide_banner -i <registered.wav> -af silencedetect=noise=-45dB:d=1 -f null - 2>&1 | rg 'silence_(start|end)' || true
```

Before any long/full 05 VibeVoice run, generate a 1-2 chunk VibeVoice preflight audition and require it to pass the raw-level gate. Do not wait until all chunks are generated before discovering that a voice prompt causes low-level VibeVoice output.

Standard preflight command for Worldview China podcast runs:

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/scripts/run_vibevoice_preflight_audition.py \
  --run-dir <run_dir> \
  --chunk-count 2 \
  --voice-prompt-policy qwen_chinese_required \
  --voice-context-policy locked_multi_speaker_roster \
  --min-source-max-volume -12.0 \
  --yellow-source-max-volume -15.0 \
  --min-source-mean-volume -30.0 \
  --device mps \
  --no-progress-bar \
  --force
```

Series episode mode must run this inside each `episode_XXX` run directory before that episode's full 05 generation. Passing conditions:

```text
05-vibevoice-preflight-audition/preflight_audition_result.json exists
status == PASS for unattended full generation
or status == YELLOW only after secondary QA explicitly passes
all PASS rows have rows[].max_volume_dbfs >= -12.0 and rows[].mean_volume_dbfs >= -30.0
YELLOW rows have -15.0 <= rows[].max_volume_dbfs < -12.0 and rows[].mean_volume_dbfs >= -30.0
no row has rows[].max_volume_dbfs < -15.0 or rows[].mean_volume_dbfs < -30.0
voice_prompt_manifest_sha256 matches the current 02c voice_prompt_manifest.json
script_sha256 matches the current podcast_script.md
```

If preflight fails, block full generation and repair 02b/02c before retrying. Do not end the parent workflow:

- Re-check whether the selected 02b clip's `reference_text` overlaps sponsor, subscribe, Spotify, URL, membership, or rolling-caption text; choose another clean clip for the same frozen speaker if needed.
- Rewrite `target_text` to a short, topic-matched Chinese prompt instead of a generic template.
- Regenerate 02c and rerun preflight.
- If the cause is still unclear, run a 2x2 text/voice crosscheck with a known-good script and voice set. If known-good script + current voice fails while current script + known-good voice passes, the current 02c voice prompt is the cause; do not rewrite the podcast script.

## Downstream Integration

The downstream VibeVoice chunk node must use:

```text
<run_dir>/02c-qwen-vibevoice-prompts/voice_prompt_manifest.json
```

over:

```text
<run_dir>/02b-source-voice-prompts/voice_prompt_manifest.json
```

Both manifests intentionally expose the same `speaker_voices[Speaker N].vibevoice_name` shape. For English or other non-Chinese source videos, if 02c is missing or not `pass`, block 05 and fix 02c; do not fall back to direct 02b usage. Direct 02b usage is allowed only for already-Chinese source audio.
