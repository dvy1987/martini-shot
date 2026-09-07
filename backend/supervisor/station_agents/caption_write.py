"""Caption Writer station agent: produce an SRT when none exists.

Used when Delivery has audio but no script (or the deterministic writer
could not emit a legal cue set). Meaning preservation is the hard rule:
do not invent or drop dialogue. Every proposal is re-validated by D-3
before it can ship.
"""

from __future__ import annotations

import json
from typing import Any

from backend.stations.delivery.captions import Cue, validate_cues
from backend.stations.loudness.scene import SPEECH_FLOOR_LUFS
from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "caption_write"
DECISIONS = ("write", "needs_human")
SUGGESTION = "needs_human"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {"type": "string", "enum": ["write", "needs_human"]},
        "cues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "lines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_s", "end_s", "lines"],
            },
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "heard_speech": {"type": "boolean"},
        "audio_too_quiet": {"type": "boolean"},
        "proposal": {
            "type": "object",
            "properties": {
                "command_name": {"type": "string"},
                "args": {"type": "object"},
            },
        },
    },
    "required": ["agent", "decision", "reason", "confidence"],
}


def quiet_audio_orchestrator_note(
    lufs: float,
    *,
    loudness_job_id: str,
    has_speech: bool,
) -> dict[str, Any] | None:
    """Tell the orchestrator to retry loudness only when speech is too quiet.

    Silence / room tone may sit far under the speech floor on purpose.
    Pumping that to talk level is a mix miss — do not send it to loudness.
    """
    if not has_speech or not loudness_job_id:
        return None
    if lufs >= SPEECH_FLOOR_LUFS:
        return None
    return {
        "kind": "audio_too_quiet",
        "has_speech": True,
        "lufs": lufs,
        "proposal": {
            "command_name": "retry_job",
            "args": {"job_id": loudness_job_id},
        },
    }


def build_prompt(
    script: str,
    duration_s: float,
    *,
    has_audio: bool,
    lufs: float | None = None,
) -> str:
    hear = (
        "LISTEN to the attached audio and caption what is said."
        if has_audio
        else "No audio is attached; use the script only."
    )
    measured = f"- measured loudness: {lufs} LUFS\n" if lufs is not None else ""
    return (
        "You are the Caption Writer agent for Martini Shot. Produce a "
        "complete caption cue set for this clip.\n\n"
        f"{hear}\n"
        f"- clip duration: {duration_s} seconds\n"
        f"{measured}"
        f"- script: {script.strip() or '(none)'}\n\n"
        "Rules:\n"
        "1. PRESERVE MEANING. If a script is provided, reuse those words "
        "verbatim — re-wrap and re-time only. Do not invent, paraphrase, "
        "or drop dialogue. If you are listening with no script, caption "
        "only what is spoken.\n"
        "2. Each line ≤ 42 characters. Reading speed ≤ 20 characters per "
        "second. Each cue ≥ 5/6 second. Gap between cues ≥ 2 frames. No "
        "overlaps. No empty cues.\n"
        "3. Return the COMPLETE cue set in chronological order.\n"
        "4. Your cues are RE-VALIDATED by the deterministic caption "
        "checker before they can ship. Residual violations block the set.\n"
        "5. If you cannot produce a legal set without changing the words, "
        "choose needs_human.\n"
        "6. If spoken words are too quiet to caption, tell the "
        "orchestrator (audio_too_quiet=true + retry_job on loudness). "
        "Silence / no spoken words is NOT a loudness miss — do not ask "
        "loudness to pump room tone up to talk level.\n\n"
        'Respond ONLY with JSON: {"agent": "caption_write", '
        '"decision": "write|needs_human", "cues": [{"start_s": 0.0, '
        '"end_s": 2.0, "lines": ["..."]}], "heard_speech": true, '
        '"audio_too_quiet": false, "reason": "...", '
        '"confidence": "low|medium|high"}. For needs_human, omit cues.'
    )


def parse_write_decision(
    text: str,
    *,
    lufs: float | None = None,
    has_speech: bool = True,
) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if payload.get("decision") == "write" and not isinstance(payload.get("cues"), list):
        raise ValueError("write requires a cues list")
    _ = lufs  # reserved: loudness retry is stamped by quiet_audio_orchestrator_note
    if not has_speech:
        payload["heard_speech"] = False
        payload["audio_too_quiet"] = False
        proposal = payload.get("proposal")
        if isinstance(proposal, dict) and proposal.get("command_name") == "retry_job":
            payload["proposal"] = {}
    return validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=SUGGESTION,
    )


def revalidate_written_cues(payload: dict[str, Any]) -> tuple[list[Cue], list[Any]]:
    rows = payload.get("cues")
    if not isinstance(rows, list):
        raise ValueError("cues must be a list")
    cues: list[Cue] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("cue entries must be objects")
        start, end, lines = row.get("start_s"), row.get("end_s"), row.get("lines")
        if (
            not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not isinstance(lines, list)
            or not all(isinstance(ln, str) for ln in lines)
        ):
            raise ValueError("cue entry fields have wrong types")
        cues.append(Cue(float(start), float(end), tuple(lines)))
    return cues, validate_cues(cues)


def decide_caption_write(
    settings: Any,
    *,
    script: str,
    duration_s: float,
    audio: tuple[bytes, str] | None = None,
) -> tuple[StationDecision, int]:
    """One metered Gemini call to write captions. Caller MUST re-validate.

    Hard gate: no script and no audio → needs_human (never invent dialogue).
    """
    if not script.strip() and audio is None:
        return (
            StationDecision(
                agent=AGENT,
                decision="needs_human",
                reason="no script and no audio — refusing to invent dialogue",
                confidence="high",
                deterministic_advice=SUGGESTION,
                overridden=False,
            ),
            0,
        )
    from backend.supervisor.otel_ai import run_agent_call

    kwargs: dict[str, Any] = {
        "span_name": "station.caption_write.agent",
        "persona": AGENT,
        "response_schema": SCHEMA,
    }
    if audio is not None:
        kwargs["audio"] = audio
    response = run_agent_call(
        settings,
        build_prompt(script, duration_s, has_audio=audio is not None),
        **kwargs,
    )
    return parse_write_decision(response["text"]), int(response["cost_micros"])
