# review-sprint · 单科目考前冲刺教练

把「课件 + 往年题 + 考纲」变成一条可执行的复习生产线：分天排期、四源关键词、B 站高重合视频、实时难度点、常考题型专练、答案重算、每日讲义与质检。

> 一个 agent skill：`SKILL.md` + 零依赖 Python CLI + 单文件状态。适配 DSH / Claude Code / Codex / Cursor 等支持 `SKILL.md` 的 agent。

## 它解决什么问题

| 常见失败 | 本 skill 的做法 |
|---|---|
| 复习计划拍脑袋，前几天学完、后几天没题 | 三阶段按剩余天数缩放；每天 4 基础 + 2 真题 + 1 拔高；按本课题型（CSAPP 16 / 通用 12）每类 ≥3 次、分布 ≥3 天 |
| 关键词只有模型随口给的几个，越复习越窄 | 模型 / 缩写 / 标题 / 本章 TF-IDF 四源融合，通用词过滤、父子术语互斥、来源可解释 |
| B 站一搜全是「中职英语」「考研英语」「ESP32」 | 锚词 → 术语表 → 负面词 → 领域锚定 → 两段式排序；宁缺毋滥，不达标只给搜索链接 |
| 视频很长，不知道看哪一段 | 有登录态时读字幕，按锚词密度定位 `?p=N&t=秒`；没有字幕就只按标题/分 P 打分 |
| 「看得懂但不会做」 | 常考度 F + 实时难度 D 选题，强化期强制混排 2–3 类题型 |
| 答案抄答案文件，错了不知道 | 确定性校验脚本；官方与重算冲突先标「待确认」，用户确认后再决定以哪边为准 |
| 模型编页码、编 BV 号 | 链接只从检索缓存来；`audit` 检查每个 BV 是否有缓存证据；来源标签必须能追到文件/页 |
| 换会话就丢进度 | `study_state.json` 单文件 + 📍 进度行 + 错题重测 |

## 四个核心增量

1. **B 站相关性检索**：不是「搜到就算」，而是锚词覆盖 + 负面词 + 领域锚定 + 字幕验证 + 阈值淘汰。
2. **按天数 & 科目自研调整**：`--exam-date` 决定阶段比例；`N≤3` 自动急救模式；材料领域自动识别；科目词汇表可扩展。
3. **实时高难度点 & 常考题型专练**：每次作答后重算 D；题型常考度 F 来自去重后的试卷统计；专练按 F/D 交错。
4. **每天知识点后挂 B 站链接**：每个知识点最多 1–2 条，放在该知识点总结之后、专练之前，标注「做完题仍卡住再看」。

## 快速开始

需要 Python 3.10+，无第三方依赖。可选安装 `pypdf` / `python-docx` / `python-pptx` 以解析 PDF/DOCX/PPTX。

```bash
# 1) 建工作区（材料可给多个文件/目录；考试日当天不排任务）
python scripts/coach.py --workspace review-sprint-workspace init \
  --course "计算机系统基础" --exam-date 2026-11-24 \
  --materials "D:/课程/课件" "D:/课程/真题" \
  --daily-minutes 120 --target 90

# 2) 看状态、排期、质检
python scripts/coach.py status --workspace review-sprint-workspace
python scripts/coach.py plan --workspace review-sprint-workspace
python scripts/coach.py audit --workspace review-sprint-workspace

# 3) 每天拿学习包（已存在时不覆盖；要重生成加 --force）
python scripts/coach.py today --workspace review-sprint-workspace

# 4) 给某个知识点找 B 站视频
python scripts/coach.py bilibili --workspace review-sprint-workspace --kp K1 --limit 2

# 5) 记录作答（自动更新错题本、D 分、FSRS）
python scripts/coach.py answer --workspace review-sprint-workspace \
  --qid P1-Q1 --result wrong --confidence 3 --cause concept

# 6) 导出
python scripts/coach.py export --workspace review-sprint-workspace --format md,ics,anki
```

Windows 用 `py -3 scripts/coach.py ...`。若机器上 `python` 是 Microsoft Store 占位符，用自带启动器：`scripts\coach.cmd ...`；macOS/Linux 用 `bash scripts/coach.sh ...`。启动器会自动找 `DSH_PYTHON`、DSH 内置 Python 或系统 Python。安装到 DSH：

```powershell
Copy-Item -Recurse review-sprint "$env:USERPROFILE\.dsh\skills\review-sprint"
```

安装到 Claude Code：`~/.claude/skills/review-sprint/`；其他 agent 放各自的 skills 目录。

## 命令

