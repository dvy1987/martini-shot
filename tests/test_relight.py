"""E-1 Relight Studio — deterministic prompt, dispatch, and agent gates."""

from __future__ import annotations

import json

import pytest


def test_relight_prompt_uses_named_presets() -> None:
    from backend.stations.relight.run import PRESETS, build_relight_prompt

    prompt = build_relight_prompt("noir")
    assert "noir" in prompt.lower()
    assert "Keep everything else the same" in prompt
    with pytest.raises(ValueError, match="unknown relight preset"):
        build_relight_prompt("neon_club")
    assert set(PRESETS) == {
        "practical_lamp",
        "ambient_daylight",
        "overhead_ceiling",
        "noir",
    }


def test_relight_station_is_dispatched() -> None:
    from backend.stations import run as dispatch

    assert "relight" in dispatch.STATION_NAMES


def test_relight_agent_abstains_on_unknown_preset() -> None:
    from backend.supervisor.station_agents.relight import parse_relight_decision

    decision = parse_relight_decision(
        json.dumps(
            {
                "agent": "relight",
                "decision": "propose_relight",
                "reason": "invented a cyberpunk look",
                "confidence": "medium",
            }
        ),
        {"preset": "cyberpunk"},
    )
    assert decision.decision == "abstain"
    assert decision.overridden is True
