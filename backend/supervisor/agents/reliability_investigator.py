"""H-1b — Reliability Investigator: root-causes failed/stuck jobs.

Real Gemini call via `run_agent_call` (one instrumented site, cost/token/
latency metered, `gen_ai.agent.name=reliability_investigator` on the span),
with Grafana MCP tools scoped to READ-ONLY plan tools (C-2.1: specialists
hold zero act-class tools — every intervention lands as an H-0 approval).
The model response is a JSON document validated against FINDING_SCHEMA by
deterministic code; a malformed or rule-violating response raises (C-1.1 —
never degrade to an invented finding).

Judgment quality is measured, not assumed: EDD suite
`reliability_root_cause` (backend/evals/datasets/reliability_root_cause.jsonl,
threshold mean_root_cause_accuracy >= 0.75, C-3.4).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from backend.approvals.commands import default_registry
from backend.core.config import Settings
from backend.supervisor.case import RELIABILITY, Case, Claim, Finding, ProposedAction
from backend.supervisor.otel_ai import run_agent_call

# Read-only Grafana plan tools (mirror _TOOL_PREFERENCES in mcp.py; write
# tools add_annotation / create_incident are deliberately absent — C-2.1).
READ_ONLY_GRAFANA_TOOLS: tuple[str, ...] = (
    "search_dashboards",
    "query_promql",
    "query_loki",
    "search_traces",
    "get_annotations",
    "list_incidents",
    "get_incident",
)

# H-0 default_registry command vocabulary — proposed actions must name one
# of these; validation enforces it against the live registry.
REGISTRY_COMMANDS: tuple[str, ...] = (
    "pause_intake",
    "resume_intake",
    "retry_job",
    "lock_shot",
    "unlock_shot",
    "add_to_continuity",
    "remove_from_continuity",
)

FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence_ref": {
                        "type": "string",
                        "description": (
                            "trace id | promql query+result | log line | "
                            "firestore doc path the claim rests on"
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
    "required": ["case_id", "claims", "proposed_actions"],
}

_CONFIDENCES = {"low", "medium", "high"}


def read_only_grafana_tools(connector: Any) -> tuple[Callable[..., Any], ...]:
    """Bind connector methods for the read-only allowlist only. Whatever the
    MCP server exposes, this can never hand the model a write tool."""
    available = set(getattr(connector, "available_tools", ()) or ())
    bound: list[Callable[..., Any]] = []
    for name in READ_ONLY_GRAFANA_TOOLS:
        if available and name not in available:
            continue
        fn = getattr(connector, name, None)
        if callable(fn):
            bound.append(fn)
    return tuple(bound)


def validate_finding_payload(payload: Any, *, case_id: str) -> Finding:
    """Deterministic gate between the model and the pipeline. Anything not
    matching the contract raises ValueError — fail loud (C-1.1)."""
    if not isinstance(payload, dict):
        raise ValueError("finding payload must be a JSON object")
    if payload.get("case_id") != case_id:
        raise ValueError(
            f"case_id mismatch: payload {payload.get('case_id')!r} != case {case_id!r}"
        )
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("finding must carry at least one claim (evidence or nothing)")
    claims: list[Claim] = []
    for raw in raw_claims:
        if not isinstance(raw, dict):
            raise ValueError("claim must be an object")
        text = str(raw.get("text") or "").strip()
        evidence_ref = str(raw.get("evidence_ref") or "").strip()
        confidence = raw.get("confidence")
        if not text or not evidence_ref:
            raise ValueError("claim needs non-empty text and evidence_ref")
        if confidence not in _CONFIDENCES:
            raise ValueError(
                f"claim confidence must be low|medium|high, got {confidence!r}"
            )
        claims.append(
            Claim(text=text, evidence_ref=evidence_ref, confidence=confidence)
        )

    actions: list[ProposedAction] = []
    raw_actions = payload.get("proposed_actions") or []
    if not isinstance(raw_actions, list):
        raise ValueError("proposed_actions must be a list")
    for raw in raw_actions:
        if not isinstance(raw, dict):
            raise ValueError("proposed action must be an object")
        name = str(raw.get("command_name") or "")
        if default_registry.get(name) is None:
            raise ValueError(
                f"proposed command {name!r} is not in the H-0 registry; "
                f"allowed: {list(REGISTRY_COMMANDS)}"
            )
        reversible = raw.get("reversible")
        if not isinstance(reversible, bool):
            raise ValueError("proposed action needs an explicit boolean 'reversible'")
        cost = raw.get("cost_estimate_micros")
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
            raise ValueError("cost_estimate_micros must be a non-negative integer")
        args = raw.get("args")
        if not isinstance(args, dict):
            raise ValueError("proposed action args must be an object")
        actions.append(
            ProposedAction(
                command_name=name,
                args=args,
                cost_estimate_micros=cost,
                reversible=reversible,
            )
        )
    return Finding(
        specialist=RELIABILITY, case_id=case_id, claims=claims, proposed_actions=actions
    )


def build_investigation_prompt(case: Case) -> str:
    """Deterministic brief: trigger + shared evidence + the ground rules.
    No hidden state — whatever the model sees is in the persisted case."""
    evidence = json.dumps(case.evidence, indent=2, default=str)
    trigger = json.dumps(case.trigger, indent=2, default=str)
    return f"""You are the Reliability Investigator on the Martini Shot post-production pipeline.

CASE {case.case_id} (version {case.version})
TRIGGER:
{trigger}

SHARED EVIDENCE BASELINE (real job/telemetry data):
{evidence}

You may investigate further with the attached read-only Grafana tools
(dashboards, PromQL, Loki logs, traces, annotations, incidents). You have
NO write tools: you cannot pause, retry, or annotate anything yourself.

GROUND RULES:
1. Every claim must cite a concrete evidence_ref (trace id, PromQL query +
   result, log line, or Firestore doc path). No evidence, no claim.
2. Rate confidence honestly: high only when the evidence directly shows it.
3. Proposed actions must use ONLY these H-0 registry commands:
   {", ".join(REGISTRY_COMMANDS)}.
   They are proposals for human/budgeted approval — you never execute.
4. Mark each proposed action reversible: true only if undoing it restores
   the prior state exactly.
5. If the evidence is insufficient for a root cause, say so with low
   confidence instead of guessing.

Respond with JSON matching the required schema: case_id (echo this case's
id), claims, proposed_actions."""


def investigate(
    case: Case,
    settings: Settings,
    *,
    connector: Any = None,
) -> Finding:
    """One real Gemini investigation of the case. `connector` is an optional
    GrafanaMcpConnector; when present its READ-ONLY tools are attached so the
    model can pull live telemetry. Malformed responses raise (fail loud)."""
    tools = read_only_grafana_tools(connector) if connector is not None else ()
    raw = run_agent_call(
        settings,
        build_investigation_prompt(case),
        span_name="specialist.reliability_investigator",
        persona=RELIABILITY,
        tools=tools,
        response_schema=FINDING_SCHEMA,
    )
    payload = json.loads(raw["text"])
    return validate_finding_payload(payload, case_id=case.case_id)
