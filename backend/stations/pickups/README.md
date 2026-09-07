# Virtual Pickups (S2) — live QC + repair

**Capability:** Frame extract → flicker score → **Pickups Vision QC** (Gemini
looks at real frame extracts) → if the agent asks for a retry, **Omni edit**
re-renders the clip (Veo fallback if Omni fails) with strengthened identity
anchors, up to 2 times, then `needs_human`. A clean clip is not regenerated.

This is the live worker path (`run_pickups`), not eval-only. The identity
round-trip remains the measurement surface; retries no longer re-score the
same bytes.

**Real services:** GCS, ffmpeg, Gemini vision (`pickups_vision_qc`), Omni
edit, Veo fallback, OTLP `pc_flicker_score`.

**How to run tests / evals**

```
python -m pytest tests/test_pickups.py tests/test_pickups_vision_qc.py -q
python scripts/pickups_eval.py
python scripts/pickups_vision_qc_eval.py
```

Detector-only eval (`pickups_eval.py`) still writes JSONL under
`docs/evidence/D-5/` at $0. Live vision-QC eval: `docs/evidence/A10-4/`.
