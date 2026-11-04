# Changelog

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
- **领域**：`--domain` 强制领域；CSAPP 16 类、通用 12 类；`domains` 命令；`calc` 支持 choice/numeric/exact。
- **安全**：TLS 失败不再自动降级；`--insecure` 不带 Cookie；curl 回退改为显式 `--allow-curl`。
- **B 站评分**：字幕只加分，不再让有字幕视频得分更低。
- **SKILL.md**：开场信息收集、绝对路径、判分流程、`today` 不覆盖、frontmatter 精简；≤6 KB。
- **状态**：schema 升到 `@2`，旧工作区自动补字段。
- 测试：46 项，含排期不含考试日、冲突 resolve、错题关闭、领域切换、TLS 拒绝等。

## 0.1.0 — 2026-11-04

首个版本：四源关键词、B 站检索/字幕、20 天排期、16 类题型、答案重算、每日讲义、导出与质检。
