# Design: H-0 Typed Approval→Action Executor
Date: 2026-09-02 | Status: Approved (owner + agent, brainstorming chain) · Pre-mortem + adversarial review applied 2026-09-02 — findings folded into the contract below (see §Pre-mortem)

## Summary
Today, approving anything in Martini Shot just flips a status label — nothing downstream executes. This design makes "approve" trigger a real action for every station, including Spend Control, through one shared, auditable dispatcher, so the Grafana-track demo has one genuine evidence→proposal→approval→action→QC loop instead of several half-finished ones.

## Problem
- `decide_approval` (`backend/api/spine.py`) only rewrites `pc-approvals.status`. No code path executes on approval.
- `retry_job` (`backend/supervisor/agent.py`) is `raise NotImplementedError`.
- Spend Control (S5b) is the one station that already "acts" — but it acts *before* any approval decision (auto-throttle); the approval it opens for *resuming* does nothing when approved today. That's the same bug in a different spot.
- Amendment A8 (`docs/memory/decision-log.md`, 2026-09-02) promotes D-9 (Extend) + AL-1 (alternates) ahead of Dub QC specifically to get one real loop live. That loop needs somewhere real to plug into.

## Approach
**Approach C — one dispatcher, two lanes**, chosen over two alternatives during brainstorming:
- **Rejected — Approach A (everything is a Job):** semantically wrong for instant actions. Forcing `pause_intake`/`resume_intake` through the job worker would make a "pause" appear as a fake entry in the same timeline lane as real ingest/loudness/delivery jobs, and adds a queue hop to something that's already a safe, fast, tested function.
- **Rejected — Approach B (new command system + new reconciler):** building a second queue-like system from scratch five days before submission is how you ship new bugs into a product that already passed Gate G2. Reuse the proven queue instead of duplicating it.
- **Accepted — Approach C:** fast, already-idempotent actions (pause/resume/retry) run immediately through a small registry; anything that needs real render/compute time (Extend) is handed to the existing, chaos-tested Firestore lease queue. One state machine, one audit-trail writer, both lanes.

## Architecture

### Data model (additive only — C-6.4, C-1 no destructive migration)
`pc-approvals` document gains these fields (existing fields — `approval_id`, `project_id`, `job_id`, `kind`, `title`, `detail`, `status`, `created_at`, `cost_delta_micros` — are unchanged):

```text
command: {name: str, args: dict}   # what to do; args are command-specific
lane: derived at dispatch time from the registry, NOT stored (avoids drift if a command's lane changes)
acting_since: str | None           # ISO timestamp when status becomes "acting" (sweeper staleness check)
result: dict                       # terminal outcome, same shape convention as Job.result
approver: str | None               # reserved for H-3 Firebase identity; null until then
```

`pc-jobs` (`backend/jobs/models.py`) gains one additive field:
```text
approval_id: str | None = None     # set when a job was created BY an approval, for the completion hook to find its way back
```

Status vocabulary (extends existing `proposed`/`approved`/`rejected`):
`proposed → approved → acting → resolved | failed`, plus the existing terminal `rejected` (a human said no — distinct from `failed`, which means we tried and the action itself failed).

### Command registry
New module `backend/approvals/commands.py`, same shape as the existing `ToolRegistry` (`backend/supervisor/registry.py`) but a separate registry for a separate concern (station actions triggered by human approval, not agent-to-Grafana calls).

```python
@registry.command("pause_intake", lane="fast", idempotent=True)
def _pause_intake(store, approval) -> dict: ...


@registry.command("generate_alternate", lane="slow")
def _generate_alternate(store, gcs, approval) -> Job: ...
```

**Fail-closed registration rule:** registering `lane="fast"` without `idempotent=True` raises at import time. This operationalizes guardrail #1 as code, not a comment.

