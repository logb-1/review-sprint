"""Phase planning, 7-question daily matrix, spacing/FSRS and load control."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from .util import clamp, today

DEFAULT_CSAPP_TYPES = [
    ("T1", "数制与编码转换"),
    ("T2", "整数表示与运算"),
    ("T3", "浮点表示"),
    ("T4", "浮点运算与舍入"),
    ("T5", "数据对齐与结构体布局"),
    ("T6", "汇编阅读与寻址"),
    ("T7", "条件跳转与循环"),
    ("T8", "过程调用与栈帧"),
    ("T9", "数组与指针"),
    ("T10", "结构体/联合体/枚举"),
    ("T11", "链接与符号"),
    ("T12", "重定位与 ELF"),
    ("T13", "异常与中断"),
    ("T14", "进程与系统调用"),
    ("T15", "存储层次与缓存"),
    ("T16", "程序优化与性能"),
]

DEFAULT_GENERIC_TYPES = [
    ("T1", "概念辨析"), ("T2", "性质判断"), ("T3", "公式计算"), ("T4", "推导证明"),
    ("T5", "图表分析"), ("T6", "案例分析"), ("T7", "流程设计"), ("T8", "比较异同"),
    ("T9", "综合应用"), ("T10", "实验/实践"), ("T11", "简答论述"), ("T12", "开放探究"),
]


def seed_question_types(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("questionTypes"):
        return state["questionTypes"]
    domain = state.get("domain", "general")
    source = DEFAULT_CSAPP_TYPES if domain == "cs_systems" else DEFAULT_GENERIC_TYPES
    state["questionTypes"] = [
        {"id": tid, "name": name, "signals": "", "formula": "", "trap": ""}
        for tid, name in source
    ]
    return state["questionTypes"]


def phase_for(day: int, total: int, ratios: dict[str, float] | None = None) -> str:
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


def phase_plan(total: int, ratios: dict[str, float] | None = None) -> list[dict[str, Any]]:
    return [{"day": d, "phase": phase_for(d, total, ratios)} for d in range(1, total + 1)]


def _spread_days(total: int, count: int) -> list[int]:
    """Pick `count` distinct days spread across the days before the exam."""
    if total <= 1:
        return [1]
    available = list(range(1, total)) or [1]
    if count >= len(available):
        return available
    if count <= 1:
        return [available[len(available) // 2]]
    picks: list[int] = []
    for i in range(count):
        index = round((len(available) - 1) * i / max(1, count - 1))
        day = available[index]
        if day in picks:
            for candidate in available:
                if candidate not in picks:
                    day = candidate
                    break
        picks.append(day)
    return picks


def _slot_kinds(state: dict[str, Any], total: int) -> dict[str, int]:
    settings = state.get("settings", {})
    if total <= 3:
        return {"basic": 2, "past": 2, "advanced": 1}
    return dict(settings.get("dailySlots", {"basic": 4, "past": 2, "advanced": 1}))


def _minutes(state: dict[str, Any], kind: str) -> int:
    return int(state.get("settings", {}).get("minutesPerSlot", {}).get(kind, 10))


def _pick_question(state: dict[str, Any], qtype: str, kind: str, used: set[str]) -> dict[str, Any] | None:
    pool = [q for q in state.get("questions", []) if q.get("type") == qtype and q.get("id") not in used]
    if not pool:
        return None
    exact = [q for q in pool if q.get("kind") == kind]
    chosen = (exact or pool)[0]
    used.add(chosen["id"])
    return chosen


def _kp_first_days(state: dict[str, Any], total: int) -> dict[str, int]:
    chapters = state.get("chapters", [])
    kps = state.get("knowledgePoints", [])
    if not kps:
        return {}
    build_days = [d for d in range(2, max(2, round(total * 0.4)) + 1)] or [max(1, total - 1)]
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for kp in kps:
        by_chapter.setdefault(kp.get("chapter", ""), []).append(kp)
    order = [c.get("id") for c in chapters if c.get("id") in by_chapter] or list(by_chapter)
    flat: list[dict[str, Any]] = []
    for chapter_id in order:
        flat.extend(by_chapter.get(chapter_id, []))
    out: dict[str, int] = {}
    for index, kp in enumerate(flat):
        day = build_days[min(len(build_days) - 1, int(index * len(build_days) / max(1, len(flat))))]
        out[kp["id"]] = day
    return out


def build_schedule(state: dict[str, Any], start: date | None = None) -> dict[str, Any]:
    """Build a deterministic day/slot plan and attach review due dates."""
    total = max(1, (date.fromisoformat(state["examDate"]) - (start or today())).days + 1)
    types = seed_question_types(state)
    type_ids = [t["id"] for t in types]
    used: set[str] = set()
    first_days = _kp_first_days(state, total)
    days: list[dict[str, Any]] = []
    emergency = total <= 3
    normal_types = type_ids[: min(len(type_ids), 16)]
    per_day = sum(_slot_kinds(state, total).values()) if total > 3 else 5
    capacity = max(1, ((total - 1) if total >= 5 else total) * per_day // 3)
    if emergency:
        capacity = min(8, capacity)
    covered_types = normal_types[: min(len(normal_types), capacity)]

    # target 3 appearances for each covered type at three distinct days
    type_days: dict[str, list[int]] = {tid: _spread_days(total, 3) for tid in covered_types}

    for day_no in range(1, total + 1):
        current = (start or today()) + timedelta(days=day_no - 1)
        phase = phase_for(day_no, total, state.get("settings", {}).get("phaseRatios"))
        if day_no == total and total >= 5:
            slots = [{"kind": "mock", "type": "MOCK", "qid": None, "minutes": _minutes(state, "mock")} for _ in range(10)]
            slots += [{"kind": "proof", "type": "PROOF", "qid": None, "minutes": _minutes(state, "proof")} for _ in range(2)]
            kp_ids: list[str] = []
        else:
            kinds = _slot_kinds(state, total)
            slots = []
            for kind, count in kinds.items():
                slots.extend({"kind": kind, "type": "", "qid": None, "minutes": _minutes(state, kind)} for _ in range(count))
            kp_ids = [kp["id"] for kp in state.get("knowledgePoints", []) if first_days.get(kp["id"]) == day_no]
        days.append({
            "day": day_no,
            "date": current.isoformat(),
            "phase": phase,
            "slots": slots,
            "reviews": [],
            "kpIds": kp_ids,
            "minutes": sum(s["minutes"] for s in slots),
            "done": False,
            "warning": "",
        })

    # 1) place each covered type on its three target days, one slot per day
    for tid in covered_types:
        for day_no in type_days[tid][:3]:
            day = days[day_no - 1]
            free = [s for s in day["slots"] if not s["type"]]
            if not free:
                continue
            kind = "past" if tid in {"T11", "T12"} else "basic"
            slot = next((s for s in free if s["kind"] == kind), free[0])
            slot["type"] = tid

    # 2) fill remaining slots with least-used types, no more than 2 of a type/day
    for day in days:
        if day["day"] == total and total >= 5:
            continue
        for slot in day["slots"]:
            if slot["type"]:
                continue
            counts = {tid: sum(1 for s in day["slots"] if s["type"] == tid) for tid in normal_types}
            candidates = [tid for tid in normal_types if counts.get(tid, 0) < 2]
            if not candidates:
                candidates = normal_types
            candidates.sort(key=lambda tid: (sum(1 for d in days for s in d["slots"] if s["type"] == tid), tid))
            slot["type"] = candidates[0]

    # 3) attach real questions or mark placeholders
    for day in days:
        for slot in day["slots"]:
            if slot["kind"] in {"mock", "proof"}:
                slot["status"] = "needs_generation"
                continue
            q = _pick_question(state, slot["type"], slot["kind"], used)
            if q:
                slot["qid"] = q["id"]
                slot["status"] = "ready"
            else:
                slot["qid"] = None
                slot["status"] = "needs_generation"
        day["minutes"] = sum(s["minutes"] for s in day["slots"])

    # 4) spacing reviews: d+1, d+3, d+7, d+14, clipped before the exam
    exam = date.fromisoformat(state["examDate"])
    review_seen: set[tuple[str, str]] = set()
    for kp in state.get("knowledgePoints", []):
        taught = first_days.get(kp["id"])
        if not taught:
            continue
        fsrs = kp.setdefault("fsrs", {"difficulty": 5.0, "stability": 1.0, "due": "", "lastReview": ""})
        for interval in (1, 3, 7, 14):
            due = (start or today()) + timedelta(days=taught - 1 + interval)
            if due >= exam:
                due = exam - timedelta(days=1)
            if due < (start or today()):
                continue
            day = days[(due - (start or today())).days]
            if day["day"] == total and total >= 5:
                day = days[max(0, total - 2)]
            key = (day["date"], kp["id"])
            if key in review_seen:
                continue
            review_seen.add(key)
            day["reviews"].append({
                "kpId": kp["id"],
                "title": kp.get("title", ""),
                "interval": interval,
                "minutes": _minutes(state, "review"),
                "status": "planned",
            })
            if not fsrs.get("due"):
                fsrs["due"] = due.isoformat()

    # 5) load control: keep spacing reviews, trim new-content slots if needed
    budget = int(state.get("dailyMinutes", 120))
    max_reviews = int(state.get("settings", {}).get("maxReviewsPerDay", 6))
    review_minutes = max(1, _minutes(state, "review"))
    review_budget = max(review_minutes, int(budget * 0.4))
    for day in days:
        # prioritize short intervals and harder KPs
        day["reviews"].sort(key=lambda r: (int(r.get("interval", 99)), -float(
            next((kp.get("D", 0) for kp in state.get("knowledgePoints", []) if kp.get("id") == r.get("kpId")), 0)
        )))
        cap = min(max_reviews, max(0, review_budget // review_minutes))
        trimmed = 0
        if len(day["reviews"]) > cap:
            trimmed = len(day["reviews"]) - cap
            day["reviews"] = day["reviews"][:cap]
        slot_minutes = sum(s["minutes"] for s in day["slots"])
        total_minutes = slot_minutes + sum(r["minutes"] for r in day["reviews"])
        removed = 0
        while total_minutes > budget and len(day["slots"]) > 3:
            removable = [s for s in day["slots"] if s.get("kind") in {"advanced", "basic", "past"}]
            if not removable:
                break
            victim = removable[-1]
            day["slots"].remove(victim)
            removed += 1
            total_minutes -= victim["minutes"]
        day["minutes"] = total_minutes
        notes = []
        if trimmed:
            notes.append(f"复习项按优先级保留 {cap} 条（另有 {trimmed} 条未排入，需用机动时间补）")
        if removed:
            notes.append(f"复习占比超过 40%，减少 {removed} 道新题")
        if notes:
            day["warning"] = "；".join(notes)

    state["schedule"] = {
        "days": days, "builtAt": today().isoformat(), "totalDays": total,
        "emergency": emergency, "coveredTypes": covered_types,
    }
    state["phasePlan"] = phase_plan(total, state.get("settings", {}).get("phaseRatios"))
    return state["schedule"]


def due_reviews(state: dict[str, Any], on: date | None = None) -> list[dict[str, Any]]:
    day = (on or today()).isoformat()
    out = []
    for kp in state.get("knowledgePoints", []):
        fsrs = kp.get("fsrs") or {}
        due = fsrs.get("due") or ""
        if due and due <= day:
            out.append({"kpId": kp["id"], "title": kp.get("title", ""), "due": due, "stability": fsrs.get("stability", 1.0)})
    for mistake in state.get("mistakes", []):
        if not mistake.get("resolved") and str(mistake.get("retestDue", "")) <= day:
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
    """Update FSRS state for a knowledge point. rating: 1=Again 2=Hard 3=Good 4=Easy."""
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
    buffer_days = int(state.get("settings", {}).get("fsrs", {}).get("examBufferDays", 3))
    if due >= exam:
        due = max(day + timedelta(days=1), exam - timedelta(days=buffer_days))
    fsrs.update({
        "difficulty": round(difficulty, 2),
        "stability": round(stability, 2),
        "lastReview": day.isoformat(),
        "due": due.isoformat(),
    })
    kp["fsrs"] = fsrs
    if rating >= 2:
        days = set(kp.get("correctDays", []))
        days.add(day.isoformat())
        kp["correctDays"] = sorted(days)
        kp["mastered"] = len(kp["correctDays"]) >= 3
    return {"kpId": kp_id, "rating": rating, "due": due.isoformat(), "stability": fsrs["stability"], "mastered": kp.get("mastered", False)}


def compute_difficulty(state: dict[str, Any]) -> list[dict[str, Any]]:
    weights = state.get("settings", {}).get("difficultyWeights", {})
    kps = state.get("knowledgePoints", [])
    max_depth = max(1, max(len(kp.get("prereq", [])) for kp in kps)) if kps else 1
    attempts_by_q: dict[str, list[dict[str, Any]]] = {}
    for attempt in state.get("attempts", []):
        attempts_by_q.setdefault(attempt.get("questionId", ""), []).append(attempt)
    for kp in kps:
        related = [q for q in state.get("questions", []) if kp["id"] in (q.get("kpIds") or [])]
        related_ids = {q["id"] for q in related}
        tries = [a for qid, rows in attempts_by_q.items() if qid in related_ids for a in rows]
        user_error = (sum(1 for a in tries if not a.get("correct")) / len(tries)) if tries else 0.5
        steps = [float(q.get("steps", 3)) for q in related]
        past_loss = min(1.0, (sum(steps) / len(steps) / 8.0)) if steps else 0.5
        depth = len(kp.get("prereq", [])) / max_depth
        flags = 0.0
        if any(q.get("conflict") for q in related):
            flags += 0.5
        if any(m.get("highConfidence") and not m.get("resolved") for m in state.get("mistakes", [])
               if m.get("questionId") in related_ids):
            flags += 0.5
        d = (
            weights.get("pastLoss", 0.35) * past_loss
            + weights.get("userError", 0.30) * user_error
            + weights.get("prereqDepth", 0.20) * depth
            + weights.get("errorFlags", 0.15) * min(1.0, flags)
        )
        kp["D"] = round(clamp(d), 3)
        kp["difficultyParts"] = {
            "pastLoss": round(past_loss, 3), "userError": round(user_error, 3),
            "prereqDepth": round(depth, 3), "errorFlags": round(min(1.0, flags), 3),
        }
    return kps


def top_difficult(state: dict[str, Any], n: int = 3) -> list[dict[str, Any]]:
    kps = sorted(state.get("knowledgePoints", []), key=lambda k: float(k.get("D", 0)), reverse=True)
    return kps[:n]


def exam_frequency(state: dict[str, Any]) -> dict[str, float]:
    papers = state.get("papers", [])
    if not papers:
        return {t["id"]: 0.5 for t in state.get("questionTypes", [])}
    unique = []
    seen = set()
    for paper in papers:
        key = paper.get("sameAs") or paper.get("id")
        if key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    counts: dict[str, int] = {}
    points: dict[str, list[float]] = {}
    for q in state.get("questions", []):
        if not q.get("paperId"):
            continue
        tid = q.get("type")
        if not tid:
            continue
        counts[tid] = counts.get(tid, 0) + 1
        points.setdefault(tid, []).append(float(q.get("points", 1)))
    freqs = {}
    max_avg = max((sum(v) / len(v) for v in points.values()), default=1.0) or 1.0
    for tid in {t["id"] for t in state.get("questionTypes", [])}:
        papers_with = len({q.get("paperId") for q in state.get("questions", []) if q.get("type") == tid and q.get("paperId")})
        share = papers_with / max(1, len(unique))
        avg_points = sum(points.get(tid, [1])) / max(1, len(points.get(tid, [1])))
        freqs[tid] = round(min(1.0, share * (avg_points / max_avg)), 3)
    return freqs


def validate_schedule(state: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    days = state.get("schedule", {}).get("days", [])
    if not days:
        return ["未排期"]
    total = len(days)
    emergency = state.get("schedule", {}).get("emergency", False)
    types = [t["id"] for t in state.get("questionTypes", [])]
    covered = state.get("schedule", {}).get("coveredTypes") or (types[:8] if emergency else types)
    for tid in covered:
        slots = [(d["day"], s) for d in days for s in d["slots"] if s.get("type") == tid]
        distinct_days = {day for day, _ in slots}
        need = 2 if emergency else 3
        if len(slots) < need:
            problems.append(f"题型 {tid} 只出现 {len(slots)} 次（要求 ≥{need}）")
        if len(distinct_days) < need:
            problems.append(f"题型 {tid} 只分布在 {len(distinct_days)} 天（要求 ≥{need} 天）")
    budget = int(state.get("dailyMinutes", 120))
    extra_last = int(state.get("settings", {}).get("lastDayExtraMinutes", 30))
    for day in days:
        allowed = budget + (extra_last if total >= 5 and day["day"] == total else 0)
        if day["minutes"] > allowed + 5:
            problems.append(f"第 {day['day']} 天 {day['minutes']} 分钟超过预算 {allowed}")
    if total >= 5 and not any(s.get("kind") == "mock" for s in days[-1]["slots"]):
        problems.append("最后一天没有整卷模拟")
    exam = date.fromisoformat(state["examDate"])
    for day in days:
        for review in day.get("reviews", []):
            due = date.fromisoformat(day["date"])
            if due >= exam:
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
