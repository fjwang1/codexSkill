---
name: article-podcast-episode-planning
description: 为英文或中文外刊文章生成中文播客/单人口播解释视频的策划层。适用于已有 source/article.txt 和 source/source_metadata.json 的项目；输出 planning/article_brief.json、context_research_plan.json、context_cards.json、episode_profile.json、speaker_profile.json、episode_outline.json，供后续中文双人播客文稿或 single_host_script.md 按段生成。可在不抓取原文 URL 的前提下做背景补充搜索。
---

# 文章播客/口播节目策划

这个 skill 负责文稿前的策划层。不要直接写 `podcast_script.md` 或 `single_host_script.md`。先把文章变成一期中文外刊解读内容的策划案，再交给文稿 skill。

调用方决定表达模式：

- 双人播客总控使用 `mode=dialogue_podcast`：`episode_outline` 以 `dialogue_moves` 推进，`speaker_profile` 包含主持人和分析者。
- 单人口播总控使用 `mode=single_host_explainer`：`episode_outline` 以 `explanation_moves` 推进，`speaker_profile` 只保留一个单人口播主持。若为了兼容旧节点保留 `dialogue_moves`，也必须同时写出等价的 `explanation_moves`。

## 输入

```text
<project>/source/article.txt
<project>/source/source_metadata.json
<project>/source/fact_notes.md, optional
```

不要联网抓取原文，不要用 URL 替代本地 `article.txt`。如果做背景搜索，只能用于补充解释性背景，不能覆盖原文事实和主论点。

## 输出

```text
<project>/planning/
  article_brief.json
  context_research_plan.json
  context_cards.json
  episode_profile.json
  speaker_profile.json
  episode_outline.json
  planning_report.md
```

## 工作流

1. 读完整文章和 metadata。
2. 生成 `article_brief.json`：
   - `core_question`: 这篇文章真正问的问题。
   - `thesis`: 文章主判断。
   - `primary_subject`: 主场景/主对象。
   - `primary_subject_type`: `place | company | person | policy | technology | industry | event | other`。
   - `source_facts`: 原文关键事实、数字、人名、地点、时间线。
   - `tensions`: 3-6 个可推动对话的矛盾。
   - `terminology_glossary`: 面向中文口播/播客的术语写法，记录英文词、推荐中文、应避免的机械直译。
   - `proper_noun_glossary`: 面向中文口播/播客的专名本地化表，记录原文专名、实体类型、推荐口播写法、证据和置信度。
   - `do_not_invent`: 不可编造或不可外推的点。
3. 生成 `context_research_plan.json`：
   - 列出 3-8 个可补充背景的问题。
   - 标注每个问题为什么能帮助听众理解。
   - 标注 `from_article_only`、`needs_web` 或 `optional_web`。
4. 如环境允许且背景会显著提升节目质量，做简短背景搜索。
   - 可以查地点、人物履历、公司行业位置、政策背景、术语解释、历史脉络。
   - 不要查整篇文章替代源文，不要找盗版全文。
   - 每条外部信息必须记录 URL 或明确说明来自本地文章/常识推断。
5. 生成 `context_cards.json`。
   - 必须包含一张 `id="subject_orientation"` 的听众定位卡。
   - 这张卡回答“这个主对象是谁/在哪/是什么，为什么值得从它讲起”。
   - 如果环境允许联网，优先用可信外部来源补足定位信息；如果不联网或来源不足，可用 `article` / `inference`，但要在 `planning_report.md` 说明边界。
6. 生成 `episode_profile.json` 和 `speaker_profile.json`。
7. 生成 `episode_outline.json`。

## 专名本地化

不要机械保留原文英文，也不要硬猜中文。为反复出现或听众会记住的专名建立 `proper_noun_glossary`：

```json
{
  "source_form": "Tianshui Industry 2050",
  "entity_type": "person | place | organisation | company | project | product | policy | publication | other",
  "locale_guess": "chinese_source_entity | foreign_entity | mixed_or_unclear",
  "audience_form": "天水工业 2050",
  "first_mention": "一个叫“天水工业 2050”的展厅",
  "evidence": "原文写作 Tianshui Industry 2050；Tianshui 是天水，Industry 在此为展厅/产业项目名",
  "confidence": "high | medium | low",
  "handling_rule": "use_audience_form | use_role_descriptor | keep_original_with_role | verify_before_chinese_characters",
  "avoid": "不要在中文正文里直接说 Tianshui Industry 2050"
}
```

