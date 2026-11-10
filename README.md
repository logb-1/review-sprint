# review-sprint · 多种类科目考前冲刺

把一个科目的「课件 + 往年题 + 考纲」变成一条可执行的复习生产线：科目画像 → 用户指定 N 天 → 目标分量化掌握度 → 分天排期 → 主册/答案册/速记手册/刷题宝典 → 质检。

> 一个 agent skill：`SKILL.md` + 核心 CLI 零第三方运行时依赖（解析/输出按需装 `python-pptx` / `python-docx` / `pypdf`）+ 单文件状态。适配 DSH / Claude Code / Codex / Cursor 等支持 `SKILL.md` 的 agent。

## 它解决什么问题

| 常见失败 | 本 skill 的做法 |
|---|---|
| 题型只按 CSAPP 或“通用题库”硬套 | 每科一个画像：题型、单题分钟、判分方式、每日配比、阶段比例、复习间隔都由画像决定 |
| 复习计划只按固定天数模板，用户实际只有 5 天或 45 天 | **N 必须由用户给**；`N≤3` 急救、`4–7` 压缩、`8–30` 标准、`>30` 长线 |
| 目标分只是口号，不知道要掌握到什么程度 | 目标分 → L0–L4 掌握度 → 期望分/分钟贪心；放不下时给出可达分和放弃清单 |
| 每天 4+2+1，不问科目差异 | 画像 `dailyMix` + 当天预算反推题量；负载偏离 >15% 会被修正或明确提示 |
| 只有 Markdown，没有可打印的册子 | `build` 一条命令生成 5 份 MD + 5 份 DOCX；题号三册一致 |
| 答案抄答案文件，错了不知道 | 确定性校验脚本；官方/重算冲突先 pending，用户确认后 resolve |
| 模型编页码、编 BV 号 | 链接只从检索缓存来；来源标签必须追到文件/页；查不到写「待确认」 |
| 换会话就丢进度 | `study_state.json` + 📍 进度行 + 错题重测 + 掌握度等级 |

## 科目画像

内置 13 个画像，位于 `references/subjects/`：

| 画像 | 覆盖 |
|---|---|
| `cs_systems` | 计算机系统 / 组成 / OS |
| `programming` | C / C++ / Java / Python 程序设计 |
| `data_structures` | 数据结构与算法 |
| `math` | 高等数学 / 线代 / 概率统计 |
| `physics` | 大学物理 |
| `circuits` | 电路 / 模电 / 数电 |
| `chemistry_biology` | 化学 / 生物类 |
| `medicine` | 医学基础 |
| `law` | 法学 |
| `economics` | 经济 / 金融 / 会计 |
| `politics` | 政治 / 马原 / 思修类 |
| `foreign_language` | 外语类 |
| `general` | 兜底 |

每个画像至少包含：

| 字段 | 作用 |
|---|---|
| `questionTypes` | 题型 id、名称、预估单题分钟、判分方式（auto_exact / auto_numeric / rubric / recite） |
| `masteryWeights` | 理解 / 记忆 / 计算 / 应用权重 |
| `difficultyWeights` | D 的四项初值 |
| `dailyMix` | 基础 / 真题 / 拔高 / 背诵比例 |
| `phaseRatio` | 构建 / 强化 / 冲刺比例 |
| `reviewIntervals` | 首学后的复现间隔 |
| `masteryThresholds` | L2/L3/L4 正确率阈值 |
| `levelFactors` | L1–L4 单点用时系数（默认 0.55/1.0/1.55/2.15） |
| `cognitiveWeights` | 用时估算里的认知维度系数 |
| `practiceCounts` | L0–L4 每点练习量 |
| `safetyFactor` | 目标分安全系数 |
| `keywords` / `negative` | B 站检索领域词与负面词 |
| `checkers` | 该科允许的确定性校验器 |
| `typeKeywords` | 题型自动分类词（实际位置 `questionTypes[].keywords`） |

**新增科目**：复制一个 JSON，改 `subject / label / questionTypes / dailyMix / phaseRatio / levelFactors / ...`，每个数值写成 `{"value": 12, "_note": "依据..."}`；没有可靠依据时写 `"heuristic"`。内置 JSON 是唯一源文件；自定义画像放 `references/subjects/custom/`，同名会覆盖内置，不需要改 Python，也没有会重写 JSON 的生成器。

