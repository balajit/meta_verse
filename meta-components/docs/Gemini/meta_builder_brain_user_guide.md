# `meta_builder_brain` Architecture & Developer Reference Guide

The `meta_builder_brain` component serves as the core intelligence, schema synthesis, and dynamic compilation engine within the Application Builder system. It ingests raw domain specifications, synthesizes structured entity meta-models and finite-state machines (FSMs) using multi-pass LLM prompts, resolves hierarchical namespace tree structures, enforces Open Policy Agent (OPA) policy guardrails, and dynamically compiles PostgreSQL database models at runtime using Python metaclasses.

---

## Component Architecture Overview

| Module Path | Primary Classes / Entrypoints | Responsibilities & Behaviors |
| --- | --- | --- |
| `meta_builder_brain.config` | `Settings`, `settings`<br> | Loads system settings and dynamically fetches runtime API keys (`ANTHROPIC_API_KEY`, `QWEN_API_KEY`) and database credentials from OpenBao HTTP endpoints.

 |
| `meta_builder_brain.core` | `NamespaceTier`, `ResolutionContext`, `ResolutionPath`, `ASTNode`, `PropertyGraph`, `MetaBrainError`<br> | Encapsulates system types, AST property graph representations, inheritance resolution contexts, and unified exception classes.

 |
| `meta_builder_brain.ingestion` | `DocumentParser`, `SchemaParser`, `WebScraperPool`, `inspect_and_generate_spec`<br> | Parses unstructured PDF/Markdown documents, extracts OpenAPI/JSON Schema AST property graphs, scrapes web specs via Playwright, and compiles Pydantic schemas.

 |
| `meta_builder_brain.synthesis` | `HermesSynthesisAgent`, `MetaBrainSynthesizer`, `LLMClient`, `mcp_server`<br> | Coordinates two-pass entity/FSM synthesis, manages LLM client connections, executes automated repair feedback loops, and provides FastMCP tools.

 |
| `meta_builder_brain.namespace` | `TreeResolver`, `CacheGuard`, `FallbackChainResolver`<br> | Traverses child-to-root ancestor chains via PostgreSQL recursive CTEs, provides thread-safe TTL path caching, and validates pairwise OPA invariants.

 |
| `meta_builder_brain.validation` | `NamespaceManifest`, `EntityModel`, `OPAEvaluator`, `SynthesisRetryLoop`<br> | Validates canonical schema meta-models via Pydantic v2, enforces Rego policies against OPA sidecars, and re-prompts LLMs on validation failure.

 |
| `meta_builder_brain.compiler` | `DynamicMetaclassBuilder`, `NamespaceManifestModel`, `AsyncSessionFactory`<br> | Persists namespace manifests to PostgreSQL and dynamically instantiates executable SQLAlchemy ORM models using `type()` metaclasses.

 |

---

## Runtime Initialization & Secret Management

Before executing schema synthesis or dynamic code compilation, the system initializes application settings, fetches credentials from OpenBao, and provisions persistent relational tables.

* **Environment Settings**: The `Settings` class manages configuration defaults (`DATABASE_URL`, `OPA_URL`, `CACHE_TTL_SECONDS`) and loads `.env` configurations.


* **Dynamic Secret Loading**: Calling `settings.load_secrets_from_openbao()` queries the OpenBao sidecar at `/v1/secret/data/meta_builder` to retrieve API keys (`ANTHROPIC_API_KEY`, `QWEN_API_KEY`) and dynamic database connections.


* **Database Provisioning**: The `init_db()` function asynchronously creates the `namespace_manifests` and `schema_revisions` persistence tables in PostgreSQL.



```python
from meta_builder_brain.config.settings import settings
from meta_builder_brain.compiler.store import init_db

async def initialize_brain_runtime():
    # Load dynamic secrets from OpenBao
    await settings.load_secrets_from_openbao()
    # Initialize PostgreSQL storage tables
    await init_db()

```

---

## Primary Engine Subsystems

### 1. Specification Ingestion & AST Normalization

The ingestion pipeline converts diverse input sources (PDFs, Markdown, OpenAPI specs, and raw JSON Schemas) into normalized abstract syntax tree (AST) property graphs:

* **Document Parsing**: `DocumentParser` utilizes PyMuPDF (`fitz`) for fast unstructured text page-block extraction and Docling for layout-aware Markdown structure generation.


* **AST Conversion**: `SchemaParser` transforms OpenAPI v3 and JSON Schema definitions into unified `PropertyGraph` models containing `ASTNode` and `ASTNodeProperty` objects.


* **Dynamic Web Scraping**: `WebScraperPool` manages an asynchronous Playwright headless Chromium browser pool to scrape remote specification endpoints under rate limits.


* **Code Generation**: `inspect_and_generate_spec` inspects input files and leverages `datamodel-code-generator` to compile standalone Pydantic v2 model files.



### 2. Multi-Pass Domain Synthesis Pipeline

The `HermesSynthesisAgent` and `MetaBrainSynthesizer` orchestrate two-pass LLM prompts to construct valid `NamespaceManifest` meta-models:

