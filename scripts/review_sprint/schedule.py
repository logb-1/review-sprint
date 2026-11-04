"""N-day planning, subject profiles, FSRS spacing, load balance and review sync."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from .subjects import get_profile, num
from .util import clamp, today


def state_profile(state: dict[str, Any]) -> dict[str, Any]:
    profile = state.get("subjectProfile")
    if isinstance(profile, dict) and profile:
        return profile
    return get_profile(state.get("subject") or state.get("domain") or "general")


def _legacy(state: dict[str, Any]) -> bool:
    """Old workspaces/tests without a subject snapshot keep 0.2 behavior."""
    if state.get("subjectProfile"):
        return False
    if state.get("subjectSource") == "legacy":
        return True
    return not state.get("subject")


def seed_question_types(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("questionTypes"):
        return state["questionTypes"]
    profile = state_profile(state)
    types = profile.get("questionTypes") or []
    state["questionTypes"] = [
        {
            "id": t["id"],
            "name": t["name"],
            "minutes": int(num(t.get("minutes"), 10)),
            "grading": t.get("grading", "rubric"),
            "keywords": list(t.get("keywords", [])),
        }
        for t in types
    ]
    return state["questionTypes"]


def phase_for(day: int, total: int, ratios: dict[str, float] | None = None) -> str:
    """Legacy-compatible single-day label (used by older callers)."""
    ratios = ratios or {"build": 0.40, "reinforce": 0.35, "sprint": 0.25}
    if total <= 3:
        return "急救期"
    if day == 1:
        return "诊断期"
    build_end = max(1, round(total * ratios["build"]))
    reinforce_end = max(build_end, round(total * (ratios["build"] + ratios["reinforce"])))
    if day <= build_end:
        return "构建期"
    if day <= reinforce_end:
        return "强化期"
    return "冲刺期"


def _largest_remainder(total: int, ratios: dict[str, float]) -> dict[str, int]:
    keys = list(ratios)
    raw = {k: total * float(ratios[k]) for k in keys}
    counts = {k: int(math.floor(raw[k])) for k in keys}
    left = total - sum(counts.values())
    order = sorted(keys, key=lambda k: raw[k] - counts[k], reverse=True)
    for k in order[:left]:
        counts[k] += 1
    return counts


def schedule_mode(total: int) -> str:
    if total <= 3:
        return "emergency"
    if total <= 7:
        return "compressed"
    if total <= 30:
        return "standard"
    return "long"


def phase_plan(total: int, ratios: dict[str, float] | None = None) -> list[dict[str, Any]]:
    ratios = ratios or {"build": 0.40, "reinforce": 0.35, "sprint": 0.25}
    mode = schedule_mode(total)
    if mode == "emergency":
        return [{"day": d, "phase": "急救期"} for d in range(1, total + 1)]
    counts = _largest_remainder(total, ratios)
    phases: list[str] = []
    if counts.get("build", 0) > 0:
        phases.append("诊断期")
        if mode == "compressed":
            phases.extend(["压缩期（构建+强化）"] * (counts["build"] - 1 + counts.get("reinforce", 0)))
        elif mode == "long":
            first_round = max(1, (counts["build"] - 1) // 2)
            phases.extend(["构建期"] * first_round)
            phases.extend(["构建期（第二轮）"] * (counts["build"] - 1 - first_round))
            phases.extend(["强化期"] * counts.get("reinforce", 0))
        else:
            phases.extend(["构建期"] * (counts["build"] - 1))
            phases.extend(["强化期"] * counts.get("reinforce", 0))
    else:
        phases.extend(["强化期"] * counts.get("reinforce", 0))
    phases.extend(["冲刺期"] * counts.get("sprint", 0))
    phases = phases[:total]
    while len(phases) < total:
        phases.append("冲刺期")
    return [{"day": i + 1, "phase": p} for i, p in enumerate(phases)]


def _spread_days(total: int, count: int) -> list[int]:
    if total <= 1:
        return [1]
    last_type_day = total - 1 if total >= 5 else total
    available = list(range(1, last_type_day + 1)) or [1]
    if count >= len(available):
        return available
    if count <= 1:
        return [available[len(available) // 2]]
    picks: list[int] = []
    for i in range(count):
        index = round((len(available) - 1) * i / max(1, count - 1))
        day = available[index]
        if day in picks:
            day = next((candidate for candidate in available if candidate not in picks), day)
        picks.append(day)
    return picks


def _minutes(state: dict[str, Any], kind: str) -> int:
    profile = state_profile(state)
    settings_minutes = state.get("settings", {}).get("minutesPerSlot", {})
    if not _legacy(state):
        value = (profile.get("kindMinutes") or {}).get(kind)
        if value is None:
            value = settings_minutes.get(kind, 10 if kind != "review" else 5)
        return int(num(value, 10))
    return int(settings_minutes.get(kind, 10))


def _slot_kinds(state: dict[str, Any], total: int) -> dict[str, int]:
    if _legacy(state):
        if total <= 3:
            return {"basic": 2, "past": 2, "advanced": 1}
        return dict(state.get("settings", {}).get("dailySlots", {"basic": 4, "past": 2, "advanced": 1}))
    profile = state_profile(state)
    mix = profile.get("dailyMix", {})
    budget = int(state.get("dailyMinutes", 120))
    counts: dict[str, int] = {}
    for kind in ("basic", "past", "advanced", "recite"):
        ratio = num(mix.get(kind), 0.0)
        if ratio <= 0:
            continue
        avg = max(1, _minutes(state, kind))
        counts[kind] = max(1, int(round(budget * ratio / avg)))
    if not counts:
        counts = {"basic": 4, "past": 2, "advanced": 1}
    return counts


def _available(state: dict[str, Any], qtype: str, kind: str, used: set[str], attempted: set[str]) -> bool:
    return any(
        q.get("type") == qtype and q.get("kind") == kind
        and q.get("id") not in used and q.get("id") not in attempted
        for q in state.get("questions", [])
    )


def _pick_question(
    state: dict[str, Any], qtype: str, kind: str, used: set[str], attempted: set[str],
) -> dict[str, Any] | None:
    freq = exam_frequency(state)
    pool = [
        q for q in state.get("questions", [])
        if q.get("type") == qtype and q.get("kind") == kind
        and q.get("id") not in used and q.get("id") not in attempted
    ]
    if not pool:
        return None
    kp_weight = {kp["id"]: float(kp.get("weight") or 1.0) for kp in state.get("knowledgePoints", [])}
    pool.sort(
        key=lambda q: (
            freq.get(q.get("type", ""), 0),
            max((kp_weight.get(k, 1.0) for k in q.get("kpIds", [])), default=1.0),
            float(q.get("points", 1)),
        ),
        reverse=True,
    )
    chosen = pool[0]
    used.add(chosen["id"])
    return chosen


def _kp_first_days(state: dict[str, Any], total: int) -> dict[str, int]:
    chapters = state.get("chapters", [])
    kps = [kp for kp in state.get("knowledgePoints", [])
           if (state.get("mastery", {}).get(kp["id"]) or {}).get("targetLevel", "L1") != "L0"]
    if not kps:
        kps = list(state.get("knowledgePoints", []))
    if not kps:
        return {}
    if not _legacy(state):
        profile = state_profile(state)
        ratios = {k: num(v) for k, v in (profile.get("phaseRatio") or {}).items()} or None
        phases = phase_plan(total, ratios)
        build_days = [row["day"] for row in phases
                      if row["phase"] in {"诊断期", "构建期", "构建期（第二轮）", "压缩期（构建+强化）"}]
        if not build_days:
            build_days = [max(1, total - 1)]
    else:
        build_end = max(2, round(total * 0.4))
        build_days = [d for d in range(2, build_end + 1)] or [max(1, total)]
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for kp in kps:
        by_chapter.setdefault(kp.get("chapter", ""), []).append(kp)
    order = [c.get("id") for c in chapters if c.get("id") in by_chapter] or list(by_chapter)
    flat: list[dict[str, Any]] = []
    for chapter_id in order:
        kps_in_chapter = by_chapter.get(chapter_id, [])
        kps_in_chapter.sort(key=lambda kp: (float(kp.get("weight") or 1.0), float(kp.get("D") or 0.5)), reverse=True)
        flat.extend(kps_in_chapter)
    out: dict[str, int] = {}
    for index, kp in enumerate(flat):
        day = build_days[min(len(build_days) - 1, int(index * len(build_days) / max(1, len(flat))))]
        out[kp["id"]] = day
    return out


def _mock_slots(state: dict[str, Any], profile: dict[str, Any], legacy: bool) -> list[dict[str, Any]]:
    if legacy:
        mock_count, proof_count = 10, 2
    else:
        mock_count = int(num(profile.get("mockQuestions"), 10))
        proof_count = int(num(profile.get("proofQuestions"), 2))
    total = max(1, mock_count + proof_count)
    budget = int(state.get("dailyMinutes", 120))
    per_slot = max(5, int(round(budget * 1.05 / total)))
    slots = [{"kind": "mock", "type": "MOCK", "qid": None, "minutes": per_slot} for _ in range(max(1, mock_count))]
    slots += [{"kind": "proof", "type": "PROOF", "qid": None, "minutes": per_slot} for _ in range(max(0, proof_count))]
    return slots


def _assign_types(days_list: list[dict[str, Any]], covered_types: list[str], total: int, legacy: bool) -> None:
    """Guarantee each covered type appears `need` times on distinct days."""
    need = 1 if total == 1 else (2 if total <= 3 else 3)
    assignable: list[tuple[int, dict[str, Any]]] = []
    for day in days_list:
        for slot in day["slots"]:
            if slot.get("kind") in {"mock", "proof"}:
                continue
            assignable.append((day["day"], slot))
    if not assignable:
        return
    for _, slot in assignable:
        slot["type"] = ""
    day_used: dict[str, set[int]] = {tid: set() for tid in covered_types}
    counts: dict[str, int] = {tid: 0 for tid in covered_types}
    day_free: dict[int, int] = {}
    for day_no, _slot in assignable:
        day_free[day_no] = day_free.get(day_no, 0) + 1

    def take(tid: str) -> bool:
        used = day_used.setdefault(tid, set())
        candidates = [d for d, free in day_free.items() if free > 0 and d not in used]
        if not candidates:
            candidates = [d for d, free in day_free.items() if free > 0]
        if not candidates:
            return False
        day_no = max(candidates, key=lambda d: (day_free[d], -d))
        for candidate_day, slot in assignable:
            if candidate_day == day_no and not slot.get("type"):
                slot["type"] = tid
                counts[tid] = counts.get(tid, 0) + 1
                used.add(day_no)
                day_free[day_no] -= 1
                return True
        return False

    for tid in covered_types:
        while counts.get(tid, 0) < need:
            if not take(tid):
                break
    # fill remaining slots with the least-covered types, round-robin
    for _, slot in assignable:
        if slot.get("type"):
            continue
        tid = min(covered_types, key=lambda x: (counts.get(x, 0), x))
        slot["type"] = tid
        counts[tid] = counts.get(tid, 0) + 1
        day_used.setdefault(tid, set()).add(_day_no_for(days_list, slot))


def _day_no_for(days_list: list[dict[str, Any]], target: dict[str, Any]) -> int:
    for day in days_list:
        if target in day["slots"]:
            return day["day"]
    return 0


def build_schedule(state: dict[str, Any], start: date | None = None, days: int | None = None) -> dict[str, Any]:
    """Build N study days; exam day itself is never in the plan."""
    start = start or today()
    exam = date.fromisoformat(state["examDate"])
    total = int(days or state.get("days") or max(0, (exam - start).days))
    if total <= 0:
        raise ValueError("复习天数必须 ≥ 1；请用 --days 指定，或把考试日期改到未来")
    state["days"] = total
    state["examDate"] = (start + timedelta(days=total)).isoformat()
    exam = start + timedelta(days=total)
    legacy = _legacy(state)
    profile = state_profile(state)
    types = seed_question_types(state)
    type_ids = [t["id"] for t in types]
    freq = exam_frequency(state)
    attempted = {a.get("questionId") for a in state.get("attempts", []) if a.get("questionId")}
    used: set[str] = set(attempted)
    previous_days = state.get("schedule", {}).get("days", [])
    done_by_date = {d.get("date"): d.get("doneAt") for d in previous_days if d.get("done")}
    first_days = _kp_first_days(state, total)
    days_list: list[dict[str, Any]] = []
    emergency = total <= 3
    normal_types = type_ids
    per_day = sum(_slot_kinds(state, total).values())
    last_type_day = total - 1 if total >= 5 else total
    capacity = max(1, last_type_day * per_day // 3)
    if emergency:
        capacity = min(8, capacity)
    covered_types = sorted(normal_types, key=lambda tid: (freq.get(tid, 0), tid), reverse=True)[:capacity]

    phases = phase_plan(total, {k: num(v) for k, v in (profile.get("phaseRatio") or {}).items()} or None) if not legacy else None
    for day_no in range(1, total + 1):
        current = start + timedelta(days=day_no - 1)
        phase = phases[day_no - 1]["phase"] if phases else phase_for(day_no, total, state.get("settings", {}).get("phaseRatios"))
        if day_no == total and total >= 5:
            slots = _mock_slots(state, profile, legacy)
            kp_ids: list[str] = []
        else:
            slots = []
            for kind, count in _slot_kinds(state, total).items():
                slots.extend({"kind": kind, "type": "", "qid": None, "minutes": _minutes(state, kind)} for _ in range(count))
            kp_ids = [kp["id"] for kp in state.get("knowledgePoints", []) if first_days.get(kp["id"]) == day_no]
        days_list.append({
            "day": day_no,
            "date": current.isoformat(),
            "phase": phase,
            "slots": slots,
            "reviews": [],
            "kpIds": kp_ids,
            "minutes": sum(s["minutes"] for s in slots),
            "done": False,
            "warning": "",
            "loadDeviation": 0.0,
        })

    _assign_types(days_list, covered_types, total, legacy)

    for day in days_list:
        for slot in day["slots"]:
            if slot["kind"] in {"mock", "proof"}:
                slot["status"] = "needs_generation"
                continue
            if slot["kind"] == "recite":
                slot["status"] = "recite"
                continue
            q = _pick_question(state, slot["type"], slot["kind"], used, attempted)
            if q:
                slot["qid"] = q["id"]
                slot["status"] = "ready"
            else:
                slot["qid"] = None
                slot["status"] = "needs_generation"
        day["minutes"] = sum(s["minutes"] for s in day["slots"])

    intervals = [int(num(x.get("days"), 1)) for x in (profile.get("reviewIntervals") or [])] if not legacy else [1, 3, 7, 14]
    first_interval = intervals[0] if intervals else 1
    for kp in state.get("knowledgePoints", []):
        taught = first_days.get(kp["id"])
        if not taught:
            continue
        fsrs = kp.setdefault("fsrs", {"difficulty": 5.0, "stability": 1.0, "due": "", "lastReview": ""})
        if not fsrs.get("due"):
            due = start + timedelta(days=taught - 1 + max(1, first_interval))
            if due >= exam:
                due = exam - timedelta(days=1)
            if due < start:
                due = start
            fsrs["due"] = due.isoformat()

    for day in days_list:
        if day["date"] in done_by_date:
            day["done"] = True
            day["doneAt"] = done_by_date[day["date"]]

    state["schedule"] = {
        "days": days_list, "builtAt": today().isoformat(), "totalDays": total,
        "emergency": emergency, "mode": schedule_mode(total), "coveredTypes": covered_types,
        "phaseRatio": profile.get("phaseRatio") if not legacy else state.get("settings", {}).get("phaseRatios"),
    }
    state["phasePlan"] = phase_plan(total, {k: num(v) for k, v in (profile.get("phaseRatio") or {}).items()} or None) if not legacy else None
    sync_reviews(state)

    budget = int(state.get("dailyMinutes", 120))
    for day in days_list:
        total_minutes = sum(s["minutes"] for s in day["slots"]) + sum(r["minutes"] for r in day["reviews"])
        if not legacy:
            upper = budget * 1.15
            lower = budget * 0.85
            while total_minutes > upper and day.get("reviews"):
                moved = day["reviews"].pop()
                day.setdefault("reviewOverflow", []).append(moved)
                total_minutes -= moved["minutes"]
            while total_minutes > upper and len(day["slots"]) > 1:
                removable = [s for s in day["slots"] if s.get("kind") not in {"mock", "proof"}]
                if not removable:
                    break
                victim = removable[-1]
                day["slots"].remove(victim)
                total_minutes -= victim["minutes"]
            if total_minutes < lower and day["day"] != total:
                # add model-generated practice slots until the day is near budget
                kinds = [k for k, v in _slot_kinds(state, total).items() if v > 0]
                index = 0
                while total_minutes < lower and index < 3:
                    kind = kinds[index % len(kinds)] if kinds else "basic"
                    add = {"kind": kind, "type": covered_types[index % len(covered_types)] if covered_types else "", "qid": None,
                           "minutes": _minutes(state, kind), "status": "needs_generation"}
                    day["slots"].append(add)
                    total_minutes += add["minutes"]
                    index += 1
        else:
            while total_minutes > budget + 5 and len(day["slots"]) > 3:
                removable = [s for s in day["slots"] if s.get("kind") in {"advanced", "basic", "past"}]
                if not removable:
                    break
                victim = removable[-1]
                day["slots"].remove(victim)
                total_minutes -= victim["minutes"]
        day["minutes"] = total_minutes
        day["loadDeviation"] = round((total_minutes - budget) / budget, 3)
        if day["loadDeviation"] > 0.15:
            day["warning"] = f"当日负载 {total_minutes} 分钟，超过日均预算 {budget} 的 15%"
        elif day["loadDeviation"] < -0.15:
            day["warning"] = f"当日负载 {total_minutes} 分钟，低于日均预算 {budget} 的 15%"
    # Completed days are historical records: do not rewrite their slots/reviews
    # when `plan --rebuild` or `set --days` only re-plans the future.
    previous_by_date = {d.get("date"): d for d in previous_days if d.get("date")}
    for index, day in enumerate(days_list):
        old = previous_by_date.get(day.get("date"))
        if old and old.get("done"):
            days_list[index] = old
    state["schedule"]["days"] = days_list
    return state["schedule"]


def sync_reviews(state: dict[str, Any]) -> None:
    days = state.get("schedule", {}).get("days", [])
    if not days:
        return
    exam = date.fromisoformat(state["examDate"])
    for day in days:
        day["reviews"] = []
    by_date = {day["date"]: day for day in days}
    for kp in state.get("knowledgePoints", []):
        due = (kp.get("fsrs") or {}).get("due") or ""
        if not due or due >= exam.isoformat():
            continue
        day = by_date.get(due)
        if not day:
            continue
        day["reviews"].append({
            "kpId": kp["id"], "title": kp.get("title", ""), "interval": 1,
            "minutes": _minutes(state, "review"), "status": "planned", "D": kp.get("D", 0),
        })
    for day in days:
        day["reviews"].sort(key=lambda r: -float(r.get("D") or 0))
        cap = int(state.get("settings", {}).get("maxReviewsPerDay", 6))
        if len(day["reviews"]) > cap:
            overflow = day["reviews"][cap:]
            day["reviews"] = day["reviews"][:cap]
            day["reviewOverflow"] = overflow
            note = f"另有 {len(overflow)} 条到期复习未排入（保留在 reviewOverflow）"
            day["warning"] = (day["warning"] + "；" if day.get("warning") else "") + note
        day["minutes"] = sum(s["minutes"] for s in day["slots"]) + sum(r["minutes"] for r in day["reviews"])


def due_reviews(state: dict[str, Any], on: date | None = None) -> list[dict[str, Any]]:
    day = (on or today()).isoformat()
    out = []
    for kp in state.get("knowledgePoints", []):
        due = (kp.get("fsrs") or {}).get("due") or ""
        if due and due <= day:
            out.append({"kpId": kp["id"], "title": kp.get("title", ""), "due": due, "stability": (kp.get("fsrs") or {}).get("stability", 1.0)})
    for mistake in state.get("mistakes", []):
        if not mistake.get("resolved") and str(mistake.get("retestDue") or "") <= day:
            out.append({"questionId": mistake["questionId"], "due": mistake.get("retestDue"), "cause": mistake.get("cause", "")})
    return out


def retrievability(elapsed_days: float, stability: float) -> float:
    f = 19.0 / 81.0
    c = -0.5
    s = max(0.1, float(stability))
    return max(0.0, min(1.0, (1 + f * max(0.0, elapsed_days) / s) ** c))


def next_interval(stability: float, retention: float = 0.9) -> float:
    f = 19.0 / 81.0
    c = -0.5
    s = max(0.1, float(stability))
    return s / f * (retention ** (1.0 / c) - 1.0)


def review_kp(state: dict[str, Any], kp_id: str, rating: int, on: date | None = None) -> dict[str, Any]:
    kp = next((x for x in state.get("knowledgePoints", []) if x.get("id") == kp_id), None)
    if not kp:
        raise KeyError(f"未知知识点: {kp_id}")
    day = on or today()
    fsrs = kp.setdefault("fsrs", {"difficulty": 5.0, "stability": 1.0, "due": "", "lastReview": ""})
    difficulty = clamp(float(fsrs.get("difficulty", 5.0)) - 0.8 * (rating - 3), 1.0, 10.0)
    stability = max(0.5, float(fsrs.get("stability", 1.0)))
    if rating <= 1:
        stability = 1.0
    else:
        stability = min(180.0, stability * (1.15 + 0.25 * (rating - 2)))
    interval = max(1.0, next_interval(stability, float(state.get("settings", {}).get("fsrs", {}).get("targetRetention", 0.9))))
    exam = date.fromisoformat(state["examDate"])
    due = day + timedelta(days=round(interval))
    if due >= exam:
        due = exam - timedelta(days=1)
    if due < day:
        due = day
    fsrs.update({"difficulty": round(difficulty, 2), "stability": round(stability, 2),
                 "lastReview": day.isoformat(), "due": due.isoformat()})
    kp["fsrs"] = fsrs
    if rating >= 2:
        days = set(kp.get("correctDays", []))
        days.add(day.isoformat())
        kp["correctDays"] = sorted(days)
        kp["mastered"] = len(kp["correctDays"]) >= 3
    sync_reviews(state)
    return {"kpId": kp_id, "rating": rating, "due": due.isoformat(), "stability": fsrs["stability"], "mastered": kp.get("mastered", False)}


def compute_difficulty(state: dict[str, Any]) -> list[dict[str, Any]]:
    profile = state_profile(state)
    weights = {k: num(v) for k, v in (profile.get("difficultyWeights") or {}).items()} or state.get("settings", {}).get("difficultyWeights", {})
    kps = state.get("knowledgePoints", [])
    by_id = {kp["id"]: kp for kp in kps}
    depth_cache: dict[str, int] = {}

    def depth(kp: dict[str, Any], stack: set[str] | None = None) -> int:
        kid = kp["id"]
        if kid in depth_cache:
            return depth_cache[kid]
        stack = stack or set()
        if kid in stack:
            return 0
        stack.add(kid)
        value = 1 + max((depth(by_id[p], stack) for p in kp.get("prereq", []) if p in by_id), default=0)
        depth_cache[kid] = value
        return value

    max_depth = max((depth(kp) for kp in kps), default=1) or 1
    max_steps = max((float(q.get("steps", q.get("points", 1)) or 1) for q in state.get("questions", [])), default=1) or 1
    attempts_by_q: dict[str, list[dict[str, Any]]] = {}
    for attempt in state.get("attempts", []):
        attempts_by_q.setdefault(attempt.get("questionId", ""), []).append(attempt)
    for kp in kps:
        related = [q for q in state.get("questions", []) if kp["id"] in (q.get("kpIds") or [])]
        related_ids = {q["id"] for q in related}
        tries = [a for qid, rows in attempts_by_q.items() if qid in related_ids for a in rows]
        user_error = (sum(1 for a in tries if not a.get("correct")) / len(tries)) if tries else None
        steps = [float(q.get("steps", q.get("points", 1)) or 1) for q in related]
        past_loss = min(1.0, (sum(steps) / len(steps) / max_steps)) if steps else None
        rel_depth = (depth(kp) - 1) / max(1, max_depth - 1) if max_depth > 1 else 0.0
        flags = 0.0
        if any(q.get("conflict") and q.get("resolution", "pending") == "pending" for q in related):
            flags += 0.5
        if any(m.get("highConfidence") and not m.get("resolved") for m in state.get("mistakes", [])
               if m.get("questionId") in related_ids):
            flags += 0.5
        components = [
            ("pastLoss", past_loss, float(weights.get("pastLoss", 0.35))),
            ("userError", user_error, float(weights.get("userError", 0.30))),
            ("prereqDepth", rel_depth, float(weights.get("prereqDepth", 0.20))),
            ("errorFlags", min(1.0, flags), float(weights.get("errorFlags", 0.15))),
        ]
        available = [(name, value, weight) for name, value, weight in components if value is not None and weight > 0]
        total_weight = sum(weight for _, _, weight in available) or 1.0
        d = sum(value * weight for _, value, weight in available) / total_weight if available else 0.0
        kp["D"] = round(clamp(d), 3)
        kp["difficultyParts"] = {
            "pastLoss": None if past_loss is None else round(past_loss, 3),
            "userError": None if user_error is None else round(user_error, 3),
            "prereqDepth": round(rel_depth, 3),
            "errorFlags": round(min(1.0, flags), 3),
            "evidence": [name for name, _, _ in available],
        }
    return kps


def top_difficult(state: dict[str, Any], n: int = 3) -> list[dict[str, Any]]:
    return sorted(state.get("knowledgePoints", []), key=lambda k: float(k.get("D") or 0), reverse=True)[:n]


def exam_frequency(state: dict[str, Any]) -> dict[str, float]:
    papers = state.get("papers", [])
    if not papers:
        return {t["id"]: 0.5 for t in state.get("questionTypes", [])}
    by_id = {p["id"]: p for p in papers}
    unique = []
    seen = set()
    for paper in papers:
        key = paper.get("sameAs") or paper.get("id")
        if key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    year_by_key = {p.get("id"): p.get("year") for p in papers}
    points: dict[str, list[tuple[float, float]]] = {}
    for q in state.get("questions", []):
        tid = q.get("type")
        if not tid or not q.get("paperId") or q.get("sourceType") == "homework":
            continue
        key = by_id.get(q["paperId"], {}).get("sameAs") or q["paperId"]
        year = year_by_key.get(key) or year_by_key.get(q["paperId"]) or 0
        points.setdefault(tid, []).append((float(q.get("points", 1)), float(year or 0)))
    max_year = max((year for rows in points.values() for _, year in rows), default=0)
    max_avg = max((sum(p for p, _ in rows) / len(rows) for rows in points.values()), default=1.0) or 1.0
    freqs = {}
    for tid in {t["id"] for t in state.get("questionTypes", [])}:
        papers_with = {by_id.get(q.get("paperId"), {}).get("sameAs") or q.get("paperId")
                       for q in state.get("questions", [])
                       if q.get("type") == tid and q.get("paperId") and q.get("sourceType") != "homework"}
        share = len(papers_with) / max(1, len(unique))
        rows = points.get(tid, [])
        if not rows:
            freqs[tid] = 0.0
            continue
        weighted = [(p, 1.2 if max_year and year >= max_year - 1 else 1.0) for p, year in rows]
        avg_points = sum(p * w for p, w in weighted) / sum(w for _, w in weighted)
        freqs[tid] = round(min(1.0, share * (avg_points / max_avg)), 3)
    return freqs


def validate_schedule(state: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    days = state.get("schedule", {}).get("days", [])
    if not days:
        return ["未排期"]
    total = len(days)
    exam = date.fromisoformat(state["examDate"])
    if date.fromisoformat(days[-1]["date"]) >= exam:
        problems.append("排期包含了考试日；考试当天不应排学习任务")
    emergency = state.get("schedule", {}).get("emergency", False)
    types = [t["id"] for t in state.get("questionTypes", [])]
    covered = state.get("schedule", {}).get("coveredTypes") or (types[:8] if emergency else types)
    for tid in covered:
        slots = [(d["day"], s) for d in days for s in d["slots"] if s.get("type") == tid]
        distinct_days = {day for day, _ in slots}
        need = 1 if total == 1 else (2 if emergency else 3)
        if len(slots) < need:
            problems.append(f"题型 {tid} 只出现 {len(slots)} 次（要求 ≥{need}）")
        if len(distinct_days) < need:
            problems.append(f"题型 {tid} 只分布在 {len(distinct_days)} 天（要求 ≥{need} 天）")
    budget = int(state.get("dailyMinutes", 120))
    for day in days:
        if day.get("done"):
            continue
        if not _legacy(state):
            if abs(float(day.get("loadDeviation", 0))) > 0.15:
                problems.append(f"第 {day['day']} 天负载偏离日均超过 15%：{day['minutes']} 分钟（预算 {budget}）")
        else:
            extra_last = int(state.get("settings", {}).get("lastDayExtraMinutes", 30))
            allowed = budget + (extra_last if total >= 5 and day["day"] == total else 0)
            if day["minutes"] > allowed + 5:
                problems.append(f"第 {day['day']} 天 {day['minutes']} 分钟超过预算 {allowed}")
    if total >= 5 and not any(s.get("kind") == "mock" for s in days[-1]["slots"]):
        problems.append("最后一天没有整卷模拟")
    for day in days:
        for review in day.get("reviews", []):
            if date.fromisoformat(day["date"]) >= exam:
                problems.append(f"{review.get('kpId')} 的复习排在考试日或之后")
    return problems


def plan_summary(state: dict[str, Any]) -> str:
    days = state.get("schedule", {}).get("days", [])
    if not days:
        return "未排期"
    phases: dict[str, int] = {}
    for day in days:
        phases[day["phase"]] = phases.get(day["phase"], 0) + 1
    parts = [f"{k} {v} 天" for k, v in phases.items()]
    total_minutes = sum(d["minutes"] for d in days)
    return f"{len(days)} 天 · " + " / ".join(parts) + f" · 合计约 {total_minutes // 60} 小时"
