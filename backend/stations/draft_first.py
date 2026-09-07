"""D-11 Draft-first orchestration: an operation-independent state machine
shared by every Stage 1a generative op (Extend, Corrections, Relight,
Coverage, Camera Language).

State machine (owner ruling A5, draft-first): every op's FIRST render is a
draft (cheap, 360p-tier). A master render may be requested ONLY once a
linked draft alternate has cleared its QC bars. `render_master` is the sole
H-0 command allowed to promote a draft's op into a master; this module is
the deterministic gate it calls before dispatch — nothing here executes,
it only decides whether a master is ALLOWED (C-6.3/C-6.4/C-7).

    draft_requested -> draft_rendered -> qc_pending
        -> master_eligible | revise | escalate
    master_eligible -> master_requested -> master_rendered -> final_qc

`revise` means: re-render another DRAFT of the same op (one bounded
re-attempt); `escalate` means the state machine refuses to proceed
automatically and the target needs_human.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STATES: tuple[str, ...] = (
    "draft_requested",
    "draft_rendered",
    "qc_pending",
    "master_eligible",
    "revise",
    "escalate",
    "master_requested",
    "master_rendered",
    "final_qc_passed",
    "final_qc_failed",
)

# Bounded retry: at most one automatic re-render per shot+op before a
# breach must escalate to a human (never an infinite draft loop, C-7).
MAX_REVISIONS = 1

FLICKER_BAR = 0.02
VISION_BAR = 4.0


class MasterNotEligibleError(ValueError):
    """Raised by `assert_master_eligible` — never silently downgraded; the
    caller (H-0's render_master command) must refuse the dispatch."""


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def draft_cleared_bars(alternate: dict[str, Any]) -> bool:
    """The QC bars a draft must clear before a master may be requested —
    identical thresholds to the deterministic pickups gate (thresholds.yaml
    pickups_flicker / pickups_vision_judge), applied per-op."""
    scores = alternate.get("eval_scores") or {}
    flicker = _as_float(scores.get("flicker"))
    vision = _as_float(scores.get("vision_judge"))
    if flicker is None:
        return False
    flicker_ok = flicker < FLICKER_BAR
    vision_ok = vision is None or vision >= VISION_BAR
    return flicker_ok and vision_ok


def find_eligible_draft(
    alternates: list[dict[str, Any]], *, op: str
) -> dict[str, Any] | None:
    """The most recent QC-passing draft alternate for this op, or None."""
    candidates = [
        alt
        for alt in alternates
        if alt.get("op") == op
        and alt.get("status") in ("draft", "continuity")
        and draft_cleared_bars(alt)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda alt: str(alt.get("created_at") or ""))
    return candidates[-1]


def assert_master_eligible(
    alternates: list[dict[str, Any]], *, op: str
) -> dict[str, Any]:
    """The deterministic gate `render_master` calls before dispatch: raises
    MasterNotEligibleError unless a QC-passing draft alternate for `op`
    exists. Returns that draft alternate (its id becomes the master's
    lineage pointer) when eligible."""
    draft = find_eligible_draft(alternates, op=op)
    if draft is None:
        raise MasterNotEligibleError(
            f"no QC-passing draft alternate for op={op!r}; a master render "
            "requires a linked eligible draft (draft-first, owner ruling A5)"
        )
    return draft


@dataclass(frozen=True)
class ReadinessDecision:
    state: str
    reason: str


def evaluate_readiness(
    *, op: str, alternates: list[dict[str, Any]], revision_count: int
) -> ReadinessDecision:
    """Deterministic readiness call: qc_pending -> master_eligible / revise
    / escalate. This is the fallback/advisory path; the Draft-First
    Orchestrator Agent may take this under advisement (StationDecision
    contract) but the hard gate above still governs actual master
    dispatch regardless of what any agent decides."""
    op_alternates = [alt for alt in alternates if alt.get("op") == op]
    if not op_alternates:
        return ReadinessDecision("draft_requested", "no draft exists yet")
    latest = sorted(op_alternates, key=lambda alt: str(alt.get("created_at") or ""))[-1]
    if draft_cleared_bars(latest):
        return ReadinessDecision("master_eligible", "latest draft cleared both QC bars")
    if revision_count < MAX_REVISIONS:
        return ReadinessDecision(
            "revise", "latest draft breached QC; one bounded re-render remains"
        )
    return ReadinessDecision(
        "escalate",
        f"latest draft breached QC after {revision_count} revision(s); "
        "needs a human decision",
    )


def cost_delta_micros(draft_cost: int, master_cost: int) -> int:
    """Actual/estimated cost delta surfaced to the FE cost-comparison badge
    (C-6.4: integer micros)."""
    return int(master_cost) - int(draft_cost)
