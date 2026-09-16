from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.generation.artifacts import Artifact, ArtifactWriter
from meta_service_generator.generation.context import GenerationContext
from meta_service_generator.generation.dto import DTOAttributeContext, DTOGenerator, DTOSpecContext
from meta_service_generator.generation.manifest_report import BuildManifest, ManifestReportGenerator
from meta_service_generator.generation.pipeline import CodeGenerationPipeline
from meta_service_generator.generation.renderer import TemplateRenderer
from meta_service_generator.ir.model import IRField, IRModel, IRRule, IRWorkflow, ServiceIR, IRFSM


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_field_pk():
    return IRField(
        name="id",
        original_name="id",
        python_type="int",
        sql_type="INTEGER",
        is_nullable=False,
        is_primary_key=True,
    )


@pytest.fixture
def mock_field_name():
    return IRField(
        name="name",
        original_name="name",
        python_type="str",
        sql_type="VARCHAR(255)",
        is_nullable=False,
        is_primary_key=False,
    )


@pytest.fixture
def mock_field_optional():
    return IRField(
        name="description",
        original_name="description",
        python_type="str",
        sql_type="TEXT",
        is_nullable=True,
        is_primary_key=False,
    )


@pytest.fixture
def mock_model(mock_field_pk, mock_field_name, mock_field_optional):
    return IRModel(
        name="User",
        class_name="User",
        table_name="users",
        fields=(mock_field_pk, mock_field_name, mock_field_optional),
        fsm=None,
    )


@pytest.fixture
def mock_service_ir(mock_model):
    return ServiceIR(
        service_name="user_service",
        version="1.0.0",
        models=(mock_model,),
        rules=(),
        workflows=(),
        policies=(),
    )


# -----------------------------------------------------------------------------
# 1. Artifacts & ArtifactWriter Tests
# -----------------------------------------------------------------------------


def test_artifact_writer_init_success(tmp_path: Path):
    target_dir = tmp_path / "artifacts"
    writer = ArtifactWriter(target_dir)
    assert writer.target_dir == target_dir.resolve()
    assert target_dir.is_dir()


