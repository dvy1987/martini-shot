# Execution Plan: Post Command (slug: `post-command`)
Date: 2026-08-26 | Spec: `docs/specs/2026-08-26-post-command-feature-spec.md` (Approved)
Constitution: `docs/constitution.md@1` | Gates & rulings: `ideas/AO-STATION-MAP.md#amendments`

**Execution model:** coding agents in parallel where tasks are independent.
Every task carries: ID · mode (**TDD** = write failing test first → green →
refactor | **EDD** = build eval dataset+metric+threshold first → implement →
eval PASS) · dependencies (after:) · Definition of Done (DoD). No task is done
until its DoD evidence exists under `docs/evidence/<task-id>/`.

---

## PHASE -1 — Accounts & Foundations (owner + setup agent, day 0 morning)

| Task | Mode | DoD |
|---|---|---|
| F-1 Create Grafana Cloud free stack; accept Assistant T&Cs; record stack URL | owner | creds in Secret Manager / `.env.example` names listed |
| F-2 Create Google Cloud project; enable Cloud Run, GCS, Firestore, Secret Manager, Vertex AI, Cloud Build APIs; request $100 credits form (before Aug 31!) | owner | gcloud config saved locally |
| F-3 Repo init: license Apache-2.0 at root (detectable), README skeleton, CI-lite (`make lint test typecheck eval-check`), pre-commit (ruff, secret scan), gitignore incl. `.env*` | setup agent | commit exists; hooks run |
| F-4 Provision Grafana service account (for OSS MCP fallback path) + hosted MCP OAuth dry-run from dev machine; record which auth mode works headless | setup | decision note in `docs/adr/0001-mcp-auth.md` |

## PHASE 0 — G0 Generative Spike (day 0, blocks everything generative)

| Task | Mode | DoD |
|---|---|---|
| S-1 Curate 3 locked/slow shots from public-domain film into `fixtures/spike/` (README labels each file, C-1.3) | manual-ish | 3 files + README |
| S-2 Script `scripts/spike_bg_swap.py`: extract ≤12 frames, real Gemini image-edit call w/ anchor prompt + prev-frame conditioning, reassemble, compute flicker score | EDD-lite | script runs end-to-end on real API |
| S-3 Human verdict vs quality bar (mean flicker <0.18, no grotesque artifacts) recorded in `docs/evidence/G0/verdict.md`; GO or DEMOTE decision logged | owner | decision line in AO-STATION-MAP Amendments |
| **Gate G0:** spike passes → Pickups stays HERO. Fails → relight/bg-swap demoted to detect-and-report; promote Dub QC to hero slot. Either way P0 composition updated same day. | | |

## PHASE 1 — Spine (day 0–2) — three parallel tracks

### Track A — Core services (agent A)
| Task | Mode | After | DoD |
|---|---|---|---|
| A-1 `core/config.py`, structured logging, OTel init module exporting traces/metrics/logs via OTLP env vars; wired into FastAPI app factory | TDD | F-3 | unit tests for config precedence; OTel exporter initialized flag true in test harness (test uses real exporter class pointed at staging endpoint — no mock exporters) |
| A-2 GCS client wrapper (signed upload/download URLs); Firestore client wrappers | TDD | F-2 | integration test creates/uploads/downloads/deletes real objects in dev bucket + temp doc |
| A-3 Job model + lease queue (Firestore transactions): submit/lease/heartbeat/complete/fail/requeue-on-expiry; idempotency by job_id | TDD | A-2 | AC-S0.1 chaos test green: kill worker process mid-job (real subprocess kill), second worker completes it exactly once |
| A-4 ffmpeg/ffprobe wrapper (duration, fps, codec probe, loudness filter invocation, frame extraction/reassembly helpers) | TDD | A-1 | round-trip tests on fixtures; ±1 frame AC-S2.2 part 1 |

