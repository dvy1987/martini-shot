"""AC-S0.1 chaos test (plan A-3): N jobs submitted concurrently execute once
each DESPITE a worker crash mid-job — lease expiry reassignment verified.

Real subprocesses, real Firestore, real kill. Zero mocks (C-1.2).
"""

import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.jobs.models import Job
from backend.jobs.queue import FirestoreLeaseQueue

pytestmark = pytest.mark.integration

VISIBILITY_S = 4
IDLE_EXIT_S = 30


@pytest.fixture()
def env() -> object:
    settings = get_settings()
    assert settings.gcp_project_id, "real-service law C-6.2: GCP project required"
    return settings


def _spawn(mode: str, collection: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).parent / "chaos_worker.py"),
            "--collection",
            collection,
            "--stations",
            "ingest",
            "--mode",
            mode,
            "--visibility",
            str(VISIBILITY_S),
            "--idle-exit",
            str(IDLE_EXIT_S),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_status(
    queue: FirestoreLeaseQueue, job_id: str, wanted: str, timeout_s: float
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = queue.get(job_id)
        if job is not None and job.status == wanted:
            return
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} never reached {wanted}")


def _wait_any_leased(
    queue: FirestoreLeaseQueue, job_ids: list[str], timeout_s: float
) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for job_id in job_ids:
            job = queue.get(job_id)
            if job is not None and job.status == "leased":
                return job_id
        time.sleep(0.2)
    raise AssertionError("no job was ever leased by the killer worker")


def test_ac_s0_1_crash_then_exactly_once(env: object) -> None:
    settings = get_settings()
    collection = f"it-jobs-{uuid.uuid4().hex[:10]}"
    queue = FirestoreLeaseQueue(
        get_firestore(settings),
        collection=collection,
        visibility_timeout_s=VISIBILITY_S,
    )
    jobs = [
        Job(station="ingest", project_id="it-chaos", input_refs=[]) for _ in range(3)
    ]
    for job in jobs:
        queue.submit(job)

    # 1) worker crashes mid-job on its first lease. The victim is whichever
    # job the queue hands over first — created_at is millisecond-precision, so
    # three submits in a tight loop can tie and Firestore ordering is then
    # undefined. 60s: under full-suite load the cold subprocess + first lease
    # can exceed 20s. The exactly-once assertion below is unaffected.
    killer = _spawn("die", collection)
    victim_id = _wait_any_leased(queue, [job.id for job in jobs], timeout_s=60)
    killer.wait(timeout=15)

    # 2) two live workers drain everything (victim only after lease expiry)
    workers = [_spawn("complete", collection) for _ in range(2)]
    try:
        for job in jobs:
            _wait_status(queue, job.id, "passed", timeout_s=60)
    finally:
        for w in workers:
            w.wait(timeout=IDLE_EXIT_S + 10)

    # 3) exactly-once: each job executed exactly one time
    settings2 = get_settings()
    store = get_firestore(settings2)
    for job in jobs:
        executions = store.list_where("integration-test-executions", "job_id", job.id)
        assert len(executions) == 1, (
            f"exactly-once violated for {job.id}: {len(executions)} executions"
        )

    stored_victim = queue.get(victim_id)
    assert stored_victim is not None and stored_victim.attempts == 2, (
        "lease expiry reassignment not recorded"
    )
    for job in jobs:
        if job.id == victim_id:
            continue
        stored_clean = queue.get(job.id)
        assert stored_clean is not None and stored_clean.attempts == 1, (
            f"clean job {job.id} has wrong attempt count"
        )
    # cleanup: delete the test collection docs and execution ledger entries
    for job in jobs:
        queue.forget(job.id)
        for doc in store.list_where("integration-test-executions", "job_id", job.id):
            store.delete_doc("integration-test-executions", doc["id"])
