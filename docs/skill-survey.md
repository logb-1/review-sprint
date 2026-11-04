# 同类 skill 调研与差异化（2026-11-04）

本文件记录开发前的 GitHub 调研，避免重复造轮子，也说明 review-sprint 为什么仍然值得单独做。

## 1. 调研方法

- GitHub REST API 仓库搜索 + Code Search（`filename:SKILL.md` 组合 exam / 复习 / 真题 / study plan / flashcard / bilibili 等）。
- 初筛 15 个候选仓库，逐个拉 `SKILL.md` / `README` / 目录树核对，不只看描述。
- 重点看：是否覆盖「课件+真题 → 分天计划 → 复习资料 → 错题/进度」这条主链，以及有没有关键词融合、B 站检索、题型矩阵、答案重算。

## 2. 最相关项目

| 项目 | Star | 协议 | 它实际做什么 |
|---|---:|---|---|
| [ZeKaiNie/universal-examprep-skill](https://github.com/ZeKaiNie/universal-examprep-skill) | 366 | MIT | 课件/作业/往年题 → 分章 wiki + 题库；讲课、抽真题、错题本、复习讲义、小抄、跨会话进度；强调来源/页码 |
| [yoli-mi/good-learning](https://github.com/yoli-mi/good-learning) | 278 | MIT | 教材/考纲/试卷 → 知识清单 + 备考计划 + 每日课程 + 错题本；PDF 走 LaTeX |
| [serenakeyitan/open-exam-skills](https://github.com/serenakeyitan/open-exam-skills) | 168 | NOASSERTION | 模块化：citation-check、flashcards、mindmap、quiz |
| [limpidwei/final-exam-review](https://github.com/limpidwei/final-exam-review) | 5 | MIT | 考前 72 小时：多格式材料 → 分类去重 → 逐章整合 → 可打印复习 PDF |
| [asukaneko/university-final-review-skill](https://github.com/asukaneko/university-final-review-skill) | 5 | NOASSERTION | 双语、跨学科期末复习 |
| [Cusob/zjut-review-guide](https://github.com/Cusob/zjut-review-guide) | 9 | NOASSERTION | 浙工大专用复习指导；兜底会搜 B 站/小红书 |

另有 `ookkiou/408-exam-planner`、`Kosthi/11408.skill`、`sa1emie/study-skill`、`btgaskin/studykit` 等垂类实现。

## 3. 能力对照

● 完整覆盖　◐ 部分覆盖　○ 未覆盖

| 能力 | universal | final-review | good-learning | open-exam | 本项目 |
|---|:---:|:---:|:---:|:---:|:---:|
| 课件/真题多格式解析 + OCR 降级 | ● | ● | ◐ | ◐ | ● |
| 分章知识库 | ● | ● | ● | ◐ | ● |
| 四源关键词融合（模型/缩写/标题/TF-IDF） | ○ | ○ | ○ | ○ | ● |
| B 站检索 + 负面词/领域锚定/字幕定位 | ○ | ○ | ○ | ○ | ● |
| 真题题库 + 答案重算 | ◐ | ◐ | ◐ | ◐ | ● |
| 按本课题型矩阵（CSAPP 16 / 通用 12） | ◐ | ○ | ◐ | ○ | ● |
| K/E/Q 或等价复习结构 | ◐ | ◐ | ○ | ◐ | ● |
| 来源标签 + 页码回链 | ● | ◐ | ◐ | ● | ● |
| 错题本 / 跨会话进度 | ● | ○ | ● | ◐ | ● |
| PDF/DOCX 导出 + 目录页码校验 | ◐ | ● | ● | ◐ | ◐（交给 office skill） |

结论：

1. 复习资料生成这条主干已经高度重合，`universal-examprep-skill` 是最完整的同类项。
2. 没有找到同时具备**四源关键词融合、B 站防跑题检索/字幕定位、按本课题型矩阵、答案重算**的 skill。
3. 因此本项目不复制上述代码，只借鉴它们的**状态文件、来源标签、错题优先、8 类材料、三档密度**等设计；差异点集中在「检索质量」与「排期/重算的确定性」。

## 4. 为什么不做成上游插件

- 插件形态绑定宿主 API；本项目要能在 DSH / Claude Code / Codex / Cursor 等只支持 `SKILL.md` 的 agent 里跑。
- 上游项目已经很大；fork 后维护成本高，且容易与上游提示词/状态格式冲突。
- 本项目的核心是零依赖 CLI + 小 `SKILL.md`，方便审计、测试和离线运行。

## 5. 可继续借鉴的方向

- 从 `universal-examprep-skill` 借「逐题独立子智能体」的隔离讲解思路（本项目的 prompt 模板已留接口）。
- 从 `good-learning` 借 LaTeX 双版本（紧凑/宽松）与错题本字段。
- 从 `open-exam-skills` 借 claim-level citation check，把「来源标签」升级为「逐句核验」。
- 从 `zjut-review-guide` 借「课程不在仓库时搜 B 站/小红书」的兜底，但保持「不达标只给搜索链接」。
