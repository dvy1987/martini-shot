"""Pickups Vision QC station agent (A10-4 retrofit of D-6): the agent
SEES the real clip — an inline VIDEO part in the product path (ADR-0005),
frame extracts as the eval-dataset input — next to the deterministic
flicker measurement, and decides accept / retry_with_stronger_anchors /
needs_human.

This is the one measurement-station agent that MAY OVERRIDE the numeric
gate (design decision 1, owner ruling): the frames are independent
evidence, and a clean-looking extract with a breached score can be a
meter artifact. Every override is explicit (decision differs from the
deterministic suggestion) and MUST state the reason — the StationDecision
contract enforces that.

Deterministic surface (no LLM): suggestion mapping, prompt construction,
and response parsing are unit-tested; the real judgment is gated by the
live EDD eval (scripts/pickups_vision_qc_eval.py vs pickups_qc_judgment,
bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.stations.pickups.retry import MAX_RETRIES, STABILIZE_RETRIES
from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "pickups_vision_qc"
DECISIONS = ("accept", "retry_with_stronger_anchors", "needs_human")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["accept", "retry_with_stronger_anchors", "needs_human"],
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "decision", "reason", "confidence"],
}


def suggestion_for_report(report: dict[str, Any]) -> str:
    """Deterministic default — the existing retry state machine
    (stations.pickups.retry.next_action) plus meter integrity: an
    unmeasured render is never a pass."""
    try:
        frames = int(report.get("frames_analyzed") or 0)
        ok = bool(report.get("ok"))
        if not ok or frames <= 0:
            return "needs_human"
        flicker = float(report.get("flicker") or 1.0)
        threshold = float(report.get("threshold") or 0.18)
        retries_used = int(report.get("retries_used") or 0)
    except (TypeError, ValueError):
        return "needs_human"
    if flicker < threshold:
        return "accept"
    if retries_used < MAX_RETRIES:
        return "retry_with_stronger_anchors"
    return "needs_human"


def build_prompt(report: dict[str, Any], *, has_video: bool) -> str:
    """The prompt carries the flicker METRIC DOC (definition + gate), the
    measurement, the retry history, and the explicit override clause."""
    media_clause = (
        "Attached to this message: the rendered pickup as a VIDEO — "
        "WATCH it end to end. Motion defects (shake, jitter, unstable "
        "handheld drift) are visible only in motion; judge the clip as "
        "a moving image."
        if has_video
        else f"Attached to this message: {report.get('num_images', 0)} real "
        "frame extract(s) from the rendered pickup. Judge them by LOOKING."
    )
    ladder_clause = (
        f"retries used: {report.get('retries_used')} of {MAX_RETRIES} "
        f"(attempts 1-{STABILIZE_RETRIES} stabilize with stronger anchors, "
        f"{STABILIZE_RETRIES + 1}-{MAX_RETRIES} regenerate the whole clip)"
    )
    return (
        "You are the Pickups Vision QC agent for Martini Shot. "
        f"{media_clause}\n\n"
        "Flicker metric doc (deterministic meter, advisory):\n"
        "- definition: mean |I_t - median(I_t-1, I_t, I_t+1)| on "
        "grayscale frames, lower is better\n"
        f"- measured: {report.get('flicker')}\n"
        f"- gate (threshold): {report.get('threshold')}\n"
        f"- frames analyzed: {report.get('frames_analyzed')} "
        "(0 = the meter saw nothing and the number is meaningless)\n"
        f"- {ladder_clause}\n\n"
        "Judge what you see for: corruption, heavy noise, "
        "blockiness/banding, ghosting, smeared motion, color smearing, "
        "and camera instability the shot does not motivate — "
        "the visible TEXTURE and STABILITY quality of what a viewer "
        "would see. Smooth "
        "gradients and soft lighting are CLEAN even when dark or "
        "low-contrast; hard edges from in-shot content are CONTENT, not "
        "defects.\n\n"
        "Rules:\n"
        "1. METER INTEGRITY FIRST: if frames_analyzed is 0 or the meter "
        "failed (ok=false), decision MUST be needs_human regardless of "
        "what the frames look like — even visible defects cannot be "
        "tracked against a re-render without a measurement.\n"
        "2. accept when the frames are visibly clean AND the flicker is "
        "under the gate.\n"
        "3. retry_with_stronger_anchors when the frames show real "
        "defects AND the meter worked AND at least one retry slot "
        "remains: ONE re-render with pinned first/last frames and a "
        "tightened prompt.\n"
        "4. needs_human when retries are exhausted or the defect is "
        "beyond an anchor-strengthened re-render.\n"
        "5. OVERRIDE CLAUSE (owner ruling): if the flicker number "
        "breaches the gate but the frames are VISIBLY clean, you may "
        "override the numeric gate and accept — say so explicitly in "
        "your reason (meter artifact suspected). Never wave a defect "
        "you can SEE through on the number's authority alone.\n\n"
        'Respond ONLY with JSON: {"agent": "pickups_vision_qc", '
        '"decision": "accept|retry_with_stronger_anchors|needs_human", '
        '"reason": "...", "confidence": "low|medium|high"}.'
    )


def parse_vision_decision(text: str, report: dict[str, Any]) -> StationDecision:
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


def decide_pickups_vision_qc(
    settings: Any,
    *,
    report: dict[str, Any],
    video: tuple[bytes, str] | None = None,
    images: list[tuple[bytes, str]] | None = None,
) -> tuple[StationDecision, int]:
    """THE real vision QC judgment: one metered Gemini call SEEING the clip
    (inline video part per ADR-0005; stills remain the eval-dataset input
    until that dataset ships real clips), validated against the
    StationDecision contract. Returns (decision, cost_micros) — the caller
    folds the cost into the job (C-6.4). Raises on any API/validation
    error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(report, has_video=video is not None),
        span_name="station.pickups_vision_qc.agent",
        persona=AGENT,
        response_schema=SCHEMA,
        images=images,
        video=video,
    )
    decision = parse_vision_decision(response["text"], report)
    return decision, int(response["cost_micros"])


def build_inspect_prompt(context: dict[str, Any]) -> str:
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("pickups", context)
