from __future__ import annotations

from dataclasses import dataclass

from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.ir.model import IRField, IROwnership
from meta_telemetry import get_tracer, trace_span

tracer = get_tracer(
    "meta_service_generator.ir.relationships"
)


@dataclass(frozen=True, slots=True)
class NormalizedRelationshipForeignKey:
    """
    Normalized foreign-key metadata for an entity relationship.

    The FK may physically reside on either the source or target entity.
    """

    foreign_key: str | None
    ownership: IROwnership
    nullable: bool = False
    foreign_key_target: str | None = None


@trace_span("ir.relationships.normalize_foreign_key")
def normalize_relationship_foreign_key(
    *,
    source_entity: str,
    target_entity: str,
    foreign_key: str | None,
    source_fields: tuple[IRField, ...],
    target_fields: tuple[IRField, ...],
    source_table_name: str,
    source_primary_key: IRField | None,
    location: str,
) -> NormalizedRelationshipForeignKey:
    """
    Resolve the physical owner of a relationship foreign key.

    A relationship declared from Order to OrderItem may identify a foreign
    key that physically exists on OrderItem. In that case the relationship
    owns its FK on the target side rather than the source side.

    The normalization step deliberately happens before ORM validation so
    downstream generators consume canonical IR semantics.

    The FK target is always emitted using the physical database column
    name rather than the sanitized Python attribute name.

    For example:

        Python field name:
            id_

        database column:
            id

    produces:

        orders.id

    rather than:

        orders.id_
    """
    try:
        if foreign_key is None:
            return NormalizedRelationshipForeignKey(
                foreign_key=None,
                ownership=IROwnership.SOURCE,
                foreign_key_target=None,
            )

        normalized_foreign_key = foreign_key.strip()

        if not normalized_foreign_key:
            raise IRBuilderError(
                message=(
                    f"Relationship between '{source_entity}' and "
                    f"'{target_entity}' declares an empty foreign key."
                ),
                location=location,
                error_code="ERR_IR_RELATIONSHIP_EMPTY_FK",
                suggested_resolution=(
                    "Provide a valid foreign-key field name or omit "
                    "the foreign_key declaration."
                ),
            )

        source_field = _find_field(
            fields=source_fields,
            field_name=normalized_foreign_key,
        )

        if source_field is not None:
            return NormalizedRelationshipForeignKey(
                foreign_key=source_field.name,
                ownership=IROwnership.SOURCE,
                foreign_key_target=_normalize_existing_target(
                    source_field.foreign_key_target
                ),
                nullable=source_field.is_nullable,
            )

        target_field = _find_field(
            fields=target_fields,
            field_name=normalized_foreign_key,
        )

        if target_field is not None:
            foreign_key_target = _derive_foreign_key_target(
                target_field=target_field,
                target_table_name=source_table_name,
                target_primary_key=source_primary_key,
            )

            return NormalizedRelationshipForeignKey(
                foreign_key=target_field.name,
                ownership=IROwnership.TARGET,
                foreign_key_target=foreign_key_target,
                nullable=target_field.is_nullable,
            )

        raise IRBuilderError(
            message=(
                f"Relationship between '{source_entity}' and "
                f"'{target_entity}' references foreign-key field "
                f"'{foreign_key}', but that field exists on neither "
                "entity."
            ),
            location=location,
            error_code="ERR_IR_RELATIONSHIP_FK_NOT_FOUND",
            suggested_resolution=(
                "Declare the foreign-key attribute on either the "
                "source or target entity, or correct the relationship "
                "foreign_key value."
            ),
        )

    except IRBuilderError:
        raise

    except Exception as err:
        raise IRBuilderError(
            message=(
                "Failed to normalize relationship foreign key "
                f"between '{source_entity}' and '{target_entity}': "
                f"{err}"
            ),
            location=location,
            error_code="ERR_IR_RELATIONSHIP_FK_NORMALIZATION_FAILED",
            suggested_resolution=(
                "Verify relationship foreign-key metadata and "
                "entity field definitions."
            ),
        ) from err


def _find_field(
    *,
    fields: tuple[IRField, ...],
    field_name: str,
) -> IRField | None:
    """
    Resolve a field by normalized IR name, original manifest name,
    or physical database column name.
    """
    for field in fields:
        if field.name == field_name:
            return field

        if field.original_name == field_name:
            return field

        if field.db_column_name == field_name:
            return field

    return None


def _derive_foreign_key_target(
    *,
    target_field: IRField,
    target_table_name: str,
    target_primary_key: IRField | None,
) -> str:
    """
    Derive the canonical physical database target for a relationship FK.

    The target of a child FK is the primary-key database column of the
    relationship's source/parent entity.

    This helper intentionally uses db_column_name and never uses the
    sanitized Python field name as the SQLAlchemy ForeignKey target.
    """
    if target_primary_key is None:
        raise IRBuilderError(
            message=(
                f"Unable to derive foreign-key target for field "
                f"'{target_field.name}': target entity does not have "
                "a primary-key field."
            ),
            location=f"fields.{target_field.name}",
            error_code="ERR_IR_RELATIONSHIP_TARGET_PRIMARY_KEY_MISSING",
            suggested_resolution=(
                "Define exactly one primary-key field on the "
                "relationship target entity."
            ),
        )

    target_column = (
        target_primary_key.db_column_name
        or target_primary_key.original_name
    )

    if not target_column:
        raise IRBuilderError(
            message=(
                f"Unable to derive database column for primary-key "
                f"field '{target_primary_key.name}'."
            ),
            location=f"fields.{target_primary_key.name}",
            error_code="ERR_IR_RELATIONSHIP_TARGET_PRIMARY_KEY_COLUMN_MISSING",
            suggested_resolution=(
                "Ensure the primary-key field has a valid database "
                "column name."
            ),
        )

    return f"{target_table_name}.{target_column}"


def _normalize_existing_target(
    foreign_key_target: str | None,
) -> str | None:
    """
    Preserve an explicitly supplied physical foreign-key target.

    Explicit targets are assumed to already be database-qualified
    SQLAlchemy targets and are therefore not rewritten here.
    """
    if foreign_key_target is None:
        return None

    normalized = foreign_key_target.strip()

    return normalized or None
