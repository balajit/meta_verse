from __future__ import annotations

import ast

import structlog

logger = structlog.get_logger(__name__)

class NonDeterministicPatternError(Exception):
    """Raised when non-deterministic code elements are found in workflows."""
    pass

class TemporalValidator(ast.NodeVisitor):
    FORBIDDEN_MODULES = {"time", "random", "uuid"}
    FORBIDDEN_FUNCTIONS = {"time", "randint", "uuid4"}

    def __init__(self) -> None:
        super().__init__()
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in self.FORBIDDEN_MODULES:
                self.violations.append(f"Forbidden module imported: {alias.name}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN_FUNCTIONS:
            self.violations.append(f"Non-deterministic function call: {node.func.id}")
        self.generic_visit(node)

    @classmethod
    def validate_code_string(cls, code: str) -> None:
        tree = ast.parse(code)
        validator = cls()
        validator.visit(tree)
        if validator.violations:
            logger.error("temporal_validation_failed", violations=validator.violations)
            raise NonDeterministicPatternError(f"Temporal validation failed: {validator.violations}")
        logger.info("temporal_validation_passed")