---
name: daily-china-article-to-wechat-bundle
description: "每日世界现象解释型英文长文到微信公众号图文包的总控 skill。Use when the user wants to reuse china-longform-article-selection in world_explainer_longform mode to select up to 2 material-available, China-unrelated longform articles that explain what happened in a country/region, why it happened, who is affected, and why Chinese readers should still care. Social-science explanatory power, country/region anchor, institutional/social mechanism, broad audience value, and evergreen relevance are core requirements; China relevance is a hard exclusion. Run every selected article through the full WeChat production workflow: strict faithful full Chinese translation as an audit base, translation fidelity review, China-perspective full adaptation that reads like a Chinese observer explaining the foreign phenomenon, 90%+ substantive coverage/fidelity gate, independent local-Chinese-reader subagent review loop, WeChat formatting, final copy and technical packaging check, cover image, inline article lead/head image, chapter illustrations, and draft-box publishing as one single- or two-article WeChat draft. Article-local stages for selected candidates may be executed in parallel."
---

# Daily World Explainer Article To WeChat Bundle

This skill turns the existing article-selection workflow into a WeChat public-account article bundle. It does not make videos, audio, subtitles, or Bilibili drafts.

Pipeline:

```text
target_date / run_date
-> china-longform-article-selection material-gated Top 1-2 in world_explainer_longform mode
-> standardize selected article packages
-> for each selected article, in parallel where possible:
   -> strict faithful full Chinese translation as audit base
   -> translation fidelity review: completeness/fidelity + baseline Chinese clarity
   -> China-perspective adaptation plan
   -> China-perspective full adaptation: a Chinese observer explains the foreign phenomenon
   -> 90%+ substantive coverage/fidelity gate
   -> local Chinese reader review loop: independent subagent checks comprehension, China-perspective naturalness, and no fabricated reporting
   -> WeChat article formatting
   -> final copy and technical packaging check
   -> cover image
   -> inline lead/head image
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
-> China-perspective full-adaptation loop
-> 90%+ coverage/fidelity review loop
-> local Chinese reader review loop
-> WeChat Markdown formatting
-> final copy and technical packaging check
-> cover generation
-> inline lead/head image generation and insertion
-> chapter illustration generation and insertion
```

Rules:

- Do not reserve the full workflow for A1 only. Every selected article A1..A{returned_count} must receive the same translation review, China-perspective full adaptation, 90%+ coverage/fidelity gate, local Chinese reader review, cover generation, inline lead/head image generation, chapter illustration generation, formatting, and final draft inclusion.
- Preserve per-article dependency order inside each chain. For example, do not generate chapter illustrations before `wechat/reviewed_article.md` exists.
- It is acceptable to use parallel subagents or parallel shell jobs for different articles when the required inputs are already present.
- Avoid parallel writes to shared files such as `wechat_bundle/wechat_bundle_manifest.json`, `orchestration_manifest.json`, and `publish/*`. Aggregate per-article outputs first, then write shared bundle/publish artifacts once.
- Run WeChat draft creation only after all selected article chains have passed gates. Treat draft creation as a final serial step because it creates one single- or multi-article WeChat draft.

## Progress Checkpoints And Stall Recovery

This workflow is long and may run unattended. It must never spend a long time in search, capture, translation, image generation, or publishing without leaving a current checkpoint in the run directory.

Before starting Phase 1, create:

```text
orchestration_progress.json
```

Update it after every meaningful stage and at least once after each candidate capture attempt, article-local phase, image generation batch, dry-run, and live draft attempt. The file must include:

```json
{
  "schema_version": "wechat-orchestration-progress.v1",
  "target_date": "YYYY-MM-DD",
  "run_dir": "...",
  "current_phase": "selection | packaging | translation | adaptation | coverage_review | reader_review | formatting | images | bundle | dry_run | live_draft | complete | blocked",
  "heartbeat_at": "ISO-8601",
  "completed_phases": [],
  "material_available_candidate_count": 0,
  "selected_candidate_ids": [],
  "last_completed_action": "...",
  "next_action": "...",
  "blocker": null
}
```

Selection stall recovery:

- If Phase 1 has already captured at least `minimum_returned_count` material-available, production-whitelist, China-unrelated, world-explainer-quality candidates, do not keep broadening search indefinitely in search of a marginally better candidate.
- If `requested_count=2` and two hard-gate-passing candidates are already material-available, immediately write `selection/source-shortlist.json`, `selection/ranked-top5.json`, `selection/selection-decision.json`, and `selection/selection-result.md`, then proceed to Phase 2.
- If only one hard-gate-passing candidate is material-available and the workflow does not explicitly require exactly two, proceed with a single-article draft rather than continuing open-ended search.
- If the run has capture files under `selection/captures/` but no `source-shortlist.json` or `ranked-top5.json`, the next agent resuming the run must first inspect those captures and either complete selection outputs from them or write `selection/selection-stall-report.json` explaining why they are insufficient.
- If a web search, archive search, or capture attempt is repeatedly blocked, do not leave the run silent. Write `selection/selection-stall-report.json`, mark the relevant source `SOURCE_FAILED` or candidate `retrieval_unavailable`, and continue with any already-qualified candidates when `minimum_returned_count` is satisfied.

Subagent status rule:

- A subagent executing this workflow must not ignore status requests while doing long-running work. At the next safe checkpoint, it must report `current_phase`, candidate IDs/titles being processed, latest artifact paths, and any blocker, then continue unless explicitly told to stop.
- For delegated execution, split the workflow into bounded resumable stages when possible: `selection_recovery`, `article_package`, `faithful_translation`, `china_perspective_adaptation`, `wechat_text_packaging`, `images`, `publish`.
- Every delegated stage must create its target directory and write a small progress JSON before reading long source files, generating long prose, running network calls, or reading secondary references. For article-local stages, write `articles/{candidate_id}_{slug}/article_progress.json` first.
- In delegated worker prompts, the first action must be progress creation/update only. The worker must not read the source article, read long skill files, inspect manifests, or plan prose before that first progress write. This is a hard operability requirement for unattended automation.
- If a delegated stage cannot write its progress JSON within 5 minutes, it must stop and report `PROGRESS_CHECKPOINT_NOT_WRITTEN` rather than continuing invisibly.
- A subagent may rely on a concise stage-specific contract from the orchestrator plus the required excerpts already read by the orchestrator; it does not need to reread every long reference file before writing the initial progress checkpoint. It must still read the directly relevant skill sections before producing final stage artifacts.
- Do not delegate the whole China-perspective article rewrite as one monolithic task. Long-prose adaptation must be split into bounded sub-stages:
  1. `adaptation_title_strategy`: choose final China-perspective title, title anchors, explainer frame, and title rationale.
  2. `adaptation_plan`: write plan JSON/MD using the approved title strategy.
  3. `adaptation_structure`: choose H2/H3 outline, opening stance, and source-unit map.
  4. `adaptation_chapter_rewrite`: rewrite one H2 chapter at a time, preserving source units assigned to that chapter.
  5. `adaptation_assembly`: assemble chapters into `china_perspective_version.md`, verify no source note or original-reporting claim.
  6. `coverage_review`: compute and write the 90% coverage/fidelity gate.
  7. `wechat_text_packaging`: write WeChat Markdown, metadata, and article quality check.
