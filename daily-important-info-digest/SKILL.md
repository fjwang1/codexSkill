---
name: daily-important-info-digest
description: "每日下午信息推送总控。Use when the user asks for a daily important information digest, daily reading pack, or morning tech news pack that combines: (1) exactly one Chinese Markdown AI industry deep-read article selected from a single standalone source article, and (2) the selected China article produced by the local daily China article selection workflow, translated into Chinese Markdown articles rather than podcast scripts."
---

# Daily Important Info Digest

生成每日中文译文阅读包。该 skill 不生产视频、不写口播稿。AI 栏目固定只选一篇单篇深度文章，优先回答“AI 产业界发生了什么、行业在讨论什么、今天最值得读的一篇是什么”。不要选择 daily roundup、listicle、Top N stories、news digest、新闻合集、专业论文、医学/学术基准测试或过细的研究细节。所有给人读的文章 Markdown 必须直接放在同一个日期文件夹下；manifest、report、抓取笔记等机器痕迹全部放进 `_meta/`。

## Output Root

固定输出到用户随记目录。不要改成临时目录：

```text
/Users/wangfangjia/随记/晨间科技新闻/<run_date>/
  01_AI技术_<中文标题>.md
  02_中国选题_<中文标题>.md optional
  _meta/
    daily_info_index.md
    daily_info_manifest.json
    daily_info_report.md
    ai_tech_manifest.json
    selection_article_manifest.json optional
    source_material/
```

开始前确认 `/Users/wangfangjia/随记/晨间科技新闻` 可创建和写入。该目录是用户明确指定的输出位置，可以使用内置盘；不要再把本工作流输出到 `/Volumes/GT34/daily_reading_digest`。

日期目录顶层必须保持干净：只放最终文章 Markdown 和 `_meta/`，不要放 JSON、抓取笔记、音频、图片、视频或临时文件。用户打开日期文件夹时，应直接看到当天两篇或三篇文章 Markdown。

## Date Policy

除非用户指定日期：

- `run_date` = 当前 Asia/Shanghai 日期。
- AI 技术文章的 `target_date` = `run_date - 1 day`，也就是“昨天发布/更新的文章”。
- 中国选题文章优先使用今天 5 点任务产物对应的 selection target date。当前 daily 选题总控默认以“昨天”为 `target_date`，所以 6 点运行时先找 `run_date - 1 day`，找不到再找 `run_date - 2 days`。

如果用户显式给出日期，使用该日期作为 `run_date`，仍按上面规则派生默认 `target_date`；只有用户明确说“选题日期就是 X”时才直接覆盖 selection target date。

## Required Subskills

按顺序读取并执行：

1. `skills/daily-ai-tech-article-markdown/SKILL.md`
   - 只产出日期目录顶层的一篇 `01_AI技术_<中文标题>.md`，以及 `_meta/ai_tech_manifest.json`。
2. `skills/selection-article-chinese-markdown/SKILL.md`
   - 从本地 daily 选题产物找到已选文章，产出日期目录顶层的 `02_中国选题_<中文标题>.md`，以及 `_meta/selection_article_manifest.json`。

必须在执行子 skill 前读取其 `SKILL.md`。不要把子 skill 的规则复制成临时逻辑绕过。

## Workflow

1. 创建日期目录和 `_meta/`。
2. 调用 AI 技术文章子 skill：
   - 只选一篇 AI 文章。若 OpenAI 和 Anthropic 在 `target_date` 都有官方文章，也只在所有候选中选最值得读的一篇。
   - 优先单篇深度 feature、analysis、essay、interview、investigation 或公司战略/产业治理长文。
   - 如果官方来源只有短公告、release note、论文或纯产品 PR，而外部有更深的单篇产业文章，优先外部深度文章。
   - 外部候选必须是一篇独立文章，不要选 daily roundup、listicle、Top N stories、news digest、链接汇总或“今日 16 件事”。
   - 外部候选默认不要选 peer-reviewed paper、arXiv、医学 AI 论文、窄门槛 benchmark 或过度学术化研究，除非当天完全没有产业界材料且用户明确接受。
