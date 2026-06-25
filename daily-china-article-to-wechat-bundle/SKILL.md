---
name: daily-china-article-to-wechat-bundle
description: "每日英文外刊中国选题到微信公众号图文包的总控 skill。Use when the user wants to reuse china-longform-article-selection to select five material-available China Viva articles, keep all five candidates, create faithful natural Chinese translation drafts, generate WeChat cover images, package one main article plus four attached articles, and hand off to an independent WeChat publishing draft skill."
---

# Daily China Article To WeChat Bundle

This skill turns the existing China Viva article-selection workflow into a WeChat public-account article bundle. It does not make videos, audio, subtitles, or Bilibili drafts.

Pipeline:

```text
target_date
-> china-longform-article-selection material-gated Top 5
-> standardize five article packages
-> faithful Chinese translations for all five
-> WeChat article package: one main article + four attached articles
-> WeChat content compliance review and reviewed copy
-> cover images
-> WeChat inline-HTML style rendering and preview
-> wechat-article-publish-draft API draft creation
```

## Dependencies

Read these skills before executing their stages:

1. `/Users/wangfangjia/.codex/skills/china-longform-article-selection/SKILL.md`
2. `/Users/wangfangjia/.codex/skills/url-page-capture/SKILL.md` when validating or repairing capture material
3. `/Users/wangfangjia/.codex/skills/wechat-cover-image/SKILL.md` for cover generation style
4. `/Users/wangfangjia/.codex/skills/wechat-article-compliance-review/SKILL.md` for content compliance review
5. `/Users/wangfangjia/.codex/skills/wechat-article-publish-draft/SKILL.md` and its `references/wechat-article-style-spec.md` for final inline-HTML rendering and draft-box API creation

For cover sizing details, read `references/wechat-cover-spec.md`.

## Date And Output Root

Default target date:

```text
target_date = Asia/Shanghai yesterday
```

If the user specifies a date, resolve it to absolute `YYYY-MM-DD`.

Before disk-heavy work, verify `/Volumes/GT34` is mounted and writable.

Dedicated artifact root for this skill:

```text
/Volumes/GT34/daily_china_article_wechat/
```

Place all WeChat bundle run outputs under this root. Do not use ad-hoc sibling directories for this skill's standard artifacts.

Run directory:

```text
/Volumes/GT34/daily_china_article_wechat/{target_date}_china_viral/
```

Expected structure:

```text
selection/
  source-shortlist.json
  ranked-top5.json
  selection-decision.json
  selection-result.md
  final-report.md
articles/
  A1_<slug>/
    source/article.txt
    source/source_metadata.json
    media/media_manifest.json
    media/original/ optional downloaded source images/videos
    translation/translation.md
    translation/translation_manifest.json
    wechat/article.md
    wechat/reviewed_article.md
    wechat/compliance_review_result.json
    wechat/compliance_review_report.md
    wechat/article_metadata.json
    cover/main_cover.png optional for A1
    cover/thumb_square.png
  ...
wechat_bundle/
  wechat_bundle_manifest.json
  main_article.md
  attached_articles.json
  cover/
    main_900x383.png
    main_safe_square_383x383.png
    A2_thumb_500x500.png
    A3_thumb_500x500.png
    A4_thumb_500x500.png
    A5_thumb_500x500.png
publish/
  wechat_draft_report.json
  wechat_draft_report.md
  draft_payload.redacted.json
  wechat_article.html
  wechat_article.preview.html
orchestration_manifest.json
orchestration_report.md
```

## Phase 1: Selection

Call `china-longform-article-selection` explicitly with:

```json
{
  "target_date": "YYYY-MM-DD",
  "target_timezone": "Asia/Shanghai",
  "selection_mode": "china_viral",
  "requested_count": 5,
  "retrieval_gate": true,
  "preview_only": false
}
```

Hard requirements:

- Keep all five Top 5 candidates, not only the recommended best candidate.
- Every candidate must have `material_available=true`.
- Every candidate must have existing `capture_output_path`, `capture_manifest_path`, and `material_manifest_path`.
- For `legal_republication_success`, `legal_source_manifest_path` must exist.
- Do not ask the user to paste article text.
- Do not include candidates whose readable material is unavailable.

Copy or record selection outputs under this run's `selection/`.

## Phase 2: Standardize Five Article Packages

For each Top 5 candidate, create:

```text
articles/{candidate_id}_{slug}/source/article.txt
articles/{candidate_id}_{slug}/source/source_metadata.json
articles/{candidate_id}_{slug}/media/media_manifest.json
articles/{candidate_id}_{slug}/media/original/
```

