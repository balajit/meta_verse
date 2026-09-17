# Public Custom Libraries Specification Summary

## Library: `meta-config`

### File: `src/meta_config/base.py`

#### Classes & Models

```python
class MetaBaseSettings(BaseSettings):
```
> Base class for all system setting configurations with strict immutability and boot validation.

**Fields / Attributes:**
- `openbao_path: ClassVar[str | None] = None`

**Methods:**
```python
def __init__(self, **values: Any) -> None
```
```python
def settings_customise_sources(cls, settings_cls: Type[BaseSettings], init_settings: PydanticBaseSettingsSource, env_settings: PydanticBaseSettingsSource, dotenv_settings: PydanticBaseSettingsSource, file_secret_settings: PydanticBaseSettingsSource) -> Tuple[PydanticBaseSettingsSource, ...]
```
### File: `src/meta_config/exceptions.py`

#### Classes & Models

```python
class MetaConfigError(Exception):
```
> Base exception for all meta-config errors.

**Methods:**
```python
def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None
```
```python
class ConfigValidationError(MetaConfigError):
```
> Raised when configuration parsing or validation fails during application boot.

**Methods:**
```python
def __init__(self, message: str, errors: Sequence[Mapping[str, Any]], context: Optional[Dict[str, Any]] = None) -> None
```
```python
class SecretInjectionError(MetaConfigError):
```
> Raised when secrets cannot be fetched or decrypted from OpenBao.

**Methods:**
```python
def __init__(self, message: str, secret_path: str, context: Optional[Dict[str, Any]] = None) -> None
```
```python
class BootConfigurationError(MetaConfigError):
```
> Fatal exception raised to immediately halt application boot sequence.

### File: `src/meta_config/loaders/openbao.py`

#### Classes & Models

```python
class OpenBaoConfig:
```
> Configuration container for OpenBao connection specs.

**Methods:**
```python
def __init__(self, url: Optional[str] = None, token: Optional[str] = None, mount_point: str = 'secret') -> None
```
```python
class OpenBaoSettingsSource(PydanticBaseSettingsSource):
```
> Custom settings source that pulls configuration key-values from OpenBao KV engine.

**Methods:**
```python
def __init__(self, settings_cls: Type[BaseSettings], secret_path: Optional[str] = None, openbao_config: Optional[OpenBaoConfig] = None) -> None
```
```python
def get_field_value(self, field: Any, field_name: str) -> Tuple[Any, str, bool]
```
> Not used directly; __call__ extracts all values at once for efficiency.

### File: `src/meta_config/telemetry.py`

#### Top-Level Functions

```python
def trace_config_span(span_name: str) -> Generator[Any, None, None]
```
> Trace configuration operations using OpenTelemetry spans when available.

```python
def log_config_event(event_type: str, status: str, metadata: Dict[str, Any]) -> None
```
> Emit a structured log for configuration lifecycle events without leaking secrets.

```python
def log_config_error(event_type: str, error: Exception, metadata: Dict[str, Any]) -> None
```
> Emit a structured error log with actionable root-cause metadata.

### File: `tests/test_config.py`

#### Classes & Models

```python
class SimpleAppSettings(MetaBaseSettings):
```
**Fields / Attributes:**
- `app_name: str = Field(default='meta-service')`
- `port: int = Field(default=8080, ge=1, le=65535)`
- `secret_key: SecretStr = Field(...)`

```python
class CustomPathSettings(MetaBaseSettings):
```
**Fields / Attributes:**
- `database_url: str = Field(default='postgresql://localhost:5432/db')`

#### Top-Level Functions

```python
def test_settings_boot_success_with_explicit_args() -> None
```
```python
def test_settings_boot_success_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None
```
```python
def test_settings_fail_fast_on_missing_required_field() -> None
```
```python
def test_settings_fail_fast_on_invalid_value_type() -> None
```
```python
def test_runtime_immutability_enforced() -> None
```
```python
def test_extra_fields_forbidden() -> None
```
```python
def test_dict_based_model_config_openbao_path_extracted() -> None
```
### File: `tests/test_openbao.py`

#### Classes & Models

```python
class DummySettings(BaseSettings):
```
**Fields / Attributes:**
- `db_pass: str = 'default_pass'`

#### Top-Level Functions

```python
def test_openbao_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None
```
```python
def test_openbao_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None
```
```python
def test_settings_source_returns_empty_when_no_secret_path() -> None
```
```python
def test_settings_source_raises_error_on_missing_token() -> None
```
```python
def test_settings_source_raises_error_when_unauthenticated(mock_hvac_client: MagicMock) -> None
```
```python
def test_settings_source_successfully_fetches_secrets(mock_hvac_client: MagicMock) -> None
```
```python
def test_settings_source_wraps_client_exceptions(mock_hvac_client: MagicMock) -> None
```
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

## Library: `meta_polymorph`

### File: `src/meta_polymorph/domain/dtos.py`

#### Classes & Models

```python
class TenantContext(BaseModel):
```
> Context identifying tenant hierarchy and scope for resolution.

**Fields / Attributes:**
- `tenant_id: str`
- `industry_id: str`
- `global_id: str = 'global'`

```python
class ManifestIR(BaseModel):
```
> Pure, serializable Intermediate Representation container for compiled manifests.

