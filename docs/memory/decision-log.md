# Decision Log

## 2026-09-08 - Supervisor may add or remove from the cut
Status: active
Scope: Post Supervisor + continuity + H-0 lock guard
Confidence: high
Tags: autonomy, continuity, cut, envelope

### Decision
The supervisor has discretion to **add a take to the cut** and **take a
take out of the cut** (`add_to_continuity` / `remove_from_continuity`)
inside the night envelope. A human is not required. Lock still blocks
renders/retries that would overwrite frozen media.

### Context
2026-09-02 already put continuity adds inside the envelope. A later agent
told the owner the supervisor would not change the cut. Owner corrected
that: add/remove from the cut is part of ranked night spend.

### Alternatives Considered
- Keep cut changes human-only: rejected by owner.
- Unlock the shot, then mutate, then re-lock: more dangerous than a
  pointer move.

### Revisit When
Owner flips `propose_only`, or a cut change needs a human freeze that
lock no longer covers.

### Consequences
- Continuity specialist is routed on needs-human, quarantine, and
  picture stations.
- Pointer moves may have a $0 cost estimate and still dispatch.
- Grafana annotation trail + one-click revert still apply.

---

## 2026-09-08 - Rank, then spend the night envelope (owner demanded)
Status: active
Scope: Post Supervisor + finishing orchestrator
Confidence: high
Tags: autonomy, envelope, rank, spend

### Decision
The supervisor ranks work, then **spends the night envelope (default $20)
down that list**. That is the product default. `propose_only` is the off
switch. The ranking-quality exam already passed 3×1.0; the receipt is written
to live `pc-control/act-gate`.

### Context
Owner had asked repeatedly to let the supervisor prioritize and spend. A
paper receipt was left unwritten in Firestore, so ranked dispatch did nothing.

### Alternatives Considered
- Keep one-retry-only as the default: rejected by owner.
- Wait for another rehearsal: rejected by owner.

### Revisit When
Owner flips `propose_only`, or rank quality drops below 0.8.

### Consequences
- `ensure_budgeted_spend` on app boot.
- Envelope, daily house cap, and human-wins still bound spend.

---

## 2026-09-08 - Supervisor may diagnose and retry once; full ACT stays locked
Status: superseded
Scope: Post Supervisor autonomy (`budget_loop` + settings default)
Confidence: high
Tags: autonomy, retry_once, supervisor, edd

### Decision
Superseded the same day: owner demanded ranked night-envelope spend, then
cut add/remove. `retry_once` remains a tighter mode, not the default.

See: Rank, then spend the night envelope; Supervisor may add or remove
from the cut.

### Context
Owner asked to sit the finishing rank/spend exams and to let the supervisor
retry once after real thinking. Corrupt ingest, locked cuts, runaway loops, and
a second supervisor retry stay code-blocked.

### Alternatives Considered
- Unlock full ACT: rejected (owner did not watch a live gate; P-5 stands).
- Keep propose-only as the production default: rejected (owner wanted one
  autonomous retry).
- Heuristic retry without Gemini: rejected (fuzzy transient-vs-permanent needs
  live Gemini + EDD).

### Revisit When
The owner watches a live ACT gate, or the one-retry eval falls below 0.8.

### Consequences
- Hard gates in `admit_retry_once`; Gemini `decide_retry_once` for fuzzy rows.
- Stamp `result.supervisor_retries` so the next cycle cannot retry again.

---

## 2026-09-08 - Demo plan is the walk-away house order (AO §7 + A6)
Status: active
Scope: demo video (J-5), AO-STATION-MAP §7, spec walk-away paragraph, FinishBar copy
Confidence: high
Tags: demo, walk-away, finishing, grafana

### Decision
The 3-minute demo is **walk away from a real post house**, not a station-by-station
fault tour. Narration and on-screen beats follow AO-STATION-MAP §7: upload in
order → ingest file check (corrupt stops) → ingest watch (script + scene) →
**always mix** → **always pickups** on that mixed clip → wait until every clip is
through pickups → leftover agents look in upload order → Spend prices each leftover
→ orchestrator ranks impact, dependencies, and spine notes → run what still
fits. Grafana moments stay on those beats. Batch volume is a **finale**, not the
spine. J-5 records that script from the running product.

