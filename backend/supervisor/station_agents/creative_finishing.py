"""Creative Finishing Agent (H-1i, A10): turns an editor request or a QC
outcome into a render plan (or a refusal).

HARD GATE (draft_first, enforced in code): the FIRST render attempt of any
shot is a draft (low-res, cheap, draft-tier cost estimate). A master-tier
proposal without an eval-passing draft is coerced down to draft tier with
an explicit, logged override — masters are never attempted before an
eval-passing draft exists (owner ruling A5).

Deterministic surface (no LLM): suggestion mapping, prompt construction,
gate enforcement, and response parsing are unit-tested; the real judgment
is gated by the live EDD eval (scripts/creative_finishing_eval.py vs
creative_finishing_judgment, bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "creative_finishing"
DECISIONS = ("propose_render", "abstain")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {"type": "string", "enum": ["propose_render", "abstain"]},
        "tier": {"type": "string", "enum": ["draft", "master"]},
        "cost_estimate_micros": {"type": "number"},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "agent",
        "decision",
        "tier",
        "cost_estimate_micros",
        "reason",
        "confidence",
    ],
}

# Draft QC bars (mirror thresholds.yaml pickups_flicker / pickups_vision_judge).
FLICKER_BAR = 0.02
VISION_BAR = 4.0
# Cost realism bound (dataset rule): a re-render estimate may be at most
# MAX_COST_MULTIPLE x this shot's own prior attempts (cf-02).
MAX_COST_MULTIPLE = 3.0


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _draft_cleared_bars(alternate: dict[str, Any]) -> bool:
    scores = alternate.get("eval_scores") or {}
    flicker = _as_float(scores.get("flicker"))
    vision = _as_float(scores.get("vision_judge"))
    if flicker is None or vision is None:
        return False
    return flicker < FLICKER_BAR and vision >= VISION_BAR


def has_passing_draft(alternates_context: dict[str, Any]) -> bool:
    """True when an eval-passing draft exists — the ONLY state in which a
    master-tier render may be planned."""
    for alternate in alternates_context.get("alternates") or []:
        if alternate.get("status") == "draft" and _draft_cleared_bars(alternate):
            return True
    return False


def _prior_cost_micros(alternates_context: dict[str, Any]) -> int:
    return int(alternates_context.get("prior_attempt_cost_micros") or 0)


def suggestion_for_case(job: dict[str, Any], alternates_context: dict[str, Any]) -> str:
    """Deterministic default: a locked target abstains; a QC-failed draft
    or a fresh editor request proposes a DRAFT render; a draft that
    cleared the bars proposes the master."""
    if alternates_context.get("locked"):
        return "abstain"
    if has_passing_draft(alternates_context):
        return "propose_render"
    return "propose_render"


def build_prompt(job: dict[str, Any], alternates_context: dict[str, Any]) -> str:
    """The prompt carries the request/job, the shot's render history, the
    tier ladder, cost-realism rules, and the hard gate as an explicit rule."""
    prior_cost = _prior_cost_micros(alternates_context)
    return (
        "You are the Creative Finishing agent for Martini Shot. Decide the "
        "render plan for one shot — or decline.\n\n"
        f"Request/job:\n- station: {job.get('station')}\n"
        f"- job_id: {job.get('id')}\n"
        f"- status: {job.get('status')}\n"
        f"- error/context: {job.get('error') or '(none)'}\n"
        f"- result: {json.dumps(job.get('result') or {})}\n\n"
        "Shot render state:\n"
        f"{json.dumps(alternates_context)}\n\n"
        "Tier ladder — apply IN ORDER, first match wins:\n"
        "1. The target shot is LOCKED in continuity -> abstain. An extend "
        "proposal here would overwrite a locked cut; the decision belongs "
        "to a human.\n"
        "2. A draft exists that CLEARED both QC bars (flicker < 0.02 AND "
        "vision_judge >= 4.0) -> propose_render at tier master. This is "
        "the ONLY state in which a master is planned.\n"
        "3. A prior draft attempt FAILED QC -> propose_render at tier "
        "draft (one bounded re-render is justified; keep the estimate "
        "history-plausible).\n"
        "4. First render attempt of this shot (no drafts exist) -> "
        "propose_render at tier draft. DRAFT-FIRST is a hard rule: the "
        "first attempt is never a master.\n"
        "5. Anything ambiguous -> abstain.\n\n"
        "Cost rules: cost_estimate_micros must be a positive integer and "
        f"history-plausible — at most {MAX_COST_MULTIPLE}x this shot's own "
        f"prior attempt cost ({prior_cost} micros). A 0 or inflated "
        "estimate fails review (cost feeds the leverage ranking).\n\n"
        "Hard gate you cannot violate: a master-tier proposal without an "
        "eval-passing draft is rejected in code regardless of your "
        "reasoning.\n\n"
        'Respond ONLY with JSON: {"agent": "creative_finishing", '
        '"decision": "propose_render|abstain", "tier": "draft|master", '
        '"cost_estimate_micros": <number>, "reason": "...", "confidence": '
        '"low|medium|high"}. For abstain, set tier "draft" and cost 0.'
    )


def enforce_draft_first_gate(
    decision: StationDecision, alternates_context: dict[str, Any]
) -> StationDecision:
    """HARD GATE (draft_first) — enforced in code, not prompt: a
    master-tier proposal without an eval-passing draft is coerced to
    draft tier with an explicit, logged override."""
    if decision.decision != "propose_render":
        return decision
    if decision.raw.get("tier") != "master" or has_passing_draft(alternates_context):
        return decision
    return StationDecision(
        agent=decision.agent,
        decision=decision.decision,
        reason=(
            "[hard gate draft_first] master-tier proposal had NO eval-passing "
            f"draft; coerced to draft tier. Agent said: {decision.reason}"
        ),
        confidence=decision.confidence,
        deterministic_advice=decision.deterministic_advice,
        overridden=True,
        proposal=decision.proposal,
        raw={**decision.raw, "tier": "draft"},
    )


def parse_finishing_decision(
    text: str,
    job: dict[str, Any],
    alternates_context: dict[str, Any],
) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract,
    then apply the draft-first hard gate. Tolerates markdown code fences
    around the JSON but nothing else — fail loud on real drift."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"finishing payload not JSON: {exc}") from exc
    decision = validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=suggestion_for_case(job, alternates_context),
    )
    return enforce_draft_first_gate(decision, alternates_context)


def decide_creative_finishing(
    settings: Any,
    *,
    job: dict[str, Any],
    alternates_context: dict[str, Any],
) -> tuple[StationDecision, int]:
    """THE real creative-finishing judgment: one metered Gemini call over
    the request + render history, validated against the contract, hard
    gate applied. Returns (decision, cost_micros) (C-6.4). Raises on any
    API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(job, alternates_context),
        span_name="station.creative_finishing.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_finishing_decision(response["text"], job, alternates_context)
    return decision, int(response["cost_micros"])
