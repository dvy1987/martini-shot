# Feature Spec: Post Command (slug: `post-command`)
Date: 2026-08-26 | Status: **Approved** (owner rulings 2026-08-26) | Constitution: `docs/constitution.md@1`
Mission context: `ideas/AO-STATION-MAP.md` (read first) · Catalog: `ideas/IDEAS.md`

---

## 1. Summary

Post Command is a real, production-quality web product: an operations cockpit where
a film/TV project travels through post-production as instrumented jobs. A
supervisor AI agent watches every station's telemetry through the **Grafana Cloud
MCP server**, catches failures, diagnoses root causes across metrics/logs/traces,
drives fixes (including generative picture/audio repairs via Google Gemini), and
leaves an auditable annotation trail in Grafana. Built for the Agentic Cinema
hackathon Grafana track (deadline 2026-09-09 14:00 PT) as if shipping to a paying
client — zero mocks anywhere (C-1.*).

## 2. Users

| User | Needs |
|---|---|
| **Primary: Post Supervisor** | One screen showing project health across all stations; automatic incident detection with evidence; morning report; ability to approve/reject agent-proposed fixes |
| **Judge/Buyer** | Reproducible proof that everything shown is real; clear value story per station |
| **Demo operator (us)** | Scripted-but-genuine journey: one real short film traverses every station |

## 3. Platform & Deployment Topology (C-6.1)

```
┌─────────────────────┐         ┌──────────────────────────────────┐
│ Frontend            │  HTTPS  │ Backend (Cloud Run, container)   │
│ Interim: Firebase   │───────▶ │ FastAPI + ADK supervisor +       │
│ Final: Replit       │  /api/* │ workers + station services       │
│ (React+Vite build)  │ ◀──SSE── │                                  │
└─────────────────────┘         └────┬─────────────┬───────────────┘
                                     │             │
                    ┌────────────────▼───┐   ┌─────▼──────────────┐
                    │ Google Cloud       │   │ Grafana Cloud      │
                    │ GCS (media)        │   │ MCP server (agent) │
                    │ Firestore (state)  │   │ OTLP (telemetry in)│
                    │ Secret Manager     │   │ AI Observability   │
                    └────────────────────┘   └────────────────────┘
Generative calls: Gemini image editing (Nano Banana-class), Gemini text/vision,
Google Cloud TTS. All real, all billed (C-1.1).
```

## 4. Repository Layout

```
post-command/
├── backend/
│   ├── api/                 # FastAPI app (/api/v1), auth, SSE
│   ├── core/                # config, logging, otel init, gcp clients
│   ├── jobs/                # queue, lease worker pool, runner (TDD)
│   ├── supervisor/          # ADK agent + Grafana MCP toolset (EDD on decisions)
│   ├── stations/
│   │   ├── ingest/          # P0 (TDD)
│   │   ├── loudness/        # P0 (TDD)
│   │   ├── captions/        # P0 (TDD)
│   │   ├── delivery/        # P0 (TDD)
│   │   ├── pickups/         # P0 HERO (EDD)
│   │   ├── dub/             # P1 (EDD)
│   │   ├── consent/         # P1 (TDD policy engine + EDD region check)
│   │   ├── conform/         # P1 (TDD)
│   │   └── <p2>/            # cue_sheets, dialogue_doctor, trailer_bench,
│   │                        # archive, accessibility, restoration, continuity,
│   │                        # handoff_ui — built strictly in listed order
│   └── evals/               # datasets/, metrics/, thresholds.yaml, runner
├── frontend/                # React+Vite (Firebase interim deploy)
├── fixtures/                # labeled synthetic INPUT media only (C-1.3)
├── infra/grafana/           # dashboards + alerts as code (C-4.5)
├── docs/                    # adr/, evidence/, runbooks
├── scripts/                 # spike, seed, provision, deploy
└── tests/                   # unit + integration harness
```

## 5. Scope & Priority Stack (locked 2026-08-26)

**P0 — sellable core:** Spine (jobs+OTel+MCP loop+UI); Ingest & Dailies;
Virtual Pickups ★HERO; Loudness Marshal; Caption specs; Delivery specs.
**P1 — depth:** Dub timing QC; Consent guard ledger; Conform Sentinel.
**P2 — richness until deadline (in order):** Cue Sheet Auditor; Dialogue Doctor;
Trailer Bench; Archive Keeper; Accessibility Auditor; Restoration; Edit-Assist
continuity; Handoff Validator UI.

### Station capability definitions & acceptance criteria (AC)

