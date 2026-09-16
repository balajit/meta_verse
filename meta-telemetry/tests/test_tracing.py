import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from meta_telemetry.tracing import get_tracer, trace_span

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)


@pytest.fixture(autouse=True)
def clear_spans():
    exporter.clear()


def test_sync_trace_span_decorator_success():
    def extract_attrs(params: dict) -> dict:
        return {"user.id": params["user_id"]}

    @trace_span(name="SyncTestSpan", extract_attributes=extract_attrs)
    def sample_func(user_id: str, count: int) -> str:
        return f"ok_{count}"

    result = sample_func(user_id="usr_123", count=3)
    assert result == "ok_3"

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "SyncTestSpan"
    assert span.attributes["user.id"] == "usr_123"
    assert "execution.duration_ms" in span.attributes
    assert span.status.is_ok


def test_sync_trace_span_decorator_exception_handling():
    @trace_span(name="ErrorSpan")
    def failing_func():
        raise ValueError("Simulated failure")

    with pytest.raises(ValueError, match="Simulated failure"):
        failing_func()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "ErrorSpan"
    assert not span.status.is_ok
    assert span.status.description == "ValueError: Simulated failure"


@pytest.mark.asyncio
async def test_async_trace_span_decorator_success():
    def extract_attrs(params: dict) -> dict:
        return {"item.name": params["item_name"]}

    @trace_span(name="AsyncTestSpan", extract_attributes=extract_attrs)
    async def async_sample_func(item_name: str) -> bool:
        return True

    result = await async_sample_func(item_name="widget")
    assert result is True

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "AsyncTestSpan"
    assert span.attributes["item.name"] == "widget"
    assert span.status.is_ok


def test_trace_span_handles_extraction_failure_gracefully():
    def broken_extractor(params: dict) -> dict:
        raise RuntimeError("Extractor crashed")

    @trace_span(name="ExtractorErrorSpan", extract_attributes=broken_extractor)
    def func_with_broken_extractor():
        return "completed"

    res = func_with_broken_extractor()
    assert res == "completed"

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "ExtractorErrorSpan"