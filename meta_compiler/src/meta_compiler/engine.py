"""Overarching MetaCompiler Engine Facade.

Serves as the single orchestrator executing the compiler stage pipeline,
cross-cutting hooks, and optional database persistence behind an atomic
interface with full telemetry.

The engine is the ONLY orchestration entry point: manifest compilation,
semantic validation, topology planning, adapter-based self-healing, contract
verification, serialization, and persistence all flow through the stage list.
"""

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opentelemetry.trace import Status, StatusCode
from sqlalchemy.ext.asyncio import AsyncSession

from meta_compiler.config import CompilerSettings
from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.models import CompiledExecutionGraph
from meta_compiler.core.telemetry import get_tracer
from meta_compiler.exceptions import ContractValidationError, MetaCompilerError
from meta_compiler.hooks.base import BaseCompilerHook
from meta_compiler.persistence.repository import WorkflowRepository
from meta_compiler.stages.adapter_synthesizer import AdapterSynthesizerStage
from meta_compiler.stages.base import BaseCompilerStage
from meta_compiler.stages.contract_checker import ContractCheckerStage
from meta_compiler.stages.db_serializer import DBSerializerStage
from meta_compiler.stages.model_compiler import ModelCompilerStage
from meta_compiler.stages.schema_synthesis import SchemaSynthesisStage
from meta_compiler.stages.semantic_validator import SemanticValidatorStage
from meta_compiler.stages.syntax_guard import SyntaxGuardStage
from meta_compiler.stages.topology_validator import TopologyValidatorStage

logger = logging.getLogger("meta_compiler.engine")
tracer = get_tracer("meta_compiler.engine")

# Stages executed within the validation / self-healing loop. Order matters:
# synthesis and model compilation must precede semantic/topology/contract checks,
# and adapter synthesis runs after contract diagnostics to rewire and reconverge.
_VALIDATION_STAGE_CLASSES: list[type[BaseCompilerStage]] = [
    SyntaxGuardStage,
    SchemaSynthesisStage,
    ModelCompilerStage,
    SemanticValidatorStage,
    TopologyValidatorStage,
    ContractCheckerStage,
]

# Terminal stage executed once all validation stages have converged.
_TERMINAL_STAGE_CLASSES: list[type[BaseCompilerStage]] = [
    DBSerializerStage,
]


