---
name: article-podcast-title-writing
description: 为英文文章中文播客视频生成标题。适用于已有 source/article.txt、source/source_metadata.json 和 podcast_script.md 的项目，需要产出 B 站封面大字 cover/cover_title.json 与发布标题 video_title.txt，并用外刊解读/知识区高点击标题标准做自检。
---

# 播客标题写作

这个 skill 只负责标题，不负责封面制图、音频、字幕或视频合成。它把文章和中文播客稿里的核心冲突，改写成适合中文视频平台的标题资产。

生成标题前，必须先读取 `references/title_examples.md`，优先模仿相近场景里的“更好”取舍；不要把样例当作死模板。

## 输入

必须读取：

```text
<project>/source/article.txt
<project>/source/source_metadata.json
<project>/podcast_script.md
```

可选读取：

```text
<project>/source/fact_notes.md
<project>/source/images/
```

只给英文原题不够。英文标题只能作为信号，必须结合全文和中文稿判断真正的对象、冲突、后果和中文受众入口。

## 输出

```text
<project>/cover/cover_title.json
<project>/video_title.txt
```

`cover_title.json` 示例：

```json
{
  "title_text": "中国为何越来越倚重“院士治国”？",
  "title_lines": ["中国为何越来越", "倚重“院士治国”？"],
  "highlight_text": "院士治国",
  "highlight_texts": ["院士治国"],
  "highlight_style": {
    "color": "yellow",
    "font_weight": "bold"
  },
  "core_conflict": "顶尖科学家进入政府，技术竞争正在重塑中国治理精英",
  "source_title": "Xi Jinping gives China’s crack scientists new jobs inside government",
  "publication": "经济学人",
  "chinese_motifs": ["院士", "治国", "权力中枢"],
  "keyword_heat_check": {
    "used": true,
    "best_keywords": ["院士", "院士治国"],
    "weak_keywords": ["红色干部"],
    "evidence": "B 站 totalrank 搜索显示“院士”有多个百万级知识/科研视频，“红色干部”结果弱且多为思政素材。"
  },
  "read_aloud_self_check": {
    "status": "PASS",
    "read_aloud_version": "中国为何越来越倚重院士治国？",
    "is_smooth_spoken_chinese": true,
    "is_attractive": true,
    "not_keyword_stack": true,
    "issue_if_any": null,
    "revision_note": "读起来像一个自然问题句，主语、动作和反常识点完整。"
  },
  "candidate_title_sets": [
    {
      "strategy": "流量关键词版",
      "video_title": "《经济学人》：中国为何越来越倚重“院士治国”？",
      "cover_title_lines": ["中国为何越来越", "倚重“院士治国”？"],
      "highlight_texts": ["院士治国"],
      "score_reason": "院士是高注意力身份词，治国制造反常识。"
    },
    {
      "strategy": "冲突问题版",
      "video_title": "《经济学人》：科学家为什么开始进入中国权力中枢？",
      "cover_title_lines": ["科学家为什么", "进入中国权力中枢？"],
      "highlight_texts": ["科学家", "权力中枢"],
      "score_reason": "冲突清楚，但不如“院士治国”口语和有记忆点。"
    },
    {
      "strategy": "后果/反常识版",
      "video_title": "《经济学人》：中美科技战如何改写中国官场入场券？",
      "cover_title_lines": ["中美科技战如何", "改写中国官场入场券？"],
      "highlight_texts": ["科技战", "官场入场券"],
      "score_reason": "口语化强，但“做官”可能过度简化。"
    }
  ],
  "title_rationale": "用“院士治国”压缩制度变化，用“又红又专”制造政治与技术的双重张力。"
}
```

`video_title.txt` 示例：

```text
《经济学人》：中国为何越来越倚重“院士治国”？
```

## 封面标题重点规则

封面标题默认必须和发布标题的标题主体一致。发布标题 `video_title.txt` 可以带来源前缀，例如 `《经济学人》：`、`《彭博社》：`；封面标题不要带报纸/媒体名，也不要保留前缀冒号，只保留冒号后真正的标题主体。

`cover_title.json` 中：

