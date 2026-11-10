"""Markdown -> DOCX writer for the five book deliverables."""
from __future__ import annotations

import re
from pathlib import Path

_XML_BAD_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xml_safe(text: str) -> str:
    """Drop control characters that python-docx/Word cannot serialize."""
    return _XML_BAD_RE.sub("", text or "")


class DocxDependencyError(RuntimeError):
    pass


def _docx():
    try:
        import docx  # type: ignore
        from docx.shared import Pt  # type: ignore
        return docx, Pt
    except Exception as exc:  # pragma: no cover - environment dependent
        raise DocxDependencyError(
            "生成 DOCX 需要 python-docx；请运行: pip install python-docx"
        ) from exc


def _add_toc(document) -> None:
    """Insert a Word TOC field; Word/WPS updates page numbers on open/F9."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    document.add_heading("目录", level=1)
    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "打开 Word 后按 F9 更新目录页码"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(separate)
    run._r.append(text)
    run._r.append(end)
    document.add_page_break()


def _add_page_number(document) -> None:
    """Put a PAGE field in the footer so printed books keep page numbers."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    footer = document.sections[0].footer.paragraphs[0]
    footer.alignment = 1
    footer.add_run("第 ")
    run = footer.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    footer.add_run(" 页")


def _add_inline(paragraph, text: str, document, base_dir: Path) -> None:
    """Render **bold**, *italic*, `code`, and ![alt](image) without leaking markers."""
    from docx.shared import Inches

    token_re = re.compile(r"(!\[[^\]]*\]\([^)]+\)|\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")
    for token in token_re.split(text):
        if not token:
            continue
        if token.startswith("!["):
            match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", token)
            if not match:
                paragraph.add_run(token)
                continue
            source = match.group(2).strip().strip("<>")
            image = Path(source)
            if not image.is_absolute():
                image = base_dir / source
            if image.exists():
                document.add_picture(str(image), width=Inches(5.5))
            else:
                paragraph.add_run(match.group(1) or source)
        elif token.startswith("**") and token.endswith("**"):
            paragraph.add_run(token[2:-2]).bold = True
        elif token.startswith("*") and token.endswith("*"):
            paragraph.add_run(token[1:-1]).italic = True
        elif token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
        else:
            paragraph.add_run(token)


def markdown_to_docx(markdown: str, path: Path, title: str | None = None,
                     base_dir: Path | None = None) -> Path:
    markdown = _xml_safe(markdown)
    title = _xml_safe(title) if title else None
    docx, Pt = _docx()
    document = docx.Document()
    base_dir = Path(base_dir or path.parent)
    if title:
        document.core_properties.title = title
        document.add_heading(title, level=0)
        _add_toc(document)
    _add_page_number(document)
    style = document.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(10.5)

    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            i += 1
            continue
        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            p = document.add_paragraph("\n".join(code_lines))
            p.style = document.styles["No Spacing"]
            for run in p.runs:
                run.font.name = "Consolas"
            i += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(cell) <= set("-: ") for cell in row):
                    rows.append(row)
                i += 1
            if rows:
                table = document.add_table(rows=len(rows), cols=max(len(r) for r in rows))
                table.style = "Table Grid"
                for r, row in enumerate(rows):
                    for c, value in enumerate(row):
                        cell = table.cell(r, c)
                        cell.text = ""
                        _add_inline(cell.paragraphs[0], value, document, base_dir)
            continue
        heading = None
        for level in (1, 2, 3, 4):
            prefix = "#" * level + " "
            if stripped.startswith(prefix):
                heading = (level, stripped[len(prefix):].strip())
                break
        if heading:
            if heading[0] == 2:
                document.add_page_break()
            paragraph = document.add_heading("", level=min(4, heading[0]))
            _add_inline(paragraph, heading[1], document, base_dir)
            i += 1
            continue
        if stripped.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            _add_inline(paragraph, stripped[2:], document, base_dir)
            i += 1
            continue
        if stripped[0:3].isdigit() and ". " in stripped[:5]:
            paragraph = document.add_paragraph(style="List Number")
            _add_inline(paragraph, stripped, document, base_dir)
            i += 1
            continue
        paragraph = document.add_paragraph()
        _add_inline(paragraph, stripped, document, base_dir)
        i += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    return path


def convert_markdown_files(md_paths: list[Path], out_dir: Path) -> list[Path]:
    written = []
    for src in md_paths:
        dst = out_dir / (src.stem + ".docx")
        markdown_to_docx(src.read_text(encoding="utf-8"), dst, title=src.stem, base_dir=src.parent)
        written.append(dst)
    return written
