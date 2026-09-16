# Coding Agent Implementation Specification
## `fastapi_server_generator`

**Document Status:** Implementation Specification  
**Audience:** Autonomous coding agents, software engineers, reviewers, and CI systems  
**Normative Language:** `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative keywords.  
**Source of Truth:** This document translates the FastAPI Server Generator system requirements into an implementation contract. The generator MUST satisfy the source requirements for zero-modification execution, handwritten-quality output, middle-layer business execution, operator extensibility, mandated OSS tooling, generated tests, and readiness verification.

---

# 1. Purpose

`fastapi_server_generator` is a code-generation system that transforms a unified application specification into a complete, runnable, production-grade FastAPI microservice.

The generated service MUST:

- start successfully without manual source edits;
- pass formatting and static validation;
- expose the API described by the manifest;
- enforce business rules, FSM transitions, workflows, and authorization policies;
- use asynchronous SQLAlchemy 2.0 persistence;
- contain generated tests;
- support operator extensions without modifying generated core modules;
- survive regeneration without destroying operator-owned extension code;
- be deterministic for the same normalized input and generator configuration;
- fail generation with actionable diagnostics rather than emitting known-invalid projects.

The generator itself and the generated service are separate products and MUST remain architecturally separated.

---

# 2. Scope

## 2.1 Generator Responsibilities

The generator MUST own:

1. manifest loading;
2. manifest schema validation;
3. semantic/reference validation;
4. normalization;
5. intermediate representation construction;
6. dependency and cycle analysis;
7. code generation;
8. DTO generation through `datamodel-code-generator`;
9. coarse templates through Jinja2;
10. fine-grained transformations through LibCST;
11. formatting through Ruff and/or Black;
12. generated test synthesis;
13. artifact assembly;
14. generated-project verification;
15. deterministic output;
16. generation diagnostics.

## 2.2 Generated-Service Responsibilities

The generated service MUST own:

- FastAPI routing;
- DTO validation;
- application configuration;
- database lifecycle;
- repositories;
- business rules;
- FSM execution;
- workflows;
- authorization policies;
- domain exceptions;
- extension loading;
- observability;
- generated tests.

The generated service MUST NOT depend on private implementation modules of the generator unless an explicit runtime dependency is intentionally part of the architecture.

---

# 3. Repository Structure

The generator repository MUST use a structure similar to:

```text
fastapi_server_generator/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── fastapi_server_generator/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── diagnostics.py
│       ├── exceptions.py
│       │
│       ├── manifest/
│       │   ├── __init__.py
│       │   ├── loader.py
│       │   ├── schema.py
│       │   ├── validator.py
│       │   └── references.py
│       │
│       ├── ir/
│       │   ├── __init__.py
│       │   ├── model.py
│       │   ├── builder.py
│       │   ├── normalizer.py
│       │   ├── names.py
│       │   └── dependencies.py
│       │
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── relationships.py
│       │   ├── cycles.py
│       │   ├── compatibility.py
│       │   └── validation.py
│       │
│       ├── generation/
│       │   ├── __init__.py
│       │   ├── pipeline.py
│       │   ├── context.py
│       │   ├── renderer.py
│       │   ├── dto.py
│       │   ├── artifacts.py
│       │   └── manifest_report.py
│       │
│       ├── templates/
│       │   ├── project/
│       │   ├── service/
│       │   ├── models/
│       │   ├── execution/
│       │   ├── repositories/
│       │   ├── routers/
│       │   ├── extensions/
│       │   └── tests/
│       │
│       ├── transforms/
│       │   ├── __init__.py
│       │   ├── libcst_pipeline.py
│       │   ├── imports.py
│       │   ├── annotations.py
│       │   ├── cleanup.py
│       │   └── formatting.py
│       │
│       ├── verification/
│       │   ├── __init__.py
│       │   ├── imports.py
│       │   ├── syntax.py
│       │   ├── typing.py
│       │   ├── boot.py
│       │   ├── tests.py
│       │   ├── package.py
│       │   └── runner.py
│       │
│       └── extensions/
│           ├── __init__.py
│           └── contracts.py
│
├── schemas/
│   └── manifest.schema.json
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/
│   │   ├── basic_crud/
│   │   ├── crud_search/
│   │   ├── fsm/
│   │   ├── business_rules/
│   │   ├── workflow/
│   │   ├── rbac/
│   │   ├── abac/
│   │   ├── relationships/
│   │   ├── reserved_names/
│   │   ├── circular_models/
│   │   ├── soft_delete/
│   │   ├── optimistic_locking/
│   │   ├── external_integration/
│   │   ├── workflow_override/
│   │   ├── rule_override/
│   │   └── fsm_hook/
│   └── fixtures/
│
├── docs/
│   ├── architecture.md
│   ├── manifest.md
│   ├── extensions.md
│   └── troubleshooting.md
│
└── scripts/
    └── verify_generated_project.py