### Track B — Supervisor skeleton (agent B, parallel)
| Task | Mode | After | DoD |
|---|---|---|---|
| B-1 ADK agent scaffold: system persona (Post Supervisor), tool registry, autonomy toggle (propose-only default) | TDD | F-3 | unit tests for tool registry + toggle behavior |
| B-2 Grafana MCP connector: hosted endpoint client w/ OAuth token persistence + refresh; env-flag switch to OSS server w/ service-account token; tool surface: search_dashboards, query_promql, query_loki, search_traces, add_annotation, create_incident | TDD | F-4 | REAL round-trip: annotation written to our stack and read back via API in integration test (recorded response JSON as evidence; zero mocks of MCP layer) |
| B-3 AI Observability instrumentation of the agent (AI Observability SDK / OTel gen-ai conventions): tokens, cost, latency per call | TDD | A-1, B-1 | one real agent call visible in AI Observability dashboards (screenshot evidence) |

### Track C — Frontend interim shell (agent C, parallel)
| Task | Mode | After | DoD |
|---|---|---|---|
| C-1 Vite+React+TS app scaffold; API client against `/api/v1`; SSE hook; Firebase Hosting project + deploy action; dark cinematic theme tokens; empty pages routed per spec §7 | TDD (client logic) | F-3 | deployed interim URL serves shell; contract tests for API client against backend OpenAPI schema |
| **Gate G1 (end of Phase 1):** real MP4 → upload via interim FE → job created → processed by stub-free minimal ingest station (arrival+checksum only) → trace/metrics/logs visible in Grafana Explore → supervisor writes one real investigation annotation containing job_id → SSE updates UI. Evidence pack archived. Any gap = fix before Phase 2. | | | |

## PHASE 2 — P0 Stations (day 2–5; stations parallel after A-4 lands)

| Task | Station | Mode | Key tests first (RED) | DoD |
|---|---|---|---|---|
| D-1 Ingest full (probe, corruption detect, audio-sync spot check, quarantine flow) | S1 | TDD | corrupted-fixture detection table; checksum stream interruption | AC-S1.1/.2; annotation on quarantine |
| D-2 Loudness engine (ebur128 parse, stem heuristic, verdict tables, M&E check) | S3 | TDD | boundary-case LUFS verdict matrix ±0.3 dB | AC-S3.1; metric `pc_loudness_lufs` exported |
| D-3 Caption validator (SRT/VTT/TTML parsers, rule engine w/ rule IDs) | S4 | TDD | golden files: valid + 7 violation classes | AC-S4.1; 90% coverage |
| D-4 Delivery spec packs (YAML profiles + evaluator delegating D-2/D-3) | S5 | TDD | compliant/violating fixture matrix per profile | AC-S5.1; report renders in FE |
| D-5 Pickups pipeline (frame loop, anchor-prompt builder, prev-frame conditioning, reassembly) | S2 | EDD | dataset manifest FIRST (10 clips), flicker metric implementation (classical CV) + thresholds.yaml | AC-S2.1 eval suite runs; JSONL archived |
| D-6 Pickups QC + auto-retry (flicker breach → strengthen anchors → retry ×2 → needs_human) | S2 | TDD+EDD | retry state machine unit tests; threshold breach simulation using REAL prior eval outputs (no synthetic scores fabricated) | AC-S2.2; cost estimator matches actuals ±20% |
| **Gate G2:** all deterministic P0 stations pass against real fixture media through the real queue; Grafana dashboards show their metrics; FE shows live results. Evidence pack archived. | | | | |

## PHASE 3 — Hero depth + P1 (day 5–8)

| Task | Station | Mode | DoD |
|---|---|---|---|
| E-1 Relight op (stretch) behind feature flag; same eval bar | S2 | EDD | eval PASS or documented demote decision |
| E-2 Consent guard: face-region detector + policy engine + append-only ledger + IRM incident on violation | S7 | TDD (+EDD region classifier eval ≥95% IoU on fixtures) | AC-S7.1; ledger rows visible in FE; incident appears in Grafana IRM |
| E-3 Dub QC: TTS dub generation (SSML pacing), duration-delta measure, envelope cross-correlation sync estimate, Gemini listen-classify on flagged samples | S6 | EDD | AC-S6.1 eval JSONL; playable dub pair in FE |
| E-4 Conform Sentinel: manifest verifier, frame-count/reel/hash diagnostics | S8 | TDD | AC-S8.1 distinct diagnostic codes |
| **Gate G3:** hero op(s) hold quality bar across ≥3 fresh curated shots (not just spike set); consent block demonstrably fires on a planted face-touching op; evidence video clips captured (raw, unedited). | | | |

