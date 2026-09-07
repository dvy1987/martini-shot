# Agent Handoffs

## 2026-09-07 06:20 - D-10 correction guard started

### Done
- Added the first D-10 TDD slice: correction prompts reject blank intent and preserve explicit subject and continuity constraints.

### Deferred
- The actual queued Omni edit, H-0 command, EDD dataset/rubric, API, and drawer controls remain required before D-10 can be called complete.

### Next Agent Should Know
- The prompt function is `backend/stations/corrections/run.py::build_correction_prompt`; it deliberately does not infer a target from an ambiguous brief.

### Working Tree
- D-10 prompt guard and regression test ready to commit.

## 2026-09-07 06:10 - Multi-agent runtime gap closure

### Done
- Production deliberations now inject real Verification and Post Supervisor Gemini synthesis callbacks.
- Model synthesis is restricted to partitioning existing verified candidates; it cannot invent or mutate an H-0 action.
- Daily Spend Control admission is transactionally reserved, and detached cycle outcomes are consumed and logged.
- Updated stale runtime evidence; non-terminal signal routes are explicitly deferred with reasons.

### Deferred
- ACT remains deliberately unactivated until owner-approved live rehearsal. Stage 1a domain pipelines follow.

### Next Agent Should Know
- Real-service integration tests require configured GCP credentials; deterministic contracts pass locally.

### Working Tree
- Runtime gap closure ready to commit on `cursor/full-stage-1a-demo-be5d`.

## 2026-09-07 05:55 - Full Stage 1a demo scope baseline

### Done
- Confirmed Amendment A11 is reflected in the canonical task plan and feature spec.
- Corrected the durable decision record to the owner-approved $100 remaining Stage 1a eval/demo envelope.
- Indexed the active scope and logged its planning provenance.

### Decisions
- Stage 1 plus D-10, E-1, D-11, D-12, D-15, and D-16 is the demo release; G3/G3a are integrated gates.
- Each Stage 1a operation requires its own agent, live-model EDD, manual UX path, H-0 execution path, alternate, and Grafana audit.

### Deferred
- Implementation begins with the multi-agent runtime gaps, then the six Stage 1a vertical slices.

### Next Agent Should Know
- Do not edit `/opt/cursor/artifacts/plans/plan.md`; it is the immutable request reference. The canonical project artifacts are under `docs/`.

### Revisit Triggers
- $100 envelope exhaustion requires an explicit owner decision; batches above $5 require `--yes`.

### Working Tree
- Scope-record documentation changes ready to commit on `cursor/full-stage-1a-demo-be5d`.

## 2026-09-07 (late, session 2) - Stage 1a agents COMPLETE (live EDD); A1 done; E-3 run unblocked

### Done
- **H-1h / H-1i / H-1j ALL BUILT + LIVE EDD GATES GREEN** (commit `3544d5c`): continuity.py, creative_finishing.py, visual_qc.py in `backend/supervisor/station_agents/` + eval scripts `scripts/<agent>_eval.py`. Each: 3 consecutive live Vertex runs, accuracy 1.0/1.0/1.0 (gate >=0.8). Evidence `docs/evidence/H-1h|H-1i|H-1j/`. HARD GATES in code (not prompt): locked_cut_overwrite (coerces locked-cut retry -> logged abstention), draft_first (master w/o passing draft coerced to draft tier), no_metrics_no_pass + all-bars (breach/self-report distrust; promote impossible w/o clean real metrics). cf-02 dataset row has NO alternates_context (eval uses `row.get(...) or {}` — harness bug caught BEFORE billing, zero wasted calls).
- **A1 DONE** (`d5c8587`): all 4 raw urlopen sites in generative.py + run_agent_call in otel_ai.py routed through `call_with_resilience` via `_resilient_urlopen` (whole urlopen+read = one try-unit). Inline retry loops deleted.
- **Dub MP4 defect caught pre-run** (`162f011`): E-3 sources are MP4s but run_dub fed raw bytes to wave-based measure_timing — every dub job would bill TTS then die. Proven with real ffmpeg probe, fixed TDD: `source_wav()` in dubbing/qc.py decodes any container -> 24kHz mono LINEAR16 (WAV passes through). 8/8 tests in test_dubbing_run.py.
- `scripts/e3_run_worker.py` written (lint-clean): drives the 96 seeded job ids via process_job_id (NO re-seed), up to 3 passes for queue requeues, archives per-job JSONs + batch_summary to `docs/evidence/E-3/raw/`, exit 1 if non-terminal.
- Full pytest suite was started but KILLED mid-run (~35%) per owner redirect; next agent runs `make check`. Targeted: dub tests 8/8, ruff+mypy clean on all touched files.

