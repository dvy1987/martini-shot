# Project Constitution
Version: 1 | Date: 2026-08-26 | Status: Active

## C-1 Integrity / Realness (binding on all agents)
- C-1.1 The product MUST contain zero mocked, stubbed, canned, or simulated AI functionality. Every model call in a running code path hits a real permitted Google API. Rationale: deception = disqualification (owner Integrity Charter).
- C-1.2 `src/` MUST NOT contain `MagicMock`, `monkeypatch`, `Fake*` classes, or TODO-stub markers; CI greps enforce this (tests excluded). Rationale: mechanical enforcement of C-1.1.
- C-1.3 Synthetic media/fixtures are ALLOWED only as labeled INPUT data under `fixtures/` with a per-file README; faked FUNCTIONALITY is banned. Rationale: honest test data ≠ faked capability.
- C-1.4 Fault injection MUST be announced wherever shown (video narration, README). Rationale: transparency.
- C-1.5 The demo video MUST be recorded exclusively from the running product: real auth, real latency, no sped-up renders presented as live, no precomputed outputs. Rationale: buyer trusts what they can reproduce.
- C-1.6 Every public claim (README/video) MUST be reproducible by a stranger from the repo docs alone. Rationale: credibility.

## C-2 Hackathon Compliance
- C-2.1 All AI/agent capability MUST use Google AI services only (Gemini models via google-genai/google-adk/Vertex AI; Google Cloud TTS). Any other vendor's AI = build failure. Rationale: official rules §7.B.
- C-2.2 Grafana stack usage at runtime MUST route primarily through Grafana Cloud MCP (`https://mcp.grafana.com/mcp`) or OSS `grafana/mcp-grafana`; the supervisor agent MUST import and call MCP tools in code paths exercised by the demo. Rationale: track pass/fail requirement.
- C-2.3 Repo MUST be public with OSI license detectable at top before submission. Rationale: submission req.
- C-2.4 All source created fresh during contest window; no code copied from owner's prior repos (patterns/ideas OK, code lines NO). Rationale: "new project" rule.

## C-3 Testing & Verification
- C-3.1 Deterministic modules (parsers, calculators, state machines, job runner, API) MUST be built TDD: failing test written first (RED), then implementation (GREEN), then refactor. PRs without tests for new pure logic are rejected. Rationale: correctness spine.
- C-3.2 Deterministic service-layer logic MUST hold ≥90% line coverage; coverage report MUST run in CI-lite (`make test`). Rationale: regression protection.
- C-3.3 Generative capabilities (image edit, relight, dub generation, vision QC, dialogue listen-classify) MUST be built EDD: a versioned eval suite (dataset manifest + metric + threshold) MUST exist and PASS before a capability is declared done; prompts/models changes rerun evals. No eval, no merge. Rationale: reliability without faking.
- C-3.4 Eval thresholds MUST be numeric and recorded in `thresholds.yaml` (e.g., flicker score < X, LUFS tolerance ±0.5 dB, caption rule exact-match, sync offset ≤ 45 ms, vision-judge rubric ≥ 4/5 on n samples). Rationale: falsifiable quality bars.
- C-3.5 Each gate (G0–G5 in ideas/AO-STATION-MAP.md Amendments) requires recorded evidence (command output, screenshot, eval JSONL) saved under `docs/evidence/`. Rationale: audit trail.

## C-4 Observability (day 1, everywhere)
- C-4.1 Every service and worker MUST emit OpenTelemetry traces, metrics, and logs to Grafana Cloud OTLP endpoints from its first runnable commit. Rationale: Grafana-first mandate.
- C-4.2 Every job MUST produce: one trace (spans per stage), ≥3 metrics (duration, cost estimate, outcome counter), structured log lines with `job_id`, `station`, `project_id`. Rationale: supervisor needs uniform telemetry.
- C-4.3 Supervisor agent MUST act via Grafana MCP (query/investigate/annotate/incidents); every autonomous intervention MUST leave a Grafana annotation referencing `job_id`. Rationale: actions auditable in Grafana, not just app DB.
- C-4.4 The backend MUST self-instrument with Grafana Cloud AI Observability (agent traces, token usage/cost). Rationale: required meta-demo.
- C-4.5 Dashboards and alert rules MUST exist as code (provisioned via Grafana API) in `infra/grafana/`. Rationale: reproducibility (C-1.6).

## C-5 Security
- C-5.1 Secrets ONLY via env vars / Secret Manager; `.env*` gitignored; pre-commit secret scan mandatory. Rationale: public repo.
- C-5.2 Backend endpoints MUST require auth (API key minted at deploy) except health. CORS allowlist explicit. Rationale: public URL exposure.
- C-5.3 Error responses MUST NOT leak stack traces/env details. Rationale: hygiene.

## C-6 Architecture Invariants
- C-6.1 Frontend and backend deploy SEPARATELY: backend = Cloud Run container(s); frontend = Firebase Hosting interim, Replit-hosted final; all coupling via versioned HTTP/SSE API (`/api/v1/*`). Rationale: owner deployment decision.
- C-6.2 Media artifacts live in real Google Cloud Storage; job/project state in real Google Firestore. No substitute engines locally or in prod. Rationale: C-1.1 spirit — same services everywhere.
- C-6.3 Job processing MUST be asynchronous via lease-based queue (Firestore leases); workers idempotent per `job_id`. Rationale: retries without duplication.
- C-6.4 All timestamps UTC ISO-8601; money/token counts stored as integer micro-units. Rationale: aggregation safety.
- C-6.5 No component may call an LLM synchronously inside an HTTP request path >30 s; long generative work goes through jobs. Rationale: platform limits + UX.

## C-7 Cost Control
- C-7.1 Every generative call MUST carry an estimated-cost log field; per-day spend counter exported as a metric with a Grafana alert at 80% of budget. Rationale: credits are finite.
- C-7.2 Eval runs MUST print aggregate cost before executing batches > $5 estimate and require `--yes`. Rationale: surprise prevention.

## C-8 Documentation
- C-8.1 Each station directory MUST contain README describing capability, real-service dependencies, how to run its tests AND evals. Rationale: stranger-reproducible.
- C-8.2 Architectural decisions of consequence MUST get short ADRs in `docs/adr/`. Rationale: agent handoff clarity.

## Amendments
- 2026-08-26: v1 initial — derived from owner Integrity Charter, AO rulings, hackathon rules.
