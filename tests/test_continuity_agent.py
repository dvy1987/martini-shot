"""TDD for the Continuity station agent (H-1h): add/remove from the cut.

Owner ruling 2026-09-08: the supervisor may add or remove a take from the
cut inside the night envelope. Locked-cut overwrite (retry/render onto a
frozen shot) stays forbidden; pointer moves are the sanctioned path.
"""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import StationDecision, StationDecisionError
from backend.supervisor.station_agents.continuity import (
    DECISIONS,
    build_prompt,
    enforce_locked_cut_gate,
    parse_continuity_decision,
    suggestion_for_case,
)

LOCKED: dict[str, Any] = {
    "shot_id": "shot-sh-14",
    "locked": True,
    "alternates": [{"alternate_id": "alt-sh-14-1", "status": "in_continuity"}],
}

UNLOCKED_DRAFT: dict[str, Any] = {
    "shot_id": "shot-sh-31",
    "locked": False,
    "alternates": [
        {"alternate_id": "alt-sh-31-1", "status": "in_continuity"},
        {
            "alternate_id": "alt-sh-31-2",
            "status": "draft",
            "eval_scores": {"flicker": 0.004, "vision_judge": 4.6},
        },
    ],
}


def test_decision_vocabulary_includes_remove_from_the_cut() -> None:
    assert "remove_from_continuity" in DECISIONS
    assert "add_to_continuity" in DECISIONS


def test_suggestion_maps_locked_cut_to_add_not_retry() -> None:
    job = {
        "id": "job-con-01",
        "error": "pickup re-render proposed but the shot is LOCKED",
        "result": {"shot_id": "shot-sh-14", "locked": True},
    }
    assert suggestion_for_case(job, LOCKED) == "add_to_continuity"


def test_suggestion_maps_neighbor_breach_to_retry() -> None:
    job = {
        "id": "job-con-02",
        "result": {"shot_id": "shot-sh-22", "deltae": 8.1, "tolerance": 5.0},
    }
    ctx = {"shot_id": "shot-sh-22", "locked": False, "alternates": []}
    assert suggestion_for_case(job, ctx) == "retry_job"


def test_suggestion_maps_clean_draft_to_add() -> None:
    job = {
        "id": "job-con-03",
        "result": {"shot_id": "shot-sh-31", "alternate_id": "alt-sh-31-2"},
    }
    assert suggestion_for_case(job, UNLOCKED_DRAFT) == "add_to_continuity"


def test_suggestion_maps_remove_from_the_cut() -> None:
    job = {
        "id": "job-cut-out",
        "error": "operator asked to take this take out of the cut",
        "result": {
            "shot_id": "shot-sh-40",
            "retire_alternate_id": "alt-sh-40-1",
            "remove_from_cut": True,
        },
    }
    ctx = {
        "shot_id": "shot-sh-40",
        "locked": False,
        "alternates": [{"alternate_id": "alt-sh-40-1", "status": "continuity"}],
    }
    assert suggestion_for_case(job, ctx) == "remove_from_continuity"


def test_suggestion_maps_locked_remove_from_the_cut() -> None:
    job = {
        "id": "job-cut-locked",
        "error": "remove from continuity — this take should not stay in the cut",
        "result": {"shot_id": "shot-sh-14", "retire_alternate_id": "alt-sh-14-1"},
    }
    assert suggestion_for_case(job, LOCKED) == "remove_from_continuity"


def test_suggestion_abstains_without_a_shot() -> None:
    assert suggestion_for_case({"result": {}}, {"shot_id": None, "alternates": []}) == (
        "abstain"
    )


def test_prompt_says_supervisor_may_change_the_cut() -> None:
    prompt = build_prompt({"id": "job-x", "station": "pickups"}, UNLOCKED_DRAFT)
    assert "remove_from_continuity" in prompt
    assert "night envelope" in prompt.lower() or "supervisor" in prompt.lower()
    assert "NEVER propose retry_job" in prompt or "locked" in prompt.lower()


def test_parse_accepts_remove_from_continuity() -> None:
    job = {
        "id": "job-cut-out",
        "error": "take this take out of the cut",
        "result": {"shot_id": "shot-sh-40", "retire_alternate_id": "alt-sh-40-1"},
    }
    ctx = {
        "shot_id": "shot-sh-40",
        "locked": False,
        "alternates": [{"alternate_id": "alt-sh-40-1", "status": "continuity"}],
    }
    text = json.dumps(
        {
            "agent": "continuity",
            "decision": "remove_from_continuity",
            "reason": "The flagged take is in the cut and should come out.",
            "confidence": "high",
        }
    )
    decision = parse_continuity_decision(text, job, ctx)
    assert decision.decision == "remove_from_continuity"
    assert decision.overridden is False


def test_hard_gate_blocks_retry_on_locked_cut_but_allows_remove() -> None:
    retry = StationDecision(
        agent="continuity",
        decision="retry_job",
        reason="re-render",
        confidence="medium",
        deterministic_advice="add_to_continuity",
        overridden=True,
        proposal={"command_name": "retry_job"},
        raw={},
    )
    blocked = enforce_locked_cut_gate(retry, LOCKED)
    assert blocked.decision == "abstain"
    assert blocked.overridden is True

    remove = StationDecision(
        agent="continuity",
        decision="remove_from_continuity",
        reason="take it out of the cut",
        confidence="high",
        deterministic_advice="remove_from_continuity",
        overridden=False,
        proposal={},
        raw={},
    )
    allowed = enforce_locked_cut_gate(remove, LOCKED)
    assert allowed.decision == "remove_from_continuity"


def test_parse_rejects_unknown_decision() -> None:
    try:
        parse_continuity_decision(
            json.dumps(
                {
                    "agent": "continuity",
                    "decision": "overwrite_locked",
                    "reason": "no",
                    "confidence": "low",
                }
            ),
            {"result": {}},
            {"shot_id": None},
        )
    except StationDecisionError:
        return
    raise AssertionError("overwrite_locked must fail loud")
