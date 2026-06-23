---
name: bilibili-video-english-transcript
description: Download a Bilibili video, save the complete local video, extract audio, and generate an English transcript with local Whisper/MLX. Use when the user provides a Bilibili URL or BV id and asks for subtitles, ASR, transcript, English稿, 英文稿, 逐字稿, or wants a reusable B站 video-to-text workflow.
---

# Bilibili Video English Transcript

Use this skill to turn a Bilibili video into a local English transcript. The workflow saves the complete video first, extracts a 16 kHz mono WAV, runs local `mlx_whisper`, and writes TXT, SRT, JSON, and a short report.

## Quick Command

Run the bundled wrapper from any directory:

```bash
/Users/wangfangjia/.codex/skills/bilibili-video-english-transcript/scripts/run_bilibili_transcript.sh "https://www.bilibili.com/video/BV..."
```

Default output root:

```text
/Users/wangfangjia/code/bilibili-mcp/outputs/bilibili_english_transcripts/
```

Each run creates:

```text
<run-dir>/
  metadata.json
  media/<BV>.full.mp4
  audio/<BV>.16k.wav
  transcripts/<BV>.english.txt
  transcripts/<BV>.english.srt
  transcripts/<BV>.whisper.json
  report.md
```

## Workflow

1. Use the wrapper script, not ad hoc commands, unless you need to debug.
2. For a quick smoke test, pass `--clip-start` and `--clip-duration`.
3. For final transcripts, omit clip arguments and use the full audio.
4. Report the output paths to the user, especially `report.md` and `transcripts/*.english.txt`.
5. Mention that ASR is not the same as official Bilibili subtitles. If the video has hard subtitles, ASR may differ from the on-screen text.

## Model Choice

The installed working runtime is:

```text
/Users/wangfangjia/code/bilibili-mcp/.venv-asr/bin/python
```

The wrapper auto-detects that runtime. Override it with:

```bash
MLX_WHISPER_PYTHON=/path/to/python run_bilibili_transcript.sh ...
```

The script default is `mlx-community/whisper-tiny` because it is installed and fast. For higher-quality final English transcripts, use:

```bash
--model mlx-community/whisper-large-v3-turbo
```

If the large model is not fully cached, the first run may download model weights from Hugging Face and take a while.

## Useful Examples

Quick 30-second test:

```bash
/Users/wangfangjia/.codex/skills/bilibili-video-english-transcript/scripts/run_bilibili_transcript.sh \
  "https://www.bilibili.com/video/BV1nz7U6QEVi/" \
  --clip-start 00:01:20 \
  --clip-duration 30
```

Full transcript with a fixed output directory:

```bash
/Users/wangfangjia/.codex/skills/bilibili-video-english-transcript/scripts/run_bilibili_transcript.sh \
  "BV1nz7U6QEVi" \
  --run-dir "/Users/wangfangjia/code/bilibili-mcp/outputs/BV1nz7U6QEVi-asr/final-whisper"
```

Reuse an already-downloaded full video:

```bash
/Users/wangfangjia/.codex/skills/bilibili-video-english-transcript/scripts/run_bilibili_transcript.sh \
  "BV1nz7U6QEVi" \
  --source-video "/Users/wangfangjia/code/bilibili-mcp/outputs/BV1nz7U6QEVi-asr/media/BV1nz7U6QEVi.full.mp4" \
  --run-dir "/Users/wangfangjia/code/bilibili-mcp/outputs/BV1nz7U6QEVi-asr/final-whisper"
```

Higher-quality full transcript:

```bash
/Users/wangfangjia/.codex/skills/bilibili-video-english-transcript/scripts/run_bilibili_transcript.sh \
  "BV1nz7U6QEVi" \
  --model mlx-community/whisper-large-v3-turbo
```

## Operational Notes

- `yt-dlp` and `ffmpeg` must be available on PATH.
- The script defaults to `--cookies-from-browser chrome` so it can access videos that need the user's Bilibili login state.
- If Chrome cookie extraction fails, pass `--cookies-file /path/to/cookies.txt`.
- Keep the generated MP4 and WAV with the transcript so later QA can compare text against source audio.
- For videos with mixed Chinese and English speech, keep `--language en` only if the requested output is English transcript of English speech. Otherwise run with the appropriate language or do a second pass.
