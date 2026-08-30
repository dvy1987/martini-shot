"""A-1 RED tests: core/errors.py — C-5.3 error responses never leak internals."""

import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.core.errors import install_error_handlers

LEAKY = "DB password=hunter2 at C:/Users/reall/secrets.env"


def build_client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(LEAKY)

    @app.get("/not-found")
    def not_found() -> None:
        raise HTTPException(status_code=404, detail="job not found")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_returns_sanitized_envelope() -> None:
    r = build_client().get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "internal_error"


def test_no_stack_trace_or_env_details_in_body() -> None:
    blob = json.dumps(build_client().get("/boom").json())
    for forbidden in ("hunter2", "Traceback", "RuntimeError", "reall", "secrets"):
        assert forbidden not in blob, f"leaked: {forbidden}"


def test_http_exception_uses_error_envelope() -> None:
    r = build_client().get("/not-found")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "job not found"
