"""Extend station (D-9, A8): Omni scene-extend through the real pipeline.

Proposal→approval (H-0 `extend_shot`) → this station renders on the lease
queue (C-6.5/C-6.3: async, idempotent per job_id) → GCS store → deterministic
flicker QC gate → the render is recorded as an ALTERNATE (AL-1) — never an
overwrite of the locked cut. Draft-first: 360p drafts for QC loops; masters
only after eval bars pass (Spend Control enforces).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.generative import (
    build_extend_prompt,
    estimate_extend_cost_micros,
    omni_extend,
    veo_extend,
)
from backend.core.models import OMNI_MODEL, VEO_MODEL
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.shots import lifecycle as shots
from backend.stations.pickups.flicker import flicker_score

STATION = "extend"

# Continuity gate (G0 evidence: healthy Omni extends scored 0.0013-0.0032;
# a broken render is an order of magnitude worse). Drafts breaching the gate
# land as needs_human — never silently pass.
FLICKER_GATE = 0.02
# The mean above dilutes one bad frame across dozens of clean ones
# (2026-09-09 demo: a real, visually-confirmed single-frame corruption
# scored ~0.005 mean, well under gate). spike is the worst single frame.
FLICKER_SPIKE_GATE = 0.02


def draft_qc_decision(flicker: float, spike: float = 0.0) -> str:
    if flicker >= FLICKER_GATE or spike >= FLICKER_SPIKE_GATE:
        return "needs_human"
    return "pass"


def resolution_for_tier(tier: str) -> str:
    return "720p" if tier == "master" else "360p"


def run_extend(
    job: Job, gcs: GCSMedia, store: FirestoreStore, settings: Settings
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("extend requires a source media ref")
            source_uri = job.input_refs[0]
            if not source_uri.startswith("gs://"):
                raise ValueError(
                    f"extend source must be a gs:// URI, got {source_uri!r}"
                )
            shot_id = str(job.result.get("shot_id") or "")
            if not shot_id:
                raise ValueError("extend requires result.shot_id")
            prompt = str(
                job.result.get("prompt")
                or build_extend_prompt(str(job.result.get("shot_title") or shot_id))
            )

            # Product (owner 2026-09-07): Omni first; if Omni fails, Veo
            # fallback is the correct operator behavior. Record
            # omni_fallback + omni_error so evals/dev can still see an Omni
            # miss and must not count this as an Omni pass.
            omni_fallback = False
            omni_error_text = ""
            try:
                render = omni_extend(settings, input_uri=source_uri, prompt=prompt)
                render_model = str(render.get("model") or OMNI_MODEL)
            except Exception as omni_error:
                omni_fallback = True
                omni_error_text = (
                    f"{type(omni_error).__name__}: {str(omni_error)[:240]}"
                )
                log.warning(
                    "OMNI FAILED, VEO FALLBACK: %s",
                    omni_error_text,
                    extra={
                        "job_id": job.id,
                        "station": STATION,
                        "project_id": job.project_id,
                        "omni_fallback": True,
                    },
                )
                render = veo_extend(settings, input_uri=source_uri, prompt=prompt)
                render_model = str(render.get("model") or VEO_MODEL)
            destination_key = str(
                job.result.get("destination_key")
                or f"projects/{job.project_id}/extends/{job.id}.mp4"
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
            tier = str(job.result.get("tier") or "draft")
            resolution = resolution_for_tier(tier)

            # The render is an ALTERNATE attached to its shot (AL-1) — a
            # breached draft is still recorded, flagged needs_human, so the
            # evidence trail shows what was spent on it.
            artifact_ref = f"gs://{settings.gcs_bucket}/{destination_key}"
            alternate_id = shots.record_alternate(
                store,
                shot_id=shot_id,
                project_id=job.project_id,
                op="extend",
                artifact_ref=artifact_ref,
                eval_scores={"flicker": flicker},
                tier=tier,
            )

            analyzed_s = float(score.get("frames_analyzed") or 0) / 8.0
            job.cost_micros = estimate_extend_cost_micros(
                min(7.0, analyzed_s) or 7.0, resolution=resolution
            )
            job.result = {
                **job.result,
                "alternate_id": alternate_id,
                "artifact_ref": artifact_ref,
                "render_model": render_model,
                "omni_fallback": omni_fallback,
                "omni_error": omni_error_text,
                "flicker": flicker,
                "flicker_gate": FLICKER_GATE,
                "flicker_spike": spike,
                "flicker_spike_gate": FLICKER_SPIKE_GATE,
                "qc_decision": decision,
                "interaction_id": render.get("interaction_id"),
                "prompt": prompt,
                "tier": tier,
            }
            if decision != "pass":
                job.status = "needs_human"
                job.error = "extend_flicker_breach"
                outcome = "needs_human"
            else:
                outcome = "pass"
            log.info(
                "extend rendered",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "shot_id": shot_id,
                    "alternate_id": alternate_id,
                    "flicker": flicker,
                    "qc_decision": decision,
                    "render_model": render_model,
                    "omni_fallback": omni_fallback,
                    "tier": tier,
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
