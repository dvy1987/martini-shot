"""H-0 approval→action executor (TDD, RED-first) — tranche 1: registry,
state machine, fast/slow dispatch, double-dispatch guard, retry rule,
atomic intake control, single-writer tripwire.

Real Firestore only (C-6.2); per-run collections for isolation; cleanup in
finally. The annotator is an injected callable (the production one uses the
Grafana MCP connector); tests count calls with a plain closure.
"""

from __future__ import annotations

import asyncio
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest

from backend.api.events import EventHub
from backend.approvals.commands import CommandRegistry
from backend.approvals.machine import ApprovalConflict, ApprovalStateMachine
from backend.jobs.models import Job, utc_now_iso
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import WORKER_ID, _persist
from backend.stations.spend import control as intake_control

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _isolated_intake_flag(monkeypatch, run_id):
    """Pause-flag tests use per-run control docs — never the shared live one."""
    monkeypatch.setattr(intake_control, "CONTROL", f"it-control-{run_id}")
    monkeypatch.setattr(intake_control, "INTAKE_DOC", "intake")
    yield


class Harness:
    """Wires a fresh registry + machine + queue against per-run collections."""

    def __init__(self, store, approvals_col: str, jobs_col: str) -> None:
        self.store = store
        self.approvals_col = approvals_col
        self.registry = CommandRegistry()
        self.queue = FirestoreLeaseQueue(store, collection=jobs_col)
        self.hub = EventHub()
        self._queues: dict[str, asyncio.Queue] = {}
        self._project_of: dict[str, str] = {}
        self.annotations: list[dict[str, object]] = []
        self.machine = ApprovalStateMachine(
            store,
            queue=self.queue,
            hub=self.hub,
            registry=self.registry,
            collection=approvals_col,
            annotator=self._annotate,
        )
        self.handler_calls = 0

    def _annotate(self, text: str, tags: list[str]) -> dict[str, object]:
        self.annotations.append({"text": text, "tags": tags})
        return {"id": f"ann-{len(self.annotations)}"}

    def hub_events(self, approval_id: str) -> list[dict[str, object]]:
        q = self._queues.get(self._project_of.get(approval_id, ""))
        out: list[dict[str, object]] = []
        if q is None:
            return out
        while True:
            try:
                out.append(q.get_nowait())
            except asyncio.QueueEmpty:
                return out

    def register_fast(self, name: str, behavior):
        def handler(ctx, approval):
            self.handler_calls += 1
            return behavior(ctx, approval)

        self.registry.command(name, lane="fast", idempotent=True)(handler)

    def register_fast_boom(self, name: str):
        def handler(ctx, approval):
            self.handler_calls += 1
            raise RuntimeError("handler exploded")

        self.registry.command(name, lane="fast", idempotent=True)(handler)

    def register_slow(self, name: str, project_id: str):
        def handler(ctx, approval):
            self.handler_calls += 1
            return Job(station="ingest", project_id=project_id, input_refs=[])

        self.registry.command(name, lane="slow")(handler)

    def put_approval(self, command: dict[str, object] | None) -> str:
        approval_id = f"appr-{uuid.uuid4().hex[:8]}"
        project_id = f"it-{uuid.uuid4().hex[:6]}"
        if project_id not in self._queues:
            self._queues[project_id] = self.hub.subscribe(project_id)
        self._project_of[approval_id] = project_id
        self.store.set_doc(
            self.approvals_col,
            approval_id,
            {
                "approval_id": approval_id,
                "project_id": project_id,
                "kind": "fix",
                "title": "t",
                "status": "proposed",
                "command": command,
                "created_at": utc_now_iso(),
            },
        )
        return approval_id


def test_registry_rejects_fast_command_without_idempotent(env):
    registry = CommandRegistry()

    with pytest.raises(ValueError, match="idempotent"):

        @registry.command("sneaky", lane="fast")
        def _sneaky(ctx, approval):  # pragma: no cover - must never register
            return {}


