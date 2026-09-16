from __future__ import annotations

import unittest.mock as mock
from typing import Any

import pytest
from pydantic import ValidationError

from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.ir.builder import IRBuilder
from meta_service_generator.ir.dependencies import DependencyResolver
from meta_service_generator.ir.model import (
    IRFSM,
    IRField,
    IRModel,
    IRPolicy,
    IRRelationship,
    IRRule,
    IRTransition,
    IRWorkflow,
    IRWorkflowStep,
    ServiceIR,
)
from meta_service_generator.ir.names import (
    ensure_unique_identifiers,
    sanitize_identifier,
    to_pascal_case,
    to_screaming_snake_case,
    to_snake_case,
)
from meta_service_generator.ir.normalizer import TypeNormalizer
from meta_service_generator.manifest.schema import (
    AttributeSpec,
    BusinessRuleSpec,
    EntitySpec,
    FSMSpec,
    ManifestSpec,
    PolicySpec,
    RelationshipSpec,
    TransitionSpec,
    WorkflowSpec,
    WorkflowStepSpec,
)


# =============================================================================
# 1. Identifier & Naming Tests
# =============================================================================


class TestNames:
    def test_sanitize_identifier_valid(self):
        assert sanitize_identifier("user_name") == "user_name"
        assert sanitize_identifier("user-name") == "user_name"
        assert sanitize_identifier("user name") == "user_name"

    def test_sanitize_identifier_non_string_raises_type_error(self):
        with pytest.raises(TypeError, match="Identifier name must be str"):
            sanitize_identifier(123)  # type: ignore

    def test_sanitize_identifier_empty_or_non_words(self):
        assert sanitize_identifier("---") == "item"
        assert sanitize_identifier("") == "item"

    def test_sanitize_identifier_leading_digit(self):
        assert sanitize_identifier("123field") == "field_123field"

    def test_sanitize_identifier_python_reserved_keywords(self):
        assert sanitize_identifier("class") == "class_"
        assert sanitize_identifier("def") == "def_"
        assert sanitize_identifier("str") == "str_"
        assert sanitize_identifier("self") == "self_"
        assert sanitize_identifier("metadata") == "metadata_"

    def test_sanitize_identifier_invalid_identifier_fallback(self):
        with mock.patch("re.sub", return_value="123_invalid!"):
            with pytest.raises(ValueError, match="Unable to produce a valid Python identifier"):
                sanitize_identifier("bad")

    def test_ensure_unique_identifiers_success(self):
        names = ["user_id", "created-at", "status"]
        mapping = ensure_unique_identifiers(names, location="entities", kind="entity")
        assert mapping == {
            "user_id": "user_id",
            "created-at": "created_at",
            "status": "status",
        }

    def test_ensure_unique_identifiers_collision_error(self):
        names = ["user_id", "user-id"]
        with pytest.raises(IRBuilderError) as exc_info:
            ensure_unique_identifiers(names, location="entities", kind="entity")
        assert exc_info.value.error_code == "ERR_IR_IDENTIFIER_COLLISION"

    def test_ensure_unique_identifiers_duplicate_error(self):
        names = ["user_id", "user_id"]
        with pytest.raises(IRBuilderError) as exc_info:
            ensure_unique_identifiers(names, location="entities", kind="entity")
        assert exc_info.value.error_code == "ERR_IR_DUPLICATE_IDENTIFIER"

    def test_to_pascal_case(self):
        assert to_pascal_case("user_profile") == "UserProfile"
        assert to_pascal_case("user-profile") == "UserProfile"
        assert to_pascal_case("user profile") == "UserProfile"

    def test_to_pascal_case_empty(self):
        assert to_pascal_case("---") == "Item"

    def test_to_pascal_case_reserved_keyword(self):
        assert to_pascal_case("type") == "Type"

    def test_to_pascal_case_invalid_identifier(self):
        with mock.patch("re.split", return_value=["123bad"]):
            with pytest.raises(ValueError, match="Unable to produce a valid PascalCase identifier"):
                to_pascal_case("bad")

    def test_to_snake_case(self):
        assert to_snake_case("UserProfile") == "user_profile"
        assert to_snake_case("camelCase") == "camel_case"
        assert to_snake_case("kebab-case") == "kebab_case"

    def test_to_screaming_snake_case(self):
        assert to_screaming_snake_case("userProfile") == "USER_PROFILE"


