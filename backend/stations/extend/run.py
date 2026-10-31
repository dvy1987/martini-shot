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
from backend.stations.vision_qc import VISION_GATE, judge_spike_frame
from backend.stations.vision_qc import judge_render as judge_vision_render
from backend.stations.vision_qc import qc_reason as qc_reason_text

STATION = "extend"

# Continuity gate (G0 evidence: healthy Omni extends scored 0.0013-0.0032;
# a broken render is an order of magnitude worse). Drafts breaching the gate
# land as needs_human — never silently pass.
FLICKER_GATE = 0.02
# The mean above dilutes one bad frame across dozens of clean ones
# (2026-09-09 demo: a real, visually-confirmed single-frame corruption
# scored ~0.005 mean, well under gate). spike is the worst single frame.
FLICKER_SPIKE_GATE = 0.02


def draft_qc_decision(
    flicker: float,
    spike: float = 0.0,
    vision: float | None = None,
    spike_kind: str | None = None,
) -> str:
    if flicker >= FLICKER_GATE:
        return "needs_human"
    if spike >= FLICKER_SPIKE_GATE and spike_kind != "cut":
        # A hard cut's blend frame spikes the same metric (2026-10-03
        # smoke finding); only a judge-confirmed corruption breaches.
        return "needs_human"
    if vision is None or vision < VISION_GATE:
        return "needs_human"  # vision unmeasured or sub-bar is not a pass
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
            tier = str(job.result.get("tier") or "draft")
            resolution = resolution_for_tier(tier)

            # The render is an ALTERNATE attached to its shot (AL-1) — a
            # breached draft is still recorded, flagged needs_human, so the
            # evidence trail shows what was spent on it.
            artifact_ref = f"gs://{settings.gcs_bucket}/{destination_key}"
            # Spike gate with eyes: a tripped spike escalates to ONE
            # targeted judge look (corruption vs a normal scene cut —
            # a cut's blend frame has the same single-frame signature).
            spike_kind = None
            spike_cost = 0
            if spike >= FLICKER_SPIKE_GATE:
                spike_verdict = judge_spike_frame(
                    settings,
                    gcs,
                    artifact_ref,
                    spike_frame_index=int(score.get("spike_frame_index") or 1),
                    job_id=job.id,
                    station=STATION,
                    project_id=job.project_id,
                )
                if spike_verdict is not None:
                    spike_kind = str(spike_verdict["spike_kind"])
                    spike_cost = int(spike_verdict["judge_cost_micros"])
            vision = judge_vision_render(
                settings,
                gcs,
                artifact_ref,
                job_id=job.id,
                station=STATION,
                project_id=job.project_id,
            )
            vision_score = None if vision is None else vision["vision_judge"]
            decision = draft_qc_decision(flicker, spike, vision_score, spike_kind)

            vision_scores = (
                {}
                if vision is None
                else {
                    "vision_judge": vision["vision_judge"],
                    "artifact_rate": vision["artifact_rate"],
                }
            )
            alternate_id = shots.record_alternate(
                store,
                shot_id=shot_id,
                project_id=job.project_id,
                op="extend",
                artifact_ref=artifact_ref,
                eval_scores={"flicker": flicker, **vision_scores},
                tier=tier,
            )

            analyzed_s = float(score.get("frames_analyzed") or 0) / 8.0
            job.cost_micros = estimate_extend_cost_micros(
                min(7.0, analyzed_s) or 7.0, resolution=resolution
            )
            job.cost_micros += 0 if vision is None else vision["judge_cost_micros"]
            job.cost_micros += spike_cost
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
                "flicker_spike_kind": spike_kind,
                "vision_judge": vision_score,
                "vision_gate": VISION_GATE,
                "judge_cost_micros": 0
                if vision is None
                else vision["judge_cost_micros"],
                "qc_decision": decision,
                "qc_reason": qc_reason_text(
                    flicker,
                    spike,
                    vision_score,
                    flicker_gate=FLICKER_GATE,
                    spike_gate=FLICKER_SPIKE_GATE,
                    vision_gate=VISION_GATE,
                    spike_kind=spike_kind,
                ),
                "interaction_id": render.get("interaction_id"),
                "prompt": prompt,
                "tier": tier,
            }
            if decision != "pass":
                job.status = "needs_human"
                if flicker >= FLICKER_GATE or (
                    spike >= FLICKER_SPIKE_GATE and spike_kind != "cut"
                ):
                    job.error = "extend_flicker_breach"
                elif vision_score is not None:
                    job.error = "extend_vision_breach"
                else:
                    job.error = "extend_vision_unmeasured"
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
                    "vision_judge": vision_score,
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