- `title_text` 必须等于最终 `video_title.txt` 去掉来源前缀后的标题主体。若 `video_title.txt` 是 `《经济学人》：天水...`，则 `title_text` 从 `天水...` 开始。
- `title_lines` 只是 `title_text` 的视觉换行版本；去掉换行后必须和 `title_text` 完全一致。
- `highlight_texts` 标出黄色加粗重点；每一项都必须是 `title_text` 中真实出现的连续文字。
- `highlight_text` 是兼容旧封面脚本的主重点，必须等于 `highlight_texts[0]`。
- `highlight_style` 固定记录 `{"color": "yellow", "font_weight": "bold"}`。

`highlight_texts` 允许 1-3 个不重叠重点片段，但不要把整句话都标黄。颜色由封面合成 skill 固定执行：普通文字白色，`highlight_texts` 黄色加粗。

```text
可以：
video_title.txt: "《纽约时报》：美国摆烂，为什么变成最烂闹剧？"
title_text: "美国摆烂，为什么变成最烂闹剧？"
title_lines: ["美国摆烂，为什么", "变成最烂闹剧？"]
highlight_texts: ["美国摆烂", "最烂闹剧"]

可以：
video_title.txt: "《经济学人》：天水押注高科技，为什么留不下年轻人？"
title_text: "天水押注高科技，为什么留不下年轻人？"
title_lines: ["天水押注高科技，", "为什么留不下年轻人？"]
highlight_texts: ["天水", "年轻人"]

不可以：
title_lines: ["机器人进厂", "天水掉队？"]
video_title.txt: "《经济学人》：机器人进厂的天水，为什么等不到好饭碗？"
```

重点块通常放最能抓眼的主对象、身份词、冲突词或后果词，例如 `天水`、`院士治国`、`AI抢饭碗`、`35岁魔咒`、`最烂闹剧`。如果一句话整体都重要，仍要挑 1-3 个最能帮助缩略图扫读的词；城市/地点主题优先把地名列入 `highlight_texts`，再选一个结果词或冲突词。

## 主题显名与人物红线

标题必须先判断文章的主叙事对象是什么，不要只追热词：

- 城市/地点主题：如果文章主动讲一个城市、地区或地标，且该地点承载了主要叙事和事实比例，最终 `video_title.txt` 必须直接出现地点名。更重要的是，地点名应优先放在标题主体开头，成为中文标题的主位/话题位，而不是藏在修饰语、宾语或后半句里。优先写 `天水为什么...`、`天水建起...为什么...`、`为什么天水留不下年轻人？`，少写 `机器人进厂的天水...`。不要因为地名搜索热度弱就删掉事实锚点。
- 人物主题：如果文章主动讲一个人，且这个人是主角，候选标题必须先判断是否能点名。能点名时，人物姓名也应优先放在标题主体开头或问题主位，例如 `马斯克为什么...`、`黄仁勋如何...`，不要只在后半句补一个名字。
- 中国政治人物红线：如果主角是中国政治人物，尤其党和国家主要领导人、现任或退休高层政治人物，不要把姓名做成封面或发布标题钩子，不要用擦边外号替代；应停止标题生成并要求人工确认是否改选文章或改成不可发布内部研究稿。
- 其他公众人物：如果主角是非主要政治领导人的商业、科技、文化或体育名人，例如马斯克、黄仁勋、库克，且姓名已被来源确认，可以在封面或发布标题中直接点名。姓名是事实锚点，不必因为搜索热度一般就拿掉。
- 如果主题是机构、公司、产品或政策，也按同样逻辑处理：核心对象应在发布标题中清楚出现，封面可以用更短的中文母题承接。

## 工作流

1. 提取事实锚点  
   从原文和播客稿中列出 3-5 个候选冲突：主角、变化、代价、反常识、后果。不要从文件名猜来源。

2. 确认来源前缀  
   如果 `source_metadata.json`、原文页眉或 `podcast_script.md` 来源行能明确确认 publication，必须转成中文来源名并用于 `video_title.txt` 前缀。不能确认就不要加来源。来源前缀是给中文观众看的媒体署名，不能原样保留英文；例如 `Foreign Policy` 写作 `外交政策`，`Foreign Affairs` 写作 `外交事务`，`Bloomberg` 写作 `彭博社`。

