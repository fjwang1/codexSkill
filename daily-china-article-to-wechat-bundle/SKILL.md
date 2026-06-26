---
name: daily-china-article-to-wechat-bundle
description: "每日英文外刊深度长文到微信公众号图文包的总控 skill。Use when the user wants to reuse china-longform-article-selection in global_deep_longform mode to select up to 2 material-available, China-unrelated, high-quality longform articles; depth, length, originality, explanatory power, and Chinese-reader value are mandatory, while China relevance is a hard exclusion for this workflow. Run every selected article through the full WeChat production workflow: strict faithful full Chinese translation, post-translation fidelity review, a dedicated Chinese-reader optimization node for fluency/logic/structure/readability, WeChat formatting, final copy and technical packaging check, cover image, chapter illustrations, and draft-box publishing as one single- or two-article WeChat draft. Article-local stages for selected candidates may be executed in parallel."
---

# Daily Deep Longform Article To WeChat Bundle

This skill turns the existing article-selection workflow into a WeChat public-account article bundle. It does not make videos, audio, subtitles, or Bilibili drafts.

Pipeline:

```text
target_date
-> china-longform-article-selection material-gated Top 1-2 in global_deep_longform mode
-> standardize selected article packages
-> for each selected article, in parallel where possible:
   -> strict faithful full Chinese translation
   -> translation fidelity review: completeness/fidelity + baseline Chinese clarity
   -> Chinese-reader optimization: fluency + logic/structure + paragraph rhythm
   -> WeChat article formatting
   -> final copy and technical packaging check
   -> cover image
   -> chapter illustrations
-> bundle: one main article plus 0-1 attached articles, all fully produced
-> WeChat inline-HTML style rendering and preview for all selected articles
-> wechat-article-publish-draft API draft creation
```

## Dependencies

Read these skills before executing their stages:

1. `/Users/wangfangjia/.codex/skills/china-longform-article-selection/SKILL.md`
2. `/Users/wangfangjia/.codex/skills/url-page-capture/SKILL.md` when validating or repairing capture material
3. `/Users/wangfangjia/.codex/skills/wechat-cover-image/SKILL.md` for cover generation style
4. `/Users/wangfangjia/.codex/skills/wechat-article-illustrations/SKILL.md` for per-chapter article illustrations
5. `/Users/wangfangjia/.codex/skills/wechat-article-publish-draft/SKILL.md` and its `references/wechat-article-style-spec.md` for final inline-HTML rendering and draft-box API creation

For cover sizing details, read `references/wechat-cover-spec.md`.

## Parallel Execution Model

After Phase 2 creates the standardized article packages, run article-local stages independently for all selected candidates. These article-local chains may execute in parallel:

```text
A1..A{returned_count} each:
translation
-> translation fidelity review loop
-> Chinese-reader optimization loop
-> WeChat Markdown formatting
-> final copy and technical packaging check
-> cover generation
-> chapter illustration generation and insertion
```

Rules:

- Do not reserve the full workflow for A1 only. Every selected article A1..A{returned_count} must receive the same translation review, Chinese-reader optimization, cover generation, formatting, illustration generation, and final draft inclusion.
- Preserve per-article dependency order inside each chain. For example, do not generate chapter illustrations before `wechat/reviewed_article.md` exists.
- It is acceptable to use parallel subagents or parallel shell jobs for different articles when the required inputs are already present.
- Avoid parallel writes to shared files such as `wechat_bundle/wechat_bundle_manifest.json`, `orchestration_manifest.json`, and `publish/*`. Aggregate per-article outputs first, then write shared bundle/publish artifacts once.
- Run WeChat draft creation only after all selected article chains have passed gates. Treat draft creation as a final serial step because it creates one single- or multi-article WeChat draft.

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
/Volumes/GT34/daily_china_article_wechat/{target_date}_deep_longform/
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
    translation/reviewed_translation.md
    translation/translation_review_result.json
    translation/translation_review_report.md
    translation/chinese_reading_version.md
    translation/chinese_reading_optimization_result.json
    translation/chinese_reading_optimization_report.md
    wechat/article.md
    wechat/reviewed_article.md
    wechat/article_quality_check.json
    wechat/article_quality_check.md
    wechat/article_metadata.json
    illustrations/
      chapter_01_<slug>_source_2400x1600.png
      chapter_01_<slug>_wechat_2400x1600.jpg
      illustrations_manifest.json
    cover/main_cover.png
    cover/main_cover_source_2400x1021.png optional
    cover/safe_square_383x383.png
    cover/thumb_square_500x500.png
    cover/cover_manifest.json
  ...
