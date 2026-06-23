---
name: wechat-cover-image
description: Generate no-text WeChat public account cover images from full article drafts. Use when the user gives a WeChat article, asks for a 微信公众号封面图/头图/cover, or wants a metaphorical flat-design cover in the established 2.35:1 style.
---

# WeChat Cover Image

Use this skill to generate a WeChat public account cover image from a full article draft. The output should be a visual summary of the article, not a title card.

## Core Rules

- Produce a no-text image: no Chinese, English, letters, numbers, titles, captions, logos, or watermarks.
- Do not paste the article title into the image. Extract the article's central idea and turn it into a visual metaphor.
- Prefer WeChat cover ratio near `2.35:1`. Use the image model's native output size unless the user asks for a specific size.
- Keep important elements in the central safe area because WeChat may crop thumbnails differently across placements.
- Save the final selected image under `/Users/wangfangjia/generated-covers/` with a descriptive filename.
- Use the built-in `image_gen` tool unless the user explicitly asks for a different generation path.

## Visual Style

Base the style on these local references when available:

- `/Users/wangfangjia/pinterest/22.jpeg`
- `/Users/wangfangjia/pinterest/911 poster.jpeg`

Extract style, not content:

- Large solid color planes.
- Minimal flat/vector-like shapes.
- Strong graphic composition with high thumbnail readability.
- Sparse focal subject, lots of negative space.
- Crisp edges, selective bold black outlines.
- Retro screenprint/poster feeling.
- Limited but vivid palette, especially teal, chartreuse/lime, cream, black, orange/coral.
- Avoid photorealism, 3D rendering, glossy AI aesthetics, cyberpunk, robots, UI screens, and generic technology imagery.

## Workflow

1. Read the article and identify one core proposition, not just the topic.
2. Translate the proposition into 1-3 visual metaphors. Prefer concrete scenes over diagrams.
3. Choose the metaphor that is simplest at thumbnail size and emotionally aligned with the article.
4. Compose for ultra-wide `2.35:1`: wide calmness, central safe area, strong focal structure, no edge-dependent meaning.
5. Generate the image with `image_gen`.
6. Copy the generated file from `/Users/wangfangjia/.codex/generated_images/...` to `/Users/wangfangjia/generated-covers/`.
7. Report the saved path and the final prompt briefly.

## Prompt Template

Use and adapt this structure:

```text
Create an ultra-wide 2.35:1 horizontal flat graphic WeChat cover image, using the model's native output size. No text, no letters, no numbers, no logos, no watermark.

Reference style: bold minimal flat design inspired by the local references /Users/wangfangjia/pinterest/22.jpeg and /Users/wangfangjia/pinterest/911 poster.jpeg: large solid color fields, crisp vector-like edges, high contrast, simplified shapes, clean focal subject, sparse composition, retro screenprint poster feeling.

Article idea: <one-sentence distilled thesis>.

Visual metaphor: <describe the chosen scene without literal text>.

Composition for 2.35:1: ultra-wide landscape, central safe area, large negative space on left and right, strong focal subject readable at thumbnail size. Avoid relying on details near the edges.

Palette and layout: teal, chartreuse/lime, cream, black, orange/coral; large flat planes; simple geometric shapes; selective bold black outlines.

Avoid: text of any kind, title-card layout, robots, brain icons unless explicitly justified, computer screens, UI, photorealism, 3D rendering, gradients, generic AI glow.
```

## Metaphor Guidance

- For essays about execution, discipline, feedback, or goals: use paths, target, obstacles, loops, shadows, or a calm figure moving through structured space.
- For essays about clarity vs. confusion: use a clean central route contrasted with tangled side routes.
- For essays about observation or decision-making: use a figure pausing before a field, chessboard-like landscape, or separated signal/noise shapes.
- For essays about growth or learning: use transformation of messy shapes into ordered forms, but keep the image simple.
- If the article has strong emotional content, represent the emotion through shape, scale, color, and spatial tension rather than facial expressions or words.
