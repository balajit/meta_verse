# Zero-Modification FastAPI Server Generator
## System Requirements Specification — LLM-Ready Final Requirements

**Document purpose:** Define a complete, implementation-ready requirements contract for an LLM or automated code-synthesis agent that generates a production-grade FastAPI microservice from a unified specification.

**Normative language:**
- **MUST / SHALL** = mandatory.
- **MUST NOT / SHALL NOT** = prohibited.
- **SHOULD** = recommended unless a manifest explicitly defines a different supported behavior.
- **MAY** = optional implementation choice within the stated contract.

---

# 1. Architectural Vision & System Goals

## REQ-001 — Production-Grade Runnable Service

The generator MUST generate a fully runnable, production-grade FastAPI microservice from input specifications containing, as applicable:

- API schemas.
- Database models.
- FSM state definitions.
- Business rules.
- Policy authorization rules.
- Workflow execution definitions.

The generated application MUST execute out-of-the-box without manual source-code modification.

## REQ-002 — Zero-Modification Execution

The generated artifact MUST:

1. Compile successfully.
2. Pass static/type validation.
3. Start successfully.
4. Load configuration successfully.
5. Initialize required application resources successfully.
6. Execute its generated test suite successfully.
7. Require zero post-generation manual source edits.

A generation run MUST be considered unsuccessful if any of these conditions cannot be satisfied.

## REQ-003 — Handwritten-Quality Output

Generated code MUST follow idiomatic Python practices and MUST avoid visibly mechanical or unnecessarily generic structures.

Generated code MUST include, where applicable:

- Context-aware variable and function names.
- Dynamic, context-aware docstrings.
- Explicit type annotations.
- `from __future__ import annotations`.
- Structured logging.
- Clear module boundaries.
- Explicit REST-to-business-layer bindings.
- Explicit business-layer-to-repository bindings.

The generated result SHOULD be maintainable as if it had been authored by an experienced Python engineer.

## REQ-004 — Middle-Layer Architecture

The generated application MUST isolate business behavior from HTTP and persistence concerns.

The architecture MUST place a dedicated execution layer between API routers and repositories:

```text
HTTP Request
    |
    v
Routers
    |
    v
Policies
    |
    v
Business Execution Engine
    |-- Rules
    |-- FSM
    |-- Workflows
    |
    v
Repositories
    |
    v
Database
```

Routes MUST NOT directly perform business-critical database persistence.

## REQ-005 — Operator Extensibility

Operators MUST be able to customize supported workflows, rules, policies, FSM behavior, integrations, and other explicitly exposed extension points without:

- Modifying generated core modules.
- Breaking API contracts.
- Losing customizations on regeneration.

Generated core code MUST therefore be separable from operator-authored extension code.

## REQ-006 — Open-Source Utility Offloading

The generator MUST avoid reimplementing mature parsing, rendering, transformation, formatting, retry, and configuration functionality when the mandated open-source tooling provides the required capability.

The generator MUST use the following tooling responsibilities:

| Capability | Forbidden Homegrown Pattern | Required / Mandated Library | Requirement |
|---|---|---|---|
| DTO generation | Custom AST/string writers | `datamodel-code-generator` | MUST use for complex JSON Schema/OpenAPI/type generation where applicable |
| Coarse templating | String formatting/concatenation | Jinja2 | MUST use modular templates |
| Fine-grained code repair | Regex/string replacement | LibCST | MUST use CST transformations |
| Formatting | Custom indentation/whitespace logic | Ruff and/or Black | MUST use programmatic formatting |
| Resilience/retries | Custom while/try/except retry loops | Tenacity | MUST use for supported retry behavior |
| Configuration | Manual `os.getenv` parsing | `pydantic-settings` | MUST use typed configuration loading |

---

# 2. Input Manifest Contract

## REQ-007 — Unified Manifest

The generator MUST accept a unified JSON or YAML information manifest.

The manifest MUST support representation of:

- API schemas.
- Database models.
- FSM states and transitions.
- Business-rule condition matrices.
- Policy authorization rules.
- Workflow execution steps.
- Entity relationships.
- Operator-configurable generation options.

## REQ-008 — Meta-Schema Validation

Before code generation, the generator MUST validate the manifest against a generator meta-schema represented as JSON Schema.

Invalid manifests MUST fail before code emission.

The validation result MUST identify:

- The invalid location/path.
- The violated constraint.
- A human-readable explanation.
- Whether the failure is fatal.

## REQ-009 — Referential Integrity

The generator MUST validate cross-entity references before code emission.

Examples include:

- FSM triggers referencing nonexistent states.
- Workflows referencing nonexistent steps.
- Rules referencing nonexistent fields.
- Policies referencing nonexistent roles or attributes.
- API operations referencing nonexistent entities.
- Relationships referencing nonexistent models.

Unresolved required references MUST be fatal generation errors.

## REQ-010 — Relationship Resolution

The generator MUST resolve supported entity relationships including:

- 1:1.
- 1:N.
- N:M.

The generator MUST detect circular dependencies before code emission.

Circular references MUST either:

1. Be supported safely using forward references and model rebuilding, or
2. Produce an explicit validation error when the relationship cannot be safely represented.

---

# 3. Generation Pipeline

## REQ-011 — Mandatory Pipeline Stages

The generator MUST implement the following logical stages:

