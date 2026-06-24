---
name: bilibili-video-upload-draft
description: "Use when the user wants Codex to upload and publish a Bilibili Creator Center video in the user's already-logged-in Google Chrome session: open a fresh upload tab, upload a local video file and cover image from absolute paths, fill title/description/tags/category fields, verify the data stuck, then click the final submit/post button once and report the submission result. The skill name is kept for compatibility with existing pipelines."
---

# Bilibili Video Upload And Publish

Upload and publish a Bilibili video in the user's real logged-in Chrome session. After the video, cover, metadata, optional schedule, and verification gates pass, click the final `投稿`, `立即投稿`, `提交`, `发布`, or equivalent final submission button once. Do not pause for manual confirmation.

When this skill is called from a video production pipeline such as `english-article-chinese-podcast-video`, `english-article-chinese-single-host-video`, or `worldview-china-podcast-agent`, it is the final publication phase of that pipeline. It must create machine-readable submission/blocker artifacts in the video project so the parent skill can gate completion.

## Invocation Boundary

This skill is the only allowed implementation boundary for Bilibili upload and final submission work in the video production pipelines. Upstream skills and workers may prepare `bilibili_upload_metadata.json`, but they must not hand-roll Bilibili upload automation, manually create `bilibili_upload_draft_report.json`, or replace this skill with ad hoc Chrome/Playwright snippets. The report filename remains `bilibili_upload_draft_report.*` for backward compatibility; its successful status is now `SUBMITTED`, not `HANDOFF_READY`.

Required behavior:

- Before any Bilibili browser action, read this `SKILL.md` completely in the same run and record that fact in the report.
- The report JSON must include:

```json
{
  "skill_name": "bilibili-video-upload-draft",
  "skill_path": "/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md",
  "skill_invocation": "direct",
  "skill_instructions_read": true
}
```

- If the caller cannot invoke this skill directly, it must stop before opening Bilibili and report `BLOCKED_UPLOAD_SKILL_NOT_INVOKED`; it must not try a local substitute.
- A blocked report is valid only if it is produced by this skill after following this skill's gates. A caller-written report is invalid for parent Gate 13.

## Required Browser Surface

Use `chrome:control-chrome` with the Codex Chrome Extension, not the in-app browser, CDP, Playwright launched profiles, or a temporary Chrome profile. The Bilibili session depends on the user's existing Chrome login state.

In Codex, the concrete browser operation route is:

1. Use the **Chrome** plugin skill `control-chrome`, not the **Browser** plugin skill `control-in-app-browser`.
2. Read the installed Chrome plugin skill before browser work. On this machine the current known path is:

   ```text
   /Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.616.31447/skills/control-chrome/SKILL.md
   ```

   If that exact version is not present, discover the latest installed path with:

   ```bash
   find /Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome -path '*/skills/control-chrome/SKILL.md' | sort | tail -1
   ```

3. Bootstrap Chrome through the Node REPL `js` tool, typically exposed as `mcp__node_repl__js`, by importing the Chrome plugin `scripts/browser-client.mjs` and selecting the extension browser:

```js
const { setupBrowserRuntime } = await import("/Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.616.31447/scripts/browser-client.mjs");
await setupBrowserRuntime({ globals: globalThis });
globalThis.browser = await agent.browsers.get("extension");
nodeRepl.write(await browser.documentation());
```

   If that exact version is not present, discover the latest installed module with:

   ```bash
   find /Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome -path '*/scripts/browser-client.mjs' | sort | tail -1
   ```

4. Use the resulting `browser` / Chrome extension tab APIs to open or claim the Bilibili upload tab and to use file chooser `setFiles(...)`.

Do not use `/Users/wangfangjia/.codex/plugins/cache/openai-bundled/browser/.../control-in-app-browser/SKILL.md` for Bilibili uploads. That skill selects `agent.browsers.get("iab")`, which is the Codex in-app browser and does not carry the user's real Chrome Bilibili login/session.

