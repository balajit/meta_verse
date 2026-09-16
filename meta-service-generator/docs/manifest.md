# Write docs/manifest.md

cat << 'EOF' > fastapi_server_generator/docs/manifest.md

# FastAPI Server Generator — Manifest Specification

## 1. Manifest Structure Overview

The input manifest is a unified JSON or YAML document defining the domain data structures, security models, business rules, state transition graphs, and execution workflows for a target service.

Manifests are validated against `schemas/manifest.schema.json` before processing.

---

## 2. Top-Level Schema Anatomy

```yaml
version: "1.0.0"
service_name: "order_fulfillment_service"
database:
  dialect: "postgresql"
  driver: "asyncpg"

entities:
  - name: "Order"
    table_name: "orders"
    soft_delete: true
    optimistic_locking: true
    fields: [...]
    relationships: [...]

fsms:
  - name: "OrderFSM"
    entity: "Order"
    initial_state: "DRAFT"
    states: [...]
    transitions: [...]

business_rules:
  - name: "DiscountRules"
    entity: "Order"
    rules: [...]

workflows:
  - name: "CreateOrderWorkflow"
    entity: "Order"
    transactional: true
    steps: [...]

policies:
  - name: "OrderAccessPolicy"
    entity: "Order"
    rbac: [...]
    abac: [...]

