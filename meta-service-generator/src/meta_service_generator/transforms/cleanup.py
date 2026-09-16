### file name: src/meta_service_generator/transforms/cleanup.py

from __future__ import annotations

import libcst as cst

from meta_telemetry import get_tracer, trace_span


tracer = get_tracer("meta_service_generator.transforms.cleanup")


class DeadCodeCleanupTransformer(cst.CSTTransformer):
    """
    LibCST Transformer that cleans up redundant statements and pass-throughs.
    """

    @staticmethod
    def _is_standalone_pass(
        statement: cst.BaseStatement,
    ) -> bool:
        return (
            isinstance(statement, cst.SimpleStatementLine)
            and len(statement.body) == 1
            and isinstance(statement.body[0], cst.Pass)
        )

    @trace_span("transforms.cleanup.leave_IndentedBlock")
    def leave_IndentedBlock(
        self,
        original_node: cst.IndentedBlock,
        updated_node: cst.IndentedBlock,
    ) -> cst.IndentedBlock:
        statements = list(updated_node.body)

        if len(statements) <= 1:
            return updated_node

        filtered_statements = [
            statement
            for statement in statements
            if not self._is_standalone_pass(statement)
        ]

        if not filtered_statements:
            return updated_node

        return updated_node.with_changes(
            body=filtered_statements
        )