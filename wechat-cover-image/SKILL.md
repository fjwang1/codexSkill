---
name: wechat-cover-image
description: "为微信公众号文章生成无文字 2.35:1 封面图。Use when the user provides a WeChat public-account article draft and asks for 公众号封面图/头图/cover; the skill reads the article, abstracts its theme, and by default generates a New Yorker-inspired conceptual editorial cover: one strong metaphor, generous negative space, quiet wit, restrained premium composition, text-free 2.35:1 image. Use the 译见中国 color palette by default: white, near-black, Swiss red #D9251D, and restrained grays."
---

# WeChat Cover Image

Generate one WeChat public-account cover image from one article draft.

Input:

```text
one article draft, preferably Markdown or plain text
optional style: auto | 外刊高级杂志风 | 写实 | 清新 | 美式漫画 | 科技风 | 杂志风 | 极简插画
optional style modifiers: 克制高级感 | 轻微科技感 | 轻微电影感 | 轻微活力感 | 极简感
```

If the caller explicitly requires `瑞士风格`, switch from the default New Yorker-inspired variant to a Swiss editorial conceptual variant:

- white paper field
- near-black line work and flat geometry
- strong negative space
- restrained `#D9251D` red rules/bars/accents
- no photorealistic source-image crop fallback
- still no text

Output:

```text
2.35:1 horizontal cover image
2K+ source/master image when available
cover_manifest.json with article summary, abstracted theme, style, prompt, and output path
```

## Core Rules

- Read the article first. Do not design from the title alone.
- Distill the article into:
  - `core_proposition`: what the article is really saying
  - `emotional_tone`: calm, anxious, critical, hopeful, absurd, etc.
  - `visual_theme`: a short theme that can become an image
  - `visual_metaphor`: one concrete scene or symbolic composition
- Hard rule: the generated cover image must be text-free. Never ask the image model to render Chinese/English titles, letters, numbers, charts with labels, UI text, newspaper pages, documents, logos, badges, captions, subtitles, watermarks, or typography-like marks.
- If the publishing workflow later needs a title, add it outside this skill in a separate layout/compositing step. This skill's image output is always a no-text visual base.
- Default hard style rule: use one unified foreign-media translation cover style unless the user explicitly overrides it. The default style is New Yorker-inspired conceptual editorial cover art: one strong metaphor, generous negative space, quiet intelligence, subtle irony or tension when appropriate, premium restraint, and no explanatory clutter.
- Default color direction: use the `译见中国` palette as a restraint, not as a literal Swiss-grid layout.
- Output ratio must be `2.35:1`. Keep a 2K+ source/master image when available, preferably at least `2400px` wide, then use `900x383` when post-processing to an exact WeChat-ready raster is practical.
- Keep important visual information inside the center safe square because WeChat preview surfaces may crop the main cover.
- Save final files under the caller's project directory when provided; otherwise use `/Users/wangfangjia/generated-covers/`.
- Use `image_gen` for image generation unless the user explicitly asks for another path.
- Production WeChat covers must record `generation_provider: "image_gen"` and `generated_by: "image_gen"` in `cover_manifest.json`.
- Local scripts may only crop, resize, compress, and derive safe-square/thumb variants from the `image_gen` source. Do not use PIL/SVG/canvas/programmatic diagrams, source-photo crops, screenshots, or local hand-drawn placeholders as the final source art unless the user explicitly overrides the image-generation requirement.

## Cover Spec

Working production spec:

```text
main cover ratio: 2.35:1
source/master size: 2400px wide or larger when available
common raster size: 900x383
center safe square: about 383x383
```

Read `references/wechat-cover-spec.md` when exact sizing or source notes matter.

## Color System

Default `译见中国` cover palette:

```text
Paper / light base: #FFFFFF
Ink / deep subject: #1A1A1A
Signal red accent: #D9251D
Secondary gray:    #666666
Divider gray:      #E8E8E8
Soft gray:         #F4F4F4
```

Use these colors as a palette reference inside the magazine cover style:

