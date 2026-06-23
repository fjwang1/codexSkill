---
name: article-podcast-chapter-visuals
description: 基于已定稿中文双人播客稿，先用原生 PPT Master deck 流程生成正常 PPTX，再用 ppt-master-deck-video-visuals 将该 deck 项目后处理为 4K chapter_XX.png 和 chapter_semantics.json。适用于已有 podcast_script.md 的项目；本 skill 不负责音频时间线绑定。
---

# 播客章节视觉

这个 skill 负责为视频生成 PPT Master 画面资产，但它不再要求 PPT Master 进入“章节图模式”。

正式方式是两段式：

```text
podcast_script.md
-> normal PPT Master deck project + PPTX
-> postprocess existing deck to chapter_XX.png + chapter_semantics.json
```

时间线绑定由下一步 `article-podcast-chapter-timeline-binding` 完成。

## 产物独立性提示

每次运行都必须为当前视频项目重新生成 PPT Master deck 和章节图。只能复用公共 PPT Master 模板目录、脚本、字体和缓存；不得复用任何历史任务、demo、sample、comparison、validation 或其他项目的 PPTX、SVG、章节图、语义文件、文章、封面、音频、字幕、视频或 manifest。这是执行原则提示；本 skill 的最小脚本校验只验证 PPT Master 产物确实存在。

## 输入

```text
<project>/podcast_script.md
```

不要等待 `audio/dialogue_timeline.json`。本阶段可以和音频生成、ASR 对齐、标题、封面并行。

## 输出

```text
<project>/chapter_visuals/
  template_selection.json
  ppt_origin_validation.json
  chapter_semantics.json
  chapter_01.png
  chapter_02.png
  ...
  chapter_visuals_contact_sheet.jpg
```

`chapter_XX.png` 是普通 PPT Master deck 的逐页 4K 渲染结果。文件名叫 chapter 只是为了兼容视频合成流程，不代表 PPT Master 需要设计“章节卡片”。

## 生成方式

### Step 0: 自动选择 PPT Master Deck Template

默认必须从下面三套模板中选择一套，除非用户显式要求某个模板路径：

```text
editorial_magazine = /Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/editorial_magazine
swiss_grid = /Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/swiss_grid
risograph_zine = /Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/risograph_zine
```

第四套 `memphis_pop` 仍保留在 PPT Master 模板库中，但不进入正式视频流程的默认候选池；只有用户明确要求轻快、消费、青年文化、娱乐或活动感视觉时才使用。

选择依据优先读取：

```text
<project>/podcast_script.md
<project>/planning/article_brief.json           # if exists
<project>/planning/episode_profile.json         # if exists
<project>/planning/episode_outline.json         # if exists
<project>/source/source_metadata.json           # if exists
```

不要为了模板选择重新读取英文原文做内容改写；`podcast_script.md` 和 planning 摘要已经是节目语义源。

选择规则：

| Template | 适合内容 | 选择倾向 |
| --- | --- | --- |
| `editorial_magazine` | 外刊长文、城市/社会/经济、人文叙事、地方样本、人物和结构性分析 | 默认首选；当文章兼具叙事和分析时选它 |
| `swiss_grid` | 数据密度高、政策逻辑强、框架清晰、需要严肃判断和对比的文章 | 当文稿更像报告/政策分析/数字解释时选它 |
| `risograph_zine` | 观点鲜明、社会观察、文化感、街头感、强烈反差或批判性议题 | 当文章需要更强记忆点和 zine/editorial punch 时选它 |

必须写选择记录：

```text
<project>/chapter_visuals/template_selection.json
```

格式：

```json
{
  "schema_version": "ppt-master-video-template-selection.v1",
  "selected_template": "editorial_magazine",
  "template_path": "/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/editorial_magazine",
  "candidate_pool": ["editorial_magazine", "swiss_grid", "risograph_zine"],
  "reason": "文章是外刊长文解读，兼具地方叙事、经济结构和社会流动，适合杂志化编辑视觉。",
  "decision_basis": ["podcast_script.md", "planning/article_brief.json"],
  "rejected": [
    {"template": "swiss_grid", "reason": "数据重要但不是唯一主线"},
    {"template": "risograph_zine", "reason": "视觉冲击强，但可能压过外刊长文的稳重叙事"}
  ]
}
```

### Step 1: 正常 PPT Master Deck

调用：

```text
/Users/wangfangjia/.codex/skills/ppt-master-article-deck/SKILL.md
```

输入给最终 `podcast_script.md`，并必须显式传入 Step 0 选中的模板目录路径。输出是一个正常 PPT Master 项目和 PPTX。

