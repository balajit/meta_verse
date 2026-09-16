from typing import Any, Dict


def transform_builder_spec_to_manifest(spec_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms application builder specs into meta_compiler compatible entity
    and DAG workflow manifests.
    """
    model_name = spec_payload.get("model_name", "DefaultModel")
    fields = spec_payload.get("fields", {})

    return {
        "version": spec_payload.get("version", "1.0.0"),
        "entities": {
            model_name: {
                "attributes": fields
            }
        },
        "workflow": {
            "nodes": spec_payload.get("nodes", []),
            "edges": spec_payload.get("edges", [])
        }
    }