wechat_bundle/
  wechat_bundle_manifest.json
  main_article.md
  attached_articles.json
  cover/
    main_900x383.png
    main_safe_square_383x383.png
    A1_main_900x383.png
    A1_thumb_500x500.png
    A2_main_900x383.png
    A2_thumb_500x500.png
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
  "selection_mode": "global_deep_longform",
  "requested_count": 2,
  "minimum_returned_count": 1,
  "retrieval_gate": true,
  "preview_only": false
}
```

Hard requirements:

- Keep all returned candidates, not only the recommended best candidate. Returned count may be 1-2.
- Do not force exactly two articles. Depth, length, quality, non-China relevance, and material availability outrank count.
- China relevance is a hard exclusion for this WeChat workflow. Returned candidates must be unrelated to China except for incidental background mentions that are not part of the article's thesis, narrative, conflict, evidence, or reader payoff.
- All publications in the fixed source whitelist declared by `china-longform-article-selection` are account-authorized for full Chinese translation and WeChat draft/publication in this workflow. Record source metadata for internal audit, but do not block production on source-name display requirements.
- Every candidate must have `material_available=true`.
- Every candidate must have existing `capture_output_path`, `capture_manifest_path`, and `material_manifest_path`.
- For `legal_republication_success`, `legal_source_manifest_path` must exist.
- Do not ask the user to paste article text.
- Do not include candidates whose readable material is unavailable.

Copy or record selection outputs under this run's `selection/`.

## Phase 2: Standardize Selected Article Packages

For each returned candidate, create:

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

Gate: stop with `ARTICLE_PACKAGE_GATE_FAILED` if any returned article package is missing, too short, not the selected candidate, or points to missing manifests.

## Phase 3: Faithful Full Chinese Translation Drafts

Create one translation for each article:

```text
articles/{candidate_id}_{slug}/translation/translation.md
articles/{candidate_id}_{slug}/translation/translation_manifest.json
```

Translation rules:

- This phase must produce a complete Chinese translation of every substantive source paragraph. Summaries, condensed renderings, excerpt translations, structural rewrites, or "best effort narrative" versions are failures.
- Preserve the original article's meaning, facts, order, paragraph structure, names, numbers, dates, quotes, and hedging.
- Preserve paragraph order and paragraph boundaries wherever possible. If capture-noise removal changes paragraph counts, record the removed paragraph ranges and reasons in `translation_manifest.json`.
- Do not add analysis, commentary, jokes, or background that is not in the article.
- Use natural written Chinese. Avoid literal translation that reads like English syntax.
- Translate subheads naturally, but keep the original English title in metadata.
- Generate the Chinese publish title as an editorial WeChat title, not a literal title translation. It may differ from the original title when that reads better in Chinese.
- Keep source `article.txt` unchanged; write translations separately. Do not rewrite, trim, normalize, or overwrite the original source file.
- If the source contains quoted speech, preserve quote attribution and tone.
- If a sentence is ambiguous, translate conservatively and record the ambiguity in `translation_manifest.json`.
- Do not paste full third-party source text in chat responses.
- Do not translate webpage chrome, media-player controls, chart UI labels, archive navigation, loading placeholders, share widgets, accessibility navigation, cookie prompts, subscription prompts, or analytics artifacts as article text.
- Remove capture noise such as `Show video info`, `Show video description`, `LOADING`, `Metric Web`, `All series are visible`, raw chart axis fragments, archive headers, and orphan image/video captions when the underlying media is not downloaded.
- Preserve real article paragraphs and real headings only.
- The words `condensed`, `summary`, `summarized`, `abridged`, `excerpt`, `structurally faithful rendering`, or equivalent Chinese terms such as `压缩`, `摘要`, `节译`, `摘译`, `改写` must not appear as the translation strategy in any manifest or report.
- Gate: stop with `FULL_TRANSLATION_GATE_FAILED` if any substantive source paragraph is missing, merged into an untraceable summary, materially shortened, or reordered.

`translation_manifest.json` fields:

```json
{
  "candidate_id": "A1",
  "translation_type": "faithful_full_translation",
  "workflow_mode": "internal_test",
  "source_article_sha256": "...",
  "translation_sha256": "...",
  "source_article_unchanged": true,
  "paragraph_count_source": 20,
  "paragraph_count_translation": 20,
  "paragraph_alignment": "strict_same_order",
  "substantive_paragraph_count_source": 20,
  "substantive_paragraph_count_translation": 20,
  "paragraph_coverage_status": "PASS",
  "removed_noise_paragraphs": [],
  "missing_or_condensed_paragraphs": [],
  "capture_noise_removed": true,
  "media_manifest_path": "...",
  "style": "natural Chinese, faithful to source",
  "translator_notes": []
}
```

## Phase 3b: Translation Fidelity Review

After every `translation/translation.md` is created, review it before Chinese-reader optimization or WeChat formatting begins.

This node has two mandatory checks:

1. Full-translation coverage and fidelity:
   - Every substantive source paragraph must be represented in the reviewed translation in the same order.
   - The review must compare source paragraph count, substantive paragraph count, heading count, quote coverage, names, numbers, dates, and key factual sequences against the translation.
   - Paragraph count may differ only for documented capture-noise removal or clearly justified heading normalization. It must not differ because the article was summarized or condensed.
   - If `paragraph_count_translation` is far lower than `paragraph_count_source`, or if any report/manifest says the translation is condensed, summarized, abridged, excerpted, or structurally faithful rather than full, mark the review `FAIL`.

2. Baseline Chinese clarity and terminology integrity:
   - The translation must be understandable in written Chinese before entering the dedicated optimization node.
   - Fix obvious mistranslations, broken references, inconsistent entity names, wrong dates/numbers, and title problems.
   - Major rhythm, paragraph-flow, and Chinese-reader structural improvements belong to Phase 3c, not this fidelity review.
   - Preserve the original facts, order, names, numbers, dates, quotes, hedging, and attribution.
   - Do not add commentary, analysis, jokes, or background not present in the source.
   - Review the title under the Chinese Title Policy.

Required outputs:

```text
articles/{candidate_id}_{slug}/translation/reviewed_translation.md
articles/{candidate_id}_{slug}/translation/translation_review_result.json
articles/{candidate_id}_{slug}/translation/translation_review_report.md
```

Review result schema:

```json
{
  "schema_version": "wechat-translation-review.v1",
  "candidate_id": "A1",
  "status": "PASS | NEEDS_REVISION | FAIL",
  "language_quality_status": "PASS | NEEDS_REVISION",
  "full_translation_status": "PASS | NEEDS_REVISION | FAIL",
  "source_article_sha256": "...",
  "translation_sha256_before": "...",
  "reviewed_translation_sha256": "...",
  "title_before": "...",
  "title_after": "...",
  "issues": [
    {
      "type": "coverage | language_quality | title | fidelity | terminology",
      "severity": "must_fix | should_fix",
      "location": "heading or paragraph number",
      "problem": "...",
      "action": "rewrite | preserve | verify"
    }
  ],
  "revision_count": 1
}
```

Loop requirement:

- If `full_translation_status` or `language_quality_status` is not `PASS`, revise `translation/translation.md` or create a corrected `reviewed_translation.md`, then rerun this Phase 3b review.
- Repeat until both statuses are `PASS`.
- Stop with `TRANSLATION_REVIEW_GATE_FAILED` if the article cannot be made complete, faithful, and basically readable without materially changing the source.
- Phase 3c must use `translation/reviewed_translation.md`, not the raw `translation/translation.md`.
- Record every material rewrite in `translation_review_report.md`; do not silently change facts.

## Phase 3c: Chinese Reader Optimization

After `translation/reviewed_translation.md` passes Phase 3b, create a Chinese-reader-facing version:

```text
articles/{candidate_id}_{slug}/translation/chinese_reading_version.md
articles/{candidate_id}_{slug}/translation/chinese_reading_optimization_result.json
articles/{candidate_id}_{slug}/translation/chinese_reading_optimization_report.md
```

Purpose:

- Turn the faithful translation draft into a polished longform article that reads naturally to Chinese readers.
- Optimize fluency, paragraph rhythm, logical transitions, section structure, subheads, and narrative clarity.
- Keep the source's facts, claims, evidence, chronology, quotations, hedging, attribution, and overall argument intact.
- Preserve full coverage. This node is not a summary, rewrite, commentary essay, or condensed adaptation.

Allowed edits:

- Split overlong Chinese paragraphs, merge tiny adjacent fragments, and move sentence breaks so the pacing fits Chinese longform reading.
- Reorder clauses inside a sentence or within adjacent paragraphs when English syntax or article structure becomes confusing in Chinese.
- Add or rename H2/H3 subheads when they make the article easier to scan, as long as the subhead accurately reflects the nearby source material.
- Add neutral Chinese connective words such as `同时`, `然而`, `因此`, `换句话说`, or `更重要的是` only when they make an already-present logical relationship explicit.
- Replace literal translationese with idiomatic Chinese while preserving meaning and attribution.

Forbidden edits:

- Do not delete substantive information, quotes, caveats, numbers, named entities, dates, or counterarguments.
- Do not add external background, analysis, opinion, examples, facts, or causal claims that are not in the source.
- Do not move whole sections or change narrative chronology unless the optimization report explicitly marks a local structural repair and proves that the source meaning is unchanged.
- Do not make weak source claims sound certain, anonymous claims sound verified, or attributed claims sound like the publication's own conclusion.
- Do not add visible source notes, original-title blocks, URLs, or publication prefixes.

Required quality checks:

1. Readability:
   - The article should read as polished Chinese nonfiction, not line-by-line translated English.
   - Remove translationese, stiff calques, ambiguous pronouns, broken transitions, repeated subject names, and awkward noun piles.

2. Structure:
   - The lead, section breaks, subheads, and paragraph order should help Chinese readers follow the article's core tension, evidence chain, and conclusion.
   - Long English setup passages may be made more direct in Chinese, but no information may be lost.

3. Fidelity and coverage:
   - Compare the optimized version against `translation/reviewed_translation.md`.
   - Confirm every substantive point remains present.
   - Record all non-trivial paragraph splits, merges, subhead additions, and local reorderings.

Optimization result schema:

```json
{
  "schema_version": "wechat-chinese-reading-optimization.v1",
  "candidate_id": "A1",
  "status": "PASS | NEEDS_REVISION | FAIL",
  "readability_status": "PASS | NEEDS_REVISION",
  "structure_status": "PASS | NEEDS_REVISION",
  "fidelity_status": "PASS | NEEDS_REVISION | FAIL",
  "coverage_status": "PASS | NEEDS_REVISION | FAIL",
  "reviewed_translation_sha256": "...",
  "chinese_reading_version_sha256": "...",
  "title_before": "...",
  "title_after": "...",
  "paragraph_strategy": "split_merge_adjacent_paragraphs_allowed",
  "structural_changes": [
    {
      "type": "split | merge | subhead_added | transition_rephrased | local_reorder | title_polish",
      "location": "heading or paragraph number",
      "source_range": "reviewed translation paragraph range",
      "output_range": "optimized version paragraph range",
      "rationale": "..."
    }
  ],
  "forbidden_changes_found": [],
  "revision_count": 1
}
```

Loop requirement:

- If `readability_status`, `structure_status`, `fidelity_status`, or `coverage_status` is not `PASS`, revise `translation/chinese_reading_version.md`, then rerun this Phase 3c review.
- Repeat until all statuses are `PASS`.
- Stop with `CHINESE_READING_OPTIMIZATION_GATE_FAILED` if the article cannot be made fluent and structurally readable in Chinese without adding, deleting, or distorting source material.
- Later phases must use `translation/chinese_reading_version.md`, not `translation/reviewed_translation.md` or raw `translation/translation.md`.

## Chinese Title Policy

Use this policy for `source_metadata.article_title_zh`, the H1 in `translation/translation.md`, `translation/reviewed_translation.md`, `translation/chinese_reading_version.md`, `wechat/article.md`, `wechat/reviewed_article.md`, `wechat/article_metadata.json.title`, and `wechat_bundle_manifest.json.articles[].title`.

Rules:

- Treat the Chinese title as a publishable headline for a WeChat public-account article, not as a loyalty test against the English title.
- Prefer natural Chinese expression, clear stakes, and a compact hook. The title should sound like something a careful Chinese editor would write.
- Keep it accurate to the article's core claim. Do not add facts, claims, blame, causality, or certainty that the source does not support.
- Target 14-24 Chinese characters when possible; never exceed WeChat's 32-character title limit.
- Use a concrete subject plus tension, consequence, or action when helpful: e.g. `中国押注机器人，对冲人口下滑`.
- Avoid stiff English calques such as `机器人国家`, `X的赌注`, `中国的竞标`, `X之战`, or noun piles that only make sense when back-translated.
- Avoid sensational or clickbait wording: `震惊`, `炸裂`, `崩了`, `完了`, `惊天`, `内幕曝光`, `全网疯传`, `彻底摊牌`.
- Avoid unnecessary current Chinese national leader names in titles.
- Preserve the original English title and source publication separately in metadata and audit reports. Do not put source attribution in the WeChat-facing title.
- After Phase 3c optimization or manual title polishing, synchronize the final chosen title across H1, metadata, bundle manifest, and publish preview.

## Source Authorization And Attribution Display Policy

Authorization basis:

```text
account_authorized_source_whitelist
```

The account has obtained authorization for the fixed source whitelist declared by `/Users/wangfangjia/.codex/skills/china-longform-article-selection/SKILL.md` to produce full Chinese translations and WeChat drafts/publications. Treat that whitelist-level authorization as sufficient for this workflow.

WeChat-facing display rules:

- Final article titles must not contain source publication prefixes. Do not use `<中文来源名>：<标题主体>`, `The Economist: ...`, `经济学人：...`, or any equivalent source-prefix format.
- The H1 in `translation/translation.md`, `translation/reviewed_translation.md`, `translation/chinese_reading_version.md`, `wechat/article.md`, `wechat/reviewed_article.md`, `wechat/article_metadata.json.title`, `wechat_bundle_manifest.json.articles[].title`, and the final WeChat `draft/add` payload title must use the editorial Chinese title only.
- Do not add a visible source declaration, source note, "本文来自...", "编译自...", original-title block, or URL block at the beginning or end of the WeChat article body.
- Do not claim translated foreign articles are original. Preserve `source_publication`, `original_title`, `original_url`, `published_date`, and `authorization_basis` in metadata, manifests, audit reports, and redacted payloads where appropriate.
- Missing Chinese source-name mapping is never a blocker for title generation or draft creation. `source_publication_zh` may be omitted or used only as non-facing internal metadata.
- If a title contains a colon for editorial reasons, the text before the colon must be part of the headline itself, not the source publication.

## Phase 4: WeChat Article Formatting

For each translated article, create:

```text
articles/{candidate_id}_{slug}/wechat/article.md
articles/{candidate_id}_{slug}/wechat/article_metadata.json
```

Formatting rules:

- Article body is the Chinese-reader optimized version from `translation/chinese_reading_version.md`, not the raw translation, not only the fidelity-reviewed translation, not a video script, and not a commentary essay.
- Do not proceed if `translation/translation_review_result.json` is missing or `full_translation_status` / `language_quality_status` is not `PASS`.
- Do not proceed if `translation/chinese_reading_optimization_result.json` is missing or `readability_status`, `structure_status`, `fidelity_status`, or `coverage_status` is not `PASS`.
- `wechat/article.md` and `wechat/reviewed_article.md` are semantic Markdown intermediates, not the final WeChat visual format.
- Do not encode visual styling in Markdown. Keep styling centralized in `/Users/wangfangjia/.codex/skills/wechat-article-publish-draft/references/wechat-article-style-spec.md`.
- Insert downloaded original images/videos at the closest relevant position in the article.
  - Images: use valid Markdown image syntax, e.g. `![中文图注](../media/original/name.jpg)`.
  - Videos: use Markdown-compatible HTML only when a local downloaded video exists, e.g. `<video controls src="../media/original/name.mp4"></video>`.
  - Put a short translated caption below media only when the source caption is meaningful and the media file exists.
  - If media download failed or no local media exists, omit that media and its caption entirely.
- Do not add a visible source note near the top or bottom. Source publication, original title, original URL, publication date, and authorization basis belong in metadata and reports, not in the WeChat-facing article body.
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
  "source_publication_zh": "金融时报",
  "original_title": "...",
  "original_url": "...",
  "cover_path": "...",
  "thumb_path": "...",
  "translation_path": "...",
  "reviewed_translation_path": "...",
  "translation_review_result_path": "...",
  "translation_review_report_path": "...",
  "chinese_reading_version_path": "...",
  "chinese_reading_optimization_result_path": "...",
  "chinese_reading_optimization_report_path": "...",
  "translation_full_translation_status": "PASS",
  "translation_language_quality_status": "PASS",
  "chinese_reading_readability_status": "PASS",
  "chinese_reading_structure_status": "PASS",
  "chinese_reading_fidelity_status": "PASS",
  "chinese_reading_coverage_status": "PASS",
  "reviewed_article_path": "...",
  "article_quality_check_path": "...",
  "article_quality_check_report_path": "...",
  "article_quality_status": "PASS",
  "media_manifest_path": "...",
  "downloaded_media_count": 0,
  "skipped_media_count": 0,
  "noise_gate_passed": true,
  "source_article_sha256": "...",
  "translation_sha256": "..."
}
```

