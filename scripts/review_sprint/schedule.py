"""Phase planning, daily matrix, FSRS spacing, load control and review sync."""
from __future__ import annotations

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
    """Pick distinct days before the final study day (which is the mock day)."""
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


def _slot_kinds(state: dict[str, Any], total: int) -> dict[str, int]:
    settings = state.get("settings", {})
    if total <= 3:
        return {"basic": 2, "past": 2, "advanced": 1}
    return dict(settings.get("dailySlots", {"basic": 4, "past": 2, "advanced": 1}))


def _minutes(state: dict[str, Any], kind: str) -> int:
    return int(state.get("settings", {}).get("minutesPerSlot", {}).get(kind, 10))


def _available(state: dict[str, Any], qtype: str, kind: str, used: set[str], attempted: set[str]) -> bool:
    return any(
        q.get("type") == qtype and q.get("kind") == kind
        and q.get("id") not in used and q.get("id") not in attempted
        for q in state.get("questions", [])
    )


def _pick_question(
    state: dict[str, Any], qtype: str, kind: str, used: set[str], attempted: set[str],
) -> dict[str, Any] | None:
    """Only return an exact kind match; a mismatch is a needs_generation slot."""
    freq = exam_frequency(state)
    pool = [
        q for q in state.get("questions", [])
        if q.get("type") == qtype and q.get("kind") == kind
        and q.get("id") not in used and q.get("id") not in attempted
    ]
    if not pool:
        return None
    kp_weight = {kp["id"]: float(kp.get("weight", 1.0)) for kp in state.get("knowledgePoints", [])}
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
    kps = state.get("knowledgePoints", [])
    if not kps:
        return {}
    build_end = max(2, round(total * 0.4))
    build_days = [d for d in range(2, build_end + 1)] or [max(1, total)]
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for kp in kps:
        by_chapter.setdefault(kp.get("chapter", ""), []).append(kp)
    order = [c.get("id") for c in chapters if c.get("id") in by_chapter] or list(by_chapter)
    flat: list[dict[str, Any]] = []
    for chapter_id in order:
        kps_in_chapter = by_chapter.get(chapter_id, [])
        kps_in_chapter.sort(key=lambda kp: (float(kp.get("weight", 1.0)), float(kp.get("D", 0.5))), reverse=True)
        flat.extend(kps_in_chapter)
    out: dict[str, int] = {}
    for index, kp in enumerate(flat):
        day = build_days[min(len(build_days) - 1, int(index * len(build_days) / max(1, len(flat))))]
        out[kp["id"]] = day
    return out


