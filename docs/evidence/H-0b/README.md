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
- [x] Settings round-trip — test 8, plus the product route: `GET/PATCH
  /api/v1/settings` (tests/test_settings_route.py 4/4) reads/writes the same
  `pc-control/settings` doc the loop reads at cycle time; FE `Settings`
  contract aligned to the honest two-mode toggle (`propose_only` | `act`).
- [x] Autonomy toggle demotes to propose-only — test 7.
- [x] Human-wins rule — test 6.
- [x] `deliberation_ranking_quality` clears threshold before ACT — reworked
  per the 2026-09-05 ACT-gate review and now **3/3 independent runs PASS at
  1.0 end-to-end action accuracy** with hard gates clean
  (`ranking_quality_summary.json` + `ranking_quality_receipt.json`, gate
  version 1).

## ACT-gate review fixes (2026-09-05, review-driven)

1. **Action provenance contract**: every action carries
   `supporting_evidence_refs`; the verdict filter discards exactly the
   actions whose required claims were vetoed (provenance-less actions depend
   on the whole finding — any veto drops them). An unsupported action can no
   longer survive a veto (previously `apply_verdict` copied every action).
2. **Real ACT-gate eval**: deterministic routing cases are scored separately
   (`routing_ok`) and excluded from the judgment denominator; every judgment
   case runs the real verifier → provenance filter → leverage rank and is
   scored on final command AND target args, including a required-abstention
   case; hard gates (unsupported-action survival, reversibility, spend-class
   cost positivity, abstention) are run-killers, never averaged away; THREE
   independent runs are reported verbatim.
3. **Fail-closed activation**: `act` in settings alone never unlocks
   spending — `run_budgeted_dispatch` requires a CURRENT-version passing
   receipt in `pc-control/act-gate` (`ACT_GATE_VERSION=1`,
   `act_gate_passed`); without it the loop demotes to propose-only with a
   visible reason. The receipt file produced by the eval is evidence;
   writing it into `pc-control/act-gate` (activation) remains a deliberate,
   separate step — NOT done here. ACT stays locked until the demo
   rehearsal.
4. **Deterministic action-correctness gate** (beyond the review minimum):
   `REQUIRED_ACTION_ARGS` — an action lacking its command's target keys is
   rejected at the finding-schema gate; the case's own subject
   job/station is bound structurally (never model guesswork), so a
   malformed action can neither rank nor dispatch.
5. **Evidence honesty**: H-1g's 4-cycle claim was not supported by the
   committed artifacts (a single-case re-run had overwritten the JSONL);
   corrected and superseded by the 2026-09-05 full run, recorded verbatim
   including the abstentions and the gate refusal
   (`docs/evidence/H-1/H-1g.md`).

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
