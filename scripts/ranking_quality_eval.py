#!/usr/bin/env python
"""Deliberation ranking-quality rubric eval (extended per A9 plan §6 step 8).

Scores the REAL multi-agent pipeline on adversarial dimensions:
- delegation (deterministic): route_specialists matches the expected team.
- conflict: two specialists' findings conflict; the real verifier must veto
  the claim the case evidence rules out, so the correct action ranks.
- stale_evidence: a stale claim is vetoed per-claim; the finding survives
  only with its sound claims.
- abstention: with genuinely insufficient evidence, the real specialist
  proposes NO registry action (and/or says so with low confidence).
- cost_realism: real proposed actions carry a positive, history-plausible
  cost estimate (H-1g watch item: 0-cost estimates make leverage degenerate).

Suite `deliberation_ranking_quality`, threshold mean_case_accuracy >= 0.8
(thresholds.yaml) — this is H-0b's ACT-mode gate. Evidence to
docs/evidence/H-1/ranking_quality_*.json.
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
from backend.supervisor.agents.verification import verify
from backend.supervisor.case import (
    Case,
    Claim,
    Finding,
    ProposedAction,
    route_specialists,
)
from backend.supervisor.deliberation import apply_verdict, rank_actions

DATASET = ROOT / "backend" / "evals" / "datasets" / "deliberation_ranking_quality.jsonl"
EVIDENCE = ROOT / "docs" / "evidence" / "H-1"
THRESHOLD = 0.8


def _case_from_row(row: dict) -> Case:
    return Case(
        case_id=f"{row['id']}-case",
        version=1,
        created_at="2026-09-04T00:00:00.000Z",
        trigger=dict(row["trigger"]),
        evidence={"job": row.get("job") or {}},
    )


def _findings_from_row(row: dict, case: Case) -> list[Finding]:
    return [
        Finding(
            specialist=f["specialist"],
            case_id=case.case_id,
            claims=[
                Claim(
                    text=c["text"],
                    evidence_ref=c["evidence_ref"],
                    confidence=c["confidence"],
                )
                for c in f["claims"]
            ],
            proposed_actions=[
                ProposedAction(
                    command_name=a["command_name"],
                    args=dict(a["args"]),
                    cost_estimate_micros=int(a["cost_estimate_micros"]),
                    reversible=bool(a["reversible"]),
                )
                for a in f["proposed_actions"]
            ],
        )
        for f in row.get("findings") or []
    ]


def score_delegation(row: dict, settings) -> tuple[float, dict]:
    routed = route_specialists(dict(row["trigger"]))
    expected = list(row["expected_specialists"])
    ok = sorted(routed) == sorted(expected)
    return (1.0 if ok else 0.0), {"routed": routed, "expected": expected}


def score_conflict(row: dict, settings) -> tuple[float, dict]:
    case = _case_from_row(row)
    findings = _findings_from_row(row, case)
    verdict = verify(case, findings, settings)
    survivors = apply_verdict(findings, verdict)
    ranked = rank_actions(case, survivors)
    vetoed_refs = {ref for ref, _ in verdict.rejected}
    expected_vetoed = set(row.get("expected_vetoed_refs") or [])
    top = ranked[0]["command_name"] if ranked else None
    details = {
        "vetoed": sorted(vetoed_refs),
        "expected_vetoed": sorted(expected_vetoed),
        "top_command": top,
        "expected_top": row["expected_top_command"],
        "ranked": [r["command_name"] for r in ranked],
    }
    checks = [
        expected_vetoed.issubset(vetoed_refs),
        top == row["expected_top_command"],
        all(
            r["command_name"]
            in {"retry_job", "pause_intake", "lock_shot", "unlock_shot"}
            for r in ranked
        ),
    ]
    return (1.0 if all(checks) else 0.0), details


def score_stale(row: dict, settings) -> tuple[float, dict]:
    case = _case_from_row(row)
    findings = _findings_from_row(row, case)
    verdict = verify(case, findings, settings)
    survivors = apply_verdict(findings, verdict)
    ranked = rank_actions(case, survivors)
    vetoed_refs = {ref for ref, _ in verdict.rejected}
    expected_vetoed = set(row.get("expected_vetoed_refs") or [])
    stale_ref = next(iter(expected_vetoed))
    # The stale claim's actions must never rank via that claim's evidence.
    stale_action_ranks = any(
        stale_ref in (r.get("evidence_refs") or []) for r in ranked
    )
    sound_survived = any(
        claim.evidence_ref != stale_ref for f in survivors for claim in f.claims
    )
    details = {
        "vetoed": sorted(vetoed_refs),
        "expected_vetoed": sorted(expected_vetoed),
        "stale_action_ranks": stale_action_ranks,
        "sound_claim_survived": sound_survived,
    }
    checks = [
        expected_vetoed.issubset(vetoed_refs),
        not stale_action_ranks,
        sound_survived,
    ]
    return (1.0 if all(checks) else 0.0), details


def score_abstention(row: dict, settings) -> tuple[float, dict]:
    case = _case_from_row(row)
    finding = investigate(case, settings)
    claims = [{"text": c.text, "confidence": c.confidence} for c in finding.claims]
    commands = [a.command_name for a in finding.proposed_actions]
    low_confidence = all(c.confidence == "low" for c in finding.claims)
    insufficient_said = any(
        word in c.text.lower()
        for c in finding.claims
        for word in ("insufficient", "no telemetry", "cannot", "unclear", "unknown")
    )
    abstained = (not finding.proposed_actions) or (low_confidence and insufficient_said)
    details = {"commands": commands, "claims": claims, "abstained": abstained}
    return (1.0 if abstained and not commands else 0.0), details


def score_cost(row: dict, settings) -> tuple[float, dict]:
    case = _case_from_row(row)
    finding = investigate(case, settings)
    job = row["job"]
    bounds = row["cost_bounds"]
    cap = float(job["cost_micros"]) * float(bounds["max_multiple_of_history"])
    floor = float(bounds["min_micros"])
    actions = [
        {
            "command_name": a.command_name,
            "cost_estimate_micros": a.cost_estimate_micros,
        }
        for a in finding.proposed_actions
    ]
    estimates = [a.cost_estimate_micros for a in finding.proposed_actions]
    ok = bool(estimates) and all(floor <= e <= cap for e in estimates)
    return (1.0 if ok else 0.0), {"actions": actions, "cap_micros": cap}


SCORERS = {
    "delegation": score_delegation,
    "conflict": score_conflict,
    "stale_evidence": score_stale,
    "abstention": score_abstention,
    "cost_realism": score_cost,
}


def main() -> int:
    settings = get_settings()
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: list[dict] = []
    scores: list[float] = []
    for row in rows:
        scorer = SCORERS[row["dimension"]]
        record: dict = {"id": row["id"], "dimension": row["dimension"]}
        try:
            score, details = scorer(row, settings)
            record.update({"ok": True, "score": score, **details})
        except Exception as exc:
            score = 0.0
            record.update(
                {"ok": False, "score": 0.0, "error": f"{type(exc).__name__}: {exc}"}
            )
        scores.append(score)
        records.append(record)
        print(json.dumps(record, indent=2))

    mean = sum(scores) / len(scores) if scores else 0.0
    payload = {
        "suite": "deliberation_ranking_quality",
        "metric": "mean_case_accuracy",
        "threshold": THRESHOLD,
        "mean_case_accuracy": mean,
        "n": len(rows),
        "pass": mean >= THRESHOLD,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ranking_quality_eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "ranking_quality_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
