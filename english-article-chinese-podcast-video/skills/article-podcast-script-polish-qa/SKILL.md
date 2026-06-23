---
name: article-podcast-script-polish-qa
description: 对英文外刊文章中文双人播客稿做播客感润色和事实边界 QA。适用于已有 planning/*.json、source/article.txt 和 podcast_script.md 或 draft_podcast_script.md 的项目；输出 polish_report.md，并将稿件修成更自然、更有对话感、更少翻译腔、不过度编造的最终 podcast_script.md。
---

# 播客稿润色与 QA

这个 skill 负责把可用初稿变成真正像中文播客的终稿。它不是重写主题，不新增未经规划的事实；它修对话感、口语化、节奏、来源露出和事实边界。

## 输入

```text
<project>/source/article.txt
<project>/source/source_metadata.json
<project>/planning/article_brief.json
<project>/planning/context_cards.json
<project>/planning/episode_profile.json
<project>/planning/speaker_profile.json
<project>/planning/episode_outline.json
<project>/podcast_script.md or <project>/draft_podcast_script.md
```

## 输出

```text
<project>/podcast_script.md
<project>/planning/polish_report.md
```

如果输入是 `podcast_script.md`，可先复制其内容作为修改对象，不需要保留旧稿。若用户要求保留旧稿，另存 `draft_podcast_script.md`。

## 编辑原则

1. 保留事实，改善说法。
2. 只使用原文和 `context_cards.status=usable` 的背景。
3. 外部背景必须服务于理解主线，不能变成百科支线。
4. 开头可以明确说在讲《<中文来源名>》的一篇文章；后面少说“文章说/文中提到”。如果来源在 metadata 里是英文，先中文化，例如 `Foreign Policy` 写作 `外交政策`。
5. 允许主持人轻微误解、反驳、停顿式追问，让分析者澄清。
6. 不为了 TTS 短句牺牲自然表达。

## 播客感检查

逐段检查并修复：

```text
host_confusion:
  主持人是否有真实困惑，而不是只递问题？
mild_friction:
  是否有轻微反驳、误解、换位思考或“等等，这里我没想明白”？
background_detour:
  是否有短暂离开文章半步的背景解释？
subject_orientation:
  开头或前两段是否自然交代了主对象是谁/在哪/是什么，且不是百科堆砌？
return_to_thesis:
  背景解释后是否回到文章主线？
human_stakes:
  宏观机制是否落到人、城市、家庭、工作或生活感受？
```

## 口语化规则

优先把书面连接词换成真实口播：

```text
这听起来有点刺耳 -> 这感觉不太对劲啊
这就有点刺耳了 -> 这个反差很大 / 这感觉不太对劲啊 / 这个数字有点扎心
这个判断比较准确 -> 我觉得可以这么说
这就是核心问题 -> 问题就在这儿
由此可见 -> 所以你看
换句话说 -> 说白了 / 更直白一点
文章提到 -> 《<中文来源名>》抓了一个细节 / 这里有个细节很说明问题
文中有一位 -> 里面有个受访者 / 有个当地年轻人的说法很扎心
```

不要把所有句子都改成网络口水话。目标是自然、有思考，不是轻佻。

除非真的在描述声音或强烈冲击，不要把“刺耳”当泛用形容。主持人的默认反应应该更像普通人现场想问题，而不是书面评论。

## 术语和来源行

- 检查 `article_brief.terminology_glossary`，把机械直译改成中文播客自然写法。
- 检查 `article_brief.proper_noun_glossary`，把专名改成中文听众自然听到的形态。
- `high-tech` 多数时候写 `高科技`；产业政策语境可写 `先进制造`；避免全文反复写 `高技术`。
- 来源行不要重复中英文来源名。推荐：`来源文章：《经济学人》China’s high-tech rise is leaving much of the country behind`。如果原始 publication 是 `Foreign Policy`，来源行和口播都写 `《外交政策》`，不要写 `《Foreign Policy》`。
- 中国地点、园区、政策、展厅和项目名如果原文是英文转写或英文翻译，正文通常应本地化回中文。例如 `Tianshui Industry 2050` 应改为 `天水工业 2050` 或 planning 指定的自然说法。
- 中国人名只有拼音且汉字无法确认时，不要编造汉字，也不要反复保留拼音；正文优先改成角色描述，例如“当地一位年轻人”“一位当地妈妈”，并在 `polish_report.md` 记录原文拼音。
- 外国公众人物和机构有稳定中文名时必须使用中文名，例如 `Elon Musk` -> `马斯克`，`Jensen Huang` -> `黄仁勋`，`Nvidia` -> `英伟达`；无稳定中文名的小众人物可保留英文并补身份。

## 来源露出规则

推荐：

```text
开头：
  我们今天看《经济学人》一篇文章，它抓了一个很反直觉的问题...
  我们今天在《外交政策》看到一篇文章，它问的是台海导弹防御能不能照搬伊朗经验...

中间少量：
  《经济学人》用了一个细节...
  里面有个受访者的说法很说明问题...
```

避免高频：

```text
文章说...
文章提到...
作者认为...
原文里...
这篇文章指出...
```

## 事实 QA

输出前逐项检查：

- 数字是否来自原文或 usable 背景卡。
- 中文专名是否符合 `proper_noun_glossary`；不确定汉字的中国人名是否已用角色描述替代，而不是口播拼音。
- 是否残留不该出现在中文正文里的英文项目名、英文机构名或 pinyin 人名。
- 如果 `source_metadata.json.publication` 是英文，来源行、开头口播和会进入字幕的正文是否都已使用中文来源名，且没有残留 `Foreign Policy`、`Bloomberg`、`The Economist` 这类 raw publication。
- 背景补充是否有来源，或明确是根据原文作出的解释性推断。
- 是否新增了文章没有、背景卡也没有的具体事实。
- 是否把外部背景说成文章观点。
- 是否误译关键词，例如 `investing in people` 应写“投资于人”，不是“投资人”。
- 如果存在 `subject_orientation` 卡，开头或前两段是否使用；如果没有使用，是否有明确理由。

## polish_report.md

记录：

```text
status: PASS | NEEDS_FIX
main_changes:
  - ...
podcast_feel_checks:
  host_confusion: PASS/FAIL
  mild_friction: PASS/FAIL
  background_detour: PASS/FAIL
  subject_orientation: PASS/FAIL
  return_to_thesis: PASS/FAIL
  human_stakes: PASS/FAIL
fact_boundary:
  unsupported_claims_removed: ...
  uncertain_names_kept_in_original_form: ...
  proper_nouns_localized: ...
  terminology_fixed: ...
  external_cards_used: ...
remaining_risks:
  - ...
```

## Gate

通过条件：

```text
podcast_script.md exists
lint_podcast_script.py passes
planning/polish_report.md status is PASS
正文 only uses Speaker 0:/Speaker 1:
opening mentions confirmed publication with Chinese source name if source_metadata confirms it
audience-facing dialogue that will become subtitles has no raw English publication name
after opening, high-frequency article/source phrases are rare and purposeful
every major background detour maps to context_cards or article facts
subject_orientation is used near the opening when available
recurring proper nouns follow article_brief.proper_noun_glossary when available
host has real confusion or mild friction in multiple segments
no unsupported concrete facts remain
```