### Dispatch flow
1. `POST /api/v1/approvals/{id}/decision` (existing endpoint, `backend/api/spine.py`) calls one new `ApprovalStateMachine` module instead of writing status inline.
2. **`reject`** → transactional `proposed→rejected` transition. No dispatch.
3. **`approve`, fast command** → transactional `proposed→approved` transition (guard prevents double-dispatch on retried HTTP requests) → handler runs synchronously → transactional `approved→resolved|failed` with `result` → SSE + Grafana annotation.
4. **`approve`, slow command** → transactional `proposed→approved` → handler builds and submits a `Job` with a **deterministic id** (`job_id = f"job-cmd-{approval_id}"`, so the existing `queue.submit()` idempotent-create-swallow logic — already in `backend/jobs/queue.py` — makes an accidental double-dispatch a no-op) → `approval.job_id` set, `status="acting"`, `acting_since=now` → SSE + Grafana annotation (proposal accepted, render started).
5. **Job completion hook:** the worker's existing terminal-write path (`_persist` in `backend/jobs/worker.py`) additionally checks `job.approval_id`; if set, transitions the linked approval to `resolved`/`failed` from the job's outcome, through the same `ApprovalStateMachine` writer used everywhere else — not a second annotation code path.
6. **Sweeper:** one periodic task (same lifespan pattern as `_run_worker` in `backend/api/app.py`), tick ~10s. For every approval in `acting`:
   - Has `job_id` and that job is **terminal** (`passed`/`failed`/`quarantined`) but the approval wasn't updated (crash between job finishing and the hook running) → reconcile now, exactly once.
   - Has `job_id` and the job is **non-terminal** (`queued`/`leased` — including a worker that died mid-flight and the lease-expiry reassignment that follows) → **do nothing. Patience is the contract:** the approval follows the job's lifecycle and never shortcuts it. Auto-retrying a render is forbidden. Backstop: `acting` older than 15 minutes with the job still non-terminal → `failed` with `needs_human_review` (never auto-resume, never auto-retry).
   - Has no `job_id` (fast lane) and `acting_since` older than ~30s → the fast action didn't finish (process died mid-call). Re-drive at most once per staleness window, capped at 3 sweep-retries, then `failed` with a note for human review. **Order-safety:** a re-drive yields to any newer decision on the same target resource — handlers receive the approval's `decided_at` and compare-and-skip when a newer decision already touched the target, marking the approval `failed: superseded` instead of replaying stale state. Never left silently stuck.

`ApprovalStateMachine._transition` mirrors `FirestoreLeaseQueue._transition` (`@firestore.transactional`, guard-checked) — same proven pattern, new collection. One function is the only writer of approval status, `result`, SSE publish, and Grafana annotation, for **both** lanes — this is what keeps "one path everywhere" true instead of becoming two paths with extra steps.

**Commit-first, emit-after (pre-mortem clause):** the Firestore status transition lands *before* SSE/Grafana emission; both emissions are best-effort — any failure is logged and never blocks or reverts the transition. A Grafana outage can strand nothing.

**Hook isolation (pre-mortem clause):** the completion hook in `_persist` is a **projection, not truth**. The job's own terminal write never depends on approval logic; any exception inside the hook (deleted approval doc, malformed command args, anything) is logged and swallowed — the job's outcome is already durable. The sweeper rebuilds the approval from terminal job state later. Job state is the source of truth; approval status is always reconstructible from it.

### Concurrency (the one open technical risk, closed)
Two decisions racing on the *same* approval are already prevented by the existing `status != "proposed"` guard (409 today) — this design keeps that, just moves it into the shared transactional helper.

Two decisions racing on the *same underlying resource* from *different* approvals (e.g. "pause ingest" then "resume ingest" a second apart) is real but narrow for a human-paced demo. **V1 scope, explicitly stated, not hidden:** the dispatcher does not queue/serialize across different approvals; it relies on making the underlying writes themselves safe. That requires one fix beyond what was originally proposed: `pause_intake`/`resume_intake` (`backend/stations/spend/control.py`) currently read-then-write (not atomic) — rewritten as `@firestore.transactional`, matching the pattern already proven in `queue.py`. Idempotency alone doesn't prevent a lost update; atomicity does, and the pattern already exists in this codebase — this is a small, low-risk fix, not new machinery.

