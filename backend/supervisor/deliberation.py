"""Deliberation orchestrator (H-1a, Amendment A9).

One cycle: build_case → route_specialists → parallel specialist Findings →
Verification hard-filter → synthesis ranking → persist `pc-deliberations`
(+ best-effort Grafana annotation). Runs as a background job only (C-6.5) —
never inline in an HTTP request.

H-1a scope: the control flow is real and tested; specialist PERSONAS are
stand-in callables injected by the caller (H-1b..H-1e replace them). The
stand-in verifier accepts everything except non-reversible actions, which
the hard filter excludes by the owner's standing rule; the stand-in
synthesizer ranks by the H-0b leverage formula (unblocks per cost).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict
from typing import Any, Callable

from backend.approvals.machine import propose_approval
from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso
from backend.supervisor.case import (
    Case,
    Claim,
    Finding,
    Verdict,
    build_case,
    route_specialists,
)

log = logging.getLogger("pc.deliberation")

DELIBERATIONS = "pc-deliberations"

SpecialistFn = Callable[[str, Case], Finding]
SpecialistMap = dict[str, SpecialistFn]


def apply_verdict(findings: list[Finding], verdict: Verdict) -> list[Finding]:
    """HARD filter (plan §0.4): rejected specialists are excluded outright;
    rejected CLAIMS are dropped individually; a finding left with no
    surviving claims is excluded. Never a down-weight."""
    rejected_refs = {ref for ref, _reason in verdict.rejected}
    survivors: list[Finding] = []
    for finding in findings:
        if finding.specialist not in verdict.approved_specialists:
            continue
        kept_claims = [c for c in finding.claims if c.evidence_ref not in rejected_refs]
        if not kept_claims:
            continue
        survivors.append(
            Finding(
                specialist=finding.specialist,
                case_id=finding.case_id,
                claims=kept_claims,
                proposed_actions=list(finding.proposed_actions),
            )
        )
    return survivors


def _default_verifier(case: Case, findings: list[Finding]) -> Verdict:
    """Stand-in until H-1e: admits every specialist, but non-reversible
    proposed actions are excluded outright (owner's standing reversibility
    rule from H-0b)."""
    approved = sorted({f.specialist for f in findings})
    return Verdict(
        case_id=case.case_id,
        rejected=[],
        approved_specialists=approved,
        overall_confidence="medium",
    )


def rank_actions(case: Case, findings: list[Finding]) -> list[dict[str, Any]]:
    """H-0b step 3 leverage formula, unchanged: unblocks-weight per micro,
    reversibility as a hard exclusion, negative/garbage cost excluded."""
    ranked: list[dict[str, Any]] = []
    for finding in findings:
        for action in finding.proposed_actions:
            if not action.reversible:
                continue
            cost = max(0, int(action.cost_estimate_micros))
            unblocks = 2 if action.command_name == "retry_job" else 1
            leverage = round(unblocks / cost, 6) if cost > 0 else float("inf")
            ranked.append(
                {
                    "command_name": action.command_name,
                    "args": dict(action.args),
                    "cost_estimate_micros": cost,
                    "specialist": finding.specialist,
                    "evidence_refs": [c.evidence_ref for c in finding.claims],
                    "leverage": leverage,
                }
            )
    ranked.sort(key=lambda row: -row["leverage"])
    return ranked


def _stand_in_specialist(name: str, case: Case) -> Finding:
    """Used only when the caller injects no specialist for a routed name
    (never in production paths): proposes nothing, claims only that it read
    the case — visibly low confidence until H-1b..H-1e wire personas."""
    return Finding(
        specialist=name,
        case_id=case.case_id,
        claims=[
            Claim(
                text="stand-in specialist: no persona wired yet (H-1b..H-1e)",
                evidence_ref=f"case://{case.case_id}",
                confidence="low",
            )
        ],
        proposed_actions=[],
    )


async def run_deliberation_cycle(
    trigger: dict[str, Any],
    settings: Settings,
    *,
    store: FirestoreStore,
    jobs_collection: str = "pc-jobs",
    deliberation_col: str = DELIBERATIONS,
    specialists: SpecialistMap | None = None,
    verifier: Callable[[Case, list[Finding]], Verdict] | None = None,
    synthesizer: Callable[[Case, list[Finding], Verdict], dict[str, Any]] | None = None,
    annotator: Callable[[str, list[str]], Any] | None = None,
    on_complete: Callable[[dict[str, Any]], None] | None = None,
    propose: bool = True,
) -> dict[str, Any]:
    """One full cycle. `specialists` maps routed name → finding factory;
    missing names fall back to the stand-in (visible as low confidence)."""
    case = build_case(trigger, store, jobs_collection=jobs_collection)
    # Routing is deterministic over the trigger; when the caller didn't know
    # the station, the case's own job-doc evidence supplies it (real data,
    # not a model call).
    route_trigger = dict(trigger)
    if not route_trigger.get("station"):
        job_evidence = case.evidence.get("job") or {}
        if job_evidence.get("station"):
            route_trigger["station"] = str(job_evidence["station"])
    names = route_specialists(route_trigger)
    fns: SpecialistMap = specialists or {}

    def _invoke(name: str) -> Finding:
        fn = fns.get(name)
        if fn is None:
            return _stand_in_specialist(name, case)
        return fn(name, case)

    findings = list(
        await asyncio.gather(*[asyncio.to_thread(_invoke, name) for name in names])
    )
    verdict = (verifier or _default_verifier)(case, findings)
    filtered = apply_verdict(findings, verdict)
    synthesizer = synthesizer or _default_synthesizer
    recommendation = synthesizer(case, filtered, verdict)

    record: dict[str, Any] = {
        "cycle_id": f"cyc-{uuid.uuid4().hex[:12]}",
        "case_id": case.case_id,
        "case_version": case.version,
        "created_at": utc_now_iso(),
        # H-1f: denormalized for the spine list query (project-scoped lookup).
        "project_id": str(route_trigger.get("project_id") or ""),
        "trigger": route_trigger,
        "specialists": names,
        "findings": [asdict(f) for f in findings],
        "verdict": asdict(verdict),
        "recommendation": recommendation,
        "status": "proposed" if propose else "recorded",
    }
    store.set_doc(deliberation_col, record["cycle_id"], record)
    if on_complete is not None:
        try:
            # H-1f: app.py publishes this as `deliberation.completed` SSE.
            # Best-effort: a hub failure never fails the persisted cycle.
            on_complete(record)
        except Exception:
            log.exception("deliberation on_complete callback failed (cycle persisted)")
    if annotator is not None:
        try:
            annotator(
                f"deliberation cycle_id={record['cycle_id']} case_id={case.case_id} "
                f"trigger={trigger.get('kind')} specialists={','.join(names)} "
                f"actions={len(recommendation.get('ranked_actions', []))}",
                ["martini-shot", "deliberation", str(trigger.get("kind"))],
            )
        except Exception:
            log.exception("deliberation annotation failed (cycle continues)")
    return record


def _default_synthesizer(
    case: Case, findings: list[Finding], verdict: Verdict
) -> dict[str, Any]:
    """Stand-in ranking until H-1b's synthesis persona: the leverage table
    plus provenance, so the wiring is observable before the judgment is."""
    ranked = rank_actions(case, findings)
    return {
        "ranked_actions": ranked,
        "summary": (
            f"{len(findings)} finding(s) survived verification; "
            f"{len(ranked)} reversible action(s) ranked"
        ),
        "specialists": sorted({f.specialist for f in findings}),
        "dissent": [
            f"{spec}: rejected {len([r for r in verdict.rejected])}"
            for spec in sorted({f.specialist for f in findings})
            if verdict.rejected
        ],
    }


def propose_ranked_actions(
    store: FirestoreStore,
    recommendation: dict[str, Any],
    *,
    project_id: str,
    collection: str = "pc-approvals",
) -> list[str]:
    """Turn ranked actions into H-0 approvals (propose-only path; the
    envelope/ACT decision is H-0b's, unchanged)."""
    approval_ids: list[str] = []
    for action in recommendation.get("ranked_actions", []):
        approval_ids.append(
            propose_approval(
                store,
                {
                    "project_id": project_id,
                    "kind": "fix",
                    "title": f"Supervisor proposes {action['command_name']}",
                    "detail": f"evidence: {', '.join(action.get('evidence_refs') or [])}",
                    "command": {
                        "name": action["command_name"],
                        "args": dict(action.get("args") or {}),
                    },
                },
                collection=collection,
            )
        )
    return approval_ids