1. Information capture and manifest validation.
2. Coarse-grained code synthesis.
3. Fine-grained CST refactoring and polish.
4. Application factory and lifespan bootstrapping.
5. Route and integration test generation.
6. Artifact bundling and readiness verification.

A stage failure MUST prevent an artifact from being reported as production-ready.

---

## 3.1 Stage 1 — Information Capture & Manifest Validation

### REQ-012 — Stage 1 Inputs

Stage 1 MUST consume the unified JSON/YAML manifest.

### REQ-013 — Stage 1 Validation

Stage 1 MUST:

- Validate against the meta-compiler JSON Schema.
- Verify referential integrity.
- Resolve entity relationships.
- Detect circular dependencies.
- Validate required generation metadata.
- Reject ambiguous or contradictory definitions before emission.

---

## 3.2 Stage 2 — Coarse-Grained Code Synthesis

### REQ-014 — Jinja2 Synthesis

Stage 2 MUST use Jinja2 and modular templates to generate the application.

### REQ-015 — Standard Module Generation

Stage 2 MUST emit distinct modules following the target repository structure defined in this specification.

### REQ-016 — Generated Code Metadata

Generated modules MUST include:

- Context-aware docstrings.
- Type annotations.
- REST bindings.
- Database bindings.
- Appropriate imports.
- Explicit domain behavior boundaries.

---

## 3.3 Stage 3 — Fine-Grained Refactoring & AST/CST Polish

### REQ-017 — LibCST Parsing

Stage 3 MUST parse generated Python modules using LibCST.

### REQ-018 — Import and Variable Cleanup

Stage 3 MUST automatically:

- Remove unused imports.
- Resolve unused generated variables where safely possible.
- Reorder imports into standard-library, third-party, and local groups.
- Inject `from __future__ import annotations` at the head of every generated Python file.

### REQ-019 — Formatting

The generator MUST run generated code through Ruff and/or Black programmatically.

Formatting MUST be deterministic.

---

## 3.4 Stage 4 — Application Factory & Lifespan

### REQ-020 — Application Factory

The generator MUST emit `service/main.py` with a FastAPI application factory:

```python
create_app()
```

### REQ-021 — Async Lifespan

The application MUST use an async lifespan context manager.

The lifespan MUST support:

- Database connection-pool initialization/warm-up.
- Resource initialization.
- Graceful shutdown.
- Database engine disposal.
- External HTTP client cleanup.

### REQ-022 — Middleware

The generated application MUST register the required middleware suite:

- CORS.
- Request-ID tracing.
- Exception handling.
- Structured JSON logging.

Middleware configuration MUST be configurable through the manifest and/or application configuration where supported.

---

## 3.5 Stage 5 — Route & Integration Test Generation

### REQ-023 — Test Framework

The generator MUST produce a complete pytest suite using:

- `pytest`.
- `pytest-asyncio`.
- `httpx.AsyncClient`.

### REQ-024 — Core Endpoint Coverage

Generated tests MUST cover all five core REST endpoint categories:

1. Create.
2. Read.
3. Update.
4. Delete.
5. Search.

### REQ-025 — FSM Tests

Generated tests MUST cover:

- Valid FSM transitions.
- Forbidden transitions.
- Appropriate HTTP rejection behavior, including HTTP 422 and/or HTTP 400 according to the generated contract.

### REQ-026 — Business Rule Tests

Generated tests MUST cover business-rule validation failures and verify HTTP 400 behavior where the contract specifies it.

### REQ-027 — Authorization Tests

Generated tests MUST cover policy authorization failures and verify HTTP 401/403 behavior according to authentication versus authorization failure semantics.

### REQ-028 — Extension Tests

Where operator extensions are present, generated tests MUST verify:

- Extension discovery.
- Extension invocation.
- Override precedence.
- Failure handling.
- Preservation across regeneration.

---

## 3.6 Stage 6 — Artifact Bundling & Readiness Verification

### REQ-029 — Required Artifacts

The generated artifact MUST include, where applicable:

- `pyproject.toml`.
- `Dockerfile`.
- `.env.example`.
- Alembic configuration.
- Migration scripts.
- Application source.
- Tests.

### REQ-030 — Automated Readiness Verification

The generator MUST execute a verification process equivalent to:

```text
uvicorn service.main:app
+
pytest
```

The generated service MUST boot and its tests MUST pass without human intervention before the artifact is marked ready.

### REQ-031 — Verification Failure

If boot, import, configuration, migration, test, or static/type validation fails, the generator MUST:

- Mark generation as failed.
- Preserve actionable diagnostics.
- Identify the failing stage.
- Avoid reporting the artifact as production-ready.

---

# 4. Business Execution Engine

## REQ-032 — Layered Execution Order

The generated execution path MUST support:

```text
Router
  -> Policy
  -> Business Rules
  -> FSM
  -> Workflow
  -> Repository
```

The exact path MAY vary by operation, but authorization MUST occur before protected business operations and repositories MUST remain below the execution layer.

## REQ-033 — Repository Isolation

Repositories MUST be responsible for persistence operations and MUST NOT contain business-rule, authorization, or workflow orchestration logic unless explicitly designated as persistence-specific behavior.

---

# 5. Finite State Machine Engine

## REQ-034 — Typed Async FSM

The generator MUST implement a typed asynchronous FSM pattern.

### REQ-035 — Manifest-Driven States

