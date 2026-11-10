# 方法论与参数依据

本文件说明 review-sprint 的科目画像、N 天排期、目标分量化、难度、常考度与间隔复习规则来自哪里，以及哪些数字只是可调初值。

## 1. 理论 → 规则

| # | 理论 / 来源 | 结论 | 落到 skill 的规则 |
|---|---|---|---|
| T1 | 遗忘曲线（Ebbinghaus 1885）；间隔效应（Cepeda et al. 2006；2008） | 分散复习优于集中复习；最佳间隔随保持期变化，约为保持期的 10%–30% | 画像 `reviewIntervals` 给首学后的复现阶梯；越过考试日截到考前 1–3 天 |
| T2 | 测试效应 / 提取练习（Roediger & Karpicke 2006） | 反复测试的长期保持优于反复重读 | 每天先闭卷回忆；复习用答题，不用重读 |
| T3 | 连续重学（Rawson & Dunlosky 2011） | 先学到能答对，再在不同日子各答对一次，长期保持最好 | L4 要求至少 3 个不同日子答对；同日多次只计 1 次 |
| T4 | Leitner / SM-2 / FSRS | 可按记忆状态算下次复习日 | 用 FSRS 简化式 + 考试截止约束；画像间隔用于首轮复习 |
| T5 | 交错练习（Rohrer & Taylor 2007） | 混排题型练习当下更难，延迟测验更好 | 强化期起每天至少 2 类题型；禁止整天只练一类 |
| T6 | 预测试效应（Richland, Kornell & Kao 2009） | 学之前先尝试作答，即使答错也有益 | 第 1 天诊断；每天新内容前 1–2 道预测试 |
| T7 | 高信心错误（Butterfield & Metcalfe 2001） | 自信却答错的题，纠正后记得更牢 | 记录信心 0–3；高信心错误单独标记，次日必考 |
| T8 | 元认知 / 流畅性错觉（Bjork） | 重读的熟悉感会高估掌握 | 掌握度只看作答记录，不看「已读」 |
| T9 | 睡眠巩固（Walker；Diekelmann & Born） | 学习后睡眠有助巩固 | 每天最后是睡前 3 题；次日开场先回忆这 3 题 |
| T10 | 认知负荷 / 样例效应 / 专长逆转（Sweller；Kalyuga 2003；Renkl） | 初学者看完整样例收益大；熟练后样例是负担 | 构建期给完整步骤；强化期只给提示；冲刺期只给题 |
| T11 | 多媒体分段原则（Mayer） | 自控的短片段优于整段长视频 | B 站定位到分 P / 时间段，不推整套合集 |
| T12 | 生成效应 / 自我解释（Chi 等） | 自己生成、自己解释记得更牢 | 考前默写速记表、用自己的话解释难点，再对照系统版本 |

> 上表数字是原始研究的大致结论，用作参数初值；不要在用户界面写成精确承诺。

## 2. 科目画像的数值依据

画像字段不是装饰：`schedule` 读 `phaseRatio / dailyMix / reviewIntervals / mockQuestions`，`quantify` 读 `masteryThresholds / masteryScoreRates / safetyFactor / masteryWeights`，`audit` 读 `checkers`，`topics` 读 `keywords / negative / biliPrefix`。每个数值旁边的 `_note` 写明依据或「经验初值，可调」。

新增科目只加 `references/subjects/<name>.json`。最小校验：`subject / label / biliPrefix / matchKeywords / questionTypes / dailyMix / phaseRatio / difficultyWeights / reviewIntervals / masteryThresholds / safetyFactor` 必填；每个数值必须有 `_note`。

## 3. N 天与阶段

**N 由用户给**，不设默认值。若只给考试日期，`N = 考试日 − 开始日`，考试当天不排任务；用户同时给日期与 N 且冲突时先问，不静默选择。

| N | 模式 | 阶段行为 |
|---|---|---|
| 1–3 | `emergency` | 取消构建/强化，全部「急救期」；按 F 保留高价值题型，列出放弃项 |
| 4–7 | `compressed` | 第 1 天诊断，构建+强化合并为「压缩期（构建+强化）」，最后冲刺 |
| 8–30 | `standard` | 诊断 → 构建 → 强化 → 冲刺 |
| >30 | `long` | 构建期拆成两轮（第一轮/第二轮），再强化、冲刺 |

阶段天数：

```
counts = largest_remainder(N, phaseRatio)   # 总和严格等于 N
第 1 天 = 诊断期
其余 = 构建 / 强化 / 冲刺（按画像比例）
```

例：N=5、比例 0.4/0.35/0.25 → 2/1/1（诊断在第 1 个构建日）；N=12；N=30。不要拿某一个 N 当固定模板。

## 4. 每日配比与负载

总任务量先算出来：

```
W = Σ(KP 学习分钟 + 题型练习分钟) + 复习分钟 + 模拟分钟
日均 = W / N
```

`dailyMix` 给出基础 / 真题 / 拔高 / 背诵的**时间比例**；`kindMinutes` 给出各类平均单题用时；由此反推当天槽位数：

```
count(kind) = max(1, round(dailyMinutes × mix(kind) / minutes(kind)))
```

强约束：

