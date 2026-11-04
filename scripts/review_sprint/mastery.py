"""Mastery levels L0-L4 and answer-driven updates."""
from __future__ import annotations

from datetime import date
from typing import Any

from .subjects import get_profile, num

LEVELS = ["L0", "L1", "L2", "L3", "L4"]
LEVEL_LABELS = {
    "L0": "放弃",
    "L1": "认识",
    "L2": "会做基础题",
    "L3": "熟练",
    "L4": "稳拿",
}
DEFAULT_THRESHOLDS = {"L2": 0.70, "L3": 0.80, "L4": 0.85}
DEFAULT_RATES = {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95}


def thresholds(state: dict[str, Any]) -> dict[str, float]:
    profile = state.get("subjectProfile") or get_profile(state.get("subject") or "general")
    raw = profile.get("masteryThresholds") or {}
    out = dict(DEFAULT_THRESHOLDS)
    for key in ("L2", "L3", "L4"):
        if key in raw:
            out[key] = num(raw[key], out[key])
    return out


def score_rates(state: dict[str, Any]) -> dict[str, float]:
    profile = state.get("subjectProfile") or get_profile(state.get("subject") or "general")
    raw = profile.get("masteryScoreRates") or {}
    return {key: num(raw.get(key), DEFAULT_RATES[key]) for key in LEVELS}


def level_from_accuracy(accuracy: float, thresholds_map: dict[str, float]) -> str:
    if accuracy >= thresholds_map.get("L4", 0.85):
        return "L4"
    if accuracy >= thresholds_map.get("L3", 0.80):
        return "L3"
    if accuracy >= thresholds_map.get("L2", 0.70):
        return "L2"
    if accuracy > 0:
        return "L1"
    return "L0"


def update_mastery(
    state: dict[str, Any], question_id: str, correct: bool,
    confidence: int = 2, on: date | None = None,
) -> list[dict[str, Any]]:
    """Recompute current level for every KP touched by this question."""
    question = next((q for q in state.get("questions", []) if q.get("id") == question_id), None)
    if not question:
        return []
    day = (on or date.today()).isoformat()
    qids = {q["id"] for q in state.get("questions", []) if set(q.get("kpIds", [])) & set(question.get("kpIds", []))}
    rows = [a for a in state.get("attempts", []) if a.get("questionId") in qids]
    tmap = thresholds(state)
    out = []
    for kp_id in question.get("kpIds", []):
        mastery = state.setdefault("mastery", {}).setdefault(kp_id, {
            "targetLevel": "L0", "currentLevel": "L0", "attempts": 0,
            "accuracy": 0.0, "correctDays": [], "updatedAt": "",
        })
        related = [a for a in rows]
        correct_count = sum(1 for a in related if a.get("correct"))
        accuracy = correct_count / len(related) if related else 0.0
        level = level_from_accuracy(accuracy, tmap)
        # L4 additionally requires correctness on at least three distinct days.
        if level == "L4":
            days = {a.get("date") for a in related if a.get("correct")}
            if len(days) < 3:
                level = "L3"
        mastery.update({
            "currentLevel": level,
            "attempts": len(related),
            "accuracy": round(accuracy, 3),
            "correctDays": sorted({a.get("date") for a in related if a.get("correct")}),
            "updatedAt": day,
        })
        target = mastery.get("targetLevel", "L0")
        mastery["completed"] = LEVELS.index(level) >= LEVELS.index(target)
        if mastery["completed"]:
            mastery["completedAt"] = day
        out.append({"kpId": kp_id, **mastery})
    return out


def summary(state: dict[str, Any]) -> dict[str, int]:
    counts = {level: 0 for level in LEVELS}
    for item in state.get("mastery", {}).values():
        counts[item.get("currentLevel", "L0")] = counts.get(item.get("currentLevel", "L0"), 0) + 1
    return counts
