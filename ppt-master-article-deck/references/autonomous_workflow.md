# Autonomous PPT-Master Workflow

This reference converts ppt-master's human confirmation checkpoint into an internal design decision process. It must not be used to hard-code defaults; it is a set of questions the agent answers from the source.

## Dynamic Design Gates

Before writing `design_spec.md`, answer these gates from the manuscript and the user's request:

1. Purpose and audience: Who will use the deck, what decision or understanding should they leave with, and how much context can be assumed?
2. Output language: Use the user's requested language. If unspecified, infer from the conversation, source, and likely audience.
3. Canvas and format: Choose the physical slide format from the viewing context: conference/screen, classroom, mobile/social, memo-like story, or another explicit use case.
4. Narrative structure: Identify the source's real argument units, tension, evidence, turning points, and ending. Let these units determine slide count.
5. Communication mode: Choose among editorial narrative, general visual explainer, consulting/data brief, top-consulting logical memo, product/keynote, academic, or another appropriate mode.
6. Visual tone: Derive the tone from subject matter and source voice: restrained, analytical, urgent, cultural, human-centered, technical, optimistic, critical, etc.
7. Palette: Pick colors that support the tone and topic. Avoid one-note palettes and avoid blindly reusing colors from previous decks.
8. Typography: Choose PPT-safe fonts that fit language and tone. Ensure CJK text renders well when Chinese appears.
9. Information design: Decide which claims deserve charts, timelines, maps, diagrams, quotes, comparisons, or quiet text-first layouts.
10. Icon/image strategy: Use icons and native SVG information design when they carry meaning. Use real/generated imagery only when it materially improves comprehension and the required assets are available.
11. Parallel asset plan: If imagery is needed, decide the full asset manifest up front so independent raster image/search/edit tasks can run in parallel. Keep slide SVG authoring sequential.
12. Footer policy: No visible source or attribution footer captions on any slide. Use page numbers only if they improve orientation.
13. Speaker notes: Decide whether notes should be concise presenter prompts, detailed voiceover notes, or omitted for a lightweight deck.

## Page Count Heuristic

Do not start with a target page count. Start with the argument map:

- one slide for the central promise or tension
- one slide for each major argument unit that needs its own visual treatment
- one slide for major evidence clusters when compression would hide the point
- one slide for a synthesis, implication, or decision frame

Compress when adjacent units repeat the same visual job. Split when a slide would need two unrelated headlines, too many numbers, or incompatible layouts. A strong deck can be short or long; the right count is the count that preserves the argument's shape.

## Style Selection Signals

Use these signals to choose a mode, then adapt rather than copying a style preset:

- Public policy, economics, markets, strategy, inequality, corporate or industrial analysis: consulting/data or editorial consulting.
- Cultural essay, human story, travel, history, society: editorial narrative or visual explainer.
- Technical report, research, engineering, science: structured technical explainer with precise diagrams.
- Product launch, pitch, campaign, creator story: keynote/product mode with stronger visual pacing.
- Mixed article with both people and systems: alternate human-scale pages with system/evidence pages.

## Quality Bar

- Every slide has one dominant message, visible hierarchy, and enough whitespace for reading.
- Charts use calibrated coordinates and truthful scales.
- Text does not overlap, overflow, or rely on tiny unreadable labels.
- The deck should feel designed for this manuscript, not like a generic template filled with bullets.
- The exported PPTX is the product; SVG and preview artifacts are intermediate checks.
