# Loudness Marshal (S3)

**Capability:** Hear the mix (prefer the sibling dub WAV over the picture soundtrack), classify quiet/normal/loud × with/without dialogue, mix with ffmpeg `loudnorm` toward that target, and when speech is buried **lift the voice over the room**. Re-measure. Everything stays in a comfortable hearing range; a continuing shot stays in family with the last mix. Best effort — never `needs_human`.

**Real services:** GCS object download/upload, ffmpeg ebur128 + loudnorm, Gemini Loudness Strategist (listens), OTLP metric `pc_loudness_lufs`. Mixed audio is an ALTERNATE on the shot (AL-1).

**How to run tests**

```
python -m pytest tests/test_loudness.py tests/test_scene_loudness.py tests/test_loudness_strategy.py -q
```

**Evals:** `loudness_strategy_judgment` (remediation path) and `scene_loudness_judgment` (scene class + mix path). Live runner: `python scripts/scene_loudness_eval.py`.
