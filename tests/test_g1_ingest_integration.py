"""G1 ingest: real GCS object + checksum + D-1 probe/quarantine."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.core.config import get_settings, reset_settings
from backend.jobs.worker import process_job_id

SLATE = Path(__file__).resolve().parents[1] / "fixtures" / "g1" / "slate.mp4"

pytestmark = pytest.mark.integration


def test_ingest_upload_then_worker_checksum() -> None:
    reset_settings()
    settings = get_settings()
    assert settings.gcp_project_id and settings.gcs_bucket and settings.api_key
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    payload = SLATE.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    project_id = f"g1-{uuid.uuid4().hex[:8]}"
    job_id = ""
    key = ""
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/projects/{project_id}/ingest",
                headers=headers,
                files={"file": ("slate.mp4", payload, "video/mp4")},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            job_id = str(body["job_id"])
            assert body["status"] == "queued"
            assert body["station"] == "ingest"
            key = str(body["input_refs"][0])

            processed = process_job_id(app.state.queue, app.state.gcs, settings, job_id)
            assert processed is not None
            assert processed.id == job_id
            assert processed.checksum_sha256 == digest
            assert processed.status == "passed"

            fetched = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            assert fetched.status_code == 200
            assert fetched.json()["status"] == "pass"
            assert fetched.json()["checksum_sha256"] == processed.checksum_sha256
            assert client.get("/api/v1/projects", headers=headers).status_code == 200
            assert (
                client.get(
                    f"/api/v1/projects/{project_id}", headers=headers
                ).status_code
                == 200
            )
            assert (
                client.get(
                    "/api/v1/projects/no-such-project", headers=headers
                ).status_code
                == 404
            )
            assert client.get("/api/v1/approvals", headers=headers).status_code == 200
            assert (
                client.get(
                    f"/api/v1/projects/{project_id}/reports/morning?date=2099-01-01",
                    headers=headers,
                ).status_code
                == 404
            )
            empty = client.post(
                f"/api/v1/projects/{project_id}/ingest",
                headers=headers,
                files={"file": ("empty.mp4", b"", "video/mp4")},
            )
            assert empty.status_code == 400
            decide = client.post(
                "/api/v1/approvals/missing/decision",
                headers=headers,
                json={"decision": "approve"},
            )
            assert decide.status_code == 404
            assert (
                client.get("/api/v1/jobs/no-such-job", headers=headers).status_code
                == 404
            )
            bad_decision = client.post(
                "/api/v1/approvals/missing/decision",
                headers=headers,
                json={"decision": "maybe"},
            )
            assert bad_decision.status_code == 400
            approval_id = f"ap-cov-{uuid.uuid4().hex[:8]}"
            app.state.store.set_doc(
                "pc-approvals",
                approval_id,
                {
                    "approval_id": approval_id,
                    "project_id": project_id,
                    "kind": "spend",
                    "title": "coverage",
                    "status": "proposed",
                    "created_at": "2026-09-01T00:00:00Z",
                },
            )
            approved = client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                headers=headers,
                json={"decision": "approve", "reason": "coverage"},
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "approved"
            conflict = client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                headers=headers,
                json={"decision": "reject"},
            )
            assert conflict.status_code == 409
            report_key = f"{project_id}:2026-09-01"
            app.state.store.set_doc(
                "pc-morning-reports",
                report_key,
                {
                    "date": "2026-09-01",
                    "generated_at": "2026-09-01T00:00:00Z",
                    "verdicts": [],
                },
            )
            morning = client.get(
                f"/api/v1/projects/{project_id}/reports/morning?date=2026-09-01",
                headers=headers,
            )
            assert morning.status_code == 200
            assert morning.json()["date"] == "2026-09-01"
            app.state.store.delete_doc("pc-approvals", approval_id)
            app.state.store.delete_doc("pc-morning-reports", report_key)
    finally:
        if job_id:
            app.state.queue.forget(job_id)
        if key:
            try:
                app.state.gcs.delete(key)
            except Exception:
                pass
        app.state.store.delete_doc("pc-projects", project_id)


def test_bitflipped_slate_quarantines() -> None:
    reset_settings()
    settings = get_settings()
    assert settings.gcp_project_id and settings.gcs_bucket and settings.api_key
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    payload = bytearray(SLATE.read_bytes())
    payload[int(len(payload) * 0.8)] ^= 0xFF
    project_id = f"g1q-{uuid.uuid4().hex[:8]}"
    job_id = ""
    key = ""
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/projects/{project_id}/ingest",
                headers=headers,
                files={"file": ("slate.mp4", bytes(payload), "video/mp4")},
            )
            assert response.status_code == 200, response.text
            job_id = str(response.json()["job_id"])
            key = str(response.json()["input_refs"][0])
            processed = process_job_id(app.state.queue, app.state.gcs, settings, job_id)
            assert processed is not None
            assert processed.status == "quarantined"
            fetched = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            assert fetched.json()["status"] == "quarantined"
    finally:
        if job_id:
            app.state.queue.forget(job_id)
        if key:
            try:
                app.state.gcs.delete(key)
            except Exception:
                pass
        app.state.store.delete_doc("pc-projects", project_id)


def test_ingest_rejected_when_intake_paused() -> None:
    from backend.stations.spend.control import pause_intake

    reset_settings()
    settings = get_settings()
    assert settings.gcp_project_id and settings.gcs_bucket and settings.api_key
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    previous = app.state.store.get_doc("pc-control", "intake")
    pause_intake(app.state.store, "ingest", "coverage")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects/g1pause/ingest",
                headers=headers,
                files={"file": ("slate.mp4", SLATE.read_bytes(), "video/mp4")},
            )
            assert response.status_code == 429
    finally:
        if previous is None:
            app.state.store.delete_doc("pc-control", "intake")
        else:
            app.state.store.set_doc("pc-control", "intake", previous)
