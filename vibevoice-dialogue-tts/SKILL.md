---
name: vibevoice-dialogue-tts
description: Use the local community VibeVoice CLI to generate long-form single-speaker or up-to-four-speaker TTS audio with VibeVoice-1.5B only. Trigger when the user asks to run VibeVoice, VibeVoice TTS, VibeVoice-1.5B, local dialogue/single-host TTS, or explicitly says not to use Qwen/fallback TTS.
metadata:
  short-description: Local VibeVoice long-form TTS
---

# VibeVoice Long-Form TTS

Use this skill to generate single-speaker or dialogue audio with the local community VibeVoice install. Dialogue mode supports a locked roster of up to four speakers, matching VibeVoice-1.5B's documented limit. This skill is deliberately separate from Qwen-based TTS workflows.

## Local Defaults

- Repo: `/Users/wangfangjia/code/VibeVoice`
- Python: `/Users/wangfangjia/code/VibeVoice/.venv/bin/python`
- Model: `/Volumes/GT34/AI/code-models/VibeVoice-1.5B-modelscope-clean`
- Default/recommended device path: `mps`
- Default MPS dtype/attention: `float16`, `sdpa`
- MPS environment: set `PYTORCH_ENABLE_MPS_FALLBACK=1` and `TOKENIZERS_PARALLELISM=false`
- Stable fallback device path: `cpu`
- CPU fallback dtype/attention: `float32`, `eager`
- Voices:
  - `Speaker 0` -> `Xinran` -> `demo/voices/zh-Xinran_woman.wav`
  - `Speaker 1` -> `BowenClean` -> `demo/voices/zh-BowenClean_man.wav`

`BowenClean` is copied from the auditioned prompt `06_VV_zh-Bowen_man.wav` and is not the same file as the older repo-local `zh-Bowen_man.wav`.

The wrapper defaults only cover the common two-speaker path. For three- or four-speaker dialogue, explicitly pass one `--speaker-names` value for every locked global speaker slot. Use `Speaker 0..Speaker 3` internally when possible; the wrapper also handles VibeVoice's older `Speaker 1..Speaker 4` examples by resolving the speaker index base.

Do not use Qwen, Qwen3-TTS, or any fallback TTS unless the user explicitly asks to switch away from VibeVoice.

## Input Format

Default dialogue mode expects speaker-tagged text with one to four speaker IDs:

```text
Speaker 0: First host line.
Speaker 1: Second host line.
Speaker 0: Follow-up line.
```

Four-speaker dialogue is valid when the caller passes four locked voices:

```text
Speaker 0: First participant line.
Speaker 1: Second participant line.
Speaker 2: Third participant line.
Speaker 3: Fourth participant line.
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

If the user provides a DOCX or Markdown script, first extract only the requested portion and write a clean `.txt` file in the format above. Keep turns reasonably short. For Chinese production audio on this Mac, split any single `Speaker N:` turn longer than about `220` Chinese characters at natural sentence or clause boundaries before calling VibeVoice. Do not send `400+` character monologues as one speaker turn; they can make CPU generation run for a long time without writing any WAV or report until completion. For long-form production, keep chunks around `350-650` Chinese spoken characters, hard max about `800`, unless the user explicitly wants a stress test.

## Recommended Command

Prefer the bundled wrapper:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/dialogue.txt \
  --output-dir /absolute/path/vibevoice_outputs
```

Default mode is `--speaker-mode dialogue`, preserving the original two-speaker behavior when two speaker names are passed:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/dialogue.txt \
  --output-dir /absolute/path/vibevoice_outputs \
  --speaker-mode dialogue \
  --speaker-names Xinran BowenClean
```

For three or four speakers, pass the full locked roster in numeric speaker order:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/dialogue_4p.txt \
  --output-dir /absolute/path/vibevoice_outputs \
  --speaker-mode dialogue \
  --speaker-names VoiceForSpeaker0 VoiceForSpeaker1 VoiceForSpeaker2 VoiceForSpeaker3 \
  --speaker-index-base 0
```

