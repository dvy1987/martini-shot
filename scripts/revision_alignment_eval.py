#!/usr/bin/env python
"""D-15 Revision Room alignment: live Gemini maps script → shots.

No string-match fake. Gate >= 0.8, 3 runs. C-7.2 print; --yes over $5.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.supervisor.station_agents.revision_room import decide_alignment

DATASET = ROOT / "backend" / "evals" / "datasets" / "revision_alignment_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "D-15"
THRESHOLD = 0.8
LOOK_ESTIMATE_MICROS = 80_000


def _load() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _hit(row: dict, spans: list[dict]) -> bool:
    expected = set(row["expected_shot_ids"])
    got = {str(span.get("shot_id")) for span in spans}
    return expected <= got and bool(spans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    rows = _load()
    estimate = LOOK_ESTIMATE_MICROS * len(rows) * args.runs
    print(
        f"revision_alignment_eval estimate {estimate} micros "
        f"(${estimate / 1_000_000:.2f}) live Gemini; "
        f"{len(rows)} rows × {args.runs} runs"
    )
    if estimate > 5_000_000 and not args.yes:
        print("batch over $5 requires --yes (C-7.2)", file=sys.stderr)
        return 2
    settings = get_settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records: list[dict] = []
    summaries: list[dict] = []
    for run in range(1, args.runs + 1):
        hits = 0
        cost = 0
        for row in rows:
            try:
                spans, micros = decide_alignment(
                    settings,
                    script_text=row["script"],
                    shots=row["shots"],
                )
                cost += micros
                score = 1.0 if _hit(row, spans) else 0.0
                reason = json.dumps([s.get("shot_id") for s in spans])
            except Exception as exc:
                score = 0.0
                reason = f"{type(exc).__name__}: {exc}"[:240]
                spans = []
            hits += int(score)
            rec = {
                "run": run,
                "id": row["id"],
                "score": score,
                "reason": reason[:240],
            }
            records.append(rec)
            print(json.dumps(rec), flush=True)
        accuracy = hits / len(rows) if rows else 0.0
        summary = {
            "run": run,
            "mean_case_accuracy": round(accuracy, 3),
            "hits": hits,
            "n": len(rows),
            "cost_micros": cost,
            "pass": accuracy >= THRESHOLD,
        }
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"revision_alignment_eval_{stamp}.jsonl").write_text(
        "\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8"
    )
    means = [row["mean_case_accuracy"] for row in summaries]
    payload = {
        "suite": "revision_alignment_judgment",
        "runs": summaries,
        "mean_case_accuracy": round(sum(means) / len(means), 3) if means else 0.0,
        "pass": all(row["pass"] for row in summaries),
    }
    (EVIDENCE / f"revision_alignment_summary_{stamp}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
