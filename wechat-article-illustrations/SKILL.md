---
name: wechat-article-illustrations
description: "为微信公众号长文按章节生成并嵌入正文插图。Use when a translated WeChat article needs one text-free illustration per H2 chapter/section, matching the New Yorker-inspired conceptual editorial style from wechat-cover-image, using only each chapter's own content to avoid repeated imagery, producing 3:2 high-resolution 2K+ source images and optimized WeChat inline images, then inserting Markdown image references into wechat/reviewed_article.md."
---

# WeChat Article Illustrations

Generate and insert one body illustration per article chapter.

Hard requirement:

- Every Markdown H2 chapter must have exactly one body illustration inserted immediately after that H2 heading.
- Cover images, WeChat thumbnails, title images, lead images, source article images, or fallback full-article images do **not** count as chapter illustrations.
- If an article has one or more H2 headings, fallback full-article illustration mode is forbidden.
- Do not publish or draft-submit an article whose H2 chapter count is greater than its inserted chapter-illustration count.

Use this after `wechat/reviewed_article.md` exists and before `wechat-article-publish-draft` renders the article.

## Relationship To Cover Skill

Do not reuse the cover image itself as body art.

Reuse the **style language** from `wechat-cover-image`, not the cover ratio:

- New Yorker-inspired conceptual editorial illustration.
- One strong metaphor.
- Generous negative space.
- Quiet, intelligent visual storytelling.
- Text-free image.
- `他山译读` palette: `#FFFFFF`, `#1A1A1A`, `#D9251D`, `#666666`, `#E8E8E8`, `#F4F4F4`.

Body illustrations use a different ratio:

```text
3:2 horizontal
source/master: 2400x1600 or larger
wechat inline: 2400x1600 optimized JPG when possible
```

Why `3:2`:

- It is calmer and more editorial than 16:9 inside a long WeChat article.
- It gives the metaphor room without becoming a full-width banner.
- It still works well at phone width after the renderer scales images to `width:100%`.

## Chapter Scope

Default chapter definition:

```text
each Markdown H2 section: lines from `## heading` until the next `## heading`
```

Do not feed the whole article to each illustration prompt.

For each chapter, use only:

- the chapter heading
- that chapter's body text
- at most one sentence of local context if needed for continuity

This avoids repeating the same robot/cradle/cover metaphor across every chapter.

If the article has no H2 headings, create at most 3 semantic sections from the body and record that fallback in the manifest. If the article has any H2 heading, do not use fallback mode.

## Placement

Insert each illustration immediately after its H2 heading:

```markdown
## 章节标题

![插图](../illustrations/chapter_01_slug_wechat_2400x1600.jpg)

正文开始……
```

Use alt text `插图` so the current WeChat renderer does not show a visible caption. Captions are optional and should be added only when the user requests them.

## Prompt Rules

Each chapter prompt must be self-contained and text-free:

```text
Create a 3:2 horizontal WeChat article body illustration. Absolutely no text, no letters, no numbers, no logos, no watermark, no typography-like marks.

Chapter heading: <heading>.
Chapter-specific content summary: <summary derived only from this chapter>.
Visual metaphor: <one metaphor specific to this chapter, not reused from other chapters>.
Style: New Yorker-inspired conceptual editorial illustration, quiet intelligent visual metaphor, generous negative space, hand-crafted ink-and-gouache feel, premium restraint.
Palette: white/light neutral base #FFFFFF, near-black subject #1A1A1A, restrained grays #666666 #E8E8E8 #F4F4F4, one controlled Swiss red #D9251D accent.
Composition: 3:2 horizontal, center-safe subject, calm spacing, simple enough for phone reading, not a banner, not an infographic.

Negative prompt: no title, no readable text, no pseudo-text, no letters, no numbers, no charts, no dashboard, no UI, no documents, no newspaper pages, no logo, no watermark, no rigid Swiss-grid poster, no crowded scene, no glossy sci-fi render.
```

## Output Structure

For each article:

```text
illustrations/
  chapter_01_<slug>_source_2400x1600.png
  chapter_01_<slug>_wechat_2400x1600.jpg
  chapter_02_<slug>_source_2400x1600.png
  chapter_02_<slug>_wechat_2400x1600.jpg
  illustrations_manifest.json
wechat/
  reviewed_article.md
  reviewed_article.before_illustrations.<timestamp>.md
```

## Workflow

1. Read `wechat/reviewed_article.md`.
2. Split into H2 chapters.
3. For each chapter, design a distinct metaphor using only that chapter's content.
4. Call `image_gen` once per chapter.
5. Save generated images.
6. Run:

   ```bash
   UV_CACHE_DIR=/Volumes/GT34/Caches/uv uv run --with pillow \
     python /Users/wangfangjia/.codex/skills/wechat-article-illustrations/scripts/postprocess_and_insert_illustrations.py \
     --article-dir /path/to/articles/A1_slug \
     --image-map /path/to/image_map.json
   ```

7. Re-run the WeChat draft dry-run so `publish/wechat_article.preview.html` includes the inserted images.

## Image Map

The postprocess script expects:

```json
{
  "schema_version": "wechat-article-illustrations.image-map.v1",
  "style_version": "new-yorker-conceptual-editorial-v1",
  "images": [
    {
      "chapter_index": 1,
      "heading": "机器中的人形机器人",
      "generated_image_path": "/absolute/path/to/generated.png",
      "prompt": "...",
      "negative_prompt": "..."
    }
  ]
}
```

## Quality Gate

Pass only if:

- Each H2 chapter has exactly one inserted illustration.
- The inserted illustration count equals the H2 chapter count whenever H2 headings exist.
- Cover/title/source/lead images are excluded from the illustration count.
- Each illustration source/master is `2400x1600` or larger.
- Each inline image is `3:2`, at least `2400px` wide, and referenced from `wechat/reviewed_article.md`.
- Each prompt used only that chapter's content, not the whole article.
- The images are text-free: no letters, numbers, labels, logos, UI, documents, charts, or pseudo-text.
- The three chapter illustrations are visually related but not repetitive.
- `illustrations_manifest.json` records chapter headings, prompts, source image paths, processed image paths, and insertion status.
