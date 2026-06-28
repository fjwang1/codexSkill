---
name: worldview-china-podcast-title-cover
description: "For Worldview China YouTube podcast/video translation runs, create an attractive Chinese video title and 4K cover by combining a justified speaker/source identity prefix such as 黄仁勋, 美国议员, 俄罗斯教授, or 上海美国商会前会长 with a platform-native Chinese hook title based on the source title, transcript, claims, conflicts, consequences, or a sharp source-speaker quote; then write video_title.txt and cover/cover_title.json, choose a source-video podcast frame as the cover background, and compose cover/cover_4k.png with centered large Chinese title text. Use when the workflow needs video title or cover assets for a YouTube source-video podcast, not for article-based podcast titles or AI-generated article covers."
---

# Worldview China Podcast Title Cover

This skill is the title and cover node for YouTube source-video podcast translation. It is intentionally different from the article podcast cover chain:

- Article podcast: create a platform-native title and AI-generated cover background.
- YouTube podcast: add a justified external speaker/source identity prefix, write a platform-native hook title from the source conversation, and use a frame from the source video as the cover background.

## Contract

Build the title from two parts:

```text
<source_identity_label>：<translated_title_core>
```

The title should communicate both:

- The video is sourced from an outside/foreign-facing conversation.
- The claim is interesting enough to click.
- The prefix itself is a viewer-facing identity hook, not a filing label.
- The title core itself contains concrete content: what changed, who is under pressure, what conflict is being argued, or what consequence matters. A title made of names, institutions, regions, and topic nouns is not enough.

Use the original YouTube title as a reference signal for `translated_title_core`, not as a cage. If the original title is weak, vague, or translation-flavored, abandon its surface form and write the strongest truthful Chinese hook supported by the transcript: a sharp claim, conflict question, consequence, counterintuitive statement, or a source-speaker quote whose wording is allowed to be punchy out of its full context. The identity label may come from the YouTube title, description, visible speaker, transcript, or reliable local metadata.

Before finalizing a title, apply the Bilibili viewer information test:

- If the viewer has never heard of the named person, does the prefix still explain why this person is worth listening to? If not, replace the name with a meaningful role label. For example, `亚当·图兹：` is weak for most Bilibili viewers; `哥大经济学家：` gives immediate context.
- If the viewer only reads the title core, can they repeat the main claim or tension in one sentence? If not, the core is too vague.
- If the title sounds like a database row, conference agenda, or keyword pile, rewrite it into a concrete claim, pressure point, consequence, or question.

Rules:

- `video_title.txt` must contain the full Chinese title in `<source_identity_label>：<translated_title_core>` form.
- Prefer a famous person's Chinese name when the speaker is genuinely famous and clearly identified, e.g. `马斯克：`, `特朗普：`, `黄仁勋：`.
- If there is no famous person, use a concise role/nationality identity that gives the viewer context, e.g. `美国议员：`, `俄罗斯教授：`, `美国鉴证大V：`, `华尔街分析师：`, `美国智库学者：`, `上海美国商会前会长：`.
- The identity prefix must be attractive enough to carry the first half of the title. Prefer a concrete lived-experience, institutional, seniority, geography, time, or track-record hook over a bland taxonomy. For example, write `旅居中东20年学者：` rather than `中国中东问题专家：`; write `上海美国商会前会长：` rather than `美国商界人士：`.
- Identity selection is priority based, not a blanket ban on generic labels:
  1. Famous clearly identified person: use the person's Chinese name.
  2. Strong public title or China-linked role: use the real title if it is concise and clickable, e.g. `上海美国商会前会长：`, `白宫前中国顾问：`, `大西洋理事会学者：`, `旅居中东20年学者：`.
  3. Weak, obscure, or overlong real title: use a short truthful fallback label that viewers understand quickly, e.g. `中国问题专家：`, `中东专家：`, `中国专家：`.
  4. Never use empty labels such as `专家：`, `学者：`, `外国学者：`, `海外专家：`, or awkward hybrid labels such as `中国中东问题专家：` / `中东中国问题专家：`.