* **Pass 1 (Entity Schema Discovery)**: Queries local or remote LLM endpoints (e.g., Qwen/Gemma) using `LLMClient.generate_qwen_json()` to extract entities, attributes, data types, and primary key definitions into raw JSON.


* **Pass 2 (FSM Synthesis & Invariant Binding)**: Prompts Claude 3.5 Sonnet via `LLMClient.generate_anthropic()` to synthesize finite state machine (FSM) lifecycles, state transitions, guard conditions, and parent manifest inheritance.


* **Automated Repair Loop**: `SynthesisRetryLoop` catches Pydantic validation errors (`ValidationErrorTrace`) and re-prompts the LLM with error traces up to `max_retries=3` times to achieve valid schema output.



```python
from pathlib import Path
from meta_builder_brain.synthesis.agent import MetaBrainSynthesizer, HermesSynthesisAgent

# Facade pipeline execution
synthesizer = MetaBrainSynthesizer()
manifest, compiled_types_path = await synthesizer.synthesize_spec(
    spec_path=Path("./specs/fintech_v1.md"),
    spec_name="fintech_custom",
    output_dir=Path("./output"),
    tenant_id="tenant_001",
    tier="custom"
)

```

### 3. Hierarchical Namespace Resolution & OPA Policy Enforcement

Namespaces follow a three-tier hierarchy: `global` $\rightarrow$ `industry` $\rightarrow$ `custom`.

* **Recursive CTE Tree Traversal**: `TreeResolver.resolve_lineage()` issues PostgreSQL recursive CTE queries on `namespace_manifests` to construct an ordered child-to-root ancestor list while detecting cyclical inheritance.


* **Thread-Safe Memory Caching**: `CacheGuard` maintains an `asyncio.Lock`-guarded TTL cache for verified `ResolutionPath` models.


* **OPA Governance Evaluation**: `FallbackChainResolver` iterates along the ancestor chain and invokes `OPAEvaluator.evaluate_policy()` to enforce Rego policy checks (`fsm/inheritance`) for primary key immutability and state transition safety.



```python
from meta_builder_brain.core.types import ResolutionContext
from meta_builder_brain.namespace.fallback_chain import FallbackChainResolver

context = ResolutionContext(
    tenant_id="tenant_001",
    industry_domain="fintech",
    custom_namespace="tenant_account_v2"
)

resolver = FallbackChainResolver()
resolution_path, lineage_manifests = await resolver.resolve_and_validate(
    context=context,
    target_namespace_id="tenant_account_v2"
)

```

### 4. Dynamic Metaclass ORM Compilation

The `DynamicMetaclassBuilder` compiles resolved manifest lineage into executable SQLAlchemy ORM model classes at runtime:

* **Lineage Merging**: Manifests are merged in sequence from Root (`global`) down to Child (`custom`), allowing lower tiers to add or override entity attributes.


* **Data Type Mapping**: The `TYPE_MAP` dictionary maps manifest attribute types to native SQLAlchemy column definitions:


* `string` $\rightarrow$ `sqlalchemy.String`

* `integer` $\rightarrow$ `sqlalchemy.Integer`

* `float` $\rightarrow$ `sqlalchemy.Float`

* `boolean` $\rightarrow$ `sqlalchemy.Boolean`

* `datetime` $\rightarrow$ `sqlalchemy.DateTime(timezone=True)`

* `uuid` $\rightarrow$ `sqlalchemy.dialects.postgresql.UUID`

* `json` $\rightarrow$ `sqlalchemy.JSON`



* **Metaclass Allocation**: Constructs executable ORM classes dynamically via `type(class_name, (self.base_class,), class_dict)` and registers them in a local lookup cache.



```python
from meta_builder_brain.compiler.metaclass_builder import DynamicMetaclassBuilder

builder = DynamicMetaclassBuilder()
compiled_models = builder.compile_orm_models(lineage_manifests)

# Extract generated SQLAlchemy model class
AccountORM = compiled_models["Account"]

```

---

## System Integration Interfaces

### REST API Gateway Router (`/api/v1/gateway`)

The FastAPI service exposes gateway endpoints for ingestion and schema compilation:

* `POST /api/v1/gateway/ingest/raw`: Parses raw JSON/OpenAPI schema AST payloads, validates `NamespaceManifest`, and persists records to PostgreSQL.


* `POST /api/v1/gateway/ingest/openapi`: Enqueues background Playwright web scraping tasks to retrieve external OpenAPI specs.


* `POST /api/v1/gateway/ingest/rfc`: Submits raw specification text directly to `HermesSynthesisAgent` for two-pass LLM synthesis.


* `POST /api/v1/gateway/compile/{namespace_id}`: Triggers lineage resolution, OPA policy checks, and metaclass compilation for target namespaces.



### FastMCP Server Tools (`mcp_server`)

The `mcp_server` exposes `FastMCP` tools to allow LLM agents to inspect database schema states:

* `get_global_schema(entity_name: Optional[str])`: Queries base schema definitions stored under the `global` tier.


* `get_tenant_manifest(tenant_id: str, namespace_id: str)`: Fetches an active namespace manifest for a target tenant.


* `list_available_namespaces(tenant_id: str)`: Lists all accessible parent and ancestor namespace records for a given tenant.