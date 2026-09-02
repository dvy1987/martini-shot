"""Grafana MCP connector (plan B-2, ADR-0001, C-2.2).

The supervisor reaches Grafana ONLY through the MCP protocol. Two
transports behind MCP_MODE (ADR-0001 auth duality):

- `oss`     : local `mcp-grafana` server binary over stdio, authenticated
              with the service-account token (headless; Cloud Run path).
- `hosted`  : Grafana Cloud MCP at https://mcp.grafana.com/mcp over
              Streamable HTTP, user-scoped OAuth 2.1 (one-time browser
              consent on the dev machine; token persistence lands with
              plan F-4).

Fail-closed: missing config raises at build time, never silently degrades
to raw HTTP (C-2.2). Token values never appear in any repr.

Surface: sync methods (ADK FunctionTool / registry friendly). The async
MCP session runs on a dedicated event-loop thread owned by the connector.
"""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Self

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from backend.core.config import Settings
from backend.jobs.models import utc_now_iso

HOSTED_MCP_URL = "https://mcp.grafana.com/mcp"

# Plan tool surface -> real MCP tool names (hosted naming first, OSS alias second)
_TOOL_PREFERENCES: dict[str, tuple[str, ...]] = {
    "search_dashboards": ("search_dashboards",),
    "query_promql": ("query_prometheus", "query_promql"),
    "query_loki": ("query_loki_logs", "query_loki"),
    "search_traces": ("search_traces", "tempo_traceql-search"),
    "get_annotations": ("get_annotations",),
    "add_annotation": ("create_annotation", "add_annotation"),
    "create_incident": ("create_incident",),
}


class ToolUnavailable(RuntimeError):
    """The connected MCP server exposes none of the known names for a plan tool."""


@dataclass(frozen=True)
class StdioSpec:
    """Stdio launch description; env redacted in str/repr (C-5.3)."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"StdioSpec(command={self.command!r}, env=<redacted>)"

    __repr__ = __str__


@dataclass(frozen=True)
class McpServerConfig:
    mode: str
    stdio: StdioSpec | None = None
    http_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def build_server_config(settings: Settings) -> McpServerConfig:
    mode = (settings.mcp_mode or "").strip().lower()
    if mode not in ("oss", "hosted"):
        raise ValueError(
            f"MCP_MODE must be 'oss' or 'hosted', got {settings.mcp_mode!r}"
        )
    if not settings.grafana_stack_url:
        raise ValueError("GRAFANA_STACK_URL is required for the Grafana MCP connector")

    if mode == "oss":
        if not settings.mcp_grafana_bin:
            raise ValueError(
                "MCP_GRAFANA_BIN must point at the local mcp-grafana binary "
                "(docs/adr/0001-mcp-auth.md OSS fallback)"
            )
        if not settings.grafana_sa_token:
            raise ValueError(
                "GRAFANA_SA_TOKEN is required for OSS MCP mode "
                "(service-account token, headless fallback)"
            )
        env = get_default_environment()
        env["GRAFANA_URL"] = settings.grafana_stack_url
        # v1.3.0 reads GRAFANA_SERVICE_ACCOUNT_TOKEN (server README, "Usage")
        env["GRAFANA_SERVICE_ACCOUNT_TOKEN"] = settings.grafana_sa_token
        return McpServerConfig(
            mode="oss",
            stdio=StdioSpec(command=settings.mcp_grafana_bin, env=env),
        )

    return McpServerConfig(
        mode="hosted",
        http_url=HOSTED_MCP_URL,
        headers={"X-Grafana-URL": settings.grafana_stack_url},
    )


class _OwnedLoop:
    """Dedicated event-loop thread; sync facade over async session work."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self.loop.run_forever, daemon=True, name="mcp-client-loop"
        )
        self._thread.start()

    def run(self, coro: Any, timeout: float = 120.0) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)
        self.loop.close()