### Spend Control migration (what "migrate" actually means here)
Spend Control's *automatic* pause on a detected runaway stays automatic — it must not wait for a human, that's the whole point of the protection. What changes: `throttle_station` (`backend/stations/spend/act.py`) calls the **same** `pause_intake` command through the **same** dispatch+audit function a human's approval would use, instead of calling `pause_intake` directly and writing its own annotation. The auto-created "resume" approval, once a human clicks approve, now actually calls `resume_intake` through the executor — fixing the real bug where approving it does nothing today. One dispatch function, two callers (an automated station and a human decision) — not "make throttling wait for permission."

## Key Decisions
- `retry_job` is **fast lane**, not slow — it re-queues an *existing* job **only from a terminal state** (`passed`/`failed`/`quarantined`), through the queue's own requeue path so attempts accounting stays intact. Retrying a `queued`/`leased` job is **rejected with 409**: a mid-flight job (including a worker that died mid-run, pre-lease-expiry) is the lease-expiry machinery's business, never retry's. No new Job is created; the approval resolves as soon as the requeue lands. It does not wait for the retried job to finish — that job's own subsequent pass/fail is visible on the job/timeline board independently.
- Deterministic job IDs (`job-cmd-{approval_id}`) reuse the queue's existing idempotent-create behavior instead of building new dedup logic.
- The supervisor's Grafana MCP act-tools (`add_annotation`, `create_incident`, gated by `Autonomy`) are **not** migrated onto this executor — different concern (agent autonomy over an external system vs. human-approved station actions), different existing mechanism that already works correctly.
- Command lane is derived from the registry at dispatch time, never stored on the approval doc, so lane can be corrected later without a data migration.

## Edge Cases
- HTTP client retries the same `approve` POST (e.g. timeout) → transactional guard means the second call sees `status != "proposed"` and is a no-op (matches existing 409 behavior).
- Process crashes mid fast-lane handler → sweeper detects stale `acting`, safely re-runs (idempotent by registration contract), caps retries.
- Process crashes after slow-lane job is submitted but before `acting` is written → deterministic job id means a retry of the submit step is a safe no-op; sweeper still finds the approval `approved` (not yet `acting`) and can re-run the "submit" step, which is itself idempotent via the same deterministic-id mechanism.
- Job the approval is watching gets independently quarantined by the ingest station's own logic (not by this executor) → completion hook still fires (quarantine is a terminal Job status), approval resolves as `failed` citing the quarantine reason.
- Two approvals target the same resource close together → see Concurrency above: transactional writes on the underlying resource, not a serialization queue, for V1.

