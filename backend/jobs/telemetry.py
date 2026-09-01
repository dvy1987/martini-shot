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


@contextmanager
def job_span(station: str, job_id: str, project_id: str) -> Iterator[object]:
    with tracer.start_as_current_span(f"station.{station}.run") as span:
        span.set_attribute("pc.station", station)
        span.set_attribute("pc.job_id", job_id)
        span.set_attribute("pc.project_id", project_id)
        yield span


def record_job(
    station: str,
    *,
    duration_s: float,
    cost_micros: int,
    outcome: str,
) -> None:
    labels = {"station": station}
    _duration.record(duration_s, labels)
    _cost.record(float(cost_micros), labels)
    _outcome.add(1, {"station": station, "outcome": outcome})


def timed() -> float:
    return time.perf_counter()


log = logging.getLogger("pc.station")
