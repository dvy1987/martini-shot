#!/usr/bin/env python
"""Spend Guardian judgment eval (H-1d, C-3.3/.4).

Builds the REAL Spend Control state (station's own policies.yaml + the
station's detect-helper aggregation) over seeded job rows, then runs the
REAL Spend Guardian (billed Gemini call, C-1.1) to judge the proposed plan.
Metric: mean_assessment_accuracy >= 0.8 (thresholds.yaml).
Evidence: docs/evidence/H-1/spend_guardian_eval.jsonl + _summary.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.supervisor.agents.spend_guardian import investigate, read_spend_state
from backend.supervisor.case import Case

DATASET = ROOT / "backend" / "evals" / "datasets" / "spend_guardian_judgment.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "H-1"
THRESHOLD = 0.8


def main() -> int:
    settings = get_settings()
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = []
    scores: list[float] = []
    for row in rows:
        # REAL policies.yaml + REAL detect aggregation over the seeded rows.
        state = read_spend_state(
            None,
            project_id="proj-eval",
            station=row["station"],
            jobs=[{**job, "project_id": "proj-eval"} for job in row["jobs"]]
            + [
                # a couple of other-station rows so daily aggregation has real scope
                {
                    "id": "job-other-1",
                    "station": "ingest",
                    "attempts": 1,
                    "cost_micros": row["daily_spent_micros"] // 3,
                    "project_id": "proj-eval",
                },
                {
                    "id": "job-other-2",
                    "station": "delivery",
                    "attempts": 1,
                    "cost_micros": row["daily_spent_micros"]
                    - row["daily_spent_micros"] // 3,
                    "project_id": "proj-eval",
                },
            ],
        )
        case = Case(
            case_id=f"{row['id']}-case",
            version=1,
            created_at="",
            trigger={
                "kind": "spend_breach",
                "job_id": row["jobs"][0]["id"],
                "station": row["station"],
                "project_id": "proj-eval",
            },
            evidence={"jobs": row["jobs"], "proposed": row["proposed_action"]},
        )
        record: dict = {
            "id": row["id"],
            "case": row["case"],
            "expected_assessment": row["expected_assessment"],
            "policy": state["policy"],
            "daily_spent_micros": state["daily_spent_micros"],
        }
        try:
            result = investigate(
                case, settings, spend_state=state, proposal=row["proposed_action"]
            )
            record.update(
                {
                    "ok": True,
                    "assessment": result.assessment,
                    "score": 1.0
                    if result.assessment == row["expected_assessment"]
                    else 0.0,
                    "claims": [
                        {
                            "text": c.text,
                            "evidence_ref": c.evidence_ref,
                            "confidence": c.confidence,
                        }
                        for c in result.finding.claims
                    ],
                    "counter_proposals": [
                        a.command_name for a in result.finding.proposed_actions
                    ],
                }
            )
            scores.append(float(record["score"]))
        except Exception as exc:
            record.update(
                {"ok": False, "score": 0.0, "error": f"{type(exc).__name__}: {exc}"}
            )
            scores.append(0.0)
        records.append(record)
        print(
            json.dumps(
                {k: record.get(k) for k in ("id", "assessment", "score", "error")},
                indent=None,
            ),
            flush=True,
        )

    mean = sum(scores) / len(scores) if scores else 0.0
    payload = {
        "suite": "spend_guardian_judgment",
        "metric": "mean_assessment_accuracy",
        "threshold": THRESHOLD,
        "mean_assessment_accuracy": mean,
        "n": len(rows),
        "pass": mean >= THRESHOLD,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "spend_guardian_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "spend_guardian_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
