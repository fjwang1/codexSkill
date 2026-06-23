---
name: youtube-subtitle-to-chinese
description: "用于把 YouTube 外文时间轴字幕改写为自然、完整、适合 TTS 和视频合成的中文配音稿。输入通常是带 front matter 和 [HH:MM:SS - HH:MM:SS] 时间点的外文字幕 TXT；输出章节级中文配音稿和语义节点，而不是屏幕字幕。"
---

# YouTube 外文字幕转中文配音稿

使用这个 skill 将 YouTube 外文时间轴字幕改写为中文配音稿，用于后续中文 TTS、音频时长校验和视频合成。

核心方法是两层结构：

1. **章节级配音稿**：先按视频内容拆成几分钟一章，保证中文表达自然、论证完整、术语一致。
2. **语义节点**：再把每章按原字幕语义时间线拆成小节点，每个节点绑定外文字幕时间段，用于 TTS 分段、真实时长校验和对齐。

不要用画面锚点作为默认依据。自动化阶段只依赖外文字幕的语义时间点；讲解视频的画面通常跟随旁白语义，画面同步应作为语义同步的结果，而不是本 skill 的输入假设。

## 边界

- 本 skill 不生成屏幕中文字幕。
- 输出不是逐条字幕翻译，也不是短字幕块。
- 输出是给人说出来的中文配音稿。
- 优先使用原始外文时间轴字幕，不要把已经压缩过的中文字幕再当作输入。
- 不要为了对齐添加原文没有的新事实、观点或评价。
- 不要根据画面、音乐、沉默、片头或转场做推断；仅凭字幕文本时无法可靠判断这些信息。

## 输入

输入优先使用带时间点的 TXT 字幕：

```text
---
schema_version: "transcript.v1"
video_id: "..."
video_url: "..."
title: "..."
description: |
  ...
language: "en"
source: "auto_caption"
---

[00:00:00 - 00:00:03] foreign subtitle text...
[00:00:03 - 00:00:07] foreign subtitle text...
```

如果没有 front matter，也可以处理纯时间轴字幕，但需要从文件名或用户说明中获得视频 ID、源语言和标题。

## 输出

默认输出两份文件：

```text
voiceover-scripts/{video_id}.zh-CN.voiceover-script.md
voiceover-segments/{video_id}.zh-CN.semantic-nodes.json
```

Markdown 文件给人审阅；JSON 给 TTS 和视频合成程序使用。两份文件必须表达同一套章节和节点，不允许一个包含另一个没有的大段内容。

### Markdown 格式

```text
---
schema_version: "voiceover-script.v2"
source_schema_version: "transcript.v1"
video_id: "VIDEO_ID"
video_url: "https://www.youtube.com/watch?v=VIDEO_ID"
source_language: "en"
target_language: "zh-CN"
title: "..."
source_transcript_path: "..."
translation_mode: "localized_voiceover"
timing_strategy: "chapter_then_semantic_nodes"
speech_rate_model: "estimated_speech_sec = round(cjk_char_count / 4.5)"
self_check_mode: "sample_first_then_full"
---

## voice_chapter_001

- time_range: 00:00:00-00:03:17
- target_duration_sec: 197
- target_speech_sec: 177-197
- estimated_speech_sec: 188
- duration_coverage_ratio: 0.95
- coverage_status: complete
- notes: 开场总论，保留价格、性能、配置、品牌例子和保护主义论点。

[00:00:00 - 00:03:17]
章节级中文配音稿正文。这里应当像自然中文解说，而不是字幕短句。

### semantic_nodes

#### chapter_001_node_001

- time_range: 00:00:00-00:00:15
- target_duration_sec: 15
- target_speech_sec: 14-15
- estimated_speech_sec: 14
- duration_coverage_ratio: 0.93
- sync_priority: high
- source_start: 00:00:00
- source_end: 00:00:15
- source_subtitle_ids: 0001,0002,0003,0004,0005,0006,0007
- source_excerpt: Chinese electric vehicles have blown past the competition... go twice as far as any Tesla.
- must_cover: 价格低几万美元；比 Taycan 更快；续航达到 Tesla 两倍

中国电动车已经把竞争对手甩在身后。它们比美国最便宜的电动车还低几万美元，却能比二十五万美元的保时捷 Taycan 更快，续航甚至达到任何特斯拉的两倍。
```

