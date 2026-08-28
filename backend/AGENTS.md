# backend/AGENTS.md — scoped agent rules

See root `AGENTS.md` for project-wide context (constitution, boundaries, Session Lifecycle, Orchestration Map). This file adds backend-only rules.

## What this is
Python 3.12 (dev machines may run 3.13; the Cloud Run container pins 3.12), FastAPI, google-adk supervisor, Firestore lease queue, GCS media, OpenTelemetry everywhere. Layout: `api/` (FastAPI, /api/v1, SSE, auth) · `core/` (config, otel, gcp clients) · `jobs/` (queue, lease workers) · `supervisor/` (ADK + Grafana MCP) · `stations/<name>/` (16) · `evals/` (EDD suites).

## Key Commands
```
Test single:   python -m pytest tests/test_<module>.py -q
Test all:      make test
Lint:          make lint
Type check:    make typecheck      (mypy, config in mypy.ini)
Eval gate:     make eval-check     Integrity: make integrity   Full: make check
Run API (A-1): python -m uvicorn backend.api.main:app --reload   (path per scaffold)
```

## Non-Obvious Patterns
- Station contract: each `stations/<name>/` exposes a job handler conforming to the spine Job/JobResult model; every handler emits C-4.2 telemetry (one trace, >=3 metrics, structured logs with `job_id`/`station`/`project_id`) and logs a `cost_micros` estimate (C-7.1). Copy the root Code Style pattern.
- Idempotency (C-6.3): handlers tolerate re-execution per `job_id` (lease expiry reassigns). Chaos-test queue changes (AC-S0.1: real subprocess kill, exactly-once completion).
- Real services only (C-1.1, C-6.2): real Firestore/GCS (dev project) even in dev; real Gemini/TTS calls, billed — no emulators, no fakes. `fixtures/` media is INPUT data only.
- TDD: failing test first for deterministic modules (parsers, calculators, queue, API); >=90% line coverage on service-layer logic (C-3.2). EDD: dataset + metric + numeric threshold BEFORE generative features; eval JSONL to `docs/evidence/` (C-3.3/.4/.5).
- SSE + auth: event envelope schema lives in ONE module under `api/`; versioned `/api/v1` only; auth middleware exempts only `/health` (C-5.2); error responses never leak stack traces (C-5.3).
- Grafana wiring inventory (spec §6) is the naming checklist for metrics/annotations — do not invent new schemes.

## Boundaries (backend-scoped)

### Allowed without asking
- Code + tests under `backend/`, helper scripts under `scripts/` per plan tasks
- Station directories in the plan's stage order; eval datasets/thresholds

### Ask first
- Firestore schema/collection changes; new GCP services or APIs; dependency additions
- Queue semantics changes; telemetry metric contract changes

### Never
- Mock layers of any kind (C-1.2 — `make integrity` fails the build)
- Synchronous LLM calls in HTTP request paths >30 s (C-6.5)
- Hardcoded secrets — env/Secret Manager only (C-5.1)
