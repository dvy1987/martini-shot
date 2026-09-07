"""Extend QC station agent (A10-4 retrofit of D-9): the deterministic
flicker gate (0.02, G0-evidenced) stays the machine-checkable number; the
agent owns the RESPONSE to it — accept_as_draft / bounded_revision /
escalate — under the two-strikes rule and the meter-integrity rule.

Retrofit semantics (A10): the existing `draft_qc_decision` mapping becomes
the DETERMINISTIC SUGGESTION the agent receives; a different agent
decision is an explicit, logged override."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "extend_qc"
DECISIONS = ("accept_as_draft", "bounded_revision", "escalate")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["accept_as_draft", "bounded_revision", "escalate"],
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "decision", "reason", "confidence"],
}


def suggestion_for_report(report: dict[str, Any]) -> str:
    """Deterministic default: healthy-and-measured passes; a first-attempt
    marginal breach earns ONE bounded revision; a second strike, an order-
    of-magnitude breach, or an untrustworthy meter escalate. Unknown
    shapes escalate conservatively."""
    try:
        raw_flicker = report.get("flicker")
        flicker = float(raw_flicker) if raw_flicker is not None else -1.0
        gate = float(report.get("flicker_gate") or 0.02)
        frames = int(report.get("frames_analyzed") or 0)
        attempt = int(report.get("revision_attempt") or 0)
    except (TypeError, ValueError):
        return "escalate"
    if frames <= 0:
        return "escalate"  # meter-integrity: an unmeasured pass is not a pass
    if attempt >= 1:
        return "escalate"  # two-strikes: a revision already ran
    if flicker < gate:
        return "accept_as_draft"
    if flicker < gate * 10:
        return "bounded_revision"
    return "escalate"


def build_prompt(report: dict[str, Any]) -> str:
    """The prompt carries the render metadata, the flicker measurement
    with its gate, the revision history, and the response rules."""
    return (
        "You are the Extend QC agent for Martini Shot, judging one Omni "
        "scene-extend draft. The deterministic flicker meter already ran.\n\n"
        "Render report:\n"
        f"- job: {report.get('job_id')} (shot {report.get('shot_id')})\n"
        f"- render model: {report.get('render_model')}\n"
        f"- omni_fallback: {report.get('omni_fallback', False)} "
        f"(Omni error: {report.get('omni_error') or 'none'})\n"
        f"- prompt: {report.get('prompt')}\n"
        f"- flicker: {report.get('flicker')} (gate {report.get('flicker_gate')}; "
        "healthy drafts historically land 0.0013-0.0032 — ILLUSTRATIVE "
        "context only: the GATE is the binding threshold, not the "
        "historical band. A broken render is an order of magnitude over "
        "the GATE.)\n"
        f"- frames_analyzed: {report.get('frames_analyzed')} (0 means the "
        "meter saw NOTHING and the number is meaningless)\n"
        f"- revision_attempt: {report.get('revision_attempt')} (1+ means a "
        "bounded revision already ran on this shot)\n\n"
        "Rules:\n"
        "1. Accept as draft when flicker is UNDER THE GATE and the meter "
        "genuinely analyzed frames — including a revision that landed "
        "under the gate (that revision SUCCEEDED; do not escalate a "
        "recovered render).\n"
        "2. bounded_revision = ONE re-render with strengthened anchors "
        "(tighter prompt, pinned first/last frame). Reserve it for a first "
        "attempt that breaches the gate only marginally.\n"
        "3. Two-strikes: if a revision already ran and the gate is still "
        "breached, escalate — do not spend another render.\n"
        "4. An order-of-magnitude breach is a structurally broken render: "
        "escalate immediately.\n"
        "5. If frames_analyzed is 0, the measurement is untrustworthy even "
        "when the gate 'passed' — escalate; you cannot accept a pass you "
        "cannot measure.\n\n"
        'Respond ONLY with JSON: {"agent": "extend_qc", "decision": '
        '"accept_as_draft|bounded_revision|escalate", "reason": "...", '
        '"confidence": "low|medium|high"}.'
    )


def parse_extend_decision(text: str, report: dict[str, Any]) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract.
    Tolerates markdown code fences around the JSON but nothing else."""
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
        deterministic_suggestion=suggestion_for_report(report),
    )


def decide_extend_qc(
    settings: Any,
    *,
    report: dict[str, Any],
) -> tuple[StationDecision, int]:
    """THE real extend QC judgment: one metered Gemini call over the
    render report, validated against the StationDecision contract.
    Returns (decision, cost_micros) — the caller folds the cost into the
    job (C-6.4). Raises on any API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(report),
        span_name="station.extend_qc.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_extend_decision(response["text"], report)
    return decision, int(response["cost_micros"])


def build_inspect_prompt(context: dict[str, Any]) -> str:
    """Finishing look: mid-thought cut vs a breath of air."""
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("extend", context)
