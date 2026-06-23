---
name: daily-china-article-to-podcast-video
description: "每日英文外刊到中文单人口播解释视频的总控 skill。先计算 target_date（默认 Asia/Shanghai 昨天），显式传给 china-longform-article-selection，生成已通过正文可获取性门禁的 China Viva Top 5 候选；读取子 skill 自动推荐的最高分候选和本地文章材料，自动写 selection-decision.json 与 selected registry，然后标准化 article package，调用 english-article-chinese-single-host-video 生成中文单人口播解释视频并准备 B 站草稿。"
---

# Daily China Article To Podcast Video

这是“每日外刊中国选题到视频”的总控 skill。Skill 名称保留历史兼容，但从当前版本开始，后半段只走 `english-article-chinese-single-host-video` 单人口播解释视频主线，不再调用旧双人播客生产链路。

当前版本是**全自动可用正文候选版**：自动化负责选题排名、正文可获取性门禁、最高分候选选择、文章包标准化和后续视频流程。默认不等待人类选择；只有用户明确要求覆盖候选时，才改用用户指定文章。

```text
Phase 1: china-longform-article-selection -> 已通过正文可获取性门禁的 Top 5 候选 + 自动最佳候选
Phase 2: AUTO_SELECT_BEST_ARTICLE
Phase 3: 使用自动选择候选的本地材料标准化 article package
Phase 4: 可选中文阅读 Markdown
Phase 5: english-article-chinese-single-host-video -> 单人口播解释视频 + Bilibili upload draft handoff
```

不要把后半段视频生产逻辑复制到这里。这里负责目标日期、选题调用、自动选择门、文章包标准化、排期上下文和下游 skill 串联。

## 依赖 Skill

按需读取并调用：

1. `/Users/wangfangjia/.codex/skills/china-longform-article-selection/SKILL.md`
   - 负责按唯一 `china_viral` 模式筛选外部传入 `target_date` 的中国爆款候选 Top 5。
   - 当前版本会为可能进入 Top 5 的候选执行正文可获取性门禁，并自动写出最高分候选的 `selection-decision.json`；Daily 总控读取该结果继续制作。
2. `/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/SKILL.md`
   - 负责从本地英文文章文件生成完整中文单人口播解释视频，并在用户真实 Chrome 中准备 B 站投稿草稿。
   - 它只接受本地文章文件路径，不接受 URL。
3. `/Users/wangfangjia/.codex/skills/page-to-chinese-markdown/SKILL.md`
   - 可选：为审稿生成中文阅读 Markdown。
4. `/Users/wangfangjia/.codex/skills/bilibili-video-upload-draft/SKILL.md`
   - 下游视频完成后用于准备 B 站投稿草稿。

## 总原则

```text
1. 自动化运行时，必须完成已通过正文可获取性门禁的 Top 5 候选排名，并自动选择评分最高候选继续。
2. 选题阶段允许并要求按 `china-longform-article-selection` 调用 `url-page-capture` 或合法公开同文转载源门禁；不要绕过验证码、登录墙或付费墙。
3. 默认选择 `ranked-top5.json.recommended_best_candidate_id`；如果该字段缺失但 `top_candidates[0]` 已通过 gate，则选择 `top_candidates[0].candidate_id`。
4. 自动选择后写 `selection/selection-decision.json`，并写 selected registry，`selection_actor="agent"`。
5. 优先使用自动选择候选记录的 `capture_output_path` / 本地材料路径创建本地文章包并进入视频生产。
6. 对第三方外刊，不在聊天里粘贴全文或全文翻译。
```

如果用户请求中已经同时提供：

```text
候选覆盖选择（例如 A3）
候选自带可用材料，或用户额外提供的本地 article.txt 路径/完整英文正文
```

则用用户覆盖项替代自动最高分候选，并继续进入文章包标准化和视频生产。

## 输出根目录

每日总控目录：

```text
/Volumes/GT34/daily_china_article_video/{target_date}_china_viral/
```

其中 `target_date` 默认是 Asia/Shanghai 时区的昨天，除非用户明确指定其他日期。

建议结构：

```text
/Volumes/GT34/daily_china_article_video/{target_date}_china_viral/
  selection/
    source-shortlist.json
    ranked-top5.json
    selection-decision.json
    selection-result.md
    selection-request.md optional compatibility alias
    final-report.md
    captures/
    manifests/
    legal-source-checks/
  articles/
    article_01_<slug>/
      source/
        article.txt
        source_metadata.json
        reading_doc.md optional
      production_pointer.json
  videos/
    <article_slug>_<YYYYMMDD_HHMMSS>_single_host_video/
      video_pointer.json
  orchestration_manifest.json
  orchestration_report.md
```

