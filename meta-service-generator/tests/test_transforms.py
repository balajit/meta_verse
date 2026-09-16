from __future__ import annotations

import ast

import black
import libcst as cst
import pytest
from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.transforms.annotations import FutureAnnotationsTransformer
from meta_service_generator.transforms.cleanup import DeadCodeCleanupTransformer
from meta_service_generator.transforms.formatting import CodeFormattingGate
from meta_service_generator.transforms.imports import ImportOrganizerTransformer
from meta_service_generator.transforms.libcst_pipeline import LibCSTPipeline


# -----------------------------------------------------------------------------
# 1. Future Annotations Transformer Tests
# -----------------------------------------------------------------------------


def test_future_annotations_inserted_at_top():
    source = "x = 1\n"
    tree = cst.parse_module(source)
    transformed = tree.visit(FutureAnnotationsTransformer())
    assert transformed.code == "from __future__ import annotations\nx = 1\n"


def test_future_annotations_inserted_after_docstring():
    source = '"""Module docstring."""\nx = 1\n'
    tree = cst.parse_module(source)
    transformed = tree.visit(FutureAnnotationsTransformer())
    expected = '"""Module docstring."""\nfrom __future__ import annotations\nx = 1\n'
    assert transformed.code == expected


def test_future_annotations_already_present():
    source = "from __future__ import annotations\nx = 1\n"
    tree = cst.parse_module(source)
    transformed = tree.visit(FutureAnnotationsTransformer())
    assert transformed.code == source


# -----------------------------------------------------------------------------
# 2. Dead Code Cleanup Transformer Tests
# -----------------------------------------------------------------------------


def test_dead_code_cleanup_removes_standalone_pass():
    source = "def foo():\n    pass\n    return 42\n"
    tree = cst.parse_module(source)
    transformed = tree.visit(DeadCodeCleanupTransformer())
    assert transformed.code == "def foo():\n    return 42\n"


def test_dead_code_cleanup_preserves_single_pass():
    source = "def foo():\n    pass\n"
    tree = cst.parse_module(source)
    transformed = tree.visit(DeadCodeCleanupTransformer())
    assert transformed.code == source


# -----------------------------------------------------------------------------
# 3. Import Organizer Transformer Tests
# -----------------------------------------------------------------------------


def test_import_organizer_deduplicates_imports():
    source = "import os\nimport os\nfrom typing import Any\nfrom typing import Any\n"
    tree = cst.parse_module(source)
    transformed = tree.visit(ImportOrganizerTransformer())
    assert transformed.code == "import os\nfrom typing import Any\n"


# -----------------------------------------------------------------------------
# 4. Code Formatting Gate Tests
# -----------------------------------------------------------------------------


def test_formatting_gate_invalid_line_length():
    with pytest.raises(ValueError, match="line_length must be between 40 and 200"):
        CodeFormattingGate(line_length=10)


def test_formatting_gate_invalid_source_type():
    gate = CodeFormattingGate()
    with pytest.raises(CodeGenerationError) as exc_info:
        gate.format_code(123)  # type: ignore
    assert exc_info.value.error_code == "ERR_FORMATTING_SOURCE_TYPE"


def test_formatting_gate_syntax_error():
    gate = CodeFormattingGate()
    invalid_python = "def broken_func("
    with pytest.raises(CodeGenerationError) as exc_info:
        gate.format_code(invalid_python)
    assert exc_info.value.error_code == "ERR_FORMATTING_GATE_INVALID_SYNTAX"


def test_formatting_gate_success():
    gate = CodeFormattingGate()
    unformatted = "def foo(  a,  b ):    return a+b"
    formatted = gate.format_code(unformatted)
    assert "def foo(a, b):" in formatted

# -----------------------------------------------------------------------------
# Additional Code Formatting Gate Exception Handling Tests
# -----------------------------------------------------------------------------


def test_formatting_gate_black_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = CodeFormattingGate()

    def mock_format_str(src: str, mode: black.Mode) -> str:
        raise black.parsing.InvalidInput("Cannot parse input")

    monkeypatch.setattr(black, "format_str", mock_format_str)

    with pytest.raises(CodeGenerationError) as exc_info:
        gate.format_code("x = 1\n", filename="test_invalid_input.py")

    assert exc_info.value.error_code == "ERR_FORMATTING_BLACK_REJECTED"
    assert "Black rejected generated Python" in str(exc_info.value)


