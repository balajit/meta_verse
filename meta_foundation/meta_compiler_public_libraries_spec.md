# Public Custom Libraries Specification Summary

## Library: `meta_compiler`

### File: `scripts/run_ucp_driver.py`

#### Top-Level Functions

```python
def configure_logging() -> None
```
```python
def register_ucp_action_handlers(compiler: MetaCompiler) -> None
```
```python
def build_sample_ucp_manifest() -> str
```
```python
def demo_in_memory_path_aware() -> None
```
> Demonstrate embedded-host usage: JSON + path supplied together.

```python
async def run(schema_dir: Path) -> tuple[CompiledExecutionGraph, MetaCompiler]
```
```python
def write_artifacts(graph: CompiledExecutionGraph, out_dir: Path) -> list[Path]
```
```python
async def main() -> None
```
### File: `src/meta_compiler/cli.py`

#### Top-Level Functions

```python
def build_cli_parser(default_db_url: str | None = None) -> argparse.ArgumentParser
```
> Constructs the command-line argument parser with subcommands.

```python
def run_dry_run_validation(manifest_path: Path, settings_override: CompilerSettings | None = None) -> bool
```
> Executes stages 1 through 4 of the pipeline locally without requiring database access.

```python
async def run_registration(manifest_path: Path, db_url: str, settings_override: CompilerSettings | None = None) -> str | None
```
> Executes the complete 5-stage orchestration pipeline using an async SQLAlchemy session.

```python
def bootstrap() -> CompilerSettings
```
> Application bootstrap routine verifying runtime integrity before starting engine.

```python
def main() -> None
```
> CLI application main entry point.

### File: `src/meta_compiler/config.py`

#### Classes & Models

```python
class CompilerSettings(MetaBaseSettings):
```
> Compiler environment configurations with fail-fast boot validation.

Instantiation performs Pydantic validation (fail-fast) followed by runtime
asset validation (schema path existence, environment-specific rules) via
:meth:`model_post_init`. A host application therefore cannot construct a
:class:`MetaCompiler` with an invalid runtime configuration.

**Fields / Attributes:**
- `environment: Literal['development', 'test', 'production'] = Field(default='development', description='Execution environment stage.')`
- `db_connection_url: SecretStr | None = Field(default=None, description='Database connection string with credential masking. No default is embedded; must be provided explicitly in all environments.')`
- `schema_path: Path | None = Field(default=None, description='Path override for JSON schema asset. Resolves to package resource if None.')`
- `debug: bool = Field(default=False, description='Enable verbosity for compiler execution.')`

**Methods:**
```python
def model_post_init(self, __context: Any) -> None
```
> Runs runtime asset/config validation immediately after Pydantic validation.

The ``test`` environment is exempt so suites can remain hermetic; every
other environment halts the boot sequence on missing or malformed config.

```python
def get_db_url_string(self) -> str | None
```
> Safely extracts the raw database connection URL string.

```python
def get_resolved_schema_path(self) -> Path
```
> Resolves schema path using explicit configuration or package resources safely.

```python
def validate_runtime(self) -> 'CompilerSettings'
```
> Validates environment-specific rules and mandatory runtime assets.

### File: `src/meta_compiler/core/action_registry.py`

#### Classes & Models

```python
class ActionSpec:
```
> Executable metadata definition associated with a manifest action identifier.

**Fields / Attributes:**
- `action_name: str`
- `callable_func: Callable[..., Any]`
- `input_schema: type[BaseModel] | None = None`
- `output_schema: type[BaseModel] | None = None`
- `version: str = '1.0.0'`

```python
class ActionRegistry:
```
> Thread-safe registry mapping action identifiers to callables and schema contracts.

**Methods:**
```python
def __init__(self) -> None
```
```python
def register(self, action_name: str, callable_func: Callable[..., Any], input_schema: type[BaseModel] | None = None, output_schema: type[BaseModel] | None = None, version: str = '1.0.0', allow_override: bool = False) -> ActionSpec
```
> Registers an executable unit and its boundary schemas under an action key.

Args:
    action_name: Canonical string identifier for the action.
    callable_func: Executable callable object.
    input_schema: Optional Pydantic BaseModel class for input validation.
    output_schema: Optional Pydantic BaseModel class for output validation.
    version: Semantic version string for the action definition.
    allow_override: If False, raises ContractValidationError when re-registering an existing key.

Returns:
    The created and registered ActionSpec instance.

```python
def resolve(self, action_name: str) -> ActionSpec
```
> Resolves an action string to its ActionSpec or raises ContractValidationError.

```python
def has_action(self, action_name: str) -> bool
```
> Checks if an action key is registered.

```python
def unregister(self, action_name: str) -> bool
```
> Removes an action from the registry if present.

```python
def clear(self) -> None
```
> Clears all registered actions (primarily for test isolation).

```python
def list_actions(self) -> list[str]
```
> Returns a list of all registered action names.

### File: `src/meta_compiler/core/context.py`

#### Classes & Models

```python
class CompilationContext:
```
> Carries state, raw schemas, dynamic models, execution plans, and flags across stages.

**Fields / Attributes:**
- `raw_input: Any`
- `context_id: UUID = field(default_factory=uuid4)`
- `record_id: UUID | None = None`
- `manifest_spec: WorkflowManifestSpec | None = None`
- `execution_plan: ExecutionPlan | None = None`
- `raw_schemas: dict[str, dict] = field(default_factory=dict)`
- `schema_dir: Path | None = None`
- `schema_file_index: dict[str, Path] = field(default_factory=dict)`
- `db_payload: dict[str, Any] = field(default_factory=dict)`
- `compiled_models: dict[str, type[BaseModel]] = field(default_factory=dict)`
- `registry: ActionRegistry = field(default_factory=ActionRegistry)`
- `metadata: dict[str, Any] = field(default_factory=dict)`
- `diagnostics: list[Any] = field(default_factory=list)`
- `requires_reprocessing: bool = False`
- `reprocess_counter: int = 0`
- `max_reprocess_attempts: int = 3`