`english-article-chinese-single-host-video` 自身默认输出根目录仍是：

```text
/Volumes/GT34/english_aircle_to_video
```

单人口播视频 skill 每次会创建带时间戳的独立项目目录，例如 `<article_slug>_<YYYYMMDD_HHMMSS>_single_host_video/`。不要把完整视频工程复制到 daily 目录。daily 目录下的 `videos/.../video_pointer.json` 只记录实际视频工程指针。

## Phase 1: 计算目标日期并生成 Top 5

默认目标日期：

```text
target_date = Asia/Shanghai 的昨天
```

调用边界：

```text
1. Daily 总控负责决定日期。用户未指定日期时，默认 target_date = Asia/Shanghai 的昨天。
2. 如果用户在当前请求中指定其他日期，Daily 总控必须先解析为绝对 YYYY-MM-DD，并用该日期覆盖默认昨天。
3. 调用 china-longform-article-selection 时必须显式传入 target_date、target_timezone=Asia/Shanghai、selection_mode=china_viral、requested_count=5。
4. 不得依赖 china-longform-article-selection 自行默认昨天；该子 skill 缺少 target_date 时应返回 NEEDS_TARGET_DATE。
5. 所有 run_dir、selection artifact 和排期计算都必须使用同一个解析后的 target_date。
```

要求：

- 使用唯一 `selection_mode=china_viral`。
- 使用选题 skill 的白名单来源。
- 每个来源最多 1 篇。
- 排除短讯和过短资讯。
- 先用标题、摘要、metadata、搜索结果片段、公开可见片段评分，再执行正文可获取性门禁。
- 输出 Top 5 候选时，每篇必须 `material_available=true`。
- 允许选题 skill 调用 `url-page-capture` 做真实 Chrome / archive 快照抓取；Bloomberg、New York Times、Wall Street Journal 原站不可读时必须改找合法公开同文转载源，找不到则不能入选。
- 每篇必须有中文标题、英文原题、来源、原文 URL、材料来源、本地材料路径、材料 manifest 路径、中文简述、推荐理由、评分和排名依据。

把选题产物复制或记录到：

```text
selection/source-shortlist.json
selection/ranked-top5.json
selection/selection-decision.json
selection/selection-result.md
selection/selection-request.md optional compatibility alias
selection/final-report.md
```

## Phase 2: Auto Selection Gate

自动化不得在这里停止，除非没有任何候选通过正文可获取性门禁。

必须写出：

```text
selection/selection-decision.json
orchestration_manifest.json
orchestration_report.md
```

状态：

```text
AUTO_SELECTED_ARTICLE
```

默认选择规则：

```text
1. 优先读取 selection/selection-decision.json。
2. 如果子 skill 尚未写 selection-decision.json，但 ranked-top5.json 有 recommended_best_candidate_id，则用该 ID 创建 selection-decision.json。
3. 如果 recommended_best_candidate_id 缺失，但 top_candidates[0] 已满足 material_available=true 且本地材料存在，则用 top_candidates[0] 创建 selection-decision.json。
4. 如果候选材料路径不存在、manifest 不存在、或 material_available=false，则不得自动选择，状态写 FAILED_SELECTION_MATERIAL_UNAVAILABLE。
```

`selection-decision.json` 结构：

```json
{
  "target_date": "YYYY-MM-DD",
  "selection_mode": "china_viral",
  "workflow_status": "AUTO_SELECTED_BEST_CANDIDATE",
  "selected_at": "ISO-8601",
  "selection_actor": "agent",
  "selection_policy": "highest score among material_available candidates",
  "selected_candidate_id": "A1",
  "selected_rank": 1,
  "selected_score": 93,
  "selected_title_zh": "...",
  "selected_title_original": "...",
  "selected_source": "...",
  "selected_original_url": "...",
  "selected_material_source_url": "...",
  "capture_output_path": "...",
  "capture_manifest_path": "...",
  "material_manifest_path": "...",
  "legal_source_manifest_path": "... only when applicable",
  "selection_reason": "最高分且已通过正文可获取性门禁"
}
```

如果用户同时提供新的完整正文或本地 `article.txt` 路径，可以用用户材料覆盖自动候选材料，但必须在 `selection-decision.json` 记录 override 来源，并将 `selection_actor` 设为 `user`。

自动选择后写 selected registry：

```text
/Volumes/GT34/daily_china_article_video/selection_state/china_viral/{target_date}.json
```

registry 条目应记录自动选择：

