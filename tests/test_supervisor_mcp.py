"""B-2 RED tests: supervisor/mcp.py — Grafana MCP connector (plan B-2,
ADR-0001 auth duality, C-2.2 Grafana-only-via-MCP).

Pure-logic checks here; the REAL round-trip (annotation written + read
back through the live MCP server) lives in the integration module and
archives its response JSON to docs/evidence/B-2/.
"""

import json
from typing import ClassVar

import pytest
from mcp import StdioServerParameters

from backend.core.config import Settings
from backend.supervisor.mcp import (
    GrafanaMcpConnector,
    McpServerConfig,
    ToolUnavailable,
    build_server_config,
)


def settings_with(**overrides: str) -> Settings:
    base = {
        "mcp_mode": "oss",
        "mcp_grafana_bin": "tools/mcp-grafana/mcp-grafana.exe",
        "grafana_stack_url": "https://chipperm.grafana.net",
        "grafana_sa_token": "glsa_dummy",
    }
    base.update(overrides)
    return Settings(**base)


def test_connector_exposes_the_six_plan_tools() -> None:
    connector = GrafanaMcpConnector(
        McpServerConfig(
            mode="oss",
            stdio=StdioServerParameters(command="mcp-grafana", args=[]),
        )
    )
    for name in (
        "search_dashboards",
        "query_promql",
        "query_loki",
        "search_traces",
        "add_annotation",
        "create_incident",
    ):
        assert hasattr(connector, name), f"missing tool: {name}"


def test_oss_mode_builds_stdio_params_with_service_account_env() -> None:
    config = build_server_config(settings_with())
    assert config.mode == "oss"
    assert config.stdio is not None
    assert "mcp-grafana" in config.stdio.command
    assert config.stdio.env is not None
    assert config.stdio.env["GRAFANA_URL"] == "https://chipperm.grafana.net"
    assert config.stdio.env["GRAFANA_SERVICE_ACCOUNT_TOKEN"] == "glsa_dummy"


def test_hosted_mode_builds_streamable_http_target() -> None:
    config = build_server_config(settings_with(mcp_mode="hosted"))
    assert config.mode == "hosted"
    assert config.http_url == "https://mcp.grafana.com/mcp"
    assert config.headers is not None
    assert config.headers["X-Grafana-URL"] == "https://chipperm.grafana.net"


def test_oss_mode_fail_closed_without_sa_token() -> None:
    with pytest.raises(ValueError, match="GRAFANA_SA_TOKEN"):
        build_server_config(settings_with(grafana_sa_token=""))


def test_fail_closed_without_stack_url() -> None:
    with pytest.raises(ValueError, match="GRAFANA_STACK_URL"):
        build_server_config(settings_with(grafana_stack_url=""))


def test_invalid_mode_fails_closed() -> None:
    with pytest.raises(ValueError, match="MCP_MODE"):
        build_server_config(settings_with(mcp_mode="telepathy"))


class RecordingSession:
    """Transport double that records dispatches; the REAL round-trip test
    proves actual Grafana behavior — this only verifies dispatch logic."""

    DATASOURCES: ClassVar[list[dict[str, str]]] = [
        {"type": "prometheus", "uid": "grafanacloud-prom", "name": "g-prom"},
        {"type": "loki", "uid": "g-alert", "name": "g-alert-state-history"},
        {"type": "loki", "uid": "g-logs", "name": "g-logs"},
        {"type": "tempo", "uid": "grafanacloud-traces", "name": "g-traces"},
    ]

    def __init__(self, available: list[str]) -> None:
        self.available = available
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[str]:
        return list(self.available)

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        if name == "list_datasources":
            text = json.dumps(self.DATASOURCES)
        else:
            text = "ok"
        return {"content": [{"type": "text", "text": text}], "isError": False}


