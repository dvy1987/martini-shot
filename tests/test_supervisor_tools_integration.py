"""Optional live propose-only PromQL/Loki read (no Grafana writes)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.supervisor.autonomy import Autonomy
from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config
from backend.supervisor.registry import ToolRegistry
from backend.supervisor.tools import register_grafana_tools

EVIDENCE = Path("docs/evidence/B-2b")


@pytest.mark.integration
def test_propose_only_live_query_does_not_write() -> None:
    settings = get_settings()
    if not settings.grafana_sa_token or not settings.mcp_grafana_bin:
        pytest.skip("Grafana OSS MCP not configured")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    registry = ToolRegistry()
    with GrafanaMcpConnector(build_server_config(settings)) as connector:
        register_grafana_tools(
            registry, connector=connector, autonomy=Autonomy.from_env({})
        )
        refused = registry.get("create_incident").fn(
            title="must-not-write", severity="pending"
        )
        assert refused["refused"] is True
        prom = registry.get("query_promql").fn(expr="pc_job_outcome_total")
        loki = registry.get("query_loki").fn(
            logql='{service_name="martini-shot-backend"} |= `ingest checksum done`',
            limit=5,
        )
    payload = {
        "job_id": "job-12f1bb8f8b98",
        "incident_refused": refused,
        "promql": prom,
        "loki": loki,
    }
    (EVIDENCE / "propose_only_query.json").write_text(
        json.dumps(payload, default=str, indent=2), encoding="utf-8"
    )
    (EVIDENCE / "README.md").write_text(
        "# B-2b — propose-only MCP tools\n\n"
        "Supervisor registry queried PromQL/Loki through MCP. "
        "`create_incident` was refused; no incident write.\n",
        encoding="utf-8",
    )
    assert "refused" in refused
