"""D-12 Coverage station: new-angle generation using persisted subject
references and neighboring-shot context. Draft alternate via H-0's
`generate_coverage` command."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.generative import estimate_extend_cost_micros, omni_edit
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.shots import lifecycle as shots
from backend.stations.pickups.flicker import flicker_score

STATION = "coverage"
FLICKER_GATE = 0.02

# Approved coverage-angle vocabulary (locked scope, mirrors D-16's
# constrained vocabulary pattern so both stay auditable and comparable).
ANGLES: tuple[str, ...] = (
    "reverse_angle",
    "close_up",
    "wide_establishing",
    "over_the_shoulder",
    "insert",
)


def build_coverage_prompt(
    *,
    angle: str,
    intent: str,
    reference_count: int,
) -> str:
    if angle not in ANGLES:
        raise ValueError(f"unknown coverage angle {angle!r} (table: {sorted(ANGLES)})")
    clean_intent = intent.strip()
    if not clean_intent:
        raise ValueError("coverage requires explicit intent")
    if reference_count <= 0:
        raise ValueError("coverage requires at least one subject reference")
    return (
        f"Generate a new {angle.replace('_', ' ')} shot covering the same "
        f"scene and subjects shown in the source video and the "
        f"{reference_count} attached subject reference(s): {clean_intent}\n"
        "Preserve subject identity exactly from the references. The new "
        "angle must remain visually and continuity-compatible with the "
        "source shot's lighting, wardrobe, and setting."
    )


def draft_qc_decision(flicker: float) -> str:
    return "pass" if flicker < FLICKER_GATE else "needs_human"


def run_coverage(
    job: Job, gcs: GCSMedia, store: FirestoreStore, settings: Settings
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("coverage requires a source media ref")
            source_uri = job.input_refs[0]
            if not source_uri.startswith("gs://"):
                raise ValueError(
                    f"coverage source must be a gs:// URI, got {source_uri!r}"
                )
            shot_id = str(job.result.get("shot_id") or "")
            if not shot_id:
                raise ValueError("coverage requires result.shot_id")
            reference_uris: Iterable[str] = tuple(
                job.result.get("reference_uris") or ()
            )
            angle = str(job.result.get("angle") or "")
            prompt = str(
                job.result.get("prompt")
                or build_coverage_prompt(
                    angle=angle,
                    intent=str(job.result.get("intent") or ""),
                    reference_count=len(list(reference_uris)),
                )
            )
            render = omni_edit(
                settings,
                input_uri=source_uri,
                prompt=prompt,
                reference_uris=tuple(reference_uris),
            )
            destination_key = str(
                job.result.get("destination_key")
                or f"projects/{job.project_id}/coverage/{job.id}.mp4"
            )
            gcs.upload_bytes(
                destination_key, render["video_bytes"], content_type="video/mp4"
            )
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
                handle.write(render["video_bytes"])
                tmp = Path(handle.name)
            try:
                score = flicker_score(tmp, settings.ffmpeg_bin or "ffmpeg")
            finally:
                tmp.unlink(missing_ok=True)
            flicker = float(score.get("flicker_score") or 1.0)
            decision = draft_qc_decision(flicker)

            artifact_ref = f"gs://{settings.gcs_bucket}/{destination_key}"
            alternate_id = shots.record_alternate(
                store,
                shot_id=shot_id,
                project_id=job.project_id,
                op="coverage",
                artifact_ref=artifact_ref,
                eval_scores={"flicker": flicker},
            )
            tier = str(job.result.get("tier") or "draft")
            resolution = "720p" if tier == "master" else "360p"
            analyzed_s = float(score.get("frames_analyzed") or 0) / 8.0
            job.cost_micros = estimate_extend_cost_micros(
                min(7.0, analyzed_s) or 7.0, resolution=resolution
            )
            job.result = {
                **job.result,
                "alternate_id": alternate_id,
                "artifact_ref": artifact_ref,
                "render_model": render.get("model"),
                "flicker": flicker,
                "flicker_gate": FLICKER_GATE,
                "qc_decision": decision,
                "interaction_id": render.get("interaction_id"),
                "prompt": prompt,
                "angle": angle,
                "tier": tier,
            }
            if decision != "pass":
                job.status = "needs_human"
                job.error = "coverage_flicker_breach"
                outcome = "needs_human"
            else:
                outcome = "pass"
            log.info(
                "coverage rendered",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "shot_id": shot_id,
                    "alternate_id": alternate_id,
                    "flicker": flicker,
                    "qc_decision": decision,
                    "angle": angle,
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
