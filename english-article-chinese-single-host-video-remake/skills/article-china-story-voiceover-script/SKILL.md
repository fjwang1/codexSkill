---
name: article-china-story-voiceover-script
description: 将本地英文或中文文章项目重写为“以中国视角讲述中国故事”的中文单人口播稿。适用于已有 source/article.txt、source/source_metadata.json，且用户要把外部文章吸收为中国作者口吻的视频讲述，而不是外刊解读、文章摘要、报刊评论或双人播客；必须输出 single_host_script.md 和兼容镜像 podcast_script.md，稿件正文和稿件头部不得出现报刊名、作者名、来源 URL、“外媒/外刊/这篇文章说/原文认为/报道指出”等来源框架。
---

# 中国故事单人口播稿

## 目标

把一个本地文章项目重写成中文单人口播稿。原文只作为事实材料、问题意识和结构线索；最终稿要像一个中国作者基于这些材料写出的原创讲述，而不是“读外刊”“解读文章”或“转述报道”。

核心变化：

- 从“外刊解释型视频”改为“以中国视角讲中国故事”。
- 不在观众可见稿件中暴露报刊名、作者名、链接、外媒身份或“文章说”的叙述框架。
- 允许吸收原文事实、案例、数据和问题意识，但要重组为中国语境里的故事、机制和判断。
- 事实边界仍然来自原文和策划文件；不能因为换成中国作者口吻就编造一手采访、亲历、官方结论或未被材料支持的因果。

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
<project>/single_host_script.md
<project>/podcast_script.md
<project>/planning/single_host_explainer_plan.json
<project>/planning/single_host_script_generation_report.md
```

`single_host_script.md` 是正式文稿。`podcast_script.md` 是给旧标题、封面、PPT、字幕和视频后段流程使用的兼容镜像，内容必须和 `single_host_script.md` 一致；它不代表双人播客。

观众可见的两个稿件文件都必须满足来源隐身：

- 不出现报刊名、媒体名、作者名、来源 URL。
- 不出现“外媒”“外刊”“原文”“这篇文章”“报道指出”“文章认为”“作者写道”“某某媒体说”等来源框架。
- 不写“来源文章：……”这一类稿件头部。
- 不把外部标题直译成稿件标题；标题要改成自然中文问题或判断。

生产报告和 plan 可以保留来源信息，用于事实溯源和质量控制；这些信息不得进入 `single_host_script.md` 或 `podcast_script.md`。

## 核心原则

把原文当作素材库，而不是叙事主人。

每篇稿子都必须有：

- 一个中国观众能直接进入的生活、产业、地方或社会场景
- 一个中国内部正在发生的变化、压力或反差
- 一个贯穿全文的主问题
- 一组由原文支撑的关键事实、变量或人物/机构行动
- 对中国主体的能动性、限制和代价的解释
- 至少一个纠偏：这件事不能被简单理解成 A，关键其实是 B
- 至少一个真实约束：成本、信任、时间、治理、地区差异、全球环境、技术瓶颈或代际差异
- 一个能留下记忆点的大判断

不要为了“中国视角”改写事实。不能把外部分析改写成材料没有支持的民族叙事、官方口径、个人亲历或确定性结论。

## 推荐结构

把下面结构当作主路线，不是填空表。

```text
1. 中国生活或社会场景开场
   从中国观众熟悉的场景进入：家庭选择、就业压力、消费变化、县城/城市经验、产业链、地方治理、企业出海、教育、养老、住房、食品、能源、科技等。

2. 变化或反差
   说清楚这几年哪里变了，旧经验为什么不够用了。

3. 主问题
   把问题改写成中国内部问题，而不是“某报怎么看中国”。
   例子：真正的问题是，中国的这个行业为什么会在短时间里同时遇到需求、信任和成本三重压力？

4. 核心变量
   如果原文支撑多原因解释，尽早说出 3 到 6 个变量。变量名用自然中文：钱、信任、技术、时间、供应链、地方财政、家庭预期、全球需求、政策约束。

5. 逐段讲故事和机制
   每一节围绕一个问题推进：发生了什么，为什么会这样，谁在做选择，选择有什么代价。

6. 纠偏和复杂性
   明确指出常见误读：不是简单的成功/失败，不是单一政策结果，也不是某个群体突然变了。

7. 收束判断
   回到中国故事本身，给观众一个可复述的框架。
