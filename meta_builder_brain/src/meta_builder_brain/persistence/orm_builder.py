"""Dynamic metaclass factory for generating SQLAlchemy models at runtime."""

from typing import Dict, Any, Type, Callable
from sqlalchemy import Column, Integer, String, JSON, Boolean, DateTime, Float
from sqlalchemy.types import TypeEngine
from sqlalchemy.orm import DeclarativeBase

from meta_telemetry import trace_span
from meta_builder_brain.exceptions import (
    PersistenceError,
    UnsupportedTypeMappingError,
)


class DynamicMetaclassBuilder:
    """Factory for dynamically creating SQLAlchemy ORM models from schema properties at runtime."""

    # Map type identifiers to type constructors to prevent shared-instance state bugs
    TYPE_MAP: Dict[str, Callable[[], TypeEngine[Any]]] = {
        "string": lambda: String(255),
        "integer": Integer,
        "json": JSON,
        "boolean": Boolean,
        "datetime": DateTime,
        "float": Float,
    }

    @classmethod
    @trace_span(name="persistence.create_orm_model")
    def create_orm_model(
        cls,
        class_name: str,
        table_name: str,
        fields: Dict[str, Any],
        base_class: Type[DeclarativeBase],
    ) -> Type[DeclarativeBase]:
        """Dynamically generates a SQLAlchemy ORM mapped class from field specifications."""
        if not class_name or not class_name.strip():
            raise PersistenceError("ORM class_name identifier cannot be empty.")
        if not table_name or not table_name.strip():
            raise PersistenceError("ORM table_name target cannot be empty.")
        if not isinstance(fields, dict):
            raise PersistenceError("Fields specification payload must be a dictionary.")

        # Check if table was previously registered to avoid registry collisions
        if table_name in base_class.metadata.tables:
            base_class.metadata.remove(base_class.metadata.tables[table_name])

        attributes: Dict[str, Any] = {
            "__tablename__": table_name,
            "__module__": "meta_builder_brain.persistence.dynamic",
        }

        has_primary_key = False

        for field_name, field_spec in fields.items():
            field_type: str = "string"
            is_nullable: bool = True
            is_pk: bool = False

            if isinstance(field_spec, dict):
                field_type = field_spec.get("type", "string")
                is_nullable = field_spec.get("nullable", True)
                is_pk = field_spec.get("primary_key", False)
            elif isinstance(field_spec, str):
                field_type = field_spec
            else:
                raise PersistenceError(
                    f"Invalid specification format for field '{field_name}' in ORM builder."
                )

            field_type_clean = field_type.lower()
            if field_type_clean not in cls.TYPE_MAP:
                raise UnsupportedTypeMappingError(
                    f"Unsupported dynamic field type '{field_type}' for column '{field_name}'."
                )

            col_type = cls.TYPE_MAP[field_type_clean]()
            if is_pk:
                has_primary_key = True
                is_nullable = False

            attributes[field_name] = Column(col_type, primary_key=is_pk, nullable=is_nullable)

        # Ensure at least one primary key exists, defaulting to auto-increment 'id' if missing
        if not has_primary_key and "id" not in attributes:
            attributes["id"] = Column(Integer(), primary_key=True, autoincrement=True)

        try:
            return type(class_name, (base_class,), attributes)
        except Exception as exc:
            raise PersistenceError(
                f"Failed to dynamically synthesize ORM model class '{class_name}': {exc}"
            ) from exc