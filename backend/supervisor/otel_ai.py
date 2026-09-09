"""B-3: Grafana Cloud AI Observability for supervisor Gemini calls (C-4.4, C-6.4).
H-1a: `run_agent_call` is the single instrumented call site for every agent
in the deliberation pipeline; `run_supervisor_text` is a thin wrapper."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from opentelemetry import trace

from backend.core.api_resilience import call_with_resilience
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


def gemini_transient(exc: Exception) -> bool:
    """Vertex 504/503/429/timeouts on a look are retryable."""
    text = str(exc)
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__
    if "Timeout" in name:
        return True
    return any(
        token in text
        for token in (
            "429",
            "500",
            "502",
            "503",
            "504",
            "DEADLINE_EXCEEDED",
            "UNAVAILABLE",
            "RESOURCE_EXHAUSTED",
            "timed out",
            "Timeout",
        )
    )


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


def run_agent_call(
    settings: Settings,
    prompt: str,
    *,
    span_name: str,
    persona: str,
    tools: tuple[Callable[..., Any], ...] = (),
    response_schema: dict[str, Any] | None = None,
    audio: tuple[bytes, str] | None = None,
    images: list[tuple[bytes, str]] | None = None,
    video: tuple[bytes, str] | None = None,
    instrument: bool = True,
) -> dict[str, Any]:
    """H-1a: THE one instrumented Gemini call site (generalizes B-3's
    run_supervisor_text). Every specialist, the verifier and the synthesis
    step go through here — no agent can skip cost/token/latency metering by
    construction (C-4.4). `persona` lands on the span as gen_ai.agent.name
    so Grafana filters per-specialist cost ("child spans per agent").
    tools = plain Python callables (google-genai automatic function calling);
    response_schema enables typed JSON output (responseMimeType application/json).
    audio = (bytes, mime_type) attaches inline media (e.g. a dub WAV the
    agent must listen to) — same metered call, multimodal contents.
    video = (bytes, mime_type) attaches an inline VIDEO part so temporal
    judges watch the real clip, not stills (ADR-0005)."""
    if span_name.startswith("station."):
        from backend.supervisor.station_agents.base import with_operator_notes

        prompt = with_operator_notes(prompt)
    if instrument:
        instrument_genai()
    from google import genai
    from google.genai import types

    started = time.perf_counter()
    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("gen_ai.system", "gcp.vertex")
        span.set_attribute("gen_ai.request.model", TEXT_MODEL)
        span.set_attribute("gen_ai.agent.name", persona)
        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location="global",
            # Hard bound on any agent call — an unbounded generate_content
            # once stalled 10+ min mid-station (dub audio judgment).
            http_options={"timeout": 300_000},
        )
        config_kwargs: dict[str, Any] = {
            "thinking_config": types.ThinkingConfig(
                thinking_level=THINKING_LEVEL.lower(),  # type: ignore[arg-type]
                include_thoughts=THROUGH_THOUGHTS,
            )
        }
        if tools:
            config_kwargs["tools"] = list(tools)
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema
        contents: Any = prompt
        media_parts: list[Any] = []
        if images:
            for data, mime in images:
                media_parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        if audio is not None:
            data, mime = audio
            media_parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        if video is not None:
            data, mime = video
            media_parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        if media_parts:
            media_parts.append(prompt)
            contents = media_parts
        # Shared resilience: 429/5xx/DEADLINE on generate_content (idempotent).
        response = call_with_resilience(
            lambda: client.models.generate_content(
                model=TEXT_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            ),
            attempts=3,
            is_transient=gemini_transient,
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


def run_supervisor_text(
    settings: Settings, prompt: str, *, instrument: bool = True
) -> dict[str, Any]:
    """One real Gemini text call with token/cost/latency (B-3). Not an HTTP path.
    H-1a: a thin wrapper over the single instrumented call site."""
    return run_agent_call(
        settings,
        prompt,
        span_name="supervisor.generate_content",
        persona="post_supervisor",
        instrument=instrument,
    )
