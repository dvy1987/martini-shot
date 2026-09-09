"""Studio directed-edit agent: merges operator station/camera-movement
picks and free-text chat into one bounded edit intent, asking at most 5
clarifying questions along the way (2026-09-09 Studio redesign)."""

from __future__ import annotations

import json

import pytest


def _payload(decision: str, reason: str, **extra: object) -> str:
    return json.dumps(
        {
            "agent": "directed_edit",
            "decision": decision,
            "reason": reason,
            "confidence": "high",
            **extra,
        }
    )


def test_suggestion_hard_caps_at_five_questions() -> None:
    from backend.supervisor.station_agents.directed_edit import (
        MAX_QUESTIONS,
        suggestion_for_brief,
    )

    assert MAX_QUESTIONS == 5
    under_cap = {"turns": [{"question": "q1", "answer": "a1"}]}
    assert suggestion_for_brief(under_cap) == ""
    at_cap = {"turns": [{"question": f"q{i}", "answer": f"a{i}"} for i in range(5)]}
    assert suggestion_for_brief(at_cap) == "ready"
    over_cap = {"turns": [{"question": f"q{i}", "answer": f"a{i}"} for i in range(7)]}
    assert suggestion_for_brief(over_cap) == "ready"


def test_build_prompt_includes_selections_chat_text_and_transcript() -> None:
    from backend.supervisor.station_agents.directed_edit import build_prompt

    prompt = build_prompt(
        {
            "stations": ["relight", "camera_language"],
            "camera_movement": "handheld_shaky",
            "chat_text": "make it feel tense",
            "turns": [{"question": "Darker or brighter?", "answer": "Darker"}],
        }
    )
    assert "relight" in prompt.lower()
    assert "handheld camera with natural human shake" in prompt
    assert "make it feel tense" in prompt
    assert "Darker or brighter?" in prompt
    assert "Darker" in prompt
    assert "5" in prompt


def test_build_prompt_handles_nothing_selected_yet() -> None:
    from backend.supervisor.station_agents.directed_edit import build_prompt

    prompt = build_prompt(
        {"stations": [], "camera_movement": None, "chat_text": "", "turns": []}
    )
    assert "none yet" in prompt.lower() or "(none" in prompt.lower()


def test_parse_ask_requires_a_question() -> None:
    from backend.supervisor.station_agents.directed_edit import (
        StationDecisionError,
        parse_directed_edit_decision,
    )

    brief = {
        "stations": ["relight"],
        "camera_movement": None,
        "chat_text": "",
        "turns": [],
    }
    with pytest.raises(StationDecisionError, match="question"):
        parse_directed_edit_decision(_payload("ask", "need more detail"), brief)


def test_parse_ready_requires_a_final_intent() -> None:
    from backend.supervisor.station_agents.directed_edit import (
        StationDecisionError,
        parse_directed_edit_decision,
    )

    brief = {
        "stations": ["relight"],
        "camera_movement": None,
        "chat_text": "",
        "turns": [],
    }
    with pytest.raises(StationDecisionError, match="final_intent"):
        parse_directed_edit_decision(_payload("ready", "enough to act"), brief)


def test_parse_ask_returns_the_question() -> None:
    from backend.supervisor.station_agents.directed_edit import (
        parse_directed_edit_decision,
    )

    brief = {
        "stations": ["relight"],
        "camera_movement": None,
        "chat_text": "",
        "turns": [],
    }
    decision = parse_directed_edit_decision(
        _payload("ask", "need to know the mood", question="Warmer or colder light?"),
        brief,
    )
    assert decision.decision == "ask"
    assert decision.raw["question"] == "Warmer or colder light?"


def test_parse_ready_returns_the_final_intent() -> None:
    from backend.supervisor.station_agents.directed_edit import (
        parse_directed_edit_decision,
    )

    brief = {
        "stations": ["relight", "corrections"],
        "camera_movement": None,
        "chat_text": "warmer and remove the boom mic",
        "turns": [],
    }
    decision = parse_directed_edit_decision(
        _payload(
            "ready",
            "enough to act",
            final_intent="Warm the lighting and remove the visible boom mic.",
        ),
        brief,
    )
    assert decision.decision == "ready"
    assert (
        decision.raw["final_intent"]
        == "Warm the lighting and remove the visible boom mic."
    )


def test_parse_hard_gate_coerces_ask_to_ready_past_the_question_cap() -> None:
    """A model that keeps asking past 5 questions must be overridden — the
    operator answered enough; the agent must act, not stall forever."""
    from backend.supervisor.station_agents.directed_edit import (
        parse_directed_edit_decision,
    )

    brief = {
        "stations": ["relight"],
        "camera_movement": None,
        "chat_text": "make it moodier",
        "turns": [{"question": f"q{i}", "answer": f"a{i}"} for i in range(5)],
    }
    decision = parse_directed_edit_decision(
        _payload("ask", "still unsure", question="One more thing?"),
        brief,
    )
    assert decision.decision == "ready"
    assert decision.overridden is True
    assert decision.raw.get("final_intent")


def test_default_final_intent_falls_back_to_something_actionable() -> None:
    from backend.supervisor.station_agents.directed_edit import default_final_intent

    intent = default_final_intent(
        {
            "stations": ["relight", "coverage"],
            "camera_movement": "crash_zoom",
            "chat_text": "more dramatic",
            "turns": [],
        }
    )
    assert "more dramatic" in intent
    assert "relight" in intent.lower() or "lighting" in intent.lower()
    assert "crash zoom" in intent.lower() or "crash_zoom" in intent.lower()


def test_default_final_intent_never_empty_with_nothing_selected() -> None:
    from backend.supervisor.station_agents.directed_edit import default_final_intent

    intent = default_final_intent(
        {"stations": [], "camera_movement": None, "chat_text": "", "turns": []}
    )
    assert intent.strip()


def test_parser_accepts_display_cased_agent_name() -> None:
    from backend.supervisor.station_agents.directed_edit import (
        parse_directed_edit_decision,
    )

    brief = {"stations": [], "camera_movement": None, "chat_text": "hi", "turns": []}
    payload = json.dumps(
        {
            "agent": "Directed Edit",
            "decision": "ready",
            "reason": "enough",
            "confidence": "medium",
            "final_intent": "A light, tasteful pass on the clip.",
        }
    )
    decision = parse_directed_edit_decision(payload, brief)
    assert decision.agent == "directed_edit"
