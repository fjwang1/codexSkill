---
name: youtube-media-preparation
description: "用于根据 YouTube URL 准备本地素材目录：下载视频、抽取音频、获取字幕、保存缩略图和元信息。适合在配音、剪辑、视频合成之前运行。"
---

# YouTube 素材准备

使用这个 skill 将一个 YouTube 视频 URL 准备成本地素材包。

本 skill 是素材准备阶段，不做选题评分、不做翻译、不做 TTS、不做视频合成。

## 输入

输入必须是单个 YouTube 视频 URL：

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "authorized": true,
  "output_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation",
  "video_height_target": 1080,
  "cookies_from_browser": "optional, e.g. chrome or chrome:Default",
  "cookies": "optional path to cookies.txt",
  "proxy": "optional proxy URL",
  "subtitle_languages": ["en", "en-US", "en-GB"]
}
```

字段说明：

- `url`: 必填。单个 YouTube 视频 URL，不处理 playlist。
- `authorized`: 必填且必须为 `true`，表示用户确认可以处理该素材。
- `output_dir`: Worldview China 总控正式流程必填，必须是当前 run 目录下的 `02-media-preparation/`。
- `video_height_target`: 默认 `1080`。
- `cookies_from_browser`: 可选。用于把本机已授权的浏览器登录态透传给 `yt-dlp`，例如 `chrome`、`chrome:Default`、`chrome:Profile 1`。不要读取、打印或保存原始 cookie 值。
- `cookies`: 可选。Netscape `cookies.txt` 文件路径；只记录“已提供”，不要把文件内容写入日志或 manifest。
- `proxy`: 可选。HTTP/HTTPS/SOCKS 代理 URL；可能包含凭证，日志必须脱敏。
- `subtitle_languages`: 默认 `["en", "en-US", "en-GB"]`，可按视频语言调整。

不要在本 skill 中传入翻译稿、配音稿、TTS 音频或视频合成参数。

## 本机长期授权

2026-06-22 起，用户已对本机 Worldview China 播客自动化给出长期授权：如果 YouTube 元信息、字幕、格式列表或下载返回 bot/sign-in/IP 风控，直接用 `--cookies-from-browser chrome` 重试，不再询问。仍然禁止读取、导出、打印或保存 cookie 原文；`download.log` 和 `media_manifest.json` 只能记录脱敏状态，例如 `cookies_from_browser=chrome` / `provided`。

如果 `get_transcript.py` 因缺少 `youtube-transcript-api` 失败，必须先用 `uv run --with youtube-transcript-api` 重试，不得把 Python 依赖缺失记录成视频无字幕或 YouTube 风控失败。

## 输出

输出目录应包含四类核心素材：

```text
/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/
├── source.mp4             # 下载并合并后的源视频
├── source.wav             # 从 source.mp4 抽取的单声道 WAV
├── subtitles/             # getTranscript 输出的字幕 JSON/TXT
├── source.jpg             # 缩略图
├── source.info.json       # yt-dlp 原始元信息
├── metadata.json          # 规范化元信息
├── media_manifest.json    # 本 skill 的统一输出清单
├── probe.json             # source.mp4 的 ffprobe 信息
├── probe.audio.json       # source.wav 的 ffprobe 信息
└── download.log           # 下载日志
```

统一输出 manifest 示例：

```json
{
  "schema_version": "youtube-media-assets.v1",
  "video_id": "VIDEO_ID",
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "title": "Video title",
  "output_dir": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation",
  "video_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.mp4",
  "audio_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.wav",
  "thumbnail_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.jpg",
  "metadata_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/metadata.json",
  "raw_info_json_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/source.info.json",
  "transcript": {
    "status": "ok",
    "language": "en",
    "json_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/subtitles/VIDEO_ID.en.plain.json",
    "txt_path": "/Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/subtitles/VIDEO_ID.en.plain.txt"
  },
  "selected_video_format": {
    "format_id": "399",
    "height": 1080,
    "ext": "mp4"
  },
  "selected_audio_format": {
    "format_id": "140",
    "ext": "m4a"
  }
}
```

## 分辨率规则

默认目标是 `1080p`，不盲目下载最高分辨率。

选择规则：

1. 如果有 `1080p`，选质量最好的 `1080p`。
2. 如果没有 `1080p`，优先往上找最接近的分辨率，例如 `1440p`。
3. 如果没有更高分辨率，再往下找最接近的分辨率，例如 `720p`。
4. 同一高度下优先选择兼容性更好的 `mp4`，再比较码率、fps 和文件大小。
5. 音频必须优先选择 YouTube 标记的 `original` / `default` 原始音轨；同为原始音轨时优先 `language_preference` 更高者，再优先非 DRC、`m4a`、码率和文件大小。
6. 多语音轨视频中，禁止只按 `m4a`/码率/文件大小选择音频，因为这可能误选阿拉伯语、日语等自动多语言配音轨。

如果最终选择不是 `1080p`，必须在 manifest 里记录实际高度和原因。

## 字幕

字幕获取直接引用已有 getTranscript 工具：

```text
/Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/get_transcript.py
```

使用方式：

```bash
uv run --with youtube-transcript-api python /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/worldview-china-topic-selection/scripts/get_transcript.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --language en \
  --language en-US \
  --language en-GB \
  --cache-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/subtitles \
  --video-metadata-file /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation/metadata.json