- Prefer white/light neutral backgrounds, deep near-black subjects, restrained gray atmosphere, and one controlled `#D9251D` red accent.
- Red should be a small signal or focal accent, not a full red poster background.
- Do not force strict Swiss grid geometry, mechanical bar charts, or abstract PPT-like line systems unless the article itself calls for them.
- The image should still feel like a premium editorial cover, not a diagram, slide, infographic, dashboard, or template test.

## Style System

Default to a unified house style. Do not let `auto` choose a completely different visual genre per article.

House style:

```json
{
  "house_style_name": "纽约客式概念编辑封面",
  "primary_style": "概念编辑插画",
  "style_modifiers": ["强隐喻", "大留白", "克制高级感"],
  "palette": "译见中国: white + near-black + Swiss red #D9251D + restrained grays",
  "style_combo": "纽约客式概念编辑封面 + 强隐喻 + 大留白 + 译见中国配色"
}
```

### Default House Style

Use this unless the user explicitly asks for another style:

```text
New Yorker-inspired conceptual editorial cover illustration, one strong visual metaphor, quiet intelligent scene, generous negative space, minimal composition, premium restraint, subtle irony or unease when appropriate, white/light base, near-black subject, restrained grays, one controlled Swiss red #D9251D accent, no text, 2.35:1
```

Visual grammar:

- Use one dominant metaphor. Supporting objects are allowed only if they sharpen that metaphor.
- Keep the scene simple enough to read as a WeChat thumbnail.
- Prefer conceptual editorial illustration over literal news photo, infographic, poster, comic panel, or sci-fi concept art.
- Add vitality through implication, gesture, shadow, object relationship, or one strange-but-clear detail; not through clutter.
- Keep a restrained but not dull palette: white/light neutral base, deep near-black subject, subtle gray tones, and one small `#D9251D` accent.
- Put the core subject inside the center safe square.
- Avoid generic stock-photo scenes, crowded collages, fake magazine covers, fake documents, visible screens with UI, decorative background noise, and literal chart-like explanations.

New Yorker-inspired cover traits:

- The image should feel like a short story compressed into one quiet scene.
- The metaphor should be understandable without labels, but not overly literal.
- Use absence, scale shift, repetition, shadow, or one unexpected object relationship.
- Leave real empty space; do not fill every corner.
- Prefer hand-crafted editorial illustration or minimal painterly editorial art over glossy 3D render, cyberpunk, UI poster, or PPT-like geometry.
- Clever is good; cute, busy, or sensational is not.

Topic adaptation stays inside the house style:

- Technology, AI, robotics, chips, EVs, automation, and supply chains: show a concrete object behaving slightly unlike itself: a robot arm at an empty workbench, a chip as a locked room, a battery as a split path. Avoid cyberpunk, glowing code, or generic sci-fi.
- Geopolitics, trade, security, and diplomacy: use symbolic objects, thresholds, rooms, borders, shadows, or controlled tension. Avoid flags, emblems, sensational scenes, and document text.
- Economy, business, markets, and industrial policy: use a strong concrete object or spatial metaphor. Avoid charts, tickers, dashboards, and newspaper pages.
- Social change, labor, demographics, education, and culture: use absence and human-scale objects: empty chairs, gloves, coats, queues, shadows, thresholds. Avoid staged stock-photo smiles or melodrama.

Use this style recipe for `auto` or missing style:

```json
{
  "house_style_name": "纽约客式概念编辑封面",
  "primary_style": "概念编辑插画",
  "style_modifiers": ["强隐喻", "大留白", "克制高级感"],
  "style_combo": "纽约客式概念编辑封面 + 强隐喻 + 大留白 + 译见中国配色"
}
```

Add at most one topic modifier when useful:

```text
轻微科技感 | 轻微电影感 | 极简感
```

Examples:

- AI chip article: `纽约客式概念编辑封面 + 强隐喻 + 克制高级感 + 轻微科技感 + 译见中国配色`
- EV market article: `纽约客式概念编辑封面 + 强隐喻 + 大留白 + 轻微活力感 + 译见中国配色`
- rare-earth diplomacy article: `纽约客式概念编辑封面 + 强隐喻 + 克制高级感 + 轻微电影感 + 译见中国配色`
- abstract battery-recycling article: `纽约客式概念编辑封面 + 强隐喻 + 大留白 + 极简感 + 译见中国配色`

### Explicit Overrides

