# Readiness and Reconciliation

**Updated:** 2026-09-08

This is the current release-readiness record. It is not a replacement for the approved implementation plans. It exists to keep judge-facing claims honest by separating addressed findings, active limitations, and historical review notes.

## Current release assessment

Martini Shot has two real production paths:

1. The **walk-away finishing path** starts from the Timeline UX, runs the ordered media workflow, gathers specialist proposals, prices them, invokes the ADK finishing orchestrator, dispatches budgeted jobs, and refreshes final references.
2. The **Post Supervisor path** investigates failed, quarantined, and needs-human terminal cases with real specialist investigators, a Verification Agent, a Gemini synthesis agent, the approval state machine, and bounded autonomy backed by Grafana annotations or incidents.

The product is suitable for a controlled demo rehearsal. The final hackathon recording should still be made from the running deployment after verifying the full upload-to-worklist-to-Grafana path.

## Addressed findings

| Finding | Current status | Evidence |
|---|---|---|
| No production caller for deliberation | Addressed | `backend/supervisor/team.py::maybe_deliberate` is wired from the worker terminal hook in `backend/api/app.py`. |
| Production verifier was missing | Addressed | `production_verifier(settings)` is passed into `run_budgeted_cycle`; production-path tests assert the callable is present. |
| Post Supervisor synthesis was deterministic | Addressed | `production_synthesizer(settings)` calls the Gemini Post Supervisor synthesis implementation. |
| Nightly envelope could double-spend | Addressed | `reserve_envelope()` uses a transactional reservation ledger. |
| Daily house-cap check raced | Addressed | `reserve_daily_cap()` uses a transactional reservation ledger with concurrent tests. |
| ACT gate receipt was not active | Addressed | App boot calls `ensure_budgeted_spend()`, writes the ranking-quality receipt, and defaults autonomy to `act`. |
| Stand-ins could silently reach ACT dispatch | Addressed for production entry points | The production path supplies complete specialist maps, verifier, and synthesizer. Missing routed specialists are rejected. |
| H-1h through H-1j were prose only | Addressed | Executable station agents, datasets, gates, and evidence exist for Continuity, Creative Finishing, and Visual QC. |
| H-1 evidence overstated a historical shadow run | Corrected | Historical evidence now discloses the incomplete run rather than presenting it as fully complete. |

## Active limitations

### P-4: Signal taxonomy remains partially runtime-wired

The routing vocabulary includes `stuck_lease`, `crash_recovered`, `qc_breach`, `spend_breach`, `runaway`, `daily_budget`, and `dub_breach`. The current worker terminal hook intentionally triggers production deliberation for:

- `failed` → `job_failed`
- `quarantined` → `quarantine`
- `needs_human` → `pickups_needs_human`

The other signal types remain deferred because their durable event sources are not yet wired. The README and Grafana notes must not imply that every taxonomy entry automatically creates a supervisor cycle.

### P-7: Detached deliberation failure test

`maybe_deliberate()` observes detached task completion with a callback and clears `_in_flight` in a `finally` block. A dedicated runtime test for failed-task cleanup during shutdown remains missing. This is a reliability-test gap, not an indication that the production path silently ignores every failure.

### Known finishing-rank miss

The live finishing-rank evidence clears the mean threshold with runs of `0.9`, `0.9`, and `0.8`. The `fr-05` case still fails because the model placed Extend before Loudness. The runtime house order remains enforced by the finishing loop and dependency sequence, but the evaluation miss should remain disclosed.

### Full gate coverage

The repository’s full `make check` gate is still below the project’s 90% coverage target. Do not describe the repository as having a fully green release gate until the coverage gap is closed and the full gate is rerun.

## Current live evidence

| Suite | Current evidence |
|---|---|
| Spend pricing | Three live runs at 1.0. |
| Finishing rank | Three live runs at 0.9, 0.9, and 0.8. |
| Supervisor retry-once | Three live runs at 1.0. |
| Ingest understanding | Live transcript and scene-understanding evidence. |
| Stage 1a lookers | Live evidence for Extend, Corrections, Relight, Coverage, Camera Language, Continuity, Creative Finishing, Visual QC, Revision Room, and related looker paths. |
| Omni media quality | Passing suites record `render_model`, `omni_fallback`, and `omni_error`; Veo fallback rows are not counted as Omni passes. |

## Demo go/no-go checklist

Before recording the final three-minute video, verify on the actual hosted deployment:

- The Timeline loads and the backend health endpoint is reachable.
- Two or three clips can be uploaded in a deliberate order.
- Finish accepts a constrained budget and starts an asynchronous worklist.
- Ingest understanding produces a scene and a truthful spoken-word field.
- Loudness and pickups run for every clip before optional looks begin.
- The seven later-phase lookers produce real notes or honest empty rows.
- Spend pricing produces a live result.
- The ADK ranker produces a reason, order, and dependencies.
- One real selected station job completes.
- At least one proposal remains waiting or paused because of the budget.
- Run Pulse displays Grafana-backed health, burn, ETA, or intervention evidence.
- The final references contain originals plus only passed artifacts.

## Historical notes

Older handoffs and plans may say that live ranking, spend pricing, or the act gate are pending. Those statements refer to earlier repository states. The current handoff at `docs/memory/agent-handoffs.md` and the evidence files under `docs/evidence/finish-loop/` are the current references. Historical plans remain useful for provenance but should not be used as current status summaries.
