# Specification Management & Hybrid Governance Engine

## Overview
Phase 2 builds the three-tier validation engine enforcing structural syntax compliance, RFC-7807 problem details reporting, inheritance immutability rules, topological cycle detection, and low-latency Open Policy Agent (OPA) sidecar policy checking.

## File Registry & Technical Responsibilities

| File Path | Functional Scope & Implementation Details |
| --- | --- |
| `schemas/rfc7807_error.py` | `ProblemDetails` and `ValidationErrorDetail` Pydantic models for RFC-7807 problem detail generation. |
| `schemas/det_schema.py` | `DomainEntityTemplate`, `AttributeDefinition`, and `ImmutabilityTier` schema models defining Domain Entity Templates. |
| `phase_a_static/syntax_checker.py` | `StaticSyntaxChecker` enforcing size limits (2MB), format parsing (JSON/YAML), and Pydantic validation. |
| `phase_a_static/immutability_eval.py` | `ImmutabilityEvaluator` validating child schemas against parent `FINAL`, `EXTENDABLE`, and `OVERRIDABLE` tiers. |
| `phase_b_topology/networkx_dag.py` | `DependencyTopologyEngine` leveraging NetworkX for $O(V+E)$ graph cycle detection and topological build ordering. |
| `phase_c_policy/opa_client.py` | `OPAGovernanceClient` communicating asynchronously with local OPA sidecar endpoints to execute Rego policies. |