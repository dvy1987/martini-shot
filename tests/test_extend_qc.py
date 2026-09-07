"""TDD for the Extend QC station agent (A10-4 retrofit): judges the Omni
scene-extend draft over the deterministic flicker measurement and decides
accept_as_draft / bounded_revision / escalate, with the two-strikes rule
(a bounded revision already ran) and the meter-integrity rule (a pass
with no analyzed frames is not a pass)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.supervisor.station_agents.base import StationDecisionError
from backend.supervisor.station_agents.extend_qc import (
    build_prompt,
    decide_extend_qc,
    parse_extend_decision,
    suggestion_for_report,
)

HEALTHY: dict[str, Any] = {
    "job_id": "ext-001",
    "shot_id": "shot-12",
    "prompt": "Extend the scene: the detective slowly turns toward the window.",
    "render_model": "gemini-omni-1.1-flash-preview",
    "flicker": 0.0013,
    "flicker_gate": 0.02,
    "frames_analyzed": 56,
    "revision_attempt": 0,
}


def test_suggestion_maps_flicker_and_history() -> None:
    assert suggestion_for_report(HEALTHY) == "accept_as_draft"
    # First-attempt marginal breach -> one bounded revision.
    assert suggestion_for_report({**HEALTHY, "flicker": 0.021}) == "bounded_revision"
    # Second strike -> escalate.
    assert (
        suggestion_for_report({**HEALTHY, "flicker": 0.021, "revision_attempt": 1})
        == "escalate"
    )
    # An order of magnitude over the gate -> structurally broken.
    assert suggestion_for_report({**HEALTHY, "flicker": 0.21}) == "escalate"
    # A pass with no analyzed frames cannot be trusted.
    assert suggestion_for_report({**HEALTHY, "frames_analyzed": 0}) == "escalate"


def test_prompt_contains_measurements_and_rules() -> None:
    prompt = build_prompt(HEALTHY)
    assert "0.0013" in prompt
    assert "0.02" in prompt  # gate
    assert "two-strikes" in prompt.lower()
    assert "accept_as_draft|bounded_revision|escalate" in prompt
    assert "frames_analyzed" in prompt  # meter-integrity context
    fallback_prompt = build_prompt(
        {
            **HEALTHY,
            "omni_fallback": True,
            "omni_error": "Recitation: content blocked",
            "render_model": "veo-3.1-fast-generate-001",
        }
    )
    assert "omni_fallback: True" in fallback_prompt
    assert "Recitation: content blocked" in fallback_prompt


def test_parse_valid_decision() -> None:
    text = json.dumps(
        {
            "agent": "extend_qc",
            "decision": "accept_as_draft",
            "reason": "flicker within the healthy G0 band",
            "confidence": "high",
        }
    )
    assert parse_extend_decision(text, HEALTHY).decision == "accept_as_draft"


def test_parse_tolerates_fences() -> None:
    text = (
        "```json\n"
        + json.dumps(
            {
                "agent": "extend_qc",
                "decision": "bounded_revision",
                "reason": "marginal breach, first attempt",
                "confidence": "medium",
            }
        )
        + "\n```"
    )
    assert parse_extend_decision(text, HEALTHY).decision == "bounded_revision"


def test_parse_fails_loud_on_bad_decision() -> None:
    text = json.dumps(
        {
            "agent": "extend_qc",
            "decision": "re_roll_the_model",
            "reason": "x",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_extend_decision(text, HEALTHY)


def test_parse_fails_loud_on_missing_reason() -> None:
    text = json.dumps(
        {
            "agent": "extend_qc",
            "decision": "accept_as_draft",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_extend_decision(text, HEALTHY)


def test_decide_uses_one_metered_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(
                {
                    "agent": "extend_qc",
                    "decision": "accept_as_draft",
                    "reason": "healthy flicker band, first attempt",
                    "confidence": "high",
                }
            ),
            "model": "gemini-3.7-flash",
            "cost_micros": 1100,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    decision, cost = decide_extend_qc(object(), report=HEALTHY)
    assert cost == 1100
    assert len(calls) == 1
    assert "0.0013" in calls[0]["prompt"]
    assert decision.decision == "accept_as_draft"
