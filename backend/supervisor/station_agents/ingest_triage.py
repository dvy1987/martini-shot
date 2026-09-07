"""Ingest Triage station agent (A10-3): reads the deterministic probe/
corruption report and decides the quarantine disposition — re_ingest /
salvage / reject / needs_human — with BATCH-level correlation.

There is no numeric gate to override here (design decision 2): the number
IS the number. The agent owns the RESPONSE to the report. The deterministic
default mapping (reason_code -> disposition) is passed to the decision
validator as the suggestion; a different agent decision is an explicit,
reasoned choice, not a silent override.

Deterministic surface (no LLM): prompt construction, the anomaly summary,
suggestion mapping, and response parsing are unit-tested; the real
judgment-call behavior is gated by the live EDD eval
(scripts/ingest_triage_eval.py vs ingest_triage_judgment, bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "ingest_triage"
DECISIONS = ("re_ingest", "salvage", "reject", "needs_human")

# Deterministic default disposition per observed reason code. These map the
# single-file view; the agent's job is to improve on it with batch context.
SUGGESTION: dict[str, str] = {
    "empty_payload": "re_ingest",
    "corrupt_probe": "re_ingest",
    "corrupt_decode": "re_ingest",
    "missing_audio": "reject",
}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["re_ingest", "salvage", "reject", "needs_human"],
        },
        "batch_correlation": {
            "type": "string",
            "enum": ["none", "possible_upstream", "upstream_cause"],
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "agent",
        "decision",
        "batch_correlation",
        "reason",
        "confidence",
    ],
}


def suggestion_for_report(report: dict[str, Any]) -> str:
    """Deterministic default for this report (used as the validator's
    suggestion; unknown reasons escalate conservatively)."""
    return SUGGESTION.get(str(report.get("reason_code")), "needs_human")


def summarize_batch(batch_state: list[dict[str, Any]]) -> str:
    """Deterministic sibling summary: total, failures by reason, and whether
    failures share a source tape. The agent reasons over THIS, it does not
    recompute statistics from raw rows."""
    total = len(batch_state)
    failures = [r for r in batch_state if r.get("status") == "quarantined"]
    if not failures:
        return f"Batch: {total} sibling ingest jobs, none quarantined."
    by_reason: dict[str, int] = {}
    for r in failures:
        reason = str(r.get("error") or "unknown")
        by_reason[reason] = by_reason.get(reason, 0) + 1
    breakdown = ", ".join(f"{v}x {k}" for k, v in sorted(by_reason.items()))
    failed_tapes = {
        str(r.get("source_ref", "")).split("/")[1]
        for r in failures
        if len(str(r.get("source_ref", "")).split("/")) > 1
    }
    tape_note = (
        f" Failed siblings come from tape(s): {', '.join(sorted(failed_tapes))}."
        if failed_tapes
        else ""
    )
    return (
        f"Batch: {len(failures)} of {total} sibling ingest jobs quarantined "
        f"({breakdown}).{tape_note}"
    )


def batch_lines(batch_state: list[dict[str, Any]]) -> str:
    """Per-sibling rows so the agent can correlate episode <-> tape itself."""
    if not batch_state:
        return "(no sibling ingest jobs yet)"
    lines = []
    for r in batch_state:
        status = str(r.get("status") or "unknown")
        error = f" ({r['error']})" if r.get("error") else ""
        lines.append(f"- {r.get('episode_id')}: {status}{error}")
    return "\n".join(lines)


def build_prompt(report: dict[str, Any], batch_state: list[dict[str, Any]]) -> str:
    """The prompt carries the deterministic report (advisory context), the
    deterministic batch summary, and the correlation rule: recurring
    identical anomalies across episodes sharing a source are an UPSTREAM
    cause — escalate once (needs_human), do not reject every episode."""
    probe = json.dumps(report.get("probe") or {}, sort_keys=True)
    return (
        "You are the Ingest Triage agent for Martini Shot. One ingest job "
        "was quarantined by the deterministic checker; decide its "
        "disposition.\n\n"
        "Deterministic report (this job):\n"
        f"- job: {report.get('job_id')}\n"
        f"- source: {report.get('source_ref')}\n"
        f"- verdict: {report.get('verdict')}\n"
        f"- reason_code: {report.get('reason_code')}\n"
        f"- probe: {probe}\n"
        f"- checksum_sha256: {report.get('checksum_sha256')}\n\n"
        f"{summarize_batch(batch_state)}\n"
        f"Sibling ingest jobs:\n{batch_lines(batch_state)}\n\n"
        "Batch-correlation rule: if MULTIPLE episodes fail with the SAME "
        "reason and they share a source tape, the cause is upstream (bad "
        "tape/export) — choose needs_human so a person addresses the cause "
        "once; do NOT reject every affected episode.\n"
        "Choose re_ingest when the failure looks isolated or transient "
        "(transfer glitch, truncation) and a re-transfer of the same source "
        "can plausibly succeed. Choose salvage only if the content is "
        "usable with a stated limitation. Choose reject when re-ingesting "
        "cannot fix the file (e.g. the container has no audio track at "
        "all). Choose needs_human when the cause is upstream, ambiguous, "
        "or outside your vocabulary.\n\n"
        'Respond ONLY with JSON: {"agent": "ingest_triage", '
        '"decision": "re_ingest|salvage|reject|needs_human", '
        '"batch_correlation": "none|possible_upstream|upstream_cause", '
        '"reason": "...", "confidence": "low|medium|high"}.'
    )


def parse_triage_decision(text: str, report: dict[str, Any]) -> StationDecision:
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
        deterministic_suggestion=suggestion_for_report(report),
    )


def decide_ingest_triage(
    settings: Any,
    *,
    report: dict[str, Any],
    batch_state: list[dict[str, Any]],
) -> tuple[StationDecision, int]:
    """THE real triage judgment: one metered Gemini call over the report
    plus the batch state, validated against the StationDecision contract.
    Returns (decision, cost_micros) — the caller folds the cost into the
    job (C-6.4). Raises on any API/validation error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(report, batch_state),
        span_name="station.ingest_triage.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_triage_decision(response["text"], report)
    return decision, int(response["cost_micros"])


def build_inspect_prompt(context: dict[str, Any]) -> str:
    from backend.supervisor.inspect_impl import station_inspect_prompt

    return station_inspect_prompt("ingest", context)
