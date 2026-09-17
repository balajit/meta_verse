## Five-Stage Compilation Pipeline

| Stage | Module | Primary Tooling | Responsibilities & Operations |
| :--- | :--- | :--- | :--- |
| **1. Syntax Guard** | `guards/syntax_guard.py` | `jsonschema` | Ingests raw YAML/JSON specs and performs baseline structural checks against Draft 2020-12 meta-schemas before runtime instantiation. |
| **2. Dynamic Model Compiler** | `compilers/model_compiler.py` | `Pydantic V2` | Materializes typed runtime specs (`WorkflowManifestSpec`, `TaskNodeSpec`, `ArtifactRefSpec`) and enforces input/output boundary constraints (`input_ref`, `output_ref`). |
| **3. Topological Validator** | `validators/topology_validator.py` | `NetworkX` | Constructs a `DiGraph` from task dependencies, verifies acyclic integrity (`assert_acyclic_topology`), and calculates topological execution ordering. |
| **4. Payload Contract Checker** | `contracts/contract_checker.py` | `Apache Hamilton` | Builds an in-memory execution graph with `@check_output` hooks to dry-run and verify type compatibility across node boundaries prior to DB commits. |
| **5. Database Serializer** | `persistence/db_serializer.py` | `SQLAlchemy` (`asyncpg`) | Transforms verified graphs into versioned JSONB blobs and handles transactional persistence into `meta_workflow_definitions`. |

---

## 🛠 Function Interface Reference

**Pipeline Orchestrator (`orchestrator.py`)**
* `compile_and_register_manifest(raw_yaml_str: str, session: AsyncSession) -> UUID`: Executes the unified pipeline facade (Parsing $\rightarrow$ Synthesis $\rightarrow$ Topology Validation $\rightarrow$ Contract Verification $\rightarrow$ Persistence).

**Step 1: Syntax Guard (`guards/syntax_guard.py`)**
* `load_meta_schema(schema_path: Path) -> dict`: Loads and caches the static validation schema from disk.
* `validate_manifest_syntax(raw_manifest: dict) -> dict`: Executes structural validation against static meta-schemas, raising `SyntaxValidationError` on failure.

**Step 2: Dynamic Model Compiler (`compilers/model_compiler.py` & `models.py`)**
* `compile_runtime_models(validated_manifest: dict) -> WorkflowManifestSpec`: Materializes dynamic Pydantic specifications from dicts.
* `build_dynamic_artifact_schema(ref_spec: ArtifactRefSpec) -> Type[BaseModel]`: Synthesizes dynamic Pydantic data wrappers for step input/output validation.

**Step 3: Topological Validator (`validators/topology_validator.py`)**
* `build_networkx_graph(manifest: WorkflowManifestSpec) -> nx.DiGraph`: Populates graph nodes and directed edge dependencies.
* `assert_acyclic_topology(graph: nx.DiGraph) -> List[str]`: Asserts graph acyclicity using standard algorithms; raises `CyclicGraphError` if execution loops exist.
* `compute_execution_order(graph: nx.DiGraph) -> List[List[str]]`: Generates topologically sorted parallel execution stages.

**Step 4: Payload Contract Checker (`contracts/contract_checker.py`)**
* `build_hamilton_driver(manifest: WorkflowManifestSpec) -> h_driver.Driver`: Compiles in-memory Hamilton node definitions with output validation hooks.
* `verify_node_contracts(driver: h_driver.Driver, execution_order: List[str]) -> bool`: Dry-runs type checks across edges to ensure upstream output types match downstream expectations[cite: 22].

**Step 5: Database Serializer (`persistence/db_serializer.py`)**
* `to_db_payload(manifest: WorkflowManifestSpec, topo_order: List[List[str]]) -> dict`: Transforms verified models into versioned DB JSONB payloads.
* `persist_workflow_definition(payload: dict, session: AsyncSession) -> UUID`: Performs async transactional inserts into `meta_workflow_definitions` and returns definition identifiers[cite: 15, 20, 22].
