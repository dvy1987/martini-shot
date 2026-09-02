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
