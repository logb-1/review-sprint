"""Subject profiles: load, validate, detect, and unwrap annotated numbers."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .util import clean_term

PROFILE_DIR = Path(__file__).resolve().parents[2] / "references" / "subjects"
REQUIRED_FIELDS = {
    "subject", "label", "biliPrefix", "matchKeywords", "keywords", "negative",
    "questionTypes", "dailyMix", "phaseRatio", "masteryWeights", "difficultyWeights",
    "reviewIntervals", "masteryThresholds", "masteryScoreRates", "safetyFactor",
    "checkers", "kindMinutes", "mockQuestions", "proofQuestions", "minutesPerKp",
    "levelFactors", "cognitiveWeights", "practiceCounts",
}
ALIASES = {
    "programming_cpp": "programming",
    "programming_python": "programming",
    "csapp": "cs_systems",
    "computer_systems": "cs_systems",
    "maths": "math",
    "politics_theory": "politics",
    "foreign": "foreign_language",
}


def num(value: Any, default: float = 0.0) -> float:
    """Profiles annotate numbers as {'value': x, '_note': '...'}."""
    if isinstance(value, dict):
        value = value.get("value", default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _profile_path(name: str) -> Path:
    return PROFILE_DIR / f"{name}.json"


def load_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    if not PROFILE_DIR.exists():
        return profiles
    paths = sorted(PROFILE_DIR.glob("*.json"))
    custom = PROFILE_DIR / "custom"
    if custom.exists():
        paths += sorted(custom.glob("*.json"))
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        subject = str(data.get("subject") or path.stem)
        data["subject"] = subject
        data.setdefault("label", subject)
        data.setdefault("biliPrefix", data.get("label", ""))
        profiles[subject] = data
    return profiles


_PROFILES: dict[str, dict[str, Any]] | None = None


def profiles() -> dict[str, dict[str, Any]]:
    global _PROFILES
    if _PROFILES is None:
        _PROFILES = load_profiles()
    return _PROFILES


def profile_names() -> list[str]:
    return sorted(profiles())


def get_profile(name: str | None) -> dict[str, Any]:
    data = profiles()
    key = (name or "general").strip()
    key = ALIASES.get(key, key)
    if key in data:
        return data[key]
    return data.get("general", {})


def has_profile(name: str | None) -> bool:
    key = ALIASES.get((name or "").strip(), (name or "").strip())
    return key in profiles()


def _score_profile(profile: dict[str, Any], haystack: str) -> int:
    score = 0
    for word in profile.get("matchKeywords", []):
        w = str(word).strip().lower()
        if not w:
            continue
        hits = haystack.count(w)
        if hits:
            score += hits * (3 if len(w) >= 4 else 2 if len(w) >= 2 else 1)
    return score


def detect_subject(text: str, course: str = "") -> dict[str, Any]:
    """Return {subject, confidence, needsConfirmation, scores, candidates}."""
    haystack = f"{course}\n{text}".lower()
    scores = {key: _score_profile(value, haystack) for key, value in profiles().items() if key != "general"}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_key, top_score = ranked[0] if ranked else ("general", 0)
    second = ranked[1][1] if len(ranked) > 1 else 0
    if top_score <= 0:
        return {
            "subject": "general", "confidence": 0.0, "needsConfirmation": True,
            "scores": scores, "candidates": [],
        }
    confidence = top_score / (top_score + second + 0.5)
    # a single weak hit should not beat the confirmation threshold
    if top_score < 3:
        confidence = min(confidence, 0.5)
    candidates = [{"subject": k, "score": v, "confidence": round(v / (top_score + 0.0001), 2)}
                  for k, v in ranked[:3] if v > 0]
    return {
        "subject": top_key,
        "confidence": round(confidence, 3),
        "needsConfirmation": confidence < 0.6,
        "scores": scores,
        "candidates": candidates,
    }


def require_subject(text: str, course: str = "", requested: str | None = None) -> dict[str, Any]:
    """Resolve a subject or raise a structured confirmation error payload."""
    if requested:
        if not has_profile(requested):
            raise ValueError(f"未知科目画像: {requested}")
        return {"subject": ALIASES.get(requested, requested), "confidence": 1.0,
                "needsConfirmation": False, "scores": {}, "candidates": []}
    detected = detect_subject(text, course)
    if detected["needsConfirmation"]:
        raise SubjectConfirmationRequired(detected)
    return detected


class SubjectConfirmationRequired(ValueError):
    def __init__(self, detection: dict[str, Any]):
        super().__init__("科目识别置信度不足，需要用户确认")
        self.detection = detection


def normalized_numbers(profile: dict[str, Any]) -> dict[str, Any]:
    """Deep copy with annotated numbers replaced by plain numbers (for state snapshots)."""
    if isinstance(profile, dict):
        if "value" in profile and "_note" in profile:
            return profile["value"]
        return {k: normalized_numbers(v) for k, v in profile.items()}
    if isinstance(profile, list):
        return [normalized_numbers(v) for v in profile]
    return profile
