# Middleware & Lifecycle Hooks (harness v0)

## Session lifecycle
- Session start: `memory-startup` (bounded load) + latest handoff + git state check — see root AGENTS.md Session Lifecycle. Non-optional.
- Producer events (ADR/spec/plan written, major commit, skill edited, session end): memory sub-skill auto-fire per the memory skill's checkpoint list.

## Retry & resilience policies (product middleware)
| Concern | Policy |
|---|---|
| SSE stream (FE) | reconnect with exponential backoff + jitter; no polling fallback unless plan adds it |
| Grafana MCP OAuth (hosted) | 1h token, ~30d refresh; persist + refresh; on revoke treat as incident, never mock |
| Job leases (C-6.3) | expiry-based reassignment; handlers idempotent per `job_id`; chaos-tested (AC-S0.1) |
| Generative retries | capped (Pickups: 2 auto-retries then `needs_human`); every retry loop visible to Spend Control (S5b) |
| Eval batches | cost estimate printed before runs > $5; require `--yes` (C-7.2) |

## Git hooks (dev middleware)
- pre-commit: ruff lint+format, detect-secrets, integrity grep (`.pre-commit-config.yaml`).
- CI-lite gate: `make check` (lint, typecheck, tests, eval-check, integrity, harness-check).
