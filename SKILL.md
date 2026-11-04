---
name: review-sprint
description: "多种类科目考前冲刺：12 类科目画像 + 用户指定天数 + 目标分量化掌握度，导入课件/往年题，一条 build 命令生成复习计划、主册、答案册、速记手册、刷题宝典（MD/DOCX）。需要用户先给科目、复习天数、目标分、材料路径和每日时长。Keywords: 复习, 备考, 期末, 真题, 错题, B站, exam prep, study plan."
---

# review-sprint · 多种类科目考前冲刺

脚本负责解析、画像、量化、排期、检索、判分与质检；模型负责讲解、出题与解析。不要猜链接、页码、答案。

## 0. 先收集信息（缺什么问什么）

必须确认：**科目/画像**、**复习天数 N**、**目标分**、材料、往年题、每天分钟、考试日期。**N 没有默认值，不许自己填 20。**

- 只给考试日期：`N = 考试日 − 开始日`，请用户确认。
- 日期与 N 冲突：先指出，以用户确认的为准。
- 科目识别置信度 < 0.6：脚本返回候选/非零退出，**必须让用户确认**后用 `--subject` 重跑。

`SKILL_DIR`=本文件目录；`WS`=工作区路径。

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" build \
  --course "高等数学" --subject math \
  --materials "D:/课程/课件.pptx" "D:/课程/课件目录/" \
  --past-papers "D:/课程/往年题/" \
  --target 85 --days 14 --daily-minutes 150 \
  --out "$WS/output" --format md,docx
```

- `--subject` 可省略（自动识别）；画像：`references/subjects/`，含 cs_systems / programming / data_structures / math / physics / circuits / chemistry_biology / medicine / law / economics / politics / foreign_language / general。
- 缺 `--target` 或 `--days`：`build` 非零退出并列出待问字段；**必须先问用户**。
- 旧式单日流程仍可用 `init`（无 `--days` 时由考试日推算）。

## 1. build 的五册

`output/` 同时有 MD + DOCX：

| 文件 | 必含 |
|---|---|
| 01-复习计划 | 科目/目标/安全系数/可达分/放弃项；60/70/80/90/95 矩阵；按天表（日期/阶段/知识点/题号/分钟/目标等级） |
| 02-主册 | 按章节/知识点；目标等级、来源页、F/D、易错点、最小例题；题目只放题号和题干 |
| 03-答案册 | 同题号；答案、步骤、评分点、校验状态（已核验/待确认/模型给出⚠️） |
| 04-速记手册 | 每点 ≤5 行：定义/公式、易混、口诀；按最后 3 个有知识点的学习日排序 |
| 05-刷题宝典 | 按画像题型；先“识别信号 → 解法套路”，再基础→真题→拔高；只放题号 |

`build` 写 `output/_build/00_inputs.json … audit.json`；三册题号必须零缺失零多余；来源只写解析出的文件/页，查不到写「待确认」。

## 2. 画像、N 天与量化

- 画像字段：`questionTypes`（id/名称/分钟/判分方式）、`masteryWeights`、`difficultyWeights`、`dailyMix`、`phaseRatio`、`reviewIntervals`、`masteryThresholds`、`safetyFactor`、`keywords/negative`、`checkers`。新增科目只加 JSON，不改代码；每个数值带 `_note`。
- `N≤3` 急救；`4–7` 压缩（构建+强化合并）；`8–30` 标准；`>30` 长线（构建分两轮）。阶段天数用最大余数法，总和 = N；每日负载偏离 >15% 要移动或写 `reviewOverflow`。
- 掌握度：L0 放弃 / L1 认识 / L2 基础 ≥70% / L3 真题 ≥80% / L4 变式 ≥85% 且 3 个不同日子答对；阈值可由画像覆盖。
- 目标分：`期望分 = P × F × 得分率`，按“期望分/分钟”贪心到 `目标 × safetyFactor`；放不下时输出可达分、缺口、放弃项，不静默降级。

## 3. 旧式逐日流程

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" init \
  --course "计算机系统基础" --subject cs_systems \
  --days 14 --materials "D:/课件" --past-papers "D:/真题" \
  --daily-minutes 120 --target 85
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" status
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" plan --rebuild
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" today
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" audit
```

- `today` 默认不覆盖；`--force` 重生成。
- 每日：开场回忆 → 知识点（目标等级/来源/D）→ 难点 → B 站 → 题型专练（按画像 `dailyMix`，不是固定 4+2+1）→ 错因 → 速记 + 睡前 3 题 → 参考答案。
- 客观题用 `calc`/`recompute`；主观题按评分点对照，**用户确认**后标「assist 确认」。每题都调用 `answer`，否则错题/D/FSRS/掌握度不更新。
- 补录 `answer --date`；答错进错题本，连续两个不同日子答对才关闭。

## 4. 判分与冲突

`calc --spec '{"kind":"determinant","rows":[[1,2],[3,4]]}'`；`set-check` 绑定规则，`recompute` 重算。校验器由画像 `checkers` 决定：通用 `choice/exact/numeric`；数学 `matrix/determinant`；计算机系统另有 `twos/ieee754/flags/modrm/machine`。官方与重算冲突先标 **pending**；核对规格后用 `resolve-conflict --use official|recomputed --note`，不要默认以重算为准。

## 5. B 站（安全规则不变）

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" bilibili --kp K1 --limit 2
```

- 链接只能来自命令输出；禁止自写/补全 BV、分 P、时间点；每个 BV 必须能在 `.cache/bilibili` 找到。
- Cookie 只从 `BILIBILI_COOKIE`/`--cookie-file` 读，不写状态；无 Cookie 只按标题/分 P。
- 证书失败不自动降级：`--ca-file`；确需关闭校验用 `--insecure`（不带 Cookie）；403/412 用 curl 需显式 `--allow-curl`。

## 6. 导出与铁律

`audit` 有「必须修复」先修（考试日、题型覆盖、负载、五册题号、pending 冲突、链接缓存）。

1. 单课单考试日；2. 查不到写「待确认」，不编页码/答案/链接；3. 先做题后看视频；4. 冲刺不学新内容，急救说明砍掉什么；5. 讲解/出题/判分分开，主观题用户确认；6. N/目标/科目必须来自用户或用户确认，不静默填默认值。
