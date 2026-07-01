---
name: article-ai-video-visuals
description: 为中文单人口播文章视频生成全 AI 画面素材、画面提示词、素材选择清单和最终视频合成。Use when Codex has a finalized voiceover script plus real audio/dialogue timeline and needs to replace PPT chapter visuals or stock footage with AI-generated 16:9 editorial video frames, select generated assets, preserve exact overlay text outside the image model, and assemble images, subtitles, and audio into a reviewable or publishable MP4.
---

# Article AI Video Visuals

本 skill 负责把已定稿口播稿和真实音频时间轴变成全 AI 画面视频。它替代旧的 PPT 章节图和 stock footage 流程。

核心原则：

- 所有画面底图必须由 AI 生成；不要下载或混入 stock footage、新闻图、实拍图、PPT 章节图。
- 画面按真实 `audio/dialogue_timeline.json` 或人工分镜中的真实时间轴绑定，不按字数估时。
- AI 图像负责场景、构图、视觉隐喻和图表底板；精确中文、数字、标签和字幕由后处理叠加，避免模型生成乱码。
- 输出 16:9 横屏，生产目标为 `3840x2160`，审阅可降为 `1920x1080`，但 manifest 必须记录实际分辨率。
- 画面底部 18% 留给字幕：不要在底部放主体、关键图表、人物脸或重要文字。

## 输入

推荐输入：

```text
single_host_script.md
video_script/article-video-script.md
audio/final_podcast.wav
audio/dialogue_timeline.json
timed visual storyboard markdown, optional but preferred
video/final_subtitles.srt and .ass, optional
```

如果已有真实时间轴分镜，优先使用分镜中的 beat。没有分镜时，先根据 `dialogue_timeline.json` 的 turn/cue 聚合成 12-20 个 beat，再生成 manifest。

## 输出

固定输出目录：

```text
ai_video_visuals/
  visual_manifest.json
  image_prompts.json
  selected_visuals.json
  generated/
    shot_B01.png
    shot_B02.png
  selected/
    shot_B01.png
    shot_B02.png
  overlays/
    shot_B01_overlay.png
  visual_render_manifest.json
video/
  ai_visual_base.mp4
  final_subtitles.srt
  final_subtitles.ass
  final_video.mp4
  final_video_soft_subtitles.mp4, when hard subtitle burn is unavailable
```

## 画面风格

统一使用“中文科技深度解释视频”的 editorial tech documentary 风格：

- 基调：真实质感 + 克制的信息图，不做纯 PPT 页。
- 构图：横屏电影感，主体清晰，保留负空间和字幕安全区。
- 色彩：石墨黑、冷白、钢灰、少量青色和琥珀色强调；避免紫蓝渐变、单一深蓝、霓虹科幻、廉价赛博风。
- 质感：数据中心、服务器、芯片、洁净室、工程现场、城市基础设施可以做成 AI 生成的“纪实感画面”；机制、路线、生态可以做成半写实信息图底板。
- 人物：可出现远景工程师或剪影，不要近距离可识别人脸，不要口型。
- 品牌：不要任何公司 logo、媒体名、新闻网站 UI、真实产品商标、水印。
- 文字：AI 底图默认不要生成可读文字。需要精确显示的标题、数字和标签写入 `overlay_text`，由合成脚本叠加。

## Workflow

1. 确认 `/Volumes/GT34` 可写，项目目录在外置盘。
2. 从真实时间轴分镜或 `dialogue_timeline.json` 生成视觉 manifest：

```bash
python scripts/build_ai_visual_manifest.py \
  --project-dir <project-dir> \
  --storyboard-md <timed-storyboard.md> \
  --dialogue-timeline <project-dir>/audio/dialogue_timeline.json \
  --topic "中国超算 LineShine" \
  --out-dir <project-dir>/ai_video_visuals
```

3. 逐条读取 `ai_video_visuals/image_prompts.json`，用内置 `image_gen` 生成每个 shot 的 AI 底图。生成后把最终图复制为：

```text
<project-dir>/ai_video_visuals/generated/shot_B01.png
```

4. 选择素材并写出选择清单：

```bash
python scripts/select_ai_visual_assets.py \
  --project-dir <project-dir> \
  --manifest <project-dir>/ai_video_visuals/visual_manifest.json \
  --generated-dir <project-dir>/ai_video_visuals/generated \
  --selected-dir <project-dir>/ai_video_visuals/selected
```

选择规则：每个 beat 必须有一张图；若有多个候选，优先选分辨率最高、16:9 最接近、文件非空且无明显损坏的版本。人工发现图中有乱码、logo、报刊名、真实品牌或主体压住字幕区时，删除该候选并重生。

5. 合成视频：

```bash
python scripts/assemble_ai_visual_video.py \
  --project-dir <project-dir> \
  --manifest <project-dir>/ai_video_visuals/visual_manifest.json \
  --selected-manifest <project-dir>/ai_video_visuals/selected_visuals.json \
  --audio <project-dir>/audio/final_podcast.wav \
  --dialogue-timeline <project-dir>/audio/dialogue_timeline.json \
  --out <project-dir>/video/final_video.mp4
```

合成脚本会：

- 把 AI 底图裁切/缩放到目标 16:9。
- 叠加 `overlay_text` 中的精确文字和数字。
- 根据 `visual_start_sec/end_sec` 连续铺满整段音频。
- 生成 `video/final_subtitles.srt` 和 `video/final_subtitles.ass`。
- 如果本地 ffmpeg 支持 `subtitles` 滤镜，硬烧录字幕；如果不支持，生成无硬字幕 `final_video.mp4` 并额外封装 `final_video_soft_subtitles.mp4` 供审阅。
- 写出 `ai_video_visuals/visual_render_manifest.json`。

## Gate

通过条件：

```text
ai_video_visuals/visual_manifest.json exists
ai_video_visuals/image_prompts.json exists
visual_manifest uses real audio timeline and covers 0..audio_duration_sec continuously
each shot has prompt, visual_start_sec, visual_end_sec, overlay_text, safe_area
ai_video_visuals/generated contains one AI-generated image per shot
ai_video_visuals/selected_visuals.json maps every shot to a selected local image
all selected images are readable and 16:9 or safely crop-able
video/ai_visual_base.mp4 exists
video/final_video.mp4 exists and ffprobe passes
final video duration matches audio duration within 0.5 sec
video has one video stream and one audio stream
if local ffmpeg lacks subtitles/drawtext filters, visual_render_manifest records no_burned_subtitles_missing_ffmpeg_subtitles_filter and final_video_soft_subtitles.mp4 exists
ai_video_visuals/visual_render_manifest.json records image hashes, audio hash, final video hash, dimensions, fps, and subtitle paths
```

失败时停止并说明缺的 shot、损坏图、时间轴断点或 ffmpeg 错误；不要退回 PPT 章节图或 stock footage。