**Methods:**
```python
def register_compiled_models(self) -> None
```
> Injects dynamically compiled Pydantic models directly into the ActionRegistry.

```python
def to_compiled_graph(self) -> CompiledExecutionGraph
```
> Constructs an immutable CompiledExecutionGraph artifact from context state.

### File: `src/meta_compiler/core/immutable.py`

#### Classes & Models

```python
class ImmutableDict(dict):
```
> A read-only ``dict`` subclass that rejects all write operations.

Subclassing ``dict`` (rather than wrapping a mapping) keeps the value fully
serializable by Pydantic v2 and ``json.dumps`` while preventing in-place
mutation by raising ``TypeError`` on every mutator.

**Methods:**
```python
def pop(self, *args: Any) -> Any
```
```python
def popitem(self) -> Any
```
```python
def clear(self) -> None
```
```python
def update(self, *args: Any, **kwargs: Any) -> None
```
```python
def setdefault(self, *args: Any, **kwargs: Any) -> Any
```
#### Top-Level Functions

```python
def freeze_value(value: Any) -> Any
```
> Recursively converts nested dicts/lists into immutable equivalents.

Dicts become :class:`ImmutableDict`; lists become tuples. Other values are
returned unchanged.

```python
def immutable_mapping(value: Mapping[str, Any]) -> ImmutableDict
```
> Wraps a mapping into a read-only :class:`ImmutableDict`.

Returns the argument unchanged when it is already immutable; otherwise the
nested contents are recursively frozen into a fresh immutable copy.

### File: `src/meta_compiler/core/ir.py`

#### Classes & Models

```python
class NodeIR:
```
> Canonical, immutable intermediate representation of a workflow node.

**Fields / Attributes:**
- `id: str`
- `type: str`
- `inputs: tuple[str, ...] = field(default_factory=tuple)`
- `attributes: dict[str, Any] = field(default_factory=dict)`
- `disabled: bool = False`

**Methods:**
```python
def to_dict(self) -> dict[str, Any]
```
> Serializes NodeIR instance to a primitive dictionary.

```python
def from_dict(cls, data: dict[str, Any]) -> 'NodeIR'
```
> Deserializes a primitive dictionary into a validated NodeIR instance.

```python
class EdgeIR:
```
> Canonical, immutable intermediate representation of a dependency edge.

**Fields / Attributes:**
- `source: str`
- `target: str`
- `attributes: dict[str, Any] = field(default_factory=dict)`

**Methods:**
```python
def to_dict(self) -> dict[str, Any]
```
> Serializes EdgeIR instance to a primitive dictionary.

```python
def from_dict(cls, data: dict[str, Any]) -> 'EdgeIR'
```
> Deserializes a primitive dictionary into a validated EdgeIR instance.

```python
class ManifestIR:
```
> Canonical, immutable intermediate representation of a full workflow manifest.

**Fields / Attributes:**
- `namespace: str`
- `name: str`
- `version: str = '1.0.0'`
- `nodes: tuple[NodeIR, ...] = field(default_factory=tuple)`
- `edges: tuple[EdgeIR, ...] = field(default_factory=tuple)`
- `attributes: dict[str, Any] = field(default_factory=dict)`
- `manifest_hash: str | None = None`

**Methods:**
```python
def compute_canonical_hash(self) -> str
```
> Computes a deterministic SHA-256 hash of the normalized manifest payload.

```python
def with_computed_hash(self) -> Self
```
> Returns a new ManifestIR copy with the canonical hash populated.

```python
def to_dict(self) -> dict[str, Any]
```
> Serializes ManifestIR instance and nested IR entities to a primitive dictionary.

```python
def from_dict(cls, data: dict[str, Any]) -> 'ManifestIR'
```
> Deserializes a primitive dictionary into a validated, hash-computed ManifestIR instance.

### File: `src/meta_compiler/core/models.py`

#### Classes & Models

```python
class ArtifactSourceSpec(BaseModel):
```
> Identifies upstream node and output artifact origin for data provenance.

Attributes:
    task_id: Upstream producer task identifier.
    artifact_name: Upstream output artifact handle name.

**Fields / Attributes:**
- `task_id: str = Field(..., min_length=1, description='Upstream task identifier')`
- `artifact_name: str = Field(..., min_length=1, description='Upstream output artifact name')`

**Methods:**
```python
def validate_task_id(cls, v: str) -> str
```
```python
def validate_artifact_name(cls, v: str) -> str
```
```python
class ArtifactRefSpec(BaseModel):
```
> Specifies an input or output data artifact binding for a task node.

Attributes:
    name: Unique logical identifier for the artifact within task context.
    type: Primary data type string representation.
    schema_def: Optional JSON Schema dictionary defining internal payload contracts.
    source: Optional provenance link to upstream output.

**Fields / Attributes:**
- `name: str = Field(..., min_length=1, description='Artifact identifier name')`
- `type: str = Field(..., min_length=1, description='Data type specification')`
- `schema_def: Mapping[str, Any] | None = Field(default=None, alias='schema', description='Optional schema payload validation rules')`
- `source: ArtifactSourceSpec | None = Field(default=None, description='Provenance reference linking input artifact to upstream task output')`

**Methods:**
```python
def validate_name_identifier(cls, v: str) -> str
```
> Enforces strict Python variable naming rules for artifact handles.

```python
class TaskNodeSpec(BaseModel):
```
> Represents an immutable, discrete execution unit node within a workflow graph.

