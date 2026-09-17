# Meta-Builder Compiler Engine (`meta_compiler`)

The `meta_compiler` package is the core specification compilation and graph validation engine for Meta-Builder. It processes declarative YAML specifications through a five-stage pipeline to validate syntax, enforce typed data boundaries, verify DAG topologies, dry-run node contract compatibility, and serialize verified execution graphs into PostgreSQL state storage (`meta_workflow_definitions`).

---

## 🏗 Package Structure

```text
src/meta_compiler/
├── __init__.py
├── config.py                         # Environment configurations & meta-schema paths
├── schemas/
│   └── meta_schema_v1.json           # JSON Schema Draft 2020-12 static rules
├── guards/
│   ├── __init__.py
│   └── syntax_guard.py               # Step 1: jsonschema structural validation
├── compilers/
│   ├── __init__.py
│   ├── models.py                     # Pydantic V2 core models & dynamic specs
│   └── model_compiler.py             # Step 2: Typed model synthesis & payload bounds
├── validators/
│   ├── __init__.py
│   └── topology_validator.py         # Step 3: NetworkX DiGraph & cycle detection
├── contracts/
│   ├── __init__.py
│   └── contract_checker.py           # Step 4: Apache Hamilton in-memory DAG checks
├── persistence/
│   ├── __init__.py
│   └── db_serializer.py              # Step 5: SQLAlchemy async JSONB persistence
└── orchestrator.py                   # Main pipeline facade orchestrating Steps 1–5
