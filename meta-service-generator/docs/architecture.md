# FastAPI Server Generator — System Architecture Specification

## 1. Architectural Vision & Layering Isolation

`meta_service_generator` produces runnable, zero-modification, production-grade FastAPI microservices from a unified declarative manifest. The generated application enforces explicit middle-layer isolation, preventing HTTP routers from coupling directly to persistence mechanisms or complex business domain decisions.

```text
HTTP Request
    |
    v
+-------------------------------------------------------+
| Routers (FastAPI Endpoints)                           |
+-------------------------------------------------------+
    |
    v
+-------------------------------------------------------+
| Policy Authorization Layer (RBAC / ABAC Guards)       |
+-------------------------------------------------------+
    |
    v
+-------------------------------------------------------+
| Business Execution Engine                             |
|  ├── Business Rules Engine (Pydantic-based AST)       |
|  ├── Finite State Machine (Typed Async Transitions)   |
|  └── Workflow Orchestrator (Async Step DAG)          |
+-------------------------------------------------------+
    |
    v
+-------------------------------------------------------+
| Repository Layer (Generic / Specialized Async Query)  |
+-------------------------------------------------------+
    |
    v
+-------------------------------------------------------+
| Database (SQLAlchemy 2.0 Async Session)               |
+-------------------------------------------------------+

```

### Invariants & Boundaries

1. **Routers**: Validate payloads via DTOs and delegate directly to execution workflows or policy guards. No inline ORM queries or database transactions exist in router endpoints.
2. **Policies**: Pre-evaluate caller credentials, identity claims, roles, and attributes prior to invoking execution workflows.
3. **Execution Engine**: Enforces multi-step orchestration, state machine transitions, and contextual business rules within strict atomic database transaction boundaries.
4. **Repositories**: Encapsulate SQLAlchemy 2.0 async persistence operations (CRUD, pagination, filters, soft delete) without evaluating domain rules or authorization semantics.

---

## 2. Six-Stage Generator Pipeline

The generator process transforms input specifications into executable Python code through a rigid multi-stage pipeline:

```text
[Input Manifest]
       |
       v
+-------------------------------------------------------+
| Stage 1: Manifest Load & Validation                   |
|  ├── JSON Schema draft-2020-12 validation             |
|  └── Cross-entity referential integrity validation     |
+-------------------------------------------------------+
       |
       v
+-------------------------------------------------------+
| Stage 2: Intermediate Representation (IR) Building    |
|  ├── Normalized model building & name sanitization    |
|  └── Relationship graph construction & cycle check    |
+-------------------------------------------------------+
       |
       v
+-------------------------------------------------------+
| Stage 3: Coarse-Grained Code Synthesis                |
|  ├── datamodel-code-generator for complex DTO schemas |
|  └── Jinja2 template rendering for service components |
+-------------------------------------------------------+
       |
       v
+-------------------------------------------------------+
| Stage 4: Fine-Grained AST/CST Refactoring & Polish    |
|  ├── LibCST import ordering & dependency pruning      |
|  ├── Future annotation injection                      |
|  └── Programmatic Ruff / Black formatting             |
+-------------------------------------------------------+
       |
       v
+-------------------------------------------------------+
| Stage 5: Application Lifespan & Test Generation       |
|  ├── Async lifespan factory generation                |
|  └── Route, FSM, Rule, and Workflow pytest suite      |
+-------------------------------------------------------+
       |
       v
+-------------------------------------------------------+
| Stage 6: Automated Verification & Readiness Check     |
|  ├── Dynamic import & boot sanity test                |
|  └── Programmatic pytest execution (httpx AsyncClient)|
+-------------------------------------------------------+
       |
       v
[Runnable Production Service Artifact]

```

### Pipeline Subsystems

* **`manifest/`**: Loads YAML/JSON manifests, checks schemas against `schemas/manifest.schema.json`, and verifies reference boundaries (`references.py`).
* **`ir/`**: Standardizes Python identifiers (e.g., handling collisions with keywords like `type`, `class`, `id`), resolves field mapping aliases, and normalizes DAG representations.
* **`analysis/`**: Analyzes entity relationship networks (1:1, 1:N, N:M), detects circular dependencies, and confirms type compatibility across workflow step contracts.
* **`generation/`**: Orchestrates Jinja2 templates (`templates/`) and combines them with `datamodel-code-generator` output for DTO models.
* **`transforms/`**: Utilizes LibCST to clean up unused imports, insert `from __future__ import annotations`, and apply deterministic Ruff/Black formatting.
* **`verification/`**: Boots the generated service programmatically and executes `pytest` using `httpx.AsyncClient` to confirm zero-post-generation manual edits are required.

---

## 3. Tooling Offloading Matrix

To prevent homegrown maintenance overhead, key operational capabilities are offloaded to standard open-source Python frameworks:

| Responsibility | Offloaded Tooling | Generator Subsystem |
| --- | --- | --- |
| Complex Type/DTO Synthesis | `datamodel-code-generator` | `generation/dto.py` |
| Coarse Component Rendering | `Jinja2` | `generation/renderer.py` |
| AST/CST Refactoring & Pruning | `LibCST` | `transforms/libcst_pipeline.py` |
| Formatting & Quality Checks | `Ruff` / `Black` | `transforms/formatting.py` |
| Exponential Retry & Backoff | `Tenacity` | `templates/execution/workflows.py` |
| Application Settings Loading | `pydantic-settings` | `templates/service/config.py` |
| Persistence & ORM | `SQLAlchemy 2.0 Async` | `templates/repositories/` |
| Migration Management | `Alembic` | `templates/project/alembic/` |

---

## 4. Operator Extensibility Plane

The generator isolates generated boilerplate from operator-authored customizations using an **Open-Closed Architecture**.

```text
generated_service/
├── service/                  <-- Core Area (Overwritten during regeneration)
│   ├── execution/
│   │   ├── fsm.py
│   │   ├── rules.py
│   │   └── workflows.py
│   └── extensions/
│       └── registry.py      <-- Discovers active plugin extensions at boot
└── extensions/               <-- Preserved Area (Never overwritten by generator)
    ├── hooks.py              <-- Operator custom implementations
    └── overrides.py

```

### Extension Contracts

1. **Extension Preservation**: Files residing under the `extensions/` top-level directory are created once during initial generation and preserved across manifest regeneration cycles.
2. **Registry Discovery**: On lifespan startup, `service/extensions/registry.py` inspects `extensions/` for user implementations of abstract base contracts (`AbstractWorkflowHook`, `AbstractRuleOverride`, `AbstractFSMHook`).
3. **Execution Fallback**: If an operator override is registered, the execution engine routes execution through the extension; otherwise, standard manifest defaults execute deterministically.




```
