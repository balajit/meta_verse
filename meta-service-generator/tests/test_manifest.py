from __future__ import annotations

import json
from pathlib import Path
import unittest.mock as mock
from typing import Any

import pytest
from pydantic import ValidationError

from meta_service_generator.exceptions import ManifestValidationError
from meta_service_generator.manifest.loader import ManifestLoader
from meta_service_generator.manifest.references import ReferentialIntegrityEngine
from meta_service_generator.manifest.schema import (
    AttributeSpec,
    EntitySpec,
    FSMSpec,
    ManifestSpec,
    PolicySpec,
    RelationshipSpec,
    TransitionSpec,
    WorkflowSpec,
    WorkflowStepSpec,
    BusinessRuleSpec,
)
from meta_service_generator.manifest.validator import ManifestValidator


# =============================================================================
# 1. Manifest Loader Tests
# =============================================================================


class TestManifestLoader:
    def test_init_invalid_max_bytes(self):
        with pytest.raises(ValueError, match="max_manifest_bytes must be greater than zero"):
            ManifestLoader(max_manifest_bytes=0)

    def test_load_from_path_invalid_type(self):
        loader = ManifestLoader()
        with pytest.raises(TypeError, match="path must be pathlib.Path"):
            loader.load_from_path("invalid_path")  # type: ignore

    def test_load_from_path_file_not_found(self, tmp_path: Path):
        loader = ManifestLoader()
        missing = tmp_path / "missing.json"
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_path(missing)
        assert exc.value.error_code == "ERR_MANIFEST_FILE_NOT_FOUND"

    def test_load_from_path_not_a_file(self, tmp_path: Path):
        loader = ManifestLoader()
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_path(tmp_path)
        assert exc.value.error_code == "ERR_MANIFEST_PATH_NOT_FILE"

    def test_load_from_path_file_too_large(self, tmp_path: Path):
        loader = ManifestLoader(max_manifest_bytes=10)
        large_file = tmp_path / "large.json"
        large_file.write_text('{"key": "value_exceeding_bytes"}')
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_path(large_file)
        assert exc.value.error_code == "ERR_MANIFEST_TOO_LARGE"

    def test_load_from_path_unicode_decode_error(self, tmp_path: Path):
        loader = ManifestLoader()
        bad_file = tmp_path / "bad.json"
        bad_file.write_bytes(b"\x80\x81\x82")
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_path(bad_file)
        assert exc.value.error_code == "ERR_MANIFEST_ENCODING_INVALID"

    def test_load_from_path_os_error(self, tmp_path: Path):
        loader = ManifestLoader()
        file_path = tmp_path / "test.json"
        file_path.write_text('{"key": "value"}')

        with mock.patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
            with pytest.raises(ManifestValidationError) as exc:
                loader.load_from_path(file_path)
            assert exc.value.error_code == "ERR_MANIFEST_READ_FAILED"

    def test_load_from_str_non_str_content(self):
        loader = ManifestLoader()
        with pytest.raises(TypeError, match="content must be str"):
            loader.load_from_str(123)  # type: ignore

    def test_load_from_str_empty_content(self):
        loader = ManifestLoader()
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_str("   ")
        assert exc.value.error_code == "ERR_MANIFEST_EMPTY"

    def test_load_from_str_unsupported_suffix(self):
        loader = ManifestLoader()
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_str("content", suffix=".xml")
        assert exc.value.error_code == "ERR_MANIFEST_EXTENSION_UNSUPPORTED"

    def test_load_from_str_inline_json_and_yaml_fallback(self):
        loader = ManifestLoader()
        # Valid JSON
        data_json = loader.load_from_str('{"version": "1.0.0"}')
        assert data_json["version"] == "1.0.0"

        # Valid YAML (invalid JSON)
        data_yaml = loader.load_from_str("version: 1.0.0\nservice_name: yaml_svc")
        assert data_yaml["service_name"] == "yaml_svc"

        # Invalid both
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_str("{invalid json & yaml:")
        assert exc.value.error_code == "ERR_MANIFEST_SYNTAX_INVALID"

    def test_parse_json_non_dict_root(self):
        loader = ManifestLoader()
        with pytest.raises(ManifestValidationError) as exc:
            loader.load_from_str("[1, 2, 3]", suffix=".json")
        assert exc.value.error_code == "ERR_MANIFEST_TOP_LEVEL_INVALID"


