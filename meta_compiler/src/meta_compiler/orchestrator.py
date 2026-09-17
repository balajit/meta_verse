"""Pipeline orchestrator module for meta_compiler.

Exposes a decoupled API separating in-memory ManifestIR compilation from
database registration, supporting dry runs, CI validation, previews, and transactional persistence.
"""

import logging
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from meta_compiler.config import CompilerSettings
from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.ir import ManifestIR
from meta_compiler.core.models import (
    CompiledExecutionGraph,
    ExecutionPlan,
    NodeExecutionMetadata,
    WorkflowManifestSpec,
)
from meta_compiler.engine import MetaCompiler
from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.persistence.repository import WorkflowRepository
from meta_compiler.stages.contract_checker import ContractChecker
from meta_compiler.stages.db_serializer import to_db_payload

logger = logging.getLogger("meta_compiler.orchestrator")

PreCommitGuardHook = Callable[[dict[str, Any]], Awaitable[None]]


@runtime_checkable
class CompilerConfigProvider(Protocol):
    """Structural protocol matching host containers supplying compiler_settings."""

    compiler_settings: CompilerSettings


class PipelineCompilationError(MetaCompilerError):
    """Raised when any stage of the compilation pipeline encounters a fatal failure."""

    def __init__(self, stage: str, message: str, details: Any = None) -> None:
        super().__init__(message=f"[{stage}] {message}", details=details)
        self.stage = stage


