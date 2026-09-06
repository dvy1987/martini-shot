"""Caption Remediation station agent (A10-3): turns deterministic D-3
violation reports into CONCRETE cue fixes (re-timing, re-segmentation,
line splitting). Closed loop (design decision 2): every proposed fix set
is RE-VALIDATED by the deterministic rule engine (stations.delivery.
captions.validate_cues) before it can ship — the validator remains the
arbiter; a fix with residual violations is refused, never shipped.

Meaning preservation is the agent's hard rule: re-timing and splitting
only — inventing or deleting dialogue is grounds for needs_human.

Deterministic surface (no LLM): prompt construction, fix re-validation,
SRT rendering, and response parsing are unit-tested; the real judgment is
gated by the live EDD eval (scripts/caption_remediation_eval.py vs
caption_remediation_judgment, bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.stations.delivery.captions import Cue, validate_cues
from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "caption_remediation"
DECISIONS = ("apply_fixes", "needs_human")
# The deterministic status quo: any D-3 violation lands as needs_human.
SUGGESTION = "needs_human"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {"type": "string", "enum": ["apply_fixes", "needs_human"]},
        "fixed_cues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "lines": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_s", "end_s", "lines"],
            },
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "decision", "reason", "confidence"],
}


def build_prompt(cues: list[dict[str, Any]], violations: list[dict[str, Any]]) -> str:
    """The prompt carries the offending cues, the deterministic violation
    report, the meaning-preservation rule, and the closed-loop disclosure:
    whatever it proposes is re-validated by the deterministic engine."""
    return (
        "You are the Caption Remediation agent for Martini Shot. The "
        "deterministic caption checker (rules CAP-001..CAP-007) flagged "
        "violations; produce a corrected cue set.\n\n"
        "Offending cues (start_s/end_s in seconds):\n"
        f"{json.dumps(cues, indent=2)}\n\n"
        "Deterministic violations:\n"
        + "\n".join(
            f"- {v['rule_id']} (cue {v.get('cue_index')}): {v['message']}"
            for v in violations
        )
        + "\n\nRules of engagement:\n"
        "1. PRESERVE MEANING: reuse the original text verbatim — you may "
        "re-time (extend/shift starts and ends), re-segment (split one cue "
        "into several), and re-wrap lines (max 42 chars per line). You may "
        "NOT invent, paraphrase, or delete dialogue. If a compliant fix "
        "would require changing the words, choose needs_human.\n"
        "2. Return the COMPLETE corrected cue set (every cue, fixed or "
        "untouched), in chronological order, in fixed_cues.\n"
        "3. Your proposal is RE-VALIDATED by the deterministic rule engine "
        "before it can ship; any residual violation (reading speed > 20 "
        "cps, line > 42 chars, duration < 5/6 s, gap < 2 frames, overlap, "
        "empty text) blocks the whole fix set.\n"
        "4. If the violation cannot be fixed within these bounds, choose "
        "needs_human.\n"
        "5. An empty cue (CAP-007) means the source text is MISSING — you "
        "cannot know what was lost, so there is nothing safe to fill in "
        "and nothing safe to drop; choose needs_human.\n\n"
        'Respond ONLY with JSON: {"agent": "caption_remediation", '
        '"decision": "apply_fixes|needs_human", "fixed_cues": '
        '[{"start_s": 0.0, "end_s": 0.0, "lines": ["..."]}], "reason": '
        '"...", "confidence": "low|medium|high"}. For needs_human, omit '
        "fixed_cues."
    )


def parse_remediation_decision(
    text: str,
    cues: list[dict[str, Any]],
    violations: list[dict[str, Any]],
) -> StationDecision:
    """Validate the model's JSON against the StationDecision contract.
    Tolerates markdown code fences around the JSON but nothing else."""
    del cues, violations  # the suggestion is constant; kept for symmetry
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if payload.get("decision") == "apply_fixes" and not isinstance(
        payload.get("fixed_cues"), list
    ):
        raise ValueError("apply_fixes requires a fixed_cues list")
    return validate_station_decision(
        payload,
        agent=AGENT,
        allowed_decisions=DECISIONS,
        deterministic_suggestion=SUGGESTION,
    )


def revalidate_fixed_cues(
    payload: dict[str, Any],
) -> tuple[list[Cue], list[Any]]:
    """THE closed loop (C-1.1): convert the agent's proposed cue set into
    real Cue objects and hand them to the DETERMINISTIC D-3 engine. Returns
    (cues, residual_violations) — empty residual means the fix may ship.
    Fail loud on any shape drift."""
    rows = payload.get("fixed_cues")
    if not isinstance(rows, list):
        raise ValueError("fixed_cues must be a list")
    cues: list[Cue] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("fixed_cues entries must be objects")
        start = row.get("start_s")
        end = row.get("end_s")
        lines = row.get("lines")
        if (
            not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not isinstance(lines, list)
            or not all(isinstance(ln, str) for ln in lines)
        ):
            raise ValueError("fixed_cues entry fields have wrong types")
        cues.append(Cue(float(start), float(end), tuple(lines)))
    return cues, validate_cues(cues)


def render_srt(cues: list[Cue]) -> str:
    """Deterministic SRT rendering of a validated fix set."""
    blocks = []
    for i, cue in enumerate(cues, start=1):
        start = _srt_ts(cue.start_s)
        end = _srt_ts(cue.end_s)
        blocks.append(f"{i}\n{start} --> {end}\n" + "\n".join(cue.lines))
    return "\n\n".join(blocks) + "\n"


def _srt_ts(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def decide_caption_remediation(
    settings: Any,
    *,
    cues: list[dict[str, Any]],
    violations: list[dict[str, Any]],
) -> tuple[StationDecision, int]:
    """THE real remediation judgment: one metered Gemini call over the cues
    plus the violation report, validated against the StationDecision
    contract. Returns (decision, cost_micros) — the caller folds the cost
    into the job (C-6.4). The caller MUST run revalidate_fixed_cues before
    shipping anything (closed loop). Raises on API/validation error."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(cues, violations),
        span_name="station.caption_remediation.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_remediation_decision(response["text"], cues, violations)
    return decision, int(response["cost_micros"])
