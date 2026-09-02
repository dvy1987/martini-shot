"""Pickups station: extract/reassemble + flicker QC. No Veo call in this path."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.core.gcs import GCSMedia
from backend.core.media import FFmpeg
from backend.jobs.models import Job
from backend.jobs.telemetry import (
    job_span,
    log,
    record_flicker,
    record_job,
    timed,
)
from backend.stations.pickups.cost import estimate_micros
from backend.stations.pickups.flicker import flicker_score
from backend.stations.pickups.retry import apply_retries

STATION = "pickups"
FLICKER_THRESHOLD = 0.18
MICROS_PER_FRAME = 0  # identity QC path; generate path is eval-gated (C-7.2)


def run_pickups(job: Job, gcs: GCSMedia, media: FFmpeg) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("pickups requires media")
            payload = gcs.download_bytes(job.input_refs[0])
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "src.mp4"
                src.write_bytes(payload)
                frames_dir = Path(tmp) / "frames"
                frames = media.extract_frames(src, frames_dir, fps=8.0)
                out = Path(tmp) / "roundtrip.mp4"
                media.reassemble(frames, out, fps=8.0)
                score = flicker_score(out, media.ffmpeg_bin)
            flicker = float(score.get("flicker_score") or 1.0)
            record_flicker(STATION, flicker)
            retry = apply_retries(flicker, FLICKER_THRESHOLD)
            job.cost_micros = estimate_micros(len(frames), MICROS_PER_FRAME)
            job.result = {
                "flicker": score,
                "retry": retry,
                "frames": len(frames),
            }
            if retry["final"] == "needs_human":
                job.status = "needs_human"
                job.error = "flicker_breach"
                outcome = "needs_human"
            else:
                outcome = "pass"
            log.info(
                "pickups qc done",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "flicker_score": flicker,
                    "final": retry["final"],
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