FSM states and transitions MUST be generated from the manifest.

Example:

```text
DRAFT -> PENDING_APPROVAL -> PUBLISHED
```

### REQ-036 — Explicit Transition Enforcement

The FSM MUST:

- Permit only declared transitions.
- Reject undeclared transitions.
- Raise `InvalidStateTransitionError` or the generated equivalent domain exception.
- Provide deterministic transition behavior.

### REQ-037 — Entry/Exit Hooks

The FSM MUST support explicit:

- Entry hooks.
- Exit hooks.
- Transition hooks where configured.

### REQ-038 — Atomic State Persistence

FSM state updates MUST be bound to the entity database record within an atomic transaction.

A state transition MUST NOT be persisted independently of the business operation that authorizes the transition.

---

# 6. Business Rules Engine

## REQ-039 — Pydantic-Based Rule Evaluation

The rules engine MUST use a Pydantic-based condition/action evaluation model.

### REQ-040 — Rule Sources

The engine MUST support manifest-defined:

- Decision tables.
- Boolean expression trees.
- Preconditions.
- Postconditions.

### REQ-041 — Rule Context

Rule evaluation MUST be able to inspect the request context and all explicitly authorized business context needed by the rule.

### REQ-042 — Exact Rule Violations

Rule failures MUST produce structured errors containing, where available:

- Rule identifier.
- Entity.
- Field/path.
- Expected condition.
- Actual value/context.
- Human-readable violation.
- Machine-readable error code.

The API response MUST expose only information permitted by the security contract.

---

# 7. Workflow Orchestrator

## REQ-043 — Async Step-DAG

The workflow engine MUST support asynchronous step DAGs.

The manifest MUST be able to express:

- Sequential steps.
- Parallel steps.
- Dependencies.
- Conditional steps.
- Failure behavior.
- Compensation handlers.

### REQ-044 — Workflow Execution

The engine MUST support multi-step workflows such as:

```text
Validate Payload
    ->
Reserve Stock
    ->
Charge Account
    ->
Mutate FSM State
```

### REQ-045 — Transactional Failure Handling

Workflow operations that participate in a database transaction MUST execute inside an explicit transaction boundary, such as:

```python
async with session.begin():
    ...
```

If a participating step raises an exception, database changes within that transaction MUST roll back.

### REQ-046 — Compensation

Where external or non-transactional side effects occur, the workflow MUST support compensating steps.

The generator MUST NOT falsely assume that a database rollback can undo an external side effect.

### REQ-047 — Step Failure Semantics

Every workflow step MUST have a defined failure policy:

- Retry.
- Abort.
- Compensate.
- Continue, only when explicitly permitted.
- Escalate.

An unspecified failure policy MUST NOT be guessed by the generator.

### REQ-048 — Parallel Workflow Safety

Parallel steps MUST declare their dependencies and MUST NOT introduce unsafe concurrent mutation of the same transactional entity without an explicit concurrency policy.

---

# 8. Policy Authorization Layer

## REQ-049 — Pre-Operation Authorization

The policy engine MUST act as a pre-operation guard for protected endpoints.

### REQ-050 — RBAC

The policy engine MUST support role-based authorization rules.

### REQ-051 — ABAC

The policy engine MUST support attribute-based authorization rules.

### REQ-052 — Request Attributes

The policy engine MUST be able to inspect authorized:

- Headers/tokens.
- Identity claims.
- Entity attributes.
- Request payload attributes.
- Resource ownership/context.

### REQ-053 — Authorization Ordering

Authorization MUST occur before protected business rules/workflows execute when the policy contract requires pre-operation enforcement.

### REQ-054 — Authentication vs Authorization

The generated service MUST distinguish:

- Unauthenticated requests → HTTP 401 where applicable.
- Authenticated but unauthorized requests → HTTP 403 where applicable.

---

# 9. Operator Extensibility Plane

## REQ-055 — Open-Closed Extension Architecture

Generated core logic MUST reside in a regeneration-controlled area.

Operator-authored extensions MUST reside in a preserved extension area.

The generator MUST NOT overwrite operator-authored extension files during normal regeneration.

## REQ-056 — Extension Interfaces

The generator MUST emit base interfaces equivalent to:

- `AbstractWorkflowHook`.
- `AbstractRuleOverride`.

The extension contract MUST define method signatures, lifecycle, inputs, outputs, error behavior, and execution ordering.

## REQ-057 — Plugin Registry

The generator MUST emit a plugin registry capable of discovering supported operator classes during application startup.

### REQ-058 — Default Fallback

If no extension is registered for an extension point, the system MUST execute the generated default behavior.

### REQ-059 — Override Precedence

When multiple applicable overrides exist, precedence MUST be deterministic.

The system MUST reject ambiguous competing overrides unless the manifest explicitly defines a composition strategy.

### REQ-060 — Extension Validation

Invalid extensions MUST fail clearly during startup or generation validation rather than causing an unexplained runtime failure.

---

# 10. Operator Customization Requirements

The following requirements extend the original operator model so an operator can customize the generated service without editing generated core code.

## REQ-061 — Custom Workflow Insertion

Operators MUST be able to insert custom steps before, after, or between supported workflow steps.

**Use case:** Insert a third-party fraud/risk API call before `OrderRepository.create()`.

Expected behavior:

```text
Validate Order
    ->
Fraud Check [operator extension]
    ->
Create Order
```

