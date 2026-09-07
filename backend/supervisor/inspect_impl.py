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
    "ingest": "ingest_understand",
    "loudness": "loudness_strategy",
    "delivery": "delivery_strategy",
    "spend": "spend_steward",
    "pickups": "pickups_vision_qc",
    "dub": "dub_qc",
    "extend": "extend",
    "corrections": "corrections",
    "relight": "relight",
    "coverage": "coverage",
    "camera_language": "camera_language",
}

_SPECIALTY = {
    "ingest": (
        "Watch the original clip. Write spoken words (the script) and a "
        "short scene description. Silence is valid: ingested=true, empty "
        "spoken_words, still describe the picture. The ingest JOB already "
        "checked the container. Use and preserve context ingested / "
        "spoken_words / scene — do not invent a different line."
    ),
    "loudness": (
        "Hearability AND presence. Classify quiet/normal/loud with or "
        "without dialogue. Unhearable speech is high. If speech is buried "
        "in the room, lift the voice — do not only turn the whole track "
        "up. Do not pump a true quiet-no-dialogue scene up to talk level."
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
        "Pick exactly one bucket. MUST: the shot dies mid-thought or "
        "mid-action so the story does not land — status=needs_work, "
        "kind=defect, impact=high or medium, propose a 360p draft extend "
        "as an ALTERNATE. NICE: the beat already lands; a breath of air "
        "at the end would help — status=needs_work, kind=improvement, "
        "impact=low, propose that same draft alternate. LEAVE: the shot "
        "is already complete — status=ok, impact=none, kind=none, do not "
        "propose, no proposal object. Never overwrite a locked cut. Keep "
        "everything else the same."
    ),
    "corrections": (
        "Pick exactly one bucket. MUST: wrong or unreadable signage, "
        "burned-in text that lies, or a misspelled on-set graphic — "
        "status=needs_work, kind=defect, impact=medium or high, name the "
        "intent, propose a 360p draft alternate. NICE: an unmotivated prop "
        "(cup, bag, toolbox) the scene does not need — status=needs_work, "
        "kind=improvement, impact=low or medium, name the intent, propose "
        "that draft. LEAVE: no wrong signage, graphic, or unmotivated prop "
        "— status=ok, impact=none, kind=none, do not propose, no proposal "
        "object. Never overwrite a locked cut. Keep everything else the "
        "same. You MAY name the intent from looking; do not wait for a "
        "human brief."
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


def _public_context(context: dict[str, Any]) -> dict[str, Any]:
    skip = {"store", "settings", "payload", "media", "watch"}
    return {
        key: value
        for key, value in context.items()
        if key not in skip and not str(key).startswith("_")
    }


def station_inspect_prompt(station: str, context: dict[str, Any]) -> str:
    if station not in ROSTER:
        raise InspectNoteError(f"unknown station {station!r}")
    public = _public_context(context)
    return (
        f"You are the {station} finishing agent for Martini Shot.\n"
        f"{INSPECT_CONTRACT}\n"
        f"Specialty:\n{_SPECIALTY[station]}\n\n"
        "Ingest metadata on every look: ingested (bool), spoken_words "
        "(script from the original), scene (description). If ingested is "
        "true, use that script and description; do not invent a different "
        "line. If ingested is false, say so — do not guess dialogue.\n\n"
        f"Context:\n{json.dumps(public, default=str)}\n\n"
        f'The JSON field "station" MUST be "{station}". '
        f'The JSON field "agent" MUST be "{_AGENT[station]}". '
        f"Default cost_estimate_micros if unsure: "
        f"{DEFAULT_COST_MICROS[station]}. "
        'proposal.kind is "station_job" with "station" matching you and '
        '"args" for presets/intents/movements when needed. '
        "If status is needs_work you MUST include that proposal object. "
        "Keep summary to one short sentence so the JSON is complete."
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
    if str(payload.get("status") or "") == "needs_work" and not payload.get("proposal"):
        payload["proposal"] = {
            "kind": "station_job",
            "station": station,
            "args": {},
        }
    if station == "extend" and str(payload.get("status") or "") == "needs_work":
        proposal = dict(payload.get("proposal") or {})
        args = dict(proposal.get("args") or {})
        args.setdefault("tier", "draft")
        proposal["kind"] = str(proposal.get("kind") or "station_job")
        proposal["station"] = "extend"
        proposal["args"] = args
        payload["proposal"] = proposal
    if station == "corrections" and str(payload.get("status") or "") == "needs_work":
        proposal = dict(payload.get("proposal") or {})
        args = dict(proposal.get("args") or {})
        args.setdefault("tier", "draft")
        if not str(args.get("intent") or "").strip():
            args["intent"] = str(payload.get("summary") or "").strip()
        proposal["kind"] = str(proposal.get("kind") or "station_job")
        proposal["station"] = "corrections"
        proposal["args"] = args
        payload["proposal"] = proposal
    if payload.get("cost_estimate_micros") in (None, ""):
        payload["cost_estimate_micros"] = DEFAULT_COST_MICROS[station]
    return validate_inspect_note(payload)


def _ingest_look_note(context: dict[str, Any]) -> InspectNote:
    from backend.supervisor.station_agents.ingest_understand import scene_bag

    bag = scene_bag(context.get("scene_understanding") or context)
    shot_id = str(context.get("shot_id") or "")
    if bag.get("ingested"):
        words = bag["spoken_words"] or "(none)"
        scene = bag["scene"] or "(none)"
        return InspectNote(
            station="ingest",
            agent=_AGENT["ingest"],
            status="ok",
            impact="none",
            kind="none",
            summary=f"ingested; spoken_words={words}; scene={scene}",
            cost_estimate_micros=DEFAULT_COST_MICROS["ingest"],
            proposal={},
            shot_id=shot_id,
            reason="ingest look already on the shot",
        )
    return empty_note("ingest", agent=_AGENT["ingest"])


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
    if station == "ingest":
        note = _ingest_look_note(context)
        if note.status != "empty":
            return note
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
        note: InspectNote | None = None
        last_exc: Exception | None = None
        for _attempt in range(3):
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
                last_exc = None
                break
            except InspectNoteError as exc:
                last_exc = exc
                log.warning("inspect JSON retry station=%s err=%s", station, exc)
        if note is None:
            raise last_exc or InspectNoteError("inspect returned no JSON")
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
