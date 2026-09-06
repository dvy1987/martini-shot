"""Settings round-trip (H-0b DoD): autonomy toggle + nightly envelope live in
Firestore (`pc-control/settings`) so the product's Settings UI changes them
with one flip, no redeploy. Contract is the FE's /api/v1/settings.

Real Firestore (C-6.2); the shared control doc is never mutated by tests —
per-run collections, like every other suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import google_auth
from backend.api.app import create_app
from backend.core.config import get_settings, reset_settings
from backend.supervisor import budget_loop

pytestmark = pytest.mark.integration

OWNER_TOKEN = "owner-token"


def accept_owner(token: str) -> dict:
    """Deterministic stand-in for the production verifier (dependency
    injection at the module boundary — production uses real Google ID-token
    verification). Same contract: claims dict, or raises."""
    if token == OWNER_TOKEN:
        return {"email": "owner@example.com", "email_verified": True}
    if token == "not-owner-token":
        raise google_auth.GoogleTokenNotOwner("other@example.com")
    raise google_auth.GoogleTokenError("bad token")


@pytest.fixture()
def client(monkeypatch, run_id):
    """App with the settings doc pointed at a per-run collection and the
    deterministic owner verifier injected (settings writes are owner-gated)."""
    monkeypatch.setattr(budget_loop, "CONTROL", f"it-control-{run_id}")
    reset_settings()
    settings = get_settings()
    app = create_app(
        settings, telemetry=False, worker=False, settings_token_verifier=accept_owner
    )
    headers = {
        "X-API-Key": settings.api_key,
        "X-Google-ID-Token": OWNER_TOKEN,
    }
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


# ---------------------------------------------------------------------------
# Review round 2, finding 4: settings WRITES are owner-gated by Google
# sign-in (C-5.2 spirit: the API key identifies the machine, the Google ID
# token identifies the OWNER). Reads stay API-key-only.
# ---------------------------------------------------------------------------


@pytest.fixture()
def gated_app(run_id, monkeypatch):
    """App with the settings doc on a per-run collection and the
    deterministic owner verifier injected (same one the `client` fixture
    uses; the no-sign-in case simply omits the header)."""
    monkeypatch.setattr(budget_loop, "CONTROL", f"it-control-{run_id}")
    reset_settings()
    app = create_app(
        get_settings(),
        telemetry=False,
        worker=False,
        settings_token_verifier=accept_owner,
    )
    headers = {"X-API-Key": get_settings().api_key}
    with TestClient(app) as test_client:
        yield test_client, headers


def test_patch_settings_without_google_sign_in_fails_closed(gated_app):
    test_client, headers = gated_app

    response = test_client.patch(
        "/api/v1/settings", headers=headers, json={"autonomy": "act"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

    # The flip did NOT happen.
    assert test_client.get("/api/v1/settings", headers=headers).json()["autonomy"] == (
        "propose_only"
    )


def test_patch_settings_with_owner_google_token_succeeds(gated_app):
    test_client, headers = gated_app

    response = test_client.patch(
        "/api/v1/settings",
        headers={**headers, "X-Google-ID-Token": "owner-token"},
        json={"autonomy": "act", "post_command_budget_micros": 5_000_000},
    )
    assert response.status_code == 200
    assert response.json()["autonomy"] == "act"

    # A GET sees it — the loop will read the same doc.
    assert test_client.get("/api/v1/settings", headers=headers).json()["autonomy"] == (
        "act"
    )


def test_patch_settings_with_signed_in_non_owner_is_forbidden(gated_app):
    test_client, headers = gated_app

    response = test_client.patch(
        "/api/v1/settings",
        headers={**headers, "X-Google-ID-Token": "not-owner-token"},
        json={"autonomy": "act"},
    )
    assert response.status_code == 403
    assert test_client.get("/api/v1/settings", headers=headers).json()["autonomy"] == (
        "propose_only"
    )


def test_patch_settings_with_garbage_token_is_unauthorized(gated_app):
    test_client, headers = gated_app

    response = test_client.patch(
        "/api/v1/settings",
        headers={**headers, "X-Google-ID-Token": "garbage"},
        json={"autonomy": "act"},
    )
    assert response.status_code == 401


def test_verify_owner_id_token_fails_closed_when_unconfigured():
    """No GOOGLE_CLIENT_ID / GOOGLE_OWNER_EMAIL configured → every token is
    refused. The gate degrades to locked, never to open."""
    import dataclasses

    from backend.api.google_auth import GoogleTokenError, verify_owner_id_token

    unconfigured = dataclasses.replace(
        get_settings(), google_client_id="", google_owner_email=""
    )
    with pytest.raises(GoogleTokenError):
        verify_owner_id_token("any-token", unconfigured)


def test_verify_owner_id_token_rejects_malformed_token():
    """A token that is not a valid Google ID token (real verifier; a
    syntactically-broken token fails before any network round-trip) is
    refused."""
    import dataclasses

    from backend.api.google_auth import GoogleTokenError, verify_owner_id_token

    configured = dataclasses.replace(
        get_settings(),
        google_client_id="test-client-id.apps.googleusercontent.com",
        google_owner_email="owner@example.com",
    )
    with pytest.raises(GoogleTokenError):
        verify_owner_id_token("not-a-jwt", configured)


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