```json
{
  "article_key": "sha256:...",
  "selected_sequence": 1,
  "selected_at": "ISO-8601 with +08:00",
  "selection_actor": "agent",
  "title_en": "...",
  "title_zh": "...",
  "source": "...",
  "url": "...",
  "score": 88,
  "viral_score": 88,
  "retrieval_method": "original_public_open | archive_capture_success | legal_republication_success | human_override",
  "local_path": "...",
  "status": "selected_material_available"
}
```

如果同一目标日期已有 registry 条目，`selected_sequence` 使用下一个整数。

## Publish Schedule Policy

Daily 总控负责把 registry 中的 `selected_sequence` 转换成 B 站定时发布时间，并在调用下游 `english-article-chinese-single-host-video` 时把排期作为上下文传入。

排期规则固定为 Asia/Shanghai：

```text
china_viral selected_sequence 1 -> 11:00
china_viral selected_sequence 2 -> 17:00
china_viral selected_sequence >= 3 -> 17:00 之后每篇顺延 2 小时，且不得生成过去时间
```

动态日期必须按实际写入排期时的 Asia/Shanghai 当前时间计算，不使用 `target_date` 作为发布日期：

```text
now = 当前 Asia/Shanghai 时间
slot_time = selected_sequence 对应的 HH:MM
candidate = now 的本地日期 + slot_time
if now < candidate:
  scheduled_publish_at = candidate
else:
  scheduled_publish_at = candidate + 1 day
```

也就是说：如果现在还没到当天 11:00 / 17:00，就排当天 11:00 / 17:00；如果已经到达或超过该 slot，就排下一天同一 slot。`selected_sequence >= 3` 的顺延 slot 也必须经过同样的“未来时间”检查。不得生成过去时间。

调用视频 skill 前，必须传入：

```json
{
  "scheduled_publish_at": "ISO-8601 timestamp with +08:00 offset",
  "scheduled_publish_timezone": "Asia/Shanghai",
  "schedule_source": "daily-china-article-to-podcast-video selection_mode=china_viral target_date=YYYY-MM-DD selected_sequence=N slot=HH:MM dynamic_next_occurrence"
}
```

## Phase 3: 文章包标准化

把被选候选的文章材料标准化成单人口播视频 skill 可接受的本地英文文章包。

必须输出：

```text
articles/article_<nn>_<slug>/source/article.txt
articles/article_<nn>_<slug>/source/source_metadata.json
```

`article.txt`：

- 只放可供视频流程读取的英文文章材料。
- 保留英文原文标题和正文。
- 不要把中文简述或分析混入正文。
- 默认从被选候选的 `capture_output_path` / 本地材料路径复制或规范化到当前 article package。
- 如果用户粘贴的是全文，在本地保存为 `article.txt` 并记录为 `human_override`。
- 如果用户给的是本地路径，可以复制或规范化到当前 article package，并记录为 `human_override`。

`source_metadata.json` 至少包含：

```json
{
  "publication": "Financial Times",
  "article_title": "English title",
  "article_title_zh": "中文标题",
  "author": "...",
  "published_date": "YYYY-MM-DD",
  "source_url": "https://...",
  "fulltext_status": "original_public_open | archive_capture_success | legal_republication_success | human_override",
  "capture_provider": "url-page-capture | human",
  "capture_method": "url-page-capture actual method | human_override",
  "material_source_url": "https://...",
  "capture_output_path": "...",
  "capture_manifest_path": "...",
  "legal_source_manifest_path": "...",
  "material_manifest_path": "...",
  "selection_id": "A1",
  "target_date": "YYYY-MM-DD"
}
```

如果 `article.txt` 不存在、太短、不是目标文章、或主题和候选文章不一致，不得进入视频生产。

## Phase 4: 可选中文阅读 Markdown

默认可以为被选文章生成一个审稿辅助件：

```text
articles/article_<nn>_<slug>/source/reading_doc.md
```

使用 `page-to-chinese-markdown`。

注意：

- 对第三方外刊，默认生成中文阅读文档/结构化笔记，不做全文逐字翻译。
- 这个文件帮助审稿，不作为 `english-article-chinese-single-host-video` 的硬输入。
- 视频生产仍以英文 `article.txt` 和 `source_metadata.json` 为准。

## Phase 5: 单篇视频生产

