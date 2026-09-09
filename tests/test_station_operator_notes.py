"""Station agents write operator notes that cover four facts, without headings."""

from backend.supervisor.station_agents.base import (
    OPERATOR_NOTES_RULE,
    with_operator_notes,
)


def test_operator_notes_rule_asks_for_four_facts_without_headings() -> None:
    text = OPERATOR_NOTES_RULE.lower()
    assert "problem" in text
    assert "ignored" in text or "left alone" in text
    assert "changed" in text or "kept" in text
    assert "fail" in text
    assert "heading" in text or "label" in text


def test_with_operator_notes_appends_the_rule_once() -> None:
    prompt = with_operator_notes("Listen to the mix and pick a target.")
    assert "Listen to the mix and pick a target." in prompt
    assert OPERATOR_NOTES_RULE in prompt
    assert prompt.count(OPERATOR_NOTES_RULE) == 1
    assert with_operator_notes(prompt) == prompt


def test_station_agent_call_attaches_operator_notes_rule(monkeypatch) -> None:
    from backend.core.config import get_settings
    from backend.supervisor import otel_ai

    captured: dict = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["contents"] = contents
            usage = type(
                "U",
                (),
                {
                    "prompt_token_count": 1,
                    "candidates_token_count": 1,
                    "thoughts_token_count": 0,
                },
            )()
            return type("R", (), {"usage_metadata": usage, "text": "{}"})()

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    otel_ai.run_agent_call(
        get_settings(),
        "Listen to the mix.",
        span_name="station.loudness_strategy.agent",
        persona="loudness_strategy",
        instrument=False,
    )
    assert OPERATOR_NOTES_RULE in captured["contents"]


def test_non_station_call_does_not_attach_operator_notes(monkeypatch) -> None:
    from backend.core.config import get_settings
    from backend.supervisor import otel_ai

    captured: dict = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["contents"] = contents
            usage = type(
                "U",
                (),
                {
                    "prompt_token_count": 1,
                    "candidates_token_count": 1,
                    "thoughts_token_count": 0,
                },
            )()
            return type("R", (), {"usage_metadata": usage, "text": "ok"})()

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    otel_ai.run_agent_call(
        get_settings(),
        "root-cause this",
        span_name="specialist.reliability",
        persona="reliability_investigator",
        instrument=False,
    )
    assert captured["contents"] == "root-cause this"
