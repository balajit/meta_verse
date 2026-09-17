from __future__ import annotations

import graphlib
from collections.abc import Callable

from meta_service_generator.exceptions import ManifestValidationError
from meta_service_generator.manifest.schema import ManifestSpec, EntitySpec
from meta_telemetry import get_tracer, trace_span

tracer = get_tracer("meta_service_generator.manifest.references")


class ReferentialIntegrityEngine:
    """Validates cross-object manifest references and dependencies."""

    @trace_span("manifest.references.validate")
    def validate(
        self,
        manifest: ManifestSpec,
        source_label: str = "manifest",
    ) -> None:
        violations: list[tuple[str, str, str]] = []

        def add(
            location: str,
            message: str,
            code: str,
        ) -> None:
            violations.append((location, message, code))

        entity_map: dict[str, EntitySpec] = {}

        for idx, entity in enumerate(manifest.entities):
            if entity.name in entity_map:
                add(
                    f"{source_label}#/entities/{idx}/name",
                    f"Duplicate entity name '{entity.name}'.",
                    "ERR_REF_DUPLICATE_ENTITY",
                )
            else:
                entity_map[entity.name] = entity

        entity_names = set(entity_map)

        for entity_idx, entity in enumerate(manifest.entities):
            attr_names = [
                attr.name
                for attr in entity.attributes
            ]

            self._add_duplicate_values(
                attr_names,
                lambda name: add(
                    (
                        f"{source_label}#/entities/{entity_idx}/"
                        "attributes"
                    ),
                    (
                        f"Duplicate attribute name '{name}' on "
                        f"entity '{entity.name}'."
                    ),
                    "ERR_REF_DUPLICATE_ATTRIBUTE",
                ),
            )

            relationship_names = [
                rel.name
                for rel in entity.relationships
            ]

            self._add_duplicate_values(
                relationship_names,
                lambda name: add(
                    (
                        f"{source_label}#/entities/{entity_idx}/"
                        "relationships"
                    ),
                    (
                        f"Duplicate relationship name '{name}' on "
                        f"entity '{entity.name}'."
                    ),
                    "ERR_REF_DUPLICATE_RELATIONSHIP",
                ),
            )

            for rel_idx, rel in enumerate(entity.relationships):
                rel_loc = (
                    f"{source_label}#/entities/{entity_idx}/"
                    f"relationships/{rel_idx}"
                )

                if rel.target_entity not in entity_names:
                    add(
                        rel_loc,
                        (
                            f"Relationship '{rel.name}' on entity "
                            f"'{entity.name}' references non-existent "
                            f"target entity '{rel.target_entity}'."
                        ),
                        "ERR_REF_UNKNOWN_TARGET_ENTITY",
                    )

                if (
                    rel.foreign_key is not None
                    and rel.foreign_key not in attr_names
                ):
                    add(
                        f"{rel_loc}/foreign_key",
                        (
                            f"Relationship '{rel.name}' references "
                            f"unknown foreign-key attribute "
                            f"'{rel.foreign_key}' on entity "
                            f"'{entity.name}'."
                        ),
                        "ERR_REF_UNKNOWN_FOREIGN_KEY",
                    )

            if entity.fsm is not None:
                fsm = entity.fsm
                fsm_loc = (
                    f"{source_label}#/entities/{entity_idx}/fsm"
                )

                valid_states = set(fsm.states)

                if len(valid_states) != len(fsm.states):
                    add(
                        f"{fsm_loc}/states",
                        (
                            f"FSM on entity '{entity.name}' contains "
                            "duplicate states."
                        ),
                        "ERR_REF_FSM_DUPLICATE_STATE",
                    )

                if fsm.initial_state not in valid_states:
                    add(
                        f"{fsm_loc}/initial_state",
                        (
                            f"FSM on entity '{entity.name}' defines "
                            f"initial_state '{fsm.initial_state}' not "
                            "in declared states."
                        ),
                        "ERR_REF_FSM_INVALID_INITIAL_STATE",
                    )

                attribute_map = {
                    attr.name: attr
                    for attr in entity.attributes
                }

                state_attr = attribute_map.get(
                    fsm.state_attribute
                )

                if state_attr is None:
                    add(
                        f"{fsm_loc}/state_attribute",
                        (
                            f"FSM state_attribute "
                            f"'{fsm.state_attribute}' is not defined "
                            f"on entity '{entity.name}'."
                        ),
                        "ERR_REF_FSM_UNKNOWN_ATTRIBUTE",
                    )
                elif state_attr.type != "str":
                    add(
                        f"{fsm_loc}/state_attribute",
                        (
                            f"FSM state_attribute "
                            f"'{fsm.state_attribute}' must use type 'str'."
                        ),
                        "ERR_REF_FSM_INVALID_ATTRIBUTE_TYPE",
                    )

                transition_keys: set[tuple[str, str]] = set()

                for trans_idx, trans in enumerate(
                    fsm.transitions
                ):
                    trans_loc = (
                        f"{fsm_loc}/transitions/{trans_idx}"
                    )

                    key = (
                        trans.trigger,
                        trans.source_state,
                    )

                    if key in transition_keys:
                        add(
                            trans_loc,
                            (
                                f"Duplicate FSM transition for trigger "
                                f"'{trans.trigger}' from state "
                                f"'{trans.source_state}'."
                            ),
                            "ERR_REF_FSM_DUPLICATE_TRANSITION",
                        )

                    transition_keys.add(key)

                    if trans.source_state not in valid_states:
                        add(
                            f"{trans_loc}/source_state",
                            (
                                f"FSM transition '{trans.trigger}' "
                                f"references unknown source_state "
                                f"'{trans.source_state}'."
                            ),
                            "ERR_REF_FSM_UNKNOWN_STATE",
                        )

                    if trans.target_state not in valid_states:
                        add(
                            f"{trans_loc}/target_state",
                            (
                                f"FSM transition '{trans.trigger}' "
                                f"references unknown target_state "
                                f"'{trans.target_state}'."
                            ),
                            "ERR_REF_FSM_UNKNOWN_STATE",
                        )

        self._validate_named_collections(
            manifest,
            source_label,
            add,
        )

        for rule_idx, rule in enumerate(
            manifest.business_rules
        ):
            if rule.target_entity not in entity_names:
                add(
                    (
                        f"{source_label}#/business_rules/"
                        f"{rule_idx}/target_entity"
                    ),
                    (
                        f"Business rule '{rule.name}' targets "
                        f"non-existent entity '{rule.target_entity}'."
                    ),
                    "ERR_REF_RULE_UNKNOWN_ENTITY",
                )

        for wf_idx, workflow in enumerate(
            manifest.workflows
        ):
            wf_loc = (
                f"{source_label}#/workflows/{wf_idx}"
            )

            step_names = [
                step.name
                for step in workflow.steps
            ]

            self._add_duplicate_values(
                step_names,
                lambda name: add(
                    f"{wf_loc}/steps",
                    (
                        f"Duplicate workflow step name '{name}' "
                        f"in workflow '{workflow.name}'."
                    ),
                    "ERR_REF_WORKFLOW_DUPLICATE_STEP",
                ),
            )

            step_set = set(step_names)
            graph: dict[str, set[str]] = {
                name: set()
                for name in step_names
            }

            for step_idx, step in enumerate(
                workflow.steps
            ):
                step_loc = (
                    f"{wf_loc}/steps/{step_idx}"
                )

                for dep in step.depends_on:
                    if dep not in step_set:
                        add(
                            f"{step_loc}/depends_on",
                            (
                                f"Workflow step '{step.name}' depends "
                                f"on non-existent step '{dep}'."
                            ),
                            "ERR_REF_WORKFLOW_MISSING_DEPENDENCY",
                        )
                    elif dep == step.name:
                        add(
                            f"{step_loc}/depends_on",
                            (
                                f"Workflow step '{step.name}' cannot "
                                "depend on itself."
                            ),
                            "ERR_REF_WORKFLOW_SELF_DEPENDENCY",
                        )
                    else:
                        graph[step.name].add(dep)

            try:
                list(
                    graphlib.TopologicalSorter(graph).static_order()
                )
            except graphlib.CycleError as err:
                raw_cycle = (
                    err.args[1]
                    if len(err.args) > 1
                    else "unknown cycle"
                )
                cycle_str = (
                    " -> ".join(raw_cycle)
                    if isinstance(raw_cycle, (list, tuple))
                    else str(raw_cycle)
                )

                add(
                    wf_loc,
                    (
                        f"Workflow '{workflow.name}' contains a "
                        f"dependency cycle: {cycle_str}."
                    ),
                    "ERR_REF_WORKFLOW_DEPENDENCY_CYCLE",
                )

        if violations:
            primary_loc, primary_msg, primary_code = violations[0]

            raise ManifestValidationError(
                message=(
                    f"Referential integrity failure: {primary_msg}"
                ),
                location=primary_loc,
                error_code=primary_code,
                suggested_resolution=(
                    "Align manifest names, references, FSM states, "
                    "foreign keys, and workflow dependencies."
                ),
                details={
                    "violation_count": len(violations),
                    "all_violations": [
                        {
                            "location": location,
                            "message": message,
                            "error_code": code,
                        }
                        for location, message, code in violations
                    ],
                },
            )

    @staticmethod
    def _add_duplicate_values(
        values: list[str],
        add_violation: Callable[[str], None],
    ) -> None:
        seen: set[str] = set()
        reported: set[str] = set()

        for value in values:
            if value in seen and value not in reported:
                add_violation(value)
                reported.add(value)
            seen.add(value)

    @staticmethod
    def _validate_named_collections(
        manifest: ManifestSpec,
        source_label: str,
        add: Callable[[str, str, str], None],
    ) -> None:
        collections = (
            (
                manifest.business_rules,
                "business_rules",
                "ERR_REF_DUPLICATE_RULE",
            ),
            (
                manifest.workflows,
                "workflows",
                "ERR_REF_DUPLICATE_WORKFLOW",
            ),
            (
                manifest.policies,
                "policies",
                "ERR_REF_DUPLICATE_POLICY",
            ),
        )

        for values, section, code in collections:
            seen: set[str] = set()

            for idx, value in enumerate(values):
                if value.name in seen:
                    add(
                        f"{source_label}#/{section}/{idx}/name",
                        (
                            f"Duplicate {section[:-1]} name "
                            f"'{value.name}'."
                        ),
                        code,
                    )

                seen.add(value.name)