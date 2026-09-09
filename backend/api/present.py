"""Map lease-queue Job documents onto the /api/v1 Job contract (spec §7)."""

from __future__ import annotations

from backend.jobs.models import Job

_STATUS = {
    "queued": "queued",
    "leased": "running",
    "passed": "pass",
    "failed": "fail",
    "quarantined": "quarantined",
    "throttled": "throttled",
    "needs_human": "needs_human",
}


def job_to_api(job: Job) -> dict[str, object]:
    error = None
    if job.error:
        code = "job_failed"
        if job.status == "quarantined":
            code = str(job.error)
        elif job.status == "throttled":
            code = "throttled"
        error = {"code": code, "message": job.error}
    return {
        "job_id": job.id,
        "station": job.station,
        "project_id": job.project_id,
        "input_refs": list(job.input_refs),
        "status": _STATUS.get(job.status, job.status),
        "attempts": job.attempts,
        "cost_micros": job.cost_micros,
        "error": error,
        "checksum_sha256": job.checksum_sha256,
        "result": dict(job.result) if job.result else {},
    }


def project_to_api(
    *,
    project_id: str,
    title: str,
    created_at: str,
    jobs: list[Job],
    include_jobs: bool = True,
) -> dict[str, object]:
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.station] = counts.get(job.station, 0) + 1
    statuses = {job.status for job in jobs}
    if "failed" in statuses:
        health = "failing"
    elif statuses & {"quarantined", "throttled", "needs_human"}:
        health = "degraded"
    else:
        health = "healthy"
    return {
        "project_id": project_id,
        "title": title,
        "created_at": created_at,
        "station_counts": counts,
        "health": health,
        "jobs": [job_to_api(job) for job in jobs] if include_jobs else [],
    }


def approval_to_api(doc: dict[str, object]) -> dict[str, object]:
    return {
        "approval_id": str(doc.get("approval_id") or ""),
        "project_id": str(doc.get("project_id") or ""),
        "job_id": doc.get("job_id"),
        "kind": str(doc.get("kind") or "fix"),
        "title": str(doc.get("title") or ""),
        "detail": doc.get("detail"),
        "before_url": doc.get("before_url"),
        "after_url": doc.get("after_url"),
        "cost_delta_micros": doc.get("cost_delta_micros"),
        "created_at": str(doc.get("created_at") or ""),
        "status": str(doc.get("status") or "proposed"),
        # Watchdog/decision outcome (peer-review fix): the UI renders WHY an
        # approval ended, including sweeper redrive and human-review flags.
        "result": doc.get("result"),
        "approver": doc.get("approver"),
        "decided_at": doc.get("decided_at"),
        "decision_reason": doc.get("decision_reason"),
        "sweep_retries": doc.get("sweep_retries"),
    }