```

The exact names MAY differ, but responsibilities MUST remain separated.

---

# 4. Architecture

## 4.1 Generator Architecture

The generator MUST implement the following logical pipeline:

```text
Unified JSON/YAML Manifest
          |
          v
+-------------------------+
| Load + Schema Validate  |
+-------------------------+
          |
          v
+-------------------------+
| Semantic Validation     |
| References/Relationships|
| Cycle Detection         |
+-------------------------+
          |
          v
+-------------------------+
| Normalized IR           |
+-------------------------+
          |
          v
+-------------------------+
| Generation Planning     |
+-------------------------+
          |
          +--------------------+
          |                    |
          v                    v
  datamodel-codegen       Jinja2 templates
          |                    |
          +---------+----------+
                    v
             Raw Generated Code
                    |
                    v
             LibCST Transform
                    |
                    v
             Ruff / Black
                    |
                    v
          Generated Test Suite
                    |
                    v
          Artifact Verification
                    |
                    v
             PASS / FAIL
```

## 4.2 Generated-Service Architecture

The generated service MUST follow:

```text
HTTP Request
    |
    v
Router
    |
    v
DTO Validation
    |
    v
Policy Guard
    |
    v
Business Execution Engine
    +--> Rules
    +--> FSM
    +--> Workflow
    |
    v
Repository
    |
    v
Async SQLAlchemy
    |
    v
Database
```

Routes MUST NOT contain direct persistence logic.

The middle layer MUST remain the boundary for business decisions and orchestration.

---

# 5. Module Responsibilities

## 5.1 `manifest`

### `loader.py`

MUST:

- load JSON and YAML;
- reject unsupported formats;
- preserve useful source-location information where possible;
- produce actionable parse errors.

### `schema.py`

MUST expose the canonical manifest schema and schema version.

### `validator.py`

MUST validate:

- required fields;
- types;
- enumerations;
- structural constraints;
- references;
- incompatible combinations.

### `references.py`

MUST resolve references between:

- entities;
- fields;
- relationships;
- endpoints;
- FSM states;
- transitions;
- rules;
- policies;
- workflow steps.

Unknown references MUST fail generation.

---

## 5.2 `ir`

The IR is the canonical normalized representation consumed by all later stages.

No renderer SHOULD need to understand raw JSON/YAML structure.

### `model.py`

Defines typed IR objects.

### `builder.py`

Transforms validated manifest data into IR.

### `normalizer.py`

MUST:

- canonicalize names;
- resolve defaults;
- normalize ordering;
- resolve aliases;
- normalize types;
- normalize relationships;
- normalize endpoint definitions;
- normalize FSM/rule/workflow/policy references.

### `names.py`

MUST provide deterministic safe Python identifiers and external names.

It MUST handle:

- Python keywords;
- invalid identifier characters;
- collisions;
- case differences;
- reserved generated names;
- module/class/function conflicts.

External API/database names MUST be preserved through aliases where required.

---

# 6. IR Design

The IR MUST be explicit, typed, immutable where practical, and deterministic.

A conceptual structure is:

```python
GeneratorIR
├── metadata
├── project
├── entities[]
│   ├── name
│   ├── python_name
│   ├── table_name
│   ├── fields[]
│   ├── relationships[]
│   ├── lifecycle
│   └── operations
├── schemas[]
├── endpoints[]
├── fsm_definitions[]
├── rule_sets[]
├── policy_sets[]
├── workflows[]
├── extensions[]
├── dependencies
└── generation_options
```

## 6.1 Entity IR

An entity MUST contain enough information to generate:

- DB model;
- Create DTO;
- Update DTO;
- Response DTO;
- Search DTO;
- repository;
- router;
- execution-layer bindings;
- tests.

## 6.2 Field IR

A field SHOULD include:

```text
external_name
python_name
db_column_name
type
nullable
required
default
default_factory
constraints
validation
sensitive
indexed
unique
primary_key
foreign_key
```

## 6.3 Relationship IR

Relationships MUST explicitly represent:

- source entity;
- target entity;
- cardinality;
- ownership;
- foreign key;
- nullable relationship;
- cascade behavior;
- loading strategy;
- serialization direction.

The generator MUST detect relationship cycles before emission.

## 6.4 Endpoint IR

Each endpoint MUST contain:

```text
operation
method
path
entity
request_schema
response_schema
status_code
authorization_policy
workflow
idempotency
```

Core CRUD/search operations MUST be representable.

## 6.5 FSM IR

FSM definitions MUST contain:

```text
entity
state_field
states[]
transitions[]
initial_state
entry_hooks
exit_hooks
transition_guards
```

Each transition MUST define:

```text
from_state
trigger
to_state
guards
actions
```

## 6.6 Rule IR

Rules MUST represent:

```text
rule_id
priority
preconditions
conditions
actions
postconditions
failure_code
failure_message
```

The representation MUST support decision tables and boolean expression trees.

## 6.7 Workflow IR

Workflow IR MUST support:

```text
workflow_id
steps[]
dependencies
execution_mode
transaction_boundary
retry_policy
timeout
compensation
```

Steps MUST form a valid DAG.

## 6.8 Policy IR

Policy IR MUST support:

- RBAC;
- ABAC;
- endpoint-level authorization;
- required roles;
- required attributes;
- resource/request comparisons.

---

# 7. Manifest Schema

The canonical manifest MUST be versioned.

Conceptual top-level schema:

```yaml
version: "1"

