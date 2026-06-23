---
name: worldview-china-podcast-title-cover
description: "For Worldview China YouTube podcast/video translation runs, create an attractive Chinese video title and 4K cover by combining a justified speaker/source identity prefix such as 黄仁勋, 美国议员, 俄罗斯教授, or 上海美国商会前会长 with a smooth Chinese translation of the original YouTube title, then write the same title to video_title.txt and cover/cover_title.json, choose a source-video podcast frame as the cover background, and compose cover/cover_4k.png with centered large Chinese title text. Use when the workflow needs video title or cover assets for a YouTube source-video podcast, not for article-based podcast titles or AI-generated article covers."
---

# Worldview China Podcast Title Cover

This skill is the title and cover node for YouTube source-video podcast translation. It is intentionally different from the article podcast cover chain:

- Article podcast: create a platform-native title and AI-generated cover background.
- YouTube podcast: add a justified external speaker/source identity prefix, reuse the original YouTube title meaning as the title core, and use a frame from the source video as the cover background.

## Contract

Build the title from two parts:

```text
<source_identity_label>：<translated_title_core>
```

The title should communicate both:

- The video is sourced from an outside/foreign-facing conversation.
- The claim is interesting enough to click.

Use the original YouTube title as the semantic source for `translated_title_core`. The identity label may come from the YouTube title, description, visible speaker, transcript, or reliable local metadata.

Rules:

- `video_title.txt` must contain the full Chinese title in `<source_identity_label>：<translated_title_core>` form.
- Prefer a famous person's Chinese name when the speaker is genuinely famous and clearly identified, e.g. `马斯克：`, `特朗普：`, `黄仁勋：`.
- If there is no famous person, use a concise role/nationality identity that gives the viewer context, e.g. `美国议员：`, `俄罗斯教授：`, `美国鉴证大V：`, `华尔街分析师：`, `美国智库学者：`, `上海美国商会前会长：`.
- Do not use lazy source labels such as `来自...`, `中文配音版`, `油管搬运`, `外网播客`, `《频道名》：`, `《播客名》：`, `CGSP：`, or `Podcast：`.
- Do not invent a famous name or role. If identity is uncertain, use a conservative generic role that is supported by metadata or transcript.
- `cover/cover_title.json.title_text` must equal `video_title.txt`.
- The cover title must be the same Chinese title used as the video title.
- The cover title must use centered layout on the 16:9 cover, not the article workflow's left-side title layout.
- The centered title must stay inside the 4:3 information-feed crop-safe box on a 3840x2160 cover: left/right crop-safe margins are 480px each, so the title block max width is 2880px. Do not use the full 16:9 width for title text.
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
   - Non-famous but credentialed speaker: use `nationality/region + role`, or the strongest concrete public role.
   - If multiple speakers, use the person whose viewpoint/title claim drives the video; if unclear, use the guest's role rather than the host/channel.
   - Record the evidence in `--identity-basis`.
3. Translate the original title faithfully into `translated_title_core`:
   - Preserve the original meaning and stance.
   - Smooth grammar and word choice for Chinese reading.
   - Do not include the identity prefix in the core.
   - Do not turn a statement into a different question unless the original is a question.
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

The script normalizes the selected frame to 3840x2160 and calls the existing editorial cover compositor:

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/scripts/compose_editorial_cover.py
```

It passes `--layout center` to the compositor. In this mode the compositor must keep every rendered title line inside the 4:3 crop-safe center box (`x=480..3360`) so Bilibili information-flow 4:3 thumbnails do not cut off left or right title edges. Do not use the default article-cover left layout for this skill.

## Gate

Pass only if:

```text
video_title.txt exists and has a justified source identity prefix followed by `：`
video_title.txt does not use lazy source labels such as 来自, 中文配音版, 油管搬运, 外网播客, CGSP, Podcast
cover/cover_title.json exists
cover_title.json.title_text equals video_title.txt stripped of trailing newline
cover_title.json.source_title records the original YouTube title
cover_title.json.title_source equals youtube_original_title_translated_with_source_identity
cover_title.json.source_identity_label equals the prefix before `：` in video_title.txt
cover_title.json.translated_title_core equals the title after `：` in video_title.txt
cover/background_raw.png and cover/background.png exist
cover/image_source_manifest.json records image_type=source_video_frame_background
cover/cover_4k.png exists and is 3840x2160
cover/cover_4k.png has the Chinese title burned in
cover/cover_4k.png uses centered title layout with every title line inside the 4:3 crop-safe center box
02d-title-cover/title_cover_manifest.json exists
```

If the selected frame does not visibly communicate podcast/interview form, stop and choose a better source frame. Do not fall back to AI-generated bottom art unless the user explicitly changes the product direction.
