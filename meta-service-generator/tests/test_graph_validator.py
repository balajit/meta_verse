from types import SimpleNamespace
import pytest

from meta_service_generator.analysis.relationships import RelationshipGraph
from meta_service_generator.analysis.validation import IRSemanticValidator
from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.ir.model import IRPolicy, ServiceIR, IRWorkflow, IRWorkflowStep, IRModel, IRFSM, \
    IRTransition, IRRule


# --- Relationship Graph Validation Tests ---

def test_relationship_graph_duplicate_entity_error():
    manifest = SimpleNamespace(
        entities=[
            SimpleNamespace(name="User", relationships=[], attributes=[]),
            SimpleNamespace(name="User", relationships=[], attributes=[]),
        ]
    )
    with pytest.raises(IRBuilderError, match="Duplicate entity name 'User'"):
        RelationshipGraph(manifest)


def test_relationship_graph_unknown_target_error():
    manifest = SimpleNamespace(
        entities=[
            SimpleNamespace(
                name="User",
                relationships=[
                    SimpleNamespace(name="r1", target_entity="Role", foreign_key=None, cardinality="1:N")
                ],
                attributes=[],
            )
        ]
    )
    with pytest.raises(IRBuilderError, match="references unknown target entity 'Role'"):
        RelationshipGraph(manifest)


def test_relationship_graph_unknown_foreign_key_error():
    manifest = SimpleNamespace(
        entities=[
            SimpleNamespace(name="Role", relationships=[], attributes=[]),
            SimpleNamespace(
                name="User",
                relationships=[
                    SimpleNamespace(name="r1", target_entity="Role", foreign_key="missing_fk", cardinality="1:N")
                ],
                attributes=[SimpleNamespace(name="id", nullable=False)],
            ),
        ]
    )
    with pytest.raises(IRBuilderError, match="references foreign key 'missing_fk', but that attribute does not exist"):
        RelationshipGraph(manifest)


# --- IR Semantic Validator Tests ---

def test_validate_unique_model_names():
    service_ir = SimpleNamespace(
        service_name="TestService",
        models=[SimpleNamespace(name="User"), SimpleNamespace(name="User")],
        workflows=[],
        rules=[],
        policies=[],
    )
    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError, match="Duplicate IR model name 'User'"):
        validator.validate(service_ir)


def test_validate_fsm_reachability_errors():
    validator = IRSemanticValidator()

    # Unreachable state
    service_ir_unreachable = SimpleNamespace(
        service_name="FSMService",
        models=[
            SimpleNamespace(
                name="Order",
                fsm=SimpleNamespace(
                    initial_state="draft",
                    states=["draft", "submitted", "orphan_state"],
                    transitions=[
                        SimpleNamespace(trigger="submit", source_state="draft", target_state="submitted")
                    ],
                ),
            )
        ],
        workflows=[],
        rules=[],
        policies=[],
    )
    with pytest.raises(IRBuilderError, match="contains unreachable states: \\['orphan_state'\\]"):
        validator.validate(service_ir_unreachable)


def test_validate_workflow_dags_errors():
    validator = IRSemanticValidator()

    # Workflow step cycle
    service_ir_cycle = SimpleNamespace(
        service_name="WorkflowService",
        models=[],
        workflows=[
            SimpleNamespace(
                name="deploy",
                steps=[
                    SimpleNamespace(name="step_a", depends_on=["step_b"]),
                    SimpleNamespace(name="step_b", depends_on=["step_a"]),
                ],
            )
        ],
        rules=[],
        policies=[],
    )
    with pytest.raises(IRBuilderError, match="Circular step dependency detected in workflow 'deploy'"):
        validator.validate(service_ir_cycle)


def test_validate_business_rules_and_policies():
    validator = IRSemanticValidator()

    service_ir = SimpleNamespace(
        service_name="RulePolicyService",
        models=[SimpleNamespace(name="User", fsm=None)],
        workflows=[],
        rules=[
            SimpleNamespace(
                name="rule1",
                target_entity="User",
                expression="user.age >= 18",
                error_message="Underage",
            )
        ],
        policies=[
            SimpleNamespace(
                name="policy1",
                roles=["admin"],
                actions=["read", "write"],
            )
        ],
    )
    # Validation passes without error
    validator.validate(service_ir)

# -----------------------------------------------------------------------------
# IRSemanticValidator Coverage Tests
# -----------------------------------------------------------------------------

def test_validator_success():
    model = IRModel(name="User", class_name="User", table_name="users", fields=(), fsm=None)
    service_ir = ServiceIR(service_name="test_service", version="1.0.0", models=(model,), rules=(), workflows=(), policies=())
    validator = IRSemanticValidator()
    validator.validate(service_ir)