- If using a short generic fallback such as `中国问题专家` or `中东专家`, `identity_basis` must explain that the source supports this domain label and that no brighter concise title is available or worth using.
- Do not use lazy source labels such as `来自...`, `中文配音版`, `油管搬运`, `外网播客`, `《频道名》：`, `《播客名》：`, `CGSP：`, or `Podcast：`.
- Do not use internal column/topic labels as the identity prefix, including `世界眼中的中国`, `世界看中国`, `海外视角`, `外网热议`, `中国观察`, `国际观察`, `嘉宾访谈`, or `专家圆桌`. Those are account/series tags, not viewer-facing title information.
- Do not invent a famous name or role. If identity is uncertain, use a conservative generic role that is supported by metadata or transcript.
- The title core must point out the “eye” of the episode. Do not write generic background titles such as `变局之后，美国、中国和新中东`, `中东停火与中国经济足迹`, `中国在中东的新格局`, or `中国角色的脉络` because the viewer still cannot tell what happened between those actors.
- Do not write a title core that is only a pile of proper nouns or abstract topics, such as `中国冲击2.0、德国工业与全球贸易`, `达沃斯、中国经济与世界秩序`, or `美国学者谈中国制造`. These phrases may be accurate, but they do not tell the viewer what the video says.
- Prefer concrete content verbs and consequence frames: `中国冲击2.0先打到德国工业`, `德国工业为什么最先承压`, `外企为什么还离不开中国市场`, `美国盟友开始重新算中国账`. The exact wording must still be supported by the source.
- Do not rely on an obscure real name, institution acronym, podcast title, or event name as the main attraction unless that name is already broadly recognizable to Chinese viewers. Use the name only when the name itself carries click value; otherwise translate the credential into a viewer-readable identity.
- Good title cores may be a little overstated if the source conversation supports them in substance or as an in-context quote, but they must not fabricate facts or invert the speaker's meaning.
- `cover/cover_title.json.title_text` must equal `video_title.txt`.
- The cover title must be the same Chinese title used as the video title.
- Series episode exception: when `<run_dir>/episode_manifest.json` exists and `--episode-index` is provided, `video_title.txt` must include the series title, an episode order marker, and the episode subtitle, e.g. the default `系列名·第1集：中国的经济韧性`. `cover/cover_title.json.title_text` defaults to the unnumbered cover title, e.g. `系列名：中国的经济韧性`. In that case `cover/cover_title.json.video_title_text` must equal `video_title.txt` and `cover_title_omits_episode_index` must be true.
- The cover title must use centered layout on the 16:9 cover, not the article workflow's left-side title layout.
- The centered title must stay inside the 4:3 information-feed crop-safe box on a 3840x2160 cover: left/right crop-safe margins are 480px each, so the title block max width is 2880px. Do not use the full 16:9 width for title text.
- Cover title sizing priority is: keep a large-font two-line title if it fits; if large two lines do not fit, keep the large font and use three lines; only shrink the font after a large-font three-line layout still cannot fit. Do not preserve a cramped two-line break that forces the whole title to become small.
- The cover background should come from the downloaded source video, preferably a talking-head, split-screen, or visible podcast/interview frame.
- Do not use the original YouTube thumbnail if it is clickbait, political stock art, off-topic, or does not show the podcast form.
- Do not use the article cover AI-background gate here; `source_video_frame_background` is allowed and expected for this skill.

Example:

```text
Original YouTube title:
China's Economy Is Stronger and Weaker Than You Think

Chinese title:
上海美国商会前会长：中国经济，比你想象的更强，也更脆弱
```

## Inputs

Required:

```text
<run_dir>/02-source-capture/youtube-media/source.info.json
<run_dir>/02-source-capture/youtube-media/source.mp4
```

Preferred existing frame QA inputs:

```text
<run_dir>/02-source-capture/source-video-frame-qa/middle.png
<run_dir>/02-source-capture/source-video-frame-qa/opening.png
<run_dir>/02-source-capture/source-video-frame-qa/end.png
```

The agent must provide both:

```text
--speaker-label / --source-identity-label
--translated-title-core
```

The script does not use an LLM and does not choose the identity label itself.

## Outputs

```text
<run_dir>/video_title.txt
<run_dir>/cover/cover_title.json
<run_dir>/cover/background_raw.png
<run_dir>/cover/background.png
<run_dir>/cover/visual_subject.json
<run_dir>/cover/image_source_manifest.json
<run_dir>/cover/cover_4k.png
<run_dir>/02d-title-cover/title_cover_manifest.json
<run_dir>/02d-title-cover/title_cover_report.md
```

`cover_title.json` is compatible with the existing `bilibili-podcast-cover` compositor, but its provenance rules are different: this skill records source-video-frame provenance instead of AI-image provenance.

## Workflow

1. Read the original YouTube title from `source.info.json`; fall back to `metadata.json` or `source_metadata.json`.
2. Decide `source_identity_label`:
   - Famous clearly identified speaker: use the person's Chinese name.
   - Non-famous but credentialed speaker: first look for an attractive public role or lived-experience hook supported by evidence: years in the relevant region, former office, named institution, seniority, founder/host/editor role, China-linked office, or a distinctive professional vantage point.
   - When several truthful labels are available, choose the one a Bilibili viewer would understand fastest and be most likely to click. Strong specificity beats taxonomy: `上海美国商会前会长` > `美国商界人士`; `旅居中东20年学者` > `中国中东问题专家`.
   - If the truthful specific title is too long, obscure, institution-heavy, or not meaningfully more clickable, deliberately simplify to a short domain label such as `中国问题专家`, `中东专家`, `经济学家`, or `前外交官`.
   - Avoid awkward hybrid labels and empty labels: `中国中东问题专家`, `中东中国问题专家`, `外国学者`, `海外专家`, `专家`, `学者`.
   - If multiple speakers, use the person whose viewpoint/title claim drives the video; if unclear, use the guest's role rather than the host/channel.
   - Record the evidence in `--identity-basis`.
3. Write `translated_title_core` as a platform-native hook:
   - Read the original title, transcript, and current episode script; identify the strongest object, conflict, consequence, or quote.
   - Preserve the source speaker's broad meaning and stance, but do not mechanically translate a weak original title.
   - Do not include the identity prefix in the core.
   - Prefer one of three strategies: flow-keyword title, conflict question, or consequence/counterintuitive title.
   - Self-check by reading only the Chinese title: the viewer should immediately know who or what is clashing with what, what pressure is landing on whom, or what strong claim is being made.
   - Run a "so what?" check. If the core can be followed by "这到底说了什么？", it is not ready. Rewrite from topic nouns into a claim or consequence.
   - Translate obscure speaker identity into useful viewer information when needed. Example: if the source says Adam Tooze is speaking but the audience is unlikely to know him, `哥大经济学家：中国冲击2.0先打到德国工业` is stronger than `亚当·图兹：中国冲击2.0正在打到德国身上`.
4. Choose 2-4 highlight substrings from the full Chinese title for yellow cover text. Prefer the identity label and the most important nouns/adjectives. They must be continuous substrings of the full title.
5. Choose the cover background:
   - Prefer `source-video-frame-qa/middle.png` if it clearly shows the podcast/interview form.
   - Use `opening.png` or `end.png` if they are visually stronger.
   - Use `--frame` for an explicitly selected frame.
   - Use `--source-time-sec` only when no existing frame QA image is suitable.
6. Run the script. The script always asks the shared cover compositor to use centered title layout for this YouTube source-video podcast workflow:

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-podcast-title-cover/scripts/build_title_cover.py \
  --run-dir <run_dir> \
  --speaker-label "上海美国商会前会长" \
  --identity-basis "YouTube description identifies Ker Gibbs as a longtime China-based executive and former president of the American Chamber of Commerce in Shanghai." \
  --translated-title-core "中国经济，比你想象的更强，也更脆弱" \
  --highlight-text "上海美国商会前会长" \
  --highlight-text "中国经济" \
  --highlight-text "更强" \
  --highlight-text "更脆弱" \
  --force
