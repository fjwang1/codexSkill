---
name: worldview-china-source-voice-prompts
description: Extract clean per-speaker voice reference WAVs from a downloaded Worldview China YouTube podcast source audio. For English or other non-Chinese sources, these references are mandatory inputs to the Qwen3 Chinese VibeVoice prompt bridge, not final direct VibeVoice prompts. Use after youtube-media-preparation has produced source.wav.
---

# Worldview China Source Voice Prompts

Use this skill after `02 Source Capture` has produced a complete local source audio:

```text
<run_dir>/02-source-capture/youtube-media/source.wav
```

The goal is not model training. The goal is to cut clean single-speaker reference WAVs from the original podcast audio and register them in:

```text
/Users/wangfangjia/code/VibeVoice/demo/voices/
```

For English or other non-Chinese source videos, Qwen3 uses these WAVs plus matching reference text to generate Chinese VibeVoice prompts. VibeVoice should not use English source WAVs directly for formal full-audio generation. If the source audio is already Chinese, VibeVoice may use these WAVs directly.

## Requirements

- `source.wav` must exist and ffprobe successfully.
- Prefer a speaker-labeled timeline with `Speaker 0` / `Speaker 1` and start/end times.
- If no timeline exists, use source transcript speaker markers such as `>>` as a fallback; treat that result as lower confidence.
- Extract only clean single-speaker audio: no overlapping speech, no music, no intro/outro bed, no applause, no long silence.
- Target `30-60` seconds per speaker; accept at least `25` seconds only for smoke or constrained sources.
- Keep each selected clip around `8-18` seconds, then concatenate multiple clips into one reference per speaker.
- Convert references to WAV, mono, 24 kHz, PCM s16le.

## Standard Command

Run the bundled script from the podcast run directory:

```bash
/Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-source-voice-prompts/scripts/extract_source_voice_prompts.py \
  --run-dir /Volumes/GT34/Generated/world_and_china_podcast/YYYYMMDD_N \
  --force
```

Outputs:

```text
<run_dir>/02b-source-voice-prompts/
├── source_speaker_timeline.normalized.json
├── voice_prompt_manifest.json
├── voice_prompt_report.md
├── speaker0/
│   ├── en-<VoiceName>_source.wav
│   └── clips/*.wav
└── speaker1/
    ├── en-<VoiceName>_source.wav
    └── clips/*.wav
```

By default the script also copies the two final reference WAVs to VibeVoice's voice directory. Use `--no-register-voices` only when intentionally auditing without changing available VibeVoice voices.

## Timeline Sources

The script discovers timeline evidence in this order:

1. `--timeline-json <path>` if provided.
2. `<run_dir>/02b-source-voice-prompts/source_speaker_timeline.json`.
3. `<run_dir>/02-source-capture/source_speaker_timeline.json`.
4. `<run_dir>/03-source-translation/source_transcript.zh.json`, useful when validating on an already translated run.
5. `<run_dir>/02-source-capture/source_transcript.en.txt` parsed with `>>` speaker-change markers.

Formal production should prefer a timeline created immediately after source capture, before translation. Using `03-source-translation/source_transcript.zh.json` is acceptable for backfilling and validation on existing runs, but do not make the production node depend on translation.

## Validation

After extraction:

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels \
  -of default=noprint_wrappers=1 <reference.wav>

ffmpeg -hide_banner -i <reference.wav> -af volumedetect -f null - 2>&1 | tail -n 12
ffmpeg -hide_banner -i <reference.wav> -af silencedetect=noise=-45dB:d=1 -f null - 2>&1 | rg 'silence_(start|end)' || true
```

Require:

- each reference duration is at least 25 seconds, ideally 30-60 seconds;
- `sample_rate=24000`, `channels=1`, `codec_name=pcm_s16le`;
- no large silent block;
- voice names in `voice_prompt_manifest.json` are present in `/Users/wangfangjia/code/VibeVoice/demo/voices/`.

For publishable runs, generate a short VibeVoice audition before committing to the full chunked audio run.

## Integration

When this node passes, the default downstream path is:

```text
02b English source reference -> 02c Qwen Chinese VibeVoice prompts -> 05 VibeVoice chunks
```

The Qwen bridge skill reads:

```text
<run_dir>/02b-source-voice-prompts/voice_prompt_manifest.json
```

and creates:

```text
<run_dir>/02c-qwen-vibevoice-prompts/voice_prompt_manifest.json
```

The VibeVoice chunk node must use the 02c manifest for English or other non-Chinese source videos. Only when the source audio is already Chinese should it read this 02b manifest directly and map:

```text
Speaker 0 -> speaker_voices["Speaker 0"].vibevoice_name
Speaker 1 -> speaker_voices["Speaker 1"].vibevoice_name
```

If both 02c and 02b manifests are absent, formal production must stop. Default `Xinran` / `BowenClean` preset voices are allowed only for explicit debugging or smoke validation, and the run report must make that fallback explicit.
