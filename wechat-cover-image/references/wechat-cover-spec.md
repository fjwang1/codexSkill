# WeChat Cover Spec

Last checked: 2026-06-25.

No publicly indexed official WeChat backend dimensions page was found during this check. Public WeChat design references consistently describe:

- Main/top article cover: `2.35:1`, commonly `900x383`.
- Main cover safe square: centered crop around `383x383`.
- Attached/sub-article thumbnail: square (`1:1`).

References checked:

- Canva China WeChat official account sizes: https://www.canva.cn/sizes/wechat-official-account/
- Yiban 2026 cover guide: https://yiban.io/geo/36058
- Yiban cover-size article: https://yiban.io/blog/24836
- 135 Editor guide: https://www.135editor.com/essences/10593.html

Production rule:

Use `2.35:1` / `900x383` as the working output target, keep important content in the center safe square, and have any future publishing skill re-check the live WeChat backend UI before upload.

When available, preserve a 2K+ source/master cover image, preferably at least `2400px` wide, before generating the `900x383` WeChat-ready raster.

## 译见中国 Palette

Use the following palette as the default color direction for generated no-text cover images:

```text
Paper / light base: #FFFFFF
Ink / deep subject: #1A1A1A
Signal red accent: #D9251D
Secondary gray:    #666666
Divider gray:      #E8E8E8
Soft gray:         #F4F4F4
```

Use the palette as a color mood inside the default New Yorker-inspired conceptual editorial cover style:

- One strong metaphor.
- Generous negative space.
- Quiet, intelligent visual storytelling.
- Restrained, premium composition.
- No embedded text.

Do not force covers into a rigid Swiss-grid poster, diagram, dashboard, or infographic unless the user explicitly asks for that.
