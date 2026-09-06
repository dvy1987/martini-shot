# Feature Spec: Martini Shot (slug: `post-command`)
Date: 2026-08-26 | Amended: 2026-08-28 (owner rulings: 4-stage split, Spend Control station, batch demo, product display name **Martini Shot** — codename/slug unchanged; §7 amendment: SSE envelope, sign-in-to-approve auth, Replit mechanics; A5: Stage 1a generative fast-follow, demo batch 3 languages, Vertex AI compute) | **2026-09-06 (A10: agentic stations — every judgment surface gets a bespoke agent; dub time-fit decision, ADR-0004)** | Status: **Approved** | Constitution: `docs/constitution.md@1`
Mission context: `ideas/AO-STATION-MAP.md` (read first) · Catalog: `ideas/IDEAS.md`

---

## 1. Summary

Martini Shot is a real, production-quality web product: an operations cockpit where
a film/TV project travels through post-production as instrumented jobs. A
supervisor AI agent watches every station's telemetry through the **Grafana Cloud
MCP server**, catches failures, diagnoses root causes across metrics/logs/traces,
drives fixes (including generative picture/audio repairs via Google Gemini), and
leaves an auditable annotation trail in Grafana. Built for the Agentic Cinema
hackathon Grafana track (deadline 2026-09-09 14:00 PT) as if shipping to a paying
client — zero mocks anywhere (C-1.*).

**Scope model (2026-08-28 amendment):** stations are organized into **4 build
stages** by what they contribute to the product story, replacing the P0/P1/P2
priority stack. Stage 1 alone is a complete, sellable product: everything on the
direct path from "files arrive" to "files ship." Later stages finish compliance,
add audio/library depth, then the editing side.

**Agentic station layer (A10, 2026-09-06, owner-approved):** every station with a
judgment surface gains a bespoke agent that holds REAL judgment authority — the
deterministic verdict is advice the agent may override with a stated, logged reason
(`overridden: true`), and measurement-station agents own the RESPONSE to the
deterministic report (triage, remediation strategy, fixes, profile routing — fixes
re-validated by the deterministic rule engines they must satisfy). Measurements
themselves stay exact and machine-checkable; H-0 remains the only executor; every
agent is gated by its own EDD suite (≥0.8) against real billed model calls before it
ships. Roster + contract: `docs/specs/2026-09-06-agentic-stations-design.md`.

## 2. Users

