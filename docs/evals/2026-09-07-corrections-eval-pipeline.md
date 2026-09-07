# Eval Pipeline: D-10 Corrections

## System Overview — bounded Omni edits through H-0, maturity stage 3
The Corrections Agent (or the walk-away `finish_corrections` looker) names
a bounded intent. H-0 enqueues a lease-queue Omni `edit` job. Flicker QC
(0.02) gates the DRAFT alternate. Critical outputs: agent decision, Omni
artifact, flicker, alternate `op=correction`. Empty, locked, and injective
briefs are hard-gated in code.

## Evaluator Stack
### Layer 1 — Deterministic
- Explicit intent required
- Locked cut refused
- Prompt-injection markers abstain
- Alternate is never an overwrite; status starts `draft`
- Flicker gate `< 0.02`
- Quality tape must be `original-probes/` (not gradient/BBB)

### Layer 2 — Statistical
- `corrections_quality.mean_output_flicker < 0.02`
- `corrections_omni_primary.omni_render_rate >= 1.0`

### Layer 3 — LLM-as-judge
- Live `gemini-3.7-flash` on labeled briefs
- `corrections_judgment.mean_case_accuracy >= 0.8`
- Dataset covers signage, prop removal, on-set graphic, plus known-bad abstentions

## Checkpoints
1. Hard-gate the brief.
2. Agent judgment.
3. H-0 approve → `cor-<approval_id>`.
4. Omni edit on an **original clip that still has the deficit**. If Omni
   cannot be called, stop. Do not pass on Veo or gradients.

## Dataset
| Split | Size | Source |
|---|---|---|
| Happy path | 4 | signage, prop_removal, on_set_graphic, lettering replace |
| Known-bad | 4 | empty, locked, injection, missing intent |
| Quality holdout | 3 original kinds × 3 runs | café-sign, table-cup, chalkboard-opnn on `original-probes/` |

## CI/CD Integration
- Pre-merge: `make check` (thresholds structure, TDD, no live Omni)
- Task DoD: `scripts/corrections_judgment_eval.py --runs 3` then
  `scripts/corrections_quality_eval.py --runs 3`

## Cost Estimate
- Judgment: ~8 flash calls × 3 runs ≈ $0.10
- Quality: ~3 Omni 360p drafts × 3 runs ≈ $2.10; plus one Omni start clip
  if `chalkboard-opnn.mp4` is missing
