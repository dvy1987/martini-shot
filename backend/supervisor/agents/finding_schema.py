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
    "extend_shot",
)

# Target contract per command (ACT-gate review fix: action correctness is
# deterministic at the gate, not a prompt hope). An action whose args lack
# these non-empty values is rejected before it can ever rank or dispatch.
REQUIRED_ACTION_ARGS: dict[str, tuple[str, ...]] = {
    "retry_job": ("job_id",),
    "lock_shot": ("shot_id",),
    "unlock_shot": ("shot_id",),
    "add_to_continuity": ("shot_id", "alternate_id"),
    "remove_from_continuity": ("shot_id", "alternate_id"),
    "pause_intake": ("station",),
    "resume_intake": ("station",),
    "extend_shot": ("shot_id", "project_id", "source_uri"),
}


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


def validate_actions(
    payload: dict[str, Any],
    claims: list[Claim] | None = None,
    *,
    subject_job_id: str | None = None,
    subject_station: str | None = None,
) -> list[ProposedAction]:
    """Parse proposed_actions. When the finding's claims are supplied, each
    action's supporting_evidence_refs are validated against them (ACT-gate
    review fix 1): every declared ref must cite a claim in the SAME finding.
    An action that declares no refs is legal but conservative — the verdict
    filter treats it as depending on the whole finding.

    subject_job_id: the case's investigated job. A job-scoped action with a
    missing job_id binds to it deterministically (structural target, not
    model guesswork); any other target must be explicit or the gate refuses."""
    claim_refs = {c.evidence_ref for c in (claims or [])}
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
        # Structural target binding: the case's own subject is the target of
        # an action whose args the model left empty. Anything else must be
        # explicit (review fix: action correctness at the gate).
        if not str(args.get("job_id") or "").strip() and subject_job_id:
            if name == "retry_job":
                args = {**args, "job_id": subject_job_id}
        if (
            name in ("pause_intake", "resume_intake")
            and not str(args.get("station") or "").strip()
            and subject_station
        ):
            args = {**args, "station": subject_station}
        raw_refs = raw.get("supporting_evidence_refs") or []
        if not isinstance(raw_refs, list) or any(
            not isinstance(ref, str) or not ref.strip() for ref in raw_refs
        ):
            raise ValueError(
                "supporting_evidence_refs must be a list of non-empty strings"
            )
        supporting = tuple(dict.fromkeys(ref.strip() for ref in raw_refs))
        if claims is not None:
            unknown = [ref for ref in supporting if ref not in claim_refs]
            if unknown:
                raise ValueError(
                    f"supporting_evidence_refs cite claims outside this finding: "
                    f"{unknown}"
                )
        missing = [
            key
            for key in REQUIRED_ACTION_ARGS.get(name, ())
            if not str(args.get(key) or "").strip()
        ]
        if missing:
            raise ValueError(
                f"proposed {name!r} args missing required target keys: {missing} "
                f"(args must identify the exact target from the case evidence)"
            )
        actions.append(
            ProposedAction(
                command_name=name,
                args=args,
                cost_estimate_micros=cost,
                reversible=reversible,
                supporting_evidence_refs=supporting,
            )
        )
    return actions


def validate_finding_payload(
    payload: Any,
    *,
    case_id: str,
    specialist: str,
    subject_job_id: str | None = None,
    subject_station: str | None = None,
) -> Finding:
    """Deterministic gate for a plain finding payload."""
    if not isinstance(payload, dict):
        raise ValueError("finding payload must be a JSON object")
    if payload.get("case_id") != case_id:
        raise ValueError(
            f"case_id mismatch: payload {payload.get('case_id')!r} != case {case_id!r}"
        )
    claims = validate_claims(payload)
    return Finding(
        specialist=specialist,
        case_id=case_id,
        claims=claims,
        proposed_actions=validate_actions(
            payload,
            claims,
            subject_job_id=subject_job_id,
            subject_station=subject_station,
        ),
    )
