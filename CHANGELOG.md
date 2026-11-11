# Changelog

## 0.4.5 — 2026-11-11

- **法学长文本章节结构修复**：`## 第N节` 不再被误判为 chapter 边界，节标题留在所属章内。
- **单标题不回退关键词**：一章只有一个真实标题时不再退化为关键词泛词；“一般规定”等通用标题自动加章名前缀（如“法人·一般规定”）。
- **真实法学 draft 复核**：结构化《民法典》总则编 10 章 21 节，生成 21 个可读 KPs、89 个待生成题位、42 个占位符；精确页引用 21/21（100%）。真实模型 fill 仍未完成。
- 回归：75 tests。

## 0.4.4 — 2026-11-10

- **真实材料的引用页码修复**：引用校验现在在同文件所有章节里定位页码，不再被“第一章在前、后面章节页码更大”的切分方式误判；精确页未命中时单独报告“同文件可检索”，通过线仍按精确页 ≥90%。
- **跨页引文截断**：`collect_citations` 按 `【第N页】` 截取引文，避免一句跨页导致精确页码校验失败。
- **章节标题噪声过滤**：拒绝 `第2页`、`HX`、`xF` 等 OCR 噪声标题；标题不可用时回退 PDF 文件名，多个片段加序号，避免主册出现无意义标题。
- **真实材料复核**：math/circuits/law v2 draft 的精确页引用分别为 48/48、68/68、38/38（100%），同文件可检索 100%；真实模型 fill 仍未完成，答案/rubric 覆盖仍为 0。
- 回归：72 tests（新增/调整引用与标题断言）。

## 0.4.3 — 2026-11-10

- **真实 PDF 文本清洗**：pypdf 文本层可能含孤立 UTF-16 surrogate 和 XML 控制字符，导致 state JSON 写入失败或 DOCX 报 `All strings must be XML compatible`。`ingest._clean_text` 现在同时剔除孤立 surrogate 与 C0 控制字符（保留 `\t\n\r`）。
- **DOCX 兜底**：`docx_writer.markdown_to_docx` 在渲染前清洗 XML 非法字符，真实课件/速记册不再因隐藏控制字符中断。
- 回归：71 tests；新增 surrogate/控制字符与 DOCX 清洗断言。

## 0.4.2 — 2026-11-10

- **OMML 公式不丢字**：DOCX/PPTX 提取时把 `m:t` 数学运行文本作为线性公式追加到正文（如 `x^2 + 1`），表格单元格同样处理；不声称已转为可编辑公式。
- 回归：70 tests；新增 OMML 提取断言。

## 0.4.1 — 2026-11-10

- **每日一条命令**：新增 `day`，一次输出进度、今日学习包、下一步；`--json` 只输出今日包 JSON。
- **实际用时**：attempts 新增 `actualSeconds`，`report` 优先读取；保留 `timeSec` 兼容旧 state。
- 回归：70 tests；DOCX/图片/surface 不变。

## 0.4.0 — 2026-11-10

按 `review-sprint-改进建议.md` 修计划闭环、语义质检、输入保真与评测；接口仍按 0.x 处理：

