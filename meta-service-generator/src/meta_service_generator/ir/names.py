from __future__ import annotations

import keyword
import re

PYTHON_RESERVED_KEYWORDS: frozenset[str] = frozenset(
    keyword.kwlist
) | {
    "type",
    "id",
    "dict",
    "list",
    "set",
    "tuple",
    "str",
    "int",
    "float",
    "bool",
    "object",
    "self",
    "cls",
    "metadata",
}


def sanitize_identifier(name: str) -> str:
    """Convert an arbitrary name into a valid Python identifier."""
    if not isinstance(name, str):
        raise TypeError(
            f"name must be str, got {type(name).__name__}."
        )

    cleaned = re.sub(
        r"\W+",
        "_",
        name,
    ).strip("_")

    if not cleaned:
        cleaned = "item"

    if cleaned[0].isdigit():
        cleaned = f"field_{cleaned}"

    if cleaned in PYTHON_RESERVED_KEYWORDS:
        cleaned = f"{cleaned}_"

    if not cleaned.isidentifier():
        raise ValueError(
            f"Unable to sanitize '{name}' into a valid "
            "Python identifier."
        )

    return cleaned


def to_pascal_case(name: str) -> str:
    """
    Convert snake_case, kebab-case, space-separated, camelCase, or
    PascalCase names into PascalCase while preserving existing internal
    capitalization.
    """
    if not isinstance(name, str):
        raise TypeError(
            f"name must be str, got {type(name).__name__}."
        )

    words = [
        word
        for word in re.split(
            r"[_\-\s]+",
            name.strip(),
        )
        if word
    ]

    if not words:
        return "Item"

    result = "".join(
        word[:1].upper() + word[1:]
        for word in words
    )

    if result[0].isdigit():
        result = f"Model{result}"

    if not result.isidentifier():
        raise ValueError(
            f"Unable to convert '{name}' into a valid "
            "Python class identifier."
        )

    return result



def to_snake_case(name: str) -> str:
    """Convert PascalCase, camelCase, or kebab-case names."""
    if not isinstance(name, str):
        raise TypeError(
            f"name must be str, got {type(name).__name__}."
        )

    s1 = re.sub(
        r"(.)([A-Z][a-z]+)",
        r"\1_\2",
        name,
    )

    s2 = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        s1,
    ).lower()

    cleaned = re.sub(
        r"[\-\s]+",
        "_",
        s2,
    )

    return sanitize_identifier(cleaned)


def to_screaming_snake_case(name: str) -> str:
    """Convert an arbitrary name to SCREAMING_SNAKE_CASE."""
    return to_snake_case(name).upper()
