import pytest
from meta_polymorph.merger.deep_merger import deep_merge, UNSET_SENTINEL, DeepMerger


def test_flat_key_merge_and_override():
    base = {"a": 1, "b": 2, "c": 3}
    override = {"b": 20, "d": 4}
    result = deep_merge(base, override)

    assert result == {"a": 1, "b": 20, "c": 3, "d": 4}


def test_deep_nesting():
    base = {
        "level1": {
            "level2": {
                "a": 1,
                "b": 2,
            },
            "keep": True,
        }
    }
    override = {
        "level1": {
            "level2": {
                "b": 22,
                "c": 33,
            }
        }
    }
    result = deep_merge(base, override)

    expected = {
        "level1": {
            "level2": {
                "a": 1,
                "b": 22,
                "c": 33,
            },
            "keep": True,
        }
    }
    assert result == expected


def test_array_list_overrides():
    base = {
        "tags": ["python", "asyncio"],
        "nested": {"items": [1, 2, 3]},
    }
    override = {
        "tags": ["rust", "pydantic"],
        "nested": {"items": [4, 5]},
    }
    result = deep_merge(base, override)

    assert result == {
        "tags": ["rust", "pydantic"],
        "nested": {"items": [4, 5]},
    }


def test_unset_flat_and_nested_keys():
    base = {
        "a": 10,
        "b": 20,
        "nested": {
            "x": 100,
            "y": 200,
            "deep": {"remove_me": "yes", "stay": "here"},
        },
    }
    override = {
        "a": UNSET_SENTINEL,
        "nested": {
            "y": "$unset",
            "deep": {"remove_me": "$unset"},
        },
        "non_existent": "$unset",
    }
    result = deep_merge(base, override)

    expected = {
        "b": 20,
        "nested": {
            "x": 100,
            "deep": {"stay": "here"},
        },
    }
    assert result == expected


def test_deep_merger_wrapper_class():
    base = {"key": "val"}
    override = {"key": "new_val"}
    assert DeepMerger.deep_merge(base, override) == {"key": "new_val"}