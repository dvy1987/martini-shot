"""H-1 extension — Localization Investigator: root-causes dub/language QC
breaches (dub_breach trigger: wrong language track, dub loudness out of
tolerance, timing drift vs the picture).

Same contract as the other specialists: one real Gemini call via
`run_agent_call` (instrumented, metered, `gen_ai.agent.name=localization`
on the span), JSON response validated by the shared finding gate — a
malformed or rule-violating response raises (C-1.1, fail loud). Judgment
quality is exercised end-to-end by the ACT-gate eval suite
`deliberation_ranking_quality` (hard gates on unsupported-action survival,
cost positivity, reversibility and abstention — C-3.4).
"""

from __future__ import annotations

import json
from typing import Any

from backend.core.config import Settings
from backend.supervisor.agents.finding_schema import (
    REGISTRY_COMMANDS,
)
from backend.supervisor.agents.finding_schema import (
    validate_finding_payload as _validate_finding_payload,
)
from backend.supervisor.agents.reliability_investigator import (
    FINDING_SCHEMA,
    read_only_grafana_tools,
)
from backend.supervisor.case import LOCALIZATION, Case, Finding
from backend.supervisor.otel_ai import run_agent_call


def validate_finding_payload(payload: Any, *, case: Case) -> Finding:
    """Deterministic gate between the model and the pipeline (shared rules in
    finding_schema.py). Anything not matching the contract raises ValueError."""
    return _validate_finding_payload(
        payload,
        case_id=case.case_id,
        specialist=LOCALIZATION,
        subject_job_id=str(case.evidence.get("job_id") or "") or None,
        subject_station=str(
            case.trigger.get("station") or case.evidence.get("station") or ""
        )
        or None,
    )


def build_investigation_prompt(case: Case) -> str:
    """Deterministic brief: trigger + shared evidence + the ground rules."""
    evidence = json.dumps(case.evidence, indent=2, default=str)
    trigger = json.dumps(case.trigger, indent=2, default=str)
    return f"""You are the Localization Investigator on the Martini Shot
post-production pipeline. You diagnose dubbing / language-track QC breaches:
wrong or missing language track, dub loudness out of tolerance, dub timing
drift against the picture, or a localized master failing its spec check.

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
   There is no registry command for "run QC checks" or anything similar —
   QC already ran and its output IS the evidence baseline. Any command not
   in the list above is rejected outright and the whole finding FAILS
   validation.
   args are MANDATORY and must be copied from the SHARED EVIDENCE BASELINE:
   job-scoped commands (retry_job) take args {{"job_id": "<the job_id field
   from the evidence>"}}; intake commands take {{"station": "<station
   name>"}}. NEVER return empty args ({{}}) — an action without its target
   id is rejected outright and the finding fails validation.
   They are proposals for human/budgeted approval — you never execute.
4. Mark each proposed action reversible: true when acting then undoing
   leaves no permanent change. A dub re-render is reversible (it re-runs
   the same work and attaches an alternate); a pause resumes. Irreversible
   means destructive or one-way — none are in the registry.
5. When the evidence DOES support a diagnosis, propose the matching action
   and estimate its cost honestly from the job's own cost history — never
   0 for an action that spends money: your cost estimate feeds a leverage
   ranking and a 0 estimate makes the ranking meaningless.
6. ABSTAIN (empty proposed_actions, said with low confidence) only when NO
   action is justified. When the evidence clearly shows a dub QC breach and
   a registry command is the sanctioned remediation for exactly that
   condition (e.g. a dub loudness breach → retry_job re-renders and
   re-measures), propose THAT action, citing the evidence that shows the
   breach, and say plainly if the upstream root cause remains open.

Respond with JSON matching the required schema: case_id (echo this case's
id), claims, proposed_actions."""


def investigate(
    case: Case,
    settings: Settings,
    *,
    connector: Any = None,
) -> Finding:
    """One real Gemini investigation of the dub/localization case. `connector`
    is an optional GrafanaMcpConnector; when present its READ-ONLY tools are
    attached. Malformed responses raise (fail loud)."""
    tools = read_only_grafana_tools(connector) if connector is not None else ()  # type: ignore[assignment]
    raw = run_agent_call(
        settings,
        build_investigation_prompt(case),
        span_name="specialist.localization",
        persona=LOCALIZATION,
        tools=tools,
        response_schema=FINDING_SCHEMA,
    )
    payload = json.loads(raw["text"])
    return validate_finding_payload(payload, case=case)
