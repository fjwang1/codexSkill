---
name: article-chinese-podcast-script
description: 将已有节目策划层的英文或中文文章改写成中文双人播客文稿。适用于已有 source/article.txt，优先读取 planning/article_brief.json、context_cards.json、episode_profile.json、speaker_profile.json 和 episode_outline.json，按 segment 输出 Speaker 0 女主持、Speaker 1 男分析者的追问式 podcast_script.md，供后续润色和 VibeVoice 使用。
---

# 文章转中文播客文稿

这个 skill 负责 Gate 2 Script Draft：把节目策划案写成中文双人播客文稿。它不再兼任节目导演；高质量主流程必须先运行 `article-podcast-episode-planning`。

## 输入

```text
<project>/source/article.txt
<project>/source/source_metadata.json, optional
<project>/source/fact_notes.md, optional
<project>/planning/article_brief.json, preferred
<project>/planning/context_cards.json, preferred
<project>/planning/episode_profile.json, preferred
<project>/planning/speaker_profile.json, preferred
<project>/planning/episode_outline.json, preferred
```

不要处理 URL。输入必须已经是本地文件或已抽出的本地正文。

如果 `planning/episode_outline.json` 存在，必须使用它按段写稿，不要重新发明节目结构。只有在用户明确要求快速原版或 planning 文件缺失时，才使用旧的一步改写 fallback，并在回复中说明这是低保真原版。

## 输出

```text
<project>/podcast_script.md
<project>/planning/script_generation_report.md
```

默认人物：

- `Speaker 0`：女主持人。负责提问、追问、质疑、换位思考、把复杂内容拉回听众。
- `Speaker 1`：男分析者。负责讲故事、解释机制、补背景、给判断。

## 文稿格式

```markdown
# 中文播客文稿：<中文节目标题>

来源文章：<中文来源名 + 文章标题；无法确认 publication 时只写文章标题或来源文件名>
形式：一男一女双人播客，主持人追问式
建议时长：<估算时长>

## 人物

- Speaker 0：女主持人，追问与推进
- Speaker 1：男分析者，机制解释与判断

## 正文

Speaker 0: ...

Speaker 1: ...
```

## 高质量主流程

1. 读取 planning artifacts。
   - `article_brief.json` 提供主问题、主论点、事实边界、primary subject 和术语表。
   - `article_brief.json.terminology_glossary` 提供中文口播术语；优先使用推荐中文，避免机械直译。
   - `article_brief.json.proper_noun_glossary` 提供专名本地化写法；正文必须优先使用 `audience_form` 或 `first_mention`。
   - `context_cards.json` 提供可用背景卡，只能使用 `status=usable` 的卡；其中 `subject_orientation` 是听众定位卡，开头或前两段必须自然使用。
   - `episode_profile.json` 提供节目要求和来源露出规则。
   - `speaker_profile.json` 提供 Speaker 0/1 的人格和说话职责。
   - `episode_outline.json` 提供每段的 source facts、context cards、dialogue moves 和 avoid。

2. 按 `episode_outline.json.segments` 写稿。
   - 每个 segment 先完成它自己的对话动作，再进入下一段。
   - 每段允许短暂背景延伸，但必须回到该段 `source_facts` 和文章主线。
   - 不要把 `context_cards` 写成百科；只把它们转成帮助听众理解的两三句话。
   - `subject_orientation` 的用法是给听众定位，不是硬塞百科：比如“这地方大概在哪、过去靠什么、为什么它能代表这个问题”。
   - 写稿时可以保留 `## <segment name>` 作为结构标记；正文仍只使用 `Speaker 0:` / `Speaker 1:`。

3. 让主持人承担真实听众视角。
   - 不只是递问题，要有“等等，这里我没想明白”“这是不是说明...”“会不会太宿命论了？”这类真实反应。
   - 每个长 segment 至少有一次追问、轻微反驳、误解澄清或换位思考。
   - 主持人要把宏观概念拉回城市、家庭、工作、工资、孩子、消费等可感对象。

4. 让分析者讲机制而不是堆事实。
   - 先回答主持人的困惑，再补背景和原文事实。
   - 数字、人名、地点必须来自原文或 usable 背景卡。
   - 不确定汉字的中国人名不要强行造字，也不要让口播反复读拼音；优先改写成“当地一位年轻人/一位当地妈妈/一位受访者”等角色描述，并在 report 里保留原文拼音。
   - 术语要像中文播客，不像翻译稿；例如多数语境下 `high-tech` 说“高科技”或“先进制造”，不要反复写“高技术”。

5. 写 `planning/script_generation_report.md`。
   - 记录使用了哪些 planning files。
   - 记录每个 segment 使用的 context cards。
   - 记录未使用或回避的高风险背景。

## 快速原版 fallback

仅当 planning artifacts 不存在或用户明确要求“先出原版”时使用：

1. 先理解文章，不要逐段翻译。
   - 提炼中心问题。
   - 找出关键事实、数字、人物、地点、时间线、因果链。
   - 找出真正值得讨论的矛盾或张力。
   - 找出可以转成听众问题的点。
   - 如果 `source_metadata.json` 或本地原文可见 publication，在文稿顶部 `来源文章：` 行以中文来源名保留该来源，供最终 `video_title.txt`、口播开头和字幕声明来源；不要从文件名强猜。英文 publication 必须中文化，例如 `Foreign Policy` 写作 `外交政策`，`Bloomberg` 写作 `彭博社`。

