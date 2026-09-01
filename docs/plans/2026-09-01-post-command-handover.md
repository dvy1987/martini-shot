# Handover — Martini Shot (post-command) · 2026-09-01 (rev 2)

> **To the receiving agent.** This replaces rev 1 from earlier today. Since then the
> other agent's work landed in the working tree and has been gate-verified and
> committed by the orchestrator (see §1). The owner is non-technical: translate
> trade-offs to plain language, own the architecture calls yourself. The constitution
> (C-1..C-8) is binding; zero-mock law (C-1.*) is the product. RED before GREEN, always.
> Deadline Sep 8 — submit ≥24 h early.

## 0 · Read first, in this order

1. `AGENTS.md` (root) + `backend/AGENTS.md` + `frontend/AGENTS.md`
2. `docs/constitution.md` · `docs/design/DESIGN.md` (v3, binding design direction)
3. `docs/plans/2026-08-26-post-command-plan.md` + tasks file (task IDs are the shared language)
4. `docs/adr/0001-mcp-auth.md` · `docs/adr/0002-model-toolchain-pinning.md`
5. `docs/memory/agent-handoffs.md` (latest entries) → then `git status` + `git log`
6. Session start: `memory-startup`. End: memory capture.

## 1 · Verified state (2026-09-01, orchestrator)

### On `main` (pushed)
`d0d866c` A-1 · `715db8c` A-2 · `5f8456c` A-3 · `f8e4606` A-4 · `d538927` A-5 ·
`bedbe03`+`fc15867` B-1 · `553bfdd`+`e292948` OTLP auth + signal endpoints · `4aaa6d5` B-2 live round-trip.

### Committed this session (the other agent's uncommitted tree, gate-verified first)
- **Gate G1 RUN and PASSED** — real MP4 → ingest (arrival+checksum) → traces/metrics/logs in
  Grafana → annotation with job_id → SSE queued→running→pass. Evidence: `docs/evidence/G1/`
  (`gate.json`, `sse.ndjson`, README). Job `job-12f1bb8f8b98`; trace `1558b20e2f5b0e99fd29d2dd40627bfd`;
  3 PromQL + Loki line + annotation id 4.
- **D-1 core**: `backend/stations/ingest/` (checksum + run), `backend/jobs/worker.py` (lease loop,
  process_one/process_job_id), `backend/jobs/telemetry.py`, `backend/supervisor/annotate.py`.
- **API spine**: `backend/api/spine.py` (projects/jobs/ingest upload/SSE), `present.py`, `events.py`;
  FE timeline wired to it.
- **Replit UX Steps 3–6** (Screening Room, dailies, slates, ⌘K palette, Lens): FE libs + components
  + tests. `docs/runbooks/replit-static-deploy.md`. `fixtures/g1/`.
- Orchestrator fixes on top: spine `Annotated[UploadFile, File()]` (ruff B008), ruff format,
  FE `src/test/setup.ts` localStorage shim (C-1.3 fixture; Node ≥22 needs `--localstorage-file`),
  chaos-test FIFO fix (see gotcha §5).

### Gates at handover
Backend pytest **95 passed** (final confirm run; chaos test now stable ×3), ruff/format/mypy clean,
`make integrity` clean. FE: tsc/eslint/vitest **63/63**/build all green.

## 2 · Environment facts

- GCP project `martini-shot`; Firestore `(default)`; GCS `martini-shot-media`. Real services in dev (C-6.2).
- Grafana stack `chippermosquito2692` (ap-south-1). OTLP token stays whole-line `base64(1810754:glc_…)` in `.env`
  (parsed by `backend/core/otel.py::_auth_headers`). SA token fresh 2026-09-01 (46 chars, 200 on `/api/datasources`).
- mcp-grafana v1.3.0 at `tools/mcp-grafana/mcp-grafana.exe` (gitignored; env var `GRAFANA_SERVICE_ACCOUNT_TOKEN` —
  NOT `GRAFANA_API_TOKEN`). 80 tools. `query_prometheus` needs `expr`+`datasourceUid`+`endTime`;
  instant PromQL on sparse counters returns `{data:[]}` — use range queries.
- Cloud datasource UIDs: `grafanacloud-prom` / `-logs` / `-traces`.
- Frontend deps: framer-motion present; **no `firebase` yet** → sign-in-to-approve (spec §7.2) NOT built.

## 3 · Remaining queue (reconciled against tasks file)

| # | Work | Notes |
|---|------|-------|
| 1 | **D-1 completion** — probe, corruption detect, audio-sync spot check, quarantine flow | ingest core exists; checksum/lease proven at G1 |
| 2 | **Sign-in-to-approve** (spec §7.2) — Firebase JS SDK + decision POST gate; backend `firebase-admin` verification + approver on annotation | owner-approved ruling; needs new FE dep (covered by ruling) |
| 3 | **B-3 AI Observability** (`backend/supervisor/` per C-4.4) | tokens/cost/latency per agent call |
| 4 | **F-4 hosted MCP OAuth** persistence | one-way door; design review first |
| 5 | **D-2..D-7 stations** (loudness, captions sub-check, delivery pack, spend control, pickups ×2) + **Gate G2** | one station per commit, C-8.1 README each |
| 6 | H-1..H-4 (investigation chains, morning report, approvals inbox, dashboards-as-code) | EDD for generative chains |
| 7 | J-0..J-6 (batch seed, chaos pass, Replit rehearsal J-3, README, video, submission) | submit ≥24 h early |

Spend: gen-AI ceiling $50–75; batches >$5 need owner `--yes` (C-7.2). Stage 1 only this sprint (Stage 1a behind G3).

## 4 · Definition of done (every module)

`make check` fully green → evidence in `docs/evidence/<task-id>/` → tasks-file row flipped with pointer →
commit + push (cite task ID + RED→GREEN) → memory capture if ≥20 files.

## 5 · Gotchas (learned the hard way)

- **Chaos test FIFO:** `created_at` is ms-precision — tight-loop submits tie and Firestore lease order is
  undefined. The test is order-agnostic now (`_wait_any_leased`); don't reintroduce jobs[0] assumptions.
- **OTLP counters are sparse** — instant PromQL returns empty; range query or fresh `scripts/otel_smoke.py`.
- Pre-commit ruff-format may reformat mid-commit → re-add + re-commit once; twice → STOP and read the diff.
- Long commands (full suite ≈4 min) → background + poll the log.
- FE tests: localStorage shim lives in `src/test/setup.ts`; vitest needs it under Node ≥22.
- Real-network blips happen → rerun a red test in isolation before debugging.
- `detect-secrets`: inline allowlist only on env-var NAMES/dummy fixtures, never real secrets.
- ASGI/Firestore: `@firestore.transactional` decorator (no `Transaction.run` in v2.29);
  per-run collections `it-jobs-<uuid>` for isolation.
- Model IDs live ONLY in `backend/core/models.py`; text reasoning = `gemini-3.7-flash`, thinking HIGH.

## 6 · Receiving-agent checklist

- [ ] `memory-startup`; read `agent-handoffs.md`; `git status` matches §1
- [ ] `make check` green; FE gates green
- [ ] Pick from §3 in order; announce the task ID before starting; one module per commit
- [ ] Owner touchpoint for anything in "Ask first" (backend/AGENTS.md boundaries)
