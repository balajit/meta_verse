# Public Custom Libraries Specification Summary

## Library: `meta-service-generator`

### File: `scripts/msg_driver.py`

#### Classes & Models

```python
class ServiceGeneratorDriver:
```
> Driver class containing a comprehensive, multi-domain sample manifest
exercising CRUD, FSM states, business rules, workflows, policies, and extensions.

**Methods:**
```python
def get_comprehensive_manifest() -> dict
```
```python
def run_pipeline(cls) -> None
```
### File: `src/meta_service_generator/analysis/compatibility.py`

#### Classes & Models

```python
class ViolationSeverity(StrEnum):
```
> Severity classification for schema compatibility violations [source: 3].

```python
class FieldDefinitionSpec(BaseModel):
```
> Specification of a single schema field for compatibility analysis [source: 3].

**Fields / Attributes:**
- `name: str = Field(..., min_length=1, description='Field attribute name.')`
- `type_name: str = Field(..., min_length=1, description='Python or OpenAPI type string representation.')`
- `is_nullable: bool = Field(default=False, description='Indicates whether None is a valid value.')`
- `has_default: bool = Field(default=False, description='Indicates whether a default value is supplied.')`
- `default_value: Any = Field(default=None, description='The default value if present.')`

```python
class SchemaManifestSpec(BaseModel):
```
> Manifest representing a complete versioned entity schema [source: 3].

**Fields / Attributes:**
- `schema_id: str = Field(..., min_length=1, description='Unique entity identifier.')`
- `version: str = Field(..., min_length=1, description='Semantic version string of the schema.')`
- `fields: tuple[FieldDefinitionSpec, ...] = Field(default=(), description='Immutable collection of field specifications.')`
- `polymorphic_discriminator: str | None = Field(default=None, description='Discriminator field name for meta_polymorph routing.')`

```python
class CompatibilityViolation(BaseModel):
```
> Detailed record of a single compatibility violation [source: 3].

**Fields / Attributes:**
- `severity: ViolationSeverity = Field(..., description='Severity level of the violation.')`
- `field_name: str = Field(..., min_length=1, description='Target field associated with the violation.')`
- `issue_type: str = Field(..., min_length=1, description='Categorical key describing the flaw type.')`
- `description: str = Field(..., min_length=1, description='Human-readable explanation of the incompatibility.')`
- `suggested_resolution: str = Field(..., min_length=1, description='Actionable recommendation for resolving the violation.')`

```python
class CompatibilityReport(BaseModel):
```
> Summary report produced by the schema compatibility analyzer [source: 3].

**Fields / Attributes:**
- `is_compatible: bool = Field(..., description='True if no CRITICAL violations exist.')`
- `source_version: str = Field(..., min_length=1, description='Original schema version string.')`
- `target_version: str = Field(..., min_length=1, description='Evolved schema version string.')`
- `violations: tuple[CompatibilityViolation, ...] = Field(default=(), description='Immutable collection of detected compatibility violations.')`

```python
class SchemaCompatibilityAnalyzer:
```
> Evaluates backwards compatibility between schema versions to prevent
breaking API changes, field type mismatches, and polymorphic dispatch failures [source: 3].

**Methods:**
```python
def analyze(self, source_schema: SchemaManifestSpec, target_schema: SchemaManifestSpec) -> CompatibilityReport
```
> Compares a source schema against an evolved target schema and returns a CompatibilityReport [source: 3].

#### Top-Level Functions

```python
def enforce_compatibility(source_schema: SchemaManifestSpec, target_schema: SchemaManifestSpec) -> CompatibilityReport
```
> Convenience function that evaluates compatibility and raises CodeGenerationError if critical violations exist [source: 3].

### File: `src/meta_service_generator/analysis/cycles.py`

#### Classes & Models

```python
class CycleAnalyzer:
```
> Detects dependency loops and evaluates if circular entity references are resolvable [source: 3].

**Methods:**
```python
def __init__(self, graph: RelationshipGraph) -> None
```
```python
def analyze(self) -> dict[str, bool]
```
> Returns a mapping of entity_name -> is_in_circular_dependency.
Raises IRBuilderError if an unresolvable mutual non-nullable loop exists [source: 3].

### File: `src/meta_service_generator/analysis/relationships.py`

#### Classes & Models

```python
class RelationshipEdge:
```
> Immutable directional relationship edge used by graph analysis.

**Fields / Attributes:**
- `source_entity: str`
- `target_entity: str`
- `cardinality: str`
- `foreign_key: str | None`
- `foreign_key_nullable: bool`
- `relationship_name: str`

```python
class RelationshipGraph:
```
> Builds and manages directional relationship adjacency lists for entities [source: 3].

**Methods:**
```python
def __init__(self, manifest: ManifestSpec) -> None
```
```python
def adjacency(self) -> dict[str, frozenset[str]]
```
> Return a read-only snapshot of the graph adjacency structure.

```python
def edges(self) -> tuple[RelationshipEdge, ...]
```
> Return immutable relationship edges.

```python
def get_dependencies(self, entity_name: str) -> frozenset[str]
```
> Return immutable dependency targets for an entity.

```python
def get_outgoing_edges(self, entity_name: str) -> tuple[RelationshipEdge, ...]
```
> Return all outgoing relationship edges for an entity.

```python
def get_edge(self, source_entity: str, target_entity: str) -> RelationshipEdge | None
```
> Return a matching relationship edge, if one exists.

### File: `src/meta_service_generator/analysis/validation.py`

#### Classes & Models

```python
class IRSemanticValidator:
```
> Performs deep semantic validation on ServiceIR prior to code synthesis [source: 3].

**Methods:**
```python
def validate(self, service_ir: ServiceIR) -> None
```
> Executes all semantic IR checks and halts generation on any invariant violation.

### File: `src/meta_service_generator/cli.py`

#### Top-Level Functions

```python
def generate_command(manifest: Annotated[Path, typer.Option('--manifest', '-m', help='Path to input JSON or YAML service manifest.', exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True)], output_dir: Annotated[Path, typer.Option('--output-dir', '-o', help='Directory path where synthesized service files will be emitted.', resolve_path=True)], json_diagnostics: Annotated[bool, typer.Option('--json-diagnostics', help='Emit errors strictly using REQ-030 JSON structure.')] = False) -> None
```
> Generates a zero-modification FastAPI service from a valid manifest.

```python
def verify_command(project_dir: Annotated[Path, typer.Option('--project-dir', '-p', help='Path to generated microservice project directory.', exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True)], json_diagnostics: Annotated[bool, typer.Option('--json-diagnostics', help='Emit errors strictly using REQ-030 JSON structure.')] = False) -> None
```
> Executes Stage 6 readiness verification suite against a target service.

```python
def schema_command(export: Annotated[Path, typer.Option('--export', '-e', help='File path to export JSON Schema definition.', resolve_path=True)], json_diagnostics: Annotated[bool, typer.Option('--json-diagnostics', help='Emit errors strictly using REQ-030 JSON structure.')] = False) -> None
```
> Exports the Draft 2020-12 manifest schema specification[cite: 2].

### File: `src/meta_service_generator/config.py`

#### Classes & Models

```python
class GeneratorSettings(MetaBaseSettings):
```
> Immutable framework configuration managing emission paths, strictness flags,
formatting preferences, and diagnostic outputs.

**Fields / Attributes:**
- `target_emission_path: Path = Field(default=Path('./output'), description='Target directory for synthesized FastAPI service source files.')`
- `strictness_flags: dict[str, bool] = Field(default_factory=lambda: {'enforce_strict_types': True, 'fail_on_warning': False, 'validate_referential_integrity': True}, description='Behavioral strictness settings for code generation stages.')`
- `formatting_preferences: dict[str, str] = Field(default_factory=lambda: {'line_length': '100', 'formatter': 'ruff'}, description='Code formatting configuration applied during AST post-processing.')`
- `json_diagnostics: bool = Field(default=False, description='Emit diagnostic reports strictly as REQ-030 JSON structures.')`
- `debug: bool = Field(default=False, description='Enable verbosity for internal telemetry and pipeline diagnostics.')`

**Methods:**
```python
def validate_emission_path(cls, value: Path) -> Path
```
```python
def get_strictness(self, key: str, default: bool = True) -> bool
```
#### Top-Level Functions

```python
def load_settings(**overrides: Any) -> GeneratorSettings
```
> Instantiates and returns the frozen GeneratorSettings singleton or instance.
Halts execution immediately if invalid parameters are provided.

### File: `src/meta_service_generator/diagnostics.py`

#### Classes & Models