class MetaCompiler:
    """Overarching Meta Compiler Engine Facade.

    Serves as the single, fully encapsulated building block for host application
    integration. Manages pipeline execution, cross-cutting hooks, and DB persistence.
    """

    def __init__(
        self,
        settings: CompilerSettings | None = None,
        registry: ActionRegistry | None = None,
        hooks: list[BaseCompilerHook] | None = None,
        custom_stage_classes: list[type[BaseCompilerStage]] | None = None,
    ) -> None:
        self.settings = settings or CompilerSettings()
        self.registry = registry or ActionRegistry()
        self.hooks: list[BaseCompilerHook] = hooks or []
        self.raw_schemas: dict[str, dict] = {}
        self.schema_dir: Path | None = None
        self.schema_file_index: dict[str, Path] = {}

        if custom_stage_classes is not None:
            self._validation_stage_classes = list(custom_stage_classes)
            self._terminal_stage_classes: list[type[BaseCompilerStage]] = []
        else:
            self._validation_stage_classes = list(_VALIDATION_STAGE_CLASSES)
            self._terminal_stage_classes = list(_TERMINAL_STAGE_CLASSES)

        logger.info(
            "Initialized MetaCompiler engine facade with %d validation stages and %d hooks",
            len(self._validation_stage_classes),
            len(self.hooks),
            extra={
                "event": "engine.initialized",
                "stage_count": len(self._validation_stage_classes),
                "hook_count": len(self.hooks),
                "environment": self.settings.environment,
            },
        )

    def load_raw_schemas(self, schema_dir: str | Path) -> int:
        """Ingests raw JSON schemas from disk into memory without dynamic synthesis."""
        with tracer.start_as_current_span("MetaCompiler.load_raw_schemas") as span:
            schema_path = Path(schema_dir).resolve()
            span.set_attribute("schema.root_path", str(schema_path))

            if not schema_path.exists() or not schema_path.is_dir():
                err_msg = f"Schema directory not found: {schema_path}"
                span.set_status(Status(StatusCode.ERROR, err_msg))
                raise FileNotFoundError(err_msg)

            loaded_count = 0
            self.schema_dir = schema_path
            self.schema_file_index.clear()
            for json_path in schema_path.rglob("*.json"):
                relative = json_path.relative_to(schema_path).with_suffix("")
                action_key = str(relative).replace("/", ".").replace("\\", ".")

                try:
                    schema_data = json.loads(json_path.read_text(encoding="utf-8"))
                    self.raw_schemas[action_key] = schema_data
                    self.schema_file_index[action_key] = json_path
                    loaded_count += 1
                except Exception as err:
                    logger.warning(
                        "Failed to parse schema JSON at %s: %s",
                        json_path,
                        err,
                        extra={"event": "engine.schema_parse_failure", "path": str(json_path)},
                    )

            if not self.raw_schemas:
                err_msg = f"No valid JSON schema files found in directory: {schema_path}"
                span.set_status(Status(StatusCode.ERROR, err_msg))
                raise MetaCompilerError(err_msg)

            span.set_attribute("schema.loaded_count", loaded_count)
            logger.info(
                "Successfully loaded %d raw JSON schemas into engine.",
                loaded_count,
                extra={"event": "engine.schemas_loaded", "count": loaded_count},
            )
            return loaded_count

    def register_schema(
        self,
        action_key: str,
        schema: dict[str, Any],
        source_path: str | Path | None = None,
    ) -> None:
        """Register a single JSON schema with its logical file path.

        The ``source_path`` preserves the ``shopping/types/buyer.json``-style
        hierarchy needed for relative ``$ref`` resolution when the engine is
        embedded in a larger application that owns schemas in-memory (DB/S3).
        """
        if not action_key or not isinstance(action_key, str):
            raise ValueError("action_key must be a non-empty string")
        if not isinstance(schema, dict):
            raise ValueError("schema must be a dict")
        self.raw_schemas[action_key] = schema
        if source_path is not None:
            resolved = Path(source_path).resolve() if Path(source_path).is_absolute() else (Path.cwd() / source_path).resolve()
            # If source_path is relative like shopping/types/buyer.json, keep it
            # relative to cwd for determinism, but store resolved absolute.
            self.schema_file_index[action_key] = resolved
            # Auto-infer schema_dir if not set
            if self.schema_dir is None:
                # Heuristic: strip the action_key suffix to get base
                try:
                    rel = Path(action_key.replace(".", "/") + ".json")
                    # If resolved path ends with rel, base is parent remainder
                    if str(resolved).endswith(str(rel)):
                        self.schema_dir = Path(str(resolved)[: -len(str(rel))].rstrip("/")) or Path.cwd()
                    else:
                        self.schema_dir = resolved.parent
                except Exception:
                    self.schema_dir = resolved.parent
        else:
            # No explicit path — synthesize virtual path under schema_dir or cwd
            base = self.schema_dir or Path.cwd()
            virtual = (base / (action_key.replace(".", "/") + ".json")).resolve()
            self.schema_file_index[action_key] = virtual
            if self.schema_dir is None:
                self.schema_dir = base.resolve()

    def register_schemas(
        self,
        schemas: dict[str, dict[str, Any]],
        *,
        base_dir: str | Path | None = None,
        path_map: dict[str, str | Path] | None = None,
        clear_existing: bool = False,
    ) -> int:
        """Bulk-register schemas with optional path context (auto-infer with explicit override).

        Args:
            schemas: Mapping ``action_key -> JSON schema dict``.
            base_dir: Explicit ``schema_dir`` override. If ``None`` and ``path_map``
                is given, inferred as common ancestor of all resolved paths.
            path_map: Per-action ``action_key -> source_path``. If omitted,
                paths are synthesized as ``base_dir/action_key.replace(".","/")+".json"``.
            clear_existing: If ``True``, clears prior ``raw_schemas``/``file_index``
                before registering (mirrors ``load_raw_schemas`` semantics).

        Returns:
            Number of schemas registered.
        """
        import os

        if not isinstance(schemas, dict):
            raise ValueError("schemas must be a dict[str, dict]")
        if clear_existing:
            self.raw_schemas.clear()
            self.schema_file_index.clear()
            if base_dir is not None:
                self.schema_dir = Path(base_dir).resolve()

        # Resolve all paths first to allow common-ancestor inference
        resolved_map: dict[str, Path] = {}
        for key in schemas:
            raw_path = (path_map or {}).get(key) if path_map else None
            if raw_path is not None:
                p = Path(raw_path)
                resolved_map[key] = p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()
            elif base_dir is not None:
                resolved_map[key] = (Path(base_dir) / (key.replace(".", "/") + ".json")).resolve()
            elif self.schema_dir is not None:
                resolved_map[key] = (self.schema_dir / (key.replace(".", "/") + ".json")).resolve()
            else:
                # No base — will be inferred after loop if possible, else cwd
                resolved_map[key] = (Path.cwd() / (key.replace(".", "/") + ".json")).resolve()

        # Auto-infer schema_dir from resolved_map if not explicitly overridden
        if base_dir is not None:
            self.schema_dir = Path(base_dir).resolve()
        elif path_map is not None and resolved_map:
            try:
                common = os.path.commonpath([str(p) for p in resolved_map.values()])
                common_p = Path(common)
                # If commonpath is a file (has suffix), use its parent
                if common_p.suffix == ".json":
                    common_p = common_p.parent
                # Keep virtual path even if it doesn't exist on disk (in-memory schemas)
                self.schema_dir = common_p.resolve()
            except Exception:
                first = next(iter(resolved_map.values()))
                self.schema_dir = first.parent.resolve()
        elif self.schema_dir is None and resolved_map:
            # No explicit base_dir/path_map inference, but need a dir for bundler gate
            first = next(iter(resolved_map.values()))
            self.schema_dir = first.parent.resolve()

        for key, schema in schemas.items():
            self.raw_schemas[key] = schema
            self.schema_file_index[key] = resolved_map[key]

        logger.info(
            "Registered %d schemas via register_schemas (base_dir=%s).",
            len(schemas),
            str(self.schema_dir) if self.schema_dir else None,
            extra={"event": "engine.schemas_registered", "count": len(schemas), "base_dir": str(self.schema_dir) if self.schema_dir else None},
        )
        return len(schemas)

    def write_per_file_schemas(self, out_root: str | Path, clear_output: bool = True) -> list[Path]:
        """Emit one ``.py`` per JSON schema mirroring hierarchy with cross-file imports."""
        from meta_compiler.stages.per_file_writer import write_per_file_schemas

        return write_per_file_schemas(
            raw_schemas=self.raw_schemas,
            file_index=self.schema_file_index,
            schema_dir=self.schema_dir,
            out_root=Path(out_root),
            clear_output=clear_output,
        )

    def register_action(
        self, action_name: str, callable_func: Callable[..., Any], **kwargs: Any
    ) -> None:
        """Convenience delegation to register domain actions into the underlying registry."""
        self.registry.register(action_name, callable_func, **kwargs)
        logger.debug(
            "Registered domain action '%s' via engine facade",
            action_name,
            extra={"event": "engine.action_registered", "action_name": action_name},
        )

    def add_hook(self, hook: BaseCompilerHook) -> None:
        """Inject cross-cutting concerns (security checks, telemetry, audit logs)."""
        if not isinstance(hook, BaseCompilerHook):
            raise TypeError(f"Hook must inherit from BaseCompilerHook, got {type(hook)}")
        self.hooks.append(hook)
        logger.debug(
            "Added hook '%s' to engine facade",
            hook.__class__.__name__,
            extra={"event": "engine.hook_added", "hook_class": hook.__class__.__name__},
        )

    def _instantiate_pipeline(self) -> list[BaseCompilerStage]:
        """Return all stage instances for a compilation pass (validation + terminal)."""
        return self._instantiate_validation_stages() + self._instantiate_terminal_stages()

    def _instantiate_validation_stages(self) -> list[BaseCompilerStage]:
        """Factory producing fresh validation stage instances per compilation pass."""
        return [stage_cls() for stage_cls in self._validation_stage_classes]

    def _instantiate_terminal_stages(self) -> list[BaseCompilerStage]:
        """Factory producing fresh terminal stage instances per compilation pass."""
        return [stage_cls() for stage_cls in self._terminal_stage_classes]

    def _instantiate_adapter_stage(self) -> AdapterSynthesizerStage:
        """Factory producing the adapter self-healing stage instance."""
        return AdapterSynthesizerStage()

    def _run_validation_loop_sync(
        self,
        context: CompilationContext,
        execute_stage: Callable[[BaseCompilerStage], None],
        validation_stages: list[BaseCompilerStage],
        adapter_stage: AdapterSynthesizerStage,
    ) -> None:
        """Runs the converging validation stages, applying adapter rewiring until clean.

        Stages preceding model compilation (syntax guard, schema synthesis) run once;
        the model-compilation onward sub-pipeline is re-run after each adapter pass so
        newly synthesized adapters are reflected in the compiled manifest.
        """
        model_index = self._model_compilation_index()

        def _run_from(index: int) -> None:
            for stage in validation_stages[index:]:
                execute_stage(stage)

        _run_from(0)

        while context.requires_reprocessing:
            if context.reprocess_counter >= context.max_reprocess_attempts:
                err_msg = (
                    f"Pipeline failed to converge after "
                    f"{context.max_reprocess_attempts} reprocess attempts."
                )
                logger.error(
                    "%s",
                    err_msg,
                    extra={
                        "event": "engine.convergence_failure",
                        "max_attempts": context.max_reprocess_attempts,
                        "context_id": str(context.context_id),
                    },
                )
                raise ContractValidationError(err_msg)

            if context.diagnostics:
                with tracer.start_as_current_span("MetaCompiler.adapter_reprocess") as repair_span:
                    repair_span.set_attribute("adapter.mismatch_count", len(context.diagnostics))
                    execute_stage(adapter_stage)
                    context.diagnostics.clear()

            context.reprocess_counter += 1
            context.requires_reprocessing = False
            _run_from(model_index)

    def _model_compilation_index(self) -> int:
        """Index of the model-compilation stage within the validation pipeline."""
        for index, stage_cls in enumerate(self._validation_stage_classes):
            if stage_cls is ModelCompilerStage:
                return index
        return 0

    async def _safe_execute_error_hooks(
        self, context: CompilationContext, error: Exception
    ) -> None:
        """Executes error hooks safely without allowing secondary exceptions to mask primary errors."""
        with tracer.start_as_current_span("MetaCompiler._safe_execute_error_hooks") as span:
            span.set_attribute("context.id", str(context.context_id))
            span.set_attribute("error.type", type(error).__name__)
            for hook in self.hooks:
                try:
                    await hook.on_error(context, error)
                except Exception as hook_err:
                    span.record_exception(hook_err)
                    logger.error(
                        "Error hook '%s' failed during error handling: %s",
                        hook.__class__.__name__,
                        hook_err,
                        exc_info=True,
                        extra={
                            "event": "engine.hook_error_failure",
                            "hook_class": hook.__class__.__name__,
                            "primary_error": str(error),
                            "hook_error": str(hook_err),
                        },
                    )

    def _execute_stage_sync(self, context: CompilationContext, stage: BaseCompilerStage) -> None:
        """Executes a single stage with telemetry; the synchronous core primitive."""
        stage_name = stage.__class__.__name__
        stage_start = time.perf_counter()
        with tracer.start_as_current_span(f"Stage.{stage_name}") as stage_span:
            stage_span.set_attribute("context.id", str(context.context_id))
            logger.debug(
                "Executing stage '%s' for context %s",
                stage_name,
                context.context_id,
                extra={
                    "event": "engine.stage_start",
                    "stage": stage_name,
                    "context_id": str(context.context_id),
                },
            )
            stage.run(context, self.registry)
            stage_duration = (time.perf_counter() - stage_start) * 1000
            stage_span.set_attribute("stage.duration_ms", stage_duration)
            logger.debug(
                "Completed stage '%s' in %.2fms",
                stage_name,
                stage_duration,
                extra={
                    "event": "engine.stage_success",
                    "stage": stage_name,
                    "duration_ms": stage_duration,
                    "context_id": str(context.context_id),
                },
            )

    def _run_sync_pipeline(self, context: CompilationContext) -> None:
        """Runs the full sync stage pipeline (validation loop + terminal stage)."""
        validation_stages = self._instantiate_validation_stages()
        adapter_stage = self._instantiate_adapter_stage()
        terminal_stages = self._instantiate_terminal_stages()

        def _execute(stage: BaseCompilerStage) -> None:
            self._execute_stage_sync(context, stage)

        self._run_validation_loop_sync(
            context=context,
            execute_stage=_execute,
            validation_stages=validation_stages,
            adapter_stage=adapter_stage,
        )
        for stage in terminal_stages:
            _execute(stage)

    def compile_sync(self, manifest_input: str | dict[str, Any]) -> CompilationContext:
        """Sync entry point: runs the entire stage pipeline without hooks or persistence."""
        context = CompilationContext(
            raw_input=manifest_input,
            raw_schemas=self.raw_schemas.copy(),
            schema_dir=self.schema_dir,
            schema_file_index=dict(self.schema_file_index),
            registry=self.registry,
        )
        with tracer.start_as_current_span("MetaCompiler.compile_sync") as span:
            span.set_attribute("context.id", str(context.context_id))
            self._run_sync_pipeline(context)
            span.set_status(Status(StatusCode.OK))
        return context

    async def compile(
        self, manifest_input: str, session: AsyncSession | None = None
    ) -> CompiledExecutionGraph:
        """Atomic operation: Validates, compiles, executes hooks, and optionally persists graph."""
        start_time = time.perf_counter()
        context = CompilationContext(
            raw_input=manifest_input,
            raw_schemas=self.raw_schemas.copy(),
            schema_dir=self.schema_dir,
            schema_file_index=dict(self.schema_file_index),
            registry=self.registry,
        )

        with tracer.start_as_current_span("MetaCompiler.compile") as span:
            span.set_attribute("context.id", str(context.context_id))
            span.set_attribute("engine.has_db_session", session is not None)
            span.set_attribute("engine.stage_count", len(self._validation_stage_classes))

            logger.info(
                "Starting atomic compilation pass (Context ID: %s)",
                context.context_id,
                extra={
                    "event": "engine.compile_start",
                    "context_id": str(context.context_id),
                    "has_db_session": session is not None,
                },
            )

            try:
                # 1. Pre-Compilation Hooks
                for hook in self.hooks:
                    await hook.on_pre_compile(context)

                # 2. Stage Pipeline Execution (adapter-based self-healing included)
                self._run_sync_pipeline(context)

                # 3. Post-Compilation Hooks
                for hook in self.hooks:
                    await hook.on_post_compile(context)

                # 4. Optional Persistence
                if session and context.db_payload:
                    with tracer.start_as_current_span("MetaCompiler.persist_db") as db_span:
                        repo = WorkflowRepository(session)
                        context.record_id = await repo.save(context.db_payload)
                        db_span.set_attribute("record.id", str(context.record_id))
                        logger.info(
                            "Persisted workflow graph record '%s'",
                            context.record_id,
                            extra={
                                "event": "engine.persisted",
                                "record_id": str(context.record_id),
                                "context_id": str(context.context_id),
                            },
                        )

                        # 5. Post-Persistence Hooks
                        for hook in self.hooks:
                            await hook.on_persist(context)

                total_duration_ms = (time.perf_counter() - start_time) * 1000
                span.set_attribute("engine.total_duration_ms", total_duration_ms)
                logger.info(
                    "Atomic compilation successfully completed in %.2fms",
                    total_duration_ms,
                    extra={
                        "event": "engine.compile_success",
                        "total_duration_ms": total_duration_ms,
                        "context_id": str(context.context_id),
                    },
                )

                return context.to_compiled_graph()

            except Exception as err:
                total_duration_ms = (time.perf_counter() - start_time) * 1000
                span.record_exception(err)
                span.set_status(Status(StatusCode.ERROR, str(err)))
                logger.error(
                    "Compilation failed after %.2fms: %s",
                    total_duration_ms,
                    err,
                    exc_info=True,
                    extra={
                        "event": "engine.compile_failure",
                        "total_duration_ms": total_duration_ms,
                        "error": str(err),
                        "context_id": str(context.context_id),
                    },
                )
                await self._safe_execute_error_hooks(context, err)

                if isinstance(err, MetaCompilerError):
                    raise
                raise MetaCompilerError(
                    f"Compilation failed due to unexpected error: {err}"
                ) from err