### Next Agent Should Know
- **FIRST ACTION: run the E-3 batch** — `.venv\Scripts\python.exe scripts\e3_run_worker.py` (96 real jobs, ~$0.10 pre-approved). Dub jobs are the 24 billable ones. Then A3: archive raw outputs (dub WAVs from GCS `projects/<project>/dubs/<job>.<lang>.wav` refs in job results) + write `docs/evidence/E-3/README.md`. Then G3 (Workstream C of the Stage 1a plan) — all three H-1 agents are DONE, only G3 evidence + FE dub pair remain for Stage 1a.
- New unit tests for the three agents were NOT written as files (owner redirect; sanity-checked via inline parse/gate assertions instead). If `make check` needs coverage: test schema validation, fence-tolerant parse, one run_agent_call per invocation, and the three hard gates (patterns in test_station_agents.py).
- Live-eval pattern proven: cheap model + ordered decision ladder in prompt + hard gate in code = 1.0 accuracy first try on all three suites.

### Revisit Triggers
- Jobs stuck non-terminal >30 min -> lease/429 (A1 wrapper now absorbs transients).
- Eval miss -> prompt rule only on real miss; ordered ladder if tuning overshoots.
- Budget error on TTS/Veo -> stop, report cost, ask owner.

### Working Tree
- All committed + pushed at `162f011` (main == origin/main).

## 2026-09-07 (late) - A10 complete; E-3 batch queued (96 jobs live); Stage 1a handoff

### Done
- A10 amendment FULLY delivered: 9 station agents (Dub QC, Batch Orchestrator, Ingest Triage, Loudness Strategy, Caption Remediation, Delivery Strategy, Extend QC, Spend Steward, Pickups Vision QC) - all EDD gates 3-run green, evidence in `docs/evidence/A10-*/`, pushed through `f879888`.
- E-3 demo batch: manifest approved (8 eps x es-ES/fr-FR/de-DE = 24 items x 4 stations = **96 REAL jobs submitted** to Firestore lease queue, ~$0.10 est, owner-approved). Sources uploaded to `gs://martini-shot-media/e3/`. Dry-run + seed evidence in `docs/evidence/E-3/`. **Worker has NOT run - jobs are queued, first action for next agent.**
- Shared API-resilience layer `backend/core/api_resilience.py` + 9 tests green (jittered exponential backoff, Retry-After honored, 429+5xx transient, fail-loud 4xx). Call-site rewiring NOT done - see plan Workstream A1.
- Owner directives active: (1) API hygiene is SYSTEMIC - all outbound calls route through `call_with_resilience`; (2) keep ALL raw outputs for the demo - archive to `docs/evidence/E-3/raw/`; (3) credits low - cheapest step that advances the plan.

### Next Agent Should Know
- **Read `docs/plans/2026-09-07-stage1a-completion-plan.md` FIRST - it is the complete execution plan through Stage 1a completion** (E-3 run + raw archive, H-1h/i/j agents with hard gates, G3, FE dub pair). Written for a cheap-model executor: explicit commands and pitfalls included.
- 96 jobs in queue: process via `scripts/e3_run_worker.py` (create per plan A2, mirrors g2_gate.py import style) or the API lifespan worker. Do not re-seed.
- Stage 1a remainder: only H-1h/i/j agents missing; datasets + thresholds already seeded on disk.
- PowerShell 5.1: no `&&`; pre-commit runs ruff-format (format before add); git exit-1 on stderr noise is cosmetic - verify with `git log -1`.

### Revisit Triggers
- Jobs stuck non-terminal >30 min -> check worker lease + transient 429 handling (A1 wrapper should absorb; persistent = real failure, record honestly).
- Eval miss -> tune prompt ONLY on real miss; ordered decision ladder if tuning overshoots (spend_steward.py pattern).
- Budget error on TTS/Veo -> stop, report cost, ask owner.

### Working Tree
- Everything committed + pushed at handoff (HEAD past `e433398`, includes E-3 seed artifacts + resilience layer + this handoff).