**S0 Spine**
- Job model: `{job_id, station, project_id, input_refs[], status, attempts, cost_micros, error?}` in Firestore; lease-based async worker pool; retries idempotent (C-6.3).
- Every job emits C-4.2 telemetry; SSE `/api/v1/projects/{id}/events` streams state.
- **AC-S0.1** (TDD): queue test — N jobs submitted concurrently execute once each despite worker crash mid-job (lease expiry reassignment verified).
- **AC-S0.2** (integration): a job's trace visible in Grafana Tempo within 60 s of completion; its 3 metrics queryable in Mimir/PromQL.

**S1 Ingest & Dailies (TDD)**
- Registers arrival of media files; computes checksums; probes via ffprobe (container/codec/duration/fps); detects corrupt/truncated files (probe failure or zero-byte tail); waveform-sync spot check flags missing audio stream.
- **AC-S1.1**: given fixture set incl. one corrupted MP4 (bit-flipped at 80% offset), station marks it `quarantined` with reason code; healthy files pass; results annotated in Grafana referencing job_id.
- **AC-S1.2**: ≥90% coverage on parser/checksum modules.

**S2 Virtual Pickups ★HERO (EDD)**
- Ops: `background_swap` (prompt-driven), `outpaint_reframe` (target AR 9:16/1:1 from 16:9), `relight` (day→dusk; stretch). Pipeline per op: extract frames (configurable fps ≤12, clip ≤5 s) → per-frame Gemini image edit with anchor prompt + previous-frame conditioning → reassemble via ffmpeg → QC pass.
- QC: classical flicker/drift score (frame-to-frame histogram + optical-flow magnitude) computed per output clip; Gemini vision rubric judge (adherence/artifacts 1–5).
- Consent guard hook (see S7): face-region detection (OpenCV/classical) gates ops; performance regions are refused, logged to ledger.
- Auto-retry: on flicker-score breach, strengthen anchors (reference keyframe injected) up to 2 retries before `needs_human`.
- **AC-S2.1** (eval EDD): dataset = 10 curated clips (fixtures/, public-domain, locked/slow shots). Thresholds (`thresholds.yaml`): mean flicker score < 0.18 (normalized), vision judge ≥ 4.0 avg, artifact-rate (frames flagged) < 8%. Eval JSONL stored under `docs/evidence/`.
- **AC-S2.2** (TDD): frame extraction/reassembly round-trips duration±1 frame; cost estimator matches logged actuals ±20%.

**S3 Loudness Marshal (TDD)**
- ffmpeg `ebur128` measurement; targets: streaming -16 LUFS ±1, broadcast -24 LKFS ±1 (per-delivery-spec configurable); true-peak ceiling -1 dBTP. Reports per-stem diagnosis (dialogue vs music vs FX hot) via stem separation heuristic (ffmpeg filters), plus M&E presence check.
- **AC-S3.1**: given fixtures calibrated near thresholds, measured LUFS matches ffmpeg reference within ±0.3 dB; verdict logic table-driven and unit-tested across boundary cases.

**S4 Caption Specs (TDD)**
- Parse SRT/VTT/TTML; validate: reading speed ≤ 20 cps (config), line length ≤ 42 chars, min duration 5/6 s, gap ≥ 2 frames, overlap detection, TTML profile conformance basics.
- **AC-S4.1**: golden-file tests over valid + 7 violation classes of fixtures; exact rule IDs reported; blocking verdict wired to delivery.

**S5 Delivery Specs (TDD)**
- Spec packs per destination (streaming/social/broadcast profiles in versioned YAML): container, codec, AR, fps range, bitrate ceilings, loudness ref (delegates S3), caption presence (delegates S4). Produces pass/fail report with fix suggestions.
- **AC-S5.1**: table-driven tests: each spec pack against compliant + violating fixtures yields expected rule outcomes; unknown destination rejected.

**S6 Dub Timing QC (EDD, P1)**
- Generate real dubs: Google Cloud TTS (SSML-paced) per language; measure duration delta vs original segment timings (≤ 45 ms tolerance target, threshold in yaml); sync-offset estimation via cross-correlation of energy envelopes; Gemini listens to flagged samples (audio input) for truncation/artifact classification.
- **AC-S6.1** (eval): dataset = 6 segments × 3 languages; duration-delta MAE recorded; truncation detection recall ≥ 90% on seeded truncated fixtures (labeled inputs).

**S7 Consent Guard (P1: TDD engine + EDD region classifier)**
- Policy engine: operation scopes (technique-only whitelist); face-region map from detector; ledger append-only (Firestore) `{job_id, op, regions_touched, decision}`; violations block + IRM incident via MCP.
- **AC-S7.1**: unit tests: relight touching detected face region → blocked + ledger row + incident created (incident creation asserted via recorded MCP call result, not mock).

**S8 Conform Sentinel (TDD, P1)**
- Verify re-encoded master matches locked-cut manifest: frame counts, per-reel durations ±1 frame, audio channel maps, hash chain of source refs.
- **AC-S8.1**: manifest mismatch fixtures (off-by-one frames, swapped reel) each produce distinct diagnostic codes.

