"""Dub QC station agent (A10): Gemini listens to the dubbed audio and
classifies it, with the deterministic measurement as ADVICE it may override.

Deterministic surface (no LLM): prompt construction and response parsing are
unit-tested here; the real listen-call behavior is gated by the live EDD
eval (scripts/dub_qc_eval.py vs dub_timing/dub_truncation_recall)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "dub_qc"
DECISIONS = ("accept", "re_render", "needs_human")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": ["clean", "truncated", "artifact", "pacing_mismatch"],
        },
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "pace_adjustment": {
            "type": "string",
            "enum": ["faster", "slower", "none"],
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "classification", "decision", "reason", "confidence"],
}

# The deterministic verdict maps into the agent's decision vocabulary —
# the caller supplies this mapping so an agent decision that differs is a
# logged override (owner ruling: advice may be overridden, explicitly).
SUGGESTION = {"pass": "accept", "flagged": "needs_human"}


def build_prompt(m: dict[str, Any], *, script: str = "") -> str:
    """The prompt includes the deterministic measurements as context, the
    REFERENCE LINE (so missing content is detectable — evidence: fr-03's
    'Prise trois' alone sounded like a complete sentence until compared to
    the script), AND the explicit override clause — the agent is the judge,
    not the gate."""
    script_line = (
        f'\nReference line the dub MUST contain (target language): "{script}"\n'
        if script
        else ""
    )
    return (
        "You are the Dub QC agent for Martini Shot, judging one dubbed line "
        "against its source. Listen to the attached audio.\n\n"
        "Deterministic measurements (advisory):\n"
        f"- duration delta: {m['duration_delta_ms']:+d} ms "
        f"(tolerance ±{m['tolerance_ms']:.0f} ms)\n"
        f"- sync offset: {m['sync_offset_ms']:+d} ms (positive = dub starts late)\n"
        f"- deterministic verdict: {m['verdict']}\n"
        f"{script_line}\n"
        "You may take the deterministic verdict under advisement and override "
        "it — if you do, say so in your reason. Judge by listening: is speech "
        "cut off mid-word or mid-phrase (truncated)? Is any part of the "
        "reference line missing? Are there artifacts (clicks, robotic "
        "segments, doubled words)? Does the pacing or energy mismatch the "
        "source line? Report truncation even when the duration delta is "
        "inside tolerance.\n\n"
        'Respond ONLY with JSON: {"agent": "dub_qc", '
        '"classification": "clean|truncated|artifact|pacing_mismatch", '
        '"decision": "accept|re_render|needs_human", "reason": "...", '
        '"confidence": "low|medium|high"}. \'re_render\' means regenerate '
        "the dub (pick it when truncation or artifacts make the line "
        "unusable); 'needs_human' means ambiguous damage a person must "
        "review."
    )


def parse_dub_decision(text: str, m: dict[str, Any]) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract.
    Tolerates markdown code fences around the JSON (observed occasionally
    from thinking models) but nothing else — fail loud on real drift."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    return validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=SUGGESTION.get(str(m["verdict"]), "needs_human"),
    )


def decide_dub(
    settings: Any,
    *,
    measurements: dict[str, Any],
    dubbed_wav: bytes,
    script: str = "",
) -> tuple[StationDecision, int]:
    """THE real Dub QC judgment: one metered Gemini call listening to the
    dub (audio inline part), validated against the StationDecision contract.
    Returns (decision, cost_micros) — the station folds the cost into the
    job (C-6.4). Raises on any API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(measurements, script=script),
        span_name="station.dub_qc.agent",
        persona=AGENT,
        response_schema=SCHEMA,
        audio=(dubbed_wav, "audio/wav"),
    )
    decision = parse_dub_decision(response["text"], measurements)
    return decision, int(response["cost_micros"])