If the fraud check fails, the workflow MUST follow its declared failure policy and MUST NOT persist the order when persistence is conditional on fraud approval.

## REQ-062 — Custom Workflow Replacement

Operators MUST be able to replace a generated workflow while preserving its external API contract.

**Use case:** Replace a generated `CreateOrderWorkflow` with a tenant-specific fulfillment workflow.

## REQ-063 — Custom Workflow Step Configuration

Operators MUST be able to configure:

- Step ordering.
- Step enablement.
- Step timeout.
- Retry policy.
- Compensation behavior.
- Conditional execution.

**Use case:** Disable an optional inventory reservation step for digital products.

## REQ-064 — Custom Rule Override

Operators MUST be able to replace or augment generated business rules.

**Use case:** Apply a seasonal 15% discount without changing the database schema or API routes.

## REQ-065 — Rule Composition

Operators MUST be able to specify whether an override:

- Replaces the default.
- Runs before the default.
- Runs after the default.
- Adds an additional validation.
- Adds an additional condition.

The default composition behavior MUST be deterministic.

## REQ-066 — Custom Policy Override

Operators MUST be able to customize endpoint authorization rules.

**Use case:** Permit a regional manager to update orders only within their assigned region.

## REQ-067 — Custom FSM Side Effects

Operators MUST be able to attach behavior to:

- State entry.
- State exit.
- State transition.

**Use case:** Send a Slack notification after `PENDING -> APPROVED`.

Side effects that must occur only after successful persistence MUST execute post-commit.

## REQ-068 — Custom FSM Transition Rules

Operators MUST be able to add permitted transition guards without editing generated FSM core code.

**Use case:** Permit `APPROVED -> PUBLISHED` only when an external compliance check succeeds.

## REQ-069 — Custom API Behavior

Operators MUST be able to customize supported endpoint behavior without modifying generated router core code.

Supported extension points SHOULD include:

- Pre-request hooks.
- Post-request hooks.
- Response transformation hooks.
- Request enrichment hooks.

API contract changes MUST require explicit manifest/schema changes rather than silent extension behavior.

## REQ-070 — Custom Validation

Operators MUST be able to add domain validation that is not expressible through the generated DTO schema.

**Use case:** Reject an order when the customer has exceeded a business-defined daily limit.

## REQ-071 — Custom Repository Behavior

Operators SHOULD be able to provide repository extensions for supported persistence-specific behavior without modifying generated repository base code.

**Use case:** Add a database-specific search optimization or specialized query.

Business rules MUST remain outside repository extensions.

## REQ-072 — External Integration Extensions

Operators MUST be able to register external integrations through defined extension interfaces.

Supported integration configuration MUST include, where relevant:

- Endpoint.
- Authentication reference.
- Timeout.
- Retry policy.
- Circuit/failure behavior.
- Request/response mapping.
- Idempotency behavior.

Secrets MUST NOT be emitted into generated source code.

## REQ-073 — Custom Event/Notification Handlers

Operators MUST be able to attach asynchronous notifications or events to supported lifecycle points.

**Use case:** Publish `OrderApproved` after a successful transaction commit.

## REQ-074 — Custom Configuration

Operators MUST be able to override supported configuration values through environment/configuration rather than generated source modification.

Configuration precedence MUST be deterministic.

## REQ-075 — Tenant/Environment Customization

Where multi-environment or multi-tenant behavior is supported by the manifest, operators MUST be able to customize behavior per environment/tenant without generating divergent core code.

**Use case:** Enable a stricter fraud threshold in production than in development.

## REQ-076 — Feature Flags

The generated system SHOULD support manifest/configuration-driven feature flags for optional workflows, rules, integrations, and endpoint behavior.

A disabled feature MUST NOT leave broken imports or unreachable mandatory dependencies.

## REQ-077 — Extension Compatibility Across Regeneration

Regeneration MUST preserve compatible operator extensions.

If a generated interface changes incompatibly, the generator MUST identify the incompatible extension and report the required migration rather than silently producing a broken application.

---

# 11. Persistence Requirements

## REQ-078 — SQLAlchemy 2.0

Generated persistence code MUST use SQLAlchemy 2.0 async patterns.

### REQ-079 — Async Database Driver

The generated database layer MUST support an async database driver such as `asyncpg` where PostgreSQL is selected.

### REQ-080 — Generic Repository

The generated base repository MUST support the manifest's required CRUD and search operations.

The target repository MUST support soft-delete where enabled.

### REQ-081 — Transaction Ownership

Transaction ownership MUST be explicit.

The system MUST NOT silently open independent transactions that defeat workflow atomicity.

### REQ-082 — Rollback Safety

Database transactions MUST roll back on raised exceptions.

Sessions MUST not be returned to the pool in an invalid transactional state.

---

# 12. Search, Query & Pagination Requirements

## REQ-083 — Dedicated Search DTO

The generator MUST create a dedicated `SearchDTO`.

All search fields MUST be optional and default to `None`.

Example:

```python
class SearchDTO(BaseModel):
    name: str | None = None
    status: str | None = None
```

`SearchDTO` MUST be distinct from `CreateDTO`.

## REQ-084 — Partial Search

Partial search requests MUST NOT fail because create-time fields are non-nullable.

### REQ-085 — Pagination

Search MUST support a deterministic pagination contract where enabled.