| 命令 | 作用 |
|---|---|
| `init` | 导入材料、分类、切章、抽题、配对答案、建知识点、排期 |
| `status` | 📍 进度行、到期复习、错题、排期问题 |
| `plan` | 生成/重建排期与排期表 |
| `today` | 生成当天 Markdown 学习包（默认不覆盖已有文件；`--force` 重生成） |
| `done` | 把某天标记为完成 |
| `answer` | 记录作答（可 `--date` 补录）；更新错题、D、FSRS |
| `review` | 单独记录一次知识点复习（1–4 评分） |
| `quiz` | 错题优先 + 常考度抽题 |
| `keywords` | 四源关键词融合结果（带来源） |
| `bilibili` | 检索、打分、缓存、输出真实链接 |
| `types` | 题型矩阵 + 常考度 F |
| `weights` | 知识点权重、考纲/重点证据、D |
| `calc` | 补码/IEEE-754/标志位/ModRM/机器码，或 choice/exact/numeric |
| `set-check` | 给题目绑定确定性校验规则（写入前先执行校验） |
| `recompute` | 按规则重算并与官方答案比对；冲突标 pending |
| `resolve-conflict` | 确认冲突以官方或重算为准 |
| `audit` | 质检门禁（排期、链接、来源、未处理冲突） |
| `reclassify` | 手动改材料分类（不自动重算章节） |
| `domains` | 列出内置领域与题型数 |
| `export` | Markdown / ICS / Anki CSV |
| `doctor` | 环境、依赖、Cookie 状态 |
| `set` | 改考试日期/预算/目标/密度并重排 |
| `add-question` | 向题库加入一道题（模型补题用） |
| `sources` | 列出知识点与来源标签 |

## 每日产出结构

1. 📍 进度行（阶段、到期复习、剩余天数、下一步）
2. 开场回忆（闭卷，信心 0–3）
3. 今日知识点（K 编号、来源页、来源标签）
4. 难点精讲（D 分前 3：具体错法、易混对、最小例题）
5. B 站补课（每个知识点后，1–2 条，带匹配理由）
6. 题型专练（4 基础 + 2 真题 + 1 拔高，交错）
7. 错因分类（概念/计算/审题/记忆/时间）
8. 速记表 + 睡前 3 题 + 明日预告
9. 参考答案与解析（先题后答，冲突注明）

## 排期与算法

### 三阶段

| 阶段 | 占比 | N=20 | 内容 |
|---|---|---|---|
| 诊断 | 第 1 天 | 第 1 天 | 诊断卷，按章节/题型测底 |
| 构建 | 40% | 第 1–8 天 | 新知识点 + 完整样例 + 基础题 |
| 强化 | 35% | 第 9–15 天 | 题型矩阵专练、交错、错题 |
| 冲刺 | 25% | 第 16–20 天 | 整卷模拟、错题、速记表；最后 1 天模拟 |

`N = 考试日 − 开始日`，**考试当天不排学习任务**；`N≤3` 取消构建期，按常考度 F 保留高价值题型，并明确告知放弃了什么。

### FSRS + 考试截止

```
R(t,S) = (1 + F·t/S)^C,  F = 19/81, C = -0.5
I(r,S) = S/F · (r^(1/C) − 1),  r=0.9 时 I=S
```

- 评分映射：答错 = Again；答对但信心 0–1 = Hard；信心 2 = Good；信心 3 = Easy。
- 若下次复习日越过考试日，改排到考前 1–3 天。
- 知识点在 3 个不同日子答对才标「掌握」；同一天多次只计 1 次。
- 答错后连续两个不同日子答对，错题才关闭。

### 难度 D 与常考度 F

```
D = 加权平均(往年失分率, 用户错误率, 前置深度, 易错标记)
F = 出现该题型的去重试卷数 / 去重后试卷数 × 平均分值权重 × 近年加权
```

- 没有证据的项不参与 D 的加权平均（例如还没作答时不把用户错误率当成 0.5）。
- `steps` 由题目分值折算；前置深度按依赖链递归计算，不再固定 0/1。
- 权重是初值，放在 `settings.difficultyWeights`，可用真实作答回看调整。

### 负载控制

- 每天预算 `--daily-minutes`，每类题有预估用时。
- 复习优先保留，先减少新题；单日复习超过 `maxReviewsPerDay` 的部分进入 `reviewOverflow` 并显式提示。
- 计划只重排未来；`plan --rebuild` 不会把已做过的题重新排进来。

## B 站检索

### 五层过滤

1. 锚词：每个知识点 1–2 个必须出现的核心术语。
2. 术语表：课程领域词表，用于扩展查询与打分。
3. 负面词：跑题词黑名单，命中即淘汰。
4. 领域锚定：识别 C++/Python/CS 系统/数学等，淘汰跨领域结果。
5. 两段式排序：先相关度过滤（默认 0.5），再质量排序。

### 字幕与时间点

