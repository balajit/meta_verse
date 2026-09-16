#!/usr/bin/env python3
"""
End-to-End Integration Test Driver with Explicit Verification Engine
-------------------------------------------------------------------
Executes compilation, CAS persistence, gateway routing, and fencing while
running deep structural, cryptographic, and state invariant assertions.
"""
import ast
import asyncio
import hashlib
import json
import sys
import tempfile
import uuid
from pathlib import Path

from meta_application_builder.experience.cli_tool.execution_gateway import (
    CLIExecutionGateway,
    ExecutionMode,
)

from meta_application_builder.control_plane.state_engine.dual_lock_fencing import (
    DualLockFencing,
    StaleWorkerError,
    WorkerFenceToken,
)
from meta_application_builder.control_plane.state_engine.state_machine import (
    BuildState,
    InvalidStateTransitionError,
)

from meta_application_builder.bcr_cas.bulk_api.publication_saga import SagaOrchestrator
from meta_application_builder.bcr_cas.bulk_api.resolve_batch import (
    BatchResolutionRequest,
    BatchResolver,
)
from meta_application_builder.bcr_cas.cas_service.cas_storage import (
    CASConfig,
    ContentAddressedStorage,
)
from meta_application_builder.bcr_cas.exceptions import InvalidTransitionError
from meta_application_builder.bcr_cas.urn_resolver.lifecycle_state import (
    ComponentLifecycle,
    LifecycleState,
)
from meta_application_builder.bcr_cas.urn_resolver.urn_parser import ComponentURN
from meta_application_builder.compiler_engine.brain_adapter.ir_sanitizer import (
    IRSanitizer,
)
from meta_application_builder.compiler_engine.validation.payload_guard import (
    PayloadGuard,
)
from meta_application_builder.control_plane.services.build_application_service import (
    BuildApplicationService,
    BuildJobRequest,
)

# Subsystem Imports

SPEC_FILE = Path("complex_spec.json")


def verify_ir_schema(sanitized_ir, original_payload: dict) -> None:
    """Verifies that the sanitized IR matches schema constraints and types."""
    print("  [VERIFY] IR Field Definitions & Metadata Invariants...")
    expected_fields = {f["name"]: f for f in original_payload["fields"]}
    assert len(sanitized_ir.fields) == len(expected_fields), (
        f"Field count mismatch: expected {len(expected_fields)}, got {len(sanitized_ir.fields)}"
    )

    for field in sanitized_ir.fields:
        assert field.name in expected_fields, f"Unexpected field '{field.name}' in IR"
        exp = expected_fields[field.name]
        assert str(field.type_hint) == exp["type_hint"], (
            f"Type mismatch for {field.name}: {field.type_hint} != {exp['type_hint']}"
        )
        assert field.nullable == exp["nullable"], f"Nullability mismatch for {field.name}"
        assert field.default == exp["default"], f"Default value mismatch for {field.name}"

    assert sanitized_ir.metadata["domain"] == original_payload["metadata"]["domain"]
    print("  ✓ IR Schema Verification: PASSED")


def verify_cas_persistence(cas_storage: ContentAddressedStorage, digest: str) -> None:
    """Verifies physical file presence and cryptographic integrity in CAS."""
    print("  [VERIFY] Cryptographic Hash & CAS File Structure...")
    blob_path = cas_storage.get_blob_path(digest)
    assert blob_path.exists(), f"CAS blob file missing at path: {blob_path}"

    content = blob_path.read_bytes()
    computed_hash = hashlib.sha256(content).hexdigest()
    assert computed_hash == digest, (
        f"CAS Hash corruption! Expected {digest}, computed {computed_hash}"
    )

    # Decode stored bytes into Python source string
    source_code = content.decode("utf-8")

    # Validate valid Python AST syntax instead of JSON parsing
    parsed_ast = ast.parse(source_code)
    assert parsed_ast is not None, "Failed to parse AST from stored CAS code"
    print(f"  ✓ CAS Storage Verification (SHA256={digest[:12]}...): PASSED")


def verify_lifecycle_fencing_safety() -> None:
    """Verifies state machine invalid transitions and worker fencing rejects."""
    print("  [VERIFY] Negative Testing: Invalid Transitions & Fence Rejections...")

    # 1. State Machine Boundary Check
    lifecycle = ComponentLifecycle(current_state=LifecycleState.DRAFT)
    try:
        lifecycle.transition(LifecycleState.ARCHIVED)  # Direct DRAFT -> ARCHIVED illegal
        assert False, "Failed to reject illegal lifecycle transition"
    except InvalidStateTransitionError:
        print("    ✓ Caught expected InvalidStateTransition exception.")
    except InvalidTransitionError:
        print("    ✓ Caught expected InvalidTransition exception.")

    # 2. Dual-Lock Fencing Rejection Check (Stale Worker Token)
    active_token = WorkerFenceToken(worker_id="worker_active", lease_generation=3, version_id=10)
    stale_token = WorkerFenceToken(worker_id="worker_stale", lease_generation=2, version_id=9)


    try:
        is_valid = DualLockFencing.verify_fence(current=stale_token, recorded=active_token)
        assert is_valid is False, "Dual-Lock Fencing allowed a stale worker fence token!"
    except StaleWorkerError:
        print("    ✓ Stale worker lease fence correctly rejected.")

    print("    ✓ Stale worker lease fence correctly rejected.")

    print("  ✓ Negative Safety Verification: PASSED")