判断规则：

- 中国语境里的地点、政府项目、园区、展厅、政策名，原文常是英文转写或翻译；中文播客正文要优先本地化。例如 `Tianshui Industry 2050` 应写成 `天水工业 2050` 或更自然的 `天水这个 2050 工业展厅`，必要时在 report 里记录原文英文。
- 中国人名如果原文只有拼音，先查 source、图片、metadata 或可信背景来源；能确认汉字才写汉字。不能确认时，不要编造“石/史/施/时”等字，口播正文优先写成“当地一位 27 岁年轻人”“一位当地妈妈”，并在 report/brief 里保留 `source_form`。
- 外国公众人物、公司、机构如果中文世界有稳定叫法，必须用稳定中文名，例如 `Elon Musk` -> `马斯克`，`Jensen Huang` -> `黄仁勋`，`Mark Zuckerberg` -> `扎克伯格`，`Nvidia` -> `英伟达`。
- 没有稳定中文名的外国小众人物，可以保留英文，但第一次要加身份或机构，例如“欧亚集团分析师 Dan Wang”。如果其华语姓名可确认，再用中文名。
- 品牌、模型、论文标题、法案标题、英文缩写是否翻译，取决于中文听众习惯：中文世界通常说英文的保留英文，通常有译名的用译名，第一次可补英文括注；口播不要堆括号。
- 低置信度专名不要放进口播做记忆点；用角色、地点、身份替代。

## Primary Subject 规则

不要写死某个对象。每篇文章都必须识别一个主场景/主对象，并按类型补背景：

```text
place:
  在哪里、历史角色、经济/文化名片、为什么能代表文章问题
company:
  怎么起家、行业位置、商业模式、竞争对手、为什么此刻出问题
person:
  身份、履历、权力/利益位置、为什么此人是文章切口
policy:
  解决什么旧问题、制造什么新问题、影响谁
technology:
  它解决什么、过去怎么工作、现在为什么变重要、谁被排除在外
industry:
  产业链位置、利润/就业/政策结构、赢家和输家
event:
  发生了什么、为什么不是孤立事件、背后的机制
```

无论 `primary_subject_type` 是哪一种，都要为它生成 `subject_orientation`：

```text
place:
  2-4 句说明它在哪里、听众可能听过它什么、过去承担过什么角色、为什么文章从这里切入
company:
  2-4 句说明它做什么、在行业里处于什么位置、为什么它能代表文章问题
person:
  2-4 句说明此人的身份/位置/利益关系，为什么文章通过此人进入主题
policy:
  2-4 句说明政策原本想解决什么问题、影响哪些人、为什么现在引发争议
technology:
  2-4 句说明技术是什么、解决什么旧问题、为什么现在变重要
industry:
  2-4 句说明产业链位置、就业/利润/政策结构，为什么它是文章核心场景
event:
  2-4 句说明事件发生了什么、为什么不是孤立新闻、它暴露了什么机制
```

`subject_orientation` 不是百科介绍。它是给主持人开场、转场和听众定位用的半步背景。

## context_cards.json

每张卡必须可被后续文稿直接使用：

```json
{
  "cards": [
    {
      "id": "subject_background",
      "topic": "主对象背景",
      "status": "usable",
      "source_type": "article | external_verified | inference",
      "summary": "用 2-4 句中文说明背景。",
      "use_in_script": "说明这张卡应该插入哪一段、解决听众什么困惑。",
      "evidence": ["原文事实或来源摘要"],
      "source_urls": ["https://..."],
      "risk": "none | needs_attribution | weak_source | avoid_overclaiming"
    }
  ]
}
```

只能把 `status=usable` 的卡交给文稿。外部背景卡要用于解释，不要喧宾夺主。

## episode_profile.json

固定生成中文外刊解读内容要求：

```json
{
  "name": "chinese_article_deep_dive | chinese_single_host_article_explainer",
  "target_audience": "中文知识区/外刊解读听众",
  "source_mention_policy": "开头用中文来源名明确提一次来源；后续主要讨论问题本身，少量必要处可说《<中文来源名>》抓了一个细节。英文 publication 必须中文化，例如 Foreign Policy 写作《外交政策》。",
  "style": [
    "像自然中文内容，不像翻译稿、新闻播报或课堂讲义",
    "允许短暂离开文章补背景，但必须回到文章主线",
    "不要为了 TTS 强行短句，优先自然表达",
    "主持人要有困惑、误解、追问和纠偏；单人口播用自问自答承载这些动作"
  ],
  "quality_targets": [
    "scene-setting",
    "background extension",
    "mechanism explanation",
    "mild disagreement",
    "listener empathy",
    "clear return to article thesis"
  ]
}
```

