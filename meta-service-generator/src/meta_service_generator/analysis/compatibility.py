from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(
    "meta_service_generator.analysis.compatibility"
)
tracer = get_tracer(
    "meta_service_generator.analysis.compatibility"
)


class ViolationSeverity(StrEnum):
    """Severity classification for schema compatibility violations [source: 3]."""

    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class FieldDefinitionSpec(BaseModel):
    """Specification of a single schema field for compatibility analysis [source: 3]."""

    name: str = Field(
        ...,
        min_length=1,
        description="Field attribute name.",
    )

    type_name: str = Field(
        ...,
        min_length=1,
        description="Python or OpenAPI type string representation.",
    )

    is_nullable: bool = Field(
        default=False,
        description="Indicates whether None is a valid value.",
    )

    has_default: bool = Field(
        default=False,
        description="Indicates whether a default value is supplied.",
    )

    default_value: Any = Field(
        default=None,
        description="The default value if present.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class SchemaManifestSpec(BaseModel):
    """Manifest representing a complete versioned entity schema [source: 3]."""

    schema_id: str = Field(
        ...,
        min_length=1,
        description="Unique entity identifier.",
    )

    version: str = Field(
        ...,
        min_length=1,
        description="Semantic version string of the schema.",
    )

    fields: tuple[FieldDefinitionSpec, ...] = Field(
        default=(),
        description="Immutable collection of field specifications.",
    )

    polymorphic_discriminator: str | None = Field(
        default=None,
        description="Discriminator field name for meta_polymorph routing.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class CompatibilityViolation(BaseModel):
    """Detailed record of a single compatibility violation [source: 3]."""

    severity: ViolationSeverity = Field(
        ...,
        description="Severity level of the violation.",
    )

    field_name: str = Field(
        ...,
        min_length=1,
        description="Target field associated with the violation.",
    )

    issue_type: str = Field(
        ...,
        min_length=1,
        description="Categorical key describing the flaw type.",
    )

    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable explanation of the incompatibility.",
    )

    suggested_resolution: str = Field(
        ...,
        min_length=1,
        description="Actionable recommendation for resolving the violation.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class CompatibilityReport(BaseModel):
    """Summary report produced by the schema compatibility analyzer [source: 3]."""

    is_compatible: bool = Field(
        ...,
        description="True if no CRITICAL violations exist.",
    )

    source_version: str = Field(
        ...,
        min_length=1,
        description="Original schema version string.",
    )

    target_version: str = Field(
        ...,
        min_length=1,
        description="Evolved schema version string.",
    )

    violations: tuple[CompatibilityViolation, ...] = Field(
        default=(),
        description="Immutable collection of detected compatibility violations.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class SchemaCompatibilityAnalyzer:
    """
    Evaluates backwards compatibility between schema versions to prevent
    breaking API changes, field type mismatches, and polymorphic dispatch failures [source: 3].
    """

    @trace_span("analysis.compatibility.analyze")
    def analyze(
        self,
        source_schema: SchemaManifestSpec,
        target_schema: SchemaManifestSpec,
    ) -> CompatibilityReport:
        """
        Compares a source schema against an evolved target schema and returns a CompatibilityReport [source: 3].
        """
        if not isinstance(
            source_schema,
            SchemaManifestSpec,
        ):
            raise CodeGenerationError(
                message=(
                    "source_schema must be SchemaManifestSpec; "
                    f"received {type(source_schema).__name__}."
                ),
                location="source_schema",
                error_code="ERR_SCHEMA_SOURCE_TYPE_INVALID",
                suggested_resolution=(
                    "Provide a validated SchemaManifestSpec instance."
                ),
            )

        if not isinstance(
            target_schema,
            SchemaManifestSpec,
        ):
            raise CodeGenerationError(
                message=(
                    "target_schema must be SchemaManifestSpec; "
                    f"received {type(target_schema).__name__}."
                ),
                location="target_schema",
                error_code="ERR_SCHEMA_TARGET_TYPE_INVALID",
                suggested_resolution=(
                    "Provide a validated SchemaManifestSpec instance."
                ),
            )

        if source_schema.schema_id != target_schema.schema_id:
            raise CodeGenerationError(
                message=(
                    f"Cannot compare different schemas: "
                    f"'{source_schema.schema_id}' and "
                    f"'{target_schema.schema_id}'."
                ),
                location="schema_id",
                error_code="ERR_SCHEMA_ID_MISMATCH",
                suggested_resolution=(
                    "Compare two versions of the same schema_id."
                ),
            )

        logger.info(
            "Analyzing schema compatibility.",
            extra={
                "event_type": "analysis.compatibility.started",
                "schema_id": source_schema.schema_id,
                "source_version": source_schema.version,
                "target_version": target_schema.version,
            },
        )

        source_fields = self._index_fields(
            source_schema.fields
        )
        target_fields = self._index_fields(
            target_schema.fields
        )

        violations: list[CompatibilityViolation] = []

        self._check_discriminator_compatibility(
            source_schema,
            target_schema,
            violations,
        )

        self._check_removed_fields(
            source_fields,
            target_fields,
            target_schema,
            violations,
        )

        self._check_added_fields(
            source_fields,
            target_fields,
            target_schema,
            violations,
        )

        self._check_field_modifications(
            source_fields,
            target_fields,
            source_schema,
            target_schema,
            violations,
        )

        ordered_violations = tuple(
            sorted(
                violations,
                key=lambda violation: (
                    violation.field_name,
                    violation.issue_type,
                    violation.severity.value,
                ),
            )
        )

        # Preserve existing compatibility semantics:
        # only CRITICAL violations make the schema incompatible.
        is_compatible = not any(
            violation.severity
            == ViolationSeverity.CRITICAL
            for violation in ordered_violations
        )

        report = CompatibilityReport(
            is_compatible=is_compatible,
            source_version=source_schema.version,
            target_version=target_schema.version,
            violations=ordered_violations,
        )

        if not is_compatible:
            critical_count = sum(
                1
                for violation in ordered_violations
                if violation.severity
                == ViolationSeverity.CRITICAL
            )

            logger.error(
                "Schema compatibility check failed.",
                extra={
                    "event_type": "analysis.compatibility.failed",
                    "schema_id": source_schema.schema_id,
                    "source_version": source_schema.version,
                    "target_version": target_schema.version,
                    "critical_violations": critical_count,
                    "total_violations": len(
                        ordered_violations
                    ),
                },
            )

        else:
            logger.info(
                "Schema compatibility check passed.",
                extra={
                    "event_type": "analysis.compatibility.completed",
                    "schema_id": source_schema.schema_id,
                    "source_version": source_schema.version,
                    "target_version": target_schema.version,
                    "violation_count": len(
                        ordered_violations
                    ),
                },
            )

        return report

    @staticmethod
    def _index_fields(
        fields: tuple[FieldDefinitionSpec, ...],
    ) -> Mapping[str, FieldDefinitionSpec]:
        indexed: dict[str, FieldDefinitionSpec] = {}

        for field in fields:
            if field.name in indexed:
                raise CodeGenerationError(
                    message=(
                        f"Duplicate field '{field.name}' "
                        "found in compatibility schema."
                    ),
                    location=f"fields/{field.name}",
                    error_code="ERR_SCHEMA_DUPLICATE_FIELD",
                    suggested_resolution=(
                        "Ensure every schema field name is unique."
                    ),
                )

            indexed[field.name] = field

        return indexed

    def _check_discriminator_compatibility(
        self,
        source: SchemaManifestSpec,
        target: SchemaManifestSpec,
        violations: list[CompatibilityViolation],
    ) -> None:
        if (
            source.polymorphic_discriminator
            != target.polymorphic_discriminator
        ):
            violations.append(
                CompatibilityViolation(
                    severity=ViolationSeverity.CRITICAL,
                    field_name=(
                        source.polymorphic_discriminator
                        or "<none>"
                    ),
                    issue_type="DISCRIMINATOR_MUTATION",
                    description=(
                        f"Polymorphic discriminator altered from "
                        f"'{source.polymorphic_discriminator}' to "
                        f"'{target.polymorphic_discriminator}'. "
                        "This breaks meta_polymorph dispatch rules."
                    ),
                    suggested_resolution=(
                        "Retain original polymorphic discriminator field "
                        "or use meta_polymorph alias mappings."
                    ),
                )
            )

    def _check_removed_fields(
        self,
        source_fields: Mapping[str, FieldDefinitionSpec],
        target_fields: Mapping[str, FieldDefinitionSpec],
        target: SchemaManifestSpec,
        violations: list[CompatibilityViolation],
    ) -> None:
        """
        Detect removed fields using the already-built target index.

        The previous implementation rebuilt target_fields for every source
        field. Reusing the existing index makes this O(n) rather than O(n²).
        """
        for field_name, source_field in source_fields.items():
            if field_name in target_fields:
                continue

            severity = (
                ViolationSeverity.CRITICAL
                if (
                    not source_field.is_nullable
                    and not source_field.has_default
                )
                else ViolationSeverity.MAJOR
            )

            violations.append(
                CompatibilityViolation(
                    severity=severity,
                    field_name=field_name,
                    issue_type="FIELD_REMOVAL",
                    description=(
                        f"Field '{field_name}' present in "
                        f"source schema was removed from "
                        f"target version v{target.version}."
                    ),
                    suggested_resolution=(
                        "Deprecate the field by marking it optional instead "
                        "of removing it immediately."
                    ),
                )
            )

    def _check_added_fields(
        self,
        source_fields: Mapping[str, FieldDefinitionSpec],
        target_fields: Mapping[str, FieldDefinitionSpec],
        target: SchemaManifestSpec,
        violations: list[CompatibilityViolation],
    ) -> None:
        for field_name, target_field in target_fields.items():
            if field_name in source_fields:
                continue

            if (
                not target_field.is_nullable
                and not target_field.has_default
            ):
                violations.append(
                    CompatibilityViolation(
                        severity=ViolationSeverity.CRITICAL,
                        field_name=field_name,
                        issue_type="NON_NULLABLE_ADDITION",
                        description=(
                            f"Newly added field '{field_name}' in "
                            f"v{target.version} is non-nullable and lacks "
                            "a default value, breaking existing payloads."
                        ),
                        suggested_resolution=(
                            "Provide a default value or mark newly added "
                            "fields as Optional[T] = None."
                        ),
                    )
                )

    def _check_field_modifications(
        self,
        source_fields: Mapping[str, FieldDefinitionSpec],
        target_fields: Mapping[str, FieldDefinitionSpec],
        source: SchemaManifestSpec,
        target: SchemaManifestSpec,
        violations: list[CompatibilityViolation],
    ) -> None:
        for field_name, source_field in source_fields.items():
            target_field = target_fields.get(
                field_name
            )

            if target_field is None:
                continue

            if source_field.type_name != target_field.type_name:
                violations.append(
                    CompatibilityViolation(
                        severity=ViolationSeverity.CRITICAL,
                        field_name=field_name,
                        issue_type="TYPE_MISMATCH",
                        description=(
                            f"Field '{field_name}' type changed from "
                            f"'{source_field.type_name}' to "
                            f"'{target_field.type_name}'."
                        ),
                        suggested_resolution=(
                            "Maintain identical field types or register a "
                            "meta_compiler dynamic conversion handler."
                        ),
                    )
                )

            if (
                source_field.is_nullable
                and not target_field.is_nullable
                and not target_field.has_default
            ):
                violations.append(
                    CompatibilityViolation(
                        severity=ViolationSeverity.CRITICAL,
                        field_name=field_name,
                        issue_type="NULLABILITY_RESTRICTION",
                        description=(
                            f"Field '{field_name}' was nullable in "
                            f"v{source.version} but made non-nullable "
                            f"without a default in v{target.version}."
                        ),
                        suggested_resolution=(
                            "Ensure fields previously marked nullable retain "
                            "a default value when nullability is restricted."
                        ),
                    )


@trace_span("analysis.compatibility.enforce_compatibility")
def enforce_compatibility(
    source_schema: SchemaManifestSpec,
    target_schema: SchemaManifestSpec,
) -> CompatibilityReport:
    """
    Convenience function that evaluates compatibility and raises CodeGenerationError if critical violations exist [source: 3].
    """
    analyzer = SchemaCompatibilityAnalyzer()

    report = analyzer.analyze(
        source_schema,
        target_schema,
    )

    if not report.is_compatible:
        critical_issues = [
            f"[{violation.field_name}] "
            f"{violation.description}"
            for violation in report.violations
            if violation.severity
            == ViolationSeverity.CRITICAL
        ]

        raise CodeGenerationError(
            message=(
                f"Schema compatibility evaluation failed for "
                f"'{source_schema.schema_id}': "
                f"{'; '.join(critical_issues)}"
            ),
            location=(
                f"schema_id:{source_schema.schema_id}"
            ),
            error_code="ERR_SCHEMA_INCOMPATIBLE",
            suggested_resolution=(
                "Review suggested resolutions in the compatibility report "
                "and resolve breaking changes before code synthesis."
            ),
            details={
                "schema_id": source_schema.schema_id,
                "source_version": source_schema.version,
                "target_version": target_schema.version,
                "critical_violation_count": len(
                    critical_issues
                ),
            },
        )

    return report