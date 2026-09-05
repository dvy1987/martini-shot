"""Settings round-trip (H-0b DoD): autonomy toggle + nightly envelope live in
Firestore (`pc-control/settings`) so the product's Settings UI changes them
with one flip, no redeploy. Contract is the FE's /api/v1/settings.

Real Firestore (C-6.2); the shared control doc is never mutated by tests —
per-run collections, like every other suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.core.config import get_settings, reset_settings
from backend.supervisor import budget_loop

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(monkeypatch, run_id):
    """App with the settings doc pointed at a per-run collection."""
    monkeypatch.setattr(budget_loop, "CONTROL", f"it-control-{run_id}")
    reset_settings()
    settings = get_settings()
    app = create_app(settings, telemetry=False, worker=False)
    headers = {"X-API-Key": settings.api_key}
    with TestClient(app) as test_client:
        yield test_client, headers


def test_get_settings_returns_the_default_toggle_and_envelope(client):
    test_client, headers = client

    response = test_client.get("/api/v1/settings", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["autonomy"] == "propose_only", "propose-only is the safe default"
    assert body["post_command_budget_micros"] == 20_000_000  # owner default


def test_patch_settings_round_trips_without_redeploy(client):
    test_client, headers = client

    patched = test_client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"autonomy": "act", "post_command_budget_micros": 5_000_000},
    )
    assert patched.status_code == 200
    assert patched.json() == {
        "autonomy": "act",
        "post_command_budget_micros": 5_000_000,
    }

    # A GET (the next cycle's read) sees the new values — no redeploy.
    assert test_client.get("/api/v1/settings", headers=headers).json() == {
        "autonomy": "act",
        "post_command_budget_micros": 5_000_000,
    }

    # The budgeted loop reads the SAME doc — the envelope really moved.
    assert (
        budget_loop.load_envelope_micros(
            get_firestore_store(), collection=budget_loop.CONTROL
        )
        == 5_000_000
    )


def get_firestore_store():
    from backend.core.config import get_settings
    from backend.core.firestore import get_firestore

    return get_firestore(get_settings())


def test_patch_rejects_invalid_autonomy_and_nonpositive_budget(client):
    test_client, headers = client

    bad_mode = test_client.patch(
        "/api/v1/settings", headers=headers, json={"autonomy": "yolo"}
    )
    assert bad_mode.status_code == 422

    bad_budget = test_client.patch(
        "/api/v1/settings", headers=headers, json={"post_command_budget_micros": -1}
    )
    assert bad_budget.status_code == 422

    # Nothing was written.
    assert test_client.get("/api/v1/settings", headers=headers).json() == {
        "autonomy": "propose_only",
        "post_command_budget_micros": 20_000_000,
    }


def test_load_autonomy_mode_defaults_to_propose_only(monkeypatch, run_id):
    monkeypatch.setattr(budget_loop, "CONTROL", f"it-control-{run_id}")
    store = get_firestore_store()
    assert budget_loop.load_autonomy_mode(store) == "propose_only"
    store.set_doc(
        budget_loop.CONTROL,
        budget_loop.SETTINGS_DOC,
        {"autonomy": "act"},
    )
    assert budget_loop.load_autonomy_mode(store) == "act"
