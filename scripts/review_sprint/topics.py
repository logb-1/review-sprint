"""Subject-aware anchoring and query construction for Bilibili retrieval.

Profiles live in ``references/subjects/*.json``; this module only adapts them
for retrieval.  Keeping no per-subject keyword list here is intentional: adding
a subject must be a data-only change.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .subjects import ALIASES, detect_subject, get_profile, profiles
from .util import clean_term

GENERIC_NEGATIVE = [
    "中职英语", "考研英语", "阅读理解", "四级", "六级", "雅思", "托福",
    "直播", "带货", "vlog", "美食", "舞蹈", "游戏", "开箱", "手机测评",
    "情感", "搞笑", "综艺", "影视", "动漫",
]


def _domain_map() -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    for name, profile in profiles().items():
        data[name] = {
            "label": profile.get("label", name),
            "prefix": profile.get("biliPrefix", ""),
            "keywords": list(profile.get("keywords", [])),
            "negative": list(profile.get("negative", [])),
        }
    # compatibility aliases used by older workspaces / callers
    for alias, target in ALIASES.items():
        if target in data and alias not in data:
            data[alias] = dict(data[target])
    return data


DOMAINS = _domain_map()


def detect_domain(text: str, course: str = "") -> str:
    return detect_subject(text, course)["subject"]


def domain_of(state: dict[str, Any]) -> str:
    return state.get("subject") or state.get("domain") or detect_subject(
        "\n".join(state.get("materialTextSample", []) or []),
        state.get("course", ""),
    )["subject"]


def negative_words(domain: str) -> list[str]:
    profile = get_profile(ALIASES.get(domain, domain))
    words = list(GENERIC_NEGATIVE)
    words.extend(profile.get("negative", []))
    return list(dict.fromkeys(words))


def is_off_topic(text: str, domain: str) -> tuple[bool, str]:
    low = (text or "").lower()
    for word in negative_words(domain):
        if word.lower() in low:
            return True, word
    return False, ""


def domain_mismatch(text: str, domain: str) -> bool:
    """Reject another subject's obvious vocabulary when it is in the negative list."""
    low = (text or "").lower()
    profile = get_profile(ALIASES.get(domain, domain))
    for word in profile.get("negative", []):
        if len(word) >= 4 and word.lower() in low:
            return True
    return False


def anchors_for(kp: dict[str, Any], keywords: Iterable[str] | None = None, limit: int = 2) -> list[str]:
    candidates: list[str] = []
    for value in kp.get("anchors", []) or []:
        candidates.append(clean_term(value))
    candidates.append(clean_term(kp.get("title", "")))
    for value in keywords or []:
        candidates.append(clean_term(value))
    candidates.extend(clean_term(x) for x in kp.get("keywords", []) or [])

    out: list[str] = []
    seen: set[str] = set()
    for term in candidates:
        if not term or len(term) < 2:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= limit:
            break
    return out


def build_queries(anchors: list[str], domain: str, course: str = "") -> list[str]:
    profile = get_profile(ALIASES.get(domain, domain))
    info = {
        "prefix": profile.get("biliPrefix", ""),
        "label": profile.get("label", ""),
    }
    queries: list[str] = []
    if anchors:
        queries.append(" ".join(anchors[:2]))
        if len(anchors) >= 2:
            queries.append(f"{anchors[0]} {anchors[1]}")
    if info.get("prefix") and anchors:
        queries.append(f"{info['prefix']} {anchors[0]}")
    if course and anchors:
        queries.append(f"{course} {anchors[0]}")
    if not queries:
        queries.append(course or "课程")
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))


def contains_anchor(text: str, anchor: str) -> bool:
    return anchor.lower() in (text or "").lower()


def anchor_coverage(text: str, anchors: list[str]) -> float:
    """Primary anchor is mandatory-ish (0.65); remaining anchors share 0.35."""
    if not anchors:
        return 0.0
    if len(anchors) == 1:
        return 1.0 if contains_anchor(text, anchors[0]) else 0.0
    primary = 1.0 if contains_anchor(text, anchors[0]) else 0.0
    rest = sum(1 for a in anchors[1:] if contains_anchor(text, a)) / max(1, len(anchors) - 1)
    return 0.65 * primary + 0.35 * rest
