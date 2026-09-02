"""Pickups cost estimator (integer micro-units, C-6.4 / AC-S2.2)."""

from __future__ import annotations

TOLERANCE = 0.20


def estimate_micros(frame_count: int, micros_per_frame: int) -> int:
    if frame_count < 0 or micros_per_frame < 0:
        return 0
    return int(frame_count) * int(micros_per_frame)


def within_tolerance(estimate: int, actual: int, pct: float = TOLERANCE) -> bool:
    if actual == 0:
        return estimate == 0
    return abs(estimate - actual) / actual <= pct
