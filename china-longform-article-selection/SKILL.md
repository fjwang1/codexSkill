---
name: china-longform-article-selection
description: "用于从 Bloomberg、Economist、Financial Times、New York Times、New Yorker、WIRED、Wall Street Journal、Nikkei Asia、Rest of World、The Guardian、The Diplomat、The Atlantic、Harper's、London Review of Books、New York Review of Books、Noema、Quanta、ProPublica、The Information、MIT Technology Review 等英文媒体中检索外部传入 target_date 发布或更新的非中国相关英文深度长文；默认使用 global_deep_longform 模式：只要与中国无关的篇幅长、信息密度高、叙事/分析质量好的深度好文，中国相关是硬排除项；所有白名单来源的高质量文章进入统一候选池竞争，不设置每源入围配额；先按标题、摘要、metadata、公开片段召回和深度评分，再执行正文可获取性门禁；最终输出 1 到 2 篇可阅读、可进入后续制作的候选，不强行凑满 2 篇，并自动选出评分最高候选作为默认制作文章。"
---

# Deep Longform Article Selection

使用本 skill 为中文内容生产做“指定日期英文外媒非中国相关深度长文候选 1-2 篇”筛选。

当前默认版本是**非中国相关全球深度长文 + 可用正文门禁 + 自动最佳候选版**：

```text
1. AI 自动召回白名单来源中 target_date 发布或更新的深度长文，形成统一候选池。
2. AI 先基于标题、摘要、metadata、搜索结果片段、公开可见首屏或部分正文做深度/质量/篇幅初筛评分。
3. 对可能进入最终 1-2 篇候选的文章执行正文可获取性门禁，确认能得到可读文章材料。
4. 获取顺序固定为：原站公开全文 -> `url-page-capture` 归档/真实 Chrome 抓取 -> 合法公开同文转载源。
5. Bloomberg、New York Times、Wall Street Journal 归档路径默认视为不友好；原站不可读时必须寻找合法公开同文转载源，找不到就淘汰。
6. 最终从所有可用候选中统一排序输出 1 到 2 篇；允许候选两篇来自同一个媒体，不为来源多样性保留名额；自动把评分最高候选设为 `recommended_best_candidate_id` / `best_candidate`，不等待人类选择。
```

不要在最终回复里粘贴第三方文章全文或长篇翻译。

## 选题模式

本 skill 默认只使用非中国相关全球深度长文模式：

```text
selection_mode = global_deep_longform
```

`global_deep_longform` 选择“值得翻译成中文、适合公众号长文包”的英文深度好文。核心判断：

```text
1. 文章是否足够长：通常应明显超过普通新闻短讯，目标是 1800+ 英文词；专题、调查、长访谈、长评论、数据特稿、叙事特稿优先。
2. 文章是否足够好：信息密度、原创采访/数据/材料、解释框架、叙事张力、观点质量、翻译成中文后的阅读价值。
3. 文章是否适合中文公众号：有清晰问题意识，能让中文读者获得新知识、新框架或强叙事体验。
4. 中国相关是硬排除项。文章的主题、主要叙事、核心冲突、关键证据、主要人物/机构、政策影响、产业变量或读者收益不得围绕中国、中国企业、中国政府、中国社会、中国地区议题、华人身份政治、中美竞争、对华政策或中国供应链展开。只有偶发背景提及且不影响文章主旨时才可保留，并必须标注 `china_connection_type="incidental_background_only"`。
5. 不强行凑满 2 篇。宁可只返回 1 篇真正好文，也不要塞入短讯、低密度文章、中国相关文章或拿不到正文的文章。
```

模式判定：

```text
任何“深度好文”“长文”“高质量外刊”“公众号选题”“默认公众号选题”请求 -> global_deep_longform
任何“中国选题”“中国热点”“爆款”“流量”“China Viva”请求都不应由本 skill 满足；返回 `MODE_UNSUPPORTED_CHINA_RELATED_REQUEST`，不要自动回退到中国相关选题。
旧 china_viral、china_domestic 和 asia_china 已停用，不作为日常模式；不要自动回退。
```

## 输入参数

调用本 skill 时必须显式提供：

```text
target_date: YYYY-MM-DD
target_timezone: 默认 Asia/Shanghai，除非调用方明确指定其他时区
requested_count: 默认 2，但只是上限；最终返回 1 到 requested_count 篇，最多 2 篇，最少 1 篇可用高质量非中国相关候选
minimum_returned_count: 默认 1
selection_mode: 默认 global_deep_longform；中国相关模式已停用
preview_only: 当前默认 false；本 skill 必须自动给出最高分候选作为本轮默认答案
retrieval_gate: 默认 true；进入最终候选集前必须通过正文可获取性门禁
```

日期职责边界：

```text
1. 上游总控、自动化任务或直接用户请求负责决定 target_date。
2. 如果上游想跑“昨天”，必须先按目标时区计算出绝对日期，再把 target_date=YYYY-MM-DD 传入本 skill。
3. 本 skill 只使用传入的 target_date 做检索窗口、输出目录和候选审计；不得自行把缺失日期解释成昨天。
4. 用户直接调用本 skill 且只说“昨天/前天/某天”时，执行 agent 可以把用户显式日期意图解析为绝对 target_date，但必须在报告中写明解析结果。
5. 如果没有任何可解析日期，返回 NEEDS_TARGET_DATE，不要启动检索或写入产物。
```

