---
name: article-podcast-cover-image-generation
description: 为英文外刊文章中文播客视频生成封面无字主体图。适用于已有 source/article.txt、source/source_metadata.json、podcast_script.md 和 cover/cover_title.json 的项目；优先使用可落盘 AI 图像生成工具产出完整底图；当当前环境的 AI 图像工具无法提供可保存文件时，允许使用来源清晰、授权可记录、主题相关的真实图片作为底图；严禁本地 Pillow/程序化绘图或占位图替代，输出 cover/background.png、cover/visual_subject.json 和 image source manifest。
---

# 封面主体图生成

这个 skill 只负责封面底图，不负责写标题、不负责最终叠字。目标是为 B 站大字封面提供一张**无字、单主体、低复杂度、能被一眼识别、左侧可叠标题**的完整 AI 生成底图。

## 输入

```text
<project>/source/article.txt
<project>/source/source_metadata.json
<project>/podcast_script.md
<project>/cover/cover_title.json
<project>/source/images/, optional
```

## 输出

```text
<project>/cover/
  visual_subject.json
  image_source_manifest.json
  background_raw.png
  background.png
```

`background_raw.png` 是 AI 生成的完整无字底图。`background.png` 是标准化后的 3840x2160 底图：仍然是同一张完整图，不加蓝底、不贴右侧框。它必须已经在画面右侧包含主体，并在左侧留下干净标题区，供 `bilibili-podcast-cover` 叠加标题。

从最终封面看，结构仍然是两层：第一层是完整底图，第二层是本地叠字。从图像生成看，第一层本身是一张完整图片，不再拆成“蓝色背景 + 右侧主体图”。

## 硬性禁令：不得用程序化或占位图冒充底图

`cover/background_raw.png` 必须来自以下可审计来源之一：

1. AI 图像生成模型或工具直接产出的完整无字底图。
2. 项目 `source/images/` 中随文章一起提供、且主题相关的原始图片。
3. Wikimedia Commons、官方媒体包、明确授权图库或其他能记录来源 URL、作者/机构和 license 的真实图片。

严禁用 Pillow、SVG、Canvas、matplotlib、PPT、draw.io、网页截图、视频帧、地图/轨迹图或任何本地程序化绘图来生成或替代底图主体。

允许使用 Pillow/本地脚本的范围只有：

- 对 AI 生成结果做等比 cover 缩放/裁切，输出 `cover/background.png`。
- 检查尺寸、格式、hash。
- 在后续 `bilibili-podcast-cover` 中叠中文标题。

Pillow/本地脚本不得创建雷达、地图、人物、物件、场景、光效、轨迹、箭头、图表或任何可被观众理解为底图主体的视觉元素。不得把 `source`、`image_type`、`model_or_tool` 或任何 provenance 字段写成 `local_pillow_generated`、`procedural_generated`、`programmatic_generated`、`manual_composite`、`screenshot`、`ppt_export` 等并继续通过。

如果 AI 图像生成不可用、超时、失败或当前工具只能返回不可落盘的图片对象，不要用程序化图兜底；先尝试 `source/images/` 或可记录授权的真实图片路线。只有当 AI、source image、licensed/reference image 都不可用或不合格时，才停在本阶段并报告：

```text
BLOCKED: cover_background_ai_generation_unavailable
```

如果 AI 图像生成结果质量不合格，必须报告：

```text
NEEDS_FIX: cover_background_ai_generation_failed
```

不得生成占位图、程序化兜底图、地图示意图或抽象科技背景来代替。真实图片兜底必须是主题相关、构图可用、没有可读文字/logo/watermark，且 provenance 写入 manifest。

## 总原则

封面图片不是文章配图，不负责解释全文。它只负责给标题一个视觉锚点。

优先级：

1. **AI 生成具体公众人物风格图**：如果文章讲具体人物，先了解人物长相、身份和职业符号，但最终仍生成高冲击力封面图，不直接使用随手拍/百科图。
2. **AI 生成代表性人物**：没有具体人物时，生成一个代表文章主题的人，例如白领、科学家、裁判、外卖员、学生、工人。
3. **AI 生成强物件**：人物弱时用一个大物件，例如手机、芯片、无人机、护照、美元、药瓶、工厂机械臂。
4. **AI 生成简单场景**：最后才用场景，例如办公室、实验室、教室、工厂、球场。

不要用随机网络图片、复杂报纸版面、网页截图、满屏小字、logo、水印或多主体拼贴。真实人物图只可作为视觉参考和事实核验，不作为最终封面图，除非用户明确要求并且授权/来源完全清楚。非人物的真实图片兜底也必须有清楚来源与授权记录，且只能作为底图素材，后续仍按本 skill 标准化为 `background.png`。

## 工作流

1. 读文章和标题  
   从 `article.txt`、`podcast_script.md` 和 `cover_title.json` 里提取：具体人物、群体身份、核心冲突、物件、场景。

2. 判断是否有具体公众人物  
   具体人物包括政治人物、运动员、CEO、科学家、裁判、作者、当事人等。若人物是文章主角，先尝试真实头像路线。

