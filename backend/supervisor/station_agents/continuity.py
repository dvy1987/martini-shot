"""Continuity Agent (H-1h, A10): reviews a flagged job against the shot's
alternates/lock state and chooses the continuity-safe action.

HARD GATE (locked_cut_overwrite, enforced in code): it must never propose
an action that targets a LOCKED cut except `add_to_continuity` (the
approval-tracked flow). A retry targeting a locked shot is coerced to an
explicit, logged abstention — never a silent overwrite (AL-1).

Deterministic surface (no LLM): suggestion mapping, prompt construction,
gate enforcement, and response parsing are unit-tested; the real judgment
is gated by the live EDD eval (scripts/continuity_eval.py vs
continuity_judgment, bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "continuity"
DECISIONS = ("add_to_continuity", "retry_job", "abstain")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["add_to_continuity", "retry_job", "abstain"],
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "decision", "reason", "confidence"],
}

# Draft QC bars (mirror thresholds.yaml pickups_flicker / pickups_vision_judge).
FLICKER_BAR = 0.02
VISION_BAR = 4.0


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _draft_clears_bars(alternate: dict[str, Any]) -> bool:
    scores = alternate.get("eval_scores") or {}
    flicker = _as_float(scores.get("flicker"))
    vision = _as_float(scores.get("vision_judge"))
    if flicker is None or vision is None:
        return False
    return flicker < FLICKER_BAR and vision >= VISION_BAR


def suggestion_for_case(job: dict[str, Any], alternates_context: dict[str, Any]) -> str:
    """Deterministic default: no shot → abstain; a locked cut routes
    through the approval-tracked add_to_continuity flow; an unlocked
    neighbor-continuity breach re-renders; a draft that cleared both QC
    bars is promoted; anything else abstains."""
    shot_id = alternates_context.get("shot_id")
    if not shot_id:
        return "abstain"
    if alternates_context.get("locked"):
        return "add_to_continuity"  # the ONLY sanctioned path for a locked cut
    result = job.get("result") or {}
    try:
        deltae = float(result.get("deltae") or 0.0)
        tolerance = float(result.get("tolerance") or 0.0)
    except (TypeError, ValueError):
        deltae, tolerance = 0.0, 0.0
    if tolerance > 0 and deltae > tolerance:
        return "retry_job"
    for alternate in alternates_context.get("alternates") or []:
        if alternate.get("status") == "draft" and _draft_clears_bars(alternate):
            return "add_to_continuity"
    return "abstain"


def build_prompt(job: dict[str, Any], alternates_context: dict[str, Any]) -> str:
    """The prompt carries the flagged job, the shot's alternates/lock
    state, the decision ladder, and the hard gate as an explicit rule."""
    return (
        "You are the Continuity agent for Martini Shot. One job was flagged "
        "for continuity review; decide the safe action.\n\n"
        f"Job:\n- station: {job.get('station')}\n"
        f"- job_id: {job.get('id')}\n"
        f"- status: {job.get('status')}\n"
        f"- error/context: {job.get('error') or '(none)'}\n"
        f"- result: {json.dumps(job.get('result') or {})}\n\n"
        "Shot continuity state:\n"
        f"{json.dumps(alternates_context)}\n\n"
        "Decision ladder — apply IN ORDER, first match wins:\n"
        "1. No shot_id in the continuity state (nothing to review) -> "
        "abstain.\n"
        "2. The shot is LOCKED in continuity: the ONLY sanctioned action is "
        "add_to_continuity (approval-tracked). NEVER propose retry_job or "
        "any direct overwrite of a locked cut — declining to a human is "
        "always acceptable (abstain).\n"
        "3. Unlocked shot whose render breaks light continuity with a "
        "locked NEIGHBOR (deltaE above tolerance): retry_job — re-render "
        "the grade to match the neighbor; the fix is reversible.\n"
        "4. A draft alternate that cleared BOTH QC bars (flicker < 0.02 "
        "AND vision_judge >= 4.0) on an unlocked shot -> add_to_continuity "
        "(approval-tracked promotion, not a re-render).\n"
        "5. Anything else -> abstain.\n\n"
        "Hard gate you cannot violate: an action that would overwrite a "
        "locked cut outside the add_to_continuity flow is forbidden and "
        "will be rejected in code regardless of your reasoning.\n\n"
        'Respond ONLY with JSON: {"agent": "continuity", "decision": '
        '"add_to_continuity|retry_job|abstain", "reason": "...", '
        '"confidence": "low|medium|high"}.'
    )


def enforce_locked_cut_gate(
    decision: StationDecision, alternates_context: dict[str, Any]
) -> StationDecision:
    """HARD GATE (locked_cut_overwrite) — enforced in code, not prompt:
    a retry_job (or any non-add_to_continuity action) targeting a LOCKED
    cut is coerced to an explicit abstention. The coercion is visible in
    the reason and flagged as an override — never silent (AL-1)."""
    if not alternates_context.get("locked"):
        return decision
    if decision.decision in ("add_to_continuity", "abstain"):
        return decision
    return StationDecision(
        agent=decision.agent,
        decision="abstain",
        reason=(
            "[hard gate locked_cut_overwrite] proposed "
            f"{decision.decision} on a LOCKED cut; only the approval-tracked "
            f"add_to_continuity flow is sanctioned. Agent said: {decision.reason}"
        ),
        confidence=decision.confidence,
        deterministic_advice=decision.deterministic_advice,
        overridden=True,
        proposal={},  # the vetoed proposal is never carried forward
        raw=decision.raw,
    )


def parse_continuity_decision(
    text: str,
    job: dict[str, Any],
    alternates_context: dict[str, Any],
) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract,
    then apply the locked-cut hard gate. Tolerates markdown code fences
    around the JSON but nothing else — fail loud on real drift."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"continuity payload not JSON: {exc}") from exc
    decision = validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=suggestion_for_case(job, alternates_context),
    )
    return enforce_locked_cut_gate(decision, alternates_context)


def decide_continuity(
    settings: Any,
    *,
    job: dict[str, Any],
    alternates_context: dict[str, Any],
) -> tuple[StationDecision, int]:
    """THE real continuity judgment: one metered Gemini call over the
    flagged job + continuity state, validated against the contract, hard
    gate applied. Returns (decision, cost_micros) (C-6.4). Raises on any
    API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(job, alternates_context),
        span_name="station.continuity.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_continuity_decision(response["text"], job, alternates_context)
    return decision, int(response["cost_micros"])
