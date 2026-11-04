# `study_state.json` 字段

`schema: review-sprint/state@3`。单文件保存；章节正文、每日包、缓存、五册都可从它重建。旧 `@1/@2` 首次加载时补齐字段并升级；旧工作区保留 `subjectSource="legacy"` 的兼容排期行为。

`examDate` 是考试日；排期只覆盖之前的 `N` 天，**考试当天没有学习任务**。`days` 是用户输入的 N；`N = examDate − startDate` 仅在未显式给 N 时用于旧式 init。

## 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema` | string | 固定 `review-sprint/state@3` |
| `createdAt` / `updatedAt` | ISO string | 创建/更新时间 |
| `course` | string | 科目名 |
| `subject` | string | 画像 id，如 `math` / `law` / `cs_systems` |
| `subjectConfidence` | number | 自动识别置信度；用户指定为 1.0 |
| `subjectSource` | string | `auto` / `user` / `legacy` |
| `subjectProfile` | object | 画像快照（含 `_note` 的原始 JSON）；避免换版本后解释漂移 |
| `examDate` | `YYYY-MM-DD` | 考试日；排期截止 |
| `startDate` | `YYYY-MM-DD` | 首次排期日 |
| `days` | int | 用户确认的复习天数 N |
| `dailyMinutes` | int | 每天预算，默认 120 |
| `targetScore` | int | 目标分 0–100 |
| `mastery` | object | `kpId -> {targetLevel,currentLevel,expectedScore,minutes,questionCount,accuracy,correctDays}` |
| `quantification` | object | 目标分量化结果（见下） |
| `workload` | object | 总任务量 W、学习/练习/复习/模拟分钟、日均、预算、超预算 |
| `build` | object | `{out,formats,completedAt,files,auditOk}` |
| `language` | string | 输出语言 |
| `materials` | array | 导入材料与解析状态 |
| `chapters` | array | 章节与来源 |
| `knowledgePoints` | array | 知识点、D、FSRS、掌握状态 |
| `questionTypes` | array | 本课题型（来自画像，含 minutes/grading/keywords） |
| `papers` | array | 去重后的试卷 |
| `questions` | array | 题库 |
| `schedule` | object | 每日槽位、复习项、质检数据 |
| `phasePlan` | array | 阶段明细（`day/phase`），长度 = N |
| `attempts` | array | 每次作答 |
| `mistakes` | array | 错题本 |
| `videos` | array | 已采纳的 B 站视频 |
| `settings` | object | 复习上限、FSRS、B 站参数 |
| `warnings` | array | 导入/排期警告 |

## `mastery{}`

```json
{
  "K1": {
    "targetLevel": "L3",
    "currentLevel": "L2",
    "expectedScore": 8.4,
    "minutes": 42.0,
    "questionCount": 3,
    "attempts": 4,
    "accuracy": 0.75,
    "correctDays": ["2026-11-05", "2026-11-07"],
    "completed": false,
    "updatedAt": "2026-11-07"
  }
}
```

- `targetLevel` 由 `quantify` 按目标分/预算贪心给出；`currentLevel` 由作答更新。
- L0 放弃 / L1 认识 / L2 基础 ≥70% / L3 真题 ≥80% / L4 变式 ≥85% 且 3 个不同日子答对；阈值可由画像覆盖。
- `questionCount` 是该等级需要的练习量（用于矩阵与每日题量反推）。

## `quantification{}`

```json
{
  "target": 85,
  "safetyFactor": 1.1,
  "requiredScore": 93.5,
  "maxScore": 95.0,
  "reachableScore": 93.5,
  "shortfall": 0.0,
  "budgetMinutes": 756.0,
  "totalMinutes": 620.0,
  "dailyMinutes": 44.3,
  "dailyQuestions": 1.4,
  "practiceQuestions": 20,
  "levels": {"K1": "L4", "K2": "L3", "...": "..."},
  "matrix": [
    {"target": 60, "required": 66.0, "achieved": 67.2, "minutes": 300, "dailyMinutes": 21.4, "dailyQuestions": 0.8, "levels": {"K1": "L2"}, "selected": false}
  ],
  "abandoned": [{"kpId": "K8", "title": "...", "lostScore": 2.3}],
  "stats": [{"kpId": "K1", "F": 1.0, "P": 10.0, "pastLoss": 0.4, "recentWeight": 1.2, "normalizedScore": 12.5}],
  "rates": {"L1": 0.3, "L2": 0.7, "L3": 0.85, "L4": 0.95},
  "thresholds": {"L2": 0.7, "L3": 0.8, "L4": 0.85}
}
```

