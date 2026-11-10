#!/usr/bin/env python3
"""Evaluate one filled review-sprint workspace against the quality gates.

The script does not call an LLM. It measures the artifacts that a real run
produced, so a weak-model smoke test can be compared with a strong-model run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from review_sprint.audit import audit  # noqa: E402
from review_sprint.books import book_question_ids  # noqa: E402
from review_sprint.state import load_session  # noqa: E402

IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _book_dir(session) -> Path:
    return Path(session.state.get("build", {}).get("out") or (session.workspace / "output"))


def _image_coverage(session, book_dir: Path) -> tuple[int, int, float | None]:
    material = sum(len(doc.get("images") or []) for doc in session.state.get("materials", []))
    seen: set[str] = set()
    for path in book_dir.glob("*.md"):
        for match in IMAGE_RE.finditer(path.read_text(encoding="utf-8")):
            seen.add(match.group(1))
    if material == 0:
        return 0, 0, None
    return material, len(seen), round(min(1.0, len(seen) / material), 3)


def evaluate(workspace: Path, name: str, citation_sample: int = 50) -> dict[str, Any]:
    session = load_session(workspace)
    session.require()
    report = audit(session, check_citations=True, citation_sample=citation_sample)
    book_dir = _book_dir(session)
    metrics = report["metrics"]
    books = sorted(book_dir.glob("*.md"))
    ids = {path.name: book_question_ids(path) for path in books}
    core = [value for key, value in ids.items() if key.startswith(("01", "02", "03", "05"))]
    id_consistent = bool(core) and all(value == core[0] for value in core[1:])
    slots = [slot for day in session.state.get("schedule", {}).get("days", []) for slot in day.get("slots", [])]
    ready = sum(1 for slot in slots if slot.get("qid"))
    material_images, book_images, image_rate = _image_coverage(session, book_dir)
    citations = report.get("citations") or {}
    return {
        "name": name,
        "workspace": str(workspace),
        "ok": report["ok"],
        "metrics": {
            "placeholders": metrics.get("placeholders", 0),
            "needsGeneration": metrics.get("needsGeneration", 0),
            "planExecutable": round(ready / len(slots), 3) if slots else 1.0,
            "answerCoverage": metrics.get("answerCoverage", 0.0),
            "solutionCoverage": metrics.get("solutionCoverage", 0.0),
            "rubricCoverage": metrics.get("rubricCoverage", 0.0),
            "citationHitRate": citations.get("rate"),
            "citationChecked": citations.get("checked"),
            "imageCoverage": image_rate,
            "materialImages": material_images,
            "bookImages": book_images,
            "bookIdConsistency": id_consistent,
            "questions": metrics.get("questions", 0),
            "days": len(session.state.get("schedule", {}).get("days", [])),
        },
        "problems": report.get("problems", []),
        "warnings": report.get("warnings", []),
        "weakModelCompletion": "n/a（需真实弱模型 run 后人工记录）",
    }


def render(report: dict[str, Any]) -> str:
    m = report["metrics"]
    def pct(value: Any) -> str:
        return "n/a" if value is None else f"{float(value) * 100:.1f}%"
    rows = [
        ("占位符", str(m["placeholders"])),
        ("待生成题位", str(m["needsGeneration"])),
        ("计划可执行率", pct(m["planExecutable"])),
        ("答案覆盖", pct(m["answerCoverage"])),
        ("解析/步骤覆盖", pct(m["solutionCoverage"])),
        ("评分点覆盖", pct(m["rubricCoverage"])),
        ("引用命中率", pct(m["citationHitRate"])),
        ("图片进册率", pct(m["imageCoverage"])),
        ("五册题号一致", "是" if m["bookIdConsistency"] else "否"),
        ("弱模型完成率", report["weakModelCompletion"]),
    ]
    lines = [f"## {report['name']}", "", "| 指标 | 值 |", "|---|---|"]
    lines.extend(f"| {key} | {value} |" for key, value in rows)
    lines.append("")
    lines.append(f"质检：{'通过' if report['ok'] else '未通过'}；问题 {len(report['problems'])} 条。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="评估已回填的 review-sprint 工作区")
    parser.add_argument("--workspace", action="append", required=True, help="name=path，可重复")
    parser.add_argument("--out", help="输出 JSON 路径")
    parser.add_argument("--citation-sample", type=int, default=50)
    args = parser.parse_args()
    reports = []
    for value in args.workspace:
        if "=" not in value:
            parser.error("--workspace 需要 name=path")
        name, path = value.split("=", 1)
        reports.append(evaluate(Path(path), name, args.citation_sample))
    payload = {"courses": reports}
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n\n".join(render(item) for item in reports))
    return 0 if all(item["ok"] for item in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
