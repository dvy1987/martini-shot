"""Live Run Pulse round-trip through Grafana MCP (C-2.2)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config
from backend.supervisor.run_pulse import assemble_run_pulse, reset_run_pulse_cache
from tests.test_spend import _Store

pytestmark = pytest.mark.integration

EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "run-pulse"


def test_live_run_pulse_archives_mcp_snapshot() -> None:
    settings = get_settings()
    config = build_server_config(settings)
    reset_run_pulse_cache()
    store = _Store()
    with GrafanaMcpConnector(config) as grafana:
        pulse = assemble_run_pulse(
            store,  # type: ignore[arg-type]
            "proj-pulse-live",
            grafana=grafana,
            worklist={"status": "running", "items": []},
        )
        assert pulse["grafana"] in {"ok", "unavailable"}
        assert "factory" in pulse
        assert "wheel" in pulse
        tools = list(grafana.available_tools)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": config.mode,
        "tools_available": tools,
        "pulse": pulse,
    }
    (EVIDENCE / "roundtrip.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