**Fields / Attributes:**
- `version: str = '1.0.0'`
- `namespace: str`
- `name: str`
- `description: str | None = ''`
- `tasks: list[dict[str, Any]] = Field(default_factory=list)`
- `entities: list[dict[str, Any]] = Field(default_factory=list)`
- `fsms: list[dict[str, Any]] = Field(default_factory=list)`

### File: `src/meta_polymorph/exceptions.py`

#### Classes & Models

```python
class PolymorphicError(Exception):
```
> Base exception for all meta_polymorph domain errors.

```python
class PolymorphicCompilationError(PolymorphicError):
```
> Raised when a hydrated polymorphic payload fails to compile into ManifestIR.

**Methods:**
```python
def __init__(self, message: str, tenant_id: Optional[str] = None, entity_id: Optional[str] = None, original_exception: Optional[Exception] = None) -> None
```
```python
def to_agent_context(self) -> dict[str, Any]
```
> Returns structured JSON-serializable metadata for automated agentic triage.

### File: `src/meta_polymorph/merger/deep_merger.py`

#### Classes & Models

```python
class DeepMerger:
```
> Stateless wrapper class providing deep dictionary merge operations.

**Methods:**
```python
def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]
```
#### Top-Level Functions

```python
def deep_merge(base: dict[str, Any], override: dict[str, Any], _current_depth: int = 0) -> dict[str, Any]
```
> Recursively merges two dictionaries into a new dictionary without mutating inputs.

### File: `src/meta_polymorph/pipeline.py`

#### Classes & Models

```python
class PolymorphicPipeline:
```
> Pipeline entrypoint orchestrating layer resolution into a compiled ManifestIR container.

**Methods:**
```python
def compile_to_ir(cls, context: TenantContext, layers: list[dict[str, Any]]) -> ManifestIR
```
> Resolves pre-ordered layers and instantiates the pure ManifestIR container.

### File: `src/meta_polymorph/resolver.py`

#### Classes & Models

```python
class PolymorphicResolver:
```
> Consolidated layer resolver executing sequential deep merges across hierarchy tiers.

**Methods:**
```python
def resolve(self, layers: list[dict[str, Any]]) -> dict[str, Any]
```
> Sequentially merges dictionary layers from base (Global) to leaf (Tenant).

### File: `tests/test_deep_merger.py`

#### Top-Level Functions

```python
def test_flat_key_merge_and_override()
```
```python
def test_deep_nesting()
```
```python
def test_array_list_overrides()
```
```python
def test_unset_flat_and_nested_keys()
```
```python
def test_deep_merger_wrapper_class()
```
### File: `tests/test_pipeline.py`

#### Top-Level Functions

```python
def test_polymorphic_pipeline_compile_to_ir_end_to_end()
```
```python
def test_polymorphic_pipeline_fallback_defaults()
```
```python
def test_polymorphic_pipeline_validation_error()
```
```python
def test_polymorphic_pipeline_rejects_malformed_layers()
```
### File: `tests/test_telemetry_integration.py`

#### Top-Level Functions

```python
def setup_global_tracer_provider() -> Generator[InMemorySpanExporter, None, None]
```
> Configures a global OpenTelemetry TracerProvider with an in-memory exporter for testing.

```python
def telemetry_setup(setup_global_tracer_provider: InMemorySpanExporter) -> Generator[tuple[InMemorySpanExporter, io.StringIO], None, None]
```
> Prepares clean span memory and attaches a StructuredJsonFormatter stream handler to the pipeline loggers.

```python
def test_pipeline_telemetry_and_logging_integration(telemetry_setup: tuple[InMemorySpanExporter, io.StringIO]) -> None
```
> Verifies span propagation, attribute extraction, and structured log trace correlation during IR compilation.

## Library: `meta_builder_brain`

### File: `src/meta_builder_brain/api/routes.py`

#### Classes & Models

```python
class BuildJobRequest(BaseModel):
```
**Fields / Attributes:**
- `tenant_id: str = Field(..., description='Tenant identifier executing build')`
- `manifest_urn: str = Field(..., description='Canonical URN spec identifier')`
- `execution_graph: Dict[str, Any] = Field(default_factory=dict, description='DAG execution graph configuration')`

```python
class SpecificationUpsertRequest(BaseModel):
```
**Fields / Attributes:**
- `urn: str = Field(..., description='Canonical URN spec identifier')`
- `namespace: str`
- `component_name: str`
- `version: str`
- `specification_manifest: Dict[str, Any]`
- `checksum_sha256: str`

#### Top-Level Functions

```python
def get_repository() -> EntityRepository
```
```python
def get_mutator() -> DatabaseMutator
```
```python
def get_orchestrator() -> BuildOrchestrator
```
```python
async def create_build_job(request: BuildJobRequest, orchestrator: BuildOrchestrator = Depends(get_orchestrator)) -> BuildJobAuditRecord
```
> Triggers a build execution job given a manifest URN and execution topology.

```python
async def get_build_job(job_id: UUID, repository: EntityRepository = Depends(get_repository)) -> BuildJobAuditRecord
```
> Retrieves audit state for a target build job by UUID.

```python
async def list_build_job_events(job_id: UUID, repository: EntityRepository = Depends(get_repository)) -> List[BuildJobEventRecord]
```
> Retrieves execution events for a build job in chronological order.

```python
async def get_specification(urn: str, repository: EntityRepository = Depends(get_repository)) -> SpecificationRecord
```
> Fetches a specification manifest record by canonical URN.

