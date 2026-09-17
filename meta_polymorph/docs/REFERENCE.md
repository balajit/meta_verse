# meta_polymorph Reference Manual

## 1. System Overview & Architectural Boundaries

**Core Purpose**
`meta_polymorph` is a pure Python (>=3.13) dynamic polymorphic manifest layer resolver and Intermediate Representation (IR) compiler. It provides multi-tenant hierarchy resolution, differential layer overriding, and manifest compilation from layered dictionary structures into validated, immutable Pydantic `ManifestIR` containers.

**Separation of Concerns**

* **Library Scope**: Manages recursive dictionary merging, sentinel-based key removal (`"$unset"`), hierarchy resolution execution, OpenTelemetry tracing via `meta_telemetry`, and final schema validation into `ManifestIR`.


* **Host Application Responsibility**: Handles storage and retrieval of raw YAML or JSON layer manifests from disk/database, string deserialization into Python `dict` instances (e.g., using `ruamel.yaml`), tenant authentication, context assembly, and runtime execution or hydration of compiled `ManifestIR` payloads.



**Dependency Footprint**

* `pydantic>=2.0.0`: Immutable schema validation (`frozen=True`) and DTO definition.


* `meta-telemetry>=0.1.0`, `opentelemetry-api>=1.27.0`, `opentelemetry-sdk>=1.27.0`: Distributed tracing and structured JSON log correlation.


* `deepmerge>=2.0.0`, `ruamel.yaml>=0.18.0`: Underlying manifest parsing and dictionary processing utilities.


* Transitive dependencies are strictly minimized to preserve pure CPU execution speed and isolate layer resolution from dynamic network/storage side-effects.



---

## 2. Exported Public API Reference

The following 8 symbols are exported via `meta_polymorph.__all__`:

| Symbol | Type | Description | Async Safe |
| --- | --- | --- | --- |
| `ManifestIR`<br> | Class (`BaseModel`) | Immutable container for compiled intermediate manifest representations.

 | Yes (CPU bound) |
| `TenantContext`<br> | Class (`BaseModel`) | Immutable DTO defining tenant, industry, and global scope keys.

 | Yes (CPU bound) |
| `PolymorphicError`<br> | Exception | Base exception class for all domain errors within `meta_polymorph`.

 | N/A |
| `PolymorphicCompilationError`<br> | Exception | Raised when layer resolution or Pydantic schema validation fails.

 | N/A |
| `PolymorphicResolver`<br> | Class | Layer resolver executing sequential deep merges across hierarchy tiers.

 | Yes (CPU bound) |
| `PolymorphicPipeline`<br> | Class | High-level orchestrator compiling context and layers into `ManifestIR`.

 | Yes (CPU bound) |
| `DeepMerger`<br> | Class | Stateless class wrapper around recursive deep merge logic with telemetry.

 | Yes (CPU bound) |
| `deep_merge`<br> | Function | Pure recursive function that merges dictionary layers without mutating inputs.

 | Yes (CPU bound) |

### Detailed Symbol Specifications

**`TenantContext`**

* **Module**: `meta_polymorph.domain.dtos`

* **Configuration**: `model_config = ConfigDict(frozen=True)`

* **Fields**:
* `tenant_id: str` (Required)


* `industry_id: str` (Required)


* `global_id: str = "global"` (Optional, default `"global"`)





**`ManifestIR`**

* **Module**: `meta_polymorph.domain.dtos`

* **Configuration**: `model_config = ConfigDict(frozen=True)`

* **Fields**:
* `version: str = "1.0.0"`

* `namespace: str` (Required)


* `name: str` (Required)


* `description: str | None = ""`

* `tasks: list[dict[str, Any]] = Field(default_factory=list)`

* `entities: list[dict[str, Any]] = Field(default_factory=list)`

* `fsms: list[dict[str, Any]] = Field(default_factory=list)`




**`PolymorphicPipeline.compile_to_ir`**

* **Signature**: `compile_to_ir(cls, context: TenantContext, layers: list[dict[str, Any]]) -> ManifestIR`

* **Behavior**: Sequentially resolves pre-ordered dictionary layers from index $0$ (base) to $N$ (leaf/tenant). Applies fallback default attributes if `namespace` or `name` are unassigned in raw layers (`namespace = context.tenant_id`, `name = f"manifest_{context.tenant_id}"`).


* **Raises**: `PolymorphicCompilationError` if layer data is not a valid `dict` or fails `ManifestIR` validation.



**`deep_merge` & `DeepMerger.deep_merge**`

* **Signature**: `deep_merge(base: dict[str, Any], override: dict[str, Any], _current_depth: int = 0) -> dict[str, Any]`