def test_fast_command_resolves_synchronously(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    seen: dict[str, bool] = {}
    h.register_fast(
        "flag_it", lambda ctx, a: seen.setdefault("ran", True) or {"ok": True}
    )
    approval_id = h.put_approval({"name": "flag_it", "args": {}})

    out = h.machine.dispatch(approval_id, "approve", approver="dev")

    assert out["status"] == "resolved"
    assert seen.get("ran") is True
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["status"] == "resolved"
    assert doc["decided_at"] and doc["result"]["ok"] is True
    assert len(h.annotations) == 1, "exactly one annotation per terminal transition"
    events = h.hub_events(approval_id)
    assert any(e["type"] == "approval.updated" for e in events)


def test_fast_command_failure_marks_failed_not_stuck(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    h.register_fast_boom("boom")
    approval_id = h.put_approval({"name": "boom", "args": {}})

    out = h.machine.dispatch(approval_id, "approve")

    assert out["status"] == "failed"
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None
    assert doc["result"]["ok"] is False
    assert "handler exploded" in str(doc["result"]["error"])


def test_slow_command_creates_deterministic_job(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    h.register_slow("make_job", project_id)
    approval_id = h.put_approval({"name": "make_job", "args": {}})

    out = h.machine.dispatch(approval_id, "approve")

    assert out["status"] == "acting"
    assert out["job_id"] == f"job-cmd-{approval_id}"
    job = h.queue.get(f"job-cmd-{approval_id}")
    assert job is not None, "real Job must exist on the lease queue"
    assert job.approval_id == approval_id
    assert job.status == "queued"
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["acting_since"]


def test_slow_job_submitted_only_after_approval_is_acting(env, approvals_col, jobs_col):
    """Peer-review fix: the job must never exist while the approval is still
    'proposed' — a crash between the two writes would orphan a running render
    with no approval watching it. Order: acting FIRST, then submit."""
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    status_at_submit: list[str] = []
    real_submit = h.queue.submit

    def spy_submit(job: Job) -> Any:
        doc = env.get_doc(approvals_col, str(job.approval_id))
        status_at_submit.append(str((doc or {}).get("status")))
        return real_submit(job)

    h.queue.submit = spy_submit  # type: ignore[method-assign]
    h.register_slow("make_job", project_id)
    approval_id = h.put_approval({"name": "make_job", "args": {}})

    h.machine.dispatch(approval_id, "approve")

    assert status_at_submit == ["acting"], (
        f"job submitted while approval was {status_at_submit}"
    )


def test_worker_terminal_write_resolves_slow_approval(env, approvals_col, jobs_col):
    """Tranche 2 wiring: the worker's terminal write triggers the completion
    hook, and the slow-lane approval resolves exactly-once from job truth."""
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    h.register_slow("make_job", project_id)
    approval_id = h.put_approval({"name": "make_job", "args": {}})
    h.machine.dispatch(approval_id, "approve")
    job_id = f"job-cmd-{approval_id}"

    job = h.queue.lease(WORKER_ID, ["ingest"])  # same worker _persist completes as
    assert job is not None and job.id == job_id
    job.status = "passed"  # pretend the station ran and passed
    _persist(job, h.queue, on_terminal=h.machine.on_job_terminal)

    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["status"] == "resolved"
    assert doc["result"]["ok"] is True and doc["result"]["job_id"] == job_id


def test_commandless_approval_resolves_as_noop(env, approvals_col, jobs_col):
    """Informational approvals carry no command: approving resolves the request
    without dispatching anything (contract held by the /decisions API)."""
    h = Harness(env, approvals_col, jobs_col)
    h.register_fast("flag_it", lambda ctx, a: {"ok": True})
    approval_id = h.put_approval(None)

    out = h.machine.dispatch(approval_id, "approve")

    assert out["status"] == "approved"
    assert out["result"] == {"ok": True, "noop": True}
    assert h.handler_calls == 0, "no handler may run for a commandless approval"
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["status"] == "approved"
    assert doc["decided_at"]


def test_double_dispatch_is_a_noop(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    h.register_fast("flag_it", lambda ctx, a: {"ok": True})
    approval_id = h.put_approval({"name": "flag_it", "args": {}})

    first = h.machine.dispatch(approval_id, "approve")
    calls_after_first = h.handler_calls
    with pytest.raises(ApprovalConflict):
        h.machine.dispatch(approval_id, "approve")

    assert h.handler_calls == calls_after_first, "handler must not re-run"
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["status"] == first["status"]


def test_reject_transitions_without_dispatching(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    h.register_fast("flag_it", lambda ctx, a: {"ok": True})
    approval_id = h.put_approval({"name": "flag_it", "args": {}})

    out = h.machine.dispatch(approval_id, "reject", approver="human-1")

    assert out["status"] == "rejected"
    assert h.handler_calls == 0
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["approver"] == "human-1"


def test_retry_rejected_for_non_terminal_job(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    target = Job(station="ingest", project_id="it-retry", input_refs=[])
    h.queue.submit(target)
    assert h.queue.claim(target.id, "w-1") is not None, "job is leased mid-flight"
    approval_id = h.put_approval({"name": "retry_job", "args": {"job_id": target.id}})

    out = h.machine.dispatch(approval_id, "approve")

    assert out["status"] == "failed"
    job = h.queue.get(target.id)
    assert job is not None and job.status == "leased", "mid-flight job untouched"


def test_retry_requeues_only_terminal_jobs(env, approvals_col, jobs_col):
    h = Harness(env, approvals_col, jobs_col)
    target = Job(station="ingest", project_id="it-retry", input_refs=[])
    h.queue.submit(target)
    assert h.queue.claim(target.id, "w-1") is not None
    assert h.queue.close(target.id, "w-1", "needs_human") is True

    approval_id = h.put_approval({"name": "retry_job", "args": {"job_id": target.id}})
    out = h.machine.dispatch(approval_id, "approve")

    assert out["status"] == "resolved"
    job = h.queue.get(target.id)
    assert job is not None and job.status == "queued"
    assert job.attempts == 0, "fresh lease budget after a deliberate retry"
    assert job.lease_owner is None


def test_pause_resume_never_loses_update(env, run_id):
    """Statistical lost-update regression: 25 rounds of racing opposite calls.
    Under read-then-write, a resume that reads before a pause commits can clobber
    it; under transactions the last-committed write always wins."""

    def round_ops(r: str, out: dict[str, str]):
        def do_pause():
            intake_control.pause_intake(env, "ingest", r)
            out["pause"] = utc_now_iso()

        def do_resume():
            intake_control.resume_intake(env, "ingest")
            out["resume"] = utc_now_iso()

        return do_pause, do_resume

    for round_no in range(25):
        intake_control.resume_intake(env, "ingest")
        out: dict[str, str] = {}
        do_pause, do_resume = round_ops(f"r{round_no}", out)

        t1 = threading.Thread(target=do_pause)
        t2 = threading.Thread(target=do_resume)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        last_op = max(out, key=lambda k: out[k])
        expected = last_op == "pause"
        assert intake_control.is_intake_paused(env, "ingest") is expected, (
            f"round {round_no}: last-committed op ({last_op}) lost — read-then-write clobber"
        )
    intake_control.resume_intake(env, "ingest")


def test_only_the_state_machine_writes_approval_status(env):
    """Single-writer tripwire (same spirit as the C-1.2 integrity check):
    no module outside approvals/machine.py may write approval status."""
    backend = Path(__file__).resolve().parents[1] / "backend"
    offenders: list[str] = []
    pattern = re.compile(
        r"set_doc\(\s*[A-Za-z_]*APPROVALS|set_doc\(\s*[\"']pc-approvals[\"']"
    )
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith("approvals/"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            offenders.append(rel)
    assert offenders == [], (
        f"approval status must only be written by approvals/machine.py, found: {offenders}"
    )


def test_completion_hook_resolves_watching_approval(env, approvals_col, jobs_col):
    """Slow-lane job turning terminal flips the linked approval — via the
    machine, exactly once."""
    h = Harness(env, approvals_col, jobs_col)
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    h.register_slow("make_job", project_id)
    approval_id = h.put_approval({"name": "make_job", "args": {}})
    out = h.machine.dispatch(approval_id, "approve")
    job_id = str(out["job_id"])
    job = h.queue.get(job_id)
    assert job is not None

    worker_id = "w-hook"
    assert h.queue.claim(job_id, worker_id) is not None
    h.queue.complete(job_id, worker_id, cost_micros=0)

    resolved = h.machine.on_job_terminal(h.queue.get(job_id))  # type: ignore[arg-type]
    assert resolved is True
    doc = env.get_doc(approvals_col, approval_id)
    assert doc is not None and doc["status"] == "resolved"

    # Reconciling again (crash-after-resolve) must be a no-op, not an error.
    assert h.machine.on_job_terminal(h.queue.get(job_id)) is False  # type: ignore[arg-type]