### JSON 格式

语义节点 JSON 必须且只能使用示例中的字段。不要添加临时字段、评审字段或程序私有字段；需要记录评审结果时另存单独报告。

```json
{
  "schema_version": "voiceover-semantic-nodes.v1",
  "video_id": "VIDEO_ID",
  "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "title": "...",
  "source_transcript_path": "...",
  "source_language": "en",
  "target_language": "zh-CN",
  "speech_rate_model": "estimated_speech_sec = round(cjk_char_count / 4.5)",
  "chapters": [
    {
      "chapter_id": "chapter_001",
      "start": "00:00:00",
      "end": "00:03:17",
      "target_duration_sec": 197,
      "chapter_title": "开场总论：中国电动车为何领先",
      "chapter_voice_text": "章节级中文配音稿正文。",
      "nodes": [
        {
          "node_id": "chapter_001_node_001",
          "start": "00:00:00",
          "end": "00:00:15",
          "source_start": "00:00:00",
          "source_end": "00:00:15",
          "source_subtitle_ids": ["0001", "0002", "0003", "0004", "0005", "0006", "0007"],
          "source_excerpt": "Chinese electric vehicles have blown past the competition... go twice as far as any Tesla.",
          "target_duration_sec": 15,
          "sync_priority": "high",
          "must_cover": ["价格低几万美元", "比 Taycan 更快", "续航达到 Tesla 两倍"],
          "voice_text": "中国电动车已经把竞争对手甩在身后。它们比美国最便宜的电动车还低几万美元，却能比二十五万美元的保时捷 Taycan 更快，续航甚至达到任何特斯拉的两倍。",
          "estimated_speech_sec": 14,
          "duration_coverage_ratio": 0.93,
          "coverage_status": "complete"
        }
      ]
    }
  ]
}
```

### TTS manifest 格式

TTS 生成后另存 manifest 文件，例如：

```json
{
  "schema_version": "voiceover-tts-manifest.v1",
  "inter_segment_pause_sec": 0.12,
  "segments": [
    {
      "node_id": "chapter_001_node_001",
      "voice_text_sha256": "sha256-of-normalized-voice-text",
      "audio_path": "draft-segments/chapter_001_node_001.wav",
      "actual_tts_sec": 13.8,
      "target_duration_sec": 15,
      "actual_coverage_ratio": 0.92,
      "cumulative_drift_sec": -0.8,
      "status": "approved",
      "needs_rerun": false
    }
  ]
}
```

## 改写目标

目标是准确、顺耳、能配音、能按语义对齐。

### 准确

- 保留原视频的核心事实、数字、专有名词、因果关系、转折关系、例子、类比和说话立场。
- 不要用摘要替代原文内容。
- 自动字幕常有断句错误、口误或识别错误；可以根据上下文修正明显错误，但不能自行编造。
- 遇到不确定的人名、机构、术语，保留原文或采用“中文译名（原文）”。

### 顺耳

- 使用自然简体中文，避免翻译腔。
- 面向中文视频观众，可以调整语序、拆分长句、合并碎句，让逻辑更清楚。
- 口播稿应像中文讲解，不像书面论文，也不是逐字字幕。
- 允许加入必要连接句，让中文连贯；连接句只能基于原文上下文。

### 能配音

- 章节稿可以连续自然；节点稿必须 TTS-ready。
- 单个口播句估算不应超过 30 秒，过长句必须拆短。
- 不要为了凑时长添加空话、套话或重复废话。
- 保留中文标点、数字、品牌名、英文术语和 URL。
- 送入 TTS 的 `voice_text` 不应包含 Markdown、字段名、注释或不会朗读的说明文字。

