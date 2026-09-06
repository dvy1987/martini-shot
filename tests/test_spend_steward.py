"""TDD for the Spend Steward station agent (A10-4 retrofit of D-7).

The DETERMINISTIC policy triggers (runaway attempts, per-job cost cap,
daily budget) remain the authority for WHEN Spend Control acts — the
enforcement path is unchanged. The steward owns WHICH allowed response:
throttle_station / stop_all_intake / require_approval. Every enforcement
still creates the Grafana incident (C-4.3) — the agent cannot suppress
it; it only chooses among actions that all carry it."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.supervisor.station_agents.base import StationDecisionError
from backend.supervisor.station_agents.spend_steward import (
    build_prompt,
    decide_spend_steward,
    parse_steward_decision,
    suggestion_for_trigger,
)

BUDGET: dict[str, Any] = {
    "trigger_type": "daily_budget",
    "station": "all",
    "attempts": 0,
    "runaway_requeues": 8,
    "job_cost_micros": 0,
    "max_cost_micros_per_job": 0,
    "spent_micros": 5_200_000,
    "daily_budget_micros": 5_000_000,
}


def test_suggestion_maps_triggers() -> None:
    # Runaway churn -> throttle that station.
    assert (
        suggestion_for_trigger(
            {
                **BUDGET,
                "trigger_type": "runaway_attempts",
                "station": "extend",
                "attempts": 9,
            }
        )
        == "throttle_station"
    )
    # Per-job cap -> throttle that station.
    assert (
        suggestion_for_trigger(
            {**BUDGET, "trigger_type": "job_over_cap", "station": "dub"}
        )
        == "throttle_station"
    )
    # Budget breach under 2x -> deterministic default: throttle intake.
    assert suggestion_for_trigger(BUDGET) == "throttle_station"
    # Budget breach >= 2x -> runaway spend: stop everything.
    assert (
        suggestion_for_trigger({**BUDGET, "spent_micros": 10_000_001})
        == "stop_all_intake"
    )
    # Unknown trigger -> conservative: a human decides.
    assert suggestion_for_trigger({"trigger_type": "weird"}) == "require_approval"


def test_prompt_contains_trigger_and_rules() -> None:
    prompt = build_prompt(BUDGET)
    assert "5,200,000" in prompt or "5200000" in prompt
    assert "throttle_station|stop_all_intake|require_approval" in prompt
    assert "C-4.3" in prompt  # incident always created — the agent cannot suppress it
    assert "2x" in prompt  # the stop-all threshold is stated


def test_parse_valid_decision() -> None:
    text = json.dumps(
        {
            "agent": "spend_steward",
            "decision": "throttle_station",
            "station": "ingest",
            "reason": "runaway requeues on intake",
            "confidence": "high",
        }
    )
    decision = parse_steward_decision(text, BUDGET)
    assert decision.decision == "throttle_station"


def test_parse_tolerates_fences() -> None:
    text = (
        "```json\n"
        + json.dumps(
            {
                "agent": "spend_steward",
                "decision": "require_approval",
                "station": "dub",
                "reason": "borderline, no breach yet",
                "confidence": "medium",
            }
        )
        + "\n```"
    )
    assert parse_steward_decision(text, BUDGET).decision == "require_approval"


def test_parse_fails_loud_on_bad_decision() -> None:
    text = json.dumps(
        {
            "agent": "spend_steward",
            "decision": "ignore_it",
            "station": "all",
            "reason": "x",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_steward_decision(text, BUDGET)


def test_parse_fails_loud_on_missing_reason() -> None:
    text = json.dumps(
        {
            "agent": "spend_steward",
            "decision": "throttle_station",
            "station": "ingest",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_steward_decision(text, BUDGET)


def test_decide_uses_one_metered_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(
                {
                    "agent": "spend_steward",
                    "decision": "stop_all_intake",
                    "station": "all",
                    "reason": "runaway spend at 2.6x budget",
                    "confidence": "high",
                }
            ),
            "model": "gemini-3.7-flash",
            "cost_micros": 1200,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    runaway = {**BUDGET, "spent_micros": 13_000_000}
    decision, cost = decide_spend_steward(object(), trigger=runaway)
    assert cost == 1200
    assert len(calls) == 1
    assert "runaway" in calls[0]["prompt"].lower()
    assert decision.decision == "stop_all_intake"
