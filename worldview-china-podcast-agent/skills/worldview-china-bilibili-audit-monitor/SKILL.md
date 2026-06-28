---
name: worldview-china-bilibili-audit-monitor
description: "Check Bilibili post-submission audit status for Worldview China podcast/video runs, including the 10-minute retry loop after SUBMITTED reports, extraction of returned/rejected issue details from Bilibili Creator Center, and writing audit monitor reports/rejection lessons that drive repair and resubmission."
---

# Worldview China Bilibili Audit Monitor

This skill monitors the Bilibili audit state after `bilibili-video-upload-draft` has submitted a Worldview China episode. It does not upload, repair, or resubmit video files. It classifies the current Bilibili state and, when a稿件 is returned, extracts the platform issue details needed by the parent workflow to repair the episode.

## Inputs

Prefer a project directory containing `bilibili_upload_draft_report.json`:

```text
<episode_or_run_dir>/bilibili_upload_draft_report.json
<episode_or_run_dir>/bilibili_upload_metadata.json
```

If no project directory is given, require at least one of:

```text
bvid
bilibili_progress_url
bilibili_upload_draft_report.json
```

The upload report is the source of truth for `bvid`, `bilibili_progress_url`, title, video path, and submission evidence. If the report lacks `bvid`, open the success/progress tab or manuscript management page and resolve the newest稿件 matching the submitted title.

## Browser Boundary

Use the same browser boundary as Bilibili upload:

- Read `/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md` before opening Bilibili.
- Read the installed Chrome `control-chrome` skill and use the user's real Chrome extension session through `node_repl`; do not use the in-app browser, temporary Chrome profiles, or standalone Playwright.
- Do not click final publish/upload controls here. This skill only checks status and opens issue detail pages.
- Keep the final audit/progress tab open as `handoff` when browser work ends.

## Monitor Loop

Default mode is `monitor_after_submission`:

1. Confirm the upload report has `status="SUBMITTED"` and final submit evidence. If not, write `status="BLOCKED"` with `blocked_phase="precondition"` and enough evidence for the parent workflow to return to 11 upload/final-submit recovery; this monitor node stops because it cannot classify an unsubmitted稿件, but the parent workflow must not end.
2. Wait 10 minutes after the recorded submission time or, if the submission time is already more than 10 minutes ago, check immediately.
3. Open the progress URL:

   ```text
   https://member.bilibili.com/platform/upload-manager/archive-process?bvid=<BVID>
   ```

4. Classify status:
   - `APPROVED`: visible text indicates audit passed, published, visible, or no longer under review/returned.
   - `REVIEWING`: visible text includes `稿件审核 进行中`, `审核中`, `待审核`, `处理中`, or equivalent.
   - `RETURNED`: visible text includes `已退回`, `不予审核通过`, `稿件问题`, `查看问题`, `违规时间点`, or equivalent.
   - `UNKNOWN`: page is loaded but evidence is ambiguous.
   - `BLOCKED`: login/captcha/network/Chrome problem prevents checking.
5. If `APPROVED`, write report and stop.
6. If `REVIEWING` on the first check, wait another 10 minutes and check once more.
7. If the second check is still `REVIEWING`, write `status="REVIEW_PENDING_AFTER_MAX_CHECKS"` and stop. This is an acceptable terminal state for the parent workflow; do not keep polling forever.
8. If any check returns `RETURNED`, immediately extract issue details, write reports and rejection lessons, and return `status="RETURNED_NEEDS_REPAIR"`.

`max_checks` defaults to `2`; `check_interval_minutes` defaults to `10`. Do not exceed these defaults unless the user explicitly requests a longer monitor.

When a Codex automation supports thread wakeups, prefer scheduling a wakeup for each 10-minute check instead of a fragile long-running browser session. If no wakeup mechanism is available in the current tool surface, a controlled local wait is acceptable, but still write heartbeat lines to the monitor report.

## Returned Issue Extraction

On `RETURNED`, capture the details from the Bilibili issue/progress page. If the page has `查看问题`, `稿件问题`, `修改视频`, or similar controls, open the problem detail view but do not submit an appeal.

Extract and record:

- `bvid`
- current URL and page title
- manuscript title if visible
- platform status text, such as `已退回`
- platform summary, especially lines like `根据相关法律法规、政策及《社区公约》，该视频不予审核通过`
- all rejected timepoints, preserving exact strings such as `P1(00:15:19-00:15:45)`
- violation position, such as `P1内容`
- modification suggestion
- policy category headings visible on the page, such as `关于法律法规`, `关于国家宗教政策`, `关于恐怖主义`
- the raw issue text excerpt needed for repair, capped to a concise excerpt; do not dump the whole page