```python
async def upsert_specification(request: SpecificationUpsertRequest, mutator: DatabaseMutator = Depends(get_mutator)) -> SpecificationRecord
```
> Registers or updates a specification manifest record in the repository.

### File: `src/meta_builder_brain/config.py`

#### Classes & Models

```python
class BrainSettings(MetaBaseSettings):
```
> Centralized configuration for meta_builder_brain loaded via meta-config.

**Fields / Attributes:**
- `DATABASE_URL: str = Field(default='postgresql+asyncpg://postgres:postgres@localhost:5432/meta_brain', description='Async PostgreSQL database URL', validation_alias=AliasChoices('BRAIN_DATABASE_URL', 'DATABASE_URL'))`
- `OPA_SIDECAR_URL: str = Field(default='http://localhost:8181/v1/data', description='Open Policy Agent sidecar endpoint URL', validation_alias=AliasChoices('BRAIN_OPA_SIDECAR_URL', 'OPA_SIDECAR_URL'))`
- `BCR_URN_PREFIX: str = Field(default='urn:meta:bcr:', description='URN prefix for Blueprint Component Registry entities', validation_alias=AliasChoices('BRAIN_BCR_URN_PREFIX', 'BCR_URN_PREFIX'))`
- `ENVIRONMENT: str = Field(default='production', description='Deployment environment name', validation_alias=AliasChoices('BRAIN_ENVIRONMENT', 'ENVIRONMENT'))`
- `LOG_LEVEL: str = Field(default='INFO', description='Application logging verbosity level', validation_alias=AliasChoices('BRAIN_LOG_LEVEL', 'LOG_LEVEL'))`
- `OPENBAO_URL: Optional[str] = Field(default=None, description='OpenBao secrets server endpoint URL', validation_alias=AliasChoices('BRAIN_OPENBAO_URL', 'OPENBAO_URL'))`
- `OPENBAO_TOKEN: Optional[str] = Field(default=None, description='Authentication token for OpenBao secrets server', validation_alias=AliasChoices('BRAIN_OPENBAO_TOKEN', 'OPENBAO_TOKEN'))`

**Methods:**
```python
def database_url(self) -> str
```
```python
def opa_sidecar_url(self) -> str
```
```python
def bcr_urn_prefix(self) -> str
```
```python
def environment(self) -> str
```
```python
def log_level(self) -> str
```
#### Top-Level Functions

```python
def bootstrap_configuration() -> BrainSettings
```
> Bootstraps application settings with error handling for misconfigurations.

### File: `src/meta_builder_brain/dag_engine.py`

#### Classes & Models

```python
class DAGGraph(NamedTuple):
```
**Fields / Attributes:**
- `execution_order: List[str]`

```python
class TreeResolver:
```
> Resolves component dependency trees and validates URN formats.

**Methods:**
```python
def validate_urn(urn: str) -> Dict[str, str]
```
> Validates and parses standard blueprint URNs (urn:meta:bcr:<namespace>:<component>:<version>).

```python
def build_and_validate_dag(cls, components: Dict[str, List[str]]) -> DAGGraph
```
> Validates component URNs and builds dependency graph to return execution order.

```python
class ComponentDAGEngine:
```
> Manages dependency topological sorting and lineage graphs for blueprint components.

**Methods:**
```python
def __init__(self) -> None
```
```python
def add_component(self, component_urn: str, dependencies: List[str]) -> None
```
> Adds a component node and its directed dependency edges to the graph.

```python
def compute_execution_order(self) -> List[str]
```
> Computes topological execution order for dependency processing.

```python
def get_upstream_dependencies(self, component_urn: str) -> Set[str]
```
> Retrieves all transitive upstream dependency URNs for a target component.

### File: `src/meta_builder_brain/exceptions.py`

#### Classes & Models

```python
class MetaBuilderBrainError(Exception):
```
> Base exception class for all domain-specific errors in Meta Builder Brain.

**Methods:**
```python
def __init__(self, message: str, payload: Optional[Any] = None) -> None
```
```python
class ConfigurationError(MetaBuilderBrainError):
```
> Raised when application configuration bootstrapping or OpenBao secret loading fails.

```python
class TelemetryInitError(MetaBuilderBrainError):
```
> Raised when telemetry or structured logging initialization fails.

```python
class DAGEngineError(MetaBuilderBrainError):
```
> Base exception for Directed Acyclic Graph execution and topology failures.

```python
class DAGCycleError(DAGEngineError):
```
> Raised when a cyclic dependency is detected within component graph topology.

```python
class DAGNodeNotFoundError(DAGEngineError):
```
> Raised when a target component or URN node is missing from the DAG.

```python
class EmptyDAGError(DAGEngineError):
```
> Raised when an operation is executed on a DAG containing no node components.

```python
class InvalidURNError(DAGEngineError):
```
> Raised when a URN string does not match the expected URN specification format.

```python
class LineageResolutionError(MetaBuilderBrainError):
```
> Raised when lineage closure or multi-tenant graph lookup fails.

```python
class GovernancePolicyError(MetaBuilderBrainError):
```
> Base exception for Open Policy Agent and governance validation failures.

```python
class GovernancePolicyViolationError(GovernancePolicyError):
```
> Raised when an entity specification or FSM state transition violates policy rules.

