# Ingest station (S1)

**Capability:** Register arrival of a media object in GCS, SHA-256 the bytes, ffprobe the container, decode-check for bit-rot/corruption, and flag missing audio. Corrupt or mute-container files go to `quarantined` with a reason code (not re-queued). A healthy clip is then **watched**: Gemini writes spoken words (or none) and a short scene description onto the **shot** as `scene_understanding`. The orchestrator and later stations read that metadata.

**Real services:** Google Cloud Storage (`GCS_BUCKET`). Firestore lease queue (`pc-jobs`) + `pc-shots`. ffmpeg/ffprobe. Gemini 3.7 Flash (audio + frames). Grafana Cloud OTLP (`pc_job_*` plus span `station.ingest.run` / `station.ingest.understand`).

**How to run tests**

```
python -m pytest tests/test_ingest_checksum.py tests/test_ingest_probe.py tests/test_ingest_understand.py -q
python -m pytest tests/test_g1_ingest_integration.py -q
```

**Evals:** `ingest_transcript_judgment` and `ingest_scene_judgment` (bar >= 0.8). Live: `python scripts/ingest_understand_eval.py`.
