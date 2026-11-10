#!/usr/bin/env python3
"""Create a portable skill zip and its SHA-256 checksum."""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from review_sprint import __version__  # noqa: E402

INCLUDE = ("SKILL.md", "SECURITY.md")
DIRS = ("scripts", "references")


def build(out_dir: Path) -> tuple[Path, Path]:
    version = __version__
    out_dir.mkdir(parents=True, exist_ok=True)
    package = out_dir / f"review-sprint-skill-{version}.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in INCLUDE:
            zf.write(ROOT / name, f"review-sprint/{name}")
        for dirname in DIRS:
            for path in (ROOT / dirname).rglob("*"):
                if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                zf.write(path, f"review-sprint/{path.relative_to(ROOT).as_posix()}")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    checksum = package.with_suffix(package.suffix + ".sha256")
    checksum.write_text(f"{digest}  {package.name}\n", encoding="utf-8")
    return package, checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    args = parser.parse_args()
    package, checksum = build(Path(args.out))
    print(package)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
