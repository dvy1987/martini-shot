"""A-3 RED tests: jobs/queue.py — lease semantics on REAL Firestore (C-6.2, C-6.3).

Zero mocks: every test drives the real Firestore database with transactions.
AC-S0.1 (chaos: crash mid-job, exactly-once completion) lives in
test_lease_queue_chaos.py with real subprocesses.
"""

import uuid

import pytest

from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.jobs.models import Job, new_job_id
from backend.jobs.queue import FirestoreLeaseQueue

pytestmark = pytest.mark.integration


VISIBILITY_S = 4


@pytest.fixture()
def queue() -> FirestoreLeaseQueue:
    settings = get_settings()
    assert settings.gcp_project_id, "real-service law C-6.2: GCP project required"
    store = get_firestore(settings)
    collection = f"it-jobs-{uuid.uuid4().hex[:10]}"
    q = FirestoreLeaseQueue(
        store, collection=collection, visibility_timeout_s=VISIBILITY_S
    )
    submitted: list[str] = []
    original_submit = q.submit

    def tracking_submit(job: Job) -> None:
        submitted.append(job.id)
        original_submit(job)

    q.submit = tracking_submit  # type: ignore[method-assign]
    yield q
    for job_id in set(submitted):
        q.forget(job_id)


@pytest.fixture()
def project() -> str:
    return f"it-{uuid.uuid4().hex[:8]}"


def test_submit_is_idempotent_by_job_id(queue: FirestoreLeaseQueue) -> None:
    job = Job(station="ingest", project_id="it-x", input_refs=["gs://b/f.mp4"])
    queue.submit(job)
    queue.submit(job)  # second submit must not duplicate or error
    stored = queue.get(job.id)
    assert stored is not None and stored.id == job.id


def test_lease_claims_job_once_and_sets_visibility(
    queue: FirestoreLeaseQueue,
) -> None:
    job = Job(station="ingest", project_id="it-x", input_refs=[])
    queue.submit(job)
    leased = queue.lease(worker_id="w-1", stations=["ingest"])
    assert leased is not None and leased.id == job.id
    assert leased.status == "leased"
    assert leased.attempts == 1
    assert leased.lease_owner == "w-1"
    # second worker gets nothing while the lease is fresh
    assert queue.lease(worker_id="w-2", stations=["ingest"]) is None


def test_lease_respects_station_filter(queue: FirestoreLeaseQueue) -> None:
    queue.submit(Job(station="loudness", project_id="it-x", input_refs=[]))
    assert queue.lease(worker_id="w-1", stations=["ingest"]) is None
    leased = queue.lease(worker_id="w-1", stations=["loudness", "ingest"])
    assert leased is not None and leased.station == "loudness"


def test_complete_is_owner_guarded(queue: FirestoreLeaseQueue) -> None:
    job = Job(station="ingest", project_id="it-x", input_refs=[])
    queue.submit(job)
    queue.lease(worker_id="w-1", stations=["ingest"])
    # wrong owner may not complete
    assert queue.complete(job.id, worker_id="w-2", cost_micros=100) is False
    assert queue.complete(job.id, worker_id="w-1", cost_micros=100) is True
    stored = queue.get(job.id)
    assert stored is not None
    assert stored.status == "passed"
    assert stored.cost_micros == 100


def test_fail_requeues_then_goes_dead(queue: FirestoreLeaseQueue) -> None:
    job = Job(station="ingest", project_id="it-x", input_refs=[])
    queue.submit(job)
    queue.lease(worker_id="w-1", stations=["ingest"])
    queue.fail(job.id, worker_id="w-1", error="boom")
    stored = queue.get(job.id)
    assert stored is not None
    assert stored.status == "queued"  # attempt 1 → back to queue
    queue.lease(worker_id="w-2", stations=["ingest"])
    queue.fail(job.id, worker_id="w-2", error="boom")
    stored = queue.get(job.id)
    assert stored is not None
    assert stored.status == "failed"  # attempt 2 (max) → dead
    assert stored.error == "boom"


def test_heartbeat_extends_lease_only_for_owner(
    queue: FirestoreLeaseQueue,
) -> None:
    job = Job(station="ingest", project_id="it-x", input_refs=[])
    queue.submit(job)
    queue.lease(worker_id="w-1", stations=["ingest"])
    assert queue.heartbeat(job.id, worker_id="w-2") is False
    assert queue.heartbeat(job.id, worker_id="w-1") is True


def test_expired_lease_is_reassigned_to_next_worker(
    queue: FirestoreLeaseQueue,
) -> None:
    """Core AC-S0.1 mechanism (without the subprocess): a worker that stops
    heartbeating loses the lease; a new worker picks the job up."""
    job = Job(station="ingest", project_id="it-x", input_refs=[])
    queue.submit(job)
    queue.lease(worker_id="w-dies", stations=["ingest"])
    import time

    time.sleep(VISIBILITY_S + 1)
    leased = queue.lease(worker_id="w-2", stations=["ingest"])
    assert leased is not None and leased.id == job.id
    assert leased.lease_owner == "w-2"
    assert leased.attempts == 2
    # the dead worker may no longer complete it
    assert queue.complete(job.id, worker_id="w-dies", cost_micros=0) is False
    new_id = new_job_id()
    assert new_id.startswith("job-")


def test_quarantine_does_not_requeue(queue: FirestoreLeaseQueue) -> None:
    job = Job(station="ingest", project_id="it-x", input_refs=["k"])
    queue.submit(job)
    leased = queue.lease(worker_id="w-1", stations=["ingest"])
    assert leased is not None
    assert queue.quarantine(leased.id, "w-1", "corrupt_decode") is True
    stored = queue.get(job.id)
    assert stored is not None
    assert stored.status == "quarantined"
    assert stored.error == "corrupt_decode"
    assert queue.lease(worker_id="w-2", stations=["ingest"]) is None
