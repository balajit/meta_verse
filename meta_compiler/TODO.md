# meta_compiler — TODO / Deferred Work

This file tracks work that was explicitly deferred or planned but not implemented
in the current remediation pass. Items are ordered by priority.

## Deferred by decision (awaiting user sign-off)

### 1. Sandbox `custom_types_module` execution (gVisor-like isolation)
**Status:** Postponed (decision: integrate a gVisor-like sandbox environment later)

The compiler accepts a `custom_types_module` path and executes the referenced
Python file via `importlib.util.spec_from_file_location(...)` +
`spec.loader.exec_module(...)`. This is arbitrary code execution if an attacker
can influence the path; the `.py` suffix check is not a sandbox.

Planned remediation:
- Run dynamic module execution in an isolated worker / container with a narrow
  IPC contract (gVisor / OCI sandbox).
- Register trusted model packages at application bootstrap as the primary path.
- Enforce an allowlisted import namespace.
- Never import arbitrary filesystem paths supplied by manifests.

### 2. `reorganize.py` production-safety guardrails
**Status:** Postponed (not present under `src/`; exists only in `mc_review` snapshots)

If `reorganize.py` is re-introduced, it must add:
- `main()` / `if __name__ == "__main__"` guard,
- dry-run mode,
- confirmation prompt,
- repository-root verification,
- rollback / backup / transaction boundary.

Destructive filesystem operations at import/run time are unacceptable.

## Non-blocking follow-ups

### 3. Structured error triage beyond stack strings
Replace remaining raw `"error": str(err)` extra fields with structured
`error_type` + `root_cause` + `component` on all error log records.

### 4. Tenacity for retry/backoff if convergence/retry logic expands
The review recommends Tenacity for any future retry/backoff; adopt only when
retry logic grows.

### 5. Jinja2 if dynamic source templates are still required
The review recommends Jinja2 for templated source generation if templates must
remain. Currently all generation is code-driven (datamodel-code-generator).

### 6. Contract checker structural compatibility (optional, non-blocking)
`is_type_compatible()` only treats a producer/consumer pair as compatible when
types are identical or a subclass relation holds. Distinct-but-structurally
identical BaseModel classes are always flagged and an adapter injected. This is
currently intended semantics (strict contract identity + functional adapter),
but a structural JSON-Schema compatibility fallback could reduce spurious
adapters. Not required by REVIEW.md; revisit in a later phase.
