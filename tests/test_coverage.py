"""D-12 Coverage — angle vocabulary, references, agent abstention."""

from __future__ import annotations

import json

import pytest


def test_coverage_prompt_requires_angle_intent_and_references() -> None:
    from backend.stations.coverage.run import ANGLES, build_coverage_prompt

    prompt = build_coverage_prompt(
        angle="over_the_shoulder",
        intent="hold on the lead as they turn",
        reference_count=1,
    )
    assert "over the shoulder" in prompt
    assert "source video" in prompt
    assert "attached subject reference" not in prompt
    stills = build_coverage_prompt(
        angle="close_up",
        intent="tighter",
        reference_count=2,
        extra_still_count=2,
    )
    assert "2 attached still" in stills
    with pytest.raises(ValueError, match="unknown coverage angle"):
        build_coverage_prompt(angle="dutch", intent="x", reference_count=1)
    with pytest.raises(ValueError, match="explicit intent"):
        build_coverage_prompt(angle=ANGLES[0], intent="  ", reference_count=1)
    with pytest.raises(ValueError, match="subject reference"):
        build_coverage_prompt(angle=ANGLES[0], intent="hold", reference_count=0)


def test_coverage_omni_edit_keeps_exactly_one_video() -> None:
    from backend.stations.coverage.run import omni_edit_refs

    src = "gs://b/table.mp4"
    assert omni_edit_refs(src, (src,)) == ()
    assert omni_edit_refs(src, (src, "gs://b/face.jpg")) == ("gs://b/face.jpg",)
    assert omni_edit_refs(src, ("gs://b/neighbor.mp4", "gs://b/face.jpg")) == (
        "gs://b/face.jpg",
    )


def test_draft_qc_decision_catches_a_single_frame_spike_the_mean_misses() -> None:
    """2026-09-09 demo: a real, localized single-frame corruption scored
    ~0.005 mean (well under gate) because the whole-clip average dilutes
    one bad frame across dozens of clean ones. The worst-frame spike must
    still gate it."""
    from backend.stations.coverage.run import (
        FLICKER_GATE,
        FLICKER_SPIKE_GATE,
        draft_qc_decision,
    )

    assert draft_qc_decision(0.001) == "pass"
    assert draft_qc_decision(0.001, spike=0.001) == "pass"
    assert draft_qc_decision(0.001, spike=FLICKER_SPIKE_GATE) == "needs_human"
    assert draft_qc_decision(FLICKER_GATE) == "needs_human"


def test_coverage_agent_abstains_without_references() -> None:
    from backend.supervisor.station_agents.coverage import parse_coverage_decision

    decision = parse_coverage_decision(
        json.dumps(
            {
                "agent": "coverage",
                "decision": "propose_coverage",
                "reason": "I can imagine the face",
                "confidence": "low",
            }
        ),
        {"angle": "close_up", "intent": "tighter", "reference_uris": []},
    )
    assert decision.decision == "abstain"
    assert decision.overridden is True