- If `adaptation_plan` has no new output within 90 seconds after the initial progress checkpoint, split it smaller and run only `adaptation_title_strategy` first. Write `translation/china_perspective_title_strategy.json` before any full plan or long outline.
- Each `adaptation_chapter_rewrite` sub-stage must write its partial output under `translation/china_perspective_chapters/` before moving to the next chapter. This makes the long rewrite resumable and auditable.
- After every key artifact write, update the relevant progress JSON immediately. For article-local stages this means updating `article_progress.json` after writing each of: adaptation plan JSON, adaptation plan MD, structure JSON, each chapter rewrite, assembled version, coverage result, local reader review, WeChat article, metadata, and quality check. Do not wait until the end of a multi-file stage to update progress.
- The orchestrator must check a delegated stage within 60-90 seconds for the expected progress file or first output. If there is no progress, close that worker and split the stage smaller instead of waiting indefinitely.

## Date And Output Root

Default run date:

```text
target_date = Asia/Shanghai today unless the automation/user explicitly wants a named run date
```

If the user specifies a date, resolve it to absolute `YYYY-MM-DD`. In `world_explainer_longform`, this is the run/audit date and output directory date, not an article-publication hard gate.

Before disk-heavy work, verify `/Volumes/GT34` is mounted and writable.

Dedicated artifact root for this skill:

```text
/Volumes/GT34/daily_china_article_wechat/
```

Place all WeChat bundle run outputs under this root. Do not use ad-hoc sibling directories for this skill's standard artifacts.

## Explicit User Overrides

Respect explicit workflow overrides from the user even when they are stricter than the default bundle policy.

Examples:

- If the user explicitly requires `两篇文章` or equivalent, treat the target bundle size as exactly 2 unless there is a true hard blocker such as no second China-unrelated, material-available, world-explainer-quality article. A weaker editorial-fit preference is not enough to drop the second article silently.
- If the user explicitly requires `瑞士风格`, apply that requirement consistently across WeChat layout/preview, covers, chapter illustrations, and chapter structure.
- If the user explicitly requires chaptered reading structure, then articles without usable original subheads must be rewritten into semantic `##` sections before illustration generation and before dry-run preview review.

Run directory:

```text
/Volumes/GT34/daily_china_article_wechat/{target_date}_world_explainer/
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
    translation/china_perspective_adaptation_plan.json
    translation/china_perspective_adaptation_plan.md
    translation/china_perspective_version.md
    translation/china_perspective_adaptation_result.json
    translation/china_perspective_adaptation_report.md
    translation/china_perspective_coverage_result.json
    translation/china_perspective_coverage_report.md
    translation/local_reader_review_result.json
    translation/local_reader_review_report.md
    translation/local_reader_review_rounds/ optional round reports
    wechat/article.md
    wechat/reviewed_article.md
    wechat/article_quality_check.json
    wechat/article_quality_check.md
    wechat/article_metadata.json
    illustrations/
      lead_00_<slug>_source_2400x1600.png
      lead_00_<slug>_wechat_2400x1600.jpg
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
  "selection_mode": "world_explainer_longform",
  "requested_count": 2,
  "minimum_returned_count": 1,
  "retrieval_gate": true,
  "preview_only": false,
  "fresh_lookback_days": 30,
  "recent_lookback_years": 2,
  "evergreen_allowed": true,
  "same_day_required": false,
  "publication_date_required": false,
  "max_candidate_pool": 30,
  "max_retrieval_gate_candidates": 8,
  "staleness_check_required": true
}
```

For generic non-exact-two runs, `minimum_returned_count` is 1. For any explicit `两篇文章` request, raise it to 2 and stop before draft creation if two qualified articles cannot be returned.

Hard requirements:

- Keep all returned candidates, not only the recommended best candidate. Default returned count may be 1-2.
- Preserve the selection skill's scoring fields for every returned candidate: `world_explainer_score`, `score`, `topical_momentum_score`, `topical_momentum_confidence`, `topical_momentum_window`, `topical_momentum_evidence`, `topical_momentum_reason`, `topical_momentum_risk`, and `ranking_score_formula`. Do not recompute or drop them during article packaging.
- If the user or automation explicitly requires exactly two articles, `returned_count` and the final bundle article count must be exactly 2. If fewer than 2 material-available, China-unrelated, world-explainer-quality articles survive hard gates, stop and report `INSUFFICIENT_QUALIFIED_WORLD_EXPLAINER_ARTICLES_FOR_EXACT_TWO` instead of creating a one-article draft.
- Selection should cover all 20 production whitelist sources declared by `china-longform-article-selection` and may use discovery/background sources for topic discovery and staleness checks.
- Each production source should be searched once and recorded in `selection/source-shortlist.json` as `FOUND`, `NO_SOURCE_CANDIDATE`, or `SOURCE_FAILED`; discovery/background sources must be separately labeled and cannot enter final production without authorization.
- Each production source may contribute at most one article: the strongest China-unrelated world-explainer candidate from that source in the current fresh/recent/evergreen strategy.
- `SOURCE_FAILED` is a selection gate failure for unattended automation unless the failure is explicitly accepted in the final report; do not silently proceed after skipping a source.
- The merged pool is built from 0..1 best candidate per source, then ranked globally; the default final bundle uses the best 1-2 material-available articles.
- Do not pad with weak, short, China-related, explanation-poor, stale-without-evergreen-value, unauthorized, or unavailable articles merely to reach two. However, when exact-two is explicitly required, count is a hard gate after quality/material/authorization/China-exclusion gates: either produce two qualified articles or stop before draft creation.
- China relevance is a hard exclusion for this WeChat workflow. Returned candidates must be unrelated to China except for incidental background mentions that are not part of the article's thesis, narrative, conflict, evidence, or reader payoff.
- All publications in the production whitelist declared by `china-longform-article-selection` are account-authorized for full Chinese translation and WeChat draft/publication in this workflow. Discovery/background sources are not automatically authorized; record source metadata for internal audit, but do not block production on source-name display requirements for authorized sources.
- Every candidate must have `material_available=true`.
- Every candidate must have existing `capture_output_path`, `capture_manifest_path`, and `material_manifest_path`.
- For `legal_republication_success`, `legal_source_manifest_path` must exist.
- If an otherwise eligible candidate has an original URL but the original site/public direct channel cannot provide complete readable text, selection must attempt the archive.is mirror family through the real Chrome archive flow before declaring the article unavailable or moving to legal republication. Require an audit artifact under `selection/archive-checks/` with `archive_attempted=true`, mirror statuses, and the failure reason if no usable snapshot is found.
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
  "world_explainer_score": 91,
  "topical_momentum_score": 15,
  "topical_momentum_confidence": "high",
  "topical_momentum_window": "24h | 72h | 7d | none",
  "topical_momentum_evidence": [],
  "topical_momentum_reason": "...",
  "topical_momentum_risk": "low | medium | high",
  "ranking_score_formula": "min(100, round(0.85 * world_explainer_score + topical_momentum_score))",
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
  "archive_attempted": false,
  "archive_status": "not_needed_original_public_open | success | failed_no_snapshot | failed_captcha_or_security | failed_snapshot_body_unusable | blocked_real_chrome_unavailable",
  "archive_audit_path": null,
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
- Generate an initial Chinese publish title as an editorial WeChat title, not a literal title translation. It may differ from the original title when that reads better in Chinese, but the final title must be rewritten and checked again in Phase 3c as a China-perspective world-explainer title.
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

