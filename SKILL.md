---
name: review-sprint
description: "期末、考研或证书考试的单科冲刺：手上有课件和往年题，需要分天复习计划、按目标分量化强度、每日学习包，以及可打印的主册/答案册/速记/刷题册时使用。Keywords: 复习, 备考, 期末, 真题, 错题, B站, exam prep, study plan."
---

# review-sprint · 单科考前冲刺

脚本负责解析、画像、量化、排期、检索、判分与质检；模型负责讲解、出题、解析和五册补写。不要猜链接、页码、答案。

## 0. 先收集信息（缺什么问什么）

必须确认：**科目/画像**、**复习天数 N**、**目标分**、材料、往年题、每天分钟、考试日期（可选）。**N 没有默认值，不许自己填 20。**

- 只给考试日期：`N = 考试日 − 开始日`，请用户确认。
- 日期与 N 冲突：先指出，以用户确认的为准。
- 科目识别置信度 < 0.6：脚本返回候选/非零退出，**必须让用户确认**后用 `--subject` 重跑。
- `--daily-minutes` 未给时 build 会打印“使用默认 120 分钟”；考试日未给时会打印“按今天 + N 推算”。

`SKILL_DIR`=本文件目录；`WS`=工作区。命令用 `python "$SKILL_DIR/scripts/coach.py" ...`；Windows 也可用 `"$SKILL_DIR\scripts\coach.cmd"` / `coach.ps1`，macOS/Linux 用 `bash "$SKILL_DIR/scripts/coach.sh"`。路径分隔符按平台替换。

## 1. 阶段 A：build 一次

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" build \
  --course "高等数学" --subject math \
  --materials "D:/课程/课件.pptx" "D:/课程/课件目录/" \
  --past-papers "D:/课程/往年题/" \
  --target 85 --days 14 --daily-minutes 150 \
  --out "$WS/output" --format md,docx
```

- `--subject` 可省略（自动识别）；`--domain` 是旧别名。画像在 `references/subjects/`。
- `--format` 可只写 `md`；要 DOCX 需 python-docx；PDF 可选，需 LibreOffice。
- 缺 `--target/--days`：退出码 2，JSON 模式输出 `{"needsInput":["target","days"]}`；**先问用户**。
- 工作区已有 state：默认拒绝覆盖。保留历史用 `--refresh-materials`；确实重来用 `--force`（先备份 `study_state.<时间>.bak.json`）。
- 输入支持 PPTX/PDF/DOCX/MD/TXT；旧 `.ppt` 用 LibreOffice 转 `.pptx`。
- 每步落 `output/_build/00_inputs.json … audit.json`；`fill_tasks.json` 是待模型补写清单。

## 2. 阶段 A 续：fill 五册

build 生成 5 份 MD（可选 DOCX）：01 计划、02 主册、03 答案册、04 速记手册、05 刷题宝典。脚本只填结构、来源、题号、F/D；需要讲解/口诀/解析的地方输出：

```html
<!-- MODEL:main:K3 -->
<!-- MODEL:answer:P1-Q1 -->
<!-- MODEL:cheatsheet:K3 -->
<!-- MODEL:drill:T2 -->
<!-- MODEL:kpMap:P1-Q2 -->
```

1. 先读 `references/prompt-templates.md` 第 1–4 节，按模板写内容。
2. 运行 `coach.py fill --tasks` 拿 `fill_tasks.json`；每项有 `id / type / instruction / source / stem`。
3. 把回填写成 `{"tasks":{"main:K3":"...","answer:P1-Q1":"...","kpMap:P1-Q2":["K1"]}}`，运行：

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" fill --apply fill.json
```

`fill` 会写回 `knowledgePoints[].mainNote/cheatsheet`、`questions[].solution` 和 `questionTypes[].method`，重渲染五册并重跑 audit。**占位符 >0 时 audit 必须失败**，不能算完成；`kpMap` 未填的题不进入 F/P 统计。

## 3. 阶段 B：每日循环

build 只生产册子，**不产生作答记录**。每天必须走：

```bash
coach.py status
coach.py today
coach.py answer --qid ... --result correct|wrong --confidence 0..3 --cause ...
coach.py done --day N
```

- `today` 默认不覆盖已有 daily；`--force` 重生成。
- 客观题用 `calc`/`recompute`；主观题按评分点对照，**用户确认**后标「assist 确认」。
- 每道题都调用 `answer`，否则错题、D、FSRS、掌握度不更新；补录用 `--date`。
- `status` 看到期复习/错题/剩余天数；`set --days N` 只重排未来并保留已完成日；`plan --rebuild` 同理。

## 4. 目标分与 N 天

- 画像字段：`questionTypes / dailyMix / phaseRatio / levelFactors / reviewIntervals / masteryThresholds / safetyFactor / checkers / keywords`。
- `N≤3` 急救、4–7 压缩、8–30 标准、>30 长线；阶段用最大余数法，总和 = N；每日负载偏差 >15% 要移动或进 `reviewOverflow`。
- 掌握度 L0 放弃 / L1 认识 / L2 基础 ≥70% / L3 真题 ≥80% / L4 变式 ≥85% 且 3 个不同日子答对；阈值可由画像覆盖。
- 目标分：`期望分 = P × F × 得分率`，按“期望分/分钟”贪心到 `目标 × safetyFactor`；放不下时输出可达分区间、缺口、放弃项。覆盖率低时可达分按区间看。

## 5. 答案与冲突

`calc --spec` / `set-check` / `recompute`。校验器由画像 `checkers` 决定：通用 `choice/exact/numeric`；数学 `matrix/determinant`；计算机系统另有 `twos/ieee754/flags/modrm/machine`。官方与重算冲突先标 **pending**；核对规格后用：

```bash
coach.py resolve-conflict --qid ... --use official|recomputed --note "..."
```

不要默认以重算为准。

## 6. B 站（安全规则不变）

```bash
coach.py bilibili --kp K1 --limit 2
```

- 链接只能来自命令输出；禁止自写/补全 BV、分 P、时间点；每个 BV 必须能在 `.cache/bilibili` 找到。
- Cookie 只从 `BILIBILI_COOKIE`/`--cookie-file` 读，不写状态；无 Cookie 只按标题/分 P。
- 证书失败不自动降级：`--ca-file`；确需关闭校验用 `--insecure`（不带 Cookie）；403/412 用 curl 需显式 `--allow-curl`。

## 7. 参考文件（按需读）

| 场景 | 读 |
|---|---|
| 填五册占位符 | `references/prompt-templates.md` 第 0–4 节 |
| 查 state 字段/迁移 | `references/state-schema.md` |
| 调阶段、FSRS、D/F、目标量化 | `references/methodology.md` |
| 看 audit 阈值/验收 | `references/quality-gates.md` |
| 选/改科目画像 | `references/subjects/*.json`；自定义放 `custom/` |
| B 站接口/风控 | `references/bilibili-api.md` |

## 8. JSON 与退出码

所有子命令支持 `--json`；约定：`0` 成功，`1` 质检失败/仍有占位符，`2` 需要用户输入，`3` 缺依赖/状态冲突。

```bash
coach.py build ... --json
coach.py audit --json
coach.py status --json
```

## 9. 铁律

1. 单课单考试日；2. 查不到写「待确认」，不编页码/答案/链接；3. 先做题后看视频；4. 冲刺不学新内容，急救说明砍掉什么；5. 讲解/出题/判分分开，主观题用户确认；6. `audit` 有「必须修复」先修；7. N/目标/科目必须来自用户或用户确认，不静默填默认值；8. 五册占位符未填完不算完成。
