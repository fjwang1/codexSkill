---
name: wechat-article-illustrations
description: "为微信公众号长文生成并嵌入正文头图和章节插图。Use when a translated WeChat article needs one text-free inline lead/head image before the first paragraph plus one text-free illustration per H2 chapter/section, matching the New Yorker-inspired conceptual editorial style from wechat-cover-image, using article-level content only for the lead image and each chapter's own content for chapter images, producing 3:2 high-resolution 2K+ source images and optimized WeChat inline images, then inserting Markdown image references into wechat/reviewed_article.md."
---

# WeChat Article Illustrations

Generate and insert one inline lead/head image plus one body illustration per article chapter.

Use this after `wechat/reviewed_article.md` exists and before `wechat-article-publish-draft` renders the article.

## Relationship To Cover Skill

Do not reuse the cover image itself as body art. The inline lead/head image is a separate WeChat body image, not the WeChat API cover/thumbnail.

Reuse the **style language** from `wechat-cover-image`, not the cover ratio:

- New Yorker-inspired conceptual editorial illustration.
- One strong metaphor.
- Generous negative space.
- Quiet, intelligent visual storytelling.
- Text-free image.
- `译见中国` palette: `#FFFFFF`, `#1A1A1A`, `#D9251D`, `#666666`, `#E8E8E8`, `#F4F4F4`.

If the caller explicitly requires `瑞士风格`, switch the body-illustration family from the default New Yorker-inspired editorial variant to a Swiss editorial conceptual variant:

- white paper field
- near-black line work and flat geometry
- strict negative space
- restrained `#D9251D` red rules/bars/accents
- still text-free, still metaphor-first, still not an infographic

Body illustrations, including the inline lead image, use a different ratio:

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

## Lead Image Scope

Every article must have exactly one inline lead/head image before the first body paragraph. This is required even when the article already has a WeChat API cover image.

The lead image prompt may use article-level context:

- final Chinese title
- original English title when useful
- the first 2-4 paragraphs or opening thesis
- a short whole-article summary
- one overall visual metaphor that is not reused as any chapter illustration

The lead image should orient the reader into the article's central tension. It must not summarize the whole article as an infographic, and it must not use source-publication branding, title text, URL text, or visible labels.

Default lead image placement:

```markdown
# 文章标题

![头图](../illustrations/lead_00_slug_wechat_2400x1600.jpg)

第一段正文……
```

If the article starts with a lead paragraph, blockquote, or short editor-style opener after H1, insert the lead image before that first body text. Do not place the lead image after the first H2; it is not a chapter illustration.

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

If the article has no H2 headings:

- For ordinary short articles outside the deep-longform bundle, you may create at most 3 semantic fallback sections and record that fallback in the manifest.
- For the daily deep-longform bundle, do not silently fall back to one illustration. The control workflow must first rewrite the article into semantic `##` chapters, then generate one illustration per chapter.
- If the caller explicitly requires chaptered Swiss-style packaging, treat missing H2 headings as a pre-illustration failure, not as permission to skip structure.

## Placement

Insert the lead image immediately after the H1 title and before the first body paragraph:

```markdown
# 文章标题

![头图](../illustrations/lead_00_slug_wechat_2400x1600.jpg)

第一段正文……
```

Insert each illustration immediately after its H2 heading:

```markdown
## 章节标题

![插图](../illustrations/chapter_01_slug_wechat_2400x1600.jpg)

正文开始……
```

Use alt text `头图` for the lead image and `插图` for chapter images so the current WeChat renderer does not show visible captions. Captions are optional and should be added only when the user requests them.

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

Each lead image prompt must also be self-contained and text-free:

