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
- Prefer a speaker-labeled timeline with contiguous `Speaker 0..Speaker N-1` and start/end times.
- Before extraction, the parent workflow must have already produced `<run_dir>/02a-speaker-census/speaker_roster.json` with `status=frozen`, `1 <= speaker_count == voice_count <= 4`, and contiguous speaker ids by checking the first 6 minutes of the source video/audio.
- This 02b node consumes the frozen 02a roster. It must not re-infer speaker count or create a new voice roster from local extraction candidates.
- If no timeline exists, use source transcript speaker markers such as `>>` as a fallback; treat that result as lower confidence.
- Extract only clean single-speaker audio: no overlapping speech, no music, no intro/outro bed, no sponsor/ad read, no rolling-caption repetition, no applause, no long silence.
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
<run_dir>/02a-speaker-census/speaker_roster.json
<run_dir>/02b-source-voice-prompts/
├── speaker_roster.json
├── source_speaker_timeline.normalized.json
├── voice_prompt_manifest.json
├── voice_prompt_report.md
├── speaker0/
│   ├── en-<VoiceName>_source.wav
│   └── clips/*.wav
├── speaker1/
    ├── en-<VoiceName>_source.wav
    └── clips/*.wav
└── speaker<N-1>/
    ├── en-<VoiceName>_source.wav
    └── clips/*.wav
```

By default the script also copies every frozen speaker's final reference WAV to VibeVoice's voice directory. Use `--no-register-voices` only when intentionally auditing without changing available VibeVoice voices.

## Timeline Sources

The script discovers timeline evidence in this order:

1. `<run_dir>/02a-speaker-census/speaker_roster.json` for the fixed speaker/voice roster. This is mandatory for formal production.
2. `--timeline-json <path>` if provided, only for locating clean candidate clips after the roster is frozen.
3. `<run_dir>/02b-source-voice-prompts/source_speaker_timeline.json`.
4. `<run_dir>/02-source-capture/source_speaker_timeline.json`.
5. `<run_dir>/03-source-translation/source_transcript.zh.json`, useful when validating on an already translated run.
6. `<run_dir>/02-source-capture/source_transcript.en.json` parsed from unlabeled caption segments with `>>` speaker-change markers. This is a lower-confidence fallback for YouTube auto captions that do not expose speaker labels; if it cannot prove the frozen 02a roster, provide an explicit timeline instead.
7. `<run_dir>/02-source-capture/source_transcript.en.txt` parsed with timestamped `>>` speaker-change markers.

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

- `02a-speaker-census/speaker_roster.json.status == "frozen"`, `1 <= speaker_count == voice_count <= 4`, and speaker ids are contiguous `Speaker 0..Speaker N-1`;
- `02b-source-voice-prompts/voice_prompt_manifest.json.speaker_census_roster_path` points to the current 02a roster;
- each reference duration is at least 25 seconds, ideally 30-60 seconds;
- `sample_rate=24000`, `channels=1`, `codec_name=pcm_s16le`;
- no large silent block, music, sponsor language, URL/contact read, or rolling-caption repeated phrases;
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

The VibeVoice chunk node must use the 02c manifest for English or other non-Chinese source videos. Only when the source audio is already Chinese should it read this 02b manifest directly and map every frozen speaker:

```text
Speaker 0 -> speaker_voices["Speaker 0"].vibevoice_name
Speaker 1 -> speaker_voices["Speaker 1"].vibevoice_name
...
Speaker N-1 -> speaker_voices["Speaker N-1"].vibevoice_name
```

If both 02c and 02b manifests are absent, formal production must stop. Default `Xinran` / `BowenClean` preset voices are allowed only for explicit debugging or smoke validation, and the run report must make that fallback explicit.

Downstream chunks must preserve this frozen roster for every episode and chunk. A chunk that contains only one speaker still belongs to the same 1-4 speaker roster; it must not trigger a new voice choice, voice name, speaker numbering scheme, or default preset fallback.