## speaker_profile.json

双人播客模式映射到最终 `Speaker 0` / `Speaker 1`，profile 要给出可写作的人格：

```json
{
  "speakers": [
    {
      "id": "Speaker 0",
      "role": "女主持人",
      "backstory": "中文外刊解读播客主持，代表普通听众的疑问。",
      "personality": "自然、敏锐、会承认没想明白，会把抽象议题拉回普通人的生活。",
      "must_do": ["追问", "复述困惑", "轻微反驳", "把宏观词翻成生活问题"],
      "must_not_do": ["像新闻主播", "连续发表长评论"]
    },
    {
      "id": "Speaker 1",
      "role": "男分析者",
      "backstory": "熟悉外刊叙事和相关领域背景的分析者。",
      "personality": "解释机制、补历史脉络、给判断但不过度武断。",
      "must_do": ["讲机制", "补背景", "承认不确定性", "把原文事实连接成因果链"],
      "must_not_do": ["逐段翻译", "把所有话说成结论"]
    }
  ]
}
```

单人口播模式只保留一个可写作人格，字段名仍是 `speaker_profile.json` 以兼容后续节点：

```json
{
  "speakers": [
    {
      "id": "Speaker 0",
      "role": "单人口播主持",
      "backstory": "中文外刊解释型视频主持，既代表观众的疑问，也负责机制解释和判断收束。",
      "personality": "自然、敏锐、会承认直觉误读，会把抽象议题拉回普通人的生活。",
      "must_do": ["用中文生活经验开场", "提出主问题", "尽早给出核心变量组", "逐步解释机制", "保留约束和代价"],
      "must_not_do": ["像新闻主播", "逐段翻译", "写成双人对话", "把所有话说成结论"]
    }
  ]
}
```

## episode_outline.json

推荐 5-7 个 segment。每个 segment 必须包含事实锚点和推进动作。

双人播客模式使用：

```json
{
  "segment_id": "seg_01",
  "name": "抓人的中文段落名",
  "purpose": "这一段在整期节目中的功能",
  "source_facts": ["来自原文的事实锚点"],
  "context_cards_to_use": ["subject_background"],
  "dialogue_moves": [
    "主持人先提出听众直觉或困惑",
    "分析者解释一个机制",
    "主持人短暂追问或反驳",
    "回到文章主论点"
  ],
  "avoid": ["本段不要变成百科介绍", "不要引入无来源判断"]
}
```

`dialogue_moves` 是导演层的核心。它决定这一段为什么像播客，而不是摘要。

单人口播模式使用：

```json
{
  "segment_id": "seg_01",
  "name": "抓人的中文段落名",
  "purpose": "这一段在整期节目中的功能",
  "source_facts": ["来自原文的事实锚点"],
  "context_cards_to_use": ["subject_background"],
  "explanation_moves": [
    "提出一个观众会有的直觉或困惑",
    "给出短答案或纠偏",
    "解释一个机制",
    "落到原文事实或中文生活场景",
    "回到文章主论点并转入下一问"
  ],
  "avoid": ["本段不要变成百科介绍", "不要引入无来源判断"]
}
```

`explanation_moves` 决定这一段为什么像一个视频讲解，而不是摘要。

## Gate

通过条件：

```text
planning/article_brief.json exists
planning/context_research_plan.json exists
planning/context_cards.json exists
planning/episode_profile.json exists
planning/speaker_profile.json exists
planning/episode_outline.json exists
article_brief records primary_subject and primary_subject_type
article_brief records terminology_glossary for key translated terms
article_brief records proper_noun_glossary for recurring people/places/projects/organisations
context_cards only contains article/external_verified/inference source_type
external_verified cards include source_urls
episode_outline has 5-7 segments
every segment has source_facts, avoid, and either dialogue_moves for dialogue_podcast mode or explanation_moves for single_host_explainer mode
episode_outline first two segments use subject_orientation or explain why not
planning_report.md explains research mode and source boundary
```