3. 判断主题显名和人物红线  
   判断主对象是城市/地点、人物、公司/机构、产品、政策还是抽象议题。城市/地点和可点名人物主题必须在最终发布标题中显名，并优先放到标题主体开头作为主位/话题位；中国政治人物红线触发时停止并人工确认，不继续生成可发布标题。

4. 提取中文流量关键词  
   先列出 6-12 个候选关键词。必须包含原文直译词和中文互联网转译词，尤其关注身份、阶层、权力、金钱、饭碗、教育、产业、科技、监管和国家队等中文平台高注意力词。

5. 寻找中文语境母题  
   把文章里的抽象概念转成中国用户熟悉的说法：制度经验、职场经验、教育身份、平台消费、社会新闻、产业地名、钱和饭碗。不要停留在外刊原词或翻译腔。

6. 查 B 站候选关键词视频热度  
   对最有希望的 3-6 个关键词或短词组使用下面的唯一热度参考工具。热度只辅助选词，不替代事实判断。不要用完整标题句子去搜热度。

7. 口语化压缩  
   先写出新闻腔版本，再压成中文短视频口语腔。删掉 `改写结构`、`重塑格局`、`推动转型`、`深层原因` 等公文/翻译腔词，换成 `抢饭碗`、`堵死`、`下单`、`上桌`、`上岸`、`出海`、`卡脖子`、`深圳造`、`国家队` 这类能让中文用户秒懂的动作词或短标签。

8. 区分热度词和表达钩子  
   热度工具查出来强的词，适合承担流量入口；搜索热度弱但很有中文口语反差的词，可以承担表达钩子。封面可以用表达钩子，发布标题必须补上强热度词和事实锚点。

9. 生成候选标题  
   至少生成 3 组候选发布标题，且三组必须来自不同策略：流量关键词版、冲突问题版、后果/反常识版。不要只换同义词。每组同时给出该发布标题的 `cover_title_lines` 视觉换行和 `highlight_texts`。若有城市/地点或可点名人物主角，至少两组候选的标题主体必须以该主角开头或用 `为什么<主角>...` 句式，最终选中组也必须做到主位优先。

10. 选择一组最终标题  
   最终 `cover_title.json.title_text` 必须等于最终 `video_title.txt` 去掉来源前缀后的标题主体。封面负责用换行和黄色加粗重点提升扫读，不负责另写一个短标题，也不显示报纸/媒体名。

11. 标题自读验收  
   最终写入前，必须把选中的标题主体当作中文口播句子自己读一遍，不看英文原题，不看内部解释，只看普通观众会看到的标题本身。
   - 读起来必须顺：主语、动作、冲突或问题关系清楚，不能像关键词硬拼。
   - 必须有吸引力：听完能立刻知道“谁遇到了什么反常识/后果/冲突”，而不是只看到几个热词。
   - 不通过时，回到候选标题重选或重写；不要靠在 `title_lines` 里换行来掩盖标题本体不顺。

   在 `cover_title.json` 中记录：

   ```json
   {
     "read_aloud_self_check": {
       "status": "PASS | NEEDS_FIX",
       "read_aloud_version": "去掉来源前缀和视觉换行后，按口播读出的标题",
       "is_smooth_spoken_chinese": true,
       "is_attractive": true,
       "not_keyword_stack": true,
       "issue_if_any": null,
       "revision_note": "为什么通过，或为什么回退重写"
     }
   }
   ```

12. 写入文件  
   创建 `cover/` 目录；写入 `cover_title.json` 和根目录 `video_title.txt`。不要在 `cover_title.json` 里设计底图、颜色或排版；底图由 `article-podcast-cover-image-generation` 负责，颜色和排版由 `bilibili-podcast-cover` 负责。

## B 站关键词热度工具

这是本 skill 唯一的外部热度参考工具。它用于比较候选关键词/短词组的视频搜索热度，帮助判断哪个词更像中文 B 站用户会点的词。

工具调用：

```text
mcp__bilibili_mcp.search_video
```

调用方式：

```json
{
  "keyword": "<候选关键词或短词组>",
  "order_type": "totalrank",
  "page": 1,
  "page_size": 8
}
```