If a chunk contains only one participant from a larger dialogue, still pass the full roster and `--speaker-index-base 0`; the wrapper will keep that speaker mapped to the same global voice slot.

For single-host long-form audio, use exactly one speaker:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/single_host.txt \
  --output-dir /absolute/path/vibevoice_outputs \
  --speaker-mode single \
  --speaker-names Xinran
```

The wrapper checks the local paths and runs the recommended MPS path by default:

- `demo/inference_from_file.py`
- `--speaker_names Xinran BowenClean` in dialogue mode, or `--speaker_names Xinran` in single mode
- `--device mps`
- `--attn_implementation sdpa`
- `--torch_dtype float16`
- `--cfg_scale 1.3`
- `--do_sample --temperature 0.9 --top_p 0.9`
- `--max_length_times 1.6`
- default `--ddpm_steps 10`

The wrapper's `--torch-dtype auto` and `--attn-implementation auto` resolve by device:

- `cpu` -> `float32`, `eager`
- `mps` -> `float16`, `sdpa`
- `cuda` -> `bfloat16`, `flash_attention_2`

To force the CPU fallback path:

```bash
/Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_dialogue.py \
  --txt-path /absolute/path/dialogue.txt \
  --output-dir /absolute/path/vibevoice_outputs \
  --speaker-mode dialogue \
  --speaker-names Xinran BowenClean \
  --device cpu
```

CPU fallback resolves to `float32` + `eager`. Use it when MPS is unavailable or produces invalid audio, but do not prefer it for routine production on this Mac.

Do not lower `ddpm_steps` or heavily reduce `max_length_times` for anything that will be judged as publishable audio. Low-step / low-length experiments are acceptable only for smoke tests, and should be labeled as such.

Use `--check-model` on first use or after any model download changes. It verifies the three known VibeVoice-1.5B safetensors SHA256 hashes.

## Resident Batch Runner

For multi-chunk production, prefer the resident batch runner so VibeVoice loads the processor/model once and then generates every job in the JSON list in the same Python process:

```bash
/Users/wangfangjia/code/VibeVoice/.venv/bin/python \
  /Users/wangfangjia/.codex/skills/vibevoice-dialogue-tts/scripts/run_vibevoice_resident_batch.py \
  --jobs-json /absolute/path/vibevoice_jobs.json \
  --report-json /absolute/path/vibevoice_batch_report.json \
  --no-progress-bar