- 每天实际分钟与 `dailyMinutes` 的偏差 ≤ ±15%；超出时先移出可移动练习，再移出到期复习到 `reviewOverflow`；仍超则写 `warning` 并由 `audit` 拦截。
- 复习优先保留，但单日复习上限 `maxReviewsPerDay`；超出的进入 `reviewOverflow`，不静默丢弃。
- 最后一天模拟题量来自画像 `mockQuestions`，不是固定模板；每槽分钟按预算回算，保证可打印日程不爆时。

## 5. 目标分 → 掌握度

掌握等级（阈值可由画像 `masteryThresholds` 覆盖）：

| 等级 | 含义 | 判定 |
|---|---|---|
| L0 | 放弃 | 不排新学；只保留在总览/放弃清单 |
| L1 | 认识 | 能选对概念题（有正确作答即可） |
| L2 | 会做基础题 | 基础题正确率 ≥ 70%（可覆盖） |
| L3 | 熟练 | 真题正确率 ≥ 80%，限时内完成（可覆盖） |
| L4 | 稳拿 | 变式/拔高正确率 ≥ 85%，且 3 个不同日子答对（可覆盖） |

量化：

```
contribution(K) = P(K) × F(K) × weight(K) × recentWeight(K)
normalized(K)   = contribution(K) / Σ contribution × 100
expected(K, L)  = normalized(K) × scoreRate(L)
```

- `F`：去重试卷中出现该考点/题型的比例；近年（近两年）权重 1.2。
- `P`：该考点相关题的平均分值；没有往年题时用全卷平均分。
- `recentWeight`：近年卷 ×1.2，其余 ×1.0。
- `scoreRate`：画像 `masteryScoreRates` 的 L1–L4 初值（默认 0.30/0.70/0.85/0.95）。
- `levelFactors`、`cognitiveWeights`、`practiceCounts`：该科 L1–L4 用时系数、认知维度权重、练习量；全部在画像里，代码只做 fallback。
- `safetyFactor`：画像 `safetyFactor`，默认 1.10；目标分先乘安全系数。
- `coverage`：映射到知识点的往年题分值 / 试卷总分；低于 80% 时可达分给区间 `[reachableLow, reachableScore]`，不要假装精确。

贪心：从所有 K 的 L0 开始，每次选「下一等级的期望分增量 / 增量分钟」最大的 K 升级，直到达到 `目标 × safetyFactor` 或时间预算耗尽。预算 = `N × dailyMinutes × 0.90`（留 10% 机动）。

输出：

- `reachableScore`、`requiredScore`、`shortfall`、`totalMinutes`、`dailyQuestions`；
- 60/70/80/90/95 五档矩阵；用户档位 `selected=true`；
- `abandoned[]`：停在 L0 的考点及估算丢分；
- `mastery{}`：每个考点的目标等级、当前等级、期望分、分钟、题量。

## 6. 常考度 F、难度 D 与错题

```
F = 出现该题型的去重试卷数 / 去重后试卷数 × 平均分值权重 × 近年加权
D = 加权平均(往年失分率, 用户错误率, 前置深度, 易错标记)
```

- 先做试卷去重（5-gram Jaccard ≥ 0.75 视为同源），再统计。
- 没有证据的 D 分量不参与加权：没作答时用户错误率不是 0.5，没往年题时不用固定 3/8。
- 前置深度按 `prereq` 链递归；`steps` 由分值折算。
- 每次 `answer` / `review` 后重算 D；达到目标等级后仍保留错题重测，不提前删除。
- 错题连续两个不同日子答对才关闭；L4 额外要求 3 个不同日子。

## 7. FSRS 简化式（非 FSRS-6 官方实现）

> 本项目**没有**实现 FSRS-6：没有官方参数拟合、没有 21 参数权重、没有真实复习日志校准。这里只借用“可提取性/稳定性/间隔”的形状，参数是启发式初值；文档和输出不应把它称为 FSRS-6。

```
R(t,S) = (1 + F·t/S)^C,  F = 19/81, C = -0.5
I(r,S) = S/F · (r^(1/C) − 1),  r=0.9 时 I=S
```

- 初始 `difficulty=5, stability=1`。
- 评分 1=Again、2=Hard、3=Good、4=Easy。
- 更新：`D' = clamp(D − 0.8·(rating−3), 1, 10)`；`S' = S·(1.15 + 0.25·(rating−2))`，Again 重置为 1。
- 截止约束：若 `due >= examDate`，改排到 `max(今天+1, 考试日−3)`。
- 画像 `reviewIntervals` 用于首轮复习排期；之后由简化式的 stability/due 接管。

## 8. 五册与来源

- 三册（02 主册 / 03 答案册 / 05 刷题宝典）使用同一套题号；`audit` 比对集合，缺一题或多一题都算「必须修复」。
- 来源只写解析结果里的 `file`/`page`；拿不到就写「待确认」，不补页码。
- 答案状态只允许：已核验（脚本重算）、待确认（无答案/冲突/仅官方）、模型给出⚠️（未经官方或重算核验）。主观题由用户确认后标「assist 确认」。

## 9. 参数不是事实

阶段比例、D 权重、FSRS 参数、阈值、`dailyMix` 都是初值。用真实作答回看：如果某类题一直错但 D 不高，调 `userError` 权重；如果复习总超时，调 `maxReviewsPerDay` 或 `dailyMinutes`；如果目标总放不下，降低目标或增加 N，不要偷偷改 safetyFactor。
