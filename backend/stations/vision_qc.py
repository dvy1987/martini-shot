"""Per-render vision QC producer (2026-10-03).

The eval-only gap this closes: `backend/evals/vision_judge.py` could
detect ghosting/morphing the flicker meter is blind to, but no product
render path ever CALLED it — `eval_scores.vision_judge` was always
absent, and the draft bars treated `None` as a pass (fixed the same day
in draft_first.py / visual_qc.py). Every Stage 1a render now gets ONE
billed judge look (one retry on transient failure) before its alternate
is recorded; an unjudgeable render is needs_human — never a fake score
(C-1.1, C-3.5)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from backend.evals.vision_judge import judge_render_artifact
from backend.jobs.telemetry import log
from backend.supervisor.otel_ai import gemini_transient, run_agent_call

STATION = "vision_qc"

# Mirrors thresholds.yaml pickups_vision_judge and draft_first.VISION_BAR.
VISION_GATE = 4.0

_RETRY_SLEEP_S = 20.0  # transient 429/503 windows outlast a single look

_SPIKE_PROMPT = (
    "These are 3 CONSECUTIVE frames from a rendered video clip, at the "
    "moment a single-frame anomaly detector fired on the MIDDLE frame. "
    "Decide what the anomaly is. Answer ONLY with JSON: "
    '{"spike_kind": "cut|corruption", "note": "one sentence"}. '
    'spike_kind="cut" when the middle frame is a normal film-grammar '
    "scene cut or transition blend (the picture legitimately changes to "
    'a different shot). spike_kind="corruption" only when the middle '
    "frame shows damage a viewer would notice that is NOT a shot change: "
    "ghosting, duplicated limbs, smeared faces, blocky artifacts, torn "
    "geometry inside the same shot."
)

_SPIKE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spike_kind": {"type": "string", "enum": ["cut", "corruption"]},
        "note": {"type": "string"},
    },
    "required": ["spike_kind", "note"],
}


def download_artifact(settings: Any, gcs: Any, artifact_ref: str, work: Path) -> Path:
    clip = work / "artifact.mp4"
    clip.write_bytes(gcs.download_bytes(artifact_ref))
    return clip


def extract_frames_at(
    clip: Path, ffmpeg_bin: str, work: Path, *, count: int
) -> list[Path]:
    """fps=8 frame grid — the SAME sampling flicker_score uses, so spike
    frame indexes align (768px for judge legibility)."""
    import subprocess

    subprocess.run(
        [
            ffmpeg_bin,
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            "fps=8,scale=768:-2",
            "-frames:v",
            str(count),
            "-q:v",
            "2",
            str(work / "f_%03d.jpg"),
        ],
        check=True,
        timeout=120,
        capture_output=True,
    )
    return sorted(work.glob("f_*.jpg"))


def judge_spike_frame(
    settings: Any,
    gcs: Any,
    artifact_ref: str,
    *,
    spike_frame_index: int,
    job_id: str,
    station: str,
    project_id: str,
    work_dir: Path | None = None,
) -> dict[str, Any] | None:
    """ONE billed look at the spike frame ±1: real corruption, or a normal
    scene cut the 3-tap median flagged? 2026-10-03 smoke finding: a hard
    cut's transition-blend frame has the SAME single-frame signature as a
    glitch, and legitimate cuts were landing needs_human. The judge is the
    arbiter. Returns {'spike_kind': 'cut'|'corruption', note,
    judge_cost_micros} or None on failure (worst case, C-3.5)."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(work_dir) if work_dir else Path(tmp)
            work.mkdir(parents=True, exist_ok=True)
            clip = download_artifact(settings, gcs, artifact_ref, work)
            frames = extract_frames_at(clip, _ffmpeg_bin(settings), work, count=60)
            mid = min(max(spike_frame_index, 1), max(len(frames) - 2, 1))
            window = frames[mid - 1 : mid + 2]
            if len(window) < 1:
                log.info(
                    "spike frame window empty",
                    extra={
                        "job_id": job_id,
                        "station": station,
                        "project_id": project_id,
                        "spike_frame_index": spike_frame_index,
                    },
                )
                return None
            images = [(path.read_bytes(), "image/jpeg") for path in window]
            response = run_agent_call(
                settings,
                _SPIKE_PROMPT,
                span_name="station.vision_qc.spike_verdict",
                persona="pickups_vision_judge",
                response_schema=_SPIKE_SCHEMA,
                images=images,
            )
            import json as _json

            payload = _json.loads(str(response["text"]).strip())
            return {
                "spike_kind": str(payload["spike_kind"]),
                "note": str(payload.get("note") or "")[:200],
                "judge_cost_micros": int(response.get("cost_micros") or 0),
            }
    except Exception as exc:
        log.info(
            "spike verdict look failed",
            extra={
                "job_id": job_id,
                "station": station,
                "project_id": project_id,
                "error": f"{type(exc).__name__}: {exc}"[:200],
            },
        )
        return None


