"""Supervisor Grafana annotation after a real job (C-2.2, C-4.3)."""

from __future__ import annotations

from backend.core.config import Settings
from backend.jobs.models import Job
from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config


def annotate_job(settings: Settings, job: Job, verdict: str) -> dict:
    """Write an investigation annotation that names job_id (C-4.3)."""
    config = build_server_config(settings)
    checksum = job.checksum_sha256 or ""
    text = (
        f"G1 investigation job_id={job.id} project_id={job.project_id} "
        f"station={job.station} verdict={verdict} checksum={checksum}"
    )
    with GrafanaMcpConnector(config) as connector:
        return connector.add_annotation(
            text, tags=["martini-shot", "g1", job.station, f"job:{job.id}"]
        )
