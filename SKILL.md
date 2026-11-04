---
name: review-sprint
description: "单科目考前冲刺：导入课件与真题，生成分天计划、四源关键词、B站高重合视频、每日讲义、实时难度与常考题型专练、答案重算与质检。适用于期末、考研、证书考试的单科复习；需要用户先给科目、考试日期、材料路径、每日时长和目标分。Keywords: 复习, 备考, 期末, 真题, 错题, B站, exam prep, study plan."
---

# review-sprint · 单科目考前冲刺

脚本负责解析、排期、检索、打分与重算；模型负责讲解、出题与解析。不要猜链接、页码、答案。

## 0. 先收集信息

开始前确认（缺什么问什么，不要猜）：科目、考试日期、材料路径、每天分钟、目标分。考试当天不排学习任务。

`SKILL_DIR`=本文件目录；`WS`=工作区路径（如 `$PWD/review-sprint-workspace`），不要放进安装目录。

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$PWD/review-sprint-workspace" init \
  --course "计算机系统基础" --exam-date 2026-11-24 \
  --materials "D:/课程/课件" "D:/课程/真题" \
  --daily-minutes 120 --target 90 --domain cs_systems
```

- 没有 `python`：Windows 用 `"$SKILL_DIR\scripts\coach.cmd"`，macOS/Linux 用 `bash "$SKILL_DIR/scripts/coach.sh"`。
- `--domain` 可省略（自动识别）；可选 `cs_systems / math / law / economics / medicine / general`。非 CSAPP 科目用 12 类通用题型。
- 材料默认只读复制；答案与试卷自动配对；扫描 PDF/旧 Office 会标「待转换」，不要假装读到。

## 1. 建计划与质检

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" status
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" plan --rebuild
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" audit
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" types
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" weights
```

- 三阶段：诊断 → 构建 → 强化 → 冲刺；最后学习日整卷模拟。
- 每天默认 4 基础 + 2 真题 + 1 拔高；题型数按本课实际类型（CSAPP 16，通用 12），每类 ≥3 次且 ≥3 天。
- `audit` 有「必须修复」时先修；冲突未处理、排期超预算、链接无缓存都算。
- `types` 看常考度 F；`weights` 看知识点权重、考纲等级、重点标记与 D。

## 2. 每天这样用

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" today
```

`today` 默认**不覆盖**已存在的 daily 文件；要重生成加 `--force`。

1. **开场回忆**：闭卷答到期复习/错题，信心 0–3。
2. **今日知识点**：替换 daily 里的 `<!-- MODEL: ... -->`；保留来源标签。
3. **难点精讲**：D 前 3；具体错法、易混对、最小例题。
4. **B 站补课**：每点 1–2 条；没有就运行第 4 节命令。
5. **题型专练**：4+2+1；缺题先 `add-question`。
6. **错因分类**：概念/计算/审题/记忆/时间。
7. **速记表 + 睡前 3 题 + 明日预告**。
8. **参考答案**：只放最后，先题后答。

判分与记录：

- 客观题用 `calc`/`recompute` 脚本判，结果标「已核验」。
- 主观题按评分点对照参考答案，列出命中/遗漏，**由用户确认**后标「assist 确认」，不得冒充自动判分。
- **每道题做完都调用 `answer`**；否则错题、D、FSRS 不会更新。

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" answer \
  --qid P1-Q1 --result wrong --confidence 3 --cause concept
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" done --day 2
```

补录用 `--date YYYY-MM-DD`；答错进错题本、次日重测；连续两个不同日子答对才关闭错题。

## 3. 答案重算与冲突

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" calc \
  --kind flags --op sub --a 5 --b 7 --bits 8
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" set-check \
  --qid P1-Q21 --check '{"kind":"flags","op":"sub","a":5,"b":7,"bits":8}'
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" recompute --qid P1-Q21
```

- 支持 `twos/decode/ieee754/ieee754_decode/flags/modrm/machine`，以及通用的 `choice/exact/numeric`。
- 官方答案与重算不一致时先标 **pending**；核对 `check` 规格无误后：

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" resolve-conflict \
  --qid P1-Q21 --use official|recomputed --note "核对说明"
```

只有 pending 会阻塞 `audit`；不要默认「以重算为准」。

## 4. 四源关键词与 B 站

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" keywords --chapter CH2
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" bilibili --kp K1 --limit 2
```

- 关键词四源、B 站五层过滤、阈值与权重见 `references/methodology.md` / `references/bilibili-api.md`。
- 链接只能来自命令输出；**禁止自写/补全 BV 号、分 P、时间点**。每个 BV 必须能在 `.cache/bilibili` 找到。
- 无 Cookie 只能按标题/分 P 打分；有 Cookie 才可能读字幕定位。Cookie 只从 `BILIBILI_COOKIE`/`--cookie-file` 读，不写状态。
- 证书失败不自动降级：用 `--ca-file`；确需关闭校验用 `--insecure`（**不带 Cookie**）。403/412 要 curl 重试时显式加 `--allow-curl`，风险自负。

## 5. 导出

```bash
python "$SKILL_DIR/scripts/coach.py" --workspace "$WS" export --format md,ics,anki
```

要 DOCX/PDF 用 office skill 转换；页码用 PDF 书签反查。

## 6. 铁律

1. 单课单考试日；2. 查不到写「待确认」，不编页码/答案/链接；3. 先做题后看视频；4. 冲刺不学新内容，急救说明砍掉什么；5. 讲解/出题/判分分开，主观题用户确认；6. `audit` 有「必须修复」先修。

## 7. 参考

参考：`references/methodology.md`（阶段/FSRS/D/F）、`bilibili-api.md`（接口/风控）、`state-schema.md`（状态字段）、`prompt-templates.md`（模板）、`quality-gates.md`（质检）。

降级：无网只给搜索链接；无字幕只按标题/分P；扫描件标 OCR；读不到要列出。
