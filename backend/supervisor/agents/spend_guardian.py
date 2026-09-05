"""H-1d — Spend Guardian: challenges spend-bearing plans against REAL state.

Reads the Spend Control station's own artifacts — policies.yaml caps, project
budgets, and the station's Firestore job rows aggregated through the SAME
detect helpers the station uses — and judges a proposed action:

  - reasonable     fits caps, retries remaining, budget headroom
  - underpriced    the proposal's cost estimate ignores the real history
                   (attempts exhausted, runaway requeues, near-cap spend)
  - over_budget    project budget already breached — no further spend proposals

Same guarantees as H-1b/H-1c: one instrumented call site, read-only tools
only, deterministic validation that fails loud (C-1.1). Judgment quality is
EDD: backend/evals/datasets/spend_guardian_judgment.jsonl (REAL policies.yaml
+ detect helpers), threshold mean_assessment_accuracy >= 0.8 (C-3.4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from backend.core.config import Settings
from backend.core.firestore import FirestoreStore
from backend.stations.spend.detect import project_spend_micros
from backend.stations.spend.policy import load_policies, project_budgets, station_policy
from backend.supervisor.agents.finding_schema import (
    REGISTRY_COMMANDS,
    validate_actions,
    validate_claims,
)
from backend.supervisor.case import SPEND_GUARDIAN, Case, Finding
from backend.supervisor.otel_ai import run_agent_call

SPEND_ASSESSMENTS: tuple[str, ...] = ("reasonable", "underpriced", "over_budget")


@dataclass(frozen=True)
class SGFinding:
    finding: Finding
    assessment: str


SPEND_FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "string"},
        "assessment": {
            "type": "string",
            "enum": ["reasonable", "underpriced", "over_budget"],
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
                            "policy key | job doc path | spend figure the claim rests on"
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
    "required": ["case_id", "assessment", "claims", "proposed_actions"],
}


def read_spend_state(
    store: FirestoreStore | None,
    *,
    project_id: str,
    station: str,
    jobs_collection: str = "pc-jobs",
    jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """REAL Spend Control state: the station's own policies.yaml caps and
    budgets, plus job rows — read live via store, or supplied directly (eval
    runner / tests). Aggregation uses the station's own detect helpers."""
    policies = load_policies()
    policy = station_policy(policies, station)
    if jobs is None:
        if store is None:
            raise ValueError("either store or jobs is required")
        rows = store.list_where(jobs_collection, "project_id", project_id) or []
    else:
        rows = jobs
    station_rows = [
        row
        for row in rows
        if str(row.get("station") or "") == station
        and str(row.get("id") or row.get("job_id") or "")
    ]
    budgets = project_budgets(policies)
    daily_spent = int(project_spend_micros(rows))
    return {
        "project_id": project_id,
        "station": station,
        "policy": {
            "max_cost_micros_per_job": int(policy.get("max_cost_micros_per_job") or 0),
            "max_retries": int(policy.get("max_retries") or 0),
            "runaway_requeues": int(policy.get("runaway_requeues") or 0),
        },
        "budgets": budgets,
        "daily_spent_micros": daily_spent,
        "daily_budget_micros": int(budgets.get("daily_budget_micros") or 0),
        "daily_remaining_micros": max(
            0, int(budgets.get("daily_budget_micros") or 0) - daily_spent
        ),
        "jobs": [
            {
                "job_id": str(row.get("id") or row.get("job_id") or ""),
                "status": row.get("status"),
                "attempts": int(row.get("attempts") or 0),
                "cost_micros": int(row.get("cost_micros") or 0),
            }
            for row in station_rows
        ],
        "station_spent_micros": int(project_spend_micros(station_rows)),
    }


