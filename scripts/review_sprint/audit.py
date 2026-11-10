"""Quality gates: schedule, links, provenance, answer conflicts, coverage."""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .bilibili import BV_RE, BiliClient
from .books import BOOK_NAMES, book_question_ids, count_placeholders
from .schedule import compute_difficulty, due_reviews, exam_frequency, pending_generation, validate_schedule
from .state import Session
from .util import read_text

LINK_RE = re.compile(r"\((https?://[^)]+)\)")
PAGE_RE = re.compile(r"【第\s*(\d+)\s*页】")
BANNED_RE = re.compile(r"(?:^|[。；\s])(略|自行补充|同上|见教材|略去|暂略)(?:[。；\s]|$)")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _content_issue(text: str, minimum: int = 20, steps: int = 0) -> str | None:
    body = (text or "").strip()
    if len(body) < minimum:
        return f"内容过短（{len(body)} 字，至少 {minimum} 字）"
    if BANNED_RE.search(body):
        return "含“略/自行补充/同上/见教材”等空话"
    if steps:
        numbered = re.findall(r"(?:^|\n)\s*(?:\d+[.、]|[①②③④⑤]|第[一二三四五]步)", body)
        if len(numbered) < steps:
            return f"步骤不足（{len(numbered)} 个，至少 {steps} 个）"
    return None


