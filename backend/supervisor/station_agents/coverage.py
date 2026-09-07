"""Coverage Agent (D-12): new-angle generation with subject references."""

from __future__ import annotations

import json
from typing import Any

from backend.stations.coverage.run import ANGLES
from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "coverage"
DECISIONS = ("propose_coverage", "abstain")
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
    angle = str(brief.get("angle") or "")
    intent = str(brief.get("intent") or "").strip()
    references = brief.get("reference_uris") or []
    if angle not in ANGLES or not intent or not references:
        return "abstain"
    return "propose_coverage"


def build_prompt(brief: dict[str, Any]) -> str:
    return (
        "You are the Coverage agent for Martini Shot. Propose a new angle "
        f"from {sorted(ANGLES)} using persisted subject references, or abstain "
        "when references/intent/angle are insufficient.\n\n"
        f"Brief:\n{json.dumps(brief)}\n\n"
        "Respond ONLY with JSON. Proposals use H-0 command generate_coverage."
    )


def parse_coverage_decision(text: str, brief: dict[str, Any]) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"coverage payload not JSON: {exc}") from exc
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
                "[hard gate reference_sufficiency] angle, intent, or references "
                f"missing; coerced to abstain. Agent said: {decision.reason}"
            ),
            confidence=decision.confidence,
            deterministic_advice="abstain",
            overridden=True,
            proposal={},
            raw=decision.raw,
        )
    return decision


def decide_coverage(
    settings: Any, *, brief: dict[str, Any]
) -> tuple[StationDecision, int]:
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(brief),
        span_name="station.coverage.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_coverage_decision(response["text"], brief), int(
        response["cost_micros"]
    )


def build_inspect_prompt(context: dict[str, Any]) -> str:
    """Finishing look: missing geography AND helpful extra angles."""
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("coverage", context)