```text
Create a 3:2 horizontal WeChat article lead/head image to appear after the H1 and before the first paragraph. Absolutely no text, no letters, no numbers, no logos, no watermark, no typography-like marks.

Article title: <final Chinese title>.
Opening thesis / reader setup: <summary derived from the title and first 2-4 paragraphs>.
Article-level visual metaphor: <one overall metaphor that introduces the article and is not reused by chapter illustrations>.
Style: New Yorker-inspired conceptual editorial illustration, quiet intelligent visual metaphor, generous negative space, hand-crafted ink-and-gouache feel, premium restraint.
Palette: white/light neutral base #FFFFFF, near-black subject #1A1A1A, restrained grays #666666 #E8E8E8 #F4F4F4, one controlled Swiss red #D9251D accent.
Composition: 3:2 horizontal, center-safe subject, calm opening image for phone reading, not a cover thumbnail, not a banner, not an infographic.

Negative prompt: no title, no readable text, no pseudo-text, no letters, no numbers, no charts, no dashboard, no UI, no documents, no newspaper pages, no logo, no watermark, no source branding, no crowded collage.
```

## Output Structure

For each article:

```text
illustrations/
  lead_00_<slug>_source_2400x1600.png
  lead_00_<slug>_wechat_2400x1600.jpg
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
2. Design one distinct lead image metaphor using the title, opening thesis, and short whole-article context.
3. Split into H2 chapters.
4. For each chapter, design a distinct metaphor using only that chapter's content.
5. Call `image_gen` once for the lead image and once per chapter.
6. Save generated images.
7. Run:

   ```bash
   UV_CACHE_DIR=/Volumes/GT34/Caches/uv uv run --with pillow \
     python /Users/wangfangjia/.codex/skills/wechat-article-illustrations/scripts/postprocess_and_insert_illustrations.py \
     --article-dir /path/to/articles/A1_slug \
     --image-map /path/to/image_map.json \
     --require-lead-image
   ```

8. Re-run the WeChat draft dry-run so `publish/wechat_article.preview.html` includes the inserted images.

Generation-source rule:

- Production cover/body art must be generated by `image_gen`.
- Local scripts may crop, resize, compress, validate, and insert images, but must not create the final source art themselves.
- Do not use PIL/SVG/canvas/programmatic diagrams, local hand-drawn placeholders, source-photo crops, chart redraws, screenshots, or stock-like local composites as the generated source image.
- The manifest must make the generation source auditable.

## Image Map

The postprocess script expects:

```json
{
  "schema_version": "wechat-article-illustrations.image-map.v1",
  "style_version": "new-yorker-conceptual-editorial-v1",
  "generation_provider": "image_gen",
  "generated_by": "image_gen",
  "lead_image": {
    "role": "lead_image",
    "generated_image_path": "/absolute/path/to/generated_lead.png",
    "generation_provider": "image_gen",
    "generated_by": "image_gen",
    "prompt": "...",
    "negative_prompt": "..."
  },
  "images": [
    {
      "chapter_index": 1,
      "heading": "机器中的人形机器人",
      "generated_image_path": "/absolute/path/to/generated.png",
      "generation_provider": "image_gen",
      "generated_by": "image_gen",
      "prompt": "...",
      "negative_prompt": "..."
    }
  ]
}
```

## Quality Gate

Pass only if:

- The article has exactly one inserted lead image before the first body paragraph and before the first H2 chapter.
- Each H2 chapter has exactly one inserted illustration.
- For repaired or explicitly chaptered deep-longform bundles, `fallback_single_illustration` must be false.
- The lead image and every source illustration were generated by `image_gen`; `generation_provider` / `generated_by` must be `image_gen` at the image-map and manifest item level.
- Local programmatic images, deterministic geometric diagrams, screenshots, source-photo crops, SVG/PIL/canvas drawings, and placeholders fail the production gate even if they are text-free and visually consistent.
- Each lead/chapter source/master is `2400x1600` or larger.
- Each inline image is `3:2`, at least `2400px` wide, and referenced from `wechat/reviewed_article.md`.
- Chapter prompts used only that chapter's content, not the whole article. The lead prompt used only article-level title/opening/summary context and did not reuse a chapter metaphor.
- The images are text-free: no letters, numbers, labels, logos, UI, documents, charts, or pseudo-text.
- The chapter illustrations are visually related but not repetitive.
- `illustrations_manifest.json` records the lead image, chapter headings, prompts, `generation_provider`, source image paths, processed image paths, and insertion status.
