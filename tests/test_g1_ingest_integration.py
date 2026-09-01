"""G1 ingest: real GCS object + checksum + lease worker (arrival+checksum)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.core.config import get_settings, reset_settings
from backend.jobs.worker import process_job_id

G1_DIGEST = "e651652d7cc45083d37620a36aa0610ccf1ad840a968a53c79352b4d5a35915a"  # pragma: allowlist secret - test fixture digest, not a credential

pytestmark = pytest.mark.integration


def test_ingest_upload_then_worker_checksum() -> None:
    reset_settings()
    settings = get_settings()
    assert settings.gcp_project_id and settings.gcs_bucket and settings.api_key
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    payload = b"martini-shot-g1"
    project_id = f"g1-{uuid.uuid4().hex[:8]}"
    job_id = ""
    key = ""
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/projects/{project_id}/ingest",
                headers=headers,
                files={"file": ("turnover.bin", payload, "application/octet-stream")},
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
            assert processed.checksum_sha256 == G1_DIGEST

            fetched = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            assert fetched.status_code == 200
            assert fetched.json()["status"] == "pass"
            assert fetched.json()["checksum_sha256"] == processed.checksum_sha256
    finally:
        if job_id:
            app.state.queue.forget(job_id)
        if key:
            try:
                app.state.gcs.delete(key)
            except Exception:
                pass
        app.state.store.delete_doc("pc-projects", project_id)