```python
class OPAPolicyValidationError(GovernancePolicyViolationError):
```
> Raised when OPA policy validation checks fail or deny execution.

```python
class OPAServiceUnavailableError(GovernancePolicyError):
```
> Raised when the OPA sidecar HTTP engine times out, drops connection, or returns 5xx.

```python
class PersistenceError(MetaBuilderBrainError):
```
> Base exception for database access and transaction failures.

```python
class DatabaseConnectionError(PersistenceError):
```
> Raised when database connectivity drops or connection pooling fails.

```python
class EntityNotFoundError(PersistenceError):
```
> Raised when a requested entity URN or primary key record does not exist.

```python
class DuplicateURNError(PersistenceError):
```
> Raised when inserting an entity URN that violates unique primary key constraints.

```python
class TransactionRollbackError(PersistenceError):
```
> Raised when an active database transaction fails and undergoes rollback.

```python
class UnsupportedTypeMappingError(PersistenceError):
```
> Raised when an unknown or unsupported field type mapping is encountered during dynamic ORM/schema mapping.

```python
class CASLockError(PersistenceError):
```
> Raised when optimistic concurrency fence token validation fails.

```python
class IdempotencyError(PersistenceError):
```
> Raised when duplicate processing is detected on an active key.

```python
class IdempotencyConflictError(IdempotencyError):
```
> Raised when a concurrent operation or key collision violates idempotency guarantees.

```python
class SagaError(PersistenceError):
```
> Raised when saga transaction verification fails.

```python
class MigrationError(PersistenceError):
```
> Raised when database migration execution fails.

```python
class IngestionError(MetaBuilderBrainError):
```
> Base exception for external document parsing and ingestion pipelines.

```python
class HermesSynthesisError(IngestionError):
```
> Raised when RFC text parsing fails to synthesize valid schema representations.

```python
class BuildExecutionError(MetaBuilderBrainError):
```
> Raised when build job orchestration or compiler execution encounters an unrecoverable failure.

### File: `src/meta_builder_brain/governance/opa.py`

#### Classes & Models

```python
class OPAEvaluator:
```
> HTTP sidecar client for evaluating Rego policy contracts.

**Methods:**
```python
def __init__(self, settings: BrainSettings) -> None
```
```python
async def evaluate_policy(self, policy_path: str, input_data: Dict[str, Any]) -> Dict[str, Any]
```
> Posts evaluation payload to local OPA sidecar endpoint.

```python
async def validate_component_governance(self, component_urn: str, payload: Dict[str, Any]) -> bool
```
> Validates component specification against governance rules.

### File: `src/meta_builder_brain/ingestion/hermes.py`

#### Classes & Models

```python
class HermesSynthesisAgent:
```
> Agent for synthesizing canonical JSON schemas from raw RFC text specs.

**Methods:**
```python
async def synthesize_rfc_spec(self, raw_rfc_text: str) -> Dict[str, Any]
```
> Parses RFC text and builds a canonical JSON schema object.

### File: `src/meta_builder_brain/ingestion/scraper.py`

#### Classes & Models

```python
class ScraperError(Exception):
```
> Raised when Playwright headless retrieval fails.

```python
class PlaywrightSchemaScraper:
```
> Headless browser scraping pipeline for OpenAPI endpoint and documentation retrieval.

**Methods:**
```python
async def scrape_openapi_spec(self, url: str) -> Dict[str, Any]
```
### File: `src/meta_builder_brain/lineage/cache.py`

#### Classes & Models

```python
class CacheGuard:
```
> Thread-safe and async-safe in-memory cache for precomputed graph lineage outcomes[cite: 1].

**Methods:**
```python
def __init__(self) -> None
```
```python
async def get(self, key: str) -> Optional[Any]
```
```python
async def set(self, key: str, value: Any) -> None
```
```python
async def invalidate(self, key: str) -> None
```
```python
async def clear(self) -> None
```
### File: `src/meta_builder_brain/lineage/closure.py`

#### Classes & Models

```python
class LineageClosureResolver:
```
> Resolves transitive ancestor and descendant relationships within component DAGs.

**Methods:**
```python
def __init__(self, repository: Any = None, mutator: Optional[DatabaseMutator] = None) -> None
```
```python
async def register_relation(self, ancestor_id: str, descendant_id: str, depth: int = 1) -> None
```
> Registers a directional lineage relation between an ancestor and descendant.

```python
async def resolve_ancestors(self, descendant_id: str) -> List[str]
```
> Resolves all transitive ancestors for the specified descendant entity.

### File: `src/meta_builder_brain/main.py`

#### Classes & Models

```python
class ApplicationContainer:
```
> Lifecycle container holding initialized services and persistence components.

**Methods:**
```python
def __init__(self, pool_manager: DatabasePoolManager, repository: EntityRepository, mutator: DatabaseMutator, orchestrator: BuildOrchestrator, lineage_resolver: LineageClosureResolver) -> None
```
```python
class RawIngestRequest(BaseModel):
```
**Fields / Attributes:**
- `namespace_id: str`
- `component_name: str`
- `version: str`
- `raw_schema: Dict[str, Any]`

```python
class RFCIngestRequest(BaseModel):
```
**Fields / Attributes:**
- `raw_rfc_text: str`
- `namespace_id: str`

