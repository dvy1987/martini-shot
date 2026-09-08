"""Bounded supervisor autonomy: diagnose, then at most one retry_job."""

from __future__ import annotations

import pytest

from backend.supervisor.agents.supervisor_retry import (
    SupervisorRetryError,
    parse_retry_decision,
)
from backend.supervisor.budget_loop import _select_retry_once, admit_retry_once


def test_retry_once_admits_a_first_transient_failure() -> None:
    ok, reason = admit_retry_once(
        command_name="retry_job",
        args={"job_id": "job-1"},
        job={
            "id": "job-1",
            "status": "failed",
            "attempts": 1,
            "station": "loudness",
            "error": "firestore write failed: 429 RESOURCE_EXHAUSTED",
            "result": {},
        },
    )
    assert ok is True
    assert reason == "retry_once"


def test_retry_once_refuses_a_second_supervisor_retry() -> None:
    ok, reason = admit_retry_once(
        command_name="retry_job",
        args={"job_id": "job-1"},
        job={
            "id": "job-1",
            "status": "failed",
            "attempts": 2,
            "error": "still failing",
            "result": {"supervisor_retries": 1},
        },
    )
    assert ok is False
    assert "already" in reason


def test_retry_once_refuses_corrupt_ingest() -> None:
    ok, reason = admit_retry_once(
        command_name="retry_job",
        args={"job_id": "job-c"},
        job={
            "id": "job-c",
            "status": "quarantined",
            "attempts": 1,
            "station": "ingest",
            "error": "checksum mismatch: sha256 ab12cf != manifest 9e23ab",
            "result": {"code": "CORRUPT_INPUT"},
        },
    )
    assert ok is False
    assert "corrupt" in reason or "checksum" in reason


def test_retry_once_refuses_locked_cut() -> None:
    ok, reason = admit_retry_once(
        command_name="retry_job",
        args={"job_id": "job-lock"},
        job={
            "id": "job-lock",
            "status": "needs_human",
            "attempts": 1,
            "error": "shot is LOCKED in continuity",
            "result": {"locked": True, "shot_id": "shot-14"},
        },
    )
    assert ok is False
    assert "locked" in reason


def test_retry_once_refuses_runaway_attempts() -> None:
    ok, reason = admit_retry_once(
        command_name="retry_job",
        args={"job_id": "job-r"},
        job={
            "id": "job-r",
            "status": "failed",
            "attempts": 8,
            "error": "identical error each attempt",
            "result": {},
        },
    )
    assert ok is False
    assert "runaway" in reason


def test_retry_once_refuses_house_wide_commands() -> None:
    ok, reason = admit_retry_once(
        command_name="lock_shot",
        args={"shot_id": "shot-1"},
        job={
            "id": "job-1",
            "status": "failed",
            "attempts": 1,
            "error": "x",
            "result": {},
        },
    )
    assert ok is False
    assert "command" in reason


def test_retry_once_admits_a_picture_fix() -> None:
    ok, reason = admit_retry_once(
        command_name="correct_shot",
        args={
            "job_id": "job-1",
            "shot_id": "shot-a",
            "project_id": "proj-1",
            "source_uri": "gs://bucket/clip.mp4",
            "intent": "remove the cup",
        },
        job={
            "id": "job-1",
            "status": "failed",
            "attempts": 1,
            "station": "pickups",
            "error": "cup still in frame after first pass",
            "result": {"locked": False},
        },
    )
    assert ok is True
    assert reason == "retry_once"


def test_retry_once_honors_gemini_abstain() -> None:
    ok, reason = admit_retry_once(
        command_name="retry_job",
        args={"job_id": "job-1"},
        job={
            "id": "job-1",
            "status": "failed",
            "attempts": 1,
            "error": "loudness gate breached",
            "result": {},
        },
        llm_decision="abstain",
    )
    assert ok is False
    assert "abstain" in reason


def test_parse_retry_decision_accepts_closed_vocab() -> None:
    assert (
        parse_retry_decision(
            '{"agent": "supervisor_retry", "decision": "retry", '
            '"reason": "429 rate limit on first attempt"}'
        )
        == "retry"
    )
    assert (
        parse_retry_decision(
            '{"agent": "supervisor_retry", "decision": "propose", '
            '"reason": "aspect needs a human destination call"}'
        )
        == "propose"
    )
    assert (
        parse_retry_decision(
            '{"agent": "supervisor_retry", "decision": "fix", '
            '"reason": "rewrite the cafe sign then re-run pickups"}'
        )
        == "fix"
    )


def test_parse_retry_decision_rejects_invented_decisions() -> None:
    with pytest.raises(SupervisorRetryError):
        parse_retry_decision(
            '{"agent": "supervisor_retry", "decision": "lock_shot", "reason": "x"}'
        )


class _DocStore:
    def __init__(self, jobs: dict) -> None:
        self._jobs = jobs

    def get_doc(self, collection: str, doc_id: str) -> dict | None:
        return self._jobs.get(doc_id)


def test_select_retry_once_keeps_only_the_first_admitted_retry() -> None:
    store = _DocStore(
        {
            "job-1": {
                "id": "job-1",
                "status": "failed",
                "attempts": 1,
                "error": "429 RESOURCE_EXHAUSTED",
                "result": {},
            },
            "job-2": {
                "id": "job-2",
                "status": "failed",
                "attempts": 1,
                "error": "429 RESOURCE_EXHAUSTED",
                "result": {},
            },
        }
    )
    chosen, skipped = _select_retry_once(
        store,
        "jobs",
        [
            {
                "command_name": "retry_job",
                "args": {"job_id": "job-1"},
                "cost_estimate_micros": 50_000,
            },
            {
                "command_name": "lock_shot",
                "args": {"shot_id": "shot-x"},
                "cost_estimate_micros": 1,
            },
            {
                "command_name": "retry_job",
                "args": {"job_id": "job-2"},
                "cost_estimate_micros": 50_000,
            },
        ],
    )
    assert [row["args"]["job_id"] for row in chosen] == ["job-1"]
    reasons = {str(row.get("command_name")): row["reason"] for row in skipped}
    assert "command" in reasons["lock_shot"]
    assert "already chosen" in reasons["retry_job"]


def test_select_retry_once_dispatches_a_fix_then_one_retry() -> None:
    store = _DocStore(
        {
            "job-1": {
                "id": "job-1",
                "status": "failed",
                "attempts": 1,
                "station": "pickups",
                "error": "cup still in frame",
                "result": {"locked": False},
            }
        }
    )
    chosen, skipped = _select_retry_once(
        store,
        "jobs",
        [
            {
                "command_name": "correct_shot",
                "args": {
                    "job_id": "job-1",
                    "shot_id": "shot-a",
                    "project_id": "proj-1",
                    "source_uri": "gs://bucket/clip.mp4",
                    "intent": "remove the cup",
                },
                "cost_estimate_micros": 3_000_000,
            },
            {
                "command_name": "retry_job",
                "args": {"job_id": "job-1"},
                "cost_estimate_micros": 50_000,
            },
            {
                "command_name": "lock_shot",
                "args": {"shot_id": "shot-a"},
                "cost_estimate_micros": 1,
            },
        ],
    )
    assert [row["command_name"] for row in chosen] == ["correct_shot", "retry_job"]
    assert skipped[0]["command_name"] == "lock_shot"
    assert "command" in str(skipped[0]["reason"])