```

For a series episode:

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-podcast-title-cover/scripts/build_title_cover.py \
  --run-dir <run_dir>/04b-series-episodes/episode_001 \
  --speaker-label "系列名" \
  --translated-title-core "中国的经济韧性" \
  --episode-index 1 \
  --episode-title-template "{series_title}·{episode_order_marker}：{subtitle}" \
  --episode-order-marker-template "第{episode_index}集" \
  --frame <parent_run_dir>/02-source-capture/source-video-frame-qa/middle.png \
  --force
```

The optional `--cover-include-episode-index` flag is only for explicit user requests. Default series covers omit the episode marker so every cover reads like `系列名：<episode_subtitle>` while the Bilibili title is read from `episode_manifest.json.video_title` or generated from `--episode-title-template` plus the series-wide `--episode-order-marker-template`.

The script normalizes the selected frame to 3840x2160 and calls the existing editorial cover compositor:

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/scripts/compose_editorial_cover.py
```

It passes `--layout center` to the compositor. In this mode the compositor must keep every rendered title line inside the 4:3 crop-safe center box (`x=480..3360`) so Bilibili information-flow 4:3 thumbnails do not cut off left or right title edges. Do not use the default article-cover left layout for this skill.

For centered podcast covers, `cover_title.json.title_lines` are advisory source breaks, not a command to keep a too-long line. The compositor must select the final rendered line breaks by this priority:

1. Large-font two-line title if it fits.
2. Large-font three-line title if two lines do not fit.
3. Shrunk-font three-line title only if large three lines still do not fit.

The manifest written next to `cover_4k.png` must record the final `visual_line_policy`, `font_start_size_px`, `font_size_px`, and final `title_lines`.

## Gate

Pass only if:

```text
video_title.txt exists and has a justified source identity prefix followed by `：`
video_title.txt does not use lazy source labels such as 来自, 中文配音版, 油管搬运, 外网播客, CGSP, Podcast
cover/cover_title.json exists
cover_title.json.title_text equals video_title.txt stripped of trailing newline for single-video runs
if --episode-index is used, cover_title.json.video_title_text equals video_title.txt and cover_title.json.title_text omits the episode marker
cover_title.json.source_title records the original YouTube title
cover_title.json.title_source equals podcast_source_identity_plus_platform_native_hook or the legacy youtube_original_title_translated_with_source_identity
cover_title.json.source_identity_label equals the prefix before `：` in video_title.txt
cover_title.json.identity_label_policy.status == PASS
if cover_title.json.identity_label_policy.type == fallback_generic, source_identity_basis explains why the short generic fallback is justified
cover_title.json.translated_title_core equals the title after `：` in video_title.txt, or the episode subtitle for series episode titles
cover_title.json.attractive_title_policy.status == PASS
cover_title.json.attractive_title_policy confirms the title core is not merely a list of people, institutions, regions, events, or abstract topic nouns
cover_title.json.attractive_title_policy confirms the full title would still communicate useful information to a Bilibili viewer who does not know the source speaker by name
cover_title.json.highlight_texts contains 2-4 continuous substrings from the full Chinese title, prioritizing the identity label, concrete nouns, conflict words, or consequence adjectives
cover_title.json.highlight_texts does not waste highlights on weak function words, platform labels, or generic filler such as 外网, 播客, 视频, 中文配音
cover/background_raw.png and cover/background.png exist
cover/image_source_manifest.json records image_type=source_video_frame_background
cover/cover_4k.png exists and is 3840x2160
cover/cover_4k.png has the Chinese title burned in
cover/cover_4k.png uses centered title layout with every title line inside the 4:3 crop-safe center box
cover/cover_4k.manifest.json records the final centered line policy: large two lines first, large three lines second, and shrunk three lines only as fallback
02d-title-cover/title_cover_manifest.json exists
```

If the selected frame does not visibly communicate podcast/interview form, block this title/cover gate, choose a better source frame from source-video QA or extract a new source frame, then rerun the compositor. Do not fall back to AI-generated bottom art unless the user explicitly changes the product direction.