### Context
Owner locked the product sequence and asked to put that flow in the demo plan.
The 2026-08-26 §7 table (ingest corrupt → pickups hero → dub → captions →
delivery loudness fail) no longer matches the product.

### Alternatives Considered
- Keep the old fault-injection tour and mention walk-away in a caption: rejected
  (owner asked to update the demo plan with this flow).
- Make the video a season-batch heatmap first: rejected (volume sits in the finale).

### Revisit When
J-5 rehearsal shows a beat that cannot be filmed from the running product (C-1.5),
or the owner re-cuts the house order.

### Consequences
- Spec walk-away paragraph and FinishBar copy must match §7.
- Do not demo “every station looks at once after ingest.”

---

## 2026-09-07 - Walk-away: mix then pickups, then leftover Gemini looks, then orchestrator
Status: active
Scope: finishing loop, ADK propose team, spend pricing, orchestrator rank
Confidence: high
Tags: finishing, orchestrator, spend, handoff, edd

### Decision
Ingest job checks the file. Ingest agent watches and writes script + scene.
Loudness then pickups **always run as jobs** (upload order; shot N mix waits
on shot N−1). After **every** clip finishes pickups, leftover station agents
watch the updated clips in that same order (Gemini). Spend **prices each**
leftover suggestion (Gemini). The orchestrator then ranks by impact,
**named dependencies**, and remaining money, and it **reads**
`handoff_orchestrator_note` / ingest spine messages in that billed call.
A Python sort is crash fallback only. Live evals: `finishing_rank_quality`
(added post-cleanup + spine rows) and `spend_pricing_judgment`.

### Context
Owner: leftover agents must not all start with ingest. Clips arrive in
upload sequence with metadata. Orchestrator uses complex judgment including
dependencies. Handoff already writes spine notes; the boss must process them.

### Revisit When
Live rank or spend-pricing 3-run mean < 0.8.

---

## 2026-09-07 - Extend/Corrections looker: must / nice / leave
Status: active
Scope: finish_extend + finish_corrections inspect
Confidence: high
Tags: finishing, inspect, d-9, d-10, edd

### Decision
Each looker picks one bucket from the picture: **must** (`needs_work` +
`kind=defect`), **nice** (`needs_work` + `kind=improvement`), or **leave**
(`status=ok`, no proposal). The orchestrator never sees leave-it as work.
It spends defects before improvements and drops low taste first when money
is tight. Live Gemini watch is the exam — not a written brief.

### Context
Owner asked for required vs nice-to-have vs leave-it in the D-9 and D-10
ADK agents, then wiring into the boss. Prior inspect eval failed at 0.75
in part because a mid-cut was labeled taste.

### Revisit When
Live `finishing_extend_corrections_inspect` 3-run mean < 0.8.

---

## 2026-09-07 - Loudness: six scene kinds, lift voice over room, no human stop
Status: active
Scope: loudness station + Loudness Strategist + finishing cleanup order
Confidence: high
Tags: loudness, scene-class, speech-split, finishing

### Decision
Classify every mix as quiet/normal/loud × with/without dialogue (examples:
wind = quiet-no-dialogue; explosion with no line = loud-no-dialogue). Stay
inside a comfortable hearing range; loud may sit louder, quiet softer.
Speech must be hearable. If the line is buried in the room, **lift the
voice relative to ambience** (ffmpeg voice-band vs room split), not only
the whole track. A continuing shot keeps speech and room in family with
the previous mix. **Never `needs_human`.** Best effort always. After ingest
metadata exists: loudness then pickups are mandatory cleanup (that spend
is spent) before Stage 1a/dub proposals; the orchestrator then sequences
what can run together. Ingest ADK is owned by the other thread — do not
rebuild it here.

### Context
Owner rejected whisper/explosion labels as juvenile, picked voice-over-room
isolation, and said every station must not run at once.

### Rationale
A mixer judges energy × speech, then actually fixes the soundtrack.