`matrix` 固定给 60/70/80/90/95 五档；`selected` 标当前目标。放不下时 `shortfall>0` 且 `abandoned` 非空。

## `workload{}`

```json
{
  "totalMinutes": 1236,
  "learningMinutes": 380,
  "practiceMinutes": 240,
  "reviewMinutes": 60,
  "mockMinutes": 120,
  "days": 10,
  "dailyMinutes": 120,
  "dailyAverage": 123.6,
  "budgetMinutes": 1200,
  "overflowMinutes": 36
}
```

先有 W 再按 N 平均；`overflowMinutes>0` 时 `audit` 只提醒，不静默删任务。

## `materials[]`

```json
{
  "path": "绝对路径",
  "rel": "materials/chapter2.md",
  "category": "syllabus|keypoints|pastpaper|answers|homework|slides|notes|textbook|other",
  "categoryLabel": "考纲/大纲",
  "status": "ok|needs_ocr|needs_conversion|unsupported|error",
  "error": "",
  "chars": 1234,
  "hasAnswers": false,
  "categoryScores": {},
  "categoryEvidence": ""
}
```

## `chapters[]`

```json
{
  "id": "CH1",
  "title": "数据的机器级表示与处理",
  "source": {"file": "materials/chapter2.md", "pageStart": 12},
  "sources": [{"file": "materials/chapter2.md", "pageStart": 12}],
  "textFile": "chapters/CH1.md"
}
```

正文存在 `chapters/CH1.md`，含 `【第N页】` 标记；PPTX 每页标题/正文/备注都进正文，来源标到「文件名 第 X 页」。

## `knowledgePoints[]`

```json
{
  "id": "K1",
  "title": "整数的补码表示",
  "chapter": "CH2",
  "keywords": ["补码", "整数"],
  "anchors": ["补码", "整数"],
  "prereq": ["K0"],
  "source": {"file": "materials/chapter2.md", "page": 12},
  "D": 0.5,
  "difficultyParts": {"pastLoss": 0.5, "userError": null, "prereqDepth": 0.1, "errorFlags": 0.0, "evidence": ["pastLoss", "prereqDepth"]},
  "weight": 1.25,
  "syllabusLevel": 0.75,
  "emphasis": true,
  "weightReason": "考纲等级 0.75；重点/必考",
  "examFreq": 0.5,
  "fsrs": {"difficulty": 5.0, "stability": 1.0, "due": "2026-11-05", "lastReview": ""},
  "correctDays": ["2026-11-05", "2026-11-07"],
  "mastered": false
}
```

## `papers[]`

```json
{
  "id": "P1",
  "sourceFile": "materials/真题_2023-2024-1_A卷.txt",
  "title": "真题_2023-2024-1_A卷",
  "sameAs": null,
  "year": 2023,
  "chars": 6611
}
```

`sameAs` 指向同源卷；统计常考度只算一份。

## `questions[]`

```json
{
  "id": "P1-Q1",
  "paperId": "P1",
  "number": 1,
  "stem": "题干……",
  "section": "选择题",
  "type": "T2",
  "kind": "basic|past|advanced|recite",
  "points": 10,
  "steps": 5,
  "page": 2,
  "sourceFile": "materials/真题_....txt",
  "sourceType": null,
  "officialAnswer": "B",
  "answerSource": "materials/真题_..._答案.txt",
  "recomputed": {"kind": "flags", "CF": 1},
  "conflict": "",
  "resolution": "same|pending|official|recomputed",
  "resolutionNote": "",
  "resolvedAt": "",
  "finalAnswer": null,
  "check": {"kind": "twos", "value": -5, "bits": 8},
  "kpIds": ["K1"],
  "duplicateOf": null,
  "variantOf": null,
  "modelGenerated": false
}
```

