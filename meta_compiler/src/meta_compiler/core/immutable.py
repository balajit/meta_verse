"""Immutable data-structure primitives for deep-frozen IR and Pydantic models.

The compiler's ``frozen=True`` Pydantic models and ``frozen=True`` dataclasses
are only *shallowly* immutable: nested dictionaries remain writable, which makes
canonical hashes and registry entries unstable. These helpers provide JSON-safe,
read-only mappings and recursive freezing used by :mod:`meta_compiler.core.models`
and :mod:`meta_compiler.core.ir`.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, Self


class ImmutableDict(dict):
    """A read-only ``dict`` subclass that rejects all write operations.

    Subclassing ``dict`` (rather than wrapping a mapping) keeps the value fully
    serializable by Pydantic v2 and ``json.dumps`` while preventing in-place
    mutation by raising ``TypeError`` on every mutator.
    """

    _MUTATION_ERROR = "ImmutableDict does not support item assignment"

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("ImmutableDict does not support item assignment")

    def __delitem__(self, key: Any) -> None:
        raise TypeError("ImmutableDict does not support item deletion")

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("ImmutableDict does not support attribute assignment")

    def pop(self, *args: Any) -> Any:
        raise TypeError("ImmutableDict does not support pop()")

    def popitem(self) -> Any:
        raise TypeError("ImmutableDict does not support popitem()")

    def clear(self) -> None:
        raise TypeError("ImmutableDict does not support clear()")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("ImmutableDict does not support update()")

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("ImmutableDict does not support setdefault()")

    def __ior__(self, other: Any) -> Self:  # type: ignore[misc]
        raise TypeError("ImmutableDict does not support in-place union")

    def __copy__(self) -> Self:
        return type(self)(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        copied = type(self)(
            (copy.deepcopy(key, memo), copy.deepcopy(value, memo)) for key, value in self.items()
        )
        memo[id(self)] = copied
        return copied


def freeze_value(value: Any) -> Any:
    """Recursively converts nested dicts/lists into immutable equivalents.

    Dicts become :class:`ImmutableDict`; lists become tuples. Other values are
    returned unchanged.
    """
    if isinstance(value, dict):
        return ImmutableDict((key, freeze_value(item)) for key, item in value.items())
    if isinstance(value, list):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_value(item) for item in value)
    return value


def immutable_mapping(value: Mapping[str, Any]) -> ImmutableDict:
    """Wraps a mapping into a read-only :class:`ImmutableDict`.

    Returns the argument unchanged when it is already immutable; otherwise the
    nested contents are recursively frozen into a fresh immutable copy.
    """
    if isinstance(value, ImmutableDict):
        return value
    return freeze_value(dict(value)) if isinstance(value, Mapping) else ImmutableDict(value)
