---
name: archive-is-real-chrome-capture
description: "暂时不可用的网页存档抓取流程归档。仅当用户明确要求尝试 archive.is/archive.today/archive.ph/archive.md 等网页存档镜像、并明确接受真实 Chrome 中可能出现验证码或安全验证时使用；用于通过用户主 Google Chrome 的 Chrome Extension 搜索原文 URL、打开快照候选、保存截图和 chrome_proof 审计。不要被选题流程隐式调用。"
---

# Archive.is Real Chrome Capture

## 暂时不可用

当前网页存档镜像经常在真实 Chrome 中返回 CAPTCHA / security check，导致无人值守流程不可稳定使用。

默认不要调用本 skill。只有用户明确要求“试一下 archive / archive.is / archive.today / archive.ph / archive.md / 网页快照”，并接受以下限制时，才可以运行：

```text
1. 不保证能拿到正文。
2. 不自动破解 CAPTCHA、reCAPTCHA、Turnstile 或安全验证。
3. 遇到验证码只记录 captcha_blocked，然后停止该路径或切换镜像。
4. 不绕过付费墙，不读取本地 Cookie、Local Storage、Session、Preferences、Login Data 等 Chrome profile 内部文件。
5. 必须使用用户正在使用的主 Google Chrome，通过 Chrome Extension 控制；不得使用临时浏览器、CDP remote debugging 或新 profile。
```

## 输入

调用时应提供：

```text
url: 原始文章 URL，必填
title: 文章标题，可选但强烈建议提供
target_date: YYYY-MM-DD，可选，用于输出目录
out_dir: 可选；默认 /Users/wangfangjia/code/china_airtle/outputs/archive_real_chrome_capture/{target_date_or_run_id}/
max_snapshot_candidates: 默认 3
```

## 真实 Chrome 入口

本 skill 的“真实 Chrome”只指用户正在使用的主 Google Chrome，由 Chrome Extension / `chrome:control-chrome` 控制。

禁止作为合格抓取路径：

```text
chrome-cdp-*
--browser-cdp
remote-debugging-port
Playwright/Chromium 新 profile
capture-chrome-profile / .capture-chrome-profile
auto-launched Chrome
temporary browser profile
读取 Chrome profile 内部 Cookie 或存储文件
```

固定会话信息：

```text
session_name: user_real_chrome_default
access_surface: chrome:control-chrome / Chrome Extension
browser_client: /Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.611.62324/scripts/browser-client.mjs
```

如果当前工具面没有 `mcp__node_repl__js` / `node_repl js`，先使用 `tool_search` 搜索 `node_repl js`。不要因为没有名为 `chrome` 的 namespace 就判断 Chrome 不可用。

固定 bootstrap：

```js
const { setupBrowserRuntime } = await import('/Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.611.62324/scripts/browser-client.mjs');
await setupBrowserRuntime({ globals: globalThis });
globalThis.browser = await agent.browsers.get('extension');
await browser.nameSession('user_real_chrome_default');
nodeRepl.write(await browser.documentation());
```

连接后必须确认真实 Chrome 标签：

```js
const openTabs = await browser.user.openTabs();
nodeRepl.write(JSON.stringify(openTabs.slice(0, 20), null, 2));
```

如果 `browser.user.openTabs()` 成功返回用户当前 Chrome 标签页，即视为具备真实 Chrome 工具面。

只有以下情况实际发生并写入审计后，才允许报告 Chrome Extension 不可用：

```text
tool_search 搜索 node_repl js 后仍没有可用 js 工具
browser-client 绝对路径不存在
bootstrap 抛出 Chrome Extension 连接失败
agent.browsers.get("extension") 失败
browser.user.openTabs() 失败，且按 chrome troubleshooting 重试后仍失败
```

## 镜像轮换

按顺序尝试：

```text
https://archive.is/
https://archive.today/
https://archive.ph/
https://archive.md/
```

每个镜像最多做：

```text
1. 原文 URL 查询。
2. 通配快照查询。
3. 从当前运行发现的快照结果中打开最多 max_snapshot_candidates 个候选。
```

