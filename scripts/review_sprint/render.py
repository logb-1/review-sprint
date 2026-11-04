"""Markdown renderers for the daily packet, plan, cheat sheet and status."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .bilibili import format_clock
from .schedule import compute_difficulty, due_reviews, top_difficult
from .state import Session
from .util import human_minutes, write_text

SOURCE_ORIGINAL = "原文"
SOURCE_EDITED = "整理"
SOURCE_ADDED = "补充"
SOURCE_TODO = "待确认"


def source_label(kp: dict[str, Any]) -> str:
    source = kp.get("source") or {}
    file = source.get("file") or ""
    page = source.get("page")
    if file and page:
        return f"〔{SOURCE_ORIGINAL}：{Path(file).name} 第 {page} 页〕"
    if file:
        return f"〔{SOURCE_ORIGINAL}：{Path(file).name}〕"
    if kp.get("sourceLabel"):
        return f"〔{kp['sourceLabel']}〕"
    return f"〔{SOURCE_TODO}：未定位到原文，请复核〕"


def _progress(session: Session, day: dict[str, Any]) -> str:
    st = session.state
    exam = date.fromisoformat(st["examDate"])
    left = max(0, (exam - date.fromisoformat(day["date"])).days)
    return (
        f"📍 第 {day['day']}/{len(st['schedule']['days'])} 天 · {day['phase']} · "
        f"{day['date']} · 剩余 {left} 天 · 今日约 {human_minutes(day['minutes'])} · "
        f"下一步：python scripts/coach.py today"
    )


def _video_block(row: dict[str, Any]) -> str:
    title = row.get("title", "")
    author = row.get("author", "")
    score = row.get("score", 0)
    reason = row.get("reason", "")
    link = row.get("link") or row.get("searchUrl") or ""
    start = row.get("start")
    clock = f" · 从 {format_clock(start)} 开始" if start else ""
    return (
        f"- [{title}]({link}) · UP {author or '未知'} · 匹配度 {score:.2f}{clock}\n"
        f"  - 匹配理由：{reason or '锚词命中'}\n"
        f"  - 用法：先做题，仍卡住再看这一段；看完回来复述一遍。"
    )


def daily_markdown(session: Session, day: dict[str, Any] | None = None, density: str | None = None) -> str:
    st = session.require()
    day = day or session.find_day()
    if not day:
        raise SystemExit("没有找到当天安排，请先运行 plan")
    density = density or st.get("density", "standard")
    kps = {kp["id"]: kp for kp in st.get("knowledgePoints", [])}
    questions = {q["id"]: q for q in st.get("questions", [])}
    videos_by_kp: dict[str, list[dict[str, Any]]] = {}
    for row in st.get("videos", []):
        videos_by_kp.setdefault(row.get("kpId", ""), []).append(row)

    lines: list[str] = []
    lines.append(f"# {st['course']} · 第 {day['day']} 天（{day['date']}）")
    lines.append("")
    lines.append(_progress(session, day))
    lines.append("")
    if day.get("warning"):
        lines.append(f"> ⚠️ {day['warning']}")
        lines.append("")
    if day.get("phase") == "诊断期":
        lines.append("> 今天是诊断日：先独立完成，不查资料、不限时；错题会决定后续 D 分与复习优先级。")
        lines.append("")

    # 1. recall
    lines.append("## 1. 开场回忆（约 10 分钟，闭卷）")
    lines.append("")
    due = due_reviews(st, date.fromisoformat(day["date"]))
    if due:
        for item in due[:8]:
            if item.get("kpId"):
                lines.append(f"- [ ] {item['kpId']} {kps.get(item['kpId'], {}).get('title', '')}：先默写定义/公式，再对照速记表。")
            else:
                lines.append(f"- [ ] {item['questionId']}：错题重测（{item.get('cause', '未知错因')}）。")
    else:
        lines.append("- 今天没有到期复习项；用 2 分钟回忆昨天最后 3 题。")
    for item in day.get("reviews", [])[:6]:
        lines.append(f"- [ ] 间隔复习 {item['kpId']} {item.get('title', '')}（第 {item.get('interval')} 天复现）")
    lines.append("")

    # 2. knowledge points
    lines.append("## 2. 今日知识点")
    lines.append("")
    day_kps = [kps[k] for k in day.get("kpIds", []) if k in kps]
    if not day_kps:
        lines.append("> 今天没有新知识点（复习/模拟日）。")
    for kp in day_kps:
        lines.append(f"### {kp['id']} {kp['title']}")
        lines.append("")
        lines.append(f"{source_label(kp)} · 难度 D={float(kp.get('D', 0)):.2f}")
        lines.append("")
        if density == "concise":
            lines.append("<!-- MODEL: 3 句话讲清定义、适用条件、一个反例。 -->")
        else:
            lines.append("<!-- MODEL: 先用生活化类比引入，再给定义、公式/条件、一个正例和一个反例；不要直接给练习题答案。 -->")
            lines.append("")
            lines.append("**先猜一猜（预测试）**：<!-- MODEL: 出 1 道 30 秒能答完的小题，先不给答案。 -->")
        lines.append("")
        # videos after the knowledge point
        rows = videos_by_kp.get(kp["id"], [])
        if rows:
            lines.append(f"#### 🎬 卡住时看（{kp['id']} 相关）")
            lines.append("")
            for row in rows[:2]:
                lines.append(_video_block(row))
            lines.append("")
            lines.append("> 先做完下面的题，仍卡住再看；视频只是补救，不是主线。")
        else:
            lines.append(f"> 还没有高重合视频。运行 `python scripts/coach.py bilibili --kp {kp['id']}` 检索；"
                         f"没有达到阈值就只看搜索链接，不要编造。")
            lines.append("")

    # 3. difficult points
    lines.append("## 3. 难点精讲（按实时 D 分排序）")
    lines.append("")
    top = top_difficult(st, 3)
    if density == "concise":
        top = top[:2]
    for kp in top:
        parts = kp.get("difficultyParts", {})
        lines.append(f"### {kp['id']} {kp['title']} · D={float(kp.get('D', 0)):.2f}")
        lines.append("")
        lines.append(
            f"- 难度构成：往年失分 {parts.get('pastLoss', 0):.2f} · 你的错误率 {parts.get('userError', 0):.2f} · "
            f"前置深度 {parts.get('prereqDepth', 0):.2f} · 易错标记 {parts.get('errorFlags', 0):.2f}"
        )
        lines.append("- 最常见错法：<!-- MODEL: 写一个具体错法，不要写“粗心”。 -->")
        lines.append("- 易混概念对：<!-- MODEL: 写出 A vs B 的区别，各一句。 -->")
        lines.append("- 一道最小例题：<!-- MODEL: 给一道 2 分钟内能做完的例题，答案放文末。 -->")
        lines.append("")

    # 4. drills
    lines.append("## 4. 题型专练（4 基础 + 2 真题 + 1 拔高）")
    lines.append("")
    if day.get("slots"):
        for index, slot in enumerate(day["slots"], start=1):
            if slot.get("kind") in {"mock", "proof"}:
                label = "整卷模拟" if slot["kind"] == "mock" else "附加证明"
                lines.append(f"{index}. **[{label}]** <!-- MODEL: 用真题/变式组卷；不要重复已做过的题。 -->")
                continue
            qid = slot.get("qid")
            q = questions.get(qid) if qid else None
            type_name = next((t["name"] for t in st.get("questionTypes", []) if t["id"] == slot.get("type")), slot.get("type"))
            if q:
                lines.append(f"{index}. **[{slot['type']} {type_name}]** `{q['id']}` {q['stem'].splitlines()[0]}")
                if len(q["stem"].splitlines()) > 1:
                    lines.append("")
                    lines.append("   " + "\n   ".join(q["stem"].splitlines()[1:]))
            else:
                lines.append(
                    f"{index}. **[{slot['type']} {type_name}]** <!-- MODEL: 生成一道 {type_name} 的{slot['kind']}题；"
                    f"先写入题库再引用题号，不要临时编号。 -->"
                )
            lines.append("")
    else:
        lines.append("> 今天没有排题。")
    lines.append("")

    # 5. error causes
    lines.append("## 5. 错因分类（做完题后逐题标）")
    lines.append("")
    lines.append("| 题号 | 对/错 | 信心 0–3 | 错因 | 补救 |")
    lines.append("|---|---|---|---|---|")
    lines.append("|  |  |  | 概念 / 计算 / 审题 / 记忆 / 时间 | 重讲+视频 / 同类专练 / 题型识别卡 / 间隔复习 / 限时 |")
    lines.append("")

    # 6. cheat sheet
    lines.append("## 6. 今日速记表")
    lines.append("")
    lines.append("| 知识点 | 一句话理解 | 答题要点（1-2-3） |")
    lines.append("|---|---|---|")
    for kp in day_kps:
        lines.append(f"| {kp['id']} {kp['title']} | <!-- MODEL: 一句话 --> | <!-- MODEL: 123 --> |")
    if not day_kps:
        lines.append("| — | 今天以错题为主 | 只看错题本和速记表 |")
    lines.append("")

    # 7. bedtime
    lines.append("## 7. 睡前 3 题 & 明日预告")
    lines.append("")
    todays = [s for s in day.get("slots", []) if s.get("qid")]
    for slot in todays[:3]:
        lines.append(f"- [ ] {slot['qid']}：合上书，只看题干，口述思路。")
    if not todays:
        lines.append("- [ ] 从错题本任选 3 题，口述思路。")
    tomorrow = None
    for d in st.get("schedule", {}).get("days", []):
        if d["day"] == day["day"] + 1:
            tomorrow = d
            break
    if tomorrow:
        lines.append("")
        lines.append(f"明日：第 {tomorrow['day']} 天 · {tomorrow['phase']} · 约 {human_minutes(tomorrow['minutes'])}。")
    lines.append("")

    # 8. answers
    lines.append("## 8. 参考答案与解析")
    lines.append("")
    for slot in day.get("slots", []):
        qid = slot.get("qid")
        if not qid:
            continue
        q = questions.get(qid)
        if not q:
            continue
        lines.append(f"### {qid}")
        lines.append("")
        if q.get("officialAnswer"):
            lines.append(f"- 〔官方答案〕{q['officialAnswer']}")
        if q.get("recomputed"):
            lines.append(f"- 〔脚本重算〕{q['recomputed']}")
        if q.get("conflict"):
            lines.append(f"- ⚠️ {q['conflict']}")
        if not q.get("officialAnswer") and not q.get("recomputed"):
            lines.append("- ⚠️ 还没有可核验答案：先用 `coach.py calc` 重算，再写解析；不要直接抄答案文件。")
        lines.append("- 解析：<!-- MODEL: 给中间步骤、评分点、易错点；与官方答案冲突时写明依据。 -->")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def plan_markdown(state: dict[str, Any]) -> str:
    lines = [f"# {state['course']} · 复习排期", ""]
    lines.append(f"- 考试日期：{state['examDate']}")
    lines.append(f"- 每天预算：{human_minutes(int(state.get('dailyMinutes', 120)))}")
    lines.append(f"- 目标分：{state.get('targetScore', 90)}")
    lines.append("")
    lines.append("| 天 | 日期 | 阶段 | 新知识点 | 复习 | 题目 | 用时 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for day in state.get("schedule", {}).get("days", []):
        slots = len(day.get("slots", []))
        kp_text = "、".join(day.get("kpIds", [])[:3]) or "—"
        lines.append(
            f"| {day['day']} | {day['date']} | {day['phase']} | {kp_text} | "
            f"{len(day.get('reviews', []))} | {slots} | {human_minutes(day['minutes'])} | {day.get('warning', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def cheatsheet_markdown(state: dict[str, Any]) -> str:
    lines = [f"# {state['course']} · 考前速记表", ""]
    lines.append("| ID | 知识点 | 一句话 | 答题要点 | 来源 |")
    lines.append("|---|---|---|---|---|")
    for kp in state.get("knowledgePoints", []):
        lines.append(
            f"| {kp['id']} | {kp['title']} | <!-- MODEL: 一句话 --> | <!-- MODEL: 123 --> | {source_label(kp)} |"
        )
    return "\n".join(lines)


def write_daily(session: Session, day: dict[str, Any] | None = None, density: str | None = None) -> Path:
    day = day or session.find_day()
    if not day:
        raise SystemExit("没有找到当天安排，请先运行 plan")
    text = daily_markdown(session, day, density)
    path = session.daily_dir / f"D{day['day']:02d}-{day['date']}.md"
    write_text(path, text)
    return path
