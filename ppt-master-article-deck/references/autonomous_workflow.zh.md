# Autonomous PPT-Master Workflow 中文阅读版

> 原文：`/Users/wangfangjia/.codex/skills/ppt-master-article-deck/references/autonomous_workflow.md`。原文是执行权威；本文件用于中文学习和索引。

这个 reference 的作用，是把 PPT Master 里原本可能需要人类确认的设计 checkpoint，改造成 AI 内部自主完成的设计判断。它不是默认值清单，不能用来硬编码；它是一组必须从稿件和用户请求中回答的问题。

## 1. 动态设计门禁

写 `design_spec.md` 之前，需要从稿件和用户请求中回答这些门禁：

1. **目的和受众**：谁会使用这份 deck？他们看完后应该获得什么理解或决策？他们已有多少背景知识？
2. **输出语言**：使用用户要求的语言；如果没有指定，则从对话、来源材料和可能受众推断。
3. **画布和格式**：根据观看场景选择物理 slide 格式：会议/屏幕、课堂、移动端/社交媒体、memo 式故事，或其他明确用途。
4. **叙事结构**：识别来源材料真实的论证单元、张力、证据、转折点和结尾，让这些单元决定页数。
5. **沟通模式**：在 editorial narrative、general visual explainer、consulting/data brief、top-consulting logical memo、product/keynote、academic 等模式中选择。
6. **视觉语气**：从主题和来源声音推导：克制、分析性、紧迫、文化性、以人为中心、技术性、乐观、批判等。
7. **配色**：选择支持主题和语气的颜色；避免单一色系，也不要沿用上一套 deck 的颜色。
8. **字体**：选择 PPT 安全字体，匹配语言和语气；如果有中文，必须保证 CJK 文本可读。
9. **信息设计**：判断哪些 claim 应该用图表、时间线、地图、图解、引用、比较，或安静的 text-first 页面。
10. **图标/图片策略**：图标和原生 SVG 信息设计能承载意义时优先使用；真实图片或 AI 生成图片只在显著提升理解且资源可得时使用。
11. **并行资产计划**：如果需要图片，先锁定完整 asset manifest，然后图片搜索/生成/编辑可以并行；slide SVG 创作仍然顺序执行。
12. **页脚政策**：任何 slide 不放可见 source 或 attribution footer；页码只有在改善定位时才使用。
13. **讲者备注**：决定 notes 是简洁 presenter prompts、详细 voiceover notes，还是轻量 deck 中省略。

## 2. 页数判断启发式

不要从目标页数开始。先从 argument map 开始：

- 中心承诺或中心张力，通常一页。
- 每个需要独立视觉处理的主要论证单元，通常一页。
- 如果压缩会遮蔽重点，重要证据簇需要单独一页。
- 需要一页 synthesis、implication 或 decision frame。

相邻单元如果承担同样的视觉任务，可以合并。一个页面如果需要两个无关标题、太多数字或不兼容的布局，则应该拆开。好的 deck 可以短也可以长，正确页数是能保留论证形状的页数。

## 3. 风格选择信号

用这些信号选择沟通模式，然后适配，而不是复制某个 preset：

- 公共政策、经济、市场、战略、不平等、公司或产业分析：consulting/data 或 editorial consulting。
- 文化文章、人文故事、旅行、历史、社会：editorial narrative 或 visual explainer。
- 技术报告、研究、工程、科学：structured technical explainer，使用精确图解。
- 产品发布、pitch、campaign、creator story：keynote/product mode，视觉节奏更强。
- 同时有人物和系统的混合文章：在人尺度页面和系统/证据页面之间交替。

## 4. 质量标准

- 每一页有一个主导信息、清晰层级和足够阅读留白。
- 图表坐标和比例必须校准、真实。
- 文字不重叠、不溢出、不依赖过小不可读标签。
- deck 应该像是为这篇稿件设计的，而不是通用模板里填 bullets。
- 导出的 PPTX 是产品；SVG 和 preview 是中间检查产物。
