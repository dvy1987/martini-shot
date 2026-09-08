"""Continuity specialist (H-1h): maps the station agent's cut decision
into a ranked H-0 finding the supervisor can spend.

Owner ruling 2026-09-08: add/remove from the cut are inside the night
envelope. The station agent judges; this wrapper copies shot_id and
alternate_id from real evidence so the action can dispatch.
"""

from __future__ import annotations

from typing import Any

from backend.core.config import Settings
from backend.supervisor.case import CONTINUITY, Case, Claim, Finding, ProposedAction
from backend.supervisor.station_agents.base import StationDecision
from backend.supervisor.station_agents.continuity import (
    decide_continuity,
    draft_clears_bars,
)

_IN_CUT = frozenset({"continuity", "in_continuity"})
_RETRY_FALLBACK_MICROS = 1_000_000


def _shot_id(job: dict[str, Any], ctx: dict[str, Any]) -> str:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    return str(result.get("shot_id") or ctx.get("shot_id") or "")


def _alternate_for_add(job: dict[str, Any], ctx: dict[str, Any]) -> str:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    if result.get("alternate_id"):
        return str(result["alternate_id"])
    for alternate in ctx.get("alternates") or []:
        if alternate.get("status") == "draft" and draft_clears_bars(alternate):
            return str(alternate.get("alternate_id") or "")
    return ""


def _alternate_for_remove(job: dict[str, Any], ctx: dict[str, Any]) -> str:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    if result.get("retire_alternate_id"):
        return str(result["retire_alternate_id"])
    if ctx.get("current_alternate_id"):
        return str(ctx["current_alternate_id"])
    for alternate in ctx.get("alternates") or []:
        if str(alternate.get("status") or "") in _IN_CUT:
            return str(alternate.get("alternate_id") or "")
    return ""


def load_alternates_context(
    store: Any,
    job: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prefer the case's already-fetched continuity state; otherwise read
    the live shot + alternates. Missing store/shot is recorded as empty."""
    ctx = dict(existing or {})
    if ctx.get("alternates") is not None or ctx.get("shot_id"):
        return ctx
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    shot_id = str(result.get("shot_id") or "")
    if not shot_id or store is None:
        return {"shot_id": shot_id or None, "locked": False, "alternates": []}
    from backend.shots import lifecycle as shots

    shot = shots.get_shot(store, shot_id) or {}
    alts = shots.list_alternates(store, shot_id)
    return {
        "shot_id": shot_id,
        "locked": bool(shot.get("locked")),
        "current_alternate_id": shot.get("current_alternate_id"),
        "alternates": [
            {
                "alternate_id": row.get("alternate_id") or row.get("id"),
                "status": row.get("status"),
                "eval_scores": row.get("eval_scores") or {},
            }
            for row in alts
        ],
    }


def finding_from_decision(
    case: Case,
    decision: StationDecision,
    job: dict[str, Any],
    ctx: dict[str, Any],
) -> Finding:
    """Deterministic map: station decision → H-0 ProposedAction with ids."""
    job_id = str(
        job.get("id") or job.get("job_id") or case.evidence.get("job_id") or ""
    )
    shot_id = _shot_id(job, ctx)
    evidence_ref = f"job://{job_id}" if job_id else f"case://{case.case_id}"
    claims = [
        Claim(
            text=decision.reason or f"continuity chose {decision.decision}",
            evidence_ref=evidence_ref,
            confidence=decision.confidence,
        )
    ]
    actions: list[ProposedAction] = []
    if decision.decision == "add_to_continuity":
        alternate_id = _alternate_for_add(job, ctx)
        if shot_id and alternate_id:
            actions.append(
                ProposedAction(
                    command_name="add_to_continuity",
                    args={"shot_id": shot_id, "alternate_id": alternate_id},
                    cost_estimate_micros=0,
                    reversible=True,
                    supporting_evidence_refs=(evidence_ref,),
                )
            )
    elif decision.decision == "remove_from_continuity":
        alternate_id = _alternate_for_remove(job, ctx)
        if shot_id and alternate_id:
            actions.append(
                ProposedAction(
                    command_name="remove_from_continuity",
                    args={"shot_id": shot_id, "alternate_id": alternate_id},
                    cost_estimate_micros=0,
                    reversible=True,
                    supporting_evidence_refs=(evidence_ref,),
                )
            )
    elif decision.decision == "retry_job" and job_id:
        try:
            cost = int(job.get("cost_micros") or 0)
        except (TypeError, ValueError):
            cost = 0
        actions.append(
            ProposedAction(
                command_name="retry_job",
                args={"job_id": job_id},
                cost_estimate_micros=cost or _RETRY_FALLBACK_MICROS,
                reversible=True,
                supporting_evidence_refs=(evidence_ref,),
            )
        )
    return Finding(
        specialist=CONTINUITY,
        case_id=case.case_id,
        claims=claims,
        proposed_actions=actions,
    )


def investigate(
    case: Case,
    settings: Settings,
    store: Any = None,
    jobs_collection: str = "pc-jobs",
) -> Finding:
    """One live continuity judgment, then a typed finding. Fail loud."""
    del jobs_collection  # case.evidence already carries the job baseline
    job = dict(case.evidence.get("job") or {})
    ctx = load_alternates_context(
        store, job, dict(case.evidence.get("alternates_context") or {})
    )
    decision, _cost = decide_continuity(settings, job=job, alternates_context=ctx)
    return finding_from_decision(case, decision, job, ctx)
