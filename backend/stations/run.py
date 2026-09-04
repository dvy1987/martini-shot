"""Dispatch a leased job to the station named on the document."""

from __future__ import annotations

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.media import get_media
from backend.jobs.models import Job

STATION_NAMES = ("ingest", "loudness", "delivery", "spend", "pickups", "extend")


def execute(
    job: Job,
    *,
    gcs: GCSMedia,
    settings: Settings,
    store: FirestoreStore,
) -> Job:
    if job.station == "ingest":
        from backend.stations.ingest.run import run_ingest

        return run_ingest(job, gcs, get_media(settings))
    if job.station == "loudness":
        from backend.stations.loudness.run import run_loudness

        return run_loudness(job, gcs, get_media(settings))
    if job.station == "delivery":
        from backend.stations.delivery.run import run_delivery

        return run_delivery(job, gcs, store, get_media(settings))
    if job.station == "spend":
        from backend.stations.spend.run import run_spend

        return run_spend(job, store, settings)
    if job.station == "pickups":
        from backend.stations.pickups.run import run_pickups

        return run_pickups(job, gcs, get_media(settings))
    if job.station == "extend":
        from backend.stations.extend.run import run_extend

        return run_extend(job, gcs, store, settings)
    raise ValueError(f"unknown station {job.station!r}")
