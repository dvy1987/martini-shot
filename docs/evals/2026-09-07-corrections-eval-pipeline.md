# Eval Pipeline: D-10 Corrections

## System Overview — bounded Omni edits through H-0, maturity stage 3
The Corrections Agent judges a brief (propose `correct_shot` or abstain).
H-0 enqueues a lease-queue Omni `edit` job. Flicker QC (0.02) gates the
DRAFT alternate. Critical outputs: agent decision, job artifact, flicker
score, alternate `op=correction`. Empty, locked, and injective briefs are
hard-gated in code before any render.

## Evaluator Stack
### Layer 1 — Deterministic
- Explicit intent required (empty/whitespace → 400 / abstain)
- Locked cut refused (409 / H-0 locked-target guard)
- Prompt-injection markers abstain (`ignore previous`, `jailbreak`, …)
- Alternate is never an overwrite; status starts `draft`
- Flicker gate: each output `< 0.02` or job lands `needs_human`

### Layer 2 — Statistical
- `corrections_quality.mean_output_flicker < 0.02` (thresholds.yaml)
- Per-shot max flicker must also clear 0.02 (one breach fails the run)
- Cost recorded as integer micros (360p draft table)

### Layer 3 — LLM-as-judge
- Live `gemini-3.7-flash` Corrections Agent on labeled briefs
- `corrections_judgment.mean_case_accuracy >= 0.8`
- Dataset includes happy path, empty, locked, injection, protected-subject
- Known-bad rows (empty / locked / injection) must abstain

## Checkpoints
1. Hard-gate the brief (no LLM, no Omni) — halt on abstain.
2. Agent judgment (optional on HTTP via `consult_agent`) — halt on abstain.
3. H-0 approve → `cor-<approval_id>` enqueue.
4. Omni edit + flicker QC → alternate. Fail loud; never mock.

## Dataset
| Split | Size | Source |
|---|---|---|
| Happy path | 2 | `corrections_judgment.jsonl` cor-01, cor-05 |
| Edge / known-bad | 3 | empty, locked, missing intent |
| Adversarial | 1 | prompt-injection |
| Quality holdout | 3 shots × 3 runs | GCS `probes720/` synthetic-drift-01/02 + synthetic-mark-03 (C-1.3). Natural BBB recitation-refused Omni edit; recorded in `docs/evidence/D-10/`. |

Project convention is a compact labeled JSONL (not 30–50/split) because
each live Gemini/Omni call is billed against the remaining eval envelope.

## CI/CD Integration
- Pre-merge: `make check` (structure of thresholds.yaml, TDD, no live Omni)
- Nightly / task DoD: `scripts/corrections_judgment_eval.py --runs 3` then
  `scripts/corrections_quality_eval.py --runs 3` (print cost; `--yes` if >$5)
- Production: Grafana job annotations + `pc_job_duration_seconds` / cost

## Baselines and Alerts
- Judgment baseline: ≥0.8 mean accuracy across 3 consecutive runs
- Quality baseline: mean and max flicker < 0.02 on all completed renders
- Regression: any run below threshold, or a render without an alternate

## Cost Estimate
- Judgment: ~6 flash calls × 3 runs ≈ $0.06
- Quality: ~3 Omni 360p drafts × 3 runs ≈ $2.10 (C-7.2 print + `--yes` over $5)