After every `translation/translation.md` is created, review it before China-perspective adaptation or WeChat formatting begins.

This node has two mandatory checks:

1. Full-translation coverage and fidelity:
   - Every substantive source paragraph must be represented in the reviewed translation in the same order.
   - The review must compare source paragraph count, substantive paragraph count, heading count, quote coverage, names, numbers, dates, and key factual sequences against the translation.
   - Paragraph count may differ only for documented capture-noise removal or clearly justified heading normalization. It must not differ because the article was summarized or condensed.
   - If `paragraph_count_translation` is far lower than `paragraph_count_source`, or if any report/manifest says the translation is condensed, summarized, abridged, excerpted, or structurally faithful rather than full, mark the review `FAIL`.

2. Baseline Chinese clarity and terminology integrity:
   - The translation must be understandable in written Chinese before entering the dedicated China-perspective adaptation node.
   - Fix obvious mistranslations, broken references, inconsistent entity names, wrong dates/numbers, and title problems.
   - Major rhythm, paragraph-flow, China-perspective reframing, and Chinese-reader structural improvements belong to Phase 3c, not this fidelity review.
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

## Phase 3c-0: China-Perspective Adaptation Plan

After `translation/reviewed_translation.md` passes Phase 3b, create a plan before writing the public-facing article:

```text
articles/{candidate_id}_{slug}/translation/china_perspective_adaptation_plan.json
articles/{candidate_id}_{slug}/translation/china_perspective_adaptation_plan.md
```

Purpose:

- Decide how a Chinese writer/observer should explain the foreign phenomenon to Chinese readers while remaining source-based.
- Define what can be localized, reframed, reordered, or explained, and what must remain unchanged.
- Prevent two failure modes: a stiff translation that does not read like Chinese nonfiction, and an overfree commentary essay that deletes or fabricates source material.

Planning rules:

- The public-facing article may read as if written by a Chinese observer who discovered a foreign phenomenon and is explaining it to Chinese readers.
- The public-facing title must also be China-perspective and explanatory: it should tell Chinese readers which country/region the phenomenon belongs to and invite the article's central `why/how` explanation.
- Do not impersonate the original reporter. Do not write as if the Chinese writer personally interviewed people, visited the scene, obtained documents, or witnessed events unless that is explicitly true and separately documented.
- If the faithful translation contains original-reporter first person or source-outlet body attribution, convert it before public packaging. Examples that must be rewritten include `I met...`, `I walked with...`, `told me`, `we visited`, `X told <publication>`, `<publication> analyzed/found/visited/asked`, `本文多次采访请求`, and Chinese equivalents such as `告诉我`, `向我保证`, `我和...一起`, `我们见面`, `我到访时`, `Rest of World 对...`, `告诉 Rest of World`, or `没有回应本文/媒体的采访请求`. Use neutral third-person or attribution-preserving forms such as `X 说`, `受访时`, `公开报道显示`, `对当地报道的分析发现`, `没有回应多次询问`. Do not remove substantive reporting units; only change the narrative voice and attribution surface.
- Prefer formulations such as `从中国读者的视角看`, `这件事真正值得注意的地方是`, `如果把它放进制度激励里看`, or a direct explanatory lead. Avoid fake first-person reporting.
- Decide where compact Chinese-context bridges are useful, but do not add external facts, new causal claims, or new examples not present in the source unless separately marked as an editor's contextual bridge and verified.
- Identify high-importance source units that must be preserved 100%.
- Draft a title strategy before writing the article. Reject titles that merely translate the original title, preserve an English metaphor, or hide the country/region behind an abstract phrase.

Plan schema:

```json
{
  "schema_version": "wechat-china-perspective-adaptation-plan.v1",
  "candidate_id": "A1",
  "content_mode": "china_perspective_full_adaptation",
  "source_based": true,
  "original_reporting": false,
  "public_facing_source_note": false,
  "narrative_stance": "Chinese observer explains a foreign phenomenon without claiming original reporting",
  "title_strategy": {
    "mode": "china_perspective_world_explainer",
    "country_or_region_anchor": "美国",
    "phenomenon_anchor": "年轻人把暴力当职业",
    "explainer_question_or_mechanism": "为什么会发生",
    "draft_title": "美国为什么总有年轻人把暴力当职业？",
    "rationale": "Names the country, names the foreign phenomenon, and frames the article as an explanation for Chinese readers."
  },
  "allowed_perspective_moves": [
    "rewrite the lead for Chinese readers",
    "rename or add H2 chapters",
    "add compact reader-orientation transitions",
    "localize institutions and unfamiliar terms",
    "merge or split paragraphs while preserving substantive units"
  ],
  "forbidden_moves": [
    "summarize or abridge the article",
    "delete substantive source facts",
    "invent reporting, interviews, documents, scenes, or first-person travel",
    "add external causal claims not in the source",
    "claim original reporting",
    "add visible source/publication/URL blocks"
  ],
  "minimum_substantive_retention_ratio": 0.9,
  "high_importance_units_must_be_retained": true,
  "source_article_sha256": "...",
  "reviewed_translation_sha256": "..."
}
```

## Phase 3c: China-Perspective Full Adaptation

Create the public-facing Chinese article:

```text
articles/{candidate_id}_{slug}/translation/china_perspective_version.md
articles/{candidate_id}_{slug}/translation/china_perspective_adaptation_result.json
articles/{candidate_id}_{slug}/translation/china_perspective_adaptation_report.md
```

Purpose:

- Rewrite the faithful translation into a Chinese-perspective, source-based explanatory longform article.
- The article should read like a Chinese writer explaining a foreign social phenomenon to Chinese readers, not like line-by-line translation.
- Rewrite the title into a China-perspective world-explainer headline, not a literal translation or literary source-title echo.
- Preserve at least 90% of the original article's substantive units and 100% of high-importance units.
- Preserve source facts, claims, evidence, chronology, quotations, hedging, attribution, counterarguments, and causal structure.

Allowed edits:

