"""Pytest bootstrap: make the repo root importable for `backend.*` imports
regardless of how pytest is invoked (python -m pytest, plain pytest, IDE)."""

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
