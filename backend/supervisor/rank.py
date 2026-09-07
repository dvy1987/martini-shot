"""Orchestrator ranking.

The Gemini orchestrator chooses order and dependencies. Code here is the
safety rail: empty is not work, invented stations never run, forgotten
needs_work is not dropped on the floor. `rank_notes` is only the crash
fallback when the billed ranker returns garbage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from backend.supervisor.inspect import InspectNote

GENERATIVE_STATIONS = frozenset(
    {"extend", "corrections", "relight", "coverage", "camera_language"}
)
_IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}
_KIND_RANK = {"defect": 0, "improvement": 1}


def note_key(note: InspectNote) -> str:
    return f"{note.station}::{note.shot_id or ''}"


@dataclass
class RankResult:
    ordered: list[InspectNote]
    waiting: list[InspectNote] = field(default_factory=list)


@dataclass
class RankPlan:
    ordered: list[InspectNote]
    blocked_by: dict[str, list[str]] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    reason: str = ""


class RankPlanError(ValueError):
    """Malformed orchestrator JSON never silently becomes a fake ranking."""


def parse_rank_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RankPlanError(f"rank payload not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RankPlanError("rank payload must be an object")
    if "order" not in payload:
        raise RankPlanError("rank payload missing order")
    return payload


def _resolve_key(raw: str, catalog: dict[str, InspectNote]) -> str | None:
    token = str(raw or "").strip()
    if not token:
        return None
    if token in catalog:
        return token
    matches = [key for key in catalog if key == token or key.startswith(f"{token}::")]
    if len(matches) == 1:
        return matches[0]
    station_matches = [key for key in catalog if key.split("::", 1)[0] == token]
    if len(station_matches) == 1:
        return station_matches[0]
    return None


def apply_orchestrator_plan(
    notes: list[InspectNote], payload: dict[str, Any]
) -> RankPlan:
    """Honor the boss's order. Refuse invented/empty. Do not lose tickets."""
    catalog = {
        note_key(note): note
        for note in notes
        if note.status == "needs_work" and note.proposal
    }
    ordered: list[InspectNote] = []
    seen: set[str] = set()
    for raw in list(payload.get("order") or []):
        key = _resolve_key(str(raw), catalog)
        if key is None or key in seen:
            continue
        ordered.append(catalog[key])
        seen.add(key)
    dropped: list[str] = []
    for item in list(payload.get("drop") or []):
        if isinstance(item, dict):
            dropped.append(str(item.get("id") or ""))
        else:
            dropped.append(str(item))
    dropped_keys = {key for key in (_resolve_key(d, catalog) for d in dropped) if key}
    for key, note in catalog.items():
        if key in seen or key in dropped_keys:
            continue
        ordered.append(note)
        seen.add(key)
    blocked_by: dict[str, list[str]] = {}
    for dep in list(payload.get("dependencies") or []):
        if not isinstance(dep, dict):
            continue
        before = _resolve_key(str(dep.get("before") or ""), catalog)
        after = _resolve_key(str(dep.get("after") or ""), catalog)
        if not before or not after or before == after:
            continue
        if before not in catalog or after not in catalog:
            continue
        blockers = blocked_by.setdefault(after, [])
        if before not in blockers:
            blockers.append(before)
    return RankPlan(
        ordered=ordered,
        blocked_by=blocked_by,
        dropped=[key for key in dropped_keys],
        reason=str(payload.get("reason") or ""),
    )


def rank_notes(
    notes: list[InspectNote],
    *,
    shot_order: dict[str, int],
    remaining_micros: int | None = None,
) -> RankResult:
    """Crash fallback only. Empty/ok never dispatch. One generative edit per shot."""
    candidates = [
        note for note in notes if note.status == "needs_work" and note.proposal
    ]
    candidates.sort(key=lambda note: _sort_key(note, shot_order))
    ordered: list[InspectNote] = []
    waiting: list[InspectNote] = []
    generative_shots: set[str] = set()
    for note in candidates:
        if note.station in GENERATIVE_STATIONS:
            shot = note.shot_id or ""
            if shot in generative_shots:
                waiting.append(note)
                continue
            generative_shots.add(shot)
        ordered.append(note)
    if remaining_micros is not None:
        ordered, starved = _protect_higher_bands(ordered, remaining_micros)
        waiting.extend(starved)
    return RankResult(ordered=ordered, waiting=waiting)


def budget_cut(
    notes: list[InspectNote], *, remaining_micros: int
) -> tuple[list[InspectNote], list[InspectNote]]:
    take: list[InspectNote] = []
    wait: list[InspectNote] = []
    left = remaining_micros
    for note in notes:
        cost = int(note.cost_estimate_micros)
        if cost <= left:
            take.append(note)
            left -= cost
        else:
            wait.append(note)
    return take, wait


def _sort_key(
    note: InspectNote, shot_order: dict[str, int]
) -> tuple[int, int, int, int]:
    return (
        _IMPACT_RANK.get(note.impact, 9),
        _KIND_RANK.get(note.kind, 9),
        shot_order.get(note.shot_id, 10_000),
        int(note.cost_estimate_micros),
    )


def _protect_higher_bands(
    ordered: list[InspectNote], remaining_micros: int
) -> tuple[list[InspectNote], list[InspectNote]]:
    higher_cost = sum(
        int(n.cost_estimate_micros) for n in ordered if n.impact in {"high", "medium"}
    )
    parked: list[InspectNote] = []
    kept: list[InspectNote] = []
    reserved = min(higher_cost, remaining_micros)
    leftover_for_low = remaining_micros - reserved
    for note in ordered:
        if note.impact == "low" and int(note.cost_estimate_micros) > leftover_for_low:
            parked.append(note)
            continue
        kept.append(note)
        if note.impact == "low":
            leftover_for_low -= int(note.cost_estimate_micros)
    return kept, parked
