---
name: review-sprint
description: "单科目考前冲刺：导入课件与真题，生成分天复习计划、四源关键词、B站高重合视频、K/E/Q 式每日讲义、实时难度与常考题型专练、答案重算与质检。用于期末、考研、证书考试的复习。Keywords: 复习, 备考, 期末, 真题, 错题, 计划, B站, exam prep, study plan, spaced repetition."
whenToUse: "用户要复习一门课、准备考试、整理课件与真题，或需要每日计划、B站网课、错题复盘、考前速记时。"
---

# review-sprint · 单科目考前冲刺教练

本 skill 是**一条考前资料生产线**：脚本负责解析、排期、检索、打分与重算；模型负责讲解、出题与解析。不要猜链接、页码、答案。

## 0. 先定位

`SKILL_DIR` = 本 `SKILL.md` 所在目录。所有命令在 `SKILL_DIR` 下执行：

```bash
python scripts/coach.py --help
python scripts/coach.py doctor
```

Windows 无 python 用 `scripts\coach.cmd`；Unix 用 `bash scripts/coach.sh`。默认工作区 `.review-sprint`。

## 1. 建工作区

```bash
python scripts/coach.py --workspace .review-sprint init \
  --course "计算机系统基础" --exam-date 2026-11-23 \
  --materials "D:/课程/课件" "D:/课程/真题" \
  --daily-minutes 120 --target 90
```

- `--materials` 可给多个文件或目录；原始文件只读，导入时复制。
- 考纲/重点/真题/答案/作业/课件/笔记/教材按 8 类识别；答案与试卷配对。
- 先 `status` 看材料、章节、知识点、试卷、题目数；再 `plan` 排期。
- 缺依赖（扫描 PDF、旧版 Office）标 `待转换`，不要假装读到了。

## 2. 排期与质检

```bash
python scripts/coach.py plan --workspace .review-sprint --rebuild
python scripts/coach.py audit --workspace .review-sprint
python scripts/coach.py types --workspace .review-sprint
```

- 三阶段：诊断 → 构建（完整样例）→ 强化（题型混排）→ 冲刺（整卷+错题）；最后一天只模拟。
- 每天默认 4 基础 + 2 真题 + 1 拔高；最后一天 10 模拟 + 2 证明。
- 16 类题型每类 ≥3 次且分布在 ≥3 天；不够的题标 `needs_generation`，由模型补题。
- 间隔复习按 FSRS + 考试截止约束排；`audit` 必须 0 个「必须修复」。

## 3. 每天这样用

```bash
python scripts/coach.py today --workspace .review-sprint
```

按输出顺序做：

1. **开场回忆**：闭卷答到期复习与昨晚 3 题，记信心 0–3。
2. **今日知识点**：替换 `<!-- MODEL: ... -->`；保留来源标签〔原文：文件 第 N 页〕/〔整理〕/〔补充〕/〔待确认〕。
3. **难点精讲**：D 分前 3；写具体错法、易混概念对、最小例题，不写“粗心”。
4. **B 站补课**：每个知识点 1–2 条；没有就 `bilibili --kp Kx`；视频放题后。
5. **题型专练**：4 基础 + 2 真题 + 1 拔高；缺题先 `add-question`，不临时编号。
6. **错因分类**：概念/计算/审题/记忆/时间 → 重讲+视频/同类专练/题型识别卡/间隔复习/限时。
7. **速记表 + 睡前 3 题 + 明日预告**：速记表写“一句话 + 答题要点 123”。
8. **参考答案**：只放最后，先题后答；答案须能追溯到原文或重算。

记录作答：

```bash
python scripts/coach.py answer --workspace .review-sprint \
  --qid P1-Q1 --result wrong --confidence 3 --cause concept
```

答错会自动进错题本、明天重测，并重算相关知识点 D 分。

## 4. 四源关键词与 B 站检索

```bash
python scripts/coach.py keywords --workspace .review-sprint --chapter CH2
python scripts/coach.py bilibili --workspace .review-sprint --kp K1 --limit 2
```

- 关键词四源：模型 3 / 缩写 2.6 / 标题 2.5 / 本章 TF-IDF 2（跨章 +0.3）；通用词过滤、父子术语互斥、每源最多 2 条、不足用标题兜底。
- B 站五层：锚词 → 术语表 → 负面词 → 领域锚定 → 两段式排序；低于阈值只给搜索链接。
- 链接只能来自命令输出；**禁止模型自写/补全 BV 号、分 P、时间点**。每个 BV 必须能在检索缓存里找到。
- 无 Cookie 也能按标题/分 P 打分；有 Cookie 才可能拿到字幕时间点。Cookie 只从 `BILIBILI_COOKIE` 或 `--cookie-file` 读，不写进状态文件。

## 5. 答案重算与题型分析

```bash
python scripts/coach.py calc --kind flags --op sub --a 5 --b 7 --bits 8
python scripts/coach.py set-check --workspace .review-sprint --qid P1-Q21 \
  --check '{"kind":"flags","op":"sub","a":5,"b":7,"bits":8}'
python scripts/coach.py recompute --workspace .review-sprint --qid P1-Q21
```

- 覆盖：补码/移码、IEEE-754、CF/OF/SF/ZF、ModRM、常用 x86-64 指令编码。
- 重算与官方答案冲突时以重算为准，并在解析写明；无法脚本校验的题标 ⚠️，不得冒充已核验。
- `types` 输出题型矩阵、覆盖试卷数、常考度 F、排期天数；专练按 F 与 D 选题并交错。

## 6. 导出

```bash
python scripts/coach.py export --workspace .review-sprint --format md,ics,anki
```

输出排期、速记表、`.ics` 日历、Anki CSV。要 DOCX/PDF 用 office skill 转换，页码用 PDF 书签反查。

## 7. 铁律

1. 一次只服务一门课、一个考试日期。
2. 查不到写「待确认」，不编页码、不编答案、不编链接。
3. 先做题后看视频；视频只给 D 高或答错的知识点。
4. 冲刺期不引入新知识点；急救模式明确说砍掉了什么。
5. 讲解、出题、判分分开；主观题对照参考答案判。
6. `audit` 有「必须修复」先修再继续。

## 8. 参考文件

- `references/methodology.md`：理论、阶段、FSRS、D/F 公式。
- `references/bilibili-api.md`：接口、WBI、字幕、风控、缓存。
- `references/state-schema.md`：状态字段。
- `references/prompt-templates.md`：讲解/出题/重算/理由模板。
- `references/quality-gates.md`：质检门槛与回归测试。

降级：无网只给搜索链接；无字幕只按标题/分P；扫描件标 OCR；读不到要列出。