```

## 工作流程

1. 读取本地文章和已有策划文件。
   - 如果有 `article_brief.source_facts`、术语表或 `do_not_invent`，把它们当作事实边界。
   - `context_cards` 只用于解释背景和定向，不要让背景卡片替代原文。
   - `source_metadata` 只用于内部溯源，不得写入口播稿。

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

4. 生成 `planning/single_host_explainer_plan.json`。
   使用下面 schema。字段名保持英文，字段内容用中文写。

   ```json
   {
     "schema_version": "china-story-voiceover-plan.v1",
     "source_material_title": "...",
     "source_provenance_kept_out_of_script": true,
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
         "purpose": "这一节帮助观众理解什么",
         "source_facts": ["原文支撑的事实"],
         "china_story_move": "把外部材料改写成中国内部叙事的方式",
         "voiceover_moves": [
           "提出具体问题",
           "给出短答案",
           "讲一个由材料支持的中国场景或主体选择",
           "解释机制",
           "转入下一个问题"
         ],
         "avoid": ["不能出现的来源露出、夸大或跑偏内容"]
       }
     ],
     "source_erasure_checklist": [
       "稿件不出现报刊名",
       "稿件不出现作者名",
       "稿件不出现外媒/外刊/原文/这篇文章等框架",
       "稿件不出现来源 URL",
       "稿件不伪装一手采访或亲历"
     ],
     "visual_chapter_notes": [
       {
         "section": "...",
         "visual_role": "number card | comparison table | flow diagram | map | timeline | object scene | quote card",
         "note": "PPT 这一页应该把什么东西可视化"
       }
     ]
   }
   ```

5. 写 `single_host_script.md`，并同步写兼容镜像 `podcast_script.md`。
   使用下面格式：

   ```markdown
   # 单人口播稿：<自然中文标题>

   形式：以中国视角讲述中国故事的单人口播
   建议时长：<估计时长>

   ## 正文

   <正文口播稿>
   ```

   正文必须是可以直接念出来的中文。不要出现说话人标签、舞台指令、来源说明或报刊名。

   写完后，把 `single_host_script.md` 原样复制为 `<project>/podcast_script.md`。不要为了兼容镜像加入 `Speaker 0:`、`Speaker 1:` 或双人对话格式。

6. 写生成报告。
   报告包括：

   - 读取了哪些文件
   - 原文来源信息是否只保留在报告和 plan 中
   - 选择了哪个中国故事角度，为什么
   - 使用了哪些原文或策划事实
   - 有哪些事实刻意没有使用
   - 有哪些表达被删除以避免来源露出
   - 有哪些不确定性或输入结构 fallback
   - 是否运行 lint，以及结果是什么

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

`single_host_script.md` 和 `podcast_script.md` 不得出现：

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

如果报刊名本身是事实对象而不是来源，例如某媒体公司就是故事里的主体，也要避免写入口播稿；改用“这家公司”“这个机构”或重组句子。

### 保持事实边界

- 可以把材料中的事实换成中国口语表达。
- 可以调整叙事顺序，让故事更符合中文视频口播。
- 不可以新增原文没有的采访、引语、统计、政策文件、个人心理或结论。
- 不可以把“可能”“迹象”“一些人担心”改成确定事实。
- 不可以把局部案例扩大成全国结论，除非原文材料支持。

### 保持口播友好

- 使用自然中文，不要翻译腔。
- 段落要短，方便人声和 TTS 换气。
- 在场景、数字、机制、判断之间切换，不要连续堆抽象概念。
- 每 1 到 2 分钟重新锚定观众一次：比如“到这里，我们先得到第一个结论……”
- 可以自问自答：比如“那问题来了……”“为什么偏偏是现在？”“这是不是说明……？”然后直接回答。
- 不要使用 `Speaker 0:`、`Speaker 1:`、角色名或舞台指令。
- 不要把生成过程、推理修正或未完成标记写进正文，例如 `No.`、`TODO`、`纠正一下`、`这里需要`、`应该是`。
- 不要提交明显未完成的截断稿；完整讲述通常至少要覆盖开头、事实铺陈、机制拆解、约束和结尾判断。

## 质量门

完成后尽量运行 lint：

```bash
python3 /Users/wangfangjia/.codex/skills/english-article-chinese-single-host-video-remake/skills/article-china-story-voiceover-script/scripts/lint_single_host_script.py <project>/single_host_script.md
```

检查重点：

```text
single_host_script.md 存在
podcast_script.md 存在，且内容和 single_host_script.md 一致
planning/single_host_explainer_plan.json 存在
planning/single_host_script_generation_report.md 存在
稿件没有 Speaker 0/Speaker 1 标签
稿件没有报刊名、作者名、来源 URL 或来源文章头部
稿件没有外媒/外刊/原文/这篇文章/报道指出/文章认为等来源框架
开头不是读书报告、文章摘要或外刊解读腔
主问题在全文前 20% 内清楚出现
事实没有越过原文和策划文件边界
稿件包含纠偏，也包含至少一个限制、代价或矛盾
```
