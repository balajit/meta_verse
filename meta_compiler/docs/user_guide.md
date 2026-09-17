This guide details how to consume the **Blueprint Component Registry (BCR)** / `meta_compiler` package as an embedded Python library and integrate its multi-stage compilation and persistence capabilities into higher-level applications.

---

## 1. System Architecture & Module Taxonomy

```mermaid
flowchart TD
    A[Raw Manifest YAML / JSON / ManifestIR] --> B[Stage 1: SyntaxGuard]
    B -->|JSON Schema Draft-2020-12| C[Stage 2: ModelCompiler]
    C -->|Dynamic Pydantic & Entity AST| D[Stage 3: TopologyValidator]
    D -->|NetworkX DAG Verification| E[Stage 4: ContractChecker]
    E -->|ActionRegistry + Hamilton Engine| F[CompiledWorkflowDefinition]
    F --> G[Stage 5: DBSerializer & Repository]
    G -->|Asyncpg / SQLAlchemy JSONB| H[(PostgreSQL Database)]

```

### Component Integration Matrix

| Component Module | Class / Function | Primary Responsibility | Input Boundary | Output Artifact |
| --- | --- | --- | --- | --- |
| `meta_compiler.core` | `ActionRegistry` | Thread-safe registry mapping action names to Python callables & boundary models | Action name, Callable, Pydantic schemas | `ActionSpec` |
| `meta_compiler.core` | `ManifestIR` | Immutable domain Intermediate Representation with canonical SHA-256 generation | Dictionaries, raw values | Hashable `ManifestIR` value object |
| `meta_compiler.stages` | `MetaCompiler` | Facade for dynamic Pydantic model synthesis and multi-stage orchestration | Manifest Dict/YAML | `CompiledArtifacts` |
| `meta_compiler.persistence` | `WorkflowRepository` | Asynchronous PostgreSQL storage manager for workflow definitions | DB Payload Dict | Persisted UUID Record |
| `meta_compiler` | `MetaCompilerPipeline` | Application-level orchestrator for host framework embedding | `ManifestIR` / YAML / Dict | `CompiledExecutionGraph` |

---

## 2. In-Memory Action & Domain Model Registry (`meta_compiler.core`)

Provides thread-safe registration for executable functions and schemas, alongside immutable Intermediate Representation (IR) data structures with deterministic canonical hashing (`SHA-256`).

```
+-----------------------------------------------------------------------+
|                         meta_compiler.core                            |
|                                                                       |
|  +--------------------+         registers         +----------------+  |
|  |   ActionRegistry   | ------------------------> |   ActionSpec   |  |
|  +--------------------+                           +----------------+  |
|            ^                                             ^            |
|            | resolves                                    | validates  |
|  +--------------------+      transforms into      +----------------+  |
|  |     ManifestIR     | ------------------------> |   Node/EdgeIR  |  |
|  +--------------------+                           +----------------+  |
+-----------------------------------------------------------------------+

```

### Interfaces & Concrete Payloads

```python
from pydantic import BaseModel
from meta_compiler.core.action_registry import ActionRegistry, ActionSpec
from meta_compiler.core.ir import ManifestIR, NodeIR, EdgeIR


# 1. Define Input/Output Boundary Contracts
class UserIngestInput(BaseModel):
    user_id: str
    raw_payload: dict


class UserIngestOutput(BaseModel):
    user_id: str
    is_valid: bool


# 2. Register Action with Thread-Safe ActionRegistry
registry = ActionRegistry()
registry.register(
    action_name="user_ingest",
    callable_func=lambda payload: {"user_id": payload.user_id, "is_valid": True},
    input_schema=UserIngestInput,
    output_schema=UserIngestOutput,
    version="1.0.0",
)

# 3. Construct Immutable IR with SHA-256 Canonical Hashing
manifest_ir = ManifestIR(
    namespace="production",
    name="user-onboarding",
    version="1.0.0",
    nodes=(NodeIR(id="fetch_data", type="task", attributes={"action": "user_ingest"}),),
    edges=(),
).with_computed_hash()
```

```json
{
  "namespace": "production",
  "name": "user-onboarding",
  "version": "1.0.0",
  "manifest_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "nodes": [
    {
      "id": "fetch_data",
      "type": "task",
      "inputs": [],
      "attributes": { "action": "user_ingest" },
      "disabled": false
    }
  ],
  "edges": [],
  "attributes": {}
}

```

### Operational Assessment

* **Edge Cases:** Attempting to register non-callable objects or passing non-BaseModel subclasses to `input_schema` or `output_schema` immediately raises a `ContractValidationError`. Duplicate registration under the same key without passing `allow_override=True` raises a `ContractValidationError`.
* **Failure Modes:** Hash mismatch occurs if Node/Edge collections are modified without calling `compute_canonical_hash()` again.
* **Performance Trade-offs:** The `ActionRegistry` utilizes an internal `RLock` for thread safety. High-frequency registration loops should pre-register actions at application bootstrap to minimize lock contention during execution.