def _ffmpeg_bin(settings: Any) -> str:
    from backend.core.media import get_media

    return str(get_media(settings).ffmpeg_bin or "ffmpeg")


def draft_spike_decision(
    *, spike: float, spike_gate: float, spike_kind: str | None
) -> str:
    """The spike gate with eyes: a 'cut' verdict is film grammar, not a
    defect; corruption — or an unmeasured spike — is needs_human."""
    if spike < spike_gate:
        return "ok"
    return "ok" if spike_kind == "cut" else "needs_human"


def judge_render(
    settings: Any,
    gcs: Any,
    artifact_ref: str,
    *,
    job_id: str,
    station: str,
    project_id: str,
) -> dict[str, Any] | None:
    """One billed vision look at a rendered clip (gs:// URI). One retry on
    a transient Vertex failure (a quota window is not the model's verdict);
    any other failure — or a second transient — returns None. Callers must
    treat None as worst-case: vision unmeasured, render not cleared."""
    for attempt in (1, 2):
        try:
            payload = judge_render_artifact(settings, gcs, artifact_ref)
        except Exception as exc:
            log.info(
                "vision judge look failed",
                extra={
                    "job_id": job_id,
                    "station": station,
                    "project_id": project_id,
                    "attempt": attempt,
                    "error": f"{type(exc).__name__}: {exc}"[:200],
                },
            )
            if attempt == 1 and gemini_transient(exc):
                time.sleep(_RETRY_SLEEP_S)
                continue
            return None  # honest: unmeasured, never a fake score
        return {
            "vision_judge": float(payload["vision_judge"]),
            "artifact_rate": float(payload["artifact_rate"]),
            "judge_cost_micros": int(payload.get("cost_micros") or 0),
            "judge_frames": int(payload.get("frames") or 0),
        }
    return None


def vision_qc_decision(vision: float | None) -> str:
    """Draft QC: unmeasured or sub-bar vision = needs_human (C-3.5)."""
    if vision is None or vision < VISION_GATE:
        return "needs_human"
    return "pass"


def qc_reason(
    flicker: float,
    spike: float,
    vision: float | None,
    *,
    flicker_gate: float,
    spike_gate: float,
    vision_gate: float,
    spike_kind: str | None = None,
) -> str:
    """Human-readable WHY for the station's qc_decision — stored on the job
    result so a flagged render is diagnosable without reading station code
    (C-4.3 audit trail). Names the tripped gate first with the numbers."""
    vision_txt = "unmeasured" if vision is None else f"{vision:.2f}"
    parts = [
        f"flicker {flicker:.4f}",
        f"spike {spike:.4f}",
        f"vision {vision_txt}",
    ]
    breaches: list[str] = []
    if flicker >= flicker_gate:
        breaches.append(f"flicker {flicker:.4f} >= gate {flicker_gate}")
    if spike >= spike_gate:
        if spike_kind == "cut":
            parts.append(f"spike kind: {spike_kind} (film grammar, not a defect)")
        else:
            kind_txt = "" if spike_kind is None else f" [{spike_kind}]"
            breaches.append(f"spike {spike:.4f} >= gate {spike_gate}{kind_txt}")
    if vision is None:
        breaches.append("vision unmeasured (failed look = worst case, C-3.5)")
    elif vision < vision_gate:
        breaches.append(f"vision {vision:.2f} < gate {vision_gate}")
    if breaches:
        return "BREACH: " + "; ".join(breaches) + " | " + "; ".join(parts)
    return "clear: " + "; ".join(parts)