def build_schedule(state: dict[str, Any], start: date | None = None) -> dict[str, Any]:
    """Build a plan for the days *before* examDate (exam day has no study task)."""
    start = start or today()
    exam = date.fromisoformat(state["examDate"])
    total = (exam - start).days
    if total <= 0:
        raise ValueError(f"考试日 {exam} 已到或已过，无法排期；请先改 --exam-date")
    types = seed_question_types(state)
    type_ids = [t["id"] for t in types]
    freq = exam_frequency(state)
    attempted = {a.get("questionId") for a in state.get("attempts", []) if a.get("questionId")}
    used: set[str] = set(attempted)
    previous_days = state.get("schedule", {}).get("days", [])
    done_by_date = {d.get("date"): d.get("doneAt") for d in previous_days if d.get("done")}
    first_days = _kp_first_days(state, total)
    days: list[dict[str, Any]] = []
    emergency = total <= 3
    normal_types = type_ids[: min(len(type_ids), 16)]
    per_day = sum(_slot_kinds(state, total).values()) if total > 3 else 5
    last_type_day = total - 1 if total >= 5 else total
    capacity = max(1, last_type_day * per_day // 3)
    if emergency:
        capacity = min(8, capacity)
    # emergency keeps the most frequently tested types, not the first T ids
    covered_types = sorted(normal_types, key=lambda tid: (freq.get(tid, 0), tid), reverse=True)[:capacity]

    type_days: dict[str, list[int]] = {tid: _spread_days(total, 3) for tid in covered_types}

    for day_no in range(1, total + 1):
        current = start + timedelta(days=day_no - 1)
        phase = phase_for(day_no, total, state.get("settings", {}).get("phaseRatios"))
        if day_no == total and total >= 5:
            slots = [{"kind": "mock", "type": "MOCK", "qid": None, "minutes": _minutes(state, "mock")} for _ in range(10)]
            slots += [{"kind": "proof", "type": "PROOF", "qid": None, "minutes": _minutes(state, "proof")} for _ in range(2)]
            kp_ids: list[str] = []
        else:
            slots = []
            for kind, count in _slot_kinds(state, total).items():
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

    # place each covered type on three distinct days, preferring the slot kind we actually have
    for tid in covered_types:
        for day_no in type_days[tid][:3]:
            day = days[day_no - 1]
            free = [s for s in day["slots"] if not s["type"]]
            if not free:
                continue
            preferred = "past" if _available(state, tid, "past", used, attempted) else "basic"
            slot = next((s for s in free if s["kind"] == preferred), free[0])
            slot["type"] = tid

    # fill remaining slots with least-used types, max 2 of a type per day
    for day in days:
        if day["day"] == total and total >= 5:
            continue
        for slot in day["slots"]:
            if slot["type"]:
                continue
            counts = {tid: sum(1 for s in day["slots"] if s["type"] == tid) for tid in normal_types}
            candidates = [tid for tid in normal_types if counts.get(tid, 0) < 2] or normal_types
            candidates.sort(key=lambda tid: (sum(1 for d in days for s in d["slots"] if s["type"] == tid), tid))
            slot["type"] = candidates[0]

    # attach exact-kind questions; no silent substitution
    for day in days:
        for slot in day["slots"]:
            if slot["kind"] in {"mock", "proof"}:
                slot["status"] = "needs_generation"
                continue
            q = _pick_question(state, slot["type"], slot["kind"], used, attempted)
            if q:
                slot["qid"] = q["id"]
                slot["status"] = "ready"
            else:
                slot["qid"] = None
                slot["status"] = "needs_generation"
        day["minutes"] = sum(s["minutes"] for s in day["slots"])

    # one source of truth: FSRS due dates; day.reviews is a derived view
    for kp in state.get("knowledgePoints", []):
        taught = first_days.get(kp["id"])
        if not taught:
            continue
        fsrs = kp.setdefault("fsrs", {"difficulty": 5.0, "stability": 1.0, "due": "", "lastReview": ""})
        if not fsrs.get("due"):
            due = start + timedelta(days=taught - 1 + 1)
            if due >= exam:
                due = exam - timedelta(days=1)
            if due < start:
                due = start
            fsrs["due"] = due.isoformat()

    for day in days:
        if day["date"] in done_by_date:
            day["done"] = True
            day["doneAt"] = done_by_date[day["date"]]

    state["schedule"] = {
        "days": days, "builtAt": today().isoformat(), "totalDays": total,
        "emergency": emergency, "coveredTypes": covered_types,
    }
    state["phasePlan"] = phase_plan(total, state.get("settings", {}).get("phaseRatios"))
    sync_reviews(state)

    # load control: reviews are kept; new-content slots are removed first
    budget = int(state.get("dailyMinutes", 120))
    for day in days:
        total_minutes = sum(s["minutes"] for s in day["slots"]) + sum(r["minutes"] for r in day["reviews"])
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
        if removed:
            day["warning"] = f"复习占用较高，减少 {removed} 道新题（复习项保留）"
        if total_minutes > budget:
            day["warning"] = (day["warning"] + "；" if day["warning"] else "") + "复习已超今日预算，建议延长当天时间或调整每日预算"
    return state["schedule"]


def sync_reviews(state: dict[str, Any]) -> None:
    """Derive day.reviews from the single FSRS due date per knowledge point."""
    days = state.get("schedule", {}).get("days", [])
    if not days:
        return
    exam = date.fromisoformat(state["examDate"])
    for day in days:
        day["reviews"] = []
    by_date = {day["date"]: day for day in days}
    kp_by_id = {kp["id"]: kp for kp in state.get("knowledgePoints", [])}
    for kp in state.get("knowledgePoints", []):
        due = (kp.get("fsrs") or {}).get("due") or ""
        if not due or due >= exam.isoformat():
            continue
        day = by_date.get(due)
        if not day:
            continue
        day["reviews"].append({
            "kpId": kp["id"],
            "title": kp.get("title", ""),
            "interval": 1,
            "minutes": _minutes(state, "review"),
            "status": "planned",
            "D": kp.get("D", 0),
        })
    for day in days:
        day["reviews"].sort(key=lambda r: -float(r.get("D") or 0))
        cap = int(state.get("settings", {}).get("maxReviewsPerDay", 6))
        if len(day["reviews"]) > cap:
            overflow = day["reviews"][cap:]
            day["reviews"] = day["reviews"][:cap]
            day["reviewOverflow"] = overflow
            note = f"另有 {len(overflow)} 条到期复习未排入（保留在 reviewOverflow，请用机动时间补）"
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
    if due >= exam:
        due = exam - timedelta(days=1)
    if due < day:
        due = day
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
    sync_reviews(state)
    return {"kpId": kp_id, "rating": rating, "due": due.isoformat(), "stability": fsrs["stability"], "mastered": kp.get("mastered", False)}


def compute_difficulty(state: dict[str, Any]) -> list[dict[str, Any]]:
    weights = state.get("settings", {}).get("difficultyWeights", {})
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
            ("pastLoss", past_loss, weights.get("pastLoss", 0.35)),
            ("userError", user_error, weights.get("userError", 0.30)),
            ("prereqDepth", rel_depth, weights.get("prereqDepth", 0.20)),
            ("errorFlags", min(1.0, flags), weights.get("errorFlags", 0.15)),
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
    kps = sorted(state.get("knowledgePoints", []), key=lambda k: float(k.get("D", 0)), reverse=True)
    return kps[:n]


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
    extra_last = int(state.get("settings", {}).get("lastDayExtraMinutes", 30))
    for day in days:
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
