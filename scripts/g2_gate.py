#!/usr/bin/env python
"""Gate G2: deterministic stations through the real queue + Spend Control runaway.

Usage: API on :8000 (worker on). Then: python scripts/g2_gate.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from backend.core.config import get_settings, reset_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs
from backend.jobs.models import Job, utc_now_iso
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id

EVIDENCE = ROOT / "docs" / "evidence" / "G2"
SLATE = ROOT / "fixtures" / "g1" / "slate.mp4"
CAPTION = ROOT / "fixtures" / "captions" / "valid.srt"


def main() -> int:
    reset_settings()
    settings = get_settings()
    if not (settings.api_key and settings.gcp_project_id and settings.gcs_bucket):
        print("missing API/GCP config")
        return 1
    project_id = f"g2-{uuid.uuid4().hex[:8]}"
    store = get_firestore(settings)
    gcs = get_gcs(settings)
    queue = FirestoreLeaseQueue(store)
    headers = {"X-API-Key": settings.api_key}
    base = "http://127.0.0.1:8000"
    evidence: dict[str, object] = {"project_id": project_id, "jobs": []}
    keys: list[str] = []
    job_ids: list[str] = []
    try:
        with httpx.Client(timeout=60) as client:
            ingest = client.post(
                f"{base}/api/v1/projects/{project_id}/ingest",
                headers=headers,
                files={"file": ("slate.mp4", SLATE.read_bytes(), "video/mp4")},
            )
            ingest.raise_for_status()
            ingest_job = ingest.json()
            job_ids.append(ingest_job["job_id"])
            keys.extend(ingest_job.get("input_refs") or [])
            processed = process_job_id(queue, gcs, settings, ingest_job["job_id"])
            if processed is None:
                processed = queue.get(ingest_job["job_id"])
            if processed is None or not processed.input_refs:
                print("ingest job missing after process")
                return 1
            media_ref = processed.input_refs[0]

            caption_key = f"projects/{project_id}/captions/valid.srt"
            gcs.upload_bytes(
                caption_key, CAPTION.read_bytes(), content_type="text/plain"
            )
            keys.append(caption_key)

            loud = Job(
                station="loudness", project_id=project_id, input_refs=[media_ref]
            )
            queue.submit(loud)
            job_ids.append(loud.id)
            process_job_id(queue, gcs, settings, loud.id)

            delivery = Job(
                station="delivery",
                project_id=project_id,
                input_refs=[media_ref, caption_key],
                result={"destination": "streaming"},
            )
            queue.submit(delivery)
            job_ids.append(delivery.id)
            process_job_id(queue, gcs, settings, delivery.id)

            runaway = Job(
                station="pickups",
                project_id=project_id,
                input_refs=[media_ref],
                attempts=40,
                status="passed",
            )
            store.set_doc("pc-jobs", runaway.id, runaway.to_dict())
            job_ids.append(runaway.id)

            spend = Job(station="spend", project_id=project_id, input_refs=[])
            queue.submit(spend)
            job_ids.append(spend.id)
            process_job_id(queue, gcs, settings, spend.id)

            time.sleep(0.5)
            listing = client.get(
                f"{base}/api/v1/projects/{project_id}", headers=headers
            )
            approvals = client.get(f"{base}/api/v1/approvals", headers=headers)
            evidence["project"] = (
                listing.json() if listing.status_code == 200 else listing.text
            )
            evidence["approvals"] = (
                approvals.json() if approvals.status_code == 200 else approvals.text
            )
            intake = store.get_doc("pc-control", "intake") or {}
            evidence["intake"] = intake
            evidence["jobs"] = [
                queue.get(jid).to_dict() for jid in job_ids if queue.get(jid)
            ]
            throttled = "pickups" in (intake.get("paused_stations") or [])
            evidence["runaway_throttled"] = throttled
            evidence["at"] = utc_now_iso()
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "gate.json").write_text(
            json.dumps(evidence, default=str, indent=2), encoding="utf-8"
        )
        (EVIDENCE / "README.md").write_text(
            "# Gate G2\n\n"
            f"Project `{project_id}`. Ingest + loudness + delivery through the "
            "lease queue. Spend Control throttled a seeded 40× runaway "
            f"({'yes' if throttled else 'NO'}).\n",
            encoding="utf-8",
        )
        print(json.dumps({"project_id": project_id, "throttled": throttled}, indent=2))
        return 0 if throttled else 1
    finally:
        for jid in job_ids:
            try:
                queue.forget(jid)
            except Exception:
                pass
        for key in keys:
            try:
                gcs.delete(key)
            except Exception:
                pass
        try:
            store.delete_doc("pc-projects", project_id)
        except Exception:
            pass
        try:
            store.delete_doc("pc-control", "intake")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
