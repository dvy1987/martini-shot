# Execution Plan: Martini Shot (slug: `post-command`)
Date: 2026-08-26 | Amended: 2026-08-28 (4-stage staging per owner ruling; Spend Control task; batch demo seed; handoff silent/UI split; A5: Stage 1a fast-follow, batch 3 langs, Vertex AI, calendar re-baseline)
Spec: `docs/specs/2026-08-26-post-command-feature-spec.md` (Approved, amended 2026-08-28)
Constitution: `docs/constitution.md@1` | Gates & rulings: `ideas/AO-STATION-MAP.md#amendments`

**Execution model:** coding agents in parallel where tasks are independent.
Every task carries: ID · mode (**TDD** = write failing test first → green →
refactor | **EDD** = build eval dataset+metric+threshold first → implement →
eval PASS) · dependencies (after:) · Definition of Done (DoD). No task is done
until its DoD evidence exists under `docs/evidence/<task-id>/`.

**Stage mapping (2026-08-28):** Phases 2–4 build **Stage 1** (sellable core).
Phase 5 builds **Stage 2 → 3 → 4** in that order, strict, each station gated.
Stages are the spec's scope model; phases are the calendar.

**Calendar re-baseline (A5, 2026-08-28):** submission target **Sep 8** (J-6 ≥24 h
early). G0 probe Aug 28–29 · Phase 1 spine Aug 28–30 · Phase 2 Aug 31–Sep 2 ·
Phase 3 Sep 3–4 · Phase 3a (Stage 1a) Sep 5–6 · Phase 4 Sep 6 · Phase 5
compressed to I-1-only stretch on Sep 7 · Phase 6 Sep 7–8 · submit Sep 8.
Slippage cuts Stage 1a stretch items first, then Stage 1a ops, then Stage 2 —
the G3 state (complete Stage 1) is the guaranteed coherent fallback submission.

---

## PHASE -1 — Accounts & Foundations (owner + setup agent, day 0 morning)

| Task | Mode | DoD |
|---|---|---|
| F-1 Create Grafana Cloud free stack; accept Assistant T&Cs; record stack URL | owner | creds in Secret Manager / `.env.example` names listed |
| F-2 Create Google Cloud project; enable Cloud Run, GCS, Firestore, Secret Manager, Vertex AI, Cloud Build APIs; request $100 credits form (before Aug 31!) | owner | gcloud config saved locally |
| F-3 Repo init: license Apache-2.0 at root (detectable), README skeleton, CI-lite (`make lint test typecheck eval-check`), pre-commit (ruff, secret scan), gitignore incl. `.env*` | setup agent | commit exists; hooks run |
| F-4 Provision Grafana service account (for OSS MCP fallback path) + hosted MCP OAuth dry-run from dev machine; record which auth mode works headless | setup | decision note in `docs/adr/0001-mcp-auth.md` |

## PHASE 0 — G0 Generative Spike (day 0, blocks everything generative — first build action)

| Task | Mode | DoD |
|---|---|---|
| S-1 Curate 3 locked/slow shots from public-domain film into `fixtures/spike/` (README labels each file, C-1.3) | manual-ish | 3 files + README |
| S-2 Script `scripts/spike_bg_swap.py`: extract ≤12 frames, real Gemini image-edit call w/ anchor prompt + prev-frame conditioning, reassemble, compute flicker score | EDD-lite | script runs end-to-end on real API |
| S-3 Human verdict vs quality bar (mean flicker <0.18, no grotesque artifacts) recorded in `docs/evidence/G0/verdict.md`; GO or DEMOTE decision logged | owner | decision line in AO-STATION-MAP Amendments |
| **Gate G0:** spike passes → Pickups stays HERO. Fails → relight/bg-swap demoted to detect-and-report; promote Dub QC to hero slot. Either way Stage 1 composition updated same day. | | |

## PHASE 1 — Spine (day 0–2) — three parallel tracks

### Orchestration & QC (owner ruling 2026-08-29 — binding for ALL phases)

Sub-agent dispatch is allowed and encouraged for throughput, but the
orchestrator (main agent) owns quality control. Rules:

1. **Dispatch:** independent, well-scoped tasks (a plan task, a station, a
   test suite) may go to worker sub-agents. Orchestrator never delegates:
   gate runs, commits, evidence verdicts, owner communication, and any
   spec/plan/ADR amendment.
2. **Review gates per task (no exceptions, strict SDD discipline):**
   - **Self-review by orchestrator:** read the sub-agent's diff line-by-line
     against the task DoD before accepting.
   - **Deterministic work (TDD):** tests must genuinely fail first (RED
     observed, not claimed). Verify by running the failing state, not by
     trusting the report.
   - **Generative work (SDD+EDD):** dataset + metric + numeric threshold
     exist BEFORE the feature runs; orchestrator inspects real outputs, not
     the sub-agent's descriptions of them (C-1.1).
   - **Full gate on the slice:** `make check` (or frontend equivalent) green
     in the orchestrator's own run — a sub-agent's green report is not
     evidence.
   - **Adversarial pass** on anything touching money (Spend Control),
     credentials, lease/queue correctness, or audit trail (C-4.3).