## 正文可获取性门禁

本 skill 必须在输出最终候选前确认候选文章有可阅读材料。不要让“看起来很深但拿不到正文”的文章进入最终候选。

执行顺序：

```text
1. 先做候选召回和初筛评分，形成高于 requested_count 的候选池。
2. 对按分数排序后可能进入最终候选集的文章逐篇执行 retrieval gate。
3. 候选通过 gate 后才可进入最终候选集。
4. 如果候选失败，记录排除原因，然后继续检查下一篇候选，直到得到 requested_count 篇可用候选、或候选池耗尽、或继续检查只会引入低质量文章。
5. global_deep_longform 模式不要为了凑满 2 篇而降低篇幅/质量门槛；如果只有 1 篇真正合格，就只返回 1 篇。
```

可接受的正文来源：

```text
original_public_open:
  原站公开可读全文，无登录墙、订阅墙、验证码、安全验证或正文过短问题。
  即使原站公开可读，也必须用 `url-page-capture` 的 HTTP/public direct 或真实 Chrome direct 路径
  落成本地 capture package，写出 capture_output_path 和 capture_manifest_path。

archive_capture_success:
  按 /Users/wangfangjia/.codex/skills/url-page-capture/SKILL.md 调用 `url-page-capture`，
  使用真实 Chrome / archive.is 系列镜像搜索 / 快照候选流程得到可读正文。
  必须保留 `url-page-capture` 返回的实际 capture_method，而不是改写成笼统标签。

legal_republication_success:
  原站不可读且归档路径不可用时，找到合法公开同文转载源，并确认它确实是同一篇文章。
  合法转载源本身也必须通过 `url-page-capture` 或公开 HTTP 抓取落成本地材料；
  同时必须写出 legal_source_manifest_path 记录同文与授权判断。
```

禁止的正文来源：

```text
1. 社交媒体全文搬运、个人博客未授权转载、论坛复制、盗版镜像、绕付费墙教程。
2. 只基于原文写的评论、摘要、二创、播客稿、新闻聚合页、AI 总结页。
3. 只有标题、RSS 摘要、搜索片段、metadata、首屏 teaser 或付费墙提示。
4. 需要用户手动解 CAPTCHA、reCAPTCHA、Turnstile 或安全验证才能继续的路径。
5. 读取本地 Chrome Cookie、Local Storage、Session、Preferences、Login Data 等内部文件。
```

调用 `url-page-capture` 的要求：

```text
1. 必须先读取并遵守 /Users/wangfangjia/.codex/skills/url-page-capture/SKILL.md。
2. 对 archive.is/archive.today/archive.ph/archive.md，只使用该 skill 的真实 Chrome 搜索流程。
3. 不要直接打开记忆中的短快照 URL 作为成功证据；短快照必须来自当前运行的搜索结果页或用户本轮明确提供。
4. CAPTCHA/security check 不是让用户介入的提示，而是 capture_failed 的证据；切换镜像或候选后仍失败就淘汰。
5. 不要把 `url-page-capture` 的实际 `capture_method` 覆盖成别的值；用 `capture_provider` 表达工具来源。
```

真实 Chrome 工具定位：

```text
当 `url-page-capture` 要求使用 Chrome Extension / `chrome:control-chrome` 时，必须通过 Node REPL 的 JS 工具接入用户主 Chrome：

工具名：
  mcp__node_repl.js

Chrome control skill：
  /Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.616.71553/skills/control-chrome/SKILL.md

browser-client 绝对路径：
  file:///Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.616.71553/scripts/browser-client.mjs

最小连接代码：
  const { setupBrowserRuntime } = await import("file:///Users/wangfangjia/.codex/plugins/cache/openai-bundled/chrome/26.616.71553/scripts/browser-client.mjs");
  await setupBrowserRuntime({ globals: globalThis });
  globalThis.browser = await agent.browsers.get("extension");
  await browser.nameSession("🔎 Article capture");
  nodeRepl.write(await browser.documentation());
```

执行约束：

```text
1. 不得只因为普通工具搜索没有返回 `chrome:control-chrome` 就判定真实 Chrome 不可用。
2. 如果需要真实 Chrome 抓取，必须先尝试上述 Node REPL 接入路径。
3. 若上述接入失败，必须在 selection/ 下写出 `chrome-unavailable-report.json`，记录工具名、browser-client 路径、失败错误和候选 URL；然后才能把候选标记为 `BLOCKED_REAL_CHROME_UNAVAILABLE` 或 `retrieval_unavailable`。
4. 对 The Economist、Financial Times、The New Yorker、WIRED 等普通 publisher article，HTTP 抓取遇到 Cloudflare、Just a moment、登录墙、订阅墙、薄正文或安全验证后，必须尝试真实 Chrome direct，再尝试真实 Chrome archive.is/archive.today 搜索流程，除非用户明确要求跳过。
5. 对 Bloomberg / New York Times / Wall Street Journal，仍遵守“不友好站点策略”：原站不可公开读取时优先搜索合法公开同文转载源，不把 archive.is 作为主要路径反复尝试。
```

正文状态统一表达为：