## Testing
TDD, RED-first, per project convention (`.agents/skills/test-driven-development/SKILL.md`):
- Registry: fast command without `idempotent=True` raises at registration.
- Dispatch: fast command → resolved/failed synchronously, one annotation, one SSE event.
- Dispatch: slow command → `acting`, `job_id` set, a real Job exists on the queue with the deterministic id.
- Double-dispatch (simulated HTTP retry) is a no-op on both lanes.
- Completion hook: linked job resolving to pass/fail/quarantine flips the approval accordingly, through the shared writer (assert exactly one annotation).
- Sweeper: stale fast-lane `acting` → safe re-dispatch → resolves; capped at 3 attempts → `failed`. Stale slow-lane `acting` with an already-terminal job → reconciled without re-submitting a duplicate job.
- `pause_intake`/`resume_intake` transactional rewrite: two rapid opposite calls never lose an update (regression test for the concurrency fix).
- Retry source-state rule: `retry_job` on a `queued`/`leased` job → 409 rejected; on a `failed` job → requeued through the queue path with attempts intact.
- Hook isolation: completion hook raises (approval doc deleted mid-flight) → the job's terminal write still lands; worker logs and continues.
- Sweeper patience: watched job goes `leased` → worker killed (real subprocess) → lease expiry reassigns → approval remains `acting` throughout; resolves exactly once when the job turns terminal.
- Order-safety: stale crashed `resume` re-drive with a newer `pause` decision on the same target → skipped, approval `failed: superseded`, intake stays paused.
- Emission outage: annotation/SSE raises after `approved` → transition still lands; sweeper reconciles without duplicate terminal annotations (exactly one per transition).
- Single-writer enforcement: grep-test asserts no module outside `ApprovalStateMachine` writes `pc-approvals` status (same spirit as the C-1.2 integrity check).
- Spend Control integration: seeded runaway → auto-throttle still uses the shared dispatcher; approving the resulting "resume" approval actually calls `resume_intake` (fixes today's no-op bug) — must not regress Gate G2's `test_run_spend_throttles_seeded_40x_runaway`.

## Pre-mortem & adversarial review (2026-09-02 — findings folded into the contract above)

Scene: Sep 8, demo day, the approval loop broke on stage. Ranked by impact × blindness; each cause maps to a contract clause above.

1. **The double-run** — retry/re-drive touches a job a worker still holds → two workers, one render; the exactly-once guarantee (AC-S0.1) bypassed by the module meant to guard it. *Blindness trap: the chaos test's green gives false confidence — it never tested the retry path.* → Retry source-state rule (terminal-only, queue path).
2. **The slow leak** — the completion hook sits on every job's terminal write; one unguarded edge case (deleted approval, malformed args) starts failing *jobs* for *approval* reasons — invisible until many "random" job failures. → Hook isolation clause (projection, not truth; job state is the source of truth).
3. **The wrong assumption** — "idempotent = safe to re-drive." A stale crashed `resume` replayed after a newer human `pause` lets the machine overrule the human, on stage. → Sweeper order-safety clause (yield to newer decisions).
4. **The external surprise** — Grafana/SSE flakiness mid-demo (precedents: dead SA token, 401s, Tempo 401). An emission failure blocking a transition strands the state machine with the human watching. → Commit-first, emit-after clause.
5. **The structural cause** — deadline pressure erodes the one-writer rule ("just this once I'll set status inline"). → Single-writer grep-test clause.

**One thing to do before code:** the retry source-state rule — it is the only finding that can silently violate exactly-once, the project's proudest guarantee.

## Non-Goals
- Approver identity / Firebase sign-in (`decide_approval` still has no identity check) — stays deferred to H-3 / spec §7.2, unchanged by this design.
- A serialization/locking layer across different approvals touching the same resource beyond making the underlying write atomic — explicit V1 limitation, not silently dropped (see Concurrency).
- Migrating the supervisor's existing Grafana MCP autonomy-gated tools onto this executor.
- Building the full future command catalogue (Corrections, Relight, Camera Language, Revision Room commands) now — only what D-9/AL-1/retry/pause/resume need ships in V1; new stations register new commands later without touching this module's core.

## Not Doing (and Why)
- Not building a second queue/reconciler (Approach B) — unnecessary risk this close to the deadline when a proven one already exists.
- Not routing instant actions through the job worker (Approach A) — wrong semantics, pollutes the timeline board with non-media "jobs."
- Not requiring Spend Control's automatic pause to wait for human approval — that would defeat the feature's purpose (protecting budget *before* a human notices).

## Key Assumptions to Validate
- [ ] Firestore transaction latency for `pause_intake`/`resume_intake` and the approval state machine stays well under the sweeper's ~10s tick at demo scale — check during implementation, not just in theory.
- [ ] Sweeper tick (~10s) and staleness threshold (~30s) don't cause visible UI flicker or duplicate Grafana annotations under normal (non-crash) operation.
- [ ] Lease-expiry patience verified under a real subprocess kill (AC-S0.1 chaos pattern) with an approval watching: approval stays `acting` across reassignment, resolves exactly once on terminal state.

## Open Questions
(none — resolved above; anything not yet decided is captured under Non-Goals or Key Assumptions)