对每个候选关键词或短词组各调用一次。可以并行调用。不要改用百度指数、微信指数、抖音指数或 Google Trends，除非用户另行要求。

不要用完整标题、长句或带多个判断的句子去搜热度。B 站搜索热度要查“词”，不是查“标题”。完整标题太长会稀释热度、引入噪声或误判。

```text
不要搜：科技竞争如何改写红色干部晋升规则
可以搜：院士
可以搜：院士治国
可以搜：体制内
可以搜：芯片
```

通常每个查询词控制在 2-6 个中文字符；专有组合词可到 8 个字。一个好标题只需要其中 1-2 个关键词有热度，不要求整句都能搜出高热度。

比较方法：

- 看头部视频播放量：是否有百万级、十万级、万级内容。
- 看搜索结果相关性：高播放内容是否真的围绕该关键词，而不是误命中。
- 看内容语境：是否属于知识区/社科/财经/科技/职场等目标受众，而不是无关娱乐、思政素材或低质搬运。
- 看词的中文平台自然度：搜索结果标题里是否自然出现这个词。
- 如果一个词有高播放、高相关、搜索结果丰富，它是强流量词。
- 如果一个词结果少、播放低、语境偏离或只有外媒翻译腔，它是弱词。

例子：

```text
“院士”：强。B 站有多个百万级知识/科研视频，搜索心智明确。
“红色干部”：弱。结果少且多为红色文化/思政素材，不是知识区标题钩子。
“体制内”：强。搜索联想和职场内容丰富，但使用时必须确认文章事实是否贴合。
“权力中枢”：偏弱。语义准确但书面，搜索热度不如更口语/社会化的词。
```

热度结果要写进 `cover_title.json.keyword_heat_check`。如果工具不可用，记录：

```json
{
  "used": false,
  "reason": "mcp__bilibili_mcp.search_video unavailable",
  "fallback": "used semantic and Chinese-platform judgment only"
}
```

重要：热度工具只能判断“搜索热度”，不能判断“表达巧劲”。有些词单独搜索不强，但作为中文语境母题非常好，例如 `下单`、`深圳造`、`堵死`、`抄不走`。这类词不要因为搜索弱就全部丢掉。

处理方式：

- 强热度词：适合放进发布标题或封面主体，例如 `院士`、`无人机`、`中国制造`、`AI抢饭碗`。
- 强表达钩子：适合放进封面短句，例如 `这单发基辅，下单莫斯科`、`抄不走？`、`堵死资金出海？`。
- 如果表达钩子搜索热度弱，发布标题必须补上强热度词和事实锚点。

```text
封面可以：这单发基辅 / 下单莫斯科
发布标题要补：俄乌无人机战，为什么都在抢中国零件？
```

## 外刊情报局式标题经验

不要翻译题目，要翻译冲突。

也不要只复述外刊眼里的冲突。外刊里的意识形态标签、制度标签、翻译腔词，必须先过中文平台语感。标题是给中文 B 站观众看的，不是给外刊读者看的。

## 中文语境母题

很多好标题不是因为用了一个热词，而是因为它套中了中文用户熟悉的表达模板。写标题时要主动寻找这些母题：

- 制度/体制母题：`体制内`、`编制`、`上岸`、`晋升`、`国家队`、`证监会`、`权力中枢`。
- 教育/身份母题：`院士`、`清北`、`985`、`博士`、`导师`、`学术打假`。
- 钱/阶层母题：`打富豪`、`均贫富`、`饭碗`、`裁员`、`买房`、`泡沫`、`富豪税`。
- 产业/地名母题：`深圳造`、`义乌`、`华强北`、`出海`、`代工`、`卡脖子`、`产业链`。
- 平台/消费母题：`下单`、`发货`、`退钱`、`堵死`、`薅羊毛`、`灰产`。
- 社会新闻母题：`买春`、`打假`、`塌房`、`跑路`、`罚款`、`被查`。

这些不是固定词库，不能硬套。只有文章事实支撑时才可以用。目标是把外刊抽象概念落到中国用户已有的心理模板里：

