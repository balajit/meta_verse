from __future__ import annotations

from pathlib import Path
from typing import Mapping

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.generation.artifacts import (
    Artifact,
    ArtifactWriter,
)
from meta_service_generator.generation.context import (
    GenerationContext,
)
from meta_service_generator.generation.dto import DTOGenerator
from meta_service_generator.generation.manifest_report import (
    ManifestReportGenerator,
)
from meta_service_generator.generation.orm_validator import (
    validate_relationship_graph,
)
from meta_service_generator.generation.renderer import (
    TemplateRenderer,
)
from meta_service_generator.ir.model import (
    IRModel,
    ServiceIR,
)
from meta_service_generator.ir.names import to_snake_case
from meta_service_generator.local_telemetry import get_logger
from meta_service_generator.transforms.formatting import (
    CodeFormattingGate,
)
from meta_service_generator.transforms.libcst_pipeline import (
    LibCSTPipeline,
)
from meta_telemetry import get_tracer, trace_span


logger = get_logger(
    "meta_service_generator.generation.pipeline"
)

tracer = get_tracer(
    "meta_service_generator.generation.pipeline"
)


class CodeGenerationPipeline:
    """
    Orchestrates end-to-end code synthesis utilizing all package Jinja2 templates.
    """

    def __init__(
        self,
        renderer: TemplateRenderer | None = None,
        dto_generator: DTOGenerator | None = None,
        cst_pipeline: LibCSTPipeline | None = None,
        formatting_gate: CodeFormattingGate | None = None,
        manifest_reporter: ManifestReportGenerator | None = None,
    ) -> None:
        self.renderer = (
            renderer
            if renderer is not None
            else TemplateRenderer()
        )

        self.dto_generator = (
            dto_generator
            if dto_generator is not None
            else DTOGenerator()
        )

        self.cst_pipeline = (
            cst_pipeline
            if cst_pipeline is not None
            else LibCSTPipeline()
        )

        self.formatting_gate = (
            formatting_gate
            if formatting_gate is not None
            else CodeFormattingGate()
        )

        self.manifest_reporter = (
            manifest_reporter
            if manifest_reporter is not None
            else ManifestReportGenerator()
        )

    @trace_span("generation.pipeline.execute")
    def execute(
        self,
        service_ir: ServiceIR,
        target_dir: Path,
    ) -> list[Path]:
        """
        Executes complete code synthesis rendering all templates and returning emitted artifact paths.
        """
        if not isinstance(service_ir, ServiceIR):
            raise CodeGenerationError(
                message=(
                    f"service_ir must be ServiceIR, got "
                    f"{type(service_ir).__name__}."
                ),
                location="service_ir",
                error_code="ERR_GENERATION_INVALID_IR",
                suggested_resolution=(
                    "Pass a validated immutable ServiceIR instance."
                ),
            )

        if not isinstance(target_dir, Path):
            raise CodeGenerationError(
                message=(
                    f"target_dir must be pathlib.Path, got "
                    f"{type(target_dir).__name__}."
                ),
                location="target_dir",
                error_code="ERR_GENERATION_INVALID_TARGET",
                suggested_resolution=(
                    "Pass the generated service target as pathlib.Path."
                ),
            )

        try:
            target_dir = target_dir.expanduser().resolve()

            self._validate_generation_input(service_ir)

            generation_context = (
                GenerationContext.from_service_ir(service_ir)
            )

            package_name = generation_context.package_name

            # GenerationContext is the canonical source for all template
            # context. In particular, package_name MUST be used for Python
            # imports and filesystem package paths; service_name remains the
            # externally visible service identity.
            template_context = dict(
                generation_context.as_template_context()
            )

            target_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            writer = ArtifactWriter(target_dir)
            emitted_artifacts: list[Artifact] = []

            pkg_rel_dir = Path("src") / package_name
            pkg_abs_dir = target_dir / pkg_rel_dir

            logger.info(
                "Starting code generation pipeline.",
                extra={
                    "event_type": "generation_started",
                    "service_name": service_ir.service_name,
                    "package_name": package_name,
                    "target_dir": str(target_dir),
                    "model_count": len(generation_context.models),
                },
            )

            package_dirs = (
                pkg_abs_dir,
                pkg_abs_dir / "models",
                pkg_abs_dir / "repositories",
                pkg_abs_dir / "service",
                pkg_abs_dir / "routers",
                pkg_abs_dir / "execution",
                pkg_abs_dir / "extensions",
                target_dir / "tests",
            )

            for directory in package_dirs:
                self._ensure_directory(directory)

                emitted_artifacts.append(
                    writer.write_artifact(
                        self._relative_to_target(
                            directory / "__init__.py",
                            target_dir,
                        ),
                        '"""Generated package module."""\n',
                    )
                )

            emitted_artifacts.extend(
                self._generate_core_artifacts(
                    service_ir=service_ir,
                    generation_context=generation_context,
                    template_context=template_context,
                    writer=writer,
                    pkg_rel_dir=pkg_rel_dir,
                )
            )

            for model in generation_context.models:
                emitted_artifacts.extend(
                    self._generate_model(
                        model=model,
                        service_name=service_ir.service_name,
                        package_name=package_name,
                        writer=writer,
                        pkg_rel_dir=pkg_rel_dir,
                        base_context=template_context,
                    )
                )

            emitted_artifacts.extend(
                self._generate_rule_artifacts(
                    service_ir=service_ir,
                    generation_context=generation_context,
                    writer=writer,
                    pkg_rel_dir=pkg_rel_dir,
                    base_context=template_context,
                )
            )

            emitted_artifacts.extend(
                self._generate_workflow_artifacts(
                    service_ir=service_ir,
                    generation_context=generation_context,
                    writer=writer,
                    pkg_rel_dir=pkg_rel_dir,
                    base_context=template_context,
                )
            )

            emitted_artifacts.extend(
                self._generate_test_artifacts(
                    service_ir=service_ir,
                    generation_context=generation_context,
                    writer=writer,
                    base_context=template_context,
                )
            )

            manifest_artifact = (
                self.manifest_reporter.generate_manifest(
                    service_ir=service_ir,
                    artifacts=tuple(emitted_artifacts),
                    target_dir=target_dir,
                    writer=writer,
                )
            )
            emitted_artifacts.append(manifest_artifact)

            report_artifact = (
                self.manifest_reporter.generate_markdown_report(
                    service_ir=service_ir,
                    artifacts=tuple(emitted_artifacts),
                    target_dir=target_dir,
                    writer=writer,
                )
            )
            emitted_artifacts.append(report_artifact)

            logger.info(
                "Code generation pipeline completed successfully.",
                extra={
                    "event_type": "generation_completed",
                    "service_name": service_ir.service_name,
                    "package_name": package_name,
                    "artifact_count": len(emitted_artifacts),
                    "target_dir": str(target_dir),
                },
            )

            return [
                Path(artifact.absolute_path)
                for artifact in emitted_artifacts
            ]

        except CodeGenerationError:
            logger.exception(
                "Code generation failed with a domain error.",
                extra={
                    "event_type": "generation_failed",
                    "service_name": service_ir.service_name,
                    "target_dir": str(target_dir),
                },
            )
            raise

        except OSError as err:
            raise CodeGenerationError(
                message=(
                    f"Code generation filesystem operation failed: "
                    f"{err}"
                ),
                location=str(target_dir),
                error_code="ERR_GENERATION_FILESYSTEM_FAILED",
                suggested_resolution=(
                    "Verify target directory permissions and filesystem capacity."
                ),
            ) from err

        except Exception as err:
            raise CodeGenerationError(
                message=f"Code generation pipeline failed: {err}",
                location=str(target_dir),
                error_code="ERR_GENERATION_PIPELINE_FAILED",
                suggested_resolution=(
                    "Inspect ServiceIR, template output, transformations, "
                    "and target-directory permissions."
                ),
            ) from err

    def _generate_core_artifacts(
        self,
        *,
        service_ir: ServiceIR,
        generation_context: GenerationContext,
        template_context: Mapping[str, object],
        writer: ArtifactWriter,
        pkg_rel_dir: Path,
    ) -> tuple[Artifact, ...]:
        artifacts: list[Artifact] = []

        core_templates = (
            (
                pkg_rel_dir / "exceptions.py",
                "project/exceptions.py.jinja2",
            ),
            (
                pkg_rel_dir / "extensions" / "config.py",
                "extensions/config.py.jinja2",
            ),
            (
                pkg_rel_dir / "extensions" / "policy.py",
                "extensions/policy.py.jinja2",
            ),
            (
                pkg_rel_dir / "extensions" / "telemetry.py",
                "extensions/telemetry.py.jinja2",
            ),
            (
                pkg_rel_dir / "models" / "base.py",
                "models/base.py.jinja2",
            ),
            (
                pkg_rel_dir / "database.py",
                "database.py.jinja2",
            ),
            (
                pkg_rel_dir / "main.py",
                "project/main.py.jinja2",
            ),
        )

        for relative_path, template_name in core_templates:
            artifacts.append(
                self._generate_source_artifact(
                    writer=writer,
                    relative_path=relative_path,
                    template_name=template_name,
                    context=template_context,
                )
            )

        artifacts.append(
            self._generate_plain_artifact(
                writer=writer,
                relative_path=Path("pyproject.toml"),
                template_name="project/pyproject.toml.jinja2",
                context=template_context,
            )
        )

        artifacts.append(
            self._generate_plain_artifact(
                writer=writer,
                relative_path=Path(".env"),
                template_name="project/.env.jinja2",
                context=template_context,
            )
        )

        return tuple(artifacts)

    def _generate_model(
        self,
        *,
        model: IRModel,
        service_name: str,
        package_name: str,
        writer: ArtifactWriter,
        pkg_rel_dir: Path,
        base_context: Mapping[str, object],
    ) -> tuple[Artifact, ...]:
        if not isinstance(model, IRModel):
            raise CodeGenerationError(
                message=(
                    f"model must be IRModel, got "
                    f"{type(model).__name__}."
                ),
                location="model",
                error_code="ERR_GENERATION_MODEL_INVALID",
                suggested_resolution=(
                    "Pass an IRModel from GenerationContext.models."
                ),
            )

        model_context = dict(base_context)
        model_context.update(
            {
                "model": model,
                "service_name": service_name,
                "package_name": package_name,
            }
        )

        model_module_name = to_snake_case(model.name)

        dto_spec = self.dto_generator.build_dto_specs(model)

        dto_context = dict(base_context)
        dto_context.update(
            {
                "dto": dto_spec,
                "service_name": service_name,
                "package_name": package_name,
            }
        )

        artifacts: list[Artifact] = [
            self._generate_source_artifact(
                writer=writer,
                relative_path=(
                    pkg_rel_dir
                    / "models"
                    / f"{model_module_name}_dtos.py"
                ),
                template_name="models/dtos.py.jinja2",
                context=dto_context,
            ),
            self._generate_source_artifact(
                writer=writer,
                relative_path=(
                    pkg_rel_dir
                    / "models"
                    / f"{model_module_name}_orm.py"
                ),
                template_name="models/orm.py.jinja2",
                context=model_context,
            ),
            self._generate_source_artifact(
                writer=writer,
                relative_path=(
                    pkg_rel_dir
                    / "repositories"
                    / f"{model_module_name}_repository.py"
                ),
                template_name="repositories/repository.py.jinja2",
                context=model_context,
            ),
            self._generate_source_artifact(
                writer=writer,
                relative_path=(
                    pkg_rel_dir
                    / "service"
                    / f"{model_module_name}_service.py"
                ),
                template_name="service/domain_service.py.jinja2",
                context=model_context,
            ),
            self._generate_source_artifact(
                writer=writer,
                relative_path=(
                    pkg_rel_dir
                    / "routers"
                    / f"{model_module_name}_router.py"
                ),
                template_name="routers/router.py.jinja2",
                context=model_context,
            ),
        ]

        if model.fsm is not None:
            artifacts.append(
                self._generate_source_artifact(
                    writer=writer,
                    relative_path=(
                        pkg_rel_dir
                        / "execution"
                        / f"{model_module_name}_fsm.py"
                    ),
                    template_name="execution/fsm.py.jinja2",
                    context=model_context,
                )
            )

        return tuple(artifacts)

    def _generate_rule_artifacts(
        self,
        *,
        service_ir: ServiceIR,
        generation_context: GenerationContext,
        writer: ArtifactWriter,
        pkg_rel_dir: Path,
        base_context: Mapping[str, object],
    ) -> tuple[Artifact, ...]:
        if not generation_context.has_rules:
            return ()

        artifacts: list[Artifact] = []

        for model in generation_context.models:
            model_rules = tuple(
                rule
                for rule in service_ir.rules
                if rule.target_entity == model.name
            )

            if not model_rules:
                continue

            context = dict(base_context)
            context.update(
                {
                    "model": model,
                    "rules": model_rules,
                }
            )

            artifacts.append(
                self._generate_source_artifact(
                    writer=writer,
                    relative_path=(
                        pkg_rel_dir
                        / "execution"
                        / f"{to_snake_case(model.name)}_rules.py"
                    ),
                    template_name="execution/rules.py.jinja2",
                    context=context,
                )
            )

        return tuple(artifacts)

    def _generate_workflow_artifacts(
        self,
        *,
        service_ir: ServiceIR,
        generation_context: GenerationContext,
        writer: ArtifactWriter,
        pkg_rel_dir: Path,
        base_context: Mapping[str, object],
    ) -> tuple[Artifact, ...]:
        if not generation_context.has_workflows:
            return ()

        artifacts: list[Artifact] = []

        for workflow in service_ir.workflows:
            context = dict(base_context)
            context["workflow"] = workflow

            artifacts.append(
                self._generate_source_artifact(
                    writer=writer,
                    relative_path=(
                        pkg_rel_dir
                        / "execution"
                        / f"{to_snake_case(workflow.name)}_workflow.py"
                    ),
                    template_name="execution/workflows.py.jinja2",
                    context=context,
                )
            )

        return tuple(artifacts)

    def _generate_test_artifacts(
        self,
        *,
        service_ir: ServiceIR,
        generation_context: GenerationContext,
        writer: ArtifactWriter,
        base_context: Mapping[str, object],
    ) -> tuple[Artifact, ...]:
        artifacts: list[Artifact] = []

        context = dict(base_context)

        artifacts.append(
            self._generate_source_artifact(
                writer=writer,
                relative_path=Path("tests") / "conftest.py",
                template_name="tests/conftest.py.jinja2",
                context=context,
            )
        )

        if generation_context.has_fsms:
            artifacts.append(
                self._generate_source_artifact(
                    writer=writer,
                    relative_path=Path("tests") / "test_fsm.py",
                    template_name="tests/test_fsm.py.jinja2",
                    context=context,
                )
            )

        for model in generation_context.models:
            model_context = dict(base_context)
            model_context["model"] = model

            artifacts.append(
                self._generate_source_artifact(
                    writer=writer,
                    relative_path=(
                        Path("tests")
                        / f"test_{to_snake_case(model.name)}_routers.py"
                    ),
                    template_name="tests/test_routers.py.jinja2",
                    context=model_context,
                )
            )

        if generation_context.has_workflows:
            workflow_context = dict(base_context)
            workflow_context["workflows"] = service_ir.workflows

            artifacts.append(
                self._generate_source_artifact(
                    writer=writer,
                    relative_path=(
                        Path("tests") / "test_workflows.py"
                    ),
                    template_name="tests/test_workflows.py.jinja2",
                    context=workflow_context,
                )
            )

        return tuple(artifacts)

    @staticmethod
    @trace_span("generation.pipeline.validate_input")
    def _validate_generation_input(
        service_ir: ServiceIR,
    ) -> None:
        try:
            validate_relationship_graph(service_ir)
        except CodeGenerationError:
            raise
        except Exception as err:
            raise CodeGenerationError(
                message=(
                    "Generation input validation failed: "
                    f"{err}"
                ),
                location="service_ir.relationships",
                error_code="ERR_GENERATION_INVALID_RELATIONSHIPS",
                suggested_resolution=(
                    "Correct relationship foreign-key, target-entity, "
                    "back_populates, and secondary-table metadata in the IR."
                ),
            ) from err

    @trace_span("generation.pipeline.generate_source_artifact")
    def _generate_source_artifact(
        self,
        *,
        writer: ArtifactWriter,
        relative_path: Path,
        template_name: str,
        context: Mapping[str, object],
    ) -> Artifact:
        try:
            raw_code = self.renderer.render(
                template_name,
                context,
            )

            transformed_code = self.cst_pipeline.transform(
                source_code=raw_code,
                filename=relative_path.as_posix(),
            )

            formatted_code = self.formatting_gate.format_code(
                source_code=transformed_code,
                filename=relative_path.as_posix(),
            )

            return writer.write_artifact(
                relative_path=relative_path,
                content=formatted_code,
            )

        except CodeGenerationError:
            raise

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to generate source artifact "
                    f"'{relative_path}': {err}"
                ),
                location=relative_path.as_posix(),
                error_code="ERR_GENERATION_SOURCE_ARTIFACT_FAILED",
                suggested_resolution=(
                    "Inspect template rendering, AST transformations, "
                    "formatting, and artifact-write diagnostics."
                ),
            ) from err

    @trace_span("generation.pipeline.generate_plain_artifact")
    def _generate_plain_artifact(
        self,
        *,
        writer: ArtifactWriter,
        relative_path: Path,
        template_name: str,
        context: Mapping[str, object],
    ) -> Artifact:
        try:
            raw_content = self.renderer.render(
                template_name,
                context,
            )

            return writer.write_artifact(
                relative_path=relative_path,
                content=raw_content,
            )

        except CodeGenerationError:
            raise

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to generate plain artifact "
                    f"'{relative_path}': {err}"
                ),
                location=relative_path.as_posix(),
                error_code="ERR_GENERATION_PLAIN_ARTIFACT_FAILED",
                suggested_resolution=(
                    "Inspect template rendering and artifact-write diagnostics."
                ),
            ) from err

    @staticmethod
    def _ensure_directory(directory: Path) -> None:
        if directory.exists():
            if not directory.is_dir():
                raise CodeGenerationError(
                    message=(
                        f"Generation path exists but is not a directory: "
                        f"'{directory}'."
                    ),
                    location=str(directory),
                    error_code="ERR_GENERATION_PATH_NOT_DIRECTORY",
                    suggested_resolution=(
                        "Remove the conflicting file or choose another target."
                    ),
                )
            return

        try:
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to create generation directory "
                    f"'{directory}': {err}"
                ),
                location=str(directory),
                error_code="ERR_GENERATION_DIRECTORY_CREATE_FAILED",
                suggested_resolution=(
                    "Verify target-directory permissions."
                ),
            ) from err

    @staticmethod
    def _relative_to_target(
        path: Path,
        target_dir: Path,
    ) -> Path:
        try:
            return path.resolve().relative_to(
                target_dir.resolve()
            )
        except ValueError as err:
            raise CodeGenerationError(
                message=(
                    f"Generated path '{path}' is outside target "
                    f"directory '{target_dir}'."
                ),
                location=str(path),
                error_code="ERR_GENERATION_PATH_ESCAPE",
                suggested_resolution=(
                    "Ensure generated artifacts remain under target_dir."
                ),
            ) from err