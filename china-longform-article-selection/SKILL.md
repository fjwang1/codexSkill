---
name: china-longform-article-selection
description: "用于为中文公众号选择“解释世界现象”的英文深度长文；默认使用 world_explainer_longform 模式：面向中国读者解释世界上某个国家/地区发生了什么、为什么发生、影响了谁、今天为什么仍值得读。文章不要求 target_date 当天发布；target_date 是运行日期。优先社会科学解释力、国别锚点、制度/阶层/家庭/劳动/教育/城市/移民/社会信任等机制解释、人物现场和长期解释价值。中国相关仍是硬排除项。生产主文必须来自授权生产白名单或已确认授权来源；可用 discovery/background sources 发现选题和校验背景，但未经授权不得直接进入下游翻译发布。最终输出 1 到 2 篇可阅读、可进入后续制作的候选，并自动选出评分最高候选作为默认制作文章。"
---

# Deep Longform Article Selection

使用本 skill 为中文内容生产做“世界现象解释型英文深度长文候选 1-2 篇”筛选。

当前默认版本是**世界现象解释型长文 + 社会科学解释优先 + 常青价值允许 + 可用正文门禁 + 自动最佳候选版**：

```text
1. AI 以 target_date 作为本次运行日期，而不是文章发布日期硬门槛。
2. 候选可以来自最近 30 天的新文章、近 2 年的主题化解释文章、或 evergreen backlog/历史常青文章。
3. 选题必须回答：某个国家/地区发生了什么？为什么发生？影响了谁？为什么中国读者今天仍值得读？
4. 社会科学解释力是核心加分项：制度激励、阶层流动、教育竞争、家庭结构、劳动市场、城市治理、移民、犯罪、住房、性别、代际、宗教/身份、社会信任、国家能力、福利制度、消费心理等。
5. 候选召回分三层：授权生产白名单、discovery sources、background/check sources。只有授权生产白名单或已确认授权来源可以进入最终制作。
6. AI 先基于标题、摘要、metadata、搜索结果片段、公开可见首屏或部分正文做解释力/社科机制/中文读者收益初筛评分。
7. 对可能进入最终 1-2 篇候选的文章执行正文可获取性门禁，确认能得到可读文章材料。
8. 获取顺序固定为：原站公开全文 -> 真实 Chrome direct -> archive.is/archive.today/archive.ph/archive.md 真实 Chrome 镜像搜索 -> 合法公开同文转载源。
9. 如果某篇文章已成为候选、但公开原站/普通公开渠道拿不到完整正文，必须先执行 archive 镜像搜索审计，不能直接用“正文不可用”淘汰。
10. Bloomberg、New York Times、Wall Street Journal 归档路径默认视为不友好；原站不可读时仍必须做一次有审计记录的 archive 镜像尝试，但不要反复卡在 CAPTCHA；随后寻找合法公开同文转载源，找不到就淘汰。
11. 最终从所有可用候选中统一排序输出 1 到 2 篇；自动把评分最高候选设为 `recommended_best_candidate_id` / `best_candidate`，不等待人类选择。
```

不要在最终回复里粘贴第三方文章全文或长篇翻译。

## 选题模式

本 skill 默认使用世界现象解释型长文模式：

```text
selection_mode = world_explainer_longform
```

`world_explainer_longform` 选择“向中国读者解释世界上某个国家/地区发生了什么、为什么会发生”的英文深度好文。核心判断：

```text
1. 是否有明确国家/地区锚点。读者应能知道“这是哪个国家/地区的什么现象”。纯抽象思想文、纯全球趋势文、无国别锚点的人物传记默认降权。
2. 是否解释一个现象，而不只是报道一个事件。合格文章必须有制度、经济、阶层、技术、人口、气候、历史、文化或社会心理机制。
3. 是否有强社会科学解释力。优先解释制度激励、阶层流动、教育竞争、家庭结构、劳动市场、城市治理、移民、犯罪、住房、性别、代际、宗教/身份、社会信任、国家能力、福利制度、消费心理等。
4. 是否有足够材料：人物、现场、案例、数据、档案、调查、历史纵深或高质量解释框架。
5. 是否适合中文公众号：能让中国读者获得新知识、新框架或可迁移的社会理解，而不是只适合当地读者或专家小圈子。
6. 文章不要求 target_date 当天发布。旧文章、历史解释、过去事件回顾都可以入选，只要仍有长期解释价值，并能说明 `why_still_relevant`。
7. 中国相关是硬排除项。文章的主题、主要叙事、核心冲突、关键证据、主要人物/机构、政策影响、产业变量或读者收益不得围绕中国、中国企业、中国政府、中国社会、中国地区议题、华人身份政治、中美竞争、对华政策或中国供应链展开。只有偶发背景提及且不影响文章主旨时才可保留，并必须标注 `china_connection_type="incidental_background_only"`。
8. 不强行凑满 2 篇。宁可只返回 1 篇真正好文，也不要塞入短讯、低密度文章、中国相关文章、无国别机制解释或拿不到正文的文章。
```

模式判定：

