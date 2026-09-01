# Current State

**Where:** 2026-09-01 — Track A complete (A-1..A-5 on `main`), B-1 ADK supervisor on `main`, **B-2 Grafana MCP live round-trip GREEN** (uncommitted until this session's commit). OTLP traces/metrics/logs already accepted by Grafana Cloud (G1 pre-flight, `docs/evidence/G1/`).
**Blocking:** remaining Gate G1 pack from real station traffic (trace ID + 3 PromQL + Loki line under `docs/evidence/G1/`; annotation JSON now also in `docs/evidence/B-2/`) → C-1 FE review delta.
**Worker lane (A6):** 0-for-3 → **read-only research only**; orchestrator builds everything.
**Gate:** B-2 unit 12/12 + live MCP integration 1/1; ruff/mypy clean on connector. Full `make check` not re-run this slice (other integration tests hit GCS/Firestore).
**Key files:** `backend/supervisor/mcp.py`, `tests/test_supervisor_mcp*.py`, `docs/evidence/B-2/`, `backend/core/config.py` (`MCP_GRAFANA_BIN`).
**Open:** hosted MCP OAuth persistence is F-4; sparse OTLP counters need range PromQL (or a fresh `scripts/otel_smoke.py`); pytest OTel loopback stderr noise; G0 fixtures are 10-s recuts.
