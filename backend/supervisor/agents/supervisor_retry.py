"""Gemini judgment: after diagnosis, is one retry_job the right next move?"""

from __future__ import annotations

import json
from typing import Any

from backend.core.config import Settings
from backend.supervisor.otel_ai import run_agent_call

AGENT = "supervisor_retry"
DECISIONS = ("retry", "fix", "propose", "abstain")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "reason": {"type": "string"},
    },
    "required": ["agent", "decision", "reason"],
}


class SupervisorRetryError(ValueError):
    """Malformed retry-once JSON never reaches dispatch."""


def parse_retry_decision(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise SupervisorRetryError("retry payload must be an object")
    if str(payload.get("agent") or "") != AGENT:
        raise SupervisorRetryError(f"agent {payload.get('agent')!r} is not {AGENT}")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise SupervisorRetryError("reason is mandatory")
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in DECISIONS:
        raise SupervisorRetryError(f"decision {decision!r} is not in {DECISIONS}")
    return decision


def build_prompt(job: dict[str, Any], *, command_name: str = "retry_job") -> str:
    return (
        "You are the Post Supervisor for Martini Shot. Specialists already "
        "diagnosed this failed job. For THIS proposed command, choose one:\n\n"
        "If proposed_command is retry_job, answer retry when one more run "
        "of the SAME job is the move (429, 503, first loudness miss).\n"
        "If proposed_command is correct_shot, extend_shot, relight_shot, "
        "generate_coverage, or apply_camera_language, answer fix when that "
        "repair should run (then a later retry_job may re-run the station).\n"
        "propose — a human must decide (lock the cut, stop spend, pick a "
        "delivery destination, pause the house).\n"
        "abstain — this cannot help or is unsafe (corrupt file, locked cut, "
        "already used the one retry, runaway identical failures).\n\n"
        "You cannot invent commands. You cannot lock a shot, change "
        "continuity, pause intake, or render a master.\n\n"
        f"proposed_command: {command_name}\n"
        f"job:\n{json.dumps(job, indent=2, default=str)}\n\n"
        'Respond ONLY with JSON: {"agent": "supervisor_retry", '
        '"decision": "fix|retry|propose|abstain", "reason": "..."}.'
    )


def decide_retry_once(
    settings: Settings,
    *,
    job: dict[str, Any],
    command_name: str = "retry_job",
) -> tuple[str, int]:
    """Billed Gemini judgment. Returns (decision, cost_micros)."""
    response = run_agent_call(
        settings,
        build_prompt(job, command_name=command_name),
        span_name="supervisor.retry_once.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_retry_decision(response["text"]), int(response["cost_micros"])
