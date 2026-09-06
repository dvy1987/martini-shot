"""Loudness Strategist station agent (A10-3): reads the deterministic
loudness measurements and decides the remediation path — accept /
fix_stem / apply_limiter / needs_human — plus per-profile routing.

There is no numeric gate to override here (design decision 2): the LUFS
number IS the number. The agent owns the RESPONSE: which fix path, and
which delivery profiles may take this master now (routing), including the
season-coherence view (sibling-episode levels).

Deterministic surface (no LLM): suggestion mapping, prompt construction
and response parsing are unit-tested; the real judgment behavior is gated
by the live EDD eval (scripts/loudness_strategy_eval.py vs
loudness_strategy_judgment, bar >= 0.8)."""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.station_agents.base import (
    StationDecision,
    validate_station_decision,
)

AGENT = "loudness_strategy"
DECISIONS = ("accept", "fix_stem", "apply_limiter", "needs_human")
STEM_DIAGNOSES = ("balanced", "dialogue_hot", "music_hot", "unknown")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["accept", "fix_stem", "apply_limiter", "needs_human"],
        },
        "streaming_route": {"type": "string", "enum": ["accept", "block"]},
        "broadcast_route": {"type": "string", "enum": ["accept", "block"]},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "agent",
        "decision",
        "streaming_route",
        "broadcast_route",
        "reason",
        "confidence",
    ],
}


def suggestion_for_report(report: dict[str, Any]) -> str:
    """Deterministic default path for this report: stem imbalance beats a
    blanket gain change (rebalance first, re-measure after); true-peak and
    integrated misses are limiter work; meter garbage escalates."""
    if report.get("stem_diagnosis") in ("dialogue_hot", "music_hot"):
        return "fix_stem"
    streaming = str(report.get("verdict_streaming") or "meter_error")
    if streaming == "pass":
        return "accept"
    if streaming in ("fail_hot", "fail_quiet", "fail_true_peak"):
        return "apply_limiter"
    return "needs_human"


def season_lines(season_state: list[dict[str, Any]]) -> str:
    """Per-sibling LUFS rows for coherence judgment."""
    if not season_state:
        return "(no sibling loudness measurements yet)"
    return "\n".join(
        f"- {r.get('episode_id')}: {r.get('lufs')} LUFS" for r in season_state
    )


def build_prompt(report: dict[str, Any], season_state: list[dict[str, Any]]) -> str:
    """The prompt carries the deterministic measurements, the season view,
    and the two decision rules: stem-imbalance-first, and season coherence
    (align an outlier episode instead of shipping it)."""
    return (
        "You are the Loudness Strategist agent for Martini Shot. The "
        "deterministic meter (ffmpeg ebur128) measured this episode; "
        "decide the remediation path and the delivery routing.\n\n"
        "Deterministic measurements (this episode):\n"
        f"- job: {report.get('job_id')}\n"
        f"- episode: {report.get('episode_id')}\n"
        f"- integrated: {report.get('lufs_integrated')} LUFS "
        "(streaming target -16.0 ±1 LU, broadcast target -24.0 ±1 LU)\n"
        f"- true peak: {report.get('true_peak_dbtp')} dBTP (ceiling -1.0)\n"
        f"- streaming verdict: {report.get('verdict_streaming')}\n"
        f"- broadcast verdict: {report.get('verdict_broadcast')}\n"
        f"- stem diagnosis: {report.get('stem_diagnosis')} "
        "(vocabulary: balanced|dialogue_hot|music_hot|unknown; dialogue "
        "band 300-3000 Hz vs music band 4-12 kHz; |gap| > 3 LU = "
        "imbalance)\n"
        f"- dialogue band: {report.get('dialogue_band_lufs')} LUFS, "
        f"music band: {report.get('music_band_lufs')} LUFS\n\n"
        f"Season (sibling episodes, LUFS):\n{season_lines(season_state)}\n\n"
        "Decision rules:\n"
        "1. Stem imbalance beats a blanket gain change: if dialogue_hot or "
        "music_hot, choose fix_stem (rebalance the bands, then re-measure) "
        "— an integrated pass with unbalanced stems is not an ear-pass.\n"
        "2. True-peak over -1.0 dBTP with sane integrated level = a "
        "transparent peak-limit pass (apply_limiter), not a loudness "
        "change.\n"
        "3. Season coherence: if the episode passes its target but sits "
        "clearly away (>1.5 LU) from the sibling median, align it "
        "(apply_limiter toward the season level); a season whose episodes "
        "jump level feels broken even if each passes in isolation.\n"
        "4. If the meter produced nothing (meter_error), choose "
        "needs_human — you cannot fix what cannot be measured.\n\n"
        "Routing: set streaming_route / broadcast_route to accept only if "
        "that profile is currently satisfiable; a profile whose verdict "
        "fails and whose failure your decision would not fix must be "
        "blocked (e.g. broadcast -24 target is a separate master "
        "concern).\n\n"
        'Respond ONLY with JSON: {"agent": "loudness_strategy", '
        '"decision": "accept|fix_stem|apply_limiter|needs_human", '
        '"streaming_route": "accept|block", "broadcast_route": '
        '"accept|block", "reason": "...", "confidence": '
        '"low|medium|high"}.'
    )


def parse_strategy_decision(text: str, report: dict[str, Any]) -> StationDecision:
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


def decide_loudness_strategy(
    settings: Any,
    *,
    report: dict[str, Any],
    season_state: list[dict[str, Any]],
) -> tuple[StationDecision, int]:
    """THE real loudness strategy judgment: one metered Gemini call over
    the measurements plus the season state, validated against the
    StationDecision contract. Returns (decision, cost_micros) — the caller
    folds the cost into the job (C-6.4). Raises on any API/validation
    error (C-1.1)."""
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(report, season_state),
        span_name="station.loudness_strategy.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    decision = parse_strategy_decision(response["text"], report)
    return decision, int(response["cost_micros"])
