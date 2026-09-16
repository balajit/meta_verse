# Persistence Plane & Relational Storage Layer

## Overview
This phase provides the relational database foundation, AsyncPG engine pooling, PostgreSQL Row-Level Security (RLS) policies, precomputed transitive closure DAG tables, structured operational logging, and tamper-evident cryptographic event hash-chaining.

## File Registry & Technical Responsibilities

| File Path | Functional Scope & Implementation Details |
| --- | --- |
| `db_session/connection.py` | `MultiTenantDatabaseManager` providing session allocation, pool management, dynamic session variable configuration (`app.tenant_id`) for PostgreSQL RLS policies, and explicit context reset handling. |
| `models/base.py` | SQLAlchemy 2.0 Async Declarative `Base` and `TenantAwareMixin` defining UUID primary keys, tenant identifiers, and UTC timestamp metadata. |
| `models/registry.py` | `SpecificationRegistryModel` and `DAGLineageClosureModel` for precomputed graph dependency storage and rapid transitive closure lookups. |
| `models/audit.py` | `BuildJobAuditModel`, `BuildJobEventModel`, and `BuildIdempotencyKeyModel` for execution tracking, audit event chaining, and submission deduplication. |
| `lineage/closure_manager.py` | `LineageClosureManager` maintaining precomputed DAG transitive closure tables, converting $O(V+E)$ recursive queries into $O(1)$ indexed reads. |
| `audit/service.py` | `AppendOnlyAuditService` offering serialized row-level pessimistic locking (`with_for_update`) to eliminate sequence write race conditions. |
| `event_chain/crypt_chain.py` | `EventCryptographicChain` implementing SHA-256 hash chaining ($H_n = \text{SHA256}(H_{n-1} \parallel \text{seq} \parallel \text{payload})$) for tamper detection and audit log validation. |
| `migrations/env.py` | Alembic async migration configuration enabling Expand-Migrate-Contract cycles and PostgreSQL RLS policy creation scripts. |