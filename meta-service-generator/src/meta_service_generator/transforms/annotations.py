### file name: src/meta_service_generator/transforms/annotations.py

from __future__ import annotations

import libcst as cst
import libcst.matchers as m

from meta_telemetry import get_tracer, trace_span


tracer = get_tracer("meta_service_generator.transforms.annotations")


class FutureAnnotationsTransformer(cst.CSTTransformer):
    """
    LibCST Transformer that inserts `from __future__ import annotations` as the first
    statement of a module, placing it after module docstrings.
    """

    @trace_span("transforms.annotations.visit_Module")
    def leave_Module(
        self,
        original_node: cst.Module,
        updated_node: cst.Module,
    ) -> cst.Module:
        for statement in updated_node.body:
            if m.matches(
                statement,
                m.SimpleStatementLine(
                    body=[
                        m.ImportFrom(
                            module=m.Name("__future__"),
                            names=[
                                m.ImportAlias(
                                    name=m.Name("annotations")
                                )
                            ],
                        )
                    ]
                ),
            ):
                return updated_node

        future_stmt = cst.SimpleStatementLine(
            body=[
                cst.ImportFrom(
                    module=cst.Name("__future__"),
                    names=[
                        cst.ImportAlias(
                            name=cst.Name("annotations")
                        )
                    ],
                )
            ]
        )

        new_body = list(updated_node.body)

        if new_body and m.matches(
            new_body[0],
            m.SimpleStatementLine(
                body=[
                    m.Expr(
                        value=m.SimpleString()
                        | m.ConcatenatedString()
                    )
                ]
            ),
        ):
            new_body.insert(1, future_stmt)
        else:
            new_body.insert(0, future_stmt)

        return updated_node.with_changes(
            body=new_body
        )