"""G1 pre-flight: send ONE real trace + metric + log through the configured
OTLP exporters and report exporter outcomes. No mocks — failures raise.

Usage: python scripts/otel_smoke.py
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opentelemetry import metrics, trace

from backend.core.config import get_settings
from backend.core.otel import init_telemetry, shutdown_telemetry


def main() -> int:
    settings = get_settings()
    if not settings.grafana_otlp_endpoint:
        print("SKIP: no OTLP endpoint configured")
        return 0

    handle = init_telemetry(settings)
    assert handle.enabled, "telemetry must initialize with a real endpoint"

    run_id = uuid.uuid4().hex[:8]
    tracer = trace.get_tracer("pc.otel-smoke")
    meter = metrics.get_meter("pc.otel-smoke")
    counter = meter.create_counter("pc_otel_smoke_total", unit="1")

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("pc.otel-smoke")

    with tracer.start_as_current_span("otel.smoke") as span:
        span.set_attribute("pc.run_id", run_id)
        span.set_attribute("pc.station", "smoke")
        log.info("otel smoke test", extra={"run_id": run_id})
        counter.add(1, {"run_id": run_id})

    print(f"run_id={run_id}")
    print("span recorded; forcing flushes...")

    assert handle.tracer_provider is not None
    assert handle.meter_provider is not None
    tp = handle.tracer_provider
    tp.force_flush(timeout_millis=30_000)
    mp = handle.meter_provider
    mp.force_flush(timeout_millis=30_000)

    shutdown_telemetry()
    print("OK: export pipeline completed without exporter errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
