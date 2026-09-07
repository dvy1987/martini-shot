#!/usr/bin/env python
"""Spend pricing judgment: live Gemini names micros for leftover jobs.

Gate: spend_pricing_judgment mean_case_accuracy >= 0.8, 3 runs.
A hit is every expected id priced inside [min, max], no invented ids.
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
from backend.supervisor.station_agents.spend_pricing import decide_spend_pricing

DATASET = ROOT / "backend" / "evals" / "datasets" / "spend_pricing_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "finish-loop"
THRESHOLD = 0.8
ESTIMATE_MICROS_PER_CALL = 8_000


def _hit(row: dict, prices: dict[str, int]) -> bool:
    for bad in row.get("illegal_ids") or []:
        if bad in prices:
            return False
    expected = row.get("expected") or {}
    for item_id, band in expected.items():
        cost = prices.get(item_id)
        if cost is None:
            return False
        if int(cost) < int(band["min"]) or int(cost) > int(band["max"]):
            return False
    return True


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
    estimate = ESTIMATE_MICROS_PER_CALL * len(rows) * args.runs
    print(
        f"spend_pricing_eval estimate {estimate} micros "
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
            prices: dict[str, int] = {}
            try:
                prices, call_cost = decide_spend_pricing(
                    settings,
                    candidates=row["candidates"],
                    remaining_micros=int(row.get("remaining_micros") or 0),
                )
                cost_micros += int(call_cost)
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
                    json.dumps({"run": run, "id": row["id"], "score": 0.0}), flush=True
                )
                continue
            score = 1.0 if _hit(row, prices) else 0.0
            hits += int(score)
            records.append(
                {
                    "run": run,
                    "id": row["id"],
                    "score": score,
                    "prices": prices,
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
    (EVIDENCE / "spend_pricing_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "spend_pricing_summary.json").write_text(
        json.dumps({"summaries": summaries}, indent=2), encoding="utf-8"
    )
    return 0 if all(s["pass"] for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
