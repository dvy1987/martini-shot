"""Production Post Supervisor synthesis for verified specialist findings."""

from __future__ import annotations

import json
from typing import Any

from backend.core.config import Settings
from backend.supervisor.case import Case, Finding, Verdict
from backend.supervisor.deliberation import rank_actions
from backend.supervisor.otel_ai import run_agent_call

PERSONA = "post_supervisor"
SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "string"},
        "summary": {"type": "string"},
        "selected_action_indexes": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0},
        },
        "rejected_action_indexes": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0},
        },
        "dissent": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "case_id",
        "summary",
        "selected_action_indexes",
        "rejected_action_indexes",
        "dissent",
    ],
}


def validate_synthesis_payload(
    payload: Any, *, case_id: str, candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    """Resolve model choices to a complete partition of safe candidates.

    The model can select or reject existing verified candidates only; it
    cannot invent command names, arguments, costs, or evidence references.
    """
    if not isinstance(payload, dict):
        raise ValueError("synthesis payload must be an object")
    if payload.get("case_id") != case_id:
        raise ValueError("synthesis case_id must match the case")
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        raise ValueError("synthesis summary is required")
    dissent = payload.get("dissent")
    if not isinstance(dissent, list) or any(
        not isinstance(item, str) or not item.strip() for item in dissent
    ):
        raise ValueError("synthesis dissent must be a list of non-empty strings")

    selected = payload.get("selected_action_indexes")
    rejected = payload.get("rejected_action_indexes")
    if not isinstance(selected, list) or not isinstance(rejected, list):
        raise ValueError("synthesis action indexes must be lists")
    all_indexes = selected + rejected
    if any(
        not isinstance(index, int) or isinstance(index, bool) for index in all_indexes
    ):
        raise ValueError("synthesis action indexes must be integers")
    if len(set(all_indexes)) != len(all_indexes):
        raise ValueError("synthesis action indexes must not repeat")
    if set(all_indexes) != set(range(len(candidates))):
        raise ValueError("synthesis must select or reject every candidate exactly once")
    return {
        "ranked_actions": [candidates[index] for index in selected],
        "rejected_action_indexes": rejected,
        "summary": summary,
        "dissent": dissent,
    }


def build_synthesis_prompt(
    case: Case,
    findings: list[Finding],
    verdict: Verdict,
    candidates: list[dict[str, Any]],
) -> str:
    """Bounded prompt: evidence determines selection; code owns execution."""
    return f"""You are the Post Supervisor for Martini Shot.
Synthesize verified specialist findings into an accountable recommendation.
You may select or reject ONLY the indexed candidates below. You cannot invent
an action, change its target, alter its cost, or use uncited evidence. Prefer
the smallest reversible action that improves the production. Reject anything
whose whole-video value is not supported by the case evidence.

CASE:
{json.dumps({"case_id": case.case_id, "trigger": case.trigger, "evidence": case.evidence}, default=str)}

VERIFIED FINDINGS:
{json.dumps([{"specialist": finding.specialist, "claims": [claim.__dict__ for claim in finding.claims]} for finding in findings], default=str)}

VERDICT:
{json.dumps({"rejected": verdict.rejected, "confidence": verdict.overall_confidence}, default=str)}

CANDIDATES:
{json.dumps(list(enumerate(candidates)), default=str)}

Respond only with JSON matching the schema. Partition every candidate exactly
once between selected_action_indexes and rejected_action_indexes. Explain
material disagreement in dissent."""


def synthesize(
    case: Case, findings: list[Finding], verdict: Verdict, settings: Settings
) -> dict[str, Any]:
    """One metered Gemini synthesis call, constrained to verified candidates."""
    candidates = rank_actions(case, findings)
    response = run_agent_call(
        settings,
        build_synthesis_prompt(case, findings, verdict, candidates),
        span_name="supervisor.post_synthesis",
        persona=PERSONA,
        response_schema=SYNTHESIS_SCHEMA,
    )
    return validate_synthesis_payload(
        json.loads(response["text"]), case_id=case.case_id, candidates=candidates
    )
