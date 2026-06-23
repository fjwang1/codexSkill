---
name: article-podcast-chapter-timeline-binding
description: 将 PPT Master deck 图片导出产出的 chapter_semantics.json 和 4K slide images，绑定到最终 VibeVoice 音频的 audio/dialogue_timeline.json，生成可供静态视频合成消费的最终 chapter_plan.json。适用于已有 podcast_script.md、chapter_visuals/chapter_semantics.json、chapter_*.png 和 audio/dialogue_timeline.json 的中文双人播客项目。
---

# 播客章节图时间线绑定

这个 skill 负责把已生成的 PPT slide images 和解释语义绑定到最终音频时间轴。它不重新设计 slides，不重新生成 PNG，不改播客稿，不改音频，只产出最终可供 `article-podcast-static-video` 消费的 `chapter_visuals/chapter_plan.json`。

## 输入

```text
<project>/podcast_script.md
<project>/audio/dialogue_timeline.json
<project>/chapter_visuals/chapter_semantics.json
<project>/chapter_visuals/chapter_01.png
<project>/chapter_visuals/chapter_02.png
...
```

不要读取原始英文文章做绑定。绑定依据是最终播客稿和最终音频对齐时间轴，避免原文结构误导。

`chapter_semantics.json` 来自 `ppt-master-article-deck` deck 图片导出模式。每个 entry 应至少能让本 skill 判断“这张 slide image 讲什么”，常见字段如下：

```json
{
  "chapter_index": 1,
  "image": "chapter_01.png",
  "chapter_title": "...",
  "summary": "...",
  "points": ["..."],
  "interpretation": "...",
  "visual_intent": "...",
  "script_anchor_hint": "..."
}
```

## 输出

```text
<project>/chapter_visuals/
  chapter_turn_mapping.json
  chapter_plan.json
  chapter_timeline_binding_report.md
```

`chapter_plan.json` 是唯一给视频合成消费的最终章节时间轴。

## 绑定原则

- PPT Skill 决定 slide 数量、deck 结构、图片和语义。
- 上游 PPT 模板选择只影响视觉风格和 slide 语义表达；本 skill 不读取、不重选、不按模板名分配时间线。
- 本 skill 只决定每张 slide image 对应最终音频里的哪一段。
- 先由 AI 读 `chapter_semantics.json`、`podcast_script.md` 和 `audio/dialogue_timeline.json.turns`，按语义为每张 slide image 选择连续 `start_turn/end_turn`。
- AI 只写 turn 范围，不手写秒数。秒数必须由确定性脚本从 `dialogue_timeline.json` 填入。
- slide 顺序必须保持和 `chapter_semantics.json` 一致。
- turn 范围必须单调、连续或近似连续；不允许倒序、重叠或跳过大段核心内容。
- 如果一两个 turn 的边界差 1-2 秒可以接受，优先保持语义正确。

## AI Mapping

先写 `<project>/chapter_visuals/chapter_turn_mapping.json`：

```json
{
  "schema_version": "article-podcast-chapter-turn-mapping.v1",
  "method": "ai_semantic_turn_binding",
  "chapters": [
    {
      "chapter_index": 1,
      "start_turn": 1,
      "end_turn": 4,
      "confidence": "high",
      "evidence": "这一章解释天水展厅、老工业城市和 GDP 反差，对应第 1-4 个 turn。"
    }
  ]
}
```

Mapping 时优先看这些字段；缺失时用现有字段里的标题、摘要、说明文本和播客稿上下文判断：

- `chapter_title`
- `summary`
- `points`
- `interpretation` / `speaker_note`
- `visual_intent`
- `script_anchor_hint`
- `dialogue_timeline.turns[].text`
- `podcast_script.md` 中的 `##` 小节标题和 speaker turn 顺序

不要为了平均分配而牺牲语义。一个 slide image 可以覆盖多个 speaker turn。

## Deterministic Binding

写完 `chapter_turn_mapping.json` 后运行：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-timeline-binding/scripts/bind_chapter_timeline.py \
  --project-dir <project>
```

脚本会：

1. 读取 `chapter_semantics.json`、`chapter_turn_mapping.json` 和 `audio/dialogue_timeline.json`。
2. 验证章节数、图片存在、turn 范围、时间单调性。
3. 从 timeline 计算 `start_sec/end_sec`。
4. 生成连续视觉区间：第 N 章的 `end_sec` 等于第 N+1 章的 `start_sec`，最后一章覆盖到音频结尾。
5. 写入最终 `chapter_plan.json` 和 `chapter_timeline_binding_report.md`。

连续区间很重要：静态视频合成脚本按 `end_sec - start_sec` 拼接章节图片。如果中间留空隙，画面时间轴会漂移。

## Fallback

只有在验收或调试时，且 AI mapping 无法及时生成，才允许使用脚本的启发式 fallback：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-timeline-binding/scripts/bind_chapter_timeline.py \
  --project-dir <project> \
  --allow-heuristic
```

正式生产默认应写 `chapter_turn_mapping.json`，不要依赖平均切分。

## Gate

通过条件：

```text
chapter_visuals/chapter_semantics.json exists
chapter_visuals/chapter_turn_mapping.json exists
chapter_visuals/chapter_plan.json exists
chapter_visuals/chapter_timeline_binding_report.md exists
chapter_plan.json has the same chapter count as chapter_semantics.json
each entry has image and enough semantic text to bind against the dialogue timeline
each chapter has start_turn/end_turn/start_sec/end_sec
all images exist and are 3840x2160
start_turn/end_turn are monotonic and valid against dialogue_timeline.turns
start_sec/end_sec are derived from audio/dialogue_timeline.json, not invented
visual intervals are continuous: chapter[i].end_sec == chapter[i+1].start_sec within 0.01s
first chapter starts at 0.0
last chapter ends at audio duration
chapter_timeline_binding_report.md records mapping evidence and any low-confidence boundary
```

如果 gate 不通过，修复 `chapter_turn_mapping.json` 或回到 PPT deck 图片阶段重做语义，不要让视频合成消费未定时或漂移的 plan。
