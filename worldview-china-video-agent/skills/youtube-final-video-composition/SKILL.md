---
name: youtube-final-video-composition
description: "用于把已准备好的 YouTube 源视频、中文配音音频、中文字幕和封面标题合成为最终交付物：静音原视频、叠加中文主音轨、烧录中文字幕、生成高清封面图、检查片段、render_manifest.json 和 QA 报告。适合中文配音视频生产流程的最后阶段。"
---

# YouTube 最终视频合成

本 skill 只负责最后交付阶段，不做选题、下载、翻译、TTS 或音频锚点生成。

如果本 skill 目录存在脚本，优先使用：

```bash
uvx --from pillow python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-final-video-composition/scripts/compose_final_video.py \
  --video-id VIDEO_ID \
  --title "Original title" \
  --source-url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --source-video /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.mp4 \
  --voiceover-audio /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/segment-aligned-audio/final_voiceover.segment_aligned.m4a \
  --subtitle-srt /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/06-subtitles/zh-CN.voiceover.srt \
  --cover-title "中文封面标题" \
  --output-dir /Volumes/GT34/Generated/world_and_china/20260605_0/07-final-composition \
  --output-height 1080 \
  --playback-speed 1.15
```

脚本会使用 Pillow 透明字幕层回退方案，因此适合本机 ffmpeg 没有 `subtitles` / `ass` / `drawtext` filter 的环境。

## 输入

```json
{
  "video_id": "VIDEO_ID",
  "title": "原视频标题",
  "source_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "source_video_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.mp4",
  "voiceover_audio_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/segment-aligned-audio/final_voiceover.segment_aligned.m4a",
  "subtitle_srt_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/06-subtitles/zh-CN.voiceover.srt",
  "subtitle_vtt_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/06-subtitles/zh-CN.voiceover.vtt",
  "tts_manifest_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/tts/manifest.json",
  "segment_aligned_manifest_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/05-tts-alignment/segment-aligned-audio/manifest.json",
  "cover_title": "中文封面标题",
  "output_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/07-final-composition",
  "render_profile": "1080p_high_quality",
  "playback_speed": 1.15
}
```

可选：

- `source_thumbnail_path`：原缩略图，仅作参考或回退。
- `cover_frame_time_sec`：指定从源视频抽封面底图的时间点。
- `check_points`：关键检查点，例如品牌首次出现时间。
- `burn_subtitles`: 默认 `true`。
- `playback_speed`: 正式交付强制为 `1.15`。验证样片也应默认使用 `1.15`，除非明确标记为非正式调试。
- `tts_manifest_path`：TTS 生成 manifest，正式生产必须提供，用于证明音色克隆 profile。
- `segment_aligned_manifest_path`：段级对齐 manifest，正式生产必须提供，用于证明音频和字幕时间线。

## 输出

输出目录必须包含：

```text
composited/final.zh-voiceover.subtitled.mp4
audio/final_voiceover.zh-CN.m4a
subtitles/zh-CN.voiceover.srt
subtitles/zh-CN.voiceover.vtt
cover/cover.zh-CN.jpg
qa/check-clips/*.mp4
qa/keyframes/*.jpg
qa/final-render-qa-report.md
render_manifest.json
```

这些路径均相对 `output_dir`。在 Worldview China 总控流程中，`output_dir` 必须是当前 run 目录下的 `07-final-composition/`。

`subtitle_vtt_path` 可以作为输入提供；如果没有提供，必须从最终 `.srt` 自动生成 `subtitles/zh-CN.voiceover.vtt`。缺少 `.vtt` 不能通过正式交付验收。

## 交付模式 Gate

正式交付必须满足：

