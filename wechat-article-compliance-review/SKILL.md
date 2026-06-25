---
name: wechat-article-compliance-review
description: "Review and prepare Chinese WeChat public-account article drafts before cover generation, bundling, or draft-box publishing. Use when Codex has a translated China-related article, wechat/article.md, reviewed WeChat copy, or a WeChat bundle that must be checked for mainland/微信公众号 publishability, platform-rule risk, terminology, copyright/source-note risk, privacy/defamation risk, religion/ethnicity/politics risk, and light editorial softening before upload to 草稿箱."
---

# WeChat Article Compliance Review

Use this skill after faithful translation and WeChat article formatting, before cover generation, bundle manifest creation, or `wechat-article-publish-draft`.

This skill is a gate, not a rubber stamp. It may make minimum necessary edits, softening, or deletions so the article is more suitable for a mainland WeChat public account. It must not invent facts or turn the article into commentary.

## Inputs

Preferred input:

```text
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

## Workflow

1. Run the deterministic check:

   ```bash
   python3 scripts/run_wechat_article_compliance_review.py --article-dir /path/to/article
   ```

2. Read `compliance_review_report.md`.

3. If status is `FAIL`, edit `wechat/reviewed_article.md` or upstream `wechat/article.md` to resolve failures, then rerun.

4. For politically sensitive, copyright-sensitive, or source-heavy articles, do a model/editorial pass over the reviewed Markdown:
   - Remove or soften unnecessary high-risk phrases.
   - Keep necessary facts with attribution.
   - Avoid adding new claims.
   - Preserve source note and original URL.

5. Only continue to cover, bundle, and WeChat draft publishing when the status is `PASS` or `PASS_WITH_WARNINGS` and the remaining warnings are acceptable.

## Review Rules

Base the review on:

- WeChat public-account content norms: content must comply with the WeChat Public Platform Service Agreement, operating norms, and laws/regulations; Tencent may delete, block, or restrict content that is illegal, infringing, or violates rights.
- Tencent IPR public guidance: WeChat public-account content risk includes unauthorized original articles, personal privacy material, public insult/defamation, and trade secrets.
- Reused Worldview China mainland-publish rules: standardized terms, no sensitive leader-name amplification, careful Taiwan/Hong Kong/Xinjiang/religion handling, no comma-separated large numbers in Chinese publishable text.

Hard failures:

- Pornography, vulgar sexual content, gambling, drugs, graphic violence, gore, illegal transaction instructions, scam/rumor presentation, or obvious unlawful content.
- Invasion of privacy: ID numbers, private phone/address, private photos, or unnecessary personal data.
- Defamation or insult: unattributed claims that publicly humiliate, accuse, or attack an identifiable person or entity.
- Copyright/platform-originality risk: the article claims or implies original authorship for a translated/recreated third-party article, lacks clear source attribution, or includes language encouraging an original declaration.
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

- Keep factual reporting neutral and attributed: use “报道称”, “该文称”, “受访者表示”, “根据原文”.
- Prefer “争议”, “压力”, “审查”, “限制”, “监管”, “政策变化” over inflammatory wording when the original meaning permits.
- Remove sensational framing from titles and summaries.
- Cut paragraphs that are only high-risk color and not needed for the article's main argument.
- Preserve source/publication/original URL. Do not mark translated foreign articles as original.
- Convert comma-separated numbers in Chinese text: `300,000` -> `30万` where exact and natural, or `300000` if no clean Chinese unit is obvious.

## Deterministic Script

The script performs:

- Known-term replacements that are safe.
- Markdown source-note checks.
- Keyword and pattern scanning.
- Reviewed Markdown output.
- JSON/Markdown audit reports.

The script is intentionally conservative. A `PASS` from the script is not proof of legal safety; it only means deterministic checks did not find known blockers.