### 能按语义对齐

- 节点来自原外文字幕的语义时间段，不来自画面识别。
- 每个节点只覆盖该时间段原字幕表达的内容；不要把后面节点的信息提前说，也不要把前面节点的信息拖到后面说。
- 品牌、人物、数字、政策名、图表口播等高识别度信息，应落在对应语义节点内。
- 后续 TTS 的真实时长以音频为准；文本估算只用于初筛。

## 时长策略

中文配音稿不能像屏幕字幕那样过度压缩。否则 TTS 音频会明显短于原视频，视频合成时只能靠大段静音或剪视频补救。

估算规则：

```text
estimated_speech_sec = round(cjk_char_count / 4.5)
duration_coverage_ratio = estimated_speech_sec / target_duration_sec
```

- `cjk_char_count` 只统计 CJK 汉字字符，不统计空格、标点、换行、英文品牌名、URL 或阿拉伯数字。
- 英文品牌名、数字、枚举和标点停顿会影响真实 TTS 时长，所以估算不能当作最终验收。
- `duration_coverage_ratio` 保留两位小数。

目标区间：

- 章节级：`target_speech_sec` 通常取 `target_duration_sec` 的 90%-105%，优先落在 92%-100%。
- 语义节点：普通节点目标 90%-105%；高优先级节点目标 92%-102%。
- 低于 90% 通常说明过度总结，必须回到原文补回事实、数字、例子、因果链条和必要指代。
- 高于 105% 通常说明节点太啰嗦或承载了相邻节点内容，必须压缩或重分配。
- 只有当字幕文本本身明确稀疏，例如只有 `[music]` / `[applause]` 等非语言标记、广告重复口号或原字幕明显缺失，节点才可低于 90%，并必须在 `notes` 写明文本证据。

补足时长优先级：

1. 补回被遗漏的事实、数字、例子和因果链条。
2. 把原文中压缩过快的论证讲清楚。
3. 补足必要指代和自然过渡。
4. 仍然不足时，标记 `coverage_status: below_target` 或 `sparse_source`，不要硬塞废话。

压缩时优先级：

1. 删除重复铺陈和弱连接句。
2. 合并意思相近的句子。
3. 把误放到本节点的相邻信息移回正确节点。
4. 保留关键事实、数字、因果、转折、立场、例子和类比。

## 工作流

### 0. 长任务先做小样本

如果输入视频超过 10 分钟，或这是第一次为某类视频生成配音稿，不要一上来生成全片。

先选择 1-2 个代表性片段，总时长 2-5 分钟，覆盖容易出错的内容类型，例如高密度论证、技术解释、品牌枚举、广告口播、数字密集段或结尾观点。

样本必须完整走通：

```text
生成章节稿
-> 拆语义节点
-> 估算覆盖率
-> 生成真实 TTS
-> 读取 manifest 的实际时长
-> 按真实时长反馈改稿
-> 独立评估 agent 审阅
-> 通过后再生成全片
```

如果反馈暴露通用问题，先修改本 skill 或执行规则，再丢弃旧样本重新生成；不要只在样本里打补丁。

### 1. 读取元信息和术语

读取 TXT front matter、标题、描述和字幕正文，判断源语言、主题、频道语气、专业领域，以及需要统一的人名、机构名、品牌名、政策名和术语。

如果字幕文本明确是赞助广告或行动号召，除非用户明确要求删除，也要作为配音稿覆盖；可以压缩重复口号，但要保留品牌名、核心卖点、适用条件、URL 或行动指令。

### 2. 建立章节结构

先快速浏览全文结构，形成章节草图。章节边界优先选择话题切换、论点完成、例子结束、解释链条告一段落、广告或行动号召开始结束。

章节长度建议 1-4 分钟；信息密集的视频可以更短，叙事连贯的视频可以稍长。不要在一个句子、例子或论证点中间切断。

### 3. 生成章节级配音稿

每章先做连续中文稿，目标是自然、完整、可听：

