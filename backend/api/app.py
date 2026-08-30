"""FastAPI app factory (plan A-1). Run locally:

    uvicorn backend.api.app:create_app --factory

Auth (C-5.2, spec §7.2): every route requires the `X-API-Key` header except
`/api/v1/health`. An unset configured key fails closed (everything 401s).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.core.config import Settings, get_settings
from backend.core.errors import install_error_handlers
from backend.core.logging import setup_logging
from backend.core.otel import init_telemetry

API_VERSION = "0.1.0"
_OPEN_PATHS = {"/api/v1/health"}


class APIKeyMiddleware:
    """Pure-ASGI key gate (streaming-safe for SSE). Denial is fail-closed by
    construction: an unset configured key denies everything."""

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in _OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        raw_headers = dict(scope.get("headers") or {})
        provided = raw_headers.get(b"x-api-key", b"").decode("latin-1")
        if not self.api_key or provided != self.api_key:
            denied = JSONResponse(
                status_code=401, content={"error": {"code": "unauthorized"}}
            )
            await denied(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None, telemetry: bool = True) -> FastAPI:
    """Build the FastAPI app. `telemetry=False` is for tests that initialize
    OTel themselves; without a configured OTLP endpoint init is a no-op."""
    cfg = settings if settings is not None else get_settings()
    setup_logging(level=cfg.log_level)
    if telemetry:
        init_telemetry(cfg)

    app = FastAPI(title="Martini Shot API", version=API_VERSION)

    app.add_middleware(APIKeyMiddleware, api_key=cfg.api_key)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "Authorization", "Content-Type"],
    )

    install_error_handlers(app)

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/version")
    async def version() -> dict[str, str]:
        return {"version": API_VERSION, "service": cfg.service_name}

    return app
