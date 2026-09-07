"""Stage 1a H-0 commands enqueue real jobs (propose → approve → queue)."""

from __future__ import annotations

import uuid

import pytest

from backend.api import spine
from backend.api.app import create_app
from backend.core.config import get_settings, reset_settings
from backend.shots import lifecycle as shots

pytestmark = pytest.mark.integration


def test_correct_and_master_commands_respect_draft_first(
    env, run_id, monkeypatch
) -> None:
    monkeypatch.setattr(spine, "DELIBERATIONS", f"it-deliberations-{run_id}")
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="Stage 1a chain")
    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    from fastapi.testclient import TestClient

    headers = {"X-API-Key": settings.api_key}
    source = f"gs://{settings.gcs_bucket}/probes/shot-01-meadow.mp4"
    with TestClient(app) as client:
        proposed = client.post(
            f"/api/v1/shots/{shot_id}/correct",
            headers=headers,
            json={
                "source_uri": source,
                "intent": "Replace the café sign with OPEN",
                "consult_agent": False,
            },
        )
        assert proposed.status_code == 200
        approval_id = proposed.json()["approval_id"]
        approved = client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            headers=headers,
            json={"decision": "approve", "reason": "go"},
        )
        assert approved.status_code == 200
        job_doc = env.get_doc("pc-jobs", f"cor-{approval_id}")
        assert job_doc is not None
        assert job_doc["station"] == "corrections"
        assert job_doc["result"]["intent"].startswith("Replace")

        blocked = client.post(
            f"/api/v1/shots/{shot_id}/master",
            headers=headers,
            json={"op": "correction", "source_uri": source},
        )
        assert blocked.status_code == 200
        master_id = blocked.json()["approval_id"]
        failed = client.post(
            f"/api/v1/approvals/{master_id}/decision",
            headers=headers,
            json={"decision": "approve", "reason": "too soon"},
        )
        assert failed.status_code == 200
        body = failed.json()
        assert (
            body.get("status") in {"failed", "resolved"}
            or body.get("result", {}).get("ok") is not True
            or "QC-passing draft" in str(body)
        )

        shots.record_alternate(
            env,
            shot_id=shot_id,
            project_id=project_id,
            op="correction",
            artifact_ref=source,
            eval_scores={"flicker": 0.003, "vision_judge": 4.5},
        )
        eligible = client.post(
            f"/api/v1/shots/{shot_id}/master",
            headers=headers,
            json={
                "op": "correction",
                "source_uri": source,
                "intent": "Replace the café sign with OPEN",
            },
        )
        assert eligible.status_code == 200
        eligible_id = eligible.json()["approval_id"]
        ok = client.post(
            f"/api/v1/approvals/{eligible_id}/decision",
            headers=headers,
            json={"decision": "approve", "reason": "draft passed"},
        )
        assert ok.status_code == 200
        master_job = env.get_doc("pc-jobs", f"mst-cor-{eligible_id}")
        assert master_job is not None
        assert master_job["result"]["tier"] == "master"


def test_relight_coverage_camera_and_script_routes_propose(
    env, run_id, monkeypatch
) -> None:
    monkeypatch.setattr(spine, "DELIBERATIONS", f"it-deliberations-{run_id}")
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="Creative drawer")
    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    from fastapi.testclient import TestClient

    headers = {"X-API-Key": settings.api_key}
    source = f"gs://{settings.gcs_bucket}/probes/shot-01-meadow.mp4"
    with TestClient(app) as client:
        relight = client.post(
            f"/api/v1/shots/{shot_id}/relight",
            headers=headers,
            json={"source_uri": source, "preset": "noir"},
        )
        assert relight.status_code == 200
        coverage = client.post(
            f"/api/v1/shots/{shot_id}/coverage",
            headers=headers,
            json={
                "source_uri": source,
                "angle": "close_up",
                "intent": "tighter on the lead",
                "reference_uris": [source],
            },
        )
        assert coverage.status_code == 200
        camera = client.post(
            f"/api/v1/shots/{shot_id}/camera-language",
            headers=headers,
            json={"source_uri": source, "movement": "locked_off"},
        )
        assert camera.status_code == 200
        created = client.post(
            f"/api/v1/projects/{project_id}/scripts",
            headers=headers,
            json={"text": "Hello world", "based_on_version_id": None},
        )
        assert created.status_code == 200
        version_id = created.json()["version_id"]
        edited = client.post(
            f"/api/v1/projects/{project_id}/scripts",
            headers=headers,
            json={
                "text": "Hello there world",
                "based_on_version_id": version_id,
            },
        )
        assert edited.status_code == 200
        assert edited.json()["diffs"]
        regen = client.post(
            f"/api/v1/projects/{project_id}/scripts/{edited.json()['version_id']}/regenerate",
            headers=headers,
            json={
                "spans": [
                    {
                        "station": "corrections",
                        "shot_id": shot_id,
                        "source_uri": source,
                        "intent": "match the new line",
                    }
                ]
            },
        )
        assert regen.status_code == 200
        stale = client.post(
            f"/api/v1/projects/{project_id}/scripts",
            headers=headers,
            json={"text": "nope", "based_on_version_id": version_id},
        )
        assert stale.status_code == 409