Attributes:
    id: Unique identifier for the task within manifest scope.
    action: Executable routine or runner target specifier.
    depends_on: Prerequisite parent node IDs.
    inputs: Declared input artifact specifications.
    outputs: Declared output artifact specifications.
    params: Arbitrary static execution configuration.

**Fields / Attributes:**
- `id: str = Field(..., min_length=1, description='Unique node ID')`
- `action: str = Field(..., min_length=1, description='Target action identifier')`
- `depends_on: tuple[str, ...] = Field(default_factory=tuple, description='IDs of prerequisite parent nodes')`
- `inputs: tuple[ArtifactRefSpec, ...] = Field(default_factory=tuple, description='Input artifact specifications')`
- `outputs: tuple[ArtifactRefSpec, ...] = Field(default_factory=tuple, description='Output artifact specifications')`
- `params: Mapping[str, Any] = Field(default_factory=dict, description='Static task execution configuration key-values')`

**Methods:**
```python
def validate_task_id(cls, v: str) -> str
```
```python
def validate_no_self_dependency(cls, v: tuple[str, ...], info: Any) -> tuple[str, ...]
```
```python
class WorkflowManifestSpec(BaseModel):
```
> Root metadata container representing a complete, immutable declarative workflow IR.

Attributes:
    version: Manifest version identifier.
    namespace: Logical grouping boundary.
    name: Canonical workflow identifier name.
    description: Optional human-readable documentation summary.
    tasks: Sequence of declared DAG task nodes.
    entities: Optional dynamic domain model dictionary.
    fsms: Optional finite state machine specifications.
    custom_types_module: Optional filesystem path string for dynamically loaded type modules.

**Fields / Attributes:**
- `version: str = Field(..., description='Manifest protocol version')`
- `namespace: str = Field(..., min_length=1, description='Target deployment namespace')`
- `name: str = Field(..., min_length=1, description='Workflow definition identifier')`
- `description: str | None = Field(default=None, description='Detailed workflow summary')`
- `tasks: tuple[TaskNodeSpec, ...] = Field(default_factory=tuple, description='Sequence of declared DAG task nodes')`
- `entities: Mapping[str, Any] = Field(default_factory=dict, description='Dynamic domain entity AST specifications')`
- `fsms: Mapping[str, Any] = Field(default_factory=dict, description='Finite state machine state specifications')`
- `custom_types_module: str | None = Field(default=None, description='Path to dynamic custom python types module')`

**Methods:**
```python
def validate_version_format(cls, v: str) -> str
```
```python
def validate_task_graph_semantics(cls, tasks: tuple[TaskNodeSpec, ...]) -> tuple[TaskNodeSpec, ...]
```
> Validates task collection invariants: unique IDs and existence of dependency targets.

```python
def get_node_by_id(self, task_id: str) -> TaskNodeSpec | None
```
> Helper to lookup a task node by its string ID.

```python
class NodeExecutionMetadata(BaseModel):
```
> Metadata tracking discrete node execution parameters in the target graph.

**Fields / Attributes:**
- `node_id: str`
- `inputs: list[str]`
- `output_type: str`
- `is_terminal: bool = False`

```python
class CompiledExecutionGraph(BaseModel):
```
> Execution IR returned after manifest syntax, model build, DAG graph compilation, and DB registration.

**Fields / Attributes:**
- `manifest_id: str = Field(..., description='Unique ID or UUID of the registered workflow')`
- `namespace: str`
- `name: str`
- `version: str`
- `nodes: dict[str, NodeExecutionMetadata] = Field(..., description='Topological nodes in the execution graph')`
- `db_record_id: int | str = Field(..., description='Primary key of the persisted DB record')`
- `compiled_at: datetime = Field(default_factory=datetime.utcnow)`
- `metadata: dict[str, Any] = Field(default_factory=dict)`

```python
class ExecutionPlan(BaseModel):
```
> Immutable compiler output artifact summarizing workflow graph execution topology.

**Fields / Attributes:**
- `graph_version: str = Field(default='v1', description='Plan schema version')`
- `stages: tuple[tuple[str, ...], ...] = Field(..., description='Sequential parallel execution generations')`
- `critical_path: tuple[str, ...] = Field(..., description='Longest execution chain sequence from root to leaf')`
- `roots: tuple[str, ...] = Field(..., description='Entry nodes with zero upstream dependencies')`
- `leaves: tuple[str, ...] = Field(..., description='Terminal nodes with no downstream dependents')`

### File: `src/meta_compiler/core/telemetry.py`

#### Top-Level Functions

```python
def get_tracer(module_name: str | None = None) -> Tracer
```
> Acquires a tracer instance using the shared meta_telemetry API.

```python
def setup_telemetry(service_name: str = 'meta-compiler', otlp_endpoint: str = 'localhost:4317', insecure: bool = True) -> Tracer
```
> Optional driver helper to configure global OpenTelemetry SDK provider and OTLP exporter.

SHOULD ONLY be invoked by application drivers / entrypoints, NOT library modules.

### File: `src/meta_compiler/engine.py`

#### Classes & Models

```python
class MetaCompiler:
```
> Overarching Meta Compiler Engine Facade.

Serves as the single, fully encapsulated building block for host application
integration. Manages pipeline execution, cross-cutting hooks, and DB persistence.

**Methods:**
```python
def __init__(self, settings: CompilerSettings | None = None, registry: ActionRegistry | None = None, hooks: list[BaseCompilerHook] | None = None, custom_stage_classes: list[type[BaseCompilerStage]] | None = None) -> None
```
```python
def load_raw_schemas(self, schema_dir: str | Path) -> int
```
> Ingests raw JSON schemas from disk into memory without dynamic synthesis.

