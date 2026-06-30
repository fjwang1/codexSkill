---
name: article-china-story-voiceover-script
description: 将本地英文或中文文章项目转写为“以中国视角讲述中国故事”的中文 Markdown 翻译稿/改写稿。适用于已有 source/article.txt、source/source_metadata.json，且父流程要先产出 translation/china_perspective_version.md，再交给 article-video-script 转译为视频口播稿；观众可见稿不得出现报刊名、作者名、来源 URL、“外媒/外刊/这篇文章说/原文认为/报道指出”等来源框架。
---

# 中国故事 Markdown 翻译稿

## 目标

把一个本地文章项目转写为中文 Markdown 翻译稿/改写稿。原文只作为事实材料、问题意识和结构线索；最终稿要像中国作者基于这些材料写出的中文长文，而不是“读外刊”“解读文章”或“转述报道”。

本 skill 不再产出最终视频口播稿。视频口播稿由后续 `article-video-script` 节点从 `translation/china_perspective_version.md` 转译生成。

“中国视角”不是硬写正面宣传，也不是把复杂问题讲成单一立场。它指的是：

- 从中国人的生活经验、社会变化、产业处境、地方治理、家庭选择、企业压力或代际经验进入问题。
- 把外部观察重新翻译为中国内部可以理解的矛盾、选择、约束和机会。
- 让中国人、中国组织、中国地方、中国产业链、中国普通家庭成为叙事主体，而不是被外部观看的对象。
- 保留复杂性：成就、代价、矛盾、误读、限制和不确定性都可以讲。

## 输入

必需文件：

```text
<project>/source/article.txt
```

优先读取的可选文件：

```text
<project>/source/source_metadata.json
<project>/source/reading_doc.md
<project>/planning/article_brief.json
<project>/planning/context_cards.json
<project>/planning/episode_outline.json
```

如果项目目录不是标准 `source/` 结构，就读取最接近的本地原文文件，并在报告里说明使用了哪个替代输入。

## 输出

```text
<project>/translation/china_perspective_version.md
<project>/translation/china_perspective_adaptation_result.json
<project>/translation/china_perspective_adaptation_report.md
<project>/planning/china_story_translation_plan.json
```

不要写 `single_host_script.md` 或 `podcast_script.md`。这两个文件只允许后续 `article-video-script` 节点产出。

观众可见的 `translation/china_perspective_version.md` 必须满足来源隐身：

- 不出现报刊名、媒体名、作者名、来源 URL。
- 不出现“外媒”“外刊”“原文”“这篇文章”“报道指出”“文章认为”“作者写道”“某某媒体说”等来源框架。
- 不写“来源文章：……”这一类头部。
- 不把外部标题直译成中文标题；标题要改成自然中文问题或判断。

生产报告和 plan 可以保留来源信息，用于事实溯源和质量控制；这些信息不得进入 `china_perspective_version.md`。

## 工作流程

1. 读取本地文章和已有策划文件。
   - 如果有 `article_brief.source_facts`、术语表或 `do_not_invent`，把它们当作事实边界。
   - `context_cards` 只用于解释背景和定向，不要让背景卡片替代原文。
   - `source_metadata` 只用于内部溯源，不得写入观众可见稿。

2. 提取原文材料。
   - 列出原文明确支持的事实、数字、人物、地点、机构、事件和因果判断。
   - 区分“事实”“解释”“推测”“评价”。
   - 对每个事实标注能否转写为中国内部叙事。

3. 选择中国故事角度。

   可选角度包括：

   ```text
   social-change：社会生活和观念变化
   industry-mechanism：产业链、企业和市场机制
   local-governance：地方治理、公共服务和政策执行
   family-decision：家庭、代际和个人选择
   global-position：全球环境中的中国选择
   technology-system：技术、基础设施和组织能力
   risk-and-trust：风险、信任、安全感和制度约束
   ```

4. 生成 `planning/china_story_translation_plan.json`。

   字段名保持英文，字段内容用中文写：

   ```json
   {
     "schema_version": "china-story-translation-plan.v1",
     "source_material_title": "...",
     "source_provenance_kept_out_of_reader_text": true,
     "story_angle": "social-change | industry-mechanism | local-governance | family-decision | global-position | technology-system | risk-and-trust",
     "china_viewpoint": "...",
     "main_question": "...",
     "audience_entry_scene": "...",
     "phenomenon_or_tension": "...",
     "key_variables": ["..."],
     "source_supported_facts": ["..."],
     "do_not_claim": ["..."],
     "sections": [
       {
         "name": "自然中文小标题",
         "purpose": "这一节帮助读者理解什么",
         "source_facts": ["原文支撑的事实"],
         "china_story_move": "把外部材料改写成中国内部叙事的方式",
         "avoid": ["不能出现的来源露出、夸大或跑偏内容"]
       }
     ]
   }
   ```