```text
任何“深度好文”“长文”“高质量外刊”“公众号选题”“默认公众号选题”“解释世界现象”“世界上某个国家发生了什么”请求 -> world_explainer_longform
`global_deep_longform` 作为历史兼容 alias；除非用户明确要求旧模式，否则按 `world_explainer_longform` 解释并输出新字段。
任何“中国选题”“中国热点”“爆款”“流量”“China Viva”请求都不应由本 skill 满足；返回 `MODE_UNSUPPORTED_CHINA_RELATED_REQUEST`，不要自动回退到中国相关选题。
旧 china_viral、china_domestic 和 asia_china 已停用，不作为日常模式；不要自动回退。
```

## 输入参数

调用本 skill 时必须显式提供：

```text
target_date: YYYY-MM-DD；本模式下表示 run_date/运行日期，不是文章发布日期硬门槛
target_timezone: 默认 Asia/Shanghai，除非调用方明确指定其他时区
requested_count: 默认 2，但只是上限；最终返回 1 到 requested_count 篇，最多 2 篇，最少 1 篇可用高质量非中国相关候选
minimum_returned_count: 默认 1
selection_mode: 默认 world_explainer_longform；global_deep_longform 仅作历史 alias；中国相关模式已停用
preview_only: 当前默认 false；本 skill 必须自动给出最高分候选作为本轮默认答案
retrieval_gate: 默认 true；进入最终候选集前必须通过正文可获取性门禁
fresh_lookback_days: 默认 30
recent_lookback_years: 默认 2；仅用于主题化国家/现象查询，不做全来源全量回扫
evergreen_allowed: 默认 true
same_day_required: 默认 false
publication_date_required: 默认 false；能找到时必须记录，找不到不直接淘汰
max_candidate_pool: 默认 30
max_retrieval_gate_candidates: 默认 8
staleness_check_required: 默认 true
```

日期职责边界：

```text
1. 上游总控、自动化任务或直接用户请求负责决定 target_date。
2. 如果上游想跑“今天/昨天的自动任务”，必须先按目标时区计算出绝对日期，再把 target_date=YYYY-MM-DD 作为 run_date 传入本 skill。
3. 本 skill 只使用传入的 target_date 做运行目录、审计日期和新近文章窗口锚点；不得把它解释为文章必须当天发布。
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
5. world_explainer_longform 模式不要为了凑满 2 篇而降低篇幅/质量/国别机制解释门槛；如果只有 1 篇真正合格，就只返回 1 篇。
6. 对任何已经有原文 URL 的候选，只要 HTTP/public direct、源站公开页面、RSS/metadata、搜索片段或真实 Chrome direct 不能提供完整可读正文，就必须尝试 archive.is 系列镜像搜索；未完成 archive 尝试和审计前，不得写 `material_available=false`、`retrieval_unavailable`、`NO_SOURCE_CANDIDATE` 或“正文不可用”。
```

Unattended convergence rule:

```text
1. 一旦已经获得 requested_count 篇硬门槛通过、material_available=true 的 production_whitelist 候选，应停止继续拓展新的搜索来源，写出 source-shortlist.json / ranked-top5.json / selection-decision.json / selection-result.md。
2. 如果 requested_count=2 但 minimum_returned_count=1，且只有 1 篇硬门槛通过、material_available=true 的候选，而继续检索只是在寻找“可能更好”的第二篇，不得无限等待；写出单篇候选并在报告中说明未强行凑满。
3. 如果 selection/captures/ 已有可读正文文件但还没有 selection 决策文件，恢复执行时必须优先审计这些已有 capture，能通过硬门槛就收敛成候选，不能通过就写 selection-stall-report.json 说明缺口。
4. 每次 retrieval gate 尝试后必须更新 selection/progress.json，记录当前来源、候选 URL、material_available_candidate_count、最后产物路径和下一步。
5. 如果一个来源或候选连续遇到搜索阻塞、CAPTCHA、安全验证、网络失败或工具不可用，不得卡住整个 selection；记录 SOURCE_FAILED 或 retrieval_unavailable，继续检查下一候选。只有 material_available_candidate_count < minimum_returned_count 时，才允许最终以 SELECTION_STALLED_INSUFFICIENT_MATERIAL_CANDIDATES 停止。
6. “停止拓展新搜索”不等于可以跳过已记录候选的 retrieval 审计。凡是已经进入 `promising_not_final_or_not_fully_gated`、`ranked-top5.json`、`source-shortlist.json` 或报告正文的付费/受限候选，只要已有原文 URL 且原站不可公开完整读取，就必须先补做一次 bounded archive 镜像审计，或者明确写出 `archive_status="not_applicable_no_candidate_url"`。
7. 不得在报告中写“未触发 archive fallback”“已有两篇候选所以未跑 archive”来解释一个已有 URL 的付费/受限候选；正确写法是 `archive_attempted=true` 加实际失败类型，或 `archive_attempted=false` 加 `not_applicable_no_candidate_url`。
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
6. 对每个因原站/公开渠道不可读而触发 archive fallback 的候选，必须在 `selection/archive-checks/<candidate_id>.json` 写出审计；即使 archive 失败，也要记录 mirrors、snapshot candidates、CAPTCHA/security signals、失败原因和截图/manifest 路径（若有）。
7. 对付费/受限来源，如果只做到 source-level 搜索且没有发现任何具体候选 URL，必须显式记录 `archive_attempted=false`、`archive_status="not_applicable_no_candidate_url"`、`archive_failure_reason="No specific eligible article URL was discovered; archive fallback requires an original article URL."`，不要笼统写成 `SOURCE_FAILED` 或“paywall 限制”。
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
4. 对 The Economist、Financial Times、The New Yorker、WIRED 等普通 publisher article，以及固定来源白名单内其他已有原文 URL 的候选，HTTP 抓取遇到 Cloudflare、Just a moment、登录墙、订阅墙、薄正文、安全验证或正文不完整后，必须尝试真实 Chrome direct，再尝试真实 Chrome archive.is/archive.today/archive.ph/archive.md 搜索流程，除非用户明确要求跳过 archive。
5. 对 Bloomberg / New York Times / Wall Street Journal，仍遵守“不友好站点策略”：原站不可公开读取时必须做一次有审计记录的 archive 镜像尝试，但不把 archive.is 作为主要路径反复尝试；archive 不可用后优先搜索合法公开同文转载源。
6. 如果 archive fallback 被触发，最终 `source-shortlist.json`、`ranked-top5.json` 或失败审计中必须能看出 `archive_attempted=true`、`archive_status`、`archive_audit_path` 和 `archive_failure_reason`（失败时）。
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
archive_attempted = true | false
archive_status = "not_needed_original_public_open" | "success" | "failed_no_snapshot" | "failed_captcha_or_security" | "failed_snapshot_body_unusable" | "blocked_real_chrome_unavailable"
archive_audit_path = archive fallback 被触发时必填；未触发时可为 null
archive_failure_reason = archive fallback 失败时必填
```

