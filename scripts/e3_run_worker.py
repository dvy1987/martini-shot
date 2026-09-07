#!/usr/bin/env python
"""E-3 batch runner (Stage 1a plan A2): drive the 96 owner-approved jobs
through the REAL lease queue.

Reads the submitted job ids from docs/evidence/E-3/seed.json (never re-seeds),
claims each via process_job_id (same import style as scripts/g2_gate.py), and
archives per-job result JSONs plus a batch summary under
docs/evidence/E-3/raw/ (owner directive: keep ALL raw outputs for the demo).

Queue.fail requeues a job while attempts remain (max_attempts=2), so the
runner makes up to 3 passes until every job is terminal. Persistent failures
are recorded honestly — never forced past the queue's own attempt policy.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings, reset_settings
from backend.core.firestore import get_firestore
from backend.core.gcs import get_gcs
from backend.jobs.queue import FirestoreLeaseQueue
from backend.jobs.worker import process_job_id

SEED = ROOT / "docs" / "evidence" / "E-3" / "seed.json"
RAW = ROOT / "docs" / "evidence" / "E-3" / "raw"
MAX_PASSES = 3
TERMINAL = {"passed", "failed", "quarantined", "throttled", "needs_human"}

log = logging.getLogger("pc.e3_runner")


def _record(queue: FirestoreLeaseQueue, job_id: str, exc: str | None = None) -> dict:
    """Authoritative state from the QUEUE's truth, plus the runner error if any."""
    job = queue.get(job_id)
    if job is None:
        return {"job_id": job_id, "missing": True, "runner_error": exc}
    data = job.to_dict()
    if exc:
        data["runner_error"] = exc
    return data


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    reset_settings()
    settings = get_settings()
    if not settings.gcp_project_id or not settings.gcs_bucket:
        raise SystemExit("FATAL: GCP project / bucket not configured")

    job_ids: list[str] = json.loads(SEED.read_text(encoding="utf-8"))["jobs_submitted"]
    print(f"E-3 runner: {len(job_ids)} seeded jobs", flush=True)

    store = get_firestore(settings)
    queue = FirestoreLeaseQueue(store)
    gcs = get_gcs(settings)

    # Pass 1..N: process every non-terminal job. Later passes catch jobs the
    # queue requeued (attempts remaining) without exceeding its retry policy.
    results: dict[str, dict] = {}
    for pass_no in range(1, MAX_PASSES + 1):
        remaining = [
            jid
            for jid in job_ids
            if (rec := results.get(jid)) is None or rec.get("status") not in TERMINAL
        ]
        if not remaining:
            break
        print(f"--- pass {pass_no}: {len(remaining)} jobs ---", flush=True)
        for job_id in remaining:
            current = queue.get(job_id)
            if current is None:
                results[job_id] = _record(queue, job_id, "missing from queue")
                continue
            if current.status in TERMINAL:
                results[job_id] = _record(queue, job_id)
                continue
            try:
                processed = process_job_id(queue, gcs, settings, job_id)
                results[job_id] = _record(
                    queue, job_id, None if processed else "claim returned None"
                )
            except Exception as exc:  # station failure already queue.fail'ed
                log.exception("job %s raised", job_id)
                results[job_id] = _record(queue, job_id, str(exc)[:200])
            rec = results[job_id]
            print(
                f"{job_id}: {rec.get('status')} cost_micros={rec.get('cost_micros')}",
                flush=True,
            )
            (RAW / "jobs").mkdir(parents=True, exist_ok=True)
            (RAW / "jobs" / f"{job_id}.json").write_text(
                json.dumps(rec, indent=2, default=str), encoding="utf-8"
            )

    # Batch summary: counts by station x status + total metered cost.
    by_station: dict[str, Counter[str]] = {}
    total_micros = 0
    for rec in results.values():
        station = str(rec.get("station") or "unknown")
        status = str(rec.get("status") or "unknown")
        by_station.setdefault(station, Counter())[status] += 1
        total_micros += int(rec.get("cost_micros") or 0)

    summary = {
        "batch": "e3-demo",
        "seed": "docs/evidence/E-3/seed.json",
        "jobs_total": len(job_ids),
        "status_counts": dict(Counter(str(r.get("status")) for r in results.values())),
        "by_station": {s: dict(c) for s, c in sorted(by_station.items())},
        "total_cost_micros": total_micros,
        "passes_used": MAX_PASSES,
        "gcs_bucket": settings.gcs_bucket,
        "per_job_results": "docs/evidence/E-3/raw/jobs/",
    }
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "batch_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)

    not_terminal = [
        jid for jid, rec in results.items() if rec.get("status") not in TERMINAL
    ]
    if not_terminal:
        print(f"NOT terminal after {MAX_PASSES} passes: {not_terminal}", flush=True)
        return 1
    print("all E-3 jobs terminal", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
