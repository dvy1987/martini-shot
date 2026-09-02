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
    for i in range(1, n - 1):
        prev, cur, nxt = frames[i - 1], frames[i], frames[i + 1]
        for a, b, c in zip(prev, cur, nxt, strict=True):
            median = sorted((a, b, c))[1]
            residual_sum += abs(b - median) / 255.0
            residual_n += 1
    score = residual_sum / residual_n if residual_n else 0.0
    return {
        "ok": True,
        "flicker_score": round(score, 5),
        "frames_analyzed": n,
        "definition": "mean |I_t - median3| grayscale [0,1], ffmpeg raw",
    }
