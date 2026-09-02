"""Delivery station: probe + loudness + caption sub-check against a YAML pack."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.media import FFmpeg
from backend.jobs.models import Job, utc_now_iso
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.stations.delivery.evaluate import evaluate_delivery

STATION = "delivery"
REPORTS = "pc-morning-reports"


def run_delivery(job: Job, gcs: GCSMedia, store: FirestoreStore, media: FFmpeg) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("delivery requires media")
            payload = gcs.download_bytes(job.input_refs[0])
            caption_text = None
            caption_name = None
            if len(job.input_refs) > 1:
                raw = gcs.download_bytes(job.input_refs[1])
                caption_text = raw.decode("utf-8", "replace")
                caption_name = job.input_refs[1].rsplit("/", 1)[-1]
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
                handle.write(payload)
                tmp = Path(handle.name)
            try:
                probe = media.probe(tmp)
                lufs = media.loudness_lufs(tmp)
            finally:
                tmp.unlink(missing_ok=True)
            destination = str(job.result.get("destination") or "streaming")
            report = evaluate_delivery(
                destination=destination,
                probe=probe,
                lufs=lufs,
                caption_text=caption_text,
                caption_name=caption_name,
            )
            job.cost_micros = 0
            job.result = {**job.result, "delivery": report, "lufs": lufs}
            if report["verdict"] != "pass":
                job.status = "needs_human"
                job.error = "delivery_fail"
                outcome = "fail"
            else:
                outcome = "pass"
            _write_morning_line(store, job, report)
            log.info(
                "delivery evaluated",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "verdict": report["verdict"],
                },
            )
            return job
        finally:
            record_job(
                STATION,
                duration_s=timed() - started,
                cost_micros=job.cost_micros,
                outcome=outcome,
            )


def _write_morning_line(
    store: FirestoreStore, job: Job, report: dict[str, object]
) -> None:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{job.project_id}:{date}"
    existing = store.get_doc(REPORTS, key) or {
        "date": date,
        "generated_at": utc_now_iso(),
        "verdicts": [],
    }
    verdicts = list(existing.get("verdicts") or [])
    n_fail = 0
    raw_viol = report.get("violations") or []
    if isinstance(raw_viol, list):
        n_fail = len(raw_viol)
    verdicts.append(
        {
            "station": STATION,
            "verdict": report.get("verdict"),
            "summary": (
                f"{report.get('destination')} pack: {report.get('verdict')}"
                f" ({n_fail} rule hits)"
            ),
            "cost_micros": job.cost_micros,
        }
    )
    store.set_doc(
        REPORTS,
        key,
        {
            **existing,
            "date": date,
            "generated_at": utc_now_iso(),
            "verdicts": verdicts,
        },
    )
