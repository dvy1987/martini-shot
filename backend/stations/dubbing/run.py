"""Dubbing station (E-2, A10): Chirp 3 HD TTS render of one line, then the
Dub QC Agent (real Gemini listen) judges it with the deterministic timing
measurement as advisory input.

Decision flow:
  synthesize → measure timing (deterministic) → agent decision
  - accept     → job passes, ALTERNATE attached
  - re_render  → ONE pace-adjusted re-render (agent's pace_adjustment),
                 re-measure, agent decides again — second verdict is final
  - needs_human→ flagged, ALTERNATE still attached with the evidence trail
"""

from __future__ import annotations

import re
from typing import Any

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.core.gcs import GCSMedia
from backend.core.generative import tts_synthesize
from backend.jobs.models import Job
from backend.jobs.telemetry import job_span, log, record_job, timed
from backend.shots import lifecycle as shots
from backend.stations.dubbing.qc import atempo_wav, measure_timing, source_wav
from backend.supervisor.station_agents.dub_qc import decide_dub

STATION = "dub"
DUB_TOLERANCE_MS = 45  # mirrors thresholds.yaml dub_timing gate (MAE ≤45 ms)


def time_fit_dub(
    settings: Settings,
    *,
    ssml: str,
    language: str,
    original_wav: bytes,
    first_wav: bytes,
    synthesize: Any = tts_synthesize,
    voice_name: str | None = None,
    ffmpeg_bin: str | None = None,
) -> dict[str, Any]:
    """Deterministic time-fit — how a dubbing studio fits a translation to
    picture: ONE TTS render, then ffmpeg atempo time-compresses the ACTUAL
    waveform to the source window. Exact (no re-render lottery: Chirp's
    rate response measured nonlinear, 0.8 → 1.34x, and render lengths
    vary run-to-run), pitch-preserving, free, local. Refuses tempos outside
    ffmpeg's [0.5, 2.0] band — a 2x-off dub is not a pacing problem
    (wrong line or segmentation) and must not be mangled (C-1.1)."""
    del ssml, language, synthesize, voice_name  # fit is local; kept in the
    # signature so callers stay stable if a re-render fallback is ever added
    wav = first_wav
    measurements = measure_timing(original_wav, wav, tolerance_ms=DUB_TOLERANCE_MS)
    tempo = 1.0
    fit_applied = False
    if measurements["verdict"] == "flagged":
        source_ms = float(measurements["source_duration_ms"])
        dub_ms = float(measurements["dub_duration_ms"])
        if source_ms > 0 and dub_ms > 0:
            tempo = dub_ms / source_ms  # too long → speed up
            if 0.5 <= tempo <= 2.0:
                fitted = atempo_wav(
                    wav, tempo, ffmpeg_bin=ffmpeg_bin or settings.ffmpeg_bin or "ffmpeg"
                )
                fitted_m = measure_timing(
                    original_wav, fitted, tolerance_ms=DUB_TOLERANCE_MS
                )
                # Keep the stretch only if it actually closed the gap.
                if abs(fitted_m["duration_delta_ms"]) < abs(
                    measurements["duration_delta_ms"]
                ):
                    wav, measurements, fit_applied = fitted, fitted_m, True
                else:
                    tempo = 1.0
    return {
        "wav": wav,
        "measurements": measurements,
        "tempo": tempo,
        "fit_applied": fit_applied,
    }


def final_status(decision: str) -> str:
    """Agent decision → job status. A re_render that already used its one
    retry lands as needs_human (never an infinite render loop)."""
    return "pass" if decision == "accept" else "needs_human"


