# Changelog

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