```python
def register_schema(self, action_key: str, schema: dict[str, Any], source_path: str | Path | None = None) -> None
```
> Register a single JSON schema with its logical file path.

The ``source_path`` preserves the ``shopping/types/buyer.json``-style
hierarchy needed for relative ``$ref`` resolution when the engine is
embedded in a larger application that owns schemas in-memory (DB/S3).

```python
def register_schemas(self, schemas: dict[str, dict[str, Any]]) -> int
```
> Bulk-register schemas with optional path context (auto-infer with explicit override).

Args:
    schemas: Mapping ``action_key -> JSON schema dict``.
    base_dir: Explicit ``schema_dir`` override. If ``None`` and ``path_map``
        is given, inferred as common ancestor of all resolved paths.
    path_map: Per-action ``action_key -> source_path``. If omitted,
        paths are synthesized as ``base_dir/action_key.replace(".","/")+".json"``.
    clear_existing: If ``True``, clears prior ``raw_schemas``/``file_index``
        before registering (mirrors ``load_raw_schemas`` semantics).

Returns:
    Number of schemas registered.

```python
def write_per_file_schemas(self, out_root: str | Path, clear_output: bool = True) -> list[Path]
```
> Emit one ``.py`` per JSON schema mirroring hierarchy with cross-file imports.

```python
def register_action(self, action_name: str, callable_func: Callable[..., Any], **kwargs: Any) -> None
```
> Convenience delegation to register domain actions into the underlying registry.

```python
def add_hook(self, hook: BaseCompilerHook) -> None
```
> Inject cross-cutting concerns (security checks, telemetry, audit logs).

```python
def compile_sync(self, manifest_input: str | dict[str, Any]) -> CompilationContext
```
> Sync entry point: runs the entire stage pipeline without hooks or persistence.

```python
async def compile(self, manifest_input: str, session: AsyncSession | None = None) -> CompiledExecutionGraph
```
> Atomic operation: Validates, compiles, executes hooks, and optionally persists graph.

### File: `src/meta_compiler/exceptions.py`

#### Classes & Models

```python
class MetaCompilerError(Exception):
```
> Base exception for all meta_compiler runtime and compilation errors.

**Methods:**
```python
def __init__(self, message: str, details: dict[str, Any] | list[Any] | None = None, component: str | None = None) -> None
```
```python
def to_dict(self) -> dict[str, Any]
```
> Return structured, JSON-serializable diagnostic metadata.

```python
class ConfigurationError(MetaCompilerError):
```
> Raised when runtime configuration or packaged assets are invalid.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class ManifestSyntaxError(MetaCompilerError):
```
> Raised when raw YAML/JSON input cannot be parsed.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class SchemaValidationError(MetaCompilerError):
```
> Raised when manifest input violates the meta-schema.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class SemanticValidationError(MetaCompilerError):
```
> Raised when manifest semantic invariants are violated.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class DAGCompilationError(MetaCompilerError):
```
> Raised when DAG construction or validation fails.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class ContractValidationError(MetaCompilerError):
```
> Raised when action or data contracts are incompatible.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class ModelCompilationError(MetaCompilerError):
```
> Raised when runtime Pydantic model compilation fails.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class PersistenceError(MetaCompilerError):
```
> Raised when persistence or serialization fails.

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class SyntaxValidationError(ManifestSyntaxError):
```
> Alias for :class:`ManifestSyntaxError` for Step-1 syntax-guard compliance.

Exists to satisfy the exported naming contract (``SyntaxValidationError``)
while remaining identity-equal to the canonical manifest-syntax exception.

```python
class TopologyValidationError(MetaCompilerError):
```
> Raised when graph topology verification fails (pre-graph dependency checks).

**Methods:**
```python
def __init__(self, message: str) -> None
```
```python
class CyclicGraphError(TopologyValidationError):
```
> Topological cycle-detection exception (Step-3 cycle check).

Exists to satisfy the exported naming contract (``CyclicGraphError``).
Carries the detected ``cycle_nodes`` for diagnostics.

**Methods:**
```python
def __init__(self, message: str) -> None
```
### File: `src/meta_compiler/hooks/base.py`

#### Classes & Models

```python
class BaseCompilerHook(ABC):
```
> Abstract interface for injecting cross-cutting concerns into compilation lifecycles.

**Methods:**
```python
async def on_pre_compile(self, context: CompilationContext) -> None
```
> Executed prior to running stage pipeline validation.

```python
async def on_post_compile(self, context: CompilationContext) -> None
```
> Executed immediately following successful stage pipeline execution.

```python
async def on_persist(self, context: CompilationContext) -> None
```
> Executed immediately after database persistence succeeds.

```python
async def on_error(self, context: CompilationContext, error: Exception) -> None
```
> Executed when an exception occurs during compilation or persistence.

### File: `src/meta_compiler/orchestrator.py`

#### Classes & Models

```python
class CompilerConfigProvider(Protocol):
```
> Structural protocol matching host containers supplying compiler_settings.

**Fields / Attributes:**
- `compiler_settings: CompilerSettings`

```python
class PipelineCompilationError(MetaCompilerError):
```
> Raised when any stage of the compilation pipeline encounters a fatal failure.

**Methods:**
```python
def __init__(self, stage: str, message: str, details: Any = None) -> None
```
```python
class CompiledWorkflowDefinition(BaseModel):
```
> Pure in-memory compiler artifact output representing a validated workflow.

**Fields / Attributes:**
- `manifest_spec: WorkflowManifestSpec | None = None`
- `execution_plan: ExecutionPlan`
- `raw_manifest: dict[str, Any]`
- `pinned_dependencies: dict[str, Any] | None = None`
- `version_vector: dict[str, Any] | None = None`