### Alternatives Considered
- Whisper/talk/shout/impact/explosion labels: rejected (owner).
- Raise the whole track when speech is buried: rejected (owner picked a real split).
- Parallel every station after ingest: rejected (owner).

### Revisit When
- Live `scene_loudness_judgment` 3-run mean is below 0.8 on the new classes.
- Voice-band split fails on a real café/wind clip (need a stronger separator).

### Consequences
- `SCENE_CLASSES` in `backend/stations/loudness/scene.py` is the six-kind table.
- `FFmpeg.lift_speech_over_room` is the split. `fix_stem` means lift voice.
- Finishing `apply_cleanup_sequence`: loudness then pickups, then creative.

---

## 2026-09-07 - Scene-aware loudness mix (not a single TV number)
Status: superseded
Superseded by: 2026-09-07 - Loudness: six scene kinds, lift voice over room, no human stop
Scope: loudness station + batch orchestrator + Loudness Strategist
Confidence: high
Tags: loudness, e-3, scene-class, dub

### Decision
Loudness hears the **dub** (not only the picture soundtrack), classifies the
scene (silence / whisper / talk / shout / crash / explosion), mixes toward
that level, and re-measures. Whisper is one example: a bang or a crash of
pans should sit **louder** than talk. Dialogue stays easy to hear. The show
stays in one family. `needs_human` only if the mix still misses.

### Context
E-3 loudness jobs flagged `fail_quiet` and stopped. The meter was reading the
picture track and never turning the volume. Owner asked for scene-fitting
levels, not “everything to −16” and not whisper-only.

### Revisit When
Replaced 2026-09-07 by the six-kind table + voice-over-room split.

---

## 2026-09-07 - Finishing inspect EDD is a real watch, cap $20
Status: active
Scope: finishing inspect eval
Confidence: high
Tags: finishing, edd, inspect, c-7.2

### Decision
If the product needs judgment, Gemini is called. If Gemini is wired, it is
tuned with live EDD — real clips, real frames/audio, real Vertex calls. Owner
raised this exam’s spend cap to **$20**. Do not skip a billed judgment eval
to save a few dollars, and do not substitute a written vignette for a look.

### Context
Owner: skipping `finishing_inspect_eval.py` without asking was wrong. Vignette-
only scoring is not EDD for a watch.

### Revisit When
Live 3-run mean_case_accuracy < 0.8.

---

## 2026-09-07 - Finishing rank is a thinking orchestrator, not a sort key
Status: active
Scope: finishing orchestrator
Confidence: high
Tags: finishing, rank, adk, edd

### Decision
The finishing boss is a billed Gemini call over the **complete** bag of station
notes. It weighs tradeoffs and names dependencies. Python only refuses invented
stations / empty rows, and honors `blocked_by` at dispatch. The old high→low
sort is crash-fallback only. Live rank eval (not the comparator) is the gate.

### Context
Owner rejected treating a 12/12 code-sort exam as “ranking.” “How can you
prioritize without intelligence weighing pros/cons and identifying
dependencies.”

### Revisit When
Live `finishing_rank_quality` 3-run mean is below 0.8.

---

## 2026-09-07 - Walk-away finishing (billed looks, taste, high/medium/low)
Status: superseded (all-at-once roster looks). Taste bands still apply after
mix and pickups. Replacement: mix-then-pickups (2026-09-07) + demo A6 (2026-09-08).
Scope: finishing orchestrator + every existing station inspect
Confidence: high
Tags: finishing, adk, inspect, rank, walk-away

### Decision
Upload clips, set **$50**, walk away. Every roster station takes a **billed look**.
Agents propose **defects and quality/taste** (consistent-but-too-dark faces counts).
Impact is **high / medium / low**. Rank is must-hear/must-see, then defect before
taste, then earlier in the cut, then cheaper. Auto-enqueue; `needs_human` only
when the station cannot act. Budget mid-job pauses; final = originals + **passed**
only. Google ADK `Runner` actually runs the team.

### Context
Owner approved the finishing plan and ruled billed looks OK, three impact bands,
minimize human stops, and less conservative station agents.

