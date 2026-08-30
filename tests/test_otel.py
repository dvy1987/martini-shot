"""A-1 RED tests: core/otel.py — REAL OTLP exporters initialized (plan A-1 DoD:
"test uses real exporter class pointed at staging endpoint — no mock exporters").

The staging endpoint is a loopback URL; exporter construction performs no
network I/O, so these tests are hermetic while asserting the real SDK types.
"""

import pytest
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from backend.core.config import Settings
from backend.core.otel import TelemetryHandle, init_telemetry, shutdown_telemetry

STAGING = "http://127.0.0.1:4318"


def settings_with(endpoint: str) -> Settings:
    return Settings(
        grafana_otlp_endpoint=endpoint,
        grafana_otlp_token="staging-token",
        service_name="backend-test",
    )


@pytest.fixture(autouse=True)
def _teardown() -> object:
    yield None
    shutdown_telemetry()


def test_real_exporter_classes_initialized() -> None:
    handle = init_telemetry(settings_with(STAGING))
    assert isinstance(handle, TelemetryHandle)
    assert handle.enabled is True
    assert isinstance(handle.span_exporter, OTLPSpanExporter)
    assert isinstance(handle.metric_exporter, OTLPMetricExporter)


def test_global_providers_active_and_span_emittable() -> None:
    init_telemetry(settings_with(STAGING))
    provider = trace.get_tracer_provider()
    assert provider is not None
    tracer = trace.get_tracer("test.probe")
    with tracer.start_as_current_span("a1.probe") as span:
        span.set_attribute("test", "red")
    assert metrics.get_meter_provider() is not None


def test_noop_when_endpoint_missing() -> None:
    handle = init_telemetry(Settings())
    assert handle.enabled is False
    assert handle.span_exporter is None


def test_shutdown_clears_handle_and_is_idempotent() -> None:
    first = init_telemetry(settings_with(STAGING))
    shutdown_telemetry()
    second = init_telemetry(settings_with(STAGING))
    assert second is not first
    assert second.enabled is True
    shutdown_telemetry()
    shutdown_telemetry()  # idempotent, no raise