If the platform issue text is long, keep enough surrounding context to identify the rule family and the rejected windows, but avoid copying full policy pages.

## Reports

Write JSON and Markdown reports under:

```text
<project_dir>/11c-bilibili-audit-monitor/bilibili_audit_monitor_report.json
<project_dir>/11c-bilibili-audit-monitor/bilibili_audit_monitor_report.md
```

Also update the upload report with audit-monitor evidence when practical, without deleting the original submission evidence.

JSON shape:

```json
{
  "schema_version": "worldview_china_bilibili_audit_monitor.v1",
  "status": "APPROVED | REVIEWING | REVIEW_PENDING_AFTER_MAX_CHECKS | RETURNED_NEEDS_REPAIR | UNKNOWN | BLOCKED",
  "created_at": "ISO-8601",
  "project_dir": "/absolute/path",
  "bvid": "BV...",
  "title": "投稿标题",
  "check_interval_minutes": 10,
  "max_checks": 2,
  "checks": [
    {
      "check_index": 1,
      "checked_at": "ISO-8601",
      "url": "https://member.bilibili.com/platform/upload-manager/archive-process?bvid=...",
      "classification": "REVIEWING",
      "visible_status_text": "稿件审核 进行中"
    }
  ],
  "returned_issue": {
    "platform_status": "已退回",
    "issue_summary": "根据相关法律法规、政策及《社区公约》，该视频不予审核通过",
    "rejected_timepoints": ["P1(00:15:19-00:15:45)"],
    "violation_position": "P1内容",
    "policy_categories": ["关于法律法规"],
    "modification_suggestion": "建议对涉及内容进行修改或删除...",
    "issue_text_excerpt": "..."
  },
  "repair_required": true,
  "blocker": null
}
```

For non-returned statuses, set `returned_issue=null` and `repair_required=false`.

## Rejection Lessons

When status is `RETURNED_NEEDS_REPAIR`, append the issue to:

```text
<project_dir>/04c-bilibili-text-compliance/platform_rejection_lessons.json
<project_dir>/04c-bilibili-text-compliance/platform_rejection_lessons.md
```

The lesson entry must include:

- `created_at`
- `bvid`
- `rejected_timepoints`
- `platform_issue_summary`
- `policy_categories`
- `issue_text_excerpt`
- `repair_guidance_for_parent`

The parent workflow must feed this file into the next 03d/03b/04c review. Do not rely on conversation memory.

## Known Worldview China Rejection Patterns

Use these as static recall patterns while interpreting new returned issues:

- 2026-06-25/26 religion-policy rejection: A Bilibili rejection at `00:32:26-00:32:38` was caused by a broader chain around `00:31:13-00:33:37`, not just the 12-second window. The chain involved 新疆维吾尔自治区, Middle East state positioning, 刘晓波, 萨德, 九一一, 卡舒吉, Sunni Muslim world leadership, and the relationship between Uyghurs and Turkey. Treat similar chains as requiring full-context cut/bridge.
- 2026-06-26 legal/community rejection: Bilibili returned `P1(00:15:19-00:15:45)` and `P1(00:19:11-00:19:37)` after the first repair. The risk was a continuous geopolitical chain about China's mediator role, local actors not trusting or relying on China for urgent security issues, US counter-influence, and overseas-base ambitions. Treat similar chains as full-context cut/bridge risks, not keyword replacement tasks.

## Blocked Or Unknown Evidence

`BLOCKED` and `UNKNOWN` are diagnostic states, not parent workflow terminal states. Before returning either status, capture enough evidence for recovery:

- Missing `bvid` / progress URL: record which upload report fields were missing and whether the success page or稿件管理 list was checked.
- Ambiguous page state: record visible status text, URL, title, screenshot path if available, and why it did not match APPROVED/REVIEWING/RETURNED.
- Login/captcha/network/Chrome issue: record the exact browser condition and keep the tab open.

The parent workflow should then recover by reopening the progress URL or稿件管理 page, resolving `bvid` by title/submission time, restoring the real Chrome session, and retrying classification. Only when those recovery paths fail should it ask the user for intervention.

## Parent Workflow Contract

Return one of these outcomes to the caller:

- `APPROVED`: parent can finish normally.
- `REVIEW_PENDING_AFTER_MAX_CHECKS`: parent can finish with audit still pending after two checks.
- `RETURNED_NEEDS_REPAIR`: parent must repair, rerun final QA/text compliance as needed, resubmit through `bilibili-video-upload-draft`, then call this monitor loop again from a fresh submission time.
- `BLOCKED` or `UNKNOWN`: parent must first run audit recovery using the blocker evidence above; if recovery still cannot classify the稿件, report the exact blocker and keep the progress tab open.