```text
新闻腔：中国产业链影响俄乌无人机供应
口语腔：这单发基辅，下单莫斯科

新闻腔：Z 世代社会主义关注财富再分配
口语腔：打富豪，禁 AI 抢饭碗

新闻腔：顶尖科学家进入政府治理体系
口语腔：院士治国？

新闻腔：中国跨境证券监管趋严
口语腔：堵死资金出海？
```

优先寻找一句中文用户会说、会转述、会在评论区复读的话。它可以口语、有反差、有一点锋利，但不能低俗、造谣或歪曲。

不要把所有候选都交给搜索热度裁决。`深圳造`、`下单` 这类词可能搜索热度不如 `无人机`，但它们能把严肃外刊议题压成一句中国用户听得懂、记得住的话。封面看“记忆点”，发布标题看“清楚和可搜索”。

## 口语化压缩

标题要像中文短视频标题，不像翻译腔新闻标题。

压缩规则：

- 把名词化表达改成动作：`就业岗位受到冲击` -> `抢饭碗`。
- 把抽象机制改成短标签：`供应链控制力` -> `深圳造`。
- 把长因果改成问题句：`政策红利向普通人分配` -> `AI 红利分给谁？`
- 把外刊判断改成中国话：`wealth redistribution` -> `打富豪、均贫富`。
- 保留文章事实中的锋利词，不要用 `结构性`、`复杂性`、`新格局` 把标题磨平。

每组候选标题都要做一次自检：

```text
新闻腔：AI 对白领岗位造成结构性冲击
口语腔：AI 开始抢白领饭碗？
```

最终标题应优先选择口语腔；只有当口语化会损害事实准确性时，才退回更克制的表达。

常见改写方式：

- 把抽象概念变成强名词：`comparative advantage` -> `最无解的优势`、`产业政策机器`。
- 把新闻描述变成问题句：`科学家进入政府` -> `中国为何越来越倚重“院士治国”？`
- 把制度变化压缩成短标签：`crack scientists in government` -> `院士治国`。
- 把反常识放前面：`特朗普如何让世界爱上中国`。
- 把风险数字和危险意象绑定：`32万亿美元` + `定时炸弹`。
- 把平台弱词删掉：不用 `深度解析`、`震惊`、`真相`、`一文看懂`。

好标题通常满足至少两项：

- 有明确对象：国家、公司、群体、人物、制度或产业。
- 有冲突：谁压过谁、谁复制不了谁、谁被谁改变。
- 有后果：饭碗、权力、资金、战争、债务、代际、产业。
- 有反常识：本应 A，结果 B。
- 有可视名词：机器、炸弹、饭碗、门槛、战场、牌桌、通行证。
- 有强流量词：这个词本身在中文平台有搜索心智或社交注意力。

但最终标题不能只满足“有热词”。选中前必须通过自读验收：把标题主体连续读出来，确认它像一句自然中文标题，而不是热词、对象和动作词的拼接。

常见高注意力词的类型，不是固定词库，不能硬套：

- 身份/阶层：院士、白领、清北、985、打工人、老板、富豪、体制内。
- 权力/资源：晋升、上位、权力中枢、国家队、证监会、牌桌、入场券。
- 钱/产业：美债、房地产、泡沫、出海、灰产、裁员、饭碗、AI。
- 科技/竞争：芯片、机器人、AI、卡脖子、产业政策、深圳造。

流量词必须服从文章事实。热词再热，如果文章不支撑，也不能塞进标题。

封面标题尤其要避免“只有情绪，没有对象”。隐喻词可以用，但必须和一个具体锚点绑定：

```text
不好：又红又专 / 才能上桌？
更好：又红又专 / 院士治国？
更好：科学家 / 进中枢？
```

如果标题里用了 `上桌`、`牌桌`、`饭碗`、`机器`、`炸弹` 这类强隐喻，另一行必须给出明确主体，例如 `院士`、`白领`、`美债`、`深圳造`、`产业政策`。

## 封面标题规则

`title_text` / `title_lines`：