# =============================================================================
# 2. Type Normalizer Tests
# =============================================================================


class TestTypeNormalizer:
    @pytest.mark.parametrize(
        ("raw_type", "expected_py", "expected_sql"),
        [
            ("str", "str", "String"),
            ("INT", "int", "Integer"),
            ("float", "float", "Float"),
            ("bool", "bool", "Boolean"),
            ("datetime", "datetime.datetime", "DateTime(timezone=True)"),
            ("uuid", "uuid.UUID", "Uuid"),
            ("dict", "dict[str, Any]", "JSON"),
            ("list", "list[Any]", "JSON"),
        ],
    )
    def test_normalize_type_supported(self, raw_type: str, expected_py: str, expected_sql: str):
        py_type, sql_type = TypeNormalizer.normalize_type(raw_type)
        assert py_type == expected_py
        assert sql_type == expected_sql

    def test_normalize_type_non_string(self):
        with pytest.raises(IRBuilderError) as exc_info:
            TypeNormalizer.normalize_type(123)  # type: ignore
        assert exc_info.value.error_code == "ERR_IR_TYPE_NOT_STRING"

    def test_normalize_type_empty(self):
        with pytest.raises(IRBuilderError) as exc_info:
            TypeNormalizer.normalize_type("   ")
        assert exc_info.value.error_code == "ERR_IR_EMPTY_TYPE"

    def test_normalize_type_unsupported(self):
        with pytest.raises(IRBuilderError) as exc_info:
            TypeNormalizer.normalize_type("custom_blob")
        assert exc_info.value.error_code == "ERR_IR_UNSUPPORTED_TYPE"


# =============================================================================
# 3. IR Data Models Immutability & Validation Tests
# =============================================================================


class TestIRModels:
    def test_ir_field_immutability(self):
        field = IRField(
            name="id",
            original_name="id",
            python_type="int",
            sql_type="Integer",
            is_primary_key=True,
        )
        with pytest.raises(ValidationError):
            field.name = "new_id"  # type: ignore

    def test_ir_field_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            IRField(
                name="id",
                original_name="id",
                python_type="int",
                sql_type="Integer",
                extra_param="forbidden",  # type: ignore
            )


# =============================================================================
# 4. Dependency Resolver Tests
# =============================================================================


