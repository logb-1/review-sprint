"""Command-line interface for review-sprint."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import __version__
from .answer_check import compare, compute, primary_value
from .audit import audit, format_audit
from .bilibili import BiliClient, BiliError, cookie_status, load_cookie, search_url
from .build import BuildDependencyError, BuildError, BuildStateError, build as build_run
from .books import apply_fill, collect_fill_tasks, normalize_rubric, write_books
from .export import export_all
from .ingest import MATERIAL_LABELS, setup
from .mastery import update_mastery
from .quantify import quantify, schedule_workload
from .keywords import describe, extract_keywords
from .render import daily_markdown, plan_markdown, source_label
from .schedule import (
    build_schedule, compute_difficulty, due_reviews, ensure_slot_ids, exam_frequency,
    pending_generation, plan_summary, review_kp, sync_reviews, validate_schedule,
)
from .state import Session, add_attempt, load_session, mark_day_done
from .subjects import SubjectConfirmationRequired, profile_names
from .topics import DOMAINS
from .util import human_minutes, read_text, today, write_json, write_text

DEFAULT_WORKSPACE = "review-sprint-workspace"


def _session(args: argparse.Namespace) -> Session:
    session = load_session(Path(args.workspace))
    if not session.exists():
        raise SystemExit(f"未找到 {session.state_path}。先运行: coach.py init --course 课程名 --exam-date YYYY-MM-DD --materials 资料目录")
    return session


def _print_md(text: str) -> None:
    print(text)


def _write_outputs(session: Session) -> dict[str, Any]:
    """Rebuild and re-render the five books, then refresh the audit report."""
    st = session.state
    quantify(st, target=st.get("targetScore", 80), days=st.get("days"), daily_minutes=st.get("dailyMinutes"))
    build_schedule(st, days=st.get("days"))
    ensure_slot_ids(st.get("schedule", {}).get("days", []))
    schedule_workload(st)
    out = Path(st.get("build", {}).get("out") or (session.workspace / "output"))
    formats = st.get("build", {}).get("formats") or ["md", "docx"]
    paths = write_books(session, out, formats=formats)
    st.setdefault("build", {})["fillTasks"] = len(collect_fill_tasks(session))
    session.save()
    report = audit(session)
    st["build"]["auditOk"] = report["ok"]
    write_text(out / "质检报告.md", format_audit(report))
    session.save()
    return {"paths": [str(p) for p in paths], "audit": report}


def cmd_next(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    pending = pending_generation(st)
    tasks = collect_fill_tasks(session)
    day = session.find_day()
    if pending:
        action, command = "generate", "coach.py fill --tasks"
        reason = f"计划还有 {len(pending)} 个题位没有题目；先把题位生成任务交给模型，再回填。"
    elif tasks:
        action, command = "fill", "coach.py fill --tasks"
        reason = f"还有 {len(tasks)} 处讲解/答案/评分点等待模型回填。"
    elif not day:
        action, command = "done", "coach.py status"
        reason = "所有复习日都已完成。"
    else:
        path = session.daily_dir / f"D{day['day']:02d}-{day['date']}.md"
        if not path.exists():
            action, command = "today", f"coach.py today --day {day['day']}"
            reason = f"第 {day['day']} 天（{day['date']}）还没有学习包。"
        else:
            qids = [s["qid"] for s in day.get("slots", []) if s.get("qid")]
            if qids:
                action, command = "answer", f"coach.py answer --qid {qids[0]} --result correct|wrong"
                reason = f"第 {day['day']} 天学习包已生成；先做第一题 {qids[0]} 并记录结果。"
            else:
                action, command = "today", f"coach.py today --day {day['day']} --force"
                reason = "当天学习包没有可作答题目。"
    payload = {"action": action, "command": command, "reason": reason,
               "day": day.get("day") if day else None,
               "pendingGeneration": len(pending), "fillTasks": len(tasks)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"下一步：{command}")
        print(f"理由：{reason}")
    return 0


def cmd_catchup(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    today = date.today()
    missed = [
        day for day in st.get("schedule", {}).get("days", [])
        if day.get("date") and date.fromisoformat(day["date"]) < today and not day.get("done")
    ]
    if not missed:
        payload = {"ok": True, "missed": 0, "minutes": 0, "message": "没有落后的复习日。"}
    else:
        minutes = sum(int(day.get("minutes") or 0) for day in missed)
        first = missed[0]
        payload = {
            "ok": False,
            "missed": len(missed),
            "minutes": minutes,
            "days": [{"day": day["day"], "date": day["date"], "minutes": day.get("minutes", 0)} for day in missed],
            "command": f"coach.py today --day {first['day']}",
            "message": f"落后 {len(missed)} 天，约 {human_minutes(minutes)}；先补最早的一天，不要一次跳读。",
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["message"])
        for day in payload.get("days", []):
            print(f"- 第 {day['day']} 天（{day['date']}）约 {human_minutes(day['minutes'])}")
        if payload.get("command"):
            print(f"建议：{payload['command']}")
    return 0 if not missed else 1


def cmd_report(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    cutoff = today() - timedelta(days=max(1, args.days) - 1)
    attempts = [
        a for a in st.get("attempts", [])
        if str(a.get("date") or "") >= cutoff.isoformat()
    ]
    by_cause: dict[str, dict[str, int]] = {}
    by_day: dict[str, dict[str, int]] = {}
    for attempt in attempts:
        cause = str(attempt.get("cause") or "未标注")
        bucket = by_cause.setdefault(cause, {"correct": 0, "wrong": 0})
        bucket["correct" if attempt.get("correct") else "wrong"] += 1
        day = str(attempt.get("date") or "")
        bucket = by_day.setdefault(day, {"correct": 0, "wrong": 0})
        bucket["correct" if attempt.get("correct") else "wrong"] += 1
    unresolved = [m for m in st.get("mistakes", []) if not m.get("resolved")]
    payload = {
        "days": max(1, args.days),
        "attempts": len(attempts),
        "correct": sum(1 for a in attempts if a.get("correct")),
        "wrong": sum(1 for a in attempts if not a.get("correct")),
        "byCause": by_cause,
        "byDay": by_day,
        "unresolvedMistakes": len(unresolved),
        "seconds": sum(int(a.get("timeSec") or a.get("seconds") or 0) for a in attempts),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"# 最近 {payload['days']} 天作答报告")
    print(f"- 作答 {payload['attempts']} 次：正确 {payload['correct']}，错误 {payload['wrong']}，未解决错题 {payload['unresolvedMistakes']}")
    if by_cause:
        print("- 错因聚合：")
        for cause, item in sorted(by_cause.items()):
            print(f"  - {cause}: 正确 {item['correct']} / 错误 {item['wrong']}")
    if not attempts:
        print("- 还没有作答记录；先 `coach.py today` 再 `coach.py answer`。")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    if (workspace / "study_state.json").exists() and not (args.force or args.refresh_materials):
        message = f"{workspace} 已有 study_state.json；为避免清空作答，加 --refresh-materials 合并历史，或加 --force 备份后重来"
        if args.json:
            print(json.dumps({"error": "state_exists", "message": message}, ensure_ascii=False, indent=2))
        else:
            print(message)
        return 3
    materials = [Path(p) for p in args.materials]
    materials += [Path(p) for p in (getattr(args, "past_papers", None) or [])]
    missing = [str(p) for p in materials if not p.exists()]
    if missing:
        if args.json:
            print(json.dumps({"error": "missing_materials", "paths": missing}, ensure_ascii=False, indent=2))
        else:
            print("资料路径不存在: " + ", ".join(missing))
        return 2
    subject = args.subject or args.domain
    if subject and subject not in profile_names() and subject not in DOMAINS:
        if args.json:
            print(json.dumps({"error": "unknown_subject", "subject": subject}, ensure_ascii=False, indent=2))
        else:
            print("未知科目；可用：" + ", ".join(profile_names()))
        return 2
    if args.days:
        exam_date = today() + timedelta(days=int(args.days))
        if args.exam_date:
            stated = date.fromisoformat(args.exam_date)
            if (stated - today()).days != int(args.days):
                print(f"⚠️ 考试日期与 --days 不一致；以 --days={args.days} 为准")
    else:
        if not args.exam_date:
            raise SystemExit("需要 --days（复习天数）或 --exam-date（考试日期）")
        exam_date = date.fromisoformat(args.exam_date)
    if args.daily_minutes is None:
        args.daily_minutes = 120
        if not args.json:
            print("每日分钟：120（用户未提供，使用默认值；可在下次用 --daily-minutes 修改）")
    if exam_date <= today():
        message = "考试日期必须晚于今天；考试当天及之后无法排学习任务"
        if args.json:
            print(json.dumps({"error": "exam_date", "message": message}, ensure_ascii=False, indent=2))
        else:
            print(message)
        return 2
    try:
        state = setup(
            workspace, args.course, exam_date, materials,
            daily_minutes=args.daily_minutes, target_score=args.target,
            language=args.lang, density=args.density, domain=subject,
            days=int(args.days) if args.days else None,
            force=args.force, refresh_materials=args.refresh_materials,
        )
    except SubjectConfirmationRequired as exc:
        if args.json:
            print(json.dumps({"needsConfirmation": exc.detection}, ensure_ascii=False, indent=2))
        else:
            print("⚠️ 科目识别置信度不足，不能自动开始。请确认科目：")
            candidates = exc.detection.get("candidates", [])
            if not candidates:
                print("  - 未命中任何画像；可用：" + " / ".join(profile_names()))
            for item in candidates:
                print(f"  - {item['subject']}（命中分 {item['score']}）")
            print("确认后加 --subject <名称> 重跑。")
        return 2
    if args.json:
        print(json.dumps({
            "ok": True, "course": state["course"], "subject": state["subject"],
            "subjectConfidence": state.get("subjectConfidence"), "days": state.get("days"),
            "examDate": state["examDate"], "schedule": plan_summary(state),
            "chapters": len(state["chapters"]), "knowledgePoints": len(state["knowledgePoints"]),
            "questions": len(state["questions"]), "papers": len(state["papers"]),
            "workspace": str(workspace.resolve()),
        }, ensure_ascii=False, indent=2))
        return 0
    print(f"✅ 已建立工作区：{workspace.resolve()}")
    print(f"课程：{state['course']} · 考试：{state['examDate']} · 科目：{state['subject']}（置信度 {state.get('subjectConfidence')}）")
    print(f"材料：{len(state['materials'])} 个（可用 {sum(1 for m in state['materials'] if m['status'] == 'ok')}）")
    print(f"章节：{len(state['chapters'])} · 知识点：{len(state['knowledgePoints'])} · 试卷：{len(state['papers'])} · 题目：{len(state['questions'])}")
    days = state.get("schedule", {}).get("days", [])
    if days:
        print(f"学习日：{days[0]['date']} ~ {days[-1]['date']}（共 {len(days)} 天；考试日 {state['examDate']} 当天不排任务）")
    print(plan_summary(state))
    problems = validate_schedule(state)
    if problems:
        print("⚠️ 排期警告：")
        for item in problems:
            print("  - " + item)
    print("\n下一步：")
    print(f"  coach.py plan --workspace {workspace}")
    print(f"  coach.py today --workspace {workspace}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    compute_difficulty(st)
    due = due_reviews(st)
    if args.json:
        print(json.dumps({
            "progress": session.progress_line(), "course": st["course"],
            "subject": st.get("subject"), "days": st.get("days"),
            "target": st.get("targetScore"), "summary": plan_summary(st),
            "due": due, "mistakes": len([m for m in st.get("mistakes", []) if not m.get("resolved")]),
            "videos": len(st.get("videos", [])), "problems": validate_schedule(st),
        }, ensure_ascii=False, indent=2, default=str))
        return 0
    print(session.progress_line())
    print(f"课程：{st['course']} · 科目：{st.get('subject', 'general')} · 天数：{st.get('days', len(st.get('schedule', {}).get('days', [])))} · 目标：{st.get('targetScore', 80)}")
    print(plan_summary(st))
    print(f"到期复习：{len(due)} 项；错题：{len([m for m in st.get('mistakes', []) if not m.get('resolved')])} 条；视频：{len(st.get('videos', []))} 条")
    if due:
        print("\n今日到期：")
        for item in due[:10]:
            print(f"  - {item.get('kpId') or item.get('questionId')} {item.get('title', '')}")
    problems = validate_schedule(st)
    if problems:
        print("\n⚠️ 排期问题：")
        for item in problems:
            print("  - " + item)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    session = _session(args)
    if args.rebuild or not session.state.get("schedule", {}).get("days"):
        build_schedule(session.state)
        schedule_workload(session.state)
        session.save()
    text = plan_markdown(session.state)
    path = session.exports_dir / "排期.md"
    path.write_text(text, encoding="utf-8")
    if args.json:
        print(json.dumps({"markdown": text, "path": str(path), "summary": plan_summary(session.state),
                          "problems": validate_schedule(session.state)}, ensure_ascii=False, indent=2))
        return 0
    _print_md(text)
    problems = validate_schedule(session.state)
    if problems:
        print("\n⚠️ 排期问题：")
        for item in problems:
            print("  - " + item)
    print(f"\n已写入 {path}")
    return 0


def cmd_today(args: argparse.Namespace) -> int:
    session = _session(args)
    day = session.find_day(args.day)
    if not day:
        raise SystemExit(f"没有第 {args.day} 天的安排")
    path = session.daily_dir / f"D{day['day']:02d}-{day['date']}.md"
    if path.exists() and not args.force:
        text = read_text(path)
        if args.json:
            print(json.dumps({"markdown": text, "path": str(path), "overwritten": False}, ensure_ascii=False, indent=2))
        else:
            _print_md(text)
            print(f"\n<!-- 已存在，未覆盖：{path}；需要重生成用 --force -->")
        return 0
    compute_difficulty(session.state)
    session.save()
    text = daily_markdown(session, day, args.density)
    write_text(path, text)
    if args.json:
        print(json.dumps({"markdown": text, "path": str(path), "overwritten": True}, ensure_ascii=False, indent=2))
        return 0
    _print_md(text)
    print(f"\n<!-- 已写入 {path} -->")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    session = _session(args)
    day = mark_day_done(session.state, args.day)
    session.save()
    if args.json:
        print(json.dumps({"day": day["day"], "date": day["date"], "done": True,
                          "progress": session.progress_line()}, ensure_ascii=False, indent=2))
        return 0
    print(f"已标记第 {day['day']} 天完成（{day['date']}）")
    print(session.progress_line())
    return 0


def cmd_answer(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    question = session.find_question(args.qid)
    if not question:
        raise SystemExit(f"未知题号: {args.qid}")
    on = date.fromisoformat(args.date) if args.date else today()
    correct = args.result == "correct"
    attempt = add_attempt(
        st, args.qid, correct, confidence=args.confidence, cause=args.cause,
        seconds=args.seconds, note=args.note, on=on,
    )
    levels = update_mastery(st, args.qid, correct, args.confidence, on=on)
    rating = 1 if not correct else (2 if args.confidence <= 1 else 3 if args.confidence == 2 else 4)
    updates = []
    for kp_id in question.get("kpIds") or []:
        try:
            updates.append(review_kp(st, kp_id, rating, on=on))
        except KeyError:
            pass
    sync_reviews(st)
    compute_difficulty(st)
    session.save()
    if args.json:
        print(json.dumps({
            "qid": args.qid, "correct": correct, "attempt": attempt,
            "mistakes": [m for m in st.get("mistakes", []) if m.get("questionId") == args.qid],
            "reviews": updates, "mastery": levels, "progress": session.progress_line(),
        }, ensure_ascii=False, indent=2, default=str))
        return 0
    print(("✅ 答对" if correct else "❌ 答错") + f"：{args.qid}")
    if not correct:
        print(f"错因：{args.cause or '未填'}；明天会进入重测。")
        print("补救建议：概念→重讲+视频；计算→同类专练；审题→题型识别卡；记忆→间隔复习；时间→限时训练。")
    else:
        unresolved = [m for m in st.get("mistakes", []) if m.get("questionId") == args.qid and not m.get("resolved")]
        if not unresolved:
            print("这道题的错题已关闭（连续两次答对）。")
    for update in updates:
        print(f"  {update['kpId']} 下次复习：{update['due']}（稳定性 {update['stability']}）")
    for item in levels:
        print(f"  {item['kpId']} 当前掌握度：{item.get('currentLevel')}（目标 {(st.get('mastery', {}).get(item['kpId']) or {}).get('targetLevel', 'L0')}，正确率 {item.get('accuracy', 0):.2f}）")
    print(session.progress_line())
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    session = _session(args)
    result = review_kp(session.state, args.kp, args.rating)
    compute_difficulty(session.state)
    session.save()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_quiz(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    picked: list[dict[str, Any]] = []
    seen = set()
    for mistake in st.get("mistakes", []):
        if mistake.get("resolved") or str(mistake.get("retestDue") or "9999") > today().isoformat():
            continue
        q = session.find_question(mistake.get("questionId", ""))
        if q and q["id"] not in seen:
            picked.append(q)
            seen.add(q["id"])
    freq = exam_frequency(st)
    attempted = {a.get("questionId") for a in st.get("attempts", []) if a.get("questionId")}
    kp_weight = {kp["id"]: float(kp.get("weight", 1.0)) for kp in st.get("knowledgePoints", [])}
    pool = sorted(
        [q for q in st.get("questions", []) if q["id"] not in seen and q["id"] not in attempted],
        key=lambda q: (
            freq.get(q.get("type", ""), 0),
            max((kp_weight.get(k, 1.0) for k in q.get("kpIds", [])), default=1.0),
            q.get("points", 1),
        ),
        reverse=True,
    )
    for q in pool:
        if len(picked) >= args.n:
            break
        picked.append(q)
    if getattr(args, "diagnostic", False):
        by_type: dict[str, dict[str, Any]] = {}
        for q in st.get("questions", []):
            by_type.setdefault(q.get("type") or "未分组", q)
        picked = list(by_type.values())[:20]
    if args.json:
        print(json.dumps({"questions": [{"id": q["id"], "type": q.get("type"), "stem": q["stem"]} for q in picked]},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"# 今日抽题（{len(picked)} 道；错题优先，其次按常考度）")
    print("")
    for i, q in enumerate(picked, start=1):
        print(f"{i}. `{q['id']}` [{q.get('type', '')}] {q['stem']}")
        print("")
    print("做完用 `coach.py answer --qid ... --result correct|wrong` 记录。")
    return 0


def cmd_keywords(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    chapters = st.get("chapters", [])
    target = None
    if args.chapter:
        target = next((c for c in chapters if c["id"] == args.chapter or args.chapter in c["title"]), None)
    if not target:
        day = session.find_day()
        kp = next((k for k in st.get("knowledgePoints", []) if day and k["id"] in day.get("kpIds", [])), None)
        chapter_id = kp.get("chapter") if kp else (chapters[0]["id"] if chapters else None)
        target = next((c for c in chapters if c["id"] == chapter_id), chapters[0] if chapters else None)
    if not target:
        raise SystemExit("没有章节可分析")
    text = session.chapter_text(target)
    corpus = [session.chapter_text(c) for c in chapters if c["id"] != target["id"]]
    model = []
    for kp in st.get("knowledgePoints", []):
        if kp.get("chapter") == target["id"]:
            model.extend(kp.get("keywords", []))
    items = extract_keywords(text, [target.get("title", "")], model, corpus)
    if args.json:
        print(json.dumps({"chapter": target["id"], "title": target.get("title"), "items": items},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"# {target['id']} {target['title']}")
    print("")
    print(describe(items))
    print("")
    print("来源权重：model 3 / acronym 2.6 / heading 2.5 / corpus 2（跨章 +0.3）")
    return 0


def cmd_bilibili(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    kp = session.find_kp(args.kp)
    if not kp:
        raise SystemExit(f"未知知识点: {args.kp}")
    domain = st.get("domain", "general")
    cookie = load_cookie(args.cookie_file)
    cfg = st.get("settings", {}).get("bilibili", {})
    try:
        client = BiliClient(
            session.cache_dir, cookie=cookie, offline=args.offline,
            rate_seconds=float(cfg.get("rateSeconds", 1.0)),
            insecure=args.insecure, ca_file=args.ca_file, allow_curl=args.allow_curl,
        )
        result = client.recommend(
            kp, domain=domain, course=st.get("course", ""), limit=args.limit,
            threshold=float(cfg.get("threshold", 0.5)),
            whitelist=list(cfg.get("whitelist", [])), refresh=args.refresh,
        )
    except BiliError as exc:
        fallback = search_url(" ".join(kp.get("anchors") or [kp.get("title", "")]))
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc), "searchUrl": fallback}, ensure_ascii=False, indent=2))
        else:
            print(f"⚠️ B 站检索失败：{exc}")
            print(f"降级为搜索链接：{fallback}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if result.get("status") == "ok":
        st["videos"] = [v for v in st.get("videos", []) if v.get("kpId") != args.kp] + result["items"]
        session.save()
        if client.stats.get("insecureTls"):
            print("> ⚠️ 已显式使用 --insecure：不校验证书、且不发送 Cookie；仅用于本机代理环境。")
            print("")
        print(f"## {kp['id']} {kp['title']}")
        print("")
        for row in result["items"]:
            print(f"- [{row['title']}]({row['link']}) · UP {row['author']} · 匹配度 {row['score']:.2f}")
            print(f"  - {row['reason']}")
            print("  - 先做题；仍卡住再看这一段。")
            print("")
    else:
        print(f"未找到高重合视频（阈值 {cfg.get('threshold', 0.5)}）。")
        print(f"只给搜索链接，不编造 BV：{result['searchUrl']}")
        if result.get("errors"):
            print("检索错误：")
            for error in result["errors"]:
                print("  - " + error)
    return 0


def cmd_calc(args: argparse.Namespace) -> int:
    if args.spec:
        spec = json.loads(args.spec)
    else:
        spec = {"kind": args.kind}
        if args.kind == "twos":
            spec.update({"value": args.value, "bits": args.bits})
        elif args.kind == "decode":
            spec.update({"bits": args.bits, "signed": not args.unsigned})
        elif args.kind == "ieee754":
            spec.update({"value": args.value, "bits": args.ieee_bits})
        elif args.kind == "ieee754_decode":
            spec.update({"hex": args.hex, "bits": args.ieee_bits})
        elif args.kind == "flags":
            spec.update({"op": args.op, "a": args.a, "b": args.b, "bits": args.bits})
        elif args.kind == "modrm":
            spec.update({"mod": args.mod, "reg": args.reg, "rm": args.rm})
        elif args.kind == "choice":
            spec.update({"answer": args.answer})
        elif args.kind == "exact":
            spec.update({"text": args.text})
        elif args.kind == "numeric":
            spec.update({"value": args.value, "tolerance": args.tolerance})
        else:
            raise SystemExit("--kind 只支持 twos/decode/ieee754/ieee754_decode/flags/modrm/choice/exact/numeric/matrix/determinant，或直接用 --spec")
    print(json.dumps(compute(spec), ensure_ascii=False, indent=2))
    return 0


def cmd_domains(args: argparse.Namespace) -> int:
    from .subjects import num, profiles
    data = []
    for key, info in profiles().items():
        ratio = info.get("phaseRatio", {})
        data.append({
            "subject": key, "label": info.get("label", key),
            "types": len(info.get("questionTypes", [])),
            "phaseRatio": {k: num(ratio.get(k)) for k in ("build", "reinforce", "sprint")},
        })
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print("| 科目画像 | 名称 | 题型数 | 阶段比例（构建/强化/冲刺） |")
    print("|---|---|---:|---|")
    for key, info in profiles().items():
        ratio = info.get("phaseRatio", {})
        print(f"| {key} | {info.get('label', key)} | {len(info.get('questionTypes', []))} | "
              f"{num(ratio.get('build')):.2f}/{num(ratio.get('reinforce')):.2f}/{num(ratio.get('sprint')):.2f} |")
    return 0


def cmd_fill(args: argparse.Namespace) -> int:
    session = _session(args)
    if getattr(args, "tasks", False) and args.apply:
        print("--tasks 只生成清单；--apply 用于回填，二者不要同时使用")
        return 2
    if args.apply:
        path = Path(args.apply)
        if not path.exists():
            print(f"回填文件不存在：{path}")
            return 3
        payload = json.loads(read_text(path))
        result = apply_fill(session, payload)
        report = audit(session)
        session.state.setdefault("build", {})["auditOk"] = report["ok"]
        session.save()
        out = Path(session.state.get("build", {}).get("out") or (session.workspace / "output"))
        write_text(out / "质检报告.md", format_audit(report))
        result["audit"] = report
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"✅ 已回填 {len(result['applied'])} 处；剩余 {result['remaining']} 处待填")
            for path in result["paths"]:
                print(f"  {path}")
            print(format_audit(report))
        return 0 if report["ok"] else 1
    tasks = collect_fill_tasks(session)
    base = Path(session.state.get("build", {}).get("out") or (session.workspace / "output"))
    out = Path(args.out) if args.out else base / "_build" / "fill_tasks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, {"tasks": tasks})
    if args.json:
        print(json.dumps({"tasks": tasks, "file": str(out)}, ensure_ascii=False, indent=2))
    else:
        print(f"待填 {len(tasks)} 处；清单：{out}")
        for task in tasks:
            print(f"  - {task['id']}：{task['instruction']}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    missing_fields = []
    if args.target is None:
        missing_fields.append("--target（目标分）")
    if args.days is None:
        missing_fields.append("--days（复习天数 N）")
    if missing_fields:
        if args.json:
            print(json.dumps({"needsInput": ["target", "days"], "missing": missing_fields}, ensure_ascii=False, indent=2))
        else:
            print("需要先询问用户以下字段，不能自行填值：")
            for item in missing_fields:
                print("  - " + item)
        return 2
    materials = [Path(p) for p in (args.materials or [])]
    past = [Path(p) for p in (args.past_papers or [])]
    all_paths = materials + past
    missing = [str(p) for p in all_paths if not p.exists()]
    if missing:
        print("资料路径不存在：" + ", ".join(missing))
        return 2
    formats = [x.strip().lower() for x in (args.format or "md,docx").split(",") if x.strip()]
    default_daily = args.daily_minutes is None
    if default_daily:
        args.daily_minutes = 120
        if not args.json:
            print("每日分钟：120（用户未提供，使用默认值；可在下次用 --daily-minutes 修改）")
    if not args.exam_date and not args.json:
        print(f"考试日期：未提供，按今天 + {args.days} 天推算")
    try:
        result = build_run(
            Path(args.workspace), args.course, materials, past,
            target=int(args.target), days=int(args.days), daily_minutes=args.daily_minutes,
            subject=args.subject or args.domain, out=Path(args.out) if args.out else None,
            formats=formats, exam_date=date.fromisoformat(args.exam_date) if args.exam_date else None,
            force=args.force, refresh_materials=args.refresh_materials,
        )
    except BuildDependencyError as exc:
        if args.json:
            print(json.dumps({"error": "missing_dependency", "message": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"缺少依赖：{exc}")
        return 3
    except BuildStateError as exc:
        if args.json:
            print(json.dumps({"error": "state_exists", "message": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"构建拒绝：{exc}")
        return 3
    except BuildError as exc:
        if args.json:
            print(json.dumps({"error": "build_failed", "message": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"构建失败：{exc}")
        return 2
    if args.json:
        print(json.dumps({
            "ok": result["report"]["ok"],
            "output": str(result["output"]),
            "files": [{"path": str(p), "size": p.stat().st_size} for p in result["paths"]],
            "subject": result["state"].get("subject"),
            "target": args.target, "days": args.days,
            "defaultsUsed": {"dailyMinutes": 120} if default_daily else {},
            "quantification": result["quantification"],
            "audit": result["report"],
            "fillTasks": result["state"].get("build", {}).get("fillTasks", 0),
        }, ensure_ascii=False, indent=2, default=str))
        return 0 if result["report"]["ok"] else 1
    print(f"✅ 五册已生成：{result['output']}")
    print(f"科目：{result['state'].get('subject')} · 目标：{args.target} · 天数：{args.days}")
    print(f"可达预期分：{result['quantification'].get('reachableScore')} / 需要 {result['quantification'].get('requiredScore')}")
    if result["state"].get("build", {}).get("fillTasks"):
        print(f"待模型补内容：{result['state']['build']['fillTasks']} 处；运行 coach.py fill 生成清单，回填后再 audit。")
    print("")
    print("| 文件 | 大小 |")
    print("|---|---:|")
    for path in result["paths"]:
        print(f"| {path.name} | {path.stat().st_size} 字节 |")
    print("")
    print(format_audit(result["report"]))
    return 0 if result["report"]["ok"] else 1


def cmd_types(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    freq = exam_frequency(st)
    counts: dict[str, int] = {}
    papers: dict[str, set[str]] = {}
    days: dict[str, set[int]] = {}
    for q in st.get("questions", []):
        tid = q.get("type")
        if not tid:
            continue
        counts[tid] = counts.get(tid, 0) + 1
        if q.get("paperId"):
            papers.setdefault(tid, set()).add(q["paperId"])
    for day in st.get("schedule", {}).get("days", []):
        for slot in day.get("slots", []):
            if slot.get("type"):
                days.setdefault(slot["type"], set()).add(day["day"])
    rows = [
        {"id": t["id"], "name": t["name"], "count": counts.get(t["id"], 0),
         "papers": len(papers.get(t["id"], set())), "F": freq.get(t["id"], 0),
         "days": len(days.get(t["id"], set()))}
        for t in st.get("questionTypes", [])
    ]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print("| 题型 | 名称 | 题量 | 覆盖试卷 | 常考度 F | 排期天数 |")
    print("|---|---|---:|---:|---:|---:|")
    for t in st.get("questionTypes", []):
        tid = t["id"]
        print(f"| {tid} | {t['name']} | {counts.get(tid, 0)} | {len(papers.get(tid, set()))} | "
              f"{freq.get(tid, 0):.3f} | {len(days.get(tid, set()))} |")
    return 0


def cmd_set_check(args: argparse.Namespace) -> int:
    session = _session(args)
    q = session.find_question(args.qid)
    if not q:
        raise SystemExit(f"未知题号: {args.qid}")
    try:
        spec = json.loads(args.check)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--check 不是合法 JSON：{exc}")
    if not isinstance(spec, dict) or not spec.get("kind"):
        raise SystemExit("--check 必须是带 kind 的 JSON 对象")
    try:
        compute(spec)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"check 规则无法执行：{exc}")
    q["check"] = spec
    q["recomputed"] = None
    q["conflict"] = ""
    q["resolution"] = None
    session.save()
    if args.json:
        print(json.dumps({"qid": q["id"], "check": q["check"]}, ensure_ascii=False, indent=2))
        return 0
    print(f"已为 {q['id']} 绑定校验规则：{q['check']}")
    return 0


def cmd_recompute(args: argparse.Namespace) -> int:
    session = _session(args)
    q = session.find_question(args.qid)
    if not q:
        raise SystemExit(f"未知题号: {args.qid}")
    spec = q.get("check")
    if not spec:
        print(f"{q['id']} 没有登记 check 规则；请在题库里补 check，或运行 `coach.py calc` 手工验算。")
        return 2
    recomputed = compute(spec)
    q["recomputed"] = recomputed
    if not q.get("officialAnswer"):
        q["resolution"] = "recomputed"
        q["conflict"] = ""
        print(f"{q['id']} 没有官方答案；已记录重算结果，解析里标为“脚本重算”。")
    else:
        verdict = compare(q["officialAnswer"], recomputed)
        if verdict == "same":
            q["resolution"] = "same"
            q["conflict"] = ""
            print(f"{q['id']} 官方答案与重算一致。")
        else:
            q["resolution"] = "pending"
            q["conflict"] = f"官方答案={q['officialAnswer']}；脚本重算={recomputed}；需确认 check 规格是否正确"
            print(f"⚠️ {q['id']} 官方答案与重算不一致；已标为待确认。")
            print("   先核对 check 规格是否忠实转写了题干，再运行：")
            print(f"   coach.py resolve-conflict --qid {q['id']} --use official|recomputed --note '核对说明'")
    session.save()
    if args.json:
        print(json.dumps({"qid": q["id"], "recomputed": recomputed, "resolution": q.get("resolution"),
                          "conflict": q.get("conflict", "")}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(recomputed, ensure_ascii=False, indent=2))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    session = _session(args)
    q = session.find_question(args.qid)
    if not q:
        raise SystemExit(f"未知题号: {args.qid}")
    if not q.get("conflict"):
        raise SystemExit(f"{q['id']} 没有待处理的冲突")
    q["resolution"] = args.use
    q["resolutionNote"] = args.note or ""
    q["resolvedAt"] = today().isoformat()
    q["finalAnswer"] = q.get("officialAnswer") if args.use == "official" else primary_value(q.get("recomputed"))
    session.save()
    if args.json:
        print(json.dumps({"qid": q["id"], "use": args.use, "finalAnswer": q.get("finalAnswer"),
                          "note": q.get("resolutionNote", "")}, ensure_ascii=False, indent=2))
        return 0
    print(f"已处理 {q['id']}：以 {args.use} 为准；{q.get('resolutionNote', '')}")
    return 0


def cmd_weights(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    rows = [
        {"id": kp["id"], "title": kp["title"], "weight": kp.get("weight", 1.0),
         "D": kp.get("D", 0), "syllabusLevel": kp.get("syllabusLevel", 0),
         "emphasis": kp.get("emphasis", False), "reason": kp.get("weightReason", "")}
        for kp in sorted(st.get("knowledgePoints", []), key=lambda k: float(k.get("weight") or 1.0), reverse=True)
    ]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print("| 知识点 | 权重 W | D | 考纲等级 | 重点 | 依据 |")
    print("|---|---:|---:|---:|---|---|")
    for kp in sorted(st.get("knowledgePoints", []), key=lambda k: float(k.get("weight") or 1.0), reverse=True):
        print(f"| {kp['id']} {kp['title']} | {float(kp.get('weight') or 1.0):.2f} | "
              f"{float(kp.get('D', 0)):.2f} | {float(kp.get('syllabusLevel') or 0):.2f} | "
              f"{'是' if kp.get('emphasis') else '否'} | {kp.get('weightReason', '')} |")
    return 0


def cmd_reclassify(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    needle = args.file.replace("\\", "/").lower()
    material = next((m for m in st.get("materials", [])
                     if needle in str(m.get("rel", "")).lower() or needle in str(m.get("path", "")).lower()), None)
    if not material:
        raise SystemExit(f"未找到材料: {args.file}")
    if args.as_category not in MATERIAL_LABELS:
        raise SystemExit("未知分类；可选：" + ", ".join(MATERIAL_LABELS))
    material["category"] = args.as_category
    material["categoryLabel"] = MATERIAL_LABELS[args.as_category]
    material["categoryEvidence"] = "用户手动改判"
    session.save()
    if args.json:
        print(json.dumps({"file": material["rel"], "category": material["category"]}, ensure_ascii=False, indent=2))
        return 0
    print(f"已把 {material['rel']} 改为 {MATERIAL_LABELS[args.as_category]}。")
    print("章节与题库不会自动重算；确认后重新运行 init（或编辑 state 后）再 plan。")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    session = _session(args)
    report = audit(session, check_citations=getattr(args, "citations", False),
                   citation_sample=getattr(args, "citation_sample", 20))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_audit(report))
    return 0 if report["ok"] else 1


def cmd_export(args: argparse.Namespace) -> int:
    session = _session(args)
    formats = [x.strip() for x in args.format.split(",") if x.strip()]
    written = export_all(session, formats)
    if args.json:
        print(json.dumps({"formats": formats, "files": [str(p) for p in written]}, ensure_ascii=False, indent=2))
        return 0
    for path in written:
        print(path)
    return 0


def cmd_figure(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"文件不存在：{path}")
        return 2
    page = max(1, int(args.page))
    out = Path(args.out) if args.out else path.with_name(f"{path.stem}-p{page}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pypdfium2 as pdfium  # type: ignore

        pdf = pdfium.PdfDocument(str(path))
        if page > len(pdf):
            print(f"页码超出范围：{page} > {len(pdf)}")
            return 2
        bitmap = pdf[page - 1].render(scale=float(args.scale))
        bitmap.to_pil().save(out)
    except ImportError:
        try:
            import fitz  # type: ignore

            pdf = fitz.open(str(path))
            if page > len(pdf):
                print(f"页码超出范围：{page} > {len(pdf)}")
                return 2
            pix = pdf[page - 1].get_pixmap(matrix=fitz.Matrix(float(args.scale), float(args.scale)))
            pix.save(str(out))
        except ImportError:
            print("需要 pypdfium2 或 PyMuPDF 才能渲染 PDF 页面；请安装 requirements-optional.txt")
            return 2
    if args.json:
        print(json.dumps({"file": str(path), "page": page, "out": str(out)}, ensure_ascii=False, indent=2))
    else:
        print(out)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    session = load_session(Path(args.workspace))
    checks = []
    checks.append(("Python", sys.version.split()[0], True))
    for module, label in (("pypdf", "PDF 文本层"), ("fitz", "PDF 兜底"), ("docx", "DOCX"), ("pptx", "PPTX")):
        checks.append((label, "可用" if importlib.util.find_spec(module) else "未安装（会标记待转换）", importlib.util.find_spec(module) is not None))
    cookie = load_cookie(args.cookie_file)
    checks.append(("B 站 Cookie", json.dumps(cookie_status(cookie), ensure_ascii=False), True))
    if args.json:
        print(json.dumps({"checks": [{"name": n, "value": v, "ok": ok} for n, v, ok in checks],
                          "workspace": str(session.workspace), "exists": session.exists()},
                         ensure_ascii=False, indent=2))
        return 0
    print("# 环境检查")
    print("")
    for name, value, ok in checks:
        print(f"- {'✅' if ok else '⚠️'} {name}: {value}")
    if session.exists():
        st = session.state
        print("")
        print(f"- 工作区: {session.workspace}")
        print(f"- 课程: {st['course']} · 考试: {st['examDate']} · 天数: {len(st.get('schedule', {}).get('days', []))}")
        print(f"- 材料: {len(st.get('materials', []))} · 章节: {len(st.get('chapters', []))} · 题目: {len(st.get('questions', []))}")
    else:
        print("")
        print(f"- 工作区尚未初始化: {session.workspace}")
    print("")
    print("提示：Cookie 只从 BILIBILI_COOKIE 或 --cookie-file 读取，不会写入状态文件。")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    if args.exam_date:
        st["examDate"] = args.exam_date
    if args.daily_minutes:
        st["dailyMinutes"] = args.daily_minutes
    if args.target:
        st["targetScore"] = args.target
    if args.density:
        st["density"] = args.density
        st.setdefault("settings", {})["density"] = args.density
    if args.days:
        st["days"] = int(args.days)
        st["examDate"] = (today() + timedelta(days=int(args.days))).isoformat()
    elif args.exam_date:
        st["days"] = max(1, (date.fromisoformat(args.exam_date) - today()).days)
        st["examDate"] = args.exam_date
    if args.target or args.days or args.exam_date:
        quantify(st, target=st.get("targetScore", 80), days=st.get("days"), daily_minutes=st.get("dailyMinutes"))
    if args.rebuild or args.exam_date or args.days or args.target:
        build_schedule(st, days=int(args.days) if args.days else None)
        sync_reviews(st)
        schedule_workload(st)
    session.save()
    if args.json:
        print(json.dumps({"course": st["course"], "days": st.get("days"), "target": st.get("targetScore"),
                          "summary": plan_summary(st), "progress": session.progress_line()}, ensure_ascii=False, indent=2))
        return 0
    print(session.progress_line())
    print(plan_summary(st))
    return 0


def cmd_add_question(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    if any(q["id"] == args.id for q in st.get("questions", [])):
        raise SystemExit(f"题号已存在: {args.id}")
    source = getattr(args, "source", "manual")
    q = {
        "id": args.id,
        "paperId": args.paper or ("MODEL" if source == "model" else "MANUAL"),
        "number": len(st.get("questions", [])) + 1,
        "stem": args.stem,
        "section": "模型生成" if source == "model" else "",
        "type": args.type,
        "kind": args.kind,
        "points": args.points,
        "steps": getattr(args, "steps", 0) or 0,
        "page": None,
        "sourceFile": "model" if source == "model" else "manual",
        "officialAnswer": args.answer or "",
        "check": json.loads(args.check) if args.check else None,
        "kpIds": args.kp or [],
        "modelGenerated": source == "model",
        "source": source,
    }
    if getattr(args, "slot", ""):
        q["slotId"] = args.slot
    if q["officialAnswer"]:
        q["answerSource"] = "model" if source == "model" else "manual"
    if getattr(args, "solution", ""):
        q["solution"] = args.solution
        q["solutionSource"] = "model" if source == "model" else "manual"
    if getattr(args, "rubric", ""):
        _rubric = normalize_rubric(args.rubric)
        if _rubric:
            q["rubric"] = _rubric
            q["rubricSource"] = "model" if source == "model" else "manual"
    st.setdefault("questions", []).append(q)
    compute_difficulty(st)
    session.save()
    output_exists = Path(st.get("build", {}).get("out") or (session.workspace / "output")).exists()
    if output_exists:
        result = _write_outputs(session)
        if args.json:
            print(json.dumps({"question": q, **result}, ensure_ascii=False, indent=2, default=str))
            return 0
        print(f"已加入 {q['id']}（{source}），并重渲染五册")
        if result["audit"]["problems"]:
            print(f"⚠️ 质检仍有 {len(result['audit']['problems'])} 项问题；运行 coach.py audit 查看")
    elif args.json:
        print(json.dumps(q, ensure_ascii=False, indent=2))
        return 0
    else:
        print(f"已加入 {q['id']}（{source}）；五册尚未生成，运行 coach.py build 或 coach.py sync")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    session = _session(args)
    result = _write_outputs(session)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        for path in result["paths"]:
            print(path)
        print(format_audit(result["audit"]))
    return 0 if result["audit"]["ok"] else 1


def cmd_sources(args: argparse.Namespace) -> int:
    session = _session(args)
    rows = [{"id": kp["id"], "title": kp["title"], "source": source_label(kp)}
            for kp in session.state.get("knowledgePoints", [])]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        print(f"{row['id']}\t{row['title']}\t{row['source']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coach.py", description="review-sprint: 单科目考前冲刺教练")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE, help="工作区目录（默认 .review-sprint）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="导入资料并建立工作区")
    p.add_argument("--course", required=True)
    p.add_argument("--exam-date", help="YYYY-MM-DD（可选；与 --days 二选一）")
    p.add_argument("--days", type=int, help="预计复习天数 N")
    p.add_argument("--materials", nargs="+", required=True, help="资料文件或目录，可多个")
    p.add_argument("--past-papers", nargs="*", default=[], help="往年题/答案文件或目录（可选）")
    p.add_argument("--daily-minutes", type=int, default=None)
    p.add_argument("--target", type=int, default=90)
    p.add_argument("--lang", default="zh")
    p.add_argument("--density", choices=["concise", "standard", "detailed"], default="standard")
    p.add_argument("--subject", help="科目画像，如 math / law / politics / cs_systems")
    p.add_argument("--domain", help="--subject 的旧别名")
    p.add_argument("--force", action="store_true")
    p.add_argument("--refresh-materials", action="store_true", help="重新解析材料并保留作答/错题/掌握度")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="显示进度行和到期复习")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("next", help="只给一个下一步动作和理由")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("catch-up", help="检查落后的复习日并给出补课入口")
    p.set_defaults(func=cmd_catchup)

    p = sub.add_parser("report", help="按错因聚合最近 N 天作答")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("sync", help="重排、重渲染五册并刷新质检（不重新解析材料）")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("fill", help="生成五册待填清单，或把模型回填写回 state 并重渲染")
    p.add_argument("--tasks", action="store_true", help="生成待填/待生成清单（默认行为；保留显式参数）")
    p.add_argument("--apply", help="回填 JSON 文件；结构 {\"tasks\":{\"main:K1\":\"...\"}}")
    p.add_argument("--out", help="待填清单输出路径")
    p.set_defaults(func=cmd_fill)

    p = sub.add_parser("build", help="一条命令：解析 → 识别科目 → 量化 → 排期 → 五册 + 质检")
    p.add_argument("--course", required=True)
    p.add_argument("--materials", nargs="+", required=True)
    p.add_argument("--past-papers", nargs="*", default=[])
    p.add_argument("--target", type=int, help="目标分 0–100（必填）")
    p.add_argument("--days", type=int, help="复习天数 N（必填）")
    p.add_argument("--daily-minutes", type=int, default=None)
    p.add_argument("--subject")
    p.add_argument("--domain", help="--subject 的旧别名")
    p.add_argument("--exam-date")
    p.add_argument("--out")
    p.add_argument("--format", default="md,docx")
    p.add_argument("--force", action="store_true")
    p.add_argument("--refresh-materials", action="store_true", help="保留历史记录，只重新解析材料并重排")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("plan", help="生成/重建排期")
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("today", help="生成当天学习包")
    p.add_argument("--day", type=int)
    p.add_argument("--density", choices=["concise", "standard", "detailed"])
    p.add_argument("--force", action="store_true", help="覆盖已存在的 daily 文件")
    p.set_defaults(func=cmd_today)

    p = sub.add_parser("done", help="把某天标记为完成")
    p.add_argument("--day", type=int, required=True)
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("answer", help="记录一道题的作答")
    p.add_argument("--qid", required=True)
    p.add_argument("--result", choices=["correct", "wrong"], required=True)
    p.add_argument("--confidence", type=int, choices=[0, 1, 2, 3], default=2)
    p.add_argument("--cause", choices=["concept", "calc", "reading", "memory", "time", "unknown"], default="unknown")
    p.add_argument("--seconds", type=int, default=0)
    p.add_argument("--date", help="补录日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_answer)

    p = sub.add_parser("review", help="记录一次知识点复习（FSRS）")
    p.add_argument("--kp", required=True)
    p.add_argument("--rating", type=int, choices=[1, 2, 3, 4], required=True)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("quiz", help="按错题/常考度抽题；--diagnostic 覆盖各题型")
    p.add_argument("--n", type=int, default=7)
    p.add_argument("--diagnostic", action="store_true", help="诊断卷：每种题型抽 1 道，最多 20 道")
    p.set_defaults(func=cmd_quiz)

    p = sub.add_parser("keywords", help="查看四源关键词融合结果")
    p.add_argument("--chapter")
    p.set_defaults(func=cmd_keywords)

    p = sub.add_parser("bilibili", help="检索并评分 B 站视频")
    p.add_argument("--kp", required=True)
    p.add_argument("--limit", type=int, default=2)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--cookie-file")
    p.add_argument("--ca-file", help="指定代理/企业根证书")
    p.add_argument("--insecure", action="store_true", help="显式关闭证书校验；该模式不发送 Cookie")
    p.add_argument("--allow-curl", action="store_true", help="403/412 时允许用系统 curl 重试（可能触发风控）")
    p.set_defaults(func=cmd_bilibili)

    p = sub.add_parser("calc", help="确定性重算")
    p.add_argument("--kind", choices=["twos", "decode", "ieee754", "ieee754_decode", "flags", "modrm", "choice", "exact", "numeric", "matrix", "determinant"])
    p.add_argument("--spec", help="JSON 规格，优先于 --kind")
    p.add_argument("--value", type=float)
    p.add_argument("--bits", default="8")
    p.add_argument("--ieee-bits", type=int, choices=[32, 64], default=32)
    p.add_argument("--hex", default="0")
    p.add_argument("--unsigned", action="store_true")
    p.add_argument("--op", choices=["add", "sub"], default="add")
    p.add_argument("--a", type=int, default=0)
    p.add_argument("--b", type=int, default=0)
    p.add_argument("--mod", type=int, default=0)
    p.add_argument("--reg", type=int, default=0)
    p.add_argument("--rm", type=int, default=0)
    p.add_argument("--answer", default="")
    p.add_argument("--text", default="")
    p.add_argument("--tolerance", type=float, default=0.0)
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("recompute", help="按题库 check 规则重算并比对官方答案")
    p.add_argument("--qid", required=True)
    p.set_defaults(func=cmd_recompute)

    p = sub.add_parser("resolve-conflict", help="确认官方答案与重算冲突以哪边为准")
    p.add_argument("--qid", required=True)
    p.add_argument("--use", choices=["official", "recomputed"], required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("weights", help="查看知识点权重、考纲/重点证据与 D")
    p.set_defaults(func=cmd_weights)

    p = sub.add_parser("reclassify", help="手动改材料分类（不自动重算章节）")
    p.add_argument("--file", required=True)
    p.add_argument("--as-category", required=True, choices=list(MATERIAL_LABELS))
    p.set_defaults(func=cmd_reclassify)

    p = sub.add_parser("types", help="查看题型矩阵与常考度")
    p.set_defaults(func=cmd_types)

    p = sub.add_parser("domains", help="列出内置科目画像与题型数")
    p.set_defaults(func=cmd_domains)
    p = sub.add_parser("subjects", help="domains 的别名")
    p.set_defaults(func=cmd_domains)

    p = sub.add_parser("set-check", help="为题目绑定确定性校验规则")
    p.add_argument("--qid", required=True)
    p.add_argument("--check", required=True, help="JSON，例如 {\"kind\":\"twos\",\"value\":-5,\"bits\":8}")
    p.set_defaults(func=cmd_set_check)

    p = sub.add_parser("audit", help="运行质检门禁")
    p.add_argument("--citations", action="store_true", help="抽样回查五册中的原文引用（目标命中率 ≥90%%）")
    p.add_argument("--citation-sample", type=int, default=20, help="引用抽样条数，默认 20")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("export", help="导出排期/速记表/日历/Anki")
    p.add_argument("--format", default="md,ics,anki")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("figure", help="把 PDF 的某一页渲染为 PNG（公式/图片进册）")
    p.add_argument("--file", required=True, help="PDF 路径")
    p.add_argument("--page", type=int, required=True, help="页码，从 1 开始")
    p.add_argument("--out", help="输出 PNG 路径")
    p.add_argument("--scale", type=float, default=2.0, help="渲染倍率，默认 2.0")
    p.set_defaults(func=cmd_figure)

    p = sub.add_parser("doctor", help="检查环境与依赖")
    p.add_argument("--cookie-file")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("set", help="改考试日期/天数/预算/目标/密度")
    p.add_argument("--exam-date")
    p.add_argument("--days", type=int, help="复习天数 N")
    p.add_argument("--daily-minutes", type=int)
    p.add_argument("--target", type=int)
    p.add_argument("--density", choices=["concise", "standard", "detailed"])
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("add-question", help="向题库加入一道题；模型题自动标来源并重渲染五册")
    p.add_argument("--id", required=True)
    p.add_argument("--paper")
    p.add_argument("--type", required=True)
    p.add_argument("--kind", choices=["basic", "past", "advanced"], default="basic")
    p.add_argument("--stem", required=True)
    p.add_argument("--answer")
    p.add_argument("--solution", help="解析/步骤；模型生成时写 solutionSource=model")
    p.add_argument("--rubric", help="JSON 评分点列表 [{\"point\":\"...\",\"score\":1}]")
    p.add_argument("--steps", type=int, default=0, help="解析步骤数（用于质检提示）")
    p.add_argument("--source", choices=["manual", "model"], default="manual")
    p.add_argument("--slot", help="直接绑定题位号，如 D01-S02")
    p.add_argument("--check", help="JSON 校验规格")
    p.add_argument("--kp", nargs="*", default=[])
    p.add_argument("--points", type=float, default=5)
    p.set_defaults(func=cmd_add_question)

    p = sub.add_parser("sources", help="列出知识点与来源标签")
    p.set_defaults(func=cmd_sources)

    # allow --workspace / --json after the subcommand as well as before it
    for child in sub.choices.values():
        child.add_argument("--workspace", default=argparse.SUPPRESS)
        if "--json" not in child._option_string_actions:
            child.add_argument("--json", action="store_true", help="输出机器可读 JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except BiliError as exc:
        print(f"B 站错误：{exc}", file=sys.stderr)
        return 2
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
