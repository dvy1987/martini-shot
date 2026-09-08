"""E-1 Relight Studio station: named lighting-intention Omni edits that
preserve framing, identity, and geometry. Draft alternate via H-0's
`relight_shot` command — never an overwrite of the source shot."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.generative import estimate_extend_cost_micros, omni_edit
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.shots import lifecycle as shots
from backend.stations.pickups.flicker import flicker_score

STATION = "relight"
FLICKER_GATE = 0.02

# Practical lighting presets (E-1 locked scope). Each preset names the
# intended look; the model owns HOW, never invents a different mood.
PRESETS: dict[str, str] = {
    "practical_lamp": (
        "Relight this scene as if lit primarily by a warm practical lamp "
        "source within frame: soft warm key light, deep ambient shadow falloff."
    ),
    "ambient_daylight": (
        "Relight this scene as soft ambient daylight through a window: "
        "cool, diffuse, even fill with gentle directional shadows."
    ),
    "overhead_ceiling": (
        "Relight this scene as flat overhead ceiling fixtures: neutral, "
        "slightly harsh top-down light with minimal color cast."
    ),
    "noir": (
        "Relight this scene in high-contrast noir style: hard directional "
        "key light, deep black shadows, strong chiaroscuro."
    ),
}


def build_relight_prompt(preset: str) -> str:
    if preset not in PRESETS:
        raise ValueError(
            f"unknown relight preset {preset!r} (table: {sorted(PRESETS)})"
        )
    return (
        f"{PRESETS[preset]} "
        "Preserve framing, subject identity, and scene geometry exactly. "
        "Keep everything else the same."
    )


def draft_qc_decision(flicker: float) -> str:
    return "pass" if flicker < FLICKER_GATE else "needs_human"


def run_relight(
    job: Job, gcs: GCSMedia, store: FirestoreStore, settings: Settings
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("relight requires a source media ref")
            source_uri = job.input_refs[0]
            if not source_uri.startswith("gs://"):
                raise ValueError(
                    f"relight source must be a gs:// URI, got {source_uri!r}"
                )
            shot_id = str(job.result.get("shot_id") or "")
            if not shot_id:
                raise ValueError("relight requires result.shot_id")
            preset = str(job.result.get("preset") or "")
            prompt = str(job.result.get("prompt") or build_relight_prompt(preset))
            render = omni_edit(settings, input_uri=source_uri, prompt=prompt)
            destination_key = str(
                job.result.get("destination_key")
                or f"projects/{job.project_id}/relight/{job.id}.mp4"
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
                op="relight",
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
                "preset": preset,
                "tier": tier,
            }
            if decision != "pass":
                job.status = "needs_human"
                job.error = "relight_flicker_breach"
                outcome = "needs_human"
            else:
                outcome = "pass"
            log.info(
                "relight rendered",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "shot_id": shot_id,
                    "alternate_id": alternate_id,
                    "flicker": flicker,
                    "qc_decision": decision,
                    "preset": preset,
                },
            )
            return job
        finally:
            record_job(
                STATION,
                duration_s=timed() - started,
                cost_micros=job.cost_micros,
                outcome=outcome,
                project_id=job.project_id,
            )
