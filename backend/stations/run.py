"""Dispatch a leased job to the station named on the document."""

from __future__ import annotations

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.media import get_media
from backend.jobs.models import Job

STATION_NAMES = (
    "ingest",
    "loudness",
    "delivery",
    "spend",
    "pickups",
    "dub",
    "extend",
    "corrections",
    "relight",
    "coverage",
    "camera_language",
)


def execute(
    job: Job,
    *,
    gcs: GCSMedia,
    settings: Settings,
    store: FirestoreStore,
) -> Job:
    if job.station == "ingest":
        from backend.stations.ingest.run import run_ingest

        return run_ingest(job, gcs, get_media(settings), store=store, settings=settings)
    if job.station == "loudness":
        from backend.stations.loudness.run import run_loudness

        return run_loudness(
            job, gcs, get_media(settings), store=store, settings=settings
        )
    if job.station == "delivery":
        from backend.stations.delivery.run import run_delivery

        return run_delivery(job, gcs, store, get_media(settings), settings=settings)
    if job.station == "spend":
        from backend.stations.spend.run import run_spend

        return run_spend(job, store, settings)
    if job.station == "pickups":
        from backend.stations.pickups.run import run_pickups

        return run_pickups(job, gcs, get_media(settings))
    if job.station == "dub":
        from backend.stations.dubbing.run import run_dub

        return run_dub(job, gcs, store, settings)
    if job.station == "extend":
        from backend.stations.extend.run import run_extend

        return run_extend(job, gcs, store, settings)
    if job.station == "corrections":
        from backend.stations.corrections.run import run_correction

        return run_correction(job, gcs, store, settings)
    if job.station == "relight":
        from backend.stations.relight.run import run_relight

        return run_relight(job, gcs, store, settings)
    if job.station == "coverage":
        from backend.stations.coverage.run import run_coverage

        return run_coverage(job, gcs, store, settings)
    if job.station == "camera_language":
        from backend.stations.camera_language.run import run_camera_language

        return run_camera_language(job, gcs, store, settings)
    raise ValueError(f"unknown station {job.station!r}")
