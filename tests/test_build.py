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
sys.path.insert(0, str(ROOT / "eval"))
from run_eval import evaluate  # noqa: E402

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
        listed = run("fill", "--workspace", str(workspace), "--tasks", "--json")
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        self.assertIn("tasks", json.loads(listed.stdout))
        listed = run("fill", "--workspace", str(workspace), "--json")
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        self.assertIn("tasks", json.loads(listed.stdout))
        nxt = run("next", "--workspace", str(workspace), "--json")
        self.assertEqual(nxt.returncode, 0, nxt.stdout + nxt.stderr)
        self.assertIn("action", json.loads(nxt.stdout))
        data = json.loads(tasks_path.read_text(encoding="utf-8"))
        payload = {"tasks": {}}
        for task in data.get("tasks", []):
            kind = task["type"]
            kp_ids = (task.get("candidateKps") or [])[:1]
            solution = (
                "1. 先根据题干写出公式并代入已知量。\n"
                "2. 再化简、核对符号与单位，最后给出结论。"
            )
            rubric = [
                {"point": "写出关键公式", "score": 1},
                {"point": "代入并化简", "score": 1},
            ]
            if kind == "kpMap":
                payload["tasks"][task["id"]] = kp_ids
            elif kind == "answer":
                payload["tasks"][task["id"]] = {
                    "solution": solution, "answer": "测试答案", "rubric": rubric,
                }
            elif kind == "rubric":
                payload["tasks"][task["id"]] = rubric
            elif kind == "generate":
                payload["tasks"][task["id"]] = {"question": {
                    "stem": f"模型生成题 {task.get('slotId')}：请写出完整计算过程。",
                    "type": task.get("questionType") or "T1",
                    "kind": task.get("kind") or "basic",
                    "points": task.get("points") or 5,
                    "kpIds": kp_ids,
                    "solution": solution,
                    "rubric": rubric,
                    "answer": "测试答案",
                }}
            elif kind == "main":
                payload["tasks"][task["id"]] = (
                    "主册讲解：先说明定义与适用条件，再给出公式、推导步骤和一个易错点。"
                )
            elif kind == "cheatsheet":
                payload["tasks"][task["id"]] = "速记：先看条件，再套公式，最后核对符号。"
            elif kind == "drill":
                payload["tasks"][task["id"]] = (
                    "解法套路：识别题型信号，写出通式，代入参数，检查边界条件。"
                )
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
        proc = run("audit", "--workspace", str(workspace), "--citations", "--citation-sample", "50")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("citationCoverage: 100.0%", proc.stdout)

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
                evaluation = evaluate(tmp / f"ws-{subject}", subject)
                self.assertTrue(evaluation["ok"], evaluation["problems"])
                self.assertEqual(evaluation["metrics"]["placeholders"], 0)
                self.assertEqual(evaluation["metrics"]["needsGeneration"], 0)
                self.assertEqual(evaluation["metrics"]["citationHitRate"], 1.0)
                self.assertTrue(evaluation["metrics"]["bookIdConsistency"])
                state = json.loads((tmp / f"ws-{subject}" / "study_state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["subject"], subject)
                self.assertEqual(state["days"], 10)
                self.assertTrue(state["quantification"]["matrix"])
                if subject == "math":
                    model = run(
                        "add-question", "--workspace", str(tmp / "ws-math"),
                        "--id", "MODEL-EXTRA-Q1", "--type", "T1", "--kind", "basic",
                        "--stem", "模型补题：写出函数在 x=1 处的导数。",
                        "--answer", "2",
                        "--solution", "1. 写出导数定义并展开。\n2. 代入 x=1，化简得 2。",
                        "--rubric", json.dumps([
                            {"point": "写出定义", "score": 1},
                            {"point": "代入化简", "score": 1},
                        ], ensure_ascii=False),
                        "--source", "model", "--kp", "K1", "--points", "2",
                    )
                    self.assertEqual(model.returncode, 0, model.stdout + model.stderr)
                    state = json.loads((tmp / "ws-math" / "study_state.json").read_text(encoding="utf-8"))
                    added = next(q for q in state["questions"] if q["id"] == "MODEL-EXTRA-Q1")
                    self.assertTrue(added["modelGenerated"])
                    self.assertEqual(added["solutionSource"], "model")
                    self.assertTrue(added["rubric"])
                    self.assertIn("MODEL-EXTRA-Q1", (out / "03-答案册.md").read_text(encoding="utf-8"))

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