Distinguish tool availability from extension state:

- Do **not** rely on `tool_search` for `chrome:control-chrome` as the only availability test. In this desktop environment `tool_search` may return no Chrome tools even when the Chrome plugin is installed and usable through `node_repl` bootstrap.
- Before reporting `CHROME_CONTROL_TOOL_UNAVAILABLE`, run this actual probe through the Node REPL `js` tool:

  ```js
  const { setupBrowserRuntime } = await import("/Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.616.31447/scripts/browser-client.mjs");
  await setupBrowserRuntime({ globals: globalThis });
  globalThis.browser = await agent.browsers.get("extension");
  nodeRepl.write(await browser.documentation());
  ```

  If the versioned path is stale, first discover the latest `browser-client.mjs` under `/Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome`.
- Only write `blocker.code="CHROME_CONTROL_TOOL_UNAVAILABLE"` if the Node REPL `js` tool itself is unavailable, the Chrome plugin files are missing, or the bootstrap/probe above cannot create `agent.browsers.get("extension")`.
- If `agent.browsers.get("extension")` exists but cannot connect to the user's Chrome extension/session, use `CHROME_EXTENSION_UNAVAILABLE`, not `CHROME_CONTROL_TOOL_UNAVAILABLE`.
- Use `CHROME_EXTENSION_UNAVAILABLE` only when `chrome:control-chrome` is available but the Codex Chrome Extension cannot connect to the user's Chrome, or Chrome itself reports the extension/session is unavailable.
- Never infer that the user's Chrome extension is missing solely because a worker/subagent lacks the Chrome tool surface.

Before uploading local files, the Chrome extension must be allowed to access local file URLs. If `filechooser.setFiles(...)` fails with `Not allowed`, stop the upload attempt and tell the user exactly:

```text
To enable file upload, go to chrome://extensions in Chrome, click Details under the Codex extension, and enable "Allow access to file URLs." See [here](https://developers.openai.com/codex/app/chrome-extension#upload-files) for details.
```

After the user enables it, retry from the video upload step in a fresh Bilibili upload tab.

## Inputs

Prefer explicit paths from the user. If they are not provided and the current task is for an article-video workflow, infer these files from the selected video project:

```text
video/final_video.mp4
cover/cover_4k.png
video_title.txt
publish_info.txt
bilibili_upload_metadata.json
```

Use absolute paths only. Validate that the video and cover files exist before opening Bilibili.

For article-video workflow projects, prefer `<project>/bilibili_upload_metadata.json` over ad hoc inference. That file is generated by `article-podcast-static-video` after the final video is produced. Treat it as the source of truth for title, description, tags, category, creation declaration, video path, cover path, and optional scheduled publish time. Use `video_title.txt` and `publish_info.txt` only as fallbacks or cross-checks.

For `worldview-china-podcast-agent` projects, also prefer `<project>/bilibili_upload_metadata.json`. That file is generated by `worldview-china-bilibili-publish-metadata` after the final source-video revoice is produced. Treat it as the source of truth and do not replace its tags with article tags such as `外刊解读`.

When a project directory can be inferred from the metadata path or explicit video path, write reports to the legacy report paths:

```text
<project>/bilibili_upload_draft_report.json
<project>/bilibili_upload_draft_report.md
```

These report files are required even when the attempt is blocked before upload or before final submission. If no project directory can be inferred, write the same report fields to the final response and prefer an explicit output path supplied by the caller.

As a standalone skill, accept these explicit inputs:

```json
{
  "video_path": "/absolute/path/final_video.mp4",
  "cover_path": "/absolute/path/cover_4k.png",
  "title": "投稿标题",
  "description": "投稿简介",
  "tags": ["外网热议", "海外视角", "中国观察", "国际观察"],
  "category": "知识",
  "creation_declaration": "含AI生成内容",
  "scheduled_publish_at": "2026-06-16T17:00:00+08:00",
  "scheduled_publish_timezone": "Asia/Shanghai"
}
```

