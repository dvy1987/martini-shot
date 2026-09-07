#!/usr/bin/env python
"""Finishing rank quality: live Gemini orchestrator on labeled bags.

The boss must weigh tradeoffs and name dependencies. Code only strips
invented/empty work. Gate: mean_case_accuracy >= 0.8, 3 runs (C-3.4).
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
from backend.supervisor.inspect import empty_note, validate_inspect_note
from backend.supervisor.rank import note_key
from backend.supervisor.rank_impl import run_rank_agent

DATASET = ROOT / "backend" / "evals" / "datasets" / "finishing_rank_quality.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "finish-loop"
THRESHOLD = 0.8
OWNER_CAP_MICROS = 20_000_000


def _as_note(raw: dict):
    if raw.get("status") == "empty":
        return empty_note(str(raw["station"]))
    return validate_inspect_note(
        {
            "station": raw["station"],
            "agent": raw["station"],
            "status": raw.get("status") or "needs_work",
            "impact": raw["impact"],
            "kind": raw.get("kind") or "defect",
            "summary": raw.get("summary") or raw["station"],
            "cost_estimate_micros": int(raw.get("cost_estimate_micros") or 1),
            "proposal": {
                "kind": "station_job",
                "station": raw["station"],
                "args": {},
            },
            "shot_id": raw.get("shot_id") or "shot-a",
        }
    )


def score_plan(row: dict, plan) -> tuple[float, str]:
    stations = [n.station for n in plan.ordered]
    keys = [note_key(n) for n in plan.ordered]
    if row.get("expected_first") and (
        not stations or stations[0] != row["expected_first"]
    ):
        return 0.0, f"first={stations[:1]} expected={row['expected_first']}"
    if row.get("expected_dispatched") is not None:
        if stations != row["expected_dispatched"]:
            return 0.0, f"dispatched={stations} expected={row['expected_dispatched']}"
    for a, b in row.get("must_precede") or []:
        if a not in stations or b not in stations:
            return 0.0, f"missing {a} or {b} in {stations}"
        if stations.index(a) > stations.index(b):
            return 0.0, f"{a} after {b}"
    dep = row.get("expected_dependency")
    if dep:
        before, after = dep
        blockers = plan.blocked_by.get(after) or []
        if before not in blockers:
            return 0.0, f"missing dep {before}->{after} got {plan.blocked_by}"
    for before, after in row.get("forbid_dependency") or []:
        blockers = plan.blocked_by.get(after) or []
        if before in blockers:
            return 0.0, f"illegal dep {before}->{after}"
    illegal = row.get("illegal_keep") or []
    if any(station in stations for station in illegal):
        return 0.0, f"invented {illegal}"
    if any(key.startswith("trailer_bench") for key in keys):
        return 0.0, "invented trailer_bench"
    must_drop = row.get("expected_drop") or []
    for item_id in must_drop:
        if item_id in keys:
            return 0.0, f"{item_id} still ordered; drop={plan.dropped}"
    return 1.0, plan.reason[:180]


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
    estimate = 200_000 * len(rows) * args.runs
    print(
        f"finishing_rank_eval estimate {estimate} micros "
        f"(${estimate / 1_000_000:.2f}) live Gemini orchestrator"
    )
    if estimate > OWNER_CAP_MICROS and not args.yes:
        print(
            f"above ${OWNER_CAP_MICROS / 1_000_000:.0f} owner cap — pass --yes",
            file=sys.stderr,
        )
        return 2
    settings = get_settings()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    summaries = []
    records = []
    for run in range(1, args.runs + 1):
        hits = 0
        cost_micros = 0
        for row in rows:
            notes = [_as_note(raw) for raw in row["notes"]]
            shot_order = {
                str(raw.get("shot_id") or "shot-a"): i
                for i, raw in enumerate(row["notes"])
            }
            plan = run_rank_agent(
                settings,
                notes,
                shot_order=shot_order,
                remaining_micros=int(row.get("remaining_micros") or 50_000_000),
                scene_by_shot=row.get("scene_by_shot") or {},
                orchestrator_spine=row.get("orchestrator_spine") or [],
            )
            score, reason = score_plan(row, plan)
            hits += int(score)
            records.append(
                {
                    "run": run,
                    "id": row["id"],
                    "score": score,
                    "reason": reason,
                    "order": [n.station for n in plan.ordered],
                    "blocked_by": plan.blocked_by,
                }
            )
            print(
                json.dumps(
                    {"run": run, "id": row["id"], "score": score, "reason": reason}
                ),
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
    (EVIDENCE / "rank_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "rank_eval_summary.json").write_text(
        json.dumps({"summaries": summaries}, indent=2), encoding="utf-8"
    )
    return 0 if all(s["pass"] for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
