"""A10 StationDecision contract (TDD, RED-first).

Every station agent returns a validated StationDecision: the deterministic
verdict rides along as ADVICE (owner ruling: the agent may take it under
advisement), the agent's own decision is explicit, and an override is
always a logged, first-class fact.
"""

from __future__ import annotations

import json

import pytest

from backend.supervisor.station_agents.base import (
    StationDecisionError,
    validate_station_decision,
)

DUB_DECISIONS = ("accept", "re_render", "needs_human")


def _payload(**overrides):
    payload = {
        "agent": "dub_qc",
        "decision": "accept",
        "reason": "timing within tolerance and audio clean",
        "confidence": "high",
    }
    payload.update(overrides)
    return payload


def test_valid_payload_round_trips():
    decision = validate_station_decision(
        _payload(),
        agent="dub_qc",
        allowed_decisions=DUB_DECISIONS,
        deterministic_suggestion="accept",
    )
    assert decision.decision == "accept"
    assert decision.overridden is False  # matches the deterministic suggestion
    assert decision.deterministic_advice == ""


def test_override_is_explicit_and_required_to_be_justified():
    # An override without a stated reason is refused outright.
    with pytest.raises(StationDecisionError, match="reason"):
        validate_station_decision(
            _payload(decision="re_render", reason=""),
            agent="dub_qc",
            allowed_decisions=DUB_DECISIONS,
            deterministic_suggestion="accept",
        )
    decision = validate_station_decision(
        _payload(decision="re_render", reason="sync drift audible despite 40ms delta"),
        agent="dub_qc",
        allowed_decisions=DUB_DECISIONS,
        deterministic_suggestion="accept",
    )
    assert decision.overridden is True


def test_decision_outside_vocabulary_refused():
    with pytest.raises(StationDecisionError, match="decision"):
        validate_station_decision(
            _payload(decision="delete_everything"),
            agent="dub_qc",
            allowed_decisions=DUB_DECISIONS,
        )


def test_wrong_agent_payload_refused():
    with pytest.raises(StationDecisionError, match="agent"):
        validate_station_decision(
            _payload(agent="someone_else"),
            agent="dub_qc",
            allowed_decisions=DUB_DECISIONS,
        )


def test_empty_reason_refused():
    with pytest.raises(StationDecisionError, match="reason"):
        validate_station_decision(
            _payload(reason="  "),
            agent="dub_qc",
            allowed_decisions=DUB_DECISIONS,
        )


def test_proposal_must_be_in_h0_registry():
    from backend.supervisor.agents.finding_schema import REGISTRY_COMMANDS

    decision = validate_station_decision(
        _payload(
            decision="needs_human",
            proposal={
                "command_name": "retry_job",
                "args": {"job_id": "job-1"},
                "cost_estimate_micros": 100,
            },
        ),
        agent="dub_qc",
        allowed_decisions=DUB_DECISIONS,
        deterministic_suggestion="needs_human",
    )
    assert decision.proposal["command_name"] in REGISTRY_COMMANDS
    with pytest.raises(StationDecisionError, match="registry"):
        validate_station_decision(
            _payload(
                decision="needs_human",
                proposal={
                    "command_name": "nuke_station",
                    "args": {},
                    "cost_estimate_micros": 0,
                },
            ),
            agent="dub_qc",
            allowed_decisions=DUB_DECISIONS,
        )


# --- Dub QC agent: deterministic surface (prompt + parsing) -----------------


def _measurement(verdict: str):
    return {
        "duration_delta_ms": 20,
        "sync_offset_ms": 15,
        "tolerance_ms": 45.0,
        "verdict": verdict,
    }


def test_dub_prompt_carries_measurements_script_and_override_clause():
    from backend.supervisor.station_agents.dub_qc import build_prompt

    prompt = build_prompt(_measurement("pass"), script="Prise trois, épisode un.")
    assert "+20" in prompt and "deterministic verdict: pass" in prompt
    # The agent must know the reference line to catch MISSING content, not
    # just cut audio (evidence: fr-03 'Prise trois' alone sounded complete).
    assert "Prise trois, épisode un." in prompt
    # The owner's ruling is IN the prompt: advice is advisory.
    assert "override" in prompt.lower()


def test_dub_parse_maps_advice_and_flags_overrides():
    from backend.supervisor.station_agents.dub_qc import parse_dub_decision

    ok = parse_dub_decision(
        json.dumps(
            {
                "agent": "dub_qc",
                "classification": "clean",
                "decision": "accept",
                "reason": "speech intact and aligned",
                "confidence": "high",
            }
        ),
        _measurement("pass"),
    )
    assert ok.overridden is False

    override = parse_dub_decision(
        json.dumps(
            {
                "agent": "dub_qc",
                "classification": "truncated",
                "decision": "re_render",
                "reason": "last word clipped even though delta is in tolerance",
                "confidence": "medium",
            }
        ),
        _measurement("pass"),
    )
    assert override.overridden is True  # agent disagrees with 'pass' → accept

    with pytest.raises(StationDecisionError):
        parse_dub_decision(
            json.dumps(
                {
                    "agent": "dub_qc",
                    "classification": "clean",
                    "decision": "accept",
                    "reason": "ok",
                    "confidence": "extreme",
                }
            ),
            _measurement("pass"),
        )
