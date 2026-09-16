import io

import pytest

from meta_application_builder.bcr_cas.bulk_api.publication_saga import (
    ComponentManifest,
    ReservationRequest,
    SagaOrchestrator,
)
from meta_application_builder.bcr_cas.bulk_api.resolve_batch import (
    BatchResolutionRequest,
    BatchResolver,
)
from meta_application_builder.bcr_cas.cas_service.cas_storage import (
    CASConfig,
    ContentAddressedStorage,
)
from meta_application_builder.bcr_cas.cas_service.digest_verifier import (
    StreamDigestVerifier,
)
from meta_application_builder.bcr_cas.exceptions import (
    DigestVerificationError,
    InvalidTransitionError,
    InvalidURNError,
)
from meta_application_builder.bcr_cas.urn_resolver.lifecycle_state import (
    ComponentLifecycle,
    LifecycleState,
)
from meta_application_builder.bcr_cas.urn_resolver.urn_parser import ComponentURN


def test_urn_parsing():
    valid = "urn:meta:bcr:my-tenant:blueprint:core-engine:1.0.0"
    parsed = ComponentURN.from_string(valid)
    assert parsed.tenant == "my-tenant"
    assert parsed.version == "1.0.0"
    assert parsed.to_string() == valid

    with pytest.raises(InvalidURNError):
        ComponentURN.from_string("urn:invalid:format")


def test_lifecycle_transitions():
    lifecycle = ComponentLifecycle()
    assert lifecycle.current_state == LifecycleState.DRAFT
    lifecycle.transition(LifecycleState.ACTIVE)
    assert lifecycle.current_state == LifecycleState.ACTIVE

    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(LifecycleState.DRAFT)


def test_digest_verification():
    content = b"hello world c-store"
    stream = io.BytesIO(content)
    digest = StreamDigestVerifier.hash_stream(stream)

    stream2 = io.BytesIO(content)
    assert StreamDigestVerifier.verify(digest, stream2) is True

    stream3 = io.BytesIO(b"tampered content")
    with pytest.raises(DigestVerificationError):
        StreamDigestVerifier.verify(digest, stream3)


def test_cas_storage(tmp_path):
    config = CASConfig(storage_root=tmp_path / "cas")
    cas = ContentAddressedStorage(config)

    data = b"binary artifact stream payload"
    digest = cas.store(io.BytesIO(data))

    retrieved_stream = cas.retrieve(digest)
    assert retrieved_stream.read() == data


def test_batch_resolver():
    root = ComponentURN.from_string("urn:meta:bcr:alpha:blueprint:app:1.0.0")
    dep = ComponentURN.from_string("urn:meta:bcr:alpha:lib:common:1.0.0")

    req = BatchResolutionRequest(
        root_urns=[root],
        dependency_map={root.to_string(): [dep]}
    )
    resolved = BatchResolver.resolve_dag(req)
    assert len(resolved) == 2
    assert resolved[0].name == "common"
    assert resolved[1].name == "app"


def test_publication_saga():
    orchestrator = SagaOrchestrator()
    urn = ComponentURN.from_string("urn:meta:bcr:alpha:blueprint:app:1.0.0")
    manifest = ComponentManifest(urn=urn, sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                                 size_bytes=100)
    req = ReservationRequest(saga_id="saga-test-1", manifests=[manifest])

    sid = orchestrator.reserve_batch(req)
    assert sid == "saga-test-1"
    assert orchestrator.commit_saga(sid) is True