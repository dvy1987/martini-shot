"""Creative Orchestrator: selects Stage 1a specialists for a brief or signal.

Routing is deterministic from evidence type when possible; a metered Gemini
call may synthesize the final partition later (EDD-gated). No agent executes
— selected proposals still go through H-0."""

from __future__ import annotations

import json
from typing import Any

PERSONA = "creative_orchestrator"

# Closed specialist roster for the demo (Amendment A11).
SPECIALISTS: tuple[str, ...] = (
    "corrections",
    "relight",
    "draft_first",
    "coverage",
    "revision_room",
    "camera_language",
)

_SIGNAL_ROUTES: dict[str, tuple[str, ...]] = {
    "correction_requested": ("corrections", "draft_first"),
    "relight_requested": ("relight", "draft_first"),
    "coverage_requested": ("coverage", "draft_first"),
    "camera_language_requested": ("camera_language", "draft_first"),
    "script_changed": ("revision_room",),
    "draft_ready": ("draft_first",),
}

_BRIEF_TOKENS: tuple[tuple[str, str], ...] = (
    ("sign", "corrections"),
    ("text", "corrections"),
    ("replace", "corrections"),
    ("relight", "relight"),
    ("noir", "relight"),
    ("lamp", "relight"),
    ("coverage", "coverage"),
    ("close-up", "coverage"),
    ("close up", "coverage"),
    ("reverse", "coverage"),
    ("dolly", "camera_language"),
    ("handheld", "camera_language"),
    ("steadicam", "camera_language"),
    ("whip", "camera_language"),
    ("script", "revision_room"),
    ("caption", "revision_room"),
    ("master", "draft_first"),
)


def route_creative_agents(*, brief: str = "", signal: str | None = None) -> list[str]:
    """Deterministic specialist selection. Empty brief + unknown signal
    selects nobody — the orchestrator must not invent work."""
    selected: list[str] = []
    if signal and signal in _SIGNAL_ROUTES:
        selected.extend(_SIGNAL_ROUTES[signal])
    lowered = brief.lower()
    for token, agent in _BRIEF_TOKENS:
        if token in lowered and agent not in selected:
            selected.append(agent)
    if selected and "draft_first" not in selected and "revision_room" not in selected:
        selected.append("draft_first")
    return [name for name in SPECIALISTS if name in selected]


def build_synthesis_prompt(
    *, brief: str, signal: str | None, candidates: list[dict[str, Any]]
) -> str:
    return (
        "You are the Creative Orchestrator for Martini Shot. Select only "
        "the indexed candidates that improve the whole video. You cannot "
        "invent commands, costs, or evidence.\n\n"
        f"Brief: {brief}\nSignal: {signal}\n"
        f"Candidates:\n{json.dumps(list(enumerate(candidates)), default=str)}\n"
        "Respond with JSON: selected_indexes, rejected_indexes, summary, "
        "estimated_cost_micros."
    )
