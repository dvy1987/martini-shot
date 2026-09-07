"""Revision Room Agent (D-15): script diffs → regeneration proposals."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "revision_room"
DECISIONS = ("propose_regeneration", "abstain")
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


def suggestion_for_impact(affected: list[dict[str, Any]]) -> str:
    if any(item.get("affected_shot_ids") for item in affected):
        return "propose_regeneration"
    return "abstain"


def build_prompt(
    *,
    old_text: str,
    new_text: str,
    diffs: list[dict[str, Any]],
    affected: list[dict[str, Any]],
) -> str:
    return (
        "You are the Revision Room agent for Martini Shot. A script changed. "
        "Propose regeneration only for impacted shots/languages. Abstain when "
        "the diff is empty, stale, or unsupported.\n\n"
        f"Old text:\n{old_text}\n\nNew text:\n{new_text}\n\n"
        f"Diffs:\n{json.dumps(diffs)}\nAffected:\n{json.dumps(affected)}\n\n"
        "Respond ONLY with JSON. Proposals use H-0 command "
        "regenerate_affected_spans."
    )


def parse_revision_decision(
    text: str, affected: list[dict[str, Any]]
) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"revision_room payload not JSON: {exc}") from exc
    advice = suggestion_for_impact(affected)
    decision = validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=advice,
    )
    if advice == "abstain" and decision.decision != "abstain":
        return StationDecision(
            agent=decision.agent,
            decision="abstain",
            reason=(
                "[hard gate no_impact] no affected shots; coerced to abstain. "
                f"Agent said: {decision.reason}"
            ),
            confidence=decision.confidence,
            deterministic_advice="abstain",
            overridden=True,
            proposal={},
            raw=decision.raw,
        )
    return decision


def decide_revision_room(
    settings: Any,
    *,
    old_text: str,
    new_text: str,
    diffs: list[dict[str, Any]],
    affected: list[dict[str, Any]],
) -> tuple[StationDecision, int]:
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(
            old_text=old_text, new_text=new_text, diffs=diffs, affected=affected
        ),
        span_name="station.revision_room.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_revision_decision(response["text"], affected), int(
        response["cost_micros"]
    )
