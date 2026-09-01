"""G1 ingest station: register arrival and checksum the object (C-4.2)."""

from __future__ import annotations

from backend.core.gcs import GCSMedia
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.stations.ingest.checksum import sha256_hex

STATION = "ingest"


def run_ingest(job: Job, gcs: GCSMedia) -> Job:
    """Download the first input_ref from GCS and attach sha256. Real object."""
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("ingest requires a GCS object")
            key = job.input_refs[0]
            payload = gcs.download_bytes(key)
            job.checksum_sha256 = sha256_hex(payload)
            job.cost_micros = 0
            outcome = "pass"
            log.info(
                "ingest checksum done",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "checksum_sha256": job.checksum_sha256,
                    "bytes": len(payload),
                },
            )
            return job
        finally:
            record_job(
                STATION,
                duration_s=timed() - started,
                cost_micros=job.cost_micros,
                outcome=outcome,
            )