def test_artifact_writer_init_target_is_file(tmp_path: Path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("content")

    with pytest.raises(CodeGenerationError) as exc_info:
        ArtifactWriter(file_path)
    assert exc_info.value.error_code == "ERR_ARTIFACT_TARGET_NOT_DIRECTORY"


def test_artifact_writer_init_os_error(tmp_path: Path):
    with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
        with pytest.raises(CodeGenerationError) as exc_info:
            ArtifactWriter(tmp_path / "nested")
        assert exc_info.value.error_code == "ERR_ARTIFACT_TARGET_INITIALIZATION_FAILED"


def test_write_artifact_success(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    artifact = writer.write_artifact("test.txt", "hello world", is_executable=True)

    assert artifact.relative_path == "test.txt"
    assert artifact.size_bytes == 11
    assert artifact.is_executable is True
    assert (tmp_path / "test.txt").read_text() == "hello world"


def test_write_artifact_invalid_content_type(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    with pytest.raises(CodeGenerationError) as exc_info:
        writer.write_artifact("test.txt", 123)  # type: ignore
    assert exc_info.value.error_code == "ERR_ARTIFACT_CONTENT_TYPE"


def test_write_artifact_absolute_path(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    abs_path = (tmp_path / "test.txt").resolve()
    with pytest.raises(CodeGenerationError) as exc_info:
        writer.write_artifact(str(abs_path), "content")
    assert exc_info.value.error_code == "ERR_ARTIFACT_ABSOLUTE_PATH"


def test_write_artifact_empty_path(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    with pytest.raises(CodeGenerationError) as exc_info:
        writer.write_artifact(".", "content")
    assert exc_info.value.error_code == "ERR_ARTIFACT_EMPTY_PATH"


def test_write_artifact_path_traversal(tmp_path: Path):
    writer = ArtifactWriter(tmp_path / "subdir")
    with pytest.raises(CodeGenerationError) as exc_info:
        writer.write_artifact("../outside.txt", "content")
    assert exc_info.value.error_code == "ERR_ARTIFACT_PATH_TRAVERSAL"


def test_write_artifact_symlink_destination(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    target_file = tmp_path / "real.txt"
    target_file.write_text("real")

    with patch.object(Path, "is_symlink", return_value=True):
        with pytest.raises(CodeGenerationError) as exc_info:
            writer.write_artifact("real.txt", "content")
        assert exc_info.value.error_code == "ERR_ARTIFACT_SYMLINK_DESTINATION"


def test_write_artifact_symlink_parent(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()

    def mock_is_symlink(self_path):
        return self_path == sub_dir.resolve()

    with patch.object(Path, "is_symlink", side_effect=mock_is_symlink, autospec=True):
        with pytest.raises(CodeGenerationError) as exc_info:
            writer.write_artifact("subdir/file.txt", "content")
        assert exc_info.value.error_code == "ERR_ARTIFACT_SYMLINK_PARENT"

# -----------------------------------------------------------------------------
# ArtifactWriter Additional Coverage Tests
# -----------------------------------------------------------------------------

def test_artifact_writer_directory_fsync_error(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    with patch("os.fsync", side_effect=[None, OSError("fsync not supported")]):
        artifact = writer.write_artifact("test.py", "print('hello')")
        assert artifact.relative_path == "test.py"


def test_artifact_writer_temp_unlink_error(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    with patch("tempfile.NamedTemporaryFile", side_effect=OSError("Disk error")):
        with pytest.raises(CodeGenerationError) as exc_info:
            writer.write_artifact("test.py", "content")
        assert exc_info.value.error_code == "ERR_ARTIFACT_WRITE_FAILED"

    # Force an OSError during replace to enter the finally block,
    # and have unlink also raise an OSError during cleanup.
    original_replace = Path.replace
    original_unlink = Path.unlink

    def mock_replace(self, target):
        if ".tmp" in self.name:
            raise OSError("Replace failed")
        return original_replace(self, target)

    def mock_unlink(self, missing_ok=False):
        if ".tmp" in self.name:
            raise OSError("Unlink failed")
        return original_unlink(self, missing_ok=missing_ok)

    with patch.object(Path, "replace", mock_replace), \
         patch.object(Path, "unlink", mock_unlink):
        with pytest.raises(CodeGenerationError) as exc_info:
            writer.write_artifact("test.py", "content")
        assert exc_info.value.error_code == "ERR_ARTIFACT_WRITE_FAILED"


def test_artifact_writer_unicode_encode_error(tmp_path: Path):
    writer = ArtifactWriter(tmp_path)

    class BadString(str):
        def encode(self, encoding="utf-8", errors="strict"):
            raise UnicodeEncodeError("utf-8", "", 0, 1, "forced encoding error")

    with pytest.raises(CodeGenerationError) as exc_info:
        writer.write_artifact("test.py", BadString("content"))  # type: ignore
    assert exc_info.value.error_code == "ERR_ARTIFACT_ENCODING_FAILED"

# -----------------------------------------------------------------------------
# 2. Context Tests
# -----------------------------------------------------------------------------


def test_generation_context_from_service_ir(mock_service_ir):
    ctx = GenerationContext.from_service_ir(mock_service_ir)
    assert ctx.service_name == "user_service"
    assert ctx.version == "1.0.0"
    assert len(ctx.models) == 1
    assert ctx.has_fsms is False
    assert ctx.has_rules is False
    assert ctx.model_map["User"] == mock_service_ir.models[0]


def test_generation_context_from_invalid_type():
    with pytest.raises(TypeError, match="service_ir must be a ServiceIR instance"):
        GenerationContext.from_service_ir("invalid")  # type: ignore


def test_generation_context_as_template_context(mock_service_ir):
    ctx = GenerationContext.from_service_ir(mock_service_ir)
    tmpl_ctx = ctx.as_template_context()
    assert tmpl_ctx["service_name"] == "user_service"
    assert "model_map" in tmpl_ctx

# -----------------------------------------------------------------------------
# Manifest Report Additional Tests
# -----------------------------------------------------------------------------


def test_generate_manifest_type_errors(mock_service_ir, tmp_path: Path):
    reporter = ManifestReportGenerator()

    with pytest.raises(TypeError, match="service_ir must be a ServiceIR instance"):
        reporter.generate_manifest("invalid_ir", [], tmp_path)  # type: ignore

    with pytest.raises(TypeError, match="target_dir must be a pathlib.Path"):
        reporter.generate_manifest(mock_service_ir, [], "invalid_path")  # type: ignore


def test_generate_manifest_exception_handling(mock_service_ir, tmp_path: Path):
    reporter = ManifestReportGenerator()
    with patch(
        "meta_service_generator.generation.manifest_report.ArtifactWriter",
        side_effect=RuntimeError("Disk I/O error"),
    ):
        with pytest.raises(CodeGenerationError) as exc_info:
            reporter.generate_manifest(mock_service_ir, [], tmp_path)

        assert exc_info.value.error_code == "ERR_MANIFEST_GENERATION_FAILED"


def test_generate_markdown_report_type_errors(mock_service_ir, tmp_path: Path):
    reporter = ManifestReportGenerator()

    with pytest.raises(TypeError, match="service_ir must be a ServiceIR instance"):
        reporter.generate_markdown_report("invalid_ir", [], tmp_path)  # type: ignore

    with pytest.raises(TypeError, match="target_dir must be a pathlib.Path"):
        reporter.generate_markdown_report(mock_service_ir, [], "invalid_path")  # type: ignore


def test_generate_markdown_report_exception_handling(mock_service_ir, tmp_path: Path):
    reporter = ManifestReportGenerator()
    with patch(
        "meta_service_generator.generation.manifest_report.ArtifactWriter",
        side_effect=RuntimeError("Write failure"),
    ):
        with pytest.raises(CodeGenerationError) as exc_info:
            reporter.generate_markdown_report(mock_service_ir, [], tmp_path)

        assert exc_info.value.error_code == "ERR_BUILD_REPORT_GENERATION_FAILED"

# -----------------------------------------------------------------------------
# 3. DTO Generator Tests
# -----------------------------------------------------------------------------


def test_dto_generator_build_specs(mock_model):
    generator = DTOGenerator()
    spec = generator.build_dto_specs(mock_model)

    assert isinstance(spec, DTOSpecContext)
    assert spec.model_name == "User"
    assert len(spec.create_fields) == 2
    assert len(spec.update_fields) == 2
    assert len(spec.search_fields) == 2
    assert len(spec.response_fields) == 3


def test_dto_generator_invalid_type():
    generator = DTOGenerator()
    with pytest.raises(TypeError, match="model must be IRModel"):
        generator.build_dto_specs("invalid")  # type: ignore


# -----------------------------------------------------------------------------
# 4. Renderer Tests
# -----------------------------------------------------------------------------


def test_template_renderer_custom_directory_not_found(tmp_path: Path):
    invalid_dir = tmp_path / "non_existent"
    with pytest.raises(CodeGenerationError) as exc_info:
        TemplateRenderer(template_dir=invalid_dir)
    assert exc_info.value.error_code == "ERR_TEMPLATE_DIR_NOT_FOUND"


def test_template_renderer_python_literal():
    assert TemplateRenderer._python_literal("hello") == '"hello"'
    assert TemplateRenderer._python_literal(True) == "True"
    assert TemplateRenderer._python_literal(False) == "False"
    assert TemplateRenderer._python_literal(None) == "None"
    assert TemplateRenderer._python_literal(42) == "42"

    with pytest.raises(TypeError):
        TemplateRenderer._python_literal(object())


def test_template_renderer_render_validation():
    renderer = TemplateRenderer()

    with pytest.raises(CodeGenerationError) as exc1:
        renderer.render("", {})
    assert exc1.value.error_code == "ERR_TEMPLATE_NAME_INVALID"

    with pytest.raises(CodeGenerationError) as exc2:
        renderer.render("test.jinja2", "invalid_context")  # type: ignore
    assert exc2.value.error_code == "ERR_TEMPLATE_CONTEXT_INVALID"


def test_template_renderer_template_not_found():
    renderer = TemplateRenderer()
    with pytest.raises(CodeGenerationError) as exc_info:
        renderer.render("non_existent_template.jinja2", {})
    assert exc_info.value.error_code == "ERR_TEMPLATE_NOT_FOUND"


# -----------------------------------------------------------------------------
# 5. Manifest Report Tests
# -----------------------------------------------------------------------------


def test_manifest_report_generator_manifest(mock_service_ir, tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    art1 = writer.write_artifact("a.txt", "hello")
    art2 = writer.write_artifact("b.txt", "world")

    reporter = ManifestReportGenerator()
    manifest_art = reporter.generate_manifest(mock_service_ir, (art2, art1), tmp_path)

    assert manifest_art.relative_path == "build_manifest.json"
    manifest_data = json.loads((tmp_path / "build_manifest.json").read_text())
    assert manifest_data["service_name"] == "user_service"
    assert manifest_data["total_artifacts"] == 2


def test_manifest_report_generator_markdown(mock_service_ir, tmp_path: Path):
    writer = ArtifactWriter(tmp_path)
    art = writer.write_artifact("a.txt", "hello")

    reporter = ManifestReportGenerator()
    report_art = reporter.generate_markdown_report(mock_service_ir, (art,), tmp_path)

    assert report_art.relative_path == "BUILD_REPORT.md"
    report_content = (tmp_path / "BUILD_REPORT.md").read_text()
    assert "# Service Synthesis Report: user_service" in report_content


# -----------------------------------------------------------------------------
# 6. Pipeline Execution & Rollback Tests
# -----------------------------------------------------------------------------


def test_pipeline_invalid_inputs(tmp_path: Path, mock_service_ir):
    pipeline = CodeGenerationPipeline()

    with pytest.raises(CodeGenerationError) as exc1:
        pipeline.execute("invalid", tmp_path)  # type: ignore
    assert exc1.value.error_code == "ERR_GENERATION_INVALID_IR"

    with pytest.raises(CodeGenerationError) as exc2:
        pipeline.execute(mock_service_ir, "invalid")  # type: ignore
    assert exc2.value.error_code == "ERR_GENERATION_INVALID_TARGET"


def test_pipeline_execution_success(mock_service_ir, tmp_path: Path):
    mock_renderer = MagicMock(spec=TemplateRenderer)
    mock_renderer.render.return_value = "print('generated code')\n"

    mock_cst = MagicMock()
    mock_cst.transform.side_effect = lambda source_code, filename: source_code

    mock_formatter = MagicMock()
    mock_formatter.format_code.side_effect = lambda source_code, filename: source_code

    pipeline = CodeGenerationPipeline(
        renderer=mock_renderer,
        cst_pipeline=mock_cst,
        formatting_gate=mock_formatter,
    )

    out_paths = pipeline.execute(mock_service_ir, tmp_path / "output")
    assert len(out_paths) > 0
    assert (tmp_path / "output" / "build_manifest.json").exists()


def test_pipeline_intermediate_stage_failure(mock_service_ir, tmp_path: Path):
    mock_renderer = MagicMock(spec=TemplateRenderer)
    mock_renderer.render.side_effect = RuntimeError("Rendering exception")

    pipeline = CodeGenerationPipeline(renderer=mock_renderer)

    with pytest.raises(CodeGenerationError) as exc_info:
        pipeline.execute(mock_service_ir, tmp_path / "failed_output")

    assert exc_info.value.error_code == "ERR_GENERATION_PIPELINE_FAILED"


# -----------------------------------------------------------------------------
# Code Generation Pipeline Additional Tests
# -----------------------------------------------------------------------------

def test_pipeline_execution_with_rules_workflows_fsms(tmp_path: Path):
    # Setup IR model with valid IRFSM instance, Rules, and Workflows
    fsm_instance = IRFSM(
        state_attribute="status",
        initial_state="pending",
        states=("pending", "completed"),
        transitions=(),
    )
    model_with_fsm = IRModel(
        name="Order",
        class_name="Order",
        table_name="orders",
        fields=(),
        fsm=fsm_instance,
    )
    rule = IRRule(
        name="validate_order",
        target_entity="Order",
        expression="amount > 0",
        error_message="Invalid amount",
    )
    workflow = IRWorkflow(
        name="checkout",
        steps=(),
    )
    service_ir = ServiceIR(
        service_name="order_service",
        version="1.0.0",
        models=(model_with_fsm,),
        rules=(rule,),
        workflows=(workflow,),
        policies=(),
    )

    mock_renderer = MagicMock(spec=TemplateRenderer)
    mock_renderer.render.return_value = "print('rendered')\n"

    mock_cst = MagicMock()
    mock_cst.transform.side_effect = lambda source_code, filename: source_code

    mock_formatter = MagicMock()
    mock_formatter.format_code.side_effect = lambda source_code, filename: source_code

    pipeline = CodeGenerationPipeline(
        renderer=mock_renderer,
        cst_pipeline=mock_cst,
        formatting_gate=mock_formatter,
    )

    out_paths = pipeline.execute(service_ir, tmp_path / "full_service")
    assert len(out_paths) > 0
    assert (tmp_path / "full_service" / "execution" / "order_rules.py").exists()
    assert (tmp_path / "full_service" / "execution" / "checkout_workflow.py").exists()
    assert (tmp_path / "full_service" / "execution" / "order_fsm.py").exists()
    assert (tmp_path / "full_service" / "tests" / "test_fsm.py").exists()
    assert (tmp_path / "full_service" / "tests" / "test_workflows.py").exists()


def test_pipeline_os_error_handling(mock_service_ir, tmp_path: Path):
    pipeline = CodeGenerationPipeline()
    with patch.object(Path, "mkdir", side_effect=OSError("Read-only file system")):
        with pytest.raises(CodeGenerationError) as exc_info:
            pipeline.execute(mock_service_ir, tmp_path / "readonly")

        assert exc_info.value.error_code == "ERR_GENERATION_FILESYSTEM_FAILED"


def test_pipeline_ensure_directory_target_is_file(tmp_path: Path):
    file_path = tmp_path / "not_a_dir"
    file_path.write_text("content")

    with pytest.raises(CodeGenerationError) as exc_info:
        CodeGenerationPipeline._ensure_directory(file_path)

    assert exc_info.value.error_code == "ERR_GENERATION_PATH_NOT_DIRECTORY"


def test_pipeline_relative_to_target_escape(tmp_path: Path):
    target_dir = tmp_path / "target"
    outside_file = tmp_path / "outside" / "file.py"

    with pytest.raises(CodeGenerationError) as exc_info:
        CodeGenerationPipeline._relative_to_target(outside_file, target_dir)

    assert exc_info.value.error_code == "ERR_GENERATION_PATH_ESCAPE"


# -----------------------------------------------------------------------------
# Template Renderer Additional Tests
# -----------------------------------------------------------------------------


def test_renderer_package_loader_failure():
    with patch(
        "jinja2.PackageLoader",
        side_effect=ImportError("Package not found"),
    ):
        with pytest.raises(CodeGenerationError) as exc_info:
            TemplateRenderer()

        assert exc_info.value.error_code == "ERR_PACKAGE_TEMPLATE_LOADER_FAILED"


def test_renderer_with_custom_template_dir(tmp_path: Path):
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "custom.jinja2").write_text("Hello {{ name }}!")

    renderer = TemplateRenderer(template_dir=tpl_dir)
    result = renderer.render("custom.jinja2", {"name": "World"})
    assert result == "Hello World!"


def test_renderer_mapped_template_resolution():
    renderer = TemplateRenderer()
    assert renderer.resolve_template_name("main.py.jinja2") == "project/main.py.jinja2"


def test_renderer_syntax_error(tmp_path: Path):
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "bad_syntax.jinja2").write_text("{% if true %} Missing end %}")

    renderer = TemplateRenderer(template_dir=tpl_dir)
    with pytest.raises(CodeGenerationError) as exc_info:
        renderer.render("bad_syntax.jinja2", {})

    assert exc_info.value.error_code == "ERR_TEMPLATE_SYNTAX_ERROR"


def test_renderer_undefined_variable(tmp_path: Path):
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "undefined.jinja2").write_text("Hello {{ missing_var }}!")

    renderer = TemplateRenderer(template_dir=tpl_dir)
    with pytest.raises(CodeGenerationError) as exc_info:
        renderer.render("undefined.jinja2", {})

    assert exc_info.value.error_code == "ERR_TEMPLATE_UNDEFINED_VARIABLE"


def test_renderer_generic_render_exception(tmp_path: Path):
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    # Division by zero causes a runtime exception during evaluation rather than an undefined variable
    (tpl_dir / "error.jinja2").write_text("Hello {{ 1 / 0 }}!")

    renderer = TemplateRenderer(template_dir=tpl_dir)
    with pytest.raises(CodeGenerationError) as exc_info:
        renderer.render("error.jinja2", {})

    assert exc_info.value.error_code == "ERR_TEMPLATE_RENDER_FAILED"


def test_renderer_empty_output(tmp_path: Path):
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "empty.jinja2").write_text("   \n\n  ")

    renderer = TemplateRenderer(template_dir=tpl_dir)
    with pytest.raises(CodeGenerationError) as exc_info:
        renderer.render("empty.jinja2", {})

    assert exc_info.value.error_code == "ERR_TEMPLATE_EMPTY_OUTPUT"