`article.txt` must contain the captured article material only. Do not mix in Chinese summaries, scoring notes, or WeChat copy.

Media handling:

- Inspect the capture package and manifest for original article images, videos, captions, alt text, and media URLs.
- If a source image or video has a direct downloadable URL and can be fetched without login, CAPTCHA, paywall bypass, or private browser storage access, download it under `media/original/`.
- If media cannot be downloaded reliably, skip it. Do not leave player placeholders, loading messages, broken links, archive UI, or copied captions without media.
- Write `media/media_manifest.json` with `downloaded[]`, `skipped[]`, source URLs, local paths, captions, and skip reasons.
- Keep `source/article.txt` unchanged even if it contains noisy capture text; cleanup happens only in translation and WeChat formatting outputs.

`source_metadata.json` must include at least:

```json
{
  "candidate_id": "A1",
  "rank": 1,
  "score": 95,
  "publication": "Financial Times",
  "article_title": "English title",
  "article_title_zh": "中文标题",
  "author": "...",
  "published_date": "YYYY-MM-DD",
  "source_url": "https://...",
  "material_source_url": "https://...",
  "fulltext_status": "original_public_open | archive_capture_success | legal_republication_success",
  "capture_provider": "url-page-capture",
  "capture_method": "...",
  "capture_output_path": "...",
  "capture_manifest_path": "...",
  "material_manifest_path": "...",
  "media_manifest_path": "...",
  "legal_source_manifest_path": null,
  "target_date": "YYYY-MM-DD"
}
```

Gate: stop with `ARTICLE_PACKAGE_GATE_FAILED` if any of the five article packages is missing, too short, not the selected candidate, or points to missing manifests.

## Phase 3: Faithful Chinese Translation Drafts

Create one translation for each article:

```text
articles/{candidate_id}_{slug}/translation/translation.md
articles/{candidate_id}_{slug}/translation/translation_manifest.json
```

Translation rules:

- Preserve the original article's meaning, facts, order, paragraph structure, names, numbers, dates, quotes, and hedging.
- Do not add analysis, commentary, jokes, or background that is not in the article.
- Use natural written Chinese. Avoid literal translation that reads like English syntax.
- Translate titles and subheads naturally, but keep the original English title in metadata.
- Keep source `article.txt` unchanged; write translations separately. Do not rewrite, trim, normalize, or overwrite the original source file.
- If the source contains quoted speech, preserve quote attribution and tone.
- If a sentence is ambiguous, translate conservatively and record the ambiguity in `translation_manifest.json`.
- Do not paste full third-party source text in chat responses.
- Do not translate webpage chrome, media-player controls, chart UI labels, archive navigation, loading placeholders, share widgets, accessibility navigation, cookie prompts, subscription prompts, or analytics artifacts as article text.
- Remove capture noise such as `Show video info`, `Show video description`, `LOADING`, `Metric Web`, `All series are visible`, raw chart axis fragments, archive headers, and orphan image/video captions when the underlying media is not downloaded.
- Preserve real article paragraphs and real headings only.

`translation_manifest.json` fields:

```json
{
  "candidate_id": "A1",
  "translation_type": "faithful_full_translation_test",
  "workflow_mode": "internal_test",
  "source_article_sha256": "...",
  "translation_sha256": "...",
  "source_article_unchanged": true,
  "paragraph_count_source": 20,
  "paragraph_count_translation": 20,
  "paragraph_alignment": "same_order_best_effort",
  "capture_noise_removed": true,
  "media_manifest_path": "...",
  "style": "natural Chinese, faithful to source",
  "translator_notes": []
}
```

## Phase 4: WeChat Article Formatting

For each translated article, create:

```text
articles/{candidate_id}_{slug}/wechat/article.md
articles/{candidate_id}_{slug}/wechat/article_metadata.json
```

Formatting rules:

- Article body is the Chinese translation, not a video script and not a commentary essay.
- `wechat/article.md` and `wechat/reviewed_article.md` are semantic Markdown intermediates, not the final WeChat visual format.
- Do not encode visual styling in Markdown. Keep styling centralized in `/Users/wangfangjia/.codex/skills/wechat-article-publish-draft/references/wechat-article-style-spec.md`.
- Insert downloaded original images/videos at the closest relevant position in the article.
  - Images: use valid Markdown image syntax, e.g. `![中文图注](../media/original/name.jpg)`.
  - Videos: use Markdown-compatible HTML only when a local downloaded video exists, e.g. `<video controls src="../media/original/name.mp4"></video>`.
  - Put a short translated caption below media only when the source caption is meaningful and the media file exists.
  - If media download failed or no local media exists, omit that media and its caption entirely.