最终候选硬门槛：

```text
material_available 必须为 true。
capture_output_path 或等价本地文章材料路径必须存在。
capture_manifest_path 必须存在。
material_manifest_path 必须存在。
legal_republication_success 还必须有 legal_source_manifest_path。
正文必须不是登录页、付费墙、验证码页、归档搜索页、评论区或导航页。
world_explainer_longform 模式还必须满足：不是短讯；长度/信息密度至少达到“中高”；有明确国家/地区锚点；有现象解释力和社会科学解释力；有长期解释价值；与中国无关。
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
2. 如果原站不可读，仍必须做一次 bounded archive 镜像尝试并写出 `selection/archive-checks/<candidate_id>.json`；不要把 archive.is 作为主要路径反复尝试，也不要要求用户解验证码。
3. archive 不可用后，必须搜索合法公开同文转载源。
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

## 来源体系

本 skill 使用三层来源体系，不再把“每天逐一检索 20 个来源当天新文”作为唯一发现方式。

```text
production_whitelist:
  已授权或默认可进入本工作流的生产来源。最终进入翻译、公众号草稿和发布的主文，必须来自这一层，或另有明确授权审计。

discovery_sources:
  选题发现来源。可用于发现国家/地区现象、社会科学解释角度和历史常青文章；未经授权不得直接进入最终制作。

background_check_sources:
  背景校验来源。用于确认国家背景、数据、时间线、后续变化和 staleness risk；不得作为主文来源。