```python
class CompileNamespaceRequest(BaseModel):
```
**Fields / Attributes:**
- `components: Dict[str, Any] = Field(default_factory=dict)`
- `spec_deltas: Dict[str, Any] = Field(default_factory=dict)`
- `base_schemas: Dict[str, Any] = Field(default_factory=dict)`

#### Top-Level Functions

```python
async def bootstrap_application(dsn: str = DATABASE_DSN) -> ApplicationContainer
```
> Bootstraps pool manager, executes DDL, and builds dependency tree.

```python
async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]
```
> FastAPI lifespan context manager controlling application container lifecycle.

```python
async def ingest_raw_schema(payload: RawIngestRequest) -> Dict[str, Any]
```
> Ingests raw JSON schema definitions and generates canonical BCR URN.

```python
async def ingest_rfc(payload: RFCIngestRequest) -> Dict[str, Any]
```
> Ingests raw RFC document text for synthesis.

```python
async def compile_namespace(namespace_id: str, payload: CompileNamespaceRequest) -> Dict[str, Any]
```
> Triggers DAG compilation for a target blueprint namespace.

```python
async def main() -> None
```
> Main application runtime entrypoint.

### File: `src/meta_builder_brain/orchestrator.py`

#### Classes & Models

```python
class BuildOrchestrator:
```
> Coordinates schema resolution, compilation execution, OPA evaluation, and persistence updates.

**Methods:**
```python
def __init__(self, repository: Any = None, mutator: Optional[DatabaseMutator] = None, compiler: Optional[MetaCompiler] = None) -> None
```
```python
async def compile_blueprint_namespace(self, namespace_id: str, components: Dict[str, Any], spec_deltas: Dict[str, Any], base_schemas: Dict[str, Any], job_id: Optional[str] = None, session: Any = None) -> Dict[str, Any]
```
> Compiles blueprint component namespace schemas and validates governance policy.

```python
async def execute_build_job(self, tenant_id: str, manifest_urn: str, execution_graph: Dict[str, Any]) -> BuildJobAuditRecord
```
> Executes a build pipeline step-by-step with persistence auditing.

### File: `src/meta_builder_brain/persistence/mbb_models.py`

#### Classes & Models

```python
class BuildJobStatus(str, Enum):
```
```python
class IdempotencyStatus(str, Enum):
```
```python
class SpecificationRecord(BaseModel):
```
**Fields / Attributes:**
- `urn: str = Field(..., description='Canonical URN spec identifier')`
- `namespace: str`
- `component_name: str`
- `version: str`
- `specification_manifest: Dict[str, Any]`
- `checksum_sha256: str`
- `created_at: Optional[datetime] = None`
- `updated_at: Optional[datetime] = None`

```python
class BuildJobAuditRecord(BaseModel):
```
**Fields / Attributes:**
- `job_id: UUID`
- `tenant_id: str`
- `status: BuildJobStatus`
- `manifest_urn: str`
- `execution_graph: Dict[str, Any]`
- `error_message: Optional[str] = None`
- `started_at: Optional[datetime] = None`
- `completed_at: Optional[datetime] = None`
- `created_at: Optional[datetime] = None`
- `updated_at: Optional[datetime] = None`

```python
class BuildJobEventRecord(BaseModel):
```
**Fields / Attributes:**
- `event_id: UUID`
- `job_id: UUID`
- `event_type: str`
- `payload: Dict[str, Any]`
- `created_at: Optional[datetime] = None`

```python
class ArtifactManifestRecord(BaseModel):
```
**Fields / Attributes:**
- `artifact_id: UUID`
- `job_id: UUID`
- `urn: str`
- `artifact_type: str`
- `location_uri: str`
- `checksum_sha256: str`
- `created_at: Optional[datetime] = None`

```python
class LineageClosureRecord(BaseModel):
```
**Fields / Attributes:**
- `ancestor_urn: str`
- `descendant_urn: str`
- `path_length: int`
- `generation_id: int`
- `is_active: bool = False`
- `created_at: Optional[datetime] = None`

```python
class IdempotencyRecord(BaseModel):
```
**Fields / Attributes:**
- `idempotency_key: str`
- `status: IdempotencyStatus`
- `response_payload: Optional[Dict[str, Any]] = None`
- `created_at: Optional[datetime] = None`
- `updated_at: Optional[datetime] = None`
- `expires_at: datetime`

### File: `src/meta_builder_brain/persistence/mbb_mutator.py`

#### Classes & Models

```python
class DatabaseMutator:
```
> Write-only persistence layer handling mutation statements and transactional blocks.

**Methods:**
```python
def __init__(self, pool: asyncpg.Pool) -> None
```
```python
async def upsert_specification(self, record: SpecificationRecord) -> SpecificationRecord
```
> Upserts a specification manifest into the registry.

```python
async def record_build_audit(self, job_id: UUID, tenant_id: str, status: BuildJobStatus, manifest_urn: str, execution_graph: Dict[str, Any]) -> BuildJobAuditRecord
```
> Creates an initial build job audit record.

```python
async def update_build_status(self, job_id: UUID, status: BuildJobStatus, error_message: Optional[str] = None, completed_at: Optional[datetime] = None) -> None
```
> Updates status and completion state of an active build job.

```python
async def record_job_event(self, job_id: UUID, event_type: str, payload: Dict[str, Any]) -> BuildJobEventRecord
```
> Appends a discrete progress or diagnostic event to a build job log.

