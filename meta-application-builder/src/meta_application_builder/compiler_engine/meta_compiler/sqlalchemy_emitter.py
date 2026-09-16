# file name: meta_application_builder/compiler_engine/meta_compiler/sqlalchemy_emitter.py

from __future__ import annotations

import structlog

from meta_application_builder.compiler_engine.brain_adapter.ir_sanitizer import (
    UntrustedIRModel,
)

logger = structlog.get_logger(__name__)

ALLOWED_ORM_TYPES = {"int", "str", "float", "bool", "datetime", "UUID"}


class SQLAlchemyEmitter:
    @staticmethod
    def _validate_orm_type(type_hint: str) -> str:
        if type_hint not in ALLOWED_ORM_TYPES:
            raise ValueError(f"Disallowed or unverified SQLAlchemy ORM type hint: '{type_hint}'")
        return type_hint

    @staticmethod
    def emit_orm_code(ir: UntrustedIRModel, table_name: str) -> str:
        extra_imports = set()
        fields_code = [
            "    __tablename__ = " + repr(table_name),
            "    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)"
        ]

        for field in ir.fields:
            validated_type = SQLAlchemyEmitter._validate_orm_type(field.type_hint)
            if validated_type == "datetime":
                extra_imports.add("from datetime import datetime")
            elif validated_type == "UUID":
                extra_imports.add("from uuid import UUID")

            nullable_str = "nullable=True" if field.nullable else "nullable=False"
            fields_code.append(f"    {field.name}: Mapped[{validated_type}] = mapped_column({nullable_str})")

        fields_block = "\n".join(fields_code)

        imports_header = ""
        if extra_imports:
            imports_header = "\n".join(sorted(extra_imports)) + "\n"

        code = f"""{imports_header}from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class {ir.model_name}Model(Base):
{fields_block}
"""
        logger.info("sqlalchemy_orm_emitted", model_name=ir.model_name, table=table_name)
        return code