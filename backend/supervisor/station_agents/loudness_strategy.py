"""Loudness Strategist station agent (A10-3 + scene-aware mix).

Reads the deterministic meter AND listens to the audio. It does not
override the LUFS number — it chooses WHICH number this scene should
hit (whisper quieter than talk; an explosion or a crash of pans louder),
then the station applies the mix and re-measures.

Deterministic surface (no LLM): suggestion mapping, prompt construction
and response parsing are unit-tested; judgment is gated by live EDD
(loudness_strategy_judgment + scene_loudness_judgment)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "loudness_strategy"
DECISIONS = ("accept", "fix_stem", "apply_limiter", "needs_human")
STEM_DIAGNOSES = ("balanced", "dialogue_hot", "music_hot", "unknown")
SCENE_CLASSES = (
    "silence",
    "whisper",
    "dialogue",
    "shout",
    "impact",
    "explosion",
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["accept", "fix_stem", "apply_limiter", "needs_human"],
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
    return "needs_human"


def season_lines(season_state: list[dict[str, Any]]) -> str:
    """Per-sibling LUFS rows for coherence judgment."""
    if not season_state:
        return "(no sibling loudness measurements yet)"
    return "\n".join(
        f"- {r.get('episode_id')}: {r.get('lufs')} LUFS" for r in season_state
    )


def build_prompt(report: dict[str, Any], season_state: list[dict[str, Any]]) -> str:
    """Measurements + season + listen instruction. Scene class is not only
    whisper: crashes, explosions, shouts, and silence all get their own
    target. The station will mix toward target_lufs and re-measure."""
    notes = str(report.get("scene_notes") or report.get("audio_kind") or "")
    return (
        "You are the Loudness Strategist agent for Martini Shot. LISTEN to "
        "the attached audio (when present) and read the deterministic meter "
        "(ffmpeg ebur128). Pick the scene-appropriate loudness — not a "
        "single TV-loud number for every clip.\n\n"
        "Scene classes (choose exactly one):\n"
        "- silence: room tone / empty bed. Stay quiet; do NOT pump to "
        "dialogue level.\n"
        "- whisper: intimate quiet speech. Quieter than talk, still easy "
        "to hear (never bury the line).\n"
        "- dialogue: normal talk. Show baseline (~-16 LUFS streaming).\n"
        "- shout: raised voice, still speech.\n"
        "- impact: sudden disruption — pots and pans falling, a crash, a "
        "slam, a scare. Louder than talk.\n"
        "- explosion: blast / boom. Loudest class; still peak-limited.\n\n"
        "Deterministic measurements (this episode):\n"
        f"- job: {report.get('job_id')}\n"
        f"- episode: {report.get('episode_id')}\n"
        f"- audio kind: {report.get('audio_kind') or 'unknown'} "
        f"(prefer the dub, not the picture soundtrack)\n"
        f"- scene notes: {notes or '(none)'}\n"
        f"- integrated: {report.get('lufs_integrated')} LUFS "
        "(dialogue/streaming anchor -16.0 ±1 LU, broadcast -24.0 ±1 LU; "
        "THIS clip's target depends on scene_class)\n"
        f"- true peak: {report.get('true_peak_dbtp')} dBTP (ceiling -1.0)\n"
        f"- streaming verdict vs -16: {report.get('verdict_streaming')}\n"
        f"- broadcast verdict vs -24: {report.get('verdict_broadcast')}\n"
        f"- stem diagnosis: {report.get('stem_diagnosis')} "
        "(vocabulary: balanced|dialogue_hot|music_hot|unknown; dialogue "
        "band 300-3000 Hz vs music band 4-12 kHz; |gap| > 3 LU = "
        "imbalance)\n"
        f"- dialogue band: {report.get('dialogue_band_lufs')} LUFS, "
        f"music band: {report.get('music_band_lufs')} LUFS\n\n"
        f"Season (sibling episodes, LUFS):\n{season_lines(season_state)}\n\n"
        "Decision rules:\n"
        "1. Stem imbalance beats a blanket gain change: if dialogue_hot or "
        "music_hot, choose fix_stem (rebalance the bands, then re-measure) "
        "— an integrated pass with unbalanced stems is not an ear-pass.\n"
        "2. True-peak over -1.0 dBTP with sane integrated level = a "
        "transparent peak-limit pass (apply_limiter), not a loudness "
        "change.\n"
        "3. Season coherence: speech classes (whisper/dialogue/shout/"
        "silence) should sit in one family with siblings; impacts and "
        "explosions MAY be louder than the season median — that is "
        "correct, do not squash a bang to match a talky episode.\n"
        "4. If the meter produced nothing (meter_error), choose "
        "needs_human — you cannot fix what cannot be measured.\n"
        "5. If the clip is the wrong LEVEL for its scene (a whisper as "
        "loud as a shout, an explosion as quiet as talk, dialogue too "
        "quiet to hear), choose apply_limiter so the station MIXES toward "
        "your target_lufs. Whisper is only one example.\n"
        "6. Set target_lufs to the integrated level this scene should "
        "hit. Speech must stay audible (do not target below -23 LUFS for "
        "whisper/dialogue/shout).\n\n"
        "Routing: set streaming_route / broadcast_route to accept only if "
        "that profile is currently satisfiable; a profile whose verdict "
        "fails and whose failure your decision would not fix must be "
        "blocked (e.g. broadcast -24 target is a separate master "
        "concern).\n\n"
        'Respond ONLY with JSON: {"agent": "loudness_strategy", '
        '"decision": "accept|fix_stem|apply_limiter|needs_human", '
        '"streaming_route": "accept|block", "broadcast_route": '
        '"accept|block", "scene_class": "silence|whisper|dialogue|shout|'
        'impact|explosion", "target_lufs": -16.0, "reason": "...", '
        '"confidence": "low|medium|high"}.'
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
    if scene not in {"impact", "explosion"}:
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