def test_validator_duplicate_model_names():
    model1 = IRModel(name="User", class_name="User", table_name="users", fields=(), fsm=None)
    model2 = IRModel(name="User", class_name="UserDuplicate", table_name="users_dup", fields=(), fsm=None)
    service_ir = ServiceIR(service_name="test_service", version="1.0.0", models=(model1, model2), rules=(), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_DUPLICATE_MODEL"


def test_validator_fsm_invalid_initial_state():
    fsm = IRFSM(state_attribute="status", initial_state="non_existent", states=("pending",), transitions=())
    model = IRModel(name="Order", class_name="Order", table_name="orders", fields=(), fsm=fsm)
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(model,), rules=(), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_FSM_INVALID_INITIAL_STATE"


def test_validator_fsm_unknown_source_state():
    transition = IRTransition(trigger="pay", source_state="unknown", target_state="paid")
    fsm = IRFSM(state_attribute="status", initial_state="pending", states=("pending", "paid"), transitions=(transition,))
    model = IRModel(name="Order", class_name="Order", table_name="orders", fields=(), fsm=fsm)
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(model,), rules=(), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_FSM_UNKNOWN_SOURCE_STATE"


def test_validator_fsm_unknown_target_state():
    transition = IRTransition(trigger="pay", source_state="pending", target_state="unknown")
    fsm = IRFSM(state_attribute="status", initial_state="pending", states=("pending", "paid"), transitions=(transition,))
    model = IRModel(name="Order", class_name="Order", table_name="orders", fields=(), fsm=fsm)
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(model,), rules=(), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_FSM_UNKNOWN_TARGET_STATE"


def test_validator_fsm_unreachable_state():
    fsm = IRFSM(state_attribute="status", initial_state="pending", states=("pending", "unreachable"), transitions=())
    model = IRModel(name="Order", class_name="Order", table_name="orders", fields=(), fsm=fsm)
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(model,), rules=(), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_FSM_UNREACHABLE_STATE"


def test_validator_workflow_duplicate_steps():
    step = IRWorkflowStep(name="step1", action="do_something", depends_on=())
    workflow = IRWorkflow(name="wf", steps=(step, step))
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(workflow,), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_WORKFLOW_DUPLICATE_STEP"


def test_validator_workflow_unknown_dependency():
    step = IRWorkflowStep(name="step1", action="do_something", depends_on=("missing",))
    workflow = IRWorkflow(name="wf", steps=(step,))
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(workflow,), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_WORKFLOW_UNKNOWN_DEPENDENCY"


def test_validator_workflow_self_dependency():
    step = IRWorkflowStep(name="step1", action="do_something", depends_on=("step1",))
    workflow = IRWorkflow(name="wf", steps=(step,))
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(workflow,), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_WORKFLOW_SELF_DEPENDENCY"


def test_validator_workflow_cycle():
    step1 = IRWorkflowStep(name="step1", action="do_something", depends_on=("step2",))
    step2 = IRWorkflowStep(name="step2", action="do_something", depends_on=("step1",))
    workflow = IRWorkflow(name="wf", steps=(step1, step2))
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(workflow,), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_WORKFLOW_CYCLE"


def test_validator_rule_unknown_target():
    rule = IRRule(name="rule1", target_entity="NonExistent", expression="x > 0", error_message="Err")
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(rule,), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_RULE_UNKNOWN_TARGET"


def test_validator_rule_empty_expression():
    model = IRModel(name="User", class_name="User", table_name="users", fields=(), fsm=None)
    rule = IRRule(name="rule1", target_entity="User", expression="   ", error_message="Err")
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(model,), rules=(rule,), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_RULE_EMPTY_EXPRESSION"


def test_validator_rule_empty_error_message():
    model = IRModel(name="User", class_name="User", table_name="users", fields=(), fsm=None)
    rule = IRRule(name="rule1", target_entity="User", expression="x > 0", error_message="")
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(model,), rules=(rule,), workflows=(), policies=())

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_RULE_EMPTY_ERROR_MESSAGE"


def test_validator_policy_empty_roles():
    policy = IRPolicy(name="pol", roles=(), actions=("read",))
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(), policies=(policy,))

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_POLICY_EMPTY_ROLES"


def test_validator_policy_empty_actions():
    policy = IRPolicy(name="pol", roles=("admin",), actions=())
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(), policies=(policy,))

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_POLICY_EMPTY_ACTIONS"


def test_validator_policy_whitespace_role():
    policy = IRPolicy(name="pol", roles=("   ",), actions=("read",))
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(), policies=(policy,))

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_POLICY_EMPTY_ROLE"


def test_validator_policy_whitespace_action():
    policy = IRPolicy(name="pol", roles=("admin",), actions=("  ",))
    service_ir = ServiceIR(service_name="test", version="1.0.0", models=(), rules=(), workflows=(), policies=(policy,))

    validator = IRSemanticValidator()
    with pytest.raises(IRBuilderError) as exc_info:
        validator.validate(service_ir)
    assert exc_info.value.error_code == "ERR_IR_POLICY_EMPTY_ACTION"