### Rationale
A defect-only look leaves a dark-but-consistent scene unfixed. A two-band rank
cannot separate “dies mid-thought” from “optional dolly.”

### Alternatives Considered
- Skip billed inspect to save money: rejected (owner).
- high/low only: rejected (owner asked for medium).
- Propose-only / needs_human on quiet: rejected (auto-enqueue mix).

### Revisit When
Live inspect 3-run eval is below 0.8, or ADK Runner fails in production.

---

## 2026-09-07 - Scene-aware loudness mix (not a single TV number)
Status: active
Scope: loudness station + batch orchestrator + Loudness Strategist
Confidence: high
Tags: loudness, e-3, scene-class, dub

### Decision
Loudness hears the **dub** (not only the picture soundtrack), classifies the
scene (silence / whisper / talk / shout / crash / explosion), mixes toward
that level, and re-measures. Whisper is one example: a bang or a crash of
pans should sit **louder** than talk. Dialogue stays easy to hear. The show
stays in one family. `needs_human` only if the mix still misses.

### Context
E-3 loudness jobs flagged `fail_quiet` and stopped. The meter was reading the
picture track and never turning the volume. Owner asked for scene-fitting
levels, not “everything to −16” and not whisper-only.

### Rationale
A single streaming target treats an explosion at talk level as a pass. The
product is a mixer: listen, pick the fitting number, apply, check again.

### Alternatives Considered
- Keep measure-only + needs_human: rejected (owner: actually fix it).
- Whisper duck only: rejected (owner: louder events too).
- Always −16 LUFS: rejected (kills scene dynamics).

### Revisit When
- Stem remix (dialogue vs music) lands; today imbalance is still `fix_stem`.
- Delivery should consume the mixed artifact instead of the picture URI.

### Consequences
- Orchestrator stamps `dub_job_id` on loudness jobs.
- Station applies ffmpeg `loudnorm` and writes an ALTERNATE.
- New eval suite `scene_loudness_judgment` (bar >= 0.8).

## 2026-09-07 - Eval footage: generate original clips with the real deficit
Status: active
Scope: generative evals (Omni/Veo)
Confidence: high
Tags: edd, omni, fixtures, recitation, d-9, d-10

### Decision
If a public-domain or third-party clip fails Omni because Google treats it as
an ownership / copying / infringement refusal, generate **new original clips
that still have the defect the feature must fix**, then run live EDD and
fix the feature. Do not pass on color-bar/gradient stand-ins. Do not silently
switch models to hide the miss. If Omni cannot be called, stop and tell the
owner.

### Context
BBB grove/clearing `recitation` refusals led an agent to use ffmpeg gradient
clips for a “green” D-10 quality eval. The owner rejected that tape. A later
D-9 recheck passed when Omni generated original café scenes and extended them.

### Rationale
The eval must exercise the product problem (signage, extend, relight, …), not
a clip that is easy for the model because it contains nothing to fix.

### Alternatives Considered
- Keep using BBB and call the feature blocked: rejected (filter ≠ product bug).
- Gradient/colorbar INPUT as the quality tape: rejected by owner.
- Silent Veo fallback so the suite still “passes”: rejected.

### Revisit When
- Google’s filter starts refusing **our own generated** clips the same way, or
  the owner supplies a preferred original-footage library for evals.

### Consequences
- Binding text in root `AGENTS.md`, `backend/AGENTS.md`, and
  `.cursor/rules/eval-footage.mdc`.
- Follow-on ruling the same day: Veo fallback only after Omni EDD on original
  deficit clips; Omni-fail / Veo-success must always be disclosed to the owner
  (see next entry).

## 2026-09-07 - Veo fallback is last; Omni-fail / Veo-success must be told
Status: superseded
Superseded by: 2026-09-07 - Product Veo fallback vs eval-only original clips
Scope: generative evals and station fallbacks
Confidence: high
Tags: omni, veo, edd, disclosure

### Decision
Add a Veo fallback **only after** original deficit clips have been generated
and the feature has been EDD-tested on Omni. During development and evals, if
Omni fails and Veo succeeds on the same work, **tell the owner immediately**
(clip, Omni error, Veo finished). Never present that as an Omni pass.