`scheduled_publish_at` is optional. This upload skill does not decide which topic belongs to the 11:00 or 17:00 daily slot; that policy belongs to the upstream orchestration skill. It does normalize the provided time at upload time: keep a future exact time unchanged, but if a daily slot time has already passed, roll it forward to the next occurrence of the same wall-clock slot. If no scheduled time is provided, leave Bilibili's timing controls unchanged and report that no schedule was requested. Scheduled submissions still proceed through the same final submission gate after the schedule is verified.

## Fresh Tab Rule

Every upload attempt must create a new Chrome tab:

```js
const tab = await browser.tabs.new();
await tab.goto("https://member.bilibili.com/platform/upload/video/frame?spm_id_from=333.33.top_bar.upload");
```

If Bilibili shows `本地浏览器存在1个未提交的视频`, do not click `继续编辑` or `不用了` unless the user explicitly asks. Those controls may resume or discard an existing draft. Prefer starting a new tab and attempting the upload controls directly.

If the Chrome control tool is unavailable, a fresh upload tab cannot be opened, or the page does not reach Bilibili Creator Center because the user is logged out, blocked, or redirected, write `bilibili_upload_draft_report.json` with `status="BLOCKED"`, `blocked_phase="open_upload_page"`, and the visible URL/title/text evidence when available.

## Browser Stability Lessons

The Bilibili upload page is a live SPA. Make the automation resilient by treating each phase as a gate with observable proof, not as a sequence of clicks:

- Use a fresh Chrome tab for every upload attempt. Do not reuse a tab that has a failed or partially submitted state unless the retry is for the same field inside the same upload.
- Wait for the upload/edit form to become visible before filling metadata. A completed `setFiles(...)` call only proves the file was handed to Chrome; it does not prove Bilibili accepted or processed it.
- If local file upload fails with `Not allowed`, the fix is Chrome extension file URL permission. Do not switch to a temporary browser profile, because that loses the user's logged-in Bilibili session.
- For all text fields, fill, blur, then re-read the page value. If a field does not stick, retry once using the visible control path and keyboard selection. Do not report success from a typed keystroke alone.
- The title input may scroll offscreen after editing description or tags. Locate by placeholder and scroll/click the actual input; avoid stale coordinates.
- Quill description editors can swallow synthetic value assignment. Use click, `ControlOrMeta+A`, `Backspace`, `type(...)`, `Tab`, then verify `.innerText`.
- Bilibili may auto-generate tags. Remove existing tag chips first, then add intended tags one by one with Enter. After each tag, verify that a chip was created or that the page rejected/capped it. Record the accepted tag set. Live test note: `上B站看播客` appeared under `参与话题` and did not create a normal tag chip, so replace it with a relevant article tag when ordinary chip count matters.
- If Bilibili shows a remaining-tag hint such as `还可以添加4个标签`, use it as evidence of the real cap for the current page. Stop when the page refuses more tags; do not loop forever trying to force the target count.
- Category selectors and option DOM are unstable. Prefer visible labels and final displayed text. For this workflow the target is always `知识`; if the page already displays `知识`, do not reopen the selector.
- Cover upload must be proven by the cover editor closing and the preview changing to a Bilibili-hosted image URL. `C:\fakepath\cover_4k.png` in an image input is necessary but not sufficient.
- Cover crop confirmation buttons such as `完成` are safe because they only save the cover. Final video submission buttons `投稿`, `立即投稿`, `提交`, or `发布` are safe only inside the Final Submission Gate after all verification checks pass; before that gate they are never safe.
- If a modal, toast, or validation error appears, snapshot the visible text, retry only the failed phase, and keep the upload tab open. After the same field fails three times with the same error, stop and report the blocker with current accepted values.

## Video Upload