- `title_text` 默认等于 `video_title.txt` 的标题主体，不包括 `《经济学人》：`、`《彭博社》：` 等来源前缀。
- `title_lines` 是 `title_text` 的视觉换行，不是短标题改写；`"".join(title_lines) == title_text`。
- 最好 2-3 行，最多 3 行。
- 每行 6-14 个中文字符优先。
- 至少包含一个具体主体或对象锚点，不能只有情绪词、价值判断或隐喻。
- 可以保留问号、逗号和标题主体内部必要标点；不要保留来源书名号和来源冒号。
- 不要写成完整摘要，不要写成论文题目。

封面标题应完整复用发布标题主体，例如：

```text
天水押注高科技，
为什么留不下年轻人？
```

不要写成：

```text
《经济学人》：
天水押注高科技，
为什么留不下年轻人？
```

## 发布标题规则

`video_title.txt`：

- 标题主体建议 18-36 个中文字符；来源前缀不计入。
- 若来源明确，格式为 `《<中文来源名>》：<标题主体>`。
- 来源前缀必须是中文媒体名；不要输出 `《Foreign Policy》：`、`《Bloomberg》：`、`《The Economist》：` 这类英文来源前缀。
- 如果来源是英文或中英混写，先查下面的常见映射；没有公认中文名时，保守直译成中文媒体名。若直译会明显误导或无法判断，应停止并要求人工确认，不要为了不断流程而保留英文来源名。
- `cover_title.json.publication` 也必须记录最终中文来源名，不要记录英文 publication。
- 标题主体必须包含对象、冲突、后果或反常识点中的至少两项。
- 去掉来源前缀后的标题主体必须与 `cover_title.json.title_text` 完全一致。
- 不歪曲文章事实，不把复杂议题压成单一阴谋论。

常见来源中文名：

```text
The Economist -> 经济学人
Financial Times -> 金融时报
The New York Times -> 纽约时报
The New Yorker -> 纽约客
The Atlantic -> 大西洋月刊
The Wall Street Journal -> 华尔街日报
WIRED -> 连线
Bloomberg -> 彭博社
Bloomberg Businessweek -> 彭博商业周刊
The Guardian -> 卫报
Foreign Policy -> 外交政策
Foreign Affairs -> 外交事务
The Washington Post -> 华盛顿邮报
Reuters -> 路透社
Associated Press -> 美联社
BBC -> 英国广播公司
CNN -> 美国有线电视新闻网
Nikkei Asia -> 日经亚洲
The Wire China -> 连线中国
Rest of World -> 世界其余地区
The Diplomat -> 外交学者
China Leadership Monitor -> 中国领导层观察
Time -> 时代
```

## 自检 Gate

写完后逐项检查：

```text
cover/cover_title.json exists
cover_title.json has title_text, title_lines, highlight_text, highlight_texts, highlight_style, core_conflict, chinese_motifs, keyword_heat_check, candidate_title_sets, title_rationale
cover_title.json has read_aloud_self_check with status PASS
read_aloud_self_check confirms the final title reads smoothly as spoken Chinese, is attractive, and is not a keyword stack
title_text equals video_title.txt after removing a leading source prefix like 《经济学人》：
title_text does not include the source publication prefix or its colon
joining title_lines with no separator equals title_text
title_lines has 1-3 lines and is readable for 4K thumbnail cover
title_lines is plain text, with no color markup or layout syntax
highlight_text equals highlight_texts[0]
highlight_texts has 1-3 non-overlapping continuous substrings found in title_text
highlight_style records color=yellow and font_weight=bold
title_text includes at least one concrete subject/object anchor from the article
title_text translates the article's core conflict, not merely the English title
candidate_title_sets has at least 3 different strategies, not near-duplicate rewrites
video_title.txt exists
if publication is clearly visible, video_title.txt starts with 《<中文来源名>》：
source prefix contains no raw English publication name, e.g. not 《Foreign Policy》：
if publication is not clearly visible, video_title.txt has no guessed source prefix
video_title.txt is specific and contains at least two of object/conflict/consequence/counterintuitive point
no unsupported clickbait words such as 真相/震惊/内幕/一文看懂
keyword_heat_check records whether B 站 keyword heat tool was used or why it was skipped
final title passes read-aloud self-check after keyword heat and candidate selection; if not, candidate selection must be rerun
no factual distortion or one-sided conspiracy framing
cover_title.json does not design the background image, colors, font, or title position
```
