import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unittest

from review_sprint.keywords import extract_keywords, split_headings


class KeywordTest(unittest.TestCase):
    def setUp(self):
        self.text = (
            "第2章 数据的机器级表示。补码是计算机中表示有符号整数的常用方法。"
            "补码运算可以统一加法与减法。IEEE754 标准规定了浮点数的表示。"
            "x86-64 使用 64 位寄存器。溢出是指运算结果超出表示范围。"
        )
        self.corpus = [self.text, "第2章 补码与溢出练习。补码的符号位参与运算。"]

    def test_four_sources(self):
        items = extract_keywords(
            self.text,
            ["第2章 数据的机器级表示", "补码与溢出"],
            ["补码", "IEEE754"],
            self.corpus,
        )
        terms = {x["term"]: x for x in items}
        self.assertIn("IEEE754", terms)
        self.assertIn("补码", terms)
        self.assertIn("acronym", terms["IEEE754"]["sources"])
        self.assertIn("model", terms["补码"]["sources"])

    def test_acronym_survives(self):
        items = extract_keywords(self.text, ["x86-64"], [], self.corpus)
        terms = {x["term"] for x in items}
        self.assertIn("x86-64", terms)

    def test_generic_terms_dropped(self):
        items = extract_keywords("本章主要内容概述。数据表示方法。", ["主要内容"], [], [])
        terms = {x["term"] for x in items}
        self.assertNotIn("主要内容", terms)

    def test_parent_child_filter(self):
        text = "计算机系统 补码 是重点。补码 的运算。"
        items = extract_keywords(text, ["计算机系统 补码"], ["计算机系统 补码", "补码"], [])
        terms = [x["term"] for x in items]
        self.assertIn("计算机系统 补码", terms)
        self.assertNotIn("补码", terms)

    def test_fallback_to_heading(self):
        items = extract_keywords("这一页只有很少的字。", ["补码与溢出"], [], [])
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(any("heading" in source for item in items for source in item["sources"]))

    def test_split_headings(self):
        parts = split_headings(["第2章 数据的机器级表示：补码/溢出"])
        self.assertIn("数据的机器级表示", parts)
        self.assertIn("补码", parts)
        self.assertIn("溢出", parts)


if __name__ == "__main__":
    unittest.main()