```python
class MetaCompilerPipeline:
```
> Engine wrapper supporting hosted lifespan injection and standalone execution.

**Methods:**
```python
def __init__(self, settings: CompilerSettings | None = None) -> None
```
```python
def from_provider(cls, provider: Any) -> 'MetaCompilerPipeline'
```
> Factory extracting CompilerSettings dynamically from a host container or dict.

```python
def compile(self, manifest_input: ManifestIR | str | dict[str, Any], registry: ActionRegistry | None = None, pinned_dependencies: dict[str, Any] | None = None, version_vector: dict[str, Any] | None = None, schemas: dict[str, dict[str, Any]] | None = None, schema_dir: str | Path | None = None, schema_paths: dict[str, str | Path] | None = None) -> CompiledWorkflowDefinition
```
```python
async def compile_and_register(self, manifest_input: ManifestIR | str | dict[str, Any], session: AsyncSession, registry: ActionRegistry | None = None, pinned_dependencies: dict[str, Any] | None = None, version_vector: dict[str, Any] | None = None, pre_commit_guard: PreCommitGuardHook | None = None, schemas: dict[str, dict[str, Any]] | None = None, schema_dir: str | Path | None = None, schema_paths: dict[str, str | Path] | None = None) -> CompiledExecutionGraph
```
#### Top-Level Functions

```python
def compile_manifest(manifest_input: ManifestIR | str | dict[str, Any], registry: ActionRegistry | None = None, pinned_dependencies: dict[str, Any] | None = None, version_vector: dict[str, Any] | None = None, settings: CompilerSettings | None = None, schemas: dict[str, dict[str, Any]] | None = None, schema_dir: str | Path | None = None, schema_paths: dict[str, str | Path] | None = None) -> CompiledWorkflowDefinition
```
> Executes in-memory compilation pipeline consuming ManifestIR or raw inputs without DB side-effects.

```python
async def register_workflow(compiled_def: CompiledWorkflowDefinition, session: AsyncSession) -> UUID
```
> Persists a compiled definition after executing an optional pre-commit guard callback.

```python
async def compile_and_register_manifest(manifest_input: ManifestIR | str | dict[str, Any], session: AsyncSession, registry: ActionRegistry | None = None, pinned_dependencies: dict[str, Any] | None = None, version_vector: dict[str, Any] | None = None, pre_commit_guard: PreCommitGuardHook | None = None, settings: CompilerSettings | None = None, schemas: dict[str, dict[str, Any]] | None = None, schema_dir: str | Path | None = None, schema_paths: dict[str, str | Path] | None = None) -> CompiledExecutionGraph
```
> End-to-end orchestration pipeline taking ManifestIR or raw inputs, compiling, and persisting.

### File: `src/meta_compiler/persistence/mutator.py`

#### Classes & Models

```python
class MutationGuardError(MetaCompilerError):
```
> Raised when a mutation violates the pinned-dependency snapshot contract.

**Methods:**
```python
def __init__(self, message: str, details: dict[str, Any] | None = None) -> None
```
```python
class WorkflowDefinitionMutator:
```
> Append-only mutation handler that routes transitions through the repository.

**Methods:**
```python
def __init__(self, session: AsyncSession) -> None
```
```python
async def register_mutation(self, compiled_def: CompiledWorkflowDefinition, manifest_patch: dict[str, Any], new_version: str) -> UUID
```
> Persists a new, mutated definition row after verifying snapshot drift.

#### Top-Level Functions

```python
def compute_version_vector(pinned_dependencies: dict[str, Any]) -> dict[str, str]
```
> Produces a ``{dependency_name: pinned_version}`` vector from a dependency snapshot.

```python
def assert_no_pinned_dependency_drift(version_vector: dict[str, str], current_versions: dict[str, str]) -> None
```
> Fails the mutation if any pinned dependency has drifted from the published state.

```python
def build_mutated_payload(base_payload: dict[str, Any], manifest_patch: dict[str, Any], new_version: str, pinned_dependencies: dict[str, Any] | None = None, version_vector: dict[str, str] | None = None) -> dict[str, Any]
```
> Applies an append-only mutation to a definition payload producing a new row payload.

The ``id`` is regenerated (a mutation creates a new record), the version is
bumped to ``new_version``, and provenance vectors are carried forward or
recomputed from the pinned dependency snapshot.

### File: `src/meta_compiler/persistence/repository.py`

#### Classes & Models

```python
class RepositoryError(MetaCompilerError):
```
> Raised when database operations fail within the repository layer.

**Methods:**
```python
def __init__(self, message: str, details: dict[str, Any] | None = None) -> None
```
```python
class WorkflowRepository:
```
> Repository handling asynchronous persistence for compiled workflow definitions.

**Methods:**
```python
def __init__(self, session: AsyncSession) -> None
```
```python
async def save(self, payload: dict[str, Any]) -> UUID
```
```python
async def persist_workflow_definition(self, payload: dict[str, Any]) -> UUID
```
> Stages an insert operation into the `meta_workflow_definitions` table.

### File: `src/meta_compiler/stages/adapter_synthesizer.py`

#### Classes & Models

```python
class AdapterSynthesisError(MetaCompilerError):
```
> Raised when transformation adapter synthesis or AST rewiring fails.

**Methods:**
```python
def __init__(self, message: str, details: dict[str, Any] | None = None) -> None
```
```python
class AdapterSynthesizerStage(BaseCompilerStage):
```
> Stage 5 Adapter: Synthesizes graph transformation adapters based on contract diagnostics.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
```python
class AdapterSynthesizer:
```
> Synthesizes immutable manifest transformations.

**Methods:**
```python
def synthesize_adapters(self, context: CompilationContext) -> None
```
> Process pending diagnostics and replace the manifest with a transformed copy.

