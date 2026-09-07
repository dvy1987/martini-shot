"""Ingest understand agent: watch the original clip after the file check.

Produces two shot-metadata fields from one metered Gemini watch:
spoken words (or none), and a short description of what is happening.
Never invents dialogue on a silent soundtrack.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from backend.core.media import FFmpeg
from backend.shots import lifecycle as shots
from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "ingest_understand"
DECISIONS = ("understood", "needs_human")
SUGGESTION = "understood"
MAX_FRAMES = 6

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {"type": "string", "enum": ["understood", "needs_human"]},
        "has_speech": {"type": "boolean"},
        "spoken_words": {"type": "string"},
        "scene": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "agent",
        "decision",
        "has_speech",
        "spoken_words",
        "scene",
        "reason",
        "confidence",
    ],
}


def build_prompt() -> str:
    return (
        "You are the Ingest Understand agent for Martini Shot. WATCH the "
        "attached frames and LISTEN to the attached audio. This is the "
        "original clip, not a dub.\n\n"
        "Write two fields for shot metadata:\n"
        "1. spoken_words — the words that are actually spoken, verbatim. "
        "If nobody speaks (room tone, a beep, music only, silence), "
        "has_speech=false and spoken_words MUST be empty. Do not invent "
        "dialogue. Do not caption on-screen text that is not spoken.\n"
        "2. scene — a short description of what is happening on camera "
        "(who/where/what). Describe the picture even when there is no "
        "speech. Do not replace the picture with a story that is not there.\n\n"
        "If you cannot see or hear the clip, choose needs_human.\n\n"
        'Respond ONLY with JSON: {"agent": "ingest_understand", '
        '"decision": "understood|needs_human", "has_speech": true, '
        '"spoken_words": "...", "scene": "...", "reason": "...", '
        '"confidence": "low|medium|high"}.'
    )


def parse_understand_decision(text: str) -> StationDecision:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    spoken = str(payload.get("spoken_words") or "").strip()
    has_speech = bool(payload.get("has_speech")) and bool(spoken)
    payload["has_speech"] = has_speech
    payload["spoken_words"] = spoken if has_speech else ""
    payload["scene"] = str(payload.get("scene") or "").strip()
    return validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=SUGGESTION,
    )


def scene_understanding_from_shot(store: Any, shot_id: str) -> dict[str, Any] | None:
    if not shot_id:
        return None
    doc = shots.get_shot(store, shot_id) or {}
    meta = doc.get("scene_understanding")
    return dict(meta) if isinstance(meta, dict) else None


def watch_parts(
    media: FFmpeg, payload: bytes
) -> tuple[tuple[bytes, str] | None, list[tuple[bytes, str]]]:
    """Full soundtrack + a few frames so Gemini can hear and see."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "clip.mp4"
        src.write_bytes(payload)
        audio: tuple[bytes, str] | None = None
        try:
            audio = (media.extract_wav(src), "audio/wav")
        except RuntimeError:
            audio = None
        frames_dir = Path(tmp) / "frames"
        images: list[tuple[bytes, str]] = []
        try:
            frames = media.extract_frames(src, frames_dir, fps=1.0)[:MAX_FRAMES]
        except RuntimeError:
            frames = []
        for frame in frames:
            images.append((frame.read_bytes(), "image/png"))
        return audio, images


def understanding_doc(decision: StationDecision) -> dict[str, Any]:
    raw = decision.raw
    has_speech = bool(raw.get("has_speech"))
    return {
        "spoken_words": str(raw.get("spoken_words") or "") if has_speech else "",
        "has_speech": has_speech,
        "scene": str(raw.get("scene") or ""),
        "decision": decision.decision,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


def decide_ingest_understand(
    settings: Any,
    payload: bytes,
    media: FFmpeg,
) -> tuple[StationDecision, int]:
    """One metered Gemini watch. Caller stamps shot metadata."""
    from backend.supervisor.otel_ai import run_agent_call

    audio, images = watch_parts(media, payload)
    if audio is None and not images:
        return (
            StationDecision(
                agent=AGENT,
                decision="needs_human",
                reason="could not extract audio or frames from the clip",
                confidence="high",
                deterministic_advice=SUGGESTION,
                overridden=True,
            ),
            0,
        )
    kwargs: dict[str, Any] = {
        "span_name": "station.ingest.understand",
        "persona": AGENT,
        "response_schema": SCHEMA,
    }
    if audio is not None:
        kwargs["audio"] = audio
    if images:
        kwargs["images"] = images
    response = run_agent_call(settings, build_prompt(), **kwargs)
    return parse_understand_decision(response["text"]), int(response["cost_micros"])
