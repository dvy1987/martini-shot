# H-1d — Spend Guardian agent

TDD + EDD per plan §6 step 3. Commit: see `git log -1 --format=%H`.

## What was built

- `backend/supervisor/agents/spend_guardian.py`
  - `read_spend_state` reads REAL Spend Control state: the station's own `policies.yaml` caps (`max_cost_micros_per_job`, `max_retries`, `runaway_requeues`), project budgets, and job rows aggregated through the SAME helpers the station uses (`project_spend_micros`, `station_policy`, `project_budgets`) — live via `store.list_where`, or supplied directly for eval/tests. Absence of jobs is data, not invention.
  - Adds the assessment dimension to the validated finding schema: `assessment` ∈ {reasonable, underpriced, over_budget}.
  - Prompt carries the real caps, the real daily aggregation, and the plan under review; ground rules define underpricing against the REAL history (attempts vs max_retries, runaway_requeues with unchanged errors, remaining cap vs estimate, repeated burn without error change) and require counter-proposals from the H-0 registry only.
  - `investigate` → single instrumented call site (`specialist.spend_guardian` span, `gen_ai.agent.name=spend_guardian`).

## TDD evidence

`tests/test_spend_guardian.py` — 11 tests: real policy caps + real budgets flow into the state; station-scoped aggregation through the real detect helper (other stations excluded); happy-path assessment; 4 invalid-assessment rejections; invented-command rejection; foreign-case rejection; prompt carries the real per-job cap / daily budget / runaway key / proposal estimate / assessment vocabulary; wiring test (persona, span, schema, real state in prompt).

## EDD evidence (live run, real Gemini, real cost — C-1.1)

`spend_guardian_eval.jsonl` + `spend_guardian_summary.json` (this directory):

- **mean_assessment_accuracy = 1.0 (5/5), threshold 0.8 → PASS.** Real `gemini-3.7-flash` (thinking HIGH) via the single instrumented site.
- Correct on all five judgment classes: retry after attempts exhausted → underpriced; sensible retry with margin → reasonable; daily budget breached → over_budget; runaway loop (8 requeues, 9.8M micros burned) asking for another cycle → underpriced; cheap transient retry → reasonable.

## Full gate at commit

ruff ✓ (check + format), mypy ✓ (70 files), thresholds.yaml ✓ (6 suites), integrity C-1.2 ✓, harness drift ✓. Full pytest run: 249/250 passed, coverage 91.7%; the single failure (`test_sweeper_redrive_yields_to_newer_decision_on_same_target`) was a transient Firestore `400 Invalid transaction` during a heavily throttled run (the suite took 3.4× its usual wall time) — re-run in isolation: **8/8 green**.
