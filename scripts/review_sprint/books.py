"""Five deliverable books: plan, main, answers, cheatsheet, drill."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .docx_writer import convert_markdown_files
from .answer_check import primary_value
from .mastery import LEVEL_LABELS
from .render import source_label
from .schedule import exam_frequency
from .state import Session
from .subjects import get_profile, num
from .util import human_minutes, write_text

BOOK_NAMES = {
    "plan": "01-复习计划",
    "main": "02-主册",
    "answers": "03-答案册",
    "cheatsheet": "04-速记手册",
    "drill": "05-刷题宝典",
}


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "—"


def _target_level(state: dict[str, Any], kp_id: str) -> str:
    return (state.get("mastery", {}).get(kp_id) or {}).get("targetLevel", "L0")


def _kp_excerpt(session: Session, kp: dict[str, Any], limit: int = 240) -> str:
    chapter = next((c for c in session.state.get("chapters", []) if c.get("id") == kp.get("chapter")), None)
    if not chapter:
        return "待确认：未定位到章节原文"
    text = session.chapter_text(chapter)
    for candidate in (kp.get("title", ""), chapter.get("title", "")):
        index = text.find(candidate) if candidate else -1
        if index >= 0:
            return text[index:index + limit].replace("\n", " ").strip()
    return text[:limit].replace("\n", " ").strip() or "待确认：章节正文为空"


def _first_sentence(text: str) -> str:
    if not text or text.startswith("待确认"):
        return text or "待确认：无原文"
    for sep in ("。", "；", "\n", "[备注]"):
        if sep in text:
            return text.split(sep, 1)[0].strip()
    return text.strip()


def _pitfall(text: str) -> str:
    if "易错" in text:
        return text.split("易错", 1)[1].lstrip("：: ").split("。", 1)[0].strip()
    return "待确认：原文未标注易错点"


def _all_questions(state: dict[str, Any]) -> list[dict[str, Any]]:
    return list(state.get("questions", []))


def _question_ids(state: dict[str, Any]) -> list[str]:
    return [q["id"] for q in _all_questions(state)]


def plan_markdown(state: dict[str, Any]) -> str:
    q = state.get("quantification", {})
    profile = state.get("subjectProfile") or get_profile(state.get("subject") or "general")
    lines = [f"# {state['course']} · 复习计划", ""]
    lines.append(f"- 科目画像：{profile.get('label', state.get('subject'))}（{state.get('subject')}）")
    lines.append(f"- 复习天数：{state.get('days', len(state.get('schedule', {}).get('days', [])))} 天")
    lines.append(f"- 每日预算：{human_minutes(int(state.get('dailyMinutes', 120)))}")
    lines.append(f"- 目标分：{state.get('targetScore', 80)}；安全系数：{q.get('safetyFactor', '—')}")
    lines.append(f"- 可达预期分：{q.get('reachableScore', '—')} / 需要 {q.get('requiredScore', '—')}")
    w = state.get("workload", {})
    if w:
        lines.append(f"- 总任务量 W：{w.get('totalMinutes', '—')} 分钟；日均 {w.get('dailyAverage', '—')} 分钟；预算 {w.get('budgetMinutes', '—')} 分钟；超预算 {w.get('overflowMinutes', 0)} 分钟")
    if q.get("shortfall"):
        lines.append(f"- ⚠️ 缺口：{q['shortfall']} 分；当前时间预算下无法达到安全目标。")
    lines.append("")
    lines.append("## 目标分–掌握度矩阵")
    lines.append("")
    lines.append("| 目标分 | 安全后需要 | 可达 | 总分钟 | 每日分钟 | 每日题量 | 标记 |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for row in q.get("matrix", []):
        mark = "★ 当前" if row.get("selected") else ""
        lines.append(f"| {row['target']} | {row['required']} | {row['achieved']} | {row['minutes']} | "
                     f"{row['dailyMinutes']} | {row['dailyQuestions']} | {mark} |")
    lines.append("")
    if q.get("abandoned"):
        lines.append("## 放弃项")
        lines.append("")
        lines.append("| 知识点 | 估算丢分 |")
        lines.append("|---|---:|")
        for item in q["abandoned"]:
            lines.append(f"| {item['kpId']} {item['title']} | {item['lostScore']} |")
        lines.append("")
    lines.append("## 按天计划")
    lines.append("")
    lines.append("| 天 | 日期 | 阶段 | 知识点 | 题号 | 预估分钟 | 目标等级 |")
    lines.append("|---|---|---|---|---|---:|---|")
    for day in state.get("schedule", {}).get("days", []):
        kps = "、".join(day.get("kpIds", []))
        qids = "、".join(s.get("qid") or "待生成" for s in day.get("slots", []) if s.get("qid") or s.get("status") == "needs_generation")
        levels = "、".join(f"{kid}:{_target_level(state, kid)}" for kid in day.get("kpIds", []))
        lines.append(f"| {day['day']} | {day['date']} | {day['phase']} | {kps or '—'} | {qids or '—'} | "
                     f"{day['minutes']} | {levels or '—'} |")
    lines.append("")
    return "\n".join(lines)


def main_markdown(session: Session) -> str:
    state = session.state
    lines = [f"# {state['course']} · 主册", ""]
    lines.append("> 题目只放题号和题干；答案见《03-答案册》，解析中的来源以〔原文：文件 第 N 页〕为准。")
    lines.append("")
    for chapter in state.get("chapters", []):
        lines.append(f"## {chapter['id']} {chapter['title']}")
        lines.append("")
        for kp in [k for k in state.get("knowledgePoints", []) if k.get("chapter") == chapter["id"]]:
            lines.append(f"### {kp['id']} {kp['title']}")
            lines.append("")
            excerpt = _kp_excerpt(session, kp)
            related = [q for q in _all_questions(state) if kp["id"] in (q.get("kpIds") or [])]
            lines.append(f"- 目标等级：{_target_level(state, kp['id'])} {LEVEL_LABELS.get(_target_level(state, kp['id']), '')}")
            lines.append(f"- 来源：{source_label(kp)}")
            lines.append(f"- F/D：F={float(kp.get('examFreq') or 0):.2f} · D={float(kp.get('D') or 0):.2f}")
            lines.append(f"- 定义/要点：{_first_sentence(excerpt)}")
            lines.append(f"- 易错点：{_pitfall(excerpt)}")
            example = related[0]["stem"] if related else "待确认：题库尚未覆盖该知识点"
            lines.append(f"- 最小例题：{example}")
            lines.append("- 相关题号：" + ("、".join(q["id"] for q in related) if related else "待生成"))
            lines.append("")
    lines.append("## 全部题目（题号 + 题干）")
    lines.append("")
    lines.append("| 题号 | 题型 | 题干 |")
    lines.append("|---|---|---|")
    for q in _all_questions(state):
        lines.append(f"| {q['id']} | {q.get('type', '')} | {q.get('stem', '').replace(chr(10), ' ')[:180]} |")
    lines.append("")
    return "\n".join(lines)


def answer_markdown(state: dict[str, Any]) -> str:
    lines = [f"# {state['course']} · 答案册", ""]
    lines.append("> 与主册、刷题宝典使用同一套题号；校验状态只写证据支持的结论。")
    lines.append("")
    lines.append("| 题号 | 答案 | 步骤/解析 | 评分点 | 校验状态 |")
    lines.append("|---|---|---|---|---|")
    for q in _all_questions(state):
        official = q.get("officialAnswer")
        recomputed = q.get("recomputed")
        resolution = q.get("resolution", "pending" if q.get("conflict") else "same")
        answer = q.get("finalAnswer") or official or primary_value(recomputed) or "待确认"
        if q.get("conflict") and resolution == "pending":
            status = "待确认（官方与重算冲突）"
        elif q.get("conflict") and resolution == "official":
            status = "已确认：以官方为准"
        elif q.get("conflict") and resolution == "recomputed":
            status = "已确认：以重算为准"
        elif q.get("modelGenerated") or q.get("answerSource") == "model":
            status = "模型给出⚠️（未经官方/重算核验）"
        elif recomputed:
            status = "已核验（脚本重算）"
        elif official:
            status = "待确认（仅官方答案，未重算）"
        else:
            status = "待确认（无答案）"
        steps = q.get("solution") or q.get("analysis")
        if not steps:
            if recomputed:
                steps = f"按脚本重算结果 {primary_value(recomputed)} 对照；客观题直接判定。"
            elif official:
                steps = "仅官方答案，未提供逐步解析；核对时标「待核验」。"
            else:
                steps = "待确认：无答案、无解析，不得编造。"
        points = q.get("points", "—")
        lines.append(f"| {q['id']} | {str(answer).replace(chr(10), ' ')} | {str(steps).replace(chr(10), ' ')[:160]} | "
                     f"{points} 分 | {status} |")
    lines.append("")
    return "\n".join(lines)


def cheatsheet_markdown(session: Session) -> str:
    state = session.state
    kp_days = [day for day in state.get("schedule", {}).get("days", []) if day.get("kpIds")]
    last3 = {kid for day in (kp_days[-3:] or state.get("schedule", {}).get("days", [])[-3:]) for kid in day.get("kpIds", [])}
    kps = sorted(state.get("knowledgePoints", []), key=lambda k: (k["id"] not in last3, k["id"]))
    lines = [f"# {state['course']} · 速记手册", ""]
    lines.append("> 每个知识点 ≤5 行；按考前最后 3 天顺序排列，可单独打印。")
    lines.append("")
    for kp in kps:
        lines.append(f"## {kp['id']} {kp['title']}")
        lines.append("")
        lines.append(f"- 来源：{source_label(kp)}")
        lines.append(f"- 定义/公式：{_kp_excerpt(session, kp, 120)}")
        lines.append(f"- 易混对比：先写「{kp['title']}」的适用条件，再与同章相邻概念对比。")
        lines.append("- 口诀/记忆：先定义，再条件，最后做一道最小例题；考前只看这三行。")
        lines.append("")
    return "\n".join(lines)


def drill_markdown(state: dict[str, Any]) -> str:
    lines = [f"# {state['course']} · 刷题宝典", ""]
    lines.append("> 只放题号，答案见《03-答案册》；按科目画像的题型分组。")
    lines.append("")
    freq = exam_frequency(state)
    for qtype in state.get("questionTypes", []):
        items = [q for q in _all_questions(state) if q.get("type") == qtype["id"]]
        if not items:
            continue
        lines.append(f"## {qtype['id']} {qtype['name']}（{len(items)} 题）")
        lines.append("")
        lines.append(f"- 识别信号：{qtype.get('keywords') or '待确认'}")
        lines.append(f"- 解法套路：先抓题干关键词 → 写定义/公式 → 代入计算 → 检查边界与单位。")
        lines.append(f"- 判分方式：{qtype.get('grading', 'rubric')}；F={freq.get(qtype['id'], 0):.2f}")
        lines.append("")
        lines.append("| 题号 | 出处 | 年份 | 分值 | F |")
        lines.append("|---|---|---|---:|---:|")
        for q in sorted(items, key=lambda q: ({"basic": 0, "past": 1, "advanced": 2, "recite": 3}.get(q.get("kind", ""), 9), q["id"])):
            paper = next((p for p in state.get("papers", []) if p.get("id") == q.get("paperId")), {})
            lines.append(f"| {q['id']} | {paper.get('sourceFile', q.get('sourceFile', '待确认'))} | "
                         f"{paper.get('year', '—')} | {q.get('points', '—')} | {freq.get(q.get('type', ''), 0):.2f} |")
        lines.append("")
    known_types = {t["id"] for t in state.get("questionTypes", [])}
    other = [q for q in _all_questions(state) if q.get("type") not in known_types]
    if other:
        lines.append(f"## 未分组题（{len(other)} 题）")
        lines.append("")
        lines.append("| 题号 | 出处 | 年份 | 分值 |")
        lines.append("|---|---|---|---:|")
        for q in other:
            paper = next((p for p in state.get("papers", []) if p.get("id") == q.get("paperId")), {})
            lines.append(f"| {q['id']} | {paper.get('sourceFile', q.get('sourceFile', '待确认'))} | {paper.get('year', '—')} | {q.get('points', '—')} |")
        lines.append("")
    return "\n".join(lines)


def write_books(session: Session, out_dir: Path, formats: list[str] | None = None) -> list[Path]:
    formats = formats or ["md", "docx"]
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = {
        "plan": plan_markdown(session.state),
        "main": main_markdown(session),
        "answers": answer_markdown(session.state),
        "cheatsheet": cheatsheet_markdown(session),
        "drill": drill_markdown(session.state),
    }
    md_paths: list[Path] = []
    for key, text in texts.items():
        path = out_dir / f"{BOOK_NAMES[key]}.md"
        write_text(path, text)
        md_paths.append(path)
    written = list(md_paths)
    if "docx" in formats:
        written.extend(convert_markdown_files(md_paths, out_dir))
    return written


def book_question_ids(book_dir: Path) -> dict[str, set[str]]:
    """Read question ids from the three question-bearing books."""
    import re
    out: dict[str, set[str]] = {}
    pattern = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*-Q\d+(?:-\d+)?\b")
    for key, name in (("main", "02-主册"), ("answers", "03-答案册"), ("drill", "05-刷题宝典")):
        path = book_dir / f"{name}.md"
        if not path.exists():
            continue
        out[key] = set(pattern.findall(path.read_text(encoding="utf-8")))
    return out
