"""Semantic validator tests operating on the typed WorkflowManifestSpec contract."""

import pytest
from pydantic import ValidationError

from meta_compiler.core.models import TaskNodeSpec, WorkflowManifestSpec
from meta_compiler.stages.semantic_validator import (
    ManifestSemanticError,
    ManifestSemanticValidator,
)


def _manifest(*tasks: TaskNodeSpec) -> WorkflowManifestSpec:
    return WorkflowManifestSpec(
        version="v1",
        namespace="ns",
        name="wf",
        entities={},
        fsms={},
        tasks=tasks,
    )


def test_valid_manifest_passes() -> None:
    manifest = _manifest(
        TaskNodeSpec(id="a", action="alpha"),
        TaskNodeSpec(id="b", action="beta", depends_on=("a",)),
    )
    ManifestSemanticValidator().validate(manifest)


def test_self_dependency_rejected_at_model_boundary() -> None:
    with pytest.raises(ValidationError):
        TaskNodeSpec(id="a", action="alpha", depends_on=("a",))


def test_missing_dependency_rejected_at_model_boundary() -> None:
    with pytest.raises(ValidationError):
        _manifest(TaskNodeSpec(id="a", action="alpha", depends_on=("ghost",)))


def test_input_artifact_references_missing_source_task() -> None:
    from meta_compiler.core.models import ArtifactRefSpec, ArtifactSourceSpec

    manifest = _manifest(
        TaskNodeSpec(
            id="a",
            action="alpha",
            inputs=(
                ArtifactRefSpec(
                    name="in",
                    type="int",
                    source=ArtifactSourceSpec(task_id="ghost", artifact_name="out"),
                ),
            ),
        )
    )
    with pytest.raises(ManifestSemanticError):
        ManifestSemanticValidator().validate(manifest)


def test_input_artifact_type_mismatch_with_source_output() -> None:
    from meta_compiler.core.models import ArtifactRefSpec, ArtifactSourceSpec

    manifest = _manifest(
        TaskNodeSpec(
            id="producer",
            action="alpha",
            outputs=(ArtifactRefSpec(name="out", type="int"),),
        ),
        TaskNodeSpec(
            id="consumer",
            action="beta",
            depends_on=("producer",),
            inputs=(
                ArtifactRefSpec(
                    name="in",
                    type="str",
                    source=ArtifactSourceSpec(task_id="producer", artifact_name="out"),
                ),
            ),
        ),
    )
    with pytest.raises(ManifestSemanticError):
        ManifestSemanticValidator().validate(manifest)
