from __future__ import annotations

import structlog
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class TelemetryInitializationError(Exception):
    """Raised when OpenTelemetry provider configuration fails."""
    pass


class TelemetryConfig(BaseModel):
    service_name: str = Field(default="meta-application-builder", min_length=1)
    environment: str = Field(default="production", min_length=1)
    enable_console_exporter: bool = True


class OpenTelemetryManager:
    @classmethod
    def initialize(cls, config: TelemetryConfig) -> None:
        try:
            provider = TracerProvider()
            if config.enable_console_exporter:
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)

            meter_provider = MeterProvider()
            metrics.set_meter_provider(meter_provider)

            logger.info("otel_telemetry_initialized", service=config.service_name, env=config.environment)
        except Exception as e:
            logger.error("otel_initialization_failed", error=str(e))
            raise TelemetryInitializationError(f"Failed to initialize OpenTelemetry: {e}") from e