Only use the older style families when the user explicitly asks for them. Even then, keep the output simple, metaphor-forward, premium, text-free, and compatible with the `译见中国` palette unless the user requests a different palette.

### 瑞士风格

Use this when the caller explicitly requires a Swiss-style house look across cover, article layout, and body illustrations.

Prompt traits:

```text
Swiss editorial conceptual illustration, white paper background, near-black keylines, flat geometric shapes, disciplined composition, generous negative space, one or two controlled #D9251D red bars/accents, no text, no logos, no photo crop, 2.35:1, center-safe subject
```

Avoid:

```text
literal source-photo crops, fake magazine mastheads, busy collage, dashboard graphics, chart labels, glossy 3D rendering
```

### 写实

Use only when explicitly requested, or when the user asks for a realistic documentary look.

Prompt traits:

```text
documentary editorial realism, cinematic natural light, believable scene, restrained composition, white/near-black/gray palette with a small Swiss red #D9251D accent when natural, no text, 2.35:1, center-safe subject
```

Avoid:

```text
stock-photo cliches, fake newspaper pages, readable logos, sensational disaster imagery
```

### 清新

Use only when explicitly requested, or when the user asks for a lighter visual tone.

Prompt traits:

```text
bright clean editorial illustration or light realistic scene, airy composition, soft daylight, white/light gray base, controlled red #D9251D accent, no text, 2.35:1
```

Avoid:

```text
overly cute mascots, pastel clutter, childish expression unless the article is explicitly playful
```

### 美式漫画

Use only when explicitly requested. Do not use this automatically for foreign-media translation covers.

Prompt traits:

```text
American comic cover style, bold ink outlines, dynamic composition, vivid contrast, one controlled red accent, no text, 2.35:1
```

Avoid:

```text
superhero IP lookalikes, speech bubbles with text, excessive violence
```

### 科技风

Use only when explicitly requested as the primary style. For normal AI/chip/EV articles, keep `杂志风` primary and add only `轻微科技感`.

Prompt traits:

```text
clean technology editorial visual, precise materials, restrained white/black/gray palette with one Swiss red #D9251D accent, subtle futuristic mood, no readable UI, no text, 2.35:1
```

Avoid:

```text
generic glowing brains, floating code, illegible UI screens, cyberpunk haze unless the article tone really calls for it
```

### 杂志风

This is a fallback primary style. The default primary style is now `概念编辑插画`.

Prompt traits:

```text
high-end magazine editorial cover image, sophisticated composition, strong central metaphor, restrained 译见中国 palette, no text, 2.35:1
```

Avoid:

```text
fake magazine mastheads, text blocks, overdesigned collage that fails at thumbnail size
```

### 极简插画

Use only when explicitly requested as the primary style. For abstract structural articles, keep `杂志风` primary and add only `极简感`.

Prompt traits:

```text
minimal flat editorial illustration, large shapes, strong negative space, crisp edges, central symbolic subject, white/near-black/gray palette with one Swiss red #D9251D accent, no text, 2.35:1
```

Local style references may be used when available:

```text
/Users/wangfangjia/pinterest/22.jpeg
/Users/wangfangjia/pinterest/911 poster.jpeg
```

Extract style only, not content.

## Workflow

1. Read the article draft.
2. Write a short design brief:
   - `core_proposition`
   - `theme`
   - `house_style_name`
   - `primary_style`
   - `style_modifiers`
   - `style_combo`
   - `palette`
   - `visual_metaphor`
   - `dominant_subject`
   - `composition`
   - `negative_prompt`
3. Generate the cover prompt.
4. Call `image_gen`.
5. Save the output image.
6. If needed, crop/resize to an exact `2.35:1` cover, preferably `900x383`.
7. Preserve a 2K+ source/master image when available.
8. Create `cover_manifest.json`.
9. Report only the saved image path, manifest path, chosen theme, style, and prompt summary.

## Prompt Template

