from meta_compiler.contracts.action_registry import ActionRegistry
from pydantic import BaseModel


class ProvisionAccountInput(BaseModel):
    account_id: str
    username: str


class ProvisionAccountOutput(BaseModel):
    status: str
    account_id: str


def get_configured_action_registry() -> ActionRegistry:
    registry = ActionRegistry()

    # Register domain actions used by DAG execution nodes
    registry.register(
        action_name="provision_account",
        callable_func=lambda account_id, username: {"status": "created", "account_id": account_id},
        input_schema=ProvisionAccountInput,
        output_schema=ProvisionAccountOutput,
        version="1.0.0",
    )
    return registry