On the current Bilibili upload page, the first-screen video controls observed are:

```text
Upload area text: 点击上传或将视频拖拽到此区域 / 上传视频
Video input 1: input[type="file"][accept*=".mp4"] hidden under the upload area
Video input 2: input[type="file"][name="buploader"][accept*=".mp4"] visible
Subtitle input: input[type="file"][name="buploader"][accept=".txt"]
```

Use the browser file chooser flow. The most reliable trigger observed was clicking `.upload-area`:

```js
const chooserPromise = tab.playwright.waitForEvent("filechooser", { timeoutMs: 15000 });
await tab.playwright.locator(".upload-area").click({ timeoutMs: 10000 });
const chooser = await chooserPromise;
await chooser.setFiles([videoPath]);
```

Hard rule: never use `locator.fill(path)` or equivalent text-entry APIs on `input[type=file]`. A failure such as `Input of type "file" cannot be filled` proves only that the wrong primitive was used; it is not evidence that file upload automation is unavailable. After that error, retry with the file chooser flow above before reporting any blocker.

Fallback trigger if `.upload-area` disappears after page changes:

```js
const videoInput = tab.playwright.locator('input[type="file"][name="buploader"][accept*=".mp4"]');
await videoInput.click({ timeoutMs: 10000 });
```

After setting the file, verify that the page has left the first-screen upload state or shows upload progress / uploaded video information. Do not assume success from the absence of an exception.

## Metadata Filling

After video upload completes and Bilibili renders the edit form:

1. Load `<project>/bilibili_upload_metadata.json` when present. Require `schema_version="bilibili_upload_metadata.v1"` for strict use. Cross-check `title` against `video_title.txt`. For article-video workflow metadata, verify `description` contains `先行提要` and does not contain `章节：` or timestamp ranges such as `00:00-01:09`; do not cross-check or force chapter lines into the Bilibili description. If `metadata.workflow=="worldview-china-podcast-agent"`, preserve its title, description, and tags exactly except for Bilibili page rejection/capping.
2. Fill title from metadata `title`; fallback to `video_title.txt`. Trim only if Bilibili visibly rejects the full title, and report the trim.
3. Fill description from metadata `description`. Fallback order:
   - `video_title.txt` title plus a short `先行提要：` generated from `cover/cover_title.json`, `planning/article_brief.json`, or source metadata.
   - a minimal fallback of title plus `先行提要：本期围绕原文的核心问题，梳理事件背景、利益冲突和可能后果。`
   Do not include `章节：`, `publish_info.txt` chapter lines, timestamp ranges, chapter slugs, local paths, model names, internal manifests, script hashes, or production QA notes.
4. Fill tags from metadata `tags`. Target 8-10 visible tags, because the current Bilibili upload page has accepted up to 10 tags. If `metadata.workflow=="worldview-china-podcast-agent"`, use video/podcast tags generated upstream, such as `外网热议`, `海外视角`, `中国观察`, `国际观察`, `国际播客`, `中文配音`, `中国经济`, `财经解读`, `中美关系`, `贸易战`, `中国制造`, `供应链`, or the verified source identity label. Do not supplement with article-only tags (`外刊解读`, `外刊精读`, `英语学习`, `英语听力`) unless the metadata already contains them with a justified source type. If metadata is missing or underfilled for an article workflow, generate tags by this rule:
   - Start with fixed base tags: `外刊解读`, `国际观察`.
   - Add `财经解读` or `社会观察` when the article context supports it.
   - Add `亚洲观察` for Asia-related episodes.
   - Add `中国观察` only when China is a material variable in the article or episode, not merely because the channel is China-focused.
   - Add source publication when confirmed, such as `经济学人`, `金融时报`, `外交政策`, `彭博社`, or `外交学者`.
   - Add concrete article tags from title, `source/source_metadata.json`, `planning/article_brief.json`, `cover/cover_title.json.keyword_heat_check.best_keywords`, `cover/cover_title.json.chinese_motifs`, and the chapter titles. Prefer country/region, policy object, industry, institution, core conflict, and named theme terms.
   - Do not use `外刊精读`, `英语学习`, or `英语听力` unless the video is actually an English-learning/close-reading product.
   - Remove duplicates, punctuation, spaces, `#`, commas, quotes, and unrelated traffic terms. Keep each tag under 20 Chinese characters. Do not count `参与话题` entries as ordinary tags unless the page also creates visible tag chips for them.
