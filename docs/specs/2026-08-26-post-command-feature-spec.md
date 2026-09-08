# Feature Spec: Martini Shot (slug: `post-command`)
Date: 2026-08-26 | Amended: 2026-08-28, 2026-09-06, 2026-09-07, 2026-09-08 | Status: **Approved with current implementation addendum** | Constitution: `docs/constitution.md@1`

**Current implementation addendum, 2026-09-08:** This specification contains historical planning sections that predate the current Cloud Run, Google Identity Services, eleven-station dispatcher, and walk-away finishing implementation. The current runtime authority is `README.md`, `docs/judge-guide.md`, `docs/pending-work.md`, `docs/memory/current-state.md`, and the production files linked from those documents. Historical plans remain useful for provenance but must not override current code.
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
| **Demo operator (us)** | Scripted-but-genuine journey: two or three ordered clips traverse the current walk-away path; a larger batch is optional evidence, not the primary claim |

## 3. Platform & Deployment Topology (C-6.1)

The current implementation uses a Vite/React frontend and a FastAPI backend. The supported production backend target is Google Cloud Run. The frontend can run in the Replit development workflow or be built as `frontend/dist` for a compatible static or combined host.

```
┌─────────────────────┐       HTTPS / SSE       ┌──────────────────────────────┐
│ React + Vite        │ ─────────────────────▶  │ FastAPI on Cloud Run         │
│ Timeline + worklist │ ◀─────────────────────  │ ADK + workers + stations     │
└─────────────────────┘                        └───────┬──────────┬───────────┘
                                                        │          │
                                          ┌─────────────▼───┐  ┌────▼──────────────┐
                                          │ Google Cloud     │  │ Grafana MCP       │
                                          │ Firestore + GCS  │  │ hosted or OSS     │
                                          │ Gemini + ADK     │  │ OTLP + dashboards │
                                          └──────────────────┘  └───────────────────┘
```

Generative calls use Google Gemini or Vertex-backed services, Google ADK, Google Cloud TTS where required, and real media tooling. Grafana is reached through MCP, not raw HTTP wrappers.

## 4. Repository Layout

```
martini-shot/
├── backend/api/             # FastAPI app, finish/worklist/SSE/approval routes
├── backend/core/            # config, logging, OpenTelemetry, GCP clients
├── backend/jobs/            # Firestore lease queue, worker, handoff guard
├── backend/stations/        # Eleven explicit worker station implementations
├── backend/supervisor/      # ADK finishing, Post Supervisor, Grafana MCP, Run Pulse
├── frontend/                # React + Vite Timeline, worklist, alternates, approvals
├── infra/grafana/           # Dashboards and alert rules as code
├── scripts/                 # Evaluations, provisioning, seeding, deployment helpers
├── docs/evidence/           # Real model/evaluation/integration evidence
├── docs/runbooks/           # Local development and deployment runbooks
└── tests/                   # Unit, integration, and contract tests
```

The current worker roster is defined in `backend/stations/run.py`. Historical planning documents may describe future or stretch stations that are not current worker branches.

## 5. Scope & Build Stages (amended 2026-08-28)

**Stage 1 — sellable core (files arrive → files ship):**
Spine (jobs+OTel+MCP loop+UI); Handoff Validator (invisible, in-spine, no UI);
Ingest & Dailies; Virtual Pickups ★HERO; Loudness Marshal; Dub timing QC;
Caption specs (**as part of the delivery check, not its own screen**); Delivery
& Compliance pack; **Spend Control (NEW — acts, not just reports)**.

**Stage 1a — full demo scope (A11, owner ruling 2026-09-07):**
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
interpolation), **Versioning** (9:16 cutdowns). Every generated clip lands as an **alternate** attached to its shot — never silently overwriting a locked cut; adding/removing from continuity is an approval-tracked action. The currently wired Stage 1a paths are exposed through the frontend controls and worker dispatcher described in `README.md` and `docs/judge-guide.md`. Each path uses the approval, queue, alternate, QC, cost, and evidence controls that are present in code. Do not treat a historical roadmap row as a production capability unless it has a current dispatcher branch, frontend path, and evidence artifact.
D-13 Transition Forge and D-14 Versioning remain stretch only.

