"""Standalone chaos-test worker (AC-S0.1, plan A-3). Run as a REAL subprocess:

    python tests/chaos_worker.py --collection it-jobs-abc --stations ingest \
        --mode die|complete --visibility 4 --idle-exit 25

die-mode: leases a job, then hard-crashes (os._exit) WITHOUT completing —
simulates a worker killed mid-job.
complete-mode: executes the job (records an execution in the real
`integration-test-executions` ledger collection) and completes it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.jobs.queue import FirestoreLeaseQueue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    parser.add_argument("--stations", required=True)
    parser.add_argument("--mode", choices=["die", "complete"], required=True)
    parser.add_argument("--visibility", type=int, default=4)
    parser.add_argument("--idle-exit", type=int, default=25)
    args = parser.parse_args()

    settings = get_settings()
    assert settings.gcp_project_id, "real-service law C-6.2: GCP project required"
    queue = FirestoreLeaseQueue(
        get_firestore(settings),
        collection=args.collection,
        visibility_timeout_s=args.visibility,
    )
    worker_id = f"w-{args.mode}-{uuid.uuid4().hex[:6]}"
    started = time.monotonic()

    while time.monotonic() - started < args.idle_exit:
        job = queue.lease(worker_id=worker_id, stations=args.stations.split(","))
        if job is None:
            time.sleep(0.4)
            continue
        if args.mode == "die":
            os._exit(1)  # crash mid-job: no complete, no heartbeat
        store = queue.store
        store.set_doc(
            "integration-test-executions",
            f"{job.id}-{uuid.uuid4().hex[:8]}",
            {
                "job_id": job.id,
                "worker": worker_id,
                "at": datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            },
        )
        queue.complete(job.id, worker_id=worker_id, cost_micros=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
