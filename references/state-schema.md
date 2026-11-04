# `study_state.json` 字段

`schema: review-sprint/state@2`。单文件保存；所有派生文件（章节、每日包、缓存）都可从它重建。旧 `@1` 工作区首次加载时会自动补字段并升级。

`examDate` 是考试日；排期只覆盖 `examDate` 之前的 `N` 天，**考试当天没有学习任务**（最后学习日是考试前一天）。

## 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema` | string | 固定 `review-sprint/state@1` |
| `createdAt` / `updatedAt` | ISO string | 创建/更新时间 |
| `course` | string | 科目名 |
| `examDate` | `YYYY-MM-DD` | 考试日；排期以它为截止 |
| `startDate` | `YYYY-MM-DD` | 首次排期日 |
| `dailyMinutes` | int | 每天预算，默认 120 |
| `targetScore` | int | 目标分，用于急救模式取舍 |
| `language` | string | 输出语言 |
| `materials` | array | 导入材料与解析状态 |
| `chapters` | array | 章节与来源 |
| `knowledgePoints` | array | 知识点、D、FSRS、掌握状态 |
| `questionTypes` | array | 本课题型（CSAPP 16 / 通用 12） |
| `papers` | array | 去重后的试卷 |
| `questions` | array | 题库 |
| `schedule` | object | 每日槽位、复习项、质检数据 |
| `attempts` | array | 每次作答 |
| `mistakes` | array | 错题本 |
| `videos` | array | 已采纳的 B 站视频（带缓存证据） |
| `settings` | object | 权重、阶段比例、B 站参数 |
| `warnings` | array | 导入/排期警告 |

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
  "hasAnswers": false
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

正文存在 `chapters/CH1.md`，含 `【第N页】` 标记，用于来源页码。

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

`sameAs` 指向同源卷；统计常考度时只算一份。

## `questions[]`

```json
{
  "id": "P1-Q1",
  "paperId": "P1",
  "number": 1,
  "stem": "题干……",
  "section": "选择题",
  "type": "T2",
  "kind": "basic|past|advanced",
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
  "variantOf": null
}
```

- `steps` 由分值折算，用于 D 的往年失分项。
- `resolution`：`pending` 时 `audit` 拦截；`official`/`recomputed` 是用户确认后的结论。
- `variantOf` 表示数字变式（如 -5 vs -6），不按重复题丢弃。
- 题号在同一试卷内全局唯一；分节重号会自动加 `-2` 后缀。

## `schedule`

```json
{
  "builtAt": "2026-11-04",
  "totalDays": 20,
  "emergency": false,
  "coveredTypes": ["T1", "..."],
  "days": [
    {
      "day": 1,
      "date": "2026-11-04",
      "phase": "诊断期",
      "kpIds": [],
      "slots": [
        {"kind": "basic", "type": "T1", "qid": "P1-Q1", "minutes": 10, "status": "ready"}
      ],
      "reviews": [
        {"kpId": "K1", "title": "…", "interval": 1, "minutes": 5, "status": "planned", "D": 0.5}
      ],
      "reviewOverflow": [],
      "minutes": 90,
      "done": false,
      "doneAt": "",
      "warning": ""
    }
  ]
}
```

- `slots[].status`：`ready`（有题）/`needs_generation`（模型补题）。
- `reviews[]` 是间隔复习项；`due` 在 KP 的 FSRS 里。
- `warning` 记录负载控制/复习裁剪。

## `attempts[]` / `mistakes[]`

```json
{"date":"2026-11-04","questionId":"P1-Q1","correct":false,"confidence":3,"cause":"concept","timeSec":90,"note":"","retestDue":"2026-11-05"}
{"questionId":"P1-Q1","date":"2026-11-04","cause":"concept","highConfidence":true,"retestDue":"2026-11-05","resolved":false,"resolvedAt":"","resolvedBy":"","consecutiveCorrect":0}
```

- `confidence` 0–3；`cause`：`concept|calc|reading|memory|time|unknown`。
- 高信心错误（confidence ≥2）单独标记，次日必考。
- 答错刷新未解决错题；连续两个不同日子答对后才 `resolved=true`。

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
  "difficultyWeights": {"pastLoss": 0.35, "userError": 0.30, "prereqDepth": 0.20, "errorFlags": 0.15},
  "phaseRatios": {"build": 0.40, "reinforce": 0.35, "sprint": 0.25},
  "dailySlots": {"basic": 4, "past": 2, "advanced": 1},
  "mockSlots": {"mock": 10, "proof": 2},
  "minutesPerSlot": {"basic": 10, "past": 15, "advanced": 20, "mock": 12, "proof": 15, "review": 5},
  "maxReviewsPerDay": 6,
  "lastDayExtraMinutes": 30,
  "bilibili": {"enabled": true, "threshold": 0.5, "maxPerKp": 2, "cacheDays": 7, "rateSeconds": 1.0, "whitelist": []},
  "fsrs": {"targetRetention": 0.9, "F": 0.2345679, "C": -0.5, "examBufferDays": 3}
}
```
