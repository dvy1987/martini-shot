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


ALIGN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "span_id": {"type": "string"},
                    "start_char": {"type": "integer"},
                    "end_char": {"type": "integer"},
                    "shot_id": {"type": "string"},
                    "language": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["span_id", "start_char", "end_char", "shot_id"],
            },
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "spans", "reason"],
}


def build_align_prompt(*, script_text: str, shots: list[dict[str, Any]]) -> str:
    return (
        "You are the Revision Room alignment agent for Martini Shot. "
        "Map the script to shots using spoken_words and scene from ingest. "
        "Do not invent dialogue. Assign character ranges of the script to "
        "shot_id. language is usually en unless the shot is dubbed.\n\n"
        f"Script:\n{script_text}\n\n"
        f"Shots:\n{json.dumps(shots, default=str)}\n\n"
        "Respond ONLY with JSON: "
        '{"agent": "revision_room", "spans": [{"span_id": "sp-1", '
        '"start_char": 0, "end_char": 12, "shot_id": "...", '
        '"language": "en", "reason": "..."}], "reason": "...", '
        '"confidence": "low|medium|high"}.'
    )


def parse_alignment_spans(
    text: str, *, script_text: str, shot_ids: set[str]
) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise StationDecisionError("alignment payload must be an object")
    spans_out: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("spans") or []):
        if not isinstance(raw, dict):
            continue
        shot_id = str(raw.get("shot_id") or "")
        if shot_id not in shot_ids:
            continue
        start_char = int(raw.get("start_char") or 0)
        end_char = int(raw.get("end_char") or 0)
        if end_char <= start_char:
            continue
        start_char = max(0, min(start_char, len(script_text)))
        end_char = max(start_char, min(end_char, len(script_text)))
        spans_out.append(
            {
                "span_id": str(raw.get("span_id") or f"sp-{index + 1}"),
                "start_char": start_char,
                "end_char": end_char,
                "shot_id": shot_id,
                "language": str(raw.get("language") or "en"),
                "reason": str(raw.get("reason") or ""),
            }
        )
    return spans_out


def decide_alignment(
    settings: Any,
    *,
    script_text: str,
    shots: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    from backend.supervisor.otel_ai import run_agent_call

    shot_ids = {str(row.get("shot_id") or "") for row in shots if row.get("shot_id")}
    response = run_agent_call(
        settings,
        build_align_prompt(script_text=script_text, shots=shots),
        span_name="station.revision_room.align",
        persona=AGENT,
    )
    return parse_alignment_spans(
        response["text"], script_text=script_text, shot_ids=shot_ids
    ), int(response["cost_micros"])
