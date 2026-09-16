from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.generation.artifacts import Artifact, ArtifactWriter
from meta_service_generator.ir.model import ServiceIR
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger("meta_service_generator.generation.manifest_report")
tracer = get_tracer("meta_service_generator.generation.manifest_report")


class BuildMetadata(BaseModel):
    generator_version: str
    manifest_digest: str
    template_version: str
    transform_version: str

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )


class BuildManifest(BaseModel):
    """
    Immutable build manifest containing deterministic artifact metadata and service context.
    """

    #metadata: BuildMetadata
    service_name: str
    service_version: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    total_artifacts: int
    total_bytes: int
    artifacts: tuple[Artifact, ...]

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class ManifestReportGenerator:
    """
    Generates deterministic JSON build manifests and human-readable Markdown reports.
    """

    @staticmethod
    def _sorted_artifacts(
        artifacts: Sequence[Artifact],
    ) -> tuple[Artifact, ...]:
        """Returns artifacts in deterministic relative-path order."""
        return tuple(
            sorted(
                artifacts,
                key=lambda artifact: artifact.relative_path,
            )
        )

    @staticmethod
    def _validate_artifacts(
        artifacts: Sequence[Artifact],
    ) -> tuple[Artifact, ...]:
        if not isinstance(artifacts, Sequence):
            raise CodeGenerationError(
                message=(
                    "artifacts must be a sequence of Artifact instances; "
                    f"received {type(artifacts).__name__}."
                ),
                location="artifacts",
                error_code="ERR_MANIFEST_INVALID_ARTIFACTS",
                suggested_resolution=(
                    "Pass the artifacts emitted by ArtifactWriter."
                ),
            )

        validated = tuple(artifacts)

        for index, artifact in enumerate(validated):
            if not isinstance(artifact, Artifact):
                raise CodeGenerationError(
                    message=(
                        f"Artifact at index {index} must be Artifact, got "
                        f"{type(artifact).__name__}."
                    ),
                    location=f"artifacts[{index}]",
                    error_code="ERR_MANIFEST_INVALID_ARTIFACT",
                    suggested_resolution=(
                        "Pass only Artifact records returned by ArtifactWriter."
                    ),
                )

        return validated

    @trace_span("generation.manifest_report.generate_manifest")
    def generate_manifest(
        self,
        service_ir: ServiceIR,
        artifacts: Sequence[Artifact],
        target_dir: Path,
        writer: ArtifactWriter | None = None,
    ) -> Artifact:
        """
        Creates build_manifest.json containing cryptographic hashes for all emitted artifacts.
        """
        if not isinstance(service_ir, ServiceIR):
            raise CodeGenerationError(
                message=(
                    "service_ir must be a ServiceIR instance; "
                    f"received {type(service_ir).__name__}."
                ),
                location="service_ir",
                error_code="ERR_MANIFEST_INVALID_IR",
                suggested_resolution=(
                    "Pass the validated immutable ServiceIR used for generation."
                ),
            )

        if not isinstance(target_dir, Path):
            raise CodeGenerationError(
                message=(
                    "target_dir must be pathlib.Path; "
                    f"received {type(target_dir).__name__}."
                ),
                location="target_dir",
                error_code="ERR_MANIFEST_INVALID_TARGET",
                suggested_resolution=(
                    "Pass the generation target as pathlib.Path."
                ),
            )

        try:
            artifact_writer = (
                writer
                if writer is not None
                else ArtifactWriter(target_dir)
            )

            sorted_artifacts = self._sorted_artifacts(
                self._validate_artifacts(artifacts)
            )

            total_bytes = sum(
                artifact.size_bytes
                for artifact in sorted_artifacts
            )

            manifest = BuildManifest(
                service_name=service_ir.service_name,
                service_version=service_ir.version,
                total_artifacts=len(sorted_artifacts),
                total_bytes=total_bytes,
                artifacts=sorted_artifacts,
            )

            manifest_json = json.dumps(
                manifest.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ) + "\n"

            result = artifact_writer.write_artifact(
                "build_manifest.json",
                manifest_json,
            )

            logger.info(
                "Build manifest generated.",
                extra={
                    "event_type": "build_manifest_generated",
                    "service_name": service_ir.service_name,
                    "artifact_count": len(sorted_artifacts),
                    "total_bytes": total_bytes,
                    "manifest_path": result.relative_path,
                },
            )

            return result

        except CodeGenerationError:
            raise

        except (OSError, TypeError, ValueError) as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to generate build manifest report: {err}"
                ),
                location="build_manifest.json",
                error_code="ERR_MANIFEST_GENERATION_FAILED",
                suggested_resolution=(
                    "Verify service IR data and target directory write permissions."
                ),
            ) from err

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to generate build manifest report: {err}"
                ),
                location="build_manifest.json",
                error_code="ERR_MANIFEST_GENERATION_FAILED",
                suggested_resolution=(
                    "Verify service IR data and target directory write permissions."
                ),
            ) from err

    @trace_span("generation.manifest_report.generate_markdown_report")
    def generate_markdown_report(
        self,
        service_ir: ServiceIR,
        artifacts: Sequence[Artifact],
        target_dir: Path,
        writer: ArtifactWriter | None = None,
    ) -> Artifact:
        """
        Generates human-readable BUILD_REPORT.md summary for build logs and agentic triage.
        """
        if not isinstance(service_ir, ServiceIR):
            raise CodeGenerationError(
                message=(
                    "service_ir must be a ServiceIR instance; "
                    f"received {type(service_ir).__name__}."
                ),
                location="service_ir",
                error_code="ERR_REPORT_INVALID_IR",
                suggested_resolution=(
                    "Pass the validated immutable ServiceIR used for generation."
                ),
            )

        if not isinstance(target_dir, Path):
            raise CodeGenerationError(
                message=(
                    "target_dir must be pathlib.Path; "
                    f"received {type(target_dir).__name__}."
                ),
                location="target_dir",
                error_code="ERR_REPORT_INVALID_TARGET",
                suggested_resolution=(
                    "Pass the generation target as pathlib.Path."
                ),
            )

        try:
            artifact_writer = (
                writer
                if writer is not None
                else ArtifactWriter(target_dir)
            )

            sorted_artifacts = self._sorted_artifacts(
                self._validate_artifacts(artifacts)
            )

            lines: list[str] = [
                f"# Service Synthesis Report: {service_ir.service_name}",
                f"**Version:** {service_ir.version}  ",
                (
                    f"**Generated At:** "
                    f"{datetime.now(timezone.utc).isoformat()}  "
                ),
                f"**Total Artifacts:** {len(sorted_artifacts)}  ",
                (
                    f"**Total Size:** "
                    f"{sum(a.size_bytes for a in sorted_artifacts)} bytes  "
                ),
                "",
                "## Generated File Artifacts",
                "",
                "| Relative Path | Size (Bytes) | SHA-256 Digest | Executable |",
                "| :--- | :--- | :--- | :--- |",
            ]

            for artifact in sorted_artifacts:
                short_hash = artifact.content_hash[:12]
                exec_flag = "Yes" if artifact.is_executable else "No"

                lines.append(
                    f"| `{artifact.relative_path}` | "
                    f"{artifact.size_bytes} | "
                    f"`{short_hash}...` | "
                    f"{exec_flag} |"
                )

            report_content = "\n".join(lines) + "\n"

            result = artifact_writer.write_artifact(
                "BUILD_REPORT.md",
                report_content,
            )

            logger.info(
                "Build report generated.",
                extra={
                    "event_type": "build_report_generated",
                    "service_name": service_ir.service_name,
                    "artifact_count": len(sorted_artifacts),
                    "report_path": result.relative_path,
                },
            )

            return result

        except CodeGenerationError:
            raise

        except (OSError, TypeError, ValueError) as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to generate markdown build report: {err}"
                ),
                location="BUILD_REPORT.md",
                error_code="ERR_BUILD_REPORT_GENERATION_FAILED",
                suggested_resolution=(
                    "Ensure target folder is writable and artifact records are intact."
                ),
            ) from err

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to generate markdown build report: {err}"
                ),
                location="BUILD_REPORT.md",
                error_code="ERR_BUILD_REPORT_GENERATION_FAILED",
                suggested_resolution=(
                    "Ensure target folder is writable and artifact records are intact."
                ),
            ) from err