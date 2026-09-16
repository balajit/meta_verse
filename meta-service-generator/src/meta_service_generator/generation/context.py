from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.ir.model import IRModel, ServiceIR
from meta_service_generator.ir.names import sanitize_identifier, to_snake_case
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span


logger = get_logger("meta_service_generator.generation.context")
tracer = get_tracer("meta_service_generator.generation.context")


class GenerationContext(BaseModel):
    """Immutable compiler context shared by every generation subsystem."""

    service_name: str
    package_name: str
    version: str

    models: tuple[IRModel, ...]

    has_fsms: bool = False
    has_rules: bool = False
    has_workflows: bool = False
    has_policies: bool = False

    template_version: str
    transform_version: str
    generator_version: str

    extra_imports: tuple[str, ...] = Field(default_factory=tuple)

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )

    @property
    def model_map(self) -> Mapping[str, IRModel]:
        return MappingProxyType(
            {model.name: model for model in self.models}
        )

    @classmethod
    @trace_span("generation.context.from_service_ir")
    def from_service_ir(
        cls,
        service_ir: ServiceIR,
        *,
        generator_version: str = "GV_DEFAULT",
        template_version: str = "TV_DEFAULT",
        transform_version: str = "TRV_DEFAULT",
    ) -> "GenerationContext":
        if not isinstance(service_ir, ServiceIR):
            raise CodeGenerationError(
                message=(
                    "Generation context requires a ServiceIR instance; "
                    f"received {type(service_ir).__name__}."
                ),
                location="service_ir",
                error_code="ERR_GENERATION_CONTEXT_INVALID_IR",
                suggested_resolution=(
                    "Pass the validated immutable ServiceIR produced by the "
                    "manifest-to-IR compilation stage."
                ),
            )

        try:
            package_name = sanitize_identifier(
                to_snake_case(service_ir.service_name)
            )

            if not package_name.isidentifier():
                raise CodeGenerationError(
                    message=(
                        f"Invalid generated package name: "
                        f"{package_name!r}."
                    ),
                    location="service_name",
                    error_code="ERR_GENERATION_PACKAGE_NAME_INVALID",
                    suggested_resolution=(
                        "Choose a service_name that can be represented as "
                        "a Python package."
                    ),
                )

            context = cls(
                service_name=service_ir.service_name,
                package_name=package_name,
                version=service_ir.version,
                models=tuple(service_ir.models),
                has_fsms=any(
                    model.fsm is not None
                    for model in service_ir.models
                ),
                has_rules=bool(service_ir.rules),
                has_workflows=bool(service_ir.workflows),
                has_policies=bool(service_ir.policies),
                generator_version=generator_version,
                template_version=template_version,
                transform_version=transform_version,
            )

            logger.info(
                "Generation context created.",
                extra={
                    "event_type": "generation_context_created",
                    "service_name": context.service_name,
                    "package_name": context.package_name,
                    "version": context.version,
                    "model_count": len(context.models),
                    "has_fsms": context.has_fsms,
                    "has_rules": context.has_rules,
                    "has_workflows": context.has_workflows,
                    "has_policies": context.has_policies,
                },
            )

            return context

        except CodeGenerationError:
            raise

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to construct generation context for service "
                    f"'{service_ir.service_name}': {err}"
                ),
                location="generation_context",
                error_code="ERR_GENERATION_CONTEXT_BUILD_FAILED",
                suggested_resolution=(
                    "Verify ServiceIR service metadata and "
                    "generation-version values."
                ),
            ) from err

    def as_template_context(self) -> Mapping[str, Any]:
        """Return a read-only template context."""

        return MappingProxyType(
            {
                "service_name": self.service_name,
                "package_name": self.package_name,
                "version": self.version,
                "models": self.models,
                "model_map": self.model_map,
                "has_fsms": self.has_fsms,
                "has_rules": self.has_rules,
                "has_workflows": self.has_workflows,
                "has_policies": self.has_policies,
                "extra_imports": self.extra_imports,
                "generator_version": self.generator_version,
                "template_version": self.template_version,
                "transform_version": self.transform_version,
            }
        )