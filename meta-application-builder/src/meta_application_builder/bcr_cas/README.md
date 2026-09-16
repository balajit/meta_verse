# Blueprint Component Registry (BCR) & CAS Engine

## Overview
Coordinates global URN resolutions (`urn:meta:bcr:...`), lifecycle state machines (`DRAFT`, `ACTIVE`, `DEPRECATED`, `RETIRED`), physical Content-Addressed Storage (CAS) operations, and bulk dependency tree resolutions.

## File Registry & Technical Responsibilities

| File Path | Functional Scope & Implementation Details |
| --- | --- |
| `urn_resolver/urn_parser.py` | Standardized URN string parsing, schema validation, and scope extraction. |
| `urn_resolver/lifecycle_state.py` | Enforces state transitions and dependency resolution matrices across versioned URN records. |
| `cas_service/cas_storage.py` | Physical CAS manager supporting staged writes, atomic promotions, and path partitioning. |
| `cas_service/digest_verifier.py` | SHA-256 byte-stream verifier for incoming and stored CAS code artifacts. |
| `bulk_api/resolve_batch.py` | Bulk URN resolution engine fetching complete closure graphs in a single request. |
| `bulk_api/publication_saga.py` | Reserve (`/reserve`) and Commit (`/commit`) endpoint controllers for idempotent artifact publication. |