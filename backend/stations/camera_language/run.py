"""D-16 Camera Language station: constrained camera-movement generation
limited to the approved vocabulary, with disclosed reference-style
influence. Draft alternate via H-0's `apply_camera_language` command."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.generative import estimate_extend_cost_micros, omni_edit_bounded
from backend.core.media import FFmpeg
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.shots import lifecycle as shots
from backend.stations.pickups.flicker import flicker_score

STATION = "camera_language"
FLICKER_GATE = 0.02
# The mean above dilutes one bad frame across dozens of clean ones
# (2026-09-09 demo: a real, visually-confirmed single-frame corruption
# scored ~0.005 mean, well under gate). spike is the worst single frame.
FLICKER_SPIKE_GATE = 0.02

# Approved camera-movement vocabulary (locked scope, D-16). Anything else
# is refused before a render is ever attempted.
MOVEMENTS: tuple[str, ...] = (
    "dolly_tracking",
    "dolly_zoom",
    "handheld_shaky",
    "steadicam",
    "whip_pan",
    "crash_zoom",
    "snorricam",
    "locked_off",
)

_DESCRIPTIONS: dict[str, str] = {
    "dolly_tracking": "a smooth dolly/tracking move alongside the subject",
    "dolly_zoom": "a dolly zoom (vertigo effect): dolly one way while zooming the other",
    "handheld_shaky": "handheld camera with natural human shake",
    "steadicam": "a smooth, floating Steadicam move",
    "whip_pan": "a fast whip pan between two points of interest",
    "crash_zoom": "an abrupt, fast crash zoom onto the subject",
    "snorricam": "a SnorriCam rig locked to the subject's body, world moving around them",
    "locked_off": "a completely static, locked-off frame with no camera movement",
}

# Public alias: the Studio directed-edit agent (backend/supervisor/station_agents/
# directed_edit.py) quotes the same official vocabulary/descriptions rather than
# inventing its own, so the two surfaces can never drift apart.
MOVEMENT_DESCRIPTIONS: dict[str, str] = _DESCRIPTIONS


def build_camera_language_prompt(
    *, movement: str, reference_style: str | None = None
) -> str:
    if movement not in MOVEMENTS:
        raise ValueError(
            f"unknown camera movement {movement!r} (table: {sorted(MOVEMENTS)})"
        )
    disclosure = (
        f" Reference-style influence (disclosed): {reference_style.strip()}."
        if reference_style and reference_style.strip()
        else ""
    )
    return (
        f"Re-shoot this scene using {_DESCRIPTIONS[movement]}.{disclosure} "
        "Preserve subject identity, wardrobe, and setting exactly. Keep "
        "everything else the same."
    )


def draft_qc_decision(flicker: float, spike: float = 0.0) -> str:
    if flicker >= FLICKER_GATE or spike >= FLICKER_SPIKE_GATE:
        return "needs_human"
    return "pass"


def run_camera_language(
    job: Job, gcs: GCSMedia, store: FirestoreStore, settings: Settings
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("camera_language requires a source media ref")
            source_uri = job.input_refs[0]
            if not source_uri.startswith("gs://"):
                raise ValueError(
                    f"camera_language source must be a gs:// URI, got {source_uri!r}"
                )
            shot_id = str(job.result.get("shot_id") or "")
            if not shot_id:
                raise ValueError("camera_language requires result.shot_id")
            movement = str(job.result.get("movement") or "")
            prompt = str(
                job.result.get("prompt")
                or build_camera_language_prompt(
                    movement=movement,
                    reference_style=job.result.get("reference_style"),
                )
            )
            media = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
            render = omni_edit_bounded(
                settings,
                gcs,
                media,
                input_uri=source_uri,
                prompt=prompt,
                scratch_prefix=f"projects/{job.project_id}/_omni_scratch/{job.id}",
            )
            destination_key = str(
                job.result.get("destination_key")
                or f"projects/{job.project_id}/camera_language/{job.id}.mp4"
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
            spike = float(score.get("spike_score") or 0.0)
            decision = draft_qc_decision(flicker, spike)

            artifact_ref = f"gs://{settings.gcs_bucket}/{destination_key}"
            alternate_id = shots.record_alternate(
                store,
                shot_id=shot_id,
                project_id=job.project_id,
                op="camera_language",
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
                "flicker_spike": spike,
                "flicker_spike_gate": FLICKER_SPIKE_GATE,
                "qc_decision": decision,
                "interaction_id": render.get("interaction_id"),
                "prompt": prompt,
                "movement": movement,
                "tier": tier,
                "omni_chunked": bool(render.get("chunked")),
                "omni_chunk_count": render.get("chunk_count"),
            }
            if decision != "pass":
                job.status = "needs_human"
                job.error = "camera_language_flicker_breach"
                outcome = "needs_human"
            else:
                outcome = "pass"
            log.info(
                "camera_language rendered",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "shot_id": shot_id,
                    "alternate_id": alternate_id,
                    "flicker": flicker,
                    "qc_decision": decision,
                    "movement": movement,
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
