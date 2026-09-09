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


def test_draft_qc_decision_catches_a_single_frame_spike_the_mean_misses() -> None:
    """2026-09-09 demo: a real, localized single-frame corruption scored
    ~0.005 mean (well under gate) because the whole-clip average dilutes
    one bad frame across dozens of clean ones. The worst-frame spike must
    still gate it."""
    from backend.stations.camera_language.run import (
        FLICKER_GATE,
        FLICKER_SPIKE_GATE,
        draft_qc_decision,
    )

    assert draft_qc_decision(0.001) == "pass"
    assert draft_qc_decision(0.001, spike=0.001) == "pass"
    assert draft_qc_decision(0.001, spike=FLICKER_SPIKE_GATE) == "needs_human"
    assert draft_qc_decision(FLICKER_GATE) == "needs_human"


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
