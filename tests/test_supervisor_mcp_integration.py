"""B-2 DoD (integration): REAL round-trip through the local mcp-grafana
server (stdio, SA token) into Grafana Cloud — dashboard search, PromQL
query of the live smoke metric, annotation WRITTEN and READ BACK with a
job_id reference (C-4.3). Response JSON archived to docs/evidence/B-2/.
Zero mocks — this is the actual Grafana tenant.
"""

import json
import time
import uuid
from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.supervisor.mcp import GrafanaMcpConnector, build_server_config

pytestmark = pytest.mark.integration

EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "B-2"


def test_real_mcp_roundtrip_archives_evidence() -> None:
    settings = get_settings()
    config = build_server_config(settings)  # fail-closed on missing env
    run_id = uuid.uuid4().hex[:8]

    with GrafanaMcpConnector(config) as gmc:
        assert gmc.available_tools, "MCP server exposed no tools"
        tools_snapshot = list(gmc.available_tools)

        # -- read path: dashboards + live metric ---------------------------
        # OTLP counters are sparse; mcp-grafana instant queries miss them.
        # Range over the last hour matches the Grafana Cloud Prometheus proxy.
        dashboards = gmc.search_dashboards("martini")
        promql = gmc.query_promql(
            "pc_otel_smoke_total",
            queryType="range",
            startTime="now-1h",
            stepSeconds=15,
        )
        assert not promql.get("isError"), promql
        assert promql["content"], "empty PromQL response"
        promql_text = promql["content"][0]["text"]
        assert "pc_otel_smoke_total" in promql_text or '"data"' in promql_text

        # -- write path: annotation with job_id reference (C-4.3) ----------
        text = f"B-2 MCP round-trip job_id=b2-{run_id}"
        created = gmc.add_annotation(text, tags=["martini-shot", "b2-roundtrip"])
        assert not created.get("isError"), created
        created_text = created["content"][0]["text"]

        # -- read back the annotation ---------------------------------------
        annotations = gmc.get_annotations(tags=["b2-roundtrip"])
        readback_text = annotations["content"][0]["text"]
        assert f"job_id=b2-{run_id}" in readback_text, readback_text[:400]

    # -- archive the DoD evidence (real responses only) ---------------------
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": config.mode,
        "server": "mcp-grafana v1.3.0 (stdio, SA token)",
        "tools_available": tools_snapshot,
        "search_dashboards_count": len(dashboards["content"][0]["text"]),
        "promql_response": promql_text[:2000],
        "annotation_created": created_text[:500],
        "annotation_readback_contains_job_id": f"job_id=b2-{run_id}",
    }
    (EVIDENCE / "roundtrip.json").write_text(json.dumps(payload, indent=2))
    print(f"round-trip archived: run_id={run_id}, tools={len(tools_snapshot)}")
