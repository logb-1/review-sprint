# 真实评测协议

目标不是证明“单测通过”，而是回答三个问题：

1. **计划能不能执行**：计划里的题位是否都有题，还是每天让模型现场编？
2. **内容能不能核对**：答案、步骤、rubric、原文引用是否真的存在且能回查？
3. **图/公式有没有丢**：课件里的图、PDF 里的公式页有没有进五册？

## 三门真实课（不要用合成题代替）

| 课程 | 取材重点 | 要验证 |
|---|---|---|
| 高等数学 | 公式、函数图、极限/积分步骤 | 公式转写、图进册、步骤 rubric |
| 电路 / 医学 | 电路图、解剖图、表格 | PPTX 图片、图注、图→页→KP |
| 法学 / 文科 | 长文本、法条、案例 | 长文引用、页码、主观题评分点 |

每门课至少包含：课件、1 套往年题、1 份答案/评分标准；记录材料页数、题数、图数。

## 跑法

先按 `SKILL.md` 完成 build 和真实模型 fill（**不要**用测试占位内容），然后：

```bash
python eval/run_eval.py \
  --workspace math=C:/runs/math \
  --workspace circuits=C:/runs/circuits \
  --workspace law=C:/runs/law \
  --out eval/report.json
```

脚本只读工作区，不调用模型，输出 10 项指标：

| 指标 | 通过线 | 说明 |
|---|---|---|
| placeholders | 0 | 五册剩余 `<!-- MODEL -->` |
| needsGeneration | 0 | 计划中无题可用的题位 |
| planExecutable | 100% | 有 qid 的 slot / 全部 slot |
| answerCoverage | 100% | 有答案或重算结果 |
| solutionCoverage | 100% | 有步骤/解析 |
| rubricCoverage | 100% | 有评分点列表 |
| citationHitRate | ≥90% | 按文件+页码抽样回查引文 |
| imageCoverage | 记录值 | 进册图片 / 材料图片；无图课程为 n/a |
| bookIdConsistency | 是 | 01/02/03/05 题号集合一致 |
| weakModelCompletion | 人工记录 | 弱模型按同一 `fill_tasks.json` 的完成率、错答率、耗时 |

`weakModelCompletion` 不能由脚本伪造：用同一份任务清单分别跑强/弱模型，人工抽检 30 条并记录。没有真实 run 就写“未测”，不要写百分比。

## 结果怎么写

- `eval/report.json` 原样保留；README 只贴真实跑出的表。
- 引用命中率 <90%：先修页码/引文，不要改阈值。
- 图片进册率低：先看 `state.materials[].images` 是否有图；没有就是解析没抽到，不是排版问题。
- 计划可执行率低：先看 `fill_tasks.json` 是否有 `generate:<slotId>`；没有就是 scheduler 还在造无题题位。

## CI

CI 的 `build-artifacts` 只做**构建冒烟**（五册能生成、命令不 traceback），不冒充真实评测。真实评测需要课程材料和模型，结果进 `eval/report.json` 后再更新 README 表。
