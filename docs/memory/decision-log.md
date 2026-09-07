# Decision Log

## 2026-09-07 - Full Stage 1a is required for the hackathon demo (Amendment A11)
Status: active
Scope: demo release
Confidence: high
Tags: stage-1a, demo, scope, edd, ux

### Decision
The demo release comprises Stage 1 **and the full non-stretch Stage 1a
roadmap**: D-10 Corrections, E-1 Relight Studio, D-11 Draft-first
orchestration, D-12 Coverage, D-15 Revision Room, and D-16 Camera Language.
The former requirement that full Stage 1a await G3 is removed for these tasks;
G3 and G3a become integrated release gates. The demo must support both a
hero-shot creative journey and an episode-level revision journey.

### Constraints
- Features remain separate domain pipelines; they reuse shared H-0, AL-1,
  lease-queue, real GCS/Firestore, `run_agent_call`, Grafana MCP/OTel, and
  frontend HTTP/SSE primitives rather than duplicating them.
- Every generative capability is EDD-first with real Gemini/Vertex calls,
  numeric thresholds, prompt-hardening iterations, and archived three-run
  evidence. Every feature must be exposed in the running UX.
- Remaining Stage 1a eval/demo spend is capped at $50. Batches over $5 still
  print their estimate and require `--yes` (C-7.2); exceeding $50 requires a
  new owner approval.
- D-13 Transition Forge and D-14 Versioning remain stretch; Stage 2+ does not
  enter the demo scope.

### Revisit trigger
If the remaining $50 envelope is exhausted before integrated G3/G3a, the
owner decides whether to expand the envelope or reduce scope by explicit
amendment; no feature is silently downgraded to an eval-only claim.

## 2026-09-04 - Omni-vs-Veo: Omni on Vertex WORKS — becomes primary video path (owner request)
Status: active (supersedes the same-day "blocked on credentials" entry below)
Scope: D-9 Extend, dub/render features, ADR 0002 model pinning
Confidence: high (live renders + deterministic flicker comparison vs archived G0 Veo outputs)

### Finding
1. Omni 1.1 Flash is callable on **Vertex** via the Agent Platform interactions
   endpoint (`aiplatform.googleapis.com/v1beta1/.../interactions`, project
   IAM identity — no Gemini API key needed). Model: `gemini-omni-1.1-flash-preview`
   (the GA ID is not served for interactions on Vertex).
2. The required request shape (what G0 and the first probe missed):
   media by gs:// URI + `generation_config.video_config.task` (REQUIRED) +
   **no `response_format` for extend/edit** — `aspect_ratio` there is
   explicitly rejected for these tasks and poisoned every earlier attempt.
