"""Persistent single-file state for one course / one exam date."""
from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .util import SCHEMA, now_iso, read_json, today, write_json

WORKSPACE_FILES = ("materials", "chapters", "daily", "exports", ".cache")


class StateExistsError(RuntimeError):
    """Raised instead of silently overwriting an existing workspace."""


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
    exam_date: date | None = None,
    *,
    start_date: date | None = None,
    daily_minutes: int = 120,
    target_score: int = 90,
    language: str = "zh",
    density: str = "standard",
    subject: str = "general",
    profile: dict[str, Any] | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    start = start_date or today()
    if exam_date is None:
        if days is None:
            raise ValueError("new_state 需要 exam_date 或 days")
        exam_date = start + timedelta(days=int(days))
    total_days = int(days) if days is not None else max(1, (exam_date - start).days)
    settings = default_settings()
    settings["density"] = density
    return {
        "schema": SCHEMA,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "course": course,
        "examDate": exam_date.isoformat(),
        "startDate": start.isoformat(),
        "days": total_days,
        "dailyMinutes": daily_minutes,
        "targetScore": target_score,
        "subject": subject,
        "subjectConfidence": 1.0,
        "subjectSource": "default",
        "subjectProfile": profile or {},
        "mastery": {},
        "quantification": {},
        "workload": {},
        "build": {},
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
        "settings": settings,
        "warnings": [],
    }


def migrate_state(state: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool]:
    """Fill fields added after 0.1 without breaking old workspaces."""
    if not state:
        return state, False
    changed = False
    if state.get("schema") != SCHEMA:
        state["schema"] = SCHEMA
        changed = True
    settings = state.get("settings")
    if not isinstance(settings, dict):
        settings = {}
        state["settings"] = settings
        changed = True
    defaults = default_settings()
    for key, value in defaults.items():
        if key not in settings:
            settings[key] = value
            changed = True
    for key, value in (
        ("subject", "general"), ("subjectConfidence", 0.0), ("subjectSource", "legacy"),
        ("subjectProfile", {}), ("mastery", {}), ("quantification", {}), ("workload", {}), ("build", {}),
    ):
        if key not in state:
            state[key] = value
            changed = True
    if "days" not in state:
        try:
            start = date.fromisoformat(str(state.get("startDate"))[:10])
            exam = date.fromisoformat(str(state.get("examDate"))[:10])
            state["days"] = max(1, (exam - start).days)
        except (TypeError, ValueError):
            state["days"] = len(state.get("schedule", {}).get("days", [])) or 1
        changed = True
    for q in state.get("questions", []):
        for key, value in (("resolution", None), ("finalAnswer", None), ("steps", max(1, round(float(q.get("points", 1)) / 2)))):
            if key not in q:
                q[key] = value
                changed = True
    for kp in state.get("knowledgePoints", []):
        for key, value in (("weight", 1.0), ("syllabusLevel", 0.0), ("emphasis", False), ("weightReason", "")):
            if key not in kp:
                kp[key] = value
                changed = True
    return state, changed


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
        self.assets_dir = self.workspace / "assets"
        self.cache_dir = self.workspace / ".cache"
        for d in (self.materials_dir, self.chapters_dir, self.daily_dir, self.exports_dir, self.assets_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        raw = read_json(self.state_path, None)
        self.state, migrated = migrate_state(raw)
        if migrated:
            write_json(self.state_path, self.state)

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

    def backup(self) -> Path | None:
        """Copy the state aside before a destructive rebuild."""
        if not self.state_path.exists():
            return None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.workspace / f"study_state.{stamp}.bak.json"
        shutil.copy2(self.state_path, target)
        return target

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
        if not days:
            return None
        if day is not None:
            return next((item for item in days if int(item.get("day", 0)) == int(day)), None)
        current = today().isoformat()
        for item in days:
            if item.get("date") == current:
                return item
        # date before the plan: start at the first study day
        if current < str(days[0].get("date", "")):
            return days[0]
        # date after the plan: last study day (exam day is not in the plan)
        if current > str(days[-1].get("date", "")):
            return days[-1]
        # a gap (missed day): show the next unfinished day, but tell the user to replan
        for item in days:
            if not item.get("done") and str(item.get("date", "")) >= current:
                return item
        return days[-1]

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
        due = _due_count(st)
        mistakes = len([m for m in st.get("mistakes", []) if not m.get("resolved")])
        left = _days_left(st)
        return (
            f"📍 第 {day_no}/{total} 天 · {phase} · {date_str} · "
            f"到期复习 {due} · 错题 {mistakes} · 剩余 {left} 天 · "
            f"下一步：coach.py next"
        )


def _days_left(state: dict[str, Any]) -> int:
    try:
        exam = date.fromisoformat(str(state.get("examDate"))[:10])
    except ValueError:
        return 0
    return max(0, (exam - today()).days)


def _due_count(state: dict[str, Any], on: date | None = None) -> int:
    day = (on or today()).isoformat()
    count = 0
    for kp in state.get("knowledgePoints", []):
        due = (kp.get("fsrs") or {}).get("due") or ""
        if due and due <= day:
            count += 1
    for mistake in state.get("mistakes", []):
        if not mistake.get("resolved") and str(mistake.get("retestDue") or "") <= day:
            count += 1
    return count


def mark_day_done(state: dict[str, Any], day_no: int, *, on: date | None = None) -> dict[str, Any]:
    day = next((d for d in state.get("schedule", {}).get("days", []) if int(d.get("day", 0)) == int(day_no)), None)
    if not day:
        raise KeyError(f"未知天: {day_no}")
    day["done"] = True
    day["doneAt"] = (on or today()).isoformat()
    return day


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
        "actualSeconds": max(0, int(seconds)),
        "note": note,
    }
    state.setdefault("attempts", []).append(attempt)
    if not correct:
        retest = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        attempt["retestDue"] = retest
        existing = next((m for m in state.get("mistakes", [])
                         if m.get("questionId") == qid and not m.get("resolved")), None)
        if existing:
            existing.update({
                "date": day, "cause": attempt["cause"],
                "highConfidence": existing.get("highConfidence") or confidence >= 2,
                "retestDue": retest,
            })
        else:
            state.setdefault("mistakes", []).append({
                "questionId": qid,
                "date": day,
                "cause": attempt["cause"],
                "highConfidence": confidence >= 2,
                "retestDue": retest,
                "resolved": False,
                "consecutiveCorrect": 0,
            })
        return attempt

    attempt["retestDue"] = None
    # Close a mistake after two consecutive correct attempts on different days.
    rows = [a for a in state.get("attempts", []) if a.get("questionId") == qid]
    trailing_days = []
    for row in reversed(rows):
        if not row.get("correct"):
            break
        if row.get("date") not in trailing_days:
            trailing_days.append(row.get("date"))
    if len(trailing_days) >= 2:
        for mistake in state.get("mistakes", []):
            if mistake.get("questionId") == qid and not mistake.get("resolved"):
                mistake["resolved"] = True
                mistake["resolvedAt"] = day
                mistake["resolvedBy"] = "two-consecutive-correct"
                mistake["consecutiveCorrect"] = len(trailing_days)
    return attempt