## 快速开始（一条 build）

需要 Python 3.10+；XML/PPTX 解析需要 `python-pptx`，DOCX 输出需要 `python-docx`（缺失时自动降级为只出 Markdown 并警告），PDF 文本层用 `pypdf`（缺失时标 `needs_ocr`，不中断）：

```bash
python -m pip install -r requirements-optional.txt

python scripts/coach.py --workspace review-sprint-workspace build \
  --course "高等数学" --subject math \
  --materials "D:/课程/课件" "D:/课程/课件.pptx" \
  --past-papers "D:/课程/往年题" \
  --target 85 --days 14 --daily-minutes 150 \
  --out review-sprint-workspace/output --format md,docx
```

`output/` 会生成：

```text
01-复习计划.md / .docx
02-主册.md / .docx
03-答案册.md / .docx
04-速记手册.md / .docx
05-刷题宝典.md / .docx
质检报告.md
_build/00_inputs.json ... audit.json
```

- `--target`、`--days` 缺任意一个，命令非零退出并打印需要询问的字段；模型不得自己填。
- 工作区已有 state 时 build 默认拒绝覆盖：保留作答/错题/掌握度用 `--refresh-materials`；确实重来用 `--force`（先备份 `study_state.<时间>.bak.json`）。
- 输入支持 PPTX / PDF / DOCX / MD / TXT；旧 `.ppt` 用 LibreOffice 先转 `.pptx`（没有则明确报错）。
- `--subject` 省略时按材料自动识别；置信度 <0.6 时命令非零退出，必须让用户确认候选。`--domain` 是旧别名。
- `--format` 至少包含 `md` 或 `docx`；只要 Markdown 可不装 python-docx。含 `pdf` 时调用 LibreOffice（`soffice`）。
- `--out` 可自定义；`_build/` 保存每一步中间结果，便于中断排查。
- `--json` 输出机器可读结果；退出码：0 成功、1 质检失败/占位符未填、2 需要用户输入、3 缺依赖/状态冲突。

### 五册不是最终稿：fill

脚本只填结构、来源、题号、F/D；讲解、口诀、解析、评分点、题型套路、题目→知识点映射会输出带 ID 的占位符；计划中没有现成题的题位会标 `D01-S02待生成`（题位号不是题号）：

```html
<!-- MODEL:main:K3 -->  <!-- MODEL:answer:P1-Q1 -->  <!-- MODEL:rubric:P1-Q1 -->
<!-- MODEL:cheatsheet:K3 -->  <!-- MODEL:drill:T2 -->  <!-- MODEL:kpMap:P1-Q2 -->
```

1. 读 `references/prompt-templates.md` 第 1–4 节。
2. `coach.py fill --tasks` 生成 `fill_tasks.json`；除 main/answer/rubric/cheatsheet/drill/kpMap 外，每个缺口题位有一项 `generate:<slotId>`。
3. 按 `{"tasks":{"main:K3":"...","generate:D01-S02":{"question":{"stem":"...","solution":"...","rubric":[{"point":"...","score":2}],"answer":"..."}}}}` 回填，运行 `coach.py fill --apply fill.json`。
4. `fill` 重渲染五册并重跑 audit；`needsGeneration=0`、占位符 0、答案/解析/评分点覆盖 100% 才算完成。
5. `coach.py next` 只给一个下一步；`coach.py sync` 重排+重渲染；`add-question --source model --slot D01-S02` 可单题补录。

真实课评测用 `eval/run_eval.py` 读已回填工作区，见 `eval/README.md`；脚本不调用模型，不伪造弱模型结果。

### N 天怎么分阶段

| N | 模式 | 行为 |
|---|---|---|
| 1–3 | 急救 | 取消构建期，按 F 保留高价值题型，明确列出放弃内容 |
| 4–7 | 压缩 | 构建 + 强化合并为「压缩期」，最后保留冲刺 |
| 8–30 | 标准 | 诊断 → 构建 → 强化 → 冲刺，比例由画像 `phaseRatio` 决定 |
| >30 | 长线 | 构建期拆成两轮，适合长周期证书/考研 |

阶段天数用最大余数法保证总和恰好等于 N；每日实际负载以 `dailyMinutes` 为中心，超过 ±15% 会移动题量或明确提示。

## 目标分 → 掌握度