3. Live results (same shots/prompts as G0's Veo renders):
   - bg-swap edit: completed, flicker 0.00131 vs Veo 0.00992 (Omni 7.5x cleaner; gate < 0.02)
   - scene extend: completed, input doubled (240→480 frames = real extension),
     flicker 0.00322 = 0.70x source vs Veo 0.69x — equivalent class
4. Watch items: Vertex serves the -preview ID (GA migration pending — re-pin
   when it lands); extend is append-only 3-10s per call, 10s context; extend
   prompts must stay simple (docs' guidance; elaborate prompts were refused);
   preview pricing to be read from billing at the next spend review.

### Decision
- Primary video path: **Omni via Vertex Agent Platform interactions**
  (`backend/core/models.py` OMNI_MODEL; Veo 3.1 Fast stays pinned as fallback).
- ALL Gemini text calls stay on the same Vertex endpoint family
  (`generate_content`) — the interactions surface does not serve
  `gemini-3.7-flash` (G0 routing probe: 400 "Unsupported model interaction"),
  so "Agent Platform for everything" today means one platform, two surfaces.
- D-9 Extend and render features build against Omni first; Veo fallback is
  retained as the eval comparison arm per A5.

## 2026-09-04 - Omni-vs-Veo check before Veo-feature build (owner request)
Status: recommendation delivered, blocked on owner credential decision
Scope: D-9 Extend, dub/render features, ADR 0002 model pinning
Confidence: high (live probe + official docs, 2026-09-04)

### Finding
1. Omni 1.1 Flash went GA 2026-08-27 as `gemini-omni-1.1-flash` (the `-preview`
   ID in models.py deprecates 2026-09-30). GA capabilities cover everything the
   video features need: conversational editing, append-style extension (3-10s,
   10s context, up to 40s), first/last-frame interpolation, subject references,
   360p→4K resolution tiers. Pricing ~$0.10/s at 720p, ~1/3 at 360p draft.
2. BUT the GA model's documented and only-supported video surface is the
   **Gemini API** (API key). The project has NO Gemini API key (.env
   GEMINI_API_KEY is empty).
3. On Vertex (our primary runtime, owner credits): interactions serves ONLY the
   `-preview` ID (GA ID → "Unsupported model interaction"); the preview ID
   completes text but rejects every video-input shape (400 invalid argument,
   404 with response_format) — both in G0 (2026-08-29) and in today's probe.
4. Veo 3.1 Fast (`veo-3.1-fast-generate-001`) remains the ONLY working video
   path on current credentials (proven at G0 with gate-passing renders).

### Recommendation
Yes, Omni can replace Veo — unlock it by adding a billed Gemini API key
(AI Studio, paid tier). That is a provisioning step needing owner action.
Until then, Veo stays the render path; no Veo features blocked: D-9 Extend
builds against the media-gateway abstraction, model choice is an eval decision
per A5, and Omni-vs-Veo A/B on the same prompts/shots is already staged
(scripts/omni_probe.py vs archived G0 Veo outputs, flicker-gated).

### Revisit triggers
- Owner provides a Gemini API key → run omni_probe.py stage 2 on GA ID, compare
  flicker vs G0 Veo outputs, record winner via ADR 0002 amendment + eval JSONL.
- Vertex Enterprise Agent Platform adds Omni video on project credentials → re-probe.

## 2026-09-03 - Peer-review hardening pass on the approval executor (H-0)
Status: active
Scope: project
Confidence: high

A second agent reviewed the executor implementation; every finding was verified against the code before acting.

**Real, fixed (TDD, each with a failing-test-first):**
1. Slow-lane orphan: job was submitted before the approval moved to acting → a crash between the writes
   strands a running render with no watcher. Now: acting FIRST (with deterministic job_id + job_spec
   snapshot), submit second (idempotent); the sweeper resubmits a missing job from the snapshot.
2. Retryable failures reported as terminal: queue.fail auto-requeues while attempts remain, but the
   worker's hook reported the local stale copy to the approval. Now the hook fires only from the
   queue's authoritative state (re-fetch after every terminal write); requeued jobs stay silent.
3. Lost-lease writes ignored: a stale worker could resolve an approval from rejected writes. Same fix
   as (2): authoritative re-fetch; lost-lease → no hook.
4. Fast-lane "exactly once" overstated: redrive had a check-then-act window. Now the redrive claims
   via guarded approved→acting transition (concurrent sweepers conflict), AND the intake commands
   re-check order-safety at execution time (`backend/approvals/orders.py`, fail-closed when freshness
   is unprovable). Language corrected: fast lane is at-least-once with mandatory idempotency; slow
   lane is exactly-once.
5. Watchdog invisible in UX: approval presenter now exposes result/approver/decided_at/decision_reason/
   sweep_retries; TS union includes "failed"; App.tsx handles approval.updated SSE events.
6. Retry history erased: requeue now appends retry_history {from_status, had_attempts, at} before the
   attempts reset.
7. Supervisor retry tool was `NotImplementedError` in production: now genuinely wired through the
   terminal-only requeue (mid-flight refused), with an integration test.

**Recorded, not code:**
8. D-5 relabeled "identity/detector baseline eval": pickups_eval.py runs the flicker detector on
   labeled inputs with no model call ($0). thresholds.yaml's pickups_vision_judge/artifact_rate bars
   stay DECLARED but are not yet executable — they activate when real generative outputs exist.
   Generative pickups eval remains owed; do not present D-5 as a generative evaluation.
9. SSE is in-process (single Cloud Run instance). Deployment must pin max-instances=1 until/unless a
   Firestore-backed fanout replaces EventHub. Acceptable for demo scale; revisit if multi-instance.
10. `approver` records "dev" on the API path until H-3 (sign-in LAST, owner ruling); acceptable while
    the product is private/local only.

## 2026-09-03 - Supervisor becomes a hierarchical multi-agent specialist team (Amendment A9)
Status: active
Scope: project
Confidence: high
Tags: architecture, multi-agent, adk, supervisor, h0b, h1

### Decision
The Post Supervisor is no longer one monolithic `LlmAgent`. It becomes a team: Post Supervisor
(routes + synthesizes) delegates to parallel specialists — Reliability Investigator, Delivery QC
Agent, Spend Guardian (Localization Agent deferred until E-2 ships) — each returning typed findings
(claims + evidence citations + proposed actions) with **zero act-class tools**; a Verification Agent
hard-filters unsupported/stale/resolved claims before synthesis; only H-0 executes anything. Stage
1a adds Continuity, Creative Finishing, and Visual QC agents once AL-1+D-9 land. Full design:
`docs/plans/2026-09-03-multiagent-supervisor-plan.md`. Amends (does not rewrite) H-0b's plan of
record: only step 2 ("collect candidates") changes source — H-0b's owner rulings (no action-count
cap, envelope covers continuity, self-correction can't re-fight a human) stand verbatim.

### Context
Owner: "the current martini-shot is not a multiagent flow but the hackathon agent needs multi-agent
flow" — a second agent's proposal (hierarchical specialist team, 8-step build order) was reviewed
critically rather than adopted verbatim, per the owner's explicit instruction not to follow it
blindly. The shape (specialists as professional-judgment domains, not one-per-station; typed
findings; only H-0 acts; visible disagreement in the FE) was validated as sound and kept.

### What I changed from the source proposal, and why
1. **Localization Agent deferred to E-2** — no dubbed artifact exists yet; an agent with nothing
   real to judge is an empty shell, not a stubbed capability, but still a wasted build slot.
2. **No ADK `Runner`/`sub_agents` transfer of control** — grep-verified nothing in this repo has ever
   invoked an ADK `Runner`; `build_supervisor()`'s `LlmAgent` has zero callers today. The one proven
   live-call pattern is `otel_ai.py::run_supervisor_text` (direct `genai.Client`, proven in B-3
   evidence). `google-genai==2.20.0` (installed, version-checked) already supports plain-callable
   tools + `responseSchema` structured output — extending the proven pattern is lower-risk than a new
   ADK Runner/session integration under a 5-day runway.
3. **Parallelism is real `asyncio.gather`**, not dependent on Gemini emitting parallel tool calls —
   makes specialist routing TDD-testable (deterministic table), not an LLM decision.
4. **Verification's rejection is a hard filter** (excluded, not down-weighted) — mirrors the
   reversibility rule the owner already set in H-0b.
5. **H-0b's document is amended in place** (one addendum section), not rewritten.

### Alternatives considered
- Adopt the proposal verbatim, including ADK `sub_agents`/`AgentTool` control transfer — rejected:
  bigger, riskier lift with zero prior art in this codebase, and full conversational control-transfer
  is harder to force back to the supervisor for synthesis than a deterministic Python fan-out/fan-in.
- Build Localization Agent now as a placeholder — rejected: nothing real for it to specialize in
  until E-2; ships in the same slice as Dub QC instead.

### Revisit triggers
- If a live interactive agent-chat surface is scoped later, revisit ADK `Runner`+`sub_agents` (real,
  available, just unused here).
- If E-2 (Dub QC) timeline slips past the multi-agent slice, re-confirm Localization Agent still
  waits rather than shipping early with fabricated dub-quality signals.

## 2026-09-02 - Budgeted autonomy: supervisor acts freely inside a $20 envelope (owner ruling)
Status: active
Scope: project
Confidence: high
Tags: autonomy, budget, h0b, spend, continuity, product

### Decision
The supervisor gets a **spend envelope** (default **$20** = `POST_COMMAND_BUDGET_MICROS=20000000`, adjustable in the UX settings) within which it acts **autonomously**: it collects candidate actions, stack-ranks them by **leverage** (unblocks-delivery × severity ÷ cost, weighted by reversibility), and works down the ranked list until the envelope is spent. The envelope covers renders, retries, drafts **and continuity adds** — the owner explicitly overrode the agent recommendation that continuity stays human-approved. Envelope empty → remaining items become ranked proposals in the morning report (graceful degradation, never failure).

### Context
2026-09-02, during the H-0 design discussion. Owner: "we need to set a budget within which the supervisor can make whatever changes it sees fit… it will have to stack rank the changes based on leverage. I want the orchestrator to do real thinking." This is the graduated-autonomy end-state: propose-only remains the fallback (autonomy toggle), not the ceiling.

### Mitigations that make full autonomy survivable
- **Continuity-add is one-click revertible**: every continuity mutation emits a Grafana alert + annotation and lands as an alternates-lane change with a revert action; nothing is destroyed — the locked-cut material is never overwritten, only the continuity pointer moves.
- Daily house cap (Spend Control) stands **above** the envelope; envelope is a sub-cap.
- Draft-first is the default reflex: masters only after a QC-passing draft; never propose a master when a draft informs.
- The ranked deliberation table (candidate, leverage, cost, decision, why) is itself persisted + annotated — the reasoning is auditable, not vibes.
- Autonomy toggle can demote the whole loop to propose-only at any moment.
- Deliberation runs as a background job (C-6.5), text-LLM standard, thinking HIGH.

### Alternatives Considered
- **Continuity stays human-approved regardless of budget:** rejected by owner — full autonomy inside the envelope, with revert+alert as the compensating control.
- **Fixed per-action approval with no envelope:** rejected — makes the supervisor a pager with extra steps; the leverage-ranked budget is the product differentiator ("an employee with a budget, not an intern with a form").

### Revisit When
- Any real (non-demo) deployment is exposed — budget autonomy should be reviewed against production risk before then.
- Envelope burn pattern shows reasoning bugs converting to money (rank eval drift, cost estimates off by >2×).
- Owner changes the envelope in UX — no code change should be needed, only the settings value.

## 2026-09-02 - Amendment A8: promote Extend + real approval-executor ahead of Dub QC/G3
Status: active
Scope: project
Confidence: high
Tags: amendment, stage-1a, extend, approvals, grafana-track, product

### Decision
Owner is optimizing to **win** the Grafana track, not only to bank Stage 1 as a fallback. Promote **AL-1 (alternates model) + D-9 (Extend, Veo single ≤7s segment)** and a new **H-0 typed approval→action executor** ahead of E-2/E-3 (Dub QC) and Gate G3. This crosses the A5 rule ("Stage 1a starts only after G3") for these two items only. Dub QC and G3 are not cancelled — they move after this slice and are still required to call Stage 1 complete.

### Context
2026-09-02. An outside agent proposed closing "Stage 1/G3" via a Veo Extend wedge with a typed command state machine, claiming a plan amendment was needed because H-* sits after Stage 1a. That specific claim was false — the tasks file already sequenced Phase 4 (H-1..H-4) before parked Stage 1a per the 2026-08-30 A7 ruling. The proposal's real, correct insight was orthogonal to that false claim: `decide_approval` (`backend/api/spine.py`) only flips a status field; nothing downstream executes anything except Spend Control's own direct act path. `retry_job` is `NotImplementedError`. Pickups is identity-QC only (no generative call). G0 evidence (`docs/evidence/G0/VERDICT.md`) shows Veo Extend cleaner (flicker 0.69×, better than source) than the spec'd S2 background_swap frame-by-frame Gemini image edit (13.97×, still under threshold but noisier) — and Omni video-input editing 400s on this runtime.

### Rationale
The Grafana track judges an observable, auditable evidence→proposal→approval→action→QC loop, not generative breadth. That loop does not exist yet outside Spend Control. Building one real instance — Extend, chosen for reliability over the spec'd background_swap — end to end, wrapped in a reusable typed executor, is a stronger demo lever than finishing Dub QC first. The executor generalizes the pattern already proven for Spend Control (S5b acts directly) so H-3's "approvals render/resolve" stops being cosmetic everywhere else.

### Alternatives Considered
- **Keep written order (Dub QC → G3 → Stage 1a):** rejected per owner ruling; undersells the track differentiator by demo day if time runs out.
- **Adopt the outside agent's "Extend closes Stage 1" framing verbatim:** rejected — Extend is genuinely Stage 1a work per spec §5, not Stage 1's S2. Framed instead as a deliberate, disclosed Stage-1a promotion (this decision), not a silent Stage-1 finish.
- **Build the executor generically for all stations before choosing an op:** deferred — sequencing D-9 alongside H-0 gives the executor a real caller on day one instead of a speculative contract.
- **Full Stage 1a build order (AL-1→D-9→D-10→E-1→...) all at once:** rejected for now; only AL-1+D-9 promoted, rest of Stage 1a stays gated behind G3.

### Revisit When
- H-0 + D-9 + AL-1 land: re-baseline whether Dub QC / G3 still fits the calendar before 7 Sep.
- If Extend demo reliability regresses on fresh (non-G0) shots, re-open background_swap as the flagship op instead.
- If time runs out before Dub QC, ship G2 + H-0/D-9 as the fallback story instead of the original G3 Stage-1-only fallback.

### Consequences
- `docs/plans/2026-08-26-post-command-tasks.md` amended (Phase 3a-early section, A8) — tasks file, not spec, carries this ruling for now; spec §5 Stage-1/Stage-1a boundary text is unchanged (Extend is still labeled Stage 1a there, on purpose).
- Before writing H-0's command/state-machine code: run the architecture chain per `AGENTS.md` (brainstorming → deep-thinking → api-and-interface-design) since this is a new cross-station module boundary — not skipped, just not done in this planning conversation.
- Billable: D-9 uses real Veo renders. Cost estimate + Spend Control gate before batches (C-7.2).

## 2026-09-02 - Hosted MCP OAuth deferred to post-sprint; hackathon ships OSS + SA token
Status: active
Scope: project
Confidence: high
Tags: mcp, oauth, f4, auth, deferral

### Decision
The hackathon submission ships **OSS mcp-grafana + service-account token only** (`MCP_MODE=oss`, live-proven at B-2/B-2b). Hosted Grafana MCP OAuth (browser login + saved token persistence, plan F-4) is deferred to **post-hackathon work, ordered LAST** in the parked backlog (tasks file, "PARKED — post-sprint backlog").

### Context
Owner ruling 2026-09-02. F-4 rated a one-way door in the handover model plan (implementing auth wrong is the danger; deferring it is safe). OSS path is the demo-critical route with live round-trip evidence; hosted OAuth adds nothing judge-visible. Six days to deadline; G3/demo-batch/rehearsal take priority.

### Consequences
- Before J-3 (hosting rehearsal): add an honest "OSS-only MCP auth" line to README limitations (J-4).
- SA token is a demo single point of failure: keep the regeneration runbook (`docs/plans/2026-09-01-post-command-handover.md` §2) handy through J-6.
- Deferral does not burn the door: F-4 remains implementable post-sprint unchanged.

### Revisit When
- Post-hackathon (or if Grafana-track judging requires hosted-MCP usage — verify track rules before assuming so).
- SA token rotation becomes operationally painful.

## 2026-09-02 - Spend Control is live queue action, not a BigQuery billing warehouse
Status: active
Scope: project
Confidence: high
Tags: spend, s5b, c-7, bigquery, grafana, product

### Decision
Stage 1 money control is the **Spend Control station** (S5b): it reads integer `cost_micros` on Firestore job documents and **acts** (pause intake, Approvals inbox, Grafana annotation). GCP **BigQuery billing export is not** the live spend brain. A later BQ reconcile may be added as audit, not as a replacement.

### Context
2026-09-02, after Gate G2. Owner asked whether building Spend Control instead of “leveraging BigQuery” was a product/feature difference. A stale agent handover (M8) had listed “ledger reconcile vs BQ export.” Approved spec S5b and constitution C-6.4 / C-7 never named BigQuery as the control plane. Hackathon rules mention BigQuery ML only as an allowed Google AI tool.

### Rationale
A runaway station can re-queue in seconds. The brake has to sit on the same Firestore lease queue the worker uses. Billing export into BigQuery is delayed warehouse data: good for “did our micros match the invoice?”, useless for pausing intake in time. Grafana-track demo also needs the act + annotation on the job, not a warehouse query.

### Alternatives Considered
- **Live control via BigQuery / Billing export:** rejected for Stage 1. Latency and the wrong system of record (invoice vs job).
- **Spend Control on `pc-jobs.cost_micros` (spec S5b):** accepted. Already implemented (`backend/stations/spend/`, Gate G2 throttled a 40× runaway).
- **BQ billing export as a later reconcile layer:** deferred. Optional audit after billable Dub/TTS exists; does not replace the station.
- **JSONL-only ledger (`docs/evidence/spend/ledger.jsonl`):** rejected as the product. That file is G0 spike cost evidence, not runtime control.
- **Cue-sheet “ledger matching” (spec S6):** not this decision. Stage 2 music licenses.

### Revisit When
- Owner wants invoice-truth vs `cost_micros` (add BQ export **on top**, do not rip out S5b).
- GCP Billing export lag is proven short enough for a control loop (unlikely; still ask before swapping systems of record).
- Daily spend Grafana alert at 80% of budget (C-7.1 / task H-4) is implemented — that is metric+alert, still not BQ.
- Spec/plan amendment names BigQuery as a Stage 1 requirement.

### Consequences
- Next agents must not treat handover M8 as an open product gap.
- `cost_micros` on jobs remains the system of record for throttle/stop/approve.
- C-7.1 80% Grafana alert is still owed at H-4; that does not reopen BigQuery as the live brain.
- ADR: `docs/adr/0003-spend-control-not-bigquery.md`.

## 2026-09-02 - Auth is built LAST; executor ships auth-agnostic (owner ruling)
Status: active
Scope: project
Confidence: high
Tags: auth, sign-in, f5, h0, deferral, spec-7.2

### Decision
Owner ruling 2026-09-02: **no sign-in gate now** — Firebase Auth (spec §7.2) is built **last, when the whole product is done**. Rationale: auth in the loop makes every test and demo run harder; it must not gate development velocity. H-0's executor and approval API are therefore built **auth-agnostic**: the approval schema carries a nullable `approver` identity (populated `"dev"` placeholder until Firebase lands), and token verification is a pluggable middleware slot, not inline logic.

### Consequences
- Spec §7.2 (sign-in-to-approve) stays REQUIRED for the shipped product: it must land before J-5 (demo video) or be disclosed as a limitation in J-4's README. Decision point: J-3 rehearsal.
- No second action path may grow around the missing auth (H-0 remains the only executor).
- Demo approvals run as `approver: "dev"` until Firebase lands; the Grafana annotation (C-4.3) records whatever identity exists at act time.
- Revisit: the moment any real deployment is exposed beyond localhost/dev, auth can no longer wait.

---

## 2026-09-06 - A10: Agentic stations (owner-approved amendment)

Type: decision (amendment A10)
Scope: project
Confidence: high
Tags: a10, agentic-stations, edd, station-agents, dub-qc, orchestrator

### Decision
Owner ruling 2026-09-06 (dialogue + adversarial self-review): every station with a
judgment surface becomes agentic - 8 bespoke personas + a Batch Orchestrator agent.
The deterministic verdict is ADVICE the agent may override with a stated, logged
reason (overridden: true); measurement-station agents own the RESPONSE to the
deterministic report (triage/remediation/fixes/profile routing), with every agent fix
re-validated by the deterministic rule engines it must satisfy. Measurements stay
exact and machine-checkable. H-0 remains the only executor. Each agent ships only
after its EDD gate (mean_case_accuracy >= 0.8, 3 real runs) passes - datasets seeded
BEFORE the agent code. Design: docs/specs/2026-09-06-agentic-stations-design.md.
Build order: Dub QC (A10-1) -> Orchestrator (A10-2) -> strategists (A10-3) ->
retrofits (A10-4). Task rows: docs/plans/2026-08-26-post-command-tasks.md.

### Consequences
- EDD dataset count grows by 8 (orchestrator_planning, ingest_triage_judgment,
  loudness_strategy_judgment, caption_remediation_judgment,
  delivery_strategy_judgment, pickups_qc_judgment, extend_qc_judgment,
  spend_steward_judgment) on top of the shipped dub_qc.
- Schedule risk accepted by owner (bespoke personas vs one shared judge).
- Malformed/failed agent responses fall back to the deterministic verdict, marked
  decision_mode: deterministic_fallback - visible, never silent.

---

## 2026-09-06 - Dub time-fit via ffmpeg atempo, not re-rendering (ADR-0004)

Type: decision (engineering, evidence-based)
Scope: dub station (E-2)
Confidence: high (measured probe + 3 green eval runs)
Tags: dub-qc, atempo, tts, chirp, e2

### Decision
A dub is time-fitted to its source line with ONE TTS render + a deterministic
ffmpeg tempo stretch (ackend/stations/dubbing/qc.py::atempo_wav), not by
re-rendering at an adjusted rate. The Dub QC Agent judges the FITTED audio with the
reference script in the prompt (missing-content detection). The eval's truncation
defect is a hard EOF mid-speech (	runcate_speech_wav), not a tail cut.

### Evidence and consequences
- Chirp 3 HD rate response measured nonlinear (probe scripts/probe_tts_rate.py:
  rate 0.8 -> 1.34x duration), so re-render fitting cannot hit the 45 ms gate;
  atempo is exact, free, local, pitch-preserving. Gate result: MAE 4.8-9.9 ms.
- TTS tails carry breath/noise above naive amplitude floors AND sentence-final
  words below any floor: tail cuts remove silence, not words. Transcription probes
  (scripts/probe_fr03_hear.py) proved the agent was RIGHT twice to call tail-cut
  dubs clean - the dataset mutation was the defect until fixed.
- A dub QC agent that cannot see the reference line cannot detect MISSING content
  ("Prise trois." is a complete sentence until compared to the script).
- ffmpeg piped WAVs carry streaming headers (nframes=0xFFFFFFFF): WAV readers must
  read to EOF, never copy nframes (_read_wav, 	runcate_wav).

---

## 2026-09-07 - A10 delivered: 9 agentic station layers, all EDD gates green

Type: decision (execution record, amendment A10 complete)

### Decision
The full A10 amendment landed in two days: A10-1 Dub QC (done earlier), A10-2
Batch Orchestrator, A10-3 four measurement-station strategists, A10-4 three
retrofits. Nine agents total, each: dataset seeded BEFORE tuning, one metered
flash call, StationDecision contract, deterministic suggestion riding along
(differences = explicit logged overrides), visible fallbacks, 3-run live EDD
evidence at >= 0.8 (most at 1.0).

### Consequences
- Prompt tuning lessons are now a reusable playbook (H-1b loop on real
  responses): vibe rules swing models - use explicit ordered decision ladders;
  historical context can outshine a binding threshold (mark what is
  illustrative); meter-integrity must be unconditional and first; fixture
  reality must match labels (SMPTE test patterns honestly read as defects).
- `run_agent_call` supports audio AND images inline - one instrumented site.
- Spend Steward: deterministic triggers remain the only START authority; the
  agent picks among allowed responses; enforcement path unchanged (C-4.3).
- Next: E-3 batch manifest + owner-approved billable run (C-7.2), G3 gate.
