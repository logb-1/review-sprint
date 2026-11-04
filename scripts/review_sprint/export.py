"""Calendar and Anki exports."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .render import cheatsheet_markdown, plan_markdown, source_label
from .state import Session
from .util import write_text


def _escape_ics(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def to_ics(state: dict[str, Any]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//review-sprint//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for day in state.get("schedule", {}).get("days", []):
        day_date = date.fromisoformat(day["date"])
        start = datetime.combine(day_date, time(19, 0))
        end = start + timedelta(minutes=max(30, int(day.get("minutes", 60))))
        kps = "、".join(day.get("kpIds", []))
        desc = f"{day['phase']}；知识点：{kps or '复习/模拟'}；题量：{len(day.get('slots', []))}；复习：{len(day.get('reviews', []))}"
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:review-sprint-{day['date']}-{day['day']}@local",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_escape_ics('复习：' + state['course'] + ' 第' + str(day['day']) + '天')}",
            f"DESCRIPTION:{_escape_ics(desc)}",
            "END:VEVENT",
        ])
    exam = date.fromisoformat(state["examDate"])
    lines.extend([
        "BEGIN:VEVENT",
        f"UID:review-sprint-exam-{state['examDate']}@local",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{exam.strftime('%Y%m%d')}",
        f"SUMMARY:{_escape_ics('考试：' + state['course'])}",
        "END:VEVENT",
    ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def to_anki_csv(state: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Front", "Back", "Tags"])
    for kp in state.get("knowledgePoints", []):
        front = f"{state['course']} · {kp['id']} {kp['title']}"
        back = "一句话：\n答题要点：\n" + source_label(kp)
        writer.writerow([front, back, f"review-sprint {kp.get('chapter', '')}"])
    for q in state.get("questions", []):
        answer = q.get("recomputed") or q.get("officialAnswer")
        if not answer:
            continue
        writer.writerow([q.get("stem", ""), answer, f"review-sprint {q.get('type', '')}"])
    return buffer.getvalue()


def export_all(session: Session, formats: list[str] | None = None) -> list[Path]:
    st = session.require()
    formats = formats or ["md", "ics", "anki"]
    written: list[Path] = []
    stem = f"{st['course']}_复习"
    if "md" in formats:
        path = session.exports_dir / f"{stem}_排期.md"
        write_text(path, plan_markdown(st))
        written.append(path)
        path = session.exports_dir / f"{stem}_速记表.md"
        write_text(path, cheatsheet_markdown(st))
        written.append(path)
    if "ics" in formats:
        path = session.exports_dir / f"{stem}_日历.ics"
        write_text(path, to_ics(st))
        written.append(path)
    if "anki" in formats:
        path = session.exports_dir / f"{stem}_Anki.csv"
        write_text(path, to_anki_csv(st))
        written.append(path)
    return written
