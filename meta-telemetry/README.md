# meta-telemetry

Lightweight OpenTelemetry API instrumentation and structured JSON logging utilities for backend microservices and domain components.

## Features

- **Zero SDK Coupling**: Depends exclusively on `opentelemetry-api`. Does not enforce SDK runtime or exporter choices on host applications.
- **Structured JSON Logging**: Provides `StructuredJsonFormatter` to format standard Python logging output as JSON, automatically injecting trace context (`trace_id`, `span_id`).
- **Parametrized Tracing Decorator**: `@trace_span` wraps synchronous and asynchronous functions to automatically manage span creation, dynamic attribute extraction, timing, and error recording.
- **Agentic Triage Ready**: Error formatting captures exception types and contextual key-value pairs designed for automated AI agent log parsing.

## Installation

```bash
uv add meta-telemetry