```python
async def save_artifact_manifest(self, artifact_id: UUID, job_id: UUID, urn: str, artifact_type: str, location_uri: str, checksum_sha256: str) -> ArtifactManifestRecord
```
> Persists metadata manifest for a generated build artifact.

```python
async def batch_insert_lineage_closures_and_swap_generation(self, generation_id: int, closures: List[LineageClosureRecord]) -> None
```
> Atomically inserts batch closure paths and toggles current active generation ID.

```python
async def create_idempotency_key(self, key: str, expires_at: datetime) -> bool
```
> Atomic Compare-And-Set key creation for idempotent execution guard.

```python
async def complete_idempotency_key(self, key: str, payload: Dict[str, Any]) -> None
```
> Marks an active idempotency token as completed with its response payload.

```python
async def cleanup_expired_idempotency_keys(self) -> int
```
> Deletes expired idempotency tokens from the database.

### File: `src/meta_builder_brain/persistence/mbb_pool.py`

#### Classes & Models

```python
class DatabasePoolManager:
```
> Manages the asyncpg connection pool lifecycle and schema DDL initialization.

**Methods:**
```python
def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20, command_timeout: float = 60.0) -> None
```
```python
async def init_pool(self) -> None
```
> Initializes the underlying asyncpg connection pool.

```python
async def close_pool(self) -> None
```
> Gracefully terminates all active connections in the pool.

```python
def get_pool(self) -> asyncpg.Pool
```
> Retrieves the active asyncpg connection pool instance.

```python
async def execute_ddl(self, schema_file_path: str) -> None
```
> Executes raw DDL statements from an external SQL file to bootstrap schema.

```python
async def execute_migrations(self, alembic_ini_path: str) -> None
```
> Programmatically runs Alembic database migrations to upgrade head.

### File: `src/meta_builder_brain/persistence/mbb_repository.py`

#### Classes & Models

```python
class EntityRepository:
```
> Read-only data access repository for hydrating domain entity records.

**Methods:**
```python
def __init__(self, pool: asyncpg.Pool) -> None
```
```python
async def get_specification(self, urn: str) -> Optional[SpecificationRecord]
```
> Fetches a single specification record by canonical URN.

```python
async def list_specifications(self, namespace: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[SpecificationRecord]
```
> Lists specification records with optional filtering by namespace.

```python
async def get_build_job(self, job_id: UUID) -> Optional[BuildJobAuditRecord]
```
> Fetches a build job audit record by UUID.

```python
async def get_build_job_events(self, job_id: UUID) -> List[BuildJobEventRecord]
```
> Fetches all events associated with a build job in chronological order.

```python
async def get_artifact_manifests(self, job_id: UUID) -> List[ArtifactManifestRecord]
```
> Fetches generated artifact manifests for a given build job.

```python
async def get_active_closure_descendants(self, ancestor_urn: str, generation_id: Optional[int] = None) -> List[LineageClosureRecord]
```
> Executes closure lookup query for descendant components of a given ancestor URN.

```python
async def get_idempotency_record(self, idempotency_key: str) -> Optional[IdempotencyRecord]
```
> Retrieves active idempotency record by key.

### File: `src/meta_builder_brain/persistence/models.py`

#### Classes & Models

```python
class Base(DeclarativeBase):
```
> Declarative base class for dynamically generated and static ORM models.

```python
class SpecificationsRegistry(Base):
```
```python
class BuildJobAudit(Base):
```
```python
class BuildJobEvents(Base):
```
```python
class ArtifactManifests(Base):
```
### File: `src/meta_builder_brain/persistence/orm_builder.py`

#### Classes & Models

```python
class DynamicMetaclassBuilder:
```
> Factory for dynamically creating SQLAlchemy ORM models from schema properties at runtime.

**Fields / Attributes:**
- `TYPE_MAP: Dict[str, Callable[[], TypeEngine[Any]]] = {'string': lambda: String(255), 'integer': Integer, 'json': JSON, 'boolean': Boolean, 'datetime': DateTime, 'float': Float}`

**Methods:**
```python
def create_orm_model(cls, class_name: str, table_name: str, fields: Dict[str, Any], base_class: Type[DeclarativeBase]) -> Type[DeclarativeBase]
```
> Dynamically generates a SQLAlchemy ORM mapped class from field specifications.

### File: `src/meta_builder_brain/telemetry.py`

#### Top-Level Functions

```python
def setup_telemetry(log_level: str = 'INFO', log_file_path: Optional[str] = None) -> None
```
> Configures root logger handlers and formatting with fallback recovery.

```python
def with_trace(span_name: str) -> Callable[[F], F]
```
> Decorator wrapping functions in a telemetry trace span.

### File: `tests/conftest.py`

#### Top-Level Functions

```python
def mock_settings() -> BrainSettings
```
> Provides test application settings instance.

```python
async def async_session() -> AsyncGenerator[AsyncSession, None]
```
> Provides an isolated, in-memory SQLAlchemy AsyncSession per test.

```python
def mock_pg_connection() -> AsyncMock
```
> Mocks an individual asyncpg connection object with context managers and query methods.

```python
def mock_pg_pool(mock_pg_connection: AsyncMock) -> AsyncMock
```
> Mocks an asyncpg.Pool handling pool.acquire() context management.

