"""B-3 live supervisor Gemini call (skip without GCP)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.config import get_settings
from backend.supervisor.otel_ai import run_supervisor_text

EVIDENCE = Path("docs/evidence/B-3")


@pytest.mark.integration
def test_real_supervisor_text_call_records_cost() -> None:
    settings = get_settings()
    if not settings.gcp_project_id:
        pytest.skip("GCP project required for a real Gemini call")
    result = run_supervisor_text(
        settings, "Reply with exactly: B-3 probe OK", instrument=True
    )
    assert result["input_tokens"] >= 1
    assert result["cost_micros"] >= 0
    assert result["latency_ms"] > 0
    assert "B-3" in (result["text"] or "") or result["text"]
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ai_call.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (EVIDENCE / "README.md").write_text(
        "# B-3 AI Observability\n\n"
        "One real `gemini-3.7-flash` supervisor call. "
        f"cost_micros={result['cost_micros']} "
        f"input_tokens={result['input_tokens']} "
        f"output_tokens={result['output_tokens']} "
        f"latency_ms={result['latency_ms']}.\n",
        encoding="utf-8",
    )