```python
class DiagnosticReport(BaseModel):
```
**Fields / Attributes:**
- `generation_status: GenerationStatus = Field(default='failed', description='Current operational status of generator pipeline.')`
- `stage: str = Field(..., min_length=1, description='Pipeline stage where event occurred.')`
- `error_code: str = Field(..., min_length=1, description='Machine-readable error identifier.')`
- `message: str = Field(..., min_length=1, description='Human-readable root cause explanation.')`
- `location: str = Field(default='global', min_length=1, description='Manifest JSON Pointer or emitted source path.')`
- `severity: DiagnosticSeverity = Field(default='fatal', description='Severity classification.')`
- `suggested_resolution: str = Field(..., min_length=1, description='Actionable remediation advice for build operator or agent.')`

```python
class DiagnosticEngine:
```
**Methods:**
```python
def __init__(self, json_mode: bool = False) -> None
```
```python
def create_report_from_exception(self, exc: Exception) -> DiagnosticReport
```
```python
def emit(self, report: DiagnosticReport) -> None
```
### File: `src/meta_service_generator/exceptions.py`

#### Classes & Models

```python
class GeneratorError(Exception):
```
> Root domain exception for meta_service_generator.

All pipeline failures must inherit from this class to guarantee
REQ-030 mapping.

**Methods:**
```python
def __init__(self, message: str, stage: str = 'pipeline_initialization', error_code: str = 'ERR_GENERATOR_INTERNAL', location: str | None = None, severity: str = 'fatal', suggested_resolution: str | None = None, details: Mapping[str, Any] | None = None) -> None
```
```python
def to_diagnostic_dict(self) -> dict[str, Any]
```
> Converts the exception directly into a REQ-030 compliant diagnostic dictionary.

```python
class ManifestValidationError(GeneratorError):
```
> Raised during Stage 1 manifest ingestion, schema, or referential integrity failures.

**Methods:**
```python
def __init__(self, message: str, location: str | None = None, error_code: str = 'ERR_STAGE1_MANIFEST_INVALID', suggested_resolution: str | None = None, details: Mapping[str, Any] | None = None) -> None
```
```python
class IRBuilderError(GeneratorError):
```
> Raised during Stage 2 Intermediate Representation translation or cycle analysis.

**Methods:**
```python
def __init__(self, message: str, location: str | None = None, error_code: str = 'ERR_STAGE2_IR_TRANSLATION', suggested_resolution: str | None = None, details: Mapping[str, Any] | None = None) -> None
```
```python
class CodeGenerationError(GeneratorError):
```
> Raised during Stage 3/4 AST/CST code synthesis, template execution, or formatting.

**Methods:**
```python
def __init__(self, message: str, location: str | None = None, error_code: str = 'ERR_STAGE3_4_CODE_GEN', suggested_resolution: str | None = None, details: Mapping[str, Any] | None = None) -> None
```
```python
class VerificationError(GeneratorError):
```
> Raised during Stage 6 dynamic boot testing or test runner failures.

**Methods:**
```python
def __init__(self, message: str, location: str | None = None, error_code: str = 'ERR_STAGE6_VERIFICATION_FAILED', suggested_resolution: str | None = None, details: Mapping[str, Any] | None = None) -> None
```
### File: `src/meta_service_generator/extensions/contracts.py`

#### Classes & Models

```python
class ExtensionContext(BaseModel, Generic[ContextDataT]):
```
> Immutable execution context passed to operator extension hooks [source: 3].

**Fields / Attributes:**
- `execution_id: str = Field(..., min_length=1, description='Unique ID for tracing current operation context.')`
- `tenant_id: str | None = Field(default=None, description='Optional tenant identifier.')`
- `actor_id: str | None = Field(default=None, description='Identifier of invoking user or service.')`
- `payload: ContextDataT = Field(..., description='Strongly typed payload model.')`

```python
class AbstractWorkflowHook(ABC, Generic[ContextDataT]):
```
> Abstract base class for operator workflow step hooks and overrides [source: 3].

**Methods:**
```python
async def before_step(self, step_name: str, context: ExtensionContext[ContextDataT]) -> ExtensionContext[ContextDataT] | None
```
> Executed prior to running a workflow step. Returns updated context or None.

```python
async def after_step(self, step_name: str, result: Any, context: ExtensionContext[ContextDataT]) -> Any | None
```
> Executed immediately after a workflow step completes.

```python
async def override_step(self, step_name: str, context: ExtensionContext[ContextDataT]) -> Any | None
```
> Replaces execution of a specific step if non-None is returned.

```python
class AbstractRuleOverride(ABC, Generic[ContextDataT]):
```
> Abstract base class for overriding or augmenting business rule evaluations [source: 3].

**Methods:**
```python
async def evaluate_rule_override(self, rule_name: str, context: ExtensionContext[ContextDataT], default_result: bool) -> bool | None
```
> Override or compose business rule logic. Return bool to force result, or None to keep default.

```python
class AbstractFSMHook(ABC, Generic[ContextDataT]):
```
> Abstract base class for state transition guards and post-commit hooks [source: 3].

**Methods:**
```python
async def before_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[ContextDataT]) -> None
```
> Transition guard. Raise Exception to block state transition.

```python
async def after_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[ContextDataT]) -> None
```
> Post-commit side-effect hook after state transition succeeds.

### File: `src/meta_service_generator/extensions/hooks.py`

#### Classes & Models

```python
class DefaultWorkflowHook(AbstractWorkflowHook[ContextDataT], Generic[ContextDataT]):
```
> Default no-op fallback implementation for workflow step hooks [source: 3].

**Methods:**
```python
async def before_step(self, step_name: str, context: ExtensionContext[ContextDataT]) -> ExtensionContext[ContextDataT] | None
```
```python
async def after_step(self, step_name: str, result: Any, context: ExtensionContext[ContextDataT]) -> Any | None
```
```python
async def override_step(self, step_name: str, context: ExtensionContext[ContextDataT]) -> Any | None
```
```python
class DefaultRuleOverride(AbstractRuleOverride[ContextDataT], Generic[ContextDataT]):
```
> Default no-op fallback implementation for business rule overrides [source: 3].

**Methods:**
```python
async def evaluate_rule_override(self, rule_name: str, context: ExtensionContext[ContextDataT], default_result: bool) -> bool | None
```
```python
class DefaultFSMHook(AbstractFSMHook[ContextDataT], Generic[ContextDataT]):
```
> Default no-op fallback implementation for state machine transition hooks [source: 3].

**Methods:**
```python
async def before_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[ContextDataT]) -> None
```
```python
async def after_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[ContextDataT]) -> None
```
### File: `src/meta_service_generator/extensions/registry.py`

#### Classes & Models

```python
class ExtensionRegistry(Generic[ContextDataT]):
```
> Registry that discovers, loads, and executes operator extension hooks
during application startup lifespan [source: 3].

A registry instance owns its lifecycle and is intentionally not implemented
as a process-global asyncio singleton.

**Methods:**
```python
def __init__(self) -> None
```
```python
def initialized(self) -> bool
```
> Return whether extension discovery has completed.

```python
def workflow_hooks(self) -> Sequence[AbstractWorkflowHook[ContextDataT]]
```
```python
def rule_overrides(self) -> Sequence[AbstractRuleOverride[ContextDataT]]
```
```python
def fsm_hooks(self) -> Sequence[AbstractFSMHook[ContextDataT]]
```
```python
async def discover_and_register(self, package_path: str = 'extensions') -> None
```
> Scans the operator extensions package for plugin implementations and registers them.
Must be invoked during FastAPI startup lifespan [source: 3].

```python
async def execute_before_step(self, step_name: str, context: ExtensionContext[ContextDataT]) -> ExtensionContext[ContextDataT]
```
```python
async def execute_after_step(self, step_name: str, result: Any, context: ExtensionContext[ContextDataT]) -> Any
```
```python
async def execute_step_override(self, step_name: str, context: ExtensionContext[ContextDataT]) -> tuple[bool, Any]
```
```python
async def evaluate_rule_override(self, rule_name: str, context: ExtensionContext[ContextDataT], default_result: bool) -> bool
```
```python
async def execute_before_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[ContextDataT]) -> None
```
```python
async def execute_after_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[ContextDataT]) -> None
```
### File: `src/meta_service_generator/generation/artifacts.py`

#### Classes & Models

```python
class Artifact(BaseModel):
```
> Immutable representation of a synthesized file artifact.

**Fields / Attributes:**
- `relative_path: str`
- `absolute_path: str`
- `content_hash: str`
- `size_bytes: int`
- `is_executable: bool = False`
- `created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())`

```python
class ArtifactWriter:
```
> Safely writes file artifacts with path traversal protection and atomic file operations.

**Methods:**
```python
def __init__(self, target_dir: Path | str) -> None
```
```python
def write_artifact(self, relative_path: Path | str, content: str, is_executable: bool = False) -> Artifact
```
> Atomically writes file content to target destination after validating path bounds.

### File: `src/meta_service_generator/generation/context.py`

#### Classes & Models

```python
class GenerationContext(BaseModel):
```
> Immutable, fully prepared rendering context passed directly into Jinja2 templates.

