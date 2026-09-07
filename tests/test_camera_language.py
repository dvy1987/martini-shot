"""D-16 Camera Language — vocabulary gate and agent abstention."""

from __future__ import annotations

import json

import pytest


def test_camera_language_prompt_is_vocabulary_bound() -> None:
    from backend.stations.camera_language.run import (
        MOVEMENTS,
        build_camera_language_prompt,
    )

    prompt = build_camera_language_prompt(
        movement="dolly_zoom", reference_style="Hitchcock Vertigo"
    )
    assert "dolly zoom" in prompt.lower()
    assert "Hitchcock Vertigo" in prompt
    assert "Keep everything else the same" in prompt
    with pytest.raises(ValueError, match="unknown camera movement"):
        build_camera_language_prompt(movement="crane_360")
    assert "locked_off" in MOVEMENTS


def test_camera_language_agent_abstains_on_unknown_movement() -> None:
    from backend.supervisor.station_agents.camera_language import (
        parse_camera_language_decision,
    )

    decision = parse_camera_language_decision(
        json.dumps(
            {
                "agent": "camera_language",
                "decision": "propose_camera_language",
                "reason": "a drone orbit would be cooler",
                "confidence": "high",
            }
        ),
        {"movement": "drone_orbit"},
    )
    assert decision.decision == "abstain"
    assert decision.overridden is True
