# Eval Pipeline: D-9 / D-10 inspect lookers (must / nice / leave)

## System Overview — billed clip watch, maturity stage 3
`finish_extend` and `finish_corrections` look at the source clip and stamp
one bucket. Critical output: inspect JSON (`status`, `impact`, `kind`,
optional draft proposal). Orchestrator only sees `needs_work`. This
pipeline is the looker exam, not the Omni render exam.

## Evaluator Stack
### Layer 1 — Deterministic
- Inspect schema (`ok` has no proposal; `needs_work` has a station_job)
- `jobs_from_notes` skips `ok`
- Rank `_candidates` skips `ok` / empty
- Quality tape is `original-probes/` (not gradient/BBB)

### Layer 2 — Statistical
- `finishing_extend_corrections_inspect.mean_case_accuracy >= 0.8`
- Three consecutive live runs (same bar as other finishing EDD)

### Layer 3 — LLM-as-judge
- Production model watches frames: `gemini-3.7-flash` via `run_inspect`
- Labels live in `finishing_inspect_judgment.jsonl` (fi-03, fi-07, fi-09–fi-13)
- Rubric: `docs/evals/2026-09-07-extend-corrections-inspect-rubric.md`
- No second judge model — match to human labels on the watch

## Checkpoints
1. Build labeled clips from original GCS tape (`ensure_inspect_clips`).
2. Extract frames (and wav only if the station is loudness).
3. Billed `run_inspect` — same path as the product ADK tool.
4. Score status/impact/kind. Empty on a clip with frames is a miss.

## Dataset
| Split | Size | Description | Source |
|---|---|---|---|
| Extend must | 1 | Kitchen cut at 2.2s | ffmpeg from original kitchen |
| Extend nice | 1 | Full kitchen, optional air | original kitchen |
| Extend leave | 1 | Sitting two-shot already lands | original table-cup |
| Corrections must | 2 | CLOSED overlay; OPNN chalkboard | cafe+drawtext; original chalkboard |
| Corrections nice | 1 | Paper cup | original table-cup |
| Corrections leave | 1 | Florist, nothing to rewrite | original florist |
| Known-bad (full suite) | 1 | Unwired coverage stays empty | fi-06 |

## CI/CD Integration
- Pre-merge: `make eval-check` (threshold structure) + unit tests
- DoD: `python scripts/finishing_inspect_eval.py --stations extend,corrections --runs 3`
- Full roster inspect remains `finishing_inspect_judgment` (bar 0.8)

## Baselines and Alerts
- Prior full-suite live run: 0.75 / 0.75 / 0.75 (failed). Mid-cut was
  mislabeled as improvement; that label is now defect.
- Regression: any 3-run mean < 0.8, or leave-it rows proposing work.

## Cost Estimate
- 7 billed looks × 3 runs ≈ $3.15 printed (150k micros/look). C-7.2:
  print; `--yes` over $5. Owner inspect cap $20.

## Recommended Tools
- Product path: `backend/supervisor/inspect_impl.py::run_inspect`
- Evidence: `docs/evidence/finish-loop/inspect_eval_corrections_extend_*`
