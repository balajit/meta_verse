import pytest

from meta_service_generator.analysis.compatibility import (
    CompatibilityReport,
    FieldDefinitionSpec,
    SchemaCompatibilityAnalyzer,
    SchemaManifestSpec,
    ViolationSeverity,
    enforce_compatibility,
)
from meta_service_generator.exceptions import CodeGenerationError


@pytest.fixture
def base_schema():
    return SchemaManifestSpec(
        schema_id="UserSchema",
        version="1.0.0",
        polymorphic_discriminator="type",
        fields=(
            FieldDefinitionSpec(name="id", type_name="str", is_nullable=False, has_default=False),
            FieldDefinitionSpec(name="email", type_name="str", is_nullable=False, has_default=False),
            FieldDefinitionSpec(name="age", type_name="int", is_nullable=True, has_default=True, default_value=18),
        ),
    )


def test_schema_mismatch_raises_error(base_schema):
    target = base_schema.model_copy(update={"schema_id": "DifferentSchema"})
    analyzer = SchemaCompatibilityAnalyzer()

    with pytest.raises(CodeGenerationError, match="Cannot compare different schemas"):
        analyzer.analyze(base_schema, target)


def test_duplicate_fields_in_schema_raises_error():
    invalid_schema = SchemaManifestSpec(
        schema_id="UserSchema",
        version="1.0.0",
        fields=(
            FieldDefinitionSpec(name="id", type_name="str"),
            FieldDefinitionSpec(name="id", type_name="int"),
        ),
    )
    analyzer = SchemaCompatibilityAnalyzer()
    with pytest.raises(CodeGenerationError, match="Duplicate field 'id'"):
        analyzer.analyze(invalid_schema, invalid_schema)


def test_discriminator_mutation_critical_violation(base_schema):
    target = base_schema.model_copy(update={"polymorphic_discriminator": "alt_type", "version": "2.0.0"})
    report = SchemaCompatibilityAnalyzer().analyze(base_schema, target)

    assert report.is_compatible is False
    assert any(v.issue_type == "DISCRIMINATOR_MUTATION" and v.severity == ViolationSeverity.CRITICAL for v in report.violations)


def test_removed_fields_severity_evaluation(base_schema):
    # Removing non-nullable required field -> CRITICAL
    target_critical = base_schema.model_copy(
        update={
            "version": "1.1.0",
            "fields": (
                FieldDefinitionSpec(name="id", type_name="str"),
                FieldDefinitionSpec(name="age", type_name="int", is_nullable=True, has_default=True),
            ),
        }
    )
    report_crit = SchemaCompatibilityAnalyzer().analyze(base_schema, target_critical)
    assert report_crit.is_compatible is False
    assert any(v.field_name == "email" and v.severity == ViolationSeverity.CRITICAL for v in report_crit.violations)

    # Removing nullable field with default -> MAJOR (Non-breaking)
    target_major = base_schema.model_copy(
        update={
            "version": "1.1.0",
            "fields": (
                FieldDefinitionSpec(name="id", type_name="str"),
                FieldDefinitionSpec(name="email", type_name="str"),
            ),
        }
    )
    report_maj = SchemaCompatibilityAnalyzer().analyze(base_schema, target_major)
    assert report_maj.is_compatible is True
    assert any(v.field_name == "age" and v.severity == ViolationSeverity.MAJOR for v in report_maj.violations)


def test_added_non_nullable_field_without_default(base_schema):
    target = base_schema.model_copy(
        update={
            "version": "1.1.0",
            "fields": (
                *base_schema.fields,
                FieldDefinitionSpec(name="status", type_name="str", is_nullable=False, has_default=False),
            ),
        }
    )
    report = SchemaCompatibilityAnalyzer().analyze(base_schema, target)
    assert report.is_compatible is False
    assert any(v.issue_type == "NON_NULLABLE_ADDITION" and v.severity == ViolationSeverity.CRITICAL for v in report.violations)


def test_field_type_and_nullability_modifications(base_schema):
    target = base_schema.model_copy(
        update={
            "version": "1.1.0",
            "fields": (
                FieldDefinitionSpec(name="id", type_name="int"),  # Type change
                FieldDefinitionSpec(name="email", type_name="str"),
                FieldDefinitionSpec(name="age", type_name="int", is_nullable=False, has_default=False),  # Made non-nullable without default
            ),
        }
    )
    report = SchemaCompatibilityAnalyzer().analyze(base_schema, target)
    assert report.is_compatible is False
    issues = {v.issue_type for v in report.violations}
    assert "TYPE_MISMATCH" in issues
    assert "NULLABILITY_RESTRICTION" in issues


def test_enforce_compatibility_raises_on_critical_violations(base_schema):
    target = base_schema.model_copy(update={"polymorphic_discriminator": "changed"})
    with pytest.raises(CodeGenerationError, match="Schema compatibility evaluation failed"):
        enforce_compatibility(base_schema, target)


def test_enforce_compatibility_passes_for_compatible_changes(base_schema):
    target = base_schema.model_copy(
        update={
            "version": "1.1.0",
            "fields": (
                *base_schema.fields,
                FieldDefinitionSpec(name="bio", type_name="str", is_nullable=True, has_default=True, default_value=None),
            ),
        }
    )
    report = enforce_compatibility(base_schema, target)
    assert isinstance(report, CompatibilityReport)
    assert report.is_compatible is True