```python
def inject_transformation_adapter(self, context: CompilationContext, manifest: WorkflowManifestSpec, mismatch: ContractMismatch) -> WorkflowManifestSpec
```
> Synthesizes a single adapter task node and rewires dependency links.

The returned manifest is a new immutable model. The original manifest
and its task nodes are never mutated.

### File: `src/meta_compiler/stages/base.py`

#### Classes & Models

```python
class BaseCompilerStage(ABC):
```
> Abstract Base Class for all isolated compiler stages in the MetaCompiler pipeline.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
> Executes stage transformation or validation against the compilation context.

Args:
    context: Shared compilation context carrying raw input, AST specs, and artifacts.
    registry: Central action registry for input/output schema and action resolution.

Raises:
    MetaCompilerError: Subclasses raise domain-specific compiler exceptions on failure.

### File: `src/meta_compiler/stages/common.py`

#### Classes & Models

```python
class CompiledArtifacts:
```
> Container holding compiled manifest specifications, topology graphs, and DB payloads.

**Methods:**
```python
def __init__(self, manifest_spec: Any, execution_order: Any, db_payload: dict[str, Any], compiled_models: dict[str, type[BaseModel]] | None = None) -> None
```
```python
def write_to_disk(self, target_dir: Path) -> list[Path]
```
> Safely writes compiled artifacts and dynamic source code to disk.

#### Top-Level Functions

```python
def generate_model_source_code(models: dict[str, type[BaseModel]]) -> str
```
> Generates clean, executable Python source code for dynamic Pydantic models.

Delegates to the datamodel-code-generator backed implementation in
:mod:`meta_compiler.stages.model_compiler` so that schema composition,
constraints, and annotations are handled by a single, canonical generator.

### File: `src/meta_compiler/stages/contract_checker.py`

#### Classes & Models

```python
class ContractMismatch:
```
> Diagnostic metadata capturing incompatible task edge boundaries.

**Fields / Attributes:**
- `producer_id: str`
- `consumer_id: str`
- `producer_action: str`
- `consumer_action: str`
- `expected_type: type[Any]`
- `actual_type: type[Any]`

```python
class ContractCheckerStage(BaseCompilerStage):
```
> Stage 4 Adapter: Read-only edge type verification and dry-run execution check.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
```python
class ContractChecker:
```
> Encapsulates semantic edge contract verification and Hamilton dry-run graph execution.

**Methods:**
```python
def __init__(self, registry: ActionRegistry) -> None
```
```python
def verify_edge_contracts(self, context: CompilationContext) -> None
```
> Pure read-only diagnostic pass. Populates context.diagnostics without mutating AST.

```python
def build_hamilton_driver(self, manifest: WorkflowManifestSpec) -> tuple[h_driver.Driver, str]
```
> Compiles an in-memory Hamilton execution driver for the manifest along with module cleanup key.

```python
def verify_node_contracts(self, manifest: WorkflowManifestSpec, execution_plan: Any) -> bool
```
> Performs a Hamilton dry-run pass stage-by-stage.

#### Top-Level Functions

```python
def is_type_compatible(producer_type: type[Any], consumer_type: type[Any], _depth: int = 0, _max_depth: int = 15) -> bool
```
> Evaluates type equality, subclassing, numeric promotion, covariance,
and optional/nullable type assignability between producer outputs and consumer inputs.

```python
def verify_node_contracts(manifest: WorkflowManifestSpec, execution_plan: Any, registry: ActionRegistry) -> bool
```
> Backward-compatible functional wrapper delegating to scoped ContractChecker instance.

```python
def verify_edge_contracts(manifest: WorkflowManifestSpec, registry: ActionRegistry) -> list[ContractMismatch]
```
> Validates edge type compatibility across a compiled manifest.

Raises :class:`ContractValidationError` for unregistered actions or
unresolvable producer references, and returns any recorded edge
``ContractMismatch`` diagnostics for incompatible producer→consumer
output/input type boundaries.

### File: `src/meta_compiler/stages/db_serializer.py`

#### Classes & Models

```python
class DBSerializerStage(BaseCompilerStage):
```
> Stage 5 Adapter: JSONB payload normalization.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
```python
class SerializationError(MetaCompilerError):
```
> Raised when JSONB payload mapping or database serialization fails.

**Methods:**
```python
def __init__(self, message: str, details: dict[str, Any] | None = None) -> None
```
#### Top-Level Functions

```python
def to_db_payload(compiled_def: CompiledArtifacts | dict[str, Any] | Any, id_override: UUID | None = None) -> dict[str, Any]
```
> Transforms compiled artifacts or workflow definitions into a DB JSONB payload map.

### File: `src/meta_compiler/stages/model_compiler.py`

#### Classes & Models

```python
class EntityModelCompiler:
```
> Internal domain entity and dynamic artifact model compilation engine.

**Methods:**
```python
def compile_domain_models(self, entities: dict[str, Any]) -> dict[str, type[BaseModel]]
```
> Dynamically compiles entity AST dictionaries into runtime Pydantic BaseModel classes.

```python
def compile(self, manifest_input: str | dict[str, Any] | BaseModel, registry: ActionRegistry | None = None, custom_types_module: Path | None = None) -> CompiledArtifacts
```
> Executes multi-stage compilation from raw input to validated artifacts with rewind support.

### File: `src/meta_compiler/stages/per_file_writer.py`

#### Top-Level Functions

```python
def write_per_file_schemas() -> list[Path]
```
> Generate one ``.py`` per JSON schema, mirroring hierarchy with imports.

### File: `src/meta_compiler/stages/schema_bundler.py`

#### Classes & Models

```python
class SchemaBundler:
```
> Bundles a single action schema's external ``$ref`` into ``$defs``.