**Fields / Attributes:**
- `service_name: str`
- `version: str`
- `models: tuple[IRModel, ...]`
- `has_fsms: bool = False`
- `has_rules: bool = False`
- `has_workflows: bool = False`
- `has_policies: bool = False`
- `extra_imports: tuple[str, ...] = Field(default_factory=tuple)`

**Methods:**
```python
def model_map(self) -> Mapping[str, IRModel]
```
> Returns an immutable model-name lookup.

```python
def from_service_ir(cls, service_ir: ServiceIR) -> GenerationContext
```
> Creates an immutable rendering context from ServiceIR.

```python
def as_template_context(self) -> dict[str, Any]
```
> Produces a template-facing dictionary without exposing mutable
internal configuration state.

### File: `src/meta_service_generator/generation/dto.py`

#### Classes & Models

```python
class DTOAttributeContext(BaseModel):
```
> Immutable template context for one DTO attribute.

**Fields / Attributes:**
- `name: str`
- `original_name: str`
- `python_type: str`
- `is_optional: bool = False`
- `default_value: str = '...'`

```python
class DTOSpecContext(BaseModel):
```
> Immutable rendering specification for generated DTO classes.

**Fields / Attributes:**
- `model_name: str`
- `class_name: str`
- `create_fields: tuple[DTOAttributeContext, ...]`
- `update_fields: tuple[DTOAttributeContext, ...]`
- `search_fields: tuple[DTOAttributeContext, ...]`
- `response_fields: tuple[DTOAttributeContext, ...]`

```python
class DTOGenerator:
```
> Synthesizes isolated Create, Update, Search, and Response DTO contexts enforcing REQ-004.

**Methods:**
```python
def build_dto_specs(self, model: IRModel) -> DTOSpecContext
```
### File: `src/meta_service_generator/generation/manifest_report.py`

#### Classes & Models

```python
class BuildManifest(BaseModel):
```
> Immutable build manifest containing deterministic artifact metadata and service context.

**Fields / Attributes:**
- `service_name: str`
- `service_version: str`
- `generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())`
- `total_artifacts: int`
- `total_bytes: int`
- `artifacts: tuple[Artifact, ...]`

```python
class ManifestReportGenerator:
```
> Generates deterministic JSON build manifests and human-readable Markdown reports.

**Methods:**
```python
def generate_manifest(self, service_ir: ServiceIR, artifacts: Sequence[Artifact], target_dir: Path) -> Artifact
```
> Creates build_manifest.json containing cryptographic hashes for all emitted artifacts.

```python
def generate_markdown_report(self, service_ir: ServiceIR, artifacts: Sequence[Artifact], target_dir: Path) -> Artifact
```
> Generates human-readable BUILD_REPORT.md summary for build logs and agentic triage.

### File: `src/meta_service_generator/generation/pipeline.py`

#### Classes & Models

```python
class CodeGenerationPipeline:
```
> Orchestrates end-to-end code synthesis utilizing all package Jinja2 templates.

**Methods:**
```python
def __init__(self, renderer: TemplateRenderer | None = None, dto_generator: DTOGenerator | None = None, cst_pipeline: LibCSTPipeline | None = None, formatting_gate: CodeFormattingGate | None = None, manifest_reporter: ManifestReportGenerator | None = None) -> None
```
```python
def execute(self, service_ir: ServiceIR, target_dir: Path) -> list[Path]
```
> Executes complete code synthesis rendering all templates and returning emitted artifact paths.

### File: `src/meta_service_generator/generation/renderer.py`

#### Classes & Models

```python
class TemplateRenderer:
```
> Strict Jinja2 rendering engine loading filesystem and package Jinja2 templates directly.

**Methods:**
```python
def __init__(self, template_dir: Path | str | None = None) -> None
```
```python
def resolve_template_name(self, template_name: str) -> str
```
> Resolves short or mapped template names to canonical relative package paths.

```python
def render(self, template_name: str, context: Mapping[str, Any]) -> str
```
> Render one named Jinja2 template using strict variable validation.

### File: `src/meta_service_generator/ir/builder.py`

#### Classes & Models

```python
class IRBuilder:
```
> Translates a validated ManifestSpec into a compiler ServiceIR [source: 3].

**Methods:**
```python
def build(self, manifest: ManifestSpec) -> ServiceIR
```
### File: `src/meta_service_generator/ir/dependencies.py`

#### Classes & Models

```python
class DependencyResolver:
```
> Resolves topological module execution order and isolates circular imports for generated code [source: 3].

**Methods:**
```python
def topological_sort_models(self, service_ir: ServiceIR) -> tuple[IRModel, ...]
```
> Orders models topologically based on entity relationship dependencies.

Circular relationship edges are ignored by the topological sorter because
those relationships are explicitly handled through deferred imports.

```python
def compute_import_manifest(self, model: IRModel, service_ir: ServiceIR) -> dict[str, frozenset[str]]
```
> Computes standard and deferred TYPE_CHECKING imports for a target model.

Circular references are placed in TYPE_CHECKING imports to avoid
runtime module loops [source: 3].

### File: `src/meta_service_generator/ir/model.py`

#### Classes & Models

```python
class IRField(BaseModel):
```
> Intermediate representation of a generated model field.

**Fields / Attributes:**
- `name: str`
- `original_name: str`
- `python_type: str`
- `sql_type: str`
- `is_primary_key: bool = False`
- `is_nullable: bool = False`
- `is_unique: bool = False`
- `is_indexed: bool = False`

```python
class IRRelationship(BaseModel):
```
> Intermediate representation of an entity relationship.

**Fields / Attributes:**
- `name: str`
- `original_name: str`
- `target_entity: str`
- `target_class_name: str`
- `cardinality: Literal['1:1', '1:N', 'N:M']`
- `foreign_key: str | None = None`
- `is_circular: bool = False`

```python
class IRTransition(BaseModel):
```
> Intermediate representation of a finite-state-machine transition.

**Fields / Attributes:**
- `trigger: str`
- `source_state: str`
- `target_state: str`
- `guards: tuple[str, ...] = Field(default_factory=tuple)`

```python
class IRFSM(BaseModel):
```
> Intermediate representation of an entity finite-state machine.

**Fields / Attributes:**
- `state_attribute: str`
- `initial_state: str`
- `states: tuple[str, ...]`
- `transitions: tuple[IRTransition, ...]`

```python
class IRRule(BaseModel):
```
> Intermediate representation of a business rule.

**Fields / Attributes:**
- `name: str`
- `target_entity: str`
- `expression: str`
- `error_message: str`

```python
class IRWorkflowStep(BaseModel):
```
> Intermediate representation of one workflow step.

**Fields / Attributes:**
- `name: str`
- `action: str`
- `depends_on: tuple[str, ...] = Field(default_factory=tuple)`
- `max_retries: int = 3`

```python
class IRWorkflow(BaseModel):
```
> Intermediate representation of a workflow.

**Fields / Attributes:**
- `name: str`
- `steps: tuple[IRWorkflowStep, ...]`

```python
class IRPolicy(BaseModel):
```
> Intermediate representation of an authorization policy.

**Fields / Attributes:**
- `name: str`
- `roles: tuple[str, ...]`
- `actions: tuple[str, ...]`
- `claims_required: tuple[str, ...] = Field(default_factory=tuple)`

```python
class IRModel(BaseModel):
```
> Intermediate representation of a generated domain model.

**Fields / Attributes:**
- `name: str`
- `class_name: str`
- `table_name: str`
- `fields: tuple[IRField, ...]`
- `relationships: tuple[IRRelationship, ...] = Field(default_factory=tuple)`
- `fsm: IRFSM | None = None`
- `has_circular_dependencies: bool = False`

```python
class ServiceIR(BaseModel):
```
> Complete immutable intermediate representation of a service.

**Fields / Attributes:**
- `service_name: str`
- `version: str`
- `models: tuple[IRModel, ...]`
- `rules: tuple[IRRule, ...] = Field(default_factory=tuple)`
- `workflows: tuple[IRWorkflow, ...] = Field(default_factory=tuple)`
- `policies: tuple[IRPolicy, ...] = Field(default_factory=tuple)`

### File: `src/meta_service_generator/ir/names.py`

#### Top-Level Functions

```python
def sanitize_identifier(name: str) -> str
```
> Sanitizes arbitrary strings into valid Python identifiers.

Python keywords, builtin names, and generator-reserved contextual names
receive a trailing underscore to prevent generated-code collisions.

```python
def ensure_unique_identifiers(names: Iterable[str]) -> dict[str, str]
```
> Sanitizes a collection of source names and rejects collisions.

Example:
    customer-id -> customer_id
    customer_id -> customer_id

These source names cannot safely coexist because they would generate
the same Python identifier.

```python
def to_pascal_case(name: str) -> str
```
> Converts snake_case, kebab-case, or space-separated strings to PascalCase.

