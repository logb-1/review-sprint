"""Persistent single-file state for one course / one exam date."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .util import SCHEMA, now_iso, read_json, today, write_json

WORKSPACE_FILES = ("materials", "chapters", "daily", "exports", ".cache")


def default_settings() -> dict[str, Any]:
    return {
        "density": "standard",          # concise | standard | detailed
        "difficultyWeights": {
            "pastLoss": 0.35,
            "userError": 0.30,
            "prereqDepth": 0.20,
            "errorFlags": 0.15,
        },
        "phaseRatios": {"build": 0.40, "reinforce": 0.35, "sprint": 0.25},
        "dailySlots": {"basic": 4, "past": 2, "advanced": 1},
        "mockSlots": {"mock": 10, "proof": 2},
        "minutesPerSlot": {"basic": 10, "past": 15, "advanced": 20, "mock": 12, "proof": 15, "review": 5},
        "maxReviewsPerDay": 6,
        "lastDayExtraMinutes": 30,
        "bilibili": {
            "enabled": True,
            "threshold": 0.5,
            "maxPerKp": 2,
            "cacheDays": 7,
            "rateSeconds": 1.0,
            "whitelist": [],
        },
        "fsrs": {
            "targetRetention": 0.9,
            "F": 19.0 / 81.0,
            "C": -0.5,
            "examBufferDays": 3,
        },
    }


def new_state(
    course: str,
    exam_date: date,
    *,
    start_date: date | None = None,
    daily_minutes: int = 120,
    target_score: int = 90,
    language: str = "zh",
    density: str = "standard",
) -> dict[str, Any]:
    start = start_date or today()
    return {
        "schema": SCHEMA,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "course": course,
        "examDate": exam_date.isoformat(),
        "startDate": start.isoformat(),
        "dailyMinutes": daily_minutes,
        "targetScore": target_score,
        "language": language,
        "materials": [],
        "chapters": [],
        "knowledgePoints": [],
        "questionTypes": [],
        "papers": [],
        "questions": [],
        "schedule": {"days": []},
        "attempts": [],
        "mistakes": [],
        "videos": [],
        "settings": default_settings(),
        "warnings": [],
    }


class Session:
    """A workspace containing study_state.json plus derived artifacts."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.state_path = self.workspace / "study_state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.materials_dir = self.workspace / "materials"
        self.chapters_dir = self.workspace / "chapters"
        self.daily_dir = self.workspace / "daily"
        self.exports_dir = self.workspace / "exports"
        self.cache_dir = self.workspace / ".cache"
        for d in (self.materials_dir, self.chapters_dir, self.daily_dir, self.exports_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.state = read_json(self.state_path, None)

    def exists(self) -> bool:
        return bool(self.state)

    def require(self) -> dict[str, Any]:
        if not self.state:
            raise SystemExit(f"未找到 {self.state_path}，请先运行: coach.py init --course ... --exam-date ... --materials ...")
        return self.state

    def save(self) -> None:
        if not self.state:
            return
        self.state["updatedAt"] = now_iso()
        write_json(self.state_path, self.state)

    def chapter_text(self, chapter: dict[str, Any]) -> str:
        rel = chapter.get("textFile")
        if rel:
            path = self.workspace / rel
            if path.exists():
                return path.read_text(encoding="utf-8")
        return chapter.get("text", "")

    def find_kp(self, kp_id: str) -> dict[str, Any] | None:
        for kp in self.state.get("knowledgePoints", []):
            if kp.get("id") == kp_id:
                return kp
        return None

    def find_question(self, qid: str) -> dict[str, Any] | None:
        for q in self.state.get("questions", []):
            if q.get("id") == qid:
                return q
        return None

    def find_day(self, day: int | None = None) -> dict[str, Any] | None:
        days = self.state.get("schedule", {}).get("days", [])
        if day is None:
            for item in days:
                if item.get("date") == today().isoformat():
                    return item
            for item in days:
                if not item.get("done"):
                    return item
            return days[-1] if days else None
        for item in days:
            if int(item.get("day", 0)) == int(day):
                return item
        return None

    def progress_line(self) -> str:
        st = self.state or {}
        days = st.get("schedule", {}).get("days", [])
        current = self.find_day()
        if current:
            day_no = current.get("day", 1)
            phase = current.get("phase", "")
            date_str = current.get("date", "")
        else:
            day_no, phase, date_str = 1, "未排期", today().isoformat()
        total = len(days) or max(1, _days_left(st))
        due = len([a for a in st.get("attempts", []) if a.get("retestDue") and str(a["retestDue"]) <= today().isoformat()])
        mistakes = len(st.get("mistakes", []))
        left = _days_left(st)
        return (
            f"📍 第 {day_no}/{total} 天 · {phase} · {date_str} · "
            f"到期复习 {due} · 错题 {mistakes} · 剩余 {left} 天 · "
            f"下一步：python scripts/coach.py today"
        )


def _days_left(state: dict[str, Any]) -> int:
    try:
        exam = date.fromisoformat(str(state.get("examDate"))[:10])
    except ValueError:
        return 0
    return max(0, (exam - today()).days)


def load_session(workspace: str | Path) -> Session:
    return Session(Path(workspace))


def due_attempts(state: dict[str, Any], on: date | None = None) -> list[dict[str, Any]]:
    day = (on or today()).isoformat()
    return [a for a in state.get("attempts", []) if a.get("retestDue") and str(a.get("retestDue")) <= day]


def add_attempt(
    state: dict[str, Any],
    qid: str,
    correct: bool,
    *,
    confidence: int = 2,
    cause: str = "",
    seconds: int = 0,
    on: date | None = None,
    note: str = "",
) -> dict[str, Any]:
    day = (on or today()).isoformat()
    attempt = {
        "date": day,
        "questionId": qid,
        "correct": bool(correct),
        "confidence": max(0, min(3, int(confidence))),
        "cause": cause or ("none" if correct else "unknown"),
        "timeSec": max(0, int(seconds)),
        "note": note,
    }
    state.setdefault("attempts", []).append(attempt)
    if not correct:
        attempt["retestDue"] = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        state.setdefault("mistakes", []).append({
            "questionId": qid,
            "date": day,
            "cause": attempt["cause"],
            "highConfidence": confidence >= 2,
            "retestDue": (date.fromisoformat(day) + timedelta(days=1)).isoformat(),
            "resolved": False,
        })
    return attempt