The contract MUST define:

- Page/offset or cursor behavior.
- Page size.
- Maximum page size.
- Stable ordering.
- Empty-result behavior.

### REQ-086 — Sorting

If sorting is supported, sort fields MUST be allowlisted.

The system MUST NOT construct unsafe SQL from arbitrary user-provided field names.

### REQ-087 — Filtering

Generated filters MUST be type-aware and MUST reject unsupported fields/operators.

---

# 13. API Contract Requirements

## REQ-088 — Five Core REST Operations

For each applicable entity, the generator MUST support the five core operation categories:

```text
POST   Create
GET    Read
PUT/PATCH Update
DELETE Delete
POST   Search
```

The exact HTTP method/path mapping MUST be explicit in the generated API contract.

## REQ-089 — Request Validation

Invalid request payloads MUST be rejected before business execution.

## REQ-090 — Response Models

Endpoints MUST return typed response DTOs.

The generated service MUST NOT expose ORM objects directly as an uncontrolled API response.

## REQ-091 — Consistent Error Contract

Domain, validation, authorization, persistence, integration, and unexpected errors MUST map to a consistent structured error schema.

---

# 14. Error & Exception Requirements

## REQ-092 — Domain Exception Hierarchy

The generated service MUST define domain-specific exception types.

At minimum, the architecture MUST distinguish:

- Validation failures.
- Invalid FSM transitions.
- Authorization failures.
- Not-found conditions.
- Conflict conditions.
- External dependency failures.
- Transaction failures.
- Unexpected internal failures.

## REQ-093 — Exception Handlers

FastAPI exception handlers MUST convert known domain exceptions into appropriate HTTP responses.

### REQ-094 — No Sensitive Leakage

Error responses MUST NOT expose:

- Secrets.
- Credentials.
- Tokens.
- Database connection strings.
- Internal stack traces in production responses.
- Sensitive authorization context.

Detailed diagnostics MUST remain in controlled logs.

---

# 15. Resilience Requirements

## REQ-095 — Tenacity

Retryable operations MUST use Tenacity rather than custom retry loops.

## REQ-096 — Retry Classification

Only explicitly retryable failures MUST be retried.

The system MUST NOT retry:

- Deterministic validation failures.
- Authorization failures.
- Invalid FSM transitions.
- Non-idempotent operations unless an idempotency mechanism exists.

## REQ-097 — Exponential Backoff

Retry policies MUST support exponential backoff where retries are enabled.

### REQ-098 — Retry Limits

Every retry policy MUST have a bounded maximum attempt count and/or elapsed time.

### REQ-099 — Timeout Requirements

External calls MUST have explicit timeouts.

An absent timeout MUST NOT result in an unbounded wait.

---

# 16. Idempotency & Concurrency Requirements

## REQ-100 — Idempotent Operations

Operations capable of causing externally visible or financially/materially significant side effects SHOULD support idempotency keys where required by the manifest.

**Use case:** A client retries `POST /orders` after a network timeout; the service MUST NOT create two orders when the operation is configured as idempotent.

## REQ-101 — Duplicate Request Handling

The system MUST define behavior for duplicate requests.

### REQ-102 — Concurrent Updates

The system MUST define a concurrency strategy for mutable entities.

Supported strategies MAY include:

- Optimistic locking/version fields.
- Database row locking.
- Serialized workflow execution.

### REQ-103 — Lost Update Prevention

When concurrency control is enabled, stale updates MUST be rejected rather than silently overwriting newer state.

---

# 17. Schema Evolution & Database Migration

## REQ-104 — Migration Generation

Database schema changes MUST produce migration artifacts when migrations are enabled.

### REQ-105 — Migration Determinism

Repeated generation from the same manifest MUST NOT produce uncontrolled duplicate migrations.

### REQ-106 — Breaking Schema Changes

Breaking changes MUST be identified explicitly.

The generator MUST NOT silently destroy or rename persisted data.

### REQ-107 — API Compatibility

When configured for compatibility, schema evolution MUST define backward/forward compatibility expectations.

---

# 18. Configuration & Secrets

## REQ-108 — pydantic-settings

Application configuration MUST use `pydantic-settings`.

### REQ-109 — Startup Configuration Validation

Required configuration MUST be validated during application startup.

Invalid configuration MUST prevent the service from being reported as ready.

### REQ-110 — `.env.example`

The generated artifact MUST include `.env.example` containing configuration keys but MUST NOT contain real secrets.

### REQ-111 — Secret Handling

Secrets MUST be supplied through supported runtime configuration/secret-management mechanisms.

Secrets MUST NOT be:

- Hard-coded.
- Written into generated templates.
- Committed into generated source.
- Printed in logs.

---

# 19. Observability Requirements

## REQ-112 — Structured JSON Logging

Generated services MUST emit structured JSON logs.

### REQ-113 — Request ID

Every request MUST have a request/trace identifier.

An incoming valid identifier SHOULD be propagated; otherwise the service MUST generate one.

### REQ-114 — Correlation

Request IDs/trace IDs MUST be propagated through relevant service and integration calls where supported.

### REQ-115 — Error Logging

Unhandled failures MUST produce structured logs containing sufficient diagnostic context without exposing secrets.

### REQ-116 — Workflow Observability

Workflow execution SHOULD record:

- Workflow identifier.
- Step identifier.
- Start/end timing.
- Outcome.
- Retry count.
- Failure classification.
- Correlation ID.