```python
def to_snake_case(name: str) -> str
```
> Converts PascalCase, camelCase, or kebab-case strings to snake_case.

```python
def to_screaming_snake_case(name: str) -> str
```
> Converts arbitrary strings to SCREAMING_SNAKE_CASE for constant definitions.

### File: `src/meta_service_generator/ir/normalizer.py`

#### Classes & Models

```python
class TypeNormalizer:
```
> Maps manifest abstract types to Python runtime typing and SQLAlchemy SQL column types.

**Methods:**
```python
def normalize_type(cls, raw_type: str, location: str = 'attribute') -> tuple[str, str]
```
> Returns a tuple of (python_type_annotation, sqlalchemy_type_expression).

### File: `src/meta_service_generator/local_telemetry.py`

#### Top-Level Functions

```python
def get_logger(name: str) -> logging.Logger
```
> Return a standard Python Logger configured for structured log output.

Bridge method to supply logging capabilities alongside meta_telemetry's tracer.

### File: `src/meta_service_generator/manifest/loader.py`

#### Classes & Models

```python
class ManifestLoader:
```
> Seamlessly parses JSON and YAML service manifest definitions [source: 3].

**Fields / Attributes:**
- `DEFAULT_MAX_MANIFEST_BYTES: Final[int] = 5 * 1024 * 1024`

**Methods:**
```python
def __init__(self, max_manifest_bytes: int = DEFAULT_MAX_MANIFEST_BYTES) -> None
```
```python
def load_from_path(self, path: Path) -> dict[str, Any]
```
> Loads and parses a JSON or YAML manifest from disk.

```python
def load_from_str(self, content: str, source_label: str = 'inline_string', suffix: str | None = None) -> dict[str, Any]
```
> Parses a JSON or YAML manifest from an in-memory string.

### File: `src/meta_service_generator/manifest/references.py`

#### Classes & Models

```python
class ReferentialIntegrityEngine:
```
> Validates cross-entity referential integrity across entities, FSMs, rules, workflows, and policies [source: 3].

**Methods:**
```python
def validate(self, manifest: ManifestSpec, source_label: str = 'manifest') -> None
```
### File: `src/meta_service_generator/manifest/schema.py`

#### Classes & Models

```python
class AttributeSpec(BaseModel):
```
**Fields / Attributes:**
- `name: str`
- `type: Literal['str', 'int', 'float', 'bool', 'datetime', 'uuid', 'dict', 'list']`
- `primary_key: bool = False`
- `nullable: bool = False`
- `unique: bool = False`
- `indexed: bool = False`

```python
class RelationshipSpec(BaseModel):
```
**Fields / Attributes:**
- `name: str`
- `target_entity: str`
- `cardinality: Literal['1:1', '1:N', 'N:M']`
- `foreign_key: str | None = None`

```python
class TransitionSpec(BaseModel):
```
**Fields / Attributes:**
- `trigger: str`
- `source_state: str`
- `target_state: str`
- `guards: tuple[str, ...] = Field(default_factory=tuple)`

```python
class FSMSpec(BaseModel):
```
**Fields / Attributes:**
- `state_attribute: str`
- `initial_state: str`
- `states: tuple[str, ...]`
- `transitions: tuple[TransitionSpec, ...]`

```python
class EntitySpec(BaseModel):
```
**Fields / Attributes:**
- `name: str`
- `table_name: str | None = Field(default=None, alias='tableName')`
- `attributes: tuple[AttributeSpec, ...]`
- `relationships: tuple[RelationshipSpec, ...] = Field(default_factory=tuple)`
- `fsm: FSMSpec | None = None`

```python
class BusinessRuleSpec(BaseModel):
```
**Fields / Attributes:**
- `name: str`
- `target_entity: str`
- `expression: str`
- `error_message: str`

```python
class WorkflowStepSpec(BaseModel):
```
**Fields / Attributes:**
- `name: str`
- `action: str`
- `depends_on: tuple[str, ...] = Field(default_factory=tuple)`
- `max_retries: int = 3`

```python
class WorkflowSpec(BaseModel):
```
**Fields / Attributes:**
- `name: str`
- `steps: tuple[WorkflowStepSpec, ...]`

```python
class PolicySpec(BaseModel):
```
**Fields / Attributes:**
- `name: str`
- `roles: tuple[str, ...]`
- `actions: tuple[str, ...]`
- `claims_required: tuple[str, ...] = Field(default_factory=tuple)`

```python
class ManifestSpec(BaseModel):
```
**Fields / Attributes:**
- `version: str`
- `service_name: str`
- `entities: tuple[EntitySpec, ...]`
- `business_rules: tuple[BusinessRuleSpec, ...] = Field(default_factory=tuple)`
- `workflows: tuple[WorkflowSpec, ...] = Field(default_factory=tuple)`
- `policies: tuple[PolicySpec, ...] = Field(default_factory=tuple)`

### File: `src/meta_service_generator/manifest/validator.py`

#### Classes & Models

```python
class ManifestValidator:
```
> Validates raw dict manifests against JSON Schema Draft-2020-12 and compiles Pydantic specs [source: 3].

**Methods:**
```python
def __init__(self, schema_path: Path | None = None) -> None
```
```python
def validate(self, raw_manifest: dict[str, Any], source_label: str = 'manifest') -> ManifestSpec
```
> Validates and compiles a raw manifest into an immutable ManifestSpec.

### File: `src/meta_service_generator/msg_engine.py`

#### Classes & Models

```python
class MetaServiceGeneratorEngine:
```
> High-level engine wrapper for meta-service-generator designed for seamless
integration into application builder platforms with minimal configuration effort.

**Methods:**
```python
def __init__(self, default_output_dir: Union[str, Path] = 'generated_service')
```
```python
def generate_service(self, manifest_source: Union[str, Path, Dict[str, Any], ServiceIR], output_dir: Optional[Union[str, Path]] = None, verify: bool = True) -> Dict[str, Any]
```
> Validates a manifest (file path, dictionary, or ServiceIR), runs the generation pipeline,
and optionally verifies the generated microservice package.

### File: `src/meta_service_generator/transforms/annotations.py`

#### Classes & Models

```python
class FutureAnnotationsTransformer(cst.CSTTransformer):
```
> LibCST Transformer that inserts `from __future__ import annotations` as the first
statement of a module, placing it after module docstrings.

**Methods:**
```python
def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module
```
### File: `src/meta_service_generator/transforms/cleanup.py`

#### Classes & Models

```python
class DeadCodeCleanupTransformer(cst.CSTTransformer):
```
> LibCST Transformer that cleans up redundant statements and pass-throughs.

**Methods:**
```python
def leave_IndentedBlock(self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock) -> cst.IndentedBlock
```
### File: `src/meta_service_generator/transforms/formatting.py`

#### Classes & Models

```python
class CodeFormattingGate:
```
> In-process formatting gate enforcing Black/Ruff code styling and AST validity.

**Methods:**
```python
def __init__(self, line_length: int = 88) -> None
```
```python
def format_code(self, source_code: str, filename: str = '<generated>') -> str
```
> Formats Python source code using Black in-process and validates syntax.

### File: `src/meta_service_generator/transforms/imports.py`

#### Classes & Models

```python
class ImportOrganizerTransformer(cst.CSTTransformer):
```
> LibCST Transformer that deduplicates imports and ensures consistent module import placement.

**Methods:**
```python
def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module
```
### File: `src/meta_service_generator/transforms/libcst_pipeline.py`

#### Classes & Models

```python
class LibCSTPipeline:
```
> Executes AST/CST transformation passes sequentially on raw Python code strings.

**Methods:**
```python
def __init__(self, transformers: Sequence[type[cst.CSTTransformer]] | None = None) -> None
```
```python
def transform(self, source_code: str, filename: str = '<generated>') -> str
```
> Parses source string into LibCST module, applies all transformation passes, and returns code.

### File: `src/meta_service_generator/verification/boot.py`

#### Classes & Models

```python
class BootVerificationResult(BaseModel):
```
> Immutable result status for application startup dynamic verification [source: 3].

**Fields / Attributes:**
- `success: bool = Field(..., description='True when application import and lifespan startup completed successfully.')`
- `output: str = Field(default='', description='Captured standard output from the boot subprocess.')`
- `error_output: str | None = Field(default=None, description='Captured standard error or verification failure details.')`
- `exit_code: int | None = Field(default=0, description='Subprocess exit code. -1 indicates the process could not complete normally.')`
- `timed_out: bool = Field(default=False, description='True when the subprocess exceeded the configured timeout.')`

```python
class BootVerifier:
```
> Verifies dynamic FastAPI application boot inside an isolated subprocess context [source: 3].

**Methods:**
```python
def __init__(self, timeout_seconds: float = DEFAULT_BOOT_TIMEOUT_SECONDS) -> None
```
```python
async def verify_application_boot(self, project_root: Path, package_name: str) -> BootVerificationResult
```
> Executes app instantiation and lifespan verification in isolated subprocess [source: 3].