5. Set category/partition to `知识`. This is fixed for this article-video workflow. Do not choose entertainment, news, life, or technology just because a selector suggests it.
6. Set creation declaration to `含AI生成内容`. This is fixed for outputs from the AI article-video pipelines.
7. If `scheduled_publish_at` is present, normalize it to the effective Asia/Shanghai wall-clock time, set Bilibili to scheduled publishing for that effective time, then verify the displayed date and time. If it is absent, do not touch timing controls.
8. Do not fill unsupported claims, clickbait wording, or unrelated tags just for traffic.

Use DOM snapshots to locate the actual form controls in the current Bilibili UI. Bilibili changes class names; prefer visible labels and nearby containers over brittle global class selectors.

Observed stable controls after video upload:

```text
Title: input[placeholder="请输入稿件标题"]
Creation declaration: input[placeholder="请选择符合您视频内容的创作声明"]
Partition/category display: .selector-container
Tags: #tag-container, selected chips .label-item-v2-content, delete icons .tag-pre-wrp .close
Tag input: #tag-container input[placeholder="按回车键Enter创建标签"]
Description editor: .desc-container .ql-editor
```

Important: the title field may be above the viewport after editing description/tags. Do not use fixed coordinates unless a fresh inspection shows the title input is visible. If the input's `getBoundingClientRect().y` is negative, scroll up before clicking it. The reliable title path is:

```js
const titleInput = tab.playwright.getByPlaceholder("请输入稿件标题", { exact: true });
await titleInput.click();
await titleInput.press("ControlOrMeta+A");
await titleInput.press("Backspace");
await titleInput.type(title);
await titleInput.press("Tab");
```

For Quill description, use the visible editor and keyboard path:

```js
const descEditor = tab.playwright.locator(".desc-container .ql-editor");
await descEditor.click();
await descEditor.press("ControlOrMeta+A");
await descEditor.press("Backspace");
await descEditor.type(description);
await descEditor.press("Tab");
```

To replace auto-generated tags:

```js
let closes = tab.playwright.locator(".tag-pre-wrp .label-item-v2-container .close");
for (let i = 0, n = await closes.count(); i < n; i++) {
  closes = tab.playwright.locator(".tag-pre-wrp .label-item-v2-container .close");
  await closes.nth(0).click();
}
const tagInput = tab.playwright.locator('#tag-container input[placeholder="按回车键Enter创建标签"]');
for (const tag of tags) {
  await tagInput.click();
  await tagInput.fill(tag);
  await tagInput.press("Enter");
}
```

For AI-produced podcast/video pipeline outputs, set `创作声明` to `含AI生成内容`:

```js
await tab.playwright.getByPlaceholder("请选择符合您视频内容的创作声明", { exact: true }).click();
await tab.playwright.locator(".bcc-select-option-list .bcc-option").filter({ hasText: "含AI生成内容" }).click();
```

For article-video workflow outputs, set or verify the partition/category as `知识`. If the upload page already displays `知识`, leave it. If it displays a different value, open the visible category selector and choose the visible `知识` option. Because Bilibili category DOM changes frequently, select by visible text and then verify the display text contains `知识`; do not rely on a hard-coded class beyond using it to find the currently visible selector.

## Scheduled Publish

Only configure scheduled publishing when the input metadata includes `scheduled_publish_at`.

Normalize the requested time before touching the page:

