"""Shared helpers for review-sprint (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "review-sprint/state@3"

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
EN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#._/-]{1,}")
WS_RE = re.compile(r"[ \t\u3000]+")
SENT_SPLIT_RE = re.compile(r"(?<=[。！？；!?;])\s*|\n+")
NUMBERING_RE = re.compile(
    r"^\s*(?:第\s*)?(?:\d{1,3}|[一二三四五六七八九十]{1,3})\s*(?:章|节|部分|讲|单元)?\s*[、.．:：)）]?\s*"
)
GENERIC_TERMS = {
    "主要内容", "概述", "简介", "引言", "前言", "目录", "小结", "总结", "复习",
    "知识点", "重点", "难点", "考点", "例题", "习题", "练习", "作业", "课件",
    "数据", "表示", "处理", "方法", "问题", "系统", "结构", "过程", "分析",
    "设计", "实现", "原理", "基础", "概念", "定义", "性质", "特点", "应用",
    "计算机", "程序", "内容", "部分", "章节", "课程", "学习", "考试", "题目",
}
STOPWORDS_EN = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "these",
    "those", "as", "at", "by", "from", "we", "you", "they", "can", "will",
    "not", "no", "yes", "if", "then", "than", "so", "such", "into", "about",
    "chapter", "section", "lecture", "slide", "page", "example", "figure",
}


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def today() -> date:
    return date.today()


def parse_date(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return date.today()
    return date.fromisoformat(str(value)[:10])


def days_between(start: date, end: date) -> int:
    return (end - start).days


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "ignore")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def slugify(text: str, max_len: int = 48) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text, flags=re.UNICODE).strip("-")
    return (text or "item")[:max_len]


def strip_html(text: str) -> str:
    import html

    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text)


def clean_term(term: str) -> str:
    term = unicodedata.normalize("NFKC", term or "").strip()
    term = term.strip(" \t\r\n,，.。;；:：、!?！？()（）[]【】<>《》\"'“”‘’")
    term = re.sub(r"^[\d一二三四五六七八九十]+[、.．)）]\s*", "", term)
    term = re.sub(r"\s+", " ", term)
    return term.strip()


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff+#.-]", "", text)
    return text


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT_RE.split(text or "") if s.strip()]


def shingles(text: str, size: int = 3) -> set[str]:
    norm = normalize_for_match(text)
    if len(norm) <= size:
        return {norm} if norm else set()
    return {norm[i:i + size] for i in range(len(norm) - size + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def human_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} 分钟"
    h, m = divmod(minutes, 60)
    return f"{h} 小时" + (f" {m} 分钟" if m else "")


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in re.split(r"[,，;；]", value) if x.strip()]


def unique(seq: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    out = []
    for item in seq:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
