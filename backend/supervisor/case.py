"""Case model + deterministic specialist routing (H-1a, Amendment A9).

A Case is the immutable, versioned brief every specialist receives: the
trigger plus a pre-fetched shared evidence baseline. Specialists return
typed Findings (claims + evidence + proposed actions); they hold zero
act-class tools — only the H-0 approval executor executes anything.

Routing is a plain deterministic table (plan §2.4): no LLM decides who gets
consulted; only the CONTENT of a finding is a judgment call. This is what
makes delegation TDD-testable instead of only EDD-judged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso

# Specialist names (H-1a registry; Localization deferred to E-2 per plan §0.1)
RELIABILITY = "reliability_investigator"
DELIVERY_QC = "delivery_qc"
SPEND_GUARDIAN = "spend_guardian"
LOCALIZATION = "localization"

SPECIALIST_ROUTES: dict[str, list[str]] = {
    "job_failed": [RELIABILITY],
    "stuck_lease": [RELIABILITY],
    "crash_recovered": [RELIABILITY],
    "quarantine": [RELIABILITY],
    "qc_breach": [DELIVERY_QC, RELIABILITY],
    "spend_breach": [SPEND_GUARDIAN, RELIABILITY],
    "runaway": [SPEND_GUARDIAN, RELIABILITY],
    "daily_budget": [SPEND_GUARDIAN, RELIABILITY],
    "dub_breach": [LOCALIZATION, RELIABILITY],
    "pickups_needs_human": [DELIVERY_QC, RELIABILITY],
}

# Stations whose own QC verdicts are worth a Delivery QC look on failure.
_QC_STATIONS = {"loudness", "delivery", "pickups", "captions"}


@dataclass(frozen=True)
class Claim:
    text: str
    evidence_ref: str  # trace id | promql query+result | log line | firestore doc path
    confidence: Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ProposedAction:
    """One candidate for the H-0b leverage ranking. command_name must match
    an H-0 default_registry command — never invented ad hoc.

    supporting_evidence_refs: the evidence_refs of the claims this action
    DEPENDS on (ACT-gate review fix 1). Empty means "depends on the whole
    finding" — conservatively, any vetoed claim in the finding drops the
    action, so an unsupported action can never survive a veto."""

    command_name: str
    args: dict[str, Any]
    cost_estimate_micros: int
    reversible: bool  # False => excluded from ranking, never just down-weighted
    supporting_evidence_refs: tuple[str, ...] = ()

    def required_evidence_refs(self, finding: Finding) -> tuple[str, ...]:
        """The claim refs this action stands on: its declared refs, or every
        claim in the finding when none were declared (conservative default)."""
        if self.supporting_evidence_refs:
            return self.supporting_evidence_refs
        return tuple(claim.evidence_ref for claim in finding.claims)


@dataclass(frozen=True)
class Case:
    case_id: str
    version: int
    created_at: str  # UTC ISO-8601 (C-6.4)
    trigger: dict[str, Any]  # {kind, job_id?, project_id, station?, signal}
    evidence: dict[str, Any] = field(default_factory=dict)  # shared baseline


@dataclass(frozen=True)
class Finding:
    specialist: str
    case_id: str
    claims: list[Claim]
    proposed_actions: list[ProposedAction]


@dataclass(frozen=True)
class Verdict:
    case_id: str
    rejected: list[tuple[str, str]]  # (claim evidence_ref, rejection reason)
    approved_specialists: list[str]
    overall_confidence: Literal["low", "medium", "high"]


def build_case(
    trigger: dict[str, Any],
    store: FirestoreStore,
    *,
    jobs_collection: str = "pc-jobs",
) -> Case:
    """Deterministic: reads the trigger's job doc as the shared evidence
    baseline. A missing job doc is recorded as absence, never invented.
    The case always names its subject explicitly (`evidence["job_id"]`) so
    specialists can echo correct target args regardless of the underlying
    doc's id key (ACT-gate review: action args must identify the target)."""
    evidence: dict[str, Any] = {}
    job_id = str(trigger.get("job_id") or "")
    if job_id:
        evidence["job_id"] = job_id
        job_doc = store.get_doc(jobs_collection, job_id)
        evidence["job"] = job_doc
        station = str((job_doc or {}).get("station") or "")
        if station:
            evidence["station"] = station
    return Case(
        case_id=f"case-{uuid.uuid4().hex[:12]}",
        version=1,
        created_at=utc_now_iso(),
        trigger=dict(trigger),
        evidence=evidence,
    )


def route_specialists(trigger: dict[str, Any]) -> list[str]:
    """Who gets consulted — a table lookup, not a model call."""
    kind = str(trigger.get("kind") or "")
    if kind not in SPECIALIST_ROUTES:
        raise ValueError(
            f"unknown trigger kind {kind!r} (table: {sorted(SPECIALIST_ROUTES)})"
        )
    specialists = list(SPECIALIST_ROUTES[kind])
    station = str(trigger.get("station") or "")
    if (
        kind == "job_failed"
        and station in _QC_STATIONS
        and DELIVERY_QC not in specialists
    ):
        specialists.append(DELIVERY_QC)
    return specialists
