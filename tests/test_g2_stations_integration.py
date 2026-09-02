"""G2 station dispatch through the real queue (ingest already covered at G1)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.core.config import get_settings, reset_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs
from backend.jobs.models import Job
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id
from backend.stations.run import execute
from backend.stations.spend.run import run_spend
from backend.supervisor.mcp import GrafanaMcpConnector
from tests.test_supervisor_mcp import RecordingSession

SLATE = Path(__file__).resolve().parents[1] / "fixtures" / "g1" / "slate.mp4"
CAPTION = Path(__file__).resolve().parents[1] / "fixtures" / "captions" / "valid.srt"

pytestmark = pytest.mark.integration


def test_unknown_station_rejected_without_io() -> None:
    job = Job(station="telepathy", project_id="x", input_refs=[])
    with pytest.raises(ValueError, match="unknown station"):
        execute(job, gcs=None, settings=None, store=None)  # type: ignore[arg-type]


def test_loudness_delivery_pickups_spend_through_queue() -> None:
    reset_settings()
    settings = get_settings()
    assert settings.gcp_project_id and settings.gcs_bucket
    store = get_firestore(settings)
    gcs = get_gcs(settings)
    queue = FirestoreLeaseQueue(store)
    project_id = f"g2t-{uuid.uuid4().hex[:8]}"
    keys: list[str] = []
    ids: list[str] = []
    try:
        media_key = f"projects/{project_id}/media/slate.mp4"
        cap_key = f"projects/{project_id}/captions/valid.srt"
        gcs.upload_bytes(media_key, SLATE.read_bytes(), content_type="video/mp4")
        gcs.upload_bytes(cap_key, CAPTION.read_bytes(), content_type="text/plain")
        keys.extend([media_key, cap_key])

        loud = Job(station="loudness", project_id=project_id, input_refs=[media_key])
        queue.submit(loud)
        ids.append(loud.id)
        done = process_job_id(queue, gcs, settings, loud.id)
        assert done is not None
        assert "lufs" in (done.result or {})

        delivery = Job(
            station="delivery",
            project_id=project_id,
            input_refs=[media_key, cap_key],
            result={"destination": "streaming"},
        )
        queue.submit(delivery)
        ids.append(delivery.id)
        done = process_job_id(queue, gcs, settings, delivery.id)
        assert done is not None
        assert "delivery" in (done.result or {})

        pick = Job(station="pickups", project_id=project_id, input_refs=[media_key])
        queue.submit(pick)
        ids.append(pick.id)
        done = process_job_id(queue, gcs, settings, pick.id)
        assert done is not None
        assert "flicker" in (done.result or {})

        runaway = Job(
            station="pickups",
            project_id=project_id,
            input_refs=[media_key],
            attempts=40,
            status="passed",
        )
        store.set_doc("pc-jobs", runaway.id, runaway.to_dict())
        ids.append(runaway.id)
        spend = Job(station="spend", project_id=project_id, input_refs=[])
        session = RecordingSession(
            ["create_annotation", "create_incident", "list_datasources"]
        )
        connector = GrafanaMcpConnector._for_session(session)
        done = run_spend(spend, store, settings, grafana=connector)
        assert done.status == "throttled"
        intake = store.get_doc("pc-control", "intake") or {}
        assert "pickups" in (intake.get("paused_stations") or [])
    finally:
        for job_id in ids:
            try:
                queue.forget(job_id)
            except Exception:
                pass
        for key in keys:
            try:
                gcs.delete(key)
            except Exception:
                pass
        try:
            store.delete_doc("pc-control", "intake")
        except Exception:
            pass
