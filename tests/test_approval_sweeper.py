"""H-0 sweeper (tranche 2, RED-first) — the watchdog that never leaves an
action silently stuck.

Contract (locked design §Sweeper + pre-mortem clauses):
- job terminal, approval stale -> reconcile exactly-once (projection, not truth)
- job non-terminal -> PATIENCE: do nothing (never auto-retry a render)
- acting > 15 min with non-terminal job -> failed, needs_human_review backstop
- fast action crashed mid-call (approved, no result) -> re-drive, capped at 3
- order-safety: a re-drive yields to a newer decision on the same target
  (the human's decision always stands)

Real Firestore (C-6.2), per-run collections; Harness reused from the
executor suite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.approvals.machine import propose_approval
from backend.approvals.sweeper import sweep_once
from backend.stations.spend import control as intake_control
from tests.test_approval_executor import Harness

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _isolated_intake_flag(monkeypatch, run_id):
    """Pause flags go to per-run control docs — never the shared live one."""
    from backend.stations.spend import control as _control

    monkeypatch.setattr(_control, "CONTROL", f"it-control-{run_id}")
    monkeypatch.setattr(_control, "INTAKE_DOC", "intake")
    yield


def _iso_minus(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _fast_crash(
    h: Harness, command: dict, *, decided_at: str, project_id: str = "it-sweep"
) -> str:
    """Seed the state a crash between the two fast transitions leaves:
    status 'approved', decision recorded, no result, handler never ran."""
    approval_id = propose_approval(
        h.store,
        {"project_id": project_id, "kind": "fix", "title": "t", "command": command},
        collection=h.approvals_col,
    )
    doc = h.store.get_doc(h.approvals_col, approval_id) or {}
    doc["status"] = "approved"
    doc["approver"] = "human-1"
    doc["decided_at"] = decided_at
    h.store.set_doc(h.approvals_col, approval_id, doc)
    return approval_id


def test_sweeper_reconciles_terminal_job_exactly_once(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    h.register_slow("make_job", project_id)
    approval_id = h.put_approval({"name": "make_job", "args": {}})
    h.machine.dispatch(approval_id, "approve")

    job = h.queue.lease("test-worker", ["ingest"])
    assert job is not None
    h.queue.complete(job.id, "test-worker", 0)  # job finished; hook never ran

    summary = sweep_once(env, h.queue, h.machine, collection=approvals_col)
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["status"] == "resolved"
    assert doc["result"]["ok"] is True
    assert summary["reconciled"] == 1

    assert (
        sweep_once(env, h.queue, h.machine, collection=approvals_col)["reconciled"] == 0
    ), "second sweep must be a no-op (exactly-once)"


def test_sweeper_leaves_nonterminal_job_alone(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    h.register_slow("make_job", project_id)
    approval_id = h.put_approval({"name": "make_job", "args": {}})
    h.machine.dispatch(approval_id, "approve")
    assert h.queue.lease("test-worker", ["ingest"]) is not None  # now leased

    before = env.get_doc(approvals_col, approval_id)
    summary = sweep_once(env, h.queue, h.machine, collection=approvals_col)

    after = env.get_doc(approvals_col, approval_id)
    assert after is not None and after["status"] == "acting"
    assert after["acting_since"] == before["acting_since"], "patience: untouched"
    assert summary["watching"] == 1 and summary["failed_stale"] == 0


def test_sweeper_backstops_15min_stale_acting_without_retrying(
    env, approvals_col, jobs_col
):
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    h.register_slow("make_job", project_id)
    approval_id = h.put_approval({"name": "make_job", "args": {}})
    h.machine.dispatch(approval_id, "approve")
    job = h.queue.lease("test-worker", ["ingest"])
    assert job is not None

    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None
    doc["acting_since"] = _iso_minus(20)
    env.set_doc(approvals_col, approval_id, doc)

    summary = sweep_once(env, h.queue, h.machine, collection=approvals_col)

    after = env.get_doc(approvals_col, approval_id)
    assert after is not None and after["status"] == "failed"
    assert after["result"]["needs_human_review"] is True
    assert summary["failed_stale"] == 1
    moved = h.queue.get(job.id)
    assert moved is not None and moved.status == "leased", (
        "never auto-retry: the job stays exactly where the lease machinery left it"
    )


def test_sweeper_redrives_crashed_fast_action_once(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    h.register_fast("flag_it", lambda ctx, a: {"ok": True})
    approval_id = _fast_crash(
        h, {"name": "flag_it", "args": {}}, decided_at=_iso_minus(1)
    )

    summary = sweep_once(env, h.queue, h.machine, collection=approvals_col)

    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["status"] == "resolved"
    assert doc["result"]["ok"] is True
    assert doc["sweep_retries"] == 1
    assert summary["redriven"] == 1


def test_sweeper_caps_redrive_at_three_then_fails(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    h.register_fast("flag_it", lambda ctx, a: {"ok": True})
    approval_id = _fast_crash(
        h, {"name": "flag_it", "args": {}}, decided_at=_iso_minus(1)
    )
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None
    doc["sweep_retries"] = 3
    env.set_doc(approvals_col, approval_id, doc)

    summary = sweep_once(env, h.queue, h.machine, collection=approvals_col)

    after = env.get_doc(approvals_col, approval_id)
    assert after is not None and after["status"] == "failed"
    assert after["result"]["needs_human_review"] is True
    assert summary["redriven"] == 0 and summary["failed_stale"] == 1


def test_sweeper_redrive_yields_to_newer_decision_on_same_target(
    env, approvals_col, jobs_col
):
    """A stale crashed resume must never replay over a newer pause: the
    newer decision stands, intake stays paused, the resume is 'superseded'."""
    h = Harness(env, approvals_col, jobs_col)
    pid = f"it-{uuid.uuid4().hex[:6]}"
    stale_resume = _fast_crash(
        h,
        {"name": "resume_intake", "args": {"station": "ingest"}},
        decided_at=_iso_minus(5),
        project_id=pid,
    )

    newer_pause = propose_approval(
        h.store,
        {
            "project_id": pid,
            "kind": "fix",
            "title": "t",
            "command": {"name": "pause_intake", "args": {"station": "ingest"}},
        },
        collection=h.approvals_col,
    )
    h.machine.dispatch(newer_pause, "approve", approver="human-1")
    assert intake_control.is_intake_paused(env, "ingest") is True

    summary = sweep_once(env, h.queue, h.machine, collection=approvals_col)

    after = env.get_doc(approvals_col, stale_resume)
    assert after is not None and after["status"] == "failed"
    assert after["result"].get("superseded") is True
    assert summary["superseded"] == 1 and summary["redriven"] == 0
    assert intake_control.is_intake_paused(env, "ingest") is True, (
        "the newer human pause must stand — stale resume never replays"
    )
