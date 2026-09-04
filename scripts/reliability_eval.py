#!/usr/bin/env python
"""Reliability Investigator root-cause accuracy eval (H-1b, C-3.3/.4).

Runs the REAL agent (real Gemini call via run_agent_call — billed, pennies;
C-1.1: no mock candidates) over the seeded Stage-1 failure dataset
(backend/evals/datasets/reliability_root_cause.jsonl). Metric:
mean_root_cause_accuracy >= 0.75 (thresholds.yaml). Evidence to docs/evidence/H-1/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.supervisor.agents.reliability_investigator import investigate
from backend.supervisor.case import Case

DATASET = ROOT / "backend" / "evals" / "datasets" / "reliability_root_cause.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "H-1"
THRESHOLD = 0.75


def root_cause_hit(claims: list[dict], row: dict) -> bool:
    """Deterministic judge: the expected root-cause family must appear in a
    claim's text. Separators are normalized ("rate_limited" == "rate
    limiting") and rows may list alias phrasings for the same failure family
    — the judge scores the diagnosis, not the wording."""

    def norm(text: str) -> str:
        return " ".join(str(text).lower().replace("_", " ").replace("-", " ").split())

    candidates = [row["expected_root_cause"], *row.get("root_cause_aliases", [])]
    needles = [norm(c) for c in candidates]
    return any(any(n in norm(c.get("text", "")) for n in needles) for c in claims)


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
            case_id=f"{row['case_id']}-case",
            version=1,
            created_at=row["job"].get("updated_at") or "",
            trigger={
                "kind": row["kind"],
                "job_id": row["job"]["id"],
                "station": row["station"],
            },
            evidence={"job": row["job"]},
        )
        record: dict = {
            "case_id": row["case_id"],
            "expected_root_cause": row["expected_root_cause"],
        }
        try:
            finding = investigate(case, settings)
            claims = [
                {
                    "text": c.text,
                    "evidence_ref": c.evidence_ref,
                    "confidence": c.confidence,
                }
                for c in finding.claims
            ]
            commands = [a.command_name for a in finding.proposed_actions]
            record.update(
                {
                    "ok": True,
                    "score": 1.0 if root_cause_hit(claims, row) else 0.0,
                    "claims": claims,
                    "proposed_commands": commands,
                    "expected_action": row["expected_action"],
                }
            )
            scores.append(float(record["score"]))
        except Exception as exc:
            record.update(
                {"ok": False, "score": 0.0, "error": f"{type(exc).__name__}: {exc}"}
            )
            scores.append(0.0)
        records.append(record)

    mean = sum(scores) / len(scores) if scores else 0.0
    payload = {
        "suite": "reliability_root_cause",
        "metric": "mean_root_cause_accuracy",
        "threshold": THRESHOLD,
        "mean_root_cause_accuracy": mean,
        "n": len(rows),
        "pass": mean >= THRESHOLD,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "reliability_root_cause_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "reliability_root_cause_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
