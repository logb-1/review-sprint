import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tempfile
import unittest

from review_sprint.ingest import (
    ExtractedDoc, _clean_text, build_knowledge_points, classify,
    dedupe_papers, extract_answers, extract_doc, extract_questions,
    is_chapter_heading, kp_headings, split_chapters, usable_title,
)


class IngestTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify(Path("考纲.md")), "syllabus")
        self.assertEqual(classify(Path("2024-final.md")), "pastpaper")
        self.assertEqual(classify(Path("2024-final-answers.md")), "answers")
        self.assertEqual(classify(Path("真题_2023-2024-1_A卷_答案.txt")), "answers")
        self.assertEqual(classify(Path("第一章课件.pptx")), "slides")

    def test_clean_text_drops_lone_surrogates(self):
        self.assertEqual(_clean_text("a\ud835b\x00c\x1fd\t\n"), "abcd\t\n")

    def test_usable_title_rejects_page_noise(self):
        self.assertFalse(usable_title("第2页"))
        self.assertFalse(usable_title("HX"))
        self.assertFalse(usable_title("xF"))
        self.assertFalse(usable_title(""))
        self.assertTrue(usable_title("2.1 数列极限的定义"))

    def test_markdown_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chapter.md"
            path.write_text("# 第 2 章 数据\n<!-- page: 12 -->\n## 2.1 补码\n内容\n", encoding="utf-8")
            doc = extract_doc(path, "materials/chapter.md")
            self.assertEqual(doc.category, "slides")
            self.assertIn("【第12页】", doc.text)
            self.assertIn(12, [page for page, _ in doc.pages])

    def test_split_chapters_skips_code_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chapter.md"
            path.write_text(
                "# 第 1 章 概述\n\n开头\n\n" + "y" * 100 + "\n\n```c\n# 这不是章节标题\n```\n\n"
                "# 第 2 章 数据\n\n正文" + "x" * 200 + "\n",
                encoding="utf-8",
            )
            doc = extract_doc(path, "materials/chapter.md")
            chapters = split_chapters(doc)
            self.assertEqual(len(chapters), 2)
            self.assertIn("数据", chapters[1]["title"])

    def test_section_heading_stays_inside_chapter(self):
        self.assertTrue(is_chapter_heading("## 第一章 基本规定"))
        self.assertFalse(is_chapter_heading("## 第一节 一般规定"))

    def test_single_real_heading_does_not_fall_back_to_keywords(self):
        chapters = [{
            "id": "C1",
            "title": "自然人",
            "text": "## 民事权利能力和民事行为能力\n自然人的民事权利能力一律平等。\n" * 4,
            "source": {"file": "law.md", "pageStart": 1},
            "images": [],
        }]
        kps = build_knowledge_points(chapters, [])
        self.assertEqual(len(kps), 1)
        self.assertEqual(kps[0]["title"], "民事权利能力和民事行为能力")

    def test_generic_heading_gets_chapter_prefix(self):
        chapters = [{
            "id": "C1",
            "title": "法人",
            "text": "## 一般规定\n法人应当依法成立。\n" * 4,
            "source": {"file": "law.md", "pageStart": 1},
            "images": [],
        }]
        kps = build_knowledge_points(chapters, [])
        self.assertEqual(kps[0]["title"], "法人·一般规定")

    def test_questions_unique_across_sections(self):
        doc = ExtractedDoc(path=Path("paper.txt"), rel="materials/paper.txt", category="pastpaper")
        doc.text = (
            "一、选择题\n1. 第一题内容\n2. 第二题内容\n"
            "二、计算题\n1. 第三题内容\n2. 第四题内容\n"
        )
        doc.pages = [(None, doc.text)]
        questions = extract_questions(doc, "P1", [])
        ids = [q["id"] for q in questions]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("P1-Q1", ids)
        self.assertIn("P1-Q1-2", ids)

    def test_answer_buckets(self):
        doc = ExtractedDoc(path=Path("answers.txt"), rel="materials/answers.txt", category="answers")
        doc.text = "1. A\n2. B\n1. C\n2. D\n"
        answers = extract_answers(doc)
        self.assertEqual(answers[1], ["A", "C"])
        self.assertEqual(answers[2], ["B", "D"])

    def test_dedupe_papers(self):
        text = "一、选择题\n" + "1. 同一道题 " * 100
        first = ExtractedDoc(path=Path("2023-final.md"), rel="materials/2023-final.md", category="pastpaper")
        first.text = text
        second = ExtractedDoc(path=Path("2024-final.md"), rel="materials/2024-final.md", category="pastpaper")
        second.text = text
        papers = dedupe_papers([first, second])
        self.assertEqual(len(papers), 2)
        self.assertEqual(papers[1]["sameAs"], papers[0]["id"])

    def test_kp_headings(self):
        text = "## 2.1 补码\n### 【一句话是什么】\n内容\n## 2.2 浮点\n### 【规则/公式/步骤】\n内容\n"
        titles = kp_headings(text)
        self.assertEqual(titles, ["补码", "浮点"])

    def test_docx_and_pptx(self):
        with tempfile.TemporaryDirectory() as tmp:
            import docx

            docx_path = Path(tmp) / "讲义.docx"
            document = docx.Document()
            document.add_heading("第 1 章 概述", level=1)
            document.add_paragraph("这是正文，包含补码。" * 20)
            formula = docx.oxml.parse_xml(
                f'<m:oMathPara {docx.oxml.ns.nsdecls("m")}>'
                '<m:oMath><m:r><m:t>x^2 + 1</m:t></m:r></m:oMath>'
                '</m:oMathPara>'
            )
            document.add_paragraph("公式：")._p.append(formula)
            document.save(docx_path)
            doc = extract_doc(docx_path, "materials/讲义.docx")
            self.assertEqual(doc.status, "ok")
            self.assertGreater(doc.chars, 20)
            self.assertIn("x^2 + 1", doc.text)

            from pptx import Presentation

            pptx_path = Path(tmp) / "课件.pptx"
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = "第 1 章 概述"
            slide.placeholders[1].text = "补码与溢出"
            prs.save(pptx_path)
            deck = extract_doc(pptx_path, "materials/课件.pptx")
            self.assertEqual(deck.status, "ok")
            self.assertIn("补码与溢出", deck.text)


if __name__ == "__main__":
    unittest.main()
