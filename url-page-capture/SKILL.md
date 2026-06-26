---
name: url-page-capture
description: Capture complete webpage information from a user-provided URL as structured page material. Use when Codex needs to fetch article/document/page content, discover archive.is/archive.today snapshots, reuse the user's real Chrome session for blocked or profile-dependent pages, or produce a capture package for a downstream translation/Markdown skill. This skill only captures and validates page material; it does not translate, summarize, or author the final document.
---

# URL Page Capture

## Goal

Given a URL, obtain reliable page material and prove whether a real page/article body was captured.

This skill ends with a **capture package**: metadata, source URLs, selected archive snapshot if any, extracted Markdown-like source material, body preview, and manifest. Do not turn the material into a final reading document here; hand it to a downstream skill such as `page-to-chinese-markdown`.

## Output Contract

Return or save a capture object with these fields when possible:

```json
{
  "success": true,
  "input_url": "https://example.com/article",
  "resolved_url": "https://archive.is/abcde",
  "capture_method": "chrome-archive-is-search",
  "title": "Article title",
  "metadata": {
    "byline": "...",
    "published_at": "...",
    "site_name": "..."
  },
  "access_limited": false,
  "source_markdown": "# Article title\n\n...",
  "source_markdown_length": 12000,
  "body_preview": "...",
  "manifest": {}
}
```

If capture fails, return a manifest with attempted URLs, statuses, exhausted fallback routes, and the final failure reason. In unattended workflows, do not require user CAPTCHA intervention as a next action.

## Strategy

1. Try HTTP capture for ordinary public pages.
2. Use the user's main Google Chrome session for anything blocked, access-limited, archive-dependent, logged-in, or profile-dependent. This means Chrome Extension / `chrome:control-chrome`, not CDP and not a new browser profile.
3. For archive.is/archive.today, always prefer the **homepage search flow in real Chrome** over naked HTTP/timemap calls.
4. Clean temporary browser profiles, auto-launched Chrome, Playwright/Chromium profiles, and one-off CDP launches are forbidden for this skill's formal workflows. They often trigger CAPTCHA and must not be accepted as successful capture evidence.

Invalid capture evidence includes any manifest or audit path containing:

```text
chrome-cdp-*
--browser-cdp
browser_cdp_url
remote-debugging-port
capture-chrome-profile / .capture-chrome-profile
auto-launched Chrome
temporary browser profile
```

## Autonomous Capture Ladder

Do not give up after one blocked attempt. For publisher articles and archive-dependent pages, run this ladder before declaring failure:

1. **HTTP/public direct**: try normal HTTP fetch or public page capture when likely open.
2. **Real Chrome direct**: open the original URL in the user's real Chrome session and extract rendered DOM.
3. **Real Chrome archive search**: search the original URL from archive.is/archive.today homepage mirrors and open snapshot links discovered in the current run.
4. **Archive mirror rotation**: try `archive.is`, `archive.today`, `archive.ph`, and `archive.md` before failing.
5. **Snapshot candidates**: if several snapshots exist, try newest first, then older snapshots until one yields readable article material.
6. **Known page variants**: when discoverable from the page or metadata, try canonical, redirected, AMP, print, or `?output=1`-style text variants only if they are public and do not require bypassing access controls.

CAPTCHA, Turnstile, reCAPTCHA, security verification, and similar challenges are not solved automatically. They are a signal to switch routes: real Chrome session, another archive mirror, another snapshot, or another public variant. Only after the ladder is exhausted should the manifest report failure.

## Entrypoint Decision

- Ordinary public page: use `scripts/capture_url_cli.mjs` or `scripts/fetch_page.py`.
- Publisher article, paywall, FT/NYT/Economist/New Yorker-style page, archive.is/archive.today, CAPTCHA-prone page, or user asks to "operate the browser": use `scripts/capture_chrome_extension.mjs` from a Chrome-capable Codex session connected to the user's main Google Chrome.
- Do not use `--browser-cdp` in formal skill workflows. If Chrome Extension / `chrome:control-chrome` is unavailable, return `BLOCKED_REAL_CHROME_UNAVAILABLE` instead of launching a new browser or using CDP.

Do not hand-code the Chrome archive flow when the script can be imported. If the flow fails, patch the skill script, then rerun it.

## Real Chrome Autonomous Capture

Use this path for FT-style articles and any archive-dependent capture.

```js
const { setupBrowserRuntime } = await import("/path/to/chrome-plugin/scripts/browser-client.mjs");
await setupBrowserRuntime({ globals: globalThis });

const chromeBrowser = await agent.browsers.get("extension");
const { captureUrlWithChromeExtension } = await import("file:///path/to/url-page-capture/scripts/capture_chrome_extension.mjs");

const result = await captureUrlWithChromeExtension({
  browser: chromeBrowser,
  originalUrl: "https://www.ft.com/content/...",
  outPath: "/tmp/page-content.txt",
  manifestPath: "/tmp/page-content.manifest.json",
  minMarkdownChars: 4000,
  maxSnapshots: 5
});
```

