"""D-12 Coverage — angle vocabulary, references, agent abstention."""

from __future__ import annotations

import json

import pytest


def test_coverage_prompt_requires_angle_intent_and_references() -> None:
    from backend.stations.coverage.run import ANGLES, build_coverage_prompt

    prompt = build_coverage_prompt(
        angle="over_the_shoulder",
        intent="hold on the lead as they turn",
        reference_count=2,
    )
    assert "over the shoulder" in prompt
    assert "2 attached subject reference" in prompt
    with pytest.raises(ValueError, match="unknown coverage angle"):
        build_coverage_prompt(angle="dutch", intent="x", reference_count=1)
    with pytest.raises(ValueError, match="explicit intent"):
        build_coverage_prompt(angle=ANGLES[0], intent="  ", reference_count=1)
    with pytest.raises(ValueError, match="subject reference"):
        build_coverage_prompt(angle=ANGLES[0], intent="hold", reference_count=0)


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
