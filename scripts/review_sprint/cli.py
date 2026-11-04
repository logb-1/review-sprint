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
from .answer_check import compare, compute
from .audit import audit, format_audit
from .bilibili import BiliClient, BiliError, cookie_status, load_cookie, search_url
from .export import export_all
from .ingest import MATERIAL_LABELS, setup
from .keywords import describe, extract_keywords
from .render import daily_markdown, plan_markdown, source_label, write_daily
from .schedule import (
    build_schedule, compute_difficulty, due_reviews, exam_frequency, plan_summary,
    review_kp, top_difficult, validate_schedule,
)
from .state import Session, add_attempt, load_session
from .util import human_minutes, read_json, write_json

DEFAULT_WORKSPACE = ".review-sprint"


def _session(args: argparse.Namespace) -> Session:
    session = load_session(Path(args.workspace))
    if not session.exists():
        raise SystemExit(f"未找到 {session.state_path}。先运行: coach.py init --course 课程名 --exam-date YYYY-MM-DD --materials 资料目录")
    return session


def _print_md(text: str) -> None:
    print(text)


def cmd_init(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    if (workspace / "study_state.json").exists() and not args.force:
        raise SystemExit(f"{workspace} 已有 study_state.json；加 --force 覆盖，或换 --workspace")
    materials = [Path(p) for p in args.materials]
    missing = [str(p) for p in materials if not p.exists()]
    if missing:
        raise SystemExit("资料路径不存在: " + ", ".join(missing))
    state = setup(
        workspace, args.course, date.fromisoformat(args.exam_date), materials,
        daily_minutes=args.daily_minutes, target_score=args.target,
        language=args.lang, density=args.density,
    )
    print(f"✅ 已建立工作区：{workspace.resolve()}")
    print(f"课程：{state['course']} · 考试：{state['examDate']} · 领域：{state['domain']}")
    print(f"材料：{len(state['materials'])} 个（可用 {sum(1 for m in state['materials'] if m['status'] == 'ok')}）")
    print(f"章节：{len(state['chapters'])} · 知识点：{len(state['knowledgePoints'])} · 试卷：{len(state['papers'])} · 题目：{len(state['questions'])}")
    print(plan_summary(state))
    problems = validate_schedule(state)
    if problems:
        print("⚠️ 排期警告：")
        for item in problems:
            print("  - " + item)
    print("\n下一步：")
    print(f"  python scripts/coach.py plan --workspace {workspace}")
    print(f"  python scripts/coach.py today --workspace {workspace}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    due = due_reviews(st)
    print(session.progress_line())
    print(f"课程：{st['course']} · 考试：{st['examDate']} · 目标：{st.get('targetScore', 90)}")
    print(plan_summary(st))
    print(f"到期复习：{len(due)} 项；错题：{len(st.get('mistakes', []))} 条；视频：{len(st.get('videos', []))} 条")
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
        session.save()
    text = plan_markdown(session.state)
    path = session.exports_dir / "排期.md"
    path.write_text(text, encoding="utf-8")
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
    text = daily_markdown(session, day, args.density)
    path = session.daily_dir / f"D{day['day']:02d}-{day['date']}.md"
    path.write_text(text, encoding="utf-8")
    _print_md(text)
    print(f"\n<!-- 已写入 {path} -->")
    return 0


def cmd_answer(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    question = session.find_question(args.qid)
    if not question:
        raise SystemExit(f"未知题号: {args.qid}")
    correct = args.result == "correct"
    attempt = add_attempt(
        st, args.qid, correct, confidence=args.confidence, cause=args.cause,
        seconds=args.seconds, note=args.note,
    )
    if not correct:
        for mistake in st.get("mistakes", []):
            if mistake.get("questionId") == args.qid:
                mistake["retestDue"] = (date.today() + timedelta(days=1)).isoformat()
                break
    rating = 1 if not correct else (2 if args.confidence <= 1 else 3 if args.confidence == 2 else 4)
    updates = []
    for kp_id in question.get("kpIds") or []:
        try:
            updates.append(review_kp(st, kp_id, rating))
        except KeyError:
            pass
    compute_difficulty(st)
    session.save()
    print(("✅ 答对" if correct else "❌ 答错") + f"：{args.qid}")
    if not correct:
        print(f"错因：{args.cause or '未填'}；明天会进入重测。")
        print("补救建议：概念→重讲+视频；计算→同类专练；审题→题型识别卡；记忆→间隔复习；时间→限时训练。")
    for update in updates:
        print(f"  {update['kpId']} 下次复习：{update['due']}（稳定性 {update['stability']}）")
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
        if mistake.get("resolved") or str(mistake.get("retestDue") or "9999") > date.today().isoformat():
            continue
        q = session.find_question(mistake.get("questionId", ""))
        if q and q["id"] not in seen:
            picked.append(q)
            seen.add(q["id"])
    freq = exam_frequency(st)
    pool = sorted(
        [q for q in st.get("questions", []) if q["id"] not in seen],
        key=lambda q: (freq.get(q.get("type", ""), 0), q.get("points", 1)),
        reverse=True,
    )
    for q in pool:
        if len(picked) >= args.n:
            break
        picked.append(q)
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
    client = BiliClient(
        session.cache_dir, cookie=cookie, offline=args.offline,
        rate_seconds=float(cfg.get("rateSeconds", 1.0)),
    )
    try:
        result = client.recommend(
            kp, domain=domain, course=st.get("course", ""), limit=args.limit,
            threshold=float(cfg.get("threshold", 0.5)),
            whitelist=list(cfg.get("whitelist", [])), refresh=args.refresh,
        )
    except BiliError as exc:
        print(f"⚠️ B 站检索失败：{exc}")
        print(f"降级为搜索链接：{search_url(' '.join(kp.get('anchors') or [kp.get('title', '')]))}")
        return 2
    if result.get("status") == "ok":
        st["videos"] = [v for v in st.get("videos", []) if v.get("kpId") != args.kp] + result["items"]
        session.save()
        if client.stats.get("insecureTls"):
            print("> ⚠️ 本机证书链无法验证（常见于代理/抓包环境），已对本技能只读请求临时关闭校验。")
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
        else:
            raise SystemExit("--kind 只支持 twos/decode/ieee754/ieee754_decode/flags/modrm，或直接用 --spec")
    print(json.dumps(compute(spec), ensure_ascii=False, indent=2))
    return 0


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
    q["check"] = json.loads(args.check)
    session.save()
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
    if q.get("officialAnswer") is not None:
        verdict = compare(q["officialAnswer"], recomputed)
        if verdict == "different":
            q["conflict"] = f"官方答案={q['officialAnswer']}；脚本重算={recomputed}；以重算为准，解析中已说明"
        else:
            q["conflict"] = ""
    session.save()
    print(json.dumps(recomputed, ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    session = _session(args)
    report = audit(session)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_audit(report))
    return 0 if report["ok"] else 1


def cmd_export(args: argparse.Namespace) -> int:
    session = _session(args)
    formats = [x.strip() for x in args.format.split(",") if x.strip()]
    written = export_all(session, formats)
    for path in written:
        print(path)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    session = load_session(Path(args.workspace))
    checks = []
    checks.append(("Python", sys.version.split()[0], True))
    for module, label in (("pypdf", "PDF 文本层"), ("fitz", "PDF 兜底"), ("docx", "DOCX"), ("pptx", "PPTX")):
        checks.append((label, "可用" if importlib.util.find_spec(module) else "未安装（会标记待转换）", importlib.util.find_spec(module) is not None))
    cookie = load_cookie(args.cookie_file)
    checks.append(("B 站 Cookie", json.dumps(cookie_status(cookie), ensure_ascii=False), True))
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
    if args.rebuild or args.exam_date:
        build_schedule(st)
    session.save()
    print(session.progress_line())
    print(plan_summary(st))
    return 0


def cmd_add_question(args: argparse.Namespace) -> int:
    session = _session(args)
    st = session.state
    if any(q["id"] == args.id for q in st.get("questions", [])):
        raise SystemExit(f"题号已存在: {args.id}")
    q = {
        "id": args.id,
        "paperId": args.paper or "MANUAL",
        "number": len(st.get("questions", [])) + 1,
        "stem": args.stem,
        "section": "",
        "type": args.type,
        "kind": args.kind,
        "points": args.points,
        "page": None,
        "sourceFile": "manual",
        "officialAnswer": args.answer,
        "check": json.loads(args.check) if args.check else None,
        "kpIds": args.kp or [],
    }
    st.setdefault("questions", []).append(q)
    compute_difficulty(st)
    session.save()
    print(f"已加入 {q['id']}")
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    session = _session(args)
    for kp in session.state.get("knowledgePoints", []):
        print(f"{kp['id']}\t{kp['title']}\t{source_label(kp)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coach.py", description="review-sprint: 单科目考前冲刺教练")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE, help="工作区目录（默认 .review-sprint）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="导入资料并建立工作区")
    p.add_argument("--course", required=True)
    p.add_argument("--exam-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--materials", nargs="+", required=True, help="资料文件或目录，可多个")
    p.add_argument("--daily-minutes", type=int, default=120)
    p.add_argument("--target", type=int, default=90)
    p.add_argument("--lang", default="zh")
    p.add_argument("--density", choices=["concise", "standard", "detailed"], default="standard")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="显示进度行和到期复习")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("plan", help="生成/重建排期")
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("today", help="生成当天学习包")
    p.add_argument("--day", type=int)
    p.add_argument("--density", choices=["concise", "standard", "detailed"])
    p.set_defaults(func=cmd_today)

    p = sub.add_parser("answer", help="记录一道题的作答")
    p.add_argument("--qid", required=True)
    p.add_argument("--result", choices=["correct", "wrong"], required=True)
    p.add_argument("--confidence", type=int, choices=[0, 1, 2, 3], default=2)
    p.add_argument("--cause", choices=["concept", "calc", "reading", "memory", "time", "unknown"], default="unknown")
    p.add_argument("--seconds", type=int, default=0)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_answer)

    p = sub.add_parser("review", help="记录一次知识点复习（FSRS）")
    p.add_argument("--kp", required=True)
    p.add_argument("--rating", type=int, choices=[1, 2, 3, 4], required=True)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("quiz", help="按错题/常考度抽题")
    p.add_argument("--n", type=int, default=7)
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
    p.set_defaults(func=cmd_bilibili)

    p = sub.add_parser("calc", help="确定性重算")
    p.add_argument("--kind", choices=["twos", "decode", "ieee754", "ieee754_decode", "flags", "modrm"])
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
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("recompute", help="按题库 check 规则重算并比对官方答案")
    p.add_argument("--qid", required=True)
    p.set_defaults(func=cmd_recompute)

    p = sub.add_parser("types", help="查看 16 类题型矩阵与常考度")
    p.set_defaults(func=cmd_types)

    p = sub.add_parser("set-check", help="为题目绑定确定性校验规则")
    p.add_argument("--qid", required=True)
    p.add_argument("--check", required=True, help="JSON，例如 {\"kind\":\"twos\",\"value\":-5,\"bits\":8}")
    p.set_defaults(func=cmd_set_check)

    p = sub.add_parser("audit", help="运行质检门禁")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("export", help="导出排期/速记表/日历/Anki")
    p.add_argument("--format", default="md,ics,anki")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("doctor", help="检查环境与依赖")
    p.add_argument("--cookie-file")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("set", help="改考试日期/预算/目标/密度")
    p.add_argument("--exam-date")
    p.add_argument("--daily-minutes", type=int)
    p.add_argument("--target", type=int)
    p.add_argument("--density", choices=["concise", "standard", "detailed"])
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("add-question", help="向题库加入一道题")
    p.add_argument("--id", required=True)
    p.add_argument("--paper")
    p.add_argument("--type", required=True)
    p.add_argument("--kind", choices=["basic", "past", "advanced"], default="basic")
    p.add_argument("--stem", required=True)
    p.add_argument("--answer")
    p.add_argument("--check", help="JSON 校验规格")
    p.add_argument("--kp", nargs="*", default=[])
    p.add_argument("--points", type=float, default=5)
    p.set_defaults(func=cmd_add_question)

    p = sub.add_parser("sources", help="列出知识点与来源标签")
    p.set_defaults(func=cmd_sources)

    # allow --workspace after the subcommand as well as before it
    for child in sub.choices.values():
        child.add_argument("--workspace", default=argparse.SUPPRESS)

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
