"""Worker persist/fail paths (no station I/O, no Grafana writes)."""

from __future__ import annotations

import asyncio

import pytest

from backend.api.events import EventHub
from backend.jobs.models import Job
from backend.jobs.worker import _persist, process_job_id, process_one, worker_loop


class _Queue:
    def __init__(self, job: Job | None = None) -> None:
        self.job = job
        self.store = object()
        self.calls: list[tuple[object, ...]] = []
        self.authoritative: Job | None = None  # what queue.get() returns

    def get(self, job_id: str) -> Job | None:
        return self.authoritative

    def lease(self, worker_id: str, stations: list[str]) -> Job | None:
        self.calls.append(("lease", worker_id, tuple(stations)))
        return self.job

    def claim(self, job_id: str, worker_id: str) -> Job | None:
        self.calls.append(("claim", job_id, worker_id))
        return self.job

    def quarantine(
        self,
        job_id: str,
        worker_id: str,
        reason: str,
        extra: dict | None = None,
    ) -> bool:
        self.calls.append(("quarantine", job_id, reason, extra))
        return True

    def close(
        self,
        job_id: str,
        worker_id: str,
        status: str,
        *,
        cost_micros: int = 0,
        error: str | None = None,
        extra: dict | None = None,
    ) -> bool:
        self.calls.append(("close", job_id, status, extra))
        return True

    def complete(
        self,
        job_id: str,
        worker_id: str,
        cost_micros: int,
        extra: dict | None = None,
    ) -> bool:
        self.calls.append(("complete", job_id, cost_micros, extra))
        return True

    def fail(self, job_id: str, worker_id: str, error: str) -> bool:
        self.calls.append(("fail", job_id, error))
        return True


def test_persist_quarantine_throttled_and_complete() -> None:
    quarantined = Job(station="ingest", project_id="p", input_refs=["k"])
    quarantined.status = "quarantined"
    quarantined.error = "corrupt_decode"
    quarantined.checksum_sha256 = "abc"
    q = _Queue()
    _persist(quarantined, q)  # type: ignore[arg-type]
    assert q.calls[0][0] == "quarantine"

    throttled = Job(station="spend", project_id="p", input_refs=[])
    throttled.status = "throttled"
    throttled.error = "spend_enforced"
    q = _Queue()
    _persist(throttled, q)  # type: ignore[arg-type]
    assert q.calls[0][0] == "close"
    assert q.calls[0][2] == "throttled"

    held = Job(station="pickups", project_id="p", input_refs=["k"])
    held.status = "needs_human"
    q = _Queue()
    _persist(held, q)  # type: ignore[arg-type]
    assert q.calls[0][0] == "close"
    assert q.calls[0][2] == "needs_human"

    passed = Job(station="loudness", project_id="p", input_refs=["k"])
    q = _Queue()
    _persist(passed, q)  # type: ignore[arg-type]
    assert q.calls[0][0] == "complete"
    assert passed.status == "passed"


def test_process_one_and_claim_return_none_when_empty() -> None:
    q = _Queue(None)
    assert process_one(q, None, None) is None  # type: ignore[arg-type]
    assert process_job_id(q, None, None, "job-x") is None  # type: ignore[arg-type]


def test_unknown_station_fails_the_lease() -> None:
    job = Job(station="telepathy", project_id="p", input_refs=[])
    q = _Queue(job)
    with pytest.raises(ValueError, match="unknown station"):
        process_job_id(q, None, None, job.id)  # type: ignore[arg-type]
    assert any(call[0] == "fail" for call in q.calls)


def test_worker_loop_idles_then_fails_unknown_station() -> None:
    job = Job(station="telepathy", project_id="p", input_refs=[])
    q = _Queue()
    leases = {"n": 0}

    def lease(_worker_id: str, _stations: list[str]) -> Job | None:
        leases["n"] += 1
        if leases["n"] == 1:
            return None
        return job

    q.lease = lease  # type: ignore[method-assign]

    async def run() -> None:
        hub = EventHub()
        task = asyncio.create_task(worker_loop(q, None, None, hub))  # type: ignore[arg-type]
        for _ in range(40):
            await asyncio.sleep(0.05)
            if any(call[0] == "fail" for call in q.calls):
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert any(call[0] == "fail" for call in q.calls)


