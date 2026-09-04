# H-0b — Budgeted autonomy loop: dispatch mechanics (2026-09-04/05)

## What landed

`backend/supervisor/budget_loop.py` — the deliberation loop is a **caller of
H-0, not a second brain**. Ranked actions from the verified multi-agent
recommendation (Amendment A9 pipeline) dispatch down the list through the
SAME `ApprovalStateMachine`, self-approved as `system:supervisor_budget`.
No second state machine, no second audit trail, no second annotation writer.

Owner rulings encoded (plan 2026-09-02, unchanged):
- **Envelope is the sole quantity bound** (no action-count cap): default
  $20/night (`DEFAULT_ENVELOPE_MICROS`), one envelope per UTC calendar night
  shared across all cycles; the counter is the supervisor's narrower one
  (`supervisor_spend_micros`: real job `cost_micros` once the completion hook
  writes them, the loop's estimate otherwise). Human/Spend-Control spend is
  never counted toward it.
- **Daily house cap sits above the envelope**: a candidate that would breach
  `project_budgets()["daily_budget_micros"]` is refused even with envelope
  room left (Spend Control's own policy + spend math, not a duplicate).
- **Human-wins**: a target a human decided on tonight is skipped by the
  loop's own later ranking (order-safety spirit of the sweeper).
- **Adversarial money**: garbage/negative cost estimates are
  non-dispatchable (`coerce_cost_micros` — reuse, not reinvention).
- **Graceful degradation**: skipped candidates are never dropped — each
  carries its reason (`nightly envelope exhausted`, `daily house cap`,
  `human already decided this target tonight`, `no credible cost estimate`,
  `autonomy: propose_only`) and `ranked_for_morning_report: true` in the
  persisted decision table.
- **Settings round-trip, no redeploy**: the envelope lives in the
  `pc-control/budget` Firestore doc (`post_command_budget_micros`); a missing
  or invalid doc falls back to the owner default.
- **Autonomy toggle**: propose-only mode records the full ranked table for
  the morning report and dispatches nothing.

## Tests — 10/10 (`tests/test_budget_loop.py`, real Firestore, per-run collections)

1. ACT mode self-approves down the ranked list (`system:supervisor_budget`, resolved).
2. Envelope stops the list mid-way (sole bound; leftovers recorded).
3. Consecutive cycles the same night share one envelope.
4. Daily house cap halts spend even with envelope room (integration).
5. Garbage/negative/zero cost candidates are never dispatchable.
6. Human-wins: the loop cannot re-fight a human decision on the same target.
7. Propose-only: nothing dispatched, ranked proposals recorded.
8. Envelope round-trips from Firestore without redeploy (per-run control doc).
9. Supervisor spend counts only self-approved actions.
10. End-to-end signal-fired cycle: real stuck-job evidence → specialist
    finding → verification → leverage ranking → self-approved dispatch →
    decision table + `status: acted` persisted on `pc-deliberations/{cycle_id}`
    → Grafana-visible ranked table via annotation.

Gates: budget_loop suite 10/10, deliberation suite 9/9 (regression), ruff,
mypy clean.

## DoD status (plan §Definition of Done)

- [x] `pc-deliberations` docs from a real cycle — H-1g shadow run (4/4 real cycles) + test 10.
- [x] Ranked table as Grafana annotation — test 10 asserts the annotation call; production annotator is the Grafana MCP connector.
- [x] Envelope exhaustion end-to-end — tests 2/3 (leftovers persisted with reasons).
- [x] House cap halts with envelope room — test 4 (integration, Spend Control source of truth).
- [x] Settings round-trip — test 8.
- [x] Autonomy toggle demotes to propose-only — test 7.
- [x] Human-wins rule — test 6.
- [x] `deliberation_ranking_quality` clears threshold before ACT — 0.857 PASS (2026-09-04); **ACT remains gated on this suite**.

## Honest watch items

- The dispatch counter reconciles to real job `cost_micros` only after the
  completion hook writes them; slow-lane renders in flight count at their
  estimate until then (bounded by the envelope check at dispatch time).
- Cost-estimate realism is the known model-variance watch item from the
  ranking-quality eval (run-2 cost_realism flip); ACT-mode spend accuracy
  depends on it.
- A live ACT-mode night run (real $20 envelope) is intentionally NOT executed
  here — the eval gate passed, but the first real ACT night belongs to the
  demo rehearsal window with the owner watching, per the plan's go-live gate.
