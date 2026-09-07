# Ingest understand live eval (2026-09-07)

Gemini 3.7 Flash watches labeled clips (audio + frames) after a file-open
check. Two bars in `thresholds.yaml`: `ingest_transcript_judgment` and
`ingest_scene_judgment`, both mean_case_accuracy >= 0.8.

## Result

| Suite | Score | Gate |
|---|---|---|
| ingest_transcript_judgment | **0.958** | >= 0.8 |
| ingest_scene_judgment | **1.00** | >= 0.8 |

8 cases × 3 runs. Cost **$0.08**. Pass.

Run 3 missed `speech-03` (single word “Yes.”) on transcript only; scene
still hit. Known-bad silent clips did not invent dialogue.

Raw: `ingest_understand_eval.jsonl`, `ingest_understand_eval_summary.json`.