- Interpret ISO timestamps with offsets directly.
- If the user provides a local date/time without an offset, interpret it in `scheduled_publish_timezone`, defaulting to `Asia/Shanghai`.
- Convert the requested time to Asia/Shanghai and compare it with the current Asia/Shanghai time at the moment of upload.
- If the requested time is still in the future, keep the exact requested date and wall-clock time.
- If the requested time is not in the future and its wall-clock time is one of the daily Bilibili slots (`11:00` or `17:00`), roll it forward to the next future occurrence of the same slot. Example: if `2026-06-20T11:00:00+08:00` is requested but upload happens at `2026-06-20 12:30 Asia/Shanghai`, use `2026-06-21 11:00 Asia/Shanghai`.
- Also treat a time as a daily slot when `schedule_source` identifies `daily-china-article-to-podcast-video`; in that case roll a passed slot to the next future occurrence of the same `HH:MM` wall-clock time.
- If the requested time is not in the future and is not a daily slot time, stop before changing the timing controls and report `blocker.code="SCHEDULE_IN_PAST"`.
- Use the effective time for Bilibili controls and verification. If rollover was applied and a metadata file exists, update only its schedule fields so `scheduled_publish_at` records the effective ISO-8601 time while `schedule_source` remains unchanged.
- Preserve both the requested and effective wall-clock times in the submission report, for example `scheduled_publish_at_requested="2026-06-20 17:00 Asia/Shanghai"` and `scheduled_publish_at_effective="2026-06-21 17:00 Asia/Shanghai"`.

Bilibili's timing controls may be labeled differently across releases. Locate them by visible text near `定时发布`, `发布时间`, `预约发布`, `立即发布`, or equivalent radio/checkbox controls. The stable rule is:

1. Find the publish timing section after the required metadata fields are visible.
2. Choose the option whose visible text means scheduled publishing, not immediate publishing.
3. Fill the date and time controls using the effective Asia/Shanghai date and hour/minute.
4. Blur the controls and read back the displayed date/time.
5. Retry the scheduling phase once if the displayed value does not match.

Do not click final `投稿` / `立即投稿` / `发布` immediately after setting a schedule. The schedule is only part of the data-entry phase; after verifying the schedule display, continue to the Verification Gate and then the Final Submission Gate.

Observed 2026-06 upload page path:

```js
await tab.playwright.locator(".time-container .switch-container").click();
await tab.playwright.locator(".date-picker-date").click();
await tab.playwright.locator(".date-picker-container .date-picker-body-item").filter({ hasText: "16" }).click();
await tab.playwright.locator(".date-picker-timer").click();
await tab.playwright.locator(".time-picker-panel-select-wrp").nth(0).locator(".time-picker-panel-select-item").filter({ hasText: "17" }).click();
await tab.playwright.locator(".time-picker-panel-select-wrp").nth(1).locator(".time-picker-panel-select-item").filter({ hasText: "00" }).click();
await tab.playwright.locator(".section-title-content-main").filter({ hasText: "定时发布" }).click();
```

Then verify:

```js
const scheduleValues = await tab.playwright.locator(".time-container .date-show").allInnerTexts();
// expected: ["2026-06-16", "17:00"]
```

If the hour item receives the selected class but the visible time still shows the old hour, click outside the time picker or press Escape, then re-read `.time-container .date-show`. In the observed page, the display refreshed from `22:00` to `17:00` only after blur.

## Cover Upload

Only attempt cover upload after video upload has succeeded and the edit form is visible. Locate the cover section by visible text such as `封面`, `更换封面`, `上传封面`, `编辑封面`, or an image crop dialog.

Use the same file chooser flow with `cover_4k.png`:

```js
const chooserPromise = tab.playwright.waitForEvent("filechooser", { timeoutMs: 15000 });
await coverUploadControl.click({ timeoutMs: 10000 });
const chooser = await chooserPromise;
await chooser.setFiles([coverPath]);
```

