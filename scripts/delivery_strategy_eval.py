#!/usr/bin/env python
"""Delivery strategy eval (A10-3, C-3.3/.4): the REAL agent chooses the
delivery strategy over per-destination evaluations produced by the REAL
D-4 engine (evaluate_delivery); scored on decision + destination (+ the
H-0 proposal command when one is expected).

Gate (thresholds.yaml): delivery_strategy_judgment mean_case_accuracy >= 0.8.
Honest accounting (C-3.5): a failed call counts as a MISS.

Evidence: docs/evidence/A10-3/delivery_strategy_eval.jsonl + _summary.json.
Cost: 8 flash calls/run (~$0.02) — under the $5 owner-approval bar (C-7.2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.stations.delivery.evaluate import evaluate_delivery
from backend.supervisor.station_agents.delivery_strategy import (
    decide_delivery_strategy,
)

DATASET = ROOT / "backend" / "evals" / "datasets" / "delivery_strategy_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "A10-3"
THRESHOLD = 0.8


def _real_evaluations(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic prep: run the REAL D-4 engine per destination — the
    dataset carries only the labeled INPUT probe."""
    return [
        evaluate_delivery(
            destination=dest,
            probe=row["probe"],
            lufs=row["lufs"],
            caption_text=row.get("caption_text"),
            caption_name=row.get("caption_name"),
        )
        for dest in row["destinations"]
    ]


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
        expected = row["expected"]
        score = 0.0
        decision = ""
        destination = ""
        detail = "agent call failed"
        evaluations = _real_evaluations(row)
        try:
            doc, _cost = decide_delivery_strategy(
                settings, probe=row["probe"], evaluations=evaluations
            )
            decision = doc.decision
            destination = str(doc.raw.get("destination") or "")
            proposal = doc.proposal.get("command_name") or ""
            detail = doc.reason
            ok = (
                decision == expected["decision"]
                and destination == expected["destination"]
                and proposal == expected.get("proposal_command", "")
            )
            score = 1.0 if ok else 0.0
        except Exception as exc:  # honest accounting: a failed call is a miss
            detail = f"ERROR {type(exc).__name__}: {exc}"[:200]
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "expected": expected["decision"],
                "decision": decision,
                "destination": destination,
                "reason": detail[:200],
                "score": score,
            }
        )
        print(
            json.dumps(
                {
                    k: records[-1][k]
                    for k in ("run", "id", "decision", "destination", "score")
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
        print(f"=== delivery_strategy_judgment run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    payload = {
        "suite": "delivery_strategy_judgment",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "pass": all(s["pass"] for s in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "delivery_strategy_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "delivery_strategy_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
