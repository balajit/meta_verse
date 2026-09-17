# AGENTS.md — Engineering Guidelines & Execution Instructions

This document provides system instructions for AI coding agents operating within the `meta_compiler` codebase. Adhere to these constraints to minimize context token consumption, eliminate redundant file scans, and maximize first-pass code correctness.

---

## ⚡ Quick Context & Core Stack

* **Domain:** Declarative specification compiler & DAG validator for `meta_builder`.
* **Language & Runtime:** Python 3.11+, AsyncIO.
* **Package Manager:** `uv` (`uv run ...`, `uv add ...`).
* **Core Libraries:** `pydantic` (v2), `jsonschema`, `networkx`, `sf-hamilton`, `sqlalchemy` (v2 async), `asyncpg`, `pyyaml`.

---

## 🛠️ Tooling & Validation Workflows

Before declaring any implementation task complete, run the verification suite in sequence. Do NOT ask the user to run basic linters.

```bash
# 1. Format & Lint (auto-fixable issues)
uv run ruff check --fix .
uv run ruff format .

# 2. Static Type Checks
uv run mypy src/meta_compiler

# 3. Unit & Integration Test Suite
uv run pytest tests/

---

##File & Package Organization

    Subpackages: Use lowercase Snake Case (meta_compiler/guards, meta_compiler/compilers).
    Modules: Name files after their single responsibility (syntax_guard.py, topology_validator.py, db_serializer.py).
    Test Files: Mirror source structure in tests/ with test_ prefixes (tests/guards/test_syntax_guard.py).

---

##Identifiers & Types

    Classes: PascalCase (SyntaxGuard, WorkflowManifestSpec, TopologicalValidator).
    Functions & Methods: snake_case (validate_manifest_syntax, compile_runtime_models).
    Database Tables: meta_ prefix with pluralized snake_case (meta_workflow_definitions, meta_workflow_instances, meta_task_executions).
    Variables & Constants: Use UPPER_CASE for module-level constants (META_SCHEMA_V1_PATH).

---
###Coding Best Practices & Pattern Standards
1. Type Hints & Pydantic V2

    Always use strict typing on all function signatures (def fn(param: dict[str, Any]) -> WorkflowManifestSpec:).
    For dynamic model compilation, leverage Pydantic V2 create_model or static BaseModel schemas with strict ConfigDict(extra="forbid").

2. Async Engine & Persistence

    Database routines in db_serializer.py MUST use SQLAlchemy 2.0 async sessions (AsyncSession).
    Avoid synchronous blocking I/O inside orchestrator paths. Use aiofiles or standard async wrappers if reading large external spec manifests.

3. Error Handling & Structured Exceptions

    Do NOT raise generic Exception or return raw string error messages.
    Define and raise specialized domain exceptions:
        SyntaxValidationError (Step 1 syntax guards)
        ModelCompilationError (Step 2 dynamic model creation)
        CyclicGraphError (Step 3 NetworkX cycle checks)
        ContractValidationError (Step 4 Hamilton output contract checks)
---
###Telemetry, Logging & Observability
    Every compiler module must provide structured runtime execution visibility without inflating context logs.

###Logging Standards

    Use standard logging.getLogger("meta_compiler.<module_name>").

    Log at INFO for step transitions and key outputs (e.g., Workflow definition persisted with ID: {definition_id}).

    Log at DEBUG for internal graph transformations (e.g., topological generation counts, raw node counts).

    Include contextual IDs (namespace, workflow_name, version) in log extra fields or structured strings.

example:
import logging

logger = logging.getLogger("meta_compiler.validators.topology_validator")

def assert_acyclic_topology(graph: nx.DiGraph) -> List[str]:
    logger.debug("Running cycle detection on graph with %d nodes", graph.number_of_nodes())
    if not nx.is_directed_acyclic_graph(graph):
        cycles = list(nx.simple_cycles(graph))
        logger.error("Cyclic dependency detected: %s", cycles)
        raise CyclicGraphError(f"Workflow DAG contains cycles: {cycles}")
    return list(nx.topological_sort(graph))

---

##Token Minimization Strategies for Agents

    Targeted Reading: Use specific offset/line range reads instead of dumping entire files when debugging minor errors.
    Minimal File Rewrites: When using editing tools, edit only the affected function or import blocks rather than replacing entire module contents.
    Concise Verification Output: Run linters with compact reporters (uv run ruff check --output-format=concise).
    No Premature Explanations: Focus on delivering code implementations directly. Omit conversational filler before or after file updates.

---
