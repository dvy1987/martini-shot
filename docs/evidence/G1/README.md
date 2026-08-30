# G1 Evidence — OTLP pipeline live (pre-flight, 2026-08-30)

## Result: ingestion transport-verified, all three signals accepted

`scripts/otel_smoke.py` against the real Grafana Cloud OTLP gateway
(`otlp-gateway-prod-ap-south-1`, stack chipperm…):

| Signal | Endpoint | Outcome |
|---|---|---|
| traces | `…/otlp/v1/traces` | 2xx (no exporter errors) |
| metrics | `…/otlp/v1/metrics` | 2xx — after signal-path fix |
| logs | `…/otlp/v1/logs` | 2xx — after signal-path fix |

run_id of final green smoke: `369c3e15` (metric `pc_otel_smoke_total`,
span `otel.smoke`, log "otel smoke test", service `martini-shot-backend`).

## Two real bugs found and fixed on the way (TDD)
1. **Signal paths (404):** Python OTLP HTTP exporters POST to the endpoint URL
   verbatim; passing the gateway base `…/otlp` broke metrics/logs. Fixed in
   `core/otel.py::_signal_endpoints` (RED→GREEN in `tests/test_otel.py`).
2. **Auth scheme (401):** bare `glc_` Bearer pushed traces but 401'd
   metrics/logs. Grafana's OTLP gateway wants Basic auth with the OTLP
   instance id as username — the portal's `base64(<instanceId>:<token>)`
   template. `_auth_headers` now accepts that whole pasted line and computes
   the Basic blob (RED→GREEN in `tests/test_otel_auth.py`).

## Read-side caveat (expected)
The OTLP token is write-scoped: API metric query returned 401 (cannot read
with it). Visual/API confirmation lands with GRAFANA_SA_TOKEN (B-2
service-account token), which is also required for the MCP round-trip.

## Remaining for full G1
- 3 PromQL + 1 Loki line + trace ID captured from real station traffic
- annotation JSON round-trip (needs B-2)
