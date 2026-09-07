# Delivery & Compliance (S5)

**Capability:** Versioned YAML destination packs (streaming / broadcast / social). Evaluator checks container, codec, aspect, fps, bitrate, delegates loudness (D-2) and caption spec validation (D-3). Missing captions are **written** from the dubbed script (deterministic wrap/time). Broken SRTs go through the Caption Remediation agent, then D-3 re-validates. Gemini Caption Writer listens only when there is audio and no script. If captions hear spoken words that are too quiet, Delivery notes the orchestrator to retry loudness; silence / no spoken words is not a mix miss. Delivery grades the loudness **mix** when that artifact exists. Unknown destinations fail closed. A morning-report line is written so the Reports screen can render the pack without a dedicated captions screen.

**Real services:** GCS, ffmpeg, Firestore `pc-morning-reports`, Gemini (caption write/edit).

**How to run tests**

```
python -m pytest tests/test_captions.py tests/test_delivery.py tests/test_caption_write.py tests/test_caption_remediation.py -q
```

**Evals:** `caption_remediation_judgment` (editor) and `caption_write_judgment` (writer). Live: `python scripts/caption_write_eval.py`.