## Phase 4b: Final Copy And Technical Packaging Check

For each article after `wechat/article.md` is created and before cover, bundle, or publish, run a final editor read-through and technical packaging check.

Required outputs:

```text
articles/{candidate_id}_{slug}/wechat/reviewed_article.md
articles/{candidate_id}_{slug}/wechat/article_quality_check.json
articles/{candidate_id}_{slug}/wechat/article_quality_check.md
```

Rules:

- This phase does not replace Phase 3b or Phase 3c. It catches issues introduced by Markdown packaging, media captions, title synchronization, source-display handling, image paths, and final publishable copy assembly.
- `reviewed_article.md` is the only article body allowed to enter bundle/publish.
- Read the full article as a Chinese editor. Fix remaining awkward transitions, paragraph rhythm problems, unclear references, duplicated words, broken punctuation, and headline/subhead mismatches.
- Do not run policy keyword screening for this China-unrelated workflow. Do not soften, delete, or skip material because of old topic categories. If the WeChat API itself rejects a draft, stop and report the API error.
- Preserve every substantive source fact, quote, date, number, attribution, caveat, and counterargument already carried through Phase 3c.
- Review the title against the Chinese Title Policy. Rewrite hard translations or awkward headline fragments even when the body reads cleanly.
- Do not claim translated foreign articles are original. Preserve source publication, original title, original URL, and authorization basis in metadata/reports, not as visible article-body source notes.
- Verify that the final article body contains no visible source declaration, original-title block, URL block, source-prefix headline, capture noise, broken Markdown image path, orphan media caption, raw webpage control text, or inline visual styling.
- Update `wechat/article_metadata.json` with `reviewed_article_path`, `article_quality_check_path`, `article_quality_check_report_path`, `article_quality_status`, and the final synchronized `title`.