- Rewrite the title so it foregrounds the country/region plus the phenomenon and usually asks or implies `为什么/如何`: e.g. `美国为什么总有年轻人把暴力当职业？`.
- Rewrite the opening to set up why this foreign phenomenon matters to Chinese readers.
- Add, rename, split, or merge H2/H3 sections to create a clear explanatory structure.
- Reorder paragraphs locally when it improves Chinese explanatory flow and does not distort source chronology, causality, or emphasis.
- Merge adjacent source paragraphs or split long paragraphs, as long as every substantive unit remains traceable.
- Convert foreign institutions, laws, places, and social roles into compact Chinese explanations at first mention.
- Use Chinese explanatory transitions that make already-present source logic explicit.
- Replace translationese with native Chinese nonfiction prose.
- Use a limited China-reader bridge when it is interpretive rather than factual, for example `对中国读者来说，这里的关键不是海藻本身，而是农业、地方财政和监管责任如何缠在一起。`

Forbidden edits:

- Do not keep a title that only sounds elegant after reading the original, but gives Chinese readers no country/region or explanatory hook, such as `一条水法` on its own.
- Do not summarize, abridge, excerpt, or compress the article into a shorter commentary.
- Do not delete substantive information merely because it is foreign, complex, or inconvenient for narrative rhythm.
- Do not invent reporting. The article must not imply the Chinese writer personally interviewed source characters, visited the scene, read unpublished documents, or obtained data.
- Do not carry over the original reporter's first-person field notes into the Chinese public voice. Keep direct quotes by source characters, but convert narrator phrases such as `告诉我`, `我在...见到`, `我和...走在...`, `我们到访时`, and `we met` into third-person source-based narration.
- Do not leave repeated source-publication names inside the body as attribution scaffolding when they are not necessary for comprehension. Keep `source_publication`, `original_title`, URL, author, publication date, and authorization basis in metadata, manifests, and reports; the WeChat-facing body should not visibly read as `X told Rest of World` / `Rest of World visited...` / `Guardian found...`. Preserve attribution substance by rewriting to `X 说`, `一项分析发现`, `受访者表示`, `公开记录显示`, or another source-faithful neutral form.
- Do not add external facts, examples, dates, numbers, legal claims, or causal claims absent from the source unless a separate verified context note is explicitly allowed by the user. Default is no external facts.
- Do not change attributed claims into verified facts or weak source claims into certainty.
- Do not add visible source notes, original-title blocks, URLs, or publication prefixes.
- Do not claim the article is original reporting or original work.

Adaptation result schema:

```json
{
  "schema_version": "wechat-china-perspective-adaptation.v1",
  "candidate_id": "A1",
  "status": "PASS | NEEDS_REVISION | FAIL",
  "content_mode": "china_perspective_full_adaptation",
  "source_based": true,
  "original_reporting": false,
  "public_facing_source_note": false,
  "readability_status": "PASS | NEEDS_REVISION",
  "china_perspective_status": "PASS | NEEDS_REVISION",
  "structure_status": "PASS | NEEDS_REVISION",
  "localization_status": "PASS | NEEDS_REVISION",
  "no_fabricated_reporting_status": "PASS | NEEDS_REVISION | FAIL",
  "source_fidelity_status": "PASS | NEEDS_REVISION | FAIL",
  "title_china_perspective_status": "PASS | NEEDS_REVISION | FAIL",
  "title_country_or_region_anchor": "美国",
  "title_phenomenon_anchor": "年轻人把暴力当职业",
  "title_explainer_frame": "why_question | how_question | mechanism_statement | consequence_statement",
  "title_rationale": "Names the country/region and phenomenon, and frames the article as an explanation for Chinese readers.",
  "reviewed_translation_sha256": "...",
  "china_perspective_version_sha256": "...",
  "title_before": "...",
  "title_after": "...",
  "structural_changes": [
    {
      "type": "lead_rewrite | split | merge | subhead_added | transition_added | local_reorder | title_polish",
      "location": "heading or paragraph number",
      "source_range": "reviewed translation paragraph range",
      "output_range": "china perspective version paragraph range",
      "rationale": "..."
    }
  ],
  "reader_orientation_bridges": [
    {
      "location": "...",
      "text": "...",
      "basis": "interpretive bridge from source material, no new external fact"
    }
  ],
  "forbidden_changes_found": [],
  "revision_count": 1
}
```

## Phase 3c-1: 90% Coverage And Fidelity Gate

After `translation/china_perspective_version.md` is written, run a dedicated coverage/fidelity review:

```text
articles/{candidate_id}_{slug}/translation/china_perspective_coverage_result.json
articles/{candidate_id}_{slug}/translation/china_perspective_coverage_report.md
```

Review method:

- Break `source/article.txt` or `translation/reviewed_translation.md` into substantive units: facts, scenes, characters, dates, numbers, quotes, arguments, causal links, caveats, counterarguments, and key background explanations.
- Mark each unit as `retained`, `partially_retained`, `omitted_with_reason`, `noise_removed`, or `distorted`.
- Compute `retained_substantive_unit_ratio`.
- High-importance units must all be retained. The 90% threshold does not permit deleting the core thesis, key evidence, important quotes, numbers, chronology, caveats, or counterarguments.
- Removed units may only be capture noise, duplicate navigation/captions, repeated transition material, or genuinely redundant phrasing. Every removal must be documented.

Hard gates:

- `retained_substantive_unit_ratio >= 0.90`
- `high_importance_retention_status = "PASS"`
- `distortion_status = "PASS"`
- `no_summary_or_abridgement_status = "PASS"`
- `no_fabricated_reporting_status = "PASS"`
- `not_original_claim_status = "PASS"`

Coverage result schema:

```json
{
  "schema_version": "wechat-china-perspective-coverage.v1",
  "candidate_id": "A1",
  "status": "PASS | NEEDS_REVISION | FAIL",
  "minimum_required_retention_ratio": 0.9,
  "retained_substantive_unit_ratio": 0.94,
  "substantive_unit_count": 120,
  "retained_unit_count": 113,
  "partially_retained_unit_count": 3,
  "omitted_unit_count": 4,
  "high_importance_unit_count": 22,
  "high_importance_retained_count": 22,
  "high_importance_retention_status": "PASS | FAIL",
  "distortion_status": "PASS | FAIL",
  "no_summary_or_abridgement_status": "PASS | FAIL",
  "no_fabricated_reporting_status": "PASS | FAIL",
  "not_original_claim_status": "PASS | FAIL",
  "source_article_sha256": "...",
  "reviewed_translation_sha256": "...",
  "china_perspective_version_sha256": "...",
  "omitted_units": [
    {
      "unit_id": "S034",
      "importance": "low | medium | high",
      "reason": "capture noise | redundant transition | other justified reason",
      "reviewer_note": "..."
    }
  ],
  "distorted_units": [],
  "revision_count": 1
}
```

Loop requirement:

- If adaptation or coverage status is not `PASS`, revise `translation/china_perspective_version.md`, update the adaptation result, and rerun the 90% coverage/fidelity gate.
- Repeat until all required statuses pass.
- Stop with `CHINA_PERSPECTIVE_ADAPTATION_GATE_FAILED` if the article cannot be made Chinese-reader-native while preserving at least 90% of substantive units and all high-importance units.
- Phase 3d must use `translation/china_perspective_version.md`, not `translation/chinese_reading_version.md`, `translation/reviewed_translation.md`, or raw `translation/translation.md`.

## Phase 3d: Local Chinese Reader Review

After Phase 3c passes, run an independent reader-review loop before WeChat formatting begins.

This phase must be performed by a separate subagent. The main/control agent must not substitute its own self-review for this gate. If no subagent tool is available, stop with `LOCAL_READER_REVIEW_GATE_FAILED` and report that an independent reader review could not be run.

Reviewer persona:

- A Chinese reader who has not lived or studied abroad.
- Reads mainly Chinese media and WeChat longform articles.
- Has no assumed background in U.S. sports, U.S. sports betting, federal tax procedure, local U.S. geography, U.S. restaurant chains, or English brand names.
- Wants to understand the story smoothly, not study a translation.

Reviewer input:

```text
translation/china_perspective_version.md
```

Do not provide the source article, the intended fixes, or the main agent's private reasoning to the reviewer. The reviewer must evaluate `translation/china_perspective_version.md` as a standalone WeChat-reading experience.

Reviewer task:

- Read the full article from beginning to end as an ordinary Chinese reader.
- Identify every reading blocker, not just severe errors:
  - unexplained English brand, organization, product, place, law, sports, or industry term
  - awkward or uncommon Chinese industry wording
  - repeated full foreign names, or unnecessary first-mention full transliterations, where short names would be easier
  - unclear character relationships, role changes, or same-surname confusion
  - paragraphs that feel translated rather than written in Chinese
  - China-perspective framing that feels forced, slogan-like, or bolted on
  - passages that imply the Chinese writer personally interviewed people, visited the scene, obtained documents, or conducted original reporting
  - missing source substance: places where the article feels like a summary instead of a full source-based adaptation
  - titles or subheads that are literal, stiff, too long, or hard to share on WeChat
  - titles that do not read from a Chinese-reader perspective because they omit the country/region, hide the phenomenon, or fail to signal the `why/how` explanation
  - U.S.-specific context that needs a short gloss
  - timeline, money, legal/tax, or business-model passages that a local Chinese reader may not follow
  - sentence-level stumbles, pronoun ambiguity, broken transitions, or dense noun piles
- For each issue, provide location, quoted excerpt, why a local Chinese reader may get stuck, and a concrete revision suggestion.
- Return `PASS` only when the article can be read smoothly without needing foreign background knowledge or back-translation into English.

Required outputs:

```text
articles/{candidate_id}_{slug}/translation/local_reader_review_result.json
articles/{candidate_id}_{slug}/translation/local_reader_review_report.md
articles/{candidate_id}_{slug}/translation/local_reader_review_rounds/ optional round reports
```

Review result schema:

```json
{
  "schema_version": "wechat-local-reader-review.v1",
  "candidate_id": "A1",
  "status": "PASS | NEEDS_REVISION | FAIL",
  "round": 1,
  "reviewer_persona": "mainland_chinese_reader_no_overseas_background",
  "china_perspective_version_sha256": "...",
  "readability_status": "PASS | NEEDS_REVISION",
  "comprehension_status": "PASS | NEEDS_REVISION",
  "foreign_context_status": "PASS | NEEDS_REVISION",
  "name_burden_status": "PASS | NEEDS_REVISION",
  "term_localization_status": "PASS | NEEDS_REVISION",
  "china_perspective_naturalness_status": "PASS | NEEDS_REVISION",
  "china_perspective_title_status": "PASS | NEEDS_REVISION",
  "no_fabricated_reporting_status": "PASS | NEEDS_REVISION | FAIL",
  "not_summary_status": "PASS | NEEDS_REVISION | FAIL",
  "wechat_title_status": "PASS | NEEDS_REVISION",
  "issues": [
    {
      "type": "term | name | foreign_context | sentence | paragraph | structure | title",
      "severity": "must_fix | should_fix",
      "location": "heading or paragraph number",
      "excerpt": "...",
      "reader_blocker": "why a local Chinese reader may pause or misunderstand",
      "suggestion": "concrete revision"
    }
  ],
  "revision_count_after_review": 0
}
```

Loop requirement:

- If the subagent returns `NEEDS_REVISION` or `FAIL`, the main/control agent must revise `translation/china_perspective_version.md`, update `translation/china_perspective_adaptation_result.json` hashes/statuses when material wording changes, rerun the 90% coverage/fidelity gate, and write a round report under `translation/local_reader_review_rounds/`.
- Then send only the revised `translation/china_perspective_version.md` back to a separate local-reader subagent review. Prefer reusing the same subagent thread if available so it can verify previous blockers are resolved, but do not let it edit the article directly.
- Repeat until the local-reader review result is `PASS`.
- Stop with `LOCAL_READER_REVIEW_GATE_FAILED` if the article cannot be made smooth for the reviewer without deleting, adding, or distorting substantive source material.
- Later phases must use the Phase 3d-passed `translation/china_perspective_version.md`, not any earlier draft.

## Chinese Title Policy

Use this policy for `source_metadata.article_title_zh`, the H1 in `translation/translation.md`, `translation/reviewed_translation.md`, `translation/china_perspective_version.md`, `wechat/article.md`, `wechat/reviewed_article.md`, `wechat/article_metadata.json.title`, and `wechat_bundle_manifest.json.articles[].title`.

Rules:

