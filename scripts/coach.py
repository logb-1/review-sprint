#!/usr/bin/env python3
"""review-sprint CLI entry point.

Usage:
    python scripts/coach.py --workspace .review-sprint init --course 计算机系统基础 \
        --exam-date 2026-11-24 --materials ./courseware ./papers
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from review_sprint.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
