# Compilation Engine & Code Synthesis Facade

## Overview
Houses the core code compilation pipeline (`meta_builder_brain`, `meta_polymorph`, `meta_compiler`). Converts raw inputs and spec deltas into normalized `ManifestIR` and emits target Python models and schemas.

## File Registry & Technical Responsibilities

| File Path | Functional Scope & Implementation Details |
| --- | --- |
| `brain_adapter/ir_sanitizer.py` | Sanitizes untrusted LLM outputs into schema-compliant `UNTRUSTED IR`. |
| `polymorph_adapter/manifest_merger.py` | Multi-tier spec delta merger building closed canonical `ManifestIR` payloads. |
| `meta_compiler/ast_builder.py` | Abstract Syntax Tree (AST) construction engine. |
| `meta_compiler/pydantic_emitter.py` | Synthesizes immutable Pydantic v2 domain model code strings. |
| `meta_compiler/sqlalchemy_emitter.py` | Synthesizes Async SQLAlchemy 2.0 ORM class structures and table schemas. |
| `verification/ruff_mypy_runner.py` | Invocations adapter for isolated sub-process `ruff` formatting and `mypy` strict type checking. |
| `verification/temporal_validator.py` | AST scanner checking Temporal workflow determinism constraints. |