- Treat the Chinese title as a China-perspective world-explainer headline for a WeChat public-account article, not as a loyalty test against the English title.
- The title should answer, at headline level, the reader's first question: `哪个国家/地区发生了什么，为什么值得读？`
- Prefer a country/region anchor plus a phenomenon anchor plus an explanatory frame. Good patterns include `X为什么...？`, `X如何...？`, `X的某种制度/危机，为什么...`, or `一件事如何暴露X的制度逻辑`.
- Prefer natural Chinese expression, clear stakes, and a compact hook. The title should sound like something a careful Chinese editor would write for Chinese readers encountering this foreign phenomenon for the first time.
- Keep it accurate to the article's core claim. Do not add facts, claims, blame, causality, or certainty that the source does not support.
- Target 14-28 Chinese characters when possible; never exceed WeChat's 32-character title limit.
- Use a concrete country/region subject plus phenomenon, tension, consequence, or mechanism when helpful: e.g. `美国为什么总有年轻人把暴力当职业？`, `法国为什么被一片海藻困住？`, `印度科技白领为什么突然失业？`.
- A question title is often the default for this account when the source article's value is explanatory. For example, prefer `美国为什么总有年轻人把暴力当职业？` over a title that only translates a metaphor or profession label.
- Titles that omit the country/region anchor are allowed only when the country/region is impossible to include naturally within 32 characters and the phenomenon is still unmistakably foreign and explanatory. Record the reason in `title_rationale`.
- Avoid stiff English calques such as `机器人国家`, `X的赌注`, `中国的竞标`, `X之战`, or noun piles that only make sense when back-translated.
- Avoid abstract, literary, or internally clever titles that create high comprehension cost for Chinese readers, such as `一条水法`, `暴力职业化`, or `海藻之灾`, unless they are paired with a clear country/region and explanatory frame.
- Avoid sensational or clickbait wording: `震惊`, `炸裂`, `崩了`, `完了`, `惊天`, `内幕曝光`, `全网疯传`, `彻底摊牌`.
- Avoid unnecessary current Chinese national leader names in titles.
- Preserve the original English title and source publication separately in metadata and audit reports. Do not put source attribution in the WeChat-facing title.
- Colons are allowed when they are natural editorial punctuation and the text before the colon is part of the headline itself, e.g. `美国西部水权困局：富人草地常绿，农场断水`.
- Colons are forbidden only when the text before the colon is a source publication name or publication alias, e.g. `经济学人：...`, `The Economist: ...`, `金融时报：...`, `ProPublica: ...`.
- After Phase 3c China-perspective adaptation or manual title polishing, synchronize the final chosen title across H1, metadata, bundle manifest, and publish preview.

## Source Authorization And Attribution Display Policy

Authorization basis:

```text
account_authorized_source_whitelist
```

The account has obtained authorization for the production whitelist declared by `/Users/wangfangjia/.codex/skills/china-longform-article-selection/SKILL.md` to produce full Chinese translations and WeChat drafts/publications. Treat that whitelist-level authorization as sufficient for this workflow. Discovery/background sources are for topic discovery and checks only unless separate authorization is recorded.

WeChat-facing display rules:

- Final article titles must not contain source publication prefixes. Do not use `<中文来源名>：<标题主体>`, `The Economist: ...`, `经济学人：...`, or any equivalent source-prefix format.
- Do not reject every colon. A colon is acceptable when the prefix is an editorial phrase rather than a publication name; reject it only when the prefix matches `source_publication`, `source_publication_zh`, or a known whitelist publication alias.
- The H1 in `translation/translation.md`, `translation/reviewed_translation.md`, `translation/china_perspective_version.md`, `wechat/article.md`, `wechat/reviewed_article.md`, `wechat/article_metadata.json.title`, `wechat_bundle_manifest.json.articles[].title`, and the final WeChat `draft/add` payload title must use the editorial China-perspective Chinese title only.
- Do not add a visible source declaration, source note, "本文来自...", "编译自...", original-title block, or URL block at the beginning or end of the WeChat article body.
- Do not claim source-based foreign article adaptations are original reporting. Preserve `source_publication`, `original_title`, `original_url`, `published_date`, `authorization_basis`, `content_mode`, `source_based`, and `original_reporting=false` in metadata, manifests, audit reports, and redacted payloads where appropriate.
- Missing Chinese source-name mapping is never a blocker for title generation or draft creation. `source_publication_zh` may be omitted or used only as non-facing internal metadata.
- If a title contains a colon for editorial reasons, the text before the colon must be part of the headline itself, not the source publication.

## Phase 4: WeChat Article Formatting

For each translated article, create:

```text
articles/{candidate_id}_{slug}/wechat/article.md
articles/{candidate_id}_{slug}/wechat/article_metadata.json
```

Formatting rules:

- Article body is the Phase 3d-passed China-perspective full adaptation from `translation/china_perspective_version.md`, not the raw translation, not only the fidelity-reviewed translation, not a video script, not a summary, and not a commentary essay.
- Do not proceed if `translation/translation_review_result.json` is missing or `full_translation_status` / `language_quality_status` is not `PASS`.
- Do not proceed if `translation/china_perspective_adaptation_result.json` is missing or `readability_status`, `china_perspective_status`, `structure_status`, `localization_status`, `no_fabricated_reporting_status`, `source_fidelity_status`, or `title_china_perspective_status` is not `PASS`.
- Do not proceed if `translation/china_perspective_coverage_result.json` is missing or `status`, `high_importance_retention_status`, `distortion_status`, `no_summary_or_abridgement_status`, `no_fabricated_reporting_status`, or `not_original_claim_status` is not `PASS`, or if `retained_substantive_unit_ratio < 0.90`.
- Do not proceed if `translation/local_reader_review_result.json` is missing or `status` is not `PASS`.
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
  "china_perspective_adaptation_plan_path": "...",
  "china_perspective_version_path": "...",
  "china_perspective_adaptation_result_path": "...",
  "china_perspective_adaptation_report_path": "...",
  "china_perspective_coverage_result_path": "...",
  "china_perspective_coverage_report_path": "...",
  "local_reader_review_result_path": "...",
  "local_reader_review_report_path": "...",
  "translation_full_translation_status": "PASS",
  "translation_language_quality_status": "PASS",
  "content_mode": "china_perspective_full_adaptation",
  "source_based": true,
  "original_reporting": false,
  "china_perspective_readability_status": "PASS",
  "china_perspective_status": "PASS",
  "china_perspective_structure_status": "PASS",
  "china_perspective_localization_status": "PASS",
  "china_perspective_no_fabricated_reporting_status": "PASS",
  "china_perspective_source_fidelity_status": "PASS",
  "title_china_perspective_status": "PASS",
  "title_country_or_region_anchor": "美国",
  "title_phenomenon_anchor": "年轻人把暴力当职业",
  "title_explainer_frame": "why_question",
  "title_rationale": "Names the country, names the phenomenon, and frames the piece as an explanation for Chinese readers.",
  "china_perspective_coverage_status": "PASS",
  "retained_substantive_unit_ratio": 0.94,
  "high_importance_retention_status": "PASS",
  "no_summary_or_abridgement_status": "PASS",
  "not_original_claim_status": "PASS",
  "local_reader_review_status": "PASS",
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

- This phase does not replace Phase 3b, Phase 3c, or Phase 3d. It catches issues introduced by Markdown packaging, media captions, title synchronization, source-display handling, image paths, and final publishable copy assembly.
- `reviewed_article.md` is the only article body allowed to enter bundle/publish.
- Read the full article as a Chinese editor. Fix remaining awkward transitions, paragraph rhythm problems, unclear references, duplicated words, broken punctuation, and headline/subhead mismatches.
- Do not run policy keyword screening for this China-unrelated workflow. Do not soften, delete, or skip material because of old topic categories. If the WeChat API itself rejects a draft, stop and report the API error.
- Preserve every substantive source fact, quote, date, number, attribution, caveat, and counterargument already carried through Phase 3d.
- Review the title against the Chinese Title Policy. Rewrite hard translations, awkward headline fragments, or non-explanatory titles even when the body reads cleanly.
- The final title must still be China-perspective: country/region anchor plus phenomenon plus `why/how` or mechanism/consequence frame, unless a documented 32-character constraint makes the country/region anchor impossible.
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
  "title_china_perspective_status": "PASS | NEEDS_REVISION | FAIL",
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
- `cover_manifest.json` must record `generation_provider: "image_gen"` and `generated_by: "image_gen"`.

