"""B-3 cost math: Vertex 3.7 Flash introductory rates → integer micros."""

from backend.supervisor.otel_ai import cost_micros, instrument_genai


def test_flash_cost_micros_uses_published_rates() -> None:
    # $0.75/1M in + $3.75/1M out → 0.75 µ + 3.75 µ per token
    assert cost_micros(100, 20) == 150
    assert cost_micros(0, 0) == 0
    assert cost_micros(-3, 10) == 38  # 10 * 3.75 = 37.5 → 38


def test_instrument_genai_is_idempotent() -> None:
    instrument_genai()
    instrument_genai()


def test_run_supervisor_text_delegates_to_run_agent_call(monkeypatch) -> None:
    """H-1a: every specialist/verifier/synthesis call goes through ONE
    instrumented call site; the B-3 supervisor call is now a thin wrapper."""
    from backend.core.config import get_settings
    from backend.supervisor import otel_ai

    captured: dict = {}

    def fake_agent_call(settings, prompt, *, span_name, persona, **kwargs):
        captured["prompt"] = prompt
        captured["span_name"] = span_name
        captured["persona"] = persona
        return {
            "model": "m",
            "text": "ok",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_micros": 0,
            "latency_ms": 0.0,
        }

    monkeypatch.setattr(otel_ai, "run_agent_call", fake_agent_call)
    out = otel_ai.run_supervisor_text(get_settings(), "diagnose job job-1")

    assert out["text"] == "ok"
    assert captured["prompt"] == "diagnose job job-1"
    assert captured["span_name"] == "supervisor.generate_content"
    assert captured["persona"] == "post_supervisor"


def test_run_agent_call_builds_typed_config(monkeypatch) -> None:
    """tools/response_schema flow into GenerateContentConfig; persona lands
    on the span (gen_ai.agent.name) so Grafana can filter per-specialist."""
    from backend.core.config import get_settings
    from backend.supervisor import otel_ai

    captured: dict = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            usage = type(
                "U",
                (),
                {
                    "prompt_token_count": 10,
                    "candidates_token_count": 5,
                    "thoughts_token_count": 0,
                },
            )()
            return type("R", (), {"usage_metadata": usage, "text": '{"claim": "ok"}'})()

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    result = otel_ai.run_agent_call(
        get_settings(),
        span_name="specialist.reliability",
        persona="reliability_investigator",
        prompt="root-cause this",
        response_schema={"type": "object"},
    )

    assert result["text"] == '{"claim": "ok"}'
    assert captured["model"] == otel_ai.TEXT_MODEL
    config = captured["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema == {"type": "object"}
    # No tools passed → the SDK normalizes to None (empty list equally
    # valid); the contract is "no tools kwarg", not "an empty tool list".
    assert config.tools in (None, [])


def test_gemini_look_treats_deadline_as_transient() -> None:
    from backend.supervisor.otel_ai import gemini_transient

    assert gemini_transient(RuntimeError("504 DEADLINE_EXCEEDED")) is True
    assert gemini_transient(RuntimeError("503 UNAVAILABLE")) is True
    assert gemini_transient(RuntimeError("429 RESOURCE_EXHAUSTED")) is True
    assert gemini_transient(TimeoutError("The read operation timed out")) is True
    assert gemini_transient(RuntimeError("400 INVALID_ARGUMENT")) is False