```text
retrieval_gate = "enabled"
manual_article_required = false when material_available=true
material_available = true | false
capture_provider = "url-page-capture"
capture_method =
  url-page-capture 返回的实际方法值，例如
  "chrome-extension-direct" |
  "chrome-extension-archive-is-search" |
  "http-public-direct" |
  "chrome-archive-is-search"
fulltext_status =
  "original_public_open" |
  "archive_capture_success" |
  "legal_republication_success" |
  "retrieval_unavailable"
capture_output_path = 本地可读文章材料路径
capture_manifest_path = 抓取该可读材料的 manifest 路径
legal_source_manifest_path = 合法转载源同文审计路径，仅 legal_republication_success 必填
material_manifest_path = 下游统一读取的主审计路径；原站/归档等于 capture_manifest_path，合法转载等于 legal_source_manifest_path
```

最终候选硬门槛：

```text
material_available 必须为 true。
capture_output_path 或等价本地文章材料路径必须存在。
capture_manifest_path 必须存在。
material_manifest_path 必须存在。
legal_republication_success 还必须有 legal_source_manifest_path。
正文必须不是登录页、付费墙、验证码页、归档搜索页、评论区或导航页。
global_deep_longform 模式还必须满足：不是短讯；长度/信息密度至少达到“中高”；有明确深度价值；与中国无关。
如果文章的主旨、主要叙事、核心冲突、关键证据、主要人物/机构、政策影响、产业变量或读者收益与中国相关，必须淘汰，不得进入最终候选。
china_viral 模式已停用；不要在本 skill 中返回中国相关候选。
```

合法转载源审计文件固定写到：

```text
selection/legal-source-checks/<candidate_id>.json
```

结构至少包含：

```json
{
  "candidate_id": "A1",
  "original_url": "https://original.example/article",
  "original_title": "Original title",
  "legal_source_url": "https://legal.example/article",
  "authorization_basis": "publisher syndication | wire redistribution | official partner republication | other explicit lawful basis",
  "same_article_evidence": {
    "title_match": true,
    "byline_match": true,
    "date_match": true,
    "public_excerpt_match": true,
    "key_facts_match": ["..."]
  },
  "capture_output_path": "...",
  "capture_manifest_path": "...",
  "verdict": "same_article_legal_republication | rejected_not_same_article | rejected_not_legal | rejected_not_readable"
}
```

## 不友好站点策略

以下站点在本地测试中对 archive.is 搜索路径不友好，常见结果是 `One more step` / security check / CAPTCHA：

```text
Bloomberg / bloomberg.com
The New York Times / nytimes.com
The Wall Street Journal / wsj.com
```

对这些来源执行固定策略：

```text
1. 先检查原站是否公开可读全文。
2. 如果原站不可读，不要把 archive.is 作为主要路径反复尝试。
3. 必须搜索合法公开同文转载源。
4. 合法源找不到、不可读、或无法确认同文时，候选标记 retrieval_unavailable 并从最终候选淘汰。
```

合法公开同文转载源判定：

```text
1. 来源必须是媒体、通讯社、授权 syndication/republishing 平台、机构数据库公开页或出版方明确授权渠道。
2. 必须能公开阅读足够正文，而不是只展示摘要或购买提示。
3. 必须和原文一致：标题/副标题、作者或署名、发布日期、主题、公开片段、关键事实至少有多项匹配。
4. 若只是“据某媒体报道”的转述、评论或二次创作，只能作为背景资料，不能让原候选通过 gate。
5. 不能确认一致时，按失败处理，不要为了凑最终候选放行。
```

## 固定来源

只从以下来源检索，除非用户明确修改白名单。global_deep_longform 模式可以使用所有来源，但最终候选必须与中国无关；明显中国专题来源通常不会产生合格候选，除非某篇文章确实与中国无关。

授权状态：本固定来源白名单内的报纸/媒体，账号均已取得全文中文翻译与微信公众号草稿/发布授权。选题阶段仍需保留来源、原题、原文 URL、发布日期、材料来源和抓取审计信息，但不得因为缺少中文来源名映射而排除候选。

1. Bloomberg / Bloomberg Businessweek
2. The Economist
3. Financial Times
4. The New York Times / The New York Times Magazine
5. The New Yorker
6. WIRED
7. The Wall Street Journal
8. Nikkei Asia
9. The Wire China
10. Rest of World
11. China Leadership Monitor
12. The Atlantic
13. MIT Technology Review
14. Foreign Affairs / Foreign Policy
15. Reuters Special Reports / Reuters Graphics / Reuters Investigates only
16. The Diplomat
17. East Asia Forum
18. Council on Foreign Relations / CSIS analysis only
19. The Guardian / Guardian Long Read / features and analysis only
20. Harper's Magazine
21. London Review of Books
22. New York Review of Books
23. The Point
24. Noema Magazine
25. Aeon / Psyche
26. Quanta Magazine
27. Nautilus
28. ProPublica
29. The Markup
30. The Information
31. Semafor deep analysis only
32. The Verge features / command-line not short news
33. The Dispatch / Persuasion / American Affairs only when essay-length and high quality

Reuters 普通快讯、market wrap、live blog、timeline 默认不要；只有 special report、graphics、investigation、deep analysis 才能进入候选。

The Guardian 普通快讯、live blog、minute-by-minute、短新闻和图片稿默认不要；只有 Guardian Long Read、feature、investigation、analysis 等高质量长文才进入候选，且必须与中国无关。

## 日期窗口

本 skill 没有日期默认值；调用方必须传入绝对 `target_date`。

检索范围：

