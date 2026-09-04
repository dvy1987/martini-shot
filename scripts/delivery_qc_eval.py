#!/usr/bin/env python
"""Delivery QC judgment eval (H-1c, C-3.3/.4).

For each seeded pack in delivery_qc_judgment.jsonl, runs the REAL D-2/D-4
chain (evaluate_delivery + loudness verdict table — the same deterministic
evaluator the delivery station uses) to produce the QC report, then runs the
REAL Delivery QC agent (billed Gemini call, C-1.1: no mock candidates) and
scores whether its classification matches the expected one. Metric:
mean_classification_accuracy >= 0.8 (thresholds.yaml).
Evidence: docs/evidence/H-1/delivery_qc_eval.jsonl + _summary.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.stations.delivery.evaluate import evaluate_delivery
from backend.supervisor.agents.delivery_qc import investigate, read_qc_report_from_doc
from backend.supervisor.case import Case

DATASET = ROOT / "backend" / "evals" / "datasets" / "delivery_qc_judgment.jsonl"
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
    for _index, row in enumerate(rows):
        # REAL D-2/D-4 chain: the evaluator produces the report from the
        # seeded INPUTS (labeled synthetic input, C-1.3) — nothing is faked.
        report = evaluate_delivery(
            destination=row["destination"],
            probe=row["probe"],
            lufs=row["lufs"],
            caption_text=row.get("caption_text"),
            caption_name=row.get("caption_name"),
        )
        job_doc = {
            "id": f"job-{row['id']}",
            "station": "delivery",
            "project_id": "proj-eval",
            "status": "failed" if report["verdict"] != "pass" else "passed",
            "result": {"lufs": row["lufs"], "delivery": report},
        }
        case = Case(
            case_id=f"{row['id']}-case",
            version=1,
            created_at="",
            trigger={
                "kind": "qc_breach",
                "job_id": job_doc["id"],
                "station": "delivery",
            },
            evidence={"job": job_doc},
        )
        record: dict = {
            "id": row["id"],
            "case": row["case"],
            "evaluator_verdict": report["verdict"],
            "evaluator_violations": [
                v.get("rule_id") for v in report.get("violations", [])
            ],
            "expected_classification": row["expected_classification"],
        }
        try:
            result = investigate(
                case,
                settings,
                qc_report=read_qc_report_from_doc(job_doc),
            )
            record.update(
                {
                    "ok": True,
                    "classification": result.classification,
                    "score": 1.0
                    if result.classification == row["expected_classification"]
                    else 0.0,
                    "claims": [
                        {
                            "text": c.text,
                            "evidence_ref": c.evidence_ref,
                            "confidence": c.confidence,
                        }
                        for c in result.finding.claims
                    ],
                    "proposed_commands": [
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
                {
                    k: record.get(k)
                    for k in (
                        "id",
                        "evaluator_verdict",
                        "classification",
                        "score",
                        "error",
                    )
                },
                indent=None,
            ),
            flush=True,
        )

    mean = sum(scores) / len(scores) if scores else 0.0
    payload = {
        "suite": "delivery_qc_judgment",
        "metric": "mean_classification_accuracy",
        "threshold": THRESHOLD,
        "mean_classification_accuracy": mean,
        "n": len(rows),
        "pass": mean >= THRESHOLD,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "delivery_qc_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "delivery_qc_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