3. **Shoddy-work protocol:** a sub-agent report that contradicts the
   orchestrator's own verification = task reverted to orchestrator's hands +
   noted in the session log; repeated failures demote that sub-agent lane to
   read-only research only.
4. **Commits:** only the orchestrator commits, in logical units, after the
   review gates above pass.

### Track A — Core services (agent A)
| Task | Mode | After | DoD |
|---|---|---|---|
| A-1 `core/config.py`, structured logging, OTel init module exporting traces/metrics/logs via OTLP env vars; wired into FastAPI app factory | TDD | F-3 | unit tests for config precedence; OTel exporter initialized flag true in test harness (test uses real exporter class pointed at staging endpoint — no mock exporters) |
| A-2 GCS client wrapper (signed upload/download URLs); Firestore client wrappers | TDD | F-2 | integration test creates/uploads/downloads/deletes real objects in dev bucket + temp doc |
| A-3 Job model + lease queue (Firestore transactions): submit/lease/heartbeat/complete/fail/requeue-on-expiry; idempotency by job_id | TDD | A-2 | AC-S0.1 chaos test green: kill worker process mid-job (real subprocess kill), second worker completes it exactly once |
| A-4 ffmpeg/ffprobe wrapper (duration, fps, codec probe, loudness filter invocation, frame extraction/reassembly helpers) | TDD | A-1 | round-trip tests on fixtures; ±1 frame AC-S2.2 part 1 |
| A-5 Handoff Validator, silent mode (S0b): turnover-manifest checks at every station transition inside the spine; block + annotate on discrepancy; no UI | TDD | A-3 | AC-S0b.1: missing-manifest-file fixture blocks transition with reason code; complete manifest passes; annotation written |

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

## PHASE 2 — Stage 1 deterministic stations (day 2–5; stations parallel after A-4 lands)

| Task | Station | Mode | Key tests first (RED) | DoD |
|---|---|---|---|---|
| D-1 Ingest full (probe, corruption detect, audio-sync spot check, quarantine flow) | S1 | TDD | corrupted-fixture detection table; checksum stream interruption | AC-S1.1/.2; annotation on quarantine |
| D-2 Loudness engine (ebur128 parse, stem heuristic, verdict tables, M&E check) | S3 | TDD | boundary-case LUFS verdict matrix ±0.3 dB | AC-S3.1; metric `pc_loudness_lufs` exported |
| D-3 Caption validator as delivery sub-check module (SRT/VTT/TTML parsers, rule engine w/ rule IDs; consumed by D-4, no own screen) | S5 | TDD | golden files: valid + 7 violation classes | AC-S5.2; 90% coverage; rule IDs surface inside delivery report |
| D-4 Delivery & Compliance pack (YAML profiles + evaluator delegating D-2 + D-3) | S5 | TDD | compliant/violating fixture matrix per profile | AC-S5.1; report renders in FE |
| D-7 Spend Control (NEW, S5b): cost aggregation from `cost_micros`; YAML policies per station (per-job cap, retry cap, hourly/daily budgets, runaway pattern ≥N re-queues); act: throttle/stop/approve; annotation + incident on breach | S5b | TDD | policy table tests; seeded runaway job (40× re-queue) → throttled; budget breach → intake paused | AC-S5b.1/.2; Grafana annotation + incident created; approval flow routes to Approvals inbox |
| D-5 Pickups pipeline (frame loop, anchor-prompt builder, prev-frame conditioning, reassembly) | S2 | EDD | dataset manifest FIRST (10 clips), flicker metric implementation (classical CV) + thresholds.yaml | AC-S2.1 eval suite runs; JSONL archived |
| D-6 Pickups QC + auto-retry (flicker breach → strengthen anchors → retry ×2 → needs_human; retry loop visible to D-7 policies) | S2 | TDD+EDD | retry state machine unit tests; threshold breach simulation using REAL prior eval outputs (no synthetic scores fabricated) | AC-S2.2; cost estimator matches actuals ±20% |
| **Gate G2:** all deterministic Stage 1 stations (S1, S3, S5 incl. captions, S5b) pass against real fixture media through the real queue; Spend Control demonstrably throttles one seeded runaway; Grafana dashboards show their metrics; FE shows live results. Evidence pack archived. | | | | |

## PHASE 3 — Stage 1 hero depth + Dub QC (day 5–8)

