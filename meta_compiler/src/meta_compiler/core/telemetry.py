"""Telemetry integration for meta_compiler.

Thin adapter over the shared ``meta_telemetry`` package to standardize on a
single telemetry implementation across the meta ecosystem. Provides:

- ``get_tracer`` delegating to ``meta_telemetry.get_tracer``.
- ``setup_telemetry`` as an application-driver-only helper (no import side effects).
- Structured JSON logging formatter pulled from ``meta_telemetry``.

Library modules MUST NOT call ``setup_telemetry``; it is reserved for
application drivers / entrypoints.
"""

import logging

from meta_telemetry import StructuredJsonFormatter
from meta_telemetry import get_tracer as meta_get_tracer
from opentelemetry import trace
from opentelemetry.trace import Tracer

logger = logging.getLogger("meta_compiler.core.telemetry")

_TRACER_NAME = "meta_compiler"


def get_tracer(module_name: str | None = None) -> Tracer:
    """Acquires a tracer instance using the shared meta_telemetry API."""
    name = module_name or _TRACER_NAME
    return meta_get_tracer(name)


def setup_telemetry(
    service_name: str = "meta-compiler",
    otlp_endpoint: str = "localhost:4317",
    insecure: bool = True,
) -> Tracer:
    """Optional driver helper to configure global OpenTelemetry SDK provider and OTLP exporter.

    SHOULD ONLY be invoked by application drivers / entrypoints, NOT library modules.
    """
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)

        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=insecure,
        )

        span_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(span_processor)

        trace.set_tracer_provider(provider)
        logger.info(
            "Configured OpenTelemetry SDK provider targeting '%s' for service '%s'",
            otlp_endpoint,
            service_name,
            extra={
                "event": "telemetry.sdk_configured",
                "endpoint": otlp_endpoint,
                "service": service_name,
            },
        )
    except ImportError as err:
        logger.warning(
            "OpenTelemetry SDK packages not installed; falling back to No-Op tracer: %s",
            err,
            extra={"event": "telemetry.sdk_import_error"},
        )
    except Exception as err:
        logger.error(
            "Failed to initialize OpenTelemetry SDK: %s",
            err,
            extra={"event": "telemetry.setup_failure"},
        )

    return get_tracer(service_name)


JSONFormatter = StructuredJsonFormatter
