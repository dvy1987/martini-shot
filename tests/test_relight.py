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


def test_draft_qc_decision_catches_a_single_frame_spike_the_mean_misses() -> None:
    """2026-09-09 demo: a real, localized single-frame corruption scored
    ~0.005 mean (well under gate) because the whole-clip average dilutes
    one bad frame across dozens of clean ones. The worst-frame spike must
    still gate it."""
    from backend.stations.relight.run import (
        FLICKER_GATE,
        FLICKER_SPIKE_GATE,
        draft_qc_decision,
    )

    assert draft_qc_decision(0.001) == "pass"
    assert draft_qc_decision(0.001, spike=0.001) == "pass"
    assert draft_qc_decision(0.001, spike=FLICKER_SPIKE_GATE) == "needs_human"
    assert draft_qc_decision(FLICKER_GATE) == "needs_human"


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
