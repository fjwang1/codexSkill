# Deprecated: Deck Image Export Mode

Do not use this reference for new work.

Chapter/video PNG export has been split out of `ppt-master-article-deck` so the normal PPT Master design process stays unpolluted. For new work, first generate a normal PPT Master deck, then run:

```text
/Users/wangfangjia/.codex/skills/ppt-master-deck-video-visuals/SKILL.md
```

The old guidance below is retained only for historical context.

## Responsibility Split

- This skill owns normal deck strategy, information design, SVG slide authoring, optional editable PPTX export, and 4K PNG rendering.
- This mode is untimed. Do not read, request, infer, preserve, or invent `start_sec/end_sec`.
- Render one PNG per final deck slide and write `chapter_semantics.json`.

## Output Contract

Create these files:

```text
<project>/chapter_visuals/
  chapter_semantics.json
  chapter_01.png
  chapter_02.png
  ...
```

Optional useful副产物:

```text
<project>/exports/<name>.pptx
<project>/svg_output/*.svg
<project>/svg_final/*.svg
<project>/chapter_visuals/chapter_visuals_contact_sheet.jpg
```

The PNG files are the video deliverables. The PPTX is only a review/editing副产物 unless the user also asked for an editable deck.

`chapter_semantics.json` is a lightweight explanation file for the exported slides. It is not a visible caption layer and not a design constraint.

## Canvas

Render each slide as a full-frame `3840x2160` 16:9 PNG. Do not shrink the slide, letterbox it, crop it, or insert an artificial reserved strip.

Do not add default progress bars, progress tracks, top/bottom separator rules, footer status lines, or slide-template chrome just because this is for video. Use such elements only when the manuscript and chosen deck design genuinely need them. Normal deck affordances such as cover slides, divider/transition slides, closing slides, and page numbers are allowed when useful.

## Semantics Seed

Prefer a semantics seed when the strategist has already decided the final slide sequence:

```json
{
  "schema_version": "ppt-master-chapter-semantics-seed.v1",
  "visual_system": {
    "resolution": "3840x2160",
    "render_source": "ppt-master svg via headless chromium"
  },
  "chapters": [
    {
      "chapter_index": 1,
      "slide_role": "cover",
      "chapter_title": "结构偏科",
      "short_title": "偏科",
      "summary": "AI 硬件把总分拉高，非 AI 制造业正在失速。",
      "speaker_note": "这一章要解释的是，表面上制造业数据被 AI 硬件拉得很好看，但这种好看并不代表整条制造业链条都在复苏。",
      "visual_intent": "表现总量亮点和结构弱项之间的反差。",
      "script_anchor_hint": "对应播客稿中开场提出“总分好看但结构偏科”的段落。",
      "visual_type": "chosen_by_ppt_master"
    }
  ]
}
```

If no seed exists, create `chapter_visuals/chapter_semantics_seed.json` from the manuscript/script before slide authoring.

Every seed item should include enough semantics for a reader or later workflow to understand the exported slide:

- `chapter_index`
- `chapter_title`
- `summary`
- `speaker_note` or `interpretation`
- `visual_intent`
- `script_anchor_hint`
- optional `slide_role`
- optional `short_title`, `points`, `visual_type`, `keywords`, `evidence`

`points` are semantic hints only. Do not force a visible bullet list or a fixed number of points on the page.

Do not include timing fields such as `start_sec`, `end_sec`, `start_turn`, or `end_turn` in the PPT visual export seed or semantics.

When the input is a finalized `podcast_script.md`:

1. Read only the podcast script, not the original article, unless the user explicitly asks for article-based visuals.
2. Choose the full deck structure from the script's real argument structure and viewing context.
3. Cover, setup, evidence, mechanism, synthesis, transition, recap, and closing slides are all allowed when they make the deck better.
4. Write untimed slide semantics with semantic fields.
5. Render PNGs and `chapter_semantics.json`.
6. Leave timing outside this skill.

## Visual Strategy

Default audience: `面向 B 站观众` unless the user specifies another audience. Keep this label simple in `design_spec.md`.

Use the normal PPT Master strategist/executor process. The strategist should decide the page count, deck rhythm, style, palette, typography, image strategy, diagram strategy, chart strategy, and density from the script's subject, tone, evidence, pacing, and intended viewer.

Taste priors:

- Do not use black or dark main backgrounds by default. Use a dark main background only when the topic strongly requires it and record the reason in `design_spec.md`.
- Avoid generic dark tech-dashboard styling, neon blue/green palettes, and black-background highlight-line visuals.

Do not hard-code these as defaults:

- short titles
- fixed number of points
- visible bullet lists
- information-graphic-first layouts
- progress lines
- bottom chrome or footer bars
- a single repeated card template

The exported slide images may be cover pages, editorial layouts, data pages, mechanism diagrams, warm magazine-style pages, photo-led pages, map/comparison pages, section dividers, synthesis pages, or any other PPT Master-quality approach that fits the material. A validation run must use the same quality bar as a deliverable run.

## Rendering

After `finalize_svg.py`, render from `svg_final/` when present, otherwise `svg_output/`.

Use:

```bash
PLAYWRIGHT_BROWSERS_PATH=/Volumes/GT34/Caches/ms-playwright \
python3 /Users/wangfangjia/.codex/skills/ppt-master-article-deck/scripts/export_chapter_pngs.py \
  <project_path> \
  --semantics-seed <project_path>/chapter_visuals/chapter_semantics_seed.json
```

The renderer scales each SVG slide to a `3840x2160` viewport with headless Chromium, verifies image dimensions, and writes `chapter_semantics.json`. It may also create `chapter_visuals_contact_sheet.jpg` for quick human QA.
It writes `chapter_semantics.json` by extracting the seed chapter's title, summary, optional points, `speaker_note`/`interpretation`, `visual_intent`, `script_anchor_hint`, image filename, and source SVG path.

## Gate

Pass only when:

```text
chapter_visuals/chapter_semantics.json exists
chapter_semantics.json has one semantic entry per generated slide image
each semantic entry identifies its image and gives enough text to understand what the slide is about
each chapter image exists and is 3840x2160
images form one coherent PPT Master deck
no visible source/footer attribution caption appears
no visible internal production note appears
no default progress line, top/bottom separator rule, or footer status bar appears
facts, numbers, and names are traceable to the manuscript, script, or supplied seed
```
