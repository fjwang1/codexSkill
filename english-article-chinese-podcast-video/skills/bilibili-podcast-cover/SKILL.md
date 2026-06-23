---
name: bilibili-podcast-cover
description: 为中文播客视频生成 4K 16:9 B 站风格大字封面。适用于已有 cover/background.png 和由 article-podcast-title-writing 生成的 cover/cover_title.json，只负责用本地脚本在固定位置叠一层超大中文标题输出 cover_4k.png。
---

# B 站播客封面

这个 skill 负责封面第二层：在已经生成好的 `cover/background.png` 上叠缩略图式大字标题。它不负责写标题，也不负责选择或生成底图。

底图/主体图应优先由相邻 skill 生成：

```text
/Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-cover-image-generation/SKILL.md
```

该 skill 负责生成第一层：一张完整的 3840x2160 无字 AI 底图，主体在右侧，左侧天然留出标题空间。本 skill 只负责第二层：固定字体、固定位置、固定颜色规则叠字。

## 硬性禁令：本 skill 不得生成底图

本 skill 可以使用 Pillow/本地脚本做的事情只有一件：把中文标题叠到已经合格的 AI 底图上。严禁在本 skill 中用 Pillow、SVG、Canvas、matplotlib、PPT、网页截图、地图/轨迹图或任何本地程序化绘图来生成、修复、替换或补全 `cover/background.png`。

开始叠字前必须读取并检查：

```text
cover/image_source_manifest.json
cover/visual_subject.json
cover/background_raw.png
cover/background.png
```

如果 `image_source_manifest.json` 缺失，或其中 `source`、`image_type`、`model_or_tool`、provenance 字段包含 `local_pillow_generated`、`procedural_generated`、`programmatic_generated`、`manual_composite`、`screenshot`、`ppt_export`、`map_diagram`、`chart_generated` 等值，必须停止并回到 `article-podcast-cover-image-generation` 重做底图。

如果 manifest 不能证明 `background_raw.png` 来自 AI 图像生成模型/工具，也必须停止。不要临时画一个“看起来能用”的底图。

## 输入

```text
<project>/podcast_script.md
<project>/cover/background.png
<project>/cover/cover_title.json
<project>/source/fact_notes.md, optional
```

## 输出

```text
<project>/cover/
  cover_4k.png
```

## 内置字体资产

本 skill 自带封面标题字体：

```text
assets/fonts/XinQingNianTi.ttf
```

该字体来自本机剪映/VideoFusion 资源，字体内部名为 `WenYue XinQingNianTi / 文悦新青年体 W8`，剪映显示名为“新青年体”。字体文件标注为 `Non-Commercial Use / 非商用`；正式发布或商用前需要确认授权。

## 核心规则

不要让图像模型直接生成中文标题。正确流程是：

1. 读取 `cover/cover_title.json` 的 `title_text`、`title_lines`、`highlight_texts` 和兼容字段 `highlight_text`。
2. 读取第一层 `cover/background.png`。
3. 用本地脚本叠一层中文超大标题。

如果 `cover/background.png` 不存在，停止并先运行 `article-podcast-cover-image-generation`。不要在本 skill 中临时生成底图。

封面是缩略图，不是文章配图。标题必须占主要视觉比重，默认复用发布标题全文，通过换行、字号和黄色加粗重点吸引点击；底图负责给标题一个具体世界，而不是承担复杂解释。

固定结构：

```text
first layer: 3840x2160 full-bleed AI background.png with right-side dominant subject and clean left title space
second layer: 1 title block, 1-3 lines, huge Chinese type
no direct text generation by image model
no charts, no side cards, no multiple information modules
```

## 标题来源

`cover_title.json` 必须由 `article-podcast-title-writing` 先生成。本 skill 不重新发明标题，只能在发现标题明显不适合排版或不符合事实时停下，回到标题 skill 修正。

