# Loudness Marshal (S3)

**Capability:** Hear the mix (prefer the sibling dub WAV over the picture soundtrack), classify scene energy (silence / whisper / talk / shout / crash / explosion), mix with ffmpeg `loudnorm` toward that target, re-measure. Dialogue stays easy to hear; the show stays in one loudness family; a whisper may sit quieter than talk and a bang may sit louder. The meter still wins on the number. `needs_human` only if the mix still misses or speech stays unintelligible.

**Real services:** GCS object download/upload, ffmpeg ebur128 + loudnorm, Gemini Loudness Strategist (listens), OTLP metric `pc_loudness_lufs`. Mixed audio is an ALTERNATE on the shot (AL-1).

**How to run tests**

```
python -m pytest tests/test_loudness.py tests/test_scene_loudness.py tests/test_loudness_strategy.py -q
```

**Evals:** `loudness_strategy_judgment` (remediation path) and `scene_loudness_judgment` (scene class + mix path). Live runner: `python scripts/scene_loudness_eval.py`.