对通过文章包 gate 的文章，调用：

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video/SKILL.md
```

输入是：

```text
articles/article_<nn>_<slug>/source/article.txt
```

调用上下文还必须包含 Daily 预先计算的 B 站排期。

调用前必须确认：

- `article.txt` 存在且可读。
- `source_metadata.json` 存在。
- metadata 中有 `publication`、`article_title`、`source_url`。
- metadata 中有 `fulltext_status`、`capture_provider`、`capture_method`、`material_manifest_path`。
- `fulltext_status` 为 `original_public_open`、`archive_capture_success`、`legal_republication_success` 或 `human_override`。

视频生产输出位置必须遵循 `english-article-chinese-single-host-video` 的固定项目目录规则：

```text
/Volumes/GT34/english_aircle_to_video/<article_slug>_<YYYYMMDD_HHMMSS>_single_host_video/
```

Phase 5 完成后，在 daily 总控目录只写 pointer：

```text
articles/article_<nn>_<slug>/production_pointer.json
videos/<article_slug>_<YYYYMMDD_HHMMSS>_single_host_video/video_pointer.json
```

## Orchestration Manifest

每次运行都写：

```text
orchestration_manifest.json
orchestration_report.md
```

建议字段：

```json
{
  "target_date": "YYYY-MM-DD",
  "selection_mode": "china_viral",
  "run_dir": "/Volumes/GT34/daily_china_article_video/YYYY-MM-DD_china_viral",
  "status": "AUTO_SELECTED_ARTICLE | READY_FOR_VIDEO | RUNNING_VIDEO | COMPLETE | PARTIAL | FAILED | FAILED_SELECTION_MATERIAL_UNAVAILABLE",
  "selection_outputs": {
    "source_shortlist": "...",
    "ranked_top5": "...",
    "selection_decision": "...",
    "selection_result": "...",
    "selection_request": "... optional compatibility alias",
    "final_report": "..."
  },
  "selection_decision": {
    "selection_actor": "agent",
    "selected_candidate_id": "A1",
    "selection_reason": "highest score among material_available candidates",
    "capture_output_path": "..."
  },
  "publish_schedule": {
    "timezone": "Asia/Shanghai",
    "slot_policy": {
      "selected_sequence_1": "11:00",
      "selected_sequence_2": "17:00",
      "selected_sequence_3_plus": "17:00 plus 2 hours per additional selected_sequence",
      "rollover": "if current Asia/Shanghai time has reached or passed the slot, use next day same slot"
    },
    "computed_at": "ISO-8601 timestamp with +08:00 offset",
    "slot_time": "HH:MM",
    "scheduled_publish_at": "ISO-8601 timestamp with +08:00 offset"
  },
  "articles": [
    {
      "selection_id": "A1",
      "title_en": "...",
      "title_zh": "...",
      "source_url": "...",
      "article_material_status": "AVAILABLE_FROM_SELECTION | PROVIDED_BY_USER | INVALID",
      "article_package_dir": "...",
      "video_status": "SUCCESS | FAILED | NOT_STARTED",
      "video_project_dir": "...",
      "single_host_script_path": "...",
      "final_video_path": "...",
      "bilibili_upload_metadata_path": "...",
      "bilibili_upload_draft_report_path": "...",
      "scheduled_publish_at": "ISO-8601 timestamp with +08:00 offset"
    }
  ]
}
```

## Gate Summary

```text
Gate 1 Selection Ranking:
  selection/ranked-top5.json exists
  selection/selection-decision.json exists
  selection/selection-result.md exists
  selection/final-report.md exists
  candidates have title_zh, title_en, source, url, summary_zh, score
  candidates have material_available=true, capture_output_path/material path, capture_manifest_path, material_manifest_path
  legal_republication_success candidates also have legal_source_manifest_path
  workflow_status is AUTO_BEST_RECOMMENDED or equivalent

Gate 2 Auto Selection:
  selection-decision.json exists before article package creation
  selection_actor is agent unless the user explicitly overrides
  selected article count is exactly 1 unless the current user request explicitly asks for another count
  selected candidate material exists and matches selected candidate, unless user explicitly provides a human_override article

Gate 3 Article Package:
  source/article.txt exists
  source/source_metadata.json exists
  metadata contains publication/title/source_url/fulltext_status/capture_provider/capture_method/material_manifest_path
  fulltext_status is original_public_open, archive_capture_success, legal_republication_success, or human_override
  capture_provider is url-page-capture or human

Gate 4 Video:
  english-article-chinese-single-host-video completes its own gates
  single_host_script.md path recorded when available
  final video path recorded in orchestration manifest
  Bilibili metadata and upload draft report recorded when present
```

## Final Response

When complete after selected available article, respond with:

- 选中的文章。
- selection_actor=agent 或 user override，和选择记录路径。
- Top 5 简表：ID、中文标题、来源、分数、材料路径。
- 本地 article package 路径。
- 单人口播稿 `single_host_script.md` 路径。
- 视频项目目录、最终视频路径和 `bilibili_upload_metadata.json` 路径。
- `bilibili_upload_draft_report.json` 路径和上传草稿状态。
- `scheduled_publish_at` 和使用的排期规则。
- 失败阶段和原因。
