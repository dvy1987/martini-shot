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
from typing import Any
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
        tasks: list[asyncio.Task] = []
        if getattr(app.state, "worker_enabled", False):
            tasks.append(
                asyncio.create_task(
                    _run_worker(app, cfg, hub),
                    name="pc-lease-worker",
                )
            )
            tasks.append(
                asyncio.create_task(
                    _run_sweeper(app),
                    name="pc-approval-sweeper",
                )
            )
        yield
        for task in tasks:
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
        from backend.api.spine import _grafana_annotator
        from backend.approvals.machine import ApprovalStateMachine

        machine = ApprovalStateMachine(
            store, queue=queue, hub=hub, annotator=_grafana_annotator(cfg)
        )
        app.state.queue = queue
        app.state.gcs = gcs
        app.state.store = store
        app.state.machine = machine
        install_spine_routes(
            app,
            queue=queue,
            store=store,
            gcs=gcs,
            hub=hub,
            settings=cfg,
            machine=machine,
        )
        app.state.worker_enabled = worker

    return app


async def _run_worker(app: FastAPI, cfg: Settings, hub: EventHub) -> None:
    from backend.jobs.worker import worker_loop
    from backend.supervisor.team import maybe_deliberate

    machine = getattr(app.state, "machine", None)
    store = getattr(app.state, "store", None)

    def on_terminal(job: Any) -> None:
        # H-0: approval bookkeeping first (never delayed by deliberation).
        if machine is not None:
            machine.on_job_terminal(job)
        # H-0b signal-fired deliberation: fire-and-forget, propose-only
        # unless the ACT gate receipt is present, idempotent per job,
        # never raises into the worker path (see supervisor/team.py).
        if store is not None and getattr(app.state, "worker_enabled", False):
            from backend.api.spine import _grafana_annotator

            maybe_deliberate(
                job,
                store=store,
                settings=cfg,
                machine=machine,
                annotator=_grafana_annotator(cfg),
            )

    await worker_loop(
        app.state.queue,
        app.state.gcs,
        cfg,
        hub,
        on_terminal=on_terminal,
    )


async def _run_sweeper(app: FastAPI) -> None:
    """Watchdog tick (H-0): every 10s, reconcile crashed actions, enforce the
    15-minute needs-human backstop and redrive crashed fast actions."""
    import asyncio as _asyncio

    from backend.approvals.sweeper import sweep_once

    while True:
        try:
            await _asyncio.to_thread(
                sweep_once, app.state.store, app.state.queue, app.state.machine
            )
        except Exception:
            import logging

            logging.getLogger("pc.approvals.sweeper").exception("sweeper tick failed")
        await _asyncio.sleep(10)
