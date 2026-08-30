"""Structured JSON logging (C-4.2): UTC ISO-8601 timestamps and the job context
fields (`job_id`, `station`, `project_id`) on every line. Server-side logs MAY
carry exception text — C-5.3 applies to HTTP responses, not internal logs.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import IO

_RESERVED: set[str] = set(
    logging.LogRecord("x", 0, "x", 0, "x", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


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
