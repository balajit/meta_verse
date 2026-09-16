from __future__ import annotations

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.ir.model import IRModel
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict


logger = get_logger("meta_service_generator.generation.dto")
tracer = get_tracer("meta_service_generator.generation.dto")


class DTOAttributeContext(BaseModel):
    """Immutable template context for one DTO attribute."""

    name: str
    original_name: str
    python_type: str
    is_optional: bool = False
    default_value: str = "..."

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class DTOSpecContext(BaseModel):
    """Immutable rendering specification for generated DTO classes."""

    model_name: str
    class_name: str
    create_fields: tuple[DTOAttributeContext, ...]
    update_fields: tuple[DTOAttributeContext, ...]
    search_fields: tuple[DTOAttributeContext, ...]
    response_fields: tuple[DTOAttributeContext, ...]

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class DTOGenerator:
    """Synthesizes isolated Create, Update, Search, and Response DTO contexts enforcing REQ-004."""

    @trace_span("generation.dto.build_dto_specs")
    def build_dto_specs(self, model: IRModel) -> DTOSpecContext:
        if not isinstance(model, IRModel):
            raise CodeGenerationError(
                message=(
                    f"model must be IRModel, got "
                    f"{type(model).__name__}."
                ),
                location="model",
                error_code="ERR_DTO_INVALID_MODEL",
                suggested_resolution=(
                    "Pass a validated immutable IRModel from ServiceIR."
                ),
            )

        try:
            create_fields: list[DTOAttributeContext] = []
            update_fields: list[DTOAttributeContext] = []
            search_fields: list[DTOAttributeContext] = []
            response_fields: list[DTOAttributeContext] = []

            for field in model.fields:
                response_fields.append(
                    DTOAttributeContext(
                        name=field.name,
                        original_name=field.original_name,
                        python_type=field.python_type,
                        is_optional=field.is_nullable,
                        default_value=(
                            "None" if field.is_nullable else "..."
                        ),
                    )
                )

                if field.is_primary_key:
                    continue

                create_fields.append(
                    DTOAttributeContext(
                        name=field.name,
                        original_name=field.original_name,
                        python_type=field.python_type,
                        is_optional=field.is_nullable,
                        default_value=(
                            "None" if field.is_nullable else "..."
                        ),
                    )
                )

                update_fields.append(
                    DTOAttributeContext(
                        name=field.name,
                        original_name=field.original_name,
                        python_type=field.python_type,
                        is_optional=True,
                        default_value="None",
                    )
                )

                search_fields.append(
                    DTOAttributeContext(
                        name=field.name,
                        original_name=field.original_name,
                        python_type=field.python_type,
                        is_optional=True,
                        default_value="None",
                    )
                )

            result = DTOSpecContext(
                model_name=model.name,
                class_name=model.class_name,
                create_fields=tuple(create_fields),
                update_fields=tuple(update_fields),
                search_fields=tuple(search_fields),
                response_fields=tuple(response_fields),
            )

            logger.info(
                "DTO specifications generated.",
                extra={
                    "event_type": "dto_specs_generated",
                    "model_name": model.name,
                    "create_field_count": len(result.create_fields),
                    "update_field_count": len(result.update_fields),
                    "search_field_count": len(result.search_fields),
                    "response_field_count": len(result.response_fields),
                },
            )

            return result

        except CodeGenerationError:
            raise

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to generate DTO specifications for model "
                    f"'{model.name}': {err}"
                ),
                location=f"models/{model.name}",
                error_code="ERR_DTO_GENERATION_FAILED",
                suggested_resolution=(
                    "Verify entity field definitions and type attributes."
                ),
            ) from err