2. 设计临时节目结构。
   - 开场从听众能理解的问题切入，不要说“今天我们来读一篇文章”。
   - 中段用主持人追问推动机制解释。
   - 深段加入反直觉点、争议、伦理或政策含义。
   - 结尾总结启发，而不是复述文章结论。
   - 长文可以分 4-6 个 `##` 内容章节；章节是结构和视觉参考，不是 TTS 生成单位。后续章节视觉数量和形式由 PPT Master 根据最终稿件动态判断。

3. 写成真实对谈。
   - `Speaker 0` 每次发言通常 1-3 句，负责推动。
   - `Speaker 1` 每次发言通常 2-6 句，负责解释。
   - 每 2-4 个 `Speaker 1` 回合中，`Speaker 0` 必须有一次真正追问或转向。

## VibeVoice 友好回合规则

后续音频默认由 VibeVoice 整篇生成。文稿仍必须控制回合长度，因为长回合会让对话节奏变差，也会增加 ASR 对齐难度：

- `Speaker 0` 回合：通常 30-160 中文字。
- `Speaker 1` 回合：通常 100-320 中文字。
- `Speaker 1` 不要连续输出超过 60-75 秒；太长时拆成两个自然回合，中间让 `Speaker 0` 追问、确认或转场。
- 不要把一个章节写成一个超长发言。
- 不要写括号舞台提示，例如 `（惊讶地）`；把情绪写进台词、标点和追问本身，避免 TTS 把提示读出来。
- 不要为了短句破坏自然播客表达；本项目优先播客质量，再考虑 TTS。

## 硬约束

- 默认只使用 `Speaker 0:` 和 `Speaker 1:` 两个说话人。
- 正文不要使用 `林遥：`、`陈澈：` 或其他中文 speaker 标签；这些只可出现在人物说明里。
- 不要让两个人都像评论员一样轮流发表长段观点。
- 不要频繁出现“这篇文章说”“文章提到”“作者写道”“原文里”。
- 高质量主流程开头应明确提到已确认中文来源名，例如《经济学人》《外交政策》；不要说成 `Foreign Policy`、`Bloomberg` 这类英文来源。开头之后主要讨论文章代表的问题，不要反复读文章。
- 不要写成新闻播报、课堂讲义、论文摘要或读书笔记。
- 不要残留翻译腔术语；能用自然中文解释的，不要机械直译英文词。
- 不要把“刺耳”当万能反应词；除非真的在描述声音或强烈冲击，主持人更自然的说法通常是“这感觉不太对劲啊”“这个反差很大”“这个数字有点扎心”。
- 保留核心事实、数字和复杂度；不要编造文章没有的细节。
- 对第三方版权文章只做转化性改写和摘要式表达，不逐段翻译或复刻原文。

## 专名中文化

面向观众的中文文稿应使用中文世界里自然的叫法，而不是机械照抄英文或硬猜中文。

- 每个反复出现的专名先查 `proper_noun_glossary`，按 `audience_form` / `first_mention` 写。
- 中国地点、园区、政府项目、展厅、政策名即使原文是英文，也通常应本地化回中文。例如 `Tianshui Industry 2050` 不要直接口播成英文，应写成 `天水工业 2050`、`天水这个 2050 工业展厅` 或 planning 指定的自然说法。
- 中国人名只有拼音、无法确认汉字时，正文少用拼音；优先写角色和关系，例如“27 岁的天水年轻人”“一位当地妈妈”。不要编造 `Shi Tingting` 到底是哪几个汉字。
- 外国公众人物、公司和机构如果中文世界已有稳定叫法，必须使用稳定中文名，例如 `Elon Musk` 写 `马斯克`，`Jensen Huang` 写 `黄仁勋`，`Mark Zuckerberg` 写 `扎克伯格`，`Nvidia` 写 `英伟达`。
- 没有稳定中文名的外国小众人物，可以保留英文，但第一次要加身份，例如“欧亚集团分析师 Dan Wang”。
- `Zhipu` / `Zhipu AI` 写作 `智谱`。
- `high-tech` 通常写作 `高科技`；涉及产业政策时可写作 `先进制造`。除非原文或中文语境明确需要，不要反复写 `高技术`。
- 原文证据、图片 credit 或 source/article.txt 可保留英文；播客正文、字幕、章节图和封面标题应使用中文名。已确认的英文媒体 publication 必须中文化，例如 `Foreign Policy` -> `外交政策`，`The Economist` -> `经济学人`，`Bloomberg` -> `彭博社`。

## 质检

运行结构检查：

```bash
python /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-chinese-podcast-script/scripts/lint_podcast_script.py \
  <project>/podcast_script.md --host "Speaker 0" --expert "Speaker 1"
```

Gate 通过条件：

```text
podcast_script.md exists
planning/script_generation_report.md exists when planning artifacts are present
lint passes
正文 speaker turns only use Speaker 0/Speaker 1
host genuinely asks and redirects
host shows real confusion, mild friction, or listener empathy across segments
expert explains mechanisms clearly
major background detours map to episode_outline context_cards_to_use or article facts
opening or first two content segments use subject_orientation when available
recurring proper nouns follow article_brief.proper_noun_glossary when available
source mention follows episode_profile.source_mention_policy when available
confirmed publication uses Chinese source name in source line and opening; no raw English publication name leaks into audience-facing dialogue/subtitles
turn lengths are suitable for long-form dialogue and ASR alignment
script_hash is recorded for downstream gates
```
