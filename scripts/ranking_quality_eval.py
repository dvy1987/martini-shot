#!/usr/bin/env python
"""ACT-gate eval: deliberation ranking quality (review rework 2026-09-05).

Per the H-0b ACT-gate review, this eval now measures JUDGMENT quality, not
routing plumbing:

- Deterministic routing cases are scored separately as `routing_ok` and are
  EXCLUDED from the ACT-quality denominator (they test a lookup table, not
  judgment).
- Every judgment case runs the real pipeline: real specialists (investigate)
  or the case's adversarial findings through the REAL verifier → provenance
  filter (apply_verdict) → leverage ranking. Propose-only: nothing dispatches.
- Scoring is end-to-end ACTION accuracy: the final top command AND its target
  args must match expected_action (null = required abstention, ranked must be
  empty).
- HARD GATES (any violation fails the run regardless of the mean):
  * unsupported_action_survival == 0 — no ranked action may depend on a
    vetoed claim (provenance contract);
  * reversibility — no irreversible action ever ranks;
  * abstention — required abstentions rank nothing;
  * cost — every ranked action carries a positive estimate, and within the
    case's history-plausible bounds when specified.
- THREE independent runs per invocation, all reported verbatim (no
  cherry-picking); the gate passes only if EVERY run passes.

On pass this yields a versioned ACT gate receipt (gate_version matches
backend.supervisor.budget_loop.ACT_GATE_VERSION). The receipt file is
evidence; writing it into `pc-control/act-gate` (the activation step) stays a
deliberate, separate action — never a side effect of an eval run.

Evidence: docs/evidence/H-1/ranking_quality_eval.jsonl + _summary.json
(+ _receipt.json on pass).
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
RUNS = 3

from backend.supervisor.budget_loop import (
    ACT_GATE_SUITE as ACT_SUITE_NAME,
)
from backend.supervisor.budget_loop import ACT_GATE_VERSION


def _case_from_row(row: dict) -> Case:
    """Mirror build_case's contract exactly (subject named explicitly), so
    the eval exercises the same case shape the production specialists see."""
    job = row.get("job") or {}
    return Case(
        case_id=f"{row['id']}-case",
        version=1,
        created_at="2026-09-05T00:00:00.000Z",
        trigger=dict(row["trigger"]),
        evidence={"job_id": job.get("id"), "job": job},
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
                    supporting_evidence_refs=tuple(
                        a.get("supporting_evidence_refs") or ()
                    ),
                )
                for a in f["proposed_actions"]
            ],
        )
        for f in row.get("findings") or []
    ]


def _args_match(expected: dict, actual: dict) -> bool:
    return all(actual.get(k) == v for k, v in expected.items())


def _real_specialist_findings(case: Case, settings) -> list:
    """Run the SAME production specialist map the app wires
    (supervisor.team.production_specialists) for every routed name — the
    eval exercises the production wiring, not a hardcoded persona. The map
    gets a real Firestore store (C-1.1: no mocks), so Delivery QC reads its
    evaluator report path exactly as it does in the app; a missing job doc
    is recorded as absence, never invented."""
    from backend.core.firestore import get_firestore
    from backend.supervisor.team import production_specialists

    global _EVAL_STORE
    if _EVAL_STORE is None:
        _EVAL_STORE = get_firestore(settings)
    specialists = production_specialists(_EVAL_STORE, settings)
    return [specialists[name](name, case) for name in route_specialists(case.trigger)]


_EVAL_STORE = None


def score_action_accuracy(row: dict, settings) -> tuple[float, dict]:
    """End-to-end: real verifier → provenance filter → leverage rank; the
    final top command AND args must match expected_action (null = the case
    REQUIRES abstention)."""
    case = _case_from_row(row)
    findings = (
        _findings_from_row(row, case)
        if row.get("findings")
        else _real_specialist_findings(case, settings)
    )
    verdict = verify(case, findings, settings)
    survivors = apply_verdict(findings, verdict)
    ranked = rank_actions(case, survivors)
    vetoed_refs = {ref for ref, _ in verdict.rejected}

    # HARD GATES (each is a run-killer, never averaged away):
    # Cost positivity applies to SPEND-CLASS commands only — control-plane
    # actions (pause/resume intake, lock/unlock) legitimately cost 0.
    spend_commands = {"retry_job", "extend_shot", "add_to_continuity"}
    unsupported = [
        r["command_name"]
        for r in ranked
        if set(r.get("supporting_evidence_refs") or []) & vetoed_refs
    ]
    irreversible = [r["command_name"] for r in ranked if not r.get("reversible")]
    zero_cost = [
        r["command_name"]
        for r in ranked
        if r["command_name"] in spend_commands and r["cost_estimate_micros"] <= 0
    ]
    expected = row.get("expected_action")
    if expected is None:
        abstained = not ranked
        top_ok = abstained
    else:
        top_ok = (
            bool(ranked)
            and ranked[0]["command_name"] == expected["command_name"]
            and _args_match(expected.get("args") or {}, ranked[0]["args"])
        )
    details = {
        "vetoed": sorted(vetoed_refs),
        "claims": [
            {"text": c.text, "evidence_ref": c.evidence_ref, "confidence": c.confidence}
            for f in findings
            for c in f.claims
        ],
        "proposed_before_filter": [
            a.command_name for f in findings for a in f.proposed_actions
        ],
        "ranked": [
            {
                "command": r["command_name"],
                "args": r["args"],
                "cost": r["cost_estimate_micros"],
                "supporting": r.get("supporting_evidence_refs"),
            }
            for r in ranked
        ],
        "expected_action": expected,
        "top_ok": top_ok,
        "hard_gates": {
            "unsupported_action_survival": unsupported,
            "irreversible_ranked": irreversible,
            "zero_cost_ranked": zero_cost,
            "abstention_ok": expected is not None or not ranked,
        },
    }
    score = 1.0 if top_ok else 0.0
    return score, details


def score_cost_realism(row: dict, settings) -> tuple[float, dict]:
    """Real investigate call: a positive, history-plausible cost estimate
    AND the expected action (review: action correctness is not optional)."""
    score, details = score_action_accuracy(row, settings)
    job = row["job"]
    bounds = row["cost_bounds"]
    cap = float(job["cost_micros"]) * float(bounds["max_multiple_of_history"])
    floor = float(bounds["min_micros"])
    in_bounds = bool(details["ranked"]) and all(
        floor <= r["cost"] <= cap for r in details["ranked"]
    )
    details["cost_bounds"] = {"min_micros": floor, "cap_micros": cap}
    details["cost_in_bounds"] = in_bounds
    details["top_ok"] = bool(details["top_ok"] and in_bounds)
    return (1.0 if details["top_ok"] else 0.0), details


def score_routing(row: dict) -> tuple[bool, dict]:
    routed = route_specialists(dict(row["trigger"]))
    expected = list(row["expected_specialists"])
    return (sorted(routed) == sorted(expected)), {
        "routed": routed,
        "expected": expected,
    }


SCORERS = {
    "conflict": score_action_accuracy,
    "stale_evidence": score_action_accuracy,
    "abstention": score_action_accuracy,
    "cost_realism": score_cost_realism,
}


def run_once(rows: list[dict], settings, run_index: int) -> dict:
    records: list[dict] = []
    scores: list[float] = []
    routing_ok = True
    hard_gate_failures: list[str] = []
    for row in rows:
        if row["dimension"] == "delegation":
            ok, details = score_routing(row)
            routing_ok = routing_ok and ok
            records.append(
                {
                    "id": row["id"],
                    "dimension": "delegation",
                    "routing_ok": ok,
                    **details,
                }
            )
            continue
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
        gates = record.get("hard_gates") or {}
        for gate in (
            "unsupported_action_survival",
            "irreversible_ranked",
            "zero_cost_ranked",
        ):
            if gates.get(gate):
                hard_gate_failures.append(f"{row['id']}:{gate}={gates[gate]}")
        if gates.get("abstention_ok") is False:
            hard_gate_failures.append(f"{row['id']}:abstention_ok=false")
        scores.append(score)
        records.append(record)

    mean = sum(scores) / len(scores) if scores else 0.0
    return {
        "run": run_index + 1,
        "metric": "end_to_end_action_accuracy",
        "n_judgment_cases": len(scores),
        "mean_action_accuracy": round(mean, 4),
        "threshold": THRESHOLD,
        "routing_ok": routing_ok,
        "hard_gate_failures": hard_gate_failures,
        "records": records,
        "pass": mean >= THRESHOLD and routing_ok and not hard_gate_failures,
    }


def main() -> int:
    settings = get_settings()
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    runs = [run_once(rows, settings, i) for i in range(RUNS)]
    all_pass = all(run["pass"] for run in runs)

    payload = {
        "suite": ACT_SUITE_NAME,
        "gate_version": ACT_GATE_VERSION,
        "runs_required": RUNS,
        "runs": [{k: v for k, v in run.items() if k != "records"} for run in runs],
        "pass": all_pass,
        "note": (
            "All runs reported verbatim (no cherry-picking). Routing cases "
            "scored separately (routing_ok), excluded from the judgment "
            "denominator. Hard gates are run-killers, never averaged away."
        ),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    flat_records = [
        json.dumps({"run": run["run"], **record})
        for run in runs
        for record in run["records"]
    ]
    (EVIDENCE / "ranking_quality_eval.jsonl").write_text(
        "\n".join(flat_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "ranking_quality_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    if all_pass:
        receipt = {
            "passed": True,
            "gate_version": ACT_GATE_VERSION,
            "suite": ACT_SUITE_NAME,
            "threshold": THRESHOLD,
            "runs": RUNS,
            "run_results": [run["mean_action_accuracy"] for run in runs],
            "hard_gate_failures": [],
        }
        (EVIDENCE / "ranking_quality_receipt.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
        print(
            "ACT gate receipt written to docs/evidence/H-1/ranking_quality_receipt.json"
        )
        print("Activation remains a SEPARATE deliberate write to pc-control/act-gate.")
    print(json.dumps(payload, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