### File: `src/meta_service_generator/verification/imports.py`

#### Classes & Models

```python
class ImportVerificationResult(BaseModel):
```
> Immutable result status for module import verification [source: 3].

**Fields / Attributes:**
- `module_name: str = Field(..., min_length=1, description='Python module being verified.')`
- `is_importable: bool = Field(..., description='True when the module imports successfully.')`
- `error_output: str | None = Field(default=None, description='Captured import failure details.')`
- `exit_code: int | None = Field(default=0, description='Subprocess exit code.')`
- `timed_out: bool = Field(default=False, description='True when module import exceeded the configured timeout.')`

```python
class ImportVerifier:
```
> Verifies dynamic import viability in isolated subprocesses using uv [source: 3].

**Methods:**
```python
def __init__(self, timeout_seconds: float = DEFAULT_IMPORT_TIMEOUT_SECONDS) -> None
```
```python
async def verify_module_import(self, project_root: Path, module_name: str) -> ImportVerificationResult
```
> Executes module import check inside isolated subprocess [source: 3].

```python
async def verify_all_imports(self, project_root: Path, package_name: str) -> tuple[ImportVerificationResult, ...]
```
> Scans project package and verifies importability for all submodules [source: 3].

### File: `src/meta_service_generator/verification/package.py`

#### Classes & Models

```python
class PackageVerificationResult(BaseModel):
```
> Immutable result status for pyproject configuration and dependency tree validation.

**Fields / Attributes:**
- `is_valid: bool = Field(..., description='True if pyproject.toml is valid and buildable.')`
- `build_output: str = Field(default='', description='Standard output from build verification.')`
- `error_output: str | None = Field(default=None, description='Standard error details if build failed.')`
- `exit_code: int | None = Field(default=0, description='Package build subprocess exit code.')`
- `timed_out: bool = Field(default=False, description='True when package build exceeded the configured timeout.')`

```python
class PackageVerifier:
```
> Verifies pyproject.toml validity, dependency resolution, and package buildability.

**Methods:**
```python
def __init__(self, timeout_seconds: float = DEFAULT_PACKAGE_TIMEOUT_SECONDS) -> None
```
```python
async def verify_package(self, project_root: Path) -> PackageVerificationResult
```
> Executes pyproject validation and package build verification using uv in an isolated subprocess.

```python
async def enforce_package_validity(self, project_root: Path) -> PackageVerificationResult
```
> Evaluates package validity and raises CodeGenerationError on failure.

### File: `src/meta_service_generator/verification/runner.py`

#### Classes & Models

```python
class VerificationPipelineResult(BaseModel):
```
> Immutable result summary for the complete Stage 6 verification pipeline [source: 3].

**Fields / Attributes:**
- `syntax_passed: bool = Field(..., description='True when all generated Python files pass AST validation.')`
- `package_passed: bool = Field(..., description='True when generated package build succeeds.')`
- `imports_passed: bool = Field(..., description='True when every generated Python module imports successfully.')`
- `typing_passed: bool = Field(..., description='True when strict mypy verification succeeds.')`
- `boot_passed: bool = Field(..., description='True when application import and FastAPI lifespan startup succeed.')`
- `tests_passed: bool = Field(..., description='True when the generated pytest suite succeeds.')`
- `syntax_results: tuple[SyntaxVerificationResult, ...] = Field(default=(), description='Immutable syntax verification results.')`
- `package_result: PackageVerificationResult | None = Field(default=None, description='Package build verification result.')`
- `import_results: tuple[ImportVerificationResult, ...] = Field(default=(), description='Immutable module import verification results.')`
- `type_result: TypeCheckResult | None = Field(default=None, description='Static type verification result.')`
- `boot_result: BootVerificationResult | None = Field(default=None, description='Application boot verification result.')`
- `test_result: TestSuiteExecutionResult | None = Field(default=None, description='Generated test suite execution result.')`
- `details: str = Field(..., min_length=1, description='Human-readable verification summary.')`

```python
class VerificationRunner:
```
> Orchestrates sequential execution of all generated-project verification gates [source: 3].

**Methods:**
```python
def __init__(self, syntax_verifier: SyntaxVerifier | None = None, package_verifier: PackageVerifier | None = None, import_verifier: ImportVerifier | None = None, type_verifier: TypeVerifier | None = None, boot_verifier: BootVerifier | None = None, test_verifier: TestSuiteVerifier | None = None) -> None
```
```python
async def run_pipeline(self, project_root: Path, package_name: str) -> VerificationPipelineResult
```
> Runs all verification stages against synthesized service directory [source: 3].

### File: `src/meta_service_generator/verification/syntax.py`

#### Classes & Models

```python
class SyntaxVerificationResult(BaseModel):
```
> Immutable result status for AST syntax verification [source: 3].

**Fields / Attributes:**
- `file_path: str = Field(..., min_length=1, description='Path to the Python source file.')`
- `is_valid: bool = Field(..., description='True when Python AST parsing succeeds.')`
- `error_message: str | None = Field(default=None, description='Syntax parser error message.')`
- `line_number: int | None = Field(default=None, ge=1, description='One-based source line containing syntax failure.')`
- `column_offset: int | None = Field(default=None, ge=0, description='Zero-based parser column offset.')`

```python
class SyntaxVerifier:
```
> Verifies syntactical validity of generated Python modules using AST parsing [source: 3].

**Methods:**
```python
def verify_file(self, file_path: Path) -> SyntaxVerificationResult
```
> Parses a single Python file into an AST to verify syntax [source: 3].

```python
def verify_directory(self, directory: Path) -> tuple[SyntaxVerificationResult, ...]
```
> Recursively parses all Python files within target directory [source: 3].

### File: `src/meta_service_generator/verification/tests.py`

#### Classes & Models

```python
class TestSuiteExecutionResult(BaseModel):
```
> Immutable result summary for synthesized test suite execution.

**Fields / Attributes:**
- `passed: bool = Field(..., description='True if all synthesized tests passed.')`
- `exit_code: int | None = Field(..., description='Pytest process exit code.')`
- `stdout: str = Field(default='', description='Standard output from pytest execution.')`
- `stderr: str = Field(default='', description='Standard error output from pytest execution.')`
- `timed_out: bool = Field(default=False, description='True when pytest exceeded the configured timeout.')`

```python
class TestSuiteVerifier:
```
> Executes synthesized pytest suite inside an isolated subprocess and reports results.

**Methods:**
```python
def __init__(self, timeout_seconds: float = DEFAULT_TEST_TIMEOUT_SECONDS) -> None
```
```python
async def run_test_suite(self, project_root: Path) -> TestSuiteExecutionResult
```
> Runs pytest on generated tests/ directory in target project.

```python
async def enforce_test_suite_pass(self, project_root: Path) -> TestSuiteExecutionResult
```
> Evaluates test suite execution and raises CodeGenerationError on any test failures.

### File: `src/meta_service_generator/verification/typing.py`

#### Classes & Models

```python
class TypeCheckIssue(BaseModel):
```
> Detailed record of a single static type checking issue.

**Fields / Attributes:**
- `file_path: str = Field(..., min_length=1, description='Path to file containing type error.')`
- `line_number: int = Field(..., ge=1, description='Line number of type error.')`
- `error_code: str = Field(..., min_length=1, description='Mypy error code key.')`
- `message: str = Field(..., min_length=1, description='Type error description.')`

```python
class TypeCheckResult(BaseModel):
```
> Immutable result summary for static type checking.

**Fields / Attributes:**
- `is_valid: bool = Field(..., description='True if mypy passed with zero type errors.')`
- `issues: tuple[TypeCheckIssue, ...] = Field(default=(), description='Immutable collection of parsed mypy issues.')`
- `raw_output: str = Field(default='', description='Raw output string from mypy execution.')`
- `exit_code: int | None = Field(default=0, description='Mypy subprocess exit code.')`
- `timed_out: bool = Field(default=False, description='True when mypy exceeded the configured timeout.')`

```python
class TypeVerifier:
```
> Verifies static type compliance of synthesized codebase using mypy in isolated subprocesses.

**Methods:**
```python
def __init__(self, timeout_seconds: float = DEFAULT_TYPECHECK_TIMEOUT_SECONDS) -> None
```
```python
async def verify_types(self, project_root: Path) -> TypeCheckResult
```
> Executes strict mypy type checking against the generated source directory.

```python
async def enforce_type_safety(self, project_root: Path) -> TypeCheckResult
```
> Evaluates static type safety and raises CodeGenerationError on failure.

### File: `tests/conftest.py`

#### Top-Level Functions

```python
def base_schema() -> Dict[str, Any]
```
```python
def acyclic_dag() -> nx.DiGraph
```
```python
def direct_cycle_graph() -> nx.DiGraph
```
```python
def indirect_cycle_graph() -> nx.DiGraph
```
```python
def disconnected_graph() -> nx.DiGraph
```
### File: `tests/test_cli.py`

