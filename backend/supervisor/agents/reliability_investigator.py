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

from backend.core.config import Settings
from backend.supervisor.agents.finding_schema import (
    REGISTRY_COMMANDS,
)
from backend.supervisor.agents.finding_schema import (
    validate_finding_payload as _validate_finding_payload,
)
from backend.supervisor.case import RELIABILITY, Case, Finding
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

# H-0 registry command vocabulary now lives in finding_schema.py (shared by
# all specialists); imported as REGISTRY_COMMANDS.

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


def validate_finding_payload(payload: Any, *, case: Case) -> Finding:
    """Deterministic gate between the model and the pipeline (shared rules in
    finding_schema.py). Anything not matching the contract raises ValueError
    — fail loud (C-1.1). The case's subject job_id rides along so the gate
    can bind structurally-determined targets."""
    return _validate_finding_payload(
        payload,
        case_id=case.case_id,
        specialist=RELIABILITY,
        subject_job_id=str(case.evidence.get("job_id") or "") or None,
        subject_station=str(
            case.trigger.get("station") or case.evidence.get("station") or ""
        )
        or None,
    )


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
   args are MANDATORY and must be copied from the SHARED EVIDENCE BASELINE:
   job-scoped commands (retry_job) take args {{"job_id": "<the job_id field
   from the evidence>"}}; shot-scoped commands take {{"shot_id": ...}};
   intake commands take {{"station": "<station name>"}}. NEVER return empty
   args ({{}}) — an action without its target id is rejected outright and
   the finding fails validation. For a job failure you are investigating,
   the job_id is in the evidence baseline; echo it verbatim.
   They are proposals for human/budgeted approval — you never execute.
4. Mark each proposed action reversible: true when acting then undoing
   leaves no permanent change — a retry simply re-runs the same work, a
   pause resumes, an alternate attaches without overwriting anything.
   add_to_continuity and remove_from_continuity are reversible pointer
   moves; the supervisor may dispatch them inside the night envelope.
   You MUST copy shot_id and alternate_id from the evidence; if those
   ids are missing, leave cut changes to the continuity specialist.
   Irreversible means destructive or one-way (deleted media, overwritten
   locked cuts) — those are not in the registry at all.
5. When the evidence DOES support a diagnosis, propose the matching action
   and estimate its cost honestly from the job's own cost history — never
   0 for an action that spends money: your cost estimate feeds a leverage
   ranking and a 0 estimate makes the ranking meaningless.
6. ABSTAIN (empty proposed_actions, said with low confidence) only when NO
   action is justified. Do NOT confuse "upstream root cause is unclear"
   with "no action is justified": when the evidence clearly shows a gate
   breach or stuck state and a registry command is the sanctioned
   remediation for exactly that condition (e.g. a loudness gate breach →
   retry_job re-measures; a runaway retry loop → pause_intake), propose
   THAT action, citing the evidence that shows the breach, and say plainly
   that the upstream root cause remains open. Proposing a sanctioned,
   reversible remediation while the root cause is open is not speculation;
   inventing a fix for a case with NO observable signal is.

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
    return validate_finding_payload(payload, case=case)