project:
  name: example_service
  package: service
  python_version: "3.12"

database:
  dialect: postgresql
  driver: asyncpg

entities:
  - name: Order
    table: orders
    fields: []
    relationships: []

api:
  endpoints: []

fsm:
  definitions: []

rules:
  sets: []

policies:
  sets: []

workflows:
  definitions: []

extensions:
  definitions: []

generation:
  output_directory: generated_service
  format: ruff
  strict: true
  verify: true
```

The implementation MUST define a formal JSON Schema in `schemas/manifest.schema.json`.

The schema MUST enforce structural correctness, while semantic validation remains in the manifest validation layer.

## 7.1 Manifest Requirements

The manifest MUST support:

- entities;
- API schemas;
- database models;
- relationships;
- FSM states/transitions;
- business rules;
- policy authorization;
- workflows;
- extension declarations;
- generation options.

The schema MUST reject ambiguous or incomplete constructs where code generation would otherwise require guessing.

## 7.2 Referential Integrity

Examples:

- endpoint entity MUST exist;
- endpoint DTO MUST exist;
- FSM transition states MUST exist;
- workflow step dependencies MUST exist;
- rule references MUST resolve;
- policy references MUST resolve;
- foreign-key targets MUST exist.

---

# 8. Generation Pipeline

## Stage 0 — Configuration

Load generator configuration using typed configuration.

The generator SHOULD use `pydantic-settings` for its own configuration.

Configuration MUST include:

- input manifest;
- output directory;
- verification mode;
- formatting mode;
- Python target;
- overwrite policy;
- extension preservation policy.

---

## Stage 1 — Input Capture

1. Load JSON/YAML.
2. Parse.
3. Attach diagnostics.
4. Validate schema.
5. Stop immediately on fatal schema errors.

No code MUST be emitted from an invalid manifest.

---

## Stage 2 — Semantic Analysis

Perform:

- reference validation;
- relationship resolution;
- circular dependency detection;
- naming analysis;
- endpoint consistency;
- FSM validation;
- workflow DAG validation;
- rule validation;
- policy validation;
- extension compatibility validation.

---

## Stage 3 — IR Construction

Build the normalized IR.

Requirements:

- deterministic ordering;
- explicit defaults;
- no unresolved references;
- no generator templates consuming raw manifest objects;
- stable identifiers.

The IR MUST be serializable for debugging.

---

## Stage 4 — Generation Planning

Before writing files, calculate a generation plan:

```text
GenerationPlan
├── files_to_create
├── files_to_replace
├── files_to_preserve
├── transformations
├── dependencies
└── verification_steps
```

The plan MUST identify operator-owned files before generation begins.

---

## Stage 5 — DTO Generation

Use `datamodel-code-generator`.

The generator MUST NOT implement a competing custom DTO type generator.

DTO generation MUST handle:

- Pydantic V2;
- field validation;
- aliases;
- nested models;
- references;
- circular models;
- optional search fields.

---

## Stage 6 — Jinja2 Coarse Generation

Jinja2 MUST generate structural modules.

Templates MUST remain presentation-oriented.

Business decisions MUST NOT be embedded as opaque template logic.

Generated code MUST include:

- context-aware docstrings;
- explicit types;
- explicit REST bindings;
- explicit DB bindings;
- clear module boundaries.

---

# 9. Generated-Service Contract

The generated service MUST include:

```text
service/
├── main.py
├── config.py
├── database.py
├── exceptions.py
├── models/
├── execution/
├── repositories/
├── routers/
└── extensions/
```

## 9.1 Application Factory

`service/main.py` MUST expose:

```python
def create_app() -> FastAPI:
    ...