- 覆盖原视频完整主时间线，不是 `first60`、`sample`、`validation` 或局部章节。
- `render_profile` 不能包含 `validation`。
- `playback_speed` 必须是 `1.15`。最终 MP4、交付目录里的中文音频、烧录字幕和交付 `.srt` / `.vtt` 必须同时处于 1.15 倍交付时间线。
- 输入中文音频来自正式锚点流程，而不是缓存字幕时间戳草稿。
- 输入中文音频来自同一个原视频音色克隆 profile；`tts_manifest_path` 或 `segment_aligned_manifest_path.voice_clone` 必须证明 `mode == voice_clone_only`。
- 输出同时包含最终 MP4、中文音频、SRT、VTT、封面、检查片段、关键帧、QA 报告和 manifest。

验证样片必须满足：

- 在 `render_profile` 或上级 manifest 中明确标注 `validation_not_formal_delivery: true`。
- 不得写入正式历史文件。
- 最终报告不得称其为正式成片。

## 合成规则

- 原视频画面保留，原声静音。
- 音频使用中文配音音轨。
- 中文字幕必须烧录进最终 MP4，同时保留 `.srt` / `.vtt`。
- 上游源视频、原声音频锚点、中文配音段和输入 SRT 仍使用原始主时间线；最终合成阶段统一映射为交付时间线：`delivery_time = source_time / playback_speed`。
- 成片时长以源视频和中文音轨较短者除以 `playback_speed` 为准；正常情况下最终 MP4 和交付中文音频应小于 `0.3s` 差异。
- 交付目录中的 `audio/final_voiceover.zh-CN.m4a` 必须是已经 1.15 倍加速后的中文音频，不得只是原速音频拷贝。
- 不要在本阶段改写字幕文本或配音稿；内容问题回到上游修。
- 输入 SRT 必须已经通过上游字幕 QA。不能把 `voiceover-segments.json` 直接转换成“每段一条”的粗 SRT 来合成；任何单条 cue 超过 `8s` 或可见文本超过 `48` 字，应视为上游字幕/分段失败。
- 最终 MP4 必须原子落盘：先写到同目录临时文件，例如 `final.zh-voiceover.subtitled.mp4.tmp.mp4`，`ffmpeg` 进程完全结束后对临时文件跑 `ffprobe`。
- 只有临时文件 `ffprobe` 可读、包含视频流和音频流、时长符合预期、文件大小连续两次检查稳定后，才能 rename 到正式 `final.zh-voiceover.subtitled.mp4`。
- `render_manifest.json` 必须在正式文件 rename 之后生成，并且其中的 `final.size`、`final.duration`、流信息必须来自当前正式文件的现场 `ffprobe`。不要先写 manifest 再继续覆盖最终 MP4。
- 如果正式文件已存在，不能在原路径上直接边写边覆盖；必须写新临时文件，验证通过后替换。
- 如果 `ffprobe` 报 `moov atom not found`、缺音频流、缺视频流、时长不匹配或文件大小不稳定，本阶段直接 FAIL，不得交给最终验收。
- 字幕烧录必须证明版本一致。若 `playback_speed = 1.0`，输入 SRT、交付 SRT、overlay 来源 SRT 和最终 MP4 抽帧应同源同 hash；若 `playback_speed != 1.0`，输入 SRT 是原始时间线，交付 SRT/VTT 和 overlay 来源 SRT 必须是按 `delivery_time = source_time / playback_speed` 缩放后的同一版字幕。`render_manifest.json` 至少记录 `input_srt_sha256`、`final_srt_sha256`、`input_timeline`、`final_timeline`、`input_cue_sha256`、`final_cue_sha256`、`overlay_source_srt_sha256`、`overlay_source_cue_sha256`、`overlay_cue_count`。
- 如果上游有 `subtitle-timeline-report.json`，最终合成 QA 必须记录并核对该报告的 `srt_path`、cue count 和输入 SRT 哈希。正式 1.15x 交付时，最终 SRT 哈希可以不同于上游报告，但必须证明最终 SRT 是从该输入 SRT 等比例缩放得到，且最终 SRT、VTT、overlay 和抽帧同源。
- 如果使用 Pillow overlay，生成 overlay 前必须清空旧的 `work/subtitle_overlay` 目录；不能复用旧 PNG、旧 ffconcat 或旧 overlay 视频。
- 合成后必须从最终正式 MP4 现场抽取关键帧，而不是从 overlay 文件或旧检查片段抽帧。关键帧时间应覆盖普通字幕、关键锚点和随机中段。
- 合成后必须目视检查关键帧中的中文字幕字形完整性。若出现单个汉字笔画残缺、像半乱码、缺字方框、替代符号或异常字体 fallback，不能交给最终验收；应更换可靠简体中文字体重烧，或回到 06 改写该 cue 文本。