- **计划闭环**：slots 有稳定 `slotId`（`D01-S02`）；每个无题 slot 生成 `generate:<slotId>` 任务；`fill --apply` 写回生成题（`modelGenerated`、solution/rubric/answer）并重排绑定；`audit` 把 `needsGeneration>0` 当硬门禁。
- **下一步**：新增 `next`（只给一个动作/命令/理由）、`sync`（重排+重渲染+质检）、`catch-up`（落后天数）；`report` 按错因聚合最近 N 天；`progress` 不再固定说 today。
- **诊断卷**：`quiz --diagnostic` 每种题型抽 1 题，最多 20 题；`day` 一次给出进度、今日学习包和下一步。
- **单题补录**：`add-question --source model --slot ... --solution ... --rubric ...`，写 `modelGenerated/answerSource/solutionSource/rubricSource` 并自动重渲染五册。
- **语义质检**：`fill_tasks` 增加 rubric；答案册输出逐项评分点；`audit` 增加 `solutionCoverage/rubricCoverage/needsGeneration`，检查最短长度、步骤数、禁用“略/自行补充/同上/见教材”。
- **引用回查**：五册写 `〔原文：文件 第 N 页〕` 和 `citations.json`；`audit --citations` 按页码/归一化子串/相似度抽样，命中率 <90% 失败；模型生成题无教材来源，不参与引用统计。
- **图/公式进册**：PPTX `shape.image`、DOCX `inline_shapes`、PDF 页面图抽取到 `assets/`，按章节/知识点关联，主册 `![]()`，DOCX `add_picture`；新增 `figure --file --page` 用 pypdfium2/PyMuPDF 渲染单页。
- **DOCX**：支持行内粗体/斜体/代码/图片、页脚页码；`**P1-Q1**` 不再带星号；TOC 仍需 F9。
- **安全**：新增 `SECURITY.md`；材料用 `<<<MATERIAL ... MATERIAL>>>` 边界，明确不可信输入；模型题有来源标记。
- **评测**：新增 `eval/run_eval.py` 与 `eval/README.md`，测量占位符、待生成、计划可执行率、答案/解析/评分点覆盖、引用命中、图片进册、题号一致；不伪造真实课/弱模型结果。
- **CI**：Python 3.10/3.11/3.12/3.13 × Windows/Ubuntu；ruff 改为 `E9,F`；coverage 门槛 50%；新增 `check_build.py` 替代 `|| test $? -eq 1` 假绿，Windows 构建并上传五册。
- **测试**：70 项；新增 DOCX、图片、surface、generate/next/sync/add-question/citation 断言。
- **文档**：SKILL/README/quality-gates/state-schema 更新；FSRS 明确标为“简化式，非 FSRS-6 官方实现”。

## 0.3.0 — 2026-11-04

按修改意见修复；版本回到 0.x，接口未承诺稳定：

- **不再清空进度**：`build/init` 遇到已有 state 默认拒绝；`--force` 先备份 `study_state.<时间>.bak.json`；新增 `--refresh-materials` 只重解析材料，保留 attempts/错题/掌握度/FSRS。
- **五册给模型留位置**：需要讲解/口诀/解析/题型套路/题目映射处输出 `<!-- MODEL:... -->`；新增 `fill --tasks` 清单和 `fill --apply` 回填，回填后重渲染。占位符 >0 时 audit 必须失败。
- **有效质检**：新增答案覆盖率、kp 映射率、未映射题数、占位符数、pending 冲突等指标，不再只靠“同一题库渲染所以题号必然一致”。
- **同名材料不再覆盖**：复制时加来源短哈希前缀。
- **单 Session**：build 只解析一次、量化/排期一次，写盘后同一 Session 渲染和 audit。
- **依赖与格式**：允许 `--format md`；DOCX 缺失时降级为只出 Markdown 并警告；PDF 无 pypdf 时标 needs_ocr 不中断；build 前自动 doctor；依赖加版本上限。
- **量化可信度**：新增往年题→知识点覆盖率与可达分区间；L1–L4 时间系数移入画像 `levelFactors`；无依据的 `_note` 统一 `heuristic`；删除会覆盖用户修改的画像生成器，自定义画像放 `references/subjects/custom/`。
- **未映射题**：build 输出 `fill_tasks.json` 的 `kpMap` 任务，fill 后进入 F/P 统计。
- **JSON/退出码**：所有子命令支持 `--json`；0/1/2/3 约定；build 缺字段输出 `needsInput`。
- **SKILL.md**：阶段 A（build+fill）/阶段 B（status→today→answer→done）；明确 references 入口；平台无关命令；description 只写触发场景。
- **安装**：新增只拷贝 skill 本体的 `install-skill.ps1/.sh`。
- **CI**：Python 3.10/3.11/3.12；ruff；examples 完整 build 并上传 artifact。
- 测试：新增 refresh 保留 attempts、fill、占位符、同名材料、JSON 等。

## 1.0.0 — 2026-11-04（内部预发布，已撤回）

多科目 / 用户定天数 / 目标分量化 / 五册输出；因接口尚未稳定，版本号回到 0.3.0。

