"""Domain anchoring and query construction for Bilibili retrieval."""
from __future__ import annotations

import re
from typing import Any, Iterable

from .util import clean_term

DOMAINS: dict[str, dict[str, Any]] = {
    "cs_systems": {
        "label": "计算机系统",
        "prefix": "计算机系统",
        "keywords": [
            "补码", "原码", "移码", "浮点", "IEEE754", "汇编", "寄存器", "机器码",
            "指令", "栈帧", "链接", "重定位", "虚拟内存", "页表", "缓存", "局部性",
            "异常", "中断", "进程", "系统调用", "x86", "ModRM", "ELF", "操作系统",
            "计算机组成", "体系结构",
        ],
        "negative": [
            "中职英语", "考研英语", "阅读理解", "四级", "六级", "雅思", "托福",
            "ESP32", "单片机", "嵌入式", "前端", "Java", "Python", "机器学习",
            "深度学习", "数据分析", "游戏开发", "装机", "电脑维修", "手机测评",
            "直播", "带货", "vlog", "美食", "舞蹈", "考研政治",
        ],
    },
    "programming_cpp": {
        "label": "C++",
        "prefix": "C++",
        "keywords": [
            "C++", "类", "对象", "继承", "多态", "虚函数", "模板", "STL", "容器",
            "迭代器", "构造函数", "析构函数", "运算符重载", "引用", "指针", "RAII",
            "智能指针", "异常处理", "命名空间", "编译", "链接",
        ],
        "negative": [
            "Java", "Python", "前端", "JavaScript", "Go 语言", "Rust", "C#",
            "中职英语", "考研英语", "四级", "六级", "雅思", "托福", "游戏开发",
            "直播", "带货", "美食", "舞蹈",
        ],
    },
    "programming_python": {
        "label": "Python",
        "prefix": "Python",
        "keywords": ["Python", "列表", "字典", "元组", "装饰器", "生成器", "异常", "模块", "包", "pandas", "numpy"],
        "negative": ["C++", "Java", "前端", "JavaScript", "Go 语言", "Rust", "C#", "中职英语", "考研英语", "直播", "带货"],
    },
    "math": {
        "label": "数学",
        "prefix": "数学",
        "keywords": ["极限", "导数", "积分", "级数", "微分方程", "矩阵", "行列式", "特征值", "概率", "分布", "期望", "方差"],
        "negative": ["考研英语", "四级", "六级", "雅思", "托福", "直播", "带货", "美食", "舞蹈"],
    },
    "economics": {
        "label": "经济学",
        "prefix": "经济学",
        "keywords": ["供给", "需求", "弹性", "边际", "效用", "均衡", "GDP", "通货膨胀", "货币政策", "财政政策", "博弈"],
        "negative": ["考研英语", "四级", "六级", "雅思", "托福", "直播", "带货", "美食", "舞蹈"],
    },
    "law": {
        "label": "法学",
        "prefix": "法学",
        "keywords": ["法条", "构成要件", "违约责任", "侵权", "合同", "刑法", "民法", "诉讼", "管辖", "证据"],
        "negative": ["考研英语", "四级", "六级", "雅思", "托福", "直播", "带货", "美食", "舞蹈"],
    },
    "medicine": {
        "label": "医学",
        "prefix": "医学",
        "keywords": ["解剖", "生理", "病理", "药理", "诊断", "治疗", "症状", "细胞", "感染", "免疫"],
        "negative": ["考研英语", "四级", "六级", "雅思", "托福", "直播", "带货", "美食", "舞蹈"],
    },
    "general": {
        "label": "课程",
        "prefix": "",
        "keywords": [],
        "negative": [
            "中职英语", "考研英语", "阅读理解", "四级", "六级", "雅思", "托福",
            "直播", "带货", "vlog", "美食", "舞蹈", "游戏", "开箱", "手机测评",
        ],
    },
}

GENERIC_NEGATIVE = [
    "中职英语", "考研英语", "阅读理解", "四级", "六级", "雅思", "托福",
    "直播", "带货", "vlog", "美食", "舞蹈", "游戏", "开箱", "手机测评",
    "情感", "搞笑", "综艺", "影视", "动漫",
]


def detect_domain(text: str, course: str = "") -> str:
    haystack = f"{course}\n{text}".lower()
    scores: dict[str, int] = {}
    for key, domain in DOMAINS.items():
        if key == "general":
            continue
        score = 0
        for word in domain["keywords"]:
            if word.lower() in haystack:
                score += 2 if len(word) >= 4 else 1
        if score:
            scores[key] = score
    if not scores:
        return "general"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def domain_of(state: dict[str, Any]) -> str:
    return state.get("domain") or detect_domain(
        "\n".join(state.get("materialTextSample", []) or []),
        state.get("course", ""),
    )


def negative_words(domain: str) -> list[str]:
    words = list(GENERIC_NEGATIVE)
    words.extend(DOMAINS.get(domain, DOMAINS["general"])["negative"])
    return list(dict.fromkeys(words))


def is_off_topic(text: str, domain: str) -> tuple[bool, str]:
    low = (text or "").lower()
    for word in negative_words(domain):
        if word.lower() in low:
            return True, word
    return False, ""


def domain_mismatch(text: str, domain: str) -> bool:
    """A lightweight cross-domain check: reject another language's course."""
    low = (text or "").lower()
    if domain == "programming_cpp":
        return any(x in low for x in ("java ", "python ", "javascript", "go 语言", "rust ", "c#"))
    if domain == "programming_python":
        return any(x in low for x in ("c++", "java ", "javascript", "go 语言", "rust ", "c#"))
    if domain == "cs_systems":
        return any(x in low for x in ("考研英语", "中职英语", "前端", "java ", "python ", "机器学习", "嵌入式"))
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
    info = DOMAINS.get(domain, DOMAINS["general"])
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
