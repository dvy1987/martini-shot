"""Draft-First Orchestrator Agent (D-11): subjective readiness over real QC.

The deterministic state machine in `backend.stations.draft_first` still
rejects master dispatch without an eligible draft. This agent may take that
advice under advisement (StationDecision) but cannot bypass the hard gate."""

from __future__ import annotations

import json
from typing import Any

from backend.stations.draft_first import evaluate_readiness
from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "draft_first"
DECISIONS = ("authorize_master", "revise", "escalate", "wait")
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "proposal": {"type": "object"},
    },
    "required": ["agent", "decision", "reason", "confidence"],
}

_STATE_TO_DECISION = {
    "master_eligible": "authorize_master",
    "revise": "revise",
    "escalate": "escalate",
    "draft_requested": "wait",
}


def suggestion_for_state(
    *, op: str, alternates: list[dict[str, Any]], revision_count: int
) -> str:
    readiness = evaluate_readiness(
        op=op, alternates=alternates, revision_count=revision_count
    )
    return _STATE_TO_DECISION.get(readiness.state, "wait")


def build_prompt(
    *, op: str, alternates: list[dict[str, Any]], revision_count: int
) -> str:
    readiness = evaluate_readiness(
        op=op, alternates=alternates, revision_count=revision_count
    )
    return (
        "You are the Draft-First Orchestrator for Martini Shot. Decide whether "
        "a draft is informative enough to authorize a master, request one "
        "bounded revision, or escalate to a human. You cannot bypass the "
        "deterministic master-eligibility gate.\n\n"
        f"Op: {op}\nRevision count: {revision_count}\n"
        f"Deterministic readiness: {readiness.state} ({readiness.reason})\n"
        f"Alternates:\n{json.dumps(alternates)}\n\n"
        "Vocabulary: authorize_master | revise | escalate | wait.\n"
        "A master without a QC-passing draft is forbidden.\n"
        "Respond ONLY with JSON."
    )


def parse_draft_first_decision(
    text: str,
    *,
    op: str,
    alternates: list[dict[str, Any]],
    revision_count: int,
) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"draft_first payload not JSON: {exc}") from exc
    advice = suggestion_for_state(
        op=op, alternates=alternates, revision_count=revision_count
    )
    decision = validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=advice,
    )
    if advice != "authorize_master" and decision.decision == "authorize_master":
        return StationDecision(
            agent=decision.agent,
            decision=advice,
            reason=(
                "[hard gate draft_first] master not eligible; coerced to "
                f"{advice}. Agent said: {decision.reason}"
            ),
            confidence=decision.confidence,
            deterministic_advice=advice,
            overridden=True,
            proposal={},
            raw=decision.raw,
        )
    return decision


def decide_draft_first(
    settings: Any,
    *,
    op: str,
    alternates: list[dict[str, Any]],
    revision_count: int = 0,
) -> tuple[StationDecision, int]:
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(op=op, alternates=alternates, revision_count=revision_count),
        span_name="station.draft_first.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_draft_first_decision(
        response["text"],
        op=op,
        alternates=alternates,
        revision_count=revision_count,
    ), int(response["cost_micros"])
