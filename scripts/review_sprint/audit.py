"""Quality gates: schedule, links, provenance, answer conflicts, coverage."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .bilibili import BV_RE, BiliClient
from .schedule import compute_difficulty, due_reviews, exam_frequency, validate_schedule
from .state import Session
from .util import read_text

LINK_RE = re.compile(r"\((https?://[^)]+)\)")


def audit(session: Session) -> dict[str, Any]:
    st = session.require()
    problems: list[str] = []
    warnings: list[str] = []

    problems.extend(validate_schedule(st))
    compute_difficulty(st)

    # provenance
    for kp in st.get("knowledgePoints", []):
        source = kp.get("source") or {}
        if not source.get("file") and not kp.get("sourceLabel"):
            warnings.append(f"{kp['id']} 没有原文来源，将显示为“待确认”")
    pending = [m for m in st.get("materials", []) if m.get("status") != "ok"]
    for material in pending:
        warnings.append(f"材料未解析：{material['rel']}（{material.get('status')}：{material.get('error', '')}）")

    # answer conflicts
    for q in st.get("questions", []):
        if q.get("officialAnswer") and q.get("recomputed") and q.get("conflict"):
            problems.append(f"{q['id']} 官方答案与重算冲突：{q['conflict']}")
        if q.get("officialAnswer") and not q.get("recomputed") and not q.get("check"):
            warnings.append(f"{q['id']} 只抄了官方答案，尚未重算")

    # Bilibili links: every rendered BV must exist in state videos or client cache
    client = BiliClient(session.cache_dir, offline=True)
    cached = client.cached_bvids()
    known = {row.get("bvid") for row in st.get("videos", []) if row.get("bvid")}
    for path in session.daily_dir.glob("*.md"):
        text = read_text(path)
        for bvid in BV_RE.findall(text):
            if bvid not in known and bvid not in cached:
                problems.append(f"{path.name} 出现未在检索缓存中的 BV 号：{bvid}")
    for row in st.get("videos", []):
        if row.get("bvid") and row["bvid"] not in cached and row["bvid"] not in known:
            problems.append(f"视频记录缺少缓存证据：{row['bvid']}")

    # coverage
    covered_types = {q.get("type") for q in st.get("questions", []) if q.get("type")}
    for t in st.get("questionTypes", []):
        if t["id"] not in covered_types:
            warnings.append(f"题型 {t['id']} {t['name']} 还没有对应题目")
    kp_chapters = {kp.get("chapter") for kp in st.get("knowledgePoints", [])}
    for chapter in st.get("chapters", []):
        if chapter["id"] not in kp_chapters:
            warnings.append(f"章节 {chapter['id']} {chapter['title']} 没有知识点")

    # due review sanity
    exam = st.get("examDate", "")
    for item in due_reviews(st):
        if item.get("due") and item["due"] > exam:
            problems.append(f"复习到期日晚于考试：{item}")

    return {
        "ok": not problems,
        "problems": problems,
        "warnings": warnings,
        "stats": {
            "materials": len(st.get("materials", [])),
            "chapters": len(st.get("chapters", [])),
            "knowledgePoints": len(st.get("knowledgePoints", [])),
            "questions": len(st.get("questions", [])),
            "papers": len(st.get("papers", [])),
            "days": len(st.get("schedule", {}).get("days", [])),
            "videos": len(st.get("videos", [])),
            "dueReviews": len(due_reviews(st)),
        },
        "examFrequency": exam_frequency(st),
    }


def format_audit(report: dict[str, Any]) -> str:
    lines = ["# 质检报告", ""]
    lines.append("结果：✅ 通过" if report["ok"] else "结果：❌ 有问题")
    lines.append("")
    lines.append("## 统计")
    for key, value in report["stats"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    if report["problems"]:
        lines.append("## 必须修复")
        for item in report["problems"]:
            lines.append(f"- ❌ {item}")
        lines.append("")
    if report["warnings"]:
        lines.append("## 提醒")
        for item in report["warnings"]:
            lines.append(f"- ⚠️ {item}")
        lines.append("")
    if report.get("examFrequency"):
        lines.append("## 题型常考度（F）")
        for tid, value in sorted(report["examFrequency"].items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"- {tid}: {value:.3f}")
        lines.append("")
    return "\n".join(lines)
