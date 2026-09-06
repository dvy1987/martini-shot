#!/usr/bin/env python
"""Orchestrator planning eval (A10-2, C-3.3/.4): the REAL agent plans the
station chain for each seeded manifest item; the plan is validated by the
deterministic subsequence rule and scored against the expected chain.

Gate (thresholds.yaml): orchestrator_planning mean_case_accuracy >= 0.8.
Honest accounting (C-3.5): a failed/invalid plan counts as a MISS (it lands
as deterministic_fallback in production — which would also mismatch any
trimmed expected chain).

Evidence: docs/evidence/A10-2/orchestrator_planning_eval.jsonl + _summary.json.
Cost: 12 flash calls/run (~$0.03) — under the $5 owner-approval bar (C-7.2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.supervisor.orchestrator import plan_chain
from backend.supervisor.station_agents.orchestrator import plan_item

DATASET = ROOT / "backend" / "evals" / "datasets" / "orchestrator_planning.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "A10-2"
THRESHOLD = 0.8


def run_suite(run_index: int) -> tuple[list[dict], dict]:
    settings = get_settings()
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: list[dict] = []
    hits = 0
    for row in rows:
        item = row["item"]
        default_chain = plan_chain(item)
        chain, doc = plan_item(settings, item, default_chain=default_chain)
        expected = list(row["expected_chain"])
        score = 1.0 if chain == expected else 0.0
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "expected": expected,
                "planned": chain,
                "decision_mode": doc["decision_mode"],
                "overridden": doc["overridden"],
                "reason": doc["reason"][:200],
                "score": score,
            }
        )
        print(
            json.dumps(
                {
                    k: records[-1][k]
                    for k in ("run", "id", "planned", "decision_mode", "score")
                }
            ),
            flush=True,
        )

    accuracy = hits / len(rows) if rows else 0.0
    summary = {
        "run": run_index,
        "mean_case_accuracy": round(accuracy, 3),
        "hits": hits,
        "n": len(rows),
        "pass": accuracy >= THRESHOLD,
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    all_records: list[dict] = []
    summaries: list[dict] = []
    for i in range(1, args.runs + 1):
        print(f"=== orchestrator_planning run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    payload = {
        "suite": "orchestrator_planning",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "pass": all(s["pass"] for s in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "orchestrator_planning_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "orchestrator_planning_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
