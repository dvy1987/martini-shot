"""TDD for the Pickups Vision QC station agent (A10-4 retrofit of D-6):
SEES real frame extracts (inline image parts) alongside the flicker
metric doc, and decides accept / retry_with_stronger_anchors /
needs_human — the one measurement-station agent that MAY override the
numeric gate (design decision 1: overrides explicit + reasoned)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.supervisor.station_agents.base import StationDecisionError
from backend.supervisor.station_agents.pickups_vision_qc import (
    build_prompt,
    decide_pickups_vision_qc,
    parse_vision_decision,
    suggestion_for_report,
)

MEASUREMENTS: dict[str, Any] = {
    "flicker": 0.012,
    "threshold": 0.18,
    "frames_analyzed": 56,
    "retries_used": 0,
    "ok": True,
}


def test_suggestion_maps_flicker_and_retries() -> None:
    assert suggestion_for_report(MEASUREMENTS) == "accept"
    # Over gate, retries left -> one strengthened-anchor re-render.
    assert (
        suggestion_for_report({**MEASUREMENTS, "flicker": 0.22})
        == "retry_with_stronger_anchors"
    )
    # Over gate, retries exhausted -> escalate.
    assert (
        suggestion_for_report({**MEASUREMENTS, "flicker": 0.41, "retries_used": 2})
        == "needs_human"
    )
    # Meter integrity: no frames analyzed -> not a pass you can trust.
    assert (
        suggestion_for_report({**MEASUREMENTS, "frames_analyzed": 0, "ok": False})
        == "needs_human"
    )


def test_prompt_contains_metric_doc_and_override_clause() -> None:
    prompt = build_prompt(MEASUREMENTS, num_images=2)
    assert "0.18" in prompt  # the gate from the metric doc
    assert "median" in prompt  # the metric definition (flicker doc)
    assert "override" in prompt.lower()  # explicit override clause
    assert "2" in prompt  # how many frame extracts are attached
    assert "accept|retry_with_stronger_anchors|needs_human" in prompt


def test_parse_valid_decision() -> None:
    text = json.dumps(
        {
            "agent": "pickups_vision_qc",
            "decision": "accept",
            "reason": "frames visibly clean; flicker in healthy band",
            "confidence": "high",
        }
    )
    assert parse_vision_decision(text, MEASUREMENTS).decision == "accept"


def test_parse_tolerates_fences() -> None:
    text = (
        "```json\n"
        + json.dumps(
            {
                "agent": "pickups_vision_qc",
                "decision": "retry_with_stronger_anchors",
                "reason": "banding visible, first attempt",
                "confidence": "medium",
            }
        )
        + "\n```"
    )
    decision = parse_vision_decision(text, MEASUREMENTS)
    assert decision.decision == "retry_with_stronger_anchors"


def test_parse_fails_loud_on_bad_decision() -> None:
    text = json.dumps(
        {
            "agent": "pickups_vision_qc",
            "decision": "ship_it_blind",
            "reason": "x",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_vision_decision(text, MEASUREMENTS)


def test_parse_fails_loud_on_missing_reason() -> None:
    text = json.dumps(
        {
            "agent": "pickups_vision_qc",
            "decision": "accept",
            "confidence": "low",
        }
    )
    with pytest.raises(StationDecisionError):
        parse_vision_decision(text, MEASUREMENTS)


def test_decide_uses_one_metered_call_with_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(
                {
                    "agent": "pickups_vision_qc",
                    "decision": "accept",
                    "reason": "frames clean despite the gate breach - "
                    "override: meter artifact suspected",
                    "confidence": "high",
                }
            ),
            "model": "gemini-3.7-flash",
            "cost_micros": 1600,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    images = [(b"\xff\xd8fake1", "image/jpeg"), (b"\xff\xd8fake2", "image/jpeg")]
    decision, cost = decide_pickups_vision_qc(
        object(), report=MEASUREMENTS, images=images
    )
    assert cost == 1600
    assert len(calls) == 1
    assert len(calls[0]["images"]) == 2  # both frames attached
    assert decision.decision == "accept"
