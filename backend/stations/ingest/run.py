"""Ingest station: checksum, probe, quarantine, then watch the original (S1)."""

from __future__ import annotations

from typing import Any

from backend.core.gcs import GCSMedia
from backend.core.media import FFmpeg, get_media
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.stations.ingest.checksum import sha256_hex
from backend.stations.ingest.classify import classify_payload

STATION = "ingest"


def run_ingest(
    job: Job,
    gcs: GCSMedia,
    media: FFmpeg | None = None,
    store: Any | None = None,
    settings: Any | None = None,
) -> Job:
    """Checksum + probe first. Only a healthy clip is watched for words + scene."""
    started = timed()
    outcome = "fail"
    if media is None:
        from backend.core.config import get_settings

        media = get_media(get_settings())
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("ingest requires a GCS object")
            key = job.input_refs[0]
            payload = gcs.download_bytes(key)
            job.checksum_sha256 = sha256_hex(payload)
            job.cost_micros = 0
            verdict, reason, probe = classify_payload(payload, media)
            job.result = {
                **job.result,
                "probe": {
                    k: probe[k]
                    for k in (
                        "duration_s",
                        "fps",
                        "codec",
                        "has_audio",
                        "width",
                        "height",
                    )
                    if k in probe
                },
            }
            if verdict == "quarantined":
                job.status = "quarantined"
                job.error = reason
                outcome = "quarantined"
                log.info(
                    "ingest quarantined",
                    extra={
                        "job_id": job.id,
                        "station": STATION,
                        "project_id": job.project_id,
                        "reason": reason,
                        "checksum_sha256": job.checksum_sha256,
                    },
                )
                return job
            shot_id = str(job.result.get("shot_id") or "")
            if settings is not None and store is not None and shot_id:
                from backend.shots import lifecycle as shots
                from backend.supervisor.station_agents import ingest_understand as watch

                decision, cost = watch.decide_ingest_understand(
                    settings, payload, media
                )
                job.cost_micros = int(cost)
                understanding = watch.understanding_doc(decision)
                understanding["cost_micros"] = int(cost)
                shots.record_scene_understanding(
                    store,
                    shot_id,
                    spoken_words=str(understanding.get("spoken_words") or ""),
                    has_speech=bool(understanding.get("has_speech")),
                    scene=str(understanding.get("scene") or ""),
                    cost_micros=int(cost),
                )
                job.result["scene_understanding"] = understanding
            outcome = "pass"
            log.info(
                "ingest checksum done",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "checksum_sha256": job.checksum_sha256,
                    "bytes": len(payload),
                    "watched": bool(job.result.get("scene_understanding")),
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