```text
目标日期 = 外部传入的 target_date
只检索目标日期 00:00-23:59 内发布或更新的文章。
global_deep_longform 模式也不得向前回看补数；如果目标日期只有 1 篇真正合格，就只返回 1 篇。
每个候选必须标注 date_scope="target_date" 和 date_reason。
```

如果媒体只显示相对时间、源站时区或搜索结果日期不一致，可以保留候选，但必须标注：

```text
date_confidence: low | medium | high
date_reason: 为什么认为它属于 target_date 或为什么不确定
```

候选池和最终候选都优先选择日期确认度高的文章。

## 统一候选池召回

不要按来源设置入围配额。每个白名单来源可以返回 0 篇、1 篇或多篇质量合格候选，但单个来源最多提交 5 篇候选到统一候选池；超过 5 篇就没有下游价值，不要继续抓取、评分或保留。所有候选进入同一个全局候选池后统一评分、统一执行正文可获取性门禁、统一竞争最多 2 篇最终候选。

来源多样性不是排序目标。若 The Economist、Bloomberg、Financial Times 或任何其他单一媒体在同一天有多篇明显更强的深度好文，最终候选可以多篇甚至全部来自同一个媒体。不要为了“每源均衡”保留弱文章，也不要因为某来源已经有文章入围而压低同源强文章。

若某来源没有任何合格文章，返回 `NO_SOURCE_CANDIDATE`。不要为了凑来源数量放入短讯、低相关文章或正文不可获取文章。

理想执行方式：

1. 并发检索所有来源，不要串行一个媒体做完再做下一个。
2. 如果可用，启动 source scout 子 agent，每个来源一个。
3. 每个 scout 只负责自己的来源，不做跨来源比较，但可返回该来源所有质量合格候选。
4. 每个 scout 不得设置固定上限为 1；每个来源最多返回 5 篇最强质量合格候选，并记录被排除的低质/短讯/日期不符文章。
5. 合并所有来源候选后，按统一评分规则排序，形成全局最多 2 篇候选；不强行凑满。

如果没有子 agent 工具，使用可并发的搜索/读取工具批量执行。

## 短讯和长度规则

不要返回“一两句话能说清楚”的资讯类短讯。默认排除：

```text
news brief
briefing
live updates
market wrap
daily roundup
newsletter digest
press release rewrite
wire copy
纯股价/财报即时消息
纯制裁/任命/发布会单点消息
SEO 汇总页
无原创采访、数据、案例或分析框架的短稿
```

召回初筛阶段不要臆测精确词数。用标题、摘要、栏目、页面类型、metadata、搜索结果片段和公开可见页面结构估计：

```text
estimated_word_count: null 或粗估
length_judgement: "足够" | "可能足够" | "偏短" | "无法确认"
length_confidence: "high" | "medium" | "low"
is_short_news: true | false
length_basis: "metadata/search_snippet/source_visible_excerpt/section_type/etc."
```

进入 retrieval gate 的候选应尽量满足：

```text
is_short_news = false
length_judgement 不是 "偏短"
```

最终候选必须额外满足：

```text
material_available = true
```

如果文章质量可能很高但长度无法确认，可以进入 retrieval gate；只有抓取或合法公开源验证后确认为可读材料，才允许进入最终候选。

## 主题相关性

### global_deep_longform

文章必须与中国无关。非中国题材只有深、长、好、适合中文读者，才可以进入最终候选。

中国相关硬排除：

```text
以下任一情况为 `china_exclusion_status="EXCLUDE"`，不得进入 retrieval gate 或最终候选：
- 标题、摘要、核心论题、主要叙事、主要人物/机构、政策影响或产业变量围绕中国、中国地区议题、中国企业、中国政府、中国社会、华人身份政治、中美竞争、对华政策、中国供应链展开。
- 中国不是唯一对象，但文章的解释框架或读者收益需要中国变量才能成立。
- 文章主要价值在于帮助中文读者理解中国处境、对华政策、地缘政治中的中国角色，或中国社会/产业/普通人经验。

只有以下情况可保留，并必须标注 `china_connection_type="incidental_background_only"`：
- 中国只是列表式背景、历史比较、全球市场中的非关键例子，删除该提及也不改变文章主旨。
```

默认优先这些深度方向：

```text
全球政治经济与制度变化
科技、AI、芯片、互联网平台、科学突破及其社会后果
商业、产业、公司、劳动、供应链、金融体系的深度解释
城市、住房、教育、医疗、代际、阶层、家庭与个人生活
战争、外交、地缘政治，但必须有清晰机制、人物或社会后果，不要普通战况短讯
气候、能源、环境、农业、公共卫生，但必须有叙事或解释框架
思想、文化、文学、历史、哲学、社会科学长文，只要中文读者会真正获得新视角
调查报道、人物特写、长访谈、数据特稿、长评论、书评型思想文章
```

默认淘汰或强降权：

```text
普通快讯、新闻简报、市场短讯、财报单点、政策声明复述
只有观点姿态，没有事实材料、采访、数据、历史纵深或解释框架
只适合非常窄的专业圈，翻译后中文读者获得感弱
标题吸引但正文可能是 newsletter 摘要、链接聚合或短评
无法确认属于 target_date 当天发布/更新
```

每个候选必须输出：