- **科目画像**：新增 `references/subjects/*.json` 13 个（12 类 + general）；题型、单题分钟、判分方式、`dailyMix`、`phaseRatio`、`reviewIntervals`、`masteryThresholds`、`safetyFactor`、`checkers`、B 站关键词全部数据化；每个数值带 `_note`。
- **科目识别**：`init/build` 先按材料打分；置信度 <0.6 返回候选并要求用户 `--subject` 确认；`--domain` 保留为别名。
- **N 天**：`--days` 由用户输入；`N≤3` 急救、4–7 压缩、8–30 标准、>30 长线；阶段天数用最大余数法保证总和=N；`set --days N` 只重排未来，保留已完成与已做过的题。
- **负载**：先算总任务量 W/日均/预算/超预算，再按画像 `dailyMix` + `kindMinutes` 反推题量；每日与 `dailyMinutes` 偏差 >15% 会移动题量/复习并写 `reviewOverflow`，`audit` 拦截。
- **目标分量化**：新增 `quantify.py`；F/P/失分率/近年×1.2；L0–L4 掌握度；按“期望分/分钟”贪心到 `目标×safetyFactor`；输出 60/70/80/90/95 五档矩阵、可达分、缺口、放弃清单、每日题量。
- **掌握度回写**：`answer` 更新 `mastery.currentLevel`；L4 要求 3 个不同日子答对；FSRS/D/错题关闭规则保留。
- **build**：新增一条命令：解析 → 科目 → 量化 → N 天排期 → 五册 MD+DOCX → audit；缺 `--target/--days` 非零退出并列出待问字段；每步写 `output/_build/*.json`。
- **五册**：01 计划（矩阵+按天表）、02 主册、03 答案册、04 速记手册、05 刷题宝典；02/03/05 题号一一对应，`audit` 缺一题/多一题都拦截；DOCX 依赖缺失时报错并给安装命令。
- **校验器**：按画像 `checkers` 开放；新增 `matrix`/`determinant` 数学校验；`calc` 支持。
- **状态**：schema 升 `@3`，新增 `subject / subjectConfidence / subjectProfile / days / mastery / quantification / build`；旧 `@1/@2` 自动迁移。
- **测试**：66 项；新增画像、科目切换/识别、N=1/3/5/7/10/14/20/30/45、60 vs 90 单调、容量放弃、旧状态迁移、math/law build 5×2 与三册题号一致；原 46 项全部保留。

## 0.2.0 — 2026-11-04

审查意见落地（P0/P1/P2 的一部分）：

- **答案比对**：按 `kind` 取主字段，支持 `0xFB`/`FB`/`251`/8 位二进制、flags 部分匹配、choice/numeric/exact。
- **冲突处理**：官方与重算不一致先标 `pending`，新增 `resolve-conflict --use official|recomputed`；`audit` 只拦 pending。
- **排期**：`N = 考试日 − 开始日`，考试当天不再排学习任务；`total<=0` 报错。
- **错题**：答错刷新未解决错题；连续两个不同日子答对才关闭。
- **进度**：`find_day` 按日期定位；新增 `done --day N`；重建保留已完成日与已做过的题。
- **复习日程**：只保留 FSRS `due` 一个来源；`sync_reviews` 生成每日视图；超出上限进入 `reviewOverflow`。
- **选题**：按 F/知识点权重/分值选题；kind 不匹配标 `needs_generation`；急救按 F 截断；作业/习题进入 basic 池。
- **D 分**：缺失证据不参与加权平均；`steps` 由分值折算；前置深度递归计算。
- **分类**：文件名+内容打分，输出依据；答案/复习指南不再误判为试卷；支持 `reclassify`。
- **变式题**：数字不同不再当重复题，标 `variantOf`。
- **考纲/重点**：参与 KP 权重、`weights` 展示与排序。
- **领域**：`--domain` 强制领域；旧版两套题型（CSAPP / 通用）；`domains` 命令；`calc` 支持 choice/numeric/exact。
- **安全**：TLS 失败不再自动降级；`--insecure` 不带 Cookie；curl 回退改为显式 `--allow-curl`。
- **B 站评分**：字幕只加分，不再让有字幕视频得分更低。
- **SKILL.md**：开场信息收集、绝对路径、判分流程、`today` 不覆盖、frontmatter 精简；≤6 KB。
- **状态**：schema 升到 `@2`，旧工作区自动补字段。
- 测试：46 项。

## 0.1.0 — 2026-11-04

首个版本：四源关键词、B 站检索/字幕、早期固定天数示例排期、16 类题型、答案重算、每日讲义、导出与质检。