class TestDependencyResolver:
    @pytest.fixture
    def resolver(self) -> DependencyResolver:
        return DependencyResolver()

    def test_topological_sort_success(self, resolver: DependencyResolver):
        user_model = IRModel(
            name="User",
            class_name="User",
            table_name="users",
            fields=(IRField(name="id", original_name="id", python_type="int", sql_type="Integer"),),
        )
        post_model = IRModel(
            name="Post",
            class_name="Post",
            table_name="posts",
            fields=(IRField(name="id", original_name="id", python_type="int", sql_type="Integer"),),
            relationships=(
                IRRelationship(
                    name="author",
                    original_name="author",
                    target_entity="User",
                    target_class_name="User",
                    cardinality="1:N",
                ),
            ),
        )
        service_ir = ServiceIR(
            service_name="blog",
            version="1.0.0",
            models=(post_model, user_model),
        )

        ordered = resolver.topological_sort_models(service_ir)
        assert [m.name for m in ordered] == ["User", "Post"]

    def test_topological_sort_unknown_model_error(self, resolver: DependencyResolver):
        post_model = IRModel(
            name="Post",
            class_name="Post",
            table_name="posts",
            fields=(),
            relationships=(
                IRRelationship(
                    name="author",
                    original_name="author",
                    target_entity="NonExistent",
                    target_class_name="NonExistent",
                    cardinality="1:N",
                ),
            ),
        )
        service_ir = ServiceIR(
            service_name="blog",
            version="1.0.0",
            models=(post_model,),
        )

        with pytest.raises(IRBuilderError) as exc_info:
            resolver.topological_sort_models(service_ir)
        assert exc_info.value.error_code == "ERR_IR_DEPENDENCY_UNKNOWN_MODEL"

    def test_topological_sort_cycle_error(self, resolver: DependencyResolver):
        a_model = IRModel(
            name="A",
            class_name="A",
            table_name="a",
            fields=(),
            relationships=(
                IRRelationship(
                    name="b",
                    original_name="b",
                    target_entity="B",
                    target_class_name="B",
                    cardinality="1:1",
                    is_circular=False,
                ),
            ),
        )
        b_model = IRModel(
            name="B",
            class_name="B",
            table_name="b",
            fields=(),
            relationships=(
                IRRelationship(
                    name="a",
                    original_name="a",
                    target_entity="A",
                    target_class_name="A",
                    cardinality="1:1",
                    is_circular=False,
                ),
            ),
        )
        service_ir = ServiceIR(service_name="cycle", version="1.0.0", models=(a_model, b_model))

        with pytest.raises(IRBuilderError) as exc_info:
            resolver.topological_sort_models(service_ir)
        assert exc_info.value.error_code == "ERR_IR_DEPENDENCY_CYCLE"

    def test_compute_import_manifest(self, resolver: DependencyResolver):
        user_model = IRModel(
            name="User",
            class_name="User",
            table_name="users",
            fields=(
                IRField(name="created_at", original_name="created_at", python_type="datetime.datetime", sql_type="DateTime"),
                IRField(name="id", original_name="id", python_type="uuid.UUID", sql_type="Uuid"),
                IRField(name="meta", original_name="meta", python_type="dict[str, Any]", sql_type="JSON"),
            ),
            relationships=(
                IRRelationship(
                    name="profile",
                    original_name="profile",
                    target_entity="Profile",
                    target_class_name="Profile",
                    cardinality="1:1",
                    is_circular=True,
                ),
            ),
        )
        profile_model = IRModel(
            name="Profile",
            class_name="Profile",
            table_name="profiles",
            fields=(),
        )
        service_ir = ServiceIR(service_name="test", version="1.0.0", models=(user_model, profile_model))

        imports = resolver.compute_import_manifest(user_model, service_ir)
        assert "from typing import TYPE_CHECKING" in imports["standard"]
        assert "import datetime" in imports["standard"]
        assert "import uuid" in imports["standard"]
        assert "from typing import Any" in imports["standard"]
        assert "from .profile import Profile" in imports["type_checking_models"]

    def test_compute_import_manifest_unknown_model_error(self, resolver: DependencyResolver):
        user_model = IRModel(
            name="User",
            class_name="User",
            table_name="users",
            fields=(),
            relationships=(
                IRRelationship(
                    name="ghost",
                    original_name="ghost",
                    target_entity="Ghost",
                    target_class_name="Ghost",
                    cardinality="1:1",
                ),
            ),
        )
        service_ir = ServiceIR(service_name="test", version="1.0.0", models=(user_model,))

        with pytest.raises(IRBuilderError) as exc_info:
            resolver.compute_import_manifest(user_model, service_ir)
        assert exc_info.value.error_code == "ERR_IR_IMPORT_UNKNOWN_MODEL"


# =============================================================================
# 5. IR Builder Tests
# =============================================================================


