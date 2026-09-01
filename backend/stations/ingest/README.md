# Ingest station (G1 subset)

**Capability:** Register arrival of a media object in GCS and compute SHA-256 of the bytes. Gate G1 only — no ffprobe, corruption detect, or audio-sync (those land in plan D-1 / AC-S1.1).

**Real services:** Google Cloud Storage (`GCS_BUCKET`). Firestore lease queue (`pc-jobs`). Grafana Cloud OTLP (`pc_job_duration_seconds`, `pc_job_cost_micros`, `pc_job_outcome_total` plus the ingest span `station.ingest.run`).

**How to run tests**

```
python -m pytest tests/test_ingest_checksum.py -q
python -m pytest tests/test_g1_ingest_integration.py -q
```

**Evals:** none (deterministic checksum; no generative path).