# -- H-0 tranche 2: the completion hook (worker tells the approval machine) --


def test_persist_calls_completion_hook_after_terminal_write() -> None:
    seen: list[Job] = []
    passed = Job(station="loudness", project_id="p", input_refs=["k"])
    q = _Queue()
    _persist(passed, q, on_terminal=seen.append)  # type: ignore[arg-type]
    assert q.calls[0][0] == "complete", "terminal write must land FIRST"
    assert seen == [passed], "hook must see the job in its final state"


def test_hook_failure_never_breaks_the_terminal_write() -> None:
    def boom(_job: Job) -> None:
        raise RuntimeError("hook exploded")

    passed = Job(station="loudness", project_id="p", input_refs=["k"])
    q = _Queue()
    _persist(passed, q, on_terminal=boom)  # type: ignore[arg-type]
    assert q.calls[0][0] == "complete", "hook isolation: write still lands"


def test_failed_job_reaches_the_hook_via_fail_path() -> None:
    seen: list[Job] = []
    job = Job(station="telepathy", project_id="p", input_refs=[])
    q = _Queue(job)
    with pytest.raises(ValueError, match="unknown station"):
        process_job_id(q, None, None, job.id, on_terminal=seen.append)  # type: ignore[arg-type]
    assert any(call[0] == "fail" for call in q.calls)
    assert seen and seen[0].status == "failed"


def test_worker_loop_calls_completion_hook_on_fail() -> None:
    seen: list[Job] = []
    job = Job(station="telepathy", project_id="p", input_refs=[])
    q = _Queue()
    q.lease = lambda _worker_id, _stations: job  # type: ignore[method-assign]

    async def run() -> None:
        hub = EventHub()
        task = asyncio.create_task(
            worker_loop(q, None, None, hub, on_terminal=seen.append)  # type: ignore[arg-type]
        )
        for _ in range(40):
            await asyncio.sleep(0.05)
            if any(call[0] == "fail" for call in q.calls) and seen:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert any(call[0] == "fail" for call in q.calls)
    assert seen and seen[0].status == "failed"


# -- Peer-review fixes: the hook reports the QUEUE's truth, not local copies --


def test_requeued_job_never_reports_terminal_to_hook(monkeypatch) -> None:
    """queue.fail requeues when attempts remain: the hook must see the real
    state (queued), not the worker's stale local 'failed' copy."""
    import backend.jobs.worker as worker_mod

    seen: list[Job] = []
    job = Job(station="loudness", project_id="p", input_refs=["k"])
    q = _Queue(job)
    q.authoritative = Job(station="loudness", project_id="p", input_refs=["k"])
    q.authoritative.status = "queued"  # queue.fail requeued it

    def boom_execute(*args: object, **kwargs: object) -> Job:
        raise RuntimeError("station exploded")

    monkeypatch.setattr(worker_mod, "execute", boom_execute)
    with pytest.raises(RuntimeError):
        process_job_id(q, None, None, job.id, on_terminal=seen.append)  # type: ignore[arg-type]
    assert any(call[0] == "fail" for call in q.calls)
    assert seen == [], "a requeued job is NOT terminal — the hook must stay silent"


def test_hook_uses_authoritative_job_when_terminal_write_wins() -> None:
    seen: list[Job] = []
    job = Job(station="loudness", project_id="p", input_refs=["k"])
    q = _Queue(job)
    q.authoritative = Job(station="loudness", project_id="p", input_refs=["k"])
    q.authoritative.status = "passed"
    _persist(job, q, on_terminal=seen.append)  # type: ignore[arg-type]
    assert seen and seen[0].status == "passed"


def test_hook_silent_when_terminal_write_loses_the_lease() -> None:
    """A stale worker whose completion write was rejected must not resolve
    the approval from its stale copy."""
    seen: list[Job] = []
    job = Job(station="loudness", project_id="p", input_refs=["k"])
    q = _Queue(job)
    q.complete = lambda *a, **kw: False  # type: ignore[method-assign]
    q.authoritative = Job(station="loudness", project_id="p", input_refs=["k"])
    q.authoritative.status = "leased"  # another worker owns it now
    _persist(job, q, on_terminal=seen.append)  # type: ignore[arg-type]
    assert seen == [], "lost lease: no hook from stale state"