- `resolution=pending` 时 `audit` 拦截；`official`/`recomputed` 是用户确认后的结论。
- `type` 必须来自当前画像 `questionTypes[].id`；无画像题标「未分组」。
- `check.kind` 必须在画像 `checkers` 内；`matrix/determinant` 是数学画像的确定性校验器。

## `schedule`

```json
{
  "builtAt": "2026-11-04",
  "totalDays": 14,
  "emergency": false,
  "mode": "standard|compressed|long|emergency",
  "coveredTypes": ["T1", "..."],
  "phaseRatio": {"build": 0.4, "reinforce": 0.35, "sprint": 0.25},
  "days": [
    {
      "day": 1,
      "date": "2026-11-04",
      "phase": "诊断期",
      "kpIds": [],
      "slots": [
        {"kind": "basic", "type": "T1", "qid": "P1-Q1", "minutes": 10, "status": "ready|needs_generation|recite"}
      ],
      "reviews": [{"kpId": "K1", "title": "…", "interval": 1, "minutes": 5, "status": "planned", "D": 0.5}],
      "reviewOverflow": [],
      "minutes": 112,
      "loadDeviation": -0.067,
      "done": false,
      "doneAt": "",
      "warning": ""
    }
  ]
}
```

- `slots[].status`：`ready` 有题 / `needs_generation` 模型补题 / `recite` 背诵槽（无题号）。
- `reviews[]` 是间隔复习项；`due` 在 KP 的 FSRS 里。
- `loadDeviation` 是相对 `dailyMinutes` 的偏差；`audit` 要求 |偏差| ≤ 15%。
- `reviewOverflow` 记录因单日上限/负载被移出的复习，不静默丢。

## `attempts[]` / `mistakes[]`

```json
{"date":"2026-11-04","questionId":"P1-Q1","correct":false,"confidence":3,"cause":"concept","timeSec":90,"note":"","retestDue":"2026-11-05"}
{"questionId":"P1-Q1","date":"2026-11-04","cause":"concept","highConfidence":true,"retestDue":"2026-11-05","resolved":false,"resolvedAt":"","resolvedBy":"","consecutiveCorrect":0}
```

- `confidence` 0–3；`cause`：`concept|calc|reading|memory|time|unknown`。
- 高信心错误（confidence ≥2）单独标记，次日必考。
- 答错刷新未解决错题；连续两个不同日子答对后才 `resolved=true`。
- `answer` 同时更新 `mastery[kpId].currentLevel`。

## `videos[]`

```json
{
  "kpId": "K1",
  "bvid": "BV1xx411c7mD",
  "title": "…",
  "author": "…",
  "play": 120000,
  "page": 1,
  "start": 10,
  "end": 15,
  "link": "https://www.bilibili.com/video/BV1xx411c7mD?t=10",
  "score": 0.97,
  "reason": "标题命中 2/2…",
  "anchors": ["补码", "整数"],
  "fetchedAt": 1793770376
}
```

`audit` 只信任 `videos[]` 或 `.cache/bilibili/*.json` 中出现的 BV。

## `settings`

```json
{
  "density": "concise|standard|detailed",
  "maxReviewsPerDay": 6,
  "lastDayExtraMinutes": 30,
  "bilibili": {"enabled": true, "threshold": 0.5, "maxPerKp": 2, "cacheDays": 7, "rateSeconds": 1.0, "whitelist": []},
  "fsrs": {"targetRetention": 0.9, "F": 0.2345679, "C": -0.5, "examBufferDays": 3}
}
```

画像里的 `difficultyWeights / phaseRatio / dailyMix / kindMinutes / reviewIntervals / mockQuestions` 优先于旧 `settings` 字段；旧工作区没有画像时回退到 `settings` 的兼容值。