```

The resident runner defaults to `--device mps` and auto-selects `float16` + `sdpa`. To force the CPU fallback, add `--device cpu`; that auto-selects `float32` + `eager`.

`vibevoice_jobs.json` must contain:

```json
{
  "jobs": [
    {
      "job_id": "chunk_001",
      "txt_path": "/absolute/path/chunk_001/audio/vibevoice_dialogue.txt",
      "output_dir": "/absolute/path/chunk_001/audio/vibevoice_raw",
      "speaker_mode": "dialogue",
      "speaker_names": ["VoiceForSpeaker0", "VoiceForSpeaker1", "VoiceForSpeaker2"],
      "speaker_index_base": "0",
      "force": false
    }
  ]
}
```

`speaker_names` may contain one name in `single` mode or two to four names in `dialogue` mode. For formal chunked workflows with a global `Speaker 0..N-1` roster, set `speaker_index_base` to `"0"` even when the current chunk contains only one speaker.

The resident runner must not pass voice prompt WAVs in raw first-appearance order while leaving the original global `Speaker N` labels in the text. VibeVoice's processor labels prompt samples as local `Speaker 0`, `Speaker 1`, ... by list position. For chunks that start with `Speaker 1` or contain only `Speaker 2`, the runner remaps the chunk to local contiguous speaker IDs and records `global_to_local_speaker_map`, `voice_sample_speaker_numbers`, and `actual_speakers` in the report. This preserves the global voice roster without reversing voices on out-of-order chunks.

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
7. Do not switch to Qwen/Qwen3-TTS, lower `ddpm_steps`, or heavily reduce `max_length_times` unless the user explicitly approves a different quality/backend policy. MPS is the default backend; CPU is an explicit fallback, not the first retry choice on this Mac.

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

Report the final WAV path, duration, sample rate, channels, and any warning. Mention that MPS is the recommended fast path and CPU is a slower fallback if runtime matters.

## Known Behavior

- Clean model hashes were verified for `/Volumes/GT34/AI/code-models/VibeVoice-1.5B-modelscope-clean`.
- Earlier MPS attempts failed: `mps` with `float16` produced NaN probabilities, and `mps` with `float32` stalled in testing. On 2026-06-24, with torch 2.12.0 on this Mac, `mps` + `float16` + `sdpa` completed sampled VibeVoice smoke tests and real article chunks without NaN.
- `mps` + `float32` + `sdpa` can load and enter generation, but it is impractically slow here: a 3-turn smoke ran about 60-80 seconds per token and was stopped.
- `mps` + `float16` + `sdpa` smoke results on 2026-06-24:
  - tiny 1-turn, `ddpm_steps=10`: 4.27s WAV, 13.28s generation, RTF 3.11x, mean/max volume -26.5/-7.6 dB.
  - 3-turn dialogue, `ddpm_steps=10`: 28.80s WAV, 81.51s generation, RTF 2.83x, mean/max volume -24.9/-5.5 dB, no >2s silence.
- `mps` + `float16` + `sdpa` real article result on 2026-06-24:
  - Prabowo resource nationalism single-speaker Chinese translation, `Xinran`, `ddpm_steps=10`, `max_length_times=1.6`, chunks of 634 and 650 spoken Chinese characters.
  - `chunk_01`: 141.20s WAV, mean/max volume -25.0/-7.4 dB, no >2s silence.
  - `chunk_02`: 130.93s WAV, mean/max volume -25.4/-7.5 dB, no >2s silence.
  - Combined first two chunks: 272.13s WAV, mean/max volume -25.2/-7.4 dB, no >2s silence.
  - Observed wall time was materially better than CPU on the same first chunk; use MPS as default/recommended backend.
- CPU `float32` generated a 212.8 second two-speaker WAV from the first two chapters successfully.
- CPU `float32`/`eager` fallback can still work, but it is not the preferred path on this Mac. On 2026-06-24, the same 634-character Prabowo `chunk_01` ran for more than 21 minutes without writing a WAV before being stopped by the user; MPS had already produced a usable 141.20s WAV for that chunk.
- That successful reference used a substantive script: 21 turns, about 1169 Chinese characters, and 212.8 seconds of output. Ultra-short 6-turn scripts have produced low-level, raspy, dragged, or mispronounced audio on the same model. Prefer realistic context length when judging VibeVoice quality.
- 2026-06-22 Worldview podcast run showed a different failure mode: a 916-character chunk with a single 458-character speaker turn ran CPU `model.generate(...)` for over 20 minutes without writing a WAV/report. The fix is not to abandon VibeVoice; split long same-speaker turns first and keep production chunks around `350-600` Chinese characters, hard max `800`, max single turn about `220`.
- If the raw VibeVoice wav is suspiciously quiet, for example `mean_volume < -30 dB` or `max_volume < -10 dB`, rerun generation or repair the voice prompt instead of rescuing it with loudness normalization; normalization will amplify generation artifacts. Values between `-10` and `-8 dBFS` may pass production if the workflow explicitly uses the relaxed gate, but they should be reported and spot-checked because they are weaker than the historical good range.
- VibeVoice logs may mention Qwen tokenizer internals because VibeVoice uses a Qwen2 text-tokenizer component. That is not Qwen3-TTS fallback.
