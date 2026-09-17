"""Workflow definition mutation boundary.

Routing rule (Review Scope Item 1): every state transition of a stored workflow
definition is append-only and must flow through this module at the repo
boundary. Compiled definitions are immutable; a "mutation" produces a NEW
definition row with a bumped version, guarded by a pinned-dependency drift
check against the currently published snapshot before the row is inserted.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.orchestrator import CompiledWorkflowDefinition
from meta_compiler.persistence.repository import WorkflowRepository
from meta_compiler.stages.db_serializer import to_db_payload

logger = logging.getLogger("meta_compiler.persistence.mutator")

PreCommitGuardHook = Callable[[dict[str, Any]], Awaitable[None]]


class MutationGuardError(MetaCompilerError):
    """Raised when a mutation violates the pinned-dependency snapshot contract."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details)


def compute_version_vector(pinned_dependencies: dict[str, Any]) -> dict[str, str]:
    """Produces a ``{dependency_name: pinned_version}`` vector from a dependency snapshot."""
    version_vector: dict[str, str] = {}
    for dep_name, dep_snapshot in pinned_dependencies.items():
        version = (
            dep_snapshot.get("version", "unknown") if isinstance(dep_snapshot, dict) else "unknown"
        )
        version_vector[str(dep_name)] = str(version)
    return version_vector


def assert_no_pinned_dependency_drift(
    version_vector: dict[str, str],
    current_versions: dict[str, str],
) -> None:
    """Fails the mutation if any pinned dependency has drifted from the published state."""
    drifted = {
        dep_name: {"pinned": pinned_version, "current": current_versions.get(dep_name)}
        for dep_name, pinned_version in version_vector.items()
        if current_versions.get(dep_name) != pinned_version
    }
    if drifted:
        logger.error(
            "Mutation blocked: pinned dependency drift detected: %s",
            drifted,
            extra={"event": "mutator.drift_blocked", "drifted": drifted},
        )
        raise MutationGuardError(
            message=(
                "Cannot mutate workflow: pinned dependency snapshot has drifted from "
                "the published registry state."
            ),
            details={"drifted_dependencies": drifted},
        )


def build_mutated_payload(
    base_payload: dict[str, Any],
    manifest_patch: dict[str, Any],
    new_version: str,
    pinned_dependencies: dict[str, Any] | None = None,
    version_vector: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Applies an append-only mutation to a definition payload producing a new row payload.

    The ``id`` is regenerated (a mutation creates a new record), the version is
    bumped to ``new_version``, and provenance vectors are carried forward or
    recomputed from the pinned dependency snapshot.
    """
    merged_manifest = dict(base_payload.get("compiled_manifest") or {})
    merged_manifest.update(manifest_patch)

    mutated: dict[str, Any] = dict(base_payload)
    mutated["compiled_manifest"] = merged_manifest
    mutated["version"] = new_version

    if pinned_dependencies is not None:
        mutated["pinned_dependencies"] = pinned_dependencies
    if version_vector is not None:
        mutated["version_vector"] = version_vector
    elif pinned_dependencies:
        mutated["version_vector"] = compute_version_vector(pinned_dependencies)

    return mutated


class WorkflowDefinitionMutator:
    """Append-only mutation handler that routes transitions through the repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = WorkflowRepository(session)

    async def register_mutation(
        self,
        compiled_def: CompiledWorkflowDefinition,
        manifest_patch: dict[str, Any],
        new_version: str,
        *,
        current_versions: dict[str, str] | None = None,
        pre_commit_guard: PreCommitGuardHook | None = None,
    ) -> UUID:
        """Persists a new, mutated definition row after verifying snapshot drift."""
        start_time = time.perf_counter()

        pinned = compiled_def.pinned_dependencies or {}
        version_vector = compiled_def.version_vector or compute_version_vector(pinned)

        if current_versions is not None:
            assert_no_pinned_dependency_drift(version_vector, current_versions)

        if pre_commit_guard is not None and pinned:
            await pre_commit_guard(pinned)

        base_payload = to_db_payload(compiled_def)
        mutated_payload = build_mutated_payload(
            base_payload,
            manifest_patch=manifest_patch,
            new_version=new_version,
            pinned_dependencies=pinned or None,
            version_vector=version_vector,
        )

        record_uuid = await self._repo.persist_workflow_definition(mutated_payload)

        logger.info(
            "Registered mutated workflow definition (ID: %s, version: %s) in %.2fms",
            record_uuid,
            new_version,
            (time.perf_counter() - start_time) * 1000,
            extra={
                "event": "mutator.register_mutation_success",
                "record_uuid": str(record_uuid),
                "version": new_version,
            },
        )
        return record_uuid