def _datasources_from_listing(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Unwrap mcp-grafana v1.3.0 `{datasources, total, hasMore}` or a bare list."""
    content = raw.get("content") or []
    if not content:
        return []
    listing: Any = json.loads(content[0]["text"])
    if isinstance(listing, dict):
        listing = listing.get("datasources", listing.get("items", []))
    if not isinstance(listing, list):
        raise ToolUnavailable(
            f"list_datasources returned unexpected shape: {type(listing).__name__}"
        )
    return [ds for ds in listing if isinstance(ds, dict)]


def _result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and "content" in result:
        return result  # already normalized (DI/dispatch sessions)
    content = getattr(result, "content", None) or []
    return {
        "content": [
            {"type": getattr(c, "type", ""), "text": getattr(c, "text", "")}
            for c in content
        ],
        "isError": bool(getattr(result, "isError", False)),
    }


class GrafanaMcpConnector:
    """Sync facade over a live MCP session with the Grafana server.

    Use as a context manager: `with GrafanaMcpConnector(config) as gmc: ...`
    """

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._loop: _OwnedLoop | None = None
        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        self._tools: list[str] = []
        self._ds_uids: dict[str, str] = {}

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def connect(self) -> None:
        if self._session is not None:
            return
        self._loop = _OwnedLoop()
        try:
            self._stack, self._session, self._tools = self._loop.run(
                self._open_session()
            )
        except BaseException:
            self.close()
            raise

    def _uid_for(self, signal: str) -> str:
        """Datasource UID by signal type, discovered via list_datasources.
        Grafana Cloud convention: grafanacloud-{prom,logs,traces}; for loki
        variants prefer the '-logs' one (usage/alert-state also exist)."""
        if not self._ds_uids:
            raw = self.call_tool("_list_datasources", {})
            for ds in _datasources_from_listing(raw):
                dtype, uid = ds.get("type", ""), ds.get("uid", "")
                if dtype:
                    self._ds_uids.setdefault(dtype, uid)
                if dtype == "loki" and str(ds.get("name", "")).endswith("-logs"):
                    self._ds_uids["loki"] = uid
                if dtype == "tempo" and "traces" in str(ds.get("uid", "")).lower():
                    self._ds_uids["tempo"] = uid
        uid = self._ds_uids.get(signal)
        if not uid:
            raise ToolUnavailable(
                f"no datasource of type {signal!r} discovered; known: {self._ds_uids}"
            )
        return uid

    async def _open_session(
        self,
    ) -> tuple[AsyncExitStack, Any, list[str]]:
        stack = AsyncExitStack()
        try:
            if self.config.mode == "oss" and self.config.stdio is not None:
                params = StdioServerParameters(
                    command=self.config.stdio.command,
                    args=self.config.stdio.args,
                    env=self.config.stdio.env,
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            else:
                # SDK streamable_http_client takes headers via httpx client, not kwargs.
                client = create_mcp_http_client(headers=self.config.headers or None)
                await stack.enter_async_context(client)
                read, write, *_rest = await stack.enter_async_context(
                    streamable_http_client(self.config.http_url, http_client=client)
                )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            return stack, session, tools
        except BaseException:
            await stack.aclose()
            raise

    def close(self) -> None:
        stack, self._stack = self._stack, None
        self._session, self._tools, self._ds_uids = None, [], {}
        if self._loop is not None:
            if stack is not None:
                try:
                    self._loop.run(stack.aclose(), timeout=30)
                except Exception:
                    pass
            self._loop.stop()
            self._loop = None

    # -- plumbing ----------------------------------------------------------

    @classmethod
    def _for_session(cls, session: Any) -> Self:
        """Bind to an existing session-like object (dispatch tests, DI)."""
        connector = cls.__new__(cls)
        connector.config = McpServerConfig(mode="oss")
        connector._loop = None
        connector._stack = None
        connector._session = session
        connector._tools = list(getattr(session, "available", []))
        connector._ds_uids = {}
        return connector

    @property
    def available_tools(self) -> list[str]:
        return list(self._tools)

    def _resolve(self, plan_name: str) -> str:
        if plan_name == "_list_datasources":
            if "list_datasources" in self._tools:
                return "list_datasources"
            raise ToolUnavailable(
                "list_datasources unavailable; cannot resolve datasource UIDs"
            )
        for candidate in _TOOL_PREFERENCES.get(plan_name, ()):
            if candidate in self._tools:
                return candidate
        raise ToolUnavailable(
            f"plan tool {plan_name!r} unavailable on this MCP server "
            f"(no match for {list(_TOOL_PREFERENCES.get(plan_name, []))}); "
            f"available: {self._tools}"
        )

    def call_tool(self, plan_name: str, arguments: dict[str, Any]) -> dict:
        resolved = self._resolve(plan_name)
        result = self._session.call_tool(resolved, arguments)
        if asyncio.iscoroutine(result):
            if self._loop is not None:
                result = self._loop.run(result)
            else:  # session-bound without owned loop (DI/dispatch tests)
                result = asyncio.run(result)
        return _result_to_dict(result)

    # -- plan tool surface (thin wrappers) ---------------------------------
    # Argument shapes follow mcp-grafana v1.3.0 input schemas (probed live).

    def search_dashboards(self, query: str) -> dict:
        return self.call_tool("search_dashboards", {"query": query})

    def query_promql(self, query: str, **extra: Any) -> dict:
        args: dict[str, Any] = {
            "expr": query,
            "datasourceUid": self._uid_for("prometheus"),
            "endTime": utc_now_iso(),
            # mcp-grafana v1.3.0 defaults queryType to range, which then
            # requires stepSeconds. Instant is the supervisor's default.
            "queryType": "instant",
            **extra,
        }
        return self.call_tool("query_promql", args)

    def query_loki(self, query: str, limit: int | None = None, **extra: Any) -> dict:
        args: dict[str, Any] = {
            "logql": query,
            "datasourceUid": self._uid_for("loki"),
            **extra,
        }
        if limit is not None:
            args["limit"] = limit
        return self.call_tool("query_loki", args)

    def search_traces(self, query: str, **extra: Any) -> dict:
        return self.call_tool(
            "search_traces",
            {"query": query, "datasourceUid": self._uid_for("tempo"), **extra},
        )

    def get_annotations(self, tags: list[str] | None = None, **extra: Any) -> dict:
        args: dict[str, Any] = {**extra}
        if tags:
            args["tags"] = list(tags)
        return self.call_tool("get_annotations", args)

    def add_annotation(
        self, text: str, tags: list[str] | None = None, **extra: Any
    ) -> dict:
        return self.call_tool(
            "add_annotation", {"text": text, "tags": list(tags or []), **extra}
        )

    def create_incident(
        self, title: str, severity: str, room_prefix: str = "pc", **extra: Any
    ) -> dict:
        return self.call_tool(
            "create_incident",
            {
                "title": title,
                "severity": severity,
                "roomPrefix": room_prefix,
                **extra,
            },
        )
