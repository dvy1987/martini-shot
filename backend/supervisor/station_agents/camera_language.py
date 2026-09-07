"""Camera Language Agent (D-16): constrained movement vocabulary."""

from __future__ import annotations

import json
from typing import Any

from backend.stations.camera_language.run import MOVEMENTS
from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "camera_language"
DECISIONS = ("propose_camera_language", "abstain")
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
    movement = str(brief.get("movement") or "")
    if movement not in MOVEMENTS:
        return "abstain"
    return "propose_camera_language"


def build_prompt(brief: dict[str, Any]) -> str:
    return (
        "You are the Camera Language agent for Martini Shot. Limit outputs to "
        f"{sorted(MOVEMENTS)}. Disclose reference-style influence when present. "
        "Incompatible movement requests must abstain.\n\n"
        f"Brief:\n{json.dumps(brief)}\n\n"
        "Respond ONLY with JSON. Proposals use H-0 command apply_camera_language."
    )


def parse_camera_language_decision(text: str, brief: dict[str, Any]) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"camera_language payload not JSON: {exc}") from exc
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
                "[hard gate vocabulary] movement not in the approved table; "
                f"coerced to abstain. Agent said: {decision.reason}"
            ),
            confidence=decision.confidence,
            deterministic_advice="abstain",
            overridden=True,
            proposal={},
            raw=decision.raw,
        )
    return decision


def decide_camera_language(
    settings: Any, *, brief: dict[str, Any]
) -> tuple[StationDecision, int]:
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(brief),
        span_name="station.camera_language.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_camera_language_decision(response["text"], brief), int(
        response["cost_micros"]
    )


def build_inspect_prompt(context: dict[str, Any]) -> str:
    """Finishing look: a motivated move can be taste, not only a typed brief."""
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("camera_language", context)
