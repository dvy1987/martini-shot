"""D-11 Draft-first state machine — master requires a QC-passing draft."""

from __future__ import annotations

import pytest

from backend.stations.draft_first import (
    MasterNotEligibleError,
    assert_master_eligible,
    cost_delta_micros,
    evaluate_readiness,
)


def test_master_rejected_without_eligible_draft() -> None:
    with pytest.raises(MasterNotEligibleError, match="QC-passing draft"):
        assert_master_eligible(
            [{"op": "correction", "status": "draft", "eval_scores": {"flicker": 0.9}}],
            op="correction",
        )


def test_master_eligible_when_draft_clears_bars() -> None:
    draft = {
        "alternate_id": "alt-ok",
        "op": "relight",
        "status": "draft",
        "created_at": "2026-09-07T00:00:00Z",
        "eval_scores": {"flicker": 0.003, "vision_judge": 4.2},
    }
    assert assert_master_eligible([draft], op="relight")["alternate_id"] == "alt-ok"
    readiness = evaluate_readiness(op="relight", alternates=[draft], revision_count=0)
    assert readiness.state == "master_eligible"


def test_failed_draft_revises_once_then_escalates() -> None:
    failed = {
        "op": "coverage",
        "status": "draft",
        "created_at": "2026-09-07T00:00:00Z",
        "eval_scores": {"flicker": 0.4},
    }
    assert (
        evaluate_readiness(op="coverage", alternates=[failed], revision_count=0).state
        == "revise"
    )
    assert (
        evaluate_readiness(op="coverage", alternates=[failed], revision_count=1).state
        == "escalate"
    )


def test_draft_first_agent_cannot_authorize_ineligible_master() -> None:
    import json

    from backend.supervisor.station_agents.draft_first import (
        parse_draft_first_decision,
    )

    decision = parse_draft_first_decision(
        json.dumps(
            {
                "agent": "draft_first",
                "decision": "authorize_master",
                "reason": "looks fine to me",
                "confidence": "high",
                "proposal": {
                    "command_name": "render_master",
                    "args": {"shot_id": "s", "project_id": "p", "op": "correction"},
                },
            }
        ),
        op="correction",
        alternates=[],
        revision_count=0,
    )
    assert decision.decision == "wait"
    assert decision.overridden is True


def test_cost_delta_is_integer_micros() -> None:
    assert cost_delta_micros(233_338, 700_000) == 466_662
