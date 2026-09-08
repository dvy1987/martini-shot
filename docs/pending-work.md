# Pending Work — Multi-Agent Recon

Updated: 2026-09-08

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

**Addressed (stale as of 2026-09-08).** `team.maybe_deliberate` passes
`production_verifier(settings)`. Test:
`test_maybe_deliberate_fires_one_act_cycle_per_job` asserts a callable
verifier on the production cycle.

### P-2 — Post Supervisor synthesis is still deterministic, not agentic

**Addressed (stale as of 2026-09-08).** Production passes
`production_synthesizer(settings)` (live Gemini Post Supervisor). The finishing
orchestrator (impact, dependencies, budget) is a separate brain and sat its
live 3×0.8 exam on 2026-09-08 (`docs/evidence/finish-loop/rank_eval_summary.json`,
`spend_pricing_summary.json`).

### P-3 — Daily house-cap check is still a read/check/dispatch race

**Addressed (stale as of 2026-09-08).** `reserve_daily_cap` is transactional.
Test: `test_parallel_daily_cap_reservations_cannot_overspend`.

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

### P-5 — Ranked night-envelope spend was not turned on in live Firestore

**Addressed (2026-09-08, owner demanded).** Ranking eval already passed 3×1.0.
The receipt is now written to `pc-control/act-gate` on app boot
(`ensure_budgeted_spend`). Default settings are `act`: rank, then spend the
$20 night envelope down that list. `propose_only` remains the kill switch.

### P-6 — H-1 evidence wording still contains stale runtime claims

**Addressed (2026-09-08).** Worker hook is in `app.py`. Default is ranked
spend inside the night envelope. The 2026-09-05 shadow run still had 3/4
completed cycles.

### P-7 — Fire-and-forget deliberation task lifecycle needs a clean outcome

**Mostly addressed.** `maybe_deliberate` uses `add_done_callback` and clears
`_in_flight` in `finally`. A dedicated fail/shutdown test is still missing.

Required completion evidence:

- Runtime test for failed deliberation task cleanup.

## Current assessment

The finishing boss and the Post Supervisor verifier/synthesis path are in the
product. Live rank exam (2026-09-08): 0.9 / 0.9 / 0.8. Live spend-pricing exam:
1.0 × 3. Live one-retry exam: 1.0 × 3 (`docs/evidence/supervisor-retry/`).
Default autonomy is **rank, then spend the night envelope**. The
ranking-quality receipt is written to `pc-control/act-gate`. `propose_only`
is the kill switch. The supervisor may **add or remove a take from the
cut** inside that envelope. Worker still only fires deliberation on failed /
quarantined / needs_human (P-4, deferred).
