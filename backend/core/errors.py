"""Error response envelope (C-5.3): clients get stable codes, never stack
traces, exception text, or environment details. Full detail goes to server logs.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def error_body(code: str, message: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {"error": {"code": code}}
    if message:
        body["error"] = {"code": code, "message": message}
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def on_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Deliberately no echo of `exc.errors()` — input values could leak.
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", "Request validation failed"),
        )

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "unhandled error",
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "Internal server error"),
        )