# =============================================================================
# 2. Referential Integrity Engine Tests
# =============================================================================


class TestReferentialIntegrityEngine:
    @pytest.fixture
    def engine(self) -> ReferentialIntegrityEngine:
        return ReferentialIntegrityEngine()

    def test_duplicate_entity_name(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(
                EntitySpec(name="User", attributes=(AttributeSpec(name="id", type="int"),)),
                EntitySpec(name="User", attributes=(AttributeSpec(name="id", type="int"),)),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_DUPLICATE_ENTITY"

    def test_duplicate_attribute_name(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(
                EntitySpec(
                    name="User",
                    attributes=(
                        AttributeSpec(name="id", type="int"),
                        AttributeSpec(name="id", type="str"),
                    ),
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_DUPLICATE_ATTRIBUTE"

    def test_unknown_target_entity_and_foreign_key(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(
                EntitySpec(
                    name="User",
                    attributes=(AttributeSpec(name="id", type="int"),),
                    relationships=(
                        RelationshipSpec(
                            name="rel1",
                            target_entity="MissingEntity",
                            cardinality="1:1",
                            foreign_key="missing_fk",
                        ),
                    ),
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_UNKNOWN_TARGET_ENTITY"

    def test_unknown_foreign_key(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(
                EntitySpec(
                    name="User",
                    attributes=(AttributeSpec(name="id", type="int"),),
                    relationships=(
                        RelationshipSpec(
                            name="rel1",
                            target_entity="User",
                            cardinality="1:1",
                            foreign_key="non_existent_attribute",
                        ),
                    ),
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_UNKNOWN_FOREIGN_KEY"

    def test_fsm_validation_errors(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(
                EntitySpec(
                    name="User",
                    attributes=(AttributeSpec(name="id", type="int"),),
                    fsm=FSMSpec(
                        state_attribute="non_existent_state_attr",
                        initial_state="invalid_init",
                        states=("state1", "state1"),  # Duplicate state
                        transitions=(
                            TransitionSpec(
                                trigger="t1",
                                source_state="unknown_src",
                                target_state="unknown_tgt",
                            ),
                        ),
                    ),
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code in {
            "ERR_REF_FSM_DUPLICATE_STATE",
            "ERR_REF_FSM_INVALID_INITIAL_STATE",
            "ERR_REF_FSM_UNKNOWN_ATTRIBUTE",
            "ERR_REF_FSM_UNKNOWN_STATE",
        }

    def test_business_rule_unknown_entity(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(),
            business_rules=(
                BusinessRuleSpec(
                    name="rule1",
                    target_entity="MissingEntity",
                    expression="x > 0",
                    error_message="Error",
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_RULE_UNKNOWN_ENTITY"

    def test_workflow_duplicate_step(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(),
            workflows=(
                WorkflowSpec(
                    name="wf",
                    steps=(
                        WorkflowStepSpec(name="step1", action="act", depends_on=()),
                        WorkflowStepSpec(name="step1", action="act", depends_on=()),
                    ),
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_WORKFLOW_DUPLICATE_STEP"

    def test_workflow_self_dependency_error(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(),
            workflows=(
                WorkflowSpec(
                    name="wf",
                    steps=(
                        WorkflowStepSpec(name="step1", action="act", depends_on=("step1",)),
                    ),
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_WORKFLOW_SELF_DEPENDENCY"

    def test_workflow_missing_dependency(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(),
            workflows=(
                WorkflowSpec(
                    name="wf",
                    steps=(
                        WorkflowStepSpec(name="step1", action="act", depends_on=("missing_step",)),
                    ),
                ),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_WORKFLOW_MISSING_DEPENDENCY"

    def test_duplicate_policy_name(self, engine: ReferentialIntegrityEngine):
        manifest = ManifestSpec(
            version="1.0.0",
            service_name="svc",
            entities=(),
            policies=(
                PolicySpec(name="pol", roles=("admin",), actions=("read",)),
                PolicySpec(name="pol", roles=("admin",), actions=("read",)),
            ),
        )
        with pytest.raises(ManifestValidationError) as exc:
            engine.validate(manifest)
        assert exc.value.error_code == "ERR_REF_DUPLICATE_POLICY"


# =============================================================================
# 3. Manifest Validator Tests
# =============================================================================


class TestManifestValidator:
    def test_validator_init_schema_missing(self, tmp_path: Path) -> None:
        missing_schema = tmp_path / "missing.schema.json"
        with pytest.raises(RuntimeError, match="Manifest JSON Schema is missing"):
            ManifestValidator(schema_path=missing_schema)

    def test_validator_init_invalid_json_schema(self, tmp_path: Path) -> None:
        invalid_schema = tmp_path / "invalid.schema.json"
        invalid_schema.write_text("not json", encoding="utf-8")
        with pytest.raises(
            RuntimeError, match="Manifest JSON Schema is not valid JSON"
        ):
            ManifestValidator(schema_path=invalid_schema)

    def test_validator_init_os_error(self, tmp_path: Path) -> None:
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(
            '{"$schema": "https://json-schema.org/draft/2020-12/schema"}',
            encoding="utf-8",
        )
        with mock.patch.object(
            Path, "read_text", side_effect=OSError("Read permission denied")
        ):
            with pytest.raises(
                RuntimeError, match="Failed to read Manifest JSON Schema"
            ):
                ManifestValidator(schema_path=schema_file)

    def test_validator_init_generic_exception(self, tmp_path: Path) -> None:
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(
            '{"$schema": "https://json-schema.org/draft/2020-12/schema"}',
            encoding="utf-8",
        )
        with mock.patch(
            "jsonschema.Draft202012Validator.check_schema",
            side_effect=ValueError("Invalid schema structure"),
        ):
            with pytest.raises(
                RuntimeError,
                match="Failed to initialize JSON Schema Draft-2020-12 validator",
            ):
                ManifestValidator(schema_path=schema_file)

    def test_default_schema_resolution_success(self) -> None:
        validator = ManifestValidator()
        assert validator._schema_path.name == "manifest.schema.json"

    def test_packaged_schema_resolution_failure(self) -> None:
        with mock.patch(
            "importlib.resources.files",
            side_effect=ImportError("Package missing"),
        ):
            with pytest.raises(
                RuntimeError,
                match="Unable to resolve packaged manifest.schema.json",
            ):
                ManifestValidator._resolve_packaged_schema_path()

    def test_validate_root_not_dict(self, tmp_path: Path) -> None:
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(
            '{"$schema": "https://json-schema.org/draft/2020-12/schema"}',
            encoding="utf-8",
        )
        validator = ManifestValidator(schema_path=schema_file)

        with pytest.raises(ManifestValidationError) as exc:
            validator.validate("not_a_dict")  # type: ignore[arg-type]
        assert exc.value.error_code == "ERR_MANIFEST_ROOT_INVALID"

    def test_validate_schema_violation(self, tmp_path: Path) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["version", "service_name"],
            "properties": {
                "version": {"type": "string"},
                "service_name": {"type": "string"},
            },
        }
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        validator = ManifestValidator(schema_path=schema_file)

        with pytest.raises(ManifestValidationError) as exc:
            validator.validate({"version": "1.0.0"})

        assert exc.value.error_code == "ERR_MANIFEST_SCHEMA_VIOLATION"
        assert exc.value.details["validation_error_count"] == 1
        assert "service_name" in exc.value.message

    def test_validate_pydantic_type_mismatch(self, tmp_path: Path) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
        }
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        validator = ManifestValidator(schema_path=schema_file)

        with pytest.raises(ManifestValidationError) as exc:
            validator.validate({})

        assert exc.value.error_code == "ERR_MANIFEST_TYPE_MISMATCH"
        assert "Type compilation error" in exc.value.message
        assert exc.value.details["validation_error_count"] > 0

    def test_validate_full_success_and_referential_integrity(self) -> None:
        validator = ManifestValidator()
        raw_manifest = {
            "version": "1.0.0",
            "service_name": "test_service",
            "entities": [
                {
                    "name": "User",
                    "attributes": [{"name": "id", "type": "int"}],
                }
            ],
        }
        spec = validator.validate(raw_manifest)
        assert isinstance(spec, ManifestSpec)
        assert spec.service_name == "test_service"
        assert spec.version == "1.0.0"
        assert len(spec.entities) == 1

    def test_json_pointer_formatting(self) -> None:
        assert ManifestValidator._json_pointer(()) == "/"
        assert (
            ManifestValidator._json_pointer(["entities", 0, "name/key~1"])
            == "/entities/0/name~1key~01"
        )