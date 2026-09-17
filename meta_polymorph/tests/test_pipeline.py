import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

from meta_polymorph import (
    ManifestIR,
    PolymorphicCompilationError,
    PolymorphicPipeline,
    TenantContext,
)


def test_polymorphic_pipeline_compile_to_ir_end_to_end():
    global_yaml = """
    version: "1.0.0"
    namespace: "global_default"
    name: "base_workflow"
    description: "Global base workflow template"
    tasks:
      - id: "task_ingest"
        action: "read_source"
    entities:
      - name: "BaseRecord"
    fsms:
      - name: "default_fsm"
        initial: "DRAFT"
    """

    industry_yaml = """
    namespace: "fintech"
    description: "Fintech industry workflow template"
    entities:
      - name: "TransactionRecord"
    """

    tenant_yaml = """
    name: "acme_custom_workflow"
    description: "Acme specific payment workflow"
    tasks:
      - id: "task_acme_process"
        action: "process_payment"
    """

    yaml = YAML(typ="safe")
    layers = [
        yaml.load(global_yaml),
        yaml.load(industry_yaml),
        yaml.load(tenant_yaml),
    ]

    context = TenantContext(
        tenant_id="tenant_acme",
        industry_id="fintech",
        global_id="global"
    )

    manifest_ir = PolymorphicPipeline.compile_to_ir(context, layers)

    assert isinstance(manifest_ir, ManifestIR)
    assert manifest_ir.version == "1.0.0"
    assert manifest_ir.namespace == "fintech"
    assert manifest_ir.name == "acme_custom_workflow"
    assert manifest_ir.description == "Acme specific payment workflow"
    assert manifest_ir.tasks == [{"id": "task_acme_process", "action": "process_payment"}]
    assert manifest_ir.entities == [{"name": "TransactionRecord"}]
    assert manifest_ir.fsms == [{"name": "default_fsm", "initial": "DRAFT"}]


def test_polymorphic_pipeline_fallback_defaults():
    context = TenantContext(
        tenant_id="tenant_beta",
        industry_id="healthcare"
    )

    manifest_ir = PolymorphicPipeline.compile_to_ir(context, [])

    assert manifest_ir.namespace == "tenant_beta"
    assert manifest_ir.name == "manifest_tenant_beta"


def test_polymorphic_pipeline_validation_error():
    context = TenantContext(
        tenant_id="tenant_error",
        industry_id="logistics"
    )

    invalid_layers = [{"tasks": "not_a_list"}]

    with pytest.raises(PolymorphicCompilationError) as exc_info:
        PolymorphicPipeline.compile_to_ir(context, invalid_layers)

    err = exc_info.value
    assert err.tenant_id == "tenant_error"
    assert isinstance(err.original_exception, ValidationError)


def test_polymorphic_pipeline_rejects_malformed_layers():
    context = TenantContext(
        tenant_id="tenant_robust",
        industry_id="retail"
    )

    malformed_layers = [
        {
        None,
        "string_layer",
        }
    ]

    with pytest.raises(PolymorphicCompilationError) as exc_info:
        PolymorphicPipeline.compile_to_ir(context, malformed_layers)

    err = exc_info.value
    assert err.tenant_id == "tenant_robust"
    assert "is not a valid dictionary" in str(err)