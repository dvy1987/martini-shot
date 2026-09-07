"""Billed finishing orchestrator: weigh tradeoffs and name dependencies."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.supervisor.inspect import InspectNote
from backend.supervisor.rank import (
    RankPlan,
    apply_orchestrator_plan,
    note_key,
    parse_rank_json,
    rank_notes,
)

log = logging.getLogger("pc.finishing.rank")

RANK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "order": {"type": "array", "items": {"type": "string"}},
        "dependencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["before", "after"],
            },
        },
        "drop": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id"],
            },
        },
        "reason": {"type": "string"},
    },
    "required": ["order", "reason"],
}

ORCHESTRATOR_PROMPT = """You are the finishing orchestrator for Martini Shot.
Specialist station agents already looked at the clips. You now have the
complete bag of their proposals. Your job is to THINK:

- Weigh impact vs cost vs story. Unhearable audio or unreadable faces usually
  outrank cosmetic craft — unless a specialist's note makes a real case otherwise.
- Name dependencies. Example: mix a scene before extending it so generated
  picture/sound matches hearable dialogue. Example: do not run two generative
  picture edits on the same shot at once; sequence them.
- Independent clips, or sound vs picture that do not overwrite the same file,
  may run in parallel (no dependency).
- Do not invent a station, a shot, or a job that is not in the candidate list.
- Empty notes are attendance holes, not work. ok / leave-it notes are not
  candidates — never turn them into jobs.
- kind=defect is required. Spend it before kind=improvement (nice-to-have).
- When the envelope is tight, drop low improvements first. Dropped work waits.
- Spend never becomes a picture job.

IDs are "station::shot_id". Return JSON only.
"""


def _candidates(notes: list[InspectNote]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for note in notes:
        if note.status != "needs_work" or not note.proposal:
            continue
        rows.append(
            {
                "id": note_key(note),
                "station": note.station,
                "shot_id": note.shot_id,
                "impact": note.impact,
                "kind": note.kind,
                "summary": note.summary,
                "cost_estimate_micros": note.cost_estimate_micros,
            }
        )
    return rows


def plan_from_text(notes: list[InspectNote], text: str) -> RankPlan:
    return apply_orchestrator_plan(notes, parse_rank_json(text))


def fallback_plan(notes: list[InspectNote], *, shot_order: dict[str, int]) -> RankPlan:
    ranked = rank_notes(notes, shot_order=shot_order)
    return RankPlan(
        ordered=[*ranked.ordered, *ranked.waiting],
        blocked_by={},
        dropped=[],
        reason="fallback: ranker JSON failed; heuristic order only",
    )


def run_rank_agent(
    settings: Any,
    notes: list[InspectNote],
    *,
    shot_order: dict[str, int],
    remaining_micros: int,
) -> RankPlan:
    """One billed thinking-HIGH call over the complete bag of inspect notes."""
    from backend.supervisor.otel_ai import run_agent_call

    candidates = _candidates(notes)
    if not candidates:
        return RankPlan(ordered=[], reason="no needs_work")
    prompt = (
        f"{ORCHESTRATOR_PROMPT}\n"
        f"remaining_micros: {remaining_micros}\n"
        f"shot_order_earlier_first: {json.dumps(shot_order)}\n"
        f"candidates:\n{json.dumps(candidates, indent=2)}\n"
    )
    print(
        "finishing rank estimate: billed orchestrator call "
        f"(thinking HIGH) remaining_micros={remaining_micros}",
        flush=True,
    )
    try:
        response = run_agent_call(
            settings,
            prompt,
            span_name="station.finishing.rank",
            persona="finishing_orchestrator",
            response_schema=RANK_SCHEMA,
        )
        plan = plan_from_text(notes, response["text"])
        if not plan.reason:
            plan.reason = "orchestrator ranked"
        return plan
    except Exception:
        log.exception("finishing ranker failed; heuristic fallback")
        return fallback_plan(notes, shot_order=shot_order)


def rank_complete_bag(
    settings: Any,
    notes: list[InspectNote],
    *,
    shot_order: dict[str, int],
    remaining_micros: int,
    adk_text: str = "",
) -> RankPlan:
    """Honor the ADK orchestrator JSON when present; else billed ranker.

    The boss ranks the complete bag of station notes (all clips), not one
    specialist in isolation. Heuristic sort is last-resort crash fallback.
    """
    if str(adk_text or "").strip():
        try:
            plan = plan_from_text(notes, adk_text)
            if plan.ordered or not _candidates(notes):
                return plan
        except Exception:
            log.exception("ADK orchestrator JSON unusable; billed rank fallback")
    if settings is not None:
        return run_rank_agent(
            settings,
            notes,
            shot_order=shot_order,
            remaining_micros=remaining_micros,
        )
    return fallback_plan(notes, shot_order=shot_order)
