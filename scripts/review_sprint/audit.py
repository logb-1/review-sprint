"""Quality gates: schedule, links, provenance, answer conflicts, coverage."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .bilibili import BV_RE, BiliClient
from .books import BOOK_NAMES, book_question_ids, count_placeholders
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
    workload = st.get("workload") or {}
    if float(workload.get("overflowMinutes") or 0) > 0:
        warnings.append(f"总任务量超预算 {workload['overflowMinutes']} 分钟（W={workload.get('totalMinutes')}，预算={workload.get('budgetMinutes')}）")

    # answer conflicts: only unresolved (pending) ones block the audit
    for q in st.get("questions", []):
        if q.get("conflict") and q.get("resolution", "pending") == "pending":
            problems.append(f"{q['id']} 官方答案与重算冲突（待确认）：{q['conflict']}")
        elif q.get("conflict") and q.get("resolution") == "official":
            warnings.append(f"{q['id']} 已确认以官方答案为准：{q.get('resolutionNote', '')}")
        elif q.get("conflict") and q.get("resolution") == "recomputed":
            warnings.append(f"{q['id']} 已确认以重算为准：{q.get('resolutionNote', '')}")
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
        if row.get("bvid") and row["bvid"] not in cached:
            problems.append(f"视频记录缺少缓存证据：{row['bvid']}")

    # five-book consistency + meaningful content metrics
    book_dir = Path(st.get("build", {}).get("out") or (session.workspace / "output"))
    metrics: dict[str, Any] = {}
    if book_dir.exists():
        id_sets = book_question_ids(book_dir)
        expected = {q["id"] for q in st.get("questions", [])}
        if id_sets:
            for name, ids in id_sets.items():
                missing = expected - ids
                extra = ids - expected
                if missing:
                    problems.append(f"{BOOK_NAMES.get(name, name)} 缺少题号：{', '.join(sorted(missing))}")
                if extra:
                    problems.append(f"{BOOK_NAMES.get(name, name)} 出现题库外题号：{', '.join(sorted(extra))}")
            if len({tuple(sorted(v)) for v in id_sets.values()}) > 1:
                problems.append("主册 / 答案册 / 刷题宝典的题号集合不一致")
        for key in ("main", "answers", "drill"):
            if key not in id_sets:
                problems.append(f"缺少五册文件：{BOOK_NAMES.get(key, key)}")
        placeholders = count_placeholders(book_dir)
        metrics["placeholders"] = placeholders
        if placeholders:
            problems.append(
                f"五册还有 {placeholders} 处待模型填充（<!-- MODEL:... -->）；"
                "运行 coach.py fill 生成清单并回填后再 audit"
            )
        questions = st.get("questions", [])
        answered = sum(1 for q in questions if q.get("finalAnswer") or q.get("recomputed") or q.get("solution"))
        metrics["questions"] = len(questions)
        metrics["answered"] = answered
        metrics["answerCoverage"] = round(answered / len(questions), 3) if questions else 0.0
        mapped = sum(1 for q in questions if q.get("kpIds"))
        metrics["mappedQuestions"] = mapped
        metrics["unmappedQuestions"] = len(questions) - mapped
        metrics["kpCoverage"] = round(mapped / len(questions), 3) if questions else 0.0
        if metrics["answerCoverage"] < 0.8:
            warnings.append(f"答案覆盖率 {metrics['answerCoverage']:.0%} 低于 80%；先 fill 并 recompute")
        if metrics["unmappedQuestions"]:
            warnings.append(f"{metrics['unmappedQuestions']} 道题没有 kpIds；先 fill 的 kpMap 任务")
    metrics["pendingConflicts"] = sum(1 for q in st.get("questions", []) if q.get("conflict") and q.get("resolution", "pending") == "pending")
    metrics["unresolvedMistakes"] = sum(1 for m in st.get("mistakes", []) if not m.get("resolved"))
    metrics["dueReviews"] = len(due_reviews(st))
    quant = st.get("quantification") or {}
    metrics["coverage"] = quant.get("coverage")
    if quant.get("coverageLow"):
        warnings.append(f"往年题知识点覆盖率仅 {float(quant.get('coverage') or 0):.0%}；可达分按区间看")

    # coverage of question types
    profile = st.get("subjectProfile") or {}
    allowed_checkers = set(profile.get("checkers") or [])
    if allowed_checkers:
        for q in st.get("questions", []):
            kind = (q.get("check") or {}).get("kind")
            if kind and kind not in allowed_checkers:
                warnings.append(f"{q['id']} 使用了科目画像未声明的校验器 {kind}")
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
        "metrics": metrics,
        "stats": {
            "materials": len(st.get("materials", [])),
            "chapters": len(st.get("chapters", [])),
            "knowledgePoints": len(st.get("knowledgePoints", [])),
            "questions": len(st.get("questions", [])),
            "papers": len(st.get("papers", [])),
            "days": len(st.get("schedule", {}).get("days", [])),
            "videos": len(st.get("videos", [])),
            "dueReviews": len(due_reviews(st)),
            "placeholders": metrics.get("placeholders", 0),
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
    metrics = report.get("metrics") or {}
    if metrics:
        lines.append("## 内容指标")
        for key in ("placeholders", "answered", "questions", "answerCoverage", "kpCoverage", "coverage", "unmappedQuestions", "pendingConflicts", "unresolvedMistakes"):
            if key in metrics and metrics[key] is not None:
                value = metrics[key]
                if key in {"answerCoverage", "kpCoverage", "coverage"}:
                    value = f"{float(value):.1%}"
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