---

## 3. Standalone Validation & Compilation Engine (`meta_compiler.stages`)

Processes raw manifest inputs through a 4-stage validation pipeline: JSON Schema validation (`Draft202012Validator`), dynamic Pydantic AST model synthesis (`create_model`), NetworkX DAG topology verification, and Apache Hamilton dry-run execution checks.

```mermaid
sequenceDiagram
    autonumber
    participant App as Host Application
    participant SG as SyntaxGuard
    participant MC as ModelCompiler
    participant TV as TopologyValidator
    participant CC as ContractChecker

    App->>SG: validate_manifest_syntax(raw_yaml)
    SG-->>App: Validated Raw Dict
    App->>MC: compile_domain_models(entities)
    MC-->>App: Dynamic Pydantic Classes
    App->>TV: validate_topology(WorkflowManifestSpec)
    TV-->>App: NetworkX Graph & ExecutionPlan
    App->>CC: verify_node_contracts(manifest, plan, registry)
    CC-->>App: Hamilton Dry-Run Verification (True)

```

### Interfaces & Concrete Payloads

```python
from meta_compiler.orchestrator import compile_manifest
from meta_compiler.stages.model_compiler import MetaCompiler

# Standard raw manifest definition
manifest_yaml = """
version: "1.0.0"
namespace: "analytics"
name: "etl-pipeline"
tasks:
  - id: "extract"
    action: "user_ingest"
    outputs:
      - name: "raw_data"
        type: "json"
  - id: "transform"
    action: "user_ingest"
    depends_on: ["extract"]
    inputs:
      - name: "raw_data"
        type: "json"
"""

# Compile in-memory without side effects
compiled_def = compile_manifest(manifest_input=manifest_yaml, registry=registry)

# Optional: Directly compile AST Entities into live Pydantic models
meta_compiler = MetaCompiler()
domain_models = meta_compiler.compile_domain_models(
    {
        "UserRecord": {
            "attributes": {
                "id": {"data_type": "uuid", "nullable": False},
                "email": {"data_type": "string", "nullable": False},
            }
        }
    }
)
```

```json
{
  "manifest_spec": {
    "version": "1.0.0",
    "namespace": "analytics",
    "name": "etl-pipeline",
    "tasks": [
      {
        "id": "extract",
        "action": "user_ingest",
        "depends_on": [],
        "inputs": [],
        "outputs": [{"name": "raw_data", "type": "json"}]
      },
      {
        "id": "transform",
        "action": "user_ingest",
        "depends_on": ["extract"],
        "inputs": [{"name": "raw_data", "type": "json"}],
        "outputs": []
      }
    ]
  },
  "execution_plan": {
    "stages": [["extract"], ["transform"]],
    "topological_order": ["extract", "transform"]
  }
}

```

### Operational Assessment

* **Edge Cases:** Cyclic dependencies in `tasks[].depends_on` trigger a `DAGCompilationError` during NetworkX topological sorting. Disconnected orphan nodes or references to unknown task IDs fail semantic validation.
* **Failure Modes:** Type mismatches between a producer node's output schema and a consumer node's input schema raise `ContractValidationError` during Hamilton dynamic module synthesis.
* **Performance Trade-offs:** In-memory dynamic code generation constructs dynamic Hamilton modules in `sys.modules`. Unused dynamic modules are automatically cleaned up in `finally` blocks to prevent memory leaks during iterative compilation loops.

---

## 4. Transactional Persistence & Repository Integration (`meta_compiler.persistence`)

Handles serialization of compiled artifacts into normalized JSONB structures and manages asynchronous operations against the `meta_workflow_definitions` database table.

```
+------------------------------------------------------------------------+
|                      meta_compiler.persistence                         |
|                                                                        |
|  +--------------------+    to_db_payload()    +---------------------+  |
|  | CompiledDefinition | --------------------> |   JSONB DB Map      |  |
|  +--------------------+                       +---------------------+  |
|                                                          |             |
|                                                          v             |
|  +--------------------+                       +---------------------+  |
|  | PostgreSQL DB      | <==================== |  WorkflowRepository |  |
|  +--------------------+    AsyncSession       +---------------------+  |
+------------------------------------------------------------------------+

```

### Interfaces & Concrete Payloads