读取结构：

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
  "title_rationale": "用“院士治国”压缩制度变化，用“又红又专”制造政治与技术的双重张力。"
}
```

排版复查：

- `title_text` 是封面标题全文，默认应与 `<project>/video_title.txt` 去掉来源前缀后的标题主体一致。封面不要显示 `《经济学人》：`、`《彭博社》：` 等媒体名和前缀冒号。
- `title_lines` 是 `title_text` 的视觉换行版本，不是另写一个短封面标题；去掉换行后必须等于 `title_text`。
- 封面合成层默认会把标题重新折成 3 行渲染，以保持大字号和信息流一致性；这只改变换行，不改变、删减、替换或重写 `title_text` 的任何字符。
- `title_lines` 最好 2-3 行，最多 3 行；每行尽量 6-14 个中文字符。即使上游标题 skill 给出 2 行，本 skill 也可以在不改标题内容的前提下重新折为 3 行。
- `title_lines` 是纯文本，不带颜色语法。
- `highlight_texts` 标出需要渲染为黄色加粗的重点片段；合成脚本把这些片段渲染成黄色并加厚描边，其余文字白色。
- `highlight_text` 是兼容旧脚本的主重点，应等于 `highlight_texts[0]`。
- 每个 `highlight_texts` 项都必须是标题中真实出现的连续文字；允许 1-3 个不重叠重点片段。
- 如果整句话都重要，不要整句全黄；优先标出主对象、身份词或后果词。例如城市主题可同时标城市名和结果词。
- 一行太长时先调整视觉换行，不要删词改写成另一个封面标题；本 skill 的脚本会优先重排为 3 行，而不是继续把字号压小。
- 如果标题不够短、不够抓眼、像论文标题、事实有问题，停止并重跑 `article-podcast-title-writing`。

## 背景输入

`cover/background.png` 是输入，不是本 skill 的设计对象。它必须由第一层 skill 生成，且应满足：

```text
3840x2160
full-bleed AI-generated editorial image, no added blue base
image_source_manifest.json proves AI image generation provenance
not local_pillow_generated/procedural_generated/programmatic_generated/manual_composite/screenshot/ppt_export
right-side dominant subject
left title area clean and low-detail
no readable text/logo/watermark
```

如果背景主体位置、裁切或风格不对，回到 `article-podcast-cover-image-generation` 修正，不要在本 skill 里改背景逻辑。

## 本地合成

封面分两层：

```text
第一层：cover/background.png
  由 article-podcast-cover-image-generation 生成。
  固定 3840x2160 完整 AI 底图，右侧有主体，左侧留给标题。

第二层：cover/cover_4k.png
  由本 skill 合成。
  读取 cover/background.png 和 cover/cover_title.json，在固定位置叠新青年体标题。
```

第一层脚本在相邻 skill：

```bash
python /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/article-podcast-cover-image-generation/scripts/compose_background_layer.py \
  --input <project>/cover/background_raw.png \
  --out <project>/cover/background.png
```

第二层使用本 skill 下脚本：

```bash
python /Users/wangfangjia/.codex/skills/english-article-chinese-podcast-video/skills/bilibili-podcast-cover/scripts/compose_editorial_cover.py \
  --background <project>/cover/background.png \
  --out <project>/cover/cover_4k.png \
  --title-json <project>/cover/cover_title.json
```

如果系统 Python 没有 Pillow，使用 Codex runtime Python：

```bash
/Users/wangfangjia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 ...
```

## 默认视觉参数

- 画布：`3840x2160`。
- 默认中文标题字体：`assets/fonts/XinQingNianTi.ttf`（文悦新青年体 W8 / 剪映“新青年体”）。
- 如内置字体不可用，才回退到系统中文粗黑体或模拟加粗。
- 普通标题：白色 `#FFFFFF`。
- 重点标题：亮黄 `#F9F850`，并用更厚描边做视觉加粗。
- 同一封面标题块内所有渲染行必须使用同一字体和同一字号；优先把标题重排为 3 行以使用接近三行模板的大字号，不要因为 2 行标题中某一行过长而把整块字压得很小。
- 厚黑描边，4K 下通常 28-36 px。
- 黑色阴影，不使用明显的文字卡片。
- 文字位置固定：左上 x=384；文字最大宽度约 2450px，以支持三行大字号标题。
- 标题块占左侧约 `60%` 内容区；图片主体在右侧，左侧必须留给标题。

## Gate

通过条件：

```text
cover/background.png exists
cover/cover_title.json exists
cover/image_source_manifest.json exists and confirms AI-generated background provenance
cover/image_source_manifest.json does not contain local_pillow_generated, procedural_generated, programmatic_generated, manual_composite, screenshot, ppt_export, map_diagram or chart_generated
cover/visual_subject.json exists and records strategy, style, image_prompt and negative_prompt
cover/cover_4k.png exists
cover/cover_4k.png is 3840x2160
Chinese title text is burned into cover_4k.png
all title lines use the same font family and font size; highlight changes color/weight only, not line-level size
rendered title is preferably 3 visual lines; if source title_lines has 1-2 lines, cover composition may reflow it to 3 lines while preserving joined title text exactly
title is large and readable when scaled to mobile thumbnail size
background has one clear visual subject and no readable stray text/logo/watermark
```

如果第一版“审美不错但不抓眼”，通常说明标题不够短、不够大或底图没有主体。标题问题回到 `article-podcast-title-writing`；底图主体、留白或风格问题回到 `article-podcast-cover-image-generation`；本 skill 只调整叠字尺寸和位置，不换底图。
