---
name: vibevoice-dialogue-tts
description: Use the local community VibeVoice CLI to generate long-form single-speaker or two-speaker TTS audio with VibeVoice-1.5B only. Trigger when the user asks to run VibeVoice, VibeVoice TTS, VibeVoice-1.5B, local dialogue/single-host TTS, or explicitly says not to use Qwen/fallback TTS.
metadata:
  short-description: Local VibeVoice long-form TTS
---

# VibeVoice Long-Form TTS

Use this skill to generate single-speaker or dialogue audio with the local community VibeVoice install. This skill is deliberately separate from Qwen-based TTS workflows.

## Local Defaults

- Repo: `/Users/wangfangjia/code/VibeVoice`
- Python: `/Users/wangfangjia/code/VibeVoice/.venv/bin/python`
- Model: `/Volumes/GT34/AI/code-models/VibeVoice-1.5B-modelscope-clean`
- Stable device path: `cpu`
- Stable dtype/attention: `float32`, `eager`
- Voices:
  - `Speaker 0` -> `Xinran` -> `demo/voices/zh-Xinran_woman.wav`
  - `Speaker 1` -> `BowenClean` -> `demo/voices/zh-BowenClean_man.wav`

`BowenClean` is copied from the auditioned prompt `06_VV_zh-Bowen_man.wav` and is not the same file as the older repo-local `zh-Bowen_man.wav`.

Do not use Qwen, Qwen3-TTS, or any fallback TTS unless the user explicitly asks to switch away from VibeVoice.

## Input Format

Default dialogue mode expects speaker-tagged text:

```text
Speaker 0: First host line.
Speaker 1: Second host line.
Speaker 0: Follow-up line.
```

Single-speaker mode accepts either one explicit speaker:

```text
Speaker 0: Single host line.
Speaker 0: Next single host line.
```

or VibeVoice's official plain-text single-speaker style:

```text
Single host line.
Next single host line.
```

When plain text is used, the wrapper writes a temporary `Speaker 1:` tagged copy before calling `demo/inference_from_file.py`, because VibeVoice's processor treats plain text as `Speaker 1` but the file inference demo requires explicit speaker tags.

If the user provides a DOCX or Markdown script, first extract only the requested portion and write a clean `.txt` file in the format above. Keep turns reasonably short. For Chinese production audio on this Mac, split any single `Speaker N:` turn longer than about `220` Chinese characters at natural sentence or clause boundaries before calling VibeVoice. Do not send `400+` character monologues as one speaker turn; they can make CPU generation run for a long time without writing any WAV or report until completion.

## Recommended Command

Prefer the bundled wrapper:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/dialogue.txt \
  --output-dir /absolute/path/vibevoice_outputs
```

Default mode is `--speaker-mode dialogue`, preserving the original two-speaker behavior:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/dialogue.txt \
  --output-dir /absolute/path/vibevoice_outputs \
  --speaker-mode dialogue \
  --speaker-names Xinran BowenClean
```

For single-host long-form audio, use exactly one speaker:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/single_host.txt \
  --output-dir /absolute/path/vibevoice_outputs \
  --speaker-mode single \
  --speaker-names Xinran
```

The wrapper checks the local paths and runs:

- `demo/inference_from_file.py`
- `--speaker_names Xinran BowenClean` in dialogue mode, or `--speaker_names Xinran` in single mode
- `--device cpu`
- `--attn_implementation eager`
- `--torch_dtype float32`
- `--cfg_scale 1.3`
- `--do_sample --temperature 0.9 --top_p 0.9`
- `--max_length_times 1.6`
- default `--ddpm_steps 10`

Do not lower `ddpm_steps` or heavily reduce `max_length_times` for anything that will be judged as publishable audio. Low-step / low-length experiments are acceptable only for smoke tests, and should be labeled as such.

Use `--check-model` on first use or after any model download changes. It verifies the three known VibeVoice-1.5B safetensors SHA256 hashes.

## Resident Batch Runner

For multi-chunk production, prefer the resident batch runner so VibeVoice loads the processor/model once and then generates every job in the JSON list in the same Python process:

```bash
/Users/wangfangjia/code/VibeVoice/.venv/bin/python \
  /Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_resident_batch.py \
  --jobs-json /absolute/path/vibevoice_jobs.json \
  --report-json /absolute/path/vibevoice_batch_report.json \
  --device cpu \
  --torch-dtype float32 \
  --attn-implementation eager \
  --no-progress-bar
