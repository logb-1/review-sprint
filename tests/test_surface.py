import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COACH = ROOT / "scripts" / "coach.py"
COMMANDS = [
    "init", "status", "next", "catch-up", "sync", "fill", "build", "plan", "today",
    "day", "done", "answer", "review", "quiz", "keywords", "bilibili", "calc", "recompute",
    "resolve-conflict", "weights", "reclassify", "types", "subjects", "set-check",
    "audit", "export", "figure", "doctor", "set", "add-question", "sources", "report",
]


class SurfaceTest(unittest.TestCase):
    def _help(self, *args: str) -> str:
        proc = subprocess.run(
            [sys.executable, str(COACH), *args, "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_every_documented_command_has_help(self):
        for command in COMMANDS:
            with self.subTest(command=command):
                self._help(command)

    def test_documented_flags_exist(self):
        self.assertIn("--tasks", self._help("fill"))
        self.assertIn("--citations", self._help("audit"))
        self.assertIn("--source", self._help("add-question"))
        self.assertIn("--slot", self._help("add-question"))
        self.assertIn("--page", self._help("figure"))
        self.assertIn("--seconds", self._help("answer"))


if __name__ == "__main__":
    unittest.main()
