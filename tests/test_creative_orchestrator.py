"""Creative Orchestrator routing is deterministic and closed-set."""

from __future__ import annotations

from backend.supervisor.agents.creative_orchestrator import (
    SPECIALISTS,
    route_creative_agents,
)


def test_empty_brief_selects_nobody() -> None:
    assert route_creative_agents(brief="", signal=None) == []


def test_signage_brief_routes_corrections_and_draft_first() -> None:
    selected = route_creative_agents(brief="replace the café sign text")
    assert selected == ["corrections", "draft_first"]
    assert set(selected).issubset(SPECIALISTS)


def test_script_signal_routes_revision_room_only() -> None:
    selected = route_creative_agents(signal="script_changed")
    assert selected == ["revision_room"]
