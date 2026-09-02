"""Pickups QC retry state machine (D-6). Scores must be real measurements."""

from __future__ import annotations

MAX_RETRIES = 2


def next_action(
    score: float, threshold: float, retries_used: int, *, max_retries: int = MAX_RETRIES
) -> str:
    if score < threshold:
        return "pass"
    if retries_used < max_retries:
        return "retry_strengthen"
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
        if action != "retry_strengthen":
            return {"final": action, "retries_used": retries, "steps": steps}
        retries += 1