- L0 放弃；L1 认识；L2 基础题 ≥70%；L3 真题 ≥80%；L4 变式/拔高 ≥85% 且 3 个不同日子答对。
- 每个考点 `期望分 = 平均分值 P × 出现率 F × 该等级得分率`；按“期望分 / 所需分钟”从高到低贪心，直到 `目标分 × safetyFactor`。
- 放不下时输出「可达最高预期分」「缺口」「放弃项与各丢多少分」，不静默降级。
- 同时输出往年题→知识点覆盖率；覆盖率低于 80% 时可达分按区间 `[low, high]` 看，避免把“抽漏知识点”当成高精度。
- 同时输出总任务量 W、日均分钟、预算与超预算分钟；`01-复习计划` 会列出。
- 输出 60 / 70 / 80 / 90 / 95 五档矩阵：所需考点等级、总分钟、每日分钟、每日题量；用户档位高亮。
- 作答后按 L0–L4 更新当前等级；FSRS 简化式、D 实时重算、错题关闭规则保留（**不是 FSRS-6 官方实现**，参数未拟合）。

## 阶段 B：每日循环

`build` 只生产册子，**不产生作答记录**。每天走：

```bash
coach.py status
coach.py next
coach.py today
coach.py answer --qid ... --result correct|wrong --confidence 0..3 --cause ... --seconds 90
coach.py done --day N
coach.py catch-up
```

原有命令全部保留：

```bash
# 建工作区；N 可由考试日推算，也可直接 --days
python scripts/coach.py --workspace ws init \
  --course "计算机系统基础" --subject cs_systems \
  --days 14 --materials "D:/课件" --past-papers "D:/真题" \
  --daily-minutes 120 --target 85

python scripts/coach.py --workspace ws status
python scripts/coach.py --workspace ws plan --rebuild
python scripts/coach.py --workspace ws today          # 默认不覆盖；--force 重生成
python scripts/coach.py --workspace ws answer --qid P1-Q1 --result wrong --confidence 3 --cause concept
python scripts/coach.py --workspace ws done --day 2
python scripts/coach.py --workspace ws export --format md,ics,anki
python scripts/coach.py --workspace ws audit
```

## 命令

| 命令 | 作用 |
|---|---|
| `build` | 一条命令：解析 → 识别科目 → 量化 → N 天排期 → 五册 MD/DOCX → audit |
| `next` | 只给一个下一步动作、命令和理由（generate/fill/today/answer/done） |
| `catch-up` | 列出已过期未完成的天数与补课入口 |
| `report` | 按错因聚合最近 N 天作答（`--days 7`，`--json`） |
| `sync` | 不重新解析材料，重排、重渲染五册并刷新质检 |
| `fill` | `--tasks` 出补写/生成清单；`--apply` 回填并重渲染 |
| `figure` | 把 PPTX/PDF 指定页渲染为 PNG（pypdfium2/PyMuPDF） |
| `init` | 导入材料、分类、抽知识点/题、配对答案、按画像排期 |
| `status` | 📍 进度行、科目、天数、目标、到期复习、错题、排期问题 |
| `plan` | 生成/重建排期（保留已完成日与已做过题） |
| `today` | 当天 Markdown 学习包（不覆盖已有文件） |
| `day` | 一次完成：进度 + 今日学习包 + 下一步建议 |
| `done` | 标记某天完成 |
| `answer` | 记录作答；更新错题、D、FSRS 简化式、掌握度 |
| `review` | 单独记录一次知识点复习（1–4 评分） |
| `quiz` | 错题优先 + 常考度抽题；`--diagnostic` 覆盖各题型 |
| `keywords` | 四源关键词融合结果 |
| `bilibili` | 检索、打分、缓存、输出真实链接 |
| `types` | 题型矩阵 + 常考度 F |
| `weights` | 知识点权重、考纲/重点证据、D |
| `calc` | 补码/IEEE-754/标志位/ModRM/机器码，或 choice/exact/numeric/matrix/determinant |
| `set-check` | 给题目绑定确定性校验规则（写入前先执行校验） |
| `recompute` | 按规则重算并比对官方答案；冲突标 pending |
| `resolve-conflict` | 确认冲突以官方或重算为准 |
| `audit` | 质检门禁（排期、五册题号、链接、来源、冲突、负载） |
| `reclassify` | 手动改材料分类（不自动重算章节） |
| `subjects` / `domains` | 列出内置画像与题型数 |
| `export` | Markdown / ICS / Anki CSV |
| `doctor` | 环境、依赖、Cookie 状态 |
| `set` | 改考试日期/天数/预算/目标/密度并重排 |
| `add-question` | 向题库加入一道题 |
| `sources` | 列出知识点与来源标签 |

