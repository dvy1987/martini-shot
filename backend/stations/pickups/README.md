# Virtual Pickups (S2) — QC path

**Capability:** Frame extract → reassemble (ffmpeg) and a classical flicker score. Anchor-prompt builder and retry state machine are wired. **No Veo/Omni call** on this path: generation is EDD-gated (`backend/evals/thresholds.yaml` + dataset manifest) and batches >$5 need `--yes` (C-7.2). Identity round-trip proves AC-S2.2 duration; retry tests use **real** G0 flicker numbers from `docs/evidence/G0/flicker_scores.json`.

**Real services:** GCS, ffmpeg, OTLP `pc_flicker_score`.

**How to run tests / evals**

```
python -m pytest tests/test_pickups.py -q
python scripts/pickups_eval.py
```

Eval writes JSONL under `docs/evidence/D-5/`.
