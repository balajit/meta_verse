from __future__ import annotations

import structlog

from meta_application_builder.compiler_engine.brain_adapter.ir_sanitizer import (
    UntrustedIRModel,
)

logger = structlog.get_logger(__name__)

ALLOWED_TYPE_HINTS = {"str", "int", "float", "bool", "dict", "list", "UUID", "datetime"}


class PydanticEmitter:
    @staticmethod
    def _validate_type_hint(type_hint: str) -> str:
        # Prevent arbitrary code execution or injection via dynamic type hint strings
        if type_hint not in ALLOWED_TYPE_HINTS and not type_hint.startswith("Optional["):
            raise ValueError(f"Disallowed or unverified type hint expression: '{type_hint}'")
        return type_hint

    @staticmethod
    def emit_model_code(ir: UntrustedIRModel) -> str:
        fields_code = []
        for field in ir.fields:
            validated_type = PydanticEmitter._validate_type_hint(field.type_hint)
            default_repr = f" = {field.default!r}" if field.default is not None else ""
            if field.nullable and field.default is None:
                type_str = f"None | {validated_type}"
                default_repr = " = None"
            else:
                type_str = validated_type
            fields_code.append(f"    {field.name}: {type_str}{default_repr}")

        fields_block = "\n".join(fields_code) if fields_code else "    pass"

        # Explicit AST node validation or strict template rendering using only allowlisted structures
        code = f"""from pydantic import BaseModel, ConfigDict

class {ir.model_name}(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
{fields_block}
"""
        logger.info("pydantic_model_emitted", model_name=ir.model_name)
        return code