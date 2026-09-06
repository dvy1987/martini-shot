"""Delivery Strategist station agent (A10-3): selects the delivery
profile over REAL per-destination evaluations (the deterministic D-4
engine ran first), makes accept-with-deviation calls with stated
rationale, and routes fix suggestions through H-0 — the agent proposes,
H-0 executes.

The number IS the number (design decision 2): the deterministic per-
destination verdicts are facts. The agent owns the CHOICE among them:
which profile ships, whether a MINOR deviation is acceptable, when to
hold for a deterministic fix (retry_job proposal), and when a human is
needed.

Deterministic surface (no LLM): suggestion mapping, prompt construction,
and response parsing are unit-tested; the real judgment is gated by the
live EDD eval (scripts/delivery_strategy_eval.py vs
delivery_strategy_judgment, bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "delivery_strategy"
DECISIONS = ("deliver", "deliver_with_deviation", "hold", "needs_human")
DESTINATIONS = ("streaming", "broadcast", "social")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["deliver", "deliver_with_deviation", "hold", "needs_human"],
        },
        "destination": {
            "type": "string",
            "enum": ["streaming", "broadcast", "social", "none"],
        },
        "proposal": {
            "type": "object",
            "properties": {
                "command_name": {"type": "string"},
                "args": {"type": "object"},
            },
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "decision", "destination", "reason", "confidence"],
}


def suggestion_for_evaluations(
    evaluations: list[dict[str, Any]],
) -> str:
    """Deterministic default: deliver if some destination passes every
    rule; otherwise hold (a visible stop state the pipeline understands).
    No evaluations at all is a caller bug, not a strategy."""
    if not evaluations:
        raise ValueError("evaluations must not be empty (caller bug)")
    return "deliver" if any(e.get("verdict") == "pass" for e in evaluations) else "hold"


def _eval_lines(evaluations: list[dict[str, Any]]) -> str:
    lines = []
    for e in evaluations:
        verdict = str(e.get("verdict") or "unknown")
        head = f"- {e.get('destination')}: {verdict}"
        violations = e.get("violations") or []
        if violations:
            head += " — " + "; ".join(
                f"{v.get('rule_id')}: {v.get('message')}" for v in violations
            )
        lines.append(head)
    return "\n".join(lines)


def build_prompt(probe: dict[str, Any], evaluations: list[dict[str, Any]]) -> str:
    """The prompt carries the pack probe, the REAL per-destination
    evaluations (facts), and the strategy rules: prefer a full pass;
    deviation only when minor and structural rules are clean; fixes are
    proposed to H-0, never executed by the agent."""
    return (
        "You are the Delivery Strategist agent for Martini Shot. The "
        "deterministic delivery evaluator already scored this pack "
        "against every candidate destination profile; choose the "
        "strategy.\n\n"
        "Pack probe:\n"
        f"{json.dumps(probe, sort_keys=True)}\n\n"
        "Deterministic per-destination evaluations (facts, rules "
        "DEL-001..DEL-007):\n"
        f"{_eval_lines(evaluations)}\n\n"
        "Strategy rules:\n"
        "1. PREFER A FULL PASS: if any destination passes every rule, "
        "deliver it (decision 'deliver', destination set).\n"
        "2. ACCEPT-WITH-DEVIATION when the ONLY misses are MINOR "
        "loudness misses (within ~2 LU of the target) and every "
        "structural rule (container/codec/AR/fps) is clean and no "
        "destination passes outright; state the rationale. A minor "
        "loudness miss is a routing judgment, NOT a re-render blocker.\n"
        "3. HOLD only for STRUCTURAL blockers (container/codec/AR/fps "
        "violations) that a deterministic re-render fixes: set "
        "destination to 'none' (nothing is shipping) and propose the fix "
        'through H-0 as {"command_name": "retry_job", "args": {...}} — '
        "you propose, H-0 executes; never assume the fix already "
        "happened. A hold WITHOUT a proposal is valid only when you "
        "cannot name a deterministic fix.\n"
        "4. NEEDS_HUMAN when the pack is structurally broken in several "
        "independent ways, or the right action is outside your "
        "vocabulary.\n\n"
        'Respond ONLY with JSON: {"agent": "delivery_strategy", '
        '"decision": "deliver|deliver_with_deviation|hold|needs_human", '
        '"destination": "streaming|broadcast|social|none", "proposal": '
        '{"command_name": "...", "args": {...}} (only for hold-with-fix), '
        '"reason": "...", "confidence": "low|medium|high"}.'
    )


def parse_strategy_decision(
    text: str,
    evaluations: list[dict[str, Any]],
) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract
    (the base gate also checks any H-0 proposal against the live
    registry). Tolerates markdown code fences around the JSON."""
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
        deterministic_suggestion=suggestion_for_evaluations(evaluations),
    )


def decide_delivery_strategy(
    settings: Any,
    *,
    probe: dict[str, Any],
    evaluations: list[dict[str, Any]],
) -> tuple[StationDecision, int]:
    """THE real delivery strategy judgment: one metered Gemini call over
    the probe plus the per-destination evaluations, validated against the
    StationDecision contract. Returns (decision, cost_micros) — the
    caller folds the cost into the job (C-6.4). Raises on any
    API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(probe, evaluations),
        span_name="station.delivery_strategy.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_strategy_decision(response["text"], evaluations)
    return decision, int(response["cost_micros"])
