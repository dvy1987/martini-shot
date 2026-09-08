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
