"""H-1c — Delivery QC agent: judges delivery-pack QC reports (D-2/D-4).

Reads the REAL D-4 evaluator output (result.delivery: destination, verdict,
violations with rule IDs) plus the REAL D-2 loudness measurement (result.lufs)
from the job doc, and asks the model to CLASSIFY the case:

  - genuine_breach   the evaluator failed the pack (rule table is
                     authoritative — the agent never overrides a verdict)
  - borderline_pass  evaluator passed the pack, but a measurement sits close
                     enough to a threshold to flag (not alarm)
  - pass             clean, with margin

Same guarantees as H-1b: one instrumented Gemini call site, read-only tools
only, deterministic schema validation that fails loud (C-1.1). Judgment
quality is EDD: backend/evals/datasets/delivery_qc_judgment.jsonl (seeded
packs run through the REAL evaluate_delivery chain), threshold
mean_classification_accuracy >= 0.8 (C-3.4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.supervisor.agents.finding_schema import (
    REGISTRY_COMMANDS,
    validate_actions,
    validate_claims,
)
from backend.supervisor.case import DELIVERY_QC, Case, Claim, Finding, ProposedAction
from backend.supervisor.otel_ai import run_agent_call

QC_CLASSIFICATIONS: tuple[str, ...] = ("genuine_breach", "borderline_pass", "pass")

# D-2's real tolerance (backend/stations/loudness/verdict.py) — named in the
# prompt so "borderline" is judgeable against the same table the evaluator used.
LOUDNESS_TOLERANCE_LU = 1.0


@dataclass(frozen=True)
class QCFinding:
    finding: Finding
    classification: str


QC_FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": list(QC_CLASSIFICATIONS),
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence_ref": {
                        "type": "string",
                        "description": (
                            "job doc path | rule id | report field the claim rests on"
                        ),
                    },
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["text", "evidence_ref", "confidence"],
            },
        },
        "proposed_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "command_name": {"type": "string"},
                    "args": {"type": "object"},
                    "cost_estimate_micros": {"type": "integer"},
                    "reversible": {"type": "boolean"},
                },
                "required": [
                    "command_name",
                    "args",
                    "cost_estimate_micros",
                    "reversible",
                ],
            },
        },
    },
    "required": ["case_id", "classification", "claims", "proposed_actions"],
}


def read_qc_report(
    store: FirestoreStore, job_id: str, *, jobs_collection: str = "pc-jobs"
) -> dict[str, Any]:
    """Read the REAL D-2/D-4 output off the job doc. Absence is recorded
    explicitly (found=False), never invented."""
    doc = store.get_doc(jobs_collection, job_id) or {}
    result = doc.get("result") or {}
    delivery = result.get("delivery")
    lufs = result.get("lufs")
    return {
        "job_id": job_id,
        "found": doc.get("id") is not None and delivery is not None,
        "delivery_report": delivery,
        "lufs": lufs,
        "note": None
        if delivery is not None
        else f"job {job_id}: no delivery QC report",
    }


def read_qc_report_from_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Same shape, from an in-memory job doc (eval runner / tests)."""
    result = doc.get("result") or {}
    delivery = result.get("delivery")
    return {
        "job_id": doc.get("id"),
        "found": delivery is not None,
        "delivery_report": delivery,
        "lufs": result.get("lufs"),
        "note": None if delivery is not None else "no delivery QC report",
    }


def validate_qc_finding_payload(payload: Any, *, case_id: str) -> QCFinding:
    """Deterministic gate: shared finding rules + the classification enum."""
    if not isinstance(payload, dict):
        raise ValueError("finding payload must be a JSON object")
    if payload.get("case_id") != case_id:
        raise ValueError(
            f"case_id mismatch: payload {payload.get('case_id')!r} != case {case_id!r}"
        )
    classification = payload.get("classification")
    if classification not in QC_CLASSIFICATIONS:
        raise ValueError(
            f"classification must be one of {list(QC_CLASSIFICATIONS)}, "
            f"got {classification!r}"
        )
    finding = Finding(
        specialist=DELIVERY_QC,
        case_id=case_id,
        claims=validate_claims(payload),
        proposed_actions=validate_actions(payload),
    )
    return QCFinding(finding=finding, classification=str(classification))


def build_qc_prompt(case: Case, qc_report: dict[str, Any]) -> str:
    """Deterministic brief: the REAL D-2/D-4 report + classification rules.
    The evaluator's verdict table is authoritative — the agent interprets,
    never overrides."""
    report = json.dumps(qc_report, indent=2, default=str)
    return f"""You are the Delivery QC agent on the Martini Shot post-production pipeline.

CASE {case.case_id} (version {case.version})
TRIGGER:
{json.dumps(case.trigger, indent=2, default=str)}

REAL QC REPORT (D-2 loudness + D-4 delivery pack evaluator output):
{report}

Context: the loudness tolerance is {LOUDNESS_TOLERANCE_LU} LU around the
profile target; caption and container rules are structural (rule IDs DEL-001..DEL-007).

CLASSIFY this case as exactly one of:
- "genuine_breach": the evaluator FAILED the pack (any violation is a breach,
  marginal or not — the rule table is authoritative) — or required structure
  is missing.
- "borderline_pass": the evaluator PASSED the pack but a measurement sits
  close to a threshold (e.g. loudness delta >= half the tolerance) — worth a
  note, not an alarm.
- "pass": clean, with margin.

You NEVER override the evaluator's verdict; you interpret it. Every claim
must cite a concrete evidence_ref (job doc path, rule ID, or report field).
Proposed actions must use ONLY these H-0 registry commands:
{", ".join(REGISTRY_COMMANDS)} — they are proposals, you never execute.
Mark reversibility honestly. If the report is missing or inconclusive,
say so with low confidence.

Respond with JSON matching the required schema: case_id (echo), classification,
claims, proposed_actions."""


def investigate(
    case: Case,
    settings: Settings,
    *,
    store: FirestoreStore | None = None,
    jobs_collection: str = "pc-jobs",
    connector: Any = None,
    qc_report: dict[str, Any] | None = None,
) -> QCFinding:
    """One real Gemini classification over the REAL QC report. The report is
    read from the job doc via `store` unless the caller supplies it directly
    (eval runner / in-memory cases). Malformed responses raise (fail loud)."""
    if qc_report is None:
        job_id = str(case.trigger.get("job_id") or "")
        if store is None:
            raise ValueError("either store or qc_report is required")
        qc_report = read_qc_report(store, job_id, jobs_collection=jobs_collection)
    tools: tuple[Callable[..., Any], ...] = ()
    if connector is not None:
        from backend.supervisor.agents.reliability_investigator import (
            read_only_grafana_tools,
        )

        tools = read_only_grafana_tools(connector)
    raw = run_agent_call(
        settings,
        build_qc_prompt(case, qc_report),
        span_name="specialist.delivery_qc",
        persona=DELIVERY_QC,
        tools=tools,
        response_schema=QC_FINDING_SCHEMA,
    )
    payload = json.loads(raw["text"])
    return validate_qc_finding_payload(payload, case_id=case.case_id)


__all__ = [
    "QC_CLASSIFICATIONS",
    "QC_FINDING_SCHEMA",
    "QCFinding",
    "ProposedAction",
    "Claim",
    "build_qc_prompt",
    "investigate",
    "read_qc_report",
    "read_qc_report_from_doc",
    "validate_qc_finding_payload",
]
