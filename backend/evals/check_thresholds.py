#!/usr/bin/env python
"""CI-lite eval gate (constitution C-3.4: thresholds MUST be numeric).

Validates the STRUCTURE of backend/evals/thresholds.yaml: every suite must
declare a metric and a numeric threshold. It does not run evals (the runner
lands with the EDD tasks in plan Phase 2). Exits 0 while no suites are
registered yet.
"""

from __future__ import annotations

import sys
from pathlib import Path

THRESHOLDS = Path(__file__).resolve().parent / "thresholds.yaml"


def main() -> int:
    if not THRESHOLDS.exists():
        print(
            "no eval suites registered yet (thresholds.yaml absent) — OK before Phase 2"
        )
        return 0
    try:
        import yaml
    except ImportError:
        print("PyYAML missing: pip install -r requirements-dev.txt", file=sys.stderr)
        return 1
    data = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8")) or {}
    suites = data.get("suites")
    if not isinstance(suites, list) or not suites:
        print("thresholds.yaml must contain a non-empty 'suites' list", file=sys.stderr)
        return 1
    errors: list[str] = []
    for i, suite in enumerate(suites):
        if not isinstance(suite, dict) or not suite.get("name"):
            errors.append(f"suites[{i}]: missing name")
            continue
        if "metric" not in suite:
            errors.append(f"suites[{i}] ({suite.get('name')}): missing 'metric'")
        if "threshold" not in suite:
            errors.append(f"suites[{i}] ({suite.get('name')}): missing 'threshold'")
        elif not isinstance(suite["threshold"], (int, float)):
            errors.append(
                f"suites[{i}] ({suite.get('name')}): threshold must be numeric (C-3.4)"
            )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"thresholds.yaml valid: {len(suites)} suite(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
