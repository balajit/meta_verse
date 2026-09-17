"""Integration tests verifying OpenTelemetry tracing and structured JSON logging in meta_polymorph."""

import io
import json
import logging
from typing import Generator
import pytest

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from meta_telemetry import StructuredJsonFormatter
from meta_polymorph import ManifestIR, PolymorphicPipeline, TenantContext


@pytest.fixture(scope="module", autouse=True)
def setup_global_tracer_provider() -> Generator[InMemorySpanExporter, None, None]:
    """Configures a global OpenTelemetry TracerProvider with an in-memory exporter for testing."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter


@pytest.fixture
def telemetry_setup(
        setup_global_tracer_provider: InMemorySpanExporter,
) -> Generator[tuple[InMemorySpanExporter, io.StringIO], None, None]:
    """Prepares clean span memory and attaches a StructuredJsonFormatter stream handler to the pipeline loggers."""
    exporter = setup_global_tracer_provider
    exporter.clear()

    # Capture log output in memory
    log_stream = io.StringIO()
    stream_handler = logging.StreamHandler(log_stream)

    formatter = StructuredJsonFormatter(
        service_name="polymorphic_test_service",
        environment="test",
    )
    stream_handler.setFormatter(formatter)

    # Attach handler to root meta_polymorph logger
    logger = logging.getLogger("meta_polymorph")
    logger.setLevel(logging.INFO)
    logger.addHandler(stream_handler)

    yield exporter, log_stream

    logger.removeHandler(stream_handler)


def test_pipeline_telemetry_and_logging_integration(
        telemetry_setup: tuple[InMemorySpanExporter, io.StringIO],
) -> None:
    """Verifies span propagation, attribute extraction, and structured log trace correlation during IR compilation."""
    exporter, log_stream = telemetry_setup

    context = TenantContext(
        tenant_id="tenant_acme",
        industry_id="fintech",
        global_id="global_v1",
    )
    layers = [
        {
            "version": "1.0.0",
            "namespace": "global_base",
            "description": "Base template",
            "tasks": [{"id": "t1", "action": "ingest"}],
        },
        {
            "name": "acme_pipeline",
            "description": "Acme override",
            "tasks": [{"id": "t1", "action": "ingest_v2"}],
        },
    ]

    # Execute pipeline compilation
    manifest_ir = PolymorphicPipeline.compile_to_ir(context, layers)


    # Assert business correctness
    assert isinstance(manifest_ir, ManifestIR)
    assert manifest_ir.name == "acme_pipeline"
    assert manifest_ir.namespace == "global_base"  # Inherited from layer 0

    # --- 1. Validate OpenTelemetry Spans ---
    finished_spans = exporter.get_finished_spans()
    span_names = [span.name for span in finished_spans]

    assert "PolymorphicPipeline.compile_to_ir" in span_names
    assert "PolymorphicResolver.resolve" in span_names
    assert "DeepMerger.deep_merge" in span_names

    # Inspect pipeline entrypoint span
    pipeline_span = next(
        s for s in finished_spans if s.name == "PolymorphicPipeline.compile_to_ir"
    )
    assert pipeline_span.status.is_ok
    assert pipeline_span.attributes.get("tenant.id") == "tenant_acme"
    assert pipeline_span.attributes.get("tenant.industry_id") == "fintech"
    assert pipeline_span.attributes.get("pipeline.layer_count") == 2
    assert "execution.duration_ms" in pipeline_span.attributes

    # --- 2. Validate Structured JSON Log Output ---
    log_output = log_stream.getvalue().strip().split("\n")
    assert len(log_output) >= 2

    log_entries = [json.loads(line) for line in log_output if line]

    for entry in log_entries:
        # Service & metadata assertions
        assert entry["service"]["name"] == "polymorphic_test_service"
        assert entry["service"]["environment"] == "test"

        # OpenTelemetry Trace context injection assertions
        assert "trace_id" in entry
        assert "span_id" in entry
        assert entry["trace_id"] == f"{pipeline_span.get_span_context().trace_id:032x}"

    # Check compilation start event payload
    start_event = next(
        e for e in log_entries if e.get("extra", {}).get("event_type") == "compilation_start"
    )
    assert start_event["extra"]["tenant_id"] == "tenant_acme"
    assert start_event["extra"]["layer_count"] == 2

    # Check compilation success event payload
    success_event = next(
        e for e in log_entries if e.get("extra", {}).get("event_type") == "compilation_success"
    )
    assert success_event["extra"]["tenant_id"] == "tenant_acme"
    assert "duration_ms" in success_event["extra"]