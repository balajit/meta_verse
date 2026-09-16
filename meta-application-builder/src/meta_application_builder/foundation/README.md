# System Foundation, Governance & Boundary Protocols

## Overview
This phase establishes core security boundaries, tenant isolation policies, OpenBao identity configurations, and multi-service containerization substrates. It enforces zero-trust governance semantics prior to business logic invocation across Experience, Control, and Governance Planes using configurable HTTP sidecar or in-process policy evaluation.

## File Registry & Technical Responsibilities

| File Path | Functional Scope & Implementation Details |
| --- | --- |
| `security_context/claims.py` | Strict Pydantic v2 validation schema for OIDC RS256 JWT claims (`tenant_id`, `sub`, `iss`, `aud`, `roles`, `permissions`). |
| `security_context/identity.py` | Thread/Async context-var safe workload identity extraction, RAII `scope()` context manager, token management, and lifecycle cleanup. |
| `governance_rego/opa_evaluator.py` | Core governance policy engine abstraction supporting dual evaluation modes (`HTTP_SIDECAR` for local/isolated APIs and `IN_PROCESS_WASM` for high-throughput compiler workloads). |
| `governance_rego/tenant_isolation.rego` | Rego rules enforcing tenant namespace isolation (`urn:meta:bcr:provider:{tenant_id}:*`) and strict regex-validated ABAC boundary assertions. |
| `governance_rego/immutability_rules.rego` | Rego evaluation definitions for `FINAL`, `EXTENDABLE`, and `OVERRIDABLE` blueprint attribute tiers. |
| `openbao_config/policy_approle.hcl` | Access Control Lists (ACLs) and AppRole secret lease policies for dynamic credentials and KMS handles. |
| `docker_infra/docker-compose.yml` | Containerized setup for local sidecar Open Policy Agent (OPA v0.62+), OpenBao server (v2.1+), and PostgreSQL 16+. |