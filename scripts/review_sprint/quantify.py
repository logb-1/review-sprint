"""Target-score -> mastery-level quantification (L0-L4).

The algorithm is deliberately explainable: each knowledge point has a
contribution = P * F * weight * recent, normalised to 100.  We greedily buy
level upgrades with the best expected-score gain per minute until the
safety-adjusted target is reached or the time budget is exhausted.
"""
from __future__ import annotations

from typing import Any

from .mastery import LEVELS, score_rates, thresholds
from .subjects import get_profile, num

PRACTICE_COUNT = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}


def _unique_papers(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    seen: set[str] = set()
    out: dict[str, dict[str, Any]] = {}
    for paper in state.get("papers", []):
        key = paper.get("sameAs") or paper.get("id")
        if key in seen:
            continue
        seen.add(key)
        out[paper.get("id")] = paper
    return out


def kp_stats(state: dict[str, Any], profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    profile = profile or get_profile(state.get("subject") or "general")
    papers = _unique_papers(state)
    all_questions = state.get("questions", [])
    avg_points = sum(float(q.get("points", 1) or 1) for q in all_questions) / max(1, len(all_questions))
    years = [int(p.get("year") or 0) for p in papers.values()]
    max_year = max(years, default=0)
    stats: list[dict[str, Any]] = []
    for kp in state.get("knowledgePoints", []):
        related = [q for q in all_questions if kp["id"] in (q.get("kpIds") or [])]
        paper_ids = {q.get("paperId") for q in related if q.get("paperId")}
        if papers:
            f = len(paper_ids & set(papers)) / max(1, len(papers))
        else:
            f = float(kp.get("examFreq") or 0.4)
        p = (sum(float(q.get("points", 1) or 1) for q in related) / len(related)) if related else avg_points
        loss_values = []
        for q in related:
            if q.get("pastLoss") is not None:
                loss_values.append(float(q["pastLoss"]))
            elif q.get("steps") is not None:
                loss_values.append(min(1.0, float(q["steps"]) / 10.0))
        loss = sum(loss_values) / len(loss_values) if loss_values else float((kp.get("difficultyParts") or {}).get("pastLoss") or 0.4)
        recent = 1.0
        if max_year and years:
            kp_years = [int(papers[q["paperId"]].get("year") or 0) for q in related if q.get("paperId") in papers]
            if kp_years:
                recent = 1.2 if max(kp_years) >= max_year - 1 else 1.0
        weight = float(kp.get("weight") or 1.0)
        contribution = max(0.0, p * max(0.05, f) * weight * recent)
        stats.append({
            "kpId": kp["id"], "title": kp.get("title", ""), "chapter": kp.get("chapter", ""),
            "F": round(f, 3), "P": round(p, 2), "pastLoss": round(loss, 3),
            "recentWeight": recent, "weight": weight,
            "contribution": round(contribution, 3),
            "questionIds": [q["id"] for q in related],
        })
    total = sum(x["contribution"] for x in stats) or 1.0
    for item in stats:
        item["normalizedScore"] = round(item["contribution"] / total * 100.0, 2)
    return stats


def _avg_type_minutes(profile: dict[str, Any]) -> float:
    values = [num(t.get("minutes"), 10) for t in profile.get("questionTypes", [])]
    return sum(values) / len(values) if values else 10.0


def _level_minutes(profile: dict[str, Any], level: str) -> float:
    base = num(profile.get("minutesPerKp"), 12)
    factor = {"L1": 0.55, "L2": 1.0, "L3": 1.55, "L4": 2.15}.get(level, 0.0)
    weights = profile.get("masteryWeights") or {}
    cognitive = (
        0.35 * num(weights.get("understand"), 0.25)
        + 0.20 * num(weights.get("memory"), 0.25)
        + 0.30 * num(weights.get("calculation"), 0.25)
        + 0.15 * num(weights.get("application"), 0.25)
    )
    factor *= 0.80 + 0.40 * cognitive
    practice = PRACTICE_COUNT.get(level, 0) * _avg_type_minutes(profile)
    return round(base * factor + practice, 1)


def _plan_for_target(
    stats: list[dict[str, Any]], profile: dict[str, Any], budget_minutes: float,
    target: float, rates: dict[str, float], threshold_map: dict[str, float],
) -> dict[str, Any]:
    levels = {s["kpId"]: "L0" for s in stats}
    by_id = {s["kpId"]: s for s in stats}
    used = 0.0
    achieved = 0.0
    practice = 0
    while achieved < target:
        best = None
        for item in stats:
            kid = item["kpId"]
            current = levels[kid]
            idx = LEVELS.index(current)
            if idx >= len(LEVELS) - 1:
                continue
            nxt = LEVELS[idx + 1]
            gain = item["normalizedScore"] * (rates.get(nxt, 0.0) - rates.get(current, 0.0))
            cost = max(1.0, _level_minutes(profile, nxt) - _level_minutes(profile, current))
            score_per_min = gain / cost
            if best is None or score_per_min > best[0]:
                best = (score_per_min, kid, nxt, gain, cost)
        if best is None:
            break
        _, kid, nxt, gain, cost = best
        if used + cost > budget_minutes:
            break
        old_level = levels[kid]
        practice += PRACTICE_COUNT.get(nxt, 0) - PRACTICE_COUNT.get(old_level, 0)
        levels[kid] = nxt
        used += cost
        achieved += gain
    # achieved is already in 0-100 contribution units
    achieved = min(100.0, round(achieved, 2))
    minutes = round(used, 1)
    return {
        "levels": levels,
        "achieved": achieved,
        "minutes": minutes,
        "practiceQuestions": practice,
        "totalLevels": sum(LEVELS.index(v) for v in levels.values()),
    }


def workload(state: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explicit total workload W and its per-day average."""
    profile = profile or state.get("subjectProfile") or get_profile(state.get("subject") or "general")
    days = max(1, int(state.get("days") or 1))
    daily = int(state.get("dailyMinutes") or 120)
    avg_type = _avg_type_minutes(profile)
    mastery = state.get("mastery", {})
    learning = sum(float(v.get("minutes") or 0) for v in mastery.values())
    practice = sum(float(v.get("questionCount") or 0) * avg_type for v in mastery.values())
    review_minutes = 5
    reviews = sum(1 for kp in state.get("knowledgePoints", []) if kp.get("fsrs", {}).get("due"))
    review_total = max(0, reviews) * review_minutes
    mock_count = num(profile.get("mockQuestions"), 8)
    proof_count = num(profile.get("proofQuestions"), 1)
    mock_total = (mock_count + proof_count) * num((profile.get("kindMinutes") or {}).get("mock"), 12)
    total = learning + practice + review_total + mock_total
    budget = days * daily
    result = {
        "totalMinutes": round(total, 1),
        "learningMinutes": round(learning, 1),
        "practiceMinutes": round(practice, 1),
        "reviewMinutes": round(review_total, 1),
        "mockMinutes": round(mock_total, 1),
        "days": days,
        "dailyMinutes": daily,
        "dailyAverage": round(total / days, 1),
        "budgetMinutes": budget,
        "overflowMinutes": round(max(0.0, total - budget), 1),
    }
    state["workload"] = result
    return result


def schedule_workload(state: dict[str, Any]) -> dict[str, Any]:
    """Replace the estimate with the actual scheduled minutes (all slots/reviews)."""
    days = max(1, int(state.get("days") or 1))
    daily = int(state.get("dailyMinutes") or 120)
    total = sum(int(day.get("minutes") or 0) for day in state.get("schedule", {}).get("days", []))
    budget = days * daily
    result = {
        "totalMinutes": total,
        "learningMinutes": (state.get("workload") or {}).get("learningMinutes", 0),
        "practiceMinutes": (state.get("workload") or {}).get("practiceMinutes", 0),
        "reviewMinutes": sum(int(r.get("minutes") or 0) for day in state.get("schedule", {}).get("days", []) for r in day.get("reviews", [])),
        "mockMinutes": sum(int(s.get("minutes") or 0) for day in state.get("schedule", {}).get("days", []) for s in day.get("slots", []) if s.get("kind") in {"mock", "proof"}),
        "days": days,
        "dailyMinutes": daily,
        "dailyAverage": round(total / days, 1),
        "budgetMinutes": budget,
        "overflowMinutes": round(max(0.0, total - budget), 1),
    }
    state["workload"] = result
    return result


def quantify(
    state: dict[str, Any], target: float | None = None,
    days: int | None = None, daily_minutes: int | None = None,
) -> dict[str, Any]:
    profile = state.get("subjectProfile") or get_profile(state.get("subject") or "general")
    target = float(target if target is not None else state.get("targetScore", 80))
    days = int(days or state.get("days") or 1)
    daily = int(daily_minutes or state.get("dailyMinutes") or 120)
    safety = num(profile.get("safetyFactor"), 1.10)
    required = min(100.0, target * safety)
    rates = score_rates(state)
    tmap = thresholds(state)
    stats = kp_stats(state, profile)
    top_contribution = sum(max(0.0, s["normalizedScore"]) for s in stats) or 1.0
    budget = max(1.0, days * daily * 0.90)
    full = _plan_for_target(stats, profile, budget, 100.0, rates, tmap)
    chosen = _plan_for_target(stats, profile, budget, required, rates, tmap)

    def row(tier: float) -> dict[str, Any]:
        plan = _plan_for_target(stats, profile, budget, min(100.0, tier * safety), rates, tmap)
        return {
            "target": tier,
            "required": round(min(100.0, tier * safety), 1),
            "achieved": plan["achieved"],
            "minutes": plan["minutes"],
            "dailyMinutes": round(plan["minutes"] / max(1, days), 1),
            "dailyQuestions": round(plan["practiceQuestions"] / max(1, days), 1),
            "levels": {k: v for k, v in plan["levels"].items() if v != "L0"},
            "selected": abs(tier - target) < 0.01,
        }

    matrix = [row(t) for t in (60, 70, 80, 90, 95)]
    if all(abs(tier - target) > 0.01 for tier in (60, 70, 80, 90, 95)):
        matrix.append(row(target))
        matrix.sort(key=lambda item: item["target"])
    chosen_levels = chosen["levels"]
    mastery = {}
    for kp in state.get("knowledgePoints", []):
        kid = kp["id"]
        level = chosen_levels.get(kid, "L0")
        mastery[kid] = {
            "targetLevel": level,
            "currentLevel": (state.get("mastery", {}).get(kid) or {}).get("currentLevel", "L0"),
            "expectedScore": round(next((s["normalizedScore"] for s in stats if s["kpId"] == kid), 0.0) * rates.get(level, 0.0), 2),
            "minutes": _level_minutes(profile, level),
            "questionCount": PRACTICE_COUNT.get(level, 0),
        }
    abandoned = []
    for item in stats:
        if chosen_levels.get(item["kpId"], "L0") == "L0":
            abandoned.append({
                "kpId": item["kpId"], "title": item["title"],
                "lostScore": round(item["normalizedScore"] * rates.get("L4", 0.95), 2),
            })
    result = {
        "target": target,
        "safetyFactor": safety,
        "requiredScore": round(required, 1),
        "maxScore": full["achieved"],
        "reachableScore": chosen["achieved"],
        "shortfall": round(max(0.0, required - chosen["achieved"]), 1),
        "budgetMinutes": round(budget, 1),
        "totalMinutes": chosen["minutes"],
        "dailyMinutes": round(chosen["minutes"] / max(1, days), 1),
        "dailyQuestions": round(chosen["practiceQuestions"] / max(1, days), 1),
        "practiceQuestions": chosen["practiceQuestions"],
        "levels": {k: v for k, v in chosen_levels.items() if v != "L0"},
        "matrix": matrix,
        "abandoned": sorted(abandoned, key=lambda x: x["lostScore"], reverse=True),
        "stats": stats,
        "rates": rates,
        "thresholds": tmap,
        "selectedTier": target,
    }
    state["quantification"] = result
    state.setdefault("mastery", {})
    for kid, plan in mastery.items():
        current = state["mastery"].get(kid, {})
        state["mastery"][kid] = {
            **current,
            "targetLevel": plan["targetLevel"],
            "currentLevel": current.get("currentLevel", "L0"),
            "expectedScore": plan["expectedScore"],
            "minutes": plan["minutes"],
            "questionCount": plan["questionCount"],
        }
    workload(state, profile)
    return result
