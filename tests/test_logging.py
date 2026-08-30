"""A-1 RED tests: core/logging.py — structured JSON logs (C-4.2 field contract)."""

import io
import json
import logging
from datetime import datetime

from backend.core.logging import setup_logging


def _capture() -> tuple[io.StringIO, logging.Handler]:
    buf = io.StringIO()
    handler = setup_logging(level="DEBUG", stream=buf)
    return buf, handler


def test_json_line_has_utc_ts_level_message() -> None:
    buf, handler = _capture()
    try:
        logging.getLogger("pc.test").info("loudness done")
        data = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert data["message"] == "loudness done"
        assert data["level"] == "INFO"
        assert data["logger"] == "pc.test"
        ts = data["ts"]
        assert ts.endswith("Z")
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    finally:
        logging.getLogger().removeHandler(handler)


def test_job_context_fields_surface() -> None:
    """C-4.2: job_id, station, project_id must survive into the JSON line."""
    buf, handler = _capture()
    try:
        logging.getLogger("pc.test").info(
            "station finished",
            extra={"job_id": "j-1", "station": "loudness", "project_id": "p-1"},
        )
        data = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert data["job_id"] == "j-1"
        assert data["station"] == "loudness"
        assert data["project_id"] == "p-1"
    finally:
        logging.getLogger().removeHandler(handler)
