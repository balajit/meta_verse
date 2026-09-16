# file name: /meta-application-builder/src/meta_application_builder/services/build_service.py

from __future__ import annotations

import io
import uuid
from typing import Any, Dict, Optional

import structlog
from meta_application_builder.bcr_cas.cas_service.cas_storage import ContentAddressedStorage
from meta_application_builder.compiler_engine.brain_adapter.ir_sanitizer import IRSanitizer
from meta_application_builder.foundation.governance_rego.opa_evaluator import OPAEvaluator
from meta_application_builder.bcr_cas.bulk_api.publication_saga import ComponentManifest, ReservationRequest, SagaOrchestrator
from pydantic import BaseModel, ConfigDict, Field
from meta_application_builder.compiler_engine.meta_compiler.pydantic_emitter import PydanticEmitter
from meta_application_builder.compiler_engine.verification.ruff_mypy_runner import RuffMypyRunner
from sqlalchemy.ext.asyncio import AsyncSession
from meta_application_builder.compiler_engine.meta_compiler.sqlalchemy_emitter import SQLAlchemyEmitter
from meta_application_builder.compiler_engine.verification.temporal_validator import TemporalValidator
from meta_application_builder.bcr_cas.urn_resolver.urn_parser import ComponentURN

from meta_application_builder.config.config_bao import BuildServiceConfig
from meta_application_builder.control_plane.outbox.queue_envelope import (
    QueueEnvelope,
)
from meta_application_builder.control_plane.state_engine.state_machine import (
    BuildState,
    BuildStateMachine,
)
from meta_application_builder.persistence.audit.tamper_evident_ledger import (
    TamperEvidentLedger,
)

logger = structlog.get_logger(__name__)


class BuildJobRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    tenant_id: str
    actor: str
    blueprint_id: str
    spec_payload: Dict[str, Any]
    job_id: uuid.UUID = Field(default_factory=uuid.uuid4)


class BuildJobResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    job_id: uuid.UUID
    state: BuildState
    cas_digest: Optional[str] = None
    saga_id: Optional[str] = None
    error_message: Optional[str] = None


