# Decision Log

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
