# 质检门槛与回归测试

## 1. 自动门禁（`coach.py audit`）

| 类别 | 检查 | 失败级别 |
|---|---|---|
| 排期 | `days` 与 `schedule.days` 长度一致；不含考试日 | 必须修复 |
| 排期 | 每类覆盖题型 ≥3 次且 ≥3 个不同天（急救 ≥2/≥2；单日 ≥1） | 必须修复 |
| 排期 | 每天用时与 `dailyMinutes` 偏差 ≤15%（画像态）；旧工作区按旧预算规则 | 必须修复 |
| 负载 | 记录总任务量 W、日均、预算与超预算分钟；超预算要提醒 | 提醒 |
| 排期 | 最后学习日有整卷模拟（题量按画像 `mockQuestions`） | 必须修复 |
| 复习 | 所有复习日 < 考试日；超上限的进 `reviewOverflow` | 必须修复 |
| 五册 | 02 主册 / 03 答案册 / 05 刷题宝典的题号集合完全一致，零缺失零多余 | 必须修复 |
| 五册 | `<!-- MODEL:... -->` 占位符为 0；否则先 fill | 必须修复 |
| 五册 | 答案覆盖率、kp 映射率、未映射题数写进报告；覆盖率 <80% 提醒 | 提醒 |
| 五册 | 三册文件存在；来源页码只来自解析结果 | 必须修复 / 提醒 |
| 答案 | 冲突 `resolution=pending` 必须处理；`official`/`recomputed` 只提醒 | 必须修复 |
| 答案 | `check.kind` 必须在画像 `checkers` 内 | 提醒 |
| 链接 | 渲染文本中的每个 BV 都在 `videos[]` 或 `.cache/bilibili` | 必须修复 |
| 来源 | 每个 K 点有文件/页或标「待确认」 | 提醒 |
| 材料 | 未解析材料要列出状态与原因 | 提醒 |
| 覆盖 | 每个题型至少一道题；每个章节至少一个 K 点 | 提醒 |

`audit` 退出码：0 = 无「必须修复」；1 = 有问题。

## 2. 测试门槛（`python -m unittest discover -s tests -v`）

| 测试 | 断言 |
|---|---|
| 画像 | 13 个画像可加载；必填字段齐全；每个数值有 `_note`；dailyMix/phaseRatio 不是整份复制 |
| 科目切换 | 同一批合成材料用 math/law/politics 排期，题型分组、每日配比、复习间隔确实不同 |
| 科目识别 | 数学/法学材料分别识别为 math/law；低置信度返回 `needsConfirmation` |
| N 天 | N=1,3,5,7,10,14,20,30,45：阶段天数总和=N；负载偏差 ≤15% 或 warning；validate 无问题 |
| 阶段模式 | `N≤3` emergency、4–7 compressed、8–30 standard、>30 long |
| 量化 | 同一份往年题 target=60 与 90，掌握度/题量单调；放不下时输出可达分与放弃清单 |
| 旧状态 | `@1/@2` 能读取并补齐 `subject / mastery / quantification / days` |
| 构建 | 合成 PPTX + 往年题，math 与 law 各跑一次；5 份 × md+docx；三册题号一致；fill 后 audit 通过 |
| 构建 | build 已有 state 默认拒绝；--refresh-materials 保留 attempts；--force 先备份 |
| 构建 | 同名材料不会互相覆盖；build 缺字段 JSON 输出 needsInput |
| 构建 | --format md 只出 Markdown；占位符 >0 时 audit 必须失败 |
| 缺字段 | build 缺 target/days 非零退出，并打印需要询问的字段 |
| 排期 | 考试日不排；每类 ≥3 次 × ≥3 天；最后一天有模拟；每天不超预算 |
| FSRS | 稳定性单调、due 不越考试日 |
| 关键词 | 四源来源可解释；`x86-64` 不被长度过滤；父子互斥；不足用标题兜底 |
| B 站 WBI | 官方 mixin 向量与 `w_rid` 向量一致 |
| B 站过滤 | 负面词/跨领域结果被淘汰；主锚词必须命中 |
| B 站链接 | 输出 BV 必须来自 fixture 检索；不出现未检索的 BV |
| B 站评分 | 字幕只加分；有字幕不会低于无字幕 |
| B 站 TLS | `--insecure` 与 Cookie 同时使用直接拒绝 |
| 字幕 | 窗口定位从第一个命中 cue 开始 |
| 答案比对 | `0xFB`/`FB`/`251` 与 twos 重算一致；flags 部分匹配；choice/numeric/exact/matrix/determinant |
| 冲突 | pending 阻塞 audit；resolve 后 audit 通过 |
| 错题 | 连续两个不同日子答对才关闭 |
| 解析 | DOCX/PPTX 可读；Markdown 页码标记；代码块里的 `#` 不当章节；PPTX 短页可切章 |
| 分类 | 答案文件不被当成试卷；复习指南不被当成试卷；文件名误分类 |
| 题目 | 分节重号自动加后缀；答案按出现顺序分桶；数字变式不被去重 |
| CLI | init → status → plan → today（不覆盖）→ done → answer → set-check → recompute → resolve → audit → export 全绿 |
| build | 缺 target/days 返回字段清单；两科目 5×2 产物；题号一致；docx 依赖缺失时降级 md |

当前共 66 项测试（原有 46 项全部保留）。

## 3. 抽检（人工/模型）

- 任选 3 天：每个 K 点的〔原文〕标签能否在对应文件页码找到？
- 任选 3 条 B 站链接：BV 号、分 P、时间点是否与接口返回一致？
- 任选 3 道有官方答案的题：重算结果与解析是否一致？冲突题是否写明最终采用哪边？
- 五册：02/03/05 题号是否一一对应？03 的校验状态是否与脚本证据一致？
- 目标矩阵：60/70/80/90/95 是否随目标提高而掌握等级/分钟单调？放不下时有没有放弃清单？
- 急救/压缩/长线：是否明确说明砍掉/合并了什么？
- 弱模型跑一天：有没有编造命令、链接、页码？

## 4. 失败降级

| 失败 | 允许的降级 | 禁止 |
|---|---|---|
| 无网络 | 只给搜索链接 | 编 BV 号 |
| 无 Cookie/无字幕 | 标题/分 P 打分，不给时间点 | 编时间点 |
| 证书失败 | `--ca-file` 或显式 `--insecure`（不带 Cookie） | 自动降级并继续带 Cookie |
| 扫描 PDF | 标「待 OCR」 | 假装读到 |
| 旧版 Office | 标「待转换」 | 假装解析成功 |
| 无 python-docx | 降级只出 md 并警告 | 声称已输出 docx |
| 无校验脚本 | 标 ⚠️ 未核验 | 声称已重算 |
| 官方与重算冲突 | 标 pending，用户确认后 resolve | 静默抄官方或静默改答案 |
| 时间放不下 | 给可达分 + 放弃清单 | 静默降低目标/删考点 |

## 5. 发布前清单

- [ ] `SKILL.md` frontmatter `name` 与目录名一致，description 写「多种类科目」
- [ ] `python -m compileall scripts tests` 通过
- [ ] 66 项单元测试全绿
- [ ] CI 覆盖 Python 3.10/3.11/3.12，build-artifacts 上传五册
- [ ] 合成 math/law 示例 `build` 各一次，5×md+docx，audit 无「必须修复」
- [ ] 不含真实课件/试卷/Cookie/个人路径
- [ ] 版本号、CHANGELOG 同步（1.0.0）
- [ ] `references/subjects/*.json` 每个数值有 `_note`