## PHASE 4 — Supervisor intelligence (day 8–10)

| Task | Mode | DoD |
|---|---|---|
| H-1 Investigation chains: alert→PromQL→LogQL→Tempo correlation playbook prompts; severity rubric; proposal formatting | EDD (rubric judge) | AC-A.1 integration scenario green end-to-end |
| H-2 Morning report generator (Gemini summarization over real telemetry excerpts w/ citations to query results) | EDD | AC-A.2 faithfulness rubric ≥4/5 on 5 seeded scenarios |
| H-3 Approvals inbox FE + autonomy toggle enforcement (propose vs act) | TDD | toggle honored in agent middleware tests |
| H-4 Dashboards-as-code finalized (Project Overview heatmap, Station Health, Cost, Evals, Self-Observability) + alert rules incl. spend 80% | config | `infra/grafana/` provisions cleanly via API into fresh folder; screenshots archived |

## PHASE 5 — P2 richness (day 10–13, strictly in order, each gated by its own check)

I-1 Cue Sheet Auditor (TDD) → I-2 Dialogue Doctor (EDD) → I-3 Trailer Bench (TDD)
→ I-4 Archive Keeper (TDD) → I-5 Accessibility Auditor (TDD) → I-6 Restoration
stats + clean-up stretch (EDD) → I-7 Edit-Assist continuity (EDD) → I-8 Handoff
Validator UI surfacing spine-level checks (TDD).
Rule: station N+1 starts only when station N's integration truth-check passes;
any slip consumes P2 budget, never P0/P1 polish.

## PHASE 6 — Full-journey rehearsal, hardening, submission (day 12–15)

| Task | Mode | DoD |
|---|---|---|
| J-1 Seed full journey: public-domain short traverses EVERY completed station; supervisor handles all seeded faults (announced list maintained in `fixtures/journey/README.md`) | integration | AC-A.1 style assertions per station; morning report compiles |
| J-2 Chaos pass: kill workers mid-run, revoke+refresh OAuth, network flap to OTLP — product recovers without data loss | integration | recovery log evidence; no orphaned leases |
| J-3 Replit hosting swap rehearsal (identical build, CORS/base-URL change only) | deploy | both URLs live; rollback doc |
| J-4 README final: stranger-rerunnable quickstart (env, provision scripts, make targets, cost expectations), honest limitations section | docs | fresh-agent reproducibility walkthrough passes (C-1.6) |
| J-5 Record 3-min video FROM THE RUNNING PRODUCT (C-1.5), narration script lists announced fault injections; captions EN | media | raw takes + final cut archived under `docs/evidence/video/` |
| J-6 Devpost submission form complete; repo About shows license; submit ≥24 h early | admin | confirmation email screenshot |

## Gate Summary

G0 spike verdict · G1 spine truth-check · G2 P0 determinstic truth · G3 hero
quality bar · G4 full journey · G5 freeze (video from product only). Failed
gate ⇒ fix or demote lowest-priority unfinished work; NEVER substitute mocks
(C-1.*).

## Parallelization Map (agent workforce)

Max 3–4 concurrent agents: Phases 1 A∥B∥C; Phase 2 D-1..D-4 ∥ D-5..D-6 (two
agents) once A-4 lands; Phase 3 four-way; Phase 6 sequential-ish (J-1→J-2→J-5).
Owner touchpoints required at: F-1/F-2, G0 verdict, G3 quality review, G5
recording session, J-6 submission.

## Budget Guardrails

Estimated spend caps: spike <$2 · evals total <$25 · journey rehearsals <$20 ·
buffer $50. `pc_job_cost_micros` dashboard reviewed at each gate; alert at 80%
(C-7.1).