Quality check schema:

```json
{
  "schema_version": "wechat-article-quality-check.v1",
  "candidate_id": "A1",
  "status": "PASS | NEEDS_REVISION | FAIL",
  "readability_status": "PASS | NEEDS_REVISION",
  "structure_status": "PASS | NEEDS_REVISION",
  "source_display_status": "PASS | NEEDS_REVISION | FAIL",
  "noise_status": "PASS | NEEDS_REVISION | FAIL",
  "markdown_media_status": "PASS | NEEDS_REVISION | FAIL",
  "reviewed_article_sha256": "...",
  "issues": [
    {
      "type": "readability | structure | source_display | noise | markdown_media | title",
      "severity": "must_fix | should_fix",
      "location": "heading or paragraph number",
      "problem": "...",
      "action": "rewrite | delete_noise | fix_path | preserve"
    }
  ],
  "revision_count": 1
}
```

Gate: stop with `ARTICLE_QUALITY_GATE_FAILED` if any article lacks reviewed output or has `status` set to `FAIL`.

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
- Source note: do not render by default. Source metadata remains in JSON/reports unless the user explicitly asks for visible attribution in the article body.
- Body images: full content width, max-width 100%, height auto, left aligned, no radius.
- Captions: 12px muted gray, left aligned, only when alt text is meaningful.
- Use inline styles only; no JavaScript, iframes, external CSS, forms, gradients, shadows, rounded cards, or complex layout tricks.

