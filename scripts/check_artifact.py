#!/usr/bin/env python3
"""Reviewer-facing repository consistency checks.

This catches stale paths/claims that make OSS artifacts look unreproducible.
It is intentionally lightweight and runs without PX4/Gazebo/AirSim.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "README_CN.md",
    "LICENSE",
    "ARTIFACT.md",
    "REVIEWER_CHECKLIST.md",
    "Dockerfile",
    ".dockerignore",
    ".env.example",
    "pyproject.toml",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".github/workflows/ci.yml",
    "tests/test_mock_adapter.py",
    "tests/test_server_smoke.py",
    "scripts/smoke_mock.sh",
]

STALE_PATTERNS = [
    r"clients/",
    r"requirements-edge\.txt",
    r"core\.doctor",
    r"/api/doctor/run",
    r"scripts/start_gz_sim\.sh",
    r"Multi-platform clients",
    r"15 React components",
]

TEXT_GLOBS = [
    "README*.md",
    "ARTIFACT.md",
    "REVIEWER_CHECKLIST.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/*.md",
    "scripts/*.sh",
    ".github/workflows/*.yml",
]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        fail("missing required artifact files: " + ", ".join(missing))

    offenders: list[str] = []
    combined = re.compile("|".join(STALE_PATTERNS))
    for glob in TEXT_GLOBS:
        for path in ROOT.glob(glob):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if combined.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    if offenders:
        fail("stale artifact references found:\n" + "\n".join(offenders))

    absolute_duplicates = list((ROOT / "Users").glob("**/*")) if (ROOT / "Users").exists() else []
    if absolute_duplicates:
        fail("repository contains accidental absolute-path duplicate tree under Users/")

    print("artifact consistency checks passed")


if __name__ == "__main__":
    main()
