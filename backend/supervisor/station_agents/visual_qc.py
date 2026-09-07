"""Visual QC Agent (H-1j, A10): judges one draft render against its REAL
metric doc — never the generator's self-report.

HARD GATES (enforced in code):
- no_metrics_no_pass: without a real metric doc the agent refuses to
  judge (abstain) — absence of evidence is never a pass.
- flicker_threshold / all-bars: a draft breaching ANY bar is never waved
  through; a breach forces bounded_revision regardless of self-report.

Deterministic surface (no LLM): suggestion mapping, prompt construction,
gate enforcement, and response parsing are unit-tested; the real judgment
is gated by the live EDD eval (scripts/visual_qc_eval.py vs
visual_qc_judgment, bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    StationDecisionError,
    validate_station_decision,
)

AGENT = "visual_qc"
DECISIONS = ("promote", "bounded_revision", "abstain")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["promote", "bounded_revision", "abstain"],
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "decision", "reason", "confidence"],
}

# QC bars (mirror thresholds.yaml pickups_flicker / pickups_artifact_rate).
FLICKER_BAR = 0.02
ARTIFACT_BAR = 0.08


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def suggestion_for_metrics(metrics_doc: dict[str, Any] | None) -> str:
    """Deterministic default: no real metrics -> abstain; all bars clear
    -> promote; ANY breach -> bounded_revision. Self-reports are not
    evidence and are deliberately not read here."""
    if not metrics_doc:
        return "abstain"
    flicker = _as_float(metrics_doc.get("flicker"))
    artifact_rate = _as_float(metrics_doc.get("artifact_rate"))
    if flicker is None or artifact_rate is None:
        return "abstain"  # a malformed meter reading is not evidence either
    if flicker < FLICKER_BAR and artifact_rate < ARTIFACT_BAR:
        return "promote"
    return "bounded_revision"


def build_prompt(job: dict[str, Any], metrics_doc: dict[str, Any] | None) -> str:
    """The prompt carries the draft's job doc and the REAL metric doc,
    with the distrust-self-report rule made explicit."""
    metrics_json = json.dumps(metrics_doc) if metrics_doc else "null"
    return (
        "You are the Visual QC agent for Martini Shot, judging ONE draft "
        "render against its measured metrics.\n\n"
        f"Draft job:\n- station: {job.get('station')}\n"
        f"- job_id: {job.get('id')}\n"
        f"- result: {json.dumps(job.get('result') or {})}\n\n"
        f"REAL metric doc (measured post-render):\n{metrics_json}\n\n"
        "QC bars: flicker < 0.02 AND artifact_rate < 0.08. ALL bars "
        "matter — a single breach is a breach.\n\n"
        "Decision ladder — apply IN ORDER, first match wins:\n"
        "1. No real metric doc (null above) -> abstain. You cannot judge "
        "what was not measured; absence of evidence is never a pass.\n"
        "2. Any metric breaches its bar (flicker >= 0.02 OR artifact_rate "
        ">= 0.08) -> bounded_revision. A breaching draft is NEVER waved "
        "through — even when the generating pipeline self-reports "
        "'excellent'. The self-report is NOT evidence; only the measured "
        "doc is.\n"
        "3. Every bar clears -> promote (recommend promotion through the "
        "approval-tracked add_to_continuity flow; you never mutate "
        "anything directly).\n\n"
        "Hard gates you cannot violate: a missing metric doc can never "
        "yield promote; a breaching metric can never yield promote.\n\n"
        'Respond ONLY with JSON: {"agent": "visual_qc", "decision": '
        '"promote|bounded_revision|abstain", "reason": "...", '
        '"confidence": "low|medium|high"}.'
    )


def enforce_qc_gate(
    decision: StationDecision, metrics_doc: dict[str, Any] | None
) -> StationDecision:
    """HARD GATES (no_metrics_no_pass, all-bars) — enforced in code, not
    prompt: promote is only reachable with real metrics that clear every
    bar. Violations coerce to abstain (unmeasurable) or bounded_revision
    (breach) with an explicit, logged override — a breach is never waved
    through."""
    if decision.decision != "promote":
        return decision
    if not metrics_doc:
        return StationDecision(
            agent=decision.agent,
            decision="abstain",
            reason=(
                "[hard gate no_metrics_no_pass] promote without a real metric "
                f"doc is forbidden. Agent said: {decision.reason}"
            ),
            confidence=decision.confidence,
            deterministic_advice=decision.deterministic_advice,
            overridden=True,
            proposal={},
            raw=decision.raw,
        )
    flicker = _as_float(metrics_doc.get("flicker"))
    artifact_rate = _as_float(metrics_doc.get("artifact_rate"))
    breached = (
        flicker is None
        or artifact_rate is None
        or flicker >= FLICKER_BAR
        or artifact_rate >= ARTIFACT_BAR
    )
    if not breached:
        return decision
    return StationDecision(
        agent=decision.agent,
        decision="bounded_revision",
        reason=(
            "[hard gate flicker_threshold] real metrics breach a QC bar "
            f"(flicker={metrics_doc.get('flicker')}, artifact_rate="
            f"{metrics_doc.get('artifact_rate')}); a breach is never waved "
            f"through. Agent said: {decision.reason}"
        ),
        confidence=decision.confidence,
        deterministic_advice=decision.deterministic_advice,
        overridden=True,
        proposal={},
        raw=decision.raw,
    )


def parse_vqc_decision(
    text: str,
    job: dict[str, Any],
    metrics_doc: dict[str, Any] | None,
) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract,
    then apply the QC hard gates. Tolerates markdown code fences around
    the JSON but nothing else — fail loud on real drift."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise StationDecisionError(f"visual QC payload not JSON: {exc}") from exc
    decision = validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=suggestion_for_metrics(metrics_doc),
    )
    return enforce_qc_gate(decision, metrics_doc)


def decide_visual_qc(
    settings: Any,
    *,
    job: dict[str, Any],
    metrics_doc: dict[str, Any] | None,
) -> tuple[StationDecision, int]:
    """THE real visual QC judgment: one metered Gemini call over the
    draft + its real metric doc, validated against the contract, gates
    applied. Returns (decision, cost_micros) (C-6.4). Raises on any
    API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(job, metrics_doc),
        span_name="station.visual_qc.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_vqc_decision(response["text"], job, metrics_doc)
    return decision, int(response["cost_micros"])