Image rules:

- Prefer no-text covers unless the user explicitly asks for text.
- The cover source art must be generated by `image_gen`. Local scripts may only crop, resize, compress, and derive safe-square/thumb variants from the `image_gen` source.
- Do not use PIL/SVG/canvas/programmatic diagrams, source-photo crops, screenshots, or local hand-drawn placeholders as production cover source art unless the user explicitly overrides the image-generation requirement.
- Use the existing `wechat-cover-image` New Yorker-inspired conceptual editorial cover style: one strong metaphor, generous negative space, quiet visual storytelling, restrained premium composition.
- Add the `他山译读` palette as color direction: white/light base, near-black subject, restrained grays, and one controlled Swiss red `#D9251D` accent.
- Do not force covers to replicate Swiss grid, PPT diagrams, dashboards, or infographics.
- Do not ask image models to render Chinese or English title text.
- Keep the main article's important subject inside the center `383x383` safe square.
- Use the existing `wechat-cover-image` visual style unless the user specifies a different brand style.
- Store generation prompts and source article IDs in image manifests.

## Phase 5b: Lead Image And Chapter Illustrations

Read `/Users/wangfangjia/.codex/skills/wechat-article-illustrations/SKILL.md`.

For every selected article A1..A{returned_count}, generate one inline lead/head image plus one body illustration per H2 chapter after that article's `wechat/reviewed_article.md` exists. Do not skip attached articles.

Default outputs:

```text
articles/{candidate_id}_{slug}/illustrations/
  lead_00_<slug>_source_2400x1600.png
  lead_00_<slug>_wechat_2400x1600.jpg
  chapter_01_<slug>_source_2400x1600.png
  chapter_01_<slug>_wechat_2400x1600.jpg
  chapter_02_<slug>_source_2400x1600.png
  chapter_02_<slug>_wechat_2400x1600.jpg
  illustrations_manifest.json
```

Rules:

- Generate an inline lead/head image and chapter illustrations for every selected article.
- The inline lead/head image is not the WeChat API cover and must not reuse the cover image. It is a separate body image inserted in `wechat/reviewed_article.md`.
- Insert the lead image immediately after the H1 title and before the first body paragraph or first lead block, using alt text `头图`.
- For this deep-longform workflow, long articles must not ship with `fallback_single_illustration=true`. If an article has no usable H2 chapters, go back upstream, create semantic `##` sections, regenerate the reviewed article, and then create one illustration per H2 chapter.
- Use article-level context only for the lead image prompt: final title, opening thesis, first 2-4 paragraphs, and short whole-article summary. Do not reuse the cover metaphor or any chapter metaphor.
- Use only the content of the current H2 chapter when prompting each illustration.
- Do not feed the whole article to every illustration prompt.
- Use the same New Yorker-inspired conceptual editorial style as `wechat-cover-image`.
- Use the `他山译读` palette: white/light base, near-black subject, restrained grays, and one controlled Swiss red `#D9251D` accent.
- Body illustration ratio: `3:2` horizontal.
- Keep high-resolution source/master images at `2400x1600` or larger.
- Use optimized `*_wechat_2400x1600.jpg` images for Markdown insertion.
- Insert chapter images immediately after their H2 headings in `wechat/reviewed_article.md` with alt text `插图`.
- Do not add visible captions unless the user explicitly asks for captions.
- The lead image and every chapter illustration source image must be generated by `image_gen`; `image_map.json` and `illustrations_manifest.json` must record `generation_provider: "image_gen"` / `generated_by: "image_gen"` at top level, for `lead_image`, and for each chapter image item.
- `image_map.json` and `illustrations_manifest.json` must also preserve the real original `image_gen` output path for the lead image and every chapter image, using `generated_image_path`, `original_generated_image_path`, or `image_gen_source_path`. That path must point under the local image_gen output root (`~/.codex/generated_images/...`), not only to a project-local processed copy under `illustrations/_generated/`.
- Local scripts may only crop, resize, compress, validate, and insert generated images. They must not create the source art with PIL/SVG/canvas/programmatic drawing or local placeholders.
- Stop with `WECHAT_ILLUSTRATION_GATE_FAILED` if the lead image is missing, placed after the first H2, reused from the cover, or if any inserted image is below 2400px wide, has visible text/pseudo-text, repeats the same metaphor as another image, or lacks `image_gen` provenance.

## Phase 6: Bundle Manifest

Create:

```text
wechat_bundle/wechat_bundle_manifest.json
wechat_bundle/main_article.md
wechat_bundle/attached_articles.json
```

Hard rule:

- This skill publishes one WeChat draft every time after all gates pass. If returned_count=1 in a non-exact-two run, it is a single-article draft. If returned_count>1, it is a multi-article draft. If exact-two is required, returned_count=1 is a blocker, not a single-article fallback.
- The article with the highest final `score` from `china-longform-article-selection` is the main article (`wechat_role: "main"`). That score already includes the audited topical momentum boost when present. The remaining selected articles, if any, are attached/sub articles (`wechat_role: "attached"`) in descending selection-score order.
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