```

生产白名单默认保留以下 20 个来源。world_explainer_longform 模式仍应优先覆盖这些来源，但检索目标是“可解释国家/地区现象的高质量候选”，不是“target_date 当天每源一篇”。最终候选必须与中国无关。

裁剪原则：

- 保留长期稳定产出深度报道、长特写、长评论、调查、思想长文、数据项目或科学/技术/社会深度解释的来源。
- 移除以短讯、政策简报、区域快讯、普通时政更新、单点市场消息或中国专题为主的来源。
- 不再要求每个来源当天最佳一篇；每次运行每个生产来源最多提交 1 个最强候选，避免同源刷屏。

授权状态：本固定来源白名单内的报纸/媒体，账号均已取得全文中文翻译与微信公众号草稿/发布授权。选题阶段仍需保留来源、原题、原文 URL、发布日期、材料来源和抓取审计信息，但不得因为缺少中文来源名映射而排除候选。

1. Bloomberg / Bloomberg Businessweek features and magazine longform only
2. The Economist essays, briefings, special reports, Technology Quarterly, finance/economics deep explainers, culture essays
3. Financial Times Big Read, Magazine, longform investigations, deep analysis, Work & Careers features, tech/business deep dives
4. The New York Times / The New York Times Magazine investigations, magazine features, long features, substantial essay-length Opinion only
5. The New Yorker reported features, essays, profiles, cultural criticism, science/tech longform
6. WIRED features, investigations, science/AI/tech society longform
7. The Wall Street Journal investigations, features, Exchange/Review essays, not ordinary markets copy
8. Rest of World features on platforms, labor, internet culture, technology and emerging markets
9. The Atlantic feature essays, reported analysis, ideas/culture/technology longform
10. MIT Technology Review feature stories, investigations, AI/biotech/climate/compute deep explainers
11. Foreign Affairs / Foreign Policy essay-length analysis only
12. Reuters Special Reports / Reuters Graphics / Reuters Investigates only
13. The Guardian / Guardian Long Read / features / investigations / analysis only
14. Harper's Magazine essay-length reporting, criticism, politics, culture
15. London Review of Books essay-length literature, politics, history, culture, philosophy
16. New York Review of Books essay-length literature, politics, history, culture, philosophy
17. Noema Magazine systems, technology, political economy, philosophy and global society longform
18. Aeon / Psyche ideas, social science, philosophy, psychology and science longform
19. Quanta Magazine high-quality science and mathematics features
20. ProPublica investigations and data-rich projects

Reuters 普通快讯、market wrap、live blog、timeline 默认不要；只有 special report、graphics、investigation、deep analysis 才能进入候选。

The Guardian 普通快讯、live blog、minute-by-minute、短新闻和图片稿默认不要；只有 Guardian Long Read、feature、investigation、analysis 等高质量长文才进入候选，且必须与中国无关。

以下来源从默认 daily deep-longform 检索集中移除，除非用户明确要求临时加入：Nikkei Asia、The Wire China、China Leadership Monitor、The Diplomat、East Asia Forum、Council on Foreign Relations、CSIS、The Point、Nautilus、The Markup、The Information、Semafor、The Verge、The Dispatch、Persuasion、American Affairs。

### Discovery Sources

以下来源可作为选题发现和背景提示，但默认不直接进入最终制作，除非另有授权或同文合法授权来源审计：

```text
Al Jazeera English longform / investigations
BBC InDepth / BBC Future / BBC Verify
Le Monde Diplomatique English
The Conversation
Christian Science Monitor
New Lines Magazine
The New Humanitarian
African Arguments
The Africa Report
Americas Quarterly
NACLA
Middle East Eye
Inside Climate News
Carbon Brief
Semafor explainers
NPR longform / Planet Money / Embedded transcript-style features
```

Discovery source 的作用：

```text
1. 发现“某国发生了什么、为什么发生”的可解释现象。
2. 生成主题化查询词，例如 Argentina inflation longform explained、South Korea education pressure feature。
3. 帮助判断哪些国家/地区和社会科学主题值得进入生产白名单检索。
4. 未授权 discovery 文章不得写入最终 top_candidates，除非 `authorization_basis` 和合法同文材料审计明确可用。
```

### Source Balance

为避免公众号长期变成美国/英国观察，world_explainer_longform 默认加以下来源多样性偏好：

```text
1. 非美国/英国国家锚点在同等质量下优先。
2. 最近 7 次选题中，如果美国题材已超过 3 次，新的美国题材需要明显更高解释力才能胜出。
3. 最终 2 篇候选尽量来自不同国家/地区、不同社会机制；除非同一国家的第二篇明显更强。
4. 来源多样性不能压过质量门槛；不要为了地区均衡塞入弱文。
```

## 日期窗口

本 skill 没有日期默认值；调用方必须传入绝对 `target_date`。

检索范围：

```text
target_date = 外部传入的 run_date / 审计日期
same_day_required = false
fresh_window = target_date 往前 30 天；用于发现近期解释型长文。
recent_window = target_date 往前 2 年；只在明确国家/现象主题查询时使用，不做全来源全量回扫。
evergreen_backlog = 无固定日期限制；使用本地候选库或少量主题化搜索补充，不能每天全网无限回看。
每个候选必须标注 date_scope、published_date、event_or_phenomenon_period、date_reason。
```

如果媒体只显示相对时间、源站时区或搜索结果日期不一致，可以保留候选；找不到发布日期也不直接淘汰，但必须标注：

```text
date_confidence: low | medium | high
date_reason: 为什么认为发布日期/更新日期可靠或不确定
```

候选池和最终候选优先选择解释力强、仍然相关的文章；日期确认度只是审计和 staleness risk 判断，不是硬淘汰条件。

旧文和历史事件文章必须额外判断：

```text
timeliness_requirement: none | low | medium | high
evergreen_value_score: 0-5
why_still_relevant: 为什么今天仍值得中国读者读
what_has_changed_since_publication: 发表后哪些关键事实可能变化
staleness_risk: low | medium | high
needs_update_check: true | false
```

## 统一候选池召回

按“生产来源覆盖 + 主题化发现 + 常青库”召回后再统一排序：

1. 每次运行先覆盖生产白名单来源，寻找 fresh_window 内的解释型长文；每个生产来源最多提交 1 篇最强候选。
2. 同时使用 6-10 个主题化查询，从 discovery sources 和公开搜索中发现国家/地区现象，但未经授权不得进入最终制作。
3. 读取本地 evergreen backlog（若存在），最多取 10 篇未制作或值得复评的常青候选参与排序。
4. 统一候选池默认最多 30 篇；超过时按国别锚点、社会科学解释力、中文读者收益和授权可制作性先裁剪。
5. 最多对前 8 篇执行正文可获取性门禁；不要对几十篇候选都抓全文。
6. 若某来源没有任何合格文章，返回 `NO_SOURCE_CANDIDATE`。不要为了凑来源数量放入短讯、低质文章、中国相关文章、无国别解释力文章或正文不可获取文章。
7. 最终候选必须来自授权生产白名单或通过合法同文授权审计；discovery-only 候选只能进入“发现但不可制作”列表。
8. 最终候选可以来自任意生产来源；来源多样性是加分/降权项，不是弱文通行证。

## 实时热点识别与加权

`world_explainer_longform` 不能只奖励常青解释力。若某个世界现象正在成为当日或近几日的公共议题，且候选文章仍满足长文、材料、非中国、授权和正文可获取门槛，应在排序中显著上浮。

热点判断不能靠模型直觉，必须用可审计信号。对进入最终排序前 8 名或可能进入最终 1-2 篇的候选，执行一个 bounded topical momentum check，并写入候选字段。允许使用 discovery/background sources 做热点验证，但未经授权的文章仍不能作为主文进入生产。

优先使用这些信号：

```text
1. 同日/近 72 小时多源覆盖：
   生产白名单、discovery sources、通讯社、官方机构、地方主流媒体或专业机构中，是否有多篇独立报道/解释/更新围绕同一现象。

