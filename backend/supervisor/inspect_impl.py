"""Billed finishing inspect: one look per roster station, quality + defects."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.supervisor.inspect import (
    DEFAULT_COST_MICROS,
    INSPECT_CONTRACT,
    INSPECT_SCHEMA,
    ROSTER,
    InspectNote,
    InspectNoteError,
    empty_note,
    validate_inspect_note,
)

log = logging.getLogger("pc.finishing.inspect")

_AGENT = {
    "ingest": "ingest_triage",
    "loudness": "loudness_strategy",
    "delivery": "delivery_strategy",
    "spend": "spend_steward",
    "pickups": "pickups_vision_qc",
    "dub": "dub_qc",
    "extend": "extend_qc",
    "corrections": "corrections",
    "relight": "relight",
    "coverage": "coverage",
    "camera_language": "camera_language",
}

_SPECIALTY = {
    "ingest": (
        "File health. Corrupt/missing media is high. A technically valid "
        "but unusable ingest (no picture, no sound) is high."
    ),
    "loudness": (
        "Hearability AND presence. Unhearable or clipping is high. A mix "
        "that meters near target but dialogue feels thin is medium. Do not "
        "pump a true silence/whisper scene up to TV-loud."
    ),
    "delivery": (
        "Captions and pack completeness. Missing required captions is high. "
        "Captions that exist but bury the line or miss a beat are medium."
    ),
    "spend": (
        "Envelope only. Never propose picture, sound, or editorial work. "
        "ok unless the house is already over cap."
    ),
    "pickups": (
        "Damage, flicker, AND frames that could be cleaner. A broken frame "
        "is high. Subtle instability is medium."
    ),
    "dub": (
        "If no target language/script is on the project, status=ok with "
        "summary that no dub was requested — not empty. If a script exists: "
        "truncated/missing line is high; a complete but stiff read is medium."
    ),
    "extend": (
        "Does the shot die mid-thought (medium/high) or merely want a breath "
        "of air at the end (low)?"
    ),
    "corrections": (
        "Wrong signage/text is a defect. Visual clutter the film would be "
        "better without is an improvement — you MAY name the intent from "
        "looking; do not wait for a human brief."
    ),
    "relight": (
        "Inconsistent lighting is a defect. Consistent but too dark, faces "
        "unreadable, eyes lost in shadow is high improvement — propose a "
        "named preset (practical_lamp, ambient_daylight, overhead_ceiling, "
        "noir). Already-visible scenes that could be more cinematic are low."
    ),
    "coverage": (
        "Missing geography is medium/high. A reverse, close-up, or insert "
        "that would help the audience is an improvement even if an angle "
        "exists. Choose reverse_angle, close_up, wide_establishing, "
        "over_the_shoulder, or insert."
    ),
    "camera_language": (
        "If the brief asks for a move, honor it. If the shot is locked-off "
        "and a motivated move would help (dolly_tracking, steadicam, etc.), "
        "propose it as low improvement. Do not abstain only because nobody "
        "typed a movement."
    ),
}


def station_inspect_prompt(station: str, context: dict[str, Any]) -> str:
    if station not in ROSTER:
        raise InspectNoteError(f"unknown station {station!r}")
    return (
        f"You are the {station} finishing agent for Martini Shot.\n"
        f"{INSPECT_CONTRACT}\n"
        f"Specialty:\n{_SPECIALTY[station]}\n\n"
        f"Context:\n{json.dumps(context, default=str)}\n\n"
        f'The JSON field "station" MUST be "{station}". '
        f'The JSON field "agent" MUST be "{_AGENT[station]}". '
        f"Default cost_estimate_micros if unsure: "
        f"{DEFAULT_COST_MICROS[station]}. "
        'proposal.kind is "station_job" with "station" matching you and '
        '"args" for presets/intents/movements when needed.'
    )


def parse_inspect_text(text: str, station: str) -> InspectNote:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise InspectNoteError(f"{station} inspect payload not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InspectNoteError(f"{station} inspect payload must be an object")
    payload["station"] = station
    payload.setdefault("agent", _AGENT[station])
    return validate_inspect_note(payload)


def run_inspect(
    station: str,
    *,
    settings: Any | None = None,
    context: dict[str, Any] | None = None,
    images: list[tuple[bytes, str]] | None = None,
    audio: tuple[bytes, str] | None = None,
    preview_cache: Any | None = None,
) -> InspectNote:
    """Billed look. On garbage JSON, empty row + log — not a fake all-good."""
    context = dict(context or {})
    if settings is None:
        raise InspectNoteError("inspect requires live settings (no mock look)")
    from backend.supervisor.clip_preview import VISUAL_STATIONS
    from backend.supervisor.otel_ai import run_agent_call

    err = ""
    if preview_cache is not None and images is None and audio is None:
        images, audio, err = preview_cache.parts_for(
            station, str(context.get("clip_uri") or "")
        )
        context["preview"] = {
            "frames": len(images or []),
            "has_audio": audio is not None,
            "error": err,
        }
        if station in VISUAL_STATIONS and not images:
            log.error(
                "inspect had no frames station=%s uri=%s err=%s",
                station,
                context.get("clip_uri"),
                err,
            )
            return empty_note(station, agent=_AGENT[station])
    try:
        response = run_agent_call(
            settings,
            station_inspect_prompt(station, context),
            span_name=f"station.{station}.inspect",
            persona=_AGENT[station],
            response_schema=INSPECT_SCHEMA,
            images=images,
            audio=audio,
        )
        note = parse_inspect_text(response["text"], station)
        extra = int(response.get("cost_micros") or 0)
        if extra and note.status != "empty":
            return InspectNote(
                station=note.station,
                agent=note.agent,
                status=note.status,
                impact=note.impact,
                kind=note.kind,
                summary=note.summary,
                cost_estimate_micros=note.cost_estimate_micros,
                proposal=dict(note.proposal),
                shot_id=note.shot_id,
                reason=note.reason,
            )
        return note
    except Exception:
        log.exception("inspect failed station=%s", station)
        return empty_note(station, agent=_AGENT[station])


def register_all(register: Any) -> None:
    for station in ROSTER:

        def _fn(*, _station: str = station, **kwargs: Any) -> InspectNote:
            return run_inspect(_station, **kwargs)

        register(station, _fn)