```python
def entity_repository(mock_pg_pool: AsyncMock) -> EntityRepository
```
> Provides an EntityRepository instance backed by the mocked asyncpg connection pool.

```python
def database_mutator(mock_pg_pool: AsyncMock) -> DatabaseMutator
```
> Provides a DatabaseMutator instance backed by the mocked asyncpg connection pool.

```python
def sample_urns() -> Dict[str, str]
```
> Provides standard sample component URN strings for test assertions.

```python
def sample_dag_components(sample_urns: Dict[str, str]) -> Dict[str, List[str]]
```
> Provides sample DAG dependency mappings for topology testing.

### File: `tests/test_api_routes.py`

#### Top-Level Functions

```python
async def test_ingest_raw_schema()
```
```python
async def test_ingest_rfc()
```
```python
async def test_compile_namespace_route()
```
### File: `tests/test_config_and_telemetry.py`

#### Top-Level Functions

```python
def test_brain_settings_defaults()
```
```python
def test_bootstrap_configuration_success()
```
```python
def test_bootstrap_configuration_failure()
```
```python
def test_setup_telemetry(tmp_path)
```
```python
def test_with_trace_decorator()
```
### File: `tests/test_dag_engine.py`

#### Top-Level Functions

```python
def test_validate_urn_success()
```
```python
def test_validate_urn_failure()
```
```python
def test_build_and_validate_dag_success()
```
```python
def test_build_and_validate_dag_cycle_detected()
```
### File: `tests/test_governance_opa.py`

#### Top-Level Functions

```python
async def test_opa_evaluate_policy_allow(mock_settings: BrainSettings)
```
```python
async def test_opa_evaluate_policy_deny(mock_settings: BrainSettings)
```
### File: `tests/test_ingestion.py`

#### Top-Level Functions

```python
async def test_hermes_synthesis_agent_success()
```
```python
async def test_hermes_synthesis_agent_empty_input()
```
```python
async def test_playwright_schema_scraper_success()
```
```python
async def test_playwright_schema_scraper_http_error()
```
### File: `tests/test_lineage_and_cache.py`

#### Top-Level Functions

```python
async def test_cache_guard_operations()
```
```python
async def test_lineage_closure_resolver(async_session: AsyncSession)
```
### File: `tests/test_negative_scenarios.py`

#### Top-Level Functions

```python
def test_config_bootstrap_failure()
```
```python
def test_telemetry_invalid_log_level()
```
```python
def test_telemetry_file_permission_denied()
```
```python
def test_dag_empty_execution()
```
```python
def test_dag_cyclical_dependency()
```
```python
def test_dag_missing_node_queries()
```
```python
async def test_opa_service_unreachable(mock_settings: BrainSettings)
```
```python
async def test_opa_policy_denial(mock_settings: BrainSettings)
```
```python
def test_orm_builder_empty_class_name()
```
```python
def test_orm_builder_unsupported_type()
```
```python
def test_orm_builder_invalid_field_format()
```
```python
async def test_hermes_empty_payload()
```
```python
async def test_hermes_unparseable_text()
```
### File: `tests/test_orchestrator.py`

#### Top-Level Functions

```python
async def test_orchestrator_compile_namespace_success(mock_settings: BrainSettings, async_session: AsyncSession)
```
### File: `tests/test_persistence.py`

#### Top-Level Functions

```python
async def test_specifications_registry_crud(async_session: AsyncSession)
```
```python
async def test_build_job_audit_events_relationship(async_session: AsyncSession)
```
```python
def test_dynamic_metaclass_builder_synthesis()
```
## Library: `meta-telemetry`

### File: `src/meta_telemetry/exceptions.py`

#### Classes & Models

```python
class TelemetryError(Exception):
```
> Base exception for all meta_telemetry domain errors.

**Methods:**
```python
def to_dict(self) -> dict[str, Any]
```
> Returns structured metadata for agentic error triage.

```python
class SpanExtractionError(TelemetryError):
```
> Raised when attribute extraction for an OpenTelemetry span fails.

**Methods:**
```python
def __init__(self, message: str, function_name: Optional[str] = None, original_exception: Optional[Exception] = None) -> None
```
```python
def to_dict(self) -> dict[str, Any]
```
> Returns structured metadata for agentic error triage.

```python
class LoggingFormattingError(TelemetryError):
```
> Raised when JSON formatting of a log record fails.

**Methods:**
```python
def __init__(self, message: str, log_record_name: str, original_exception: Optional[Exception] = None) -> None
```
```python
def to_dict(self) -> dict[str, Any]
```
> Returns structured metadata for agentic error triage.

### File: `src/meta_telemetry/logging.py`

#### Classes & Models

```python
class DateSeqRotatingFileHandler(BaseRotatingHandler):
```
> File handler writing to an active date-stamped log file and shifting full logs

downward into versioned archives (_v1.log = prev current, _v2.log = prev prev current).

File Naming Rules:
- Active log:        {app_name}_{DDMMYY_HHMMSS}.log
- Most recent prev:  {app_name}_{DDMMYY_HHMMSS}_v1.log
- Older archives:    {app_name}_{DDMMYY_HHMMSS}_v2.log ... _v{N}.log

**Methods:**
```python
def __init__(self, base_dir: str | Path, app_name: str = 'meta_app', max_bytes: int = DEFAULT_MAX_BYTES, backup_count: int = 5, encoding: str = 'utf-8', delay: bool = False, date_format: str = '%d%m%y_%H%M%S', use_utc: bool = True) -> None
```
```python
def shouldRollover(self, record: logging.LogRecord) -> bool
```
> Determines if a rollover is required due to date boundary change or file size.

