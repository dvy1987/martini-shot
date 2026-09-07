"""D-10 correction prompt construction and queued Omni edit execution."""

from __future__ import annotations

from typing import Iterable


def build_correction_prompt(
    *,
    intent: str,
    protected_subjects: Iterable[str],
    continuity_constraints: Iterable[str],
) -> str:
    """Build the bounded instruction supplied to the real Omni edit call."""
    clean_intent = intent.strip()
    if not clean_intent:
        raise ValueError("correction requires explicit intent")
    protected = ", ".join(item.strip() for item in protected_subjects if item.strip())
    constraints = ", ".join(
        item.strip() for item in continuity_constraints if item.strip()
    )
    return (
        "Edit this video only to accomplish the following bounded correction:\n"
        f"{clean_intent}\n\n"
        f"Protected subjects and regions: {protected or 'none specified'}.\n"
        f"Continuity constraints: {constraints or 'preserve the source shot'}.\n"
        "Do not alter protected subjects, identity, framing, or geometry. "
        "Keep everything else the same."
    )
