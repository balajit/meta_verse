from __future__ import annotations

import ast

import structlog

logger = structlog.get_logger(__name__)

ALLOWED_MODULES = {"pydantic", "typing", "sqlalchemy", "sqlalchemy.orm"}


class ASTBuilder:
    @staticmethod
    def create_class(name: str, bases: list[ast.expr], body: list[ast.stmt]) -> ast.ClassDef:
        logger.debug("ast_building_class", class_name=name, base_count=len(bases))
        return ast.ClassDef(
            name=name,
            bases=bases,
            keywords=[],
            body=body if body else [ast.Pass()],
            decorator_list=[]
        )

    @staticmethod
    def create_import(module_name: str, names: list[str]) -> ast.ImportFrom:
        if module_name not in ALLOWED_MODULES:
            raise SecurityError(f"Module '{module_name}' is not allowed for dynamic code generation.")

        return ast.ImportFrom(
            module=module_name,
            names=[ast.alias(name=n, asname=None) for n in names],
            level=0
        )


class SecurityError(Exception):
    """Raised when an unallowed module or unsafe expression is detected."""
    pass