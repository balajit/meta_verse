# MetaBuilder Polymorphic Execution Platform 'meta_polymorph' - Phase 2

Phase 2 transitions MetaBuilder from a static DAG compiler (`meta_compiler`) into a dynamic polymorphic execution platform (`{MODULE_NAME}`)[cite: 7, 8]. It introduces multi-tenant hierarchy resolution, differential overriding, entity FSM state mechanics, and foundational platform manifests (Learning Platform and Commerce Platform)[cite: 7, 8].

---

## Directory Functionality & Architectural Overview

```text
.
├── pyproject.toml
├── README.md
├── src/
│   └── {MODULE_NAME}/
│       ├── config/             # System configuration management & OPA policy evaluation rules.
│       ├── core/               # Shared exception hierarchies, constants, and fundamental types.
│       ├── namespace/          # 1. Namespace Resolution Engine (Hierarchy traversal & dynamic lookup).
│       ├── merger/             # 2. Polymorphic Merge Engine (JSON patch, delta graph compilation, contracts).
│       ├── fsm/                # 3. Entity FSM State Engine (Lifecycle guards, state transitions, hooks).
│       ├── hydrator/           # 4. Dynamic Manifest Hydrator & Domain Realizers (YAML parsing & platforms).
│       ├── db/                 # Database layer with SQLAlchemy Async models and session handlers.
│       └── manifests/          # Declarative YAML manifests across Global, Industry, and Custom tiers.
└── tests/                      # Automated unit and integration test suites for Phase 2 components.