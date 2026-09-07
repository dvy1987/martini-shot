"""Delivery station: probe + loudness + captions (write missing, edit broken)."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.media import FFmpeg
from backend.jobs.models import Job, utc_now_iso
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.stations.delivery.evaluate import evaluate_delivery
from backend.stations.delivery.prepare import prepare_captions

STATION = "delivery"
REPORTS = "pc-morning-reports"
JOBS_COLLECTION = "pc-jobs"


def resolve_delivery_media(job: Job, store: Any | None) -> tuple[str, str]:
    """Prefer the loudness mix so delivery grades the fixed audio."""
    if not job.input_refs:
        raise ValueError("delivery requires media")
    picture = job.input_refs[0]
    loud_id = str(job.result.get("loudness_job_id") or "")
    if not store or not loud_id:
        return picture, "picture"
    doc = store.get_doc(JOBS_COLLECTION, loud_id)
    if not doc:
        return picture, "picture"
    ref = str((doc.get("result") or {}).get("artifact_ref") or "")
    if not ref:
        return picture, "picture"
    return ref, "loudness_mix"


def run_delivery(
    job: Job,
    gcs: GCSMedia,
    store: FirestoreStore,
    media: FFmpeg,
    settings: Any | None = None,
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            media_ref, media_kind = resolve_delivery_media(job, store)
            payload = gcs.download_bytes(media_ref)
            existing_srt = None
            if len(job.input_refs) > 1:
                existing_srt = gcs.download_bytes(job.input_refs[1]).decode(
                    "utf-8", "replace"
                )
            suffix = ".wav" if media_ref.lower().endswith(".wav") else ".mp4"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(payload)
                tmp = Path(handle.name)
            try:
                probe = media.probe(tmp)
                lufs = media.loudness_lufs(tmp)
                duration_s = float(probe.get("duration_s") or 0.0)
            finally:
                tmp.unlink(missing_ok=True)
            mime = "audio/wav" if suffix == ".wav" else "audio/mp4"
            script = str(job.result.get("script") or "")
            shot_id = str(job.result.get("shot_id") or "")
            scene_meta = None
            if store is not None and shot_id:
                from backend.supervisor.station_agents.ingest_understand import (
                    scene_understanding_from_shot,
                )

                scene_meta = scene_understanding_from_shot(store, shot_id)
                if scene_meta and not script.strip():
                    script = str(scene_meta.get("spoken_words") or "")
            speech = (
                bool(scene_meta.get("has_speech"))
                if scene_meta is not None
                else bool(script.strip())
            )
            srt, cap_meta = prepare_captions(
                existing_srt=existing_srt,
                script=script,
                duration_s=duration_s,
                settings=settings,
                audio=(payload, mime),
                lufs=lufs,
                loudness_job_id=str(job.result.get("loudness_job_id") or ""),
                has_speech=speech,
            )
            caption_ref = None
            alternate_id = None
            if srt:
                key = f"projects/{job.project_id}/captions/{job.id}.srt"
                gcs.upload_bytes(key, srt.encode("utf-8"), content_type="text/plain")
                bucket = str(getattr(settings, "gcs_bucket", "") or "local")
                caption_ref = f"gs://{bucket}/{key}"
                shot_id = str(job.result.get("shot_id") or "")
                if store is not None and shot_id:
                    from backend.shots import lifecycle as shots

                    alternate_id = shots.record_alternate(
                        store,
                        shot_id=shot_id,
                        project_id=job.project_id,
                        op="captions",
                        artifact_ref=caption_ref,
                        eval_scores={"caption_cues": 1.0},
                    )
            destination = str(job.result.get("destination") or "streaming")
            report = evaluate_delivery(
                destination=destination,
                probe=probe,
                lufs=lufs,
                caption_text=srt,
                caption_name="captions.srt",
            )
            job.cost_micros = int(cap_meta.get("cost_micros") or 0)
            job.result = {
                **job.result,
                "delivery": report,
                "lufs": lufs,
                "media_kind": media_kind,
                "media_ref": media_ref,
                "caption_source": cap_meta.get("source"),
                "caption_ref": caption_ref,
                "alternate_id": alternate_id,
                "agent_cost_micros": job.cost_micros,
            }
            note = cap_meta.get("orchestrator_note")
            if note is not None:
                job.result["orchestrator_note"] = note
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
                    "caption_source": cap_meta.get("source"),
                    "media_kind": media_kind,
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