class CompiledWorkflowDefinition(BaseModel):
    """Pure in-memory compiler artifact output representing a validated workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    manifest_spec: WorkflowManifestSpec | None = None
    execution_plan: ExecutionPlan
    raw_manifest: dict[str, Any]
    pinned_dependencies: dict[str, Any] | None = None
    version_vector: dict[str, Any] | None = None


_EMPTY_EXECUTION_PLAN = ExecutionPlan(
    stages=(),
    critical_path=(),
    roots=(),
    leaves=(),
)


class MetaCompilerPipeline:
    """Engine wrapper supporting hosted lifespan injection and standalone execution."""

    def __init__(self, settings: CompilerSettings | None = None) -> None:
        self.settings = settings or CompilerSettings()

    @classmethod
    def from_provider(cls, provider: Any) -> "MetaCompilerPipeline":
        """Factory extracting CompilerSettings dynamically from a host container or dict."""
        if isinstance(provider, CompilerSettings):
            return cls(settings=provider)

        cfg = getattr(provider, "compiler_settings", None)
        if isinstance(cfg, CompilerSettings):
            return cls(settings=cfg)

        if isinstance(provider, dict) and isinstance(
            provider.get("compiler_settings"), CompilerSettings
        ):
            return cls(settings=provider["compiler_settings"])

        return cls(settings=CompilerSettings())

    def compile(
        self,
        manifest_input: ManifestIR | str | dict[str, Any],
        registry: ActionRegistry | None = None,
        pinned_dependencies: dict[str, Any] | None = None,
        version_vector: dict[str, Any] | None = None,
        schemas: dict[str, dict[str, Any]] | None = None,
        schema_dir: str | Path | None = None,
        schema_paths: dict[str, str | Path] | None = None,
    ) -> CompiledWorkflowDefinition:
        return compile_manifest(
            manifest_input,
            registry=registry,
            pinned_dependencies=pinned_dependencies,
            version_vector=version_vector,
            settings=self.settings,
            schemas=schemas,
            schema_dir=schema_dir,
            schema_paths=schema_paths,
        )

    async def compile_and_register(
        self,
        manifest_input: ManifestIR | str | dict[str, Any],
        session: AsyncSession,
        registry: ActionRegistry | None = None,
        pinned_dependencies: dict[str, Any] | None = None,
        version_vector: dict[str, Any] | None = None,
        pre_commit_guard: PreCommitGuardHook | None = None,
        schemas: dict[str, dict[str, Any]] | None = None,
        schema_dir: str | Path | None = None,
        schema_paths: dict[str, str | Path] | None = None,
    ) -> CompiledExecutionGraph:
        return await compile_and_register_manifest(
            manifest_input,
            session,
            registry=registry,
            pinned_dependencies=pinned_dependencies,
            version_vector=version_vector,
            pre_commit_guard=pre_commit_guard,
            settings=self.settings,
            schemas=schemas,
            schema_dir=schema_dir,
            schema_paths=schema_paths,
        )


def compile_manifest(
    manifest_input: ManifestIR | str | dict[str, Any],
    registry: ActionRegistry | None = None,
    pinned_dependencies: dict[str, Any] | None = None,
    version_vector: dict[str, Any] | None = None,
    settings: CompilerSettings | None = None,
    schemas: dict[str, dict[str, Any]] | None = None,
    schema_dir: str | Path | None = None,
    schema_paths: dict[str, str | Path] | None = None,
) -> CompiledWorkflowDefinition:
    """Executes in-memory compilation pipeline consuming ManifestIR or raw inputs without DB side-effects."""
    start_time = time.perf_counter()
    active_settings = settings or CompilerSettings()

    if isinstance(manifest_input, ManifestIR):
        raw_input: str | dict[str, Any] = manifest_input.to_dict()
    elif isinstance(manifest_input, str):
        raw_input = manifest_input
    elif isinstance(manifest_input, dict):
        raw_input = manifest_input
    else:
        raise PipelineCompilationError(
            "Syntax Guard",
            f"Unsupported manifest input type: {type(manifest_input).__name__}",
            details=[{"received_type": type(manifest_input).__name__}],
        )

    namespace = raw_input.get("namespace", "unknown") if isinstance(raw_input, dict) else "unknown"
    name = raw_input.get("name", "unknown") if isinstance(raw_input, dict) else "unknown"

    logger.info(
        "Beginning in-memory workflow manifest compilation for '%s/%s'",
        namespace,
        name,
        extra={"event": "orchestrator.compile_start", "namespace": namespace, "name": name},
    )

    engine = MetaCompiler(settings=active_settings, registry=registry)
    if schemas is not None:
        engine.register_schemas(schemas, base_dir=schema_dir, path_map=schema_paths)
    elif schema_dir is not None or schema_paths is not None:
        # Allow path-only seeding (e.g., virtual hierarchy without schemas yet)
        # No-op if schemas empty, but ensures schema_dir is set for bundler gating
        if schema_dir is not None:
            engine.schema_dir = Path(schema_dir).resolve()
        if schema_paths:
            for k, p in schema_paths.items():
                engine.schema_file_index[k] = Path(p).resolve()
            if engine.schema_dir is None:
                import os

                try:
                    common = os.path.commonpath([str(Path(p).resolve()) for p in schema_paths.values()])
                    engine.schema_dir = Path(common).resolve() if Path(common).is_dir() else Path(common).parent.resolve()
                except Exception:
                    pass
    try:
        context = engine.compile_sync(raw_input)
    except PipelineCompilationError:
        raise
    except Exception as err:
        logger.error("Unified pipeline compilation failed for '%s/%s': %s", namespace, name, err)
        raise PipelineCompilationError(
            "Model/Topology Compiler", str(err), details=[{"error": str(err)}]
        ) from err

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "In-memory compilation completed successfully for '%s/%s' in %.2fms",
        namespace,
        name,
        duration_ms,
        extra={
            "event": "orchestrator.compile_success",
            "namespace": namespace,
            "name": name,
            "duration_ms": duration_ms,
        },
    )

    return CompiledWorkflowDefinition(
        manifest_spec=(
            context.manifest_spec
            if isinstance(context.manifest_spec, WorkflowManifestSpec)
            else None
        ),
        execution_plan=context.execution_plan or _EMPTY_EXECUTION_PLAN,
        raw_manifest=context.raw_input if isinstance(context.raw_input, dict) else {},
        pinned_dependencies=pinned_dependencies,
        version_vector=version_vector,
    )


async def register_workflow(
    compiled_def: CompiledWorkflowDefinition,
    session: AsyncSession,
    *,
    pre_commit_guard: PreCommitGuardHook | None = None,
) -> UUID:
    """Persists a compiled definition after executing an optional pre-commit guard callback."""
    start_time = time.perf_counter()
    try:
        if pre_commit_guard is not None and compiled_def.pinned_dependencies:
            logger.info(
                "Executing pre-commit snapshot drift validation hook...",
                extra={"event": "orchestrator.pre_commit_guard_start"},
            )
            await pre_commit_guard(compiled_def.pinned_dependencies)

        payload = to_db_payload(compiled_def)
        if compiled_def.pinned_dependencies:
            payload["pinned_dependencies"] = compiled_def.pinned_dependencies
        if compiled_def.version_vector:
            payload["version_vector"] = compiled_def.version_vector

        repo = WorkflowRepository(session)
        record_uuid = await repo.persist_workflow_definition(payload)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Registered workflow definition successfully (ID: %s) in %.2fms",
            record_uuid,
            duration_ms,
            extra={
                "event": "orchestrator.register_success",
                "record_uuid": str(record_uuid),
                "duration_ms": duration_ms,
            },
        )
        return record_uuid

    except MetaCompilerError:
        raise
    except Exception as err:
        logger.error(
            "Failed to register workflow definition in database: %s",
            err,
            extra={"event": "orchestrator.register_failure", "error": str(err)},
        )
        raise PipelineCompilationError(
            "Database Serializer", str(err), details=[{"error": str(err)}]
        ) from err


async def compile_and_register_manifest(
    manifest_input: ManifestIR | str | dict[str, Any],
    session: AsyncSession,
    registry: ActionRegistry | None = None,
    pinned_dependencies: dict[str, Any] | None = None,
    version_vector: dict[str, Any] | None = None,
    pre_commit_guard: PreCommitGuardHook | None = None,
    settings: CompilerSettings | None = None,
    schemas: dict[str, dict[str, Any]] | None = None,
    schema_dir: str | Path | None = None,
    schema_paths: dict[str, str | Path] | None = None,
) -> CompiledExecutionGraph:
    """End-to-end orchestration pipeline taking ManifestIR or raw inputs, compiling, and persisting."""
    start_time = time.perf_counter()
    active_settings = settings or CompilerSettings()

    compiled_def = compile_manifest(
        manifest_input,
        registry=registry,
        pinned_dependencies=pinned_dependencies,
        version_vector=version_vector,
        settings=active_settings,
        schemas=schemas,
        schema_dir=schema_dir,
        schema_paths=schema_paths,
    )

    # Build Hamilton node metadata BEFORE persistence so that every
    # compilation/validation stage (including driver synthesis) has completed
    # successfully prior to any database write.
    nodes_meta: dict[str, NodeExecutionMetadata] = {}

    if compiled_def.manifest_spec:
        action_reg = registry or ActionRegistry()
        contract_checker = ContractChecker(action_reg)
        driver, module_name = contract_checker.build_hamilton_driver(compiled_def.manifest_spec)
        try:
            raw_vars = driver.list_available_variables()
            nodes_meta = {}
            for var in raw_vars:
                deps: Any = getattr(var, "dependencies", None)
                if deps is None:
                    deps = getattr(var, "required_dependencies", set())
                if isinstance(deps, set):
                    dep_names = sorted(str(d) for d in deps)
                else:
                    dep_names = [d.name if hasattr(d, "name") else str(d) for d in deps]  # type: ignore[union-attr]
                nodes_meta[var.name] = NodeExecutionMetadata(
                    node_id=var.name,
                    inputs=dep_names,
                    output_type=str(getattr(var, "type", "object")),
                )
        finally:
            sys.modules.pop(module_name, None)

    record_uuid = await register_workflow(compiled_def, session, pre_commit_guard=pre_commit_guard)

    # Flush inserts and commit the transaction only after every validation and
    # compilation stage completed successfully.
    await session.commit()

    namespace = compiled_def.raw_manifest.get("namespace", "default")
    name = compiled_def.raw_manifest.get("name", "unnamed")
    version = str(compiled_def.raw_manifest.get("version", "v1"))

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "End-to-end compilation and registration succeeded for '%s/%s' (Record ID: %s) in %.2fms",
        namespace,
        name,
        record_uuid,
        duration_ms,
        extra={
            "event": "orchestrator.compile_and_register_success",
            "record_id": str(record_uuid),
            "duration_ms": duration_ms,
            "node_count": len(nodes_meta),
        },
    )

    return CompiledExecutionGraph(
        manifest_id=str(record_uuid),
        namespace=namespace,
        name=name,
        version=version,
        nodes=nodes_meta,
        db_record_id=str(record_uuid),
        metadata={
            "node_count": len(nodes_meta),
            "has_pinned_dependencies": compiled_def.pinned_dependencies is not None,
            "has_version_vector": compiled_def.version_vector is not None,
        },
    )
