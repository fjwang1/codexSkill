---
name: worldview-china-bilibili-text-compliance-review
description: "Independently review Worldview China podcast generated text before Bilibili publishing. Use after Chinese translation, mainland safety edit, podcast script formatting, title/cover generation, subtitle generation, or publish metadata generation to check Bilibili/mainland terminology and safety rules; failed review blocks TTS, video generation, metadata, and upload until the upstream text is fixed."
---

# Worldview China Bilibili Text Compliance Review

本 skill 是独立文本审核门禁，不负责重写正文。它检查 Worldview China 播客生产中会被朗读、上屏或投稿的派生文本：中文翻译稿、03b 安全稿、`podcast_script.md`、标题、封面标题、字幕、`bilibili_upload_metadata.json` 和 `publish_info.txt`。

同一个规则引擎要跑两类节点：03 后的早期风险门禁输出到 `03d-risk-compliance-review/`，用于在 TTS 前拦住风险；04/标题/字幕/metadata 后的发布前复查输出到 `04c-bilibili-text-compliance/`，用于确保所有新增文本仍然合规。

## 规则

审核时把这些规则和 03b 内网发布安全要求放在一起判断：

- 不得出现中国当代国家领导人的具体姓名，例如 `习近平`、`习主席`、`Xi Jinping`、单独的 `Xi`；按语境改为自然统称。外国国家领导人、历史人物和非中国当代领导人可按语义保留。
- 规范使用与国家形象相关的特定标识、呼号、称谓、用语。英文表达“中国大陆”只允许 `Chinese mainland`、`China's mainland` 或 `the mainland of China`；禁止 `mainland China` / `Mainland China`。
- 规范使用特定地点、场所表述。应使用 `侵华日军南京大屠杀遇难同胞纪念馆`；禁止简称 `南京大屠杀纪念馆`。
- 规范使用中国省级自治区表述。应使用 `新疆维吾尔自治区`；禁止 `新疆维吾尔族自治区`。
- 涉台、涉港表达统一使用完整称呼 `中国台湾`、`中国香港`；不得简称 `台湾`、`香港`。同时不得把中国台湾称为国家，不得写 `中国台湾这个国家`、中国台湾语境下的 `我们的国家`、`这些国家...中国台湾` 等表述。
- 涉疆、民族宗教、政府压迫、种族灭绝、意识形态对抗等内容属于高敏发布安全项。若原文出现，03 必须忠实记录，03b/04 必须做最小必要删改、弱化或桥接，并确保标题、封面、字幕和投稿文案不把它放大成卖点。
- 宗教内容不得构成或近似构成互联网宗教信息服务。B 站发布稿、TTS、字幕、标题、封面和投稿文案不得传播宗教教义、教规、礼仪、讲座、课程或学习路径；不得出现 `达瓦`、宣教、传教、街头外展、清真寺邀请参观/讨论、引导如何信教或皈依等内容；不得把特定宗教包装成 `真理`、`更和平`、`符合我的信仰` 或心理/精神危机的解决方案；不得以宗教名义做商业宣传、投资推广、宗教用品或宗教机构商业活动推广。
- 可以保留低风险的中性文化/社会事实，例如人口、移民、餐饮习惯、历史沿革、社群生活观察；但必须用社会观察语气呈现，不做信仰劝导、优越性判断、参与邀请或教学说明。若某段从人口/文化观察转入宣教、皈依、宗教课程、清真寺外展或宗教解决精神危机，应整段 cut 或桥接回可发布主线，不要只替换个别词。
- 标题、封面和 metadata 不得使用站队式、对抗式或诱导表态的高风险表达，例如把宗教/族群主体写成“该押注中国吗？”这类投票式标题。
- 标题、封面和 metadata 也不得把 `伊玛目`、`伊斯兰教兴起`、`皈依`、`宗教真理`、`清真寺外展` 等作为点击卖点；如果源视频主体是宗教人物或宗教议题，标题应降敏为社会文化/海外观察角度，或在选题阶段放弃该候选。
- B 站简介必须是内容简介，不是制作说明。`publish_info.txt` 或 `bilibili_upload_metadata.json.description` 不得写 `中文配音版本`、`保留原视频画面`、`替换为中文对话音频`、`方便中文观众理解原对话内容` 等流水线话术；应改成“这一集谈了什么、冲突/问题是什么、核心看点是什么”。
- 中文可发布文本不得保留英文千分位数字，例如 `300,000`。这类写法容易让 TTS 误读，也会让字幕显得不自然；应改成 `30万`、`3000` 等中文显示形式。注意这不是“所有数字转万”：普通 `300` 不动，`3,000` 不得写成 `0.3万`。
- 03b 已经 cut 或弱化的敏感表达，不得在 04 播客稿、音频 manifest、字幕、标题、封面或 metadata 中重新引入。

## 工作流

1. 主 agent 在 03/03b/04/02d/07/10 生成文本时，必须提前把上述规则写入生成约束，避免源头产出违规文本。
2. 文稿产出后，主 agent 启动独立审核子 agent，读取本 skill 和 run 目录文本产物，以无上下文审核身份给出 `PASS` / `FAIL` 和命中位置。独立审核必须特别扫描连续上下文，而不是只查词：如果一段形成“社会问题/精神危机 -> 宗教解决 -> 皈依/选择某宗教”或“社群观察 -> 宣教/课程/清真寺邀请”的叙事链，应判 `FAIL`。
3. 同时运行 bundled deterministic check，作为低成本召回：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-text-compliance-review/scripts/run_bilibili_text_compliance_review.py \
  --run-dir <run_dir> \
  --stage after_script
```

早期门禁运行时使用：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-text-compliance-review/scripts/run_bilibili_text_compliance_review.py \
  --run-dir <run_dir> \
  --stage after_translation_gate \
  --output-dirname 03d-risk-compliance-review
```

4. 默认发布前复查输出写入：

```text
04c-bilibili-text-compliance/text-compliance-review-result.json
04c-bilibili-text-compliance/text-compliance-review-report.md
```

5. 若 deterministic check 或独立审核子 agent 任一 FAIL，不得进入后续 TTS、字幕、视频合成、metadata 或 B 站投稿。应回到对应上游节点做最小必要修复，再重新运行审核。

上传前如果 02d 标题/封面、07 字幕或 10 metadata 有新增/变更，必须用同一个脚本和子 agent 复跑审核，确保 `text-compliance-review-result.json` 是最新文本的 PASS 结果。
