# meta-context

A zero-dependency, production-grade Python library for managing asynchronous execution state, correlation IDs, and tenant context across execution boundaries using standard library `contextvars`.

## Features
- **Zero Runtime Dependencies**: Built entirely on Python standard library modules (`contextvars`, `dataclasses`, `logging`, `typing`).
- **Asyncio & Thread Safe**: Context propagation across thread pools, asyncio event loops, and background tasks.
- **Strict Immutability**: Context models use slotted, frozen dataclasses and immutable mapping proxies.
- **Agentic Observability**: Structured JSON logging filters and formatters for automatic log enrichment with context state.

## Installation

```bash
uv pip install -e .
