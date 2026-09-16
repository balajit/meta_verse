# Experience Plane, REST/gRPC API & CLI Tooling

## Overview
Provides client entry points via HTTP REST endpoints and the `meta-builder` CLI. Supports Direct Mode (in-process) and Remote Mode (API-delegated) execution profiles with complete OpenTelemetry context propagation.

## File Registry & Technical Responsibilities

| File Path | Functional Scope & Implementation Details |
| --- | --- |
| `api_gateway/submit_endpoint.py` | Endpoint handler for `POST /v1/build/submit` with transactional idempotency verification. |
| `api_gateway/validate_endpoint.py` | Endpoint handler for `POST /v1/build/validate` executing dry-run validation passes. |
| `api_gateway/status_endpoint.py` | Endpoint handler for `GET /v1/build/status/{job_id}` and cancellation requests. |
| `api_gateway/artifact_endpoint.py` | Endpoint handler for `GET /v1/build/artifacts/{job_id}` returning CAS pointers and provenance models. |
| `cli_tool/main.py` | CLI entry point parsing command-line parameters, mode flags, and local paths. |
| `cli_tool/direct_mode.py` | Executes builds in-process while strictly retaining local OPA, tenant, and governance checks. |
| `cli_tool/remote_mode.py` | Client transport wrapper delegating commands to the central Application Builder Engine over TLS 1.3. |
| `telemetry/otel_config.py` | Configures OpenTelemetry trace providers, metric exporters, and span context propagation. |
