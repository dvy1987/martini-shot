# Eval Pipeline: D-9 Extend (Omni primary)

## System Overview — scene-extend through H-0, maturity stage 3
The operator (or an agent) proposes `extend_shot`. H-0 enqueues a lease-queue
job. Omni extends first; **if Omni fails the product falls back to Veo**
(correct operator behavior). Flicker QC (0.02) gates a DRAFT alternate.
Evals still require Omni: a Veo-finished row is **not** an eval pass.

## Evaluator Stack
### Layer 1 — Deterministic
- Source must be `gs://`
- Approval resolves; job id `ext-<approval_id>`
- Alternate is `draft`, never an overwrite
- `omni_fallback` must be false; `render_model` must be Omni
- Flicker gate: each output `< 0.02` or the job is `needs_human` (eval fail)

### Layer 2 — Statistical
- `extend_quality.mean_output_flicker < 0.02`
- `extend_omni_primary.omni_render_rate >= 1.0`

### Layer 3 — LLM-as-Judge
- Live `gemini-3.7-flash` Extend QC agent (`extend_qc_judgment` ≥ 0.8)
- Prompt now includes `omni_fallback` / `omni_error`
- Sampling: 100% of QC jobs (small n); not 100% of production traffic

## Checkpoints
1. Generate an **original** start clip that still has the extend deficit.
2. If Omni cannot be called, stop and tell the owner.
3. H-0 approve → Omni `run_extend`.
4. If Omni fails and Veo succeeds, **fail the suite** and tell the owner.
5. Flicker + draft alternate.

## Dataset
| Split | Size | Source |
|---|---|---|
| Quality holdout | 1 new original clip per run | Omni text-to-video (florist / café-like scenes with a continue-rolling deficit) |
| Known-bad (gate tests) | 2 | Veo-fallback record; flicker 0.03 record (`tests/test_extend.py`) |
| Judgment | `extend_qc_judgment.jsonl` | separate A10-4 suite |

BBB / gradient tapes are not the owner-accepted quality set.

## CI/CD Integration
- Pre-merge: `make check` (thresholds structure, TDD, no live Omni)
- Task DoD: `.venv\Scripts\python.exe scripts\extend_eval.py` (print cost; `--yes` over $5)

## Baselines and Alerts
- Quality: mean and per-shot flicker < 0.02 **and** Omni rendered every row
- Regression: any Veo-fallback “success”, or a render without a draft alternate

## Cost Estimate
- 1 Omni 8s generate + 1 Omni 7s extend ≈ **$1.50** at the 720p draft table
