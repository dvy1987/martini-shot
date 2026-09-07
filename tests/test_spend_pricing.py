"""TDD: spend prices leftover proposals (parse contract). Live Gemini is EDD."""

from __future__ import annotations

import json

from backend.supervisor.inspect import DEFAULT_COST_MICROS, validate_inspect_note
from backend.supervisor.station_agents.spend_pricing import (
    apply_prices,
    parse_spend_prices,
)


def test_parse_spend_prices_overrides_defaults() -> None:
    text = json.dumps(
        {
            "agent": "spend_pricing",
            "prices": [
                {"id": "extend::shot-a", "cost_estimate_micros": 1_500_000},
                {"id": "dub::shot-a", "cost_estimate_micros": 400_000},
            ],
            "reason": "Draft 360p is cheaper than a master; dub is cheaper than Omni.",
            "confidence": "high",
        }
    )
    prices = parse_spend_prices(
        text, ["extend::shot-a", "dub::shot-a", "delivery::shot-a"]
    )
    assert prices["extend::shot-a"] == 1_500_000
    assert prices["dub::shot-a"] == 400_000
    assert prices["delivery::shot-a"] == DEFAULT_COST_MICROS["delivery"]


def test_apply_prices_stamps_notes() -> None:
    note = validate_inspect_note(
        {
            "station": "extend",
            "agent": "extend",
            "status": "needs_work",
            "impact": "medium",
            "kind": "defect",
            "summary": "dies mid-thought",
            "cost_estimate_micros": 3_000_000,
            "proposal": {"kind": "station_job", "station": "extend", "args": {}},
            "shot_id": "shot-a",
        }
    )
    notes = [note]
    apply_prices(notes, {"extend::shot-a": 1_200_000})
    assert notes[0].cost_estimate_micros == 1_200_000
