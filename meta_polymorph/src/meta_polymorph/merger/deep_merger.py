"""Pure Python recursive deep merge utility with recursion depth limits."""

import copy
import logging
from typing import Any

from meta_telemetry import trace_span

UNSET_SENTINEL = "$unset"
MAX_RECURSION_DEPTH = 100

logger = logging.getLogger("meta_polymorph.merger")


def deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
    _current_depth: int = 0,
) -> dict[str, Any]:
    """Recursively merges two dictionaries into a new dictionary without mutating inputs."""
    if _current_depth > MAX_RECURSION_DEPTH:
        logger.error(
            "Max recursion depth exceeded during deep_merge",
            extra={"max_depth": MAX_RECURSION_DEPTH, "current_depth": _current_depth},
        )
        raise ValueError(
            f"Maximum recursion depth of {MAX_RECURSION_DEPTH} exceeded during manifest merge."
        )

    result = copy.deepcopy(base)

    for key, value in override.items():
        if value == UNSET_SENTINEL:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(
                result[key], value, _current_depth=_current_depth + 1
            )
        elif isinstance(value, dict):
            result[key] = deep_merge({}, value, _current_depth=_current_depth + 1)
        else:
            result[key] = copy.deepcopy(value)

    return result


def _extract_deep_merge_attrs(params: dict[str, Any]) -> dict[str, Any]:
    base = params.get("base")
    override = params.get("override")
    return {
        "merge.base_keys_count": len(base) if isinstance(base, dict) else 0,
        "merge.override_keys_count": len(override) if isinstance(override, dict) else 0,
    }


class DeepMerger:
    """Stateless wrapper class providing deep dictionary merge operations."""

    @staticmethod
    @trace_span(name="DeepMerger.deep_merge", extract_attributes=_extract_deep_merge_attrs)
    def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        return deep_merge(base, override)