- Add a compact source note near the top or bottom:
  - Chinese source name
  - Original title
  - Original URL
  - Publication date
- Do not add "AI generated" claims unless required by the publishing account policy.
- Keep headings simple and WeChat-readable.
- The final WeChat Markdown must not contain capture noise or raw webpage controls. Fail the article with `WECHAT_ARTICLE_NOISE_GATE_FAILED` if any of these remain:
  - `显示视频信息`, `显示视频说明`, `加载中`, `Metric Web`, `所有序列均可见`
  - `Show video info`, `Show video description`, `LOADING`, `All series are visible`
  - orphan chart axis labels or units as standalone paragraphs
  - archive/search/navigation/share/accessibility/subscription UI text
  - orphan media captions when the corresponding media file is absent

`article_metadata.json` fields:

```json
{
  "candidate_id": "A1",
  "wechat_role": "main | attached",
  "title": "中文标题",
  "source_publication": "Financial Times",
  "original_title": "...",
  "original_url": "...",
  "cover_path": "...",
  "thumb_path": "...",
  "translation_path": "...",
  "media_manifest_path": "...",
  "downloaded_media_count": 0,
  "skipped_media_count": 0,
  "noise_gate_passed": true,
  "source_article_sha256": "...",
  "translation_sha256": "..."
}
```

## Phase 4b: WeChat Compliance Review

Read `/Users/wangfangjia/.codex/skills/wechat-article-compliance-review/SKILL.md`.

For each article after `wechat/article.md` is created and before cover, bundle, or publish, run:

```bash
python3 /Users/wangfangjia/.codex/skills/wechat-article-compliance-review/scripts/run_wechat_article_compliance_review.py \
  --article-dir articles/{candidate_id}_{slug}
```

Required outputs:

```text
articles/{candidate_id}_{slug}/wechat/reviewed_article.md
articles/{candidate_id}_{slug}/wechat/compliance_review_result.json
articles/{candidate_id}_{slug}/wechat/compliance_review_report.md
```

Rules:

- `reviewed_article.md` is the only article body allowed to enter bundle/publish.
- If deterministic review returns `FAIL`, perform minimum necessary editorial fixes or deletions, then rerun review.
- For high-risk China politics, Taiwan/Hong Kong, Xinjiang, ethnicity, religion, privacy, defamation, copyright/originality, or source-note issues, perform an explicit editorial context pass, not only keyword replacement.
- Do not claim translated foreign articles are original. Preserve source publication, original title, and original URL.
- Update `wechat/article_metadata.json` with `reviewed_article_path`, `compliance_review_result_path`, `compliance_review_report_path`, and `compliance_status`.

Gate: stop with `WECHAT_COMPLIANCE_GATE_FAILED` if any article lacks reviewed output or has status `FAIL`.

## Phase 4c: WeChat Style Contract

Read `/Users/wangfangjia/.codex/skills/wechat-article-publish-draft/references/wechat-article-style-spec.md`.

The final visual format is generated by the draft publishing renderer, not by raw Markdown. The format model is:

```text
wechat/reviewed_article.md
-> conservative inline-style HTML
-> draft/add articles[].content
```

Style requirements:

- Use `wechat-swiss-grid-v1`, adapted from the local PPT Master `swiss_grid` template.
- Visual system: white paper `#FFFFFF`, near-black ink `#1A1A1A`, Swiss red `#D9251D`, secondary gray `#666666`, divider gray `#E8E8E8`.
- Body text: 16px, line-height 1.78, color `#1A1A1A`, left aligned, no first-line indent.
- Lead paragraph: 18px, line-height 1.72, weight 700, used once per article.
- H2: 22px, weight 900, with a 3px top rule in `#D9251D`, margin `44px 0 18px`.
- H3: 17px, weight 900, with a 3px left rule in `#D9251D`, left padding 10px.
- Source note: compact metadata block with a left red rule, 12px, color `#666666`, white background.
- Body images: full content width, max-width 100%, height auto, left aligned, no radius.
- Captions: 12px muted gray, left aligned, only when alt text is meaningful.
- Use inline styles only; no JavaScript, iframes, external CSS, forms, gradients, shadows, rounded cards, or complex layout tricks.

Dry-run publishing must write both:

```text
publish/wechat_article.html
publish/wechat_article.preview.html
```

Review `wechat_article.preview.html` when tuning typography, title hierarchy, colors, image size, captions, spacing, and source-note treatment.

## Phase 5: Cover Images