**Methods:**
```python
def __init__(self, schema_dir: Path, file_index: dict[str, Path], raw_schemas: dict[str, dict]) -> None
```
```python
def bundle_for(self, action_key: str) -> dict
```
### File: `src/meta_compiler/stages/schema_synthesis.py`

#### Classes & Models

```python
class SchemaSynthesisStage(BaseCompilerStage):
```
> Pipeline stage that converts raw JSON Schema dicts into dynamic Pydantic models.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
### File: `src/meta_compiler/stages/semantic_validator.py`

#### Classes & Models

```python
class ManifestSemanticError(MetaCompilerError):
```
> Raised when intra-manifest semantic rules or artifact linkages are violated.

**Methods:**
```python
def __init__(self, message: str, details: dict[str, Any] | None = None) -> None
```
```python
class SemanticValidatorStage(BaseCompilerStage):
```
> Pipeline stage running semantic invariant validation on the compiled manifest.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
```python
class ManifestSemanticValidator:
```
> Validates intra-manifest dependencies, artifact linkage, and static contract types.

**Methods:**
```python
def validate(self, manifest: WorkflowManifestSpec) -> None
```
> Executes full semantic invariant suite on parsed WorkflowManifestSpec.

Raises:
    ManifestSemanticError: If any semantic rule is violated.

### File: `src/meta_compiler/stages/syntax_guard.py`

#### Classes & Models

```python
class SyntaxGuardStage(BaseCompilerStage):
```
> Stage 1 Adapter: Structural syntax and JSON Schema Draft 2020-12 validation.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
#### Top-Level Functions

```python
def validate_manifest_syntax(raw_manifest: dict[str, Any], schema_path: Path | None = None, settings: CompilerSettings | None = None) -> dict[str, Any]
```
> Executes jsonschema structural validation against the static Draft 2020-12 schema.

```python
def parse_and_validate_yaml(raw_yaml_str: str, schema_path: Path | None = None, settings: CompilerSettings | None = None) -> dict[str, Any]
```
> Parses raw YAML text and immediately validates its syntax structure.

### File: `src/meta_compiler/stages/topology_validator.py`

#### Classes & Models

```python
class TopologyValidatorStage(BaseCompilerStage):
```
> Stage 3 Adapter: NetworkX DAG cycle detection and topological ordering synthesis.

**Methods:**
```python
def run(self, context: CompilationContext, registry: ActionRegistry) -> None
```
#### Top-Level Functions

```python
def validate_dependency_references(manifest: WorkflowManifestSpec) -> None
```
> Explicit pre-validation phase ensuring all dependency targets exist.

```python
def build_networkx_graph(manifest: WorkflowManifestSpec) -> nx.DiGraph
```
> Constructs a NetworkX DiGraph from a compiled workflow manifest specification.

```python
def assert_acyclic_topology(graph: nx.DiGraph) -> None
```
> Evaluates DAG integrity and raises CyclicGraphError if execution loops exist.

```python
def compute_execution_plan(graph: nx.DiGraph) -> ExecutionPlan
```
> Synthesizes a structured, immutable ExecutionPlan compiler artifact.

```python
def validate_topology(manifest: WorkflowManifestSpec) -> tuple[nx.DiGraph, ExecutionPlan]
```
> Executes topological verification and generates the runtime execution plan.

### File: `tests/config/test_config.py`

#### Top-Level Functions

```python
def test_configuration_error_identity_is_canonical() -> None
```
```python
def test_instantiation_resolves_packaged_schema_asset() -> None
```
```python
def test_instantiation_halts_when_schema_missing(tmp_path: Path) -> None
```
```python
def test_instantiation_halts_when_schema_path_is_directory(tmp_path: Path) -> None
```
```python
def test_instantiation_succeeds_with_valid_explicit_schema(tmp_path: Path) -> None
```
```python
def test_production_without_db_url_halts_at_construction(tmp_path: Path) -> None
```
```python
def test_production_with_explicit_db_url_constructs(tmp_path: Path) -> None
```
```python
def test_test_environment_is_exempt_from_runtime_validation() -> None
```
```python
def test_environment_from_env_variable() -> None
```
```python
def test_whitespace_db_url_is_treated_as_unset(tmp_path: Path) -> None
```
### File: `tests/conftest.py`

#### Classes & Models

```python
class RecordingSession:
```
> Fake AsyncSession capturing executed statements and transaction calls.

**Methods:**
```python
def __init__(self) -> None
```
```python
async def execute(self, stmt: Any) -> None
```
```python
async def commit(self) -> None
```
```python
async def close(self) -> None
```
```python
class IntOut(BaseModel):
```
**Fields / Attributes:**
- `value: int`

```python
class StrIn(BaseModel):
```
**Fields / Attributes:**
- `value: str`

```python
class IntIn(BaseModel):
```
**Fields / Attributes:**
- `value: int`

#### Top-Level Functions

```python
def recording_session() -> RecordingSession
```
> Returns a fresh fake AsyncSession recording executed statements.

```python
def action_registry() -> ActionRegistry
```
> An ActionRegistry pre-loaded with schema-less domain actions.

```python
def typed_registry() -> ActionRegistry
```
> A registry with typed (int-out -> str-in) boundary contracts.

```python
def manifest_yaml(tasks: str, name: str = 'wf') -> str
```
> Builds a valid manifest YAML document for the given task lines.

```python
def chain_manifest() -> str
```
> Two chained schema-less tasks: produce -> consume.

### File: `tests/core/test_immutable.py`

#### Top-Level Functions

