# Agent Handoffs

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