5. 写 `translation/china_perspective_version.md`。

   使用自然中文长文格式：

   ```markdown
   # <自然中文标题>

   <导语。直接进入中国语境里的场景、变化或问题，不提来源。>

   ## <小标题>

   <正文>
   ```

   写作要求：

   - 保留原文的核心事实、人物/机构行动、数字、时间线、因果链和关键判断。
   - 不逐字翻译；按中国读者理解顺序重组。
   - 不能新增原文或策划文件没有支持的采访、引语、统计、政策文件、个人心理或确定性结论。
   - 不能把“可能”“迹象”“一些人担心”改成确定事实。
   - 不能把局部案例扩大成全国结论，除非原文材料支持。
   - 每个章节都要有实质信息，不要写成空泛评论。

6. 写 `translation/china_perspective_adaptation_result.json`。

   ```json
   {
     "schema_version": "china-perspective-translation-result.v1",
     "status": "PASS | NEEDS_REVISION | FAIL",
     "article_path": "translation/china_perspective_version.md",
     "source_provenance_kept_out_of_reader_text": true,
     "coverage_estimate": 0.9,
     "story_angle": "...",
     "main_question": "...",
     "used_source_facts": ["..."],
     "intentionally_unused_source_facts": ["..."],
     "do_not_claim": ["..."],
     "revision_notes": ["..."]
   }
   ```

7. 写 `translation/china_perspective_adaptation_report.md`。

   报告包括：

   - 读取了哪些文件。
   - 原文来源信息是否只保留在报告和 plan 中。
   - 选择了哪个中国故事角度，为什么。
   - 使用了哪些原文或策划事实。
   - 有哪些事实刻意没有使用。
   - 有哪些表达被删除以避免来源露出。
   - 有哪些不确定性或输入结构 fallback。

## 写作规则

### 从中国人的问题开始

不要用这些开场：

```text
今天我们来读一篇文章……
有一篇外媒报道说……
某某报最近写了一个现象……
这篇文章真正提醒的是……
```

优先用这些进入方式：

```text
这几年，很多中国家庭都遇到一个变化……
如果你在这个行业里，会发现一个很现实的问题……
过去我们理解这件事，常常用一个旧经验；但现在这个旧经验不够用了。
一个很自然的问题来了：为什么偏偏是现在？
```

### 把外部观察改写为内部叙事

写作时把每个外部句子翻译成内部问题：

```text
不要写：某报认为，中国消费者正在改变。
要写：中国消费者确实在变，但变化不是突然发生的，它背后至少有三件事一起推着走。

不要写：文章指出，地方政府面临压力。
要写：到了地方层面，问题会变得更具体：钱从哪里来，责任谁来担，出了问题谁解释。
```

### 来源隐身禁令

`translation/china_perspective_version.md` 不得出现：

```text
外媒
外刊
原文
这篇文章
报道指出
文章认为
作者写道
据...报道
来源文章
The Economist
Economist
Bloomberg
Foreign Policy
Financial Times
New York Times
Wall Street Journal
Washington Post
Reuters
Associated Press
经济学人
彭博社
外交政策
金融时报
纽约时报
华尔街日报
华盛顿邮报
路透社
美联社
```

如果报刊名本身是事实对象而不是来源，例如某媒体公司就是故事里的主体，也要避免写入公开稿；改用“这家公司”“这个机构”或重组句子。

## 质量门

完成后检查：

```text
translation/china_perspective_version.md 存在
translation/china_perspective_adaptation_result.json 存在
translation/china_perspective_adaptation_report.md 存在
planning/china_story_translation_plan.json 存在
公开稿没有报刊名、作者名、来源 URL 或来源文章头部
公开稿没有外媒/外刊/原文/这篇文章/报道指出/文章认为等来源框架
开头不是读书报告、文章摘要或外刊解读腔
主问题在全文前 20% 内清楚出现
事实没有越过原文和策划文件边界
稿件包含纠偏，也包含至少一个限制、代价或矛盾
```
