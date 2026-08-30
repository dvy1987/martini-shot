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
from backend.core.otel import (
    TelemetryHandle,
    _signal_endpoints,
    init_telemetry,
    shutdown_telemetry,
)

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


def test_gateway_base_url_gets_signal_paths_appended() -> None:
    """RED for G1: Python OTLP HTTP exporters use the endpoint URL verbatim,
    so a gateway base like https://otlp-gateway-…/otlp must be expanded per
    signal or metrics/logs POSTs 404 (observed live 2026-08-30)."""
    eps = _signal_endpoints("https://otlp-gateway-prod-ap-south-1.grafana.net/otlp")
    assert (
        eps["traces"]
        == "https://otlp-gateway-prod-ap-south-1.grafana.net/otlp/v1/traces"
    )
    assert (
        eps["metrics"]
        == "https://otlp-gateway-prod-ap-south-1.grafana.net/otlp/v1/metrics"
    )
    assert (
        eps["logs"] == "https://otlp-gateway-prod-ap-south-1.grafana.net/otlp/v1/logs"
    )


def test_full_signal_urls_pass_through_unchanged() -> None:
    base = "https://otlp-gateway-prod-ap-south-1.grafana.net/otlp/v1/traces"
    eps = _signal_endpoints(base)
    assert eps["traces"] == base
    assert eps["metrics"] == base
    assert eps["logs"] == base