Use every returned material-available candidate. Unless the user specifies another editorial rule, keep the highest-scoring candidate as the main article and attach the remaining returned candidates in ranked order. Every returned candidate must have passed translation review, China-perspective full adaptation, 90% coverage/fidelity review, local Chinese reader review, final copy and technical packaging check, cover generation, article formatting, inline lead/head image generation, and chapter illustration generation before the bundle manifest is written.

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
  "china_perspective_adaptation_plan_path": ".../articles/A1_slug/translation/china_perspective_adaptation_plan.json",
  "china_perspective_version_path": ".../articles/A1_slug/translation/china_perspective_version.md",
  "china_perspective_adaptation_result_path": ".../articles/A1_slug/translation/china_perspective_adaptation_result.json",
  "china_perspective_coverage_result_path": ".../articles/A1_slug/translation/china_perspective_coverage_result.json",
  "local_reader_review_result_path": ".../articles/A1_slug/translation/local_reader_review_result.json",
  "local_reader_review_report_path": ".../articles/A1_slug/translation/local_reader_review_report.md",
  "article_quality_check_path": ".../articles/A1_slug/wechat/article_quality_check.json",
  "source_publication_zh": "金融时报",
  "authorization_basis": "account_authorized_source_whitelist",
  "cover_path": ".../articles/A1_slug/cover/main_cover.png",
  "wechat_upload_cover_path": ".../articles/A1_slug/cover/main_cover.png",
  "thumb_path": ".../articles/A1_slug/cover/thumb_square_500x500.png",
  "cover_manifest_path": ".../articles/A1_slug/cover/cover_manifest.json",
  "lead_image_path": ".../articles/A1_slug/illustrations/lead_00_slug_wechat_2400x1600.jpg",
  "illustrations_manifest_path": ".../articles/A1_slug/illustrations/illustrations_manifest.json",
  "translation_language_quality_status": "PASS",
  "translation_full_translation_status": "PASS",
  "content_mode": "china_perspective_full_adaptation",
  "source_based": true,
  "original_reporting": false,
  "china_perspective_readability_status": "PASS",
  "china_perspective_status": "PASS",
  "china_perspective_structure_status": "PASS",
  "china_perspective_localization_status": "PASS",
  "china_perspective_no_fabricated_reporting_status": "PASS",
  "china_perspective_source_fidelity_status": "PASS",
  "title_china_perspective_status": "PASS",
  "title_country_or_region_anchor": "美国",
  "title_phenomenon_anchor": "年轻人把暴力当职业",
  "title_explainer_frame": "why_question",
  "title_rationale": "Names the country, names the phenomenon, and frames the piece as an explanation for Chinese readers.",
  "china_perspective_coverage_status": "PASS",
  "retained_substantive_unit_ratio": 0.94,
  "high_importance_retention_status": "PASS",
  "no_summary_or_abridgement_status": "PASS",
  "not_original_claim_status": "PASS",
  "local_reader_review_status": "PASS",
  "article_quality_status": "PASS",
  "lead_image_count": 1,
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
- Do not create the draft until all selected article chains have passed translation review, China-perspective full adaptation, 90% coverage/fidelity review, local Chinese reader review, final copy and technical packaging check, cover generation, formatting, and illustration gates.
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
CHINA_PERSPECTIVE_ADAPTATION_GATE_FAILED
CHINA_PERSPECTIVE_ADAPTATION_COMPLETE
CHINA_PERSPECTIVE_COVERAGE_GATE_FAILED
CHINA_PERSPECTIVE_COVERAGE_COMPLETE
LOCAL_READER_REVIEW_GATE_FAILED
LOCAL_READER_REVIEW_COMPLETE
ARTICLE_QUALITY_GATE_FAILED
ARTICLE_FULL_WORKFLOW_COMPLETE
WECHAT_PACKAGE_READY
WECHAT_DRAFT_CREATED
COMPLETE
FAILED
```

Final report must include:

- Target date and run directory.
- Returned selection candidates A1..A{returned_count} with score, world-explainer score, topical momentum score/confidence/window/evidence summary, source, title, capture path, manifest path.
- Main article and attached article IDs.
- Translation paths for all selected articles.
- Translation review paths and full-translation/language statuses for all selected articles.
- China-perspective adaptation plan/version/result/report paths and readability/structure/localization/no-fabricated-reporting/source-fidelity statuses for all selected articles.
- China-perspective title status, country/region anchor, phenomenon anchor, explainer frame, and title rationale for all selected articles.
- 90% coverage/fidelity review paths, retained substantive unit ratio, high-importance retention, distortion, no-summary/no-abridgement, no-fabricated-reporting, and not-original-claim statuses for all selected articles.
- Local Chinese reader review paths, review rounds, statuses, and unresolved blocker counts for all selected articles.
- Final article quality check paths and statuses for all selected articles.
- Cover paths, cover manifests, and cover spec for all selected articles.
- Lead image paths, illustration manifest paths, lead image counts, and chapter illustration counts for all selected articles.
- WeChat bundle manifest path.
- Publish draft report path and status.
- WeChat style version and preview HTML path.
- Any blocker, especially translation coverage failures, China-perspective adaptation failures, 90% retention/fidelity failures, Chinese readability failures, unresolved local-reader comprehension blockers, article quality gate failures, or WeChat API errors.

## Final Acceptance Gate

Before live draft creation, run a final bundle-level acceptance gate. This gate is mandatory for repaired runs, automation runs, and any run where the user has made explicit overrides such as `两篇文章`, `瑞士风格`, or `必须分章节`.

Run:

```bash
python3 /Users/wangfangjia/.codex/skills/daily-china-article-to-wechat-bundle/scripts/final_gate_check.py \
  --run-dir /Volumes/GT34/daily_china_article_wechat/{target_date}_world_explainer \
  --require-article-count 2 \
  --min-h2 3 \
  --require-selection-source-count 20 \
  --require-per-source-cap 1 \
  --fail-on-source-failed \
  --require-swiss-cover \
  --require-swiss-illustrations \
  --require-image-gen-cover \
  --require-image-gen-illustrations \
  --require-lead-image \
  --require-china-perspective-adaptation
```

Acceptance checklist:

- The bundle contains the user-required number of articles. Do not silently downgrade from 2 to 1 when the second article was excluded only by editorial preference.
- Selection covered all 20 production whitelist sources where feasible and labeled any discovery/background sources separately.
- Each production source contributed at most one strongest candidate for the fresh/recent/evergreen strategy; final candidates are not required to be same-day published.
- Every article has China-perspective adaptation artifacts, `content_mode=china_perspective_full_adaptation`, `source_based=true`, `original_reporting=false`, adaptation status `PASS`, and no body wording that claims original interviews, scene visits, documents, or reporting by the Chinese writer.
- Every article title is China-perspective and explanatory: `title_china_perspective_status=PASS`, a recorded country/region anchor appears in the title, and the metadata records a phenomenon anchor, explainer frame, and rationale.
- Every article has a 90% coverage/fidelity review with `retained_substantive_unit_ratio >= 0.90`, all high-importance units retained, no distortion, no summary/abridgement, no fabricated reporting, and no original-reporting claim.
- Every article has at least 3 semantic `##` chapters for deep-longform reading.
- Every article has one inserted inline lead/head image after H1 and before the first body paragraph/first H2.
- Every article has one inserted body illustration per `##` chapter.
- `fallback_single_illustration` is forbidden for repaired deep-longform runs.
- Covers and illustrations record the requested Swiss-style variant when the user explicitly asked for `瑞士风格`.
- Covers, every lead/head image, and every chapter illustration are generated by `image_gen`; manifests must record `generation_provider` / `generated_by` as `image_gen` and preserve an existing original image_gen source path under `~/.codex/generated_images/...`.
- Local PIL/SVG/canvas/programmatic diagrams, source-photo crops, screenshots, and placeholder drawings are forbidden as production source art.
- The WeChat-facing title has no source prefix. Editorial colons are allowed; fail only when the colon prefix is a source publication name or known publication alias.
- The body has no visible source declaration, original-title block, URL block, or `编译自...` block.
- The draft remains a draft only; `final_publish_clicked` must stay `false`.
- `publish/wechat_article.preview.html` exists and was regenerated from the repaired reviewed articles.

Rework loop:

- If the final gate fails, do not publish live.
- Go back to the earliest failing stage, repair the article or bundle, regenerate downstream artifacts, and rerun the final gate.
- Repeat until the final gate passes.
