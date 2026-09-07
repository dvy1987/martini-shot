# Eval pipeline: walk-away leftover ranking + spend pricing

## System
Cleanup jobs (loudness then pickups) are rails. After every clip is through
pickups, leftover agents watch in upload order. Spend prices each
`needs_work` proposal. Orchestrator ranks with spine notes.

## Layers
1. Deterministic: inspect schema, `rank_payload` always includes
   `orchestrator_spine`, spend parse ignores invented ids, checksum handoff.
2. Statistical: `finishing_rank_quality` and `spend_pricing_judgment` mean
   accuracy >= 0.8 over 3 live runs.
3. LLM-as-judge: production model is the exam (match human labels).

## Scripts
- `python scripts/spend_pricing_eval.py --runs 3` (text, cheap)
- `python scripts/finishing_rank_eval.py --runs 3` (print cost; `--yes` over $5)

Evidence: `docs/evidence/finish-loop/`
