"""Spend Steward station agent (A10-4 retrofit of D-7).

Division of authority (DoD: "Spend Control enforcement path unchanged"):
the deterministic policy triggers — runaway requeues, per-job cost cap,
daily budget breach — remain the ONLY thing that can START a Spend
Control action. The steward receives the trigger as ADVICE and chooses
among the ALLOWED responses:

- throttle_station: pause one station's intake (reversible via approval)
- stop_all_intake: pause every station (reserved for runaway spend,
  >= 2x daily budget)
- require_approval: borderline/ambiguous — a human decides first

Every chosen action executes through the EXISTING enforcement functions,
so the Grafana annotation + incident still happen on every enforcement
(C-4.3). The agent cannot suppress observability and cannot invent
actions.

Deterministic surface (no LLM): suggestion mapping, prompt construction,
and response parsing are unit-tested; the real judgment is gated by the
live EDD eval (scripts/spend_steward_eval.py vs spend_steward_judgment,
bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "spend_steward"
DECISIONS = ("throttle_station", "stop_all_intake", "require_approval")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["throttle_station", "stop_all_intake", "require_approval"],
        },
        "station": {
            "type": "string",
            "enum": [
                "ingest",
                "dub",
                "loudness",
                "delivery",
                "extend",
                "pickups",
                "all",
                "none",
            ],
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "decision", "station", "reason", "confidence"],
}


def suggestion_for_trigger(trigger: dict[str, Any]) -> str:
    """Deterministic default — today's behavior, unchanged: triggers map
    to a station throttle; a budget breach at >= 2x is runaway spend and
    stops all intake; unknown triggers go to a human."""
    kind = str(trigger.get("trigger_type") or "")
    if kind == "runaway_attempts":
        return "throttle_station"
    if kind == "job_over_cap":
        return "throttle_station"
    if kind == "daily_budget":
        spent = _int(trigger.get("spent_micros"))
        budget = _int(trigger.get("daily_budget_micros"))
        if budget > 0 and spent >= 2 * budget:
            return "stop_all_intake"
        return "throttle_station"
    return "require_approval"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _fmt(n: Any) -> str:
    return f"{_int(n):,}"


def build_prompt(trigger: dict[str, Any]) -> str:
    """The prompt carries the deterministic trigger as advice, the
    response vocabulary with its escalation bar, and the C-4.3 fact that
    every enforcement creates an incident — suppression is impossible."""
    return (
        "You are the Spend Steward agent for Martini Shot. A "
        "DETERMINISTIC policy trigger fired — Spend Control is acting; "
        "choose the response.\n\n"
        "Trigger (advice):\n"
        f"- trigger: {trigger.get('trigger_type')}\n"
        f"- station: {trigger.get('station')}\n"
        f"- attempts: {trigger.get('attempts')} (runaway threshold: "
        f"{trigger.get('runaway_requeues')})\n"
        f"- job cost: {_fmt(trigger.get('job_cost_micros'))} micros "
        f"(cap: {_fmt(trigger.get('max_cost_micros_per_job'))})\n"
        f"- project spent today: {_fmt(trigger.get('spent_micros'))} micros "
        f"of {_fmt(trigger.get('daily_budget_micros'))} daily budget\n"
        f"- jobs still active: {trigger.get('jobs_active', 'unknown')}\n\n"
        "Response vocabulary:\n"
        "- throttle_station: pause ONE station's intake; reversible "
        "through the approvals inbox.\n"
        "- stop_all_intake: pause EVERY station. RESERVED for runaway "
        "spend.\n"
        "- require_approval: a human decides before intake is cut.\n\n"
        "Decision ladder — apply IN ORDER, first match wins:\n"
        "1. trigger = runaway_attempts -> throttle_station on THAT "
        "station (churn is the problem even when cost is zero).\n"
        "2. trigger = job_over_cap AND job cost >= its cap -> "
        "throttle_station on that station. If the job is only NEAR the "
        "cap (< 100%), -> require_approval on that station.\n"
        "3. trigger = daily_budget, spent >= 2x budget, OR jobs are "
        "still ACTIVELY accruing while the budget is breached -> "
        "stop_all_intake on 'all'.\n"
        "4. trigger = daily_budget, spent >= budget but < 2x, single "
        "completed outlier caused it, nothing accruing -> "
        "require_approval on 'all'.\n"
        "5. trigger = daily_budget, other cases (plain breach) -> "
        "throttle_station on 'ingest' (the intake point).\n\n"
        "Facts you cannot change: every enforcement action creates a "
        "Grafana annotation and incident (C-4.3); the trigger, not you, "
        "started this action; you choose among the three responses only "
        "— ignoring the trigger is not an option.\n\n"
        'Respond ONLY with JSON: {"agent": "spend_steward", "decision": '
        '"throttle_station|stop_all_intake|require_approval", "station": '
        '"<station|all|none>", "reason": "...", "confidence": '
        '"low|medium|high"}.'
    )


def parse_steward_decision(text: str, trigger: dict[str, Any]) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract.
    Tolerates markdown code fences around the JSON but nothing else."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    return validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=suggestion_for_trigger(trigger),
    )


def decide_spend_steward(
    settings: Any,
    *,
    trigger: dict[str, Any],
) -> tuple[StationDecision, int]:
    """THE real steward judgment: one metered Gemini call over the
    deterministic trigger, validated against the StationDecision contract.
    Returns (decision, cost_micros). The CALLER executes the chosen action
    through the existing enforcement functions (annotation + incident on
    every action, C-4.3). Raises on any API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(trigger),
        span_name="station.spend_steward.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_steward_decision(response["text"], trigger)
    return decision, int(response["cost_micros"])


def build_inspect_prompt(context: dict[str, Any]) -> str:
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("spend", context)