**Walk-away finishing (owner ruling 2026-09-07; sequence 2026-09-08):** the operator uploads clips **in order**, sets a finishing budget (this build: **$50**), and walks away. Demo beats: `ideas/AO-STATION-MAP.md` §7 + A6. **Locked sequence:** ingest **job** = file check only (corrupt file stops) → ingest **agent** watches the original and writes `spoken_words` + `scene` (silence is valid) → **loudness agent + job always runs** (listens, mixes; continuing shots stay in family) → **pickups agent + job always runs** on that mixed clip (repairs real damage) → wait until **every** clip has finished mix + pickups → leftover station agents (extend, corrections, relight, coverage, camera language, dub, delivery) watch the **updated** clips in upload order, with the ingest bag, and suggest must / nice / leave → **Spend** prices **each** leftover job → a **billed Gemini orchestrator** ranks by impact, names dependencies (what must wait on what vs what can run together), reads ingest/handoff spine notes, and keeps what still fits. Mix and pickups are not optional looks and cannot be skipped or reordered by the orchestrator. Code may not invent stations or run empty rows; a band-sort comparator is crash-fallback only. Ranked leftover work is **auto-enqueued** until the envelope is gone. If money dies mid-job, that work **pauses**; the playable final is **originals plus only `passed` jobs**. Originals are never overwritten. Unwired leftover stations show **empty** (not “all good”). Inspect, spend pricing, and rank are EDD-gated (≥0.8, 3 live runs).

**Stage 2 — finish the compliance checks (nothing ships unless every box ticks):**
Cue Sheet Auditor; Conform Sentinel; Accessibility Auditor; Handoff Validator
with its own screen (spine checks surfaced).

**Stage 3 — audio depth and library work (long-running jobs, AI listening):**
Restoration; Dialogue Doctor; Archive Keeper.

**Stage 4 — the editing side (most AI vision, upstream, least urgent):**
Edit-Assist & Continuity; Trailer Bench.

The current production dispatcher recognizes eleven worker stations: ingest, loudness, delivery, spend, pickups, dub, extend, corrections, relight, coverage, and camera_language. Additional names in historical roadmaps are not current worker branches and must not be presented as production stations.

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

**Supervisor and Finishing Agents (Google ADK + Grafana MCP)** (Stage 1 and Stage 1a)
- The walk-away finishing path creates one ADK specialist per proposal station, then invokes a billed ADK finishing orchestrator over the complete note bag. The orchestrator returns a validated order, dependencies, dropped work, and reason. `backend/supervisor/finishing_loop.py` owns queue dispatch and budget enforcement.
- The Post Supervisor path uses real specialist investigators, a Verification Agent, a Gemini synthesis call, the approval state machine, and Grafana MCP query/write tools. It currently fires for failed, quarantined, and needs-human terminal states. Additional signal types remain deferred and are recorded in `docs/pending-work.md`.
- Grafana MCP tools include dashboard search, PromQL, LogQL, Tempo trace search, annotations, and incidents. Writes respect `propose_only` and the current autonomy mode.
- **Current evidence:** live finishing-rank runs of 0.9 / 0.9 / 0.8, spend-pricing runs of 1.0 / 1.0 / 1.0, and supervisor retry-once runs of 1.0 / 1.0 / 1.0. The known `fr-05` ordering miss and below-target full-gate coverage remain disclosed in `docs/pending-work.md`.

## 6. Grafana Wiring Inventory (day 1, complete list — C-4.*)

1. OTel SDK in every Python service → OTLP traces/metrics/logs (Tempo/Mimir/Loki).
2. Metric contracts per job: `pc_job_duration_seconds{station}`, `pc_job_cost_micros{station}`, `pc_job_outcome_total{station,outcome}`, `pc_flicker_score`, `pc_loudness_lufs`, `pc_eval_score{suite}`.
3. Alert rules as code: job failure rate, quarantine events, flicker breach, loudness fail, spend threshold + runaway-job pattern (S5b), worker lease starvation.
4. Dashboards as code: Project Overview (timeline heatmap), Station Health, Cost/Spend Control, Evals, AI Observability (self).
5. Supervisor consumes MCP tools; every intervention writes annotation `{project_id, job_id, verdict}`; incidents for quarantine/spend-enforcement.
6. AI Observability SDK wraps ADK agent (traces, tokens, cost per LLM call).

