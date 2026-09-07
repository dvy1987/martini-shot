#!/usr/bin/env python
"""D-10 Corrections Agent eval: live Gemini judgments on labeled briefs.

Gate (thresholds.yaml): corrections_judgment mean_case_accuracy >= 0.8.
Honest accounting (C-3.5): a failed/invalid decision counts as a miss.

Cost: 6 flash calls/run (~$0.02) × 3 runs ≈ $0.06 — under the $5 bar (C-7.2).
Evidence: docs/evidence/D-10/corrections_judgment_eval.jsonl + _summary.json.
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
from backend.supervisor.station_agents.corrections import decide_corrections

DATASET = ROOT / "backend" / "evals" / "datasets" / "corrections_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "D-10"
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
    cost_micros = 0
    for row in rows:
        score = 0.0
        decision = ""
        reason = "agent call failed"
        try:
            doc, call_cost = decide_corrections(settings, brief=row["brief"])
            decision = doc.decision
            reason = doc.reason
            cost_micros += int(call_cost)
            score = 1.0 if decision == row["expected"]["decision"] else 0.0
        except Exception as exc:
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
        "cost_micros": cost_micros,
        "pass": accuracy >= THRESHOLD,
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    estimate = args.runs * 6 * 4000
    print(
        f"estimated_cost_micros={estimate} (~${estimate / 1_000_000:.2f}) "
        "for live Gemini judgment calls",
        flush=True,
    )

    all_records: list[dict] = []
    summaries: list[dict] = []
    for i in range(1, args.runs + 1):
        print(f"=== corrections_judgment run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    payload = {
        "suite": "corrections_judgment",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "pass": all(item["pass"] for item in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = ""
    existing = EVIDENCE / "corrections_judgment_eval.jsonl"
    # Never overwrite a prior full run: append a dated sibling if present.
    if existing.exists():
        from datetime import datetime, timezone

        stamp = "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (EVIDENCE / f"corrections_judgment_eval{stamp}.jsonl").write_text(
        "\n".join(json.dumps(row) for row in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / f"corrections_judgment_summary{stamp}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
