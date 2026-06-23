---
name: ppt-master-article-deck
description: 中文阅读版。把中文或英文稿件、文章、报告、PDF/DOCX/Markdown/文本/URL/播客稿交给本地 canonical PPT Master workflow，生成一份正常、精致、可编辑的 PPTX。
---

# PPT Master Article Deck 中文阅读版

> 原文：`/Users/wangfangjia/.codex/skills/ppt-master-article-deck/SKILL.md`。原文是执行权威；本文件用于中文学习和索引。

## 1. 角色定位

这个 skill 是一个很薄的全局 wrapper。真正的设计和执行权威仍然是本地 PPT Master：

```text
/Users/wangfangjia/code/ppt-master/skills/ppt-master/SKILL.md
```

它不在 wrapper 里重新发明一套设计模型，也不把视频章节图、播客章节图等规则硬塞进普通 PPT 生成。它的任务是：把输入稿件交给本地 PPT Master，按本地规范生成一份正常的、可编辑的 `.pptx`。

## 2. 范围

本 skill 产出的是普通 editable PPTX deck。

它不负责直接产出播客/视频用的 4K PNG 章节图。如果已经有 PPT Master 项目，后续要转成 4K 视频图像，应该走专门的视频视觉 skill。

## 3. 最小用户约束

除非用户明确指定，否则只向 PPT Master 传入这些额外约束：

- 文章型 deck 默认用 PPT 16:9，即 `ppt169`。
- 默认不要使用黑色或深色主背景。
- 避免泛泛的深色科技 dashboard 风、霓虹蓝绿配色、黑底高亮线条。
- 不要在 slide canvas 上放可见的 source/footer attribution。
- 不要在 slide canvas 上放内部生产说明、验证标签、样例标签、workflow 标签、draft/debug 标签。

不要硬编码：

- 固定页数。
- 固定卡片模板。
- 固定标题长度。
- 固定 bullet 数。
- 默认进度条。
- 强制图标风格。
- 强制字体。
- 强制图片策略。

这些都要让 PPT Master 从稿件本身动态决定。

## 4. 可选整套模板

本地 PPT Master 有一些可复用 deck 模板。wrapper 不会自动选择它们；只有调用者明确传入模板目录路径时才进入模板模式。

常见模板路径：

```text
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/editorial_magazine
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/swiss_grid
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/memphis_pop
/Users/wangfangjia/code/ppt-master/skills/ppt-master/templates/decks/risograph_zine
```

注意：裸名字如 `editorial_magazine` 不够，必须传目录路径。

## 5. 规范路径

```bash
PPT_MASTER=/Users/wangfangjia/code/ppt-master
SKILL_DIR=/Users/wangfangjia/code/ppt-master/skills/ppt-master
OUT_ROOT=/Volumes/GT34/Generated
CACHE_ROOT=/Volumes/GT34/Caches
VENV=/Volumes/GT34/Caches/ppt-master-venv
```

生成项目默认放在 `/Volumes/GT34/Generated`。大文件工作开始前先检查外置盘：

```bash
test -d /Volumes/GT34 && test -w /Volumes/GT34
```

运行脚本时优先使用外置盘上的 venv：

```bash
/Volumes/GT34/Caches/ppt-master-venv/bin/python
```

## 6. 工作流

1. 读取本地 canonical PPT Master skill：

   ```text
   /Users/wangfangjia/code/ppt-master/skills/ppt-master/SKILL.md
   ```

2. 按本地 skill 执行：项目创建、Strategist、Executor、验证、finalize、PPTX 导出。

3. 在 `/Volumes/GT34/Generated` 下初始化项目。除非用户指定别的格式，文章型 deck 默认用 `ppt169`：

   ```bash
   python3 ${SKILL_DIR}/scripts/project_manager.py init <project_slug> --format ppt169 --dir ${OUT_ROOT}
   ```

4. 用 PPT Master 的 source import 路径导入材料：

   ```bash
   python3 ${SKILL_DIR}/scripts/project_manager.py import-sources <project_path> <source_files...> --copy
   ```

5. Strategist 阶段只传入最小用户约束，其余视觉策略必须由来源稿件动态驱动。

6. Executor 阶段按本地规则逐页生成 SVG，保存到：

   ```text
   <project_path>/svg_output/
   ```

   不要批量套模板生成整套 deck。

7. 跑验证、清理、notes 拆分、finalize、PPTX 导出：

   ```bash
   python3 ${SKILL_DIR}/scripts/svg_quality_checker.py <project_path>
   python3 /Users/wangfangjia/.codex/skills/ppt-master-article-deck/scripts/remove_source_footers.py <project_path>
   python3 ${SKILL_DIR}/scripts/total_md_split.py <project_path>
   python3 ${SKILL_DIR}/scripts/finalize_svg.py <project_path>
   python3 /Users/wangfangjia/.codex/skills/ppt-master-article-deck/scripts/remove_source_footers.py <project_path> --also-final
   python3 ${SKILL_DIR}/scripts/svg_to_pptx.py <project_path>
   python3 ${SKILL_DIR}/scripts/project_manager.py validate <project_path>
   ```

8. 最后验证导出的 PPTX 存在、能被 `python-pptx` 打开、页数与 SVG deck 一致。

## 7. 最终回复应该报告什么

- 最终 PPTX 的绝对路径。
- 项目目录绝对路径。
- slide 数量和验证摘要。
- 任何重要限制或跳过的阶段。

不要把 localhost preview URL 当作交付物。