Dry-run publishing must write both:

```text
publish/wechat_article.html
publish/wechat_article.preview.html
```

Review `wechat_article.preview.html` when tuning typography, title hierarchy, colors, image size, captions, spacing, and source metadata omission.

## Phase 5: Cover Images

Read `references/wechat-cover-spec.md` and `wechat-cover-image` before generating covers.

Default cover outputs for each selected article:

```text
articles/{candidate_id}_{slug}/cover/
  main_cover.png
  main_cover_source_2400x1021.png optional but preferred
  safe_square_383x383.png
  thumb_square_500x500.png
  cover_manifest.json
```

Rules:

- Generate a full no-text cover for every selected article A1..A{returned_count}. Do not generate only A1's cover when attached articles exist.
- `main_cover.png`: `900x383` or the nearest exact `2.35:1` image the image pipeline can generate, then crop/resize to `900x383`.
- Preserve a 2K+ source/master cover image when available, preferably at least `2400px` wide.
- `safe_square_383x383`: center crop for preview and safety checking.
- `thumb_square_500x500`: center-cropped square image for local safety preview, archive, and editor-side visual checks.
- In the final WeChat multi-article draft, every article's API `thumb_media_id` upload must use the `2.35:1` `main_cover.png`/`main_cover.jpg` via `wechat_upload_cover_path` or `cover_path`. WeChat `draft/add` validates cover dimensions for attached articles too; do not upload `thumb_square_500x500.png` as the API `thumb_media_id`.
- Still keep every article's full `main_cover` for archive, preview, single-article reuse, and WeChat API upload.