```

The generated service MUST support:

```python
app = create_app()
```

## 9.2 Lifespan

Use an async lifespan context manager.

Startup MUST support:

- configuration validation;
- DB pool initialization/warm-up where configured;
- extension registration.

Shutdown MUST:

- dispose the SQLAlchemy engine;
- close HTTP clients;
- stop/await managed background resources.

---

# 10. Business Execution Engine

## 10.1 Rules

The rule engine MUST evaluate conditions before protected operations and return structured validation failures.

Rule errors MUST identify:

- rule;
- field/context;
- expected condition;
- actual value/context;
- machine-readable error code.

## 10.2 FSM

The FSM MUST:

- use typed states;
- validate transitions;
- reject illegal transitions;
- raise `InvalidStateTransitionError`;
- support entry/exit hooks;
- persist state changes atomically.

FSM state mutation MUST NOT bypass the repository/transaction boundary.

## 10.3 Workflows

The workflow engine MUST support:

- sequential steps;
- parallelizable independent steps;
- dependency-aware DAG execution;
- transaction boundaries;
- retry policies;
- timeouts;
- compensation handlers.

If a workflow fails after writes, the relevant transaction MUST roll back where the workflow is transactional.

Use:

```python
async with session.begin():
    ...
```

for transactional database workflows.

## 10.4 Policies

Policies MUST execute before business mutations.

Support:

- RBAC;
- ABAC;
- request/token attributes;
- resource attributes;
- explicit allow/deny decisions.

Unauthorized requests MUST map to appropriate HTTP 401/403 behavior.

---

# 11. Fine-Grained Code Transformation

LibCST MUST be the only fine-grained source transformation mechanism.

Regex-based source rewriting MUST NOT be used for structural Python transformations.

The LibCST pipeline MUST:

1. parse generated modules;
2. ensure `from __future__ import annotations`;
3. normalize imports;
4. remove known unused imports/variables where safe;
5. apply required generated-code repairs;
6. preserve valid comments/docstrings;
7. emit syntactically valid source.

Ruff and/or Black MUST perform final formatting.

---

# 12. Extension Architecture

Generated code MUST follow an Open/Closed extension model.

## 12.1 Ownership

### Generator-owned

```text
service/
├── execution/
├── routers/
├── repositories/
├── models/
└── generated core modules
```

These MAY be regenerated.

### Operator-owned

```text
service/extensions/
```

These MUST survive regeneration.

The generator MUST NOT silently overwrite operator-owned files.

## 12.2 Extension Contracts

Provide explicit interfaces such as:

```python
class WorkflowHook(Protocol):
    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        ...


class RuleOverride(Protocol):
    async def evaluate(self, context: RuleContext) -> RuleResult:
        ...


class FSMHook(Protocol):
    async def on_transition(
        self,
        context: TransitionContext,
    ) -> None:
        ...
