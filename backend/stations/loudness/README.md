# Loudness Marshal (S3)

**Capability:** Measure integrated LUFS / LRA / true-peak with ffmpeg `ebur128`, compare against streaming (−16) or broadcast (−24) targets ±1 LU, true-peak ceiling −1 dBTP. Stem-hot heuristic compares a dialogue band (300–3 kHz) vs a music band (4–12 kHz). M&E presence is a second audio stream.

**Real services:** GCS object download, ffmpeg, OTLP metric `pc_loudness_lufs`.

**How to run tests**

```
python -m pytest tests/test_loudness.py -q
```

**Evals:** none (deterministic meter + tables).
