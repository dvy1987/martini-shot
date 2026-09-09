"""Loudness Strategist station agent (A10-3 + scene-aware mix).

Reads the deterministic meter AND listens to the audio. It does not
override the LUFS number — it chooses WHICH number this scene should
hit (quiet / normal / loud, with or without dialogue), then the station
applies the mix, lifts speech over the room when needed, and re-measures.
Never stops for a human."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "loudness_strategy"
DECISIONS = ("accept", "fix_stem", "apply_limiter")
STEM_DIAGNOSES = ("balanced", "dialogue_hot", "music_hot", "unknown")
SCENE_CLASSES = (
    "quiet-no-dialogue",
    "quiet-with-dialogue",
    "normal-no-dialogue",
    "normal-with-dialogue",
    "loud-no-dialogue",
    "loud-with-dialogue",
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["accept", "fix_stem", "apply_limiter"],
        },
        "streaming_route": {"type": "string", "enum": ["accept", "block"]},
        "broadcast_route": {"type": "string", "enum": ["accept", "block"]},
        "scene_class": {
            "type": "string",
            "enum": list(SCENE_CLASSES),
        },
        "target_lufs": {"type": "number"},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "agent",
        "decision",
        "streaming_route",
        "broadcast_route",
        "scene_class",
        "target_lufs",
        "reason",
        "confidence",
    ],
}


def suggestion_for_report(report: dict[str, Any]) -> str:
    """Deterministic default path for this report: stem imbalance beats a
    blanket gain change (rebalance first, re-measure after); true-peak and
    integrated misses are limiter work; meter garbage escalates."""
    if report.get("stem_diagnosis") in ("dialogue_hot", "music_hot"):
        return "fix_stem"
    streaming = str(report.get("verdict_streaming") or "meter_error")
    if streaming == "pass":
        return "accept"
    if streaming in ("fail_hot", "fail_quiet", "fail_true_peak"):
        return "apply_limiter"
    return "accept"


def season_lines(season_state: list[dict[str, Any]]) -> str:
    """Per-sibling LUFS rows for coherence judgment."""
    if not season_state:
        return "(no sibling loudness measurements yet)"
    return "\n".join(
        f"- {r.get('episode_id')}: {r.get('lufs')} LUFS" for r in season_state
    )


def build_prompt(report: dict[str, Any], season_state: list[dict[str, Any]]) -> str:
    """Measurements + season + listen. Six scene kinds. Never needs_human."""
    notes = str(report.get("scene_notes") or report.get("audio_kind") or "")
    spoken = str(report.get("spoken_words") or "")
    previous = report.get("previous_loudness") or {}
    return (
        "You are the Loudness Strategist agent for Martini Shot. LISTEN to "
        "the attached audio (when present) and read the deterministic meter "
        "(ffmpeg ebur128). Pick a comfortable hearing level for THIS scene "
        "— not a single TV-loud number for every clip.\n\n"
        "Scene classes (choose exactly one):\n"
        "- quiet-no-dialogue: soft wind, surf, empty room. Stay soft. Do "
        "not pump to talk level.\n"
        "- quiet-with-dialogue: intimate quiet speech. Softer than talk, "
        "the line still easy to hear.\n"
        "- normal-no-dialogue: everyday ambience, no line.\n"
        "- normal-with-dialogue: conversational talk. Show baseline.\n"
        "- loud-no-dialogue: explosion, crash, pans falling, no line. "
        "Louder than talk, still inside a comfortable range.\n"
        "- loud-with-dialogue: loud scene that still has speech. Louder "
        "than talk; the line must stand out against the room.\n\n"
        "Deterministic measurements (this episode):\n"
        f"- job: {report.get('job_id')}\n"
        f"- episode: {report.get('episode_id')}\n"
        f"- audio kind: {report.get('audio_kind') or 'unknown'} "
        f"(prefer the dub, not the picture soundtrack)\n"
        f"- scene notes: {notes or '(none)'}\n"
        f"- spoken_words: {spoken or '(none)'}\n"
        f"- previous shot continuation: {previous or '(none)'}\n"
        f"- integrated: {report.get('lufs_integrated')} LUFS "
        "(comfortable range about -26 to -10; THIS clip's target depends "
        "on scene_class)\n"
        f"- true peak: {report.get('true_peak_dbtp')} dBTP (ceiling -1.0)\n"
        f"- streaming verdict vs -16: {report.get('verdict_streaming')}\n"
        f"- broadcast verdict vs -24: {report.get('verdict_broadcast')}\n"
        f"- stem diagnosis: {report.get('stem_diagnosis')} "
        "(vocabulary: balanced|dialogue_hot|music_hot|unknown; dialogue "
        "band 300-3000 Hz vs the LOUDER of music band 4-12 kHz or room "
        "band below 300 Hz; |gap| > 3 LU = imbalance. A storm/wind/room "
        "bed is broadband and low, not a music score — it shows up in "
        "the room band.)\n"
        f"- dialogue band: {report.get('dialogue_band_lufs')} LUFS, "
        f"music band: {report.get('music_band_lufs')} LUFS, "
        f"room band: {report.get('room_band_lufs')} LUFS\n\n"
        f"Season (sibling episodes, LUFS):\n{season_lines(season_state)}\n\n"
        "Decision rules:\n"
        "1. If speech is covered by ambience (music_hot / buried line), "
        "choose fix_stem so the station LIFTS THE VOICE relative to the "
        "room, then re-measure. Do not only turn the whole track up.\n"
        "2. True-peak over -1.0 dBTP with sane integrated level = "
        "apply_limiter.\n"
        "3. If this shot continues the previous one, keep speech and "
        "ambience in family with that previous mix — no sudden jump. "
        "Season coherence: the show stays in one loudness family.\n"
        "4. If the meter produced nothing (meter_error), choose accept "
        "and say so in reason. Never needs_human. Best effort always.\n"
        "5. If the clip is the wrong LEVEL for its class, choose "
        "apply_limiter so the station mixes toward target_lufs.\n"
        "6. Speech classes must stay audible (never target below -23 "
        "LUFS when the class is *-with-dialogue).\n"
        "7. Loud classes may sit louder than talk; quiet classes softer; "
        "everything stays inside a comfortable hearing range.\n\n"
        "Routing: set streaming_route / broadcast_route to accept only if "
        "that profile is currently satisfiable.\n\n"
        'Respond ONLY with JSON: {"agent": "loudness_strategy", '
        '"decision": "accept|fix_stem|apply_limiter", '
        '"streaming_route": "accept|block", "broadcast_route": '
        '"accept|block", "scene_class": "quiet-no-dialogue|'
        "quiet-with-dialogue|normal-no-dialogue|normal-with-dialogue|"
        'loud-no-dialogue|loud-with-dialogue", "target_lufs": -16.0, '
        '"reason": "...", "confidence": "low|medium|high"}.'
    )


def parse_strategy_decision(text: str, report: dict[str, Any]) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract.
    Tolerates markdown code fences around the JSON but nothing else."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if isinstance(payload, dict):
        if str(payload.get("decision") or "") == "needs_human":
            payload["decision"] = "accept"
        payload = _coerce_event_at_talk_level(payload, report)
    return validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=suggestion_for_report(report),
    )


def _coerce_event_at_talk_level(
    payload: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    """Hard gate (live miss scene-05): a bang sitting at the dialogue
    number is not an accept. Streaming -16 is the talk anchor, not the
    explosion's target."""
    scene = str(payload.get("scene_class") or "")
    if scene not in {"loud-no-dialogue", "loud-with-dialogue"}:
        return payload
    if str(payload.get("decision") or "") != "accept":
        return payload
    if report.get("stem_diagnosis") in ("dialogue_hot", "music_hot"):
        return payload
    streaming = str(report.get("verdict_streaming") or "")
    if streaming == "pass":
        return {**payload, "decision": "apply_limiter"}
    return payload


def decide_loudness_strategy(
    settings: Any,
    *,
    report: dict[str, Any],
    season_state: list[dict[str, Any]],
    audio: tuple[bytes, str] | None = None,
) -> tuple[StationDecision, int]:
    """THE real loudness strategy judgment: one metered Gemini call over
    the measurements plus the season state, listening when audio is
    attached. Returns (decision, cost_micros). Raises on any
    API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    kwargs: dict[str, Any] = {
        "span_name": "station.loudness_strategy.agent",
        "persona": AGENT,
        "response_schema": SCHEMA,
    }
    if audio is not None:
        kwargs["audio"] = audio
    response = run_agent_call(
        settings,
        build_prompt(report, season_state),
        **kwargs,
    )
    decision = parse_strategy_decision(response["text"], report)
    return decision, int(response["cost_micros"])


def build_inspect_prompt(context: dict[str, Any]) -> str:
    """Finishing look: unhearable is high; thin-but-legal mix is still work."""
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("loudness", context)
