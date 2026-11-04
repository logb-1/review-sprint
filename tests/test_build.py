import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import json
import shutil
import subprocess
import tempfile
import unittest

from review_sprint.books import book_question_ids

ROOT = Path(__file__).resolve().parents[1]
COACH = ROOT / "scripts" / "coach.py"
EXAMPLES = ROOT / "examples"


def run(*args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(COACH), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


class BuildTest(unittest.TestCase):
    def _build(self, subject, source, auto=False):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        workspace = tmp / f"ws-{subject}"
        out = tmp / "output"
        args = [
            "--workspace", str(workspace), "build",
            "--course", "高等数学" if subject == "math" else "法学基础",
            "--materials", str(EXAMPLES / source),
            "--target", "80", "--days", "10", "--daily-minutes", "120",
            "--out", str(out), "--format", "md,docx",
        ]
        if not auto:
            args += ["--subject", subject]
        proc = run(*args)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return tmp, out, proc

    def test_two_subjects_five_books_md_docx(self):
        for subject, source, auto in (("math", "subject_math", True), ("law", "subject_law", False)):
            with self.subTest(subject=subject):
                tmp, out, proc = self._build(subject, source, auto=auto)
                self.assertIn("五册已生成", proc.stdout)
                names = [f"{i:02d}-{name}" for i, name in enumerate(
                    ["复习计划", "主册", "答案册", "速记手册", "刷题宝典"], start=1)]
                for stem in names:
                    md = out / f"{stem}.md"
                    docx_path = out / f"{stem}.docx"
                    self.assertTrue(md.exists(), md)
                    self.assertTrue(docx_path.exists(), docx_path)
                    self.assertGreater(md.stat().st_size, 100)
                    self.assertGreater(docx_path.stat().st_size, 1000)
                    import docx as docx_mod
                    document = docx_mod.Document(str(docx_path))
                    self.assertTrue(document.paragraphs)
                self.assertEqual(len(list(out.glob("*.md"))), 6)  # five + audit report
                self.assertEqual(len(list(out.glob("*.docx"))), 5)
                sets = book_question_ids(out)
                self.assertEqual(set(sets), {"main", "answers", "drill"})
                self.assertTrue(sets["main"])
                self.assertEqual(sets["main"], sets["answers"])
                self.assertEqual(sets["main"], sets["drill"])
                self.assertIn("结果：✅ 通过", (out / "质检报告.md").read_text(encoding="utf-8"))
                state = json.loads((tmp / f"ws-{subject}" / "study_state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["subject"], subject)
                self.assertEqual(state["days"], 10)
                self.assertTrue(state["quantification"]["matrix"])

    def test_missing_target_and_days_returns_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(
                "--workspace", str(Path(tmp) / "ws"), "build",
                "--course", "高等数学",
                "--materials", str(EXAMPLES / "subject_math"),
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("需要先询问", proc.stdout)
            self.assertIn("--target", proc.stdout)
            self.assertIn("--days", proc.stdout)

    def test_low_confidence_subject_needs_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            material = Path(tmp) / "课程说明.md"
            material.write_text("# 课程说明\n\n考试 复习 重点 知识点。\n", encoding="utf-8")
            proc = run(
                "--workspace", str(Path(tmp) / "ws"), "build",
                "--course", "某课程", "--materials", str(material),
                "--target", "80", "--days", "5",
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("科目识别", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
