"""OTel telemetry init (C-4.1): traces, metrics, and logs exported via real
OTLP HTTP exporters to the Grafana Cloud endpoints configured in the env.
No mock exporters anywhere — when no endpoint is configured this module
no-ops (local unit runs), it never fakes telemetry.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from backend.core.config import Settings

log = logging.getLogger(__name__)


@dataclass
class TelemetryHandle:
    """Owns the initialized exporters/providers; enabled=False means no-op."""

    enabled: bool
    span_exporter: OTLPSpanExporter | None = None
    metric_exporter: OTLPMetricExporter | None = None
    log_handler: logging.Handler | None = None
    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None


_handle: TelemetryHandle | None = None


def _signal_endpoints(base: str) -> dict[str, str]:
    """Python OTLP HTTP exporters POST to the endpoint URL verbatim (no path
    appending), so a Grafana gateway base …/otlp must be expanded per signal;
    observed live: metrics/logs 404 when given the bare base (G1, 2026-08-30)."""
    base = base.rstrip("/")
    if base.endswith("/otlp"):
        return {
            "traces": f"{base}/v1/traces",
            "metrics": f"{base}/v1/metrics",
            "logs": f"{base}/v1/logs",
        }
    return {"traces": base, "metrics": base, "logs": base}


def _auth_headers(token: str) -> dict[str, str] | None:
    """Accept every Grafana Cloud credential shape the owner can paste:
    the portal template `base64(<instanceId>:<token>)`, the standard OTLP
    env header `Authorization=Basic <b64>` (optionally URL-encoded space),
    or a raw cloud-access-policy token (Bearer). No manual base64 math."""
    if not token:
        return None
    if token.startswith("base64(") and token.endswith(")"):
        inner = token[len("base64(") : -1]
        blob = base64.b64encode(inner.encode()).decode()
        return {"Authorization": f"Basic {blob}"}
    for prefix in ("Authorization=Basic%20", "Authorization=Basic ", "Basic "):
        if token.startswith(prefix):
            return {"Authorization": f"Basic {token[len(prefix) :]}"}
    return {"Authorization": f"Bearer {token}"}


def init_telemetry(settings: Settings) -> TelemetryHandle:
    """Initialize OTLP traces/metrics/logs once per process (idempotent)."""
    global _handle
    if _handle is not None:
        return _handle
    if not settings.grafana_otlp_endpoint:
        _handle = TelemetryHandle(enabled=False)
        return _handle

    endpoints = _signal_endpoints(settings.grafana_otlp_endpoint)
    headers = _auth_headers(settings.grafana_otlp_token)
    resource = Resource.create({"service.name": settings.service_name})

    span_exporter = OTLPSpanExporter(endpoint=endpoints["traces"], headers=headers)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_exporter = OTLPMetricExporter(endpoint=endpoints["metrics"], headers=headers)
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                metric_exporter, export_interval_millis=60_000
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    log_handler: logging.Handler | None = None
    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import (
            OTLPLogExporter,
        )
        from opentelemetry.sdk._logs import (
            LoggerProvider,
            LoggingHandler,
        )
        from opentelemetry.sdk._logs.export import (
            BatchLogRecordProcessor,
        )

        log_exporter = OTLPLogExporter(endpoint=endpoints["logs"], headers=headers)
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        log_handler = LoggingHandler(
            level=logging.INFO, logger_provider=logger_provider
        )
        logging.getLogger().addHandler(log_handler)
    except ImportError:  # logs SDK layout shifted across OTel 1.39-1.42
        log.warning("OTLP log exporter unavailable; traces and metrics remain active")

    _handle = TelemetryHandle(
        enabled=True,
        span_exporter=span_exporter,
        metric_exporter=metric_exporter,
        log_handler=log_handler,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    log.info(
        "telemetry initialized",
        extra={
            "endpoint": settings.grafana_otlp_endpoint,
            "service": settings.service_name,
        },
    )
    return _handle


def shutdown_telemetry() -> None:
    """Flush and release providers; idempotent. Global OTel API providers stay
    registered (API limitation) but their exporters are shut down."""
    global _handle
    handle, _handle = _handle, None
    if handle is None:
        return
    if handle.log_handler is not None:
        logging.getLogger().removeHandler(handle.log_handler)
    if handle.tracer_provider is not None:
        handle.tracer_provider.shutdown()
    if handle.meter_provider is not None:
        handle.meter_provider.shutdown()
