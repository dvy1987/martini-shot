"""Structured JSON logging (C-4.2): UTC ISO-8601 timestamps and the job context
fields (`job_id`, `station`, `project_id`) on every line. Server-side logs MAY
carry exception text — C-5.3 applies to HTTP responses, not internal logs.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import IO

_RESERVED: set[str] = set(
    logging.LogRecord("x", 0, "x", 0, "x", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}

_API_KEY_QUERY = re.compile(r"(api_key=)[^&\s]+", re.IGNORECASE)


def redact_api_key_query(text: str) -> str:
    """Strip EventSource query keys from access-log lines (C-5.1)."""
    return _API_KEY_QUERY.sub(r"\1REDACTED", text)


class ApiKeyAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_line = getattr(record, "request_line", None)
        if isinstance(request_line, str):
            record.request_line = redact_api_key_query(request_line)
        if isinstance(record.msg, str):
            record.msg = redact_api_key_query(record.msg)
        return True


def install_access_log_redaction() -> None:
    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, ApiKeyAccessLogFilter) for item in logger.filters):
        return
    logger.addFilter(ApiKeyAccessLogFilter())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_text"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(
    level: str = "INFO", stream: IO[str] | None = None
) -> logging.Handler:
    """Install the JSON handler on the root logger (idempotent); returns it so
    callers/tests can remove it."""
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level.upper())
    for old in list(root.handlers):
        if getattr(old, "_pc_json", False):
            root.removeHandler(old)
    handler._pc_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    return handler