```

如果该脚本不存在、依赖缺失或视频没有字幕，不要伪造字幕。应在 `media_manifest.json` 中记录：

```json
{
  "transcript": {
    "status": "failed",
    "error": "reason"
  }
}
```

## 推荐脚本

如果本 skill 目录存在脚本，优先使用：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-video-agent/skills/youtube-media-preparation/scripts/prepare_youtube_media.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --authorized \
  --output-dir /Volumes/GT34/Generated/world_and_china/{YYYYMMDD}_{N}/02-media-preparation \
  --yt-dlp-bin "uvx yt-dlp" \
  --language en \
  --language en-US \
  --language en-GB
```

如果 YouTube 返回 `Sign in to confirm you're not a bot`、`bot_signin_required` 或等价登录校验，本机已有长期授权，重试时添加：

```bash
--cookies-from-browser chrome
```

默认先使用 `chrome`。如果有多个 Chrome profile 且 `chrome` 报 profile 选择/锁定错误，再尝试常见 profile 名称，例如：

```bash
--cookies-from-browser "chrome:Default"
--cookies-from-browser "chrome:Profile 1"
```

如果用户提供 `cookies.txt`，使用：

```bash
--cookies /path/to/cookies.txt
```

如果当前 IP 被 YouTube 风控或地域网络异常，且用户提供代理，使用：

```bash
--proxy "socks5://127.0.0.1:1080"
```

不要通过浏览器 MCP 或 DevTools 把 Google/YouTube cookie 原文取出、打印、粘贴到对话或写入日志。脚本只允许把 cookie 参数透传给本机 `yt-dlp`，并在 manifest 中记录授权方式已使用。

脚本应完成：

1. 用 `yt-dlp` 读取视频格式列表和元信息。
2. 按分辨率规则选择视频/音频格式。
3. 下载并合并为 `source.mp4`。
4. 抽取 `source.wav`。
5. 保存缩略图和元信息。
6. 调用 getTranscript 获取字幕。
7. 写入 `media_manifest.json`。

默认行为：

- 脚本默认优先使用 `uvx yt-dlp`，因为系统旧版 `yt-dlp` 在 YouTube SABR 场景下可能只能看到 360p。若要指定命令，传入 `--yt-dlp-bin "uvx yt-dlp"` 或具体 yt-dlp 路径。
- 高清生产时传入 `--height 2160 --require-target-height`。如果工具只能看到低于目标高度的格式，必须失败并记录原因，不允许悄悄下载 360p/720p。
- 脚本支持 `--cookies-from-browser`、`--cookies`、`--proxy`、`--impersonate` 和 `--yt-dlp-extra-args`；这些参数必须同时用于 yt-dlp 元信息读取和正式下载。
- 命令日志必须对 `--cookies`、`--cookies-from-browser`、`--proxy` 的值脱敏；manifest 只记录是否使用授权/网络参数，不记录 cookie 原文。
- 高清下载默认使用 yt-dlp `--concurrent-fragments 8`，避免 4K DASH 视频单连接下载过慢。
- 如果输出目录中已经存在 `source.mp4` 或 `source.wav`，脚本默认复用已有文件，除非传入 `--force`。
- 复用已有 `source.mp4` 时，manifest 中的实际分辨率、编码和音频流信息必须以 `ffprobe` 结果为准，而不是以本次 `yt-dlp` 候选格式推断。
- 如果需要强制重新下载，使用 `--force`。
- 如果不允许复用已有文件，使用 `--no-reuse-existing`。

## 校验

完成后必须检查：

- `source.mp4` 存在且可被 `ffprobe` 读取。
- `source.wav` 存在，单声道，推荐 `24000 Hz`。
- 缩略图存在。
- `source.info.json` 或 `metadata.json` 存在。
- 字幕成功时，字幕 JSON/TXT 都存在；失败时，manifest 记录失败原因。
- `media_manifest.json` 路径完整，四类核心素材路径清晰。
- 多语音轨视频中，`selected_audio_format.format_note` 应包含 `original` 或 `default`，或 `selected_audio_format.language_preference >= 0`；如果存在 original/default 音轨却选中了 `language_preference < 0` 的配音轨，必须视为下载验收失败并修正。

## 交付

完成后告诉用户：

- `source.mp4` 路径和实际分辨率。
- `source.wav` 路径和音频参数。
- 字幕 JSON/TXT 路径或失败原因。
- 缩略图路径。
- `media_manifest.json` 路径。

不要在最终回答中粘贴完整 manifest。
