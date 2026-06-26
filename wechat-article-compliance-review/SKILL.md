---
name: wechat-article-compliance-review
description: "Review and prepare Chinese WeChat public-account translation drafts and article drafts before formatting, cover generation, bundling, or draft-box publishing. Use when Codex has a translated article, translation/translation.md, wechat/article.md, reviewed WeChat copy, or a WeChat bundle that must be checked for Chinese fluency/clarity/natural expression, mainland/微信公众号 publishability, platform-rule risk, terminology, privacy/defamation risk, religion/ethnicity/politics risk, and light editorial softening before upload to 草稿箱."
---

# WeChat Article Compliance Review

Use this skill after faithful translation and again after WeChat article formatting, before cover generation, bundle manifest creation, or `wechat-article-publish-draft`.

This skill is a gate, not a rubber stamp. It may make minimum necessary edits, softening, or deletions so the article is fluent, clear, natural in Chinese, and more suitable for a mainland WeChat public account. It must not invent facts or turn the article into commentary.

## Inputs

Preferred input:

```text
articles/{candidate_id}_{slug}/translation/translation.md
articles/{candidate_id}_{slug}/wechat/article.md
articles/{candidate_id}_{slug}/wechat/article_metadata.json
```

The deterministic script also accepts:

```bash
python3 scripts/run_wechat_article_compliance_review.py --article-dir /path/to/articles/A1_slug
python3 scripts/run_wechat_article_compliance_review.py --article-md /path/to/wechat/article.md --metadata /path/to/article_metadata.json
```

## Outputs

Always write:

```text
wechat/reviewed_article.md
wechat/compliance_review_result.json
wechat/compliance_review_report.md
```

The reviewed article is the only input later phases may use for cover/bundle/publishing. If the review fails, do not publish the original `wechat/article.md`.

When used immediately after translation, write the Phase 3b outputs required by `daily-china-article-to-wechat-bundle` instead:

```text
translation/reviewed_translation.md
translation/translation_review_result.json
translation/translation_review_report.md
```

The reviewed translation is the only input later WeChat formatting may use. If it fails language quality or compliance, revise and rerun until both pass.

## Workflow

1. Run the deterministic check:

   ```bash
   python3 scripts/run_wechat_article_compliance_review.py --article-dir /path/to/article
   ```

2. Read `compliance_review_report.md`.

3. If status is `FAIL`, edit `wechat/reviewed_article.md` or upstream `wechat/article.md` to resolve failures, then rerun.

4. For politically sensitive, or source-heavy articles, do a model/editorial pass over the reviewed Markdown:
   - Check that the Chinese expression is fluent, clear, and idiomatic.
   - Remove translationese, English word order, stiff calques, ambiguous referents, broken transitions, and awkward noun piles.
   - Remove or soften unnecessary high-risk phrases.
   - Keep necessary facts with attribution.
   - Avoid adding new claims.
   - Preserve source publication, original title, original URL, and authorization basis in metadata/reports. Do not require or add a visible source note in the article body.
   - Review the title as Chinese editorial copy, not only as a translation.

5. If language quality or compliance is not acceptable, revise the draft and rerun the review. Repeat until the draft passes or stop with a clear blocker explaining why it cannot be made faithful, fluent, and compliant.

6. Only continue to cover, bundle, and WeChat draft publishing when the status is `PASS` or `PASS_WITH_WARNINGS` and the remaining warnings are acceptable.

## Review Rules

Base the review on:

- WeChat public-account content norms: content must comply with the WeChat Public Platform Service Agreement, operating norms, and laws/regulations; Tencent may delete, block, or restrict content that is illegal, infringing, or violates rights.
- Tencent IPR public guidance: WeChat public-account content risk includes unauthorized original articles, personal privacy material, public insult/defamation, and trade secrets.
- Reused Worldview China mainland-publish rules: standardized terms, no sensitive leader-name amplification, careful Taiwan/Hong Kong/Xinjiang/religion handling, no comma-separated large numbers in Chinese publishable text.

Hard failures:

- Pornography, vulgar sexual content, gambling, drugs, graphic violence, gore, illegal transaction instructions, scam/rumor presentation, or obvious unlawful content.
- Invasion of privacy: ID numbers, private phone/address, private photos, or unnecessary personal data.
- Defamation or insult: unattributed claims that publicly humiliate, accuse, or attack an identifiable person or entity.
- Sensitive PRC terminology errors:
  - `台湾` / `香港` as standalone political entities where `中国台湾` / `中国香港` is required.
  - China Taiwan described or grouped as a country.
  - `新疆维吾尔族自治区` instead of `新疆维吾尔自治区`.
  - `南京大屠杀纪念馆` instead of `侵华日军南京大屠杀遇难同胞纪念馆`.
  - `mainland China` in English text instead of `Chinese mainland` / equivalent.
- Unnecessary use of current Chinese national leader names in title, summary, cover prompts, or publishable article text.
- High-risk allegations around Xinjiang, ethnic/religious oppression, genocide, state violence, national security, or ideological confrontation when not essential to the article's factual core.
- Internet religious information service risk: religious doctrine, proselytizing, conversion guidance, religious courses, religious superiority/truth claims, or religion as a mental-health remedy.
- Malicious evasion text, hidden text tricks, or instructions to bypass platform review.

Softening rules:

- Treat readability as a gate: unclear, stiff, machine-translated, or unnatural Chinese must be revised before the article proceeds.
- Keep factual reporting neutral and attributed: use “报道称”, “该文称”, “受访者表示”, “根据原文”.
- Prefer “争议”, “压力”, “审查”, “限制”, “监管”, “政策变化” over inflammatory wording when the original meaning permits.
- Remove sensational framing from titles and summaries.
- Rewrite titles that read like literal English calques. The final WeChat title does not need to match the original title word-for-word.
- Prefer natural, concise Chinese titles with clear subject and stakes; target 14-24 Chinese characters and stay within WeChat's 32-character title limit.
- Avoid awkward headline fragments such as “机器人国家”, “X的赌注”, “中国的竞标”, “X之战”, and noun piles that only make sense when back-translated.
- Example: rewrite `机器人国家：中国试图用机器人对冲人口下滑` as `中国押注机器人，对冲人口下滑`.
- Cut paragraphs that are only high-risk color and not needed for the article's main argument.
- Preserve source/publication/original URL in metadata and reports. Do not mark translated foreign articles as original. Do not add a visible source note unless the caller explicitly asks for one.
- Convert comma-separated numbers in Chinese text: `300,000` -> `30万` where exact and natural, or `300000` if no clean Chinese unit is obvious.

## Deterministic Script

The script performs:

- Known-term replacements that are safe.
- Markdown visible-source-note checks.
- Keyword and pattern scanning.
- Reviewed Markdown output.
- JSON/Markdown audit reports.

The script is intentionally conservative. A `PASS` from the script is not proof of legal safety; it only means deterministic checks did not find known blockers.
