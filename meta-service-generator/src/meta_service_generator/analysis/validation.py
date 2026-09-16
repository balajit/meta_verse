from __future__ import annotations

from collections import Counter, deque
import graphlib

from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.ir.model import ServiceIR
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span


logger = get_logger(
    "meta_service_generator.analysis.validation"
)
tracer = get_tracer(
    "meta_service_generator.analysis.validation"
)


class IRSemanticValidator:
    """Performs deep semantic validation on ServiceIR prior to code synthesis [source: 3]."""

    @trace_span("analysis.validation.validate")
    def validate(
        self,
        service_ir: ServiceIR,
    ) -> None:
        """Executes all semantic IR checks and halts generation on any invariant violation."""

        if not isinstance(
            service_ir,
            ServiceIR,
        ):
            raise IRBuilderError(
                message=(
                    "IR semantic validation requires ServiceIR; "
                    f"received {type(service_ir).__name__}."
                ),
                location="service_ir",
                error_code="ERR_IR_VALIDATION_INVALID_INPUT",
                suggested_resolution=(
                    "Pass the immutable ServiceIR produced by IRBuilder."
                ),
                details={
                    "received_type": type(service_ir).__name__,
                },
            )

        self._validate_unique_model_names(
            service_ir
        )

        self._validate_fsm_reachability(
            service_ir
        )

        self._validate_workflow_dags(
            service_ir
        )

        self._validate_business_rules(
            service_ir
        )

        self._validate_policies(
            service_ir
        )

        logger.info(
            "IR semantic validation completed successfully.",
            extra={
                "event_type": (
                    "analysis.validation.completed"
                ),
                "service_name": service_ir.service_name,
                "model_count": len(
                    service_ir.models
                ),
                "rule_count": len(
                    service_ir.rules
                ),
                "workflow_count": len(
                    service_ir.workflows
                ),
                "policy_count": len(
                    service_ir.policies
                ),
            },
        )

    @trace_span(
        "analysis.validation.validate_unique_model_names"
    )
    def _validate_unique_model_names(
        self,
        service_ir: ServiceIR,
    ) -> None:
        seen: set[str] = set()

        for model in service_ir.models:
            if model.name in seen:
                raise IRBuilderError(
                    message=(
                        f"Duplicate IR model name "
                        f"'{model.name}'."
                    ),
                    location=f"models/{model.name}",
                    error_code="ERR_IR_DUPLICATE_MODEL",
                    suggested_resolution=(
                        "Ensure each entity produces exactly "
                        "one unique IR model."
                    ),
                )

            seen.add(
                model.name
            )

    @trace_span(
        "analysis.validation.validate_fsm_reachability"
    )
    def _validate_fsm_reachability(
        self,
        service_ir: ServiceIR,
    ) -> None:
        """Verifies that all declared states in an FSM are reachable from initial_state via BFS [source: 3]."""

        for model in service_ir.models:
            if model.fsm is None:
                continue

            fsm = model.fsm

            declared_states = set(
                fsm.states
            )

            if fsm.initial_state not in declared_states:
                raise IRBuilderError(
                    message=(
                        f"FSM on entity '{model.name}' declares "
                        f"initial state '{fsm.initial_state}', "
                        "which is not present in states."
                    ),
                    location=(
                        f"entities/{model.name}/"
                        "fsm/initial_state"
                    ),
                    error_code=(
                        "ERR_IR_FSM_INVALID_INITIAL_STATE"
                    ),
                    suggested_resolution=(
                        "Add initial_state to the FSM states declaration."
                    ),
                )

            adjacency: dict[
                str,
                set[str],
            ] = {
                state: set()
                for state in declared_states
            }

            for transition in fsm.transitions:
                if (
                    transition.source_state
                    not in declared_states
                ):
                    raise IRBuilderError(
                        message=(
                            f"FSM transition '{transition.trigger}' "
                            f"references unknown source state "
                            f"'{transition.source_state}'."
                        ),
                        location=(
                            f"entities/{model.name}/"
                            "fsm/transitions"
                        ),
                        error_code=(
                            "ERR_IR_FSM_UNKNOWN_SOURCE_STATE"
                        ),
                        suggested_resolution=(
                            "Ensure every transition source_state "
                            "is declared."
                        ),
                    )

                if (
                    transition.target_state
                    not in declared_states
                ):
                    raise IRBuilderError(
                        message=(
                            f"FSM transition '{transition.trigger}' "
                            f"references unknown target state "
                            f"'{transition.target_state}'."
                        ),
                        location=(
                            f"entities/{model.name}/"
                            "fsm/transitions"
                        ),
                        error_code=(
                            "ERR_IR_FSM_UNKNOWN_TARGET_STATE"
                        ),
                        suggested_resolution=(
                            "Ensure every transition target_state "
                            "is declared."
                        ),
                    )

                adjacency[
                    transition.source_state
                ].add(
                    transition.target_state
                )

            reachable: set[str] = set()

            queue: deque[str] = deque(
                [fsm.initial_state]
            )

            while queue:
                current = queue.popleft()

                if current in reachable:
                    continue

                reachable.add(
                    current
                )

                for neighbor in sorted(
                    adjacency.get(
                        current,
                        set(),
                    )
                ):
                    if neighbor not in reachable:
                        queue.append(
                            neighbor
                        )

            unreachable = (
                declared_states - reachable
            )

            if unreachable:
                unreachable_states = sorted(
                    unreachable
                )

                raise IRBuilderError(
                    message=(
                        f"FSM on entity '{model.name}' contains "
                        f"unreachable states: {unreachable_states}."
                    ),
                    location=(
                        f"entities/{model.name}/fsm"
                    ),
                    error_code=(
                        "ERR_IR_FSM_UNREACHABLE_STATE"
                    ),
                    suggested_resolution=(
                        f"Add transitions connecting initial_state "
                        f"'{fsm.initial_state}' to states "
                        f"{unreachable_states}."
                    ),
                    details={
                        "unreachable_states": (
                            unreachable_states
                        ),
                    },
                )

    @trace_span(
        "analysis.validation.validate_workflow_dags"
    )
    def _validate_workflow_dags(
        self,
        service_ir: ServiceIR,
    ) -> None:
        """Ensures that workflow step dependencies form a valid Directed Acyclic Graph (DAG) [source: 3]."""

        for workflow in service_ir.workflows:
            step_names = tuple(
                step.name
                for step in workflow.steps
            )

            counts = Counter(
                step_names
            )

            duplicates = sorted(
                name
                for name, count in counts.items()
                if count > 1
            )

            if duplicates:
                raise IRBuilderError(
                    message=(
                        f"Workflow '{workflow.name}' contains "
                        f"duplicate step names: {duplicates}."
                    ),
                    location=(
                        f"workflows/{workflow.name}/steps"
                    ),
                    error_code=(
                        "ERR_IR_WORKFLOW_DUPLICATE_STEP"
                    ),
                    suggested_resolution=(
                        "Assign every workflow step a unique name."
                    ),
                    details={
                        "duplicate_steps": duplicates,
                    },
                )

            step_name_set = set(
                step_names
            )

            sorter: graphlib.TopologicalSorter[str] = (
                graphlib.TopologicalSorter()
            )

            for step in workflow.steps:
                sorter.add(
                    step.name
                )

                for dependency in step.depends_on:
                    if dependency not in step_name_set:
                        raise IRBuilderError(
                            message=(
                                f"Workflow '{workflow.name}' step "
                                f"'{step.name}' depends on unknown "
                                f"step '{dependency}'."
                            ),
                            location=(
                                f"workflows/{workflow.name}/"
                                f"steps/{step.name}/depends_on"
                            ),
                            error_code=(
                                "ERR_IR_WORKFLOW_UNKNOWN_DEPENDENCY"
                            ),
                            suggested_resolution=(
                                "Reference only workflow steps "
                                "declared in the same workflow."
                            ),
                        )

                    if dependency == step.name:
                        raise IRBuilderError(
                            message=(
                                f"Workflow '{workflow.name}' step "
                                f"'{step.name}' cannot depend on itself."
                            ),
                            location=(
                                f"workflows/{workflow.name}/"
                                f"steps/{step.name}/depends_on"
                            ),
                            error_code=(
                                "ERR_IR_WORKFLOW_SELF_DEPENDENCY"
                            ),
                            suggested_resolution=(
                                "Remove the step from its own "
                                "depends_on list."
                            ),
                        )

                    sorter.add(
                        step.name,
                        dependency,
                    )

            try:
                list(
                    sorter.static_order()
                )

            except graphlib.CycleError as err:
                cycle_nodes = (
                    list(
                        err.args[1]
                    )
                    if len(err.args) > 1
                    else []
                )

                raise IRBuilderError(
                    message=(
                        f"Circular step dependency detected in "
                        f"workflow '{workflow.name}': "
                        f"{' -> '.join(cycle_nodes)}."
                    ),
                    location=(
                        f"workflows/{workflow.name}"
                    ),
                    error_code="ERR_IR_WORKFLOW_CYCLE",
                    suggested_resolution=(
                        "Remove mutual or cyclical step dependencies "
                        "in 'depends_on'."
                    ),
                    details={
                        "cycle_nodes": cycle_nodes,
                    },
                ) from err

    @trace_span(
        "analysis.validation.validate_business_rules"
    )
    def _validate_business_rules(
        self,
        service_ir: ServiceIR,
    ) -> None:
        """Verifies business rule targets exist in models."""

        valid_models = {
            model.name
            for model in service_ir.models
        }

        for rule in service_ir.rules:
            if rule.target_entity not in valid_models:
                raise IRBuilderError(
                    message=(
                        f"Business rule '{rule.name}' targets "
                        f"non-existent entity "
                        f"'{rule.target_entity}'."
                    ),
                    location=f"rules/{rule.name}",
                    error_code="ERR_IR_RULE_UNKNOWN_TARGET",
                    suggested_resolution=(
                        "Ensure target_entity matches a defined entity model."
                    ),
                )

            if not rule.expression.strip():
                raise IRBuilderError(
                    message=(
                        f"Business rule '{rule.name}' "
                        "has an empty expression."
                    ),
                    location=(
                        f"rules/{rule.name}/expression"
                    ),
                    error_code=(
                        "ERR_IR_RULE_EMPTY_EXPRESSION"
                    ),
                    suggested_resolution=(
                        "Provide a valid business rule expression."
                    ),
                )

            if not rule.error_message.strip():
                raise IRBuilderError(
                    message=(
                        f"Business rule '{rule.name}' "
                        "has an empty error message."
                    ),
                    location=(
                        f"rules/{rule.name}/error_message"
                    ),
                    error_code=(
                        "ERR_IR_RULE_EMPTY_ERROR_MESSAGE"
                    ),
                    suggested_resolution=(
                        "Provide an actionable rule violation message."
                    ),
                )

    @trace_span(
        "analysis.validation.validate_policies"
    )
    def _validate_policies(
        self,
        service_ir: ServiceIR,
    ) -> None:
        """Verifies policy definition sanity."""

        for policy in service_ir.policies:
            if not policy.roles:
                raise IRBuilderError(
                    message=(
                        f"Policy '{policy.name}' defines no roles."
                    ),
                    location=f"policies/{policy.name}",
                    error_code="ERR_IR_POLICY_EMPTY_ROLES",
                    suggested_resolution=(
                        "Specify at least one target role "
                        "for policy authorization."
                    ),
                )

            if not policy.actions:
                raise IRBuilderError(
                    message=(
                        f"Policy '{policy.name}' defines no actions."
                    ),
                    location=f"policies/{policy.name}",
                    error_code="ERR_IR_POLICY_EMPTY_ACTIONS",
                    suggested_resolution=(
                        "Specify at least one permitted action "
                        "for the policy."
                    ),
                )

            if any(
                not role.strip()
                for role in policy.roles
            ):
                raise IRBuilderError(
                    message=(
                        f"Policy '{policy.name}' contains an empty role."
                    ),
                    location=(
                        f"policies/{policy.name}/roles"
                    ),
                    error_code="ERR_IR_POLICY_EMPTY_ROLE",
                    suggested_resolution=(
                        "Remove empty roles and provide valid role names."
                    ),
                )

            if any(
                not action.strip()
                for action in policy.actions
            ):
                raise IRBuilderError(
                    message=(
                        f"Policy '{policy.name}' contains an empty action."
                    ),
                    location=(
                        f"policies/{policy.name}/actions"
                    ),
                    error_code="ERR_IR_POLICY_EMPTY_ACTION",
                    suggested_resolution=(
                        "Remove empty actions and provide valid action names."
                    ),
                )