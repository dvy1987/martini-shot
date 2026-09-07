"""TDD contract for the production Post Supervisor synthesis agent."""

from __future__ import annotations

import pytest


def test_synthesis_accepts_only_a_complete_noninventive_action_partition() -> None:
    from backend.supervisor.agents.post_supervisor import validate_synthesis_payload

    candidates = [
        {"command_name": "retry_job", "args": {"job_id": "job-1"}},
        {"command_name": "pause_intake", "args": {"station": "ingest"}},
    ]
    result = validate_synthesis_payload(
        {
            "case_id": "case-1",
            "summary": "Retry the isolated failure; reject the broader pause.",
            "selected_action_indexes": [0],
            "rejected_action_indexes": [1],
            "dissent": ["spend guardian rejected the broader intervention"],
        },
        case_id="case-1",
        candidates=candidates,
    )

    assert result["ranked_actions"] == [candidates[0]]
    assert result["rejected_action_indexes"] == [1]


@pytest.mark.parametrize(
    "selected,rejected",
    [
        ([0], []),  # dropped candidate
        ([0, 0], [1]),  # duplicate candidate
        ([2], [0, 1]),  # unknown candidate
    ],
)
def test_synthesis_rejects_missing_duplicate_or_unknown_candidates(
    selected: list[int], rejected: list[int]
) -> None:
    from backend.supervisor.agents.post_supervisor import validate_synthesis_payload

    with pytest.raises(ValueError):
        validate_synthesis_payload(
            {
                "case_id": "case-1",
                "summary": "summary",
                "selected_action_indexes": selected,
                "rejected_action_indexes": rejected,
                "dissent": [],
            },
            case_id="case-1",
            candidates=[
                {"command_name": "retry_job", "args": {"job_id": "job-1"}},
                {"command_name": "pause_intake", "args": {"station": "ingest"}},
            ],
        )
