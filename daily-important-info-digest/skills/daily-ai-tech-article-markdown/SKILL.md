---
name: daily-ai-tech-article-markdown
description: "每日 AI 技术文章中文 Markdown 子 skill。Use when Codex needs to find exactly one standalone, deep AI industry article from yesterday: a feature, analysis, interview, investigation, or strategy essay about AI companies, products, governance, infrastructure, developers, or market structure. Avoid daily roundups, listicles, Top N stories, news digests, academic papers, and narrow research benchmarks by default."
---

# Daily AI Tech Article Markdown

产出每日 AI 技术文章中文阅读稿。默认只服务上游 `daily-important-info-digest`，也可单独调用。固定只选一篇单篇深度文章，不产出新闻综述、每日合集或多事件摘要。

## Inputs

- `target_date`: 默认 Asia/Shanghai 昨天，格式 `YYYY-MM-DD`。
- `output_dir`: 默认由上游传入日期目录 `/Users/wangfangjia/随记/晨间科技新闻/<run_date>/`。
- `start_index`: 默认 1，用于生成 `01_` / `02_` 文件名前缀。
- `max_external_count`: 固定 1。

## Source Priority

先查官方来源：

1. OpenAI 官方文章、新闻、产品、公司动作、政策治理或开发者生态文章。
2. Anthropic 官方文章、新闻、产品、公司动作、政策治理或开发者生态文章。

官方域名：

- OpenAI：`openai.com`，优先 `openai.com/news/`、`openai.com/index/`、`openai.com/research/`、`openai.com/blog/` 或等价官方发布页。
- Anthropic：`anthropic.com`，优先 `anthropic.com/news`、`anthropic.com/research` 或等价官方发布页。

规则：

- 只选一篇 AI 文章。即使 OpenAI 和 Anthropic 在 `target_date` 都有官方文章，也只在所有候选里选最值得读的一篇。
- 优先单篇深度 feature、analysis、essay、interview、investigation 或公司战略/产业治理长文。
- 如果官方来源只有短公告、release note、论文或纯产品 PR，而外部有更深的单篇产业文章，优先外部深度文章。
- 如果同一家公司当天有多篇，优先选择产业影响、产品/模型影响、开发者价值、生态变化、治理争议或行业讨论度最高的一篇。
- 必须打开候选页面核对发布日期或页面 metadata；日期无法确认时可列入 rejected candidates，但不要当作 `target_date` 官方命中。
- 官方候选搜索应优先使用 domain-restricted search；不要让媒体转载、论坛讨论或聚合页冒充官方发布。

外部来源优先级：

1. 高质量单篇 AI 产业深度文章：Axios、The Verge、Wired、TechCrunch、CNBC、Bloomberg、Financial Times、The Information、Stratechery、Semafor、MIT Technology Review、Fortune、The Batch、Latent Space、Import AI、Guardian、New York Magazine、The Atlantic 等。
2. 官方公司/产品/开发者生态文章：OpenAI、Anthropic、Google DeepMind/Google AI、Meta AI、Microsoft、NVIDIA、Apple、Hugging Face、Mistral、Perplexity、xAI、Cursor、GitHub、Replit 等。
3. AI 眼镜、可穿戴、硬件、机器人、芯片、开发者工具、agent、模型能力、应用生态、重要播客访谈或 transcript。

外部候选必须和 AI 产业、产品、治理、生态或热点讨论强相关。daily roundup、listicle、Top N stories、news digest、链接汇总、泛商业融资、股价、纯 PR、短讯、SEO 汇总页默认淘汰。peer-reviewed paper、arXiv、医学 AI 论文、窄门槛 benchmark 和过度学术化研究默认淘汰，除非当天完全没有产业界材料且用户明确接受。

## Retrieval Gate

必须获取可读完整正文材料后才能写译文。

执行顺序：

1. 原站公开全文。
2. 若原站不可读，读取并调用 `/Users/wangfangjia/.codex/skills/url-page-capture/SKILL.md`，按其真实 Chrome / HTTP / archive 流程抓取。
3. 若是付费墙、登录墙或验证码，参考 `/Users/wangfangjia/.codex/skills/china-longform-article-selection/SKILL.md` 的正文可获取性门禁：寻找合法公开同文转载源；找不到就淘汰。

不得使用盗版镜像、论坛搬运、绕付费墙教程、Chrome cookie 文件或需要用户手动解验证码的路径。不要只凭标题、摘要、摘录笔记或搜索片段生成译文。

如果无法取得完整原文，不要写摘要二创稿；在 manifest 中记录 `translation_status="skipped_incomplete_source"` 或 `retrieval_failed`。

## Output

写入：

```text
<output_dir>/
  01_AI技术_<中文标题>.md
  _meta/
    ai_tech_manifest.json
    source_material/
```

不要创建 `ai_tech/` 子目录放文章。文章 Markdown 必须直接在日期目录顶层。文件名必须使用中文标题，不要使用英文 slug；保留必要英文专名和缩写，例如 `OpenAI`、`Claude`、`Siri`、`AI`。

`_meta/ai_tech_manifest.json` 至少包含：

```json
{
  "target_date": "YYYY-MM-DD",
  "selection_policy": "openai_anthropic_official_first_else_one_external",
  "official_sources_checked": ["OpenAI", "Anthropic"],
  "selected_articles": [
    {
      "rank": 1,
      "source": "OpenAI",
      "title_original": "...",
      "title_zh": "...",
      "url": "https://...",
      "published_date": "YYYY-MM-DD",
      "selection_reason": "...",
      "retrieval_status": "original_public_open | capture_success | legal_republication_success | failed",
      "translation_status": "translated | skipped_incomplete_source | skipped_copyright_boundary | retrieval_failed",
      "local_material_path": "...",
      "markdown_path": "/Users/wangfangjia/随记/晨间科技新闻/YYYY-MM-DD/01_AI技术_<中文标题>.md"
    }
  ],
  "rejected_candidates": []
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

## 中文译文

（按原文段落顺序翻译。若原文有小标题，保留对应层级并翻译标题。）
```

不要添加 `为什么今天值得读`、`关键事实与数字`、`技术/产业含义`、`值得继续追的问题` 或任何额外评论栏目。

翻译要求：

- 保持原文结构、段落顺序、事实边界和语气。
- 中文表达要自然，允许为中文语序调整句式，但不得增删论点。
- 文章需要保持原文不变进行翻译。不要用二创稿替代。

## Final Response

返回选中文章数、每篇标题、来源、原文 URL、日期目录顶层 Markdown 路径或跳过原因，以及 `_meta/ai_tech_manifest.json` 路径。
