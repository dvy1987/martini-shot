"""Pickups QC retry state machine (D-6, ADR-0005 ladder). Scores must be real
measurements.

Ladder (owner ruling 2026-09-09): attempts 1–2 stabilize the render
(stronger anchors); from attempt 3 the house regenerates the WHOLE clip
from the accepted references; needs_human only after MAX_RETRIES total
attempts."""

from __future__ import annotations

MAX_RETRIES = 5
STABILIZE_RETRIES = 2


def next_action(
    score: float, threshold: float, retries_used: int, *, max_retries: int = MAX_RETRIES
) -> str:
    if score < threshold:
        return "pass"
    if retries_used < STABILIZE_RETRIES:
        return "retry_strengthen"
    if retries_used < max_retries:
        return "regenerate_clip"
    return "needs_human"


def apply_retries(
    score: float, threshold: float, *, max_retries: int = MAX_RETRIES
) -> dict[str, object]:
    """Simulate the retry loop using one real score (no fabricated measurements)."""
    steps: list[str] = []
    retries = 0
    while True:
        action = next_action(score, threshold, retries, max_retries=max_retries)
        steps.append(action)
        if action != "retry_strengthen" and action != "regenerate_clip":
            return {"final": action, "retries_used": retries, "steps": steps}
        retries += 1