| Task | Station | Mode | DoD |
|---|---|---|---|
| E-2 Dub timing QC (PROMOTED to Stage 1): TTS dub generation (SSML pacing), duration-delta measure, envelope cross-correlation sync estimate, Gemini listen-classify on flagged samples | S4 | EDD | AC-S4.1 eval JSONL; playable dub pair in FE |
| E-3 Batch demo dataset seed (start early — TTS is slow + billable): script generates 8–10 episodes × **3 languages** (EN source + 2 picked by voice quality/cost) dubs + captions into `fixtures/batch-demo/`; cost estimate printed before run (C-7.*) | fixtures | manual + scripts | dataset manifest committed; dry-run cost print; first episode fully seeded |
| **Gate G3:** hero op(s) hold quality bar across ≥3 fresh curated shots (not just spike set); Dub QC eval within thresholds; evidence video clips captured (raw, unedited). Stage 1 is now complete end-to-end. | | | |

## PHASE 3a — Stage 1a: generative fast-follow (A5, Sep 5–6; only after G3 passes)

Build order inside 1a: AL-1 → D-9 → D-10 → E-1 → D-11 → D-15 → D-16 → stretch.
Fallback order for slippage: cut D-16 → D-15 → stretch first; shipping without
1a is a complete, coherent product (Stage 1).

| Task | Op/Feature | Mode | DoD |
|---|---|---|---|
| AL-1 Alternates model + API | every generated clip = alternate `{shot_id, op, artifact_ref, eval_scores, status}`; add/remove-from-continuity = approval-tracked; FE alternates lane | TDD | alternate lifecycle unit tests; FE lane renders live alternates |
| D-9 Extend | Veo 3.1/Omni scene extension ≤40s (last-10s context, first/last-frame anchors); generated ambient beds feed S3 loudness QC | EDD | extend eval (continuity + flicker thresholds) PASS; JSONL archived |
| D-10 Corrections | Omni stateful conversational edit (element replacement, signage/text continuity fixes) routed via Approvals | EDD | corrections eval (edit-adherence rubric ≥4/5 + identity metric) PASS |
| E-1 Relight Studio | named lighting-setup presets (floor-lamp practical / ambient daylight / overhead ceiling / noir) via Omni edit; lighting-attribute rubric judge | EDD | relight eval PASS on 3 fresh shots or documented demote |
| D-11 Draft-first orchestration | 360p draft → QC → 1080p master; an un-QC'd draft never master-renders; Spend Control hooks | TDD+EDD | state machine tests; draft-vs-master cost delta recorded |
| D-12 Coverage | new-angle generation anchored by subject references; continuity metric (identity + flicker) | EDD | G0 probe gate → eval suite PASS or demote |
| D-15 Revision Room | script/caption alignment module (Gemini video understanding; alignment-accuracy metric) → user script edit → diff → affected spans → Omni replace/extend + dub pipeline for dialogue | EDD+TDD | alignment eval ≥ threshold on fixtures; one real script-edit → regenerated-span journey |
| D-16 Camera Language | preset vocabulary (dolly/tracking, dolly zoom, handheld/shaky, Steadicam, whip pan, crash zoom, SnorriCam, locked-off); Gemini genre-aware suggestions; reference-style transfer variant | EDD | camera-language rubric judge ≥ threshold; style transfer PASS or demote |
| D-13 Transition Forge (stretch) | first/last-frame interpolation between locked shots; loop variant | EDD | eval PASS or cut |
| D-14 Versioning (stretch) | 9:16 social cutdowns per delivery profile | EDD | eval PASS or cut |

**Gate G3a:** Stage 1a ops hold their eval bars; alternates lane live in FE;
Omni-vs-Veo model comparison recorded via ADR + JSONL. Fail ⇒ demote in the
order above; the G3 state remains the submission fallback.

## PHASE 4 — Supervisor intelligence (day 8–10)

| Task | Mode | DoD |
|---|---|---|
| H-1 Investigation chains: alert→PromQL→LogQL→Tempo correlation playbook prompts; severity rubric; proposal formatting | EDD (rubric judge) | AC-A.1 integration scenario green end-to-end |
| H-2 Morning report generator (Gemini summarization over real telemetry excerpts w/ citations to query results; cites Spend Control enforcement lines) | EDD | AC-A.2 faithfulness rubric ≥4/5 on 5 seeded scenarios |
| H-3 Approvals inbox FE + autonomy toggle enforcement (propose vs act); Spend Control escalations land in same inbox | TDD | toggle honored in agent middleware tests; S5b approval requests render and resolve |
| H-4 Dashboards-as-code finalized (Project Overview heatmap, Station Health, Cost/Spend Control, Evals, Self-Observability) + alert rules incl. spend threshold + runaway pattern | config | `infra/grafana/` provisions cleanly via API into fresh folder; screenshots archived |

## PHASE 5 — Stages 2 → 3 → 4 (day 10–13, strict stage order; within a stage, parallel where independent)

