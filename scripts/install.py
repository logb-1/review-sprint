#!/usr/bin/env python3
"""One-click installer for the portable review-sprint skill.

The Python part owns platform detection, dependency checks and verification.
The actual copy is delegated to the existing install-skill.ps1/.sh scripts so
there is only one implementation of the destination layout.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_NAMES = ("dsh", "claude", "codex", "cursor")

# directory under $HOME and executable used for auto-detection
DETECT = {
    "dsh": (".dsh", "dsh"),
    "claude": (".claude", "claude"),
    "codex": (".codex", "codex"),
    "cursor": (".cursor", "cursor"),
}
OPTIONAL_IMPORTS = (
    ("pypdf", "pypdf"),
    ("docx", "python-docx"),
    ("pptx", "python-pptx"),
)


def target_dir(name: str) -> Path:
    return Path.home() / f".{name}" / "skills" / "review-sprint"


def detected_targets() -> list[str]:
    found: list[str] = []
    home = Path.home()
    for name in TARGET_NAMES:
        dotdir, executable = DETECT[name]
        if (home / dotdir).exists() or shutil.which(executable):
            found.append(name)
    return found


def ask_yes(prompt: str, default: bool = True) -> bool:
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in {"y", "yes"}


def missing_optional() -> list[str]:
    missing: list[str] = []
    for module, package in OPTIONAL_IMPORTS:
        if importlib.util.find_spec(module) is None:
            missing.append(package)
    return missing


def install_dependencies(no_deps: bool, yes: bool) -> bool:
    missing = missing_optional()
    if not missing:
        print("Optional Python dependencies already installed.")
        return True
    print("Missing optional Python dependencies: " + ", ".join(missing))
    if no_deps:
        print("Skipped dependency installation (--no-deps).")
        return True
    if not yes and not ask_yes("Install them now? [Y/n] "):
        print("Skipped dependency installation; text-only features will still work.")
        return True

    requirements = ROOT / "requirements-optional.txt"
    if not requirements.is_file():
        print("WARNING: requirements-optional.txt not found; skipping.")
        return False
    print("Running: python -m pip install -r requirements-optional.txt")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements)]
        )
    except OSError as exc:
        print(f"WARNING: could not start pip: {exc}")
        return False
    if proc.returncode != 0:
        print("WARNING: dependency installation failed; continuing with core install.")
        return False
    return True


def installer_command(target: str, destination: Path | None) -> list[str]:
    if os.name == "nt":
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            raise RuntimeError("PowerShell not found; cannot run install-skill.ps1.")
        cmd = [
            exe,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "install-skill.ps1"),
            "-Target",
            target,
        ]
        if destination is not None:
            cmd.extend(["-Destination", str(destination)])
        return cmd

    cmd = ["bash", str(ROOT / "scripts" / "install-skill.sh"), target]
    if destination is not None:
        cmd.append(str(destination))
    return cmd


def verify_install(dest: Path) -> str:
    coach = dest / "scripts" / "coach.py"
    proc = subprocess.run(
        [sys.executable, str(coach), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "coach.py --version failed")
    version = (proc.stdout or "").strip().splitlines()
    return version[-1] if version else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the review-sprint skill into one or more agent skill directories."
    )
    parser.add_argument(
        "--target",
        choices=("auto", "dsh", "claude", "codex", "cursor", "all", "custom"),
        default="auto",
        help="auto detects existing agent directories; all installs all four.",
    )
    parser.add_argument(
        "--destination",
        "--dest",
        dest="destination",
        help="destination directory for --target custom",
    )
    parser.add_argument("--no-deps", action="store_true", help="do not install optional Python packages")
    parser.add_argument("--yes", action="store_true", help="non-interactive: install without prompting")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10 or newer is required.")
        return 2
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    selections: list[tuple[str, Path | None]] = []
    if args.target == "auto":
        names = detected_targets()
        if not names:
            print("No agent skill directory detected.")
            print("Use --target all, --target dsh, or --target custom --destination PATH.")
            return 2
        selections = [(name, None) for name in names]
    elif args.target == "all":
        selections = [(name, None) for name in TARGET_NAMES]
    elif args.target == "custom":
        if not args.destination:
            print("ERROR: --target custom requires --destination PATH.")
            return 2
        selections = [("custom", Path(args.destination).expanduser())]
    else:
        selections = [(args.target, None)]

    print("Install plan:")
    for name, dest in selections:
        shown = dest if dest is not None else target_dir(name)
        print(f"  - {name}: {shown}")
    if not args.yes and not ask_yes("Proceed? [Y/n] "):
        print("Cancelled.")
        return 0

    install_dependencies(args.no_deps, args.yes)
    ok = True
    for name, dest in selections:
        try:
            subprocess.run(installer_command(name, dest), check=True)
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            print(f"ERROR: install {name} failed: {exc}")
            ok = False
            continue
        installed = dest if dest is not None else target_dir(name)
        try:
            version = verify_install(installed)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"ERROR: install {name} verification failed: {exc}")
            ok = False
            continue
        print(f"OK: {name} -> {installed} (review-sprint {version})")

    print("Done." if ok else "Finished with errors.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
