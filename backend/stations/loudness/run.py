"""Loudness station: ebur128 + stem heuristic + M&E flag (S3)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.core.gcs import GCSMedia
from backend.core.media import FFmpeg, _as_int
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, record_loudness, timed
from backend.stations.loudness.verdict import (
    STREAMING_TARGET_LUFS,
    me_present,
    stem_diagnosis,
    verdict,
)

STATION = "loudness"


def run_loudness(job: Job, gcs: GCSMedia, media: FFmpeg) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("loudness requires a media object")
            payload = gcs.download_bytes(job.input_refs[0])
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
                handle.write(payload)
                tmp = Path(handle.name)
            try:
                report = media.loudness_report(tmp)
                probe = media.probe(tmp)
                dialogue = media.band_lufs(tmp, 300, 3000)
                music = media.band_lufs(tmp, 4000, 12000)
            finally:
                tmp.unlink(missing_ok=True)
            target = float(job.result.get("target_lufs") or STREAMING_TARGET_LUFS)
            lufs = report["lufs"]
            peak = report.get("true_peak_dbtp")
            decision = verdict(lufs, target=target, true_peak_dbtp=peak)
            job.cost_micros = 0
            job.result = {
                **job.result,
                "lufs": lufs,
                "true_peak_dbtp": peak,
                "lra": report.get("lra"),
                "target_lufs": target,
                "verdict": decision,
                "stems": stem_diagnosis(dialogue, music),
                "me_present": me_present(_as_int(probe.get("audio_streams"))),
            }
            record_loudness(STATION, lufs)
            if decision != "pass":
                job.status = "needs_human"
                job.error = decision
                outcome = decision
            else:
                outcome = "pass"
            log.info(
                "loudness measured",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "lufs": lufs,
                    "verdict": decision,
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