#### Classes & Models

```python
class TestCLIGenerateCommand:
```
**Methods:**
```python
def test_generate_success(self, runner: CliRunner, tmp_path: Path) -> None
```
```python
def test_generate_missing_manifest_argument(self, runner: CliRunner, tmp_path: Path) -> None
```
```python
def test_generate_non_existent_manifest_file(self, runner: CliRunner, tmp_path: Path) -> None
```
```python
def test_generate_pipeline_failure_with_json_diagnostics(self, runner: CliRunner, tmp_path: Path) -> None
```
```python
class TestCLIVerifyCommand:
```
**Methods:**
```python
def test_verify_success(self, runner: CliRunner, tmp_path: Path) -> None
```
```python
def test_verify_failure_execution_error(self, runner: CliRunner, tmp_path: Path) -> None
```
```python
class TestCLISchemaCommand:
```
**Methods:**
```python
def test_schema_export_success(self, runner: CliRunner, tmp_path: Path) -> None
```
```python
def test_schema_export_failure_diagnostics(self, runner: CliRunner, tmp_path: Path) -> None
```
#### Top-Level Functions

```python
def runner() -> CliRunner
```
### File: `tests/test_config.py`

#### Top-Level Functions

```python
def test_generator_settings_defaults()
```
```python
def test_generator_settings_env_overrides(monkeypatch, tmp_path)
```
```python
def test_load_settings_invalid_parsing_raises_runtime_error(invalid_kwargs)
```
```python
def test_load_settings_successful_overrides(tmp_path)
```
### File: `tests/test_contracts.py`

#### Classes & Models

```python
class SamplePayload(BaseModel):
```
**Fields / Attributes:**
- `user_id: str`
- `item_count: int`

```python
class TestExtensionContext:
```
**Methods:**
```python
def test_context_instantiation_valid(self) -> None
```
```python
def test_context_immutability_frozen(self) -> None
```
```python
def test_context_extra_fields_forbidden(self) -> None
```
```python
class ConcreteWorkflowHook(AbstractWorkflowHook[SamplePayload]):
```
**Methods:**
```python
async def before_step(self, step_name: str, context: ExtensionContext[SamplePayload]) -> ExtensionContext[SamplePayload] | None
```
```python
async def after_step(self, step_name: str, result: Any, context: ExtensionContext[SamplePayload]) -> Any | None
```
```python
async def override_step(self, step_name: str, context: ExtensionContext[SamplePayload]) -> Any | None
```
```python
class ConcreteRuleOverride(AbstractRuleOverride[SamplePayload]):
```
**Methods:**
```python
async def evaluate_rule_override(self, rule_name: str, context: ExtensionContext[SamplePayload], default_result: bool) -> bool | None
```
```python
class ConcreteFSMHook(AbstractFSMHook[SamplePayload]):
```
**Methods:**
```python
async def before_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[SamplePayload]) -> None
```
```python
async def after_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[SamplePayload]) -> None
```
```python
class TestAbstractContracts:
```
**Methods:**
```python
async def test_abstract_workflow_hook_raises_not_implemented(self) -> None
```
```python
async def test_abstract_rule_override_raises_not_implemented(self) -> None
```
```python
async def test_abstract_fsm_hook_raises_not_implemented(self) -> None
```
### File: `tests/test_cycle_analyzer.py`

#### Top-Level Functions

```python
def create_mock_manifest(entities_spec)
```
```python
def test_acyclic_dependency_graph()
```
```python
def test_resolvable_circular_dependency_with_nullable_fk()
```
```python
def test_unresolvable_circular_dependency_raises_error()
```
```python
def test_cycle_graph_inconsistency_error(mocker)
```
### File: `tests/test_diagnostics.py`

#### Classes & Models

```python
class CustomGeneratorError(GeneratorError):
```
**Methods:**
```python
def __init__(self, message: str, stage: str = 'parsing', error_code: str = 'ERR_PARSE_FAILED', location: str = '/entities/0', severity: str = 'error', suggested_resolution: str = 'Fix schema syntax.') -> None
```
```python
class TestDiagnosticReportModel:
```
**Methods:**
```python
def test_report_defaults_and_validation(self) -> None
```
```python
def test_report_extra_fields_forbidden(self) -> None
```
```python
class TestDiagnosticEngine:
```
**Methods:**
```python
def test_create_report_from_generator_error(self) -> None
```
```python
def test_create_report_from_generator_error_invalid_severity_fallback(self) -> None
```
```python
def test_create_report_from_unhandled_system_exception(self) -> None
```
```python
def test_emit_json_mode(self) -> None
```
```python
def test_emit_rich_panel_mode(self) -> None
```
### File: `tests/test_exceptions.py`

#### Top-Level Functions

```python
def test_generator_error_initialization_and_dict_conversion()
```
```python
def test_generator_error_validation_guards(msg, stage, code, severity, expected_err)
```
```python
def test_derived_exceptions_hierarchy(exception_cls, expected_stage, expected_code, expected_severity)
```
### File: `tests/test_generation.py`

#### Top-Level Functions

```python
def mock_field_pk()
```
```python
def mock_field_name()
```
```python
def mock_field_optional()
```
```python
def mock_model(mock_field_pk, mock_field_name, mock_field_optional)
```
```python
def mock_service_ir(mock_model)
```
```python
def test_artifact_writer_init_success(tmp_path: Path)
```
```python
def test_artifact_writer_init_target_is_file(tmp_path: Path)
```
```python
def test_artifact_writer_init_os_error(tmp_path: Path)
```
```python
def test_write_artifact_success(tmp_path: Path)
```
```python
def test_write_artifact_invalid_content_type(tmp_path: Path)
```
```python
def test_write_artifact_absolute_path(tmp_path: Path)
```
```python
def test_write_artifact_empty_path(tmp_path: Path)
```
```python
def test_write_artifact_path_traversal(tmp_path: Path)
```
```python
def test_write_artifact_symlink_destination(tmp_path: Path)
```
```python
def test_write_artifact_symlink_parent(tmp_path: Path)
```
```python
def test_artifact_writer_directory_fsync_error(tmp_path: Path)
```
```python
def test_artifact_writer_temp_unlink_error(tmp_path: Path)
```
```python
def test_artifact_writer_unicode_encode_error(tmp_path: Path)
```
```python
def test_generation_context_from_service_ir(mock_service_ir)
```
```python
def test_generation_context_from_invalid_type()
```
```python
def test_generation_context_as_template_context(mock_service_ir)
```
```python
def test_generate_manifest_type_errors(mock_service_ir, tmp_path: Path)
```
```python
def test_generate_manifest_exception_handling(mock_service_ir, tmp_path: Path)
```
```python
def test_generate_markdown_report_type_errors(mock_service_ir, tmp_path: Path)
```
```python
def test_generate_markdown_report_exception_handling(mock_service_ir, tmp_path: Path)
```
```python
def test_dto_generator_build_specs(mock_model)
```
```python
def test_dto_generator_invalid_type()
```
```python
def test_template_renderer_custom_directory_not_found(tmp_path: Path)
```
```python
def test_template_renderer_python_literal()
```
```python
def test_template_renderer_render_validation()
```
```python
def test_template_renderer_template_not_found()
```
```python
def test_manifest_report_generator_manifest(mock_service_ir, tmp_path: Path)
```
```python
def test_manifest_report_generator_markdown(mock_service_ir, tmp_path: Path)
```
```python
def test_pipeline_invalid_inputs(tmp_path: Path, mock_service_ir)
```
```python
def test_pipeline_execution_success(mock_service_ir, tmp_path: Path)
```
```python
def test_pipeline_intermediate_stage_failure(mock_service_ir, tmp_path: Path)
```
```python
def test_pipeline_execution_with_rules_workflows_fsms(tmp_path: Path)
```
```python
def test_pipeline_os_error_handling(mock_service_ir, tmp_path: Path)
```
```python
def test_pipeline_ensure_directory_target_is_file(tmp_path: Path)
```
```python
def test_pipeline_relative_to_target_escape(tmp_path: Path)
```
```python
def test_renderer_package_loader_failure()
```
```python
def test_renderer_with_custom_template_dir(tmp_path: Path)
```
```python
def test_renderer_mapped_template_resolution()
```
```python
def test_renderer_syntax_error(tmp_path: Path)
```
```python
def test_renderer_undefined_variable(tmp_path: Path)
```
```python
def test_renderer_generic_render_exception(tmp_path: Path)
```
```python
def test_renderer_empty_output(tmp_path: Path)
```
### File: `tests/test_graph_validator.py`

#### Top-Level Functions

