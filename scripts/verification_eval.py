#!/usr/bin/env python
"""Verification veto eval (H-1e, C-3.3/.4).

For each adversarial case in verification_veto.jsonl, builds the REAL case
evidence and findings deterministically, runs the REAL Verification agent
(billed Gemini call, C-1.1), and scores: does the decision match the
expected one, and (on veto) does the rejected set cover the expected
evidence_ref? Metric: mean_veto_accuracy >= 0.8 (thresholds.yaml).
Evidence: docs/evidence/H-1/verification_veto_eval.jsonl + _summary.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.supervisor.agents.verification import verify
from backend.supervisor.case import Case, Claim, Finding, ProposedAction

DATASET = ROOT / "backend" / "evals" / "datasets" / "verification_veto.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "H-1"
THRESHOLD = 0.8


def build_finding(spec: dict, case_id: str) -> Finding:  # type: ignore[type-arg]
    return Finding(
        specialist=spec["specialist"],
        case_id=case_id,
        claims=[
            Claim(
                text=c["text"],
                evidence_ref=c["evidence_ref"],
                confidence=c["confidence"],
            )
            for c in spec["claims"]
        ],
        proposed_actions=[
            ProposedAction(
                command_name=a["command_name"],
                args=a["args"],
                cost_estimate_micros=a["cost_estimate_micros"],
                reversible=a["reversible"],
            )
            for a in spec.get("proposed_actions", [])
        ],
    )


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
        case = Case(
            case_id=f"{row['id']}-case",
            version=1,
            created_at="",
            trigger=row["trigger"],
            evidence=row["case_evidence"],
        )
        findings = [build_finding(spec, case.case_id) for spec in row["findings"]]
        record: dict = {
            "id": row["id"],
            "case": row["case"],
            "expected_decision": row["expected_decision"],
            "expected_rejected_refs": row["expected_rejected_refs"],
        }
        try:
            verdict = verify(case, findings, settings)
            decision = "approve" if not verdict.rejected else "veto"
            rejected_refs = [ref for ref, _ in verdict.rejected]
            covered = all(ref in rejected_refs for ref in row["expected_rejected_refs"])
            ok = (decision == row["expected_decision"]) and (
                decision != "veto" or covered
            )
            record.update(
                {
                    "ok": True,
                    "decision": decision,
                    "rejected": [
                        {"evidence_ref": ref, "reason": reason}
                        for ref, reason in verdict.rejected
                    ],
                    "score": 1.0 if ok else 0.0,
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
                {k: record.get(k) for k in ("id", "decision", "score", "error")},
                indent=None,
            ),
            flush=True,
        )

    mean = sum(scores) / len(scores) if scores else 0.0
    payload = {
        "suite": "verification_veto",
        "metric": "mean_veto_accuracy",
        "threshold": THRESHOLD,
        "mean_veto_accuracy": mean,
        "n": len(rows),
        "pass": mean >= THRESHOLD,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "verification_veto_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "verification_veto_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
