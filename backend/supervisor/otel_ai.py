"""B-3: Grafana Cloud AI Observability for supervisor Gemini calls (C-4.4, C-6.4)."""

from __future__ import annotations

import time
from typing import Any

from opentelemetry import trace

from backend.core.config import Settings
from backend.core.models import TEXT_MODEL, THINKING_LEVEL, THROUGH_THOUGHTS
from backend.jobs.telemetry import record_ai_usage

# Vertex introductory rates through 2026-12-31 (global PayGo).
# See Google Cloud Gemini Enterprise Agent Platform pricing docs.
INPUT_USD_PER_MILLION = 0.75
OUTPUT_USD_PER_MILLION = 3.75
MICROS_PER_USD = 1_000_000

tracer = trace.get_tracer("pc.supervisor")
_instrumented = False


def cost_micros(input_tokens: int, output_tokens: int) -> int:
    """Integer micro-units: usd * 1e6, rounded. Thinking tokens count as output."""
    usd = (
        max(0, input_tokens) * INPUT_USD_PER_MILLION
        + max(0, output_tokens) * OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    return int(round(usd * MICROS_PER_USD))


def instrument_genai() -> None:
    global _instrumented
    if _instrumented:
        return
    try:
        from opentelemetry.instrumentation.google_genai import (
            GoogleGenAiSdkInstrumentor,
        )
    except ImportError:
        return
    GoogleGenAiSdkInstrumentor().instrument()
    _instrumented = True


def run_supervisor_text(
    settings: Settings, prompt: str, *, instrument: bool = True
) -> dict[str, Any]:
    """One real Gemini text call with token/cost/latency (B-3). Not an HTTP path."""
    if instrument:
        instrument_genai()
    from google import genai
    from google.genai import types

    started = time.perf_counter()
    with tracer.start_as_current_span("supervisor.generate_content") as span:
        span.set_attribute("gen_ai.system", "gcp.vertex")
        span.set_attribute("gen_ai.request.model", TEXT_MODEL)
        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location="global",
        )
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=THINKING_LEVEL.lower(),  # type: ignore[arg-type]
                    include_thoughts=THROUGH_THOUGHTS,
                )
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        thought_tokens = int(getattr(usage, "thoughts_token_count", 0) or 0)
        billed_out = output_tokens + thought_tokens
        micros = cost_micros(input_tokens, billed_out)
        latency_ms = (time.perf_counter() - started) * 1000
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", billed_out)
        span.set_attribute("pc.cost_micros", micros)
        span.set_attribute("pc.latency_ms", latency_ms)
        record_ai_usage(
            input_tokens=input_tokens,
            output_tokens=billed_out,
            cost_micros=micros,
        )
        text = getattr(response, "text", "") or ""
        return {
            "model": TEXT_MODEL,
            "text": text,
            "input_tokens": input_tokens,
            "output_tokens": billed_out,
            "cost_micros": micros,
            "latency_ms": round(latency_ms, 1),
        }