```text
depth_quality_score: 0-45
depth_quality_reason: "原创材料、信息密度、解释框架、叙事/论证质量为什么高"
length_score: 0-20
length_reason: "为什么判断这是长文/深度文，而不是短讯"
wechat_fit_score: 0-20
wechat_fit_reason: "为什么适合中文公众号读者，翻译后有什么获得感"
china_exclusion_status: "PASS | EXCLUDE"
china_connection_type: "none | incidental_background_only | china_related_excluded"
china_exclusion_reason: "为什么判断与中国无关，或为什么因中国相关被排除"
freshness_score: 0-5
global_deep_score: 0-100
quality_level: "高|中高|中|淘汰"
topic_tags: [...]
reader_payoff: "中文读者读完会获得什么"
translation_hook: "适合公众号标题/导语的切入点"
why_it_is_worth_translating: "为什么值得翻成中文"
why_it_might_fail: "为什么可能不适合"
```

硬门槛：

```text
china_exclusion_status = "EXCLUDE"：不得进入最终候选
depth_quality_score < 28：不得进入最终候选
length_score < 12：不得进入最终候选
wechat_fit_score < 10：不得进入最终候选
quality_level = "淘汰"：不得进入最终候选
```

评分：

```text
深度质量 45 分：
  40-45：调查/长特写/强分析，有原创采访、数据、档案、场景、复杂机制或高质量思想框架。
  34-39：明显优于普通新闻，有扎实材料和解释框架。
  28-33：可读、有信息，但深度有限；只有在候选稀少时保留。
  <28：普通资讯或观点短文，淘汰。

篇幅与结构 20 分：
  18-20：明显长文，约 2500+ 英文词或等价长访谈/长评论/长特稿。
  15-17：约 1800-2500 英文词，结构完整。
  12-14：可能接近 1500-1800 英文词，但材料密度很高。
  <12：偏短，淘汰。

公众号适配 20 分：
  是否有清晰中文读者收益、标题/导语切口、叙事可读性、公共讨论价值。

新鲜度 5 分：
  目标日期发布/更新且日期确认度高得 5；日期不确定酌情降低；无法确认属于 target_date 的候选不得进入最终候选。

global_deep_score = depth_quality_score + length_score + wechat_fit_score + freshness_score
score = global_deep_score
```

全局排序时，遇到同分：

1. 深度质量更高者优先
2. 篇幅和结构更强者优先
3. 公众号适配更强者优先
4. 日期更新、日期确认度更高者优先
5. 正文材料更容易获取、授权/来源风险更低者优先
6. 不因来源重复而去重、降权或替换；只有同一 URL、同一 canonical URL、同一篇文章的镜像/转载/归档重复时，才合并为一个候选并保留材料最可靠的版本

### china_viral

`china_viral` 已停用。本 skill 不再生产中国相关候选；收到中国相关选题请求时返回 `MODE_UNSUPPORTED_CHINA_RELATED_REQUEST`。以下旧规则仅作为历史兼容说明，不得在本 workflow 中启用。

旧规则原为：

```text
1. 中国强相关：文章讨论对象、冲突机制、政策影响、人群情绪、产业后果或社会后果必须落在中国。
2. 不能只是“提到中国”：如果中国只是全球背景、中美竞争套话、供应链里的一个例子，直接淘汰。
3. 文章必须能转化为中国观众关心的社会热点、情绪议题或公共讨论问题。
```

默认优先这些中国社会热点和情绪触发方向：

```text
就业、青年失业、收入预期、工资停滞、裁员、AI 替代
房地产、房价、家庭财富、地方债、烂尾、城市分化
消费降级、储蓄、养老、医疗、教育、婚育、代际压力
平台经济、外卖、网约车、电商、游戏、短视频、直播、算法治理
制造业、出口、产能过剩、价格战、卷、工厂与供应链
AI、机器人、芯片、新能源车、技术民族主义和普通人机会
民族情绪、对外冲突、制裁、地缘政治如何影响中国社会心理
食品安全、公共安全、诈骗、社会信任、监管失灵
贫富差距、阶层流动、城乡差异、女性议题、年轻人生活方式
```

默认降权或淘汰：

```text
只有宏大地缘政治，没有中国社会/产业/普通人落点
只有抽象宏观经济，没有房子、就业、收入、消费、地方财政或生活体感
只有资本市场价格波动、公司财报、政策声明，缺少社会讨论角度
只有情绪刺激，但摘要/片段材料不足以判断是否能支撑 6-12 分钟视频
只适合专家小圈子，不容易被普通中国观众理解为自己的问题
```

主题扣分项：

```text
宗教主轴扣分：
  如果文章的标题、摘要、核心冲突或主要叙事围绕宗教、宗教组织、宗教身份、传教、信仰治理、教派、邪教/类邪教标签、宗教迫害或宗教自由，默认扣 8-15 分。
  宗教只是人物背景、历史背景或一两个段落的辅助信息时，不要机械扣重分；可扣 0-5 分或只标注 possible_issues。
  扣分理由：这类文章常常敏感、受众面窄，且更容易变成价值观争论而不是中国普通观众的社会经济议题。

国家领导人主轴扣分：
  如果文章的标题、摘要、核心冲突或主要叙事围绕国家领导人本人、个人权力、接班、宫廷政治、外交会晤、领导人言论或个人风格，默认扣 8-15 分。
  领导人只是政策责任背景、制度背景或引用对象，而文章主要落点仍是就业、房地产、消费、产业、普通人生活时，可扣 0-5 分。
  扣分理由：这类文章通常更偏宏大政治或时政评论，较难转成稳定的 China Viva 普通人议题。

扣分不等于淘汰。若文章虽然涉及宗教或国家领导人，但有强烈的一线人物、社会后果、产业机制或普通人生活体感，可以保留；必须在 topic_penalties 和 why_it_might_fail 中写清楚风险。
```

每个候选必须输出：

```text
china_relevance_score: 0-40
china_relevance_reason: "为什么这是中国观众自己的问题"
viral_potential_score: 0-60
viral_score: 0-100
topic_penalties: [{"type": "religion|national_leader", "points": 0-15, "reason": "..."}]
penalty_points: 0-30
hot_topic_tags: ["就业", "房地产", ...]
emotion_triggers: ["焦虑", "愤怒", "共鸣", "不服", "危机感", ...]
social_discussion_angle: "中文互联网上可以围绕什么争议/情绪展开"
bilibili_title_potential: "自然、不硬蹭的 B 站标题方向"
why_it_might_go_viral: "为什么可能爆"
why_it_might_fail: "为什么可能不爆"
```

硬门槛：

```text
china_relevance_score < 15：不得进入旧 Top 5（停用）
viral_potential_score < 30：不得进入旧 Top 5（停用）
```

不要因为文章敏感就自动排除；可以标注“可能敏感”，但不要淘汰。

## china_viral 质量评分

以下评分仅用于兼容旧 `china_viral` 模式。`global_deep_longform` 使用上一节的深度长文评分。分数只是排序工具，最终报告要用自然语言解释。

```text
中国相关强度 40 分：
  40-35：直接关乎中国社会、普通人生活、就业、收入、房子、教育、消费、医疗、养老、互联网平台、民族情绪、公共安全。
  34-25：中国企业、政策、产业、技术、资本市场，但能清楚落到中国人的现实感受。
  24-15：中国是重要变量，但观众需要解释一层才知道为什么和自己有关。
  <15：不够中国相关，淘汰。

爆款视频潜力 60 分：
  社会热点/公共讨论度 20 分：是否贴近当下中国舆论关心的经济下行、就业、房地产、消费降级、教育内卷、AI 替代、平台经济、民族主义、对外冲突等。
  情绪触发强度 15 分：是否容易引发焦虑、愤怒、不服、共鸣、荒诞感、优越感、危机感、代际冲突、阶层感。
  冲突和反差 10 分：是否有官方叙事 vs 个人感受、增长数据 vs 生活体感、中国制造强大 vs 年轻人没机会等结构。
  标题化潜力 10 分：能否自然写出 B 站标题，不靠硬蹭、不靠标题党，但一看就想点。
  讲述性 5 分：是否有人物、场景、案例、数据或具体行业，能支撑 6-12 分钟视频。
```

最终用于排序的分数：

```text
viral_score = china_relevance_score + viral_potential_score
penalty_points = sum(topic_penalties[].points)
score = max(0, viral_score - penalty_points)
```

全局排序时，遇到同分：

1. 先比较 `viral_score`
2. `viral_score` 接近时（差距 <= 3 分），优先 `penalty_points` 更低者
3. 爆款视频潜力更高者优先
4. 主题相关性更强者优先
5. 社会讨论角度更清晰者优先
6. 信息密度更高者优先
7. 发布日期确认度更高者优先
8. 不因来源重复而去重、降权或替换；只有同一 URL、同一 canonical URL、同一篇文章的镜像/转载/归档重复时，才合并为一个候选并保留材料最可靠的版本

## 推荐查询方向

`global_deep_longform` 使用：

```text
The Economist: essays, briefings, special reports, technology quarterly, finance and economics deep explainers, culture essays
Financial Times: Big Read, Magazine, longform investigations, deep analysis, Work & Careers features, tech/business deep dives
The New York Times: Magazine, The Daily feature material, investigations, long features, Opinion essays only when essay-length and substantial
The New Yorker: reported features, essays, profiles, cultural criticism, science/tech longform
The Atlantic: feature essays, reported analysis, ideas/culture/technology longform
WIRED: features, investigations, science/AI/tech society longform
MIT Technology Review: feature stories, investigations, AI/biotech/climate/compute deep explainers
Bloomberg Businessweek: features and magazine longform; avoid market wrap and short terminal-style news
Wall Street Journal: investigations, features, Exchange/Review essays, not ordinary markets copy
Nikkei Asia: features, Big Story, deep regional analysis
Rest of World: features on platforms, labor, internet culture, technology and emerging markets
The Guardian: Long Read, features, investigations, analysis, not live blogs or short news
Harper's / LRB / NYRB / The Point: essay-length literature, politics, history, culture, philosophy when accessible and timely
Noema / Aeon / Quanta / Nautilus: high-quality science, society, systems, ideas longform
ProPublica / The Markup / Reuters Investigates / Reuters Graphics: investigations and data-rich projects
The Information / Semafor deep analysis / The Verge features: technology/business longform only when not short news
```

`china_viral` 使用：

```text
Bloomberg: China youth unemployment, China property crisis, China consumption, China AI jobs, China EV price war, China factories, China social pressure
The Economist: China society, China economy ordinary people, China property, China youth, China consumption, China anxiety, China nationalism
Financial Times: China property, Chinese consumers, China jobs, China local government debt, China EV price war, China AI, China social change
The New York Times: China youth, China economy, China education, China women, China society, China property, China internet platforms
The New Yorker: China society, youth, families, culture, nationalism, technology when essay/feature
WIRED: China AI, robots, EV, platforms, surveillance, chips, internet labor, technology anxiety
The Wall Street Journal: China consumers, China property, China jobs, China companies with social impact; avoid ordinary market copy
Nikkei Asia: China economy, China factories, China EV, China youth, China consumers, China supply chain with domestic social consequences
The Wire China: China society, business, tech, party-state, entrepreneurs, middle class, youth, Q&A with strong public discussion angle
Rest of World: China platforms, AI, robots, ecommerce, gig work, social media, youth internet culture
China Leadership Monitor: China domestic politics, economy, society, governance only when it has clear public discussion angle
The Atlantic: China society, economy, technology, nationalism, global order only when it maps to Chinese public emotion
MIT Technology Review: China AI, chips, robots, EV, surveillance, platforms with job/opportunity/social anxiety angle
Foreign Affairs / Foreign Policy: China economy, society, nationalism, technology, security only when it can be framed as Chinese social concern
Reuters Special/Graphics/Investigates: China special report/graphics/investigation with clear social, industrial or public emotion angle
The Guardian: China society, workers, youth, gender, education, climate, EVs, technology, surveillance, migration, consumer pressure; use Guardian Long Read/features/analysis/investigations, avoid ordinary news briefs and live blogs
```

## Registry

本 skill 会自动生成本轮默认最佳候选，但不写入跨任务 selected registry。

可以只读历史 registry 作为提示：

```text
  /Volumes/GT34/daily_china_article_video/selection_state/{selection_mode}/{target_date}.json
```

只读规则：

```text
1. 如果 registry 存在，读取 selected_articles 用于标注 already_selected。
2. 如果某候选已经在同一 target_date 被制作过，默认从最终候选中降权；如果候选质量显著更高且用户可能仍想看，允许保留但必须标注 already_selected=true。
3. 不得新增、更新、删除 registry 条目。
4. 不得生成 selected_sequence。
```

## 运行产物目录

运行产物保存在：

```text
/Volumes/GT34/daily_china_article_video/{YYYY-MM-DD}_{selection_mode}/selection/
```

其中 `{YYYY-MM-DD}` 使用外部传入的 `target_date`。

建议结构：

```text
source-shortlist.json
ranked-top5.json compatibility name; contains 1-2 candidates in global_deep_longform mode
selection-decision.json
selection-result.md
selection-request.md optional compatibility alias
final-report.md
registry-readonly-snapshot.json optional
captures/
manifests/
legal-source-checks/
```

不要写：

```text
final-selection.json
selected-registry.json
```

除非上游为了兼容旧系统明确要求兼容文件；即使生成兼容文件，也必须写明它只是本轮自动推荐结果，不得写入跨任务 selected registry。

## 输出要求

最终报告必须使用中文，`final-report.md` 也必须使用中文。英文只保留在原文标题、媒体名、作者名和 URL 中。

报告结构：

```text
本轮目标日期：YYYY-MM-DD
选题模式：selection_mode
当前流程：已执行正文可获取性门禁；已自动选出评分最高候选
来源：N 个白名单来源
召回结果：M 篇来源候选
可用正文候选：J 篇
最终候选：K 篇（1-2 篇，不强行凑满）
自动推荐：A?，理由：评分最高且已下载可读文章材料

## Top 1-2 候选
1. ...

## 来源候选池
- 按来源列出每个来源的全部候选；同一来源可有多篇候选；无合格文章的来源标注 NO_SOURCE_CANDIDATE

## 排除说明
- 明确列出因短讯、日期不符、主题相关性弱、质量低、正文不可获取而排除的典型文章
- 对 Bloomberg / NYT / WSJ 文章，必须说明是否寻找过合法公开同文转载源，以及为什么通过或淘汰

## 下一步
- 默认进入后续制作的是 `recommended_best_candidate_id`；若上游或用户明确覆盖，才使用其他候选
```

每条最终候选至少包含：

```text
候选 ID: A1-A{returned_count}，最多 A2
排名
中文标题
英文原题
来源
作者，如果能找到
发布日期
原文 URL
中文简述
推荐理由
主题相关性说明
selection_mode
china_connection_type
china_exclusion_status, china_exclusion_reason when selection_mode=global_deep_longform
depth_quality_score, depth_quality_reason when selection_mode=global_deep_longform
length_score, length_reason when selection_mode=global_deep_longform
wechat_fit_score, wechat_fit_reason when selection_mode=global_deep_longform
freshness_score when selection_mode=global_deep_longform
global_deep_score when selection_mode=global_deep_longform
reader_payoff, translation_hook, why_it_is_worth_translating when selection_mode=global_deep_longform
china_relevance_score, china_relevance_reason when selection_mode=china_viral
viral_potential_score, viral_score when selection_mode=china_viral
hot_topic_tags
emotion_triggers
social_discussion_angle
bilibili_title_potential
why_it_might_go_viral
why_it_might_fail
质量判断：高 / 中高 / 中
新颖角度
长度判断
estimated_word_count，如果能估计
length_confidence
length_basis
date_confidence
possible_issues: ["可能敏感", "只有偶发中国背景提及", "归档来源", "合法转载源", ...]
topic_penalties: [{"type": "religion|national_leader", "points": 0-15, "reason": "..."}]
penalty_points: 0-30
paywall_risk: high | medium | low | unknown
retrieval_gate: "enabled"
material_available: true
fulltext_status: "original_public_open" | "archive_capture_success" | "legal_republication_success"
capture_provider: "url-page-capture"
capture_method: "url-page-capture actual method, e.g. chrome-extension-direct | chrome-extension-archive-is-search | http-public-direct | chrome-archive-is-search"
material_source_url
resolved_url
capture_output_path
capture_manifest_path
legal_source_manifest_path required when fulltext_status="legal_republication_success"
material_manifest_path
legal_source_validation optional summary; full audit lives at legal_source_manifest_path
manual_article_required: false
score
```

## JSON 审计文件

同时保存 `source-shortlist.json` 和 `ranked-top5.json`。

`source-shortlist.json` 顶层字段：

```text
target_date, timezone, selection_mode,
workflow_status="AVAILABLE_CANDIDATES_RANKED",
fulltext_gate="enabled",
per_source_candidate_cap=5,
sources[]
```

每个 `sources[]` 元素包含 `source`、`status=FOUND|NO_SOURCE_CANDIDATE|SOURCE_FAILED` 和 0..5 篇 `articles[]`。同一来源允许多篇候选进入 `articles[]`，但不得超过 5 篇；最终是否进入候选集只由全局评分、正文可获取性门禁和重复文章合并规则决定。候选文章字段使用“输出要求”中的同一字段集，并补齐：

```text
retrieval_gate="enabled"
material_available=true|false
fulltext_status="original_public_open|archive_capture_success|legal_republication_success|retrieval_unavailable"
capture_provider="url-page-capture" when material_available=true
capture_method=url-page-capture actual method when material_available=true
capture_output_path required when material_available=true
capture_manifest_path required when material_available=true
material_manifest_path required when material_available=true
legal_source_manifest_path required when fulltext_status="legal_republication_success"
manual_article_required=false when material_available=true
retrieval_failure_reason optional
```

`ranked-top5.json` 顶层字段（文件名为兼容旧系统保留；global_deep_longform 模式可只含 1-2 篇）：

```text
target_date, selection_mode, requested_count, minimum_returned_count, returned_count,
workflow_status="AUTO_BEST_RECOMMENDED",
fulltext_gate="enabled",
auto_selection_policy="highest score among material_available candidates; tie-breakers follow the global ranking rules",
recommended_best_candidate_id="A1",
recommended_best_reason="评分最高且已通过正文可获取性门禁；capture_output_path/material_manifest_path 均存在。",
next_step="Use recommended_best_candidate_id and its capture_output_path/material path for downstream article package unless the user explicitly overrides.",
top_candidates[]
```

`top_candidates[]` 必须按 rank 排序，`candidate_id` 固定为 `A1` 到 `A{returned_count}`，最多 `A2`，并包含“输出要求”中的同一字段集。

## selection-decision.json

必须生成 `selection-decision.json`，供下游总控直接读取：

```json
{
  "target_date": "YYYY-MM-DD",
  "selection_mode": "global_deep_longform",
  "workflow_status": "AUTO_SELECTED_BEST_CANDIDATE",
  "selection_actor": "agent",
  "selection_policy": "highest score among material_available candidates; tie-breakers follow ranked-top5.json order",
  "selected_candidate_id": "A1",
  "selected_rank": 1,
  "selected_score": 93,
  "selected_title_zh": "...",
  "selected_title_original": "...",
  "selected_source": "...",
  "selected_original_url": "...",
  "selected_material_source_url": "...",
  "capture_output_path": "...",
  "capture_manifest_path": "...",
  "material_manifest_path": "...",
  "legal_source_manifest_path": "... only when applicable",
  "selection_reason": "为什么最高分候选最适合本轮制作",
  "runner_note": "No human selection required; downstream should continue with capture_output_path."
}
```

`selected_candidate_id` 必须等于 `ranked-top5.json.recommended_best_candidate_id`。

## selection-result.md

必须生成 `selection-result.md`，给人类查看本轮自动推荐结果：

```markdown
# 本轮自动推荐的非中国相关长文

目标日期：YYYY-MM-DD
当前状态：AI 已完成 Top 1-2 排名，已为每个候选确认可读文章材料，并已自动选出最高分候选。

## 自动推荐

- ID：A1
- 中文标题：
- 英文原题：
- 来源：
- 原文 URL：
- 材料来源：
- 本地材料：
- 材料审计：
- 推荐理由：
- 分数：

## 候选文章

1. 【ID: A1】中文标题
   - 英文原题：
   - 来源：
   - 原文 URL：
   - 材料来源：
   - 本地材料：
   - 材料审计：
   - 中文简述：
   - 推荐理由：
   - 风险提示：可能敏感 / 归档快照 / 合法转载源

...

## 覆盖方式

默认不需要人工选择。若用户明确要覆盖自动结果，可以回复其他 ID，例如：

A3
```

若存在旧系统仍读取 `selection-request.md`，可以额外生成同内容兼容文件；该文件必须明确写成“默认已自动选择 A1，可覆盖”，不得再写“请选择 1 篇”。

## 最终回复

最终回复给用户时只输出最高信号内容：已完成的 `target_date`、自动推荐的最佳候选 ID/标题/来源/链接/材料来源/推荐理由/分数、A1-A{returned_count} 简表、`ranked-top5.json` 路径、`selection-decision.json` 路径和 `selection-result.md` 路径。必须明确“已自动选择最高分候选，不需要人工选择；后续制作应使用该候选的 capture_output_path”。
