# Ingest station (S1)

**Capability:** Register arrival of a media object in GCS, SHA-256 the bytes, ffprobe the container, decode-check for bit-rot/corruption, and flag missing audio. Corrupt or silent files go to `quarantined` with a reason code (not re-queued).

**Real services:** Google Cloud Storage (`GCS_BUCKET`). Firestore lease queue (`pc-jobs`). ffmpeg/ffprobe. Grafana Cloud OTLP (`pc_job_*` plus span `station.ingest.run`). Grafana annotation on terminal states via MCP.

**How to run tests**

```
python -m pytest tests/test_ingest_checksum.py tests/test_ingest_probe.py -q
python -m pytest tests/test_g1_ingest_integration.py -q
```

**Evals:** none (deterministic).