## 2026-09-02 06:30 - Rest-of-sprint P1-P3 + G2; push pending

### Done
- P0 local commits `d8ee2e7` + `c2ecb36` were still unpushed vs `origin/main` `4aaa6d5`.
- P1: Grafana MCP tools on ToolRegistry. Act-class `add_annotation` / `create_incident` check autonomy before MCP dispatch. Evidence `docs/evidence/B-2b/`.
- P1b: `frontend/src/api/contract.test.ts`. Did not change 401 body.
- P2/B-3: real Vertex text call; `cost_micros=400`. Evidence `docs/evidence/B-3/`.
- P3: D-1..D-7 (pickups identity/EDD, no Veo). Gate G2 GREEN project `g2-6d2d7919` — spend throttled 40x runaway. Slate is silent 4:3: loudness `fail_quiet`, delivery AR fail (honest).
- 165 pytest passed, 93.64% coverage. FE typecheck/test/lint/build green.

### Debated
- Did not rewrite megacommit `d8ee2e7`. TestClient SSE stream deadlocks on the infinite ping generator.
- Grafana `create_incident` FK error on this stack; annotation still writes. Do not fake incidents.

### Decisions
- Pickups stay identity-QC until EDD bars plus `--yes` for billable generate.
- OSS MCP remains the Grafana path. Hosted OAuth still F-4.

### Deferred
- Hosted MCP OAuth (F-4). Firebase sign-in (H-3). Replit static deploy. Stage 1a.

### Next Agent Should Know
- Restart local uvicorn so spine/present match git (G2 listing hit a pre-reload process).
- Rotate `POST_COMMAND_API_KEY` / `VITE_API_KEY` (G1 SSE query-string leak).
- Grafana incident org FK may need a Cloud-side fix before Spend incidents stick.

### Revisit Triggers
- Grafana SA 401 → regenerate; do not fake MCP.
- Instant PromQL empty → range `now-1h`.
- `create_incident` FK 1452 → Grafana Cloud, not a local mock.

### Working Tree
- Logical commits then push `main` (owner approved in rest-of-sprint plan).

## 2026-09-01 14:20 - Rest-of-sprint plan locked; P0 hygiene

### Done
- Critically rejected stale M0–M5 handover: B-2 is `4aaa6d5`, G1 is GREEN (API+worker, not FE “Log a clip”).
- Owner approved: commit+push checkpoint, then supervisor MCP wiring before stations.
- G1 README no longer treats a UI intake button as the proof path. Tasks file marks B-2 done.

### Debated
- One megacommit `d8ee2e7` already bundled G1+UX; did not rewrite history. Hygiene is a follow-up commit.

### Decisions
- Hosted OAuth (F-4/M3) deferred. OSS MCP remains the Grafana path.
- Workers remain research-only.

### Deferred
- Firebase sign-in (spec §7.2) until H-3.
- Replit static deploy until owner approves the runbook table.
- Stage 1a.

### Next Agent Should Know
- After this checkpoint is pushed, execute P1 (`backend/supervisor/tools.py` + autonomy gate on `create_incident`/`add_annotation`) then P1b contract tests, then stations D-1→D-2→D-7.
- Rotate API keys (G1 SSE `?api_key=` logged).

### Revisit Triggers
- 401 from Grafana SA token → owner regenerates; do not fake MCP.
- Instant PromQL empty → range `now-1h`.

### Working Tree
- Hygiene commit on top of `d8ee2e7`; push to origin/main for Replit sync.

## 2026-09-01 13:45 - G1 gate + D-1 core + Replit Steps 3–6 verified & committed (orchestrator)


### Done
- Gate G1 RUN GREEN (real MP4 → ingest → Grafana signals → annotation w/ job_id → SSE; evidence `docs/evidence/G1/gate.json`, `sse.ndjson`).
- D-1 core: ingest station (checksum), `jobs/worker.py` lease loop, `api/spine.py` (projects/jobs/ingest/SSE), `present.py`, `events.py`, `supervisor/annotate.py`, FE timeline wiring.
- Replit UX Steps 3–6: Screening Room, dailies, slates, ⌘K, Lens (63/63 FE tests). Runbook `docs/runbooks/replit-static-deploy.md`.
- Orchestrator fixes: spine `Annotated[UploadFile, File()]`, ruff format, FE localStorage test shim (`src/test/setup.ts`), chaos-test FIFO flake fixed (order-agnostic victim).
- Full handover rev 2: `docs/plans/2026-09-01-post-command-handover.md`.