不要直接使用历史记忆中的短快照 URL 作为成功证据；短快照 URL 必须来自当前运行的镜像搜索结果页，或来自用户在本轮明确提供的 URL。

## 操作流程

1. 创建输出目录。
2. 连接真实 Chrome 并读取完整 browser documentation。
3. 调用 `browser.user.openTabs()`，优先 claim 已打开的网页存档标签；没有合适标签时新建标签。
4. 对每个镜像打开搜索入口或 URL 查询页。
5. 页面稳定后读取：
   - tab title
   - tab URL
   - 可见文本长度和粗略 word count
   - 是否包含标题或原始 URL
   - 是否出现 CAPTCHA / security check / human verification
   - 页面中的快照候选链接
6. 如果出现 CAPTCHA 或安全验证：
   - 记录 `captcha_blocked`
   - 保存截图
   - 不刷新循环
   - 切换下一个镜像或结束
7. 如果出现快照候选：
   - 打开最多 `max_snapshot_candidates` 个
   - 检查标题/主题一致性
   - 检查正文是否不是登录页、付费墙、验证码页、导航页、评论区或搜索页
   - 粗略计数正文长度
8. 如果成功，保存正文材料、manifest、截图和 chrome proof。
9. 最终必须保留一个可见 Chrome tab 作为 handoff，停在最后一次有效源站页、搜索结果页或快照页。
10. 调用 `browser.tabs.finalize({ keep })`，只保留必要 handoff/deliverable tab。

## 成功标准

只有同时满足以下条件，才可标记成功：

```text
retrieval_success = true
retrieval_method = user_chrome_archive_search 或 archive_capture
resolved_url 是当前运行发现或用户本轮提供的网页存档快照
local_path 存在且正文可读
manifest_path 存在
chrome_proof.json 存在
screenshot_path 存在
正文不是登录页、付费墙、验证码页、网页存档搜索页、评论区或导航页
正文长度优先 >= 1200 words，最低 >= 800 words，或可见英文字符 >= 4500
标题/正文主题与目标文章一致
```

如果只拿到摘要、metadata、验证码页、搜索页、订阅页或导航页，必须标记失败或 partial，不得伪报成功。

## 审计产物

建议输出：

```text
archive_capture_audit.json
chrome_proof.json
screenshots/*.png
captures/<slug>.txt          # 仅成功时
manifests/<slug>.json        # 仅成功时或 partial 时
```

`chrome_proof.json` 至少包含：

```json
{
  "tab_id": "...",
  "tab_title": "...",
  "tab_url": "...",
  "capture_method": "archive_mirror_rotation via real Chrome Extension",
  "is_archive_search": true,
  "manifest_path": "...",
  "screenshot_paths": ["..."]
}
```

`archive_capture_audit.json` 至少包含：

```json
{
  "input_url": "...",
  "input_title": "...",
  "checked_at": "ISO-8601",
  "access_surface": "Chrome Extension / user_real_chrome_default",
  "mirrors": [
    {
      "mirror": "archive.is",
      "attempts": [
        {
          "kind": "direct_url_lookup",
          "requested_url": "...",
          "resolved_url": "...",
          "title": "...",
          "word_count": 0,
          "text_length": 0,
          "captcha_signals": true,
          "likely_article_signals": false,
          "candidate_count": 0,
          "screenshot_path": "..."
        }
      ],
      "snapshot_candidates": [],
      "snapshot_attempts": [],
      "final_status": "captcha_or_security_blocked_no_snapshot_candidates"
    }
  ]
}
```

## 最终回复

最终回复用中文，简明说明：

```text
1. 哪些镜像尝试过。
2. 是否拿到可验证正文。
3. 如果失败，失败类型：captcha_blocked / no_snapshot_candidates / snapshot_body_too_short / page_not_article / blocked_real_chrome_unavailable。
4. audit、chrome_proof、截图、正文和 manifest 路径。
5. 哪个 Chrome 标签保留给用户查看。
```

不要粘贴第三方文章全文。