```

Exact names MAY evolve, but extension contracts MUST be:

- typed;
- versioned;
- documented;
- discoverable;
- testable.

## 12.3 Registry

The extension registry MUST:

- discover declared extensions;
- validate compatibility;
- register them deterministically;
- support absence of overrides;
- provide generated defaults;
- report duplicate/conflicting extensions;
- prevent invalid extensions from silently changing core behavior.

## 12.4 Extension Precedence

The system MUST define precedence explicitly.

Recommended precedence:

```text
Security / platform invariants
        >
Core transactional invariants
        >
Generated business behavior
        >
Operator extension
```

Extensions MUST NOT bypass:

- authorization invariants;
- transaction invariants;
- required validation;
- data-integrity constraints.

## 12.5 Required Extension Use Cases

The implementation MUST support:

1. External fraud/risk check before persistence.
2. Dynamic pricing/discount rule override.
3. Post-commit FSM transition notification.

For external calls, the implementation SHOULD support explicit timeout and retry policy.

---

# 13. Generated API Requirements

For each CRUD entity, generate:

1. Create;
2. Read;
3. Update;
4. Delete;
5. Search.

Search MUST use a dedicated DTO.

All search fields MUST default to `None` and be optional.

Example:

```python
class EntitySearchDTO(BaseModel):
    name: str | None = None
    status: Status | None = None
```

Search DTOs MUST NOT reuse Create DTOs.

---

# 14. Persistence Requirements

Use:

- SQLAlchemy 2.0;
- async sessions;
- typed `Mapped[...]` models;
- repository abstraction.

Repositories MUST contain persistence operations rather than business decisions.

The generator MUST support:

- primary keys;
- foreign keys;
- relationships;
- uniqueness;
- nullable fields;
- indexes;
- soft delete where configured;
- optimistic concurrency where configured.

Transaction ownership MUST be explicit.

---

# 15. Naming and Edge Cases

The generator MUST handle fields such as:

```text
type
id
def
from
class
```

External names MUST remain available through aliases.

Python-safe internal names MUST be deterministic.

The generator MUST also handle:

- invalid identifier characters;
- duplicate names after normalization;
- case collisions;
- empty manifests;
- circular DTOs;
- nested models;
- null values;
- boundary values;
- Unicode;
- timezone-aware datetimes;
- optional fields;
- partial updates.

Circular models MUST use:

```python
from __future__ import annotations
```

and Pydantic `model_rebuild()` where necessary.

---

# 16. Testing Strategy

Testing is part of generation, not an optional post-processing activity.

## 16.1 Generator Unit Tests

Test:

- manifest loading;
- schema validation;
- reference resolution;
- naming;
- IR construction;
- dependency analysis;
- cycle detection;
- template rendering;
- LibCST transforms;
- generation planning;
- extension discovery.

## 16.2 Generator Integration Tests

For each representative manifest:

```text
manifest
  -> generator
  -> project
  -> syntax check
  -> import check
  -> type check
  -> boot
  -> pytest
```

## 16.3 Generated-Service Tests

Generated tests MUST cover:

- Create;
- Read;
- Update;
- Delete;
- Search;
- invalid input;
- 400/422 validation behavior;
- 401/403 authorization failures;
- valid FSM transitions;
- invalid FSM transitions;
- business-rule failures;
- workflow failures;
- rollback behavior;
- extension behavior.

Use:

- pytest;
- pytest-asyncio;
- httpx.AsyncClient.

---

# 17. Golden-Project Strategy

Golden projects are canonical end-to-end fixtures.

Each golden project MUST contain:

```text
golden_case/
├── input/
│   └── manifest.yaml
├── expected/
│   └── ...
└── metadata.yaml
```

The test harness MUST generate the project rather than manually maintaining generated source as the primary implementation.

## Required Golden Cases

At minimum:

```text
basic_crud
crud_search
fsm
business_rules
workflow
rbac
abac
relationships
reserved_names
circular_models
soft_delete
optimistic_locking
external_integration
workflow_override
rule_override
fsm_hook
```

## Golden Test Contract

Every golden case MUST verify:

1. manifest accepted;
2. expected files generated;
3. operator-owned files preserved;
4. Python syntax valid;
5. imports resolve;
6. static/type validation passes where configured;
7. application boots;
8. generated tests pass;
9. regeneration is deterministic;
10. regeneration does not destroy extensions.

---

# 18. Rules for Modifying Generated Code

The coding agent MUST distinguish between generator source and generated artifacts.

## 18.1 Never Patch Generated Output as a Permanent Fix

If generated code is wrong:

```text
DO NOT:
edit generated_service/service/foo.py
```

Instead identify the correct generator layer:

```text
manifest schema
    |