3. 人物参考路线  
   如果文章涉及具体人物，可以使用本 skill 的 Wikimedia/Wikidata 脚本搜索可追溯图片，了解人物长相、年龄、发型、服装和职业身份。该图默认只作参考，不直接用作封面：

   ```bash
   python scripts/search_wikimedia_person_image.py \
     --name "<person name>" \
     --role-keywords "<role/context keywords>" \
     --out-dir <project>/cover/person_image_search \
     --download-best
   ```

   `--role-keywords` 必须来自文章事实，用英文逗号分隔，例如：

   ```text
   Ma Ning -> referee,football,FIFA,World Cup,Qatar
   Jensen Huang -> Nvidia,CEO,chip,AI
   Donald Trump -> president,United States
   ```

   不能只按姓名盲选第一张。重名人物很常见，必须用职业、机构、赛事、国家或文章关键词重排结果。

   参考图不能替代封面图。百科/Commons 图片往往像随手拍，构图弱、冲击力弱，不适合作为 B 站封面主体。参考搜索结果只写入 `image_source_manifest.json` 的 `reference_images`。

4. AI 生成路线  
   优先调用 `imagegen` 或明确可审计的 AI 图片生成工具，生成一个冲击力强的主体图并保存为 `cover/background_raw.png`。可以生成“一个中国足球裁判”“一个疲惫白领”“一个中国院士”，但不要生成伪造新闻现场、伪造官方照片或带真实媒体标识的图片。不得把 prompt 写好后再用 Pillow、SVG、Canvas 或脚本自己画出来。

   如果 `imagegen` 只能在对话界面返回图片而无法暴露文件路径，不能假装已经生成文件，也不能从临时目录里捡无关图片。此时进入真实图片兜底路线。

   抽象、地缘政治、军事、科技或产业主题也必须落到具体 AI 视觉主体：雷达车、防空阵地、拦截弹发射车、指挥室里的操作员、海岸雷达塔、芯片晶圆、工厂机械臂等。不要用地图轮廓、弹道弧线、流程图、图表或抽象光效当主体。

   `background_raw.png` 是一张完整 16:9 底图，可以理解为背景和主体共同构成的一层完整图：

   - 背景：极简、低复杂度，只提供地点/气氛。
   - 主体：有影响力、有视觉冲突感，放在右侧或右上/右中，主体要大，但不能贴到画面边缘。
   - 左侧：留出大面积干净区域给中文标题；不能出现人脸、主要物件、可读文字、logo 或高对比纹理。

   图片必须满足：

   ```text
   no text
   no logo
   no watermark
   single subject
   large subject
   simple background
   strong contrast
   subject on the right
   complete head/upper body, not cropped at the edge
   clean empty headline space on the left 55-65% of the image
   thumbnail-readable
   ```

5. 真实图片兜底路线

   只有当 AI 生成不可落盘或不可用时才使用。本路线必须从以下来源选择：

   - `source/images/` 中随文章提供的图片。
   - Wikimedia Commons 等可追溯授权来源。
   - 官方媒体包或明确授权图库。

   真实图片兜底要求：

   ```text
   topic-relevant
   no readable text
   no logo
   no watermark
   one dominant subject or one simple food/object/scene
   left side can be cropped into clean headline space
   source_url/license/author_or_provider recorded
   ```

   下载或复制后的原始底图仍保存为 `cover/background_raw.png`。不得使用新闻网页截图、搜索结果截图、社交媒体截图、带大段文字的图表或低清缩略图。

6. 标准化完整底图  
   `cover/background_raw.png` 保存后，必须用固定脚本标准化为 3840x2160：

   ```bash
   python scripts/compose_background_layer.py \
     --input <project>/cover/background_raw.png \
     --out <project>/cover/background.png
   ```

   这个脚本只能做等比 cover 缩放/裁切，不得在脚本内生成、绘制或补充主体元素。若 `background_raw.png` 既不是 AI 图像生成产物，也不是来源清晰的 source/licensed/reference 图片，禁止运行本步骤。

   规则：

   ```text
   画布：3840x2160
   不添加蓝底
   不把主体图贴进右侧框
   只做等比 cover 缩放/裁切
   标题安全区：x=384, width=1843；该区域必须来自 AI 图本身的干净留白
   ```

7. 写 `visual_subject.json`

   ```json
   {
     "strategy": "real_person|representative_person|object|scene",
     "style": "cinematic_realism_poster|bold_american_comic_poster",
     "person_name": "Ma Ning",
     "visual_subject": "Chinese football referee, half-body, whistle and referee uniform, stadium background",
     "core_conflict": "中国男足无缘世界杯，但中国裁判登上世界杯",
     "image_prompt": "single Chinese football referee, half body, serious expression, referee uniform, whistle, stadium lights, simple background, no text, no logo, editorial thumbnail style, high contrast",
     "negative_prompt": "text, logo, watermark, newspaper page, busy collage, multiple tiny people, fake magazine cover",
     "composition": {
       "subject_position": "right",
       "subject_scale": "large",
       "left_headline_space": "clean, low detail, no face/object/text",
       "background_complexity": "low",
       "added_blue_base": false
     }
   }
   ```

