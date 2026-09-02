"""Lease worker: station dispatch + Grafana annotation (C-6.3)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from backend.api.events import EventHub
from backend.api.present import job_to_api
from backend.core.config import Settings
from backend.core.gcs import GCSMedia
from backend.jobs.models import Job
from backend.jobs.queue import FirestoreLeaseQueue
from backend.stations.run import STATION_NAMES, execute
from backend.supervisor.annotate import annotate_job

log = logging.getLogger("pc.worker")
WORKER_ID = "pc-worker-g1"

# H-0 completion hook: after a job reaches a terminal state the worker informs
# the approval machine (projection, not truth — a hook failure can never alter
# the job's own outcome, pre-mortem clause "hook isolation").
OnTerminal = Callable[[Job], None]


def _notify_terminal(on_terminal: OnTerminal | None, job: Job) -> None:
    if on_terminal is None:
        return
    try:
        on_terminal(job)
    except Exception:
        log.exception(
            "approval completion hook failed",
            extra={
                "job_id": job.id,
                "station": job.station,
                "project_id": job.project_id,
            },
        )


def process_one(
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
    on_terminal: OnTerminal | None = None,
) -> Job | None:
    job = queue.lease(WORKER_ID, list(STATION_NAMES))
    if job is None:
        return None
    return _finish_claimed(job, queue, gcs, settings, on_terminal=on_terminal)


def process_job_id(
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
    job_id: str,
    on_terminal: OnTerminal | None = None,
) -> Job | None:
    job = queue.claim(job_id, WORKER_ID)
    if job is None:
        return None
    return _finish_claimed(job, queue, gcs, settings, on_terminal=on_terminal)


def _persist(
    job: Job,
    queue: FirestoreLeaseQueue,
    on_terminal: OnTerminal | None = None,
) -> None:
    extra: dict[str, Any] = {"result": job.result}
    if job.checksum_sha256:
        extra["checksum_sha256"] = job.checksum_sha256
    if job.status == "quarantined":
        queue.quarantine(job.id, WORKER_ID, job.error or "quarantined", extra=extra)
        _notify_terminal(on_terminal, job)
        return
    if job.status in {"throttled", "needs_human"}:
        queue.close(
            job.id,
            WORKER_ID,
            job.status,
            cost_micros=job.cost_micros,
            error=job.error,
            extra=extra,
        )
        _notify_terminal(on_terminal, job)
        return
    queue.complete(job.id, WORKER_ID, job.cost_micros, extra=extra)
    job.status = "passed"
    _notify_terminal(on_terminal, job)


def _finish_claimed(
    job: Job,
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
    on_terminal: OnTerminal | None = None,
) -> Job:
    try:
        job = execute(job, gcs=gcs, settings=settings, store=queue.store)
        _persist(job, queue, on_terminal=on_terminal)
        try:
            verdict = "pass" if job.status == "passed" else job.status
            annotate_job(settings, job, verdict)
            log.info(
                "annotation written",
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
        _notify_terminal(on_terminal, job)
        raise


async def worker_loop(
    queue: FirestoreLeaseQueue,
    gcs: GCSMedia,
    settings: Settings,
    hub: EventHub,
    on_terminal: Callable[[Job], None] | None = None,
) -> None:
    while True:
        job = await asyncio.to_thread(queue.lease, WORKER_ID, list(STATION_NAMES))
        if job is None:
            await asyncio.sleep(0.4)
            continue
        hub.publish(job.project_id, "job.updated", {"job": job_to_api(job)})
        try:
            job = await asyncio.to_thread(
                execute, job, gcs=gcs, settings=settings, store=queue.store
            )
            await asyncio.to_thread(_persist, job, queue, on_terminal)
            hub.publish(job.project_id, "job.updated", {"job": job_to_api(job)})
            try:
                verdict = "pass" if job.status == "passed" else job.status
                await asyncio.to_thread(annotate_job, settings, job, verdict)
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
            await asyncio.to_thread(_notify_terminal, on_terminal, job)
            log.exception(
                "station job failed",
                extra={
                    "job_id": job.id,
                    "station": job.station,
                    "project_id": job.project_id,
                },
            )
