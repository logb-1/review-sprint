# 自定义科目画像

把 `<subject>.json` 放在这里即可覆盖/新增画像；内置 JSON 是唯一源文件，没有生成器会重写它们。

必填字段见 `scripts/review_sprint/subjects.py` 的 `REQUIRED_FIELDS`；每个数值写成 `{"value": 12, "_note": "heuristic"}`，有真实依据才写依据。
