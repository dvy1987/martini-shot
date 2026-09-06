#!/usr/bin/env python
"""Extend QC eval (A10-4, C-3.3/.4): the REAL agent judges each seeded
extend-render report; scored against the expected decision.

Gate (thresholds.yaml): extend_qc_judgment mean_case_accuracy >= 0.8.
Honest accounting (C-3.5): a failed/invalid decision counts as a MISS.

Evidence: docs/evidence/A10-4/extend_qc_eval.jsonl + _summary.json.
Cost: 8 flash calls/run (~$0.02) — under the $5 owner-approval bar (C-7.2).
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
from backend.supervisor.station_agents.extend_qc import decide_extend_qc

DATASET = ROOT / "backend" / "evals" / "datasets" / "extend_qc_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "A10-4"
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
        score = 0.0
        decision = ""
        reason = "agent call failed"
        try:
            doc, _cost = decide_extend_qc(settings, report=row["report"])
            decision = doc.decision
            reason = doc.reason
            score = 1.0 if decision == row["expected"]["decision"] else 0.0
        except Exception as exc:  # honest accounting: a failed call is a miss
            reason = f"ERROR {type(exc).__name__}: {exc}"[:200]
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "expected": row["expected"]["decision"],
                "decision": decision,
                "reason": reason[:200],
                "score": score,
            }
        )
        print(
            json.dumps({k: records[-1][k] for k in ("run", "id", "decision", "score")}),
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
        print(f"=== extend_qc_judgment run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    payload = {
        "suite": "extend_qc_judgment",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "pass": all(s["pass"] for s in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "extend_qc_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "extend_qc_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