---

# 20. Health & Readiness

## REQ-117 — Liveness

The generated service SHOULD expose a liveness mechanism that does not require all dependencies to be available.

### REQ-118 — Readiness

The generated service SHOULD expose readiness that reflects required dependency initialization.

### REQ-119 — Startup Failure

If mandatory database/resource initialization fails, the application MUST NOT report itself as ready.

---

# 21. Security Requirements

## REQ-120 — Secure Defaults

Generated applications MUST use secure defaults wherever configuration permits.

### REQ-121 — CORS

CORS MUST be configurable and MUST NOT default to unrestricted production access unless explicitly configured.

### REQ-122 — Input Safety

User-controlled values MUST NOT be interpolated into SQL, shell commands, template source, or generated Python source without appropriate safe handling.

### REQ-123 — Dynamic Query Safety

Database query construction MUST use SQLAlchemy expressions/parameters.

### REQ-124 — Extension Isolation

Operator extensions MUST execute within the same authorization, transaction, logging, and error-handling policies applicable to the operation.

---

# 22. Generated Project Layout

The generator MUST produce a structure equivalent to:

```text
generated_service/
├── .env.example
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── migrations/
│   └── env.py
├── service/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── exceptions.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── dtos.py
│   │   └── db_models.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── fsm.py
│   │   ├── rules.py
│   │   ├── workflows.py
│   │   └── policies.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── base_repository.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── entity_router.py
│   └── extensions/
│       ├── __init__.py
│       ├── hooks.py
│       └── registry.py
└── tests/
    ├── conftest.py
    ├── test_routers.py
    ├── test_fsm.py
    └── test_workflows.py
```

Additional generated modules MAY be added when required by the manifest, but the architectural boundaries MUST remain intact.

---

# 23. Mandatory LLM Guardrails & Edge Cases

## REQ-125 — Python Keyword Name Collisions

Input fields may use Python keywords such as:

```text
type
id
def
from
class
```

The generator MUST produce valid Python.

Pydantic aliases MUST be used where required, for example:

```python
type_: str = Field(alias="type")
```

Database column mappings MUST preserve the external/schema name while using valid Python identifiers internally.

## REQ-126 — Database Rollback After Mid-Workflow Failure

If a workflow performs database writes in steps 1 and 2 and fails at step 3, all writes within the same transaction MUST roll back.

Example:

```text
Step 1 -> DB write
Step 2 -> DB write
Step 3 -> failure
             |
             v
        transaction rollback
```

## REQ-127 — Circular DTO References

All generated Python modules MUST use:

```python
from __future__ import annotations
```

Pydantic forward references MUST be resolved using `model_rebuild()` when required.

## REQ-128 — Lifespan Resource Cleanup

On shutdown, the application MUST explicitly:

```python
await engine.dispose()
```

and close/cleanup HTTP clients and other asynchronous resources.

Background tasks MUST have an explicit shutdown policy.

## REQ-129 — Search DTO Nullability

Search fields MUST be optional and default to `None`.

Search DTOs MUST NOT reuse create DTO requiredness semantics.

---

# 24. Additional LLM Generation Guardrails

## REQ-130 — No Silent Assumptions

If the manifest omits a required behavior, the generator MUST NOT invent domain-specific semantics.

It MUST either:

1. Apply a documented framework default that is explicitly permitted by this specification, or
2. Fail validation with an actionable missing-definition error.

## REQ-131 — Deterministic Generation

The same normalized manifest and generator version MUST produce semantically equivalent output.

Non-deterministic data such as timestamps, random IDs, hostnames, or unordered collection iteration MUST NOT alter generated behavior.

## REQ-132 — Stable Naming

Generated module, class, field, endpoint, constraint, and operation names MUST be deterministic.

Name collisions MUST be detected before emission.

## REQ-133 — Reserved Identifier Handling

The generator MUST handle collisions involving:

- Python keywords.
- Python built-ins.
- Existing module names.
- Duplicate model names.
- Duplicate operation names.
- Duplicate route names.
- Duplicate dependency names.

It MUST produce deterministic safe identifiers.

## REQ-134 — Generated-Code Injection Safety

Manifest values MUST be treated as data.

They MUST NOT be directly concatenated into Python source, SQL, shell commands, or templates in a manner that allows code injection.

## REQ-135 — Dependency Reproducibility

Generated dependency declarations MUST use compatible version constraints.

The generated artifact SHOULD provide a reproducible dependency lock strategy.

## REQ-136 — Import Closure

Every generated import MUST resolve in the packaged artifact.

The readiness verifier MUST detect:

- Missing imports.
- Circular imports that prevent startup.
- Incorrect module paths.
- Missing generated symbols.

## REQ-137 — Empty/Minimal Manifest

The generator MUST define behavior for:

- Empty manifest.
- Manifest with no entities.
- Entity with no fields.
- Entity with no FSM.
- Entity with no rules.
- Entity with no policies.
- Entity with no workflows.

Invalid combinations MUST fail clearly rather than generating unusable code.

## REQ-138 — Maximum/Boundary Inputs

Generated validation MUST honor schema constraints for:

- Empty strings.
- Nulls.
- Maximum lengths.
- Minimum/maximum numeric values.
- Empty arrays.
- Maximum collection sizes.
- Unicode values.
- Boundary dates/times.

