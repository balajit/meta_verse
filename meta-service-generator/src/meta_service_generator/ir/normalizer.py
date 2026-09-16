from __future__ import annotations

from meta_service_generator.exceptions import IRBuilderError


class TypeNormalizer:
    """Maps manifest primitive types to Python and SQLAlchemy types."""

    _TYPE_MAP: dict[str, tuple[str, str]] = {
        "str": ("str", "String"),
        "int": ("int", "Integer"),
        "float": ("float", "Float"),
        "bool": ("bool", "Boolean"),
        "datetime": (
            "datetime.datetime",
            "DateTime(timezone=True)",
        ),
        "uuid": (
            "uuid.UUID",
            "Uuid",
        ),
        "dict": (
            "dict[str, Any]",
            "JSON",
        ),
        "list": (
            "list[Any]",
            "JSON",
        ),
    }

    @classmethod
    def normalize_type(
        cls,
        raw_type: str,
        location: str = "attribute",
    ) -> tuple[str, str]:
        if not isinstance(raw_type, str):
            raise IRBuilderError(
                message=(
                    f"Attribute type at '{location}' must be a string, "
                    f"got {type(raw_type).__name__}."
                ),
                location=location,
                error_code="ERR_IR_TYPE_NOT_STRING",
                suggested_resolution=(
                    "Use one of the supported manifest attribute types."
                ),
            )

        normalized = raw_type.strip().lower()

        if not normalized:
            raise IRBuilderError(
                message=(
                    f"Attribute type at '{location}' cannot be empty."
                ),
                location=location,
                error_code="ERR_IR_EMPTY_TYPE",
                suggested_resolution=(
                    "Specify a supported manifest attribute type."
                ),
            )

        result = cls._TYPE_MAP.get(normalized)

        if result is not None:
            return result

        raise IRBuilderError(
            message=(
                f"Unsupported raw type '{raw_type}' encountered "
                "during IR normalization."
            ),
            location=location,
            error_code="ERR_IR_UNSUPPORTED_TYPE",
            suggested_resolution=(
                "Use one of: "
                f"{', '.join(sorted(cls._TYPE_MAP))}."
            ),
        )