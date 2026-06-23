---
name: ppt-master-deck-video-visuals
description: Convert an existing normal PPT Master project into 4K video/podcast slide images and chapter_semantics.json without changing deck design. Use after /Users/wangfangjia/code/ppt-master or ppt-master-article-deck has generated a normal PPTX/project, when the video workflow needs chapter_01.png... plus semantic sidecar metadata.
---

# PPT Master Deck Video Visuals

This is a deterministic post-processing skill. It does not design slides.

Input is an existing PPT Master project directory. The project must already contain normal deck SVGs from PPT Master:

```text
<project>/svg_final/*.svg
```

or, if finalization has not run yet:

```text
<project>/svg_output/*.svg
```

## Responsibility

Convert a normal PPT Master deck into video-ready assets:

```text
<project>/chapter_visuals/
  chapter_01.png
  chapter_02.png
  ...
  chapter_semantics.json
  chapter_visuals_contact_sheet.jpg
```

This skill must not:

- read the original article to redesign the deck
- change slide count, layout, style, colors, typography, or content
- add subtitle safe areas, progress bars, footers, labels, or chapter badges
- render visible source/footer attribution captions
- render visible internal production notes, validation/sample labels, workflow labels, draft/debug labels, or other process notes
- create or infer timing fields such as `start_sec`, `end_sec`, `start_turn`, or `end_turn`

## Output Contract

- PNGs are full-frame 16:9 renders at `3840x2160`.
- `chapter_semantics.json` has one entry per rendered slide.
- Semantics are derived from slide filenames and PPT speaker notes when available.
- Contact sheet is for QA only and must not add filename labels under thumbnails.

## Script

Run:

```bash
PY=/Volumes/GT34/Caches/ppt-master-venv/bin/python
export PLAYWRIGHT_BROWSERS_PATH=/Volumes/GT34/Caches/ms-playwright
$PY /Users/wangfangjia/.codex/skills/ppt-master-deck-video-visuals/scripts/export_deck_video_visuals.py <ppt_master_project>
```

Optional copy target for a parent video project:

```bash
$PY /Users/wangfangjia/.codex/skills/ppt-master-deck-video-visuals/scripts/export_deck_video_visuals.py \
  <ppt_master_project> \
  --copy-to <video_project>/chapter_visuals
```

## Gate

Pass only when:

```text
chapter_visuals/chapter_semantics.json exists
chapter_semantics.json has one entry per rendered slide
each entry has image, chapter_title, summary, interpretation/speaker_note, visual_intent, script_anchor_hint
no timing fields exist in semantics
all chapter_*.png files exist and are 3840x2160
no slide image contains visible source/footer attribution captions
no slide image contains visible internal production notes, validation/sample labels, workflow labels, draft/debug labels, or other process notes
contact sheet exists
```

If this gate fails, fix the post-processing script or the upstream PPT Master project. Do not redesign slides inside this skill.