def validate_assessment_payload(payload: Any, *, case: Case) -> "SGAssessment":
    """Deterministic gate: shared finding rules + the assessment enum. The
    case's subject job/station ride along for structural target binding."""
    if not isinstance(payload, dict):
        raise ValueError("finding payload must be a JSON object")
    if payload.get("case_id") != case.case_id:
        raise ValueError(
            f"case_id mismatch: payload {payload.get('case_id')!r} != case {case.case_id!r}"
        )
    assessment = payload.get("assessment")
    if assessment not in ("reasonable", "underpriced", "over_budget"):
        raise ValueError(
            f"assessment must be reasonable|underpriced|over_budget, got {assessment!r}"
        )
    claims = validate_claims(payload)
    finding = Finding(
        specialist=SPEND_GUARDIAN,
        case_id=case.case_id,
        claims=claims,
        proposed_actions=validate_actions(
            payload,
            claims,
            subject_job_id=str(case.evidence.get("job_id") or "") or None,
            subject_station=str(
                case.trigger.get("station") or case.evidence.get("station") or ""
            )
            or None,
        ),
    )
    return SGAssessment(finding=finding, assessment=str(assessment))


@dataclass(frozen=True)
class SGAssessment:
    finding: Finding
    assessment: str


def build_spend_prompt(
    case: Case, spend_state: dict[str, Any], proposal: dict[str, Any]
) -> str:
    """Deterministic brief: the REAL policy caps, the REAL spend aggregation,
    and the plan under review."""
    state = json.dumps(spend_state, indent=2, default=str)
    plan = json.dumps(proposal, indent=2, default=str)
    return f"""You are the Spend Guardian on the Martini Shot post-production pipeline.

CASE {case.case_id} (version {case.version})
TRIGGER:
{json.dumps(case.trigger, indent=2, default=str)}

PROPOSED PLAN UNDER REVIEW (another agent's or a policy's proposal):
{plan}

REAL SPEND STATE (policies.yaml caps + Firestore job rows aggregated by the
station's own detect helpers):
{state}

Judge the plan as exactly one of:
- "over_budget": daily spend already exceeds the daily budget — no spend
  proposal is reasonable until the budget recovers.
- "underpriced": the plan's cost estimate is not credible against the real
  history (attempts exhausted vs max_retries, runaway_requeues reached with
  unchanged errors, remaining per-job cap smaller than the estimate, or the
  same plan already burned budget without changing the error).
- "reasonable": fits the caps, retries remain, and daily headroom covers it.

Ground rules:
1. Every claim must cite a concrete evidence_ref (policy key, job doc path,
   or spend figure). No evidence, no claim.
2. You challenge underpriced plans — an estimate that ignores retry history
   or the runaway pattern is "underpriced" even if the raw number is small.
3. When the plan is not reasonable, propose an alternative using ONLY these
   H-0 registry commands: {", ".join(REGISTRY_COMMANDS)} (e.g. pause_intake
   on the affected station instead of another retry). You never execute.
4. Mark reversibility honestly.

Respond with JSON matching the required schema: case_id (echo), assessment,
claims, proposed_actions."""


def investigate(
    case: Case,
    settings: Settings,
    *,
    spend_state: dict[str, Any] | None = None,
    proposal: dict[str, Any] | None = None,
    store: FirestoreStore | None = None,
    jobs_collection: str = "pc-jobs",
    connector: Any = None,
) -> SGAssessment:
    """One real Gemini assessment. Either supply `spend_state` directly or
    `store` + trigger context to read it live. Fails loud on malformed
    responses (C-1.1)."""
    if spend_state is None:
        station = str(case.trigger.get("station") or "")
        project_id = str(case.trigger.get("project_id") or "")
        spend_state = read_spend_state(
            store,
            project_id=project_id,
            station=station,
            jobs_collection=jobs_collection,
        )
    if proposal is None:
        raise ValueError("proposal is required (the plan under judgment)")
    tools: tuple[Callable[..., Any], ...] = ()
    if connector is not None:
        from backend.supervisor.agents.reliability_investigator import (
            read_only_grafana_tools,
        )

        tools = read_only_grafana_tools(connector)
    raw = run_agent_call(
        settings,
        build_spend_prompt(case, spend_state, proposal),
        span_name="specialist.spend_guardian",
        persona=SPEND_GUARDIAN,
        tools=tools,
        response_schema=SPEND_FINDING_SCHEMA,
    )
    payload = json.loads(raw["text"])
    return validate_assessment_payload(payload, case=case)
