# `meta_polymorph` Technical Architecture & Integration Guide

`meta_polymorph` is an advanced dynamic metadata hydration, multi-tenant namespace inheritance, structural polymorphic merging, and Finite State Machine (FSM) persistence component. It acts as the upper-level specification engine for the Application Builder ecosystem, preparing, validating, and transforming complex workflow Directed Acyclic Graphs (DAGs) across inheritance tiers before passing them to the lower-level execution and IR engine (`meta_compiler`).

---

## 1. Core Architecture & Hierarchy Tiers

### Architectural Layers

```
+---------------------------------------------------------------------------------+
|                                 Application                                     |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                            meta_polymorph Engine                                |
|                                                                                 |
|  +-----------------------+   +----------------------+   +--------------------+  |
|  |   Namespace Engine    |   |  Hydrator & Parser   |   | Polymorphic Merger |  |
|  | (TreeResolver, Cache) |   | (Ruamel AST/Hasher)  |   |  (DeepMerger/DAG)  |  |
|  +-----------------------+   +----------------------+   +--------------------+  |
|                                         |                                       |
|  +--------------------------------------+------------------------------------+  |
|  |                    FSM & State Persister Engine                           |  |
|  |        (DynamicEntityStateMachine, OptimisticLocking, Outbox)             |  |
|  +---------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                         CompilerAdapter / Handoff                               |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                        meta_compiler (Phase 1 IR Orchestration)                 |
+---------------------------------------------------------------------------------+

```

### Hierarchy Tiers & Inheritance Order

* **Namespace Tiers**: Higher-level tiers inherit and override lower tiers in strict order: **`GLOBAL` $\rightarrow$ `INDUSTRY` $\rightarrow$ `CUSTOM**`.
* **Tree Resolver & Cycle Prevention**: `TreeResolver` builds candidate resolution paths via NetworkX DAG traversals and strictly prevents cyclical parent-child relationships using runtime graph validation.
* **Deterministic Hashing**: Manifests are normalized from Ruamel AST wrappers into primitive standard dictionaries and hashed via `canonical-json-v1` SHA-256 signatures to ensure idempotency and snapshot immutability.

---

## 2. Component Pipeline & Key Modules

| Module Path | Core Class / Functions | Primary Responsibility |
| --- | --- | --- |
| `meta_polymorph.namespace` | `TreeResolver`, `NamespaceResolver`, `CacheGuard`, `FallbackChainEvaluator` | Manages tenant namespace DAGs, resolves inheritance chains, enforces cycle detection, and caches lookup paths. |
| `meta_polymorph.hydrator` | `ManifestYAMLParser`, `ManifestSchemaValidator`, `ManifestHasher`, `BaseRealizer` | Handles loss-free Ruamel AST parsing, JSONSchema Draft 2020-12 validation, primitive normalization, and canonical hashing. |
| `meta_polymorph.merger` | `PolymorphicMerger`, `DeepMerger`, `DAGDeltaCompiler`, `ContractChecker` | Merges multi-tier JSON structures, applies RFC 6902 patches, executes DAG operations (`ADD`, `REPLACE`, `DISABLE`, `WRAP`), and checks interface types. |
| `meta_polymorph.fsm` | `DynamicEntityStateMachine`, `LifecycleGuard`, `StatePersister`, `TransitionHookRegistry` | Enforces entity state transitions (`DRAFT`, `PENDING_APPROVAL`, `ACTIVE`, `DEPRECATED`, `ARCHIVED`), pre/post-commit hooks, and outbox staging. |
| `meta_polymorph.adapters` | `CompilerAdapter` | Adapts hydrated payload specifications into `ManifestIR` (`NodeIR`, `EdgeIR`) and hands off directly to `meta_compiler`. |
| `meta_polymorph.db` | `EntityInstanceRepository`, ORM Models (`NamespaceModel`, `EntityDefinitionModel`, `EntityInstanceModel`) | Handles persistent database models, transactional outbox message staging, and version lock state transitions. |

---

## 3. Polymorphic Merging & DAG Operations

The `PolymorphicMerger` combines multi-tier manifests by evaluating sequence operations:

1. **Attributes Deep Merge**: Combines base dictionaries sequentially (`DeepMerger`).
2. **DAG Initialization**: Seeds initial node/edge set from base specs (`DAGDeltaCompiler`).
3. **DAG Delta Operations (`MergeOp`)**:
* **`ADD`**: Appends a new node and connects defined target edges.
* **`REPLACE`**: Updates node attributes while strictly preserving existing input/output edges.
* **`DISABLE`**: Sets `disabled=True` on a node while preserving edge topology to avoid broken downstream dependencies.
* **`WRAP`**: Inserts an interceptor node between target inputs and the node without introducing cycles.


