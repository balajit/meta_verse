# `meta_compiler` System & User Guide

This guide details the architecture, dynamic compilation rules, topology validation, and persistence contracts for `meta_compiler` within the Application Builder system.

---

## 1. System Overview & Pipeline Architecture

`meta_compiler` converts declarative specification manifests (YAML/JSON) into dynamic runtime Pydantic models, NetworkX execution graphs, and database-persisted IRs.

```
                                  COMPILATION PIPELINE

 ┌──────────────┐     Stage 1     ┌──────────────┐     Stage 2     ┌──────────────┐
 │ Raw Manifest │ ──────────────> │ Syntax Guard │ ──────────────> │    Model     │
 │ (YAML / JSON)│                 │ (JSONSchema) │                 │  Compiler    │
 └──────────────┘                 └──────────────┘                 └──────────────┘
                                                                          │
                                                                          ▼
 ┌──────────────┐     Stage 5     ┌──────────────┐     Stage 4     ┌──────────────┐
 │ PostgreSQL   │ <────────────── │ DB           │ <────────────── │ Dynamic      │
 │ Persistence  │                 │ Serializer   │                 │ Topology     │
 └──────────────┘                 └──────────────┘                 └──────────────┘

```

The compilation process flows sequentially through five distinct stages:

1. **Syntax Guard**: Validates incoming raw YAML/JSON structure against `meta_schema_v1.json`.
2. **Model Compiler**: Synthesizes dynamic Pydantic domain models using runtime metaclasses (`type()`).
3. **Topological Validator**: Constructs NetworkX `DiGraph` structures to detect cycles, isolated nodes, and parallel execution levels.
4. **Contract Checker**: Verifies payload type contracts across node dependencies (Hamilton payload driver integration).
5. **DB Serializer**: Prepares execution graphs and persists binary IR payloads into PostgreSQL via SQLAlchemy `AsyncSession`.

---

## 2. Manifest Specification Format

Manifests define domain entities, attributes, and downstream task dependencies.

```yaml
version: "v1"
namespace: "analytics"
name: "data_ingestion_pipeline"

entities:
  UserRecord:
    attributes:
      id:
        data_type: "integer"
        primary_key: true
      email:
        data_type: "string"
        nullable: false
      user_uuid:
        data_type: "uuid"
        nullable: false

tasks:
  - id: "fetch_source_data"
    action: "ingest_raw_logs"
  - id: "process_user_records"
    action: "transform_records"
    depends_on: ["fetch_source_data"]

```

---

## 3. Dynamic Type Mapping Reference

The Model Compiler converts string descriptors into standard Python types and Pydantic field definitions:

| Manifest Primitive | Python Type | Pydantic / SQLAlchemy Mapping |
| --- | --- | --- |
| `string` | `str` | `Field(...)` / `String` |
| `integer` | `int` | `Field(...)` / `Integer` |
| `float` / `number` | `float` | `Field(...)` / `Float` |
| `boolean` | `bool` | `Field(...)` / `Boolean` |
| `datetime` | `datetime.datetime` | `Field(...)` / `DateTime(timezone=True)` |
| `uuid` | `uuid.UUID` | `Field(...)` / `UUID(as_uuid=True)` |
| `json` / `object` | `dict` | `Field(...)` / `JSONB` |
| `array` | `list` | `Field(...)` / `ARRAY` |

---

## 4. SDK Usage & API Examples

### Dynamic Model & Artifact Synthesis

```python
from pathlib import Path
from meta_compiler.compilers.model_compiler import MetaCompiler
from meta_compiler.contracts.action_registry import ActionRegistry

manifest_yaml = """
version: "v1"
namespace: "core"
name: "identity_pipeline"
entities:
  Account:
    attributes:
      account_id: {data_type: "uuid", primary_key: true}
      balance: {data_type: "float", nullable: false}
tasks:
  - id: "load"
    action: "load_account"
"""

registry = ActionRegistry()
registry.register("load_account", lambda: {"status": "success"})

compiler = MetaCompiler()
artifacts = compiler.compile(manifest_yaml, registry=registry)

# Export generated artifacts to target directory
artifacts.write_to_disk(target_dir=Path("./dist"))

```

### Async Database Orchestration

```python
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from meta_compiler.orchestrator import compile_and_register_manifest

async def persist_manifest(manifest_str: str, db_url: str):
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        # Caller retains transaction boundary ownership
        graph = await compile_and_register_manifest(manifest_str, session)
        await session.commit()
        return graph.manifest_id

# Example execution
# asyncio.run(persist_manifest(manifest_yaml, "postgresql+asyncpg://user:pass@localhost:5432/db"))

```

---

## 5. Pipeline Stage Exception Reference

When debugging, each pipeline stage emits structured exceptions:

| Stage | Module Path | Class Name | Failure Trigger |
| --- | --- | --- | --- |
| **1. Guard** | `meta_compiler.guards.syntax_guard` | `SyntaxValidationError` | Invalid YAML, missing required keys, schema mismatch. |
| **2. Model** | `meta_compiler.compilers.model_compiler` | `ModelCompilationError` | Unsupported data types, invalid primary key configs. |
| **3. Topology** | `meta_compiler.validators.topology_validator` | `TopologyValidationError`<br>

<br>`CyclicGraphError` | Missing node references, circular dependencies in `depends_on`. |
| **4. Contract** | `meta_compiler.contracts.contract_checker` | `ContractValidationError` | Input/output Pydantic payload schema mismatch between nodes. |
| **5. Storage** | `meta_compiler.persistence.db_serializer` | `SerializationError` | DB schema migration failure, connection timeout, duplicate UUID. |

---

## 6. CLI Quick Reference

* **Validate Locally (Dry-Run)**:
```bash
meta-compiler validate -f manifest.yaml

```


* **Compile & Register in PostgreSQL**:
```bash
meta-compiler register -f manifest.yaml --db-url "postgresql+asyncpg://user:pass@localhost:5432/meta_builder"

```



---

## 7. Guidelines for Gemini Assistance

When asking Gemini to generate code or modify manifests for Application Builder:

* Request manifest YAML structures adhering to `version: "v1"` and standard primitive types.
* Ensure code requests involving `compile_and_register_manifest` maintain transaction boundary control (explicit `session.commit()`).
* Ensure dynamic models generated via `MetaCompiler` are tested against input/output boundary schemas registered in `ActionRegistry`.