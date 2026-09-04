"""Shared finding-schema validation for all specialist agents (H-1b..H-1e).

The gate between a model response and the pipeline is deterministic code:
non-empty claims with evidence refs, bounded confidence, actions restricted
to the live H-0 command registry, explicit reversibility, non-negative
integer cost, case_id echo. Anything else raises (C-1.1 fail loud).
"""

from __future__ import annotations

from typing import Any

from backend.approvals.commands import default_registry
from backend.supervisor.case import Claim, Finding, ProposedAction

CONFIDENCES = {"low", "medium", "high"}

# H-0 default_registry command vocabulary — proposed actions must name one
# of these; validation enforces it against the live registry.
REGISTRY_COMMANDS: tuple[str, ...] = (
    "pause_intake",
    "resume_intake",
    "retry_job",
    "lock_shot",
    "unlock_shot",
    "add_to_continuity",
    "remove_from_continuity",
)


def validate_claims(payload: dict[str, Any]) -> list[Claim]:
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("finding must carry at least one claim (evidence or nothing)")
    claims: list[Claim] = []
    for raw in raw_claims:
        if not isinstance(raw, dict):
            raise ValueError("claim must be an object")
        text = str(raw.get("text") or "").strip()
        evidence_ref = str(raw.get("evidence_ref") or "").strip()
        confidence = raw.get("confidence")
        if not text or not evidence_ref:
            raise ValueError("claim needs non-empty text and evidence_ref")
        if confidence not in CONFIDENCES:
            raise ValueError(
                f"claim confidence must be low|medium|high, got {confidence!r}"
            )
        claims.append(
            Claim(text=text, evidence_ref=evidence_ref, confidence=confidence)
        )
    return claims


def validate_actions(payload: dict[str, Any]) -> list[ProposedAction]:
    actions: list[ProposedAction] = []
    raw_actions = payload.get("proposed_actions") or []
    if not isinstance(raw_actions, list):
        raise ValueError("proposed_actions must be a list")
    for raw in raw_actions:
        if not isinstance(raw, dict):
            raise ValueError("proposed action must be an object")
        name = str(raw.get("command_name") or "")
        if default_registry.get(name) is None:
            raise ValueError(
                f"proposed command {name!r} is not in the H-0 registry; "
                f"allowed: {list(REGISTRY_COMMANDS)}"
            )
        reversible = raw.get("reversible")
        if not isinstance(reversible, bool):
            raise ValueError("proposed action needs an explicit boolean 'reversible'")
        cost = raw.get("cost_estimate_micros")
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
            raise ValueError("cost_estimate_micros must be a non-negative integer")
        args = raw.get("args")
        if not isinstance(args, dict):
            raise ValueError("proposed action args must be an object")
        actions.append(
            ProposedAction(
                command_name=name,
                args=args,
                cost_estimate_micros=cost,
                reversible=reversible,
            )
        )
    return actions


def validate_finding_payload(payload: Any, *, case_id: str, specialist: str) -> Finding:
    """Deterministic gate for a plain finding payload."""
    if not isinstance(payload, dict):
        raise ValueError("finding payload must be a JSON object")
    if payload.get("case_id") != case_id:
        raise ValueError(
            f"case_id mismatch: payload {payload.get('case_id')!r} != case {case_id!r}"
        )
    return Finding(
        specialist=specialist,
        case_id=case_id,
        claims=validate_claims(payload),
        proposed_actions=validate_actions(payload),
    )
