# Meta Control Plane (Phase 4)

Control plane framework exposing inspection, retry, and replanning tools to autonomous triage agents for self-healing platform execution.

## Repository Layout

```text
meta_control_plane/
├── README.md
├── src/
│   └── meta_control_plane/
│       ├── __init__.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── v1/
│       │   │   ├── __init__.py
│       │   │   ├── meta_manifest_api.py
│       │   │   ├── meta_execution_api.py
│       │   │   └── meta_graph_api.py
│       │   └── schemas/
│       │       ├── __init__.py
│       │       ├── meta_tool_schemas.py
│       │       └── meta_mutation_schemas.py
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── controller/
│       │   │   ├── __init__.py
│       │   │   ├── meta_triage_loop.py
│       │   │   └── meta_heuristic_cache.py
│       │   ├── diagnosis/
│       │   │   ├── __init__.py
│       │   │   ├── meta_failure_classifier.py
│       │   │   └── meta_tuning_heuristics.py
│       │   └── tools/
│       │       ├── __init__.py
│       │       ├── meta_inspect_tool.py
│       │       ├── meta_retry_tool.py
│       │       └── meta_replan_tool.py
│       ├── events/
│       │   ├── __init__.py
│       │   ├── meta_event_consumers.py
│       │   └── meta_telemetry_drivers.py
│       └── escalation/
│           ├── __init__.py
│           ├── meta_escalation_engine.py
│           └── meta_notification_channels.py
└── tests/
    ├── unit/
    │   ├── test_meta_tools.py
    │   └── test_meta_mutations.py
    └── integration/
        └── test_meta_triage_loop.py
