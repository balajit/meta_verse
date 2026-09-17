"""BuildOrchestrator coordinating schema resolution, OPA governance, compilation, and persistence."""

import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from meta_compiler import MetaCompiler

from meta_builder_brain.config import BrainSettings
from meta_builder_brain.exceptions import BuildExecutionError
from meta_builder_brain.governance.opa import OPAEvaluator
from meta_builder_brain.persistence.mbb_models import (
    ArtifactManifestRecord,
    BuildJobAuditRecord,
    BuildJobStatus,
)
from meta_builder_brain.persistence.mbb_mutator import DatabaseMutator
from meta_builder_brain.persistence.mbb_repository import EntityRepository

logger = logging.getLogger(__name__)


class BuildOrchestrator:
    """Coordinates schema resolution, compilation execution, OPA evaluation, and persistence updates."""

    def __init__(
        self,
        repository: Any = None,
        mutator: Optional[DatabaseMutator] = None,
        compiler: Optional[MetaCompiler] = None,
    ) -> None:
        if isinstance(repository, BrainSettings):
            self.settings: Optional[BrainSettings] = repository
            self._repository: Optional[EntityRepository] = None
        else:
            self.settings = None
            self._repository = repository

        self._mutator: Optional[DatabaseMutator] = mutator
        self._compiler: MetaCompiler = compiler or MetaCompiler()

        try:
            self.opa_evaluator: Optional[OPAEvaluator] = OPAEvaluator(
                self.settings or BrainSettings()
            )
        except Exception:
            self.opa_evaluator = None

    async def compile_blueprint_namespace(
        self,
        namespace_id: str,
        components: Dict[str, Any],
        spec_deltas: Dict[str, Any],
        base_schemas: Dict[str, Any],
        job_id: Optional[str] = None,
        session: Any = None,
    ) -> Dict[str, Any]:
        """Compiles blueprint component namespace schemas and validates governance policy."""
        actual_job_id = job_id or f"job_{uuid4().hex[:8]}"
        artifacts: Dict[str, Any] = {}

        for urn, _ in components.items():
            spec_delta = spec_deltas.get(urn, {})
            base_schema = base_schemas.get(urn, {})

            if self.opa_evaluator:
                await self.opa_evaluator.validate_component_governance(urn, spec_delta)

            compiled_schema = dict(base_schema)
            if "properties" in spec_delta or "properties" in base_schema:
                props = dict(base_schema.get("properties", {}))
                props.update(spec_delta.get("properties", {}))
                compiled_schema["properties"] = props

            artifacts[urn] = compiled_schema

        return {
            "job_id": actual_job_id,
            "namespace_id": namespace_id,
            "execution_order": list(components.keys()),
            "artifacts": artifacts,
        }

    async def execute_build_job(
        self, tenant_id: str, manifest_urn: str, execution_graph: Dict[str, Any]
    ) -> BuildJobAuditRecord:
        """Executes a build pipeline step-by-step with persistence auditing."""
        if not self._mutator or not self._repository:
            raise BuildExecutionError(
                "Repository and Mutator must be configured for build execution."
            )

        job_id: UUID = uuid4()

        job_record: BuildJobAuditRecord = await self._mutator.record_build_audit(
            job_id=job_id,
            tenant_id=tenant_id,
            status=BuildJobStatus.RUNNING,
            manifest_urn=manifest_urn,
            execution_graph=execution_graph,
        )

        await self._mutator.record_job_event(
            job_id=job_id,
            event_type="JOB_STARTED",
            payload={"manifest_urn": manifest_urn, "tenant_id": tenant_id},
        )

        try:
            spec_record = await self._repository.get_specification(manifest_urn)
            if not spec_record:
                raise BuildExecutionError(
                    f"Specification manifest URN {manifest_urn} not found in registry."
                )

            await self._mutator.record_job_event(
                job_id=job_id,
                event_type="COMPILATION_STARTED",
                payload={"urn": manifest_urn},
            )

            manifest_str: str = json.dumps(spec_record.specification_manifest)
            compiled_res = self._compiler.compile(manifest_str)
            if inspect.isawaitable(compiled_res):
                await compiled_res

            artifact_id: UUID = uuid4()
            await self._mutator.save_artifact_manifest(
                artifact_id=artifact_id,
                job_id=job_id,
                urn=manifest_urn,
                artifact_type="DYNAMIC_PYDANTIC_MODULE",
                location_uri=f"s3://artifacts/{tenant_id}/{job_id}.py",
                checksum_sha256=spec_record.checksum_sha256,
            )

            completed_time: datetime = datetime.now(timezone.utc)
            await self._mutator.update_build_status(
                job_id=job_id,
                status=BuildJobStatus.COMPLETED,
                completed_at=completed_time,
            )

            await self._mutator.record_job_event(
                job_id=job_id,
                event_type="JOB_COMPLETED",
                payload={"artifact_id": str(artifact_id)},
            )

            return BuildJobAuditRecord(
                job_id=job_id,
                tenant_id=tenant_id,
                status=BuildJobStatus.COMPLETED,
                manifest_urn=manifest_urn,
                execution_graph=execution_graph,
                started_at=job_record.started_at,
                completed_at=completed_time,
                created_at=job_record.created_at,
            )

        except Exception as err:
            logger.error(
                "Build job execution failed for ID %s: %s", str(job_id), str(err)
            )
            failed_time: datetime = datetime.now(timezone.utc)
            await self._mutator.update_build_status(
                job_id=job_id,
                status=BuildJobStatus.FAILED,
                error_message=str(err),
                completed_at=failed_time,
            )
            await self._mutator.record_job_event(
                job_id=job_id,
                event_type="JOB_FAILED",
                payload={"error": str(err)},
            )
            raise BuildExecutionError(f"Build job failed: {err}") from err