# B-2 Evidence — Grafana MCP connector (plan B-2)

Date: 2026-09-01 · RED observed (live round-trip) → GREEN.

## DoD verification — real MCP round-trip (C-2.2, C-4.3)
| Requirement | Proof |
|---|---|
| OSS stdio + SA token (ADR-0001) | `MCP_MODE=oss`, `mcp-grafana` v1.3.0; Grafana log `Starting Grafana MCP server using stdio transport`; 80 tools listed |
| PromQL of live telemetry | `roundtrip.json` `promql_response` contains `pc_otel_smoke_total` samples for `run_id=7c10c2ca` (range query `now-1h`, step 15s) |
| Annotation written + read back with `job_id` | created `{"Payload":{"id":1,"message":"Annotation added"}}`; readback contains `job_id=b2-9a3c13ed` |
| Zero mocks | Live Grafana Cloud tenant via MCP only; no raw Grafana HTTP in the connector |

Unit tests: `tests/test_supervisor_mcp.py` 12/12 (fail-closed config, tool-name mapping, v1.3.0 datasource envelope, instant default).

Live test: `tests/test_supervisor_mcp_integration.py` 1/1. Artifact: `roundtrip.json`.

## Fixes found on the live path (TDD)
1. **Datasource envelope:** mcp-grafana v1.3.0 returns `{datasources, total, hasMore}`, not a bare list. Iterating the dict raised `AttributeError`. RED: `test_datasource_uids_unwrap_v130_envelope`.
2. **Range vs instant:** OTLP counters are sparse. Instant PromQL (and even a 7-day range of a 2-day-old sample) returned `{data:[]}`. After a fresh `scripts/otel_smoke.py` emit, range `now-1h` returned samples. Connector default stays instant; the integration test uses range.

## Notes
- Token check (`GET /api/datasources`) was already HTTP 200 / 12 datasources — the earlier SyntaxError was PowerShell wrapping, not a bad `GRAFANA_SA_TOKEN`.
- Hosted OAuth persistence remains plan F-4; this slice proves the OSS headless path.
