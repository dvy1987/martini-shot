# Pending Work — Multi-Agent Recon

Updated: 2026-09-07

This document records unresolved items from the earlier implementation review.
It is intentionally separate from the approved task plans: it is a readiness
and reconciliation list, not a replacement plan. Amendment A11 (2026-09-07)
makes Stage 1 plus the full non-stretch Stage 1a roadmap the demo release;
the items below must be resolved or honestly disclosed within that release.

## Earlier review findings — status

| Finding | Status | Evidence |
|---|---|---|
| No production caller for the deliberation loop | Addressed | `backend/supervisor/team.py::maybe_deliberate` is wired from the worker terminal hook in `backend/api/app.py`; it fires for enabled terminal signals and uses production verifier/synthesis callbacks. |
| Verifier argument was ignored by `run_budgeted_cycle` | Addressed at the function boundary | `backend/supervisor/budget_loop.py` forwards `verifier`; `tests/test_budget_loop.py::test_run_budgeted_cycle_forwards_verifier` covers veto-all behavior. |
| Nightly envelope could double-spend under concurrency | Addressed | `reserve_envelope` uses a Firestore transaction on `pc-budget-reservations`; concurrent reservation tests exist. |
| Daily house cap could double-spend under concurrency | Addressed | `reserve_daily_cap` uses a project/day Firestore reservation document before H-0 dispatch; the reservation is reconciled to actual cost. |
| Settings writes lacked owner authentication | Addressed | `PATCH /api/v1/settings` now verifies `X-Google-ID-Token`, owner identity, and fails closed; route tests cover missing, invalid, non-owner, and owner cases. |
| Vetoed claims could leave their actions ranked | Addressed | `ProposedAction.required_evidence_refs` and `apply_verdict` filter action provenance; the ACT-gate eval includes unsupported-action hard gates. |
| Stand-ins could silently reach ACT dispatch | Addressed for production entry points | `run_budgeted_cycle` rejects missing routed specialists; stand-in cycles are marked non-actionable and demoted to propose-only. |
| H-1h–H-1j were only prose references | Addressed | The task table now contains executable rows for Continuity, Creative Finishing, and Visual QC, with datasets and gates. |
| H-1 evidence overstated the original shadow run | Corrected and disclosed | The 2026-09-05 evidence explicitly supersedes the overwritten 2026-09-04 artifact and reports 3/4 completed cycles honestly. |

## Remaining blockers and follow-up

### P-1 — Production path does not pass the real Verification Agent — Addressed

`team.production_verifier()` now passes the real `verification.verify()` call
to every signal-fired cycle. The existing hard-filter and verifier forwarding
tests cover veto handling; a real propose-only run remains release evidence.

### P-2 — Post Supervisor synthesis is still deterministic, not agentic — Addressed

`backend/supervisor/agents/post_supervisor.py` performs the production
Gemini synthesis through `run_agent_call`. The model receives only verified,
already-ranked candidates and can only partition their indexes; code rejects
invented, duplicated, or dropped actions before H-0 sees them.

### P-3 — Daily house-cap check is still a read/check/dispatch race — Addressed

The budget loop now reserves the project/day allowance transactionally before
the envelope and H-0 dispatch. An envelope refusal refunds that daily
reservation; dispatch reconciliation adjusts it to actual cost.

### P-4 — Signal taxonomy is only partially runtime-wired — Explicitly deferred

The routing table includes `stuck_lease`, `crash_recovered`, `qc_breach`,
`spend_breach`, `runaway`, `daily_budget`, and `dub_breach`, but the worker
terminal hook currently emits only `job_failed`, `quarantine`, and
`pickups_needs_human`.

`DEFERRED_SIGNAL_REASONS` now names every route not produced by the terminal
hook and its missing durable source. Enabled terminal signals remain
idempotent per job; adding a source requires removing the corresponding
deferral and adding its durable-trigger test.

References: `backend/supervisor/case.py`,
`backend/supervisor/team.py`.

### P-5 — ACT mode has not been activated or observed live

The current-version ACT-gate receipt exists and the code fails closed without
it, but the receipt has deliberately not been written to the live
`pc-control/act-gate` document. A watched real ACT rehearsal remains pending.

Required completion evidence:

- Owner-approved live gate activation.
- A watched real run within the configured autonomy envelope (currently $20;
  separate remaining Stage 1a eval/demo spend is capped at $100 by A11).
- Grafana annotation, H-0 transition, actual cost reconciliation, and
  rollback/revert evidence.

This is an intentional release gate, not a code defect.

### P-6 — H-1 evidence wording still contains stale runtime claims — Addressed

The H-1g runtime wording now reflects the worker-hook caller while retaining
the unactivated ACT gate and the honest 3/4 shadow-run limitation.

### P-7 — Fire-and-forget deliberation task lifecycle needs a clean outcome — Addressed

The scheduled task now has a completion callback that consumes and logs
failures/cancellation, while `_cycle` always releases its in-flight key in
`finally`. No new telemetry name was invented; the existing error log and
parent cycle span remain the observable record.

## Current assessment

The project now has a real multi-agent implementation in two related layers:

1. A Post Supervisor specialist team with deterministic routing, parallel
   specialist calls, verification, H-0 dispatch, and Grafana/Firestore
   records.
2. A batch station orchestrator that plans the allowed station chain for each
   episode-language item.

The earlier review concerns are therefore mostly addressed. The system should
not yet be described as fully complete multi-agent autonomous orchestration
until its release evidence is captured. ACT mode remains locked until P-5 and
the final live runtime evidence are complete.
