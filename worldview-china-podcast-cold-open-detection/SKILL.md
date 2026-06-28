---
name: worldview-china-podcast-cold-open-detection
description: "Conservatively detect YouTube podcast cold opens, teaser montages, countdown intros, and pre-show highlight reels before translation or dubbing. Use when Codex is preparing a longform podcast/interview/forum source video and must decide whether an opening preview segment should be removed from the active source video/transcript without risking a partial or wrong cut."
---

# Worldview China Podcast Cold Open Detection

Detect and optionally remove only complete opening teaser/cold-open segments. This skill is intentionally conservative: if the end boundary is not high-confidence, do not cut.

Use this after source capture produces `source.mp4` and `source_transcript.en.json`, before speaker census, voice prompt extraction, translation, episode split, or video rendering.

## Safety Rule

Use transcript/subtitle evidence as the primary signal for finding the candidate boundary. The detector should first read the opening transcript for teaser structure, formal-start cues, duplicate opening snippets that reappear later, and fragment risks. Visual evidence is only a boundary confirmation layer, not the main way to discover the cut.

Do not promote a source-video cut on transcript-only evidence. A confirmed destructive cut requires:

- a start-at-zero opening segment;
- a clear transcript/subtitle boundary, normally a cue such as `before we start today's podcast`, `welcome`, or `let's start`;
- subtitle evidence that the new first text is a complete opening, not an orphaned answer fragment such as `number two`, `second is`, `and`, or `but`;
- corroboration that the opening is actually a teaser/cold open, preferably duplicate-match evidence between opening snippets and later full discussion;
- strong targeted visual evidence from OCR or direct review near the transcript candidate, such as `Conversation starts in`, `Podcast starts in`, countdown text, `Coming up`, title cards, or opening highlight captions;
- boundary validation showing the cut does not split a transcript segment or begin the new source with a fragment.

If evidence is incomplete, return `NEEDS_VISUAL_REVIEW` or `NO_CONFIDENT_CUT`. Do not cut. Never remove only part of a teaser because that creates a worse opening than leaving the teaser intact.

## Workflow

1. Run detection:

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-cold-open-detection/scripts/detect_cold_open.py \
  --run-dir <run_dir> \
  --extract-frames
```

2. If the result is `NEEDS_VISUAL_REVIEW`, inspect only the extracted opening and candidate-boundary frames or pass them to an independent review agent. These frames are a confirmation step for the transcript-derived candidate, not random sampling. Write a visual review JSON:

```json
{
  "reviewer": "agent_or_human",
  "cold_open_present": true,
  "confidence": "high",
  "cold_open_end_sec": 132.64,
  "observations": [
    {"time_sec": 79.04, "text": "Conversation starts in: 48", "type": "countdown"},
    {"time_sec": 116.16, "text": "Conversation starts in: 11 / FIRST REVOLUTION", "type": "countdown_title_card"},
    {"time_sec": 132.64, "text": "before we start today's podcast", "type": "post_teaser_intro"}
  ]
}
```

Then rerun detection:

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-cold-open-detection/scripts/detect_cold_open.py \
  --run-dir <run_dir> \
  --visual-review-json <run_dir>/02-source-cold-open-detection/visual_review.json \
  --extract-frames
```

3. Only if `cold_open_detection_result.json.status == "CUT_CONFIRMED"`, apply a cut. For a validation sample:

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-cold-open-detection/scripts/apply_cold_open_cut.py \
  --run-dir <run_dir> \
  --detection-json <run_dir>/02-source-cold-open-detection/cold_open_detection_result.json \
  --sample-duration-sec 45
```

For a formal production run after the sample validation passes, promote the cleaned source:

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-cold-open-detection/scripts/apply_cold_open_cut.py \
  --run-dir <run_dir> \
  --detection-json <run_dir>/02-source-cold-open-detection/cold_open_detection_result.json \
  --promote-active
```

`--promote-active` archives originals as `source.original_with_cold_open.*` before replacing active `source.mp4`, `source.wav`, and transcript files. Do not use it on historical completed runs unless explicitly repairing them.

## Outputs

Detection writes:

```text
02-source-cold-open-detection/cold_open_detection_result.json
02-source-cold-open-detection/cold_open_detection_report.md
02-source-cold-open-detection/frames/
```

Cutting writes:

```text
02-source-cold-open-cut/source.cleaned.mp4
02-source-cold-open-cut/source.cleaned.wav
02-source-cold-open-cut/source_transcript.en.cleaned.json
02-source-cold-open-cut/source_transcript.en.cleaned.txt
02-source-cold-open-cut/cold_open_cut_validation_result.json
02-source-cold-open-cut/cold_open_cut_validation_report.md
```

## Pass Criteria

Proceed downstream only when:

- detection status is `CUT_CONFIRMED` or `NO_CONFIDENT_CUT`;
- if `CUT_CONFIRMED`, cut validation status is `PASS`;
- if validation does not pass, restore the original source and treat the run as `NO_CONFIDENT_CUT`.

`NEEDS_VISUAL_REVIEW` is not a production pass state. Resolve it by targeted visual review around the transcript candidate or keep the original source unchanged.