2. 高权威实时触发：
   官方预警、极端天气/灾害/公共卫生/选举/政策/法院/事故/统计发布、WHO/UN/IPCC/气象机构/公共机构更新等，是否把该话题推入公共议程。

3. 更新频率与页面新鲜度：
   过去 24-72 小时是否持续出现新文章、live/update 页面、专题页、follow-up、数据图更新或专家解释。

4. 搜索结果密度：
   使用精确主题词 + 国家/地区 + target_date/近 24-72 小时时间词查询，搜索结果是否集中指向同一事件/现象，而不是只有候选文章孤立存在。

5. 平台/社媒趋势线索：
   Google Trends、X/Reddit/YouTube/主流平台热榜、媒体“most read/most viewed”、newsletter topic clustering 等公开可见信号可作为辅助证据；不能单独决定入选。

6. 公共服务或生活影响：
   话题是否正在影响医院、学校、交通、能源、住房、就业、金融市场、城市秩序、公共安全或政策议程。影响越具体，热点分越可靠。
```

热点证据必须记录：

```text
topical_momentum_score: 0-15
topical_momentum_confidence: "high | medium | low"
topical_momentum_window: "24h | 72h | 7d | none"
topical_momentum_evidence: [
  {
    "signal_type": "multi_source_coverage | official_alert | search_density | update_frequency | platform_trend | public_service_impact",
    "source": "...",
    "url": "...",
    "published_or_checked_at": "YYYY-MM-DD or ISO-8601 if available",
    "summary": "为什么证明该话题正在升温"
  }
]
topical_momentum_reason: "为什么这是当下热点，而不是普通常青题材"
topical_momentum_risk: "low | medium | high"
```

评分规则：

```text
0-3：无明显实时热点；只是常青题材或孤立文章。
4-7：有局部热度；同一现象近 72 小时有少量跟进或专业圈关注。
8-11：明确热点；多家可信媒体/机构近 72 小时持续覆盖，且影响普通人生活或政策议程。
12-15：强实时热点；同日或近 24 小时密集更新，有权威预警/官方数据/公共服务中断/大规模社会影响，并且中文读者无需本地背景也能理解其现实紧迫性。
```

硬约束：

- 热点加权不得覆盖基本质量门槛。短讯、薄文、中国相关、无国别锚点、无机制解释、未授权或拿不到正文的文章仍然淘汰。
- 热点加权不得奖励纯情绪刺激、灾难猎奇或平台噪声。必须有可迁移解释价值和足够材料。
- 对气候、公共卫生、战争、选举、法院、金融危机、城市灾害、事故和社会运动等高实时性主题，默认执行 topical momentum check；不要只用 `evergreen_value_score` 低分压制。
- 如果两个候选基础解释质量接近，`topical_momentum_score` 高且证据置信度高者优先；这条优先级高于来源多样性和非美国/英国偏好。

理想执行方式：

1. 并发检索生产白名单来源，不要串行一个媒体做完再做下一个。
2. 如果可用，启动 source scout / theme scout 子 agent；source scout 负责生产来源，theme scout 负责国家/现象主题查询。
3. 每个 source scout 最多返回该来源 1 篇最强候选或明确 `NO_SOURCE_CANDIDATE` / `SOURCE_FAILED`。
4. 每个 theme scout 必须区分 `production_candidate`、`discovery_only_candidate` 和 `background_only_reference`。
5. scout 必须记录被排除的低质、短讯、中国相关、无国别锚点、无社会机制解释、过时且无常青价值、正文明显不可获取文章。
6. theme scout 还必须为可能进入最终排序的候选执行 topical momentum check，记录当日/近 72 小时多源覆盖、官方/机构信号、搜索密度、更新频率和公共服务影响。
7. 合并候选后按统一评分规则排序，形成全局最多 2 篇候选；不强行凑满。

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

### world_explainer_longform

文章必须与中国无关，并且必须能向中国读者解释一个国家/地区的现实或历史现象。非中国题材只有深、长、好还不够；它必须回答“发生了什么、为什么发生、影响了谁、今天为什么仍值得读”。

中国相关硬排除：

```text
以下任一情况为 `china_exclusion_status="EXCLUDE"`，不得进入 retrieval gate 或最终候选：
- 标题、摘要、核心论题、主要叙事、主要人物/机构、政策影响或产业变量围绕中国、中国地区议题、中国企业、中国政府、中国社会、华人身份政治、中美竞争、对华政策、中国供应链展开。
- 中国不是唯一对象，但文章的解释框架或读者收益需要中国变量才能成立。
- 文章主要价值在于帮助中文读者理解中国处境、对华政策、地缘政治中的中国角色，或中国社会/产业/普通人经验。