IR
    |
generation context
    |
Jinja2
    |
LibCST
    |
verification
```

The permanent fix MUST be applied at the earliest correct abstraction layer.

## 18.2 Allowed Generated-Code Modification

Generated source MAY be modified by:

- Jinja2 generation;
- `datamodel-code-generator`;
- LibCST;
- formatting tools.

Manual mutation by the coding agent MUST NOT be treated as part of normal generation.

## 18.3 Extension Code

Operator extension files are different.

The generator MUST preserve them.

An operator MAY manually author:

```text
service/extensions/
```

without requiring generator changes.

## 18.4 Regeneration Safety

Before regeneration:

1. identify generated files;
2. identify operator-owned files;
3. validate extension compatibility;
4. generate into a staging directory;
5. verify;
6. atomically publish where practical.

A failed generation MUST NOT leave the destination in a partially regenerated state.

---

# 19. Dependency and Packaging Rules

The generator MUST produce a complete `pyproject.toml`.

Generated dependencies MUST be explicit and reproducible.

At minimum, the generated service dependency set MUST account for:

- FastAPI;
- Pydantic V2;
- pydantic-settings;
- SQLAlchemy 2.0;
- database driver;
- Alembic;
- pytest;
- pytest-asyncio;
- httpx.

Where retries are generated, use Tenacity.

The generator MUST NOT emit imports for undeclared dependencies.

---

# 20. Verification Pipeline

Verification MUST be executable.

Recommended order:

```text
1. File completeness
2. Python syntax
3. Import resolution
4. Ruff
5. Type checking
6. Application boot
7. Health/readiness validation
8. Generated pytest suite
9. Determinism check
10. Artifact packaging check
```

A generated artifact is READY only if required checks pass.

The generator MUST return structured verification results:

```text
VerificationResult
├── status
├── checks[]
├── diagnostics[]
├── generated_path
└── duration
```

---

# 21. Diagnostics and Failure Handling

Errors MUST be actionable.

A generation failure SHOULD identify:

```text
stage
code
severity
source path
entity
field
message
suggested remediation
```

Examples:

```text
MANIFEST_UNKNOWN_REFERENCE
FSM_UNKNOWN_STATE
WORKFLOW_CYCLE
PYTHON_NAME_COLLISION
UNSUPPORTED_TYPE
EXTENSION_CONFLICT
GENERATION_SYNTAX_ERROR
BOOT_FAILURE
GENERATED_TEST_FAILURE
```

The generator MUST fail closed when correctness cannot be established.

---

# 22. Implementation Phases

## Phase 0 — Repository Bootstrap

Implement:

- package structure;
- CLI skeleton;
- configuration;
- logging;
- exception hierarchy;
- test harness;
- dependency management.

### Definition of Done

- generator package imports;
- CLI executes;
- unit-test framework runs;
- lint/format checks pass;
- no generated-service functionality is implemented yet.

---

## Phase 1 — Manifest and Schema

Implement:

- JSON Schema;
- JSON/YAML loader;
- schema validation;
- diagnostics;
- schema versioning.

### Definition of Done

- valid manifests load;
- invalid manifests fail with actionable errors;
- schema tests pass;
- fixture manifests exist.

---

## Phase 2 — Semantic Validation

Implement:

- references;
- relationships;
- naming;
- cycle detection;
- FSM validation;
- workflow DAG validation;
- policy/rule consistency.

### Definition of Done

- all invalid reference cases fail;
- circular dependencies are detected;
- valid complex manifests produce no false errors;
- all tests pass.

---

## Phase 3 — IR

Implement:

- typed IR;
- builder;
- normalizer;
- deterministic ordering;
- IR serialization/debugging.

### Definition of Done

- a valid manifest produces a complete normalized IR;
- templates no longer consume raw manifest structures;
- IR tests cover representative features.

---

## Phase 4 — Generation Planning and Project Skeleton

Implement:

- generation plan;
- project directories;
- common files;
- configuration;
- database bootstrap;
- application factory;
- exception handling.

### Definition of Done

- basic generated project has the expected structure;
- app imports successfully;
- application factory works.

---

## Phase 5 — DTO and Model Generation

Implement:

- datamodel-code-generator integration;
- Pydantic DTOs;
- SQLAlchemy models;
- aliases;
- circular model handling;
- Search DTOs.

### Definition of Done

- basic CRUD models generate;
- reserved-name fixture passes;
- circular-model fixture passes;
- DTO/model imports succeed.

---

## Phase 6 — Repository and Router Generation

Implement:

- repository interfaces;
- CRUD operations;
- search;
- routers;
- DTO bindings.

### Definition of Done

- five core endpoints generate;
- no direct DB logic exists in routers;
- generated API tests pass.

---

## Phase 7 — Rules Engine

Implement:

- condition evaluator;
- decision tables/boolean trees;
- preconditions;
- postconditions;
- structured violations.

### Definition of Done

- valid rules pass;
- invalid rules fail;
- business-rule golden project passes.

---

## Phase 8 — FSM Engine

Implement:

- typed states;
- transition validation;
- entry/exit hooks;
- persistence binding;
- transition errors.

### Definition of Done

- valid transitions succeed;
- invalid transitions fail;
- transaction behavior is tested;
- FSM golden project passes.

---

## Phase 9 — Workflow Engine

Implement:

- DAG;
- sequential execution;
- parallel-safe execution;
- transactions;
- compensation;
- retries/timeouts.

### Definition of Done

- workflow fixture passes;
- failure rollback is verified;
- compensation is verified;
- no orphaned async resources remain.

---

## Phase 10 — Policy Engine

Implement:

- RBAC;
- ABAC;
- endpoint guards;
- 401/403 handling.

### Definition of Done

- authorized requests pass;
- unauthorized requests fail;
- RBAC and ABAC golden projects pass.

---

## Phase 11 — Extension System

Implement:

- hook contracts;
- registry;
- discovery;
- precedence;
- compatibility;
- preservation.

### Definition of Done

All three mandatory extension use cases pass:

1. fraud check;
2. pricing override;
3. post-commit FSM notification.

Regeneration MUST preserve extension files.

---

## Phase 12 — LibCST and Formatting

Implement:

- CST transformation pipeline;
- future annotations;
- import normalization;
- safe cleanup;
- Ruff/Black integration.

### Definition of Done

- all generated Python parses;
- formatting checks pass;
- transformation tests pass;
- no regex-based Python structural rewrite remains.

---

## Phase 13 — Generated Test Generation

Implement generated tests for:

- CRUD;
- Search;
- FSM;
- rules;
- policies;
- workflows;
- extensions.

### Definition of Done

Every required golden project generates and passes its test suite.

---

## Phase 14 — Verification and Readiness

Implement:

- staging generation;
- syntax/import/type checks;
- application boot;
- test execution;
- deterministic generation checks;
- packaging;
- structured result reporting.

### Definition of Done

A complete golden project can execute:

```text
generate
  -> verify
  -> boot
  -> test
  -> PASS
