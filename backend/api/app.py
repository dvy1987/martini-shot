"""FastAPI app factory (plan A-1). Run locally:

    uvicorn backend.api.app:create_app --factory

Auth (C-5.2, spec §7.2): every route requires the `X-API-Key` header except
`/api/v1/health`. SSE (`.../events`) also accepts `?api_key=` because the
browser EventSource API cannot set headers. An unset configured key fails
closed (everything 401s).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from urllib.parse import parse_qs

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.api.events import EventHub
from backend.core.config import Settings, get_settings
from backend.core.errors import install_error_handlers
from backend.core.logging import install_access_log_redaction, setup_logging
from backend.core.otel import init_telemetry

API_VERSION = "0.1.0"
_OPEN_PATHS = {"/api/v1/health"}


def _provided_api_key(scope: Scope) -> str:
    raw_headers = dict(scope.get("headers") or {})
    header_key = raw_headers.get(b"x-api-key", b"").decode("latin-1")
    if header_key:
        return header_key
    path = scope.get("path") or ""
    if path.endswith("/events"):
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        values = query.get("api_key") or []
        return values[0] if values else ""
    return ""


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
        provided = _provided_api_key(scope)
        if not self.api_key or provided != self.api_key:
            denied = JSONResponse(
                status_code=401, content={"error": {"code": "unauthorized"}}
            )
            await denied(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_app(
    settings: Settings | None = None,
    telemetry: bool = True,
    worker: bool = True,
) -> FastAPI:
    """Build the FastAPI app. `telemetry=False` is for tests that initialize
    OTel themselves; without a configured OTLP endpoint init is a no-op."""
    cfg = settings if settings is not None else get_settings()
    setup_logging(level=cfg.log_level)
    install_access_log_redaction()
    if telemetry:
        init_telemetry(cfg)

    hub = EventHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if getattr(app.state, "worker_enabled", False):
            task = asyncio.create_task(
                _run_worker(app, cfg, hub),
                name="pc-lease-worker",
            )
        yield
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Martini Shot API", version=API_VERSION, lifespan=lifespan)
    app.state.hub = hub
    app.state.worker_enabled = False

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

    if cfg.gcp_project_id and cfg.gcs_bucket:
        from backend.api.spine import install_spine_routes
        from backend.core.firestore import get_firestore
        from backend.core.gcs import get_gcs
        from backend.jobs.queue import FirestoreLeaseQueue

        store = get_firestore(cfg)
        gcs = get_gcs(cfg)
        queue = FirestoreLeaseQueue(store)
        app.state.queue = queue
        app.state.gcs = gcs
        app.state.store = store
        install_spine_routes(app, queue=queue, store=store, gcs=gcs, hub=hub)
        app.state.worker_enabled = worker

    return app


async def _run_worker(app: FastAPI, cfg: Settings, hub: EventHub) -> None:
    from backend.jobs.worker import worker_loop

    await worker_loop(app.state.queue, app.state.gcs, cfg, hub)