### Context
D-9’s 2026-09-04 eval mixed Omni (gradient) and Veo (BBB) under one green
score; the owner would not have seen a systemic Omni miss.

### Rationale
Fallback keeps the operator unblocked. Silence about Omni failure hides outages.
(Clarified later: generating original clips is **eval-only**; product Veo
fallback is always the right operator behavior.)

### Alternatives Considered
- Keep silent Veo fallback in evals: rejected.
- Never allow Veo: rejected; it is allowed **after** Omni EDD, with disclosure.

### Revisit When
- Owner wants evals Omni-only with no product fallback, or Omni refusals on
  original generated clips become the common case.

### Consequences
- Agents must surface Omni-fail / Veo-success in chat and in `docs/evidence/`.
- Station jobs must keep recording `render_model`.

## 2026-09-07 - Product Veo fallback vs eval-only original clips
Status: active
Scope: generative stations and evals
Confidence: high
Tags: omni, veo, product, edd

### Decision
**Product:** Omni first; if Omni fails, fall back to Veo. That is correct
product behavior. **Development/eval only:** if Omni refuses a public-domain
clip for ownership/infringement, generate original clips that still have the
real defect and prove Omni there. Generating a new clip is not what the
product does for the operator. An eval must not count Veo success as an Omni
pass; tell the owner if that happens during development.

### Context
The “generate original clips / Veo last” wording was being read as “the
product should not Veo-fallback.” The owner clarified the opposite for the
shipped product.

### Rationale
Operators must not be stuck when Omni refuses. Evals must still catch a
broken Omni path.

### Alternatives Considered
- Fail the operator job if Omni fails: rejected.
- Count Veo-finished evals as Omni quality passes: rejected.

### Revisit When
- Owner wants product Omni-only (no Veo), or wants evals to accept Veo as
  an equivalent quality pass.

### Consequences
- Stations keep Omni→Veo fallback and record `omni_fallback`.
- `scripts/extend_eval.py` still fails the suite if Veo rendered.

## 2026-09-07 - Stage 1a is built one live-EDD feature at a time
Status: active
Scope: demo execution order
Confidence: high
Tags: stage-1a, edd, sequencing, d-10

### Decision
Build and fully EDD-verify one Stage 1a feature end-to-end before starting
the next. Start with D-10 Corrections. Do not scaffold remaining backends
and run live evals later.

### Context
Owner reversed an earlier "scaffold all six, eval afterward" leaning.
Cloud-Agent eval artifacts are not live (no GCP). Remaining eval/demo spend
is owner-capped; C-7.2 still requires a printed estimate and `--yes` above $5.

### Rationale
A half-wired Relight/Coverage/Camera surface without a green Corrections
eval is demo risk. One finished drawer journey (agent + manual + H-0 +
alternate + live numbers) is worth more than six incomplete scaffolds.

### Alternatives Considered
- Scaffold backend job/H-0/API for all six first, live EDD afterward: rejected.
- Parallelize two features: deferred until D-10 is eval-green in the running UX.

### Revisit When
- D-10 live judgment + quality gates are green and the Corrections drawer is
  in the running product, or the remaining eval envelope cannot fund the
  next feature's three-run quality batch.

### Consequences
- Next feature (E-1 Relight) does not start until D-10 evidence exists.
- Leftover scaffolds from the reversed approach are inert until their turn;
  they must not be treated as done.

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
  evidence. Every feature must be exposed in the running UX through both an
  agent-assisted and a manual user-initiated route. Six distinct domain agents
  are required: Corrections, Relight, Draft-First, Coverage, Revision Room,
  and Camera Language; the Creative Orchestrator selects relevant agents and
  makes the final whole-video improvement decision.
- Remaining Stage 1a eval/demo spend is capped at $100. Batches over $5 still
  print their estimate and require `--yes` (C-7.2); exceeding $100 requires a
  new owner approval.
- D-13 Transition Forge and D-14 Versioning remain stretch; Stage 2+ does not
  enter the demo scope.

### Revisit trigger
If the remaining $100 envelope is exhausted before integrated G3/G3a, the
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
