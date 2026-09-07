"""Spend prices leftover finishing proposals (walk-away loop).

After mix and pickups, specialists suggest work. Spend names a real
integer micro cost for EACH leftover job. The orchestrator then ranks
those numbers. Station default micros are advice, never the product price.

Deterministic surface: prompt + JSON parse. Judgment is live Gemini EDD
(scripts/spend_pricing_eval.py vs spend_pricing_judgment, bar >= 0.8).
"""

from __future__ import annotations

import json
from typing import Any

from backend.supervisor.inspect import DEFAULT_COST_MICROS

AGENT = "spend_pricing"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "prices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "cost_estimate_micros": {"type": "integer"},
                },
                "required": ["id", "cost_estimate_micros"],
            },
        },
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["agent", "prices", "reason", "confidence"],
}


class SpendPricingError(ValueError):
    """Malformed spend pricing JSON never reaches the orchestrator."""


def default_price_for(candidate_id: str) -> int:
    station = str(candidate_id or "").split("::", 1)[0]
    return int(DEFAULT_COST_MICROS.get(station, 0))


def parse_spend_prices(text: str, candidate_ids: list[str]) -> dict[str, int]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise SpendPricingError("spend pricing payload must be an object")
    if str(payload.get("agent") or "") != AGENT:
        raise SpendPricingError(f"agent {payload.get('agent')!r} is not {AGENT}")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise SpendPricingError("reason is mandatory")
    raw_prices = payload.get("prices")
    if not isinstance(raw_prices, list):
        raise SpendPricingError("prices must be an array")
    allowed = set(candidate_ids)
    out: dict[str, int] = {}
    for row in raw_prices:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "")
        if item_id not in allowed:
            continue
        try:
            cost = int(row.get("cost_estimate_micros"))
        except (TypeError, ValueError) as exc:
            raise SpendPricingError("cost_estimate_micros must be an integer") from exc
        if cost < 0:
            raise SpendPricingError("cost_estimate_micros must be >= 0")
        out[item_id] = cost
    for item_id in candidate_ids:
        out.setdefault(item_id, default_price_for(item_id))
    return out


def build_prompt(candidates: list[dict[str, Any]], remaining_micros: int) -> str:
    return (
        "You are the Spend pricing agent for Martini Shot. Specialists already "
        "looked AFTER mix and pickups. Name a real integer micro-unit cost for "
        "EACH leftover proposal. Do not invent a picture job. Do not price "
        "leave-it or empty notes (they are not in this list).\n\n"
        "Use station defaults only as advice: loudness 80_000, pickups "
        "2_000_000, dub 500_000, Omni picture drafts 3_000_000, delivery "
        "50_000. A 360p draft is cheaper than a master. A dub is cheaper "
        "than an Omni picture edit. Spend itself is 0.\n\n"
        f"remaining_micros: {remaining_micros}\n"
        f"candidates:\n{json.dumps(candidates, indent=2, default=str)}\n\n"
        'Respond ONLY with JSON: {"agent": "spend_pricing", "prices": '
        '[{"id": "extend::shot-a", "cost_estimate_micros": 3000000}], '
        '"reason": "...", "confidence": "low|medium|high"}.'
    )


def decide_spend_pricing(
    settings: Any,
    *,
    candidates: list[dict[str, Any]],
    remaining_micros: int,
) -> tuple[dict[str, int], int]:
    """Billed Gemini prices. Returns ({id: micros}, cost_micros)."""
    ids = [str(row.get("id") or "") for row in candidates if row.get("id")]
    if not ids:
        return {}, 0
    from backend.supervisor.otel_ai import run_agent_call

    response = run_agent_call(
        settings,
        build_prompt(candidates, remaining_micros),
        span_name="station.spend_pricing.agent",
        persona=AGENT,
        response_schema=SCHEMA,
    )
    return parse_spend_prices(response["text"], ids), int(response["cost_micros"])


def apply_prices(notes: list[Any], prices: dict[str, int]) -> None:
    from dataclasses import replace

    from backend.supervisor.rank import note_key

    for index, note in enumerate(list(notes)):
        key = note_key(note)
        if key in prices and hasattr(note, "cost_estimate_micros"):
            notes[index] = replace(note, cost_estimate_micros=int(prices[key]))
