from __future__ import annotations

import graphlib
from typing import Any

from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.ir.model import (
    IRCardinality,
    IRCompensation,
    IRFSM,
    IRField,
    IRLoadingStrategy,
    IRModel,
    IROwnership,
    IRPolicy,
    IRRelationship,
    IRRetryPolicy,
    IRRule,
    IRSerializationDirection,
    IRTransition,
    IRWorkflow,
    IRWorkflowExecutionMode,
    IRWorkflowStep,
    IRTransactionBoundary,
    ServiceIR,
)
from meta_service_generator.ir.names import (
    sanitize_identifier,
    to_pascal_case,
    to_snake_case,
)
from meta_service_generator.ir.normalizer import TypeNormalizer
from meta_service_generator.ir.relationships import (
    normalize_relationship_foreign_key,
)
from meta_service_generator.local_telemetry import get_logger
from meta_service_generator.manifest.schema import ManifestSpec
from meta_telemetry import get_tracer, trace_span


logger = get_logger("meta_service_generator.ir.builder")
tracer = get_tracer("meta_service_generator.ir.builder")


class IRBuilder:
    """Translates a validated ManifestSpec into ServiceIR."""

    @trace_span("ir.builder.build")
    def build(
        self,
        manifest: ManifestSpec,
    ) -> ServiceIR:
        """
        Build the canonical ServiceIR from a validated manifest.

        Relationship foreign-key normalization happens after all entities
        and fields have been converted into IR models. This ensures that
        relationship processing has access to:

        - normalized Python field names;
        - original manifest field names;
        - physical database column names;
        - primary-key metadata;
        - target model metadata.

        The resulting ServiceIR is the immutable representation consumed by
        downstream generation stages.
        """
        if not isinstance(manifest, ManifestSpec):
            raise IRBuilderError(
                message=(
                    "IRBuilder requires a validated ManifestSpec; "
                    f"received {type(manifest).__name__}."
                ),
                location="manifest",
                error_code="ERR_IR_INVALID_MANIFEST_TYPE",
                suggested_resolution=(
                    "Validate the manifest with ManifestValidator before "
                    "passing it to IRBuilder."
                ),
                details={
                    "received_type": type(manifest).__name__,
                },
            )

        try:
            circular_entities = self._find_circular_entities(
                manifest
            )

            self._validate_unique_generated_names(
                manifest
            )

            # First pass:
            # Build all IR fields and models before resolving relationships.
            #
            # Relationship FK normalization needs complete IRField metadata
            # including:
            #
            #   - normalized Python name
            #   - original manifest name
            #   - physical database column name
            #   - primary-key status
            #
            # This is important for fields such as:
            #
            #   manifest name: id
            #   Python name:   id_
            #   DB column:     id
            #
            # A relationship FK target must use the DB column name, never
            # the sanitized Python name.

            entity_models: dict[str, IRModel] = {}

            for entity in manifest.entities:
                class_name = to_pascal_case(
                    entity.name
                )

                table_name = (
                    entity.table_name
                    or to_snake_case(entity.name)
                )

                ir_fields: list[IRField] = []
                field_names: set[str] = set()

                for attr in entity.attributes:
                    sanitized_name = sanitize_identifier(
                        attr.name
                    )

                    if sanitized_name in field_names:
                        raise IRBuilderError(
                            message=(
                                f"Attribute names on entity "
                                f"'{entity.name}' collide after "
                                f"sanitization at "
                                f"'{sanitized_name}'."
                            ),
                            location=(
                                f"entities/{entity.name}/"
                                f"attributes/{attr.name}"
                            ),
                            error_code="ERR_IR_IDENTIFIER_COLLISION",
                            suggested_resolution=(
                                "Rename colliding attributes so "
                                "their sanitized Python identifiers "
                                "are unique."
                            ),
                        )

                    field_names.add(
                        sanitized_name
                    )

                    py_type, sql_type = (
                        TypeNormalizer.normalize_type(
                            attr.type,
                            location=(
                                f"entities/{entity.name}/"
                                f"attributes/{attr.name}"
                            ),
                        )
                    )

                    # Preserve the physical database column name explicitly.
                    #
                    # IRField defaults db_column_name to original_name, so
                    # this remains compatible with manifests that do not
                    # explicitly define a database column name.
                    db_column_name = getattr(
                        attr,
                        "db_column_name",
                        None,
                    )

                    api_name = getattr(
                        attr,
                        "api_name",
                        None,
                    )

                    foreign_key_target = getattr(
                        attr,
                        "foreign_key_target",
                        None,
                    )

                    foreign_key_on_delete = getattr(
                        attr,
                        "foreign_key_on_delete",
                        None,
                    )

                    foreign_key_on_update = getattr(
                        attr,
                        "foreign_key_on_update",
                        None,
                    )

                    ir_fields.append(
                        IRField(
                            name=sanitized_name,
                            original_name=attr.name,
                            python_type=py_type,
                            sql_type=sql_type,
                            is_primary_key=attr.primary_key,
                            is_nullable=attr.nullable,
                            is_unique=attr.unique,
                            is_indexed=attr.indexed,
                            db_column_name=db_column_name,
                            api_name=api_name,
                            create_required=getattr(
                                attr,
                                "create_required",
                                True,
                            ),
                            update_required=getattr(
                                attr,
                                "update_required",
                                False,
                            ),
                            response_nullable=getattr(
                                attr,
                                "response_nullable",
                                False,
                            ),
                            default_value=getattr(
                                attr,
                                "default_value",
                                None,
                            ),
                            default_factory=getattr(
                                attr,
                                "default_factory",
                                None,
                            ),
                            constraints=tuple(
                                getattr(
                                    attr,
                                    "constraints",
                                    (),
                                )
                            ),
                            validation=tuple(
                                getattr(
                                    attr,
                                    "validation",
                                    (),
                                )
                            ),
                            sensitive=getattr(
                                attr,
                                "sensitive",
                                False,
                            ),
                            foreign_key_target=(
                                foreign_key_target
                            ),
                            foreign_key_on_delete=(
                                foreign_key_on_delete
                            ),
                            foreign_key_on_update=(
                                foreign_key_on_update
                            ),
                        )
                    )

                ir_model = IRModel(
                    name=entity.name,
                    class_name=class_name,
                    table_name=table_name,
                    fields=tuple(ir_fields),
                    relationships=(),
                    endpoints=tuple(),
                    fsm=self._build_fsm(entity),
                    has_circular_dependencies=(
                        entity.name in circular_entities
                    ),
                    soft_delete=getattr(
                        entity,
                        "soft_delete",
                        False,
                    ),
                    optimistic_locking=getattr(
                        entity,
                        "optimistic_locking",
                        False,
                    ),
                    version_field=getattr(
                        entity,
                        "version_field",
                        None,
                    ),
                )

                entity_models[entity.name] = ir_model

            # Second pass:
            # Relationships are resolved only after every model has been
            # constructed. This gives FK normalization access to the actual
            # source/target IR fields and physical database metadata.

            normalized_models: list[IRModel] = []

            for entity in manifest.entities:
                model = entity_models[entity.name]

                ir_relationships = (
                    self._build_relationships(
                        entity=entity,
                        model_map=entity_models,
                        circular_entities=circular_entities,
                    )
                )

                normalized_models.append(
                    IRModel(
                        name=model.name,
                        class_name=model.class_name,
                        table_name=model.table_name,
                        fields=model.fields,
                        relationships=tuple(
                            ir_relationships
                        ),
                        endpoints=model.endpoints,
                        fsm=model.fsm,
                        has_circular_dependencies=(
                            model.has_circular_dependencies
                        ),
                        soft_delete=model.soft_delete,
                        optimistic_locking=model.optimistic_locking,
                        version_field=model.version_field,
                    )
                )

            result = ServiceIR(
                service_name=manifest.service_name,
                version=manifest.version,
                models=tuple(normalized_models),
                rules=tuple(
                    IRRule(
                        name=sanitize_identifier(
                            rule.name
                        ),
                        target_entity=rule.target_entity,
                        expression=rule.expression,
                        error_message=rule.error_message,
                    )
                    for rule in manifest.business_rules
                ),
                workflows=tuple(
                    self._build_workflow(
                        workflow
                    )
                    for workflow in manifest.workflows
                ),
                policies=tuple(
                    IRPolicy(
                        name=sanitize_identifier(
                            policy.name
                        ),
                        roles=tuple(policy.roles),
                        actions=tuple(policy.actions),
                        claims_required=tuple(
                            policy.claims_required
                        ),
                        attributes_required=tuple(
                            getattr(
                                policy,
                                "attributes_required",
                                (),
                            )
                        ),
                        endpoint_methods=tuple(
                            getattr(
                                policy,
                                "endpoint_methods",
                                (),
                            )
                        ),
                        endpoint_paths=tuple(
                            getattr(
                                policy,
                                "endpoint_paths",
                                (),
                            )
                        ),
                        resource_type=getattr(
                            policy,
                            "resource_type",
                            None,
                        ),
                    )
                    for policy in manifest.policies
                ),
            )

            logger.info(
                "Service IR construction completed.",
                extra={
                    "event_type": "ir.build.completed",
                    "service_name": result.service_name,
                    "model_count": len(result.models),
                    "rule_count": len(result.rules),
                    "workflow_count": len(result.workflows),
                    "policy_count": len(result.policies),
                    "circular_entity_count": len(
                        circular_entities
                    ),
                },
            )

            return result

        except IRBuilderError:
            raise

        except Exception as err:
            logger.exception(
                "Unexpected ServiceIR construction failure.",
                extra={
                    "event_type": "ir.build.unhandled_exception",
                    "service_name": getattr(
                        manifest,
                        "service_name",
                        None,
                    ),
                    "exception_type": type(err).__name__,
                },
            )

            raise IRBuilderError(
                message=(
                    "Failed to build Service IR from manifest: "
                    f"{err}"
                ),
                location="global",
                error_code="ERR_IR_BUILD_FAILED",
                suggested_resolution=(
                    "Verify manifest entity definitions and "
                    "relationship parameters."
                ),
                details={
                    "exception_type": type(err).__name__,
                },
            ) from err

    @staticmethod
    def _build_workflow(
        workflow: Any,
    ) -> IRWorkflow:
        """
        Normalize a manifest workflow into immutable IR metadata.

        The builder owns conversion from manifest-level workflow values to
        canonical IR enums and retry/compensation models.

        In particular, optional manifest retry configuration is never passed
        through as None to IRWorkflow.retry_policy. The IR requires a concrete
        retry policy and therefore receives IRRetryPolicy() when no policy is
        configured.
        """
        try:
            retry_policy = IRBuilder._build_retry_policy(
                getattr(
                    workflow,
                    "retry_policy",
                    None,
                )
            )

            steps = tuple(
                IRBuilder._build_workflow_step(
                    step
                )
                for step in workflow.steps
            )

            execution_mode_value = getattr(
                workflow,
                "execution_mode",
                IRWorkflowExecutionMode.PARALLEL,
            )

            transaction_boundary_value = getattr(
                workflow,
                "transaction_boundary",
                IRTransactionBoundary.WORKFLOW,
            )

            try:
                execution_mode = (
                    execution_mode_value
                    if isinstance(
                        execution_mode_value,
                        IRWorkflowExecutionMode,
                    )
                    else IRWorkflowExecutionMode(
                        str(execution_mode_value)
                    )
                )
            except (TypeError, ValueError) as err:
                raise IRBuilderError(
                    message=(
                        f"Workflow '{workflow.name}' uses invalid "
                        f"execution_mode "
                        f"'{execution_mode_value}'."
                    ),
                    location=(
                        f"workflows/{workflow.name}/execution_mode"
                    ),
                    error_code="ERR_IR_INVALID_WORKFLOW_EXECUTION_MODE",
                    suggested_resolution=(
                        "Use 'sequential' or 'parallel' for "
                        "workflow execution_mode."
                    ),
                ) from err

            try:
                transaction_boundary = (
                    transaction_boundary_value
                    if isinstance(
                        transaction_boundary_value,
                        IRTransactionBoundary,
                    )
                    else IRTransactionBoundary(
                        str(transaction_boundary_value)
                    )
                )
            except (TypeError, ValueError) as err:
                raise IRBuilderError(
                    message=(
                        f"Workflow '{workflow.name}' uses invalid "
                        f"transaction_boundary "
                        f"'{transaction_boundary_value}'."
                    ),
                    location=(
                        f"workflows/{workflow.name}/"
                        "transaction_boundary"
                    ),
                    error_code=(
                        "ERR_IR_INVALID_TRANSACTION_BOUNDARY"
                    ),
                    suggested_resolution=(
                        "Use 'workflow', 'step', or 'none' for "
                        "transaction_boundary."
                    ),
                ) from err

            return IRWorkflow(
                name=sanitize_identifier(
                    workflow.name
                ),
                steps=steps,
                execution_mode=execution_mode,
                transaction_boundary=transaction_boundary,
                retry_policy=retry_policy,
                timeout_seconds=getattr(
                    workflow,
                    "timeout_seconds",
                    None,
                ),
                compensation_enabled=getattr(
                    workflow,
                    "compensation_enabled",
                    False,
                ),
            )

        except IRBuilderError:
            raise

        except Exception as err:
            logger.exception(
                "Failed to normalize workflow '%s'.",
                getattr(
                    workflow,
                    "name",
                    "<unknown>",
                ),
                extra={
                    "event_type": "ir.workflow.normalization.failed",
                    "workflow_name": getattr(
                        workflow,
                        "name",
                        None,
                    ),
                    "exception_type": type(err).__name__,
                },
            )

            raise IRBuilderError(
                message=(
                    f"Failed to normalize workflow "
                    f"'{getattr(workflow, 'name', '<unknown>')}': "
                    f"{err}"
                ),
                location=(
                    f"workflows/"
                    f"{getattr(workflow, 'name', '<unknown>')}"
                ),
                error_code="ERR_IR_WORKFLOW_BUILD_FAILED",
                suggested_resolution=(
                    "Verify workflow retry, timeout, dependency, "
                    "execution, and compensation configuration."
                ),
                details={
                    "exception_type": type(err).__name__,
                },
            ) from err

    @staticmethod
    def _build_workflow_step(
        step: Any,
    ) -> IRWorkflowStep:
        """
        Normalize a manifest workflow step into immutable IR metadata.
        """
        max_retries = getattr(
            step,
            "max_retries",
            0,
        )
        retry_policy = IRBuilder._build_retry_policy(
            getattr(
                step,
                "retry_policy",
                None,
            ), max_retries=max_retries
        )



        return IRWorkflowStep(
            name=sanitize_identifier(
                step.name
            ),
            action=step.action,
            depends_on=tuple(
                sanitize_identifier(
                    dependency
                )
                for dependency in step.depends_on
            ),
            max_retries=max_retries,
            retry_policy=retry_policy,
            timeout_seconds=getattr(
                step,
                "timeout_seconds",
                None,
            ),
            compensation=(
                IRCompensation(
                    action=step.compensation.action,
                    timeout_seconds=(
                        step.compensation.timeout_seconds
                    ),
                )
                if getattr(
                    step,
                    "compensation",
                    None,
                )
                is not None
                else None
            ),
        )

    @staticmethod
    def _build_retry_policy(
        retry_policy: Any,
        max_retries:int=0
    ) -> IRRetryPolicy:
        """
        Normalize optional manifest retry configuration into IRRetryPolicy.

        A missing or explicitly null manifest retry policy means "use the IR
        defaults", never "set the required IR retry_policy to None".
        """
        if retry_policy is None:
            return IRRetryPolicy(max_retries=max_retries)

        if isinstance(
            retry_policy,
            IRRetryPolicy,
        ):
            return retry_policy

        try:
            return IRRetryPolicy(
                max_retries=getattr(
                    retry_policy,
                    "max_retries",
                    max_retries,
                ),
                multiplier=getattr(
                    retry_policy,
                    "multiplier",
                    1.0,
                ),
                min_seconds=getattr(
                    retry_policy,
                    "min_seconds",
                    0.1,
                ),
                max_seconds=getattr(
                    retry_policy,
                    "max_seconds",
                    10.0,
                ),
            )

        except Exception as err:
            logger.exception(
                "Failed to normalize workflow retry policy.",
                extra={
                    "event_type": "ir.workflow.retry_policy.failed",
                    "exception_type": type(err).__name__,
                },
            )

            raise IRBuilderError(
                message=(
                    "Invalid workflow retry policy: "
                    f"{err}"
                ),
                location="workflows/retry_policy",
                error_code="ERR_IR_INVALID_RETRY_POLICY",
                suggested_resolution=(
                    "Verify max_retries, multiplier, min_seconds, "
                    "and max_seconds."
                ),
                details={
                    "exception_type": type(err).__name__,
                },
            ) from err

    @staticmethod
    def _build_fsm(
        entity: Any,
    ) -> IRFSM | None:
        """
        Normalize an entity FSM into immutable IR metadata.
        """
        if entity.fsm is None:
            return None

        return IRFSM(
            state_attribute=sanitize_identifier(
                entity.fsm.state_attribute
            ),
            initial_state=entity.fsm.initial_state,
            states=tuple(entity.fsm.states),
            transitions=tuple(
                IRTransition(
                    trigger=sanitize_identifier(
                        transition.trigger
                    ),
                    source_state=transition.source_state,
                    target_state=transition.target_state,
                    guards=tuple(
                        transition.guards
                    ),
                    actions=tuple(
                        getattr(
                            transition,
                            "actions",
                            (),
                        )
                    ),
                )
                for transition in entity.fsm.transitions
            ),
            entry_hooks=tuple(
                getattr(
                    entity.fsm,
                    "entry_hooks",
                    (),
                )
            ),
            exit_hooks=tuple(
                getattr(
                    entity.fsm,
                    "exit_hooks",
                    (),
                )
            ),
            transition_guards=tuple(
                getattr(
                    entity.fsm,
                    "transition_guards",
                    (),
                )
            ),
        )

    @staticmethod
    def _normalize_cardinality(
        cardinality: IRCardinality | str,
        *,
        entity_name: str,
        relationship_name: str,
    ) -> IRCardinality:
        """
        Normalize a manifest relationship cardinality into IRCardinality.

        Manifest models may expose cardinality either as an IRCardinality
        enum or as a plain string. The IR layer must not assume that the
        manifest schema has already converted the value into an enum.

        This method deliberately avoids calling `.value` on an arbitrary
        manifest value because validated Pydantic models can still expose
        string values depending on the manifest schema declaration.
        """
        try:
            if isinstance(
                cardinality,
                IRCardinality,
            ):
                return cardinality

            normalized = str(
                cardinality
            ).strip()

            return IRCardinality(
                normalized
            )

        except (TypeError, ValueError) as err:
            raise IRBuilderError(
                message=(
                    f"Relationship '{entity_name}."
                    f"{relationship_name}' uses invalid "
                    f"cardinality '{cardinality}'."
                ),
                location=(
                    f"entities/{entity_name}/"
                    f"relationships/{relationship_name}/cardinality"
                ),
                error_code=(
                    "ERR_IR_INVALID_RELATIONSHIP_CARDINALITY"
                ),
                suggested_resolution=(
                    "Use one of the supported relationship "
                    "cardinalities: '1:1', '1:N', or 'N:M'."
                ),
            ) from err

    def _build_relationships(
        self,
        *,
        entity: Any,
        model_map: dict[str, IRModel],
        circular_entities: set[str],
    ) -> list[IRRelationship]:
        """
        Build normalized relationship metadata for an entity.

        Relationship ownership determines where the foreign-key metadata
        belongs:

        - SOURCE:
          ``foreign_key`` identifies the FK column on the source table.

        - TARGET:
          ``foreign_key_target`` identifies the FK column on the target
          table.

        - ASSOCIATION:
          ``secondary_table`` identifies the many-to-many association table.

        Cardinality values may arrive from the manifest layer either as
        ``IRCardinality`` instances or plain strings, so this method
        normalizes them before comparison.
        """
        relationship_names: set[str] = set()
        relationships: list[IRRelationship] = []

        source_model = model_map[entity.name]

        for rel in entity.relationships:
            sanitized_rel_name = sanitize_identifier(
                rel.name
            )

            if sanitized_rel_name in relationship_names:
                raise IRBuilderError(
                    message=(
                        f"Relationship names on entity "
                        f"'{entity.name}' collide after "
                        f"sanitization at "
                        f"'{sanitized_rel_name}'."
                    ),
                    location=(
                        f"entities/{entity.name}/"
                        f"relationships/{rel.name}"
                    ),
                    error_code="ERR_IR_IDENTIFIER_COLLISION",
                    suggested_resolution=(
                        "Rename colliding relationships so "
                        "their sanitized Python identifiers "
                        "are unique."
                    ),
                )

            relationship_names.add(
                sanitized_rel_name
            )

            target_model = model_map.get(
                rel.target_entity
            )

            if target_model is None:
                raise IRBuilderError(
                    message=(
                        f"Relationship '{entity.name}."
                        f"{rel.name}' references unknown target "
                        f"entity '{rel.target_entity}'."
                    ),
                    location=(
                        f"entities/{entity.name}/"
                        f"relationships/{rel.name}/target_entity"
                    ),
                    error_code="ERR_IR_UNKNOWN_RELATIONSHIP_TARGET",
                    suggested_resolution=(
                        f"Define entity '{rel.target_entity}' "
                        "or correct the relationship target."
                    ),
                )

            cardinality = self._normalize_cardinality(
                rel.cardinality,
                entity_name=entity.name,
                relationship_name=rel.name,
            )

            is_circular = (
                entity.name in circular_entities
                and rel.target_entity in circular_entities
            )

            # -----------------------------------------------------------------
            # Many-to-many relationships
            # -----------------------------------------------------------------
            if cardinality == IRCardinality.MANY_TO_MANY:
                if not rel.secondary_table:
                    raise IRBuilderError(
                        message=(
                            f"Many-to-many relationship "
                            f"'{entity.name}.{rel.name}' requires "
                            "secondary_table."
                        ),
                        location=(
                            f"entities/{entity.name}/"
                            f"relationships/{rel.name}/secondary_table"
                        ),
                        error_code="ERR_IR_MISSING_ASSOCIATION_TABLE",
                        suggested_resolution=(
                            "Define secondary_table for the "
                            "many-to-many relationship."
                        ),
                    )

                relationships.append(
                    IRRelationship(
                        name=sanitized_rel_name,
                        original_name=rel.name,
                        source_entity=entity.name,
                        target_entity=rel.target_entity,
                        target_class_name=target_model.class_name,
                        cardinality=cardinality,
                        foreign_key=None,
                        foreign_key_target=None,
                        ownership=IROwnership.ASSOCIATION,
                        nullable=False,
                        cascade=tuple(
                            getattr(rel, "cascade", ())
                        ),
                        loading=getattr(
                            rel,
                            "loading",
                            IRLoadingStrategy.SELECTIN,
                        ),
                        serialize=getattr(
                            rel,
                            "serialize",
                            IRSerializationDirection.FORWARD,
                        ),
                        is_circular=is_circular,
                        #back_populates=rel.back_populates,
                        secondary_table=rel.secondary_table,
                    )
                )

                continue

            # -----------------------------------------------------------------
            # One-to-one / one-to-many relationships
            # -----------------------------------------------------------------
            source_primary_key = (
                IRBuilder._find_primary_key(
                    source_model
                )
            )

            relationship_fk = (
                normalize_relationship_foreign_key(
                    source_entity=entity.name,
                    target_entity=rel.target_entity,
                    foreign_key=rel.foreign_key,
                    source_fields=tuple(source_model.fields),
                    target_fields=tuple(target_model.fields),
                    source_table_name=source_model.table_name,
                    source_primary_key=source_primary_key,
                    location=(
                        f"entities/{entity.name}/"
                        f"relationships/{rel.name}"
                    ),
                )
            )

            ownership = relationship_fk.ownership

            if ownership == IROwnership.SOURCE:
                if relationship_fk.foreign_key is None:
                    raise IRBuilderError(
                        message=(
                            f"Source-owned relationship "
                            f"'{entity.name}.{rel.name}' was normalized "
                            "without a foreign_key."
                        ),
                        location=(
                            f"entities/{entity.name}/"
                            f"relationships/{rel.name}/foreign_key"
                        ),
                        error_code="ERR_IR_MISSING_SOURCE_FOREIGN_KEY",
                        suggested_resolution=(
                            "Define a valid source-side foreign key "
                            "for the relationship."
                        ),
                    )

            elif ownership == IROwnership.TARGET:
                if relationship_fk.foreign_key_target is None:
                    raise IRBuilderError(
                        message=(
                            f"Target-owned relationship "
                            f"'{entity.name}.{rel.name}' was normalized "
                            "without a foreign_key_target."
                        ),
                        location=(
                            f"entities/{entity.name}/"
                            f"relationships/{rel.name}"
                        ),
                        error_code="ERR_IR_MISSING_TARGET_FOREIGN_KEY",
                        suggested_resolution=(
                            "Define the target-side foreign-key "
                            "column so target ownership can be "
                            "represented in the IR."
                        ),
                    )

            else:
                raise IRBuilderError(
                    message=(
                        f"Relationship '{entity.name}.{rel.name}' "
                        f"has unsupported ownership "
                        f"{ownership!r} for cardinality "
                        f"{cardinality.value!r}."
                    ),
                    location=(
                        f"entities/{entity.name}/"
                        f"relationships/{rel.name}/ownership"
                    ),
                    error_code="ERR_IR_INVALID_RELATIONSHIP_OWNERSHIP",
                    suggested_resolution=(
                        "Use source ownership for source-side foreign "
                        "keys, target ownership for target-side foreign "
                        "keys, or association ownership for many-to-many "
                        "relationships."
                    ),
                )

            relationships.append(
                IRRelationship(
                    name=sanitized_rel_name,
                    original_name=rel.name,
                    source_entity=entity.name,
                    target_entity=rel.target_entity,
                    target_class_name=target_model.class_name,
                    cardinality=cardinality,
                    foreign_key=relationship_fk.foreign_key,
                    foreign_key_target=(
                        relationship_fk.foreign_key_target
                    ),
                    ownership=ownership,
                    nullable=relationship_fk.nullable,
                    cascade=tuple(
                        getattr(rel, "cascade", ())
                    ),
                    loading=getattr(
                        rel,
                        "loading",
                        IRLoadingStrategy.SELECTIN,
                    ),
                    serialize=getattr(
                        rel,
                        "serialize",
                        IRSerializationDirection.FORWARD,
                    ),
                    is_circular=is_circular,
                    #back_populates=rel.back_populates,
                    #secondary_table=rel.secondary_table,
                )
            )

        return relationships

    @staticmethod
    def _find_primary_key(
        model: IRModel,
    ) -> IRField | None:
        """
        Resolve the single primary-key field of an IR model.

        Relationship FK normalization currently supports a single-column
        primary key. Composite primary keys are therefore rejected explicitly
        rather than producing ambiguous SQLAlchemy ForeignKey targets.
        """
        primary_keys = tuple(
            field
            for field in model.fields
            if field.is_primary_key
        )

        if len(primary_keys) > 1:
            raise IRBuilderError(
                message=(
                    f"Model '{model.name}' has multiple primary-key "
                    "fields; relationship FK normalization currently "
                    "requires a single primary key."
                ),
                location=f"models.{model.name}.fields",
                error_code="ERR_IR_MULTIPLE_PRIMARY_KEYS",
                suggested_resolution=(
                    "Define exactly one primary-key field for "
                    "relationship FK normalization."
                ),
            )

        return (
            primary_keys[0]
            if primary_keys
            else None
        )

    @staticmethod
    def _validate_unique_generated_names(
        manifest: ManifestSpec,
    ) -> None:
        """
        Ensure entity names cannot generate duplicate Python class names.
        """
        seen: dict[str, str] = {}

        for entity in manifest.entities:
            generated = to_pascal_case(
                entity.name
            )

            previous = seen.get(
                generated
            )

            if previous is not None:
                raise IRBuilderError(
                    message=(
                        f"Entity names '{previous}' and "
                        f"'{entity.name}' generate the same "
                        f"Python class name '{generated}'."
                    ),
                    location=(
                        f"entities/{entity.name}/name"
                    ),
                    error_code="ERR_IR_GENERATED_NAME_COLLISION",
                    suggested_resolution=(
                        "Rename entities so generated Python "
                        "class names are unique."
                    ),
                )

            seen[generated] = entity.name

    @staticmethod
    def _find_circular_entities(
        manifest: ManifestSpec,
    ) -> set[str]:
        """
        Identify entities participating in relationship cycles.

        graphlib.TopologicalSorter is used repeatedly so that all entities
        participating in detected cycles are marked as circular while
        acyclic portions of the graph are removed from consideration.
        """
        graph: dict[str, set[str]] = {
            entity.name: set()
            for entity in manifest.entities
        }

        for entity in manifest.entities:
            for relationship in entity.relationships:
                if relationship.target_entity in graph:
                    graph[entity.name].add(
                        relationship.target_entity
                    )

        remaining = {
            name: set(targets)
            for name, targets in graph.items()
        }

        circular: set[str] = set()

        while remaining:
            try:
                list(
                    graphlib.TopologicalSorter(
                        remaining
                    ).static_order()
                )
                break

            except graphlib.CycleError as err:
                cycle_nodes = {
                    str(node)
                    for node in err.args[1]
                }

                circular.update(
                    cycle_nodes
                )

                remaining = {
                    node: dependencies - cycle_nodes
                    for node, dependencies in remaining.items()
                    if node not in cycle_nodes
                }

        return circular
