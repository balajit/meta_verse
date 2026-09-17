"""Layer resolver component."""

import logging
from typing import Any

from meta_telemetry import trace_span
from meta_polymorph.merger.deep_merger import DeepMerger

logger = logging.getLogger("meta_polymorph.resolver")


def _extract_resolver_attrs(params: dict[str, Any]) -> dict[str, Any]:
    layers = params.get("layers")
    if isinstance(layers, list):
        return {
            "resolver.layer_count": len(layers),
            "resolver.valid_layer_count": sum(1 for l in layers if isinstance(l, dict)),
        }
    return {"resolver.layer_count": 0, "resolver.valid_layer_count": 0}


class PolymorphicResolver:
    """Consolidated layer resolver executing sequential deep merges across hierarchy tiers."""

    @trace_span(name="PolymorphicResolver.resolve", extract_attributes=_extract_resolver_attrs)
    def resolve(self, layers: list[dict[str, Any]]) -> dict[str, Any]:
        """Sequentially merges dictionary layers from base (Global) to leaf (Tenant)."""
        logger.debug(
            "Resolving polymorphic layers",
            extra={"layer_count": len(layers) if isinstance(layers, list) else 0},
        )
        merged_manifest: dict[str, Any] = {}
        if not isinstance(layers, list):
            raise TypeError(f"Expected layers to be a list, got {type(layers).__name__}")

        for idx, layer in enumerate(layers):
            if not isinstance(layer, dict):
                raise TypeError(
                    f"Layer at index {idx} is not a valid dictionary: {type(layer).__name__}"
                )
            merged_manifest = DeepMerger.deep_merge(merged_manifest, layer)

        return merged_manifest