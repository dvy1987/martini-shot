"""Classical flicker score without extra Python deps (ffmpeg raw gray frames)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def flicker_score(
    path: Path | str,
    ffmpeg_bin: str,
    *,
    width: int = 160,
    height: int = 90,
    fps: float = 8.0,
) -> dict[str, Any]:
    """Mean |I_t - median(I_{t-1}, I_t, I_{t+1})| on grayscale [0,1]. Lower is better."""
    result = subprocess.run(
        [
            ffmpeg_bin,
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"fps={fps},scale={width}:{height},format=gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        timeout=120,
        check=False,
    )
    raw = result.stdout
    frame_size = width * height
    if frame_size <= 0 or len(raw) < frame_size * 3:
        return {"ok": False, "error": "not enough frames"}
    n = len(raw) // frame_size
    frames = [raw[i * frame_size : (i + 1) * frame_size] for i in range(n)]
    residual_sum = 0.0
    residual_n = 0
    # A brief, real, single-frame corruption (2026-09-09 demo: a genuine
    # visible glitch confirmed by frame extraction) barely moves a
    # whole-clip MEAN — it reads "clean" against any reasonable threshold.
    # Track the worst single frame too so a real localized defect cannot
    # hide behind an average over dozens of otherwise-clean frames.
    per_frame: list[float] = []
    for i in range(1, n - 1):
        prev, cur, nxt = frames[i - 1], frames[i], frames[i + 1]
        frame_sum = 0.0
        for a, b, c in zip(prev, cur, nxt, strict=True):
            median = sorted((a, b, c))[1]
            frame_sum += abs(b - median) / 255.0
        per_frame.append(frame_sum / frame_size)
        residual_sum += frame_sum
        residual_n += frame_size
    score = residual_sum / residual_n if residual_n else 0.0
    if per_frame:
        spike_index = max(range(len(per_frame)), key=per_frame.__getitem__)
        spike_score = per_frame[spike_index]
        # +1: per_frame[0] is analyzed frame index 1 (frame 0 has no
        # predecessor for the 3-tap median).
        spike_frame_index = spike_index + 1
    else:
        spike_score = 0.0
        spike_frame_index = None
    return {
        "ok": True,
        "flicker_score": round(score, 5),
        "spike_score": round(spike_score, 5),
        "spike_frame_index": spike_frame_index,
        "frames_analyzed": n,
        "definition": "mean |I_t - median3| grayscale [0,1], ffmpeg raw",
    }
