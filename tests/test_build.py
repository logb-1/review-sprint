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
    def _fill_and_audit(self, workspace: Path, out: Path):
        tasks_path = out / "_build" / "fill_tasks.json"
        self.assertTrue(tasks_path.exists(), tasks_path)
        data = json.loads(tasks_path.read_text(encoding="utf-8"))
        payload = {"tasks": {}}
        for task in data.get("tasks", []):
            if task["type"] == "kpMap":
                payload["tasks"][task["id"]] = (task.get("candidateKps") or [])[:1]
            else:
                payload["tasks"][task["id"]] = "测试回填：" + task["id"]
        answer_path = workspace / "fill_test.json"
        answer_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        proc = run("fill", "--workspace", str(workspace), "--apply", str(answer_path))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run("audit", "--workspace", str(workspace))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("placeholders: 0", proc.stdout)
        self.assertIn("answerCoverage: 100.0%", proc.stdout)

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
        self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
        audit = run("audit", "--workspace", str(workspace))
        self.assertEqual(audit.returncode, 1, audit.stdout + audit.stderr)
        self.assertIn("待模型填充", audit.stdout)
        self._fill_and_audit(workspace, out)
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

    def test_missing_target_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(
                "--workspace", str(Path(tmp) / "ws"), "build", "--json",
                "--course", "高等数学", "--materials", str(EXAMPLES / "subject_math"),
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["needsInput"], ["target", "days"])

    def test_same_name_materials_get_distinct_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            b = Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            (a / "课件.md").write_text("# 数学\n极限 导数 积分\n", encoding="utf-8")
            (b / "课件.md").write_text("# 数学\n矩阵 行列式 概率\n", encoding="utf-8")
            proc = run(
                "--workspace", str(Path(tmp) / "ws"), "init",
                "--course", "高等数学", "--subject", "math", "--days", "5",
                "--materials", str(a), str(b),
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            state = json.loads((Path(tmp) / "ws" / "study_state.json").read_text(encoding="utf-8"))
            rels = [m["rel"] for m in state["materials"]]
            self.assertEqual(len(rels), 2)
            self.assertEqual(len(set(rels)), 2)

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

    def test_force_backs_up_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            proc = run(
                "--workspace", str(workspace), "init",
                "--course", "高等数学", "--subject", "math", "--days", "5",
                "--materials", str(EXAMPLES / "subject_math"), "--target", "80",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            proc = run(
                "--workspace", str(workspace), "build",
                "--course", "高等数学", "--subject", "math",
                "--materials", str(EXAMPLES / "subject_math"),
                "--target", "80", "--days", "5", "--force", "--format", "md",
            )
            self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
            self.assertTrue(list(workspace.glob("study_state.*.bak.json")))

    def test_refresh_materials_keeps_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            proc = run(
                "--workspace", str(workspace), "init",
                "--course", "高等数学", "--subject", "math", "--days", "10",
                "--materials", str(EXAMPLES / "subject_math"), "--target", "80",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            proc = run("answer", "--workspace", str(workspace), "--qid", "P1-Q1",
                       "--result", "wrong", "--confidence", "3", "--cause", "concept")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            proc = run(
                "--workspace", str(workspace), "build",
                "--course", "高等数学", "--subject", "math",
                "--materials", str(EXAMPLES / "subject_math"),
                "--target", "80", "--days", "10", "--format", "md",
            )
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertIn("refresh-materials", proc.stdout + proc.stderr)
            proc = run(
                "--workspace", str(workspace), "build",
                "--course", "高等数学", "--subject", "math",
                "--materials", str(EXAMPLES / "subject_math"),
                "--target", "80", "--days", "10", "--refresh-materials",
                "--format", "md",
            )
            self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
            state = json.loads((workspace / "study_state.json").read_text(encoding="utf-8"))
            self.assertTrue(any(a.get("questionId") == "P1-Q1" for a in state["attempts"]))
            self.assertTrue(any(kp.get("fsrs", {}).get("due") for kp in state["knowledgePoints"]))
            out = workspace / "output"
            self.assertTrue(list(out.glob("*.md")))
            self.assertFalse(list(out.glob("*.docx")))


if __name__ == "__main__":
    unittest.main()