```

with zero manual edits.

---

## Phase 15 — Hardening

Implement:

- failure atomicity;
- dependency closure;
- reproducibility;
- security defaults;
- observability;
- concurrency safeguards;
- regeneration safety;
- documentation;
- CI.

### Definition of Done

The generator is suitable for production use against the defined acceptance suite.

---

# 23. Phase-Gate Rules

A coding agent MUST NOT proceed to the next phase if the current phase:

- does not compile;
- has failing mandatory tests;
- leaves known TODOs in required behavior;
- introduces undocumented architectural coupling;
- modifies generated artifacts manually instead of fixing generation;
- breaks prior golden projects;
- introduces nondeterministic output;
- leaves verification failures unresolved.

Every phase MUST end with:

```text
Implementation
    ->
Unit Tests
    ->
Integration Tests
    ->
Golden Tests
    ->
Verification
    ->
Documentation
    ->
Phase Acceptance
```

---

# 24. Coding-Agent Operating Rules

The coding agent MUST:

1. Read this entire specification before implementation.
2. Treat normative requirements as binding.
3. Preserve existing architecture unless a requirement necessitates change.
4. Prefer the mandated OSS libraries over custom implementations.
5. Keep generator code separate from generated-service code.
6. Keep business logic out of templates.
7. Use typed interfaces.
8. Add tests with every capability.
9. Add regression tests for every defect.
10. Never silently ignore invalid manifest constructs.
11. Never overwrite operator extensions.
12. Keep generation deterministic.
13. Run verification before declaring completion.
14. Inspect generated output as well as generator source.
15. Treat generated-service failures as generator defects unless the manifest is invalid.
16. Document intentional deviations from this specification.
17. Avoid speculative framework additions without a concrete requirement.
18. Avoid NIH implementations where a mandated library already solves the problem.

---

# 25. Acceptance Criteria

The implementation is accepted only when all of the following are true.

## Input

- JSON and YAML manifests are supported.
- Manifest schema validation works.
- Referential integrity is enforced.
- Invalid relationships and cycles are detected.

## Generation

- Jinja2 performs coarse generation.
- `datamodel-code-generator` performs DTO generation.
- LibCST performs structural source transformations.
- Ruff and/or Black performs formatting.
- `from __future__ import annotations` is present where required.

## Generated Architecture

- Routers do not directly access the DB.
- Business logic is in the execution layer.
- Policies execute before protected mutations.
- FSM transitions are enforced.
- Workflows are explicit and testable.
- Repositories own persistence operations.

## API

- Create exists.
- Read exists.
- Update exists.
- Delete exists.
- Search exists.
- Search uses a dedicated optional-field DTO.

## Persistence

- SQLAlchemy 2.0 async is used.
- Transactions are explicit.
- Failure causes rollback where transactional semantics apply.
- Lifespan disposes resources.

## Security

- RBAC is supported.
- ABAC is supported.
- 401/403 behavior is tested.
- Extensions cannot bypass mandatory security invariants.

## Extensibility

- Operator hooks exist.
- Registry exists.
- Extensions survive regeneration.
- Default generated behavior exists when no override is present.

## Testing

- Generated tests exist.
- Golden projects exist.
- Generated applications boot.
- Generated tests pass.
- Regression tests protect prior behavior.

## Operational Quality

- Structured logging exists.
- Request-ID tracing exists.
- Exception handlers exist.
- Configuration is type-safe.
- Generated artifacts include deployment/package metadata.

## Zero Modification

The strongest acceptance test is:

```text
INPUT MANIFEST
      |
      v