If Bilibili opens a crop/confirm dialog, confirm only the cover crop/save action, not the final video submission. After confirming the cover dialog, verify that the displayed cover preview changed. If the page has a hidden `input[type=file][accept*="image"]`, prefer triggering the visible cover button that opens it.

Observed cover flow:

```js
await tab.playwright.locator(".cover-item").nth(0).click();
const chooserPromise = tab.playwright.waitForEvent("filechooser", { timeoutMs: 15000 });
await tab.playwright.locator(".cover-upload").click();
const chooser = await chooserPromise;
await chooser.setFiles([coverPath]);
await tab.playwright.locator(".cover-editor").getByText("完成", { exact: true }).click();
```

Successful application closes `.cover-editor` and changes `.cover-img` to an uploaded Bilibili URL such as `https://archive.biliimg.com/bfs/archive/...jpg`. Treat an `input[type=file][accept="image/png, image/jpeg"]` value like `C:\fakepath\cover_4k.png` as necessary but not sufficient; the final proof is the closed modal plus changed `.cover-img` style.

## Verification Gate

Before final submission, verify:

- Video upload is complete enough that Bilibili accepts metadata editing.
- Title field value equals the intended title after blur.
- Description field contains the intended text after blur.
- Tags are visible as chips/tokens, not just typed into an inactive input. For article-video workflow metadata, target 8-10 visible unique tags. If Bilibili rejects some tags or caps the count below the target, report the accepted tags and the page message.
- Category/partition shows `知识` for article-video workflow outputs.
- Creation declaration shows `含AI生成内容` for AI article-video workflow outputs.
- If `scheduled_publish_at` was provided, the page visibly shows scheduled publishing and the displayed date/time matches the effective Asia/Shanghai time after normalization. If no schedule was provided, report `scheduled_publish_at: not requested`.
- Cover preview is present and changed after upload.
- The final submit/post button is visible, enabled, and unambiguous.
- No visible validation error, blocking modal, captcha, login prompt, rights/appeal warning, or risky confirmation is present.
- The report will record `final_submit_clicked=true` only after the Final Submission Gate clicks the final button.

If any field does not stick, retry that field once using the visible control path, then re-check. If it still does not stick, do not publish; leave the tab open and report the exact field that needs manual correction.

## Final Submission Gate

After the Verification Gate passes, submit automatically. This is the only phase where final publish controls may be clicked.

Required sequence:

1. Locate a single visible enabled final submission control whose text is one of `立即投稿`, `投稿`, `发布`, or `提交`. Prefer exact visible text and scoped footer/action containers. Do not click if the locator resolves to zero or multiple visible enabled controls.
2. Click the final submission control once.
3. If Bilibili shows a routine confirmation dialog whose only meaning is final confirmation, click the visible `确认`, `确定`, `继续`, or equivalent confirmation button once.
4. If the dialog or page mentions captcha, login, phone verification, rights ownership, copyright dispute, audit risk, violation risk, appeal, account risk, or any non-routine warning, do not confirm. Write `status="BLOCKED"`, `blocked_phase="final_submit"`, and include the visible warning text.
5. Wait for proof of submission. Accept any of:
   - visible text such as `投稿成功`, `提交成功`, `发布成功`, `已提交审核`, `审核中`, or `稿件管理`;
   - navigation to a Bilibili creator center success, upload result, or manuscript-management page;
   - a visible manuscript item/status for the just-submitted title.
6. Do not retry the final click automatically if success proof is missing. A second click can duplicate a submission. Instead write `status="BLOCKED"`, `blocked_phase="final_submit"`, `final_submit_clicked=true`, `submission_status="unknown"`, and preserve the tab for inspection.

## Submission Artifacts

Always write a JSON report before returning to the parent workflow.

Successful submission shape:

