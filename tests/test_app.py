"""A-1 RED tests: api/app.py — factory, health, API-key auth (C-5.2), CORS."""

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.core.config import Settings


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "api_key": "test-key-123",  # pragma: allowlist secret (dummy test key)
        "cors_allowed_origins": ["http://localhost:5173"],
        "service_name": "backend-test",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def client(**overrides: object) -> TestClient:
    return TestClient(create_app(settings=make_settings(**overrides), telemetry=False))


def test_health_is_open() -> None:
    r = client().get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_protected_route_rejects_missing_key() -> None:
    r = client().get("/api/v1/version")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_protected_route_rejects_wrong_key() -> None:
    r = client().get("/api/v1/version", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_protected_route_accepts_valid_key() -> None:
    r = client().get("/api/v1/version", headers={"X-API-Key": "test-key-123"})
    assert r.status_code == 200
    assert "version" in r.json()


def test_fail_closed_when_api_key_unset() -> None:
    """Empty configured key must deny everything (fail-closed), never open the API."""
    r = client(api_key="").get("/api/v1/version")
    assert r.status_code == 401


def test_cors_allows_listed_origin_only() -> None:
    c = client()
    ok = c.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = c.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.test",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert bad.headers.get("access-control-allow-origin") is None