GENERATOR
      |
      v
GENERATED PROJECT
      |
      +--> format
      +--> type check
      +--> import check
      +--> boot
      +--> generated tests
      |
      v
     PASS
```

No manual source modification is permitted between generation and verification.

---

# 26. Definition of Done

The overall product is DONE only when:

1. Every mandatory requirement in this specification is implemented or explicitly documented as intentionally deferred.
2. Every implementation phase has passed its phase gate.
3. All mandatory golden projects pass.
4. Generated projects execute without manual modification.
5. Operator extensions survive regeneration.
6. Generator output is deterministic.
7. Generator failures are actionable.
8. No required capability depends on undocumented behavior.
9. The generated architecture preserves the router → policy → execution → repository boundary.
10. The verification harness can prove readiness automatically.

The coding agent MUST NOT declare the project complete merely because the generator itself passes its tests. It MUST prove that representative generated FastAPI services also pass their own verification suites.

---

# 27. Final Engineering Principle

The generator is not merely a collection of templates.

It is a compiler-like system:

```text
Specification
     |
     v
Validation
     |
     v
Semantic Analysis
     |
     v
Normalized IR
     |
     v
Generation Plan
     |
     v
Code Synthesis
     |
     v
CST Transformation
     |
     v
Formatting
     |
     v
Generated Tests
     |
     v
Verification
     |
     v
Runnable Service
```

The coding agent MUST preserve this separation.

**The central invariant is:**

> A valid specification must produce a valid, runnable, testable service without manual modification, while preserving a stable extension plane for operator-owned behavior.