* **Constants**:
* `UNSET_SENTINEL = "$unset"`

* `MAX_RECURSION_DEPTH = 100`



* **Behavior**: Deep copies the base dictionary. Replaces primitive values, recursively merges nested dictionaries, removes keys whose override value equals `"$unset"`, and completely replaces list entries. Raises `ValueError` if depth exceeds `MAX_RECURSION_DEPTH`.



**`PolymorphicCompilationError`**

* **Module**: `meta_polymorph.exceptions`

* **Inherits From**: `PolymorphicError` $\rightarrow$ `Exception`

* **Attributes**: `tenant_id: Optional[str]`, `entity_id: Optional[str]`, `original_exception: Optional[Exception]`

* **Methods**:
* `to_agent_context() -> dict[str, Any]`: Returns a structured, JSON-serializable metadata dictionary detailing `error_type`, `message`, `tenant_id`, `entity_id`, `original_exception_type`, and `original_exception_details` for automated triage.





---

## 3. Canonical Integration Patterns

**Synchronous / Asynchronous Host Integration**
`meta_polymorph` operations are pure Python, synchronous, and CPU-bound. In asynchronous host applications (e.g., FastAPI, AsyncIO task runners), invoke `PolymorphicPipeline.compile_to_ir` directly or delegate execution using `asyncio.to_thread` when processing large layer batches.

```python
import asyncio
from ruamel.yaml import YAML
from meta_polymorph import (
    ManifestIR,
    PolymorphicCompilationError,
    PolymorphicPipeline,
    TenantContext,
)

# 1. Initialize YAML parser (Host application scope)
yaml = YAML(typ="safe")

# 2. Raw layer manifest definitions (Loaded from storage by host app)
global_yaml_str = """
version: "1.0.0"
namespace: "core_platform"
name: "default_pipeline"
tasks:
  - id: "fetch_data"
    action: "http_get"
    timeout: 30
"""

tenant_yaml_str = """
name: "custom_tenant_pipeline"
tasks:
  - id: "fetch_data"
    action: "http_get"
    timeout: 60
"""

# 3. Deserialise layers into standard Python dictionaries
layers = [
    yaml.load(global_yaml_str),
    yaml.load(tenant_yaml_str),
]

# 4. Construct immutable TenantContext DTO
context = TenantContext(
    tenant_id="tenant_acme",
    industry_id="fintech"
)

# 5. Execute layer compilation pipeline
try:
    manifest_ir: ManifestIR = PolymorphicPipeline.compile_to_ir(
        context=context,
        layers=layers
    )
    print(f"Compiled Manifest: {manifest_ir.name} (Namespace: {manifest_ir.namespace})")
    print(f"Tasks: {manifest_ir.tasks}")
except PolymorphicCompilationError as exc:
    agent_logs = exc.to_agent_context()
    print(f"Compilation error context: {agent_logs}")

```

---

## 4. Edge Cases, Failure Modes & Anti-Patterns

> **WARNING: Non-Merging List Overrides**
> In `meta_polymorph`, list fields (e.g., `tasks`, `entities`, `fsms`) are **completely replaced** by higher-priority override layers. Elements within lists are not concatenated or set-merged. If an overriding layer defines a `tasks` list with 1 element, it overwrites the base layer's `tasks` list completely.
> 
> 

> **WARNING: Max Recursion Guard**
> `deep_merge` strictly limits dictionary nesting depth to `MAX_RECURSION_DEPTH = 100`. Exceeding this limit raises a `ValueError`.
> 
> 

**Explicit Anti-Patterns**

* **Passing Non-Dictionary Layers**:
* *Anti-Pattern*: Passing a list containing strings, `None`, or unparsed YAML strings to `PolymorphicPipeline.compile_to_ir`.


* *Correction*: Parse all layers into standard Python `dict` instances before invoking the pipeline.




* **Expecting Partial List Merges**:
* *Anti-Pattern*: Expecting a tenant layer to append a single task to a global `tasks` list.


* *Correction*: Redefine the full task sequence in the leaf layer if modification or extension is required.




* **Using Mutated Dictionary References**:
* *Anti-Pattern*: Modifying base input dictionaries after resolution.


* *Correction*: `deep_merge` returns deep copies, but host applications should treat input dicts as immutable. The resulting `ManifestIR` and `TenantContext` objects are frozen Pydantic models.




* **Ignoring `"$unset"` Sentinel Mechanics**:
* *Anti-Pattern*: Setting keys to `None` or `""` expecting to remove a base key.


* *Correction*: Explicitly pass `"$unset"` (or `UNSET_SENTINEL`) as the value in the overriding layer to delete the corresponding key from the merged manifest.