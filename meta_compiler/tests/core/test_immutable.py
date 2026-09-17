"""Deep immutability primitives: ImmutableDict and freeze_value."""

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import BaseModel

from meta_compiler.core.immutable import ImmutableDict, freeze_value, immutable_mapping


def test_immutable_dict_supports_reads() -> None:
    d = ImmutableDict({"a": 1, "b": 2})
    assert d["a"] == 1
    assert dict(d) == {"a": 1, "b": 2}
    assert len(d) == 2
    assert isinstance(d, Mapping)


def test_immutable_dict_blocks_item_assignment() -> None:
    d = ImmutableDict({"a": 1})
    with pytest.raises(TypeError):
        d["a"] = 2  # type: ignore[index]


def test_immutable_dict_blocks_mutators() -> None:
    d = ImmutableDict({"a": 1})
    with pytest.raises(TypeError):
        d.update({"b": 2})
    with pytest.raises(TypeError):
        del d["a"]
    with pytest.raises(TypeError):
        d.pop("a")
    with pytest.raises(TypeError):
        d.clear()
    with pytest.raises(TypeError):
        d.setdefault("b", 2)
    with pytest.raises(TypeError):
        d |= {"b": 2}


def test_freeze_value_recurses_into_containers() -> None:
    frozen = freeze_value({"outer": {"inner": [1, 2], "map": {"k": "v"}}})
    assert isinstance(frozen, ImmutableDict)
    assert isinstance(frozen["outer"], ImmutableDict)
    assert isinstance(frozen["outer"]["inner"], tuple)
    assert isinstance(frozen["outer"]["map"], ImmutableDict)
    assert frozen["outer"]["inner"] == (1, 2)


def test_freeze_value_is_round_trip_serializable() -> None:
    class Holder(BaseModel):
        payload: Any

    original = {"nested": {"list": [1, 2, 3]}}
    holder = Holder(payload=freeze_value(original))
    dumped = holder.model_dump(mode="json")
    assert dumped["payload"]["nested"]["list"] == [1, 2, 3]
    from_validation = Holder.model_validate(dumped)
    assert isinstance(from_validation.payload, dict)


def test_immutable_mapping_returns_same_frozen_instance() -> None:
    d = ImmutableDict({"a": 1})
    assert immutable_mapping(d) is d
