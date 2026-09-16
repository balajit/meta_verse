from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span


logger = get_logger("meta_service_generator.transforms.ruff")
tracer = get_tracer("meta_service_generator.transforms.ruff")


DEFAULT_RUFF_TIMEOUT_SECONDS = 60.0
MAX_RUFF_OUTPUT_BYTES = 2 * 1024 * 1024


class RuffGate:
    """Runs Ruff against generated source."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_RUFF_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )

        self.timeout_seconds = timeout_seconds

    @trace_span("transforms.ruff.check")
    def check(self, project_dir: Path) -> None:
        if not isinstance(project_dir, Path):
            raise CodeGenerationError(
                message=(
                    f"project_dir must be pathlib.Path, got "
                    f"{type(project_dir).__name__}."
                ),
                location="project_dir",
                error_code="ERR_RUFF_PROJECT_DIR_INVALID",
                suggested_resolution=(
                    "Pass the generated project root as pathlib.Path."
                ),
            )

        if not project_dir.is_dir():
            raise CodeGenerationError(
                message=(
                    f"Generated project directory does not exist: "
                    f"'{project_dir}'."
                ),
                location=str(project_dir),
                error_code="ERR_RUFF_PROJECT_DIR_NOT_FOUND",
                suggested_resolution=(
                    "Run the Ruff gate after generation has created the project."
                ),
            )

        try:
            result = subprocess.run(
                [
                    "ruff",
                    "check",
                    "--output-format",
                    "json",
                    str(project_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )

        except FileNotFoundError as err:
            raise CodeGenerationError(
                message="Ruff executable was not found.",
                location=str(project_dir),
                error_code="ERR_RUFF_NOT_INSTALLED",
                suggested_resolution=(
                    "Install Ruff in the generator execution environment."
                ),
            ) from err

        except subprocess.TimeoutExpired as err:
            raise CodeGenerationError(
                message=(
                    f"Ruff validation exceeded the "
                    f"{self.timeout_seconds:g}-second timeout."
                ),
                location=str(project_dir),
                error_code="ERR_RUFF_TIMEOUT",
                suggested_resolution=(
                    "Inspect generated-project size or increase the explicit "
                    "Ruff timeout."
                ),
            ) from err

        except OSError as err:
            raise CodeGenerationError(
                message=f"Failed to execute Ruff: {err}",
                location=str(project_dir),
                error_code="ERR_RUFF_EXECUTION_FAILED",
                suggested_resolution=(
                    "Verify that Ruff is executable in the generator environment."
                ),
            ) from err

        stdout = result.stdout[:MAX_RUFF_OUTPUT_BYTES]
        stderr = result.stderr[:MAX_RUFF_OUTPUT_BYTES]

        if result.returncode != 0:
            logger.error(
                "Ruff rejected generated project.",
                extra={
                    "event_type": "ruff_validation_failed",
                    "project_dir": str(project_dir),
                    "returncode": result.returncode,
                },
            )

            details: dict[str, object] = {
                "stdout": stdout,
                "stderr": stderr,
                "returncode": result.returncode,
            }

            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, list):
                    details["diagnostics"] = parsed
            except json.JSONDecodeError:
                pass

            raise CodeGenerationError(
                message="Ruff rejected generated project.",
                location=str(project_dir),
                error_code="ERR_GENERATION_RUFF_FAILED",
                suggested_resolution=(
                    "Fix the generated source or generation templates."
                ),
                details=details,
            )

        logger.info(
            "Ruff validation completed successfully.",
            extra={
                "event_type": "ruff_validation_passed",
                "project_dir": str(project_dir),
            },
        )


class GeneratedProjectContract:
    """
    Contract for generated-project structural and security invariants.
    """

    REQUIRED_FILES = (
        "pyproject.toml",
        "src/{package}/__init__.py",
        "src/{package}/main.py",
        "src/{package}/database.py",
        "src/{package}/extensions/config.py",
        "src/{package}/models/base.py",
        "tests/conftest.py",
    )

    FORBIDDEN_PATTERNS = (
        "eval(",
        "exec(",
        "os.getenv(",
        "postgres:postgres@",
        "await session.commit()",
        "class Base(DeclarativeBase)",
    )


class GeneratedProjectContractValidator:
    """Validates the generated project against structural and AST-level contracts."""

    @trace_span("transforms.ruff.validate_generated_project")
    def validate(
        self,
        project_root: Path,
        package_name: str,
    ) -> None:
        if not isinstance(project_root, Path):
            raise CodeGenerationError(
                message=(
                    f"project_root must be pathlib.Path, got "
                    f"{type(project_root).__name__}."
                ),
                location="project_root",
                error_code="ERR_GENERATED_PROJECT_ROOT_INVALID",
                suggested_resolution=(
                    "Pass the generated project root as pathlib.Path."
                ),
            )

        if not package_name or not package_name.isidentifier():
            raise CodeGenerationError(
                message=(
                    f"Invalid generated Python package name: "
                    f"{package_name!r}."
                ),
                location="package_name",
                error_code="ERR_GENERATED_PACKAGE_INVALID",
                suggested_resolution=(
                    "Pass the sanitized package_name from GenerationContext."
                ),
            )

        package_root = project_root / "src" / package_name

        required = tuple(
            project_root / path.format(package=package_name)
            for path in GeneratedProjectContract.REQUIRED_FILES
        )

        missing = [
            str(path.relative_to(project_root))
            for path in required
            if not path.is_file()
        ]

        if missing:
            raise CodeGenerationError(
                message="Generated-project contract is incomplete.",
                location=str(project_root),
                error_code="ERR_GENERATED_PROJECT_CONTRACT_FAILED",
                suggested_resolution=(
                    "Correct generation planning and required templates."
                ),
                details={
                    "missing_files": missing,
                },
            )

        for path in package_root.rglob("*.py"):
            try:
                source = path.read_text(
                    encoding="utf-8",
                )

                for forbidden in GeneratedProjectContract.FORBIDDEN_PATTERNS:
                    if forbidden in source:
                        raise CodeGenerationError(
                            message=(
                                f"Forbidden generated pattern "
                                f"'{forbidden}' found in '{path}'."
                            ),
                            location=str(path),
                            error_code="ERR_GENERATED_FORBIDDEN_PATTERN",
                            suggested_resolution=(
                                "Remove the forbidden construct from the "
                                "generation template."
                            ),
                            details={
                                "pattern": forbidden,
                            },
                        )

                tree = ast.parse(
                    source,
                    filename=str(path),
                )

                self._validate_python_contract(
                    tree,
                    path,
                )

            except UnicodeDecodeError as err:
                raise CodeGenerationError(
                    message=(
                        f"Generated Python file '{path}' is not valid UTF-8."
                    ),
                    location=str(path),
                    error_code="ERR_GENERATED_ENCODING_INVALID",
                    suggested_resolution=(
                        "Ensure generated source is UTF-8 encoded."
                    ),
                ) from err

            except SyntaxError as err:
                raise CodeGenerationError(
                    message=(
                        f"Generated Python file '{path}' is invalid: "
                        f"{err.msg}"
                    ),
                    location=(
                        f"{path}:{err.lineno or 0}:{err.offset or 0}"
                    ),
                    error_code="ERR_GENERATED_SYNTAX_INVALID",
                    suggested_resolution=(
                        "Inspect Jinja2 output and CST transformations."
                    ),
                ) from err

        logger.info(
            "Generated project contract validated.",
            extra={
                "event_type": "generated_project_contract_validated",
                "project_root": str(project_root),
                "package_name": package_name,
            },
        )

    @staticmethod
    def _validate_python_contract(
        tree: ast.AST,
        path: Path,
    ) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id in {"eval", "exec"}
                ):
                    raise CodeGenerationError(
                        message=(
                            f"Forbidden dynamic execution in '{path}'."
                        ),
                        location=str(path),
                        error_code="ERR_GENERATED_DYNAMIC_EXECUTION",
                        suggested_resolution=(
                            "Use declarative generated structures."
                        ),
                    )