## REQ-139 — Time Handling

If date/time fields are generated, the service MUST define timezone semantics.

Naive/aware datetime mixing MUST NOT occur.

## REQ-140 — Partial Update Semantics

If partial updates are supported, omitted fields MUST be distinguishable from fields explicitly set to null where the schema permits null.

## REQ-141 — Delete Semantics

Delete behavior MUST be explicit:

- Hard delete, or
- Soft delete.

If soft delete is configured, normal reads/searches MUST exclude deleted records unless an explicitly authorized operation requests them.

## REQ-142 — Not Found vs Conflict

The generated service MUST distinguish:

- Resource not found.
- Duplicate resource.
- Stale version.
- Invalid state.
- Constraint conflict.

These conditions MUST map to distinct machine-readable error codes.

---

# 25. Workflow Edge Cases

## REQ-143 — Reentrant Workflow Protection

The system MUST define behavior when the same workflow is invoked concurrently for the same entity.

## REQ-144 — Partial External Side Effects

If an external call succeeds but a later database transaction fails, the workflow MUST execute a configured compensation or record the unresolved side effect for recovery.

## REQ-145 — Compensation Failure

If a compensation action itself fails, the workflow MUST:

- Record the failure.
- Preserve correlation information.
- Avoid falsely reporting the workflow as fully rolled back.
- Follow the configured escalation/recovery policy.

## REQ-146 — Parallel Failure

For parallel workflow steps, the workflow MUST define whether:

- Remaining steps are cancelled.
- Already-completed steps are compensated.
- All branches are allowed to finish.
- The workflow enters a partial-failure state.

The generator MUST NOT infer these semantics.

## REQ-147 — Retry + Compensation Interaction

Retries MUST NOT accidentally execute duplicate non-idempotent side effects.

Retry policies and compensation policies MUST be evaluated together.

---

# 26. Operator Lifecycle Requirements

## REQ-148 — Extension Discovery Diagnostics

At startup, the system SHOULD report which extensions were discovered and activated.

It MUST NOT log secret configuration.

## REQ-149 — Extension Disablement

Operators MUST be able to disable an extension through supported configuration without deleting generated core code.

## REQ-150 — Extension Version Compatibility

Extensions SHOULD declare a compatibility version with the generated extension contract.

Incompatible extensions MUST be rejected with an actionable error.

## REQ-151 — Operator Override Auditability

The system SHOULD expose enough metadata to determine which operator override supplied a behavior.

**Use case:** An incident investigator needs to identify which pricing-rule override changed the final discount.

## REQ-152 — Safe Fallback

If an optional extension fails to load, the behavior MUST follow its declared policy:

- Fail startup.
- Disable extension and use default.
- Fail only affected operation.

The generator MUST NOT silently choose among these policies.

---

# 27. Testing Requirements

## REQ-153 — Unit Coverage

Generated tests MUST cover business execution components independently where practical:

- Rules.
- FSM.
- Workflows.
- Policies.
- Repositories.

## REQ-154 — Integration Coverage

Generated tests MUST exercise HTTP → policy → execution engine → repository behavior.

## REQ-155 — Transaction Tests

Tests MUST verify rollback behavior for workflow failures.

## REQ-156 — Extension Tests

Tests MUST verify operator overrides without modifying generated core modules.

## REQ-157 — Edge-Case Tests

Tests SHOULD cover:

- Invalid identifiers.
- Null values.
- Boundary values.
- Duplicate requests.
- Invalid state transitions.
- Authorization failures.
- External dependency failures.
- Retry exhaustion.
- Compensation failure.
- Concurrent update conflicts.
- Search with all fields omitted.

---

# 28. Artifact Integrity

## REQ-158 — Complete Artifact

The output artifact MUST contain everything required to build, run, test, and package the generated service.

## REQ-159 — No Missing Generated Files

The generator MUST verify that all manifest-referenced generated modules exist.

## REQ-160 — No Stale Generated References

Regeneration MUST remove or update stale generated references when the manifest removes an entity or operation, while preserving operator extension code.

## REQ-161 — Core/Extension Boundary

Generated files and operator files MUST have an unambiguous ownership boundary.

The generator MUST NOT overwrite operator-owned files.

---

# 29. Readiness Acceptance Criteria

A generation run is **PASS** only when all applicable conditions below are satisfied:

- [ ] Manifest schema validation passes.
- [ ] Referential integrity passes.
- [ ] Relationship resolution passes.
- [ ] Circular dependency handling passes.
- [ ] Code generation completes.
- [ ] CST parsing succeeds.
- [ ] Imports are valid.
- [ ] Formatting passes.
- [ ] Type/static validation passes.
- [ ] Application factory imports successfully.
- [ ] Configuration validation passes.
- [ ] Database initialization behavior is valid.
- [ ] Required migrations are present.
- [ ] Application starts successfully.
- [ ] Required middleware is registered.
- [ ] Generated tests execute successfully.
- [ ] CRUD tests pass.
- [ ] Search tests pass.
- [ ] FSM tests pass.
- [ ] Rule tests pass.
- [ ] Authorization tests pass.
- [ ] Workflow transaction tests pass.
- [ ] Operator extension tests pass when extensions exist.
- [ ] No required secret is embedded in generated source.
- [ ] Docker/build artifact is structurally valid.
- [ ] No manual source modification is required.