```python
from sqlalchemy.ext.asyncio import AsyncSession
from meta_compiler.orchestrator import register_workflow, CompiledWorkflowDefinition


async def persist_compiled_blueprint(
    compiled_def: CompiledWorkflowDefinition, session: AsyncSession
) -> str:
    # Optional pre-commit hook (e.g. drift detection, security boundary checks)
    async def verify_snapshot(pinned_deps: dict) -> None:
        if pinned_deps.get("status") == "deprecated":
            raise ValueError("Cannot persist deprecated component snapshot")

    # Transactional registration pass
    record_uuid = await register_workflow(
        compiled_def=compiled_def, session=session, pre_commit_guard=verify_snapshot
    )
    return str(record_uuid)
```

```json
{
  "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "namespace": "analytics",
  "name": "etl-pipeline",
  "version": "1.0.0",
  "description": null,
  "compiled_manifest": {
    "version": "1.0.0",
    "namespace": "analytics",
    "name": "etl-pipeline",
    "tasks": [...]
  },
  "execution_plan": {
    "stages": [["extract"], ["transform"]],
    "topological_order": ["extract", "transform"]
  }
}

```

### Operational Assessment

* **Edge Cases:** Database disconnects during `AsyncSession.execute()` raise a wrapped `RepositoryError`. Attempting to register payloads without an explicit `id` field triggers automated UUIDv4 generation via `to_db_payload`.
* **Failure Modes:** `pre_commit_guard` failures abort transaction staging before issuing SQL statements to PostgreSQL, preserving transaction boundary integrity.
* **Performance Trade-offs:** Serialization to `JSONB` uses Pydantic `model_dump(mode="json")`. Very large execution graphs with tens of thousands of tasks incur transient memory allocations during payload serialization.

---

## 5. Application Integration & End-to-End Orchestration

Integrates the full pipeline facade (`MetaCompilerPipeline`) into host frameworks like FastAPI, custom web services, CI/CD runners, or task workers.

```mermaid
flowchart LR
    Sub[Host FastAPI / CLI App] -->|Instantiates| Pipe[MetaCompilerPipeline]
    Pipe -->|1. Inject Settings/Config| Cfg[CompilerSettings]
    Pipe -->|2. In-Memory Compile| Comp[compile_manifest]
    Pipe -->|3. Async DB Session| Repo[WorkflowRepository]
    Repo -->|4. Return UUID & Nodes| Graph[CompiledExecutionGraph]

```

### Complete End-to-End Code Integration

```python
import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from meta_compiler.config import CompilerSettings
from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.orchestrator import MetaCompilerPipeline
from meta_compiler.core.models import CompiledExecutionGraph


class BlueprintRegistryService:
    """Higher-level application service embedding BCR as a core dependency."""

    def __init__(self, db_url: str, settings: Optional[CompilerSettings] = None) -> None:
        self.settings = settings or CompilerSettings(
            environment="development", db_connection_url=db_url
        )
        self.pipeline = MetaCompilerPipeline(settings=self.settings)
        self.registry = ActionRegistry()
        self._engine = create_async_engine(db_url, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )
        self._register_default_actions()

    def _register_default_actions(self) -> None:
        """Pre-populates the internal ActionRegistry with application domain tools."""
        self.registry.register(
            action_name="user_ingest",
            callable_func=lambda **kwargs: kwargs,
        )

    async def register_new_manifest(self, raw_yaml_string: str) -> CompiledExecutionGraph:
        """Exposes end-to-end manifest validation, compilation, and storage API."""
        async with self._session_factory() as session:
            async with session.begin():
                compiled_graph: CompiledExecutionGraph = await self.pipeline.compile_and_register(
                    manifest_input=raw_yaml_string, session=session, registry=self.registry
                )
                return compiled_graph

    async def shutdown(self) -> None:
        """Cleans up engine connection pools."""
        await self._engine.dispose()


# Example Usage Drive Loop
async def main() -> None:
    db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/meta_builder"
    service = BlueprintRegistryService(db_url=db_url)

    sample_yaml = """
    version: "1.0.0"
    namespace: "core_platform"
    name: "async_sync_job"
    tasks:
      - id: "step_1"
        action: "user_ingest"
    """

    try:
        result = await service.register_new_manifest(sample_yaml)
        print(f"Registered Graph ID: {result.manifest_id}")
        print(f"Nodes in Execution Plan: {list(result.nodes.keys())}")
    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

### Operational Assessment

* **Edge Cases:** Passing invalid inputs (e.g., non-YAML strings or unsupported types) raises `PipelineCompilationError` with the underlying stage specified in the exception context.
* **Failure Modes:** Runtime environment validation failures (such as missing packaged schema assets or unconfigured production database connection URLs) trigger `ConfigurationError` during service bootstrap.
* **Performance Trade-offs:** Connection pooling with `pool_pre_ping=True` mitigates dropped database connections in cloud environments. For low-latency preview/dry-run APIs, use `pipeline.compile()` directly to skip database overhead entirely.