```text
Create a 2.35:1 horizontal WeChat public account cover image. Absolutely no text, no letters, no numbers, no logos, no watermark, no typography-like marks.

Article core proposition: <one-sentence core_proposition>.
Abstract theme: <theme>.
House style: 纽约客式概念编辑封面.
Chosen style combo: <style_combo, defaulting to 纽约客式概念编辑封面 + 强隐喻 + 大留白 + one light topic modifier + 译见中国配色>.
Palette: white/light neutral base, near-black subject, restrained grays, one controlled Swiss red #D9251D accent. Use the palette as a color direction only; do not imitate a Swiss grid poster or infographic.
Dominant subject: <one clear subject or metaphorical object>.
Visual metaphor: <one concrete scene or symbolic composition>.

Composition: ultra-wide horizontal 2.35:1, one central subject or object relationship inside the center safe square, simple conceptual editorial composition, generous real negative space, subtle irony or tension, readable at small thumbnail size, clean foreground/background separation, no critical details near the edges.

Style details: New Yorker-inspired conceptual editorial illustration, quiet intelligent visual metaphor, simple subject-forward scene, restrained 译见中国 palette, premium hand-crafted editorial feel, not glossy, not busy, no text.

Negative prompt: no title card, no readable text, no pseudo-text, no letters, no numbers, no UI text, no charts with labels, no documents, no newspaper pages, no fake logos, no watermark, no collage, no crowded scene, no clutter, no low-quality AI artifacts, no rigid Swiss-grid poster, no infographic, no dashboard, no glossy sci-fi render, no stock-photo corporate scene.
```

## Manifest Schema

Write:

```json
{
  "schema_version": "wechat-cover-image.v1",
  "article_path": "...",
  "article_sha256": "...",
  "created_at": "ISO-8601",
  "generation_provider": "image_gen",
  "generated_by": "image_gen",
  "generation_source_type": "ai_generated_image",
  "cover_ratio": "2.35:1",
  "source_size_px": ">=2400px wide when available",
  "source_image_path": "...",
  "target_size_px": "900x383",
  "center_safe_square_px": "383x383",
  "house_style_name": "纽约客式概念编辑封面",
  "primary_style": "概念编辑插画",
  "style_modifiers": ["强隐喻", "大留白", "克制高级感"],
  "style_combo": "纽约客式概念编辑封面 + 强隐喻 + 大留白 + 译见中国配色",
  "palette": {
    "paper": "#FFFFFF",
    "ink": "#1A1A1A",
    "accent": "#D9251D",
    "secondary": "#666666",
    "divider": "#E8E8E8",
    "soft_gray": "#F4F4F4"
  },
  "text_policy": "no visible text, letters, numbers, logos, watermarks, labels, or typography-like marks",
  "core_proposition": "...",
  "theme": "...",
  "dominant_subject": "...",
  "visual_metaphor": "...",
  "prompt": "...",
  "negative_prompt": "...",
  "output_image_path": "...",
  "postprocess": {
    "cropped_or_resized": true,
    "final_size_px": "900x383"
  }
}
```

## Quality Gate

Pass only if:

- The image is horizontal and `2.35:1` or post-processed to `900x383`.
- The source art was generated by `image_gen`; `cover_manifest.json` must record `generation_provider: "image_gen"` and `generated_by: "image_gen"`.
- Local programmatic images, deterministic geometric diagrams, source-photo crops, screenshots, SVG/PIL/canvas drawings, and placeholders fail the production gate unless the user explicitly requested a non-AI image source.
- A 2K+ source/master image is preserved when available, preferably at least `2400px` wide.
- No visible text, pseudo-text, letters, numbers, logos, labels, UI text, watermarks, or typography-like marks appear.
- The cover expresses the article's theme, not merely a generic topic icon.
- The cover follows the New Yorker-inspired conceptual editorial cover style unless the user explicitly requested another style.
- The image uses or is compatible with the `译见中国` palette: white/light base, near-black subject, restrained grays, and one controlled Swiss red `#D9251D` accent.
- The image has one clear dominant metaphor, a simple composition, restrained premium palette, and enough visual intelligence to avoid looking generic.
- The image is not a collage, poster, infographic, busy sci-fi scene, comic panel, generic stock photo, or rigid Swiss-grid diagram unless explicitly requested.
- The main subject remains readable when center-cropped.
- The manifest records `house_style_name`, `primary_style`, `style_modifiers`, `style_combo`, `palette`, `dominant_subject`, and design reasoning.