Any mandatory failure MUST result in a failed generation status.

---

# 30. Failure Reporting Contract

Every generator failure MUST identify:

```yaml
generation_status: failed
stage: <pipeline-stage>
error_code: <machine-readable-code>
message: <human-readable-message>
location: <manifest-or-generated-file-location>
severity: fatal | error | warning
suggested_resolution: <actionable-resolution>
```

The generator MUST distinguish validation errors from generation errors and generated-application verification errors.

---

# 31. Original Operator Use Cases — Mandatory Preservation

The following original use cases MUST remain supported.

## Use Case A — External Fraud Check

**Goal:** Insert a third-party risk analysis step into `CreateOrder`.

**Required behavior:**

```text
CreateOrder
  -> custom fraud/risk check
  -> repository persistence
```

If the external check fails, persistence MUST NOT occur when the workflow declares the check as a prerequisite.

## Use Case B — Dynamic Discounting

**Goal:** Apply a seasonal 15% discount.

**Required behavior:**

```text
Request
  -> pricing rule override
  -> FSM transition
  -> persistence
```

The override MUST be possible without modifying the generated database schema or API route.

## Use Case C — FSM Notification

**Goal:** Notify Slack when an entity moves from `PENDING` to `APPROVED`.

**Required behavior:**

```text
PENDING
  -> APPROVED
  -> transaction commits
  -> asynchronous notification
```

The notification MUST NOT be emitted as a successful post-commit event if the transaction ultimately fails.

---

# 32. Operator Customization Use-Case Catalog

The generator SHOULD be evaluated against at least these operator scenarios:

| Use Case | Customization Required |
|---|---|
| Fraud screening | Insert external workflow step |
| Seasonal pricing | Override/compose business rule |
| Regional authorization | Customize ABAC policy |
| Approval notification | Add post-commit FSM hook |
| Compliance gate | Add transition guard |
| Digital product workflow | Disable inventory reservation |
| Custom fulfillment | Replace workflow |
| Customer quota | Add domain validation |
| Search optimization | Extend repository |
| Third-party payment | Add idempotent external integration |
| Tenant behavior | Configure tenant-specific policy |
| Environment behavior | Configure environment-specific behavior |
| Feature rollout | Toggle optional workflow/rule |
| Audit investigation | Identify active override |
| Emergency mitigation | Disable an extension safely |
| Regeneration | Preserve operator customizations |
| API response enrichment | Add response hook |
| External event publication | Publish post-commit event |
| Retry of transient dependency | Configure bounded retry |
| Recovery after external failure | Configure compensation |

---

# 33. Architecture Invariants

The following invariants MUST hold for every generated service:

1. Routers MUST NOT contain business-critical persistence logic.
2. Repositories MUST NOT become the business execution engine.
3. Policies MUST execute before protected operations.
4. FSM transitions MUST be explicit and validated.
5. Business rules MUST be represented independently of route handlers.
6. Workflow orchestration MUST own multi-step execution.
7. Database transactions MUST have explicit boundaries.
8. External side effects MUST NOT be assumed transactional.
9. Operator extensions MUST remain outside regenerated core modules.
10. Generated code MUST remain runnable without manual editing.
11. Search DTOs MUST remain distinct from create DTOs.
12. Secrets MUST remain outside generated source.
13. Dynamic manifest values MUST be treated as data, not executable source.
14. Generation MUST fail rather than silently invent missing domain semantics.
15. Readiness MUST not be reported until mandatory verification succeeds.

---

# 34. Implementation Tooling Requirements

The generator MUST use or integrate with:

- **datamodel-code-generator** for DTO/type generation where applicable.
- **Jinja2** for coarse-grained template rendering.
- **LibCST** for safe fine-grained Python transformations.
- **Ruff and/or Black** for formatting.
- **Tenacity** for supported retry behavior.
- **Pydantic V2** for DTOs and validation.
- **pydantic-settings** for typed configuration.
- **SQLAlchemy 2.0** for ORM/database access.
- **Alembic** for database migrations.
- **FastAPI** for the HTTP application.
- **pytest + pytest-asyncio + httpx.AsyncClient** for generated tests.

The generator MUST NOT replace these mandated capabilities with ad-hoc equivalent implementations unless a documented incompatibility requires an alternative.

---

# 35. Final LLM Generation Directive

The implementing LLM/code-generation agent MUST treat this document as a normative specification.

It MUST:

1. Read and apply every mandatory requirement.
2. Preserve all explicit manifest semantics.
3. Never silently omit a requirement because it is inconvenient to generate.
4. Never silently invent domain semantics.
5. Detect ambiguity and fail with an actionable error when no permitted default exists.
6. Generate production-quality Python.
7. Preserve the generated architectural boundaries.
8. Preserve operator customizations across regeneration.
9. Generate tests for generated behavior.
10. Verify the final artifact before declaring success.
11. Treat all external input as untrusted data.
12. Prefer deterministic, reproducible generation.
13. Handle all explicitly defined edge cases.
14. Apply the stricter rule when two requirements could otherwise create an unsafe implementation.
15. Report every unmet mandatory requirement as a generation failure.

**Definition of Done:**

> A generation run is complete only when the generated FastAPI service is structurally complete, type-safe, bootable, testable, transactionally correct, secure by default, extensible by operators, regenerable without losing operator code, and verified automatically with zero manual source modification.