def test_datasource_uids_unwrap_v130_envelope() -> None:
    """mcp-grafana v1.3.0 returns {datasources, total, hasMore}, not a bare list."""

    class EnvelopeSession(RecordingSession):
        async def call_tool(self, name: str, arguments: dict) -> dict:
            self.calls.append((name, arguments))
            if name == "list_datasources":
                text = json.dumps(
                    {
                        "datasources": self.DATASOURCES,
                        "total": len(self.DATASOURCES),
                        "hasMore": False,
                    }
                )
            else:
                text = "ok"
            return {"content": [{"type": "text", "text": text}], "isError": False}

    session = EnvelopeSession(
        ["query_prometheus", "query_loki_logs", "list_datasources"]
    )
    connector = GrafanaMcpConnector._for_session(session)
    connector.query_promql("up")
    connector.query_loki('{job="x"}')
    dispatched = [c for c in session.calls if c[0] != "list_datasources"]
    assert dispatched[0][1]["datasourceUid"] == "grafanacloud-prom"
    assert dispatched[1][1]["datasourceUid"] == "g-logs"


def test_query_promql_maps_to_prometheus_tool() -> None:
    session = RecordingSession(["query_prometheus", "list_datasources"])
    connector = GrafanaMcpConnector._for_session(session)
    connector.query_promql("pc_otel_smoke_total")
    dispatched = [c for c in session.calls if c[0] != "list_datasources"]
    assert dispatched[0][0] == "query_prometheus"
    args = dispatched[0][1]
    assert args["expr"] == "pc_otel_smoke_total"
    assert args["datasourceUid"] == "grafanacloud-prom"
    assert args["endTime"].endswith("Z")
    assert args["queryType"] == "instant"


def test_query_loki_and_annotation_names_resolve() -> None:
    session = RecordingSession(
        ["query_loki_logs", "create_annotation", "list_datasources"]
    )
    connector = GrafanaMcpConnector._for_session(session)
    connector.query_loki('{job="martini-shot-backend"}')
    connector.add_annotation("handoff blocked job_id=x", tags=["pc", "test"])
    dispatched = [c for c in session.calls if c[0] != "list_datasources"]
    assert [c[0] for c in dispatched] == ["query_loki_logs", "create_annotation"]
    loki_args = dispatched[0][1]
    assert loki_args["logql"] == '{job="martini-shot-backend"}'
    assert loki_args["datasourceUid"] == "g-logs"  # '-logs' loki preferred
    args = dispatched[1][1]
    assert "job_id=x" in args["text"]


def test_search_traces_maps_to_tempo_traceql_search() -> None:
    session = RecordingSession(["tempo_traceql-search", "list_datasources"])
    connector = GrafanaMcpConnector._for_session(session)
    connector.search_traces('{ span.pc.job_id = "job-x" }')
    dispatched = [c for c in session.calls if c[0] != "list_datasources"]
    assert dispatched[0][0] == "tempo_traceql-search"
    assert dispatched[0][1]["query"] == '{ span.pc.job_id = "job-x" }'
    assert dispatched[0][1]["datasourceUid"] == "grafanacloud-traces"


def test_add_annotation_accepts_oss_alias_name() -> None:
    session = RecordingSession(["add_annotation", "list_datasources"])
    connector = GrafanaMcpConnector._for_session(session)
    connector.add_annotation("probe", tags=["pc"])
    assert session.calls[0][0] == "add_annotation"


def test_missing_tool_raises_unavailable_with_hint() -> None:
    session = RecordingSession(["search_dashboards", "list_datasources"])
    connector = GrafanaMcpConnector._for_session(session)
    try:
        connector.create_incident("drill", severity="critical")
        raised = False
    except ToolUnavailable as exc:
        raised = True
        assert "create_incident" in str(exc)
        assert "search_dashboards" in str(exc)  # hint lists what IS available
    assert raised


def test_token_never_leaks_into_connector_repr() -> None:
    config = build_server_config(settings_with())
    assert "glsa_dummy" not in repr(config)
    assert "glsa_dummy" not in str(config.stdio)