只有以下情况可保留，并必须标注 `china_connection_type="incidental_background_only"`：
- 中国只是列表式背景、历史比较、全球市场中的非关键例子，删除该提及也不改变文章主旨。
```

默认优先这些世界现象解释方向：

```text
某国制度激励如何塑造资源分配、市场行为或公共服务
某国阶层流动、教育竞争、住房、医疗、家庭结构、代际关系、性别关系
某国劳动市场、移民、城市治理、犯罪、福利制度、社会信任、国家能力
某国气候、能源、水资源、农业、公共卫生问题背后的制度和社会后果
某国技术、平台、AI、互联网、金融创新如何改变社会关系、就业和权力结构
某国战争、冲突、民族/宗教/身份政治如何影响普通人和国家能力
某国历史事件、历史制度或长期文化结构如何解释今天的现实
跨国现象也可以入选，但必须有清楚的 country/region anchor 和可读的比较框架
```

默认淘汰或强降权：

```text
普通快讯、新闻简报、市场短讯、财报单点、政策声明复述
只有观点姿态，没有事实材料、采访、数据、历史纵深或解释框架
只适合非常窄的专业圈，翻译后中文读者获得感弱
标题吸引但正文可能是 newsletter 摘要、链接聚合或短评
无明确国家/地区锚点的抽象思想文、纯文化评论、纯人物传记
只有宏大地缘政治或政策圈话语，没有社会机制、人物现场或普通人后果
只有科技产品/科学突破，没有落到某个国家/社会后果
旧文章如果只是过时新闻、结论已被后续事实推翻、或不能说明今天为什么仍值得读，淘汰
```

每个候选必须输出：

```text
primary_country: "国家/地区锚点；跨国比较时列出主锚点"
country_or_region_anchor_score: 0-15
world_phenomenon: "这篇文章解释的世界现象"
world_phenomenon_importance_score: 0-15
what_happened: "发生了什么"
why_it_happened: "为什么发生"
affected_groups: ["受影响的人群/阶层/机构"]
social_science_explainer_score: 0-25
social_science_lens: ["制度激励", "阶层流动", "教育竞争", "劳动市场", "城市治理", ...]
institutional_or_social_mechanism: "制度/社会/经济/文化机制"
behavioral_or_class_dynamic: "行为、阶层、家庭、代际、身份或群体动态"
evidence_scene_data_score: 0-15
evidence_scene_data_reason: "人物、现场、案例、数据、档案、历史纵深为什么足够"
chinese_reader_payoff_score: 0-15
why_chinese_readers_should_care: "中国读者为什么值得读"
reader_takeaway_about_how_society_works: "读完能理解社会如何运转的什么机制"
narrative_wechat_fit_score: 0-10
explainer_hook: "适合公众号标题/导语的解释型切入点"
evergreen_value_score: 0-5
topical_momentum_score: 0-15
topical_momentum_confidence: "high | medium | low"
topical_momentum_window: "24h | 72h | 7d | none"
topical_momentum_evidence: [{"signal_type": "...", "source": "...", "url": "...", "published_or_checked_at": "...", "summary": "..."}]
topical_momentum_reason: "为什么这是当下热点，而不是普通常青题材"
topical_momentum_risk: "low | medium | high"
why_still_relevant: "为什么今天仍值得读"
what_has_changed_since_publication: "发表后可能变化的关键事实"
staleness_risk: "low | medium | high"
needs_update_check: true | false
china_exclusion_status: "PASS | EXCLUDE"
china_connection_type: "none | incidental_background_only | china_related_excluded"
china_exclusion_reason: "为什么判断与中国无关，或为什么因中国相关被排除"
world_explainer_score: 0-100
ranking_score_formula: "min(100, round(0.85 * world_explainer_score + topical_momentum_score))"
score: 0-100
quality_level: "高|中高|中|淘汰"
topic_tags: [...]
why_it_is_worth_translating: "为什么值得翻成中文"
why_it_might_fail: "为什么可能不适合"
```

硬门槛：

```text
china_exclusion_status = "EXCLUDE"：不得进入最终候选
country_or_region_anchor_score < 9：不得进入最终候选，除非是非常强的跨国比较现象
world_phenomenon_importance_score < 9：不得进入最终候选
social_science_explainer_score < 15：不得进入最终候选
evidence_scene_data_score < 8：不得进入最终候选
chinese_reader_payoff_score < 9：不得进入最终候选
quality_level = "淘汰"：不得进入最终候选
```

评分：

```text
国家/地区锚点 15 分：
  13-15：具体国家/地区、具体制度或社会场景非常清楚。
  9-12：有明确国别锚点，但局部偏全球化或抽象。
  <9：国别锚点弱，通常淘汰。

世界现象重要性 15 分：
  13-15：解释一个有公共意义、可迁移理解价值的社会/制度现象。
  9-12：现象清楚但影响面或解释面较窄。
  <9：更像单点事件或小圈子话题。

社会科学解释力 25 分：
  22-25：清楚解释制度激励、阶层、家庭、教育、劳动、城市、移民、身份、社会信任、国家能力等机制。
  18-21：有较强机制解释，但部分仍偏叙事或观点。
  15-17：有基本机制，但解释力有限；候选稀少时可保留。
  <15：缺少社会科学解释力，淘汰。

人物/现场/数据材料 15 分：
  13-15：有原创采访、人物现场、数据/档案/历史纵深或调查材料。
  8-12：材料够用但不算强。
  <8：材料薄，淘汰。

中国读者理解收益 15 分：
  13-15：明显补足中国读者世界知识盲区，能形成可迁移理解框架。
  9-12：有阅读价值，但需要较多背景解释。
  <9：受众窄或获得感弱，淘汰。

公众号叙事适配 10 分：
  是否有好标题/导语切口、章节结构、叙事可读性和普通读者进入点。

