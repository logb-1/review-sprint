from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _installer_command() -> list[str]:
    if os.name == "nt":
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            raise unittest.SkipTest("PowerShell not available")
        return [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(ROOT / "scripts" / "install-skill.ps1")]
    return ["bash", str(ROOT / "scripts" / "install-skill.sh")]


class InstallSkillTest(unittest.TestCase):
    def test_custom_install_resolves_absolute_path_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "skill dir"
            cmd = _installer_command() + ["-Target", "custom", "-Destination", str(dest)]
            if os.name != "nt":
                cmd = _installer_command() + ["custom", str(dest)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            skill = (dest / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: review-sprint", skill)
            self.assertIn("description:", skill)
            self.assertNotIn("$SKILL_DIR", skill)
            self.assertIn(dest.as_posix(), skill)
            self.assertTrue((dest / "COMPATIBILITY.md").is_file())
            self.assertTrue((dest / "requirements-optional.txt").is_file())

            proc = subprocess.run(
                [PY, str(dest / "scripts" / "coach.py"), "--version"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("0.4.6", proc.stdout)

    def test_all_targets_use_expected_directories(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            env = dict(os.environ)
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            cmd = _installer_command() + ["-Target", "all"]
            if os.name != "nt":
                cmd = _installer_command() + ["all"]
            subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)

            expected = [".dsh", ".claude", ".codex", ".cursor"]
            for dot in expected:
                dest = home / dot / "skills" / "review-sprint"
                self.assertTrue((dest / "SKILL.md").is_file(), dest)
                self.assertNotIn("$SKILL_DIR", (dest / "SKILL.md").read_text(encoding="utf-8"))
                self.assertTrue((dest / "COMPATIBILITY.md").is_file())


if __name__ == "__main__":
    unittest.main()
