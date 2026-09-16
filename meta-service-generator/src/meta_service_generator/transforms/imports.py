from __future__ import annotations

import libcst as cst

from meta_telemetry import get_tracer, trace_span


tracer = get_tracer("meta_service_generator.transforms.imports")


class ImportOrganizerTransformer(cst.CSTTransformer):
    """
    Semantics-preserving import deduplication.

    Import ordering is intentionally delegated to Ruff.
    """

    @staticmethod
    def _import_key(
        import_node: cst.Import | cst.ImportFrom,
    ) -> str:
        return cst.Module(
            body=[
                cst.SimpleStatementLine(
                    body=[import_node],
                )
            ]
        ).code.strip()

    @trace_span("transforms.imports.visit_Module")
    def leave_Module(
        self,
        original_node: cst.Module,
        updated_node: cst.Module,
    ) -> cst.Module:
        seen: set[str] = set()
        new_body: list[cst.BaseStatement] = []

        for statement in updated_node.body:
            if not isinstance(statement, cst.SimpleStatementLine):
                new_body.append(statement)
                continue

            rebuilt: list[cst.BaseSmallStatement] = []

            for element in statement.body:
                if not isinstance(
                    element,
                    (cst.Import, cst.ImportFrom),
                ):
                    rebuilt.append(element)
                    continue

                key = self._import_key(element)

                if key in seen:
                    continue

                seen.add(key)
                rebuilt.append(element)

            if rebuilt:
                new_body.append(
                    statement.with_changes(body=rebuilt)
                )

        return updated_node.with_changes(body=new_body)

class ImportDeduplicationTransformer(cst.CSTTransformer):
    """
    Remove duplicate imports without changing statement ordering.

    Import movement is intentionally forbidden because imports can have
    observable execution side effects.
    """

    @staticmethod
    def _key(
        node: cst.Import | cst.ImportFrom,
    ) -> str:
        return cst.Module(
            body=[
                cst.SimpleStatementLine(body=[node]),
            ]
        ).code.strip()

    @trace_span("transforms.imports.visit_Module")
    def leave_Module(
        self,
        original_node: cst.Module,
        updated_node: cst.Module,
    ) -> cst.Module:
        seen: set[str] = set()
        body: list[cst.BaseStatement] = []

        for statement in updated_node.body:
            if not isinstance(statement, cst.SimpleStatementLine):
                body.append(statement)
                continue

            new_small_statements: list[cst.BaseSmallStatement] = []

            for small_statement in statement.body:
                if isinstance(
                    small_statement,
                    (cst.Import, cst.ImportFrom),
                ):
                    key = self._key(small_statement)

                    if key in seen:
                        continue

                    seen.add(key)

                new_small_statements.append(small_statement)

            if new_small_statements:
                body.append(
                    statement.with_changes(
                        body=tuple(new_small_statements)
                    )
                )

        return updated_node.with_changes(body=tuple(body))