质量配置：

```text
1080p_high_quality:
  output_height: 1080
  video_codec: h264
  bitrate: 8-12 Mbps or crf 18-20
  audio_codec: aac
  audio_bitrate: target 192k; actual bitrate must be recorded because mono/24kHz TTS may encode lower

4k_archive:
  output_height: keep source height when <=2160
  video_codec: h264/hevc
  bitrate: 20-35 Mbps or visually comparable CRF
```

如果源视频高于目标高度，使用高质量缩放到目标高度。不要从低清源硬放大成高清交付。

## 字幕烧录

优先使用 ffmpeg 原生字幕能力：

```bash
ffmpeg -i source.mp4 -i voiceover.m4a \
  -vf "subtitles=zh-CN.voiceover.srt:force_style='Fontsize=44,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=3'" \
  -map 0:v:0 -map 1:a:0 ...
```

如果本机 ffmpeg 没有 `subtitles` / `ass` / `drawtext` filter：

1. 用 Pillow 将每条字幕 cue 渲染为透明 PNG。
2. 用 ffmpeg 把透明 PNG 序列合成带 alpha 的 overlay 视频。
3. 用 `overlay` filter 叠加到源视频。
4. 写入 overlay manifest，记录来源 SRT 哈希、cue 哈希和 cue 数；合成前必须校验这些字段和最终交付 SRT 一致。

如果系统 Python 没有 Pillow，不要修改项目依赖；可以临时使用：

```bash
uvx --from pillow python render_subtitle_overlay.py
```

Pillow 字幕样式：

- 底部居中。
- 参考短视频双语字幕常见的粗圆体观感：大号粗体、白字、黑色厚描边，可带极轻黑色投影。
- 默认不加半透明背景条、背景色块或背景阴影。
- 字幕位置应比传统底部字幕略低，但不能贴边或遮挡播放器安全区。
- 字幕不超过 2 行；过长则按中文标点拆 cue。
- 合成脚本会在渲染前校验 cue：cue duration `<=8s`、可见文本 `<=48` 字、无显示标点、时间单调且不越界。不满足时应回到上游拆字幕或重分段，不要调高阈值绕过。
- 字体优先使用可靠的简体中文 UI 字体，例如 PingFang SC、Hiragino Sans GB、Source Han Sans SC 或 Noto Sans CJK SC。不要优先使用容易产生老旧字形或 fallback 风险的字体；渲染后必须抽帧确认常见汉字没有半乱码观感。

## 封面图

封面优先从高清源视频抽帧，而不是默认使用低码率 YouTube 缩略图。

选择封面底图：

1. 优先选信息密度高、主题明确、有图表/产品/人物/地点信号的帧。
2. 可以参考原缩略图构图，但不要机械使用 1280x720 低码率图。
3. 没有好帧时才回退到 `source_thumbnail_path`。

封面文字：

- 默认只放中文主标题。
- 不加“中文配音版”“原视频 + 中文配音 + 中文字幕”等说明行，除非用户明确要求。
- 标题要避开 logo、车辆主体、人物脸、图表关键数字。
- 输出 `cover.zh-CN.jpg`，建议 1920x1080；最低 1280x720。

## QA

必须生成：

- `render_manifest.json`
- `qa/final-render-qa-report.md`
- 至少 3 个检查片段或覆盖首段、中段、尾段。
- 对 `check_points` 中的关键锚点，各导出前后 10-20 秒检查片段。
- 至少抽 2 张最终成片帧，确认字幕烧录成功且可读。
- 抽 1 张封面图人工/视觉检查。