class BuildApplicationService:
    """Canonical control-plane orchestrator unifying compilation lifecycle steps."""

    def __init__(
            self,
            *,
            config: Optional[BuildServiceConfig] = None,
            cas_storage: Optional[ContentAddressedStorage] = None,
            saga_orchestrator: Optional[SagaOrchestrator] = None,
            opa_evaluator: Optional[OPAEvaluator] = None,
            audit_ledger: Optional[TamperEvidentLedger] = None,

    ) -> None:
        self.config = config or BuildServiceConfig()
        self.cas = cas_storage
        self.saga = saga_orchestrator or SagaOrchestrator()
        self.opa = opa_evaluator or OPAEvaluator()
        self.ledger = audit_ledger or TamperEvidentLedger()
        self._in_memory_jobs: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def from_config(cls, config: BuildServiceConfig) -> "BuildApplicationService":
        """Factory constructor instantiating component dependencies from configuration context."""
        return cls(
            config=config,
            # Pass downstream configs to sub-services if applicable:
            # opa_evaluator=OPAEvaluator(policy_uri=config.opa_policy_uri),
            # cas_storage=ContentAddressedStorage(storage_path=config.cas_path),
        )

    def _build_opa_payload(self, sanitized_ir: Any, spec_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Formats sanitized IR and raw payload attributes to match governance.rego contract."""
        model_name = getattr(sanitized_ir, "model_name", spec_payload.get("model_name", ""))
        fields = getattr(sanitized_ir, "fields", spec_payload.get("fields", []))

        if isinstance(fields, dict):
            fields = list(fields.keys())
        elif not isinstance(fields, list):
            fields = []

        raw_metadata = spec_payload.get("metadata", {})
        tier = raw_metadata.get("tier", "standard") if isinstance(raw_metadata, dict) else "standard"

        return {
            "model_name": model_name,
            "fields": fields,
            "metadata": {"tier": tier},
        }

    async def validate_spec(self, spec_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validates payload syntax, IR structural constraints, and OPA policy boundaries."""
        violations = []
        try:
            sanitized_ir = IRSanitizer.sanitize(spec_payload)
            opa_payload = self._build_opa_payload(sanitized_ir, spec_payload)
            policy_passed = await self.opa.evaluate("policies/governance.rego", opa_payload)
            if not policy_passed:
                violations.append("Governance policy evaluation failed via OPA.")
        except Exception as err:
            violations.append(str(err))

        return {
            "is_valid": len(violations) == 0,
            "violations": violations
        }

    async def submit_build(self, request: BuildJobRequest, session: Optional[AsyncSession] = None) -> BuildJobResult:
        """Executes full transaction-consistent compilation and publishing pipeline."""
        job_id_str = str(request.job_id)
        current_state = BuildState.QUEUED
        log = logger.bind(job_id=job_id_str, tenant_id=request.tenant_id, blueprint_id=request.blueprint_id)

        self._in_memory_jobs[job_id_str] = {
            "job_id": request.job_id,
            "state": current_state,
            "cas_digest": None,
            "saga_id": None,
        }

        try:
            # 1. Spec Governance & Policy Checks
            current_state = BuildStateMachine.transition(current_state, BuildState.ACQUIRED)
            current_state = BuildStateMachine.transition(current_state, BuildState.VALIDATING_SYNTAX)
            sanitized_ir = IRSanitizer.sanitize(request.spec_payload)

            current_state = BuildStateMachine.transition(current_state, BuildState.VALIDATING_POLICY)
            opa_payload = self._build_opa_payload(sanitized_ir, request.spec_payload)
            if not await self.opa.evaluate("policies/governance.rego", opa_payload):
                raise ValueError("OPA Governance Policy Violation")

            # 2. AST Synthesis
            current_state = BuildStateMachine.transition(current_state, BuildState.COMPILING_IR)
            current_state = BuildStateMachine.transition(current_state, BuildState.SYNTHESIZING_CODE)
            pydantic_code = PydanticEmitter.emit_model_code(sanitized_ir)
            orm_code = SQLAlchemyEmitter.emit_orm_code(sanitized_ir, table_name=sanitized_ir.model_name.lower())
            combined_code = f"{pydantic_code}\n\n{orm_code}"

            for line_no, line_content in enumerate(combined_code.splitlines(), start=1):
                logger.info("generated_code_line", line=line_no, content=line_content)

            # 3. Code Verification
            current_state = BuildStateMachine.transition(current_state, BuildState.VERIFYING_AST)
            TemporalValidator.validate_code_string(combined_code)
            await RuffMypyRunner.verify_code(combined_code)

            # 4. Packaging & CAS Persistence
            current_state = BuildStateMachine.transition(current_state, BuildState.PACKAGING)
            current_state = BuildStateMachine.transition(current_state, BuildState.PERSISTING_CAS)

            code_bytes = combined_code.encode("utf-8")
            cas_digest = None
            if self.cas:
                cas_digest = self.cas.store(io.BytesIO(code_bytes))
            else:
                import hashlib
                cas_digest = hashlib.sha256(code_bytes).hexdigest()

            # 5. BCR Publishing Saga
            current_state = BuildStateMachine.transition(current_state, BuildState.PUBLISHING_BCR)
            urn_str = f"urn:meta:bcr:{request.tenant_id}:blueprint:{request.blueprint_id}:1.0.0"
            urn = ComponentURN.from_string(urn_str)
            manifest = ComponentManifest(urn=urn, sha256=cas_digest, size_bytes=len(code_bytes))
            saga_id = self.saga.reserve_batch(ReservationRequest(manifests=[manifest]))
            self.saga.commit_saga(saga_id)

            # 6. Audit Logging & Outbox Event Dispatch
            current_state = BuildStateMachine.transition(current_state, BuildState.COMPLETED)
            event_payload = {"job_id": job_id_str, "status": "SUCCESS", "cas_digest": cas_digest}

            if session:
                await self.ledger.append_event(
                    session=session,
                    tenant_id=request.tenant_id,
                    event_type="BUILD_COMPLETED",
                    actor=request.actor,
                    payload=event_payload,
                    job_id=job_id_str
                )

            envelope = QueueEnvelope.create_with_trace_context(
                event_type="build.completed",
                tenant_id=request.tenant_id,
                job_id=job_id_str,
                saga_id=saga_id,
                payload=event_payload
            )

            self._in_memory_jobs[job_id_str].update({
                "state": current_state,
                "cas_digest": cas_digest,
                "saga_id": saga_id
            })

            log.info("build_pipeline_completed_successfully", cas_digest=cas_digest)
            return BuildJobResult(job_id=request.job_id, state=current_state, cas_digest=cas_digest, saga_id=saga_id)

        except Exception as err:
            log.error("build_pipeline_failed", error=str(err))
            self._in_memory_jobs[job_id_str]["state"] = BuildState.FAILED
            return BuildJobResult(job_id=request.job_id, state=BuildState.FAILED, error_message=str(err))

    def get_status(self, job_id: uuid.UUID) -> Dict[str, Any]:
        job_info = self._in_memory_jobs.get(str(job_id))
        if not job_info:
            return {"job_id": str(job_id), "state": "NOT_FOUND"}
        return {"job_id": str(job_id),
                "state": job_info["state"].value if isinstance(job_info["state"], BuildState) else job_info["state"]}

    def get_artifact(self, job_id: uuid.UUID) -> Dict[str, Any]:
        job_info = self._in_memory_jobs.get(str(job_id))
        if not job_info or not job_info.get("cas_digest"):
            return {"job_id": str(job_id), "cas_pointer": None, "error": "Artifact not found"}
        return {
            "job_id": str(job_id),
            "cas_pointer": job_info["cas_digest"],
            "provenance_metadata": {"builder_version": "1.0.0", "saga_id": job_info.get("saga_id")}
        }