```python
def test_relationship_graph_duplicate_entity_error()
```
```python
def test_relationship_graph_unknown_target_error()
```
```python
def test_relationship_graph_unknown_foreign_key_error()
```
```python
def test_validate_unique_model_names()
```
```python
def test_validate_fsm_reachability_errors()
```
```python
def test_validate_workflow_dags_errors()
```
```python
def test_validate_business_rules_and_policies()
```
```python
def test_validator_success()
```
```python
def test_validator_duplicate_model_names()
```
```python
def test_validator_fsm_invalid_initial_state()
```
```python
def test_validator_fsm_unknown_source_state()
```
```python
def test_validator_fsm_unknown_target_state()
```
```python
def test_validator_fsm_unreachable_state()
```
```python
def test_validator_workflow_duplicate_steps()
```
```python
def test_validator_workflow_unknown_dependency()
```
```python
def test_validator_workflow_self_dependency()
```
```python
def test_validator_workflow_cycle()
```
```python
def test_validator_rule_unknown_target()
```
```python
def test_validator_rule_empty_expression()
```
```python
def test_validator_rule_empty_error_message()
```
```python
def test_validator_policy_empty_roles()
```
```python
def test_validator_policy_empty_actions()
```
```python
def test_validator_policy_whitespace_role()
```
```python
def test_validator_policy_whitespace_action()
```
### File: `tests/test_hooks.py`

#### Classes & Models

```python
class DummyPayload(BaseModel):
```
**Fields / Attributes:**
- `value: str`

```python
class TestDefaultHooks:
```
**Methods:**
```python
def dummy_context(self) -> ExtensionContext[DummyPayload]
```
```python
async def test_default_workflow_hook(self, dummy_context: ExtensionContext[DummyPayload]) -> None
```
```python
async def test_default_rule_override(self, dummy_context: ExtensionContext[DummyPayload]) -> None
```
```python
async def test_default_fsm_hook(self, dummy_context: ExtensionContext[DummyPayload]) -> None
```
### File: `tests/test_ir.py`

#### Classes & Models

```python
class TestNames:
```
**Methods:**
```python
def test_sanitize_identifier_valid(self)
```
```python
def test_sanitize_identifier_non_string_raises_type_error(self)
```
```python
def test_sanitize_identifier_empty_or_non_words(self)
```
```python
def test_sanitize_identifier_leading_digit(self)
```
```python
def test_sanitize_identifier_python_reserved_keywords(self)
```
```python
def test_sanitize_identifier_invalid_identifier_fallback(self)
```
```python
def test_ensure_unique_identifiers_success(self)
```
```python
def test_ensure_unique_identifiers_collision_error(self)
```
```python
def test_ensure_unique_identifiers_duplicate_error(self)
```
```python
def test_to_pascal_case(self)
```
```python
def test_to_pascal_case_empty(self)
```
```python
def test_to_pascal_case_reserved_keyword(self)
```
```python
def test_to_pascal_case_invalid_identifier(self)
```
```python
def test_to_snake_case(self)
```
```python
def test_to_screaming_snake_case(self)
```
```python
class TestTypeNormalizer:
```
**Methods:**
```python
def test_normalize_type_supported(self, raw_type: str, expected_py: str, expected_sql: str)
```
```python
def test_normalize_type_non_string(self)
```
```python
def test_normalize_type_empty(self)
```
```python
def test_normalize_type_unsupported(self)
```
```python
class TestIRModels:
```
**Methods:**
```python
def test_ir_field_immutability(self)
```
```python
def test_ir_field_extra_fields_forbidden(self)
```
```python
class TestDependencyResolver:
```
**Methods:**
```python
def resolver(self) -> DependencyResolver
```
```python
def test_topological_sort_success(self, resolver: DependencyResolver)
```
```python
def test_topological_sort_unknown_model_error(self, resolver: DependencyResolver)
```
```python
def test_topological_sort_cycle_error(self, resolver: DependencyResolver)
```
```python
def test_compute_import_manifest(self, resolver: DependencyResolver)
```
```python
def test_compute_import_manifest_unknown_model_error(self, resolver: DependencyResolver)
```
```python
class TestIRBuilder:
```
**Methods:**
```python
def builder(self) -> IRBuilder
```
```python
def test_build_empty_identity_validation_errors(self, builder: IRBuilder)
```
```python
def test_build_unknown_relationship_target_error(self, builder: IRBuilder)
```
```python
def test_build_full_service_ir_success(self, builder: IRBuilder)
```
```python
def test_build_unexpected_exception_wrapped(self, builder: IRBuilder)
```
### File: `tests/test_manifest.py`

#### Classes & Models

```python
class TestManifestLoader:
```
**Methods:**
```python
def test_init_invalid_max_bytes(self)
```
```python
def test_load_from_path_invalid_type(self)
```
```python
def test_load_from_path_file_not_found(self, tmp_path: Path)
```
```python
def test_load_from_path_not_a_file(self, tmp_path: Path)
```
```python
def test_load_from_path_file_too_large(self, tmp_path: Path)
```
```python
def test_load_from_path_unicode_decode_error(self, tmp_path: Path)
```
```python
def test_load_from_path_os_error(self, tmp_path: Path)
```
```python
def test_load_from_str_non_str_content(self)
```
```python
def test_load_from_str_empty_content(self)
```
```python
def test_load_from_str_unsupported_suffix(self)
```
```python
def test_load_from_str_inline_json_and_yaml_fallback(self)
```
```python
def test_parse_json_non_dict_root(self)
```
```python
class TestReferentialIntegrityEngine:
```
**Methods:**
```python
def engine(self) -> ReferentialIntegrityEngine
```
```python
def test_duplicate_entity_name(self, engine: ReferentialIntegrityEngine)
```
```python
def test_duplicate_attribute_name(self, engine: ReferentialIntegrityEngine)
```
```python
def test_unknown_target_entity_and_foreign_key(self, engine: ReferentialIntegrityEngine)
```
```python
def test_unknown_foreign_key(self, engine: ReferentialIntegrityEngine)
```
```python
def test_fsm_validation_errors(self, engine: ReferentialIntegrityEngine)
```
```python
def test_business_rule_unknown_entity(self, engine: ReferentialIntegrityEngine)
```
```python
def test_workflow_duplicate_step(self, engine: ReferentialIntegrityEngine)
```
```python
def test_workflow_self_dependency_error(self, engine: ReferentialIntegrityEngine)
```
```python
def test_workflow_missing_dependency(self, engine: ReferentialIntegrityEngine)
```
```python
def test_duplicate_policy_name(self, engine: ReferentialIntegrityEngine)
```
```python
class TestManifestValidator:
```
**Methods:**
```python
def test_validator_init_schema_missing(self, tmp_path: Path) -> None
```
```python
def test_validator_init_invalid_json_schema(self, tmp_path: Path) -> None
```
```python
def test_validator_init_os_error(self, tmp_path: Path) -> None
```
```python
def test_validator_init_generic_exception(self, tmp_path: Path) -> None
```
```python
def test_default_schema_resolution_success(self) -> None
```
```python
def test_packaged_schema_resolution_failure(self) -> None
```
```python
def test_validate_root_not_dict(self, tmp_path: Path) -> None
```
```python
def test_validate_schema_violation(self, tmp_path: Path) -> None
```
```python
def test_validate_pydantic_type_mismatch(self, tmp_path: Path) -> None
```
```python
def test_validate_full_success_and_referential_integrity(self) -> None
```
```python
def test_json_pointer_formatting(self) -> None
```
### File: `tests/test_msg_engine.py`

#### Top-Level Functions

```python
def engine(tmp_path)
```
```python
def sample_manifest()
```
```python
def test_engine_initialization(tmp_path)
```
```python
def test_generate_service_success(mock_verification_runner_cls, mock_pipeline_cls, engine, sample_manifest)
```
```python
def test_generate_service_pipeline_failure(mock_pipeline_cls, engine, sample_manifest)
```
```python
def test_generate_service_with_file_path(engine, sample_manifest, tmp_path)
```
### File: `tests/test_registry.py`

#### Classes & Models

```python
class RegistryPayload(BaseModel):
```
**Fields / Attributes:**
- `key: str`