**S9–S15 (P2, same pattern)**: Cue Sheet Auditor (ledger-vs-license windows, TDD);
Dialogue Doctor (Gemini listen-classify clipped/noisy/off-mic lines, EDD eval on
seeded defects); Trailer Bench (spec pack variant, TDD); Archive Keeper
(checksum drift sweep, TDD); Accessibility Auditor (AD presence/cue timing, TDD);
Restoration (dirt/scratch/stability stats via classical CV + generative clean-up
stretch, EDD); Edit-Assist continuity (diff-based visual checks, EDD).

**Supervisor Agent (ADK + Grafana MCP)**
- Tools bound: Grafana Cloud MCP (dashboard search, PromQL/LogQL/Tempo queries, annotations, incidents) + internal read APIs (job/project state).
- Behaviors: alert triage → investigation chain (metrics→logs→trace) → severity verdict → action proposal (retry/reroute/block) → human-approve toggle (env-configurable autonomy) → annotation + morning report generation (Gemini text summarization over telemetry excerpts).
- **AC-A.1** (integration): seeded corrupt-file scenario triggers alert; without human input agent produces investigation annotation containing correct job_id + root cause within 120 s (asserted in Grafana via query, not mocks).
- **AC-A.2** (eval): morning-report rubric judge ≥ 4/5 on 5 seeded scenarios (faithfulness: every claim traceable to a real telemetry query result).

## 6. Grafana Wiring Inventory (day 1, complete list — C-4.*)

1. OTel SDK in every Python service → OTLP traces/metrics/logs (Tempo/Mimir/Loki).
2. Metric contracts per job: `pc_job_duration_seconds{station}`, `pc_job_cost_micros{station}`, `pc_job_outcome_total{station,outcome}`, `pc_flicker_score`, `pc_loudness_lufs`, `pc_eval_score{suite}`.
3. Alert rules as code: job failure rate, quarantine events, flicker breach, loudness fail, spend 80% (C-7.1), worker lease starvation.
4. Dashboards as code: Project Overview (timeline heatmap), Station Health, Cost, Evals, AI Observability (self).
5. Supervisor consumes MCP tools; every intervention writes annotation `{project_id, job_id, verdict}`; incidents for consent/quarantine/spend.
6. AI Observability SDK wraps ADK agent (traces, tokens, cost per LLM call).

## 7. Frontend Plan

- **Interim (build target now):** Firebase Hosting, React+Vite TS. Pages: Projects list; Project Timeline (stations × jobs grid, live via SSE); Job detail (spans link-out to Grafana, evidence thumbnails, before/after slider); Approvals inbox; Morning report view; Settings (autonomy toggle).
- **Final host swap (pre-submission):** identical build deployed to Replit static hosting; only base URL/CORS change. Swap rehearsed by G4. Replit URL is the submission URL; Firebase remains as documented fallback deployment (both real).
- Design bar: dark cinematic console (matches Diverge-grade product taste), no lorem ipsum, real data only.

## 8. Non-Goals

Multi-tenant auth/RBAC beyond single-team API-key; mobile apps; non-Google model support; real client integrations (frame.io etc.); i18n of UI; SLA guarantees.

## 9. Key Decisions (ADRs will mirror)

| Decision | Choice | Why |
|---|---|---|
| Language/backend | Python 3.12, FastAPI | ADK/OTel/ffmpeg ecosystem fit |
| Queue/store | Firestore leases (no Redis/Kafka) | fewer moving parts; free tier; C-6.2 |
| Media store | GCS | required realism; signed URLs to FE |
| Agent framework | Google ADK + hosted Grafana MCP (fallback OSS server + service-account token behind env flag) | track requirement + headless reliability |
| Frame pipeline | OpenCV/ffmpeg classical + Gemini edits | flicker control + honest hybrid |
| Testing split | TDD deterministic / EDD generative | owner mandate |
| Hosting | Backend Cloud Run; FE Firebase→Replit | owner mandate |

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Generative flicker fails quality bar even on curated clips | G0 spike FIRST; demote path pre-agreed: op ships as detect+report (still real) while another P2 station promotes |
| Hosted MCP OAuth unusable headless | OSS mcp-grafana + service account env-flag fallback, proven by G1 |
| Firestore lease edge cases | property-based tests + chaos kill-test in AC-S0.1 |
| Spend overrun | micro-unit accounting, daily budget metric+alert, eval dry-run cost print (C-7.*) |
| Timeline compression | agent-workforce parallelism per plan; gates G0–G5 enforce integration truth |

## 11. Open Questions

None — owner rulings resolved prior CLs. Changes require spec amendment + owner approval.
