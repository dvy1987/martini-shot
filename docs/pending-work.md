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
| No production caller for the deliberation loop | Addressed, with scope gap | `backend/supervisor/team.py::maybe_deliberate` is wired from the worker terminal hook in `backend/api/app.py`; it fires for `failed`, `quarantined`, and `needs_human`. |
| Verifier argument was ignored by `run_budgeted_cycle` | Addressed at the function boundary | `backend/supervisor/budget_loop.py` forwards `verifier`; `tests/test_budget_loop.py::test_run_budgeted_cycle_forwards_verifier` covers veto-all behavior. |
| Nightly envelope could double-spend under concurrency | Addressed | `reserve_envelope` uses a Firestore transaction on `pc-budget-reservations`; concurrent reservation tests exist. |
| Settings writes lacked owner authentication | Addressed | `PATCH /api/v1/settings` now verifies `X-Google-ID-Token`, owner identity, and fails closed; route tests cover missing, invalid, non-owner, and owner cases. |
| Vetoed claims could leave their actions ranked | Addressed | `ProposedAction.required_evidence_refs` and `apply_verdict` filter action provenance; the ACT-gate eval includes unsupported-action hard gates. |
| Stand-ins could silently reach ACT dispatch | Addressed for production entry points | `run_budgeted_cycle` rejects missing routed specialists; stand-in cycles are marked non-actionable and demoted to propose-only. |
| H-1h–H-1j were only prose references | Addressed | The task table now contains executable rows for Continuity, Creative Finishing, and Visual QC, with datasets and gates. |
| H-1 evidence overstated the original shadow run | Corrected and disclosed | The 2026-09-05 evidence explicitly supersedes the overwritten 2026-09-04 artifact and reports 3/4 completed cycles honestly. |

## Remaining blockers and follow-up

### P-1 — Production path does not pass the real Verification Agent

`team.maybe_deliberate()` supplies the real specialist map but does not supply a
`verifier` callback. `run_budgeted_cycle()` therefore forwards `None`, and
`run_deliberation_cycle()` falls back to `_default_verifier`, which admits all
findings. The verification implementation exists and is tested, but the
running production path does not use it.

Impact: the ACT-gated production path can rank actions without the intended
independent verification pass.

Required completion evidence:

- Production team wiring passes the real Verification Agent.
- A production-path test proves a verifier veto prevents ranking and dispatch.
- A real propose-only run records the verifier verdict in `pc-deliberations`.

References: `backend/supervisor/team.py`, `backend/supervisor/deliberation.py`,
`backend/supervisor/budget_loop.py`.

### P-2 — Post Supervisor synthesis is still deterministic, not agentic

The specialist fan-out and Verification Agent are real Gemini calls, but the
default post-verification synthesis remains `_default_synthesizer()`:
fixed action ranking with `retry_job` given a hard-coded weight. There is no
production Post Supervisor Gemini call that reconciles specialist findings,
explains disagreement, and produces the final recommendation.

The separate `backend/supervisor/station_agents/orchestrator.py` is a real
batch station-chain planner, but it is not the Post Supervisor synthesis stage
described in Amendment A9.

Required decision/evidence:

- Either implement and EDD-gate a real synthesis agent, or explicitly amend
  the plan to define deterministic synthesis as the accepted supervisor
  behavior.
- If implemented, preserve deterministic schema validation, evidence
  citations, H-0 command validation, and single-call-site AI observability.

References: `backend/supervisor/deliberation.py`,
`backend/supervisor/station_agents/orchestrator.py`,
`docs/plans/2026-09-03-multiagent-supervisor-plan.md`.

### P-3 — Daily house-cap check is still a read/check/dispatch race

The nightly envelope has an atomic reservation ledger, but the daily
Spend-Control cap still uses a local `house_spent + cost` snapshot before
dispatch. Concurrent cycles can both pass that check and collectively exceed
the daily cap.

Required completion evidence:

- A shared transactional daily-cap reservation, or an equivalent
  transactionally enforced Spend-Control admission decision.
- A concurrent integration test proving the daily cap cannot be exceeded.

Reference: `backend/supervisor/budget_loop.py::run_budgeted_dispatch`.

### P-4 — Signal taxonomy is only partially runtime-wired

The routing table includes `stuck_lease`, `crash_recovered`, `qc_breach`,
`spend_breach`, `runaway`, `daily_budget`, and `dub_breach`, but the worker
terminal hook currently emits only `job_failed`, `quarantine`, and
`pickups_needs_human`.

Required completion evidence:

- Define which signals are intentionally deferred.
- Wire the required QC, Spend Control, lease-recovery, and dub signals to
  idempotent deliberation triggers.
- Prove each enabled trigger produces one durable cycle and does not duplicate
  on retries.

References: `backend/supervisor/case.py`,
`backend/supervisor/team.py`.

### P-5 — ACT mode has not been activated or observed live

The current-version ACT-gate receipt exists and the code fails closed without
it, but the receipt has deliberately not been written to the live
`pc-control/act-gate` document. A watched real ACT rehearsal remains pending.

Required completion evidence:

- Owner-approved live gate activation.
- A watched real run within the configured autonomy envelope (currently $20;
  separate remaining Stage 1a eval/demo spend is capped at $50 by A11).
- Grafana annotation, H-0 transition, actual cost reconciliation, and
  rollback/revert evidence.

This is an intentional release gate, not a code defect.

### P-6 — H-1 evidence wording still contains stale runtime claims

`docs/evidence/H-1/H-1g.md` correctly discloses the historical artifact
problem, but its runtime-readiness paragraph still says the budget loop has
“no production caller wired in `app.py` yet,” which is contradicted by the
current `team.py` and `app.py` implementation.

Required completion evidence:

- Refresh the paragraph to describe the current production wiring.
- Keep the honest limitations: ACT remains fail-closed and the latest full
  shadow run had 3/4 completed cycles with zero committed vetoes.

### P-7 — Fire-and-forget deliberation task lifecycle needs a clean outcome

`maybe_deliberate()` schedules a task and deliberately avoids blocking the
worker. Its exception path logs and re-raises inside the detached task.
Confirm that task failures are collected/observed by the runtime and that
shutdown cannot leave an unobserved exception or an in-flight guard entry.

Required completion evidence:

- Runtime test for failed deliberation task cleanup.
- Confirmed logging/metrics for cycle failure.
- Confirmed `_in_flight` cleanup on cancellation and shutdown.

## Current assessment

The project now has a real multi-agent implementation in two related layers:

1. A Post Supervisor specialist team with deterministic routing, parallel
   specialist calls, verification, H-0 dispatch, and Grafana/Firestore
   records.
2. A batch station orchestrator that plans the allowed station chain for each
   episode-language item.

The earlier review concerns are therefore mostly addressed. The system should
not yet be described as fully complete multi-agent autonomous orchestration
until P-1 and P-2 are resolved, and ACT mode should remain locked until P-3,
P-5, and the final runtime evidence are complete.