The script first tries direct rendered extraction in real Chrome. If that is blocked, thin, or access-limited, it opens archive mirrors in real Chrome, searches the original URL from the homepage, selects snapshot links produced by that search page, extracts the rendered article DOM, and writes both the capture text and manifest.

If an archive route shows CAPTCHA in real Chrome, do not stop there and do not ask the user to solve it in unattended workflows. Rotate mirrors and snapshots. If every route hits CAPTCHA or unusable content, return a failed manifest with the attempted routes and failure reasons.

## HTTP-Only CLI

For ordinary public pages only, use the bundled CLI with browser fallback disabled:

```bash
node /path/to/url-page-capture/scripts/capture_url_cli.mjs \
  "https://example.com/article" \
  --confirm-rights \
  --fallback none \
  --no-browser \
  --out /tmp/page-content.txt \
  --manifest /tmp/page-content.manifest.json
```

The CLI writes a plain text document, not Markdown. It also writes a JSON manifest with every attempted fallback and the selected capture method.

Formal workflow behavior:

1. HTTP fetch first.
2. If HTTP is blocked, thin, access-limited, or too short, stop this CLI path.
3. Switch to Chrome Extension real-browser capture if available, or return `BLOCKED_REAL_CHROME_UNAVAILABLE`.

Use `--include-html` only when the downstream workflow needs raw DOM HTML appended after the extracted text.

## HTTP Capture

Run the bundled HTTP helper:

```bash
python3 /path/to/url-page-capture/scripts/fetch_page.py "https://example.com/article" --archive auto --output /tmp/page-material.json
```

Accept an HTTP candidate only when:

- `ok: true`
- `access_limited: false`
- visible text is long enough for the expected page
- preview is not navigation, CAPTCHA, subscription, or archive chrome

If HTTP is blocked, thin, or noisy, switch to Chrome Extension control of the user's main Google Chrome. Do not switch to CDP or a temporary browser profile.

## Chrome Archive.is Search Flow

Use this for FT-style pages, paywalled articles with public archive copies, and cases where archive.is works in the user's browser.

Required flow:

1. Connect to Chrome plugin with `agent.browsers.get("extension")`.
2. Open or claim a real Chrome tab.
3. Import and run `scripts/capture_chrome_extension.mjs`.
4. The script first tries the original URL in real Chrome.
5. If direct capture fails, the script opens `https://archive.is/` plus known mirrors when needed.
6. It fills the archive search input (`#q`, `name=q`, or the search form input variant) with the original URL.
7. From the returned results page, select the newest short archive snapshot link produced by that page.
8. Open the selected short snapshot; if it fails, try older snapshot candidates.
9. Run `scripts/extract_dom_article.mjs` in the page context and write the capture package.

Do not directly open a pre-known short archive URL. The short snapshot URL must come from the archive.is search page in the current run.

### Reusable Chrome Script

From a Chrome-capable Codex session connected to the user's main Google Chrome:

```js
const { setupBrowserRuntime } = await import("/path/to/chrome-plugin/scripts/browser-client.mjs");
await setupBrowserRuntime({ globals: globalThis });
const chromeBrowser = await agent.browsers.get("extension");
await chromeBrowser.nameSession("URL page capture");

const tab = await chromeBrowser.tabs.new();
const { repeatArchiveIsChromeFlow } = await import("file:///path/to/url-page-capture/scripts/archive_is_chrome_flow.mjs");
const result = await repeatArchiveIsChromeFlow({
  tab,
  originalUrl: "https://www.ft.com/content/ab07b270-40ce-4cf2-a337-1b8db8baccab",
  runs: 3,
  minMarkdownChars: 4000,
  maxSnapshots: 3
});
```

`chromeBrowser.tabs.new()` here means a new tab in the user's existing main Google Chrome session, not a new browser/profile.

Treat capture as successful only if:

- every run has `manifest.success: true`
- selected snapshot URL came from the archive.is search result page
- extraction has `access_limited: false`
- `markdown_length` is large enough for the target page; 4000+ characters is acceptable for a normal FT analysis article
- preview starts with real article/document content, not share controls, archive chrome, CAPTCHA, login, or subscription UI

Use `result.last_extraction.markdown` as `source_markdown` for downstream processing.

## Direct Browser DOM Capture

If the page is already visible in Chrome, or if archive.is is not involved:

```js
const { default: extractArticleFromDom } = await import("file:///path/to/url-page-capture/scripts/extract_dom_article.mjs");
const extraction = await tab.playwright.evaluate(extractArticleFromDom);
```

Check `access_limited`, `markdown_length`, and `body_preview` before accepting the result.

## Handoff

When the user asks for a Chinese Markdown document, pass the capture package to `page-to-chinese-markdown`.
