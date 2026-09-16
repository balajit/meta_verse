from __future__ import annotations

import logging
from typing import Final

from meta_telemetry import get_tracer, trace_span

from meta_service_generator.ir.model import (
    IRCardinality,
    IRField,
    IRModel,
    IROwnership,
    IRRelationship,
    ServiceIR,
)

logger = logging.getLogger(__name__)

tracer = get_tracer(
    "meta_service_generator.generation.orm_validator"
)


class ORMGenerationError(Exception):
    """Raised when the normalized IR cannot produce a valid SQLAlchemy ORM graph."""

    def __init__(
        self,
        message: str,
        *,
        location: str,
        error_code: str,
        suggested_resolution: str,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.location = location
        self.error_code = error_code
        self.suggested_resolution = suggested_resolution


_ONE_TO_MANY: Final[str] = IRCardinality.ONE_TO_MANY.value
_MANY_TO_MANY: Final[str] = IRCardinality.MANY_TO_MANY.value
_ONE_TO_ONE: Final[str] = IRCardinality.ONE_TO_ONE.value


@trace_span("generation.orm_validator.validate_relationship_graph")
def validate_relationship_graph(
    service_ir: ServiceIR,
) -> None:
    """
    Validates that the ServiceIR relationship graph can be rendered into
    SQLAlchemy ORM relationships.

    Relationship foreign keys are interpreted according to relationship
    cardinality.

    For a 1:N relationship:

        source = parent
        target = child

    the foreign-key field belongs to the target model.

    Example:

        Order.items
            target_entity = OrderItem
            foreign_key = order_id

    means:

        OrderItem.order_id -> Order.<primary_key>

    It does NOT mean that Order.order_id must exist.

    For a 1:1 relationship, the foreign-key location is determined by
    relationship ownership. The current IR representation supports the
    source-side FK convention when ownership is SOURCE and the target-side
    convention when ownership is TARGET.

    Many-to-many relationships must define secondary_table.
    """
    if not isinstance(service_ir, ServiceIR):
        raise ORMGenerationError(
            message=(
                "Relationship graph validation requires a ServiceIR "
                f"instance, got {type(service_ir).__name__}."
            ),
            location="service_ir",
            error_code="ERR_ORM_INVALID_IR",
            suggested_resolution=(
                "Pass the validated immutable ServiceIR produced by the "
                "manifest-to-IR compilation stage."
            ),
        )

    model_map = service_ir.model_map

    logger.debug(
        "Validating ORM relationship graph: service=%s models=%d",
        service_ir.service_name,
        len(service_ir.models),
    )

    for model in service_ir.models:
        _validate_model_relationships(
            model=model,
            model_map=model_map,
        )

    logger.debug(
        "ORM relationship graph validation completed successfully: "
        "service=%s",
        service_ir.service_name,
    )


def _validate_model_relationships(
    *,
    model: IRModel,
    model_map: dict[str, IRModel],
) -> None:
    """
    Validate every relationship declared by one source model.
    """
    for relationship in model.relationships:
        target_model = model_map.get(
            relationship.target_entity
        )

        if target_model is None:
            raise ORMGenerationError(
                message=(
                    f"Model '{model.name}' relationship "
                    f"'{relationship.name}' references unknown target "
                    f"entity '{relationship.target_entity}'."
                ),
                location=(
                    f"models.{model.name}.relationships."
                    f"{relationship.name}.target_entity"
                ),
                error_code="ERR_ORM_UNKNOWN_RELATIONSHIP_TARGET",
                suggested_resolution=(
                    f"Define entity '{relationship.target_entity}' in the "
                    "manifest or correct the relationship target_entity."
                ),
            )

        _validate_relationship_cardinality(
            model=model,
            relationship=relationship,
        )

        if relationship.cardinality == IRCardinality.MANY_TO_MANY:
            _validate_many_to_many_relationship(
                model=model,
                relationship=relationship,
                target_model=target_model,
                model_map=model_map,
            )
            continue

        _validate_foreign_key_relationship(
            model=model,
            relationship=relationship,
            target_model=target_model,
        )


def _validate_relationship_cardinality(
    *,
    model: IRModel,
    relationship: IRRelationship,
) -> None:
    """
    Validate the relationship cardinality representation.
    """
    cardinality = str(relationship.cardinality)

    supported = {
        _ONE_TO_ONE,
        _ONE_TO_MANY,
        _MANY_TO_MANY,
    }

    if cardinality not in supported:
        raise ORMGenerationError(
            message=(
                f"Model '{model.name}' relationship "
                f"'{relationship.name}' uses unsupported cardinality "
                f"'{cardinality}'."
            ),
            location=(
                f"models.{model.name}.relationships."
                f"{relationship.name}.cardinality"
            ),
            error_code="ERR_ORM_UNSUPPORTED_CARDINALITY",
            suggested_resolution=(
                "Use one of the supported relationship cardinalities: "
                "'1:1', '1:N', or 'N:M'."
            ),
        )


@trace_span("generation.orm_validator.validate_foreign_key_relationship")
def _validate_foreign_key_relationship(
    *,
    model: IRModel,
    relationship: IRRelationship,
    target_model: IRModel,
) -> None:
    """
    Validate the normalized relationship foreign key.

    The FK location depends on relationship ownership.

    For 1:N:

        source Order
        target OrderItem
        foreign_key order_id
        ownership TARGET
        foreign_key_target orders.id

    the FK is expected on OrderItem and references Order.

    For 1:1:

        ownership=SOURCE
            FK is expected on the source.

        ownership=TARGET
            FK is expected on the target.
    """
    try:
        foreign_key = relationship.foreign_key

        if foreign_key is None:
            raise ORMGenerationError(
                message=(
                    f"Model '{model.name}' relationship "
                    f"'{relationship.name}' does not define a "
                    "foreign-key field."
                ),
                location=(
                    f"models.{model.name}.relationships."
                    f"{relationship.name}.foreign_key"
                ),
                error_code="ERR_ORM_RELATIONSHIP_FOREIGN_KEY_MISSING",
                suggested_resolution=(
                    "Define the foreign-key field on the owning side "
                    "of the relationship."
                ),
            )

        if relationship.foreign_key_target is None:
            raise ORMGenerationError(
                message=(
                    f"Model '{model.name}' relationship "
                    f"'{relationship.name}' does not define a "
                    "normalized foreign-key target."
                ),
                location=(
                    f"models.{model.name}.relationships."
                    f"{relationship.name}.foreign_key_target"
                ),
                error_code="ERR_ORM_RELATIONSHIP_FOREIGN_KEY_TARGET_MISSING",
                suggested_resolution=(
                    "Ensure the IR builder derives foreign_key_target "
                    "from the referenced model primary key."
                ),
            )

        fk_model = _foreign_key_owner_model(
            model=model,
            relationship=relationship,
            target_model=target_model,
        )

        field = _find_field(
            model=fk_model,
            field_name=foreign_key,
        )

        if field is None:
            raise ORMGenerationError(
                message=(
                    f"Model '{model.name}' relationship "
                    f"'{relationship.name}' references foreign-key "
                    f"field '{foreign_key}', but that field does not "
                    f"exist on the expected foreign-key model "
                    f"'{fk_model.name}'."
                ),
                location=(
                    f"models.{model.name}.relationships."
                    f"{relationship.name}.foreign_key"
                ),
                error_code=(
                    "ERR_ORM_RELATIONSHIP_FOREIGN_KEY_NOT_FOUND"
                ),
                suggested_resolution=(
                    f"Define field '{foreign_key}' on model "
                    f"'{fk_model.name}' or correct the relationship "
                    "foreign_key value."
                ),
            )

        referenced_model = _foreign_key_referenced_model(
            model=model,
            relationship=relationship,
            target_model=target_model,
        )

        _validate_foreign_key_field_semantics(
            source_model=model,
            relationship=relationship,
            fk_model=fk_model,
            fk_field=field,
            referenced_model=referenced_model,
        )

        expected_target = _expected_primary_key_reference(
            referenced_model=referenced_model,
        )

        if not _foreign_key_targets_match(
            actual=relationship.foreign_key_target,
            expected=expected_target,
            referenced_model=referenced_model,
        ):
            raise ORMGenerationError(
                message=(
                    f"Model '{model.name}' relationship "
                    f"'{relationship.name}' has normalized "
                    f"foreign_key_target "
                    f"'{relationship.foreign_key_target}', expected "
                    f"'{expected_target}'."
                ),
                location=(
                    f"models.{model.name}.relationships."
                    f"{relationship.name}.foreign_key_target"
                ),
                error_code="ERR_ORM_FOREIGN_KEY_TARGET_MISMATCH",
                suggested_resolution=(
                    f"Point the relationship foreign key at the "
                    f"primary key of '{referenced_model.name}'."
                ),
            )

    except ORMGenerationError:
        raise

    except Exception as err:
        raise ORMGenerationError(
            message=(
                f"Failed to validate foreign-key relationship "
                f"'{model.name}.{relationship.name}': {err}"
            ),
            location=(
                f"models.{model.name}.relationships."
                f"{relationship.name}.foreign_key"
            ),
            error_code=(
                "ERR_ORM_RELATIONSHIP_FOREIGN_KEY_VALIDATION_FAILED"
            ),
            suggested_resolution=(
                "Verify relationship ownership, foreign-key metadata, "
                "and the referenced model fields."
            ),
        ) from err


@trace_span("generation.orm_validator.resolve_foreign_key_owner")
def _foreign_key_owner_model(
    *,
    model: IRModel,
    relationship: IRRelationship,
    target_model: IRModel,
) -> IRModel:
    """
    Resolve the model that physically owns relationship.foreign_key.

    Relationship ownership is normalized during IR construction, so ORM
    validation must consume relationship.ownership rather than infer FK
    location from relationship cardinality.

    SOURCE:
        source model owns the FK.

    TARGET:
        target model owns the FK.
    """
    if relationship.ownership is IROwnership.SOURCE:
        return model

    if relationship.ownership is IROwnership.TARGET:
        return target_model

    raise ORMGenerationError(
        message=(
            f"Relationship '{model.name}.{relationship.name}' has "
            f"unsupported foreign-key ownership "
            f"'{relationship.ownership}'."
        ),
        location=(
            f"models.{model.name}.relationships."
            f"{relationship.name}.ownership"
        ),
        error_code="ERR_ORM_RELATIONSHIP_INVALID_OWNERSHIP",
        suggested_resolution=(
            "Ensure relationship ownership is normalized to "
            "IROwnership.SOURCE or IROwnership.TARGET during IR "
            "construction."
        ),
    )


@trace_span("generation.orm_validator.resolve_foreign_key_reference")
def _foreign_key_referenced_model(
    *,
    model: IRModel,
    relationship: IRRelationship,
    target_model: IRModel,
) -> IRModel:
    """
    Resolve the model whose primary key is referenced by the FK.

    Ownership and reference direction are opposites:

        ownership=SOURCE
            source owns FK
            FK references target

        ownership=TARGET
            target owns FK
            FK references source

    For the common 1:N case:

        Order.items -> OrderItem
        ownership = TARGET
        FK owner = OrderItem
        referenced model = Order

    Therefore:

        OrderItem.order_id -> orders.id
    """
    if relationship.ownership is IROwnership.SOURCE:
        return target_model

    if relationship.ownership is IROwnership.TARGET:
        return model

    raise ORMGenerationError(
        message=(
            f"Relationship '{model.name}.{relationship.name}' has "
            f"unsupported foreign-key ownership "
            f"'{relationship.ownership}'."
        ),
        location=(
            f"models.{model.name}.relationships."
            f"{relationship.name}.ownership"
        ),
        error_code="ERR_ORM_RELATIONSHIP_INVALID_OWNERSHIP",
        suggested_resolution=(
            "Ensure relationship ownership is normalized to "
            "IROwnership.SOURCE or IROwnership.TARGET during IR "
            "construction."
        ),
    )


def _validate_foreign_key_field_semantics(
    *,
    source_model: IRModel,
    relationship: IRRelationship,
    fk_model: IRModel,
    fk_field: IRField,
    referenced_model: IRModel,
) -> None:
    """
    Validate that the selected FK field has semantics compatible with
    the relationship.

    The validator intentionally does not require the IR field to already
    contain foreign_key_target. The manifest-to-IR normalization stage is
    responsible for deriving that database-level target.

    This function verifies consistency where the metadata is available.
    """
    if (
        fk_field.is_primary_key
        and str(relationship.cardinality) == _ONE_TO_MANY
    ):
        raise ORMGenerationError(
            message=(
                f"Model '{source_model.name}' relationship "
                f"'{relationship.name}' uses '{fk_model.name}."
                f"{fk_field.name}' as a 1:N foreign-key field, but "
                "that field is also the target model's primary key."
            ),
            location=(
                f"models.{source_model.name}.relationships."
                f"{relationship.name}.foreign_key"
            ),
            error_code="ERR_ORM_INVALID_ONE_TO_MANY_FOREIGN_KEY",
            suggested_resolution=(
                "Use a non-primary-key child field such as "
                "'order_id' for a 1:N relationship."
            ),
        )

    if (
        relationship.nullable is False
        and fk_field.is_nullable
    ):
        logger.warning(
            "Relationship nullability is stricter than FK field "
            "nullability: source=%s relationship=%s target=%s field=%s",
            source_model.name,
            relationship.name,
            fk_model.name,
            fk_field.name,
        )

    if (
        relationship.nullable is True
        and not fk_field.is_nullable
    ):
        raise ORMGenerationError(
            message=(
                f"Model '{source_model.name}' relationship "
                f"'{relationship.name}' is nullable, but foreign-key "
                f"field '{fk_model.name}.{fk_field.name}' is not nullable."
            ),
            location=(
                f"models.{source_model.name}.relationships."
                f"{relationship.name}"
            ),
            error_code="ERR_ORM_RELATIONSHIP_NULLABILITY_MISMATCH",
            suggested_resolution=(
                f"Make '{fk_model.name}.{fk_field.name}' nullable or "
                "mark the relationship as non-nullable."
            ),
        )

    if fk_field.foreign_key_target is not None:
        expected_target = _expected_primary_key_reference(
            referenced_model=referenced_model,
        )

        if not _foreign_key_targets_match(
            actual=fk_field.foreign_key_target,
            expected=expected_target,
            referenced_model=referenced_model,
        ):
            raise ORMGenerationError(
                message=(
                    f"Model '{source_model.name}' relationship "
                    f"'{relationship.name}' uses foreign-key field "
                    f"'{fk_model.name}.{fk_field.name}', but its "
                    f"foreign_key_target is "
                    f"'{fk_field.foreign_key_target}', expected "
                    f"'{expected_target}'."
                ),
                location=(
                    f"models.{fk_model.name}.fields."
                    f"{fk_field.name}.foreign_key_target"
                ),
                error_code="ERR_ORM_FIELD_FOREIGN_KEY_TARGET_MISMATCH",
                suggested_resolution=(
                    f"Point '{fk_model.name}.{fk_field.name}' at the "
                    f"primary key of '{referenced_model.name}'."
                ),
            )


def _validate_many_to_many_relationship(
    *,
    model: IRModel,
    relationship: IRRelationship,
    target_model: IRModel,
    model_map: dict[str, IRModel],
) -> None:
    """
    Validate an N:M relationship and its association table metadata.
    """
    secondary_table = relationship.secondary_table

    if secondary_table is None:
        raise ORMGenerationError(
            message=(
                f"Model '{model.name}' relationship "
                f"'{relationship.name}' is many-to-many but does not "
                "define secondary_table."
            ),
            location=(
                f"models.{model.name}.relationships."
                f"{relationship.name}.secondary_table"
            ),
            error_code="ERR_ORM_MANY_TO_MANY_SECONDARY_TABLE_MISSING",
            suggested_resolution=(
                "Define the association/secondary table for the "
                "many-to-many relationship."
            ),
        )

    if relationship.ownership is not IROwnership.ASSOCIATION:
        raise ORMGenerationError(
            message=(
                f"Model '{model.name}' relationship "
                f"'{relationship.name}' is many-to-many but has "
                f"invalid ownership '{relationship.ownership}'."
            ),
            location=(
                f"models.{model.name}.relationships."
                f"{relationship.name}.ownership"
            ),
            error_code="ERR_ORM_MANY_TO_MANY_INVALID_OWNERSHIP",
            suggested_resolution=(
                "Use IROwnership.ASSOCIATION for many-to-many "
                "relationships."
            ),
        )

    if relationship.foreign_key is not None:
        raise ORMGenerationError(
            message=(
                f"Model '{model.name}' relationship "
                f"'{relationship.name}' is many-to-many but defines "
                "a direct foreign key."
            ),
            location=(
                f"models.{model.name}.relationships."
                f"{relationship.name}.foreign_key"
            ),
            error_code="ERR_ORM_MANY_TO_MANY_DIRECT_FOREIGN_KEY",
            suggested_resolution=(
                "Use secondary_table and association-table metadata "
                "instead of a direct relationship foreign key."
            ),
        )

    logger.debug(
        "Validated many-to-many relationship: source=%s "
        "relationship=%s target=%s secondary_table=%s",
        model.name,
        relationship.name,
        target_model.name,
        secondary_table,
    )

    # model_map is deliberately accepted here because later validation can
    # resolve association-table metadata once the IR supports explicit
    # association-table definitions.
    del model_map


def _find_field(
    *,
    model: IRModel,
    field_name: str,
) -> IRField | None:
    """
    Find a normalized field by IR name or database column name.
    """
    for field in model.fields:
        if field.name == field_name:
            return field

        if field.original_name == field_name:
            return field

        if field.db_column_name == field_name:
            return field

    return None


def _expected_primary_key_reference(
    *,
    referenced_model: IRModel,
) -> str:
    """
    Return the canonical SQLAlchemy ForeignKey target for a model's
    primary key.
    """
    primary_keys = tuple(
        field
        for field in referenced_model.fields
        if field.is_primary_key
    )

    if len(primary_keys) != 1:
        raise ORMGenerationError(
            message=(
                f"Model '{referenced_model.name}' must have exactly one "
                "primary key to derive a relationship foreign-key "
                "target."
            ),
            location=f"models.{referenced_model.name}.fields",
            error_code="ERR_ORM_TARGET_PRIMARY_KEY_INVALID",
            suggested_resolution=(
                "Define exactly one primary-key field on the target "
                "entity before generating relationships."
            ),
        )

    primary_key = primary_keys[0]

    return (
        f"{referenced_model.table_name}."
        f"{primary_key.db_column_name or primary_key.original_name}"
    )


def _foreign_key_targets_match(
    *,
    actual: str,
    expected: str,
    referenced_model: IRModel,
) -> bool:
    """
    Compare normalized foreign-key targets while allowing a schema-qualified
    SQLAlchemy target.
    """
    normalized_actual = actual.strip()
    normalized_expected = expected.strip()

    if normalized_actual == normalized_expected:
        return True

    expected_column = normalized_expected.rsplit(
        ".",
        maxsplit=1,
    )[-1]

    if not normalized_actual.endswith(
        f".{expected_column}"
    ):
        return False

    actual_table = normalized_actual.rsplit(
        ".",
        maxsplit=1,
    )[0]

    return (
        actual_table == referenced_model.table_name
        or actual_table.endswith(
            f".{referenced_model.table_name}"
        )
    )
