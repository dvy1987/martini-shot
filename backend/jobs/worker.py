"""Lease worker: ingest station + Grafana annotation (C-6.3)."""

from __future__ import annotations

import asyncio
import logging

from backend.api.events import EventHub
from backend.api.present import job_to_api
from backend.core.config import Settings
from backend.core.gcs import GCSMedia
from backend.jobs.models import Job
from backend.jobs.queue import FirestoreLeaseQueue
from backend.stations.ingest.run import STATION, run_ingest
from backend.supervisor.annotate import annotate_job

log = logging.getLogger("pc.worker")
WORKER_ID = "pc-worker-g1"


def process_one(
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
) -> Job | None:
    """Claim the oldest ingest job, checksum it, complete, annotate. None if idle."""
    job = queue.lease(WORKER_ID, [STATION])
    if job is None:
        return None
    return _finish_claimed(job, queue, gcs, settings)


def process_job_id(
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
    job_id: str,
) -> Job | None:
    job = queue.claim(job_id, WORKER_ID)
    if job is None:
        return None
    return _finish_claimed(job, queue, gcs, settings)


def _finish_claimed(
    job: Job,
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
) -> Job:
    try:
        job = run_ingest(job, gcs)
        queue.complete(
            job.id,
            WORKER_ID,
            job.cost_micros,
            extra={"checksum_sha256": job.checksum_sha256},
        )
        job.status = "passed"
        try:
            annotate_job(settings, job, "pass")
            log.info(
                "g1 annotation written",
                extra={
                    "job_id": job.id,
                    "station": job.station,
                    "project_id": job.project_id,
                },
            )
        except Exception:
            log.exception(
                "grafana annotation failed",
                extra={
                    "job_id": job.id,
                    "station": job.station,
                    "project_id": job.project_id,
                },
            )
        return job
    except Exception as exc:
        queue.fail(job.id, WORKER_ID, str(exc)[:200])
        job.status = "failed"
        job.error = str(exc)[:200]
        raise


async def worker_loop(
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
    hub: EventHub,
) -> None:
    """Poll the lease queue on the API event loop; never blocks HTTP >30s."""
    while True:
        job = await asyncio.to_thread(queue.lease, WORKER_ID, [STATION])
        if job is None:
            await asyncio.sleep(0.4)
            continue
        hub.publish(job.project_id, "job.updated", {"job": job_to_api(job)})
        try:
            job = await asyncio.to_thread(run_ingest, job, gcs)
            await asyncio.to_thread(
                queue.complete,
                job.id,
                WORKER_ID,
                job.cost_micros,
                {"checksum_sha256": job.checksum_sha256},
            )
            job.status = "passed"
            hub.publish(job.project_id, "job.updated", {"job": job_to_api(job)})
            try:
                await asyncio.to_thread(annotate_job, settings, job, "pass")
                hub.publish(
                    job.project_id,
                    "annotation.created",
                    {"annotation_id": "grafana", "job_id": job.id},
                )
            except Exception:
                log.exception(
                    "grafana annotation failed",
                    extra={
                        "job_id": job.id,
                        "station": job.station,
                        "project_id": job.project_id,
                    },
                )
        except Exception as exc:
            await asyncio.to_thread(queue.fail, job.id, WORKER_ID, str(exc)[:200])
            job.status = "failed"
            job.error = str(exc)[:200]
            hub.publish(job.project_id, "job.updated", {"job": job_to_api(job)})
            log.exception(
                "ingest job failed",
                extra={
                    "job_id": job.id,
                    "station": job.station,
                    "project_id": job.project_id,
                },
            )
