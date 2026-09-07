# Spec Crosscheck: walk-away finishing (2026-09-07)

Verdict: **PASS for this slice** (Cursor plan + spec addendum; not copied into `docs/plans/`).

## Inputs
- Constitution `docs/constitution.md@1`
- Spec addendum in `docs/specs/2026-08-26-post-command-feature-spec.md` (walk-away finishing, 2026-09-07)
- Cursor plan `Autonomous worklist loop-989cd6bc`

## Checks

| ID | Check | Verdict |
|----|-------|---------|
| C-1 | No mocks; empty ≠ fake all-good | PASS — InspectNote empty is blank; inspect uses live Gemini |
| C-3 | EDD bars before inspect/rank LLM | PASS — thresholds.yaml `finishing_inspect_judgment` + `finishing_rank_quality` ≥ 0.8; datasets + known-bad empty/invent-station |
| C-6.5 | No LLM on HTTP >30s | PASS — POST `/finish` returns inspecting worklist; loop in background thread |
| C-6.4 | Money integer micros | PASS — budget_micros, cost_estimate_micros |
| C-7.2 | Print estimate | PASS — inspect estimate printed before billed looks |
| C-4 | ADK team metered via otel_ai look tools | PASS — station tools call `run_inspect` → `run_agent_call` |
| AL-1 | Originals kept | PASS — assemble_final always includes original_refs |

## Gaps (not blockers for this slice)
- Live inspect 3-run eval not yet executed (billed). Rank eval 3/3 at 1.0 in `docs/evidence/finish-loop/`.
- ADK Runner live path is wired; first production invoke is wall-clock on Vertex.
