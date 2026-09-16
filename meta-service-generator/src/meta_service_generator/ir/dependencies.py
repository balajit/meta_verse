from __future__ import annotations

import graphlib
from typing import cast

from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.ir.model import (
    IRModel,
    ServiceIR,
)
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span


logger = get_logger("meta_service_generator.ir.dependencies")
tracer = get_tracer("meta_service_generator.ir.dependencies")


class DependencyResolver:
    """Resolves model ordering and separates circular imports."""

    @trace_span("ir.dependencies.topological_sort_models")
    def topological_sort_models(
        self,
        service_ir: ServiceIR,
    ) -> list[IRModel]:
        if not isinstance(service_ir, ServiceIR):
            raise IRBuilderError(
                message=(
                    "DependencyResolver requires ServiceIR; "
                    f"received {type(service_ir).__name__}."
                ),
                location="service_ir",
                error_code="ERR_IR_DEPENDENCY_INVALID_INPUT",
                suggested_resolution=(
                    "Pass the immutable ServiceIR produced by IRBuilder."
                ),
                details={
                    "received_type": type(service_ir).__name__,
                },
            )

        model_map: dict[str, IRModel] = {}

        for model in service_ir.models:
            if model.name in model_map:
                raise IRBuilderError(
                    message=f"Duplicate IR model name '{model.name}'.",
                    location=f"models/{model.name}",
                    error_code="ERR_IR_DUPLICATE_MODEL",
                    suggested_resolution=(
                        "Ensure each manifest entity name is unique."
                    ),
                )

            model_map[model.name] = model

        sorter: graphlib.TopologicalSorter[str] = (
            graphlib.TopologicalSorter()
        )

        for model in service_ir.models:
            dependencies = {
                rel.target_entity
                for rel in model.relationships
                if (
                    rel.target_entity in model_map
                    and rel.target_entity != model.name
                    and not rel.is_circular
                )
            }

            sorter.add(
                model.name,
                *sorted(dependencies),
            )

        try:
            ordered_names = list(
                sorter.static_order()
            )

        except graphlib.CycleError as err:
            raw_cycle = (
                err.args[1]
                if len(err.args) > 1
                else ()
            )

            cycle_nodes = [
                str(node)
                for node in cast(
                    tuple[object, ...],
                    raw_cycle,
                )
            ]

            location = (
                f"entities/{cycle_nodes[0]}"
                if cycle_nodes
                else "entities"
            )

            logger.error(
                "Non-circular dependency cycle encountered.",
                extra={
                    "event_type": "ir.dependencies.cycle_detected",
                    "cycle_nodes": cycle_nodes,
                    "model_count": len(model_map),
                },
            )

            raise IRBuilderError(
                message=(
                    "Non-isolated dependency cycle encountered "
                    "during model sorting: "
                    f"{' -> '.join(cycle_nodes)}."
                ),
                location=location,
                error_code="ERR_IR_DEPENDENCY_CYCLE",
                suggested_resolution=(
                    "Ensure every dependency cycle is explicitly "
                    "represented as circular in the IR."
                ),
                details={
                    "cycle_nodes": cycle_nodes,
                    "model_count": len(model_map),
                },
            ) from err

        ordered_models = [
            model_map[name]
            for name in ordered_names
        ]

        logger.info(
            "IR model dependency ordering completed.",
            extra={
                "event_type": "ir.dependencies.ordering_completed",
                "model_count": len(ordered_models),
                "ordered_models": [
                    model.name
                    for model in ordered_models
                ],
            },
        )

        return ordered_models

    @trace_span("ir.dependencies.compute_import_manifest")
    def compute_import_manifest(
        self,
        model: IRModel,
        service_ir: ServiceIR,
    ) -> dict[str, set[str]]:
        """Compute standard, runtime, and deferred imports."""

        if not isinstance(model, IRModel):
            raise IRBuilderError(
                message=(
                    "compute_import_manifest requires IRModel; "
                    f"received {type(model).__name__}."
                ),
                location="model",
                error_code="ERR_IR_IMPORT_MANIFEST_INVALID_MODEL",
                suggested_resolution=(
                    "Pass an IRModel from the canonical ServiceIR."
                ),
            )

        if not isinstance(service_ir, ServiceIR):
            raise IRBuilderError(
                message=(
                    "compute_import_manifest requires ServiceIR; "
                    f"received {type(service_ir).__name__}."
                ),
                location="service_ir",
                error_code="ERR_IR_IMPORT_MANIFEST_INVALID_SERVICE",
                suggested_resolution=(
                    "Pass the immutable ServiceIR produced by IRBuilder."
                ),
            )

        runtime_imports: set[str] = set()
        type_checking_imports: set[str] = set()
        standard_imports: set[str] = set()

        for field in model.fields:
            if "datetime" in field.python_type:
                standard_imports.add(
                    "import datetime"
                )

            if "uuid.UUID" in field.python_type:
                standard_imports.add(
                    "import uuid"
                )

            if any(
                token in field.python_type
                for token in (
                    "Any",
                    "dict",
                    "list",
                )
            ):
                standard_imports.add(
                    "from typing import Any"
                )

        all_models = {
            candidate.name: candidate
            for candidate in service_ir.models
        }

        for relationship in model.relationships:
            target_model = all_models.get(
                relationship.target_entity
            )

            if (
                target_model is None
                or target_model.name == model.name
            ):
                continue

            import_statement = (
                f"from . import {target_model.class_name}"
            )

            if relationship.is_circular:
                type_checking_imports.add(
                    import_statement
                )
            else:
                runtime_imports.add(
                    import_statement
                )

        if type_checking_imports:
            standard_imports.add(
                "from typing import TYPE_CHECKING"
            )

        result = {
            "standard": standard_imports,
            "runtime_models": runtime_imports,
            "type_checking_models": type_checking_imports,
        }

        logger.debug(
            "Computed IR import manifest.",
            extra={
                "event_type": "ir.dependencies.import_manifest_computed",
                "model_name": model.name,
                "standard_import_count": len(
                    standard_imports
                ),
                "runtime_import_count": len(
                    runtime_imports
                ),
                "type_checking_import_count": len(
                    type_checking_imports
                ),
            },
        )

        return result