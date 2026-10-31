# Pickups Vision Judge — EDD evidence (2026-10-02)

Gates (thresholds.yaml), computed over the EXPECTED-CLEAR subset of the
dataset (`backend/evals/datasets/pickups_vision_judgment.jsonl`):

- `pickups_vision_judge`  mean_vision_judge >= 4.0
- `pickups_artifact_rate` artifact_rate      <  0.08
- `pickups_vision_detection` mean_case_accuracy >= 0.8 (defective clips
  must be CAUGHT, clear clips must CLEAR)

## Results (2026-10-02, scripts/pickups_vision_judge_eval.py --runs 3)

All 3 runs PASS. Final run: mean_vision_judge 5.0, artifact_rate 0.0,
detection 6/6. Evidence: vision_judge_eval.jsonl + vision_judge_summary.json.

## What the metric found

The vision judge (1 billed Gemini look per clip, 6 frames @ 768px, fps=3)
catches SPATIAL/TEMPORAL render corruption that the deterministic flicker
meter cannot see — they are orthogonal meters:

- p05 (bg-swap): ghosting/double-exposure, invisible to flicker (0.0008).
- p07 (outpaint): severe morphing between takes; a 4-frame/512px sample
  FLIPPED between "clean" and "broken" — undersampling fools the judge.
  At 768px/fps=3 it is a stable 1.0, all frames flagged.
- p09 (relight): ghosting, invisible to flicker.
- p10 (relight): temporal jitter 2.0×3 runs — and indeed the flicker
  meter's own worst spike (0.017), 18× its clean siblings.
- p06, p08: clean 5.0/0.0 consistently.

4 of 6 D-5 fixture clips are genuinely defective renders; the flicker
gate (0.18) passes all of them. The vision judge is the missing QC bar.
