#!/usr/bin/env python
"""Constitution C-1.2 mechanical enforcement: no mocks/stubs in product code.

Scans backend/ and frontend/src for banned markers. Test files are excluded
(C-1.2 excludes tests); fixtures are INPUT data only and never scanned
(C-1.3). Exit 1 on any finding so `make integrity` and pre-commit fail.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "backend", ROOT / "frontend" / "src"]
EXCLUDE_PARTS = {"tests", "node_modules", "dist", ".venv", ".git"}
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js"}

BANNED = [
    (re.compile(r"\bMagicMock\b"), "MagicMock (C-1.2: no mock layers)"),
    (re.compile(r"\bmonkeypatch\b"), "monkeypatch (C-1.2: no mock layers)"),
    (re.compile(r"\bclass\s+Fake\w*"), "Fake* class (C-1.2)"),
    (re.compile(r"\bTODO\b|\bFIXME\b"), "TODO/FIXME stub marker (C-1.2)"),
]


def main() -> int:
    findings: list[str] = []
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if EXCLUDE_PARTS & set(path.parts):
                continue
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue  # C-1.2: tests excluded
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for pattern, label in BANNED:
                    if pattern.search(line):
                        rel = path.relative_to(ROOT)
                        findings.append(
                            f"{rel}:{lineno}: {label} -> {line.strip()[:100]}"
                        )
    if findings:
        print("C-1.2 integrity violations found:")
        print("\n".join(findings))
        return 1
    print("integrity: no mocks/stubs in product code (C-1.2 clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
