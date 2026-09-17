#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"File not found: {path}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {path}: line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        )


def get_entities(manifest: dict[str, Any]) -> dict[str, Any]:
    entities = manifest.get("entities", {})

    if isinstance(entities, dict):
        return entities

    if isinstance(entities, list):
        result = {}
        for entity in entities:
            if isinstance(entity, dict):
                name = entity.get("name")
                if isinstance(name, str):
                    result[name] = entity
        return result

    return {}


def find_named_collection(obj: Any, names: set[str]) -> list[Any]:
    found = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in names:
                if isinstance(value, list):
                    found.extend(value)
                elif isinstance(value, dict):
                    found.extend(value.values())

            found.extend(find_named_collection(value, names))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(find_named_collection(item, names))

    return found


def extract_name(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None

    for key in ("name", "entity_name", "target_entity"):
        value = obj.get(key)
        if isinstance(value, str):
            return value

    return None


def validate_entity_references(manifest: dict[str, Any], errors: list[dict[str, Any]]):
    entities = get_entities(manifest)
    entity_names = set(entities)

    relationships = find_named_collection(
        manifest,
        {"relationships", "relationship"},
    )

    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue

        target = relationship.get("target_entity")

        if isinstance(target, str) and target not in entity_names:
            errors.append({
                "type": "missing_relationship_target",
                "target_entity": target,
            })

        source = relationship.get("source_entity")

        if isinstance(source, str) and source not in entity_names:
            errors.append({
                "type": "missing_relationship_source",
                "source_entity": source,
            })


def validate_cardinality(manifest: dict[str, Any], errors: list[dict[str, Any]]):
    relationships = find_named_collection(
        manifest,
        {"relationships", "relationship"},
    )

    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue

        cardinality = relationship.get("cardinality")

        if cardinality == "N:1":
            errors.append({
                "type": "unsupported_directional_cardinality",
                "message": (
                    "N:1 relationship found. The manifest pipeline requires "
                    "parent-to-child 1:N representation when N:1 is not "
                    "supported by the schema."
                ),
                "relationship": relationship,
            })


def validate_foreign_keys(manifest: dict[str, Any], errors: list[dict[str, Any]]):
    entities = get_entities(manifest)

    relationships = find_named_collection(
        manifest,
        {"relationships", "relationship"},
    )

    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue

        source = relationship.get("source_entity")
        target = relationship.get("target_entity")
        foreign_key = relationship.get("foreign_key")

        if (
            isinstance(source, str)
            and isinstance(foreign_key, str)
            and source in entities
        ):
            entity = entities[source]

            attributes = entity.get("attributes", {})

            if isinstance(attributes, dict):
                if foreign_key not in attributes:
                    errors.append({
                        "type": "missing_foreign_key_attribute",
                        "entity": source,
                        "foreign_key": foreign_key,
                        "target_entity": target,
                    })

            elif isinstance(attributes, list):
                names = {
                    item.get("name")
                    for item in attributes
                    if isinstance(item, dict)
                }

                if foreign_key not in names:
                    errors.append({
                        "type": "missing_foreign_key_attribute",
                        "entity": source,
                        "foreign_key": foreign_key,
                        "target_entity": target,
                    })


def validate_fsm_references(manifest: dict[str, Any], errors: list[dict[str, Any]]):
    entities = get_entities(manifest)

    for entity_name, entity in entities.items():
        if not isinstance(entity, dict):
            continue

        fsm = entity.get("fsm")

        if not isinstance(fsm, dict):
            continue

        state_attribute = fsm.get("state_attribute")

        attributes = entity.get("attributes", {})

        attribute_names = set()

        if isinstance(attributes, dict):
            attribute_names = set(attributes)
        elif isinstance(attributes, list):
            attribute_names = {
                item.get("name")
                for item in attributes
                if isinstance(item, dict)
            }

        if isinstance(state_attribute, str):
            if state_attribute not in attribute_names:
                errors.append({
                    "type": "missing_fsm_state_attribute",
                    "entity": entity_name,
                    "state_attribute": state_attribute,
                })

        states = fsm.get("states", [])

        if isinstance(states, list):
            state_names = set()

            for state in states:
                if isinstance(state, str):
                    state_names.add(state)
                elif isinstance(state, dict):
                    name = state.get("name")
                    if isinstance(name, str):
                        state_names.add(name)

            initial_state = fsm.get("initial_state")

            if (
                isinstance(initial_state, str)
                and initial_state not in state_names
            ):
                errors.append({
                    "type": "invalid_fsm_initial_state",
                    "entity": entity_name,
                    "initial_state": initial_state,
                })

            transitions = fsm.get("transitions", [])

            if isinstance(transitions, list):
                for transition in transitions:
                    if not isinstance(transition, dict):
                        continue

                    for field in ("source_state", "target_state"):
                        state = transition.get(field)

                        if (
                            isinstance(state, str)
                            and state not in state_names
                        ):
                            errors.append({
                                "type": "invalid_fsm_transition_state",
                                "entity": entity_name,
                                "field": field,
                                "state": state,
                            })


def dependency_graph_has_cycle(workflow: dict[str, Any]) -> bool:
    steps = workflow.get("steps", [])

    if not isinstance(steps, list):
        return False

    graph: dict[str, list[str]] = {}

    for step in steps:
        if not isinstance(step, dict):
            continue

        name = step.get("name")

        if not isinstance(name, str):
            continue

        dependencies = step.get("depends_on", [])

        if not isinstance(dependencies, list):
            dependencies = []

        graph[name] = [
            dependency
            for dependency in dependencies
            if isinstance(dependency, str)
        ]

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True

        if node in visited:
            return False

        visiting.add(node)

        for dependency in graph.get(node, []):
            if dependency in graph and visit(dependency):
                return True

        visiting.remove(node)
        visited.add(node)

        return False

    return any(visit(node) for node in graph)


def validate_workflows(manifest: dict[str, Any], errors: list[dict[str, Any]]):
    workflows = find_named_collection(
        manifest,
        {"workflows", "workflow"},
    )

    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue

        if dependency_graph_has_cycle(workflow):
            errors.append({
                "type": "workflow_dependency_cycle",
                "workflow": workflow.get("name"),
            })


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: semantic_validate.py MANIFEST_PATH",
            file=sys.stderr,
        )
        return 2

    path = Path(sys.argv[1])

    try:
        manifest = load_json(path)

        if not isinstance(manifest, dict):
            print(json.dumps({
                "status": "invalid",
                "errors": [
                    {
                        "type": "root_not_object"
                    }
                ]
            }, indent=2))
            return 1

        errors: list[dict[str, Any]] = []

        validate_entity_references(manifest, errors)
        validate_cardinality(manifest, errors)
        validate_foreign_keys(manifest, errors)
        validate_fsm_references(manifest, errors)
        validate_workflows(manifest, errors)

        result = {
            "status": "valid" if not errors else "invalid",
            "error_count": len(errors),
            "errors": errors,
        }

        print(json.dumps(result, indent=2))

        return 0 if not errors else 1

    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "message": str(exc),
        }, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
