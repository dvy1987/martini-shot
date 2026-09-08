"""C-4.2 job telemetry: one span, duration + cost + outcome metrics."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import metrics, trace

tracer = trace.get_tracer("pc.stations")
meter = metrics.get_meter("pc.stations")

_duration = meter.create_histogram("pc_job_duration_seconds", unit="s")
_cost = meter.create_histogram("pc_job_cost_micros", unit="1")
_outcome = meter.create_counter("pc_job_outcome_total")
_lufs = meter.create_histogram("pc_loudness_lufs", unit="1")
_flicker = meter.create_histogram("pc_flicker_score", unit="1")
_ai_cost = meter.create_histogram("pc_ai_cost_micros", unit="1")
_ai_tokens = meter.create_counter("pc_ai_tokens_total")


@contextmanager
def job_span(station: str, job_id: str, project_id: str) -> Iterator[object]:
    with tracer.start_as_current_span(f"station.{station}.run") as span:
        span.set_attribute("pc.station", station)
        span.set_attribute("pc.job_id", job_id)
        span.set_attribute("pc.project_id", project_id)
        yield span


def job_metric_labels(station: str, project_id: str | None = None) -> dict[str, str]:
    """PromQL slice: station always; project_id when the dump is known."""
    labels = {"station": station}
    if project_id:
        labels["project_id"] = project_id
    return labels


def record_job(
    station: str,
    *,
    duration_s: float,
    cost_micros: int,
    outcome: str,
    project_id: str | None = None,
) -> None:
    labels = job_metric_labels(station, project_id)
    _duration.record(duration_s, labels)
    _cost.record(float(cost_micros), labels)
    _outcome.add(1, {**labels, "outcome": outcome})


def record_loudness(station: str, lufs: float) -> None:
    _lufs.record(lufs, {"station": station})


def record_flicker(station: str, score: float) -> None:
    _flicker.record(score, {"station": station})


def record_ai_usage(*, input_tokens: int, output_tokens: int, cost_micros: int) -> None:
    _ai_cost.record(float(cost_micros), {"station": "supervisor"})
    _ai_tokens.add(input_tokens, {"direction": "input"})
    _ai_tokens.add(output_tokens, {"direction": "output"})


def timed() -> float:
    return time.perf_counter()


log = logging.getLogger("pc.station")
