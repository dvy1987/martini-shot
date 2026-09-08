"""TDD: continuity specialist maps add/remove-from-cut into ranked H-0 actions."""

from __future__ import annotations

from backend.supervisor.agents.continuity_investigator import finding_from_decision
from backend.supervisor.case import CONTINUITY, Case, Claim
from backend.supervisor.station_agents.base import StationDecision


def _case(**evidence):
    return Case(
        case_id="case-cut-1",
        version=1,
        created_at="2026-09-08T00:00:00Z",
        trigger={"kind": "pickups_needs_human", "job_id": "job-cut", "project_id": "p"},
        evidence={"job_id": "job-cut", **evidence},
    )


def _decision(name: str) -> StationDecision:
    return StationDecision(
        agent="continuity",
        decision=name,
        reason=f"continuity chose {name}",
        confidence="high",
        deterministic_advice=name,
        overridden=False,
        proposal={},
        raw={},
    )


def test_add_to_continuity_finding_carries_shot_and_alternate() -> None:
    job = {
        "id": "job-cut",
        "result": {"shot_id": "shot-1", "alternate_id": "alt-new"},
    }
    ctx = {
        "shot_id": "shot-1",
        "locked": False,
        "alternates": [
            {
                "alternate_id": "alt-new",
                "status": "draft",
                "eval_scores": {"flicker": 0.004, "vision_judge": 4.6},
            }
        ],
    }
    finding = finding_from_decision(
        _case(job=job), _decision("add_to_continuity"), job, ctx
    )
    assert finding.specialist == CONTINUITY
    assert len(finding.proposed_actions) == 1
    action = finding.proposed_actions[0]
    assert action.command_name == "add_to_continuity"
    assert action.args == {"shot_id": "shot-1", "alternate_id": "alt-new"}
    assert action.reversible is True


def test_remove_from_continuity_finding_carries_shot_and_alternate() -> None:
    job = {
        "id": "job-cut",
        "result": {"shot_id": "shot-1", "retire_alternate_id": "alt-old"},
    }
    ctx = {
        "shot_id": "shot-1",
        "locked": False,
        "current_alternate_id": "alt-old",
        "alternates": [{"alternate_id": "alt-old", "status": "continuity"}],
    }
    finding = finding_from_decision(
        _case(job=job), _decision("remove_from_continuity"), job, ctx
    )
    action = finding.proposed_actions[0]
    assert action.command_name == "remove_from_continuity"
    assert action.args == {"shot_id": "shot-1", "alternate_id": "alt-old"}
    assert action.reversible is True


def test_abstain_proposes_nothing() -> None:
    job = {"id": "job-cut", "result": {}}
    finding = finding_from_decision(_case(job=job), _decision("abstain"), job, {})
    assert finding.proposed_actions == []
    assert finding.claims and isinstance(finding.claims[0], Claim)
