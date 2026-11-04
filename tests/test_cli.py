import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import subprocess
import tempfile
import unittest
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
COACH = ROOT / "scripts" / "coach.py"
DEMO = ROOT / "examples" / "demo_csapp"


def run(*args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(COACH), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


class CliTest(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            exam = date.today() + timedelta(days=19)
            proc = run(
                "--workspace", str(workspace), "init",
                "--course", "计算机系统基础",
                "--exam-date", exam.isoformat(),
                "--materials", str(DEMO),
                "--daily-minutes", "120",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((workspace / "study_state.json").exists())

            proc = run("status", "--workspace", str(workspace))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("📍", proc.stdout)

            proc = run("plan", "--workspace", str(workspace))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("复习排期", proc.stdout)

            proc = run("today", "--workspace", str(workspace), "--day", "2")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("今日知识点", proc.stdout)
            self.assertIn("题型专练", proc.stdout)
            self.assertIn("原文", proc.stdout)

            proc = run("answer", "--workspace", str(workspace), "--qid", "P1-Q1",
                       "--result", "wrong", "--confidence", "3", "--cause", "concept")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("答错", proc.stdout)

            proc = run("audit", "--workspace", str(workspace))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            proc = run("export", "--workspace", str(workspace), "--format", "md,ics,anki")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(list((workspace / "exports").glob("*.ics")))
            self.assertTrue(list((workspace / "exports").glob("*.csv")))

            proc = run("calc", "--kind", "twos", "--value", "-5", "--bits", "8")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("0xFB", proc.stdout)


if __name__ == "__main__":
    unittest.main()
