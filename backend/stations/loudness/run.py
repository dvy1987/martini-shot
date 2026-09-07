"""Loudness station: hear the mix, pick a scene-fitting level, apply, re-measure.

The meter still wins on the number. The strategist listens and chooses WHICH
number (whisper quieter than talk; an explosion or a crash of pans louder).
The station then actually mixes — it does not stop at needs_human.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

from backend.core.gcs import GCSMedia
from backend.core.media import FFmpeg, _as_int
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, record_loudness, timed
from backend.stations.loudness.scene import (
    SCENE_CLASSES,
    SPEECH_FLOOR_LUFS,
    clamp_agent_target,
    scene_target_lufs,
    season_median_lufs,
)
from backend.stations.loudness.verdict import (
    STREAMING_TARGET_LUFS,
    me_present,
    stem_diagnosis,
    verdict,
)
from backend.supervisor.station_agents import loudness_strategy as strategy_mod

STATION = "loudness"
JOBS_COLLECTION = "pc-jobs"


def resolve_audio_ref(job: Job, store: Any | None) -> tuple[str, str]:
    """Prefer the sibling dub WAV; fall back to the picture soundtrack.

    Returns (gcs_ref, kind) where kind is 'dub' or 'picture'. The
    orchestrator stamps `result.dub_job_id` so this lookup is deterministic.
    """
    if not job.input_refs:
        raise ValueError("loudness requires a media object")
    picture = job.input_refs[0]
    dub_job_id = str(job.result.get("dub_job_id") or "")
    if not dub_job_id or store is None:
        return picture, "picture"
    doc = store.get_doc(JOBS_COLLECTION, dub_job_id)
    if not doc:
        return picture, "picture"
    ref = str((doc.get("result") or {}).get("artifact_ref") or "")
    if not ref:
        return picture, "picture"
    return ref, "dub"


def _suffix_for(ref: str) -> str:
    name = ref.rsplit("/", 1)[-1].lower()
    if "." in name:
        return "." + name.rsplit(".", 1)[-1]
    return ".mp4"


def _mime_for(suffix: str) -> str:
    if suffix == ".wav":
        return "audio/wav"
    if suffix in {".mp3", ".mpeg"}:
        return "audio/mpeg"
    return "audio/mp4"


def run_loudness(
    job: Job,
    gcs: GCSMedia,
    media: FFmpeg,
    store: Any | None = None,
    settings: Any | None = None,
) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            audio_ref, audio_kind = resolve_audio_ref(job, store)
            payload = gcs.download_bytes(audio_ref)
            suffix = _suffix_for(audio_ref)
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(payload)
                src = Path(handle.name)
            mixed_path: Path | None = None
            try:
                report = media.loudness_report(src)
                probe = media.probe(src)
                dialogue = media.band_lufs(src, 300, 3000)
                music = media.band_lufs(src, 4000, 12000)
                lufs = float(report["lufs"])
                peak = report.get("true_peak_dbtp")
                stems = stem_diagnosis(dialogue, music)

                season_rows: list[dict[str, Any]] = []
                batch_id = str(job.result.get("batch_id") or "")
                if store is not None and batch_id and hasattr(store, "list_where"):
                    from backend.supervisor.batch_state import (
                        read_loudness_season_state,
                    )

                    season_rows = read_loudness_season_state(store, batch_id)
                median = season_median_lufs(
                    [float(r["lufs"]) for r in season_rows if r.get("lufs") is not None]
                )

                agent_cost = 0
                scene_class = "dialogue"
                agent_doc: dict[str, Any] | None = None
                streaming_verdict = verdict(
                    lufs, target=STREAMING_TARGET_LUFS, true_peak_dbtp=peak
                )
                agent_report = {
                    "job_id": job.id,
                    "episode_id": job.result.get("episode_id"),
                    "source_ref": audio_ref,
                    "audio_kind": audio_kind,
                    "lufs_integrated": lufs,
                    "true_peak_dbtp": peak,
                    "verdict_streaming": streaming_verdict,
                    "verdict_broadcast": verdict(
                        lufs, target=-24.0, true_peak_dbtp=peak
                    ),
                    "stem_diagnosis": stems,
                    "dialogue_band_lufs": dialogue,
                    "music_band_lufs": music,
                }
                shot_id = str(job.result.get("shot_id") or "")
                if store is not None and shot_id:
                    from backend.supervisor.station_agents.ingest_understand import (
                        scene_understanding_from_shot,
                    )

                    scene_meta = scene_understanding_from_shot(store, shot_id)
                    if scene_meta:
                        agent_report["scene_notes"] = str(scene_meta.get("scene") or "")
                        agent_report["spoken_words"] = str(
                            scene_meta.get("spoken_words") or ""
                        )
                if settings is not None:
                    decision, agent_cost = strategy_mod.decide_loudness_strategy(
                        settings,
                        report=agent_report,
                        season_state=season_rows,
                        audio=(payload, _mime_for(suffix)),
                    )
                    agent_doc = decision.to_doc()
                    raw_class = str(decision.raw.get("scene_class") or "dialogue")
                    if raw_class in SCENE_CLASSES:
                        scene_class = raw_class
                    raw_target = decision.raw.get("target_lufs")
                    table = scene_target_lufs(scene_class, season_median=median)
                    if isinstance(raw_target, (int, float)):
                        target = clamp_agent_target(float(raw_target), table)
                    else:
                        target = table
                    # Meter error stays a human flag; every other path mixes.
                    skip_mix = decision.decision == "needs_human" and (
                        streaming_verdict == "meter_error" or report.get("lufs") is None
                    )
                else:
                    scene_class = str(job.result.get("scene_class") or "dialogue")
                    if scene_class not in SCENE_CLASSES:
                        scene_class = "dialogue"
                    target = scene_target_lufs(scene_class, season_median=median)
                    skip_mix = False
                peak_n = float(peak) if peak is not None else None
                if not math.isfinite(lufs) or (
                    peak_n is not None and not math.isfinite(peak_n)
                ):
                    skip_mix = True

                mixed = False
                if not skip_mix:
                    pre = verdict(lufs, target=target, true_peak_dbtp=peak)
                    if pre != "pass":
                        mixed_path = src.with_name(src.stem + "-mixed" + suffix)
                        media.apply_loudnorm(
                            src,
                            mixed_path,
                            integrated_lufs=target,
                            true_peak_dbtp=-1.5,
                        )
                        report = media.loudness_report(mixed_path)
                        lufs = float(report["lufs"])
                        peak = report.get("true_peak_dbtp")
                        dialogue = media.band_lufs(mixed_path, 300, 3000)
                        music = media.band_lufs(mixed_path, 4000, 12000)
                        stems = stem_diagnosis(dialogue, music)
                        mixed = True

                decision_code = verdict(lufs, target=target, true_peak_dbtp=peak)
                speech = scene_class in {"whisper", "dialogue", "shout"}
                unintelligible = speech and lufs < (SPEECH_FLOOR_LUFS - 1.0)

                artifact_ref = None
                alternate_id = None
                if mixed and mixed_path is not None:
                    mixed_bytes = mixed_path.read_bytes()
                    destination_key = (
                        f"projects/{job.project_id}/loudness/{job.id}{suffix}"
                    )
                    gcs.upload_bytes(
                        destination_key,
                        mixed_bytes,
                        content_type=_mime_for(suffix),
                    )
                    bucket = str(getattr(settings, "gcs_bucket", "") or "local")
                    artifact_ref = f"gs://{bucket}/{destination_key}"
                    shot_id = str(job.result.get("shot_id") or "")
                    if store is not None and shot_id:
                        from backend.shots import lifecycle as shots

                        alternate_id = shots.record_alternate(
                            store,
                            shot_id=shot_id,
                            project_id=job.project_id,
                            op="loudness_mix",
                            artifact_ref=artifact_ref,
                            eval_scores={"lufs": lufs, "target_lufs": target},
                        )

                job.cost_micros = int(agent_cost)
                job.result = {
                    **job.result,
                    "lufs": lufs,
                    "true_peak_dbtp": peak,
                    "lra": report.get("lra"),
                    "target_lufs": target,
                    "scene_class": scene_class,
                    "verdict": decision_code,
                    "stems": stems,
                    "me_present": me_present(_as_int(probe.get("audio_streams"))),
                    "audio_kind": audio_kind,
                    "audio_ref": audio_ref,
                    "mixed": mixed,
                    "artifact_ref": artifact_ref,
                    "alternate_id": alternate_id,
                    "agent": agent_doc,
                    "agent_cost_micros": int(agent_cost),
                }
                record_loudness(STATION, lufs)
                if skip_mix or decision_code != "pass" or unintelligible:
                    job.status = "needs_human"
                    job.error = (
                        "unintelligible"
                        if unintelligible and decision_code == "pass"
                        else decision_code
                    )
                    outcome = job.error or "needs_human"
                else:
                    outcome = "pass"
                log.info(
                    "loudness mixed" if mixed else "loudness measured",
                    extra={
                        "job_id": job.id,
                        "station": STATION,
                        "project_id": job.project_id,
                        "lufs": lufs,
                        "target_lufs": target,
                        "scene_class": scene_class,
                        "verdict": decision_code,
                        "audio_kind": audio_kind,
                        "mixed": mixed,
                    },
                )
                return job
            finally:
                src.unlink(missing_ok=True)
                if mixed_path is not None:
                    mixed_path.unlink(missing_ok=True)
        finally:
            record_job(
                STATION,
                duration_s=timed() - started,
                cost_micros=job.cost_micros,
                outcome=outcome,
            )