```python
class MockWorkflowHookA(AbstractWorkflowHook[RegistryPayload]):
```
**Methods:**
```python
async def before_step(self, step_name: str, context: ExtensionContext[RegistryPayload]) -> ExtensionContext[RegistryPayload] | None
```
```python
async def after_step(self, step_name: str, result: Any, context: ExtensionContext[RegistryPayload]) -> Any | None
```
```python
async def override_step(self, step_name: str, context: ExtensionContext[RegistryPayload]) -> Any | None
```
```python
class MockWorkflowHookB(AbstractWorkflowHook[RegistryPayload]):
```
**Methods:**
```python
async def before_step(self, step_name: str, context: ExtensionContext[RegistryPayload]) -> ExtensionContext[RegistryPayload] | None
```
```python
async def after_step(self, step_name: str, result: Any, context: ExtensionContext[RegistryPayload]) -> Any | None
```
```python
async def override_step(self, step_name: str, context: ExtensionContext[RegistryPayload]) -> Any | None
```
```python
class MockRuleOverrideA(AbstractRuleOverride[RegistryPayload]):
```
**Methods:**
```python
async def evaluate_rule_override(self, rule_name: str, context: ExtensionContext[RegistryPayload], default_result: bool) -> bool | None
```
```python
class MockFSMHookA(AbstractFSMHook[RegistryPayload]):
```
**Methods:**
```python
def __init__(self) -> None
```
```python
async def before_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[RegistryPayload]) -> None
```
```python
async def after_transition(self, source_state: str, target_state: str, event: str, context: ExtensionContext[RegistryPayload]) -> None
```
```python
class MockInvalidInitHook(AbstractWorkflowHook[RegistryPayload]):
```
**Methods:**
```python
def __init__(self, required_arg: str) -> None
```
```python
async def before_step(self, step_name: str, context: ExtensionContext[RegistryPayload])
```
```python
async def after_step(self, step_name: str, result: Any, context: ExtensionContext[RegistryPayload])
```
```python
async def override_step(self, step_name: str, context: ExtensionContext[RegistryPayload])
```
```python
class TestExtensionRegistryDiscovery:
```
**Methods:**
```python
async def test_discover_empty_package_path_raises_error(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
async def test_discover_non_existent_package_bypasses(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
async def test_discover_missing_dependency_raises_error(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
async def test_discover_general_import_error_raises_error(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
async def test_discover_already_initialized_skips(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
async def test_register_from_single_module_success(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
async def test_register_instantiation_failed_raises_error(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
async def test_register_package_submodule_load_failure(self, registry: ExtensionRegistry[RegistryPayload]) -> None
```
```python
class TestExtensionRegistryExecution:
```
**Methods:**
```python
async def test_execution_uninitialized_raises_error(self, registry: ExtensionRegistry[RegistryPayload], context: ExtensionContext[RegistryPayload]) -> None
```
```python
async def test_workflow_before_step_chain_and_error(self, registry: ExtensionRegistry[RegistryPayload], context: ExtensionContext[RegistryPayload]) -> None
```
```python
async def test_workflow_after_step_chain_and_error(self, registry: ExtensionRegistry[RegistryPayload], context: ExtensionContext[RegistryPayload]) -> None
```
```python
async def test_workflow_step_override(self, registry: ExtensionRegistry[RegistryPayload], context: ExtensionContext[RegistryPayload]) -> None
```
```python
async def test_evaluate_rule_override(self, registry: ExtensionRegistry[RegistryPayload], context: ExtensionContext[RegistryPayload]) -> None
```
```python
async def test_fsm_hooks_before_and_after_transition(self, registry: ExtensionRegistry[RegistryPayload], context: ExtensionContext[RegistryPayload]) -> None
```
#### Top-Level Functions

```python
def registry() -> ExtensionRegistry[RegistryPayload]
```
```python
def context() -> ExtensionContext[RegistryPayload]
```
### File: `tests/test_schema_compatibility.py`

#### Top-Level Functions

```python
def base_schema()
```
```python
def test_schema_mismatch_raises_error(base_schema)
```
```python
def test_duplicate_fields_in_schema_raises_error()
```
```python
def test_discriminator_mutation_critical_violation(base_schema)
```
```python
def test_removed_fields_severity_evaluation(base_schema)
```
```python
def test_added_non_nullable_field_without_default(base_schema)
```
```python
def test_field_type_and_nullability_modifications(base_schema)
```
```python
def test_enforce_compatibility_raises_on_critical_violations(base_schema)
```
```python
def test_enforce_compatibility_passes_for_compatible_changes(base_schema)
```
### File: `tests/test_transforms.py`

#### Classes & Models

```python
class BrokenSyntaxTransformer(cst.CSTTransformer):
```
> Transformer that generates invalid Python code triggering SyntaxError on ast.parse().

**Methods:**
```python
def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module
```
```python
class CodeGenErrorTransformer(cst.CSTTransformer):
```
> Transformer that directly raises a CodeGenerationError.

**Methods:**
```python
def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module
```
```python
class GenericErrorTransformer(cst.CSTTransformer):
```
> Transformer that raises an unexpected generic Exception.

**Methods:**
```python
def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module
```
#### Top-Level Functions

```python
def test_future_annotations_inserted_at_top()
```
```python
def test_future_annotations_inserted_after_docstring()
```
```python
def test_future_annotations_already_present()
```
```python
def test_dead_code_cleanup_removes_standalone_pass()
```
```python
def test_dead_code_cleanup_preserves_single_pass()
```
```python
def test_import_organizer_deduplicates_imports()
```
```python
def test_formatting_gate_invalid_line_length()
```
```python
def test_formatting_gate_invalid_source_type()
```
```python
def test_formatting_gate_syntax_error()
```
```python
def test_formatting_gate_success()
```
```python
def test_formatting_gate_black_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None
```
```python
def test_formatting_gate_output_syntax_error(monkeypatch: pytest.MonkeyPatch) -> None
```
```python
def test_formatting_gate_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None
```
```python
def test_libcst_pipeline_invalid_source_type()
```
```python
def test_libcst_pipeline_parse_syntax_error()
```
```python
def test_libcst_pipeline_full_transform_pass()
```
```python
def test_libcst_pipeline_transformation_produces_invalid_syntax()
```
```python
def test_libcst_pipeline_reraises_code_generation_error()
```
```python
def test_libcst_pipeline_generic_exception_handling()
```
### File: `tests/test_verification.py`

#### Classes & Models

```python
class MockSubprocess:
```
> Mock process for asyncio.subprocess.Process.

**Methods:**
```python
def __init__(self, returncode: int | None = 0, stdout: bytes = b'', stderr: bytes = b'', raise_on_kill: type[Exception] | None = None, raise_on_communicate: type[Exception] | None = None) -> None
```
```python
async def communicate(self) -> tuple[bytes, bytes]
```
```python
def kill(self) -> None
```
```python
class TestBootVerifier:
```
**Methods:**
```python
def test_init_invalid_timeout_raises_value_error(self) -> None
```
```python
async def test_validate_project_root_failures(self, tmp_path: Path) -> None
```
```python
async def test_validate_package_name_failures(self, tmp_path: Path) -> None
```
```python
async def test_verify_boot_success(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_verify_boot_failure_exit_code_or_missing_token(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_verify_boot_timeout(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_verify_boot_exceptions(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_terminate_process_branches(self, monkeypatch: pytest.MonkeyPatch) -> None
```
```python
def test_decode_output_truncation(self) -> None
```
```python
class TestImportVerifier:
```
**Methods:**
```python
def test_init_invalid_timeout(self) -> None
```
```python
async def test_validate_inputs(self, tmp_path: Path) -> None
```
```python
async def test_verify_module_import_success_and_failures(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_verify_module_import_tool_and_os_errors(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_verify_all_imports_structure_checks(self, tmp_path: Path) -> None
```
```python
async def test_verify_all_imports_success_and_failure(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
def test_module_name_from_path_failures(self, tmp_path: Path) -> None
```
```python
class TestPackageVerifier:
```
**Methods:**
```python
def test_init_invalid_timeout(self) -> None
```
```python
async def test_validate_project_root_failures(self, tmp_path: Path) -> None
```
```python
async def test_pyproject_validation_failures(self, tmp_path: Path) -> None
```
```python
async def test_verify_package_success_and_failure(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_enforce_package_validity(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_package_tool_and_os_errors(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
class TestSyntaxVerifier:
```
**Methods:**
```python
def test_verify_file_failures_and_success(self, tmp_path: Path) -> None
```
```python
def test_verify_file_oserror(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
def test_verify_directory_failures_and_success(self, tmp_path: Path) -> None
```
```python
class TestTestSuiteVerifier:
```
**Methods:**
```python
def test_init_invalid_timeout(self) -> None
```
```python
async def test_validate_project_root(self, tmp_path: Path) -> None
```
```python
async def test_tests_dir_validation_failures(self, tmp_path: Path) -> None
```
```python
async def test_run_test_suite_success_and_failure(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_enforce_test_suite_pass(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_test_suite_exceptions(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
class TestTypeVerifier:
```
**Methods:**
```python
def test_init_invalid_timeout(self) -> None
```
```python
async def test_validate_project_root(self, tmp_path: Path) -> None
```
```python
async def test_src_dir_validation_failures(self, tmp_path: Path) -> None
```
```python
async def test_verify_types_success_and_parsed_issues(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_enforce_type_safety(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
async def test_type_tool_and_os_errors(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None
```
```python
class TestVerificationRunner:
```
**Methods:**
```python
async def test_input_validation_failures(self, tmp_path: Path) -> None
```
```python
async def test_run_pipeline_full_success(self, tmp_path: Path) -> None
```
```python
async def test_run_pipeline_gate_failures(self, tmp_path: Path) -> None
```