class TestIRBuilder:
    @pytest.fixture
    def builder(self) -> IRBuilder:
        return IRBuilder()

    def test_build_empty_identity_validation_errors(self, builder: IRBuilder):
        manifest_empty_name = ManifestSpec(service_name="", version="1.0.0", entities=())
        with pytest.raises(IRBuilderError) as exc1:
            builder.build(manifest_empty_name)
        assert exc1.value.error_code == "ERR_IR_EMPTY_SERVICE_NAME"

        manifest_empty_version = ManifestSpec(service_name="svc", version="   ", entities=())
        with pytest.raises(IRBuilderError) as exc2:
            builder.build(manifest_empty_version)
        assert exc2.value.error_code == "ERR_IR_EMPTY_VERSION"

    def test_build_unknown_relationship_target_error(self, builder: IRBuilder):
        manifest = ManifestSpec(
            service_name="svc",
            version="1.0.0",
            entities=(
                EntitySpec(
                    name="User",
                    attributes=(AttributeSpec(name="id", type="int"),),
                    relationships=(
                        RelationshipSpec(name="rel", target_entity="Missing", cardinality="1:1"),
                    ),
                ),
            ),
        )
        with pytest.raises(IRBuilderError) as exc_info:
            builder.build(manifest)
        assert exc_info.value.error_code == "ERR_IR_UNKNOWN_RELATIONSHIP_TARGET"

    def test_build_full_service_ir_success(self, builder: IRBuilder):
        manifest = ManifestSpec(
            service_name="order_service",
            version="1.0.0",
            entities=(
                EntitySpec(
                    name="User",
                    attributes=(
                        AttributeSpec(name="id", type="int", primary_key=True),
                        AttributeSpec(name="status", type="str"),
                    ),
                    relationships=(
                        RelationshipSpec(name="orders", target_entity="Order", cardinality="1:N"),
                    ),
                    fsm=FSMSpec(
                        state_attribute="status",
                        initial_state="active",
                        states=("active", "suspended"),
                        transitions=(
                            TransitionSpec(
                                trigger="suspend",
                                source_state="active",
                                target_state="suspended",
                            ),
                        ),
                    ),
                ),
                EntitySpec(
                    name="Order",
                    attributes=(
                        AttributeSpec(name="id", type="int", primary_key=True),
                        AttributeSpec(name="user_id", type="int"),
                    ),
                    relationships=(
                        RelationshipSpec(
                            name="user",
                            target_entity="User",
                            cardinality="1:1",
                            foreign_key="user_id",
                        ),
                    ),
                ),
            ),
            business_rules=(
                BusinessRuleSpec(
                    name="rule1",
                    target_entity="User",
                    expression="status != 'suspended'",
                    error_message="User is suspended",
                ),
            ),
            workflows=(
                WorkflowSpec(
                    name="wf1",
                    steps=(
                        WorkflowStepSpec(name="step1", action="validate"),
                        WorkflowStepSpec(name="step2", action="process", depends_on=("step1",)),
                    ),
                ),
            ),
            policies=(
                PolicySpec(name="pol1", roles=("admin",), actions=("read", "write")),
            ),
        )

        service_ir = builder.build(manifest)

        assert service_ir.service_name == "order_service"
        assert len(service_ir.models) == 2
        assert len(service_ir.rules) == 1
        assert len(service_ir.workflows) == 1
        assert len(service_ir.policies) == 1

        user_model = next(m for m in service_ir.models if m.name == "User")
        assert user_model.fsm is not None
        assert user_model.fsm.initial_state == "active"

    def test_build_unexpected_exception_wrapped(self, builder: IRBuilder):
        manifest = ManifestSpec(service_name="svc", version="1.0.0", entities=())
        with mock.patch("meta_service_generator.ir.builder.ensure_unique_identifiers", side_effect=RuntimeError("unexpected")):
            with pytest.raises(IRBuilderError) as exc_info:
                builder.build(manifest)
            assert exc_info.value.error_code == "ERR_IR_BUILD_FAILED"