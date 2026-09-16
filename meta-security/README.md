# meta-security

`meta-security` provides token validation, claim extraction, and security policy context wrappers for the platform services.

## Architecture & Integration

This library strictly enforces separation of concerns. It validates identity payloads using `pyjwt` and `cryptography` while offloading configuration state to `meta-config`. 

For observability, `meta-security` utilizes `meta-telemetry`. It relies strictly on `opentelemetry-api` for span instrumentation and leaves TracerProvider management to the host application. All security-related logs are enriched with structured JSON formatters to inject OpenTelemetry trace context dynamically.

## Development

We utilize modern Python tooling:
* **Package Management:** `uv`, `hatchling`
* **Static Analysis:** `mypy`, `ruff`, `pylint`
* **Testing:** `pytest`

### Quick Start

1. Run the initialization script (if setting up locally for the first time).
2. Sync dependencies using `uv`.
3. Ensure the host application configures a global `TracerProvider` before invoking `meta-security` modules.