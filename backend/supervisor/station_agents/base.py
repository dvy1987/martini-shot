"""StationDecision — the contract between station agents and the pipeline
(A10 design: docs/specs/2026-09-06-agentic-stations-design.md).

Owner ruling baked in: the deterministic verdict rides along as ADVICE —
the agent may take it under advisement and override it, but an override is
always an explicit, logged, first-class fact (`overridden: true` + reason),
and every proposal still routes through H-0 (the agent never executes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.supervisor.agents.finding_schema import REGISTRY_COMMANDS

OPERATOR_NOTES_RULE = (
    "Write reason (or summary) as a short note for a film operator who is "
    "not a coder. In running sentences, cover what you thought the problem "
    "was, what you ignored or left alone, what you changed or kept, and "
    "where you failed — or that this step did not fail. Do not use those "
    "phrases as headings or labels. No rule IDs, error codes, or job numbers."
)


def with_operator_notes(prompt: str) -> str:
    """Append the operator-notes rule once so every station look writes
    the same four facts without repeating the questions."""
    if OPERATOR_NOTES_RULE in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{OPERATOR_NOTES_RULE}"


class StationDecisionError(ValueError):
    """Fail loud: a malformed station-agent response never reaches the
    pipeline (C-1.1)."""


@dataclass(frozen=True)
class StationDecision:
    agent: str
    decision: str
    reason: str
    confidence: str
    deterministic_advice: str
    overridden: bool
    proposal: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_doc(self) -> dict[str, Any]:
        """Persisted onto the job doc / deliberation trail (C-4.2)."""
        return {
            "agent": self.agent,
            "decision": self.decision,
            "reason": self.reason,
            "confidence": self.confidence,
            "deterministic_advice": self.deterministic_advice,
            "overridden": self.overridden,
            "proposal": dict(self.proposal),
        }


def validate_station_decision(
    payload: Any,
    *,
    agent: str,
    allowed_decisions: tuple[str, ...],
    deterministic_suggestion: str = "",
) -> StationDecision:
    """Deterministic gate between the model and the station. Anything not
    matching the contract raises StationDecisionError.

    `deterministic_suggestion` is the CALLER's mapping of the deterministic
    verdict into this station's decision vocabulary (e.g. gate 'pass' →
    'accept'). An agent decision different from it is an explicit override."""
    if not isinstance(payload, dict):
        raise StationDecisionError("station agent payload must be an object")
    if str(payload.get("agent") or "") != agent:
        raise StationDecisionError(
            f"payload agent {payload.get('agent')!r} does not match {agent!r}"
        )
    decision = str(payload.get("decision") or "")
    if decision not in allowed_decisions:
        raise StationDecisionError(
            f"decision {decision!r} outside allowed vocabulary {list(allowed_decisions)}"
        )
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise StationDecisionError("reason is mandatory — no unexplained judgment")
    confidence = str(payload.get("confidence") or "low")
    if confidence not in ("low", "medium", "high"):
        raise StationDecisionError(f"confidence {confidence!r} invalid")
    advice = str(payload.get("deterministic_advice") or "")
    overridden = bool(deterministic_suggestion) and decision != deterministic_suggestion
    if bool(payload.get("overridden")) and not overridden:
        overridden = True  # the agent claims an override — honor and log it
    proposal = payload.get("proposal") or {}
    if proposal:
        if not isinstance(proposal, dict):
            raise StationDecisionError("proposal must be an object")
        name = str(proposal.get("command_name") or "")
        if name not in REGISTRY_COMMANDS:
            raise StationDecisionError(
                f"proposal command {name!r} not in the H-0 registry "
                f"({list(REGISTRY_COMMANDS)}) — the agent proposes, H-0 executes"
            )
        if not isinstance(proposal.get("args"), dict):
            raise StationDecisionError("proposal args must be an object")
    return StationDecision(
        agent=agent,
        decision=decision,
        reason=reason,
        confidence=confidence,
        deterministic_advice=advice,
        overridden=overridden,
        proposal=dict(proposal),
        raw=dict(payload),
    )
