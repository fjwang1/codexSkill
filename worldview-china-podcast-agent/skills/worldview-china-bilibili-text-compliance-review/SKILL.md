---
name: worldview-china-bilibili-text-compliance-review
description: "Independently review Worldview China podcast generated text before Bilibili publishing. Use after Chinese translation, mainland safety edit, podcast script formatting, title/cover generation, subtitle generation, or publish metadata generation to check Bilibili/mainland terminology and safety rules; failed review blocks TTS, video generation, metadata, and upload until the upstream text is fixed."
---

# Worldview China Bilibili Text Compliance Review

本 skill 是独立文本审核门禁，不负责重写正文。它检查 Worldview China 播客生产中会被朗读、上屏或投稿的派生文本：中文翻译稿、03b 安全稿、`podcast_script.md`、标题、封面标题、字幕、`bilibili_upload_metadata.json` 和 `publish_info.txt`。

## 规则

审核时把这些规则和 03b 内网发布安全要求放在一起判断：

- 不得出现中国当代国家领导人的具体姓名，例如 `习近平`、`习主席`、`Xi Jinping`、单独的 `Xi`；按语境改为自然统称。外国国家领导人、历史人物和非中国当代领导人可按语义保留。
- 规范使用与国家形象相关的特定标识、呼号、称谓、用语。英文表达“中国大陆”只允许 `Chinese mainland`、`China's mainland` 或 `the mainland of China`；禁止 `mainland China` / `Mainland China`。
- 规范使用特定地点、场所表述。应使用 `侵华日军南京大屠杀遇难同胞纪念馆`；禁止简称 `南京大屠杀纪念馆`。
- 规范使用中国省级自治区表述。应使用 `新疆维吾尔自治区`；禁止 `新疆维吾尔族自治区`。
- 涉台、涉港表达统一使用完整称呼 `中国台湾`、`中国香港`；不得简称 `台湾`、`香港`。同时不得把中国台湾称为国家，不得写 `中国台湾这个国家`、中国台湾语境下的 `我们的国家`、`这些国家...中国台湾` 等表述。
- 涉疆、民族宗教、政府压迫、种族灭绝、意识形态对抗等内容属于高敏发布安全项。若原文出现，03 必须忠实记录，03b/04 必须做最小必要删改、弱化或桥接，并确保标题、封面、字幕和投稿文案不把它放大成卖点。
- 标题、封面和 metadata 不得使用站队式、对抗式或诱导表态的高风险表达，例如把宗教/族群主体写成“该押注中国吗？”这类投票式标题。
- 03b 已经 cut 或弱化的敏感表达，不得在 04 播客稿、音频 manifest、字幕、标题、封面或 metadata 中重新引入。

## 工作流

1. 主 agent 在 03/03b/04/02d/07/10 生成文本时，必须提前把上述规则写入生成约束，避免源头产出违规文本。
2. 文稿产出后，主 agent 启动独立审核子 agent，读取本 skill 和 run 目录文本产物，以无上下文审核身份给出 `PASS` / `FAIL` 和命中位置。
3. 同时运行 bundled deterministic check，作为低成本召回：

```bash
python3 /Users/wangfangjia/.codex/skills/worldview-china-podcast-agent/skills/worldview-china-bilibili-text-compliance-review/scripts/run_bilibili_text_compliance_review.py \
  --run-dir <run_dir> \
  --stage after_script
```

4. 输出固定写入：

```text
04c-bilibili-text-compliance/text-compliance-review-result.json
04c-bilibili-text-compliance/text-compliance-review-report.md
```

5. 若 deterministic check 或独立审核子 agent 任一 FAIL，不得进入后续 TTS、字幕、视频合成、metadata 或 B 站投稿。应回到对应上游节点做最小必要修复，再重新运行审核。

上传前如果 02d 标题/封面、07 字幕或 10 metadata 有新增/变更，必须用同一个脚本和子 agent 复跑审核，确保 `text-compliance-review-result.json` 是最新文本的 PASS 结果。