## 7. Frontend Plan and Current Surface

The current frontend is a React + Vite application with a Timeline route, FinishBar upload and budget control, WorklistPanel, Run Pulse, AlternatesLane, manual Stage 1a controls, approvals, reports, and Google Identity Services for owner-only settings writes. The current Replit workflow runs `npm run dev -- --host 0.0.0.0 --port 5000`. The repository deployment target is Cloud Run; the backend deployment script is `deploy.sh`.

The frontend uses `VITE_API_BASE_URL` and `VITE_API_KEY` at build time. Backend API routes require `X-API-Key`; the health endpoint is open. Settings writes use a Google ID token verified against the configured owner email. The current browser implementation uses the Google Identity Services script directly rather than a Firebase SDK.

Stage 1a surfaces include the Alternates lane, Extend, Corrections, Relight, Coverage, Camera Language, Revision Room, draft-first badges, approvals, and Run Pulse. The current frontend does not present a single polished assembled-final player as the primary path; it exposes individual alternates and the backend final-reference list. Demo language should show the final references and a real artifact without claiming a dedicated final-cut player that is not present.

Design bar: dark cinematic console, no placeholder production claims, and honest empty/unreachable states.

### 7.1 SSE event envelope (amendment 2026-08-28)

All events on `GET /api/v1/projects/{project_id}/events` share one envelope; clients MUST ignore unknown `type` values (forward compatibility). Server emits a `: ping` comment every 30s as keepalive.

```
data: {"type":"<type>","at":"<RFC3339 UTC>","payload":{ ... }}
```

Initial event set: `job.updated` (payload: `{job}`), `incident.opened` (payload: `{incident_id, job_id?, severity, title}`), `annotation.created` (payload: `{annotation_id, job_id?}`). Typed mirror: `frontend/src/types/api.ts` (`SseEvent` union).

### 7.2 Auth model: API-key reads and Google Identity Services owner writes

- **Reads** and browser event streams require the configured `X-API-Key`; `/api/v1/health` is the only open route.
- **Settings writes** require a Google ID token and an owner email allowlist. The frontend obtains the token through the Google Identity Services browser script and sends it as `Authorization: Bearer <ID token>`.
- If the Google client id or owner email is not configured, the sign-in control reports an honest unavailable state and the write gate remains closed.
- The current code does not use Firebase Auth for this path. Documentation claiming Firebase SDK authentication is historical and has been corrected here.

### 7.3 Current hosting mechanics

- Local or Replit development runs the Vite app with `npm run dev -- --host 0.0.0.0 --port 5000`.
- A static frontend build is produced with `cd frontend && npm ci && npm run build` and written to `frontend/dist`.
- `VITE_API_BASE_URL` and `VITE_API_KEY` are build-time variables. A rebuild is required after changing them.
- `deploy.sh` deploys the backend container to Cloud Run, installs the Linux OSS Grafana MCP binary, and prints the public URL and health endpoint.
- The hosted submission must be the actual running web project. A local development preview is only a rehearsal surface.

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
| Hosting | Backend Cloud Run; frontend Vite development or compatible hosted build | current repository configuration |
| Scope model | 4 build stages by product story (2026-08-28 owner ruling) | Stage 1 is self-sellable; compliance, depth, editing follow |
| Captions | Part of delivery check, not own screen | rule check, not a workflow |
| Spend Control | NEW station in Stage 1 (acts: throttle/stop/approve) | real action vs reporting; Diverge retry-loop pain; protects budget |
| Demo dataset | Two or three ordered clips for the walk-away story; larger batches remain optional evidence | the primary demo must show the running product clearly |
| FE auth | Public health only; API-key reads; Google Identity Services owner token gates settings writes | current frontend and backend implementation |
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
