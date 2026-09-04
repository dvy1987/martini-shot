# H-1c — Delivery QC agent

TDD + EDD per plan §6 step 3. Commit: see `git log -1 --format=%H`.

## What was built

- `backend/supervisor/agents/finding_schema.py` — shared deterministic validation for ALL specialists: non-empty claims with evidence refs, bounded confidence, actions restricted to the live H-0 command registry, explicit boolean reversibility, non-negative integer cost, case_id echo. `reliability_investigator.py` refactored onto it (12/12 tests still green) — no per-agent duplication as H-1d/e land.
- `backend/supervisor/agents/delivery_qc.py`
  - `read_qc_report` reads the REAL D-2/D-4 output off the job doc (`result.delivery` with destination/verdict/violations rule IDs + `result.lufs`); absence recorded explicitly, never invented.
  - Adds the DoD's judgment dimension to the finding schema: `classification` ∈ {genuine_breach, borderline_pass, pass}, validated by the same fail-loud gate.
  - Prompt carries the REAL evaluator report + the REAL D-2 tolerance (±1.0 LU) and the ground rule: the evaluator's verdict table is authoritative — the agent interprets, NEVER overrides.
  - `investigate` → single instrumented call site (`specialist.delivery_qc` span, `gen_ai.agent.name=delivery_qc`).

## TDD evidence

`tests/test_delivery_qc.py` — 12 tests: real Firestore read of a run_delivery-shaped job doc; absence recording; happy-path classification; 4 invalid-classification rejections; missing-claims rejection; invented-command rejection; foreign-case rejection; prompt carries the real report/rule IDs/tolerance/classification vocabulary; wiring test proving the REAL report reaches the model with the right persona/span/schema.

## EDD evidence (live run, real Gemini, real cost — C-1.1)

`delivery_qc_eval.jsonl` + `delivery_qc_summary.json` (this directory):

- **mean_classification_accuracy = 1.0 (5/5), threshold 0.8 → PASS.**
- The runner runs the REAL `evaluate_delivery` chain (D-2 verdict table + D-4 profile evaluator) over the seeded pack inputs — the agent judges the same artifacts the station produces, nothing fabricated.
- All five judgment classes correct: clear loudness breach (DEL-006), near-threshold pass (0.8 LU of 1.0 → borderline_pass), clean pass (0.3 LU), marginal breach (1.2 LU — rule table wins, classified breach), structural missing-captions breach (DEL-007).

## Full gate at commit

ruff ✓ (check + format), mypy ✓ (69 files), thresholds.yaml ✓ (5 suites), integrity C-1.2 ✓, harness drift ✓, pytest **239 passed, coverage 91.70%** (gate ≥90%).
