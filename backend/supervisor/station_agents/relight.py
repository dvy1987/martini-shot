"""Relight Agent (E-1): named lighting intentions, preserve identity/geometry."""

from __future__ import annotations

import json
from typing import Any

from backend.stations.relight.run import PRESETS
from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "relight"
DECISIONS = ("propose_relight", "abstain")
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


def suggestion_for_brief(brief: dict[str, Any]) -> str:
    preset = str(brief.get("preset") or "")
    if preset not in PRESETS:
        return "abstain"
    return "propose_relight"


def build_prompt(brief: dict[str, Any]) -> str:
    return (
        "You are the Relight agent for Martini Shot. Choose a named lighting "
        f"preset from {sorted(PRESETS)} or abstain. Preserve framing, identity, "
        "and geometry. Incompatible looks must abstain.\n\n"
        f"Brief:\n{json.dumps(brief)}\n\n"
        "Respond ONLY with JSON matching the schema. Proposals use H-0 "
        "command relight_shot."
    )


def parse_relight_decision(text: str, brief: dict[str, Any]) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"relight payload not JSON: {exc}") from exc
    decision = validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=suggestion_for_brief(brief),
    )
    if suggestion_for_brief(brief) == "abstain" and decision.decision != "abstain":
        return StationDecision(
            agent=decision.agent,
            decision="abstain",
            reason=(
                "[hard gate named_preset] unknown or missing preset; "
                f"coerced to abstain. Agent said: {decision.reason}"
            ),
            confidence=decision.confidence,
            deterministic_advice="abstain",
            overridden=True,
            proposal={},
            raw=decision.raw,
        )
    return decision


def decide_relight(
    settings: Any, *, brief: dict[str, Any]
) -> tuple[StationDecision, int]:
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(brief),
        span_name="station.relight.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_relight_decision(response["text"], brief), int(response["cost_micros"])


def build_inspect_prompt(context: dict[str, Any]) -> str:
    """Finishing look: consistent-but-too-dark still needs work."""
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("relight", context)
