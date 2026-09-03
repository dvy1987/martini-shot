"""B-2 leftover: Grafana MCP tools on the ADK registry (propose-only gate).

Dispatch doubles record Grafana calls; they do not fake Grafana answers.
Live queries live in tests/test_supervisor_tools_integration.py.
"""

import pytest

from backend.supervisor.autonomy import Autonomy
from backend.supervisor.mcp import GrafanaMcpConnector
from backend.supervisor.registry import ToolRegistry
from backend.supervisor.tools import register_grafana_tools
from tests.test_supervisor_mcp import RecordingSession

pytestmark_integration = pytest.mark.integration


def _wired(autonomy: Autonomy | None = None) -> tuple[ToolRegistry, RecordingSession]:
    session = RecordingSession(
        [
            "query_prometheus",
            "query_loki_logs",
            "search_dashboards",
            "tempo_traceql-search",
            "create_annotation",
            "create_incident",
            "list_datasources",
        ]
    )
    connector = GrafanaMcpConnector._for_session(session)
    registry = ToolRegistry()
    register_grafana_tools(
        registry,
        connector=connector,
        autonomy=autonomy or Autonomy.from_env({}),
    )
    return registry, session


def test_read_tools_are_registered_and_not_act_class() -> None:
    registry, _ = _wired()
    for name in (
        "query_promql",
        "query_loki",
        "search_dashboards",
        "search_traces",
    ):
        assert name in registry.names()
        assert registry.is_act_tool(name) is False


def test_annotation_and_incident_are_act_class() -> None:
    registry, _ = _wired()
    assert registry.is_act_tool("add_annotation") is True
    assert registry.is_act_tool("create_incident") is True


def test_propose_only_refuses_incident_without_grafana_write() -> None:
    registry, session = _wired(Autonomy.from_env({}))
    result = registry.get("create_incident").fn(title="runaway", severity="pending")
    assert result["refused"] is True
    assert "propose-only" in result["reason"].lower()
    assert session.calls == []


def test_propose_only_refuses_annotation_without_grafana_write() -> None:
    registry, session = _wired()
    result = registry.get("add_annotation").fn(text="job_id=job-x")
    assert result["refused"] is True
    assert session.calls == []


def test_act_mode_dispatches_incident() -> None:
    registry, session = _wired(Autonomy.from_env({"POST_COMMAND_AUTONOMY": "act"}))
    result = registry.get("create_incident").fn(title="runaway", severity="pending")
    assert result.get("refused") is not True
    names = [name for name, _ in session.calls]
    assert "create_incident" in names


def test_propose_only_allows_promql_dispatch() -> None:
    registry, session = _wired()
    registry.get("query_promql").fn(expr="pc_job_outcome_total")
    names = [name for name, _ in session.calls]
    assert "query_prometheus" in names


def test_propose_only_allows_remaining_read_tools() -> None:
    registry, session = _wired()
    registry.get("query_loki").fn(logql='{job="x"}', limit=3)
    registry.get("search_dashboards").fn(query="spend")
    registry.get("search_traces").fn(query="{ status=error }")
    names = [name for name, _ in session.calls]
    assert "query_loki_logs" in names
    assert "search_dashboards" in names
    assert "tempo_traceql-search" in names


def test_act_mode_dispatches_annotation() -> None:
    registry, session = _wired(Autonomy.from_env({"POST_COMMAND_AUTONOMY": "act"}))
    result = registry.get("add_annotation").fn(text="job_id=job-x")
    assert result.get("refused") is not True
    names = [name for name, _ in session.calls]
    assert "create_annotation" in names


def test_retry_job_tool_requeues_terminal_job() -> None:
    """Peer-review fix: the supervisor's retry tool is REAL — it requeues a
    terminal job through the lease queue (terminal-only, history kept)."""
    import uuid

    from backend.core.config import get_settings
    from backend.core.firestore import get_firestore
    from backend.jobs.models import Job
    from backend.jobs.queue import FirestoreLeaseQueue
    from backend.supervisor.agent import _make_tools

    settings = get_settings()
    assert settings.gcp_project_id, "real-service law C-6.2: GCP project required"
    store = get_firestore(settings)
    queue = FirestoreLeaseQueue(store, collection=f"it-jobs-{uuid.uuid4().hex[:10]}")
    job = Job(station="ingest", project_id="it-x", input_refs=[])
    queue.submit(job)
    assert queue.lease("w-1", ["ingest"]) is not None
    queue.fail(job.id, worker_id="w-1", error="boom")  # attempt 1 → auto-requeued
    assert queue.lease("w-2", ["ingest"]) is not None
    assert queue.fail(job.id, worker_id="w-2", error="boom") is True  # → terminal

    registry = _make_tools(store, queue=queue)
    out = registry.get("retry_job").fn(job_id=job.id)

    assert out.get("requeued") is True
    stored = queue.get(job.id)
    assert stored is not None and stored.status == "queued"
    assert queue.lease("w-3", ["ingest"]) is not None  # mid-flight now
    refused = registry.get("retry_job").fn(job_id=job.id)
    assert refused.get("error"), "mid-flight requeue must be refused"


def test_build_supervisor_registers_injected_grafana_tools() -> None:
    from backend.core.config import get_settings
    from backend.supervisor.agent import build_supervisor

    settings = get_settings()
    plain = build_supervisor(settings)
    _registry, session = _wired()
    wired = build_supervisor(
        settings, grafana=GrafanaMcpConnector._for_session(session)
    )
    assert len(wired.tools) > len(plain.tools)
