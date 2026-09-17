# Manifest Pipeline Shared Contract

You are participating in a staged manifest-generation pipeline.

AUTHORITATIVE FILE

schemas/manifest.schema.json

This file is authoritative for manifest representation.

BUSINESS INPUTS

The repository contains the authoritative business/domain requirements.
Do not invent their location. Search the repository to identify the relevant
requirements, workflow specifications, policy/business-rule documents, and
business/operational event specifications.

PIPELINE ARTIFACT DIRECTORY

.manifest-pipeline/

STAGES

01-schema-contract.json
02-domain-model.json
03-relationships.json
04-workflows.json
05-policies.json
06-manifest.json
07-validation.json
08-audit.json
final/manifest.json

GLOBAL RULES

1. Never modify schemas/manifest.schema.json.
2. Never invent domain concepts merely to satisfy the schema.
3. The schema controls representation.
4. The source requirements control business meaning.
5. Prefer explicit source information over inference.
6. Any inference must be minimal and necessary.
7. Do not create infrastructure as domain entities.
8. Do not create Event, KafkaTopic, Queue, Worker, Cache, SearchIndex,
   Elasticsearch, ClickHouse, Redis, Stripe, PayPal, Google, API, or Job
   entities unless the schema and business source explicitly establish them
   as domain entities.
9. Preserve information that cannot be structurally represented by using
   supported workflow actions, expressions, policies, or other existing
   fields where semantically appropriate.
10. Never weaken a business constraint merely to satisfy JSON Schema.
11. Never add unsupported schema properties.
12. All generated JSON artifacts must be valid JSON.
13. All final manifest changes must be deterministic and auditable.
14. Relationship cardinality is directional.
15. Never silently transform N:1 into 1:1.
16. Asynchronous execution must not be represented as a dependency on a
    nonexistent infrastructure entity.
17. Do not invent retry counts.
18. Do not invent authorization roles or claims.
19. Do not invent FSM states.
20. Do not invent convenience attributes such as created_at, updated_at,
    deleted_at, version, metadata, or status unless explicitly justified.

WHEN A STAGE COMPLETES

Write its canonical result to the prescribed artifact file.

Do not merely describe the result in chat.

The artifact is the contract consumed by the next stage.
