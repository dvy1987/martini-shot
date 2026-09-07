"""Finishing inspect note — attendance contract for the walk-away loop.

Empty is an attendance hole, never a fake all-good. Built agents return
ok / needs_work after a billed look. Impact is high | medium | low.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.stations.run import STATION_NAMES

ROSTER: tuple[str, ...] = STATION_NAMES
STATUSES = ("empty", "ok", "needs_work")
IMPACTS = ("none", "low", "medium", "high")
KINDS = ("none", "defect", "improvement")
PROPOSAL_KINDS = ("station_job", "h0")

INSPECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "station": {"type": "string", "enum": list(ROSTER)},
        "agent": {"type": "string"},
        "status": {"type": "string", "enum": list(STATUSES)},
        "impact": {"type": "string", "enum": list(IMPACTS)},
        "kind": {"type": "string", "enum": list(KINDS)},
        "summary": {"type": "string"},
        "cost_estimate_micros": {"type": "integer"},
        "proposal": {"type": "object"},
        "shot_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": [
        "station",
        "agent",
        "status",
        "impact",
        "kind",
        "summary",
        "cost_estimate_micros",
    ],
}

INSPECT_CONTRACT = """
You are judging the SOURCE CLIP for finishing — defects AND quality.
Taste is allowed. Do not abstain just because nothing is "broken."

Impact:
- high: cannot hear or see the story (unhearable, faces unreadable, truncated
  dialogue, corrupt media).
- medium: watchable but hurt (dies mid-thought, geography unclear, wrong
  signage, too dark but faces still barely readable, flicker).
- low: craft (richer lighting when already visible, optional camera move,
  extra air at the end).

status: ok if you would change nothing; needs_work if you would change
something. Do not use empty — empty is only for a missing agent.
kind: defect vs improvement.
Propose a real station job the house can run unattended. Minimize needs_human.
Respond ONLY with JSON matching the inspect schema.
"""

# Cheap mix vs billed Omni drafts. Inspect itself is metered separately.
DEFAULT_COST_MICROS: dict[str, int] = {
    "ingest": 20_000,
    "loudness": 80_000,
    "delivery": 50_000,
    "spend": 0,
    "pickups": 2_000_000,
    "dub": 500_000,
    "extend": 3_000_000,
    "corrections": 3_000_000,
    "relight": 3_000_000,
    "coverage": 3_000_000,
    "camera_language": 3_000_000,
}


class InspectNoteError(ValueError):
    """Fail loud: a malformed inspect note never reaches the orchestrator."""


@dataclass(frozen=True)
class InspectNote:
    station: str
    agent: str
    status: str
    impact: str
    kind: str
    summary: str
    cost_estimate_micros: int
    proposal: dict[str, Any] = field(default_factory=dict)
    shot_id: str = ""
    reason: str = ""

    def to_doc(self) -> dict[str, Any]:
        return {
            "station": self.station,
            "agent": self.agent,
            "status": self.status,
            "impact": self.impact,
            "kind": self.kind,
            "summary": self.summary,
            "cost_estimate_micros": self.cost_estimate_micros,
            "proposal": dict(self.proposal),
            "shot_id": self.shot_id,
            "reason": self.reason,
        }


def empty_note(station: str, *, agent: str = "") -> InspectNote:
    if station not in ROSTER:
        raise InspectNoteError(f"unknown station {station!r}")
    return InspectNote(
        station=station,
        agent=agent,
        status="empty",
        impact="none",
        kind="none",
        summary="",
        cost_estimate_micros=0,
        proposal={},
    )


def attendance_rows(notes: list[InspectNote]) -> list[InspectNote]:
    """Every roster station, in worker order. Missing notes are empty."""
    by_station = {note.station: note for note in notes}
    return [by_station.get(station) or empty_note(station) for station in ROSTER]


def validate_inspect_note(payload: Any) -> InspectNote:
    if not isinstance(payload, dict):
        raise InspectNoteError("inspect note must be an object")
    station = str(payload.get("station") or "")
    if station not in ROSTER:
        raise InspectNoteError(f"unknown station {station!r}")
    status = str(payload.get("status") or "")
    if status not in STATUSES:
        raise InspectNoteError(f"status {status!r} invalid")
    impact = str(payload.get("impact") or "")
    if impact not in IMPACTS:
        raise InspectNoteError(f"impact {impact!r} invalid")
    kind = str(payload.get("kind") or "")
    if kind not in KINDS:
        raise InspectNoteError(f"kind {kind!r} invalid")
    summary = str(payload.get("summary") or "")
    try:
        cost = int(payload.get("cost_estimate_micros"))
    except (TypeError, ValueError) as exc:
        raise InspectNoteError("cost_estimate_micros must be an integer") from exc
    if cost < 0:
        raise InspectNoteError("cost_estimate_micros must be >= 0")
    agent = str(payload.get("agent") or "")
    proposal = payload.get("proposal") or {}
    if proposal and not isinstance(proposal, dict):
        raise InspectNoteError("proposal must be an object")
    proposal = dict(proposal)
    if status == "empty":
        if summary or proposal or cost or impact != "none" or kind != "none":
            raise InspectNoteError("empty notes must be blank (not a fake all-good)")
        if not agent:
            agent = ""
    elif not summary:
        raise InspectNoteError("summary is required unless status is empty")
    if status == "ok":
        if proposal:
            raise InspectNoteError("ok notes cannot carry a proposal")
        if impact != "none" or kind != "none":
            raise InspectNoteError("ok notes use impact=none and kind=none")
    if status == "needs_work":
        if impact == "none":
            raise InspectNoteError("needs_work requires high|medium|low impact")
        if kind == "none":
            raise InspectNoteError("needs_work requires defect or improvement")
        if not proposal:
            raise InspectNoteError("needs_work requires a real proposal")
        _validate_proposal(station, proposal)
    return InspectNote(
        station=station,
        agent=agent,
        status=status,
        impact=impact,
        kind=kind,
        summary=summary,
        cost_estimate_micros=cost,
        proposal=proposal,
        shot_id=str(payload.get("shot_id") or ""),
        reason=str(payload.get("reason") or ""),
    )


def _validate_proposal(station: str, proposal: dict[str, Any]) -> None:
    kind = str(proposal.get("kind") or "")
    if kind not in PROPOSAL_KINDS:
        raise InspectNoteError(f"proposal kind {kind!r} invalid")
    if kind == "station_job":
        target = str(proposal.get("station") or "")
        if target not in ROSTER:
            raise InspectNoteError(f"proposal station {target!r} unknown")
        if station == "spend" and target != "spend":
            raise InspectNoteError("spend cannot invent creative work")
        args = proposal.get("args") or {}
        if not isinstance(args, dict):
            raise InspectNoteError("proposal args must be an object")
        return
    from backend.supervisor.agents.finding_schema import REGISTRY_COMMANDS

    name = str(proposal.get("command_name") or "")
    if name not in REGISTRY_COMMANDS:
        raise InspectNoteError(f"proposal command {name!r} not in H-0 registry")
    if station == "spend" and name not in {
        "pause_intake",
        "resume_intake",
        "retry_job",
    }:
        raise InspectNoteError("spend cannot invent creative work")
    args = proposal.get("args") or {}
    if not isinstance(args, dict):
        raise InspectNoteError("proposal args must be an object")