```json
{
  "schema_version": "bilibili_upload_draft_report.v1",
  "skill_name": "bilibili-video-upload-draft",
  "skill_path": "/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md",
  "skill_invocation": "direct",
  "skill_instructions_read": true,
  "status": "SUBMITTED",
  "created_at": "ISO-8601",
  "project_dir": "/Volumes/GT34/english_aircle_to_video/<video_project>",
  "metadata_path": "/Volumes/GT34/english_aircle_to_video/<video_project>/bilibili_upload_metadata.json",
  "video_path": "/Volumes/GT34/english_aircle_to_video/<video_project>/video/final_video.mp4",
  "cover_path": "/Volumes/GT34/english_aircle_to_video/<video_project>/cover/cover_4k.png",
  "bilibili_upload_url": "https://member.bilibili.com/platform/upload/video/frame?spm_id_from=333.33.top_bar.upload",
  "chrome_surface": "chrome:control-chrome",
  "tab_status": "submitted_audit",
  "video_upload_status": "accepted",
  "cover_upload_status": "accepted",
  "submission_status": "submitted",
  "submission_evidence": ["稿件管理", "已提交审核"],
  "field_verification": {
    "title": "matched",
    "description": "matched",
    "category": "知识",
    "creation_declaration": "含AI生成内容",
    "scheduled_publish_at": "matched | matched_after_rollover | not_requested"
  },
  "accepted_tags": ["外网热议", "海外视角", "中国观察", "国际观察"],
  "scheduled_publish_at": "effective ISO-8601 or null",
  "scheduled_publish_at_requested": "requested ISO-8601 or null",
  "scheduled_publish_at_effective": "effective ISO-8601 or null",
  "scheduled_publish_timezone": "Asia/Shanghai or null",
  "schedule_adjustment": {
    "applied": false,
    "reason": null,
    "from": null,
    "to": null
  },
  "cover_preview_changed": true,
  "final_submit_clicked": true,
  "blocker": null
}
```

Blocked shape:

```json
{
  "schema_version": "bilibili_upload_draft_report.v1",
  "skill_name": "bilibili-video-upload-draft",
  "skill_path": "/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md",
  "skill_invocation": "direct",
  "skill_instructions_read": true,
  "status": "BLOCKED",
  "created_at": "ISO-8601",
  "project_dir": "...",
  "metadata_path": "...",
  "video_path": "...",
  "cover_path": "...",
  "chrome_surface": "chrome:control-chrome",
  "blocked_phase": "open_upload_page | video_upload | metadata_fill | cover_upload | scheduled_publish | verification | final_submit",
  "retry_count": 0,
  "visible_url": "...",
  "visible_title": "...",
  "visible_text_excerpt": "...",
  "accepted_partial_values": {},
  "final_submit_clicked": false,
  "submission_status": "not_submitted",
  "blocker": {
    "code": "CHROME_CONTROL_TOOL_UNAVAILABLE | CHROME_EXTENSION_UNAVAILABLE | FILE_URL_ACCESS_NOT_ALLOWED | BILIBILI_LOGIN_REQUIRED | SCHEDULE_IN_PAST | FIELD_DID_NOT_STICK | PAGE_CHANGED | UNKNOWN",
    "message": "human-readable blocker and exact next step"
  }
}
```

If the final button was clicked once but no success proof appeared, write a blocked report with `final_submit_clicked=true`, `submission_status="unknown"`, and do not click again.

Also write a concise Markdown report with the same status, paths, accepted fields, final submission evidence, blocker, and next step. The Markdown report is for human review; the JSON report is the parent skill gate input.

## Browser Finalization

Finalize Chrome with the upload/result tab kept as `handoff` for audit. Do not close a tab that may contain success evidence or a post-submit warning.

```js
await browser.tabs.finalize({
  keep: [{ tab, status: "handoff" }]
});
```

Report the live tab state and the paths used. Never close a tab containing an in-progress or just-submitted Bilibili upload unless the user explicitly asks.