```python
def test_immutable_dict_supports_reads() -> None
```
```python
def test_immutable_dict_blocks_item_assignment() -> None
```
```python
def test_immutable_dict_blocks_mutators() -> None
```
```python
def test_freeze_value_recurses_into_containers() -> None
```
```python
def test_freeze_value_is_round_trip_serializable() -> None
```
```python
def test_immutable_mapping_returns_same_frozen_instance() -> None
```
### File: `tests/core/test_ir.py`

#### Top-Level Functions

```python
def test_node_ir_attributes_are_deep_frozen() -> None
```
```python
def test_node_ir_inputs_tuple_normalization() -> None
```
```python
def test_ir_round_trip_preserves_identity() -> None
```
```python
def test_canonical_hash_changes_when_node_attribute_changes() -> None
```
```python
def test_manifest_ir_from_dict_computes_hash() -> None
```
```python
def test_node_ir_from_dict_rejects_missing_keys() -> None
```
```python
def test_manifest_ir_from_dict_rejects_non_dict() -> None
```
### File: `tests/engine/test_engine.py`

#### Top-Level Functions

```python
def test_default_validation_stage_order() -> None
```
```python
def test_compile_sync_produces_manifest_plan_and_db_payload(action_registry) -> None
```
```python
def test_manifest_task_params_are_deep_frozen(action_registry) -> None
```
```python
def test_compile_async_returns_execution_graph(action_registry) -> None
```
```python
def test_adapter_self_healing_injects_adapter_and_converges(typed_registry) -> None
```
```python
def test_unregistered_action_fails_compilation(action_registry) -> None
```
```python
def test_self_dependency_is_rejected(action_registry) -> None
```
### File: `tests/orchestrator/test_orchestrator.py`

#### Top-Level Functions

```python
def test_compile_manifest_runs_in_memory_without_db(action_registry) -> None
```
```python
def test_compile_manifest_accepts_dict_input(action_registry) -> None
```
```python
def test_compile_manifest_rejects_unknown_action(action_registry) -> None
```
```python
def test_register_workflow_persists_and_commits(action_registry) -> None
```
```python
def test_compile_and_register_manifest_end_to_end(action_registry) -> None
```
```python
def test_pre_commit_guard_hook_is_invoked(action_registry) -> None
```
### File: `tests/persistence/test_mutator.py`

#### Top-Level Functions

```python
def test_compute_version_vector_from_snapshot() -> None
```
```python
def test_drift_guard_passes_when_current_matches() -> None
```
```python
def test_drift_guard_raises_on_drift() -> None
```
```python
def test_drift_guard_raises_on_missing_current() -> None
```
```python
def test_build_mutated_payload_bumps_version_and_carries_vector() -> None
```
```python
def test_build_mutated_payload_recomputes_vector_when_not_given() -> None
```
```python
def test_register_mutation_persists_new_record(action_registry) -> None
```
```python
def test_register_mutation_blocks_on_drift(action_registry) -> None
```
### File: `tests/persistence/test_repository.py`

#### Top-Level Functions

```python
def test_persist_stages_insert_with_native_uuid() -> None
```
```python
def test_persist_wraps_failures_in_repository_error() -> None
```
```python
def test_save_alias_delegates_to_persist() -> None
```
```python
def test_missing_id_key_raises() -> None
```
### File: `tests/stages/test_contract_checker.py`

#### Classes & Models

```python
class CustomerSchema(BaseModel):
```
**Fields / Attributes:**
- `name: str`

```python
class AuditSchema(BaseModel):
```
**Fields / Attributes:**
- `name: str`

#### Top-Level Functions

```python
def test_type_identity_is_compatible() -> None
```
```python
def test_any_is_compatible_with_everything() -> None
```
```python
def test_numeric_promotion() -> None
```
```python
def test_subclass_assignability() -> None
```
```python
def test_union_and_optional_handling() -> None
```
```python
def test_incompatible_types_rejected() -> None
```
```python
def test_incompatible_edge_contract_detected_and_self_heals(typed_registry) -> None
```
```python
def test_verify_edge_contracts_returns_mismatches() -> None
```
```python
def test_dry_run_executes_all_stages(typed_registry) -> None
```
```python
def test_schema_less_chain_has_no_edge_mismatches(action_registry) -> None
```
### File: `tests/stages/test_db_serializer.py`

#### Top-Level Functions

```python
def test_db_payload_id_is_native_uuid(action_registry) -> None
```
```python
def test_db_payload_shape_from_context(action_registry) -> None
```
```python
def test_db_payload_from_compiled_artifacts(action_registry) -> None
```
```python
def test_id_override_is_honored() -> None
```
### File: `tests/stages/test_schema_synthesis.py`

#### Top-Level Functions

```python
def test_synthesis_builds_input_output_models() -> None
```
```python
def test_synthesis_updates_registered_action_contracts() -> None
```
```python
def test_synthesis_supports_all_of_composition() -> None
```
### File: `tests/stages/test_semantic_validator.py`

#### Top-Level Functions

```python
def test_valid_manifest_passes() -> None
```
```python
def test_self_dependency_rejected_at_model_boundary() -> None
```
```python
def test_missing_dependency_rejected_at_model_boundary() -> None
```
```python
def test_input_artifact_references_missing_source_task() -> None
```
```python
def test_input_artifact_type_mismatch_with_source_output() -> None
```
### File: `tests/test_cross_schema_db_serialization.py`

#### Top-Level Functions

```python
def test_cross_schema_bundling_via_register_schemas_produces_typed_model() -> None
```
> Synthesis with in-memory cross-file $ref yields typed Amount, not dict.

```python
def test_cross_schema_db_payload_reflects_typed_manifest_not_disk() -> None
```
> End-to-end orchestrator via in-memory schemas persists typed manifest via DB payload.

```python
def test_register_schemas_auto_infer_without_explicit_base_dir() -> None
```
> Auto-infer base_dir from path_map when not explicitly passed (explicit override tested above).