```text
理解该章原文
-> 内部抽取不可遗漏清单
-> 对照前后文确认指代和术语
-> 生成章节级中文稿
-> 估算章节覆盖率
-> 过短则补回细节，过长则压缩
```

不可遗漏清单不需要写进最终文件，但自检时必须逐项回看。

### 4. 拆语义节点

每章完成后，按外文字幕时间线拆成语义节点。节点边界优先选择：

- 话题或对象切换，例如 BYD -> Geely -> Xiaomi。
- 论点推进，例如研发速度 -> 广告对比 -> 充电基础设施。
- 数字、品牌、人物、政策或例子开始。
- 原字幕中明显的句群边界。

节点通常 5-20 秒，信息特别密集时可更短，叙事连续时可略长。不要为了固定时长切断一个不可分割的事实或因果链。

每个节点必须包含：

- `node_id`
- `start`
- `end`
- `source_start`
- `source_end`
- `source_subtitle_ids`
- `source_excerpt`
- `target_duration_sec`
- `sync_priority`: `high | normal | low`
- `must_cover`
- `voice_text`
- `estimated_speech_sec`
- `duration_coverage_ratio`
- `coverage_status`

`coverage_status` 可用值：`complete | below_target | sparse_source | needs_rewrite | approved`。TTS manifest 中的 `status` 可用值：`approved | needs_rewrite | tts_failed | reused`。

源文绑定字段是强制项。`must_cover` 不能只靠模型凭感觉列，必须来自该节点的 `source_excerpt`。如果节点缺少源文绑定，后续评估无法判断是否漏译、摘要化或前后串位。

节点的 `voice_text` 应从章节级中文稿重新分配和局部改写，不要重新生成一套风格不同的碎片翻译。

### 5. 真实 TTS 反馈闭环

估算通过后，必须用后续 TTS skill 或本地 TTS 工具生成真实音频。验收以真实时长为准，而不是汉字估算。

读取音频 manifest 后，计算：

```text
actual_coverage_ratio = actual_tts_sec / target_duration_sec
cumulative_drift_sec = 当前节点累计真实音频时长 - 当前节点累计原时间线时长
```

TTS manifest 必须且只能包含 `schema_version`、`inter_segment_pause_sec`、`segments` 三个顶层字段。每个 `segments` 项必须且只能为每个节点保存：

- `node_id`
- `voice_text_sha256`
- `audio_path`
- `actual_tts_sec`
- `target_duration_sec`
- `actual_coverage_ratio`
- `cumulative_drift_sec`
- `status`: `approved | needs_rewrite | tts_failed | reused`
- `needs_rerun`

`voice_text_sha256` 基于去空白后的 `voice_text` 计算，用来判断音频是否仍对应当前文本。节点文本变化后，旧音频必须标记为不可复用。

验收建议：

- 整章真实覆盖率 >= 90%。
- 高优先级节点真实覆盖率 92%-102%。
- 普通节点真实覆盖率 90%-105%。
- 高优先级节点累计 drift 约 <= 1 秒。
- 普通节点累计 drift 必须 <= 3 秒。

失败处理：

- 节点偏短：先补回原文事实、数字、例子、因果和必要指代。
- 节点偏长：先压缩中文稿或把相邻信息移回正确节点。
- 只重跑 `needs_rerun: true`、`status: needs_rewrite`、`status: tts_failed`，或 `voice_text_sha256` 与当前节点不一致的节点。
- 复用 `status: approved` 且 hash 匹配的音频。
- 重跑后合并 manifest，保留每个节点的最新 `actual_tts_sec`、`actual_coverage_ratio`、`cumulative_drift_sec` 和 `status`。
- 不要每次都整章重跑；整章重跑只在关键节点全部通过后做。

### 6. 独立评估 agent

完成样本或整章后，必须单开一个独立评估 agent 做审阅。评估 agent 的输入应尽量是原始字幕片段、产出的章节/节点稿、真实 TTS manifest 或校验报告；不要把你自己的结论、预期答案或“哪里可能有问题”提前告诉它。

