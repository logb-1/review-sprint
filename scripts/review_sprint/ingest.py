"""Material ingestion: classify, extract, chapter, question bank, knowledge points."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .keywords import extract_keywords, split_headings
from .schedule import build_schedule, seed_question_types
from .state import Session, new_state
from .topics import detect_domain
from .util import (
    clean_term, jaccard, normalize_for_match, read_text, shingles, slugify,
    write_json, write_text,
)

MATERIAL_PRIORITY = ["syllabus", "keypoints", "pastpaper", "answers", "homework", "slides", "notes", "textbook", "other"]
MATERIAL_LABELS = {
    "syllabus": "考纲/大纲",
    "keypoints": "重点/考点",
    "pastpaper": "往年题",
    "answers": "答案/解析",
    "homework": "作业/习题",
    "slides": "课件/讲义",
    "notes": "笔记/总结",
    "textbook": "教材/阅读材料",
    "other": "其他",
}
TYPE_KEYWORDS = {
    "syllabus": ("考纲", "大纲", "syllabus", "考试范围", "考核要求", "课程目标"),
    "keypoints": ("重点", "考点", "必考", "复习要点", "划重点", "高频"),
    "pastpaper": ("真题", "试卷", "期末", "期中", "考试", "exam", "paper", "模拟", "样卷"),
    "answers": ("答案", "answer", "solution", "参考答案", "解析", "key"),
    "homework": ("作业", "homework", "hw", "习题", "练习"),
    "slides": ("课件", "讲义", "ppt", "slide", "lecture", "第1章", "第2章", "第3章"),
    "notes": ("笔记", "note", "总结", "整理", "复习"),
    "textbook": ("教材", "book", "课本", "教程", "阅读材料"),
}
HEADING_RES = [
    re.compile(r"^\s{0,3}#{1,4}\s+(.{2,80})$"),
    re.compile(r"^\s*第\s*([0-9一二三四五六七八九十]{1,3})\s*[章节部分讲单元]\s*(.{0,60})$"),
    re.compile(r"^\s*(Chapter|Unit|Part)\s+\d+\s*[:：.]?\s*(.{0,60})$", re.I),
    re.compile(r"^\s*\d{1,2}\s*[.、]\s*[^\d\s].{2,60}$"),
]
CHAPTER_RES = [
    re.compile(r"^\s{0,2}#\s+(.{2,80})$"),
    re.compile(r"^\s*第\s*([0-9一二三四五六七八九十]{1,3})\s*[章节部分]\s*(.{0,60})$"),
    re.compile(r"^\s*(Chapter|Unit|Part)\s+\d+\s*[:：.]?\s*(.{0,60})$", re.I),
]
QUESTION_RE = re.compile(r"^\s*(?:第\s*)?[（(]?(\d{1,2})[)）]?\s*[.、．:：]\s*(.{4,})$")
SECTION_RE = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、.]\s*(选择题|填空题|判断题|简答题|计算题|分析题|证明题|综合题|论述题|编程题|应用题)")
ANSWER_RE = re.compile(r"^\s*(?:第\s*)?[（(]?(\d{1,2})[)）]?\s*[.、．:：]\s*(.{1,})$")


@dataclass
class ExtractedDoc:
    path: Path
    rel: str
    category: str = "other"
    text: str = ""
    pages: list[tuple[int | None, str]] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    status: str = "ok"
    error: str = ""
    chars: int = 0
    has_answers: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "rel": self.rel,
            "category": self.category,
            "categoryLabel": MATERIAL_LABELS.get(self.category, self.category),
            "status": self.status,
            "error": self.error,
            "chars": self.chars,
            "hasAnswers": self.has_answers,
        }


def classify(path: Path, text: str = "") -> str:
    name = path.stem.lower()
    body = (text or "")[:3000].lower()
    if any(w in name for w in ("考纲", "大纲", "syllabus")):
        return "syllabus"
    if any(w in name for w in ("重点", "考点", "必考", "划重点")):
        return "keypoints"
    has_answer = any(w in name for w in ("答案", "answer", "solution", "解析"))
    has_paper = any(w in name for w in (
        "真题", "试卷", "期末", "期中", "考试", "exam", "paper", "模拟", "样卷",
        "final", "midterm", "test", "quiz", "卷",
    ))
    if has_answer:
        if "试卷" in name and not any(w in name for w in ("答案", "解析", "answer", "solution")):
            return "pastpaper"
        return "answers"
    if has_paper:
        return "pastpaper"
    if any(w in name for w in ("作业", "homework", "hw", "习题", "练习")):
        return "homework"
    if any(w in name for w in ("课件", "讲义", "ppt", "slide", "lecture")) or re.search(r"第\s*\d+\s*章", body):
        return "slides"
    if any(w in name for w in ("笔记", "note", "总结", "整理", "复习")):
        return "notes"
    if any(w in name for w in ("教材", "book", "课本", "教程", "阅读材料")):
        return "textbook"
    # content-based fallbacks
    if "选择题" in body and ("分" in body or "答案" in body):
        return "pastpaper"
    if re.search(r"^\s*第\s*\d+\s*章", body, re.M):
        return "slides"
    return "other"


def has_answer_marker(path: Path, text: str = "") -> bool:
    name = path.stem.lower()
    return any(w in name for w in ("答案", "解析", "solution", "answer")) or "参考答案" in (text or "")[:2000]


def _read_markdown_pages(text: str) -> list[tuple[int | None, str]]:
    marker = re.compile(r"<!--\s*page:\s*(\d+)\s*-->|【第\s*(\d+)\s*页】")
    if not marker.search(text):
        return [(None, text)]
    pages: list[tuple[int | None, str]] = []
    current = 1
    last = 0
    for match in marker.finditer(text):
        chunk = text[last:match.start()]
        if chunk.strip():
            pages.append((current, chunk))
        current = int(match.group(1) or match.group(2) or current + 1)
        last = match.end()
    tail = text[last:]
    if tail.strip():
        pages.append((current, tail))
    return pages or [(None, text)]


def extract_doc(path: Path, rel: str) -> ExtractedDoc:
    suffix = path.suffix.lower()
    doc = ExtractedDoc(path=path, rel=rel)
    try:
        if suffix in {".md", ".markdown", ".txt"}:
            text = read_text(path)
            text = re.sub(r"<!--\s*page:\s*(\d+)\s*-->", r"【第\1页】", text)
            text = re.sub(r"<!--\s*/?\s*page[^>]*-->", "", text)
            doc.text = text
            doc.pages = _read_markdown_pages(text)
        elif suffix == ".docx":
            import docx  # type: ignore

            document = docx.Document(str(path))
            lines = []
            headings = []
            for para in document.paragraphs:
                value = para.text.strip()
                if not value:
                    continue
                style = (para.style.name or "") if para.style else ""
                if style.lower().startswith("heading") or style in {"Title", "标题"}:
                    headings.append(value)
                    lines.append(f"## {value}")
                else:
                    lines.append(value)
            for table in document.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        lines.append(" | ".join(cells))
            doc.text = "\n".join(lines)
            doc.headings = headings
            doc.pages = [(None, doc.text)]
        elif suffix == ".pptx":
            from pptx import Presentation  # type: ignore

            prs = Presentation(str(path))
            pages = []
            headings = []
            for index, slide in enumerate(prs.slides, start=1):
                parts = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        parts.append(shape.text.strip())
                    if getattr(shape, "has_table", False):
                        for row in shape.table.rows:
                            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
                try:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        parts.append("[备注] " + notes)
                except Exception:
                    pass
                page_text = "\n".join(parts)
                pages.append((index, page_text))
                if parts:
                    first = parts[0].splitlines()[0][:60]
                    if 2 <= len(first) <= 60:
                        headings.append(first)
            doc.text = "\n\n".join(f"【第{p}页】\n{t}" for p, t in pages)
            doc.pages = pages
            doc.headings = headings
        elif suffix == ".pdf":
            pages: list[tuple[int | None, str]] = []
            try:
                from pypdf import PdfReader  # type: ignore

                reader = PdfReader(str(path))
                pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
            except Exception:
                pages = []
            if not any(text.strip() for _, text in pages):
                try:
                    import fitz  # type: ignore

                    pdf = fitz.open(str(path))
                    pages = [(i + 1, page.get_text() or "") for i, page in enumerate(pdf)]
                except Exception:
                    pages = []
            doc.pages = pages
            doc.text = "\n\n".join(f"【第{p}页】\n{t}" for p, t in pages if t.strip())
            if not doc.text.strip():
                doc.status = "needs_ocr"
                doc.error = "PDF 文本层为空，需要 OCR 或视觉模型"
        elif suffix == ".html":
            text = read_text(path)
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", "\n", text)
            import html as html_mod
            doc.text = html_mod.unescape(text)
            doc.pages = [(None, doc.text)]
        elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            doc.status = "needs_ocr"
            doc.error = "图片需要 OCR 或视觉模型"
        elif suffix in {".doc", ".ppt", ".xls"}:
            doc.status = "needs_conversion"
            doc.error = "旧版 Office 格式，需先转换为 docx/pptx/pdf"
        else:
            doc.status = "unsupported"
            doc.error = f"不支持的格式: {suffix}"
    except Exception as exc:
        doc.status = "error"
        doc.error = f"{type(exc).__name__}: {exc}"
    doc.text = doc.text or ""
    doc.chars = len(doc.text)
    doc.category = classify(path, doc.text)
    doc.has_answers = has_answer_marker(path, doc.text)
    return doc


def _line_page_map(text: str) -> list[tuple[int, int | None]]:
    """Return (offset, page) anchors parsed from 【第N页】 markers."""
    anchors = []
    for match in re.finditer(r"【第\s*(\d+)\s*页】", text):
        anchors.append((match.start(), int(match.group(1))))
    return anchors


def page_for_offset(text: str, offset: int) -> int | None:
    page = None
    for start, number in _line_page_map(text):
        if start <= offset:
            page = number
        else:
            break
    return page


def page_for_term(text: str, term: str) -> int | None:
    if not term:
        return None
    index = text.find(term)
    if index < 0:
        return None
    return page_for_offset(text, index)


def is_chapter_heading(line: str) -> bool:
    value = line.strip()
    if not value or len(value) > 90:
        return False
    if any(r.match(value) for r in CHAPTER_RES):
        return True
    # docx headings are rendered as "## 第N章 ..."
    if re.match(r"^\s*##\s+第\s*[0-9一二三四五六七八九十]{1,3}\s*[章节部分]", value):
        return True
    return False


def is_heading(line: str) -> bool:
    value = line.strip()
    if not value or len(value) > 90:
        return False
    if any(r.match(value) for r in HEADING_RES):
        return True
    if re.match(r"^\s*[0-9]{1,2}\.[0-9]{1,2}\s+", value):
        return True
    return False


def heading_title(line: str) -> str:
    value = line.strip()
    value = re.sub(r"^#{1,4}\s*", "", value)
    value = re.sub(r"^\s*第\s*[0-9一二三四五六七八九十]{1,3}\s*[章节部分讲单元]\s*", "", value)
    value = re.sub(r"^\s*(Chapter|Unit|Part)\s+\d+\s*[:：.]?\s*", "", value, flags=re.I)
    value = re.sub(r"^\s*\d{1,2}(?:\.\d{1,2})*\s*[.、:：]?\s*", "", value)
    return clean_term(value)[:80]


def split_chapters(doc: ExtractedDoc, start_index: int = 1, max_chars: int = 6000) -> list[dict[str, Any]]:
    text = doc.text
    if not text.strip():
        return []
    lines = text.splitlines()
    indices: list[int] = []
    in_code = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and is_chapter_heading(line):
            indices.append(i)
    chapters: list[dict[str, Any]] = []
    if len(indices) >= 1:
        for order, line_index in enumerate(indices):
            end = indices[order + 1] if order + 1 < len(indices) else len(lines)
            body = "\n".join(lines[line_index + 1:end]).strip()
            title = heading_title(lines[line_index])
            if not title or len(body) < 80:
                continue
            if any(word in title for word in ("使用说明", "目录", "前言", "导读")):
                continue
            chapters.append({"title": title, "text": body, "headingLine": lines[line_index].strip()})
    if not chapters:
        # fall back to fixed-size chunks at sentence boundaries
        paragraphs = re.split(r"\n\s*\n", text)
        buffer: list[str] = []
        size = 0
        for para in paragraphs:
            if size + len(para) > max_chars and buffer:
                body = "\n\n".join(buffer).strip()
                first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
                chapters.append({"title": clean_term(first)[:60] or f"第{len(chapters) + 1}部分", "text": body})
                buffer, size = [], 0
            buffer.append(para)
            size += len(para)
        if buffer:
            body = "\n\n".join(buffer).strip()
            first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
            chapters.append({"title": clean_term(first)[:60] or f"第{len(chapters) + 1}部分", "text": body})
    out = []
    for i, chapter in enumerate(chapters):
        out.append({
            "id": f"CH{start_index + i}",
            "title": chapter["title"],
            "text": chapter["text"],
            "source": {"file": doc.rel, "pageStart": page_for_term(text, chapter["text"][:20])},
        })
    return out


def merge_chapters(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for chapter in chapters:
        key = normalize_for_match(chapter["title"])[:16]
        found = None
        for existing in merged:
            other = normalize_for_match(existing["title"])[:16]
            if key and other and (key == other or (len(key) > 4 and (key in other or other in key))):
                found = existing
                break
        if found:
            found["text"] += "\n\n" + chapter["text"]
            found.setdefault("sources", []).append(chapter["source"])
        else:
            chapter.setdefault("sources", [chapter["source"]])
            merged.append(chapter)
    for i, chapter in enumerate(merged, start=1):
        chapter["id"] = f"CH{i}"
    return merged


def extract_question_type(stem: str, section: str = "") -> str:
    text = f"{section} {stem}"
    low = text.lower()
    rules = [
        ("T6", ("汇编", "反汇编", "机器码", "机器指令", "指令编码", "指令", "寄存器", "寻址", "ModRM", "mov", "lea", "call", "ret")),
        ("T2", ("补码", "原码", "反码", "移码", "无符号", "溢出", "有符号", "整数表示", "标志位", "CF", "OF", "SF", "ZF")),
        ("T3", ("浮点", "IEEE", "IEEE754", "阶码", "尾数", "规格化", "单精度", "双精度")),
        ("T4", ("舍入", "浮点运算", "精度损失", "ULP", "误差")),
        ("T5", ("对齐", "填充", "结构体大小", "sizeof", "边界对齐", "字节序", "大端", "小端", "字节图")),
        ("T10", ("联合体", "枚举", "union", "enum")),
        ("T9", ("数组", "指针", "二维", "行优先", "指针运算")),
        ("T8", ("栈帧", "过程调用", "返回地址", "参数传递", "%rsp", "%rbp", "esp", "ebp", "堆栈")),
        ("T7", ("循环", "条件跳转", "if", "while", "for", "goto", "switch")),
        ("T12", ("重定位", "ELF", "目标文件", "节头", "符号表")),
        ("T11", ("链接", "静态库", "动态库", "共享库", "符号解析", "PLT", "GOT")),
        ("T13", ("异常", "中断", "信号", "陷阱", "故障", "终止")),
        ("T14", ("进程", "fork", "exec", "系统调用", "上下文切换")),
        ("T15", ("缓存", "cache", "局部性", "命中率", "存储层次", "TLB")),
        ("T16", ("优化", "性能", "CPI", "流水线", "循环展开", "分支预测")),
        ("T1", ("进制", "十六进制", "二进制", "八进制", "转换", "真值")),
    ]
    scores = {}
    for type_id, words in rules:
        score = 0
        for word in words:
            if word.lower() in low:
                score += 3 if len(word) >= 4 else 1
        if score:
            scores[type_id] = score
    if scores:
        return max(scores.items(), key=lambda kv: kv[1])[0]
    if section:
        section_map = {
            "选择题": "T1", "填空题": "T1", "判断题": "T1", "简答题": "T11",
            "计算题": "T2", "分析题": "T6", "证明题": "T11", "综合题": "T16",
            "论述题": "T11", "编程题": "T7", "应用题": "T9",
        }
        return section_map.get(section, "T1")
    return "T1"


def _question_kind(category: str, section: str) -> str:
    if category == "pastpaper":
        return "past"
    if section in {"证明题", "综合题", "论述题"}:
        return "advanced"
    return "basic"


def extract_questions(doc: ExtractedDoc, paper_id: str, course_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = doc.text.splitlines()
    section = ""
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    seen_ids: dict[str, int] = {}
    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue
        stripped = re.sub(r"^#{1,6}\s*", "", clean_line)
        section_match = SECTION_RE.match(stripped)
        if section_match:
            section = section_match.group(1)
            if current:
                questions.append(current)
                current = None
            continue
        match = QUESTION_RE.match(stripped)
        if match and not re.match(r"^\s*【第\s*\d+\s*页】", clean_line):
            if current:
                questions.append(current)
            number = int(match.group(1))
            stem = match.group(2).strip()
            if len(stem) < 4:
                current = None
                continue
            points_match = re.search(r"[（(](\d+(?:\.\d+)?)\s*分[)）]", stem)
            points = float(points_match.group(1)) if points_match else 1.0
            base_id = f"{paper_id}-Q{number}"
            seen_ids[base_id] = seen_ids.get(base_id, 0) + 1
            qid = base_id if seen_ids[base_id] == 1 else f"{base_id}-{seen_ids[base_id]}"
            current = {
                "id": qid,
                "paperId": paper_id,
                "number": number,
                "stem": stem,
                "section": section,
                "type": extract_question_type(stem, section),
                "kind": _question_kind(doc.category, section),
                "points": points,
                "page": page_for_offset(doc.text, doc.text.find(clean_line)),
                "sourceFile": doc.rel,
                "officialAnswer": None,
                "check": None,
            }
        elif current:
            if is_heading(clean_line):
                questions.append(current)
                current = None
                continue
            current["stem"] += "\n" + clean_line
            current["stem"] = current["stem"].strip()
    if current:
        questions.append(current)
    return questions


def extract_answers(doc: ExtractedDoc) -> dict[int, list[str]]:
    answers: dict[int, list[str]] = {}
    current: int | None = None
    for line in doc.text.splitlines():
        clean_line = line.strip()
        match = ANSWER_RE.match(clean_line)
        if match:
            number = int(match.group(1))
            current = number
            answers.setdefault(number, []).append(match.group(2).strip())
        elif current and clean_line:
            if answers.get(current):
                answers[current][-1] += "\n" + clean_line
    return answers


def pair_answers(papers: list[ExtractedDoc], answers: list[ExtractedDoc]) -> dict[str, ExtractedDoc]:
    pairs: dict[str, ExtractedDoc] = {}
    for paper in papers:
        best = None
        best_score = 0.0
        for answer in answers:
            a = normalize_for_match(re.sub(r"(答案|解析|参考答案|solution|answer|key)", "", paper.path.stem, flags=re.I))
            b = normalize_for_match(re.sub(r"(答案|解析|参考答案|solution|answer|key)", "", answer.path.stem, flags=re.I))
            score = SequenceMatcher(None, a, b).ratio()
            if score > best_score:
                best, best_score = answer, score
        if best and best_score >= 0.6:
            pairs[paper.rel] = best
    return pairs


def dedupe_papers(docs: list[ExtractedDoc]) -> list[dict[str, Any]]:
    papers = []
    for doc in docs:
        if doc.category != "pastpaper":
            continue
        paper = {
            "id": "P" + str(len(papers) + 1),
            "sourceFile": doc.rel,
            "title": doc.path.stem,
            "sameAs": None,
            "year": _guess_year(doc.path.stem),
            "chars": doc.chars,
        }
        for other in papers:
            if other["sameAs"]:
                continue
            if jaccard(shingles(doc.text, 5), shingles(other.get("text", ""), 5)) >= 0.75:
                paper["sameAs"] = other["id"]
                break
        paper["text"] = doc.text
        papers.append(paper)
    for paper in papers:
        paper.pop("text", None)
    return papers


def _guess_year(name: str) -> int | None:
    match = re.search(r"(20\d{2})", name)
    return int(match.group(1)) if match else None


VALID_TITLE_TERMS = {
    "整数", "无符号", "补码", "原码", "反码", "移码", "溢出", "截断", "浮点", "浮点数",
    "阶码", "尾数", "舍入", "精度", "对齐", "填充", "结构体", "联合体", "枚举", "字节",
    "字节序", "大端", "小端", "汇编", "寄存器", "寻址", "指令", "机器码", "栈帧",
    "过程", "调用", "返回", "地址", "条件", "条件码", "跳转", "循环", "数组", "指针",
    "链接", "符号", "重定位", "异常", "中断", "进程", "线程", "系统调用", "缓存",
    "局部性", "存储", "优化", "性能", "布局", "数据", "转换", "编码", "表示",
}


def title_terms(title: str) -> list[str]:
    """Cheap title decomposition for KP->question matching."""
    title = clean_term(title)
    terms: list[str] = []
    for g in (
        "补码", "原码", "反码", "移码", "无符号", "溢出", "浮点数", "阶码", "尾数",
        "舍入", "对齐", "结构体", "联合体", "字节序", "大端", "小端", "寄存器",
        "寻址", "ModRM", "汇编", "栈帧", "过程调用", "返回地址", "条件码", "跳转",
        "链接", "重定位", "ELF", "异常", "中断", "进程", "系统调用", "缓存", "局部性",
        "优化", "性能", "指针", "数组",
    ):
        if g in title:
            terms.append(g)
    for term in split_headings([title]):
        if term.isdigit() or (re.search(r"[\u4e00-\u9fff]", term) and len(term) > 8):
            continue
        terms.append(term)
    for i in range(0, max(0, len(title) - 1)):
        term = title[i:i + 2]
        if term in VALID_TITLE_TERMS:
            terms.append(term)
    out = []
    for term in terms:
        term = clean_term(term)
        if term and len(term) >= 2 and term not in out:
            out.append(term)
    return out[:6]


def anchor_terms(title: str) -> list[str]:
    candidates = [t for t in title_terms(title) if 2 <= len(t) <= 4]
    out: list[str] = []
    for term in sorted(candidates, key=len, reverse=True):
        if any(term in other or other in term for other in out):
            continue
        out.append(term)
    return out[:2]


GENERIC_HEADINGS = (
    "使用说明", "目录", "前言", "导读", "本章导读", "知识地图", "高频考点", "题型拆解",
    "易错点清单", "本章怎么学", "学习路径", "复习节奏", "考试位置", "全景", "小结",
    "在考试中的位置", "先看地图", "一句话是什么", "为什么需要", "规则/公式", "规则公式", "典型例题", "自测",
)


def kp_headings(text: str) -> list[str]:
    level2: list[str] = []
    level3: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = re.match(r"^(#{2,3})\s+(.+)$", line.strip())
        if not match:
            continue
        title = heading_title(line)
        if not title or len(title) < 2:
            continue
        if any(word in title for word in GENERIC_HEADINGS):
            continue
        if len(match.group(1)) == 2:
            level2.append(title)
        else:
            level3.append(title)
    if len(level2) >= 2:
        return level2
    if len(level3) >= 2:
        return level3
    return level2 + level3


def build_knowledge_points(
    chapters: list[dict[str, Any]],
    question_types: list[dict[str, Any]],
    max_per_chapter: int = 8,
) -> list[dict[str, Any]]:
    kps: list[dict[str, Any]] = []
    corpus = [c["text"] for c in chapters]
    for chapter in chapters:
        if any(word in chapter["title"] for word in ("使用说明", "目录", "前言", "导读")):
            continue
        titles = kp_headings(chapter["text"])
        if len(titles) < 2:
            items = extract_keywords(chapter["text"], [chapter["title"]], [], corpus)
            titles = [x["term"] for x in items[:3]]
        if not titles:
            titles = [chapter["title"]]
        seen_titles: set[str] = set()
        for title in titles[:max_per_chapter]:
            key = clean_term(title)
            if not key or key in seen_titles:
                continue
            seen_titles.add(key)
            number = len(kps) + 1
            kp = {
                "id": f"K{number}",
                "title": clean_term(title)[:60],
                "chapter": chapter["id"],
                "keywords": title_terms(title)[:4],
                "anchors": anchor_terms(title),
                "prereq": [kps[-1]["id"]] if kps else [],
                "source": {
                    "file": chapter["source"].get("file", ""),
                    "page": page_for_term(chapter["text"], title) or chapter["source"].get("pageStart"),
                },
                "D": 0.5,
                "examFreq": 0.5,
                "fsrs": {"difficulty": 5.0, "stability": 1.0, "due": "", "lastReview": ""},
                "correctDays": [],
                "mastered": False,
            }
            kps.append(kp)
    return kps


def material_text_sample(docs: Iterable[ExtractedDoc], limit: int = 12000) -> str:
    parts = []
    total = 0
    for doc in docs:
        if doc.status != "ok":
            continue
        chunk = doc.text[:4000]
        parts.append(chunk)
        total += len(chunk)
        if total >= limit:
            break
    return "\n".join(parts)[:limit]


def setup(
    workspace: Path,
    course: str,
    exam_date: date,
    materials: list[Path],
    *,
    daily_minutes: int = 120,
    target_score: int = 90,
    language: str = "zh",
    density: str = "standard",
) -> dict[str, Any]:
    session = Session(workspace)
    state = new_state(
        course, exam_date, daily_minutes=daily_minutes, target_score=target_score,
        language=language, density=density,
    )
    session.state = state
    session.save()

    docs: list[ExtractedDoc] = []
    for source in materials:
        source = Path(source)
        target = session.materials_dir / source.name
        if source.is_file():
            shutil.copy2(source, target)
            docs.append(extract_doc(target, str(target.relative_to(session.workspace)).replace("\\", "/")))
        elif source.is_dir():
            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                rel_name = path.relative_to(source).as_posix()
                target = session.materials_dir / rel_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                docs.append(extract_doc(target, str(target.relative_to(session.workspace)).replace("\\", "/")))

    state["materials"] = [doc.to_dict() for doc in docs]
    usable = [doc for doc in docs if doc.status == "ok" and doc.text.strip()]
    state["materialTextSample"] = [material_text_sample(usable)]
    state["domain"] = detect_domain(material_text_sample(usable), course)

    chapters: list[dict[str, Any]] = []
    for doc in usable:
        if doc.category in {"answers", "syllabus", "keypoints"}:
            continue
        if doc.category == "pastpaper":
            continue
        chapters.extend(split_chapters(doc, start_index=len(chapters) + 1))
    chapters = merge_chapters(chapters)
    if not chapters and usable:
        # last resort: one chapter per usable doc
        for doc in usable:
            chapters.append({
                "id": f"CH{len(chapters) + 1}",
                "title": doc.path.stem,
                "text": doc.text,
                "source": {"file": doc.rel, "pageStart": None},
                "sources": [{"file": doc.rel, "pageStart": None}],
            })
    state["chapters"] = chapters
    seed_question_types(state)
    state["knowledgePoints"] = build_knowledge_points(chapters, state["questionTypes"])
    for chapter in chapters:
        text_path = session.chapters_dir / f"{chapter['id']}.md"
        write_text(text_path, chapter["text"])
        chapter["textFile"] = str(text_path.relative_to(session.workspace)).replace("\\", "/")
        chapter.pop("text", None)

    papers = dedupe_papers(usable)
    state["papers"] = papers
    paper_docs = {doc.rel: doc for doc in usable if doc.category == "pastpaper"}
    answer_docs = [doc for doc in usable if doc.category == "answers"]
    pairs = pair_answers([doc for doc in usable if doc.category == "pastpaper"], answer_docs)

    questions: list[dict[str, Any]] = []
    for paper in papers:
        doc = paper_docs.get(paper["sourceFile"])
        if not doc:
            continue
        extracted = extract_questions(doc, paper["id"], state["questionTypes"])
        answer_doc = pairs.get(doc.rel)
        if answer_doc:
            answer_buckets = extract_answers(answer_doc)
            counters: dict[int, int] = {}
            for question in extracted:
                number = question["number"]
                values = answer_buckets.get(number, [])
                index = counters.get(number, 0)
                if index < len(values):
                    question["officialAnswer"] = values[index]
                    question["answerSource"] = answer_doc.rel
                counters[number] = index + 1
        questions.extend(extracted)

    # dedupe near-identical stems
    kept: list[dict[str, Any]] = []
    for question in questions:
        fingerprint = shingles(question["stem"], 4)
        duplicate = None
        for other in kept:
            if jaccard(fingerprint, shingles(other["stem"], 4)) >= 0.9:
                duplicate = other
                break
        if duplicate:
            question["duplicateOf"] = duplicate["id"]
            continue
        question["kpIds"] = []
        kept.append(question)
    state["questions"] = kept

    # attach questions to KPs by keyword overlap
    for question in state["questions"]:
        hits = []
        for kp in state["knowledgePoints"]:
            if kp["title"] and (kp["title"] in question["stem"] or any(k in question["stem"] for k in kp.get("keywords", []))):
                hits.append(kp["id"])
        question["kpIds"] = hits[:3]

    build_schedule(state, start=date.today())
    session.save()
    write_json(session.workspace / "setup_report.json", {
        "course": course,
        "materials": state["materials"],
        "chapters": len(chapters),
        "papers": len(papers),
        "questions": len(kept),
        "knowledgePoints": len(state["knowledgePoints"]),
        "domain": state["domain"],
        "schedule": {
            "days": len(state["schedule"]["days"]),
            "coveredTypes": state["schedule"].get("coveredTypes", []),
        },
    })
    return state
