#!/usr/bin/env python3
"""Build the two examples and assert the expected *draft* state.

`build` intentionally exits 1 while the five books still contain model
placeholders.  This script replaces the old `|| test $? -eq 1` shell idiom,
which also hid real tracebacks: it requires the expected draft artifacts,
then checks `next` and `fill --tasks` agree that generation work is pending.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COACH = ROOT / "scripts" / "coach.py"
CASES = [
    ("math", "高等数学", "examples/subject_math"),
    ("law", "法学基础", "examples/subject_law"),
]


def run(args: list[str], *, expect: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(COACH), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if proc.returncode != expect:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"command returned {proc.returncode}, expected {expect}: {args}")
    return proc


def check_case(subject: str, course: str, materials: str, out_root: Path) -> None:
    workspace = out_root / subject
    if workspace.exists():
        shutil.rmtree(workspace)
    output = workspace / "output"
    run([
        "--workspace", str(workspace), "build",
        "--course", course, "--subject", subject,
        "--materials", materials,
        "--target", "80", "--days", "10",
        "--out", str(output), "--format", "md,docx",
    ], expect=1)
    for name in ("01-复习计划", "02-主册", "03-答案册", "04-速记手册", "05-刷题宝典"):
        assert (output / f"{name}.md").exists(), name
        assert (output / f"{name}.docx").exists(), name
    audit = json.loads(run(["--workspace", str(workspace), "audit", "--json"], expect=1).stdout)
    assert audit["metrics"]["needsGeneration"] > 0, audit
    assert audit["metrics"]["placeholders"] > 0, audit
    nxt = json.loads(run(["--workspace", str(workspace), "next", "--json"]).stdout)
    assert nxt["action"] == "generate", nxt
    tasks = json.loads(
        run(["--workspace", str(workspace), "fill", "--tasks", "--json"]).stdout
    )
    assert any(item["type"] == "generate" for item in tasks["tasks"]), tasks
    print(f"{subject}: draft ok, {len(tasks['tasks'])} fill tasks, "
          f"{audit['metrics']['needsGeneration']} slots pending")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", default="artifacts")
    args = parser.parse_args()
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    for subject, course, materials in CASES:
        check_case(subject, course, materials, out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