QA 报告必须记录：

- 源视频分辨率、码率、时长。
- 最终视频分辨率、码率、时长。
- 中文音频时长、最终音频码率。
- 最终交付播放速度，正式交付必须记录为 `1.15x`。
- 原始主时间线时长和交付时间线时长，且 `final_duration ≈ min(source_duration, voiceover_duration) / 1.15`。
- 音视频时长差。
- 字幕 cue 数、SRT 路径、VTT 路径。
- 字幕连续性报告路径，例如 `subtitle-timeline-report.json`。最终合成前必须确认每个有口播 segment 首条 cue 延迟 `<=0.8s`，segment 内无字幕空窗 `<=1.2s`。
- 字幕报告同源证据：`subtitle-timeline-report.json.srt_path`、输入 SRT、最终交付 SRT 三者必须哈希一致。
- 字幕版本一致性证据：输入 SRT 哈希、最终 SRT 哈希、overlay 来源 SRT 哈希、cue 哈希、overlay cue 数；它们必须一致。
- 字幕烧录证据：至少 2 张带字幕关键帧。
- 检查片段路径。
- 封面图路径。
- 如果上游提供配音 manifest 或 sync report，必须记录 `max_tempo_factor`、`max_tail_padding_sec` 和超阈值段。
- 必须记录 TTS 克隆证据：`tts_manifest_path`、`voice_clone.mode`、`ref_audio_sha256`、`ref_text_sha256`、`model_dir`。缺少这些字段时不能交给正式验收。
- 已知限制，例如“后半段仍使用旧时间线”。
- 最终 MP4 原子落盘证据：临时文件验证命令、正式文件 `ffprobe` 结果、正式文件大小、连续大小稳定检查结果。

## 验收失败

以下任一情况必须失败：

- 最终视频没有中文音频。
- 正式交付的 `playback_speed` 不是 `1.15`，或最终 MP4、交付中文音频、烧录字幕、交付 SRT/VTT 没有处在同一个 1.15 倍交付时间线。
- 输入 SRT/VTT 虽然单调，但存在整段字幕被推迟到段尾、首条 cue 延迟超过 `0.8s`、segment 内无字幕空窗超过 `1.2s`，或 `subtitle-timeline-report.json` 缺失。
- 输入 SRT 存在单条 cue 超过 `8s`、可见文本超过 `48` 字、显示标点，或看起来是一段一个 cue 的粗字幕。
- `subtitle-timeline-report.json` 存在但与最终 SRT 不同源，例如报告 cue 数和最终 cue 数不一致。
- 最终视频没有烧录中文字幕。
- 最终 MP4 里烧录的字幕层与交付的 `.srt` / `.vtt` 不同源，例如最终 MP4 抽帧显示旧字幕，而当前 SRT 对应时间点是另一条字幕。
- `render_manifest.json` 缺少字幕版本一致性字段；正式 1.15x 交付时，`final_srt_sha256`、`overlay_source_srt_sha256`、`final_cue_sha256`、`overlay_source_cue_sha256`、cue count 任一不一致，或缺少输入时间线到交付时间线的缩放证据。
- `render_manifest.json` 或上游 manifest 缺少音色克隆证据，或显示使用未授权预设 voice。
- 最终 MP4 不可被 `ffprobe` 解析，或出现 `moov atom not found`。
- `render_manifest.json` 中的最终文件大小、时长或流信息与当前正式文件现场 `ffprobe` 不一致。
- 缺少 `.srt` 或 `.vtt`。
- 封面缺失或仍带不需要的说明行。
- 音视频时长差异大于 `0.3s` 且没有解释。
- 源素材存在更高清版本却复用低清源。
- 关键检查片段不存在。
- QA 报告没有可验证文件路径。
- 正式模式下输出是局部样片、validation 样片或使用缓存字幕时间戳替代原声音频锚点。

失败后不要在成片上做不可追溯补丁。应回到上游素材、字幕、音频或分段步骤修正，并重新输出 manifest。
