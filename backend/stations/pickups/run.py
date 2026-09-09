"""Pickups station: measure flicker, Gemini vision QC, then actually repair."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.core.config import Settings, get_settings
from backend.core.gcs import GCSMedia
from backend.core.generative import estimate_extend_cost_micros
from backend.core.media import FFmpeg
from backend.jobs.models import Job
from backend.jobs.telemetry import (
    job_span,
    log,
    record_flicker,
    record_job,
    timed,
)
from backend.stations.pickups.anchors import (
    build_anchor_prompt,
    build_regenerate_prompt,
)
from backend.stations.pickups.cost import estimate_micros
from backend.stations.pickups.flicker import flicker_score
from backend.stations.pickups.repair import render_pickup_repair
from backend.stations.pickups.retry import MAX_RETRIES, STABILIZE_RETRIES
from backend.supervisor.station_agents.pickups_vision_qc import decide_pickups_vision_qc

STATION = "pickups"
FLICKER_THRESHOLD = 0.18
# Hard gate (not judge-only): 2026-09-09 demo — a real, visually-confirmed
# single-frame corruption scored ~0.005 mean (well under 0.18) because the
# whole-clip average dilutes one bad frame across dozens of clean ones.
# spike_score is the worst single frame; clean clips measured ~0.0003-0.01
# here, the real defect ~0.032 — 0.02 sits between the two with margin.
FLICKER_SPIKE_THRESHOLD = 0.02
MICROS_PER_FRAME = 0  # identity extract is unbilled; repairs meter separately

JudgeFn = Callable[..., tuple[Any, int]]
RepairFn = Callable[..., dict[str, Any]]


def as_gs_uri(ref: str, bucket: str) -> str:
    text = (ref or "").strip()
    if text.startswith("gs://"):
        return text
    return f"gs://{bucket}/{text.lstrip('/')}"


def _measure(
    payload: bytes, folder: Path, media: FFmpeg
) -> tuple[list[Path], dict[str, Any]]:
    src = folder / "src.mp4"
    src.write_bytes(payload)
    frames_dir = folder / "frames"
    frames = media.extract_frames(src, frames_dir, fps=8.0)
    out = folder / "roundtrip.mp4"
    media.reassemble(frames, out, fps=8.0)
    return frames, flicker_score(out, media.ffmpeg_bin)


def run_pickups(
    job: Job,
    gcs: GCSMedia,
    media: FFmpeg,
    *,
    settings: Settings | None = None,
    judge: JudgeFn | None = None,
    repair: RepairFn | None = None,
) -> Job:
    started = timed()
    outcome = "fail"
    settings = settings or get_settings()
    judge = judge or decide_pickups_vision_qc
    repair = repair or render_pickup_repair
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("pickups requires media")
            payload = gcs.download_bytes(job.input_refs[0])
            source_uri = as_gs_uri(job.input_refs[0], settings.gcs_bucket)
            retries_used = 0
            repaired = False
            omni_fallback = False
            omni_error_text = ""
            agent_costs: list[int] = []
            render_cost = 0
            last_agent: dict[str, Any] = {}
            frames: list[Path] = []
            score: dict[str, Any] = {}
            artifact_ref = ""

            with tempfile.TemporaryDirectory() as tmp:
                while True:
                    folder = Path(tmp) / f"pass-{retries_used}"
                    folder.mkdir()
                    frames, score = _measure(payload, folder, media)
                    flicker = float(score.get("flicker_score") or 1.0)
                    spike = float(score.get("spike_score") or 0.0)
                    spike_breach = spike >= FLICKER_SPIKE_THRESHOLD
                    record_flicker(STATION, flicker)
                    # ADR-0005: vision QC is a temporal judge — it watches
                    # the real rendered clip (video part), not stills.
                    report = {
                        "flicker": flicker,
                        "threshold": FLICKER_THRESHOLD,
                        "spike": spike,
                        "spike_threshold": FLICKER_SPIKE_THRESHOLD,
                        "frames_analyzed": int(
                            score.get("frames_analyzed") or len(frames)
                        ),
                        "retries_used": retries_used,
                        "ok": bool(score.get("ok", True)),
                    }
                    decision, agent_cost = judge(
                        settings, report=report, video=(payload, "video/mp4")
                    )
                    agent_costs.append(int(agent_cost))
                    last_agent = decision.to_doc()
                    name = str(decision.decision)
                    if name == "accept" and spike_breach:
                        # A localized single-frame defect breached the
                        # deterministic gate even though the judge accepted
                        # on the diluted whole-clip mean — do not pass.
                        name = "needs_human" if retries_used >= MAX_RETRIES else "retry"
                    if name == "accept":
                        outcome = "pass"
                        break
                    if name == "needs_human" or retries_used >= MAX_RETRIES:
                        job.status = "needs_human"
                        job.error = (
                            "flicker_spike_breach"
                            if spike_breach
                            else (
                                "pickups_needs_human"
                                if str(decision.decision) == "needs_human"
                                else "flicker_breach"
                            )
                        )
                        outcome = "needs_human"
                        break
                    op = str(job.result.get("op") or "pickup_repair")
                    hint = str(
                        job.result.get("hint")
                        or job.result.get("intent")
                        or "Repair damaged or unstable frames. "
                        "Preserve subjects, framing, and continuity."
                    )
                    # ADR-0005 ladder: attempts 1–2 stabilize with stronger
                    # anchors; from attempt 3 regenerate the WHOLE clip from
                    # the accepted references.
                    if retries_used >= STABILIZE_RETRIES:
                        prompt = build_regenerate_prompt(hint)
                    else:
                        prompt = build_anchor_prompt(op, hint, strengthen=True)
                    rendered = repair(settings, input_uri=source_uri, prompt=prompt)
                    payload = bytes(rendered["video_bytes"])
                    dest_key = f"projects/{job.project_id}/pickups/{job.id}.mp4"
                    gcs.upload_bytes(dest_key, payload, content_type="video/mp4")
                    artifact_ref = f"gs://{settings.gcs_bucket}/{dest_key}"
                    source_uri = artifact_ref
                    repaired = True
                    retries_used += 1
                    render_cost += estimate_extend_cost_micros(7.0, resolution="360p")
                    if rendered.get("omni_fallback"):
                        omni_fallback = True
                        omni_error_text = str(rendered.get("omni_error") or "")

            job.cost_micros = (
                estimate_micros(len(frames), MICROS_PER_FRAME)
                + render_cost
                + sum(agent_costs)
            )
            job.result = {
                **job.result,
                "flicker": score,
                "frames": len(frames),
                "agent": last_agent,
                "repaired": repaired,
                "retries_used": retries_used,
                "omni_fallback": omni_fallback,
                "omni_error": omni_error_text,
                "artifact_ref": artifact_ref,
            }
            log.info(
                "pickups qc done",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "flicker_score": float(score.get("flicker_score") or 1.0),
                    "agent_decision": last_agent.get("decision"),
                    "repaired": repaired,
                    "omni_fallback": omni_fallback,
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
