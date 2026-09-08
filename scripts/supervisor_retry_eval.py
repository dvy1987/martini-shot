#!/usr/bin/env python
"""Supervisor one-retry judgment: live Gemini + hard gates.

Gate: supervisor_retry_judgment mean_case_accuracy >= 0.8, 3 runs.
Hard-gate rows score admit_retry_once without a billed call.
Fuzzy rows score live decide_retry_once.
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
from backend.supervisor.agents.supervisor_retry import decide_retry_once
from backend.supervisor.budget_loop import FIX_ONCE_COMMANDS, admit_retry_once

DATASET = ROOT / "backend" / "evals" / "datasets" / "supervisor_retry_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "supervisor-retry"
THRESHOLD = 0.8
ESTIMATE_MICROS_PER_CALL = 8_000


def _score_hard_gate(row: dict) -> tuple[float, str]:
    job = dict(row.get("job") or {})
    ok, reason = admit_retry_once(
        command_name=str(row.get("command_name") or "retry_job"),
        args={"job_id": str(job.get("id") or "")},
        job=job,
    )
    predicted = "abstain"
    if ok:
        name = str(row.get("command_name") or "retry_job")
        predicted = "fix" if name in FIX_ONCE_COMMANDS else "retry"
    expected = str(row.get("decision") or "")
    return (1.0 if predicted == expected else 0.0), reason


def _score_live(row: dict, settings: object) -> tuple[float, str, int]:
    job = dict(row.get("job") or {})
    command_name = str(row.get("command_name") or "retry_job")
    decision, cost = decide_retry_once(settings, job=job, command_name=command_name)
    ok, reason = admit_retry_once(
        command_name=command_name,
        args={"job_id": str(job.get("id") or "")},
        job=job,
        llm_decision=decision,
    )
    expected = str(row.get("decision") or "")
    hit = decision == expected
    go = expected in ("retry", "fix")
    if go and not ok:
        hit = False
    if not go and ok:
        hit = False
    return (1.0 if hit else 0.0), f"{decision}; {reason}", int(cost)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    live_n = sum(1 for row in rows if not row.get("hard_gate"))
    estimate = ESTIMATE_MICROS_PER_CALL * live_n * args.runs
    print(
        f"supervisor_retry_eval estimate {estimate} micros "
        f"(${estimate / 1_000_000:.2f}) live Gemini"
    )
    if estimate > 5_000_000 and not args.yes:
        print("above $5 — pass --yes", file=sys.stderr)
        return 2
    settings = get_settings()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    summaries: list[dict] = []
    for run in range(1, args.runs + 1):
        hits = 0
        cost_micros = 0
        for row in rows:
            try:
                if row.get("hard_gate"):
                    score, detail = _score_hard_gate(row)
                else:
                    score, detail, call_cost = _score_live(row, settings)
                    cost_micros += call_cost
            except Exception as exc:
                records.append(
                    {
                        "run": run,
                        "id": row["id"],
                        "score": 0.0,
                        "error": type(exc).__name__,
                    }
                )
                print(
                    json.dumps({"run": run, "id": row["id"], "score": 0.0}),
                    flush=True,
                )
                continue
            hits += int(score)
            records.append(
                {
                    "run": run,
                    "id": row["id"],
                    "score": score,
                    "detail": detail,
                }
            )
            print(
                json.dumps({"run": run, "id": row["id"], "score": score}),
                flush=True,
            )
        accuracy = hits / len(rows) if rows else 0.0
        summaries.append(
            {
                "run": run,
                "mean_case_accuracy": round(accuracy, 3),
                "hits": hits,
                "n": len(rows),
                "cost_micros": cost_micros,
                "pass": accuracy >= THRESHOLD,
            }
        )
        print(json.dumps(summaries[-1]), flush=True)
    (EVIDENCE / "supervisor_retry_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "supervisor_retry_summary.json").write_text(
        json.dumps({"summaries": summaries}, indent=2), encoding="utf-8"
    )
    return 0 if all(s["pass"] for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
