---
name: selection-article-chinese-markdown
description: "每日中国选题文章中文 Markdown 子 skill。Use when Codex needs to reuse the local article selected by the daily China article selection workflow under /Volumes/GT34/daily_china_article_video, prefer today's 5pm run output and fall back to the previous day, locate the selected English article.txt or capture text, and produce a faithful Chinese Markdown translation based on the original article rather than a single-host script, podcast script, commentary, summary, or derivative explainer."
---

# Selection Article Chinese Markdown

把每日中国选题 workflow 已选中的英文文章材料转成中文 Markdown 译文。不要生成口播稿，不要写导读评论，不要读取 `single_host_script.md` 或 `podcast_script.md` 作为正文来源。

## Locator Script

优先运行：

```bash
python3 /Users/wangfangjia/.codex/skills/daily-important-info-digest/skills/selection-article-chinese-markdown/scripts/find_selected_article.py --run-date YYYY-MM-DD
```

不传 `--run-date` 时脚本使用当前 Asia/Shanghai 日期。

脚本查找顺序：

1. `/Volumes/GT34/daily_china_article_video/<run_date - 1 day>_china_viral/`
2. `/Volumes/GT34/daily_china_article_video/<run_date - 2 days>_china_viral/`

这是为了匹配 5 点 daily 选题任务：当天 5 点默认选择“昨天”的 China Viva 文章；6 点 digest 优先复用这次产物。如果第一项不存在或材料缺失，再退回前一天选题产物。

## Article Source Priority

脚本返回的 `article_text_path` 是唯一正文来源。定位时优先级为：

1. daily 总控标准化后的 `articles/article_*/source/article.txt`。
2. `orchestration_manifest.json` 中记录的 `article_package_dir/source/article.txt`。
3. `selection/selection-decision.json.capture_output_path`。
4. `selection/ranked-top5.json` 中 selected candidate 的 `capture_output_path`。

如果只找到 `single_host_script.md` 或 `podcast_script.md`，视为失败；这些是视频脚本，不是原文。

## Output

默认 `output_dir` 由上游传入日期目录：

```text
/Users/wangfangjia/随记/晨间科技新闻/<run_date>/
```

写入：

```text
<output_dir>/
  02_中国选题_<中文标题>.md
  _meta/
    selection_article_manifest.json
```

不要创建 `china_selection/` 子目录放文章。文章 Markdown 必须直接在日期目录顶层。文件名必须使用中文标题，不要使用英文 slug；保留必要英文专名和缩写。文件名前缀由上游根据 AI 文章数量决定：

```text
02_中国选题_<中文标题>.md
```

`_meta/selection_article_manifest.json` 至少包含：

```json
{
  "status": "success | skipped_not_found | skipped_copyright_boundary | failed",
  "translation_status": "translated | skipped_incomplete_source | skipped_copyright_boundary | failed",
  "run_date": "YYYY-MM-DD",
  "selected_target_date": "YYYY-MM-DD",
  "selection_decision_path": "...",
  "article_text_path": "...",
  "article_metadata_path": "... optional",
  "title_original": "...",
  "title_zh": "...",
  "source": "...",
  "original_url": "...",
  "markdown_path": "..."
}
```

## Markdown Structure

```markdown
# 中文标题

> 原题：...
> 来源：...
> 作者：...
> 发布日期：...
> 原文：...
> 本地英文材料：...

## 中文译文

（按原文段落顺序翻译。若原文有小标题，保留对应层级并翻译标题。）
```

译文必须基于 `article_text_path` 的英文原文，不得基于口播稿改写。不要添加 `为什么今天值得读`、`关键事实与数字`、`文章的核心判断`、`对中国读者的意义` 或任何额外评论栏目。

翻译要求：

- 保持原文结构、段落顺序、事实边界和语气。
- 中文表达要自然，允许为中文语序调整句式，但不得增删论点。
- 文章需要保持原文不变的进行翻译。不要用二创稿替代。

## Missing Selection

如果今天和前一天的选题产物都找不到：

- 不要联网重新选题。
- 写 `_meta/selection_article_manifest.json`，`status="skipped_not_found"`。
- 在上游 report 中写明已检查的目录。

## Final Response

返回 selection target date、英文材料路径、日期目录顶层 Markdown 路径或跳过原因、`_meta/selection_article_manifest.json` 路径。