async def main() -> None:
    print("============================================================")
    print(" Starting Meta Application Builder System Integration Test ")
    print("============================================================")

    if not SPEC_FILE.exists():
        print(f"Error: Required payload spec file '{SPEC_FILE}' was not found.")
        sys.exit(1)

    # 1. Payload Guard & IR Sanitization + Verification
    print("\n[1/7] Testing Payload Guard & IR Sanitizer...")
    raw_bytes = SPEC_FILE.read_bytes()
    guard = PayloadGuard()
    raw_payload = guard.inspect_json_payload(raw_bytes)
    sanitized_ir = IRSanitizer.sanitize(raw_payload)
    verify_ir_schema(sanitized_ir, raw_payload)

    # 2. Storage & Service Orchestration
    print("\n[2/7] Initializing Storage & Orchestration Engine...")
    with tempfile.TemporaryDirectory() as tmpdir:
        cas = ContentAddressedStorage(CASConfig(storage_root=Path(tmpdir)))
        saga = SagaOrchestrator()
        service = BuildApplicationService(cas_storage=cas, saga_orchestrator=saga)

        # 3. Control Plane Build Submission + CAS Verification
        print("\n[3/7] Submitting Build Job & Verifying CAS Integrity...")
        job_req = BuildJobRequest(
            tenant_id="tenant_alpha",
            actor="usr_test_runner",
            blueprint_id="auth-engine",
            spec_payload=raw_payload,
        )
        result = await service.submit_build(job_req)
        if result.state != BuildState.COMPLETED:
            print(f"❌ Build Failed Error: {result.error_message}")

        assert result.state.value == "COMPLETED", f"Build failed: {result.state}"
        assert result.cas_digest is not None, "Missing CAS digest in build result"
        assert result.saga_id is not None, "Missing Saga ID in build result"

        # Explicit CAS file hash check
        verify_cas_persistence(cas, result.cas_digest)

        # 4. Gateway Dispatch Verification
        print("\n[4/7] Verifying Gateway Execution Dispatch & Idempotency...")
        gateway = CLIExecutionGateway(mode=ExecutionMode.DIRECT, service=service)
        idempotency_key = str(uuid.uuid4())

        res_a = await gateway.execute_build(
            tenant_id="tenant_alpha",
            actor="usr_test_runner",
            blueprint_id="auth-engine",
            spec_payload=raw_payload,
            idempotency_key=idempotency_key,
        )
        assert res_a["state"] == "COMPLETED", "First gateway dispatch failed"
        assert res_a["cas_digest"] == result.cas_digest, "Digest mismatch on gateway build"
        print("  ✓ CLI Execution Gateway Direct Mode verified.")

        # 5. Lifecycle & Negative Invariant Verifications
        print("\n[5/7] Verifying State Transitions & Dual-Lock Safety...")
        verify_lifecycle_fencing_safety()

        # 6. URN & DAG Resolution Verification
        print("\n[6/7] Verifying URN Formatting & DAG Resolution Integrity...")
        urn = ComponentURN.from_string("urn:meta:bcr:tenant_alpha:blueprint:auth-engine:1.0.0")
        assert urn.tenant == "tenant_alpha"
        assert urn.component_type == "blueprint"
        assert urn.name == "auth-engine"
        assert urn.version == "1.0.0"

        res_req = BatchResolutionRequest(root_urns=[urn], allow_deprecated=True)
        resolved_nodes = BatchResolver.resolve_dag(res_req)
        assert len(resolved_nodes) == 1, "DAG engine returned invalid node count"
        assert str(resolved_nodes[0]) == str(urn), "Resolved node URN mismatch"
        print(f"  ✓ URN ({urn}) & Dependency DAG verified.")

        # 7. Dual-Lock Fencing Positive Verification
        print("\n[7/7] Verifying Valid Dual-Lock Worker Fencing...")
        worker_lease = WorkerFenceToken(worker_id="w1", lease_generation=5, version_id=12)
        fencing_valid = DualLockFencing.verify_fence(worker_lease, worker_lease)
        assert fencing_valid is True, "Valid fence verification failed unexpectedly"
        print("  ✓ Active Worker Fence verified.")

    print("\n============================================================")
    print(" ALL VERIFICATION STEPS AND SYSTEM INTEGRATION TESTS PASSED ")
    print("============================================================")


if __name__ == "__main__":
    asyncio.run(main())