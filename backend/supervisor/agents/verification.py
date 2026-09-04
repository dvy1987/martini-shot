"""H-1e — Verification agent: feeds the hard filter (plan §0.4).

Reviews every specialist finding against the case evidence and vetoes
claims that contradict their own cited evidence or draw unsupported
conclusions. Vetoes are HARD: apply_verdict (deliberation.py) drops vetoed
claims outright and a finding left claimless is excluded — never a
down-weight. Specialist approval is computed deterministically from the
rejected set (a specialist survives iff it keeps at least one claim), so
the model never hand-picks winners.

Same guarantees as the other specialists: one instrumented call site,
read-only tools only, deterministic validation that fails loud (C-1.1) —
including the phantom-veto guard (cannot veto a claim that does not exist).
Judgment quality is EDD: backend/evals/datasets/verification_veto.jsonl
(plausible-but-wrong adversarial findings), threshold mean_veto_accuracy
>= 0.8 (C-3.4).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from backend.core.config import Settings
from backend.supervisor.case import Case, Finding, Verdict
from backend.supervisor.otel_ai import run_agent_call

VERIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "string"},
        "decision": {"type": "string", "enum": ["approve", "veto"]},
        "overall_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rejected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "evidence_ref": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "description": "why the claim does not survive its own evidence",
                    },
                },
                "required": ["evidence_ref", "reason"],
            },
        },
    },
    "required": ["case_id", "decision", "overall_confidence", "rejected"],
}

PERSONA = "verification_agent"


def validate_verdict_payload(
    payload: Any, *, case_id: str, findings: list[Finding]
) -> Verdict:
    """Deterministic gate: enums, non-empty reasons, NO phantom vetoes
    (every rejected evidence_ref must exist among the findings' claims),
    and specialist approval computed from the rejected set."""
    if not isinstance(payload, dict):
        raise ValueError("verdict payload must be a JSON object")
    if payload.get("case_id") != case_id:
        raise ValueError(
            f"case_id mismatch: payload {payload.get('case_id')!r} != case {case_id!r}"
        )
    decision = payload.get("decision")
    if decision not in ("approve", "veto"):
        raise ValueError(f"decision must be approve|veto, got {decision!r}")
    confidence = payload.get("overall_confidence")
    if confidence not in ("low", "medium", "high"):
        raise ValueError(
            f"overall_confidence must be low|medium|high, got {confidence!r}"
        )
    raw_rejected = payload.get("rejected")
    if not isinstance(raw_rejected, list):
        raise ValueError("rejected must be a list")
    allowed_refs = known_refs(findings)
    rejected: list[tuple[str, str]] = []
    for raw in raw_rejected:
        if not isinstance(raw, dict):
            raise ValueError("rejected item must be an object")
        ref = str(raw.get("evidence_ref") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if not ref or not reason:
            raise ValueError("rejected entries need non-empty evidence_ref and reason")
        if ref not in allowed_refs:
            raise ValueError(
                f"phantom veto: evidence_ref {ref!r} does not exist in any finding claim"
            )
        rejected.append((ref, reason))
    approved = _approved_specialists(findings, {ref for ref, _ in rejected})
    return Verdict(
        case_id=case_id,
        rejected=rejected,
        approved_specialists=approved,
        overall_confidence=confidence,  # type: ignore[arg-type]
    )


def known_refs(findings: list[Finding]) -> set[str]:
    """Every claim evidence_ref the verifier is allowed to veto."""
    return {claim.evidence_ref for f in findings for claim in f.claims}


def _approved_specialists(
    findings: list[Finding], rejected_refs: set[str]
) -> list[str]:
    """Deterministic: a specialist is approved iff it keeps at least one
    claim (the hard filter semantics — never model discretion)."""
    approved: list[str] = []
    for f in findings:
        if any(claim.evidence_ref not in rejected_refs for claim in f.claims):
            approved.append(f.specialist)
    return sorted(set(approved))


def build_verification_prompt(case: Case, findings: list[Finding]) -> str:
    """Deterministic brief: the case evidence + every claim with its cited
    evidence_ref. The verifier judges claims against evidence, nothing else."""
    claims_block = []
    for finding in findings:
        claims_block.append(
            json.dumps(
                {
                    "specialist": finding.specialist,
                    "claims": [
                        {
                            "text": c.text,
                            "evidence_ref": c.evidence_ref,
                            "confidence": c.confidence,
                        }
                        for c in finding.claims
                    ],
                    "proposed_actions": [
                        {
                            "command_name": a.command_name,
                            "args": a.args,
                            "cost_estimate_micros": a.cost_estimate_micros,
                            "reversible": a.reversible,
                        }
                        for a in finding.proposed_actions
                    ],
                },
                indent=2,
            )
        )
    return f"""You are the Verification agent on the Martini Shot post-production
pipeline. Your verdict feeds a HARD filter: a claim you veto is dropped
outright and never reaches the action ranking — there is no down-weighting.

CASE {case.case_id} (version {case.version})
TRIGGER:
{json.dumps(case.trigger, indent=2, default=str)}

CASE EVIDENCE (the ground truth claims must survive):
{json.dumps(case.evidence, indent=2, default=str)}

FINDINGS UNDER REVIEW (specialist claims, each with its cited evidence_ref):
{chr(10).join(claims_block)}

VETO a claim when its text CONTRADICTS the case evidence (any of it,
including the finding's other claims and their refs) or asserts something
the evidence affirmatively rules out. Do NOT veto a claim merely because
its single cited ref is incomplete: sound inference from consistent case
evidence is approval, not a veto. Reserve vetoes for actual contradictions
(wrong numbers, misread fields, invented causes). You may ONLY veto
evidence_refs that appear in the findings above. Give a concrete reason
per veto. Approve claims that honestly reflect their evidence. Rate
overall_confidence by how directly the surviving evidence supports the case.

Respond with JSON matching the required schema: case_id (echo), decision
(approve if nothing is vetoed, veto otherwise), overall_confidence,
rejected (list of {{evidence_ref, reason}} — empty when approving)."""


def verify(
    case: Case,
    findings: list[Finding],
    settings: Settings,
    *,
    connector: Any = None,
) -> Verdict:
    """One real Gemini verification pass over all findings. Malformed or
    phantom vetoes raise (fail loud, C-1.1). Signature matches the
    deliberation cycle's verifier injection point."""
    tools: tuple[Callable[..., Any], ...] = ()
    if connector is not None:
        from backend.supervisor.agents.reliability_investigator import (
            read_only_grafana_tools,
        )

        tools = read_only_grafana_tools(connector)
    raw = run_agent_call(
        settings,
        build_verification_prompt(case, findings),
        span_name="specialist.verification",
        persona=PERSONA,
        tools=tools,
        response_schema=VERIFICATION_SCHEMA,
    )
    payload = json.loads(raw["text"])
    return validate_verdict_payload(payload, case_id=case.case_id, findings=findings)
