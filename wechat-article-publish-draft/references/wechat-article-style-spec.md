# WeChat Article Style Spec

Version: `wechat-swiss-grid-v1`

This spec defines the publishable HTML format for translated long-form news articles in the `译见中国` WeChat public-account workflow.

The visual language is adapted from the local PPT Master Swiss Grid deck:

```text
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/swiss_grid
```

It borrows the template's Swiss International Typographic Style principles: white paper, black typography, signal red accents, strict left alignment, no decoration, and a 16px modular rhythm. It is adapted for a long WeChat article, not copied as a slide layout.

## Format Model

WeChat article body content is not Markdown at publish time. The WeChat draft API accepts an HTML string in `articles[].content`.

The workflow keeps Markdown only as an editable intermediate format:

```text
wechat/reviewed_article.md
-> publishable inline-style HTML
-> draft/add articles[].content
```

Rules:

- Use conservative HTML tags only: `section`, `p`, `span`, `strong`, `em`, `h1`, `h2`, `h3`, `blockquote`, `ul`, `ol`, `li`, `hr`, `img`, `a`, `code`, `pre`.
- Use inline styles only. Do not rely on `<style>`, classes, external CSS, JavaScript, iframes, forms, custom fonts, gradients, shadows, or complex layout tricks.
- Body images must be uploaded through WeChat `media/uploadimg`; external image URLs may be filtered by WeChat.
- Cover images use permanent media material through `material/add_material?type=image`; covers are not the same as body images.
- The local preview HTML may include a phone-width wrapper, but that wrapper must not be sent as WeChat article content.

Official API grounding:

- `draft/add` uses `articles[].content` as the article body, supports HTML tags, removes JavaScript, requires fewer than 20,000 characters and less than 1 MB, and requires body image URLs to come from the article-image upload interface.
- `media/uploadimg` returns a WeChat image URL for images inserted into article content. The interface notes jpg/png only and size under 1 MB for article body images.

## Visual Direction

Editorial Swiss grid for serious translated reporting:

- White background as the dominant visual field.
- Near-black text, gray metadata, red structural accents.
- Flush-left, ragged-right text.
- Strong hierarchy through size, weight, rules, and spacing.
- No rounded cards, no shadows, no gradients, no decorative color washes.
- Red is a signal, not a background theme. Keep red under 10% of the visual surface.

## Color System

Inherited from PPT Master `swiss_grid`:

```text
Paper:      #FFFFFF
Ink:        #1A1A1A
Swiss red:  #D9251D
Secondary:  #666666
Tertiary:   #999999
Divider:    #E8E8E8
Soft gray:  #F4F4F4
```

## Typography

Base container:

```text
font-size: 16px
line-height: 1.78
color: #1A1A1A
letter-spacing: 0
text-align: left
```

Font stack:

```text
Arial, "Helvetica Neue", Helvetica, "PingFang SC", "Microsoft YaHei", sans-serif
```

WeChat title handling:

- WeChat's title field is the primary article title.
- By default, strip the first Markdown H1 from body content before sending to WeChat.
- The local preview wrapper may show a large Swiss-style title: `30px`, line-height `1.18`, weight `900`.

Lead paragraph:

- First non-source-note paragraph.
- `18px`, line-height `1.72`, weight `700`, color `#1A1A1A`.
- Bottom margin `26px`.
- Use only once per article.

Body paragraphs:

- `16px`, line-height `1.78`, color `#1A1A1A`.
- Bottom margin `18px`.
- No first-line indent.
- No justified text.

Secondary headings:

- H2 is a Swiss section header:
  - wrapper margin `44px 0 18px`
  - top red rule `3px solid #D9251D`
  - top padding `14px`
  - title `22px`, line-height `1.32`, weight `900`, color `#1A1A1A`
- H3:
  - `17px`, line-height `1.48`, weight `900`
  - left red rule `3px solid #D9251D`
  - left padding `10px`

## Source Notes

Source notes are article metadata, not quotes. Render them as a compact left-rule block:

```text
margin: 0 0 32px
padding: 14px 0 14px 16px
background: #FFFFFF
border-left: 3px solid #D9251D
font-size: 12px
line-height: 1.7
color: #666666
```

Recognized source-note starts:

```text
来源：
原文：
原载：
本文：
译注：
出处：
Source:
Original:
```

## Images

Body image block:

```text
margin: 28px 0
text-align: left
```

Image:

```text
display: block
width: 100%
max-width: 100%
height: auto
margin: 0
border-radius: 0
```

Caption:

```text
margin: 8px 0 0
font-size: 12px
line-height: 1.55
color: #666666
text-align: left
```

Caption rules:

- Use Markdown image alt text as caption only if it is meaningful.
- Suppress generic alt text such as `image`, `img`, `photo`, `picture`, `cover`, `图片`, or `图`.
- Do not keep orphan captions when the corresponding image is missing or skipped.

## Quotes And Lists

Blockquote:

```text
margin: 28px 0
padding: 16px 0 16px 18px
border-left: 4px solid #D9251D
background: #FFFFFF
font-size: 18px
line-height: 1.65
font-weight: 700
color: #1A1A1A
```

Lists:

```text
padding-left: 22px
margin: 0 0 18px
font-size: 16px
line-height: 1.78
```

List item margin: `6px 0`.

## Output Contract

Dry runs and live draft creation write:

```text
publish/wechat_article.html
publish/wechat_article.preview.html
publish/draft_payload.redacted.json
publish/wechat_draft_report.json
publish/wechat_draft_report.md
```

`wechat_article.html` is the content fragment sent to WeChat.

`wechat_article.preview.html` is only for local visual review.

`wechat_draft_report.json` must record:

```json
{
  "style_version": "wechat-swiss-grid-v1",
  "final_publish_clicked": false
}
```

## Style Change Process

When tuning the visual identity:

1. Edit this spec first.
2. Update the renderer in `scripts/publish_wechat_draft.py`.
3. Run a dry run on an existing article or bundle.
4. Compare `wechat_article.preview.html`.
5. Only create a live draft after the preview is acceptable.
