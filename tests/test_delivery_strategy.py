"""TDD for the Delivery Strategist station agent (A10-3): profile
selection over real per-destination evaluations, accept-with-deviation
with rationale, and fix suggestions routed through H-0 (the agent
proposes, H-0 executes)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.supervisor.station_agents.base import StationDecisionError
from backend.supervisor.station_agents.delivery_strategy import (
    build_prompt,
    decide_delivery_strategy,
    parse_strategy_decision,
    suggestion_for_evaluations,
)

PASS_EVAL: dict[str, Any] = {
    "destination": "streaming",
    "verdict": "pass",
    "violations": [],
}
LOUD_FAIL: dict[str, Any] = {
    "destination": "broadcast",
    "verdict": "fail",
    "violations": [{"rule_id": "DEL-006", "message": "loudness -16.1 (fail_hot)"}],
}


def test_suggestion_prefers_a_full_pass() -> None:
    assert suggestion_for_evaluations([PASS_EVAL, LOUD_FAIL]) == "deliver"
    # Nothing passes anywhere -> hold (a visible, auditable stop state).
    assert suggestion_for_evaluations([LOUD_FAIL]) == "hold"
    # No evaluations at all is a caller bug, not a strategy.
    with pytest.raises(ValueError):
        suggestion_for_evaluations([])


def test_prompt_contains_evaluations_and_rules() -> None:
    prompt = build_prompt(
        {"format": "mp4", "codec": "h264"},
        [PASS_EVAL, LOUD_FAIL],
    )
    assert "streaming" in prompt and "broadcast" in prompt
    assert "DEL-006" in prompt
    assert "deviation" in prompt.lower()  # accept-with-deviation rule
    assert "H-0" in prompt  # fix suggestions route through H-0
    assert "deliver|deliver_with_deviation|hold|needs_human" in prompt


def test_parse_valid_decision() -> None:
    text = json.dumps(
        {
            "agent": "delivery_strategy",
            "decision": "deliver",
            "destination": "streaming",
            "reason": "streaming passes every rule",
            "confidence": "high",
        }
    )
    decision = parse_strategy_decision(text, [PASS_EVAL, LOUD_FAIL])
    assert decision.decision == "deliver"
    assert decision.raw["destination"] == "streaming"


def test_parse_proposal_is_registry_gated() -> None:
    good = json.dumps(
        {
            "agent": "delivery_strategy",
            "decision": "hold",
            "destination": "none",
            "proposal": {"command_name": "retry_job", "args": {"job_id": "j1"}},
            "reason": "codec mismatch is fixable by re-render",
            "confidence": "high",
        }
    )
    decision = parse_strategy_decision(good, [LOUD_FAIL])
    assert decision.proposal["command_name"] == "retry_job"
    # An unknown command must fail loud (the agent proposes, H-0 executes).
    bad = json.dumps(
        {
            "agent": "delivery_strategy",
            "decision": "hold",
            "destination": "none",
            "proposal": {"command_name": "rm_rf_everything", "args": {}},
            "reason": "x",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_strategy_decision(bad, [LOUD_FAIL])


def test_parse_tolerates_fences() -> None:
    text = (
        "```json\n"
        + json.dumps(
            {
                "agent": "delivery_strategy",
                "decision": "deliver_with_deviation",
                "destination": "streaming",
                "reason": "1.2 LU off, structural rules clean",
                "confidence": "medium",
            }
        )
        + "\n```"
    )
    decision = parse_strategy_decision(text, [LOUD_FAIL])
    assert decision.decision == "deliver_with_deviation"


def test_parse_fails_loud_on_bad_decision() -> None:
    text = json.dumps(
        {
            "agent": "delivery_strategy",
            "decision": "ship_it_anyway",
            "destination": "streaming",
            "reason": "x",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_strategy_decision(text, [PASS_EVAL])


def test_parse_fails_loud_on_missing_reason() -> None:
    text = json.dumps(
        {
            "agent": "delivery_strategy",
            "decision": "deliver",
            "destination": "streaming",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_strategy_decision(text, [PASS_EVAL])


def test_decide_uses_one_metered_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(
                {
                    "agent": "delivery_strategy",
                    "decision": "deliver",
                    "destination": "streaming",
                    "reason": "streaming passes every rule",
                    "confidence": "high",
                }
            ),
            "model": "gemini-3.7-flash",
            "cost_micros": 1300,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    decision, cost = decide_delivery_strategy(
        object(),
        probe={"format": "mp4", "codec": "h264"},
        evaluations=[PASS_EVAL, LOUD_FAIL],
    )
    assert cost == 1300
    assert len(calls) == 1
    assert "DEL-006" in calls[0]["prompt"]
    assert decision.decision == "deliver"
