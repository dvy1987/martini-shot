"""Studio redesign (2026-09-09): the directed-edit clarify endpoint and the
add-to-final-cut promote endpoint. The clarify endpoint's success path
(a real Gemini call) is exercised live, not here — see test_directed_edit.py
for the deterministic agent contract, and the corrections endpoint tests
for the precedent of not paying for a model call in the standard suite."""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.integration
def test_directed_edit_clarify_404s_for_an_unknown_shot(env, run_id) -> None:
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings

    del run_id
    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/shots/shot-does-not-exist/directed-edit/clarify",
            headers=headers,
            json={"stations": ["relight"], "chat_text": ""},
        )
        assert response.status_code == 404


@pytest.mark.integration
def test_directed_edit_clarify_refuses_unknown_station_and_movement(
    env, run_id
) -> None:
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings
    from backend.shots import lifecycle as shots

    del run_id
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="clarify test")
    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as client:
        bad_station = client.post(
            f"/api/v1/shots/{shot_id}/directed-edit/clarify",
            headers=headers,
            json={"stations": ["extend"], "chat_text": "make it longer"},
        )
        assert bad_station.status_code == 400

        bad_movement = client.post(
            f"/api/v1/shots/{shot_id}/directed-edit/clarify",
            headers=headers,
            json={"stations": [], "camera_movement": "drone_orbit", "chat_text": ""},
        )
        assert bad_movement.status_code == 400


@pytest.mark.integration
def test_directed_edit_clarify_refuses_when_nothing_is_selected(env, run_id) -> None:
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings
    from backend.shots import lifecycle as shots

    del run_id
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="clarify test")
    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/shots/{shot_id}/directed-edit/clarify",
            headers=headers,
            json={"stations": [], "camera_movement": None, "chat_text": "   "},
        )
        assert response.status_code == 400


@pytest.mark.integration
def test_promote_proposal_approve_makes_the_alternate_the_current_version(
    env, run_id, monkeypatch
) -> None:
    """Add-to-final-cut chain: propose -> approve -> current_alternate_id
    flips, and the previously-current alternate is retired (revertible)."""
    from fastapi.testclient import TestClient

    from backend.api import spine
    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings
    from backend.shots import lifecycle as shots

    monkeypatch.setattr(spine, "DELIBERATIONS", f"it-deliberations-{run_id}")
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="promote test")
    first_id = shots.record_alternate(
        env,
        shot_id=shot_id,
        project_id=project_id,
        op="relight",
        artifact_ref="gs://bucket/first.mp4",
        eval_scores={"flicker": 0.001},
    )
    shots.promote_to_continuity(env, shot_id, first_id)
    second_id = shots.record_alternate(
        env,
        shot_id=shot_id,
        project_id=project_id,
        op="corrections",
        artifact_ref="gs://bucket/second.mp4",
        eval_scores={"flicker": 0.002},
    )

    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as client:
        proposed = client.post(
            f"/api/v1/shots/{shot_id}/promote",
            headers=headers,
            json={"alternate_id": second_id, "reason": "operator liked it"},
        )
        assert proposed.status_code == 200
        approval_id = proposed.json()["approval_id"]

        approved = client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            headers=headers,
            json={"decision": "approve", "reason": "go"},
        )
        assert approved.status_code == 200

    shot_doc = shots.get_shot(env, shot_id)
    assert shot_doc is not None
    assert shot_doc["current_alternate_id"] == second_id
    alternates = {
        row["alternate_id"]: row for row in shots.list_alternates(env, shot_id)
    }
    assert alternates[second_id]["status"] == "continuity"
    assert alternates[first_id]["status"] == "retired"


@pytest.mark.integration
def test_promote_refuses_an_empty_alternate_id(env, run_id) -> None:
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    from backend.core.config import get_settings, reset_settings
    from backend.shots import lifecycle as shots

    del run_id
    project_id = f"it-{uuid.uuid4().hex[:6]}"
    shot_id = shots.ensure_shot(env, project_id=project_id, title="promote test")
    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/shots/{shot_id}/promote",
            headers=headers,
            json={"alternate_id": "  "},
        )
        assert response.status_code == 400
