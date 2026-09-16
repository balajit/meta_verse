# meta-resiliency

A production-grade Python 3.13+ resilience component library providing decorated policies for retries, circuit breakers, and rate limiting with native OpenTelemetry tracing and structured logging. Integrated with `meta-telemetry`, `meta-config`, and `meta-context`.

---

## Key Features

- **Ecosystem Integration**: Built upon `meta-config`, `meta-telemetry`, and `meta-context` for unified runtime operations.
- **Tenacity Integration**: Battle-tested exponential backoff, jitter, and selective exception retry semantics via `@retry`.
- **Circuit Breaker Pattern**: State-machine-based execution guard (CLOSED, OPEN, HALF_OPEN) preventing downstream cascading failures via `@circuit_breaker`.
- **Sliding-Window Rate Limiter**: High-precision async/sync rate limit enforcement via `@rate_limiter`.
- **Agentic Observability**: Native OpenTelemetry span creation and structured JSON logs enriched with trace and correlation metadata.
- **Strict Immutability**: Type-safe Pydantic configuration models inheriting from `MetaBaseSettings` that fail fast on invalid inputs.

---

## Directory Architecture

```text
meta-resiliency/
├── .gitignore
├── README.md
├── pyproject.toml
├── init_project.py
├── src/
│   └── meta_resiliency/
│       ├── __init__.py
│       ├── py.typed
│       ├── circuit_breaker.py
│       ├── config.py
│       ├── exceptions.py
│       ├── rate_limiter.py
│       ├── retries.py
│       └── telemetry.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_config.py