评估 agent 只负责判断，不负责改稿。它应检查：

- 是否漏掉事实、数字、因果、转折、立场、例子和类比。
- 是否把原文压成摘要。
- 节点是否沿着原字幕语义时间线，没有前后串位。
- `must_cover` 是否真的被 `voice_text` 覆盖。
- 中文是否自然、适合 TTS。
- 节点覆盖率和累计 drift 是否满足要求。

如果评估失败，先判断失败是否来自本 skill 的通用规则；若是，修改 skill 或执行规则后重新生成样本，不要只局部修补旧输出。

### 7. 终稿自检

所有章节完成后，从头到尾通读最终中文稿，再交付。重点检查：

- 全片逻辑是否连贯。
- 术语、人名、机构名、品牌名是否一致。
- 是否有误译、反译、主语误判或代词指代错误。
- 是否有明显翻译腔、长句堆叠、突兀转折或不适合 TTS 的拗口句。
- 是否有为了补时长而添加的空话。
- 是否有节点低于 90% 却没有原因。
- 是否有真实 TTS 校验未完成的章节或节点。

## 禁止事项

- 不要输出屏幕字幕格式的短句集合。
- 不要机械保持“一行原文 = 一行中文”。
- 不要只翻译标题、描述或片段后声称完成。
- 不要输出“本段主要讲了……”这类摘要句替代正文。
- 不要因为长视频而省略中间章节。
- 不要添加中文创作者自己的评价或原视频没有的新事实。
- 不要为了填满时间添加空话。
- 不要把画面锚点当作默认依据。
- 不要把 `estimated_speech_sec` 当成真实 TTS 时长。
- 不要在节点没有通过时继续推进到全片合成。

## 完成前校验

完成后必须检查：

- 输出文件有 front matter。
- 所有章节和节点按时间单调递增。
- 章节和节点之间没有明显漏掉大段时间。
- 最后一章覆盖到输入字幕最后时间点，或明确说明尾部为何不需要配音。
- 每章和每个节点都有 `target_duration_sec`、`target_speech_sec` 或等价目标、`estimated_speech_sec`、`duration_coverage_ratio`。
- 每个节点都有源文绑定：`source_subtitle_ids`、`source_start`、`source_end`、`source_excerpt`。
- 低于 90% 的章节或节点已经重写，或有文本证据说明原因。
- 没有大段外文残留。
- 没有把长视频压缩成摘要。
- 没有漏掉关键事实、数字、因果、转折、立场、例子或类比。
- 正文不包含 Markdown 标题、注释、字段名或其他不该朗读的文本。
- 已经完成真实 TTS manifest 校验，并根据 manifest 修订失败节点。
- Markdown 和 JSON 的章节数、节点 ID、时间范围和节点正文一致。
- 已经完成独立评估 agent 审阅，并处理其反馈。

如果本 skill 目录存在 `scripts/validate_voiceover_script.py`，必须运行它校验 Markdown、JSON 和 TTS manifest：

```bash
python3 {skill_dir}/scripts/validate_voiceover_script.py \
  path/to/voiceover-script.md \
  --paired path/to/semantic-nodes.json \
  --manifest path/to/tts-manifest.json
```

该脚本负责可机械验证的事项，包括 front matter、时间连续性、估算覆盖率、源文绑定、Markdown/JSON 一致性、真实 TTS 覆盖率和累计 drift。它不能替代语义覆盖评审或独立评估 agent。

## 交付

完成后告诉用户：

- 输出 Markdown 配音稿路径。
- 输出语义节点 JSON 路径。
- 源字幕路径。
- 源语言和目标语言。
- 是否分批处理。
- 章节数量和节点数量。
- 估算覆盖率、真实 TTS 覆盖率和主要 drift 风险。
- 独立评估 agent 是否通过，是否仍有人工复核问题。

不要在最终回答中贴完整口播稿；只给 1-2 个短样例即可。
