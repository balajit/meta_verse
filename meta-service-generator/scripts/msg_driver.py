import asyncio
from pathlib import Path
from meta_service_generator.msg_engine import MetaServiceGeneratorEngine


class ServiceGeneratorDriver:
    """
    Driver class containing a comprehensive, multi-domain sample manifest
    exercising entities, attributes, relationships, FSM states, business rules,
    workflows, and policies matching ManifestSpec.
    """

    @staticmethod
    def get_comprehensive_manifest() -> dict:
        return {
          "version": "1.0.0",
          "service_name": "enterprise_order_service",
          "entities": [
            {
              "name": "Order",
              "class_name": "Order",
              "tableName": "orders",
              "attributes": [
                {"name": "id", "type": "str", "primary_key": True},
                {"name": "customer_id", "type": "str", "indexed": True},
                {"name": "total_amount", "type": "float", "nullable": False},
                {"name": "status", "type": "str", "nullable": False}
              ],
              "relationships": [
                {
                  "name": "items",
                  "target_entity": "OrderItem",
                  "cardinality": "1:N",
                  "foreign_key": "order_id"
                }
              ],
              "fsm": {
                "state_attribute": "status",
                "initial_state": "DRAFT",
                "states": ["DRAFT", "PENDING_APPROVAL", "APPROVED", "PUBLISHED"],
                "transitions": [
                  {
                    "trigger": "submit",
                    "source_state": "DRAFT",
                    "target_state": "PENDING_APPROVAL"
                  },
                  {
                    "trigger": "approve",
                    "source_state": "PENDING_APPROVAL",
                    "target_state": "APPROVED"
                  },
                  {
                    "trigger": "publish",
                    "source_state": "APPROVED",
                    "target_state": "PUBLISHED"
                  }
                ]
              }
            },
            {
              "name": "OrderItem",
              "class_name": "OrderItem",
              "tableName": "order_items",
              "attributes": [
                {"name": "id", "type": "str", "primary_key": True},
                {"name": "order_id", "type": "str", "nullable": False},
                {"name": "sku", "type": "str", "nullable": False},
                {"name": "quantity", "type": "int", "nullable": False}
              ]
            }
          ],
          "business_rules": [
            {
              "name": "order_value_validation",
              "priority": 1,
              "target_entity": "Order",
              "expression": "total_amount > 0.0",
              "error_code": "ERR_ORDER_VALUE_INVALID",
              "error_message": "Order total amount must be greater than zero."
            }
          ],
          "workflows": [
            {
              "name": "create_order_workflow",
              "execution_mode":  "sequential",
              "timeout_seconds": 30.0,
              "steps": [
                {
                  "name": "validate_payload",
                  "action": "validate",
                  "max_retries": 3,
                  "retry_policy": {
                    "max_retries": 3,
                    "multiplier": 1.0,
                    "min_seconds": 1.0,
                    "max_seconds": 5.0
                  },
                  "timeout_seconds": 5.0
                },
                {
                  "name": "persist_order",
                  "action": "persist",
                  "depends_on": ["validate_payload"],
                  "max_retries": 3,
                  "retry_policy": {
                    "max_retries": 3,
                    "multiplier": 1.0,
                    "min_seconds": 1.0,
                    "max_seconds": 5.0
                  },
                  "timeout_seconds": 10.0
                }
              ]
            }
          ],
          "policies": [
            {
              "name": "order_access_policy",
              "roles": ["customer", "admin"],
              "actions": ["create", "read", "delete"],
              "claims_required": ["sub"]
            }
          ]
        }

    @classmethod
    def run_pipeline(cls) -> None:
        manifest = cls.get_comprehensive_manifest()
        engine = MetaServiceGeneratorEngine(default_output_dir="generated_enterprise_service")

        print("Starting code synthesis and verification pipeline...")
        result = engine.generate_service(manifest_source=manifest, verify=True)

        print(f"Generation Status: {result['status']}")
        print(f"Artifact Output Path: {result['output_directory']}")
        print(f"Verification Summary: {result['verification']}")


if __name__ == "__main__":
    ServiceGeneratorDriver.run_pipeline()