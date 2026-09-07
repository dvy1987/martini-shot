#!/usr/bin/env python
"""E-3 seed (owner-approved 2026-09-07): upload the labeled source clips
to the REAL project bucket, then submit the batch through the REAL lease
queue. Idempotent per deterministic job id (C-6.3) — reruns are no-ops.
Does NOT run the worker: jobs are processed by the lease worker."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs
from backend.jobs.queue import FirestoreLeaseQueue
from backend.supervisor.orchestrator import (
    build_batch_jobs,
    estimate_batch_cost,
    load_manifest,
    submit_batch,
)

MANIFEST = ROOT / "fixtures" / "e3_batch" / "manifest.json"
SOURCES = ROOT / "fixtures" / "e3_batch" / "source"
EVIDENCE = ROOT / "docs" / "evidence" / "E-3"


def main() -> int:
    settings = get_settings()
    if not settings.gcp_project_id or not settings.gcs_bucket:
        raise SystemExit("FATAL: GCP project / bucket not configured")
    print(f"bucket: {settings.gcs_bucket}", flush=True)

    gcs = get_gcs(settings)
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not raw.get("approved"):
        raise SystemExit("FATAL: manifest not approved (C-7.2)")

    # Upload missing sources (real objects, real bucket).
    uploaded = 0
    for item in raw["items"]:
        ref = str(item["source_ref"])
        if not ref.startswith(f"gs://{settings.gcs_bucket}/"):
            raise SystemExit(
                f"FATAL: source_ref {ref} does not match bucket {settings.gcs_bucket}"
            )
        key = ref.removeprefix(f"gs://{settings.gcs_bucket}/")
        local = SOURCES / Path(key).name
        if not gcs.exists(key):
            gcs.upload_bytes(key, local.read_bytes(), content_type="video/mp4")
            uploaded += 1
            print(f"uploaded {key} ({local.stat().st_size} bytes)", flush=True)
        else:
            print(f"already present: {key}", flush=True)

    # Submit through the REAL queue (idempotent per deterministic id).
    store = get_firestore(settings)
    queue = FirestoreLeaseQueue(store)
    items = load_manifest(MANIFEST)
    jobs = build_batch_jobs(items)
    submit_batch(queue, jobs)
    print(f"submitted/ensured {len(jobs)} jobs", flush=True)

    payload = {
        "date": "2026-09-07",
        "bucket": settings.gcs_bucket,
        "sources_uploaded": uploaded,
        "sources_total": len(raw["items"]),
        "jobs_submitted": [job.id for job in jobs],
        "estimate": estimate_batch_cost(raw["items"]),
        "approved_by": "owner (AskUser sign-off, 2026-09-07)",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "seed.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"archived: {EVIDENCE / 'seed.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
