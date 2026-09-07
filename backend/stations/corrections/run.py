"""D-10 Corrections station: bounded Omni edits, always landed as a DRAFT
alternate (AL-1) — never an overwrite of the source shot. Approval-tracked
through H-0's `correct_shot` command."""

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

STATION = "corrections"

# Same continuity gate as Extend (G0 evidence): a correction that disturbs
# more than this fraction of frames breaches protected-subject preservation.
FLICKER_GATE = 0.02


def build_correction_prompt(
    *,
    intent: str,
    protected_subjects: Iterable[str],
    continuity_constraints: Iterable[str],
) -> str:
    """Build the bounded instruction supplied to the real Omni edit call."""
    clean_intent = intent.strip()
    if not clean_intent:
        raise ValueError("correction requires explicit intent")
    protected = ", ".join(item.strip() for item in protected_subjects if item.strip())
    constraints = ", ".join(
        item.strip() for item in continuity_constraints if item.strip()
    )
    return (
        "Edit this video only to accomplish the following bounded correction:\n"
        f"{clean_intent}\n\n"
        f"Protected subjects and regions: {protected or 'none specified'}.\n"
        f"Continuity constraints: {constraints or 'preserve the source shot'}.\n"
        "Do not alter protected subjects, identity, framing, or geometry. "
        "Keep everything else the same."
    )


def draft_qc_decision(flicker: float) -> str:
    return "pass" if flicker < FLICKER_GATE else "needs_human"


def run_correction(
    job: Job, gcs: GCSMedia, store: FirestoreStore, settings: Settings
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("correction requires a source media ref")
            source_uri = job.input_refs[0]
            if not source_uri.startswith("gs://"):
                raise ValueError(
                    f"correction source must be a gs:// URI, got {source_uri!r}"
                )
            shot_id = str(job.result.get("shot_id") or "")
            if not shot_id:
                raise ValueError("correction requires result.shot_id")
            prompt = str(
                job.result.get("prompt")
                or build_correction_prompt(
                    intent=str(job.result.get("intent") or ""),
                    protected_subjects=job.result.get("protected_subjects") or [],
                    continuity_constraints=job.result.get("continuity_constraints")
                    or [],
                )
            )
            render = omni_edit(settings, input_uri=source_uri, prompt=prompt)
            destination_key = str(
                job.result.get("destination_key")
                or f"projects/{job.project_id}/corrections/{job.id}.mp4"
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
            tier = str(job.result.get("tier") or "draft")
            alternate_id = shots.record_alternate(
                store,
                shot_id=shot_id,
                project_id=job.project_id,
                op="correction",
                artifact_ref=artifact_ref,
                eval_scores={"flicker": flicker},
                tier=tier,
            )
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
                "omni_fallback": False,
                "omni_error": "",
                "flicker": flicker,
                "flicker_gate": FLICKER_GATE,
                "qc_decision": decision,
                "interaction_id": render.get("interaction_id"),
                "prompt": prompt,
                "tier": tier,
            }
            if decision != "pass":
                job.status = "needs_human"
                job.error = "correction_flicker_breach"
                outcome = "needs_human"
            else:
                outcome = "pass"
            log.info(
                "correction rendered",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "shot_id": shot_id,
                    "alternate_id": alternate_id,
                    "flicker": flicker,
                    "qc_decision": decision,
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