8. 写 `image_source_manifest.json`

   `image_source_manifest.json` 必须能证明 `background_raw.png` 的来源。AI 生成记录至少包含：

   ```json
   {
     "image_type": "ai_generated_background",
     "source": "imagegen",
     "model_or_tool": "imagegen",
     "generation_date": "YYYY-MM-DD",
     "image_prompt": "...",
     "negative_prompt": "...",
     "style": "cinematic_realism_poster",
     "strategy": "representative_person|object|scene|real_person",
     "contains_real_person": false
   }
   ```

   真实图片兜底记录至少包含：

   ```json
   {
     "image_type": "licensed_reference_background",
     "source": "wikimedia_commons|source_images|official_media_kit|licensed_image_source",
     "model_or_tool": null,
     "generation_date": null,
     "source_url": "...",
     "license": "...",
     "author_or_provider": "...",
     "downloaded_file": "cover/background_raw.png",
     "selection_reason": "topic-relevant simple food/supermarket/consumer image with clean crop potential",
     "contains_real_person": false
   }
   ```

   - 真实头像参考：只记录 query、source_url、license、artist、credit、downloaded file、reject/accept reason 到 `reference_images`；参考图不能成为最终底图来源，除非最终 `image_type` 明确写成 `licensed_reference_background` 且授权/来源完全清楚。
   - AI 生成：记录 prompt、negative_prompt、model/tool、generation date、whether it depicts a real person。
   - 禁止来源值：`local_pillow_generated`、`procedural_generated`、`programmatic_generated`、`manual_composite`、`screenshot`、`ppt_export`、`map_diagram`、`chart_generated`。

## 固定风格

只保留两种默认风格：

1. `cinematic_realism_poster`  
   电影海报写实风。真实感、暗背景、强侧光、半身近景、背景虚化、有压迫感。适合多数外刊文章，是默认风格。

2. `bold_american_comic_poster`  
   硬核美漫海报风。粗黑线、强阴影、高对比、轮廓硬、颜色更冲。适合冲突特别强、标题特别 B 站化的文章。

不要使用日漫、软萌漫画、水彩、油画、扁平插画、抽象科技背景。

## 视觉主体规则

人物优先，因为人物最容易在信息流里形成停留。当文章没有具体人物时，优先生成“代表这篇文章的人”：

```text
AI 抢白领工作 -> 疲惫白领 + AI 蓝光屏
院士进政府 -> 科学家/院士风格人物 + 会议桌/文件
中国制造抄不走 -> 工厂工人或机械臂 + 单个产品
年轻人不结婚 -> 年轻人 + 婚戒/账单/空房间
外卖骑手困境 -> 骑手 + 电动车 + 城市路口
```

## 生成提示词模板

真实人物不可用时，使用这个模板写 prompt：

```text
<style>, single <subject>, <one identity symbol>,
<one conflict/location symbol>, large subject on the right,
complete head and upper body visible, not touching the image edge,
clean low-detail empty space on the left 55-65% for huge Chinese headline,
simple background, strong contrast, dramatic thumbnail,
no text, no logo, no watermark, no newspaper page, no collage
```

只允许两个大符号：

```text
主体身份符号 + 冲突/去向符号
```

例子：

```text
院士治国 -> 中国院士，院士服；政府大楼
AI 抢饭碗 -> 疲惫白领；AI 蓝光屏
马宁世界杯 -> 足球裁判；世界杯球场灯光
外卖骑手困境 -> 外卖骑手；雨夜城市
```

不要堆细节。不要同时出现会议桌、文件、实验室、政府大楼、徽章等一堆元素。缩略图里细节会变成噪声。

冲突性来自主体姿态和一两个大符号，不来自复杂画面：

- 表情：疲惫、严肃、困惑、紧张、自信。
- 道具：简历、工牌、哨子、芯片、护照、手机、账单。
- 背景：办公室、实验室、工厂、球场、城市夜景，但必须简单。

## Gate

通过条件：

```text
cover/visual_subject.json exists
cover/image_source_manifest.json exists
cover/background.png exists
background.png is image file
cover/image_source_manifest.json proves background_raw.png was created by an AI image generation model/tool or came from an approved source/licensed/reference image route
cover/image_source_manifest.json source/model_or_tool/image_type is not local_pillow_generated, procedural_generated, programmatic_generated, manual_composite, screenshot, ppt_export, map_diagram or chart_generated
cover/visual_subject.json records strategy, style, image_prompt and negative_prompt
background.png has no readable text/logo/watermark
background.png has one dominant subject
subject is on the right and remains recognizable at thumbnail size
left title area is clean enough for large text without a card or blue base
background.png is cinematic_realism_poster or bold_american_comic_poster, not flat vector, infographic, chart, map diagram or abstract tech background
if real person was used, source/license/attribution are recorded
if AI generated, prompt and negative_prompt are recorded
if licensed/source image fallback was used, source_url/license/author_or_provider/selection_reason are recorded
```
