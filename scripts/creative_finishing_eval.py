#!/usr/bin/env python
"""Creative Finishing eval (H-1i, C-3.3/.4): the REAL agent judges each
seeded extend-proposal case; scored against the expected plan, including
tier compliance (draft_first / master).

Gate (thresholds.yaml): creative_finishing_judgment mean_case_accuracy
>= 0.8. Honest accounting (C-3.5): a failed/invalid decision counts as a
MISS.

Evidence: docs/evidence/H-1i/creative_finishing_eval.jsonl + _summary.json.
Cost: 4 flash calls/run (~$0.01) — under the $5 owner-approval bar (C-7.2).
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
from backend.supervisor.station_agents.creative_finishing import (
    decide_creative_finishing,
)

DATASET = ROOT / "backend" / "evals" / "datasets" / "creative_finishing_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "H-1i"
THRESHOLD = 0.8


def expected(row: dict) -> tuple[str, str | None]:
    """(decision, tier-or-None) the case requires."""
    action = row.get("expected_action")
    if not action:
        return "abstain", None
    if action.get("draft_first"):
        return "propose_render", "draft"
    return "propose_render", (action.get("tier") or None)


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
        decision, tier = "", ""
        reason = "agent call failed"
        try:
            doc, _cost = decide_creative_finishing(
                settings,
                job=row["job"],
                # cf-02 carries no alternates_context (a shot with no
                # recorded alternates) — an empty state, not a harness error.
                alternates_context=row.get("alternates_context") or {},
            )
            decision = doc.decision
            tier = str(doc.raw.get("tier") or "")
            reason = doc.reason
            exp_decision, exp_tier = expected(row)
            score = 1.0 if decision == exp_decision else 0.0
            if exp_tier is not None and tier != exp_tier:
                score = 0.0  # tier compliance is part of the case
        except Exception as exc:  # honest accounting: a failed call is a miss
            reason = f"ERROR {type(exc).__name__}: {exc}"[:200]
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "expected": expected(row)[0],
                "expected_tier": expected(row)[1],
                "decision": decision,
                "tier": tier,
                "reason": reason[:200],
                "score": score,
            }
        )
        print(
            json.dumps(
                {k: records[-1][k] for k in ("run", "id", "decision", "tier", "score")}
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
        print(f"=== creative_finishing_judgment run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    payload = {
        "suite": "creative_finishing_judgment",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "pass": all(s["pass"] for s in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "creative_finishing_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "creative_finishing_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
