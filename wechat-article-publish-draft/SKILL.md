---
name: wechat-article-publish-draft
description: "Create WeChat public-account article drafts from local Markdown and cover images using the official WeChat API. Use when Codex needs to upload a translated Chinese article, WeChat article package, or local article directory to the WeChat/微信公众号草稿箱 only, including image upload, cover material upload, draft creation, and local publish reports. This skill must not perform final publication."
---

# WeChat Article Publish Draft

Use this skill to create a **draft only** in a WeChat public account. Never call `freepublish/submit`, never click final publish/send controls, and never claim a public article was published.

Before rendering or publishing, read `references/wechat-article-style-spec.md`. The current style version is `wechat-swiss-grid-v1`, adapted from the local PPT Master `swiss_grid` template with Swiss red `#D9251D`.

## Inputs

Prefer an article directory with this shape:

```text
wechat/reviewed_article.md
wechat/article_metadata.json
cover/main_cover.png
```

The script also accepts explicit paths for Markdown, metadata, and cover.

For a multi-article bundle, pass:

```text
wechat_bundle/wechat_bundle_manifest.json
```

The manifest may include `articles[]` with explicit paths, or `main_article_id` plus `attached_article_ids`; the script resolves standard `articles/A1_*` directories from the run root.

Multi-article model:

- A WeChat multi-article draft is represented by one `articles[]` array.
- The first array item is the main article. It appears as the large top card in WeChat.
- Every later array item is an attached/sub article. It appears below the main card.
- For the daily China bundle workflow, the selection skill's highest-scoring article must be placed first as the main article, and the remaining selected articles must follow in descending score order.

Cover upload policy:

- For WeChat API `draft/add`, every article's `thumb_media_id` must be created from a valid `2.35:1` cover image, including attached/sub articles.
- Prefer `wechat_upload_cover_path`, then `cover_path`, for all articles.
- Do not use a local square crop such as `thumb_square_500x500.png` as the API cover upload unless no valid 2.35:1 cover exists and the caller explicitly accepts the risk. The square crop is mainly for local preview/archive surfaces.

Credentials may come from environment variables or the skill-local `.env` file:

```text
WECHAT_APP_ID
WECHAT_APP_SECRET
```

or:

```text
WECHAT_ACCESS_TOKEN
```

The script loads `<SKILL_DIR>/.env` automatically before reading environment defaults.

The WeChat article author field is always hard-coded as:

```text
他山译读
```

Do not ask the user for an author name and do not use source publication names as the WeChat author.

## Workflow

1. Run a dry run first:

   ```bash
   python3 scripts/publish_wechat_draft.py --article-dir /path/to/article --dry-run
   python3 scripts/publish_wechat_draft.py --bundle-manifest /path/to/wechat_bundle_manifest.json --dry-run
   ```

2. Review `publish/wechat_draft_report.md`, `publish/wechat_article.html`, and `publish/draft_payload.redacted.json`.

   Also open or inspect `publish/wechat_article.preview.html` for local phone-width visual review. The preview file is not sent to WeChat; it is only a comparison artifact.

3. Check the `public_ip` field in the report and make sure that IP is in the WeChat API IP allowlist. The script discovers the current public IP on every run.

4. Only after the user asks to create a WeChat draft and credentials are available, run:

   ```bash
   WECHAT_APP_ID=... WECHAT_APP_SECRET=... python3 scripts/publish_wechat_draft.py --article-dir /path/to/article --live
   WECHAT_APP_ID=... WECHAT_APP_SECRET=... python3 scripts/publish_wechat_draft.py --bundle-manifest /path/to/wechat_bundle_manifest.json --live
   ```

5. Return the report path, current public IP, and whether `draft_created` is true. If the API returns an authorization or credential error, report it directly and ask the user to check the account's developer permissions, IP allowlist, and API quota.

## What The Script Does

- Extract title, source publication, and cover paths from `wechat/article_metadata.json` when present.
- For `--article-dir`, publish `wechat/reviewed_article.md`; do not silently fall back to `wechat/article.md`. If a caller wants a raw Markdown file, it must pass `--article-md` explicitly.
- Do not prefix WeChat-facing titles with source publication names. Use the metadata `title` or Markdown H1 exactly after Markdown cleanup and 32-character truncation. Source publication metadata is kept for audit/reporting only.
- Leave WeChat `content_source_url` empty by default. Do not populate the "原文链接/阅读原文" field from `original_url` or `source_url`; only set it when the user explicitly requests a 阅读原文 URL via `--content-source-url`.
- Support one article or a multi-article WeChat bundle.
- Prefer reviewed article paths when the caller's bundle manifest points to `wechat/reviewed_article.md`.
- Convert Markdown to conservative WeChat-friendly inline-style HTML using `references/wechat-article-style-spec.md`.
- Set the WeChat author field to `他山译读`.
- Discover the current public IP and record it in the report for IP allowlist checks.
- Strip the first `# title` from the body by default because WeChat has a separate title field.
- Upload local inline Markdown images through `cgi-bin/media/uploadimg` and replace their URLs.
- Upload the cover image as permanent material through `cgi-bin/material/add_material?type=image`.
- Create a single-article or multi-article draft through `cgi-bin/draft/add`.
- Write local reports and a phone preview under `publish/`.

## WeChat Format Model

WeChat article bodies are not published as Markdown. The `draft/add` API receives an HTML string in `articles[].content`.

This skill therefore treats Markdown as an editable intermediate format only:

```text
wechat/reviewed_article.md
-> styled inline HTML
-> articles[].content
```

Rendering rules:

- Use inline styles only.
- Avoid JavaScript, iframes, forms, external CSS, and complex layouts.
- Keep the body title out of content by default because WeChat has a separate title field.
- Use `wechat_article.preview.html` to compare typography, title hierarchy, color, image size, captions, spacing, and source-note treatment before live draft creation.
- Record `style_version` in the draft report.

## API Boundaries

Allowed endpoints:

```text
POST /cgi-bin/stable_token
GET  /cgi-bin/token
POST /cgi-bin/media/uploadimg
POST /cgi-bin/material/add_material?type=image
POST /cgi-bin/draft/add
```

Forbidden endpoint:

```text
POST /cgi-bin/freepublish/submit
```

`freepublish/submit` is final publication, not draft creation. Do not use it in this skill.

## Account Notes

Personal/individual公众号 accounts can generally create drafts if the account has the relevant API permission. The final `freepublish` API is restricted for公众号 to certified enterprise accounts, so this skill intentionally stops at draft creation.

If `get_access_token` fails with `61004`, the caller's outbound IP is not in the account's API IP allowlist. Ask the user to add the current server IP in 微信开发者平台/公众平台 developer settings.

## Output

The report JSON uses:

```json
{
  "schema_version": "wechat-article-publish-draft.v1",
  "status": "DRY_RUN_OK | DRAFT_CREATED | BLOCKED | FAILED",
  "draft_created": false,
  "final_publish_clicked": false,
  "article_dir": "...",
  "title": "...",
  "author": "他山译读",
  "content_source_url": "",
  "style_version": "wechat-swiss-grid-v1",
  "public_ip": "...",
  "outputs": {
    "html": "...",
    "preview_html": "...",
    "payload_redacted": "...",
    "report_markdown": "..."
  },
  "blockers": []
}
```

Always preserve `final_publish_clicked: false`.