| User | Needs |
|---|---|
| **Primary: Post Supervisor** | One screen showing project health across all stations; automatic incident detection with evidence; morning report; ability to approve/reject agent-proposed fixes |
| **Judge/Buyer** | Reproducible proof that everything shown is real; clear value story per station |
| **Demo operator (us)** | Scripted-but-genuine journey: a BATCH of files (8–10 episodes × ~30 languages for localization) traverses every station — charts must look like a working system, not a 20-row list |

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
│   │   ├── ingest/          # Stage 1 (TDD)
│   │   ├── pickups/         # Stage 1 HERO (EDD)
│   │   ├── loudness/        # Stage 1 (TDD)
│   │   ├── dub/             # Stage 1 (EDD)
│   │   ├── delivery/        # Stage 1 (TDD; includes caption-spec validation)
│   │   ├── spend/           # Stage 1 (TDD; Spend Control — acts, not just reports)
│   │   ├── cue_sheets/      # Stage 2 (TDD)
│   │   ├── conform/         # Stage 2 (TDD)
│   │   ├── accessibility/   # Stage 2 (TDD)
│   │   ├── handoff_ui/      # Stage 2 (TDD; surfaces spine-level handoff checks)
│   │   ├── restoration/     # Stage 3 (EDD stats + stretch)
│   │   ├── dialogue_doctor/ # Stage 3 (EDD)
│   │   ├── archive/         # Stage 3 (TDD)
│   │   ├── continuity/      # Stage 4 (EDD)
│   │   └── trailer_bench/   # Stage 4 (TDD)
│   └── evals/               # datasets/, metrics/, thresholds.yaml, runner
├── frontend/                # React+Vite (Firebase interim deploy)
├── fixtures/                # labeled synthetic INPUT media only (C-1.3)
├── infra/grafana/           # dashboards + alerts as code (C-4.5)
├── docs/                    # adr/, evidence/, runbooks
├── scripts/                 # spike, seed, provision, deploy
└── tests/                   # unit + integration harness
```

## 5. Scope & Build Stages (amended 2026-08-28)

**Stage 1 — sellable core (files arrive → files ship):**
Spine (jobs+OTel+MCP loop+UI); Handoff Validator (invisible, in-spine, no UI);
Ingest & Dailies; Virtual Pickups ★HERO; Loudness Marshal; Dub timing QC;
Caption specs (**as part of the delivery check, not its own screen**); Delivery
& Compliance pack; **Spend Control (NEW — acts, not just reports)**.

**Stage 1a — generative fast-follow (A5, owner ruling 2026-08-28; built only after Stage 1 gates pass):**
Omni-powered ops on the Pickups/Extend machinery: **Extend** (Veo 3.1/Omni scene
extension ≤40s, last-10s context); **Conversational Corrections** (Omni stateful
editing incl. signage/text continuity fixes, routed via Approvals); **Draft-first
rendering** (360p draft → QC → 1080p master — an un-QC'd draft never reaches a
paid master render); **Relight Studio** (named lighting-setup presets: floor-lamp
practical / ambient daylight / overhead ceiling / noir, with a lighting-attribute
rubric judge); **Coverage** (new-angle generation anchored by subject references);
**Revision Room** (script/caption alignment → user script edit → diff → affected
spans regenerated via Omni + the dub pipeline for dialogue); **Camera Language**
(preset vocabulary: dolly/tracking, dolly zoom, handheld/shaky, Steadicam, whip
pan, crash zoom, SnorriCam, locked-off — plus Gemini genre-aware suggestions and
reference-style transfer). In-1a stretch: **Transition Forge** (first/last-frame
interpolation), **Versioning** (9:16 cutdowns). Every generated clip lands as an
**alternate** attached to its shot — never silently overwriting a locked cut;
adding/removing from continuity is an approval-tracked action. All 1a ops are
EDD-gated and feasibility-probed at G0; **worst case the product ships complete
with Stage 1 alone.**

**Stage 2 — finish the compliance checks (nothing ships unless every box ticks):**
Cue Sheet Auditor; Conform Sentinel; Accessibility Auditor; Handoff Validator
with its own screen (spine checks surfaced).

**Stage 3 — audio depth and library work (long-running jobs, AI listening):**
Restoration; Dialogue Doctor; Archive Keeper.

**Stage 4 — the editing side (most AI vision, upstream, least urgent):**
Edit-Assist & Continuity; Trailer Bench.

All 15 original stations are accounted for, plus Spend Control (16 total).

### Station capability definitions & acceptance criteria (AC)

**S0 Spine** (Stage 1)
- Job model: `{job_id, station, project_id, input_refs[], status, attempts, cost_micros, error?}` in Firestore; lease-based async worker pool; retries idempotent (C-6.3).
- Every job emits C-4.2 telemetry; SSE `/api/v1/projects/{id}/events` streams state.
- **AC-S0.1** (TDD): queue test — N jobs submitted concurrently execute once each despite worker crash mid-job (lease expiry reassignment verified).
- **AC-S0.2** (integration): a job's trace visible in Grafana Tempo within 60 s of completion; its 3 metrics queryable in Mimir/PromQL.

**S0b Handoff Validator (invisible)** (Stage 1 silent → Stage 2 gets a screen)
- Runs inside the spine at every station transition; verifies turnover manifests (EDL/AAF refs, count sheets) against delivered files; discrepancies annotate + fail the gate. No UI in Stage 1.
- **AC-S0b.1** (TDD): manifest-missing-file fixture → transition blocked with reason code; complete manifest passes.
- **AC-S0b.2** (Stage 2): same checks rendered as a Handoff screen in FE.

**S1 Ingest & Dailies (TDD)** (Stage 1)
- Registers arrival of media files; computes checksums; probes via ffprobe (container/codec/duration/fps); detects corrupt/truncated files (probe failure or zero-byte tail); waveform-sync spot check flags missing audio stream.
- **AC-S1.1**: given fixture set incl. one corrupted MP4 (bit-flipped at 80% offset), station marks it `quarantined` with reason code; healthy files pass; results annotated in Grafana referencing job_id.
- **AC-S1.2**: ≥90% coverage on parser/checksum modules.

**S2 Virtual Pickups ★HERO (EDD)** (Stage 1)
- Ops: `background_swap` (prompt-driven), `outpaint_reframe` (target AR 9:16/1:1 from 16:9), `relight` (day→dusk; stretch). Pipeline per op: extract frames (configurable fps ≤12, clip ≤5 s) → per-frame Gemini image edit with anchor prompt + previous-frame conditioning → reassemble via ffmpeg → QC pass.
- QC: classical flicker/drift score (frame-to-frame histogram + optical-flow magnitude) computed per output clip; Gemini vision rubric judge (adherence/artifacts 1–5).
- Auto-retry: on flicker-score breach, strengthen anchors (reference keyframe injected) up to 2 retries before `needs_human`. Retry loops are capped and Spend Control watches them (see S5b).
- **AC-S2.1** (eval EDD): dataset = 10 curated clips (fixtures/, public-domain, locked/slow shots). Thresholds (`thresholds.yaml`): mean flicker score < 0.18 (normalized), vision judge ≥ 4.0 avg, artifact-rate (frames flagged) < 8%. Eval JSONL stored under `docs/evidence/`.
- **AC-S2.2** (TDD): frame extraction/reassembly round-trips duration±1 frame; cost estimator matches logged actuals ±20%.

**S3 Loudness Marshal (TDD)** (Stage 1)
- ffmpeg `ebur128` measurement; targets: streaming -16 LUFS ±1, broadcast -24 LKFS ±1 (per-delivery-spec configurable); true-peak ceiling -1 dBTP. Reports per-stem diagnosis (dialogue vs music vs FX hot) via stem separation heuristic (ffmpeg filters), plus M&E presence check.
- **AC-S3.1**: given fixtures calibrated near thresholds, measured LUFS matches ffmpeg reference within ±0.3 dB; verdict logic table-driven and unit-tested across boundary cases.

**S4 Dub Timing QC (EDD)** (Stage 1 — promoted from former P1; judge can LISTEN to output)
- Generate real dubs: Google Cloud TTS (SSML-paced) per language; measure duration delta vs original segment timings (≤ 45 ms tolerance target, threshold in yaml); sync-offset estimation via cross-correlation of energy envelopes; Gemini listens to flagged samples (audio input) for truncation/artifact classification.
- **AC-S4.1** (eval): dataset = 6 segments × 3 languages; duration-delta MAE recorded; truncation detection recall ≥ 90% on seeded truncated fixtures (labeled inputs).

**S5 Delivery & Compliance pack (TDD)** (Stage 1 — absorbs caption specs as a delegated check)
- Spec packs per destination (streaming/social/broadcast profiles in versioned YAML): container, codec, AR, fps range, bitrate ceilings, loudness ref (delegates S3), **caption spec validation (delegated sub-check: SRT/VTT/TTML parsing; reading speed ≤ 20 cps config; line length ≤ 42 chars; min duration 5/6 s; gap ≥ 2 frames; overlap detection; TTML profile basics)**. Produces pass/fail report with fix suggestions.
- **AC-S5.1**: table-driven tests: each spec pack against compliant + violating fixtures yields expected rule outcomes; unknown destination rejected.
- **AC-S5.2**: caption sub-check golden files over valid + 7 violation classes; exact rule IDs reported in the delivery report; failing caption check blocks shipment.

**S5b Spend Control (TDD — NEW)** (Stage 1)
- Tracks money spent per job / station / project from `cost_micros` already emitted by the spine (measurement work exists; this station ACTS on it).
- Policies (versioned YAML, per station): max spend per job; max retries before review; hourly + daily project budgets; runaway pattern detection (job re-running ≥ N times in window → suspect retry loop).
- Actions on breach: throttle (pause queue intake for station), stop (kill job family), or require approval (route to Approvals inbox). Every action → Grafana annotation + incident via MCP (the "acts, not just reports" differentiator; protects our own credits while agents build).
- **AC-S5b.1** (TDD): seeded runaway job (re-queues 40×) → throttled after N attempts per policy; annotation + incident created; approval required to resume.
- **AC-S5b.2** (TDD): daily budget breach → station intake paused; morning report cites the spend line.

**S6 Cue Sheet Auditor (TDD)** (Stage 2)
- Music cue sheets vs license windows: ledger matching + anomaly flags ("cue 7 used 12s past license"). **AC-S6.1**: seeded mismatch fixtures each yield distinct flags.

**S7 Conform Sentinel (TDD)** (Stage 2)
- Verify re-encoded master matches locked-cut manifest: frame counts, per-reel durations ±1 frame, audio channel maps, hash chain of source refs.
- **AC-S7.1**: manifest mismatch fixtures (off-by-one frames, swapped reel) each produce distinct diagnostic codes.

**S8 Accessibility Auditor (TDD)** (Stage 2)
- AD presence/placement checks; CC cue timing beyond delivery-spec format checks.
- **AC-S8.1**: fixtures missing AD track / with mistimed CC cues produce distinct rule failures.

**S9 Handoff Validator UI (TDD)** (Stage 2)
- Surface the S0b spine checks as a screen: manifest completeness per turnover, gate history, who/what unblocked each gate.
- **AC-S9.1**: FE renders live handoff gate state; a failing manifest shows blocking file names.

**S10 Restoration (EDD stats; generative clean-up stretch)** (Stage 3)
- Dirt/scratch/stability stats via classical CV on multi-day scan jobs; long-running journey framing (stall/anomaly detection, "minute 43 went wrong"). Runs as the canonical long-job monitoring example.
- **AC-S10.1** (eval): seeded defect fixtures detected ≥ 90% recall; long-job stall detection fires within one lease cycle of stall onset.

**S11 Dialogue Doctor (EDD)** (Stage 3)
- Gemini listens to dialogue stems; ranks clipped/noisy/off-mic lines; drafts ADR cue list.
- **AC-S11.1** (eval): seeded defect lines classified with ≥ 85% accuracy on labeled fixtures.

**S12 Archive Keeper (TDD)** (Stage 3)
- Checksum-drift sweeps + storage telemetry over the library; bitrot surfaced as Grafana series.
- **AC-S12.1**: seeded bitrot fixture → drift detected and annotated with file lineage.

**S13 Edit-Assist & Continuity (EDD)** (Stage 4)
- Diff-based visual continuity checks between adjacent scenes; severity/visibility triage.
- **AC-S13.1** (eval): planted continuity breaks detected above vision-judge threshold on curated pairs.

**S14 Trailer Bench (TDD)** (Stage 4)
- Trailer/promo spec regime as a spec-pack variant (runtime caps, card counts, rating cards).
- **AC-S14.1**: table-driven spec tests on compliant/violating trailer fixtures.

**Supervisor Agent (ADK + Grafana MCP)** (built with the spine, Stage 1)
- Tools bound: Grafana Cloud MCP (dashboard search, PromQL/LogQL/Tempo queries, annotations, incidents) + internal read APIs (job/project state).
- Behaviors: alert triage → investigation chain (metrics→logs→trace) → severity verdict → action proposal (retry/reroute/block) → human-approve toggle (env-configurable autonomy) → annotation + morning report generation (Gemini text summarization over telemetry excerpts).
- **AC-A.1** (integration): seeded corrupt-file scenario triggers alert; without human input agent produces investigation annotation containing correct job_id + root cause within 120 s (asserted in Grafana via query, not mocks).
- **AC-A.2** (eval): morning-report rubric judge ≥ 4/5 on 5 seeded scenarios (faithfulness: every claim traceable to a real telemetry query result).

## 6. Grafana Wiring Inventory (day 1, complete list — C-4.*)

1. OTel SDK in every Python service → OTLP traces/metrics/logs (Tempo/Mimir/Loki).
2. Metric contracts per job: `pc_job_duration_seconds{station}`, `pc_job_cost_micros{station}`, `pc_job_outcome_total{station,outcome}`, `pc_flicker_score`, `pc_loudness_lufs`, `pc_eval_score{suite}`.
3. Alert rules as code: job failure rate, quarantine events, flicker breach, loudness fail, spend threshold + runaway-job pattern (S5b), worker lease starvation.
4. Dashboards as code: Project Overview (timeline heatmap), Station Health, Cost/Spend Control, Evals, AI Observability (self).
5. Supervisor consumes MCP tools; every intervention writes annotation `{project_id, job_id, verdict}`; incidents for quarantine/spend-enforcement.
6. AI Observability SDK wraps ADK agent (traces, tokens, cost per LLM call).

## 7. Frontend Plan

- **Interim (build target now):** Firebase Hosting, React+Vite TS. Pages: Projects list; Project Timeline (stations × jobs grid, live via SSE); Job detail (spans link-out to Grafana, evidence thumbnails, before/after slider); Approvals inbox (also receives Spend Control escalations); Morning report view; Settings (autonomy toggle).
- **Final host swap (pre-submission):** identical build deployed to Replit static hosting; only base URL/CORS change. Swap rehearsed by G4. Replit URL is the submission URL; Firebase remains as documented fallback deployment (both real).
- Design bar: dark cinematic console (matches Diverge-grade product taste), no lorem ipsum, real data only.
- **Stage 1a UI surfaces (A5, built only after Stage 1 gates pass):** alternates lane in the Season Timeline (generated clips attach to their shot as alternates; continuity changes are approval actions); Revision Room (script panel aligned to shots; script edit → diff → affected spans → regeneration proposals); Camera Language suggestion chips (genre-aware, model-generated, labeled as such); Relight Studio preset row in the drawer; draft-first state badge on every generated artifact. All reuse the charter's existing components (lanes, drawer, folded evidence, wipes) — surfaces specified in `docs/design/DESIGN.md` "Stage 1a surfaces".

### 7.1 SSE event envelope (amendment 2026-08-28)

All events on `GET /api/v1/projects/{project_id}/events` share one envelope; clients MUST ignore unknown `type` values (forward compatibility). Server emits a `: ping` comment every 30s as keepalive.

```
data: {"type":"<type>","at":"<RFC3339 UTC>","payload":{ ... }}
```

Initial event set: `job.updated` (payload: `{job}`), `incident.opened` (payload: `{incident_id, job_id?, severity, title}`), `annotation.created` (payload: `{annotation_id, job_id?}`). Typed mirror: `frontend/src/types/api.ts` (`SseEvent` union).

### 7.2 Auth model: sign-in-to-approve (amendment 2026-08-28, owner ruling)

- **Reads** (projects, jobs, SSE, reports): no login; transport auth via `X-API-Key` header baked at build time (`VITE_API_KEY`). The key is extractable from a static bundle by a determined user — accepted demo trade-off; all enforcement stays server-side.
- **Deciding writes** (`POST /api/v1/approvals/{id}/decision`, `PATCH /api/v1/settings`): require Google sign-in. Frontend uses Firebase Auth (Google provider); on first decision the sign-in opens, then the request carries `Authorization: Bearer <ID token>`. Backend verifies via firebase-admin; missing/invalid → `401 {"error":{"code":"auth_required"}}`.
- Approver identity (uid + email) is stored on the approval record and included in the Grafana annotation (C-4.3) — the audit trail names the human.
- Replit Auth is NOT used (no server-side runtime on Replit static hosting). Frontend adds the Firebase JS SDK (covered by this ruling); backend adds firebase-admin under the owner's standing security/auth autonomy.

### 7.3 Replit hosting mechanics (amendment 2026-08-28)

- Replit static deployment serves `frontend/dist`; build command `cd frontend && npm ci && npm run build`.
- SPA rewrites: all non-asset paths → `/index.html` so `/approvals` and `/reports` deep-link.
- `VITE_API_BASE_URL`, `VITE_API_KEY` (and later `VITE_FIREBASE_*` web config — public by design) are BUILD-time env vars, baked per host; two hosts = two builds.
- `.replit` sits at repo root and points build/serve at `frontend/`. Deploy/undeploy actions remain owner-approved ("ask first" boundary).
- Track compliance: features built via Replit Agent (step prompts); deployed URL on replit.app is the submission URL, rehearsed at G4.

## 8. Non-Goals

Multi-tenant auth/RBAC (reads stay API-key-only; Google sign-in gates decision writes only — §7.2, 2026-08-28); mobile apps; non-Google model support; real client integrations (frame.io etc.); i18n of UI; SLA guarantees.

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
| Scope model | 4 build stages by product story (2026-08-28 owner ruling) | Stage 1 is self-sellable; compliance, depth, editing follow |
| Captions | Part of delivery check, not own screen | rule check, not a workflow |
| Spend Control | NEW station in Stage 1 (acts: throttle/stop/approve) | real action vs reporting; Diverge retry-loop pain; protects budget |
| Demo dataset | Batch: 8–10 episodes × ~30 languages | charts must look like a working system, not a list |
| FE auth | Public reads (API key); Google sign-in (Firebase) gates decision writes; approver identity in audit trail (§7.2) | owner ruling 2026-08-28 — accountability without demo friction |
| Agentic stations | Bespoke agent per judgment surface (8 + batch orchestrator); deterministic verdicts advisory with logged overrides; EDD gate ≥0.8 per agent (A10, 2026-09-06) | owner ruling — numeric proxies underfit quality; remediation/strategy is reasoned work (design doc after adversarial self-review) |
| Dub time-fit | ONE TTS render + deterministic ffmpeg atempo stretch to the source window (ADR-0004) | Chirp 3 HD rate response measured nonlinear (0.8 → 1.34×) — re-render fitting cannot hit the 45 ms bar; atempo is exact, free, pitch-preserving |

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Generative flicker fails quality bar even on curated clips | G0 spike FIRST (before any other build — 2026-08-28 ruling re-affirmed); demote path pre-agreed: op ships as detect+report (still real) while another Stage station promotes |
| Hosted MCP OAuth unusable headless | OSS mcp-grafana + service account env-flag fallback, proven by G1 |
| Firestore lease edge cases | property-based tests + chaos kill-test in AC-S0.1 |
| Spend overrun | Spend Control station (S5b) + micro-unit accounting + daily budget metric+alert + eval dry-run cost print (C-7.*) |
| Timeline compression | agent-workforce parallelism per plan; gates G0–G5 enforce integration truth |

## 11. Open Questions

None — owner rulings resolved prior CLs (latest: 2026-08-28 staging amendment). Changes require spec amendment + owner approval.