Image rules:

- Prefer no-text covers unless the user explicitly asks for text.
- Use the existing `wechat-cover-image` New Yorker-inspired conceptual editorial cover style: one strong metaphor, generous negative space, quiet visual storytelling, restrained premium composition.
- Add the `他山译读` palette as color direction: white/light base, near-black subject, restrained grays, and one controlled Swiss red `#D9251D` accent.
- Do not force covers to replicate Swiss grid, PPT diagrams, dashboards, or infographics.
- Do not ask image models to render Chinese or English title text.
- Keep the main article's important subject inside the center `383x383` safe square.
- Use the existing `wechat-cover-image` visual style unless the user specifies a different brand style.
- Store generation prompts and source article IDs in image manifests.

## Phase 5b: Chapter Illustrations

Read `/Users/wangfangjia/.codex/skills/wechat-article-illustrations/SKILL.md`.

For every selected article A1..A{returned_count}, generate one body illustration per H2 chapter after that article's `wechat/reviewed_article.md` exists. Do not skip attached articles.

Default outputs:

```text
articles/{candidate_id}_{slug}/illustrations/
  chapter_01_<slug>_source_2400x1600.png
  chapter_01_<slug>_wechat_2400x1600.jpg
  chapter_02_<slug>_source_2400x1600.png
  chapter_02_<slug>_wechat_2400x1600.jpg
  illustrations_manifest.json
```