```python
def doRollover(self) -> None
```
> Executes downward log cascade safely.

```python
class StructuredJsonFormatter(logging.Formatter):
```
> Formatter outputting JSON logs enriched with trace_id, span_id, and service metadata.

**Methods:**
```python
def __init__(self, service_name: str = 'meta_service', environment: str = 'production', fmt: Optional[str] = None, datefmt: Optional[str] = None) -> None
```
```python
def format(self, record: logging.LogRecord) -> str
```
> Formats a standard logging record into a structured JSON string.

### File: `src/meta_telemetry/tracing.py`

#### Top-Level Functions

```python
def get_tracer(name: str = 'meta_telemetry') -> Tracer
```
> Retrieves an OpenTelemetry tracer instance from the global provider.

```python
def trace_span(name: Optional[str] = None, extract_attributes: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None, tracer_name: str = 'meta_telemetry') -> Callable[[F], F]
```
> Parametrized decorator wrapping sync and async functions in OpenTelemetry trace spans.

Args:
    name: Optional explicit name for the span. Defaults to qualified function name.
    extract_attributes: Callable accepting bound function arguments and returning span attributes.
    tracer_name: Name of the tracer instance to retrieve.

### File: `tests/test_date_seq_handler.py`

#### Top-Level Functions

```python
def test_timestamped_date_seq_cascade(tmp_path: Path)
```
### File: `tests/test_logging.py`

#### Top-Level Functions

```python
def test_structured_json_formatter_basic()
```
```python
def test_structured_json_formatter_with_extra_and_non_serializable()
```
```python
def test_structured_json_formatter_injects_otel_trace_context()
```
```python
def test_timestamped_date_seq_cascade(tmp_path: Path)
```
### File: `tests/test_tracing.py`

#### Top-Level Functions

```python
def clear_spans()
```
```python
def test_sync_trace_span_decorator_success()
```
```python
def test_sync_trace_span_decorator_exception_handling()
```
```python
async def test_async_trace_span_decorator_success()
```
```python
def test_trace_span_handles_extraction_failure_gracefully()
```
## Library: `meta-security`

### File: `src/meta_security/claims.py`

#### Classes & Models

```python
class TokenClaims(BaseModel):
```
> Immutable representation of validated identity token claims.

**Fields / Attributes:**
- `sub: StrictStr = Field(..., description='Subject identifier (e.g., user UUID)')`
- `exp: StrictInt = Field(..., description='Expiration timestamp in epoch seconds')`
- `iss: StrictStr | None = Field(default=None, description='Token Issuer')`
- `aud: StrictStr | tuple[StrictStr, ...] | None = Field(default=None, description='Intended audience')`
- `roles: tuple[StrictStr, ...] = Field(default_factory=tuple, description='List of RBAC roles assigned to subject')`
- `tenant_id: StrictStr | None = Field(default=None, description='Associated tenant scope, if applicable')`

**Methods:**
```python
def is_service_account(self) -> bool
```
> Helper to determine if the claims belong to a machine-to-machine context.

### File: `src/meta_security/exceptions.py`

#### Classes & Models

```python
class MetaSecurityError(Exception):
```
> Base exception for all meta-security errors.

**Methods:**
```python
def __init__(self, message: str, context: dict[str, Any] | None = None) -> None
```
```python
class TokenValidationError(MetaSecurityError):
```
> Raised when token signature validation or verification fails.

```python
class ClaimExtractionError(MetaSecurityError):
```
> Raised when the parsed token lacks required fields or fails schema coercion.

```python
class PolicyViolationError(MetaSecurityError):
```
> Raised when a validated identity fails to satisfy the required authorization policy.

### File: `src/meta_security/policy.py`

#### Top-Level Functions

```python
def require_roles(required_roles: list[str]) -> Callable[[F], F]
```
> Decorator to enforce strictly defined RBAC roles on a function executing with a validated identity.

Expects the wrapped function to accept a `claims` parameter of type TokenClaims.

### File: `src/meta_security/tokens.py`

#### Classes & Models

```python
class SecuritySettings(MetaBaseSettings):
```
> Configuration constraints for cryptographic validation. Inherits boot-halting properties.

**Fields / Attributes:**
- `jwt_public_key: SecretStr = Field(..., description='PEM encoded public key for signature verification')`
- `jwt_algorithms: tuple[str, ...] = Field(default=('RS256',), description='Permitted cryptographic algorithms')`
- `jwt_issuer: str | None = Field(default=None, description='Required issuer validation (if set)')`
- `jwt_audience: str | None = Field(default=None, description='Required audience validation (if set)')`
- `openbao_path: ClassVar[str] = 'secret/data/backend/security'`

#### Top-Level Functions

```python
def validate_token(token: str, settings: SecuritySettings) -> TokenClaims
```
> Validate a raw JWT and extract it into a strongly-typed TokenClaims object.

:param token: Raw encoded JWT string.
:param settings: Validated SecuritySettings instance.
:return: Immutable TokenClaims object.
:raises TokenValidationError: If cryptography fails (e.g., expired, invalid signature).
:raises ClaimExtractionError: If schema validation on the claims payload fails.
