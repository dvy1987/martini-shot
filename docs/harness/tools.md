# Tool Surfaces (harness v0)

External services the product and its agents may call, plus repo-local tool scripts. Product runtime calls are governed by constitution C-1/C-2; this file documents surfaces for meta-agents.

## Product runtime (real calls only)
| Surface | Entry | Auth | Notes |
|---|---|---|---|
| Grafana Cloud MCP (hosted) | `https://mcp.grafana.com/mcp` | OAuth 2.1, one-time browser | 60+ tools; write-path tools (annotations/incidents) required by C-4.3 |
| Grafana MCP (OSS fallback) | `grafana/mcp-grafana` server | service-account token | `MCP_MODE=oss`; headless path, proven by gate G1 / ADR 0001 |
| Google AI | `google-adk`, `google-genai`, Vertex AI | ADC / Secret Manager | ONLY permitted AI vendor (C-2.1) |
| Google Cloud | Cloud Run, GCS, Firestore, Secret Manager, Cloud Build | ADC | state/media/secrets (C-6.2) |
| Grafana Cloud OTLP | telemetry endpoint | OTLP token | traces/metrics/logs from every service (C-4.1) |

## Repo-local tool scripts (safe to run)
| Script | Purpose | Exit |
|---|---|---|
| `python scripts/integrity_check.py` | C-1.2 no-mocks/stubs grep over product code | 1 on violation |
| `python backend/evals/check_thresholds.py` | C-3.4 numeric-threshold structure gate | 1 on invalid |
| `python docs/harness/drift_check.py` | harness manifest drift detection | 1 on drift |

## Agent-host tools (development time)
Droid native tools (Read/Grep/Execute/Task subagents), Cursor rules (`.cursor/rules/*.mdc`). Dev-time AI tooling is unrestricted by contest rules; runtime AI is not.