4. **JSON Patches**: Applies explicit RFC 6902 operations (`jsonpatch`) over merged attribute structures.
5. **Deterministic Export**: Exports NetworkX graph nodes and edges in sorted order and generates the final canonical manifest hash signature.

---

## 4. FSM Lifecycle Management & Persistence

### Entity Lifecycle States

`DRAFT` $\rightarrow$ `PENDING_APPROVAL` $\rightarrow$ `ACTIVE` $\rightarrow$ `DEPRECATED` $\rightarrow$ `ARCHIVED`

### State Transitions & Persistence Mechanics

* **Atomic Version Locking**: State updates in `StatePersister` evaluate expected versions using optimistic lock concurrency checks. Mismatches raise `OptimisticLockError`.
* **Pre/Post-Commit Hooks**: Pre-commit hooks run within the active database transaction scope (triggering rollbacks on errors). Post-commit hooks execute asynchronously following transaction commit.
* **Transactional Outbox Staging**: Outbox messages (`outbox_messages`) are written within the same database transaction block as state updates, guaranteeing at-least-once event delivery for downstream systems.

---

## 5. End-to-End Code Integration Example

The following code illustrates building an in-memory namespace tree, merging multi-tier manifests, evaluating FSM transitions, and compiling the output into `meta_compiler`:

```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from meta_polymorph.core.types import LifecycleState, NamespaceTier, ResolutionContext
from meta_polymorph.namespace.tree_resolver import TreeResolver
from meta_polymorph.namespace.models import NamespaceNode
from meta_polymorph.namespace.resolver import NamespaceResolver
from meta_polymorph.merger.polymorphic_merge import PolymorphicMerger
from meta_polymorph.adapters.compiler_adapter import CompilerAdapter
from meta_polymorph.domain.dtos import HydratedManifestPayload
from meta_polymorph.fsm.lifecycle_guard import LifecycleGuard
from meta_polymorph.fsm.models import TransitionRequest
from meta_polymorph.fsm.state_persister import StatePersister

async def run_pipeline():
    # 1. Setup Namespace DAG Tree
    tree_resolver = TreeResolver()
    tree_resolver.add_node(NamespaceNode(id="global", name="Global Tier", tier=NamespaceTier.GLOBAL))
    tree_resolver.add_node(NamespaceNode(id="fintech", name="FinTech Industry", tier=NamespaceTier.INDUSTRY, parent_id="global"))
    tree_resolver.add_node(NamespaceNode(id="acme_tenant", name="Acme Tenant", tier=NamespaceTier.CUSTOM, parent_id="fintech"))

    # 2. Resolve Path
    resolver = NamespaceResolver(tree_resolver)
    ctx = ResolutionContext.create(tenant_id="acme_tenant", industry_domain="fintech", custom_namespace="acme_tenant")
    resolution_path = resolver.resolve_candidate_path(ctx)
    print(f"Resolved Path: {resolution_path.path}")

    # 3. Polymorphic Multi-Tier Merging
    global_manifest = {
        "attributes": {"environment": "production", "retries": 3},
        "nodes": [{"id": "fetch_data", "type": "input"}, {"id": "process_data", "type": "compute"}],
        "edges": [["fetch_data", "process_data"]]
    }
    custom_manifest = {
        "attributes": {"retries": 5},
        "deltas": [
            {"op": "WRAP", "target_id": "process_data", "payload": {"wrapper_id": "audit_logger", "wrapper_attrs": {"type": "logger"}}}
        ]
    }

    merger = PolymorphicMerger()
    merged_spec, manifest_hash = merger.merge_tier_manifests([global_manifest, custom_manifest])
    print(f"Merged Canonical Hash: {manifest_hash}")

    # 4. FSM Validation
    fsm_guard = LifecycleGuard()
    fsm_guard.evaluate(current_state=LifecycleState.DRAFT, target_state=LifecycleState.PENDING_APPROVAL)

    # 5. Database Session & Compiler Handoff
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        # State Persistence
        persister = StatePersister(session=session)
        transition_req = TransitionRequest(
            entity_id="entity_spec_001",
            target_state=LifecycleState.PENDING_APPROVAL,
            event_name="submit",
            actor_id="admin_user",
            expected_version=1,
            payload=merged_spec
        )
        # Note: Database schema initialization assumed prior to execution in live usage

        # Emit to meta_compiler adapter
        payload = HydratedManifestPayload(
            tenant_id="acme_tenant",
            entity_id="workflow_pipeline",
            spec=merged_spec
        )
        adapter = CompilerAdapter(session=session)
        # Handoff to meta_compiler orchestrator (mocked/integrated engine step)
        # result = await adapter.emit_to_compiler(payload)

if __name__ == "__main__":
    asyncio.run(run_pipeline())

```