长期解释价值 5 分：
  不奖励“新”，奖励不过期的解释力。旧文若仍能解释今天世界，可得高分；实时变动强且需大幅更新的文章低分。

实时热点动量 15 分：
  12-15：强实时热点；同日或近 24 小时密集更新，有权威预警/官方数据/公共服务中断/大规模社会影响，并且文章能解释为什么发生、影响谁、为何重要。
  8-11：明确热点；近 72 小时多家可信来源持续覆盖，有现实影响或政策议程，但热度强度略低或证据较分散。
  4-7：局部热度；有少量跟进或专业圈关注，但普通读者感知未必强。
  0-3：无明显实时热点；主要是常青解释题材。
  说明：该项不进入 `world_explainer_score`，而是进入最终 `score`，避免把实时热度误写成文章本身的长期解释质量。

world_explainer_score =
  country_or_region_anchor_score
  + world_phenomenon_importance_score
  + social_science_explainer_score
  + evidence_scene_data_score
  + chinese_reader_payoff_score
  + narrative_wechat_fit_score
  + evergreen_value_score

score = min(100, round(0.85 * world_explainer_score + topical_momentum_score))

解释：

- `world_explainer_score` 仍是基础质量分，满分 100。
- `score` 是最终排序分，满分 100。它把基础质量压缩到 85% 后加入最高 15 分热点动量。
- 这样高质量常青文章不会被完全淘汰，但同等质量下，正在发生、正在被多源覆盖、正在影响公共生活的题材会明显上浮。
- 示例：基础质量 91、热点动量 15 的欧洲高温文章，最终 score=92；基础质量 94、热点动量 4 的常青城市文章，最终 score=84。前者应优先进入主文。
```

全局排序时，遇到同分：

1. `topical_momentum_score` 更高且 `topical_momentum_confidence` 更高者优先
2. 社会科学解释力更高者优先
3. 中国读者理解收益更高者优先
4. 国家/地区锚点更清楚者优先
5. 非美国/英国题材在同等质量下优先
6. 人物、现场、数据材料更强者优先
7. 长期解释价值更强、过时风险更低者优先
8. 正文材料更容易获取、授权/来源风险更低者优先
9. 不因来源重复而去重、降权或替换；只有同一 URL、同一 canonical URL、同一篇文章的镜像/转载/归档重复时，才合并为一个候选并保留材料最可靠的版本

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

以下评分仅用于兼容旧 `china_viral` 模式。`world_explainer_longform` 使用上一节的世界现象解释评分。分数只是排序工具，最终报告要用自然语言解释。

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

`world_explainer_longform` 使用：

```text
按国家/地区 + 社会现象 + longform/explained/feature/investigation 查询，而不是按昨天日期查询。
示例：
  Argentina inflation longform explained
  South Korea education pressure feature
  France banlieues long read
  Japan rural decline feature
  Mexico drug war state capacity investigation
  India exam coaching industry longform
  Germany energy transition social consequences
  Nigeria fintech informal economy feature
  Brazil evangelical politics social change longform
  Spain housing crisis young people feature

生产白名单检索提示：
  The Economist: country explainers, briefings, special reports, social/economic institutions, avoid pure market notes
  Financial Times: Big Read, Magazine, country economy/society/business systems, avoid ordinary markets copy
  Reuters Special Reports / Graphics / Investigates: country-level data and investigation
  The Guardian: Long Read, investigations, features, social issues outside ordinary news
  Rest of World: platforms, labor, technology and emerging-market society
  Bloomberg Businessweek: business/institution/social mechanism stories, not terminal-style news
  Foreign Affairs / Foreign Policy: only when it explains state capacity, society, institutions, or historical mechanisms; avoid policy-circle reactions
  ProPublica: US institutional/social mechanisms, but avoid overselecting US unless unusually strong
  The Atlantic / New Yorker / NYT Magazine: strong reported features, but control US cultural overrepresentation
  WIRED / MIT Technology Review: only when technology clearly changes a country/society, labor, institutions, or everyday life
  Aeon / Psyche / Noema / LRB / NYRB / Harper's: use when the article has a clear country/social phenomenon anchor; otherwise downgrade as abstract thought/culture
  Quanta: use only when science connects to a country, institution, education, social consequence, or unusually broad explanatory story
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
ranked-top5.json compatibility name; contains 1-2 candidates in world_explainer_longform mode
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
来源：N 个生产白名单来源，另含 discovery/background sources 时单独列出
召回结果：M 篇候选（production/discovery/background 分层统计）
可用正文候选：J 篇
最终候选：K 篇（1-2 篇，不强行凑满）
自动推荐：A?，理由：评分最高且已下载可读文章材料

## Top 1-2 候选
1. ...

## 来源候选池
- 必须列出生产白名单来源，不能只列有结果的来源
- 每个生产来源最多 1 篇本轮最强候选；无合格文章的来源标注 NO_SOURCE_CANDIDATE
- discovery/background sources 单独列为“发现但不可直接制作/背景校验”
- 每个来源都要写明 `source_search_status`、`best_candidate_selection_reason` 或 `no_candidate_reason`

