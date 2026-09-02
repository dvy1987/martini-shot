"""Register Grafana MCP tools on the supervisor ToolRegistry (C-2.2, C-4.3).

Act-class tools (add_annotation, create_incident) check autonomy BEFORE any
MCP dispatch so propose-only cannot write Grafana.
"""

from __future__ import annotations

from typing import Any

from backend.supervisor.autonomy import Autonomy
from backend.supervisor.mcp import GrafanaMcpConnector
from backend.supervisor.registry import ToolRegistry


def register_grafana_tools(
    registry: ToolRegistry,
    *,
    connector: GrafanaMcpConnector,
    autonomy: Autonomy,
) -> None:
    @registry.tool(description="Query Prometheus via Grafana MCP")
    def query_promql(expr: str) -> dict[str, Any]:
        return connector.query_promql(expr)

    @registry.tool(description="Query Loki via Grafana MCP")
    def query_loki(logql: str, limit: int = 30) -> dict[str, Any]:
        return connector.query_loki(logql, limit=limit)

    @registry.tool(description="Search Grafana dashboards via MCP")
    def search_dashboards(query: str) -> dict[str, Any]:
        return connector.search_dashboards(query)

    @registry.tool(description="Search traces via Grafana MCP (TraceQL)")
    def search_traces(query: str) -> dict[str, Any]:
        return connector.search_traces(query)

    @registry.tool(
        description="Write a Grafana annotation citing job_id (act-class)",
        act=True,
    )
    def add_annotation(text: str, tags: list[str] | None = None) -> dict[str, Any]:
        allowed, reason = autonomy.check("add_annotation", registry)
        if not allowed:
            return {
                "refused": True,
                "reason": reason,
                "proposal": {
                    "tool": "add_annotation",
                    "text": text,
                    "tags": tags or [],
                },
            }
        return connector.add_annotation(text, tags=tags)

    @registry.tool(
        description="Open a Grafana incident (act-class)",
        act=True,
    )
    def create_incident(title: str, severity: str = "pending") -> dict[str, Any]:
        allowed, reason = autonomy.check("create_incident", registry)
        if not allowed:
            return {
                "refused": True,
                "reason": reason,
                "proposal": {
                    "tool": "create_incident",
                    "title": title,
                    "severity": severity,
                },
            }
        return connector.create_incident(title, severity)