## 五册内容

- **01-复习计划**：量化摘要、目标分矩阵、放弃项、按天表（日期/阶段/知识点/题号/分钟/目标等级）。
- **02-主册**：按章节/知识点；目标等级、来源页、F/D、易错点、最小例题；题目只放题号和题干。
- **03-答案册**：与主册/刷题宝典同题号；答案、步骤、评分点、校验状态（已核验 / 待确认 / 模型给出⚠️）。
- **04-速记手册**：每点 ≤5 行；按最后 3 个有知识点的学习日排序，可单独打印。
- **05-刷题宝典**：按画像题型分组；先“识别信号 → 解法套路”，再按基础→真题→拔高；只放题号、出处、年份、分值、F。

`audit` 会检查三册题号集合完全一致；来源页码只来自解析结果，查不到就写「待确认」。同时报告占位符数、待生成题位、答案/解析/评分点覆盖率、引用命中率、图片进册率、kp 映射率、未映射题、pending 冲突；任一硬门禁失败都属于「必须修复」。`--citations` 会按 `_build/citations.json` 抽样回查原文页码。

## 安装

只安装 skill 本体（`SKILL.md` + `SECURITY.md` + `scripts/` + `references/`，不含 tests/examples/docs/.github/.git）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-skill.ps1
```

```bash
bash scripts/install-skill.sh [目标目录]
```

默认装到 `~/.dsh/skills/review-sprint`；Claude Code 用 `~/.claude/skills/review-sprint`，其他 agent 放各自 skills 目录。`tests/`、`examples/`、`docs/`、`.github/` 是仓库开发内容，不随 skill 安装。

发布包与校验和：

```bash
python scripts/package_skill.py --out dist
# dist/review-sprint-skill-0.4.3.zip
# dist/review-sprint-skill-0.4.3.zip.sha256
```

## 开发与测试

```bash
python -m compileall -q scripts tests eval
python -m unittest discover -s tests -v
python -m coverage run -m unittest discover -s tests -q && python -m coverage report --include="scripts/*"
python scripts/check_build.py --out-root artifacts   # draft examples；build 退出 1 是预期，脚本会核对五册/待生成任务
```

测试覆盖：画像加载/必填字段/每个数值 `_note`、科目切换、自动识别与低置信度、N=1/3/5/7/10/14/20/30/45 的阶段与负载、目标 60 vs 90 单调、容量不足的放弃清单、旧状态迁移、build 两科目 5×2 文件与三册题号一致、fill/next/sync/add-question、引用回查、待生成题位、DOCX 行内样式/页码、PPTX/DOCX 图片落盘、CLI surface。当前 71 项测试；CI 覆盖 Python 3.10/3.11/3.12/3.13 × Windows/Ubuntu，coverage 门槛 50%，examples 构建 job 在 Windows 跑并上传 artifact。

## 已知限制

- 扫描 PDF/纯图片页需要 OCR 或视觉模型；未配置时标「待转换」，不假装读到。`figure` 只做页面渲染，不做公式识别。
- 未登录 B 站通常无字幕，时间点定位不可用；只做标题/分 P 级匹配。
- 题型自动分类是关键词启发式，模型可用 `add-question --type` 修正。
- 复杂表格、公式图、代码截图仍可能解析不全；PPTX/DOCX 内嵌位图会进册，OMML 公式会抽取为线性文本（如 `x^2+1`）但不自动排成可编辑公式，必要时用 `figure` 渲染成图后人工核对。
- `build` 的 DOCX 是可编辑底稿；公式排版、目录页码仍需 Office/LibreOffice 精修（TOC 需 F9）。
- `audit` 只能证明「链接有缓存、来源有文件、题号一致、引用能回查、内容非空话」，不能证明「讲解一定正确」。
- 真实课 eval 需要三门已回填工作区与弱模型 run；仓库只提供测量脚本和协议，不附带伪造结果。

## License

MIT。示例材料为合成数据；不要把你自己的课件、试卷、Cookie 提交到仓库。