```

`vibevoice_jobs.json` must contain:

```json
{
  "jobs": [
    {
      "job_id": "chunk_001",
      "txt_path": "/absolute/path/chunk_001/audio/vibevoice_dialogue.txt",
      "output_dir": "/absolute/path/chunk_001/audio/vibevoice_raw",
      "speaker_mode": "dialogue",
      "speaker_names": ["VoiceForSpeaker0", "VoiceForSpeaker1"],
      "speaker_index_base": "auto",
      "force": false
    }
  ]
}
```

Use `run_vibevoice_dialogue.py` only for one-off debugging or parity checks. For a formal chunked podcast/video workflow, do not spawn one VibeVoice process per chunk unless the resident runner fails and the failure is recorded. The resident report records `model_load_sec`, per-job `generation_sec`, output duration, RTF, tokens, device, dtype, and attention implementation; use that report for CPU/MPS timing comparisons.

## Resource Contention And Retry Policy

Before declaring a VibeVoice run hung or failed, check whether this machine is already busy with other heavy media/model work. Look for active `VibeVoice`, `inference_from_file.py`, `run_vibevoice_*`, `ffmpeg`, `whisper`, or similar CPU/GPU-heavy processes and inspect whether the current run is still writing output files.

If another heavy job is running:

1. Do not immediately mark the VibeVoice gate as failed.
2. Record the competing process names/PIDs in the run report.
3. Wait for the competing job to finish or for clear resource relief before retrying the VibeVoice generation.
4. Poll every 5-10 minutes; for unattended automation, wait up to 90 minutes before returning `BLOCKED_AUDIO_WAITING_FOR_RESOURCES`.
5. After the competing job finishes, resume from the same VibeVoice stage; do not rerun earlier selection, script, cover, or PPT stages.

If there is no meaningful resource contention and a production VibeVoice process makes no observable progress, use bounded retries:

1. Inspect the input script before treating the run as hung: record total characters, max single-turn characters, segment count, speaker order, selected voices, and whether `show_progress_bar` was disabled.
2. If any single turn is longer than about `220` Chinese characters, stop the current run, split the long turn into same-speaker consecutive turns, rebuild the chunk/jobs plan, and retry from that node. This is an input-shaping fix, not a TTS backend change.
3. Let the initial process run long enough to estimate throughput from progress, output-file timestamps, or logs. Be aware that `model.generate(...)` writes the WAV/report only after the whole job finishes; no output file during CPU generation is not by itself proof of a hard hang.
4. If the estimated completion time is impractical for the current automation window, stop that process and retry once with the resident batch runner after fixing input shape.
5. If resident batch fails to produce the first chunk WAV after a realistic wait for the current chunk length without a competing heavy job, retry the same first chunk once. Do not use a fixed 20-minute cutoff for `900+` character chunks or chunks with long turns; first split them smaller.
6. If the repeated first-chunk attempt also produces no WAV after long-turn splitting and a realistic wait, stop and report `AUDIO_GENERATION_VIBEVOICE_TIMEOUT`.
7. Do not switch to Qwen/Qwen3-TTS, MPS, lower `ddpm_steps`, or heavily reduce `max_length_times` unless the user explicitly approves a different quality/backend policy.

Always distinguish:

- `BLOCKED_AUDIO_WAITING_FOR_RESOURCES`: other heavy local jobs are likely starving VibeVoice; retry later from the same stage.
- `AUDIO_GENERATION_VIBEVOICE_TIMEOUT`: VibeVoice made no usable progress after bounded attempts without resource contention.
- `AUDIO_GENERATION_VIBEVOICE_BAD_OUTPUT`: WAV exists but fails ffprobe or quality checks.

## Verification

After generation, always run:

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels \
  -of default=noprint_wrappers=1 /absolute/path/output.wav
```

For a quick sanity check:

```bash
ffmpeg -hide_banner -i /absolute/path/output.wav -af volumedetect -f null - 2>&1 | tail -n 12
ffmpeg -hide_banner -i /absolute/path/output.wav -af silencedetect=noise=-45dB:d=2 -f null - 2>&1 | rg 'silence_(start|end)' || true
```

Report the final WAV path, duration, sample rate, channels, and any warning. Mention that CPU is slow but stable if runtime matters.

## Known Behavior

- Clean model hashes were verified for `/Volumes/GT34/AI/code-models/VibeVoice-1.5B-modelscope-clean`.
- On this Mac, `mps` with `float16` produced NaN probabilities, and `mps` with `float32` stalled in testing.
- CPU `float32` generated a 212.8 second two-speaker WAV from the first two chapters successfully.
- That successful reference used a substantive script: 21 turns, about 1169 Chinese characters, and 212.8 seconds of output. Ultra-short 6-turn scripts have produced low-level, raspy, dragged, or mispronounced audio on the same model. Prefer realistic context length when judging VibeVoice quality.
- 2026-06-22 Worldview podcast run showed a different failure mode: a 916-character chunk with a single 458-character speaker turn ran CPU `model.generate(...)` for over 20 minutes without writing a WAV/report. The fix is not to abandon VibeVoice; split long same-speaker turns first and keep production chunks around `350-600` Chinese characters, hard max `800`, max single turn about `220`.
- If the raw VibeVoice wav is suspiciously quiet, for example `mean_volume < -30 dB` or `max_volume < -8 dB`, rerun generation instead of rescuing it with loudness normalization; normalization will amplify generation artifacts.
- VibeVoice logs may mention Qwen tokenizer internals because VibeVoice uses a Qwen2 text-tokenizer component. That is not Qwen3-TTS fallback.
