"""Vision-judge metric for the never-run thresholds.yaml gates
(pickups_vision_judge: mean_vision_judge >= 4.0; pickups_artifact_rate:
artifact_rate < 0.08).

One metered Gemini vision call per clip SEES the real frame extracts and
scores texture/stability quality 1-5 plus which frames carry visible
artifacts. Pure parsing/aggregation lives here (unit-tested); the live
judgment is gated by scripts/pickups_vision_judge_eval.py (C-3.3/.4).
No canned scores (C-1.1): every number comes from the billed look.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

VISION_BAR = 4.0
ARTIFACT_BAR = 0.08
FRAMES_PER_CLIP = 6

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vision_judge": {"type": "number"},
        "artifact_frames": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "reason": {"type": "string"},
    },
    "required": ["vision_judge", "artifact_frames"],
}

JUDGE_PROMPT = (
    "You are the pickups vision-judge meter for Martini Shot. Attached: "
    "real frame extracts, in order, from one rendered pickup clip.\n"
    "Score the clip's visible TEXTURE and STABILITY quality for a viewer "
    "on a 1-5 scale (5 = clean and stable; 4 = minor cosmetic issues a "
    "viewer barely notices; 3 = visible artifacts a viewer notices; "
    "2 = ugly and distracting; 1 = broken/corrupted). Smooth gradients, "
    "soft lighting, and dark or low-contrast footage are CLEAN; hard "
    "edges from in-shot content are CONTENT, not defects.\n"
    "Artifacts to hunt: corruption, heavy noise, blockiness/banding, "
    "ghosting, smeared motion, color smearing, flicker between frames, "
    "camera instability the shot does not motivate.\n"
    "List the 0-based indices of frames that carry a visible artifact an "
    "ordinary viewer would notice. Be exact: do not pad the list with "
    "clean frames, do not hide artifacts to be nice.\n"
    'Respond ONLY with JSON: {"vision_judge": <1-5>, '
    '"artifact_frames": [<0-based indices>], "reason": "<one sentence>"}.'
)


def parse_judge_payload(text: str, n_frames: int) -> dict[str, Any]:
    """Strict parse of the judge's JSON. Raises ValueError on garbage —
    the eval counts a failed call as a miss (C-3.5 honest accounting)."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge payload not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("judge payload must be an object")
    try:
        score = float(payload["vision_judge"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("vision_judge must be a number") from exc
    if not 1.0 <= score <= 5.0:
        raise ValueError(f"vision_judge {score} outside 1-5")
    raw_indices = payload.get("artifact_frames")
    if not isinstance(raw_indices, list):
        raise ValueError("artifact_frames must be a list")
    indices: list[int] = []
    for item in raw_indices:
        try:
            index = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"artifact frame index {item!r} not an int") from exc
        if not 0 <= index < n_frames:
            raise ValueError(f"artifact frame index {index} out of range")
        indices.append(index)
    rate = (len(set(indices)) / n_frames) if n_frames else 1.0
    return {
        "vision_judge": score,
        "artifact_frames": sorted(set(indices)),
        "artifact_rate": round(rate, 5),
        "reason": str(payload.get("reason") or ""),
    }


def summarize_judgments(
    records: list[dict[str, Any]], *, detection_threshold: float = 0.8
) -> dict[str, Any]:
    """Aggregate per-clip judgments against per-clip expectations.

    Thresholds.yaml semantics (C-3.4), computed over the EXPECTED-CLEAR
    subset — "a render that should clear the bars must clear them":
    - pickups_vision_judge:  mean_vision_judge >= 4.0
    - pickups_artifact_rate: artifact_rate      <  0.08
    A defective-expected clip that IS flagged is a detection HIT, not a
    gate breach; one that slips through is a miss (C-3.5 honest
    accounting). A record missing metrics (failed call) counts as
    worst-case: a clear-clip miss AND a detection miss.
    """
    n = len(records)
    if n == 0:
        return {
            "mean_vision_judge": 0.0,
            "artifact_rate": 1.0,
            "mean_case_accuracy": 0.0,
            "n": 0,
            "pass": False,
            "fail_reason": "no_records",
        }
    clear = [row for row in records if str(row.get("expected") or "") == "clear"]
    scores = [
        float(row["vision_judge"])
        for row in clear
        if isinstance(row.get("vision_judge"), (int, float))
    ]
    rates = [
        float(row["artifact_rate"])
        for row in clear
        if isinstance(row.get("artifact_rate"), (int, float))
    ]
    mean = sum(scores) / len(scores) if scores else 0.0
    rate = sum(rates) / len(rates) if rates else 1.0
    hits = 0
    for row in records:
        judged = isinstance(row.get("vision_judge"), (int, float)) and (
            isinstance(row.get("artifact_rate"), (int, float))
        )
        flagged = judged and (
            float(row["vision_judge"]) < VISION_BAR
            or float(row["artifact_rate"]) >= ARTIFACT_BAR
        )
        if str(row.get("expected") or "") == "clear":
            hits += int(judged and not flagged)
        else:
            hits += int(judged and flagged)
    accuracy = hits / n
    fail_reasons: list[str] = []
    if len(scores) != len(clear):
        fail_reasons.append("missing_vision_judge")
    if len(rates) != len(clear):
        fail_reasons.append("missing_artifact_rate")
    if mean < VISION_BAR:
        fail_reasons.append("vision_judge_gate")
    if rate >= ARTIFACT_BAR:
        fail_reasons.append("artifact_rate_gate")
    if accuracy < detection_threshold:
        fail_reasons.append("detection_accuracy_gate")
    return {
        "mean_vision_judge": round(mean, 5),
        "artifact_rate": round(rate, 5),
        "mean_case_accuracy": round(accuracy, 5),
        "n": n,
        "pass": not fail_reasons,
        "fail_reason": ",".join(fail_reasons),
    }


def extract_frames(
    clip: Path, ffmpeg_bin: str, work: Path, *, n: int = FRAMES_PER_CLIP
) -> list[Path]:
    """Real frame extracts (JPEG) for the judge — 768px, fps=3.

    2026-10-02 lesson: 4-frame/512px sampling FLIPPED verdicts on p07/p10
    (undersampling masks morphing/jitter); this sampling is stable 3/3."""
    result = subprocess.run(
        [
            ffmpeg_bin,
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            "fps=3,scale=768:-2",
            "-frames:v",
            str(n),
            "-q:v",
            "2",
            str(work / "f_%02d.jpg"),
        ],
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {clip.name}: {result.stderr[:200]!r}")
    return sorted(work.glob("f_*.jpg"))


def judge_render_artifact(
    settings: Any,
    gcs: Any,
    artifact_ref: str,
    *,
    frames: int = FRAMES_PER_CLIP,
) -> dict[str, Any]:
    """One billed judge look at a rendered clip artifact (gs:// URI).

    Download, extract real frames, one metered Gemini call. Raises on any
    failure — callers record it as a worst-case miss (C-3.5, C-1.1)."""
    from backend.core.media import get_media
    from backend.supervisor.otel_ai import run_agent_call

    media = get_media(settings)
    data = gcs.download_bytes(artifact_ref)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "artifact.mp4"
        src.write_bytes(data)
        extracts = extract_frames(src, media.ffmpeg_bin, Path(tmp), n=frames)
        if not extracts:
            raise RuntimeError(f"no frames extracted from {artifact_ref}")
        images = [(path.read_bytes(), "image/jpeg") for path in extracts]
        response = run_agent_call(
            settings,
            JUDGE_PROMPT,
            span_name="eval.vision_judge_render",
            persona="pickups_vision_judge",
            response_schema=JUDGE_SCHEMA,
            images=images,
        )
    return {
        **parse_judge_payload(response["text"], len(extracts)),
        "frames": len(extracts),
        # C-6.4: the billed look's cost rides along so callers (product
        # render paths via stations/vision_qc.py) can meter it on the job.
        "cost_micros": int(response.get("cost_micros") or 0),
    }


def vision_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Vision gate fields for render-quality summarizers (stage1a, extend,
    corrections): every RENDER must clear the vision bar. A record missing
    the judgment (failed look) is worst-case (C-3.5)."""
    n = len(records)
    scores = [
        float(row["vision_judge"])
        for row in records
        if isinstance(row.get("vision_judge"), (int, float))
    ]
    mean = sum(scores) / len(scores) if scores else 0.0
    fail_reasons: list[str] = []
    if n == 0 or len(scores) != n:
        fail_reasons.append("missing_vision_judge")
    if mean < VISION_BAR:
        fail_reasons.append("vision_judge_gate")
    return {
        "mean_vision_judge": round(mean, 5),
        "n_judged": len(scores),
        "vision_fail_reason": ",".join(fail_reasons),
    }
