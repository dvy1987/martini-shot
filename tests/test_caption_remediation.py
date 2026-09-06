"""TDD for the Caption Remediation station agent (A10-3): the closed loop —
the agent proposes concrete cue fixes; the DETERMINISTIC D-3 rule engine
re-validates every proposal before it can ship (C-1.1: the validator is
the arbiter)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.stations.delivery.captions import (
    RULE_LINE_LENGTH,
    RULE_READING_SPEED,
    validate_cues,
)
from backend.supervisor.station_agents.base import StationDecisionError
from backend.supervisor.station_agents.caption_remediation import (
    build_prompt,
    decide_caption_remediation,
    parse_remediation_decision,
    render_srt,
    revalidate_fixed_cues,
)

CUES: list[dict[str, Any]] = [
    {
        "index": 0,
        "start_s": 1.0,
        "end_s": 2.0,
        "lines": [
            "This line has far too many words to read comfortably in the brief moment it is displayed."
        ],
    },
    {"index": 1, "start_s": 8.0, "end_s": 11.0, "lines": ["Short enough."]},
]
VIOLATIONS: list[dict[str, Any]] = [
    {
        "rule_id": RULE_READING_SPEED,
        "message": "reading speed 85.0 cps > 20.0",
        "cue_index": 0,
    },
]

GOOD_FIX: dict[str, Any] = {
    "agent": "caption_remediation",
    "decision": "apply_fixes",
    "reason": "re-timed cue 0 into the free timeline; text preserved",
    "confidence": "high",
    "fixed_cues": [
        {
            "start_s": 1.0,
            "end_s": 4.5,
            "lines": ["This line has far too many words to"],
        },
        {
            "start_s": 4.6,
            "end_s": 7.9,
            "lines": ["read comfortably in the brief moment", "it is displayed."],
        },
    ],
}


def test_fixes_are_explicit_overrides_of_the_status_quo() -> None:
    # Without the agent, every D-3 violation lands as needs_human — that is
    # the deterministic status quo; an apply_fixes decision is therefore
    # always an explicit override, logged as such.
    decision = parse_remediation_decision(json.dumps(GOOD_FIX), CUES, VIOLATIONS)
    assert decision.overridden is True
    escalation = {
        **GOOD_FIX,
        "decision": "needs_human",
        "reason": "fix would require deleting dialogue",
    }
    assert (
        parse_remediation_decision(json.dumps(escalation), CUES, VIOLATIONS).overridden
        is False
    )


def test_prompt_contains_violations_and_rules() -> None:
    prompt = build_prompt(CUES, VIOLATIONS)
    assert "CAP-001" in prompt
    assert "reading speed 85.0 cps" in prompt
    assert '"start_s": 1.0' in prompt.replace(" ", "") or "1.0" in prompt
    assert "preserve" in prompt.lower()  # meaning-preservation rule
    assert "re-validated" in prompt.lower()  # closed-loop disclosure


def test_parse_valid_decision() -> None:
    decision = parse_remediation_decision(json.dumps(GOOD_FIX), CUES, VIOLATIONS)
    assert decision.decision == "apply_fixes"
    assert decision.raw["fixed_cues"][0]["end_s"] == 4.5


def test_parse_tolerates_fences() -> None:
    text = "```json\n" + json.dumps(GOOD_FIX) + "\n```"
    assert parse_remediation_decision(text, CUES, VIOLATIONS).decision == "apply_fixes"


def test_parse_fails_loud_on_bad_decision() -> None:
    bad = {**GOOD_FIX, "decision": "auto_destroy"}
    with pytest.raises(StationDecisionError):
        parse_remediation_decision(json.dumps(bad), CUES, VIOLATIONS)


def test_parse_fails_loud_on_non_list_cues() -> None:
    bad = {**GOOD_FIX, "fixed_cues": {"start_s": 1.0}}
    with pytest.raises(ValueError):
        parse_remediation_decision(json.dumps(bad), CUES, VIOLATIONS)


def test_parse_fails_loud_on_missing_reason() -> None:
    bad = {k: v for k, v in GOOD_FIX.items() if k != "reason"}
    with pytest.raises(StationDecisionError):
        parse_remediation_decision(json.dumps(bad), CUES, VIOLATIONS)


def test_revalidate_accepts_valid_fix() -> None:
    payload = json.loads(json.dumps(GOOD_FIX))
    cues, residual = revalidate_fixed_cues(payload)
    assert residual == []
    assert len(cues) == 2
    assert validate_cues(cues) == []


def test_revalidate_rejects_fix_with_residual_violation() -> None:
    payload = {
        **GOOD_FIX,
        "fixed_cues": [
            # Untouched over-long line spread across 7 s: reading speed now
            # passes but the LINE LENGTH rule must still catch it.
            {
                "start_s": 1.0,
                "end_s": 8.0,
                "lines": [
                    "This line has far too many words to read comfortably in the brief moment it is displayed."
                ],
            },
        ],
    }
    cues, residual = revalidate_fixed_cues(payload)
    assert cues
    assert any(v.rule_id == RULE_LINE_LENGTH for v in residual)


def test_revalidate_fails_loud_on_bad_shape() -> None:
    with pytest.raises(ValueError):
        revalidate_fixed_cues({"fixed_cues": "nope"})
    with pytest.raises(ValueError):
        revalidate_fixed_cues(
            {"fixed_cues": [{"start_s": "x", "end_s": 2.0, "lines": ["a"]}]}
        )


def test_render_srt_roundtrip() -> None:
    cues, _ = revalidate_fixed_cues(json.loads(json.dumps(GOOD_FIX)))
    srt = render_srt(cues)
    assert "1\n" in srt
    assert "00:00:01,000 --> 00:00:04,500" in srt


def test_decide_uses_one_metered_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(_settings: Any, prompt: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"prompt": prompt, **kwargs})
        return {
            "text": json.dumps(GOOD_FIX),
            "model": "gemini-3.7-flash",
            "cost_micros": 1500,
        }

    monkeypatch.setattr("backend.supervisor.otel_ai.run_agent_call", fake_call)
    decision, cost = decide_caption_remediation(
        object(), cues=CUES, violations=VIOLATIONS
    )
    assert cost == 1500
    assert len(calls) == 1
    assert "CAP-001" in calls[0]["prompt"]
    assert decision.decision == "apply_fixes"
