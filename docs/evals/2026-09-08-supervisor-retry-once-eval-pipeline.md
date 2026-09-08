# Eval pipeline: supervisor one-retry

## System

Post Supervisor specialists + verifier + synthesis already run on terminal
failure. `retry_once` autonomy then admits **at most one** `retry_job`
through H-0. Full ACT stays locked.

## Layers

1. Deterministic: `admit_retry_once` hard gates (pytest).
2. Statistical: live `supervisor_retry_judgment` mean accuracy >= 0.8 × 3.
3. LLM-as-judge: production Gemini is the exam on fuzzy rows.

## Script

`python scripts/supervisor_retry_eval.py --runs 3`

Evidence: `docs/evidence/supervisor-retry/` (2026-09-08 live: 1.0 × 3).