Read `references/wechat-cover-spec.md` and `wechat-cover-image` before generating covers.

Default cover outputs:

- Main article cover: `900x383` or the nearest exact `2.35:1` image the image pipeline can generate, then crop/resize to `900x383`.
- Main safe-square preview: center crop `383x383`.
- Attached article thumbnails: `500x500` square images or center-cropped variants.

Image rules:

- Prefer no-text covers unless the user explicitly asks for text.
- Use the existing `wechat-cover-image` high-end magazine/editorial visual style.
- Add the `译见中国` palette as color direction: white/light base, near-black subject, restrained grays, and one controlled Swiss red `#D9251D` accent.
- Do not force covers to replicate Swiss grid, PPT diagrams, dashboards, or infographics.
- Do not ask image models to render Chinese or English title text.
- Keep the main article's important subject inside the center `383x383` safe square.
- Use the existing `wechat-cover-image` visual style unless the user specifies a different brand style.
- Store generation prompts and source article IDs in image manifests.

## Phase 6: Bundle Manifest

Create:

```text
wechat_bundle/wechat_bundle_manifest.json
wechat_bundle/main_article.md
wechat_bundle/attached_articles.json
```

Default layout:

```json
{
  "bundle_type": "wechat_multi_article",
  "main_article_id": "A1",
  "attached_article_ids": ["A2", "A3", "A4", "A5"],
  "selection_policy": "A1 is highest score; A2-A5 attached in ranked order",
  "workflow_mode": "translation_test",
  "publish_mode": "wechat_api_draft",
  "cover_spec": {
    "main_cover_ratio": "2.35:1",
    "main_cover_size_px": "900x383",
    "main_safe_square_px": "383x383",
    "attached_thumb_ratio": "1:1"
  },
  "articles": []
}
```

Use all five material-available candidates. Unless the user specifies another editorial rule, keep the highest-scoring candidate as the main article and attach the remaining four in ranked order.

Each `articles[]` entry must point to reviewed copy:

```json
{
  "candidate_id": "A1",
  "wechat_role": "main",
  "article_dir": ".../articles/A1_slug",
  "wechat_article_path": ".../articles/A1_slug/wechat/reviewed_article.md",
  "metadata_path": ".../articles/A1_slug/wechat/article_metadata.json",
  "cover_path": ".../articles/A1_slug/cover/main_cover.png",
  "thumb_path": ".../articles/A1_slug/cover/thumb_square_500x500.png",
  "compliance_status": "PASS"
}
```

## Phase 7: WeChat Draft Creation

Read `/Users/wangfangjia/.codex/skills/wechat-article-publish-draft/SKILL.md` and create a real WeChat draft-box draft from the bundle manifest.

Dry run first:

```bash
python3 /Users/wangfangjia/.codex/skills/wechat-article-publish-draft/scripts/publish_wechat_draft.py \
  --bundle-manifest wechat_bundle/wechat_bundle_manifest.json \
  --dry-run
```

If credentials are available and the user has requested draft creation:

```bash
WECHAT_APP_ID=... WECHAT_APP_SECRET=... \
python3 /Users/wangfangjia/.codex/skills/wechat-article-publish-draft/scripts/publish_wechat_draft.py \
  --bundle-manifest wechat_bundle/wechat_bundle_manifest.json \
  --live
```

Rules:

- This phase creates a draft only. It must not call `freepublish/submit`.
- This phase renders `wechat/reviewed_article.md` to styled inline HTML using `wechat-swiss-grid-v1`.
- Inspect `publish/wechat_article.preview.html` before live draft creation when visual quality matters.
- The publish script discovers the current public IP and records it in `publish/wechat_draft_report.json`.
- If WeChat returns an IP allowlist, credential, quota, or API-permission error, stop and report it. Do not fall back to browser clicking.
- The final report must include draft `media_id` when `draft_created=true`.

## Orchestration Manifest

Always write:

```text
orchestration_manifest.json
orchestration_report.md
```

Statuses:

```text
SELECTION_COMPLETE
TRANSLATIONS_COMPLETE
WECHAT_COMPLIANCE_GATE_FAILED
WECHAT_PACKAGE_READY
WECHAT_DRAFT_CREATED
COMPLETE
FAILED
```

Final report must include:

- Target date and run directory.
- Top 5 with score, source, title, capture path, manifest path.
- Main article and attached article IDs.
- Translation paths for all five.
- Cover paths and cover spec.
- Compliance review paths and statuses for all five.
- WeChat bundle manifest path.
- Publish draft report path and status.
- WeChat style version and preview HTML path.
- Any blocker, especially compliance failures or WeChat API errors.