Rules:

- Generate illustrations for every selected article. If an article has no H2 chapters, create one body illustration after the lead section and record `fallback_single_illustration=true` in `illustrations_manifest.json`.
- Use only the content of the current H2 chapter when prompting each illustration.
- Do not feed the whole article to every illustration prompt.
- Use the same New Yorker-inspired conceptual editorial style as `wechat-cover-image`.
- Use the `他山译读` palette: white/light base, near-black subject, restrained grays, and one controlled Swiss red `#D9251D` accent.
- Body illustration ratio: `3:2` horizontal.
- Keep high-resolution source/master images at `2400x1600` or larger.
- Use optimized `*_wechat_2400x1600.jpg` images for Markdown insertion.
- Insert the image immediately after its H2 heading in `wechat/reviewed_article.md` with alt text `插图`.
- Do not add visible captions unless the user explicitly asks for captions.
- Stop with `WECHAT_ILLUSTRATION_GATE_FAILED` if an inserted image is missing, below 2400px wide, has visible text/pseudo-text, or repeats the same metaphor as another chapter.

## Phase 6: Bundle Manifest

Create:

```text
wechat_bundle/wechat_bundle_manifest.json
wechat_bundle/main_article.md
wechat_bundle/attached_articles.json
```

Hard rule:

- This skill publishes one WeChat draft every time. If returned_count=1, it is a single-article draft. If returned_count>1, it is a multi-article draft.
- The article with the highest score from `china-longform-article-selection` is the main article (`wechat_role: "main"`). The remaining selected articles, if any, are attached/sub articles (`wechat_role: "attached"`) in descending selection-score order.
- A1 is the main article and A2..A{returned_count} are attached articles.

Default layout:

```json
{
  "bundle_type": "wechat_multi_article",
  "main_article_id": "A1",
  "attached_article_ids": ["A2", "..."],
  "selection_policy": "A1 is highest score; A2..A{returned_count} attached in ranked order when present",
  "workflow_mode": "translation_test",
  "publish_mode": "wechat_api_draft",
  "cover_spec": {
    "main_cover_ratio": "2.35:1",
    "main_cover_size_px": "900x383",
    "main_safe_square_px": "383x383",
    "wechat_api_cover_ratio": "2.35:1",
    "attached_square_preview_thumb_ratio": "1:1"
  },
  "articles": []
}
```

Use every returned material-available candidate. Unless the user specifies another editorial rule, keep the highest-scoring candidate as the main article and attach the remaining returned candidates in ranked order. Every returned candidate must have passed translation review, Chinese-reader optimization, final copy and technical packaging check, cover generation, article formatting, and illustration generation before the bundle manifest is written.

Each `articles[]` entry must point to reviewed copy:

```json
{
  "candidate_id": "A1",
  "wechat_role": "main",
  "article_dir": ".../articles/A1_slug",
  "wechat_article_path": ".../articles/A1_slug/wechat/reviewed_article.md",
  "metadata_path": ".../articles/A1_slug/wechat/article_metadata.json",
  "reviewed_translation_path": ".../articles/A1_slug/translation/reviewed_translation.md",
  "translation_review_result_path": ".../articles/A1_slug/translation/translation_review_result.json",
  "chinese_reading_version_path": ".../articles/A1_slug/translation/chinese_reading_version.md",
  "chinese_reading_optimization_result_path": ".../articles/A1_slug/translation/chinese_reading_optimization_result.json",
  "article_quality_check_path": ".../articles/A1_slug/wechat/article_quality_check.json",
  "source_publication_zh": "金融时报",
  "authorization_basis": "account_authorized_source_whitelist",
  "cover_path": ".../articles/A1_slug/cover/main_cover.png",
  "wechat_upload_cover_path": ".../articles/A1_slug/cover/main_cover.png",
  "thumb_path": ".../articles/A1_slug/cover/thumb_square_500x500.png",
  "cover_manifest_path": ".../articles/A1_slug/cover/cover_manifest.json",
  "illustrations_manifest_path": ".../articles/A1_slug/illustrations/illustrations_manifest.json",
  "translation_language_quality_status": "PASS",
  "translation_full_translation_status": "PASS",
  "chinese_reading_readability_status": "PASS",
  "chinese_reading_structure_status": "PASS",
  "chinese_reading_fidelity_status": "PASS",
  "chinese_reading_coverage_status": "PASS",
  "article_quality_status": "PASS",
  "illustration_count": 3
}
```

## Phase 7: WeChat Draft Creation

Read `/Users/wangfangjia/.codex/skills/wechat-article-publish-draft/SKILL.md` and create one real WeChat draft-box draft from the bundle manifest. The draft must include every reviewed and fully produced selected article.

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
- Do not create the draft until all selected article chains have passed translation review, Chinese-reader optimization, final copy and technical packaging check, cover generation, formatting, and illustration gates.
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
TRANSLATION_REVIEW_GATE_FAILED
TRANSLATION_REVIEW_COMPLETE
CHINESE_READING_OPTIMIZATION_GATE_FAILED
CHINESE_READING_OPTIMIZATION_COMPLETE
ARTICLE_QUALITY_GATE_FAILED
ARTICLE_FULL_WORKFLOW_COMPLETE
WECHAT_PACKAGE_READY
WECHAT_DRAFT_CREATED
COMPLETE
FAILED
```

Final report must include:

- Target date and run directory.
- Returned selection candidates A1..A{returned_count} with score, source, title, capture path, manifest path.
- Main article and attached article IDs.
- Translation paths for all selected articles.
- Translation review paths and full-translation/language statuses for all selected articles.
- Chinese-reader optimization paths and readability/structure/fidelity/coverage statuses for all selected articles.
- Final article quality check paths and statuses for all selected articles.
- Cover paths, cover manifests, and cover spec for all selected articles.
- Illustration manifest paths and illustration counts for all selected articles.
- WeChat bundle manifest path.
- Publish draft report path and status.
- WeChat style version and preview HTML path.
- Any blocker, especially translation coverage failures, Chinese readability failures, article quality gate failures, or WeChat API errors.
