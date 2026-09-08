"""Supervisor Grafana annotation after a real job (C-2.2, C-4.3)."""

from __future__ import annotations

from backend.core.config import Settings
from backend.jobs.models import Job
from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config


def project_annotation_tag(project_id: str) -> str:
    """Grafana tag so get_annotations can slice one dump."""
    return f"project:{project_id}"


def annotation_tags(job: Job) -> list[str]:
    return [
        "martini-shot",
        "g1",
        job.station,
        f"job:{job.id}",
        project_annotation_tag(job.project_id),
    ]


def annotate_job(settings: Settings, job: Job, verdict: str) -> dict:
    """Write an investigation annotation that names job_id (C-4.3)."""
    config = build_server_config(settings)
    checksum = job.checksum_sha256 or ""
    text = (
        f"investigation job_id={job.id} project_id={job.project_id} "
        f"station={job.station} verdict={verdict} checksum={checksum}"
    )
    with GrafanaMcpConnector(config) as connector:
        return connector.add_annotation(text, tags=annotation_tags(job))