- 搜索 → 详情（`pages[]`）→ 播放器（`subtitles[]`）→ 字幕 JSON。
- 有字幕时按锚词密度找 120 秒窗口，链接带 `?p=N&t=秒`；**字幕只加分，不会让有字幕的视频比无字幕时得分更低**。
- 未登录通常没有字幕；此时只按标题/分 P/简介打分，不编时间点。
- `auth_key` 过期时，回退到 `i0.hdslb.com` 去 query 的匿名路径。

### 安全与风控

- Cookie 只从 `BILIBILI_COOKIE` 环境变量或 `--cookie-file` 读取；不写状态、不写日志、不进 Git。
- 只调用只读接口；限速默认 1 req/s；缓存 7 天；失败指数退避。
- 常见状态码：`-352` 风控、`-412` IP 拦截、`-799` 频率、`-400`/`-403`/`-404` 参数/权限。
- 缺 Referer 时可能返回 `code=0` 但只有 `v_voucher` 的软拦截；客户端会识别并报错，不当作成功。
- **证书校验失败不会自动降级**：用 `--ca-file` 指定代理根证书；确需关闭校验时用 `--insecure`，该模式不发送 Cookie。403/412 时用系统 curl 重试必须显式 `--allow-curl`，并自行承担风控/服务条款风险。

> 接口细节与 2026 年现状见 [`references/bilibili-api.md`](references/bilibili-api.md)。

## 工作区

```
review-sprint-workspace/
├─ study_state.json        # 唯一状态：课程/考试/材料/章节/KP/题库/排期/错题/视频
├─ materials/              # 原始材料副本（只读）
├─ chapters/CH*.md         # 章节正文
├─ daily/D01-*.md          # 每日学习包
├─ exports/                # 排期/速记表/ICS/Anki
├─ .cache/bilibili/        # 检索与字幕缓存（含 BV 证据）
└─ setup_report.json       # 导入报告
```

状态字段见 [`references/state-schema.md`](references/state-schema.md)。

## 答案重算覆盖

- 补码/原码/反码/移码、位宽转换、符号/无符号解释；
- IEEE-754 单/双精度编码与解码；
- `add`/`sub` 的 CF/OF/SF/ZF/AF/PF；
- ModRM 字节；
- 常用 x86-64 指令编码（mov/lea/add/sub/cmp/xor/push/pop/jmp/call/ret/nop/syscall）。

```bash
python scripts/coach.py calc --kind twos --value -5 --bits 8
python scripts/coach.py calc --kind ieee754 --value -6.5 --ieee-bits 32
python scripts/coach.py calc --kind flags --op sub --a 5 --b 7 --bits 8
python scripts/coach.py calc --kind modrm --mod 1 --reg 0 --rm 4
```

未覆盖的题：`set-check` 无法绑定就不标已核验，解析里标 ⚠️ 由模型给出。

## 测试

```bash
python -m unittest discover -s tests -v
```

46 个测试覆盖：关键词四源、排期硬约束、FSRS、B 站 WBI/过滤/缓存、题目去重、答案桶、冲突处理、错题关闭、领域切换、DOCX/PPTX 解析、CLI 端到端。

## 与已有开源 skill 的关系

调研时参考了这些同题项目的**设计取舍**，但没有复制代码：

- [ZeKaiNie/universal-examprep-skill](https://github.com/ZeKaiNie/universal-examprep-skill)：单状态文件、来源标签、作业/答案配对、错题优先、进度行。
- [limpidwei/final-exam-review](https://github.com/limpidwei/final-exam-review)：8 类材料分类、考纲优先、三档密度、章节考点速记、只读导入。
- [yoli-mi/good-learning](https://github.com/yoli-mi/good-learning)：知识清单与计划分离、每日课程、错题本字段、LaTeX PDF。
- [serenakeyitan/open-exam-skills](https://github.com/serenakeyitan/open-exam-skills)：citation-check 的核验思路。
- [SocialSisterYi/bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)：B 站接口文档（2026-01 已归档；接口事实仍有效）。

本项目的差异点在：**四源关键词融合 + B 站五层过滤/字幕定位 + 按本课题型矩阵 + 答案重算/冲突确认 + 三册同题号/页码零误差**。完整对照见 [`docs/skill-survey.md`](docs/skill-survey.md)。

## 已知限制

- 扫描 PDF / 图片需要 OCR 或视觉模型；未配置时标「待转换」，不假装读到。
- 未登录 B 站通常无字幕，时间点定位不可用；只做标题/分 P 级匹配。
- 试卷题型自动分类是启发式，模型可用 `add-question --type` 修正。
- 复杂表格、公式图、代码截图仍可能解析不全；需要人工复核来源。
- `audit` 只能证明「链接有缓存、来源有文件」，不能证明「讲解一定正确」。

## License

MIT。示例材料为合成数据；不要把你自己的课件、试卷、Cookie 提交到仓库。