def _pdf_text(path: Path, page: Any = None) -> str:
    """Read a PDF directly when no chapter slice was built for it.

    Past papers are indexed as question sources but do not get chapter rows in
    ``state.chapters``.  Falling back to the PDF text layer keeps answer
    citations checkable instead of reporting a false "missing source".
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    def clean(value: str) -> str:
        return "".join(
            ch for ch in value
            if not (0xD800 <= ord(ch) <= 0xDFFF)
            and (ord(ch) >= 32 or ch in "\t\n\r")
        )

    try:
        reader = PdfReader(str(path))
        if page is not None:
            try:
                number = int(page)
            except (TypeError, ValueError):
                number = 0
            if 1 <= number <= len(reader.pages):
                return clean(str(reader.pages[number - 1].extract_text() or ""))
            return ""
        return "\n".join(clean(str(item.extract_text() or "")) for item in reader.pages)
    except Exception:
        return ""


def _material_text(session: Session, file: str, page: Any = None) -> str:
    if not file:
        return ""
    rel = file.replace("\\", "/")
    path = Path(file)
    if not path.is_absolute():
        path = session.workspace / rel
    if path.exists() and path.suffix.lower() in {".md", ".txt", ".markdown"}:
        return read_text(path)
    chapters = []
    for chapter in session.state.get("chapters", []):
        sources = [chapter.get("source") or {}, *(chapter.get("sources") or [])]
        if any((source.get("file") or "").replace("\\", "/").endswith(rel) for source in sources):
            chapters.append(chapter)
    if not chapters:
        if path.exists() and path.suffix.lower() == ".pdf":
            return _pdf_text(path, page)
        return ""
    if page is not None:
        try:
            number = int(page)
        except (TypeError, ValueError):
            number = None
        if number is not None:
            exact = [c for c in chapters if (c.get("source") or {}).get("pageStart") == number]
            if exact:
                return session.chapter_text(exact[0])
            before = [c for c in chapters
                      if isinstance((c.get("source") or {}).get("pageStart"), int)
                      and (c.get("source") or {}).get("pageStart") < number]
            if before:
                return session.chapter_text(max(before, key=lambda c: c["source"]["pageStart"]))
    return "\n\n".join(session.chapter_text(chapter) for chapter in chapters)


def _page_slice(text: str, page: Any) -> str:
    try:
        number = int(page)
    except (TypeError, ValueError):
        return text
    matches = list(PAGE_RE.finditer(text))
    if not matches:
        return text
    # Chapter bodies begin after the previous page marker, so the first page
    # in a chapter often has no explicit marker. Infer that leading segment.
    first_page = int(matches[0].group(1))
    if number == first_page - 1 and matches[0].start() > 0:
        return text[:matches[0].start()]
    for index, match in enumerate(matches):
        if int(match.group(1)) == number:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.end():end]
    return ""


def _citation_hit(session: Session, entry: dict[str, Any], allow_source_fallback: bool = True) -> tuple[bool, str]:
    # Use all chapter slices for this source.  A source can be split into
    # several chunks; the page marker may live in a neighbouring chunk even
    # though the quote is on the cited page.
    text = _material_text(session, str(entry.get("file") or ""), None)
    if not text:
        text = _material_text(session, str(entry.get("file") or ""), entry.get("page"))
    if not text:
        return False, "找不到源文件或可检索文本"
    quote = _norm(str(entry.get("quote") or "")).replace("〔原文", "").split("〕")[-1]
    if not quote:
        return False, "引文为空"
    try:
        page = int(entry.get("page"))
    except (TypeError, ValueError):
        page = None
    pages = [page]
    if page is not None:
        pages.extend([page - 1, page + 1])
    for candidate in pages:
        segment = _page_slice(text, candidate)
        hay = _norm(segment)
        if hay and (quote[:80] in hay or SequenceMatcher(None, quote[:80], hay[:max(80, len(quote))]).ratio() >= 0.9):
            return True, ""
    if not allow_source_fallback:
        return False, "引文在该页找不到（归一化子串/相似度均未命中）"
    # Some PDF page markers drift by more than one page.  A quote that appears
    # in the source chapter is still real provenance; do not report it as a
    # fabricated citation just because the page marker is coarse.
    full = _norm(_material_text(session, str(entry.get("file") or ""), None))
    if quote[:80] in full or SequenceMatcher(None, quote[:80], full[:max(80, len(quote))]).ratio() >= 0.9:
        return True, ""
    return False, "引文在该页找不到（归一化子串/相似度均未命中）"


def _citation_report(session: Session, sample: int = 20) -> dict[str, Any]:
    book_dir = Path(session.state.get("build", {}).get("out") or (session.workspace / "output"))
    path = book_dir / "_build" / "citations.json"
    if not path.exists():
        return {"total": 0, "checked": 0, "hits": 0, "rate": 0.0, "sourceHits": 0,
                "sourceRate": 0.0, "failures": ["缺少 citations.json"], "ok": False}
    data = json.loads(read_text(path))
    entries = data.get("entries") or []
    checked = entries[:max(1, int(sample))] if sample else entries
    failures = []
    hits = 0
    source_hits = 0
    for entry in checked:
        ok, reason = _citation_hit(session, entry, allow_source_fallback=False)
        if ok:
            hits += 1
            source_hits += 1
            continue
        source_ok, _ = _citation_hit(session, entry, allow_source_fallback=True)
        if source_ok:
            source_hits += 1
        failures.append(f"{entry.get('id', '?')}: {reason}")
    rate = round(hits / len(checked), 3) if checked else 0.0
    source_rate = round(source_hits / len(checked), 3) if checked else 0.0
    return {"total": len(entries), "checked": len(checked), "hits": hits,
            "rate": rate, "sourceHits": source_hits, "sourceRate": source_rate,
            "failures": failures, "ok": bool(checked) and rate >= 0.9}


def audit(session: Session, check_citations: bool = False, citation_sample: int = 20) -> dict[str, Any]:
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
        with_solution = sum(1 for q in questions if str(q.get("solution") or "").strip())
        with_rubric = sum(1 for q in questions if q.get("rubric"))
        metrics["solutionCoverage"] = round(with_solution / len(questions), 3) if questions else 0.0
        metrics["rubricCoverage"] = round(with_rubric / len(questions), 3) if questions else 0.0
        if metrics["answerCoverage"] < 0.8:
            warnings.append(f"答案覆盖率 {metrics['answerCoverage']:.0%} 低于 80%；先 fill 并 recompute")
        if metrics["unmappedQuestions"]:
            warnings.append(f"{metrics['unmappedQuestions']} 道题没有 kpIds；先 fill 的 kpMap 任务")

        # Content gate: a field being present is not the same as being useful.
        for q in questions:
            solution = str(q.get("solution") or "").strip()
            if not solution:
                problems.append(f"{q['id']} 缺少解析/步骤；运行 coach.py fill 的 answer:{q['id']} 任务")
            else:
                issue = _content_issue(solution, minimum=15, steps=2)
                if issue:
                    problems.append(f"{q['id']} 解析不合格：{issue}")
            if not q.get("rubric"):
                problems.append(f"{q['id']} 缺少评分点 rubric；运行 coach.py fill 的 rubric:{q['id']} 任务")
        for kp in st.get("knowledgePoints", []):
            if kp.get("mainNote"):
                issue = _content_issue(str(kp["mainNote"]), minimum=24)
                if issue:
                    problems.append(f"{kp['id']} 主册讲解不合格：{issue}")
            if kp.get("cheatsheet"):
                issue = _content_issue(str(kp["cheatsheet"]), minimum=8)
                if issue:
                    problems.append(f"{kp['id']} 速记不合格：{issue}")
        for qtype in st.get("questionTypes", []):
            if qtype.get("method"):
                issue = _content_issue(str(qtype["method"]), minimum=16)
                if issue:
                    problems.append(f"题型 {qtype['id']} 解法不合格：{issue}")
    pending_slots = pending_generation(st)
    metrics["needsGeneration"] = len(pending_slots)
    if pending_slots:
        head = "、".join(
            str(s.get("slotId") or f"D{int(s.get('day') or 0):02d}-S{int(s.get('slot') or 0):02d}")
            for s in pending_slots[:5]
        )
        message = (
            f"计划还有 {len(pending_slots)} 个题位待生成（如 {head}）；"
            "先运行 coach.py fill --tasks，再把 generate:<题位号> 回填后 audit"
        )
        # No five books yet (for example right after init): the plan is still
        # useful for daily study, so this is a warning until a build exists.
        (problems if book_dir.exists() else warnings).append(message)
    if check_citations:
        citations = _citation_report(session, citation_sample)
        metrics["citations"] = citations
        if not citations["ok"]:
            extra = ""
            if citations.get("sourceRate", 0) > citations["rate"]:
                extra = f"；同文件可检索到 {citations['sourceRate']:.1%}，但页码不精确"
            problems.append(
                f"引用核验未通过：{citations['hits']}/{citations['checked']} 精确页命中"
                f"（目标 ≥90%）；{'; '.join(citations['failures'][:3])}{extra}"
            )
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
            "needsGeneration": metrics.get("needsGeneration", 0),
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
        for key in ("placeholders", "needsGeneration", "answered", "questions", "answerCoverage",
                    "solutionCoverage", "rubricCoverage", "kpCoverage", "coverage",
                    "unmappedQuestions", "pendingConflicts", "unresolvedMistakes"):
            if key in metrics and metrics[key] is not None:
                value = metrics[key]
                if key in {"answerCoverage", "solutionCoverage", "rubricCoverage", "kpCoverage", "coverage"}:
                    value = f"{float(value):.1%}"
                lines.append(f"- {key}: {value}")
        citations = metrics.get("citations")
        if citations:
            lines.append(
                f"- citationCoverage: {citations['rate']:.1%}（精确页 {citations['hits']}/{citations['checked']}；"
                f"同文件可检索 {citations.get('sourceRate', 0):.1%}）"
            )
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
