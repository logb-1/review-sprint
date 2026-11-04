"""One-command build: ingest -> subject -> quantify -> schedule -> five books -> audit."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .audit import audit, format_audit
from .books import write_books
from .docx_writer import DocxDependencyError
from .ingest import setup
from .mastery import summary as mastery_summary
from .quantify import quantify, schedule_workload
from .schedule import build_schedule, plan_summary, validate_schedule
from .state import Session, load_session
from .subjects import SubjectConfirmationRequired, has_profile, profile_names
from .util import write_json, write_text


class BuildError(RuntimeError):
    pass


class BuildDependencyError(BuildError):
    pass


def _record(step_dir: Path, name: str, data: Any) -> None:
    step_dir.mkdir(parents=True, exist_ok=True)
    write_json(step_dir / name, data)


def _require_dependencies(paths: list[Path]) -> None:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(p for p in path.rglob("*") if p.is_file())
        elif path.is_file():
            files.append(path)
    suffixes = {p.suffix.lower() for p in files}
    if suffixes & {".pptx", ".ppt"}:
        try:
            import pptx  # noqa: F401
        except Exception as exc:
            raise BuildDependencyError("解析 PPT/PPTX 需要 python-pptx；请运行: pip install python-pptx") from exc
        if ".ppt" in suffixes and not (shutil.which("soffice") or shutil.which("libreoffice")):
            raise BuildDependencyError("旧版 .ppt 需要 LibreOffice（soffice）先转 .pptx")
    if ".docx" in suffixes:
        try:
            import docx  # noqa: F401
        except Exception as exc:
            raise BuildDependencyError("解析 DOCX 需要 python-docx；请运行: pip install python-docx") from exc
    if ".pdf" in suffixes:
        try:
            import pypdf  # noqa: F401
        except Exception as exc:
            raise BuildDependencyError("解析 PDF 需要 pypdf；请运行: pip install pypdf") from exc


def _pdf_convert(docx_paths: list[Path], out_dir: Path) -> list[Path]:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise BuildDependencyError("生成 PDF 需要 LibreOffice（soffice）；或改用 --format md,docx")
    written = []
    for path in docx_paths:
        proc = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(path)],
            capture_output=True, text=True, timeout=120,
        )
        pdf = out_dir / (path.stem + ".pdf")
        if proc.returncode != 0 or not pdf.exists():
            raise BuildDependencyError(f"PDF 转换失败：{path.name}: {(proc.stderr or proc.stdout)[:200]}")
        written.append(pdf)
    return written


def build(
    workspace: Path,
    course: str,
    materials: list[Path],
    past_papers: list[Path],
    target: int,
    days: int,
    daily_minutes: int = 120,
    subject: str | None = None,
    out: Path | None = None,
    formats: list[str] | None = None,
    exam_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if target is None or days is None:
        raise BuildError("需要 --target 和 --days；请先询问用户这两个字段")
    if int(target) < 0 or int(target) > 100:
        raise BuildError("--target 必须在 0–100")
    if int(days) < 1:
        raise BuildError("--days 必须 ≥1")
    if subject and not has_profile(subject):
        raise BuildError("未知科目画像；可用：" + ", ".join(profile_names()))
    formats = formats or ["md", "docx"]
    formats = [f.strip().lower() for f in formats if f.strip()]
    if "docx" not in formats or "md" not in formats:
        raise BuildError("build 必须同时包含 md 和 docx；请用 --format md,docx[,pdf]")
    if exam_date and exam_date <= date.today():
        raise BuildError("考试日期必须晚于今天；考试当天及之后无法排学习任务")
    if exam_date and (exam_date - date.today()).days != int(days):
        print(f"⚠️ 考试日期与 --days 不一致；以 --days={days} 为准")

    workspace = Path(workspace).resolve()
    output = Path(out).resolve() if out else workspace / "output"
    step_dir = output / "_build"
    if output.exists() and not force:
        # keep old outputs but overwrite the five books; intermediate steps are replaced
        pass
    output.mkdir(parents=True, exist_ok=True)
    _record(step_dir, "00_inputs.json", {
        "course": course, "materials": [str(p) for p in materials],
        "past_papers": [str(p) for p in past_papers], "target": target,
        "days": days, "dailyMinutes": daily_minutes, "subject": subject,
        "formats": formats, "out": str(output),
    })

    all_materials = list(materials) + list(past_papers)
    _require_dependencies(all_materials)
    try:
        state = setup(
            workspace, course, exam_date or (date.today() + timedelta(days=int(days))),
            all_materials, daily_minutes=daily_minutes, target_score=int(target),
            subject=subject, days=int(days),
        )
    except SubjectConfirmationRequired as exc:
        candidates = "、".join(f"{x['subject']}({x['score']})" for x in exc.detection.get("candidates", []))
        if not candidates:
            candidates = "未命中任何画像，请从 " + " / ".join(profile_names()) + " 中指定"
        raise BuildError("科目识别置信度 <0.6，需要用户确认。候选：" + candidates + "；请加 --subject 重跑") from exc
    _record(step_dir, "01_ingest.json", {
        "materials": state.get("materials", []), "chapters": len(state.get("chapters", [])),
        "knowledgePoints": len(state.get("knowledgePoints", [])),
        "questions": len(state.get("questions", [])), "papers": len(state.get("papers", [])),
    })
    _record(step_dir, "02_subject.json", {
        "subject": state.get("subject"), "confidence": state.get("subjectConfidence"),
        "source": state.get("subjectSource"), "profile": state.get("subjectProfile"),
    })

    quantification = quantify(state, target=int(target), days=int(days), daily_minutes=daily_minutes)
    _record(step_dir, "03_quantification.json", quantification)
    build_schedule(state, days=int(days))
    schedule_workload(state)
    _record(step_dir, "04_schedule.json", {
        "summary": plan_summary(state), "problems": validate_schedule(state),
        "days": state.get("schedule", {}).get("days", []),
    })

    # setup already generated stage-one books? no: build owns the five-book output
    try:
        paths = write_books(Session(workspace), output, formats=formats)
    except DocxDependencyError as exc:
        raise BuildError(str(exc)) from exc
    docx_paths = [p for p in paths if p.suffix.lower() == ".docx"]
    if "pdf" in formats:
        paths.extend(_pdf_convert(docx_paths, output))
    _record(step_dir, "05_books.json", {
        "files": [{"path": str(p), "size": p.stat().st_size} for p in paths],
        "mastery": mastery_summary(state),
    })

    session = Session(workspace)
    state = session.require()
    state["build"] = {
        "out": str(output), "formats": formats, "completedAt": date.today().isoformat(),
        "files": [str(p) for p in paths], "auditOk": False,
    }
    session.save()
    report = audit(session)
    _record(step_dir, "audit.json", report)
    state = session.require()
    state["build"] = {
        "out": str(output), "formats": formats, "completedAt": date.today().isoformat(),
        "files": [str(p) for p in paths], "auditOk": report["ok"],
    }
    session.save()
    write_text(output / "质检报告.md", format_audit(report))
    return {
        "paths": paths, "report": report, "state": state,
        "output": output, "quantification": quantification,
    }
