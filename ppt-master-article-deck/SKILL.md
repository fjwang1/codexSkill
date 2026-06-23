---
name: ppt-master-article-deck
description: Generate a normal polished editable PPTX deck from a Chinese or English manuscript, article, report, essay, translated draft, PDF/DOCX/Markdown/text source, URL, or podcast script by delegating design and slide generation to the local canonical /Users/wangfangjia/code/ppt-master skill. Use when the user asks to turn source writing into a PPT/PPTX/deck automatically, wants one final PowerPoint file, mentions ppt-master, or wants autonomous slide design choices while keeping the local ppt-master workflow as the source of truth.
---

# PPT Master Article Deck

This is a thin global wrapper around the local canonical PPT Master skill:

```text
/Users/wangfangjia/code/ppt-master/skills/ppt-master/SKILL.md
```

Use the local PPT Master workflow as the design and execution authority. Do not fork its design model here, do not invent a separate chapter-image mode, and do not add video-specific visual rules to deck generation.

## Scope

This skill produces a normal editable `.pptx` deck.

It does **not** produce podcast/video chapter PNGs. To turn an already generated PPT Master project into 4K video slide images, run:

```text
/Users/wangfangjia/.codex/skills/ppt-master-deck-video-visuals/SKILL.md
```

## Minimal User Constraints

Unless the user says otherwise, pass only these extra constraints into the PPT Master design brief:

- Canvas: PPT 16:9 (`ppt169`) for article decks and video-adjacent decks.
- Do not use black or dark main backgrounds by default.
- Avoid generic dark tech-dashboard styling, neon blue/green palettes, and black-background highlight-line visuals.
- Delivery hygiene: do not place visible source/footer attribution captions on slide canvases.
- Delivery hygiene: do not place visible internal production notes, validation/sample labels, workflow labels, draft/debug labels, or other process notes on slide canvases.

Do not add fixed page counts, fixed card templates, fixed title lengths, fixed bullet counts, default progress lines, forced icon styles, forced typography, forced image strategies, or chapter-image semantics. Let PPT Master decide from the manuscript.

Keep source metadata and process notes in project files, notes, manifests, or the final response rather than visible slide artwork.

## Optional Deck Templates

The local PPT Master library includes these reusable deck templates. This
wrapper does not auto-select them by itself; callers must pass an explicit
template directory path when they want template mode.

```text
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/editorial_magazine
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/swiss_grid
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/memphis_pop
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/risograph_zine
```

Template mode is triggered only by explicit directory paths, matching the local
PPT Master rule. Bare names such as `editorial_magazine` are not enough.

## Paths

Use these canonical paths:

```bash
PPT_MASTER=/Users/wangfangjia/code/ppt-master
SKILL_DIR=/Users/wangfangjia/code/ppt-master/skills/ppt-master
OUT_ROOT=/Volumes/GT34/Generated
CACHE_ROOT=/Volumes/GT34/Caches
VENV=/Volumes/GT34/Caches/ppt-master-venv
```

Store generated projects under `/Volumes/GT34/Generated`. Before disk-heavy work:

```bash
test -d /Volumes/GT34 && test -w /Volumes/GT34
```

Use the external-disk venv when running PPT Master scripts:

```bash
/Volumes/GT34/Caches/ppt-master-venv/bin/python
```

## Workflow

1. Read the local canonical PPT Master skill:

   ```text
   /Users/wangfangjia/code/ppt-master/skills/ppt-master/SKILL.md
   ```

2. Follow that skill's project creation, strategist, executor, validation, finalization, and PPTX export process.

3. Initialize a project under `/Volumes/GT34/Generated` using `ppt169` unless the user explicitly asks for another format:

   ```bash
   python3 ${SKILL_DIR}/scripts/project_manager.py init <project_slug> --format ppt169 --dir ${OUT_ROOT}
   ```

4. Import source material with PPT Master's source import path:

   ```bash
   python3 ${SKILL_DIR}/scripts/project_manager.py import-sources <project_path> <source_files...> --copy
   ```

5. During the strategist step, include only the minimal user constraints above. Keep the rest of the visual strategy dynamic and source-led.

6. Generate SVG slides sequentially under `<project_path>/svg_output/` following the local PPT Master executor rules. Do not batch-template the deck.

7. Run PPT Master validation/finalization/export:

   ```bash
   python3 ${SKILL_DIR}/scripts/svg_quality_checker.py <project_path>
   python3 /Users/wangfangjia/.codex/skills/ppt-master-article-deck/scripts/remove_source_footers.py <project_path>
   python3 ${SKILL_DIR}/scripts/total_md_split.py <project_path>    # when notes/total.md exists
   python3 ${SKILL_DIR}/scripts/finalize_svg.py <project_path>
   python3 /Users/wangfangjia/.codex/skills/ppt-master-article-deck/scripts/remove_source_footers.py <project_path> --also-final
   python3 ${SKILL_DIR}/scripts/svg_to_pptx.py <project_path>
   python3 ${SKILL_DIR}/scripts/project_manager.py validate <project_path>
   ```

8. Validate that the exported PPTX exists, opens with `python-pptx`, and has the same slide count as the SVG deck.

## Final Response

Report:

- final PPTX absolute path
- project directory absolute path
- slide count and validation summary
- any material limitation or skipped step

Do not present a localhost preview URL as the deliverable.
