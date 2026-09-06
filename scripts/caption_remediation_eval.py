#!/usr/bin/env python
"""Caption remediation eval (A10-3, C-3.3/.4): the REAL agent proposes
cue fixes for each seeded violation report; scoring enforces the CLOSED
LOOP — an apply_fixes answer only counts when the deterministic D-3
engine re-validates the proposal with ZERO residual violations AND the
original wording is preserved (re-timing/re-segmentation only).

Gate (thresholds.yaml): caption_remediation_judgment mean_case_accuracy >= 0.8.
Honest accounting (C-3.5): a failed call, an invalid fix, or a fix that
rewrites dialogue all count as MISSes.

Evidence: docs/evidence/A10-3/caption_remediation_eval.jsonl + _summary.json.
Cost: 8 flash calls/run (~$0.02) — under the $5 owner-approval bar (C-7.2).
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
from backend.stations.delivery.captions import parse_srt, validate_cues
from backend.supervisor.station_agents.caption_remediation import (
    decide_caption_remediation,
    revalidate_fixed_cues,
)

DATASET = ROOT / "backend" / "evals" / "datasets" / "caption_remediation_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "A10-3"
THRESHOLD = 0.8


def _cues_and_violations(srt: str) -> tuple[list[dict], list[dict]]:
    """Deterministic prep: parse with the REAL engine, then report the REAL
    violations — the dataset carries only the labeled input SRT."""
    cues = parse_srt(srt)
    cue_rows = [
        {
            "index": i,
            "start_s": c.start_s,
            "end_s": c.end_s,
            "lines": list(c.lines),
        }
        for i, c in enumerate(cues)
    ]
    violation_rows = [
        {"rule_id": v.rule_id, "message": v.message, "cue_index": v.cue_index}
        for v in validate_cues(cues)
    ]
    return cue_rows, violation_rows


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def meaning_preserved(cues: list[dict], fixed_rows: list[dict]) -> bool:
    """Every original cue's text must survive verbatim (whitespace-normalized)
    somewhere in the fixed cue set — re-timing/re-segmentation only."""
    joined = _norm(" ".join(" ".join(row.get("lines") or []) for row in fixed_rows))
    for cue in cues:
        text = _norm(" ".join(cue.get("lines") or []))
        if text and text not in joined:
            return False
    return True


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
        expected = row["expected"]["decision"]
        score = 0.0
        decision = ""
        detail = "agent call failed"
        revalidated: bool | None = None
        meaning: bool | None = None
        cue_rows, violation_rows = _cues_and_violations(row["captions_srt"])
        if not violation_rows:
            # Labeled-input hygiene (C-1.3): every case must actually violate.
            raise ValueError(f"{row['id']}: fixture has no violations")
        try:
            doc, _cost = decide_caption_remediation(
                settings, cues=cue_rows, violations=violation_rows
            )
            decision = doc.decision
            detail = doc.reason
            if decision == "needs_human":
                score = 1.0 if expected == "needs_human" else 0.0
            else:  # apply_fixes: the closed loop decides, not the prose
                cues_obj, residual = revalidate_fixed_cues(doc.raw)
                revalidated = not residual
                meaning = meaning_preserved(cue_rows, doc.raw.get("fixed_cues") or [])
                ok = revalidated and meaning and expected == "apply_fixes"
                score = 1.0 if ok else 0.0
                if residual:
                    detail = f"RESIDUAL {[v.rule_id for v in residual]}: {detail}"
                elif not meaning:
                    detail = f"MEANING CHANGED: {detail}"
        except Exception as exc:  # honest accounting: a failed call is a miss
            detail = f"ERROR {type(exc).__name__}: {exc}"[:200]
        hits += int(score)
        records.append(
            {
                "run": run_index,
                "id": row["id"],
                "expected": expected,
                "decision": decision,
                "revalidated": revalidated,
                "meaning_preserved": meaning,
                "reason": detail[:200],
                "score": score,
            }
        )
        print(
            json.dumps(
                {
                    k: records[-1][k]
                    for k in ("run", "id", "decision", "revalidated", "score")
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
        print(f"=== caption_remediation_judgment run {i}/{args.runs} ===", flush=True)
        records, summary = run_suite(i)
        all_records.extend(records)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    payload = {
        "suite": "caption_remediation_judgment",
        "runs": args.runs,
        "gate": {"threshold": THRESHOLD, "comparison": ">="},
        "per_run": summaries,
        "pass": all(s["pass"] for s in summaries),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "caption_remediation_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in all_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "caption_remediation_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