### Decisions
- Test-only localStorage shim allowed under C-1.3 (Node ≥22 needs `--localstorage-file`; app always runs in real browser origin).
- Chaos test must not assume FIFO on tied `created_at` (ms precision) — victim is whatever the queue leases.

### Next Agent Should Know
- Remaining queue in handover §3: D-1 completion → sign-in-to-approve (NO firebase dep yet — spec §7.2 open) → B-3 → F-4 (one-way door) → D-2..D-7 + G2 → H-* → J-*.
- `make check` + FE gates all green at handover; commit + push done.

### Revisit Triggers
- Firestore lease-order tie-break: if a station needs strict FIFO, queue needs a created_at+doc-id ordering change (ask first — queue semantics).
- mcp-grafana upgrade changing tool names/shapes; SA token expiry (401s across python+curl+MCP = dead token, regenerate).

### Working Tree
- Clean after this commit (receiving agent's tree verified + committed + pushed).

## 2026-09-01 11:16 - B-2 Grafana MCP live round-trip GREEN

### Done
- Plan B-2: `backend/supervisor/mcp.py` OSS stdio connector (mcp-grafana v1.3.0 + SA token) and hosted Streamable HTTP config (OAuth persistence still F-4).
- Unit tests 12/12 (`tests/test_supervisor_mcp.py`); live integration GREEN (`tests/test_supervisor_mcp_integration.py`).
- Evidence: `docs/evidence/B-2/roundtrip.json` — PromQL `pc_otel_smoke_total` samples + annotation write/read with `job_id=b2-9a3c13ed` (C-4.3). 80 MCP tools listed.
- Config: `MCP_GRAFANA_BIN`; `mcp>=1.10,<2`; `tools/` gitignored.

### Debated
- Instant PromQL vs range: OTLP counters are sparse; Grafana Cloud instant/`now` returns `{data:[]}`. Connector default stays instant; live test uses range `now-1h` step 15s. Fresh `scripts/otel_smoke.py` emit was required to have queryable samples.

### Decisions
- OSS headless path is the proven B-2 DoD (ADR-0001 fallback). Hosted OAuth token persistence remains F-4.
- mcp-grafana v1.3.0 `list_datasources` envelope is `{datasources, total, hasMore}` — unwrap before iterating.

### Deferred
- Hosted MCP OAuth browser flow + token persistence (F-4).
- Remaining G1 pack: 3 PromQL + Loki line + trace ID from station traffic (annotation JSON now exists under B-2; G1 still wants the full ingest path).
- C-1 frontend review delta.

### Next Agent Should Know
- `MCP_MODE=oss` locally; binary at `tools/mcp-grafana/mcp-grafana.exe` (gitignored, v1.3.0). SA token works (`GET /api/datasources` HTTP 200). PowerShell `-c "..."` one-liners wrap and SyntaxError — use a here-string piped to `python -`.
- Track A (A-1..A-5) and B-1 already on `main` from prior sessions; memory was stale until this handoff.
- Workers remain research-only.

### Revisit Triggers
- Empty PromQL on `pc_otel_smoke_total` → re-run `python scripts/otel_smoke.py`, then range query (not instant).
- mcp-grafana upgrade that changes tool names or datasource JSON shape.

### Working Tree
- Committing B-2 connector + tests + evidence + env/config wiring (no `.env`).

## 2026-08-30 — crosscheck PASS, A6 worker verdict, A-1 shipped (orchestrator)
**Done:** Spec-crosscheck executed (FAIL: C-5.3/C-2.4/C-8.1 unaddressed + tasks artifact missing) → owner approved plan → amendment A7 applied to plan (C-5.3 clause in A-1 DoD, F-3b fresh-source attestation, C-8.1 station-README clause ×7, G1 records AC-S0.2 evidence) → tasks file `docs/plans/2026-08-26-post-command-tasks.md` generated → re-run **PASS** (commit `0f6c412`). Worker review (A6): B-1 (dc7b787f) + Track C (d946c76f) reported complete but wrote ZERO files → reverted to orchestrator; lane 0-for-3 → **workers demoted to read-only research**. A-1 rebuilt orchestrator-led TDD: RED observed (`docs/evidence/A-1/red-pytest.txt`), then GREEN — config/logging/otel/models/errors + app factory + main.py; C-5.3 error envelope tested; API-key gate fail-closed; test_smoke fixed to check git index (local gitignored .env is expected). Commit `d0d866c`, all hooks green, 27/27 tests. Owner rulings recorded: **Stage 1a stays as amended (A5) but this sprint builds Stage 1 only** (Phase 3a behind G3, untouched).
**Next for executing agent:**
1. A-2 GCS/Firestore wrappers (TDD, real dev bucket + temp doc) → A-3 lease queue + AC-S0.1 chaos test + pytest-cov (C-3.2) → A-4 ffmpeg wrapper → A-5 handoff validator.
2. B-2 Grafana MCP REAL round-trip (annotation write + read back); C-1 FE review delta.
3. Gate G1 evidence pack: trace ID + 3 PromQL + Loki line + annotation JSON (A7 requirement).
**Drift:** none from handoff; backend/core+api now exist (previously empty).

## 2026-08-28 — project-setup (setup agent)
**Done:** Project setup executed per `.agents/skills/project-setup`. Owner interview: non-technical owner (agents lead architecture + design), full autonomy granted for security/secrets/auth and testing/evals, Session Lifecycle + harness ON, Replit = frontend hosting + partial dev (verified rule-compliant for the Grafana track; AI restriction covers AI tooling only). Created: root/frontend/backend AGENTS.md (multi-mode), `.cursor/rules/*.mdc` adapters, knowledge graph (docs/knowledge-graph/), F-3 scaffold (LICENSE Apache-2.0, .gitignore, Makefile CI-lite, pre-commit, .env.example x2, mypy.ini, tests/test_smoke.py, scripts/integrity_check.py C-1.2, backend/evals/check_thresholds.py C-3.4, dir skeleton), README rewritten as product README.
**Validation:** `make`-equivalent gate all green: ruff check+format clean, mypy clean, pytest 3 passed, integrity clean, eval-check OK (no suites yet). Pre-commit installed.
**Next for executing agent:**
1. `/tasks` (implementation-plan tasks-only) to derive the agent-pickable task list, then `/analyze` (spec-crosscheck) — required before `/implement`.
2. Owner Phase -1 tasks outstanding: F-1 Grafana Cloud stack, F-2 GCP project + credit form BEFORE Aug 31, F-4 MCP auth dry-run → ADR 0001.
3. First build action after that: **G0 spike** (real Gemini bg-swap on 3 frames) — mandatory, blocks all generative work.
4. Proposed (owner not yet approved): spec §7 amendment for SSE envelope + FE auth + Replit mechanics (`.replit`, SPA rewrites, VITE_API_BASE_URL). See session log for the draft.
**Drift:** none from handoff; repo was docs-only before this session.

## 2026-08-28 — UX direction decided (setup session, continuation)
Owner rejected the 3-option archetype menu and ordered independent first-principles + adversarial thinking. Decision recorded in `docs/design/DESIGN.md` v1 (binding): evidence-first, exception-first, film-native grammar; flagships = Season Timeline (CSS-grid lanes, table fallback), Investigation Cards (case file, not chat), Screening Room (approvals incl. Spend Control escalations); DI-suite dark tokens (tungsten #E8A33D attention, signal #3FB68B, agent #5B7FDB); IBM Plex Sans + JetBrains Mono; demo-legibility rules (APCA ≥60, 1080p). Floor = spec §7 console, flagship additive on same typed API. Deliverable to owner: initial Replit prompt for frontend scaffold.

## 2026-08-28 — DESIGN v2 + product renamed (same session)
Owner rulings: (1) "frontend must not be crowded" → DESIGN.md v2: progressive reveal (one inspector drawer, folded evidence chips, lane collapse, Lens-hidden filters, staggered entrance) + educational carousels as film-native **slates** (welcome/investigation/accounting/dailies; skippable, `pc.seen.*` localStorage). Density confined to timeline/table data surfaces. (2) Product display name **Martini Shot** (codename slug `post-command`, `pc_*` metrics, `POST_COMMAND_*` env names unchanged). Renamed: README, AGENTS.md, spec+plan headers, DESIGN.md, LICENSE, Makefile, .env.example. Harness manifest hashes regenerated after AGENTS.md edit. Replit prompt addendum delivered (v2 + rename).

## 2026-08-28 — DESIGN v3 motion system (same session)
Owner ruling: delightful microinteractions + animations (Framer or GSAP, Leonardo.ai reference). DESIGN.md v3: Framer Motion chosen over GSAP (React primitives, single motion stack; GSAP deferred). Motion inventory + binding rules in charter (one damped spring curve, ≤280ms entrances, 3 sanctioned loops: marker pulse / pill breath / clip shimmer; reduced-motion + paused-frame truthfulness). Harness manifest hashes regenerated after the AGENTS.md rename (drift clean). Consolidated Replit prompt v2 delivered (includes v2 reveal+slates, v3 motion, Martini Shot naming).

## 2026-08-28 — frontend skeleton committed (same session)
Owner asked for a local frontend skeleton + the Replit prompt broken into sequential steps. Built `frontend/` skeleton: single strict tsconfig (ES2022, noUncheckedIndexedAccess, `@/*` alias), Vite 5 + Tailwind v4.3.3 (`@theme` tokens straight from DESIGN.md; base layer uses plain CSS vars — @apply of custom utilities is unsupported in 4.3.3), react-router-dom 6 routes (`/`, `/approvals`, `/reports`), app shell (TopBar with mono UTC clock, NavLink, ⌘K hint, truthful ConnectionPill), designed empty states on every page, timeline "Reading the board" legend rendered from STATUS_META, framer-motion variants module (revealSpring / fadeRise / drawer / stagger), typed `/api/v1` client (single transport module, X-API-Key, `{code,message}` ApiError envelope), typed endpoints module, useSSE (exponential backoff + jitter) and useBackendHealth hooks. Tests: vitest + jsdom + RTL — 19 passing (formatters, status vocabulary, client error envelope, SSE reconnect lifecycle).
**Validation:** `tsc --noEmit`, eslint, vitest 19/19, `vite build` all green; integrity gate clean (scanner extended to exclude vitest test naming — tests stay C-1.2-excluded); harness manifest regenerated after the AGENTS.md commands-line update, drift clean.
**Next for executing agent:**
1. Execute per re-baselined calendar: G0 probe (Vertex capability probe + Omni/Veo quality spike) Aug 28–29 → Phase 1 spine → Phase 2 → Phase 3 → Phase 3a (Stage 1a) → Phase 4 → Phase 6 (submit Sep 8). G0 verdict = owner touchpoint.
2. Stage 1 is the guaranteed fallback submission; Stage 1a ops demote in order D-16 → D-15 → stretch if the calendar bites.
3. Gen-AI spend ceiling $50–75; batches >$5 need owner `--yes` (C-7.2).

## 2026-08-28 — A5: Stage 1a fast-follow + backend plan approved (same session)
Owner rulings accumulated: real Gemini media-model integration everywhere (Vertex AI primary, $300 GCP credits; AI Studio fallback); demo batch trimmed to 8–10 eps × 3 languages; new features staged as **Stage 1a** (fast-follow; Stage 1 unchanged as the guaranteed coherent fallback). Stage 1a ops: D-9 Extend, D-10 Corrections, D-11 Draft-first, E-1 Relight Studio (named lighting presets + rubric judge), D-12 Coverage (subject-reference anchored), D-15 Revision Room (script alignment → diff → regen + dub pipeline), D-16 Camera Language (presets + suggestions + reference-style transfer), AL-1 Alternates model (every generated clip = alternate; continuity changes approval-tracked); stretch D-13 Transition Forge, D-14 Versioning. Docs amended: spec §5/§7 + header, plan (Phase 3a, G3a gate, calendar re-baseline, budget A5 block, E-3/J-0 3-langs), AO map §9 + header, AGENTS.md (Generative Depth block + demo-beats line), DESIGN.md (Stage 1a surfaces). Manifest regenerated; drift clean.

## 2026-08-28 — AUTH RULING: sign-in-to-approve (same session)
Owner ruled after reviewing the pasted Replit track requirements: **board open to visitors; Approve/Reject requires one-click Google sign-in (Firebase Auth on the frontend, ID token verified backend-side via firebase-admin); approver identity recorded on the approval and in the Grafana annotation (C-4.3 audit trail).** Read paths stay on the existing API-key transport. Verified: no Replit rule conflicts — their conditions cover Replit Agent usage + replit.app hosting (both already our flow) and say nothing about authentication; Replit Auth itself is unusable here (requires a Replit-hosted server; ours is Cloud Run). Consequences: frontend gains the Firebase JS SDK (one new npm dep, covered by this ruling); Replit Step 3 grows the sign-in gate before the decision POST; backend phase adds token verification middleware + approver field on annotations. Spec §7 amendment (SSE envelope + FE auth + Replit mechanics) presented for owner approval — spec itself NOT edited until that approval lands (spec §11). FOLLOW-UP: approval received; amendment written into the spec (header, §7.1–7.3, §8 non-goal, §9 decision row) and logged in SKILL-OUTPUTS.

## 2026-08-28 — Replit Steps 1–2 reviewed; review fixes applied (same session)
Owner ran Replit Agent on Steps 1–2 on Replit and pulled 5 commits (0fa6f58..0deb3cf): TimelineBoard (lanes, table fallback, lane collapse, two-click select) + project selector + App-level SSE wiring into the query cache; InvestigationDrawer (case file, folded evidence/transcript, focus trap, esc/scrim); `.replit` dev workflow; vitest ^2→^3 upgrade (kept, tests green); `attached_assets/` paste artifacts (kept per owner, now gitignored). Review verdict: charter-faithful, zero fabricated data (C-1.2 clean), 32→35 tests. Fixes applied in this commit: [P1] unvalidated `STATUS_META[job.status]` on REST paths (drawer + board) → new `statusMetaOrUnknown()` total lookup with truthful "Unrecognized" fallback + regression test (drawer renders unknown "cancelled" status without crashing); [P3] `cost_micros` truthiness on clip border ($0.00 lost its tungsten edge); [P3] ghost `font-display` class removed (5 spots — no such token). All gates green after fixes: typecheck, 35/35 vitest, eslint, build, integrity. Steps 3–6 clear to proceed on this base.

## 2026-09-06 — E-2 Dub QC station COMPLETE: agentic, eval-green, evidence pushed
Commits: 7abdb5f (station+agents+tests), 3ea25b8 (eval evidence). A10 slice 1 of 5 done.
**What exists:** ackend/stations/dubbing/{qc,run}.py + README; ackend/supervisor/station_agents/{base,dub_qc}.py (StationDecision contract: mandatory reason, explicit override vs deterministic_suggestion, proposals gated to H-0 REGISTRY_COMMANDS); 
un_agent_call gained udio=(bytes,mime) inline part + 300s HTTP timeout + bounded 429 retry (one call stalled 10+min; one 429 swallowed silently); eval scripts/dub_qc_eval.py with HONEST accounting (failed judgment = recall miss, never excluded - C-3.5).
**Live gates (docs/evidence/E-2/):** 3 runs, timing MAE 4.8/8.0/9.9ms (gate <=45), truncation recall 1.0 (gate >=0.9), ~.07/run.
**Load-bearing lessons (do not re-learn):** (1) Chirp 3 HD speakingRate/prosody response is NONLINEAR (0.8 -> 1.34x, probe scripts/probe_tts_rate.py) - re-render fitting cannot hit 45ms; the fix is ONE render + ffmpeg tempo stretch (qc.atempo_wav), exact and free. (2) TTS tails have breath/noise above naive amplitude floors AND sentence-final words below any floor - tail cuts remove silence, not words; the honest truncation-defect mutation is a hard EOF mid-speech (qc.truncate_speech_wav, 10%-of-loudest-50ms-RMS floor). Verified with real transcription probes (scripts/probe_fr03_hear.py): the agent heard "Prise 3" and was RIGHT to call the tail-cut dub clean - the dataset was the defect. (3) The dub agent needs the REFERENCE LINE in the prompt to detect missing content. (4) wave module: ffmpeg piped WAVs carry streaming headers (nframes=0xFFFFFFFF) - read to EOF, never copy nframes. (5) Full pytest suite takes ~32min (real Firestore) - use file-scoped runs; 2 pre-existing failures from H-1e commit 8f46e89 were fixed in 7abdb5f (model-ID comment in generative.py; apply_verdict now keeps actionless-but-claimed findings, drops only findings whose actions were ALL vetoed).
**Next (A10 order):** Batch Orchestrator Agent (E-3 dep) -> strategists (ingest/loudness/captions/delivery) -> retrofits (extend/pickups/spend) -> E-3 manifest + cost estimate -> G3 evidence -> FE playable dub pair. H-1h-i-j agent builds still pending. Parked: OAuth owner one-timer (5min, pre-demo).
