"""Four-source keyword fusion (model / acronym / heading / corpus TF-IDF).

Ported from the rules validated in dsh-course-assistant 1.10.0:
- weights: model 3, acronym 2.6, heading 2.5, corpus 2 (+0.3 cross-chapter)
- generic-word blacklist, numbering stripped
- parent/child terms are mutually exclusive
- each non-model source contributes at most 2 terms
- fewer than 2 survivors -> fall back to headings
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from .util import (
    CJK_RE, EN_RE, GENERIC_TERMS, STOPWORDS_EN, clean_term, normalize_for_match,
)

FUNCTION_PREFIX = (
    "的", "了", "是", "在", "和", "与", "及", "或", "为", "对", "从", "到", "由",
    "把", "被", "将", "就", "都", "也", "很", "更", "最", "又", "还", "并", "而",
    "所以", "因为", "如果", "虽然", "但是", "可以", "能够", "进行", "通过", "以及",
    "我们", "你们", "他们", "这个", "那个", "一个", "这些", "那些", "其中", "因此",
    "然后", "同时", "例如", "比如", "就是", "不是", "没有", "需要", "使用",
)
FUNCTION_SUFFIX = (
    "的", "了", "是", "在", "和", "与", "及", "或", "为", "对", "从", "到", "由",
    "中", "上", "下", "时", "后", "前", "等", "者", "所", "把", "被", "将", "就",
    "都", "也", "很", "更", "最", "又", "还", "并", "而", "且", "所以", "因为",
    "如果", "虽然", "但是", "可以", "能够", "进行", "通过", "以及", "我们", "你们",
    "他们", "这个", "那个", "一个", "这些", "那些", "其中", "因此", "然后", "同时",
)
GENERIC_EXTRA = {
    "计算机系统", "计算机", "系统", "程序", "数据", "表示", "处理", "方法", "问题",
    "主要内容", "基本概念", "概述", "本章", "本节", "课程", "考试", "复习",
    "知识点", "重点难点", "课堂", "老师", "同学", "内容", "部分", "结构",
}
GLOSSARY_CS = {
    "补码", "原码", "反码", "移码", "无符号数", "有符号数", "溢出", "截断",
    "字节序", "大端", "小端", "对齐", "填充", "浮点数", "规格化", "阶码", "尾数",
    "舍入", "标志位", "条件码", "寄存器", "栈帧", "返回地址", "调用约定",
    "链接", "重定位", "符号表", "静态链接", "动态链接", "共享库", "地址空间",
    "虚拟内存", "页表", "缺页", "异常", "中断", "信号", "系统调用", "进程",
    "上下文切换", "指令流水线", "存储层次", "缓存", "局部性", "命中率", "CPI",
    "IEEE754", "x86-64", "ModRM", "SIB", "REX", "ELF", "PLT", "GOT", "TLB",
    "MMU", "DMA", "ALU", "CPU", "ISA", "RISC", "CISC", "ASCII", "UTF-8", "GBK",
}


def _is_generic(term: str) -> bool:
    key = clean_term(term)
    if not key:
        return True
    if key in GENERIC_TERMS or key in GENERIC_EXTRA:
        return True
    if len(key) == 1 and CJK_RE.search(key):
        return True
    if re.fullmatch(r"[\d\W_]+", key):
        return True
    return False


def _boundary_ok(term: str) -> bool:
    if not term:
        return False
    if any(term.startswith(p) for p in FUNCTION_PREFIX):
        return False
    if any(term.endswith(s) for s in FUNCTION_SUFFIX):
        return False
    non_cjk = re.sub(r"[\u4e00-\u9fff\s]", "", term)
    if non_cjk and not re.search(r"[A-Za-z0-9]", non_cjk):
        return False
    return True


def split_headings(headings: Iterable[str]) -> list[str]:
    out: list[str] = []
    for heading in headings:
        text = re.sub(r"^\s*第\s*[\d一二三四五六七八九十]+\s*[章节部分讲单元]\s*", "", str(heading))
        for part in re.split(r"[\s：:、，,/|｜·\-—]+", text):
            part = clean_term(part)
            if part and not _is_generic(part) and 2 <= len(part) <= 24:
                out.append(part)
    return out


def extract_acronyms(text: str, glossary: set[str] | None = None) -> list[str]:
    glossary = glossary or GLOSSARY_CS
    counts: Counter[str] = Counter()
    for match in EN_RE.finditer(text or ""):
        token = match.group(0).strip("._/-")
        if len(token) < 2 or len(token) > 24:
            continue
        low = token.lower()
        if low in STOPWORDS_EN:
            continue
        has_upper = any(ch.isupper() for ch in token)
        has_digit = any(ch.isdigit() for ch in token)
        known = token in glossary or low in {g.lower() for g in glossary}
        if not (has_upper or has_digit or known):
            continue
        counts[token] += 1
    return [tok for tok, n in counts.most_common(24) if n >= 1]


def _chinese_runs(text: str) -> list[str]:
    runs = re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
    return runs


def chinese_candidates(text: str, glossary: set[str] | None = None) -> list[tuple[str, int]]:
    glossary = glossary or GLOSSARY_CS
    counts: Counter[str] = Counter()
    for run in _chinese_runs(text):
        run_len = len(run)
        max_n = min(6, run_len)
        for n in range(2, max_n + 1):
            for i in range(0, run_len - n + 1):
                term = run[i:i + n]
                if _is_generic(term) or not _boundary_ok(term):
                    continue
                # very common function-word pairs
                if term in {"这个", "那个", "一个", "我们", "你们", "他们", "可以", "因为", "所以"}:
                    continue
                counts[term] += 1
    scored: list[tuple[str, int]] = []
    for term, count in counts.items():
        if count < 2 and term not in glossary:
            continue
        if len(term) <= 2 and count < 3 and term not in glossary:
            continue
        scored.append((term, count))
    scored.sort(key=lambda x: (x[1] * (1.0 + 0.15 * min(len(x[0]), 6)), len(x[0])), reverse=True)
    return scored[:60]


def tfidf_terms(chapter_text: str, corpus_texts: list[str], glossary: set[str] | None = None) -> list[tuple[str, float]]:
    glossary = glossary or GLOSSARY_CS
    candidates = chinese_candidates(chapter_text, glossary)
    # acronyms also participate in corpus TF-IDF
    for token in extract_acronyms(chapter_text, glossary):
        candidates.append((token, chapter_text.count(token)))
    if not candidates:
        return []
    total_chars = max(1, len(re.findall(r"\S", chapter_text)))
    n_docs = max(1, len(corpus_texts) + 1)
    scored: list[tuple[str, float]] = []
    for term, count in candidates:
        df = 1 + sum(1 for doc in corpus_texts if term in doc)
        idf = math.log((n_docs + 1) / (df + 1)) + 1.0
        tf = count / total_chars * 1000.0
        score = tf * idf
        if df > 1:
            score *= 1.15
        scored.append((term, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:40]


def _source_terms(terms: list[tuple[str, float]], limit: int = 2) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for term, score in terms:
        key = normalize_for_match(term)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((term, score))
        if len(out) >= limit:
            break
    return out


def _parent_child_filter(items: list[dict]) -> list[dict]:
    """Drop a term when a higher-ranked selected term contains it (or vice versa)."""
    ordered = sorted(items, key=lambda x: (x["score"], len(x["term"])), reverse=True)
    kept: list[dict] = []
    for item in ordered:
        term = normalize_for_match(item["term"])
        conflict = None
        for other in kept:
            other_term = normalize_for_match(other["term"])
            if term == other_term:
                conflict = other
                break
            if term and other_term and (term in other_term or other_term in term):
                conflict = other
                break
        if conflict is None:
            kept.append(item)
        elif len(term) > len(normalize_for_match(conflict["term"])) and item["score"] >= conflict["score"]:
            kept.remove(conflict)
            kept.append(item)
    return kept


def extract_keywords(
    chapter_text: str,
    headings: Iterable[str] | None = None,
    model_keywords: Iterable[str] | None = None,
    corpus_texts: list[str] | None = None,
    glossary: set[str] | None = None,
    max_terms: int = 8,
) -> list[dict]:
    """Return [{term, score, sources}] with source-level explainability."""
    glossary = glossary or GLOSSARY_CS
    corpus_texts = corpus_texts or []
    terms: dict[str, dict] = {}

    def add(term: str, score: float, source: str) -> None:
        term = clean_term(term)
        if not term or _is_generic(term):
            return
        if not _boundary_ok(term) and source != "acronym":
            return
        key = normalize_for_match(term)
        if not key:
            return
        # corpus/heading/acronym must actually occur in the chapter
        if source in {"heading", "acronym", "corpus"} and term not in chapter_text:
            # allow acronym case-insensitive
            if source == "acronym" and term.lower() not in chapter_text.lower():
                return
            if source != "acronym":
                return
        entry = terms.setdefault(key, {"term": term, "score": 0.0, "sources": []})
        if source not in entry["sources"]:
            entry["sources"].append(source)
        entry["score"] = max(entry["score"], score)

    # source 1: model (no per-source cap)
    model_terms = [clean_term(x) for x in (model_keywords or []) if clean_term(x)]
    for term in model_terms[:8]:
        if term in chapter_text or term.lower() in chapter_text.lower():
            add(term, 3.0, "model")

    # source 2: acronyms (bypass length filter; up to 2)
    acronyms = extract_acronyms(chapter_text, glossary)
    glossary_lower = {g.lower() for g in glossary}
    acronyms.sort(key=lambda t: (t.lower() in glossary_lower, chapter_text.count(t)), reverse=True)
    for term, _count in _source_terms([(t, 1.0) for t in acronyms], limit=2):
        add(term, 2.6, "acronym")

    # source 3: headings (up to 2)
    heading_terms = split_headings(headings or [])
    for term in heading_terms[:2]:
        add(term, 2.5, "heading")

    # source 4: corpus TF-IDF (up to 2)
    corpus_terms = tfidf_terms(chapter_text, corpus_texts, glossary)
    max_corpus = max((s for _, s in corpus_terms), default=1.0) or 1.0
    ranked: list[tuple[str, float]] = []
    for term, score in corpus_terms:
        df = 1 + sum(1 for doc in corpus_texts if term in doc)
        bonus = 0.3 if df > 1 else 0.0
        ranked.append((term, 2.0 * (0.6 + 0.4 * score / max_corpus) + bonus))
    for term, score in _source_terms(ranked, limit=2):
        add(term, score, "corpus")

    items = _parent_child_filter(list(terms.values()))
    items.sort(key=lambda x: (x["score"], len(x["term"])), reverse=True)
    items = items[:max_terms]

    # fallback: at least two terms from headings
    if len(items) < 2:
        existing = {normalize_for_match(x["term"]) for x in items}
        for term in heading_terms:
            key = normalize_for_match(term)
            if not key or key in existing:
                continue
            if any(key in other or other in key for other in existing):
                continue
            items.append({"term": term, "score": 2.0, "sources": ["heading-fallback"]})
            existing.add(key)
            if len(items) >= 2:
                break
    return items


def describe(items: list[dict]) -> str:
    lines = []
    for item in items:
        lines.append(f"{item['term']}\t{item['score']:.2f}\t{','.join(item['sources'])}")
    return "\n".join(lines)