## 排除说明
- 明确列出因短讯、中国相关、无国家锚点、无社会科学解释力、过时且无常青价值、授权不可制作、正文不可获取而排除的典型文章
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
世界现象说明
selection_mode
china_connection_type
china_exclusion_status, china_exclusion_reason when selection_mode=world_explainer_longform
primary_country
country_or_region_anchor_score
world_phenomenon
world_phenomenon_importance_score
what_happened
why_it_happened
affected_groups
social_science_explainer_score
social_science_lens
institutional_or_social_mechanism
behavioral_or_class_dynamic
evidence_scene_data_score, evidence_scene_data_reason
chinese_reader_payoff_score
why_chinese_readers_should_care
reader_takeaway_about_how_society_works
narrative_wechat_fit_score
explainer_hook
evergreen_value_score
topical_momentum_score
topical_momentum_confidence
topical_momentum_window
topical_momentum_evidence
topical_momentum_reason
topical_momentum_risk
event_or_phenomenon_period
timeliness_requirement
why_still_relevant
what_has_changed_since_publication
staleness_risk
needs_update_check
world_explainer_score
ranking_score_formula
why_it_is_worth_translating when selection_mode=world_explainer_longform
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
date_scope
date_reason
possible_issues: ["可能敏感", "只有偶发中国背景提及", "归档来源", "合法转载源", ...]
topic_penalties: [{"type": "religion|national_leader", "points": 0-15, "reason": "..."}]
penalty_points: 0-30
paywall_risk: high | medium | low | unknown
source_layer: "production_whitelist | discovery_only | background_check"
authorization_basis
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
archive_attempted
archive_status
archive_audit_path required when archive_attempted=true
archive_failure_reason required when archive_attempted=true and archive_status!="success"
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
production_source_count=20,
per_source_candidate_cap=1,
source_coverage_status="PASS | PARTIAL_WITH_DISCOVERY_BACKFILL",
discovery_sources_used[],
background_check_sources_used[],
sources[]
```

每个 `sources[]` 元素包含 `source`、`source_layer`、`status=FOUND|NO_SOURCE_CANDIDATE|SOURCE_FAILED` 和 0..1 篇 `articles[]`。`sources[]` 应覆盖全部 20 个生产白名单来源；缺任何生产来源都应标注 `SOURCE_COVERAGE_PARTIAL`，但不因某个来源当天无新文而失败。同一来源不得提交多篇候选；如果同源有多篇可选文章，只保留本轮最强一篇，其余写入 `excluded_same_source[]` 或 final-report 排除说明。候选文章字段使用“输出要求”中的同一字段集，并补齐：

```text
source_search_status="FOUND|NO_SOURCE_CANDIDATE|SOURCE_FAILED"
best_candidate_selection_reason required when status="FOUND"
no_candidate_reason required when status="NO_SOURCE_CANDIDATE"
source_failure_reason required when status="SOURCE_FAILED"
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
archive_attempted=true|false
archive_status="not_needed_original_public_open|success|failed_no_snapshot|failed_captcha_or_security|failed_snapshot_body_unusable|blocked_real_chrome_unavailable"
archive_audit_path required when archive_attempted=true
archive_failure_reason required when archive_attempted=true and archive_status!="success"
```

`ranked-top5.json` 顶层字段（文件名为兼容旧系统保留；world_explainer_longform 模式可只含 1-2 篇）：

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
  "selection_mode": "world_explainer_longform",
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
  "selected_primary_country": "...",
  "selected_world_phenomenon": "...",
  "selected_social_science_lens": ["..."],
  "selected_topical_momentum_score": 13,
  "selected_topical_momentum_confidence": "high",
  "selected_topical_momentum_reason": "...",
  "selected_why_still_relevant": "...",
  "selected_material_source_url": "...",
  "capture_output_path": "...",
  "capture_manifest_path": "...",
  "material_manifest_path": "...",
  "archive_attempted": false,
  "archive_status": "not_needed_original_public_open",
  "archive_audit_path": null,
  "archive_failure_reason": null,
  "legal_source_manifest_path": "... only when applicable",
  "selection_reason": "为什么最高分候选最适合本轮制作",
  "runner_note": "No human selection required; downstream should continue with capture_output_path."
}
```

`selected_candidate_id` 必须等于 `ranked-top5.json.recommended_best_candidate_id`。

## selection-result.md

必须生成 `selection-result.md`，给人类查看本轮自动推荐结果：

```markdown
# 本轮自动推荐的世界现象解释型长文

目标日期：YYYY-MM-DD
当前状态：AI 已完成 Top 1-2 排名，已为每个候选确认可读文章材料，并已自动选出最高分候选。

## 自动推荐

- ID：A1
- 中文标题：
- 英文原题：
- 来源：
- 国家/地区锚点：
- 解释的世界现象：
- 社会科学镜头：
- 实时热点动量：
- 热点证据：
- 为什么今天仍值得读：
- 原文 URL：
- 材料来源：
- 本地材料：
- 材料审计：
- Archive 尝试：not_needed_original_public_open / success / failed_...
- Archive 审计：
- 推荐理由：
- 分数：

## 候选文章

1. 【ID: A1】中文标题
   - 英文原题：
   - 来源：
   - 国家/地区锚点：
   - 解释的世界现象：
   - 社会科学镜头：
   - 实时热点动量：
   - 热点证据：
   - 为什么今天仍值得读：
   - 原文 URL：
   - 材料来源：
   - 本地材料：
   - 材料审计：
   - Archive 尝试：
   - Archive 审计：
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