def test_formatting_gate_output_syntax_error(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = CodeFormattingGate()

    def mock_format_str(src: str, mode: black.Mode) -> str:
        return "class 123InvalidClass:\n    pass\n"

    monkeypatch.setattr(black, "format_str", mock_format_str)

    with pytest.raises(CodeGenerationError) as exc_info:
        gate.format_code("x = 1\n", filename="test_bad_output.py")

    assert exc_info.value.error_code == "ERR_FORMATTING_OUTPUT_INVALID"
    assert "Black produced syntactically invalid output" in str(exc_info.value)


def test_formatting_gate_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = CodeFormattingGate()

    def mock_format_str(src: str, mode: black.Mode) -> str:
        raise RuntimeError("Unexpected Black crash")

    monkeypatch.setattr(black, "format_str", mock_format_str)

    with pytest.raises(CodeGenerationError) as exc_info:
        gate.format_code("x = 1\n", filename="test_crash.py")

    assert exc_info.value.error_code == "ERR_FORMATTING_GATE_FAILED"
    assert "Failed to format generated file" in str(exc_info.value)

# -----------------------------------------------------------------------------
# 5. LibCST Pipeline Tests
# -----------------------------------------------------------------------------


def test_libcst_pipeline_invalid_source_type():
    pipeline = LibCSTPipeline()
    with pytest.raises(CodeGenerationError) as exc_info:
        pipeline.transform(None)  # type: ignore
    assert exc_info.value.error_code == "ERR_CST_SOURCE_TYPE"


def test_libcst_pipeline_parse_syntax_error():
    pipeline = LibCSTPipeline()
    bad_code = "class 123BadClassName:"
    with pytest.raises(CodeGenerationError) as exc_info:
        pipeline.transform(bad_code)
    assert exc_info.value.error_code == "ERR_CST_PARSING_FAILED"


def test_libcst_pipeline_full_transform_pass():
    pipeline = LibCSTPipeline()
    raw_code = '"""Doc."""\nimport os\nimport os\ndef test():\n    pass\n    return 1\n'
    transformed = pipeline.transform(raw_code, filename="test.py")

    assert "from __future__ import annotations" in transformed
    assert transformed.count("import os") == 1
    assert "pass" not in transformed
    ast.parse(transformed)

# -----------------------------------------------------------------------------
# Additional LibCST Pipeline Error Handling Tests
# -----------------------------------------------------------------------------


class BrokenSyntaxTransformer(cst.CSTTransformer):
    """Transformer that generates invalid Python code triggering SyntaxError on ast.parse()."""

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        # Construct an invalid CST node directly (e.g. invalid class identifier)
        invalid_class = cst.ClassDef(
            name=cst.Name("123InvalidClass"),
            body=cst.IndentedBlock(body=[cst.SimpleStatementLine(body=[cst.Pass()])]),
        )
        return updated_node.with_changes(body=[cst.SimpleStatementLine(body=[]), invalid_class])


class CodeGenErrorTransformer(cst.CSTTransformer):
    """Transformer that directly raises a CodeGenerationError."""

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        raise CodeGenerationError(
            message="Custom transformer failure",
            location="test.py",
            error_code="ERR_CUSTOM_TRANSFORMER",
        )


class GenericErrorTransformer(cst.CSTTransformer):
    """Transformer that raises an unexpected generic Exception."""

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        raise RuntimeError("Unexpected pipeline crash")


def test_libcst_pipeline_transformation_produces_invalid_syntax():
    pipeline = LibCSTPipeline(transformers=[BrokenSyntaxTransformer])
    with pytest.raises(CodeGenerationError) as exc_info:
        pipeline.transform("x = 1\n", filename="test_invalid.py")

    assert exc_info.value.error_code == "ERR_CST_OUTPUT_INVALID"
    assert "LibCST transformation produced invalid Python" in str(exc_info.value)


def test_libcst_pipeline_reraises_code_generation_error():
    pipeline = LibCSTPipeline(transformers=[CodeGenErrorTransformer])
    with pytest.raises(CodeGenerationError) as exc_info:
        pipeline.transform("x = 1\n")

    assert exc_info.value.error_code == "ERR_CUSTOM_TRANSFORMER"


def test_libcst_pipeline_generic_exception_handling():
    pipeline = LibCSTPipeline(transformers=[GenericErrorTransformer])
    with pytest.raises(CodeGenerationError) as exc_info:
        pipeline.transform("x = 1\n", filename="test_crash.py")

    assert exc_info.value.error_code == "ERR_CST_PIPELINE_ERROR"
    assert "AST transformation pipeline error" in str(exc_info.value)

