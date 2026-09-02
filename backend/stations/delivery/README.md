# Delivery & Compliance (S5)

**Capability:** Versioned YAML destination packs (streaming / broadcast / social). Evaluator checks container, codec, aspect, fps, bitrate, delegates loudness (D-2) and caption spec validation (D-3). Unknown destinations fail closed. A morning-report line is written so the Reports screen can render the pack without a dedicated captions screen.

**Real services:** GCS, ffmpeg, Firestore `pc-morning-reports`.

**How to run tests**

```
python -m pytest tests/test_captions.py tests/test_delivery.py -q
```

**Evals:** none (deterministic rule engine).