3. 调用选题文章子 skill：
   - 优先读取今天 5 点 daily 选题任务产物。
   - 找不到则读取前一天产物。
   - 仍找不到则跳过，不让整个 digest 失败。
   - 选题文章命名为 `02_中国选题_<中文标题>.md`。
4. 写 `_meta/daily_info_index.md`：
   - 标题：`每日译文 <run_date>`。
   - 列出每篇译文的本地路径、中文标题、英文原题、来源、原文链接和翻译状态。
5. 写 `_meta/daily_info_manifest.json` 和 `_meta/daily_info_report.md`：
   - 记录 run_date、target dates、所有输入路径、输出路径、状态、跳过原因。

## File Naming

文章 Markdown 按阅读顺序编号，文件名必须使用中文标题，不要用英文 slug。保留必要英文专名和缩写，例如 `OpenAI`、`Claude`、`Siri`、`AI`。

```text
01_AI技术_<中文标题>.md
02_中国选题_<中文标题>.md
```

生成文件名时，把中文标题里的 `/`、`:`、换行、引号、问号、星号等文件系统不友好的字符删掉或替换为中文标点；把空格压成 `_`；不要用自动生成的英文 URL slug。

同一天重复运行时，优先覆盖同名文件和 `_meta/` 中本次 manifest；不要创建 `run_1`、`final_final`、`new` 这类目录。

## Translation Standard

每篇 Markdown 只允许是来源信息 + 忠实中文译文。

固定结构：

```markdown
# 中文标题

> 原题：...
> 来源：...
> 作者：...
> 发布日期：...
> 原文：...

## 中文译文

（按原文段落顺序翻译。若原文有小标题，保留对应层级并翻译标题。）
```

禁止添加这些二创栏目，除非原文本身就有同名章节：

- `为什么今天值得读`
- `关键事实与数字`
- `技术/产业含义`
- `值得继续追的问题`
- `文章的核心判断`
- `对中国读者的意义`
- 任何“点评、导读、总结、启发、影响、怎么看”的额外分析

翻译要求：

- 保持原文结构、段落顺序、事实边界和语气，不把文章改写成解释稿。
- 中文表达要自然顺畅，允许为符合中文语序调整句式，但不得增删论点。
- 原文中的数字、机构名、人名、产品名、技术术语要准确保留；必要时采用“中文译名（英文原名）”。
- 如果只拿到摘要、摘录笔记、搜索片段或非完整正文，不能伪造“保持原文结构的中文翻译”；应在 `_meta/daily_info_report.md` 写明 `translation_skipped_incomplete_source`。

## Gates

完成时必须满足：

- 日期目录存在于 `/Users/wangfangjia/随记/晨间科技新闻/<run_date>/`。
- 日期目录顶层只包含最终文章 Markdown 和 `_meta/`。
- `_meta/daily_info_index.md` 存在。
- `_meta/daily_info_manifest.json` 存在。
- `_meta/ai_tech_manifest.json` 存在，且至少有一篇 AI 技术 Markdown，除非搜索、版权或完整原文获取失败并在 report 中说明。
- 中国选题文章缺失、版权受限或原文不完整时，manifest 中必须有明确 skip/failure 状态，不能伪造译文。
- 所有文章 Markdown 都有来源链接和本地输出路径。
- 所有文章 Markdown 使用 `## 中文译文` 作为正文主标题，不含二创栏目。

## Final Response

回复列出：

- 输出日期目录。
- AI 技术 Markdown 路径或跳过原因。
- 中国选题 Markdown 路径或跳过原因。
- `_meta/daily_info_index.md` 和 `_meta/daily_info_manifest.json` 路径。
