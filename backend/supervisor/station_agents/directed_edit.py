"""Directed Edit agent (Studio redesign, 2026-09-09): the operator ticks
zero or more finishing-station buttons, optionally a camera movement, and
types free-text intent for ONE selected clip. This agent turns that mix
into ONE bounded edit instruction for a single real Omni edit call,
asking at most `MAX_QUESTIONS` clarifying questions first.

HARD GATE: once `MAX_QUESTIONS` questions have been asked, the agent MUST
act — it can never stall the operator forever. The deterministic gate
lives in code, not just the prompt (mirrors the corrections agent's
locked/abstain hard gate).

Execution still goes through the existing corrections pipeline (H-0
`correct_shot`): this agent only decides WHAT to ask/write, never renders
or executes anything itself."""

from __future__ import annotations

import json
from typing import Any

from backend.stations.camera_language.run import MOVEMENT_DESCRIPTIONS
from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "directed_edit"
DECISIONS = ("ask", "ready")
MAX_QUESTIONS = 5

STATION_HINTS: dict[str, str] = {
    "relight": "Relight — shift the lighting look on the shot.",
    "coverage": "Coverage — generate another camera angle of the same moment.",
    "camera_language": "Camera movement — change how the camera moves through the shot.",
    "corrections": "Fix — change something specific in the picture without replacing the take.",
}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string", "enum": [AGENT]},
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "question": {"type": "string"},
        "final_intent": {"type": "string"},
    },
    "required": ["agent", "decision", "reason", "confidence"],
}


def _turns(brief: dict[str, Any]) -> list[dict[str, Any]]:
    raw = brief.get("turns") or []
    return [row for row in raw if isinstance(row, dict)]


def suggestion_for_brief(brief: dict[str, Any]) -> str:
    """Deterministic default: at or past the question cap, the only sane
    move is to act on what we have. Below the cap there is no strong
    deterministic answer — ask-vs-ready is a judgment call for the model."""
    if len(_turns(brief)) >= MAX_QUESTIONS:
        return "ready"
    return ""


def _station_lines(stations: list[str]) -> str:
    if not stations:
        return "(none — the operator selected no station buttons)"
    lines = []
    for key in stations:
        hint = STATION_HINTS.get(key, key.replace("_", " "))
        lines.append(f"- {hint}")
    return "\n".join(lines)


def _camera_movement_line(movement: str | None) -> str:
    if not movement:
        return ""
    description = MOVEMENT_DESCRIPTIONS.get(movement, movement.replace("_", " "))
    return f"\nChosen camera movement: {movement} — {description}.\n"


def _transcript(turns: list[dict[str, Any]]) -> str:
    if not turns:
        return "(none yet)"
    lines = []
    for index, turn in enumerate(turns, start=1):
        question = str(turn.get("question") or "").strip()
        answer = str(turn.get("answer") or "").strip()
        lines.append(f"{index}. Q: {question}\n   A: {answer}")
    return "\n".join(lines)


def build_prompt(brief: dict[str, Any]) -> str:
    stations = [str(item) for item in (brief.get("stations") or [])]
    movement = brief.get("camera_movement")
    chat_text = str(brief.get("chat_text") or "").strip()
    turns = _turns(brief)
    asked = len(turns)
    return (
        "You are the Directed Edit agent for Martini Shot. An operator picked "
        "zero or more finishing stations, maybe a camera movement, and typed "
        "free text describing what they want done to ONE clip. Figure out "
        "exactly what they want, asking AT MOST 5 short clarifying questions "
        "total, one at a time, only when genuinely needed. Once you know "
        "enough, stop asking and write ONE bounded edit instruction, in plain "
        "English, for a video-editing AI to follow on this single clip.\n\n"
        f"Selected stations:\n{_station_lines(stations)}\n"
        f"{_camera_movement_line(movement)}"
        f'Operator\'s own words: "{chat_text or "(nothing typed)"}"\n\n'
        f"Questions already asked and answered ({asked}/{MAX_QUESTIONS}):\n"
        f"{_transcript(turns)}\n\n"
        "Decide ONE of:\n"
        '1. "ask" — you still need to know something important and have not '
        "reached 5 questions. Ask exactly one short, concrete question (e.g. "
        "confirm a suggestion, resolve an ambiguity). Never ask about "
        "something the operator already answered.\n"
        '2. "ready" — you know enough, or you have already asked 5 questions. '
        "Write final_intent: a specific, bounded instruction combining "
        "everything selected, typed, and answered, worded for a video edit "
        "model. Do not invent details the operator never implied. If little "
        "is known, do your best with what you have — never refuse.\n\n"
        "Rules, first match wins:\n"
        "1. 5 questions already asked -> decision must be ready.\n"
        "2. Nothing selected and no chat text -> decision ready, with "
        "final_intent describing a light, tasteful pass on the clip.\n"
        "3. Otherwise decide based on how much is already known.\n\n"
        'The JSON field "agent" MUST be exactly "directed_edit" (lowercase).\n'
        "Respond ONLY with JSON matching the schema."
    )


def default_final_intent(brief: dict[str, Any]) -> str:
    """Deterministic best-effort fallback (used when the model is coerced
    past the question cap without ever writing its own final_intent, or
    if the caller wants a safe default before the first agent call)."""
    stations = [str(item) for item in (brief.get("stations") or [])]
    movement = brief.get("camera_movement")
    chat_text = str(brief.get("chat_text") or "").strip()
    turns = _turns(brief)
    parts: list[str] = []
    if chat_text:
        parts.append(chat_text)
    for key in stations:
        parts.append(
            STATION_HINTS.get(key, key.replace("_", " ")).split("—")[0].strip()
        )
    if movement:
        description = MOVEMENT_DESCRIPTIONS.get(movement, movement.replace("_", " "))
        parts.append(f"camera movement: {description}")
    for turn in turns:
        answer = str(turn.get("answer") or "").strip()
        if answer:
            parts.append(answer)
    if not parts:
        return (
            "Apply a light, tasteful pass on this clip. Keep everything else the same."
        )
    return ". ".join(parts) + ". Keep everything else the same."


def parse_directed_edit_decision(text: str, brief: dict[str, Any]) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"directed_edit payload not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise StationDecisionError("directed_edit payload must be an object")
    raw_agent = str(payload.get("agent") or "").strip().lower()
    if AGENT in raw_agent.replace("-", "_").replace(" ", "_"):
        payload["agent"] = AGENT
    decision = validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=suggestion_for_brief(brief),
    )
    if decision.decision == "ask" and not str(payload.get("question") or "").strip():
        raise StationDecisionError('decision "ask" requires a non-empty question')
    if (
        decision.decision == "ready"
        and not str(payload.get("final_intent") or "").strip()
    ):
        raise StationDecisionError('decision "ready" requires a non-empty final_intent')

    advice = suggestion_for_brief(brief)
    if advice == "ready" and decision.decision != "ready":
        # HARD GATE: past the question cap the model must act, never stall.
        return StationDecision(
            agent=decision.agent,
            decision="ready",
            reason=(
                "[hard gate directed_edit] question cap reached; coerced to "
                f"ready. Agent said: {decision.reason}"
            ),
            confidence=decision.confidence,
            deterministic_advice="ready",
            overridden=True,
            proposal={},
            raw={**decision.raw, "final_intent": default_final_intent(brief)},
        )
    return decision


def decide_directed_edit(
    settings: Any, *, brief: dict[str, Any]
) -> tuple[StationDecision, int]:
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(brief),
        span_name="station.directed_edit.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_directed_edit_decision(response["text"], brief), int(
        response["cost_micros"]
    )