def run_dub(job: Job, gcs: GCSMedia, store: FirestoreStore, settings: Settings) -> Job:
    started = timed()
    outcome = "fail"
    with job_span(STATION, job.id, job.project_id):
        try:
            if not job.input_refs:
                raise ValueError("dub requires a source media ref")
            source_uri = job.input_refs[0]
            if not source_uri.startswith("gs://"):
                raise ValueError(f"dub source must be a gs:// URI, got {source_uri!r}")
            shot_id = str(job.result.get("shot_id") or "")
            if not shot_id:
                raise ValueError("dub requires result.shot_id")
            ssml = str(job.result.get("ssml") or "")
            if not ssml:
                raise ValueError("dub requires result.ssml (target-language line)")
            language = str(job.result.get("language") or "")
            if not language:
                raise ValueError("dub requires result.language (e.g. 'es')")

            # The source may be any real container (the E-3 batch feeds
            # MP4s) — decode to the contract WAV before measuring. The dub
            # ref points at the ORIGINAL clip, not a pre-extracted stem.
            original_wav = source_wav(
                gcs.download_bytes(source_uri),
                ffmpeg_bin=settings.ffmpeg_bin or "ffmpeg",
            )
            agent_costs: list[int] = []
            tts_cost = 0

            render = tts_synthesize(settings, ssml=ssml, language_code=language)
            tts_cost += int(render["cost_estimate_micros"])

            # Deterministic fit pass first: a translated line renders at a
            # different natural length; atempo time-fit it to the source
            # window BEFORE the agent judges, so the agent evaluates
            # final-quality audio, not a pacing draft.
            fit = time_fit_dub(
                settings,
                ssml=ssml,
                language=language,
                original_wav=original_wav,
                first_wav=bytes(render["audio_bytes"]),
            )
            dub_wav = fit["wav"]
            measurements = fit["measurements"]
            # The agent judges against the reference line (script), so
            # missing content is detectable, not just cut audio.
            script = re.sub(r"<[^>]+>", "", ssml).strip()

            # The agent judges the (fitted) dub. One fresh re-render remains
            # for artifacts/truncation the fit didn't fix (voice renders are
            # nondeterministic) — second verdict is final.
            decision, agent_cost = decide_dub(
                settings,
                measurements=measurements,
                dubbed_wav=dub_wav,
                script=script,
            )
            agent_costs.append(agent_cost)

            re_rendered = False
            if decision.decision == "re_render":
                retry = tts_synthesize(settings, ssml=ssml, language_code=language)
                tts_cost += int(retry["cost_estimate_micros"])
                retry_wav = bytes(retry["audio_bytes"])
                # The re-render gets the same time-fit treatment.
                retry_fit = time_fit_dub(
                    settings,
                    ssml=ssml,
                    language=language,
                    original_wav=original_wav,
                    first_wav=retry_wav,
                )
                retry_wav = retry_fit["wav"]
                retry_measurements = retry_fit["measurements"]
                if abs(retry_measurements["duration_delta_ms"]) <= abs(
                    measurements["duration_delta_ms"]
                ):
                    dub_wav, measurements = retry_wav, retry_measurements
                re_rendered = True
                decision, agent_cost = decide_dub(
                    settings,
                    measurements=measurements,
                    dubbed_wav=dub_wav,
                    script=script,
                )
                agent_costs.append(agent_cost)
            status = final_status(decision.decision)

            destination_key = f"projects/{job.project_id}/dubs/{job.id}.{language}.wav"
            gcs.upload_bytes(destination_key, dub_wav, content_type="audio/wav")
            artifact_ref = f"gs://{settings.gcs_bucket}/{destination_key}"

            # The dub is an ALTERNATE on its shot (AL-1) — flagged verdicts
            # are still recorded so the spend is visible in the audit trail.
            alternate_id = shots.record_alternate(
                store,
                shot_id=shot_id,
                project_id=job.project_id,
                op=f"dub_{language}",
                artifact_ref=artifact_ref,
                eval_scores={
                    "duration_delta_ms": measurements["duration_delta_ms"],
                    "sync_offset_ms": measurements["sync_offset_ms"],
                },
            )

            # Cost: billed TTS characters + metered agent calls (C-6.4).
            job.cost_micros = tts_cost + sum(agent_costs)
            job.result = {
                **job.result,
                "alternate_id": alternate_id,
                "artifact_ref": artifact_ref,
                "language": language,
                "measurements": measurements,
                "fit_applied": fit["fit_applied"],
                "fit_tempo": round(fit["tempo"], 4),
                "agent": decision.to_doc(),
                "agent_cost_micros": sum(agent_costs),
                "re_rendered": re_rendered,
            }
            job.status = status
            if status == "pass":
                outcome = "pass"
            else:
                job.error = "dub_qc_flagged"
                outcome = "needs_human"
            log.info(
                "dub rendered and judged",
                extra={
                    "job_id": job.id,
                    "station": STATION,
                    "project_id": job.project_id,
                    "shot_id": shot_id,
                    "language": language,
                    "alternate_id": alternate_id,
                    "agent_decision": decision.decision,
                    "agent_override": decision.overridden,
                    "re_rendered": re_rendered,
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