每次运行本 skill 都必须为当前视频项目新建一个 PPT Master project。不要复用、引用或复制此前人工对比、验收、demo、comparison、sample 目录里的 PPT Master project/PPTX，即使文章和模板相同也不行。允许复用的是模板目录本身，不是已经生成过的 deck 成品。

新建项目建议放在 `/Volumes/GT34/Generated` 下，项目 slug 至少包含当前视频项目目录名和所选模板名；`template_selection.json` 必须在 Step 1 完成后补充记录：

```json
{
  "current_video_project": "/Volumes/GT34/english_aircle_to_video/<article_slug>_podcast_video",
  "ppt_master_project": "/Volumes/GT34/Generated/<fresh_project_slug>",
  "normal_pptx": "/Volumes/GT34/Generated/<fresh_project_slug>/exports/<deck>.pptx"
}
```

`ppt_master_project` 必须是本次运行新创建的项目，且其 `sources/` 内容来自当前视频项目的 `podcast_script.md`。

允许传给 PPT Master 的额外约束只有：

```text
canvas: PPT 16:9
target audience: 面向 B 站观众
template: <Step 0 selected explicit template directory path>
style goal: 继承所选模板，并优先生成更精致、更专业、更完整的演示文稿视觉系统
do not use black/dark main backgrounds by default
avoid generic dark tech-dashboard styling, neon blue/green palettes, and black-background highlight-line visuals
no visible source/footer attribution captions on slide canvases
no visible internal production notes, validation/sample labels, workflow labels, draft/debug labels, or other process notes on slide canvases
```

不要传入章节图、安全区、进度线、固定短标题、固定点数、信息图优先、语义 sidecar、时间线绑定等要求。

PPT Master 项目中必须能看到所选模板已复制进 `<ppt_master_project>/templates/`，尤其是 `templates/design_spec.md`。

### Step 2: Deck 后处理为视频图片

拿 Step 1 的 PPT Master 项目目录，调用：

```text
/Users/wangfangjia/.codex/skills/ppt-master-deck-video-visuals/SKILL.md
```

运行脚本：

```bash
PY=/Volumes/GT34/Caches/ppt-master-venv/bin/python
export PLAYWRIGHT_BROWSERS_PATH=/Volumes/GT34/Caches/ms-playwright
$PY /Users/wangfangjia/.codex/skills/ppt-master-deck-video-visuals/scripts/export_deck_video_visuals.py \
  <ppt_master_project> \
  --copy-to <project>/chapter_visuals
```

这个后处理只读取 `svg_final/` 或 `svg_output/` 和 notes，不改设计。

导出后立即运行最小来源校验：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-chapter-visuals/scripts/validate_ppt_chapter_origin.py \
  --project-dir <project>
```

这个脚本只验证两件事：

1. `<project>/chapter_visuals/template_selection.json` 里的 `ppt_master_project` 和 `normal_pptx` 存在、非空，且路径真实存在。
2. `ppt_master_project` 目录真实存在，且包含 `design_spec.md`、`spec_lock.md`、非空 `svg_output/` 或 `svg_final/`，以及 `exports/*.pptx`。

如果校验失败，停止在章节视觉阶段；不要用 Pillow、本地绘图、手写 PNG 或其他方式补章节图。

`scripts/generate_chapter_visuals_from_timeline.py` 只保留作旧调试脚本，不属于正式生产路径。

## 并行规则

`podcast_script.md` 定稿后即可启动本 skill，和标题、封面、VibeVoice 音频、ASR 对齐并行。

最终视频合成前必须另行完成时间线绑定：

```text
chapter_visuals/chapter_semantics.json
audio/dialogue_timeline.json
```

然后运行 `article-podcast-chapter-timeline-binding` 生成最终 timed `chapter_plan.json`。

## Gate

来源校验 gate 只要求脚本通过：

```text
chapter_visuals/template_selection.json exists
template_selection.json selected_template is one of editorial_magazine / swiss_grid / risograph_zine unless the user explicitly overrides
template_selection.json template_path is an absolute existing directory
template_selection.json records current_video_project, ppt_master_project, and normal_pptx
chapter_visuals/ppt_origin_validation.json exists
ppt origin validation script status is PASS
```

章节图输出契约：

```text
chapter_visuals/chapter_semantics.json exists
chapter_semantics.json has one entry per rendered slide image
each semantic entry identifies its image and gives enough text to understand what the slide is about
each chapter_XX.png exists and is 3840x2160
chapter_semantics.json has no start_sec/end_sec/start_turn/end_turn fields
no slide image contains visible source/footer attribution captions
no slide image contains visible internal production notes, validation/sample labels, workflow labels, draft/debug labels, or other process notes
chapter_visuals_contact_sheet.jpg exists
```

如果 gate 不通过，优先修复后处理；除非 PPT Master 项目本身失败，否则不要重写 PPT 设计。