**Stage 1a first (A5):** Phase 3a above, only after G3 passes.
**Stage 2 — compressed to the story-carrying check (A5 calendar):**
I-1 Cue Sheet Auditor (S6, TDD) ONLY IF ahead of schedule on Sep 7. I-2..I-4
(Conform Sentinel, Accessibility, Handoff UI) move post-hackathon.
**Stages 3–4 (I-5…I-9): cut from hackathon scope; they remain in the spec for
post-event development.**

Rule unchanged: stages never borrow from Stage 1 polish; the G3 state (complete
Stage 1) is the guaranteed coherent fallback submission.

## PHASE 6 — Full-journey rehearsal, hardening, submission (day 12–15)

| Task | Mode | DoD |
|---|---|---|
| J-0 Batch demo readiness: full 8–10 episode × 3-language batch traverses the pipeline; Grafana Project Overview shows system-scale volume (heatmap density, cost curve, queue depth) — charts must look like a working system, not a 20-row list | integration | batch journey screenshots archived; per-language dub coverage report |
| J-1 Seed full journey: public-domain short traverses EVERY completed station; supervisor handles all seeded faults (announced list maintained in `fixtures/journey/README.md`) | integration | AC-A.1 style assertions per station; morning report compiles |
| J-2 Chaos pass: kill workers mid-run, revoke+refresh OAuth, network flap to OTLP; Spend Control keeps runaway retries bounded during chaos — product recovers without data loss | integration | recovery log evidence; no orphaned leases; spend stayed inside policy |
| J-3 Replit hosting swap rehearsal (identical build, CORS/base-URL change only) | deploy | both URLs live; rollback doc |
| J-4 README final: stranger-rerunnable quickstart (env, provision scripts, make targets, cost expectations), honest limitations section | docs | fresh-agent reproducibility walkthrough passes (C-1.6) |
| J-5 Record 3-min video FROM THE RUNNING PRODUCT (C-1.5), narration script lists announced fault injections; show batch-scale dashboard beat; captions EN | media | raw takes + final cut archived under `docs/evidence/video/` |
| J-6 Devpost submission form complete; repo About shows license; submit ≥24 h early | admin | confirmation email screenshot |

## Gate Summary

G0 spike verdict · G1 spine truth-check · G2 Stage 1 deterministic truth (incl.
Spend Control enforcing + captions-in-delivery) · G3 hero quality bar + Stage 1
complete (the guaranteed fallback submission) · G3a Stage 1a ops hold eval bars
+ alternates lane live · G4 full journey · G5 freeze (video from product only).
Failed gate ⇒ fix or demote lowest-priority unfinished work; NEVER substitute mocks
(C-1.*).

## Parallelization Map (agent workforce)

Max 3–4 concurrent agents: Phases 1 A∥B∥C; Phase 2 D-1..D-4+D-7 ∥ D-5..D-6 (two
agents) once A-4 lands; Phase 3 two-way (E-1∥E-2) + E-3 seeded early; Phase 5
stations within a stage parallel, stages sequential; Phase 6 sequential-ish
(J-0→J-1→J-2→J-5). Owner touchpoints required at: F-1/F-2, G0 verdict, G3
quality review, G5 recording session, J-6 submission.

## Budget Guardrails

Estimated spend caps: spike <$2 · evals total <$25 · batch demo TTS + journey
rehearsals <$40 · buffer $50. Spend Control (S5b) enforces these at runtime,
not just on dashboards; `pc_job_cost_micros` dashboard reviewed at each gate;
alert at 80% (C-7.1).

**A5 compute + spend (2026-08-28):** generative models run on **Vertex AI**
(owner GCP credits, $300 available; enabled APIs include Vertex AI), AI Studio
Gemini API as the per-model fallback where Vertex lags (G0 probe decides and
records model IDs). Gen-AI spend ceiling **$50–75** total; per-batch >$5 needs
`--yes` (C-7.2). Draft-tier (360p) renders preferred for all QC loops; masters
only after QC pass (D-11).

**Model & SDK pinning (ADR 0002, 2026-08-28):** ALL text-LLM reasoning runs on
`gemini-3.7-flash` with **thinking level HIGH** + thought summaries in the audit
trail — supervisor chains (H-1), morning report (H-2), camera suggestions,
script alignment, rubric judges. Video gen/edit: `gemini-omni-1.1-flash`
(Interactions API); precision extension: `veo-3.1` (Omni-vs-Veo per-op decided
by eval); dubs: Chirp 3 HD via Cloud TTS; video understanding: `gemini-3.7-flash`.
SDKs: `google-genai==2.20.0` (never 3.x until ADK-compatible), `google-adk==2.8.0`,
Python ≥ 3.12 (dev 3.13.7). Model IDs centralized in `backend/core/models.py`.
