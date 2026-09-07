#!/usr/bin/env python
"""Caption writer eval: real Gemini produces an SRT from a script (or
refuses when there is nothing to caption).

Gate (thresholds.yaml): caption_write_judgment mean_case_accuracy >= 0.8.
A hit requires the expected decision; a write must also re-validate clean
and keep every script word (C-1.3 labeled INPUT, no canned scores).

Cost: 8 flash calls/run × 3 runs. Printed before billing; --yes if > $5.
Evidence: docs/evidence/caption-write/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.supervisor.station_agents.caption_write import (
    decide_caption_write,
    revalidate_written_cues,
)

DATASET = ROOT / "backend" / "evals" / "datasets" / "caption_write_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "caption-write"
THRESHOLD = 0.8
ESTIMATE_MICROS_PER_CALL = 3_000


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE) if w]


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
        residual = None
        missing = []
        expected = row["expected"]["decision"]
        script = str(row.get("script") or "")
        try:
            doc, call_cost = decide_caption_write(
                settings,
                script=script,
                duration_s=float(row["duration_s"]),
            )
            decision = doc.decision
            reason = doc.reason
            cost_micros += int(call_cost)
            ok_decision = decision == expected
            ok_valid = True
            ok_words = True
            if decision == "write":
                _cues, leftover = revalidate_written_cues(doc.raw)
                residual = [v.rule_id for v in leftover]
                ok_valid = not leftover
                body = " ".join(" ".join(c.lines) for c in _cues)
                missing = [w for w in _words(script) if w not in _words(body)]
                ok_words = not missing
            score = 1.0 if ok_decision and ok_valid and ok_words else 0.0
        except Exception as exc:
            reason = f"ERROR {type(exc).__name__}: {exc}"[:200]
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "expected": expected,
                "decision": decision,
                "residual": residual,
                "missing_words": missing[:12],
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
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    n_lines = sum(
        1 for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    estimate = n_lines * args.runs * ESTIMATE_MICROS_PER_CALL
    estimate_usd = round(estimate / 1_000_000, 4)
    print(
        json.dumps(
            {
                "estimate_micros": estimate,
                "estimate_usd": estimate_usd,
                "cases": n_lines,
                "runs": args.runs,
            }
        ),
        flush=True,
    )
    if estimate_usd > 5 and not args.yes:
        print("batch over $5 requires --yes (C-7.2)", file=sys.stderr)
        return 2

    all_records: list[dict] = []
    summaries: list[dict] = []
    for i in range(1, args.runs + 1):
        print(f"=== caption_write_judgment run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    billed = sum(int(s.get("cost_micros") or 0) for s in summaries)
    payload = {
        "suite": "caption_write_judgment",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "cost_micros": billed,
        "cost_usd": round(billed / 1_000_000, 4),
        "pass": all(s["pass"] for s in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